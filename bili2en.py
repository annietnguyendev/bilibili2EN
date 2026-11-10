"""
bili2en.py - Bilibili URL / local video -> English .srt, then opens in VLC.

Usage:
  python bili2en.py URL                 # audio mode (speech -> English)
  python bili2en.py URL --ocr           # also read burned-in Chinese text
  python bili2en.py URL --llm           # best quality: local Qwen via Ollama
  python bili2en.py URL --replace --llm # English drawn over burned-in Chinese
  python bili2en.py URL --hybrid --audio-lang ja  # Chinese subs + Japanese audio
  add --provider deepinfra to use cloud models (needs DEEPINFRA_API_KEY)
  python bili2en.py --list urls.txt     # batch: one URL per line
"""
import argparse, os, re, subprocess, sys, shutil
from pathlib import Path

from show import work as _work   # downloads land in <root>/_Work first
BROWSER = None  # e.g. "chrome" or "safari": reuse your Bilibili login cookies


# Bilibili's "mirrorcosov" CDN is behind a Tencent firewall that returns
# HTTP 567 to downloaders (yt-dlp issue #17847). Swap it for other mirrors.
ALT_HOSTS = [None, "upos-sz-mirroraliov.bilivideo.com",
             "upos-sz-mirrorhw.bilivideo.com", "upos-sz-mirrorali.bilivideo.com",
             "upos-sz-mirrorcos.bilivideo.com"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


MAX_HEIGHT = 1080   # 1080 needs a Bilibili login (--browser chrome); higher needs VIP


def download(url, dest_dir=None):
    import copy, yt_dlp
    from urllib.parse import urlsplit, urlunsplit
    opts = {
        "http_headers": {"Referer": "https://www.bilibili.com/",
                         "User-Agent": UA},
        "retries": 3, "fragment_retries": 3,
        "format": f"bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]/b",
        "format_sort": ["res", "tbr"],   # best size first, then highest bitrate
        "merge_output_format": "mp4",
        "noplaylist": True,          # a ?p= link gets only that part, not the whole series
        "outtmpl": str(Path(dest_dir or _work()) / "%(id)s.%(ext)s"),
        "quiet": True,
    }
    if BROWSER:
        opts["cookiesfrombrowser"] = (BROWSER,)
    # Send Range headers like a real player (the backup CDN wants them).
    opts["http_chunk_size"] = 10 * 1024 * 1024
    # Look like real Chrome at the TLS level, but ONLY for the file download.
    # (Impersonating during page/API extraction makes Bilibili return no formats.)
    dl_opts = dict(opts)
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget
        dl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
        print("  impersonating Chrome for the download (curl_cffi found)")
    except ImportError:
        print("  WARNING: curl_cffi not installed; run: "
              'pip install "yt-dlp[default,curl-cffi]"')

    def swap(u, host):
        if not host:
            return u
        parts = urlsplit(u)
        if "bilivideo.com" in parts.netloc or "akamaized" in parts.netloc:
            return urlunsplit(parts._replace(netloc=host))
        return u

    with yt_dlp.YoutubeDL(opts) as ex:          # normal: read the page/API
        info = ex.extract_info(url, download=False)
    with yt_dlp.YoutubeDL(dl_opts) as ydl:      # Chrome-like: fetch the file
        target = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
        last = None
        for host in ALT_HOSTS:
            if target.exists():
                return target
            trial = copy.deepcopy(info)
            for f in trial.get("formats", []):
                if f.get("url"):
                    f["url"] = swap(f["url"], host)
            print(f"  trying CDN: {host or 'default'}")
            try:
                ydl.process_ie_result(trial, download=True)
            except Exception as e:
                last = e
                continue
            if target.exists():
                return target
        raise RuntimeError(f"all CDN mirrors failed: {last}")


def ts(sec):
    h, r = divmod(sec, 3600); m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"


LLM_MODEL = "qwen2.5:14b"
PROVIDER = "ollama"
ENDPOINTS = {
    "ollama": "http://localhost:11434/api/generate",
    "deepinfra": "https://api.deepinfra.com/v1/openai/chat/completions",
}


def chat_json(prompt):
    """Send prompt to Ollama or OpenAI-compatible endpoint; return parsed JSON."""
    import json, urllib.request
    headers = {"Content-Type": "application/json"}
    if PROVIDER == "deepinfra":
        headers["Authorization"] = "Bearer " + os.environ["DEEPINFRA_API_KEY"]
        body = json.dumps({
            "model": LLM_MODEL, "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(ENDPOINTS[PROVIDER], data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=600) as r:
            text = json.load(r)["choices"][0]["message"]["content"]
    else:
        body = json.dumps({
            "model": LLM_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.2}
        }).encode()
        req = urllib.request.Request(ENDPOINTS[PROVIDER], data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=600) as r:
            text = json.load(r).get("response", "")

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def llm_translate(zh_lines, model=None, batch=20):
    """Translate with context using local Ollama model."""
    import json
    model = model or LLM_MODEL
    out = []
    for i in range(0, len(zh_lines), batch):
        chunk = zh_lines[i:i + batch]
        prompt = (
            "You are translating TV subtitles from Chinese.\n"
            "Translate each dialogue line into natural, concise English TV subtitles.\n\n"
            "Reply with JSON only: {\"lines\": [...]} containing exactly "
            f"{len(chunk)} English strings in order.\n"
            f"Previous English lines (context): {json.dumps(out[-5:], ensure_ascii=False)}\n"
            f"Lines: {json.dumps(chunk, ensure_ascii=False)}")
        try:
            arr = chat_json(prompt).get("lines", [])
        except Exception as e:
            print(f"  translate batch {i} failed: {e}")
            arr = []
        arr = [str(x) for x in arr][:len(chunk)]
        out += arr + chunk[len(arr):]
    return out


AUDIO_LANG = "zh"


def audio_to_english(video, model_size, llm):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    task = "transcribe" if llm else "translate"
    segs, _ = model.transcribe(
        str(video), language=AUDIO_LANG, task=task, vad_filter=True,
        initial_prompt="以下是普通话的视频字幕。" if AUDIO_LANG == "zh" else None)
    segs = list(segs)
    texts = [s.text.strip() for s in segs]
    if llm:
        texts = llm_translate(texts)
    return [(s.start, s.end, t) for s, t in zip(segs, texts)]


def ocr_to_english(video, llm, tag=True):
    from videocr import get_subtitles
    from deep_translator import GoogleTranslator
    srt = get_subtitles(str(video), lang="chi_sim",
                        sim_threshold=70, conf_threshold=65)
    blocks = re.findall(
        r"(\d\d:\d\d:\d\d,\d+) --> (\d\d:\d\d:\d\d,\d+)\n(.+?)(?:\n\n|\Z)",
        srt, re.S)
    zh = [b[2].replace(" ", "").strip() for b in blocks]
    if llm:
        en = llm_translate(zh) if zh else []
    else:
        tr = GoogleTranslator(source="zh-CN", target="en")
        en = tr.translate_batch(zh) if zh else []

    def secs(t):
        h, m, rest = t.split(":"); s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    pre = "[on-screen] " if tag else ""
    return [(secs(a), secs(b), f"{pre}{e}")
            for (a, b, _), e in zip(blocks, en) if e]


def ocr_raw(video):
    """Burned-in Chinese lines with their on-screen timing."""
    from videocr import get_subtitles
    srt = get_subtitles(str(video), lang="chi_sim",
                        sim_threshold=70, conf_threshold=65)
    blocks = re.findall(
        r"(\d\d:\d\d:\d\d,\d+) --> (\d\d:\d\d:\d\d,\d+)\n(.+?)(?:\n\n|\Z)",
        srt, re.S)

    def secs(t):
        h, m, rest = t.split(":"); s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    return [(secs(a), secs(b), z.replace(" ", "").strip())
            for a, b, z in blocks]


def hybrid_to_english(video, model_size):
    """Chinese subs (timing + meaning) + audio transcript (original words)."""
    import json
    from faster_whisper import WhisperModel
    cues = ocr_raw(video)
    print(f"  {len(cues)} on-screen lines; transcribing audio...")
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    segs = [(s.start, s.end, s.text.strip()) for s in model.transcribe(
        str(video), language=AUDIO_LANG, task="transcribe",
        vad_filter=True)[0]]
    items = []
    for a, b, zh in cues:
        heard = " ".join(t for s0, s1, t in segs
                         if s0 < b + 0.3 and s1 > a - 0.3)
        items.append({"zh": zh, "speech": heard})
    out = []
    for i in range(0, len(items), 15):
        chunk = items[i:i + 15]
        prompt = (
            "You are translating TV subtitles.\n"
            "Translate each dialogue item into natural, concise English TV subtitles.\n\n"
            "Translation Protocol:\n"
            "1. Base your English sentence primarily on 'zh' (Chinese fan subtitle) for complete grammar and comedic timing.\n"
            "2. Cross-reference 'speech' (spoken transcript) to lock in exact character names and places.\n"
            "3. Never output options or explanations (no 'or', no slashes). Return one natural line.\n"
            "4. Reply with JSON only: {\"lines\": [...]} containing exactly "
            f"{len(chunk)} strings in order.\n\n"
            f"Context: {json.dumps(out[-5:], ensure_ascii=False)}\n"
            f"Items: {json.dumps(chunk, ensure_ascii=False)}"
        )
        try:
            arr = chat_json(prompt).get("lines", [])
        except Exception as e:
            print(f"  batch {i} failed: {e}")
            arr = []
        arr = [str(x) for x in arr][:len(chunk)]
        out += arr + [c["zh"] for c in chunk[len(arr):]]
    return [(a, b, e) for (a, b, _), e in zip(cues, out) if e]


def write_srt(lines, path):
    lines.sort(key=lambda x: x[0])
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, t) in enumerate(lines, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n")


def video_size(video):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0",
         str(video)], text=True)
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def ass_time(sec):
    h, r = divmod(sec, 3600); m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02}:{s:05.2f}"


def write_ass(lines, path, w, h, plain=False):
    """plain=True: outlined text, no black box (for videos with no burned-in subs)."""
    fs, mv, ml = int(h * 0.055), int(h * 0.035), int(w * 0.08)
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + (f"Style: Cover,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,"
           f"&H80000000,1,0,0,0,100,100,0,0,1,{max(2, int(fs*0.08))},1,2,"
           f"{ml},{ml},{mv},1\n\n" if plain else
           f"Style: Cover,Arial,{fs},&H00FFFFFF,&H000000FF,&H00000000,"
           f"&H00000000,1,0,0,0,100,100,0,0,3,{int(fs*0.35)},0,2,"
           f"{ml},{ml},{mv},1\n\n")
        +
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, "
        "MarginR, MarginV, Effect, Text\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for a, b, t in sorted(lines):
            t = t.replace("\n", " ").replace("{", "(").replace("}", ")")
            f.write(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cover,,"
                    f"0,0,0,,{t}\n")


def burn(video, ass):
    out = video.with_name(video.stem + "_EN.mp4")
    vf = f"subtitles={ass.name}"
    subprocess.run(["ffmpeg", "-y", "-i", video.name, "-filter_complex", vf,
                    "-c:a", "copy", out.name], cwd=video.parent, check=True)
    return out


def open_vlc(video):
    vlc = shutil.which("vlc") or r"C:\Program Files\VideoLAN\VLC\vlc.exe"
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "VLC", str(video)])
    elif os.path.exists(vlc):
        subprocess.Popen([vlc, str(video)])


def clean_url(url):
    m = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not m:
        return url
    p = re.search(r"[?&]p=(\d+)", url)
    return f"https://www.bilibili.com/video/{m.group(1)}/" + (
        f"?p={p.group(1)}" if p else "")


def run(url, ocr, model_size, play, llm, replace=False, hybrid=False):
    local = Path(os.path.expanduser(url))
    if local.is_file():
        video = local
        print(f"Using local video file: {video}")
    else:
        url = clean_url(url)
        print(f"Downloading {url}")
        video = download(url)

    if replace:
        print("Reading burned-in Chinese + translating...")
        lines = (hybrid_to_english(video, model_size) if hybrid
                 else ocr_to_english(video, llm, tag=False))
        ass = video.with_suffix(".ass")
        write_ass(lines, ass, *video_size(video))
        write_srt(list(lines), video.with_suffix(".srt"))
        print("Burning English over the Chinese...")
        out = burn(video, ass)
        print(f"Done: {out}")
        if play:
            open_vlc(out)
        return
    print("Speech -> English...")
    lines = audio_to_english(video, model_size, llm)
    if ocr:
        print("Reading burned-in text...")
        lines += ocr_to_english(video, llm)
    srt = video.with_suffix(".srt")
    write_srt(lines, srt)
    print(f"Done: {srt}")
    if play:
        open_vlc(video)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("url", nargs="?")
    p.add_argument("--list")
    p.add_argument("--ocr", action="store_true")
    p.add_argument("--model", default="large-v3")
    p.add_argument("--llm", action="store_true",
                   help="context-aware translation with local Ollama model")
    p.add_argument("--browser", default=None,
                   help="load Bilibili login cookies from chrome/safari/firefox")
    p.add_argument("--provider", default="ollama",
                   choices=["ollama", "deepinfra"])
    p.add_argument("--llm-model", default=None,
                   help="Ollama model, e.g. qwen2.5:7b or qwen2.5:14b")
    p.add_argument("--no-play", action="store_true")
    p.add_argument("--hybrid", action="store_true",
                   help="with --replace: use subtitles AND audio together")
    p.add_argument("--audio-lang", default="zh",
                   help="spoken language for Whisper: zh, ja, ko")
    p.add_argument("--replace", action="store_true",
                   help="cover burned-in Chinese with English, same timing")
    a = p.parse_args()
    BROWSER = a.browser
    PROVIDER = a.provider
    LLM_MODEL = a.llm_model or (
        "Qwen/Qwen3.5-27B" if PROVIDER == "deepinfra" else "qwen2.5:14b")
    if a.provider == "deepinfra":
        a.llm = True
        if not os.environ.get("DEEPINFRA_API_KEY"):
            sys.exit("Set DEEPINFRA_API_KEY first.")
    AUDIO_LANG = a.audio_lang
    urls = ([u.strip() for u in open(a.list) if u.strip()]
            if a.list else [a.url])
    for u in urls:
        try:
            run(u, a.ocr, a.model, play=not a.no_play and not a.list,
                llm=a.llm, replace=a.replace or a.hybrid,
                hybrid=a.hybrid)
        except Exception as e:
            print(f"FAILED {u}: {e}")
