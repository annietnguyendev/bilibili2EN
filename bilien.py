"""
bilien.py - the whole workflow for any show. Everything goes in the BiliEN folder
($BILIEN_ROOT, default ~/BiliEN):

  1. download the video with burned-in Chinese  -> <Show> - Chinese Sub (raw)/
  2. read the Chinese + listen to the audio      -> _Work/
  3. translate to English                        -> <Show> - Subtitle Files/
  4. burn the English onto the video             -> <Show> - English Sub/

  python3 bilien.py "https://www.bilibili.com/video/BV.../?p=3" --show "My Show"
  python3 bilien.py "URL" --show "My Show" --ep 12      # save as episode 12 (default: the ?p= number)
  python3 bilien.py --list urls.txt --show "My Show"    # one URL per line, optional episode after it
  python3 bilien.py 2-10 --show "My Show"               # process episodes already downloaded
  python3 bilien.py all                                 # (--show can be left out if there is only one show)

  --force       redo episodes that already have an English video
  --audio-only  video has NO Chinese subs: translate from the spoken audio instead
                (or set "audio_only": true in _Work/<Show> profile.json)
                Input file can be named "<Show> EP01 (raw).mp4" or "(CN sub).mp4".
"""
import argparse, re, shutil, subprocess, sys, time
from pathlib import Path
from show import pick_show, index_add

HERE = Path(__file__).resolve().parent


def log(show, msg):
    print(msg)
    with open(show.work_dir / "run_all.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def step(show, script, ep, *extra):
    cmd = [sys.executable, str(HERE / script), str(ep), "--show", show.name, *extra]
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    out = p.stdout + p.stderr
    with open(show.work_dir / "run_all.log", "a", encoding="utf-8") as f:
        f.write(out)
    for line in out.splitlines():
        if any(k in line for k in ("ERROR", "UNTRANSLATED", "WARN", "DONE", "TOP", "[NEW]")):
            print("   ", line)
    return p.returncode == 0


def count_parts(url):
    """How many parts (episodes) a Bilibili link has. 1 for a normal video."""
    import yt_dlp, bili2en
    opts = {"quiet": True, "extract_flat": "in_playlist",
            "http_headers": {"Referer": "https://www.bilibili.com/", "User-Agent": bili2en.UA}}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False)
    return len(list(info.get("entries") or [])) or 1


def expand(url, ep):
    """A link without ?p= to a multi-part video = the whole series: one job per part."""
    import bili2en
    url = bili2en.clean_url(url)
    if re.search(r"[?&]p=\d+", url):
        return [(url, ep)]
    n = count_parts(url)
    if n == 1:
        return [(url, ep)]
    print(f"[SERIES] {n} parts found -> episodes 1-{n}")
    return [(f"{url}?p={i}", None) for i in range(1, n + 1)]


def fetch(show, url, ep=None):
    import bili2en
    url = bili2en.clean_url(url)
    bv = (re.search(r"BV[0-9A-Za-z]+", url) or [None])[0]
    part = int((re.search(r"[?&]p=(\d+)", url) or [None, 1])[1])
    ep = int(ep or part)
    show.make_dirs()
    dest = show.raw(ep)
    if dest.exists():
        log(show, f"[SKIP] {dest.name} already downloaded")
    else:
        cached = [show.work_dir / f"{bv}_p{part}.mp4"] + ([show.work_dir / f"{bv}.mp4"] if part == 1 else [])
        got = next((c for c in cached if bv and c.exists()), None)
        if got:
            log(show, f"[REUSE] {got.name} already in _Work -> {dest.name}")
        else:
            log(show, f"[GET] {url} -> {dest.name}")
            got = bili2en.download(url)
        shutil.move(str(got), dest)
    if bv:
        index_add(f"{bv}_p{part}", show, ep)
    return ep


def process(show, ep, force=False, audio_only=False):
    if show.en_video(ep).exists() and not force:
        log(show, f"[SKIP] {show.tag(ep)} done"); return
    if not show.raw(ep).exists():
        log(show, f"[MISSING] {show.raw(ep)}"); return
    log(show, f"===== {show.tag(ep)} {time.ctime()} =====")
    redo = ["--redo"] if force else []
    if audio_only:
        if force or not show.ja_srt(ep).exists():
            if not step(show, "whisper_ja.py", ep) or not show.ja_srt(ep).exists():
                log(show, f"[FAIL] {show.tag(ep)} audio"); return
        if force or not (show.en_srt(ep).exists() and show.en_srt(ep).stat().st_mtime > show.ja_srt(ep).stat().st_mtime):
            if not step(show, "run_audio.py", ep):
                log(show, f"[FAIL] {show.tag(ep)} translate"); return
        if not step(show, "fix_names.py", ep, "--burn"):
            log(show, f"[FAIL] {show.tag(ep)} burn"); return
        log(show, f"[DONE] {show.en_video(ep)}")
        return
    if not step(show, "ocr_zh.py", ep, *redo) or not show.zh_ocr(ep).exists():
        log(show, f"[FAIL] {show.tag(ep)} OCR"); return
    if force or not show.ja_words(ep).exists():
        if not step(show, "whisper_ja.py", ep) or not show.ja_words(ep).exists():
            log(show, f"[FAIL] {show.tag(ep)} audio"); return
    if force or not (show.en_srt(ep).exists() and show.en_srt(ep).stat().st_mtime > show.zh_ocr(ep).stat().st_mtime):
        if not step(show, "run_hybrid.py", ep):
            log(show, f"[FAIL] {show.tag(ep)} translate"); return
    if not step(show, "fix_names.py", ep, "--burn"):
        log(show, f"[FAIL] {show.tag(ep)} burn"); return
    if show.profile().get("variant"):
        step(show, "check_town.py", ep)
    log(show, f"[DONE] {show.en_video(ep)}")


def ollama_up():
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", help="Bilibili URL, or episodes: 5, 2-10, 1,3,7, all")
    ap.add_argument("--show", help="show name (used for the folder and file names)")
    ap.add_argument("--ep", type=int, help="episode number for a single URL")
    ap.add_argument("--list", help="text file: one URL per line, optional episode number after it")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--download-only", action="store_true",
                    help="only download; translate later with: bilien.py 30-53")
    ap.add_argument("--quality", type=int, default=1080,
                    help="max video height: 480, 720, 1080 (default 1080)")
    ap.add_argument("--browser", help="use your Bilibili login from chrome/safari/firefox")
    ap.add_argument("--audio-only", action="store_true",
                    help="no Chinese subs: translate from the spoken audio")
    a = ap.parse_args()
    if not a.target and not a.list:
        sys.exit(__doc__)
    import bili2en
    bili2en.MAX_HEIGHT = a.quality
    if a.browser:
        bili2en.BROWSER = a.browser
    show = pick_show(a.show)
    show.make_dirs()
    show.profile()                      # creates _Work/<Show> profile.json the first time

    jobs = []                           # (url or None, ep)
    if a.list:
        for line in Path(a.list).expanduser().read_text(encoding="utf-8").splitlines():
            bits = line.split()
            if bits and not bits[0].startswith("#"):
                jobs += expand(bits[0], bits[1] if len(bits) > 1 else None)
    elif re.match(r"https?://", a.target):
        jobs += expand(a.target, a.ep)
    else:
        jobs += [(None, ep) for ep in show.parse_eps(a.target)]

    if not a.download_only and not ollama_up():
        sys.exit("Ollama is not running, so nothing can be translated.\n"
                 "Open the Ollama app (or run: ollama serve) and try again,\n"
                 "or add --download-only to just download for now.")

    for url, ep in jobs:
        try:
            if url:
                ep = fetch(show, url, ep)
            if a.download_only:
                continue
            process(show, ep, a.force, a.audio_only or bool(show.profile().get("audio_only")))
        except Exception as e:
            log(show, f"[FAIL] {url or ep}: {e}")
    print(f"\nFolders: {show.raw_dir.parent}")


if __name__ == "__main__":
    main()
