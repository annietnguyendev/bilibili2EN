"""
show.py - the ONE place that knows folders and file names. No other script hard-codes a path.

Root folder:  $BILIEN_ROOT, else ~/BiliEN
Show name:    --show "Name", else $BILIEN_SHOW, else the only show already in the root.

Layout (one set of folders per show, all inside the root):
  <Show> - Chinese Sub (raw)/  <Show> EP01 (CN sub).mp4        1. downloaded video
  <Show> - Subtitle Files/     <Show> EP01 EN.srt / EN.ass,     2. subtitles
                               <Show> EP01 JA (whisper).srt
  <Show> - English Sub/        <Show> EP01 (EN sub).mp4         3. finished video
  _Work/                       OCR, word timing, logs, backups, <Show> profile.json, index.json
"""
import json, os, re, sys
from pathlib import Path

RAW_TAG, SUB_TAG, ENG_TAG = "Chinese Sub (raw)", "Subtitle Files", "English Sub"

# New shows start with this profile (_Work/<Show> profile.json). Edit it per show.
DEFAULT_PROFILE = {
    "title": "",               # full show title, given to the translator
    "audio_lang": "ja",        # spoken language for Whisper: ja, zh, ko, ...
    "model": "qwen2.5:14b",    # Ollama model
    "notes": [],               # extra translation rules, one string each
    "names": {},               # regex of what the audio says -> English name
    "safe_fixes": [],          # [regex, replacement] applied to every English line
    "fixes": {},               # "wrong English": "right English", applied before burning
    "variant": None,           # optional: a word whose English depends on what is heard (see README)
    "audio_only": False,       # True: video has no Chinese subs; translate from the audio (same as --audio-only)
}


def root():
    r = Path(os.environ.get("BILIEN_ROOT", Path.home() / "BiliEN")).expanduser()
    r.mkdir(parents=True, exist_ok=True)
    return r


def work():
    w = root() / "_Work"
    w.mkdir(exist_ok=True)
    return w


def shows():
    suffix = f" - {RAW_TAG}"
    return sorted(p.name[:-len(suffix)] for p in root().iterdir() if p.is_dir() and p.name.endswith(suffix))


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    return re.sub(r"\s+", " ", name)


class Show:
    def __init__(self, name):
        self.name = safe_name(name)
        if not self.name:
            sys.exit("[ERROR] Empty show name.")
        self.raw_dir = root() / f"{self.name} - {RAW_TAG}"
        self.sub_dir = root() / f"{self.name} - {SUB_TAG}"
        self.eng_dir = root() / f"{self.name} - {ENG_TAG}"
        self.work_dir = work()

    def make_dirs(self):
        for d in (self.raw_dir, self.sub_dir, self.eng_dir, self.work_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- per-episode files ----
    def tag(self, ep):
        return f"{self.name} EP{int(ep):02d}"

    def raw(self, ep):
        """Input video. '<tag> (CN sub).mp4', or '<tag> (raw).mp4' for a video with no Chinese subs."""
        cn = self.raw_dir / f"{self.tag(ep)} (CN sub).mp4"
        plain = self.raw_dir / f"{self.tag(ep)} (raw).mp4"
        return plain if plain.exists() and not cn.exists() else cn

    def en_srt(self, ep):   return self.sub_dir / f"{self.tag(ep)} EN.srt"
    def en_ass(self, ep):   return self.sub_dir / f"{self.tag(ep)} EN.ass"
    def ja_srt(self, ep):   return self.sub_dir / f"{self.tag(ep)} JA (whisper).srt"
    def ja_words(self, ep): return self.work_dir / f"{self.tag(ep)} JA whisper words.json"
    def zh_ocr(self, ep):   return self.work_dir / f"{self.tag(ep)} ZH ocr.srt"
    def en_video(self, ep): return self.eng_dir / f"{self.tag(ep)} (EN sub).mp4"

    def episodes(self):
        pat = re.compile(rf"^{re.escape(self.name)} EP(\d+) \((?:CN sub|raw)\)\.mp4$")
        if not self.raw_dir.exists():
            return []
        return sorted({int(m.group(1)) for p in self.raw_dir.iterdir() if (m := pat.match(p.name))})

    def parse_eps(self, spec):
        """'5', '2-10', '1,3,7' or 'all' (every downloaded episode)."""
        if spec == "all":
            return self.episodes()
        out = []
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-")
                out += range(int(a), int(b) + 1)
            elif part:
                out.append(int(part))
        return out

    # ---- per-show settings ----
    @property
    def profile_path(self):
        return self.work_dir / f"{self.name} profile.json"

    def profile(self):
        p = self.profile_path
        if not p.exists():
            prof = dict(DEFAULT_PROFILE, title=self.name)
            p.write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[NEW] Created {p.name} in _Work. Edit it to add names and notes for this show.")
        prof = dict(DEFAULT_PROFILE)
        prof.update(json.loads(p.read_text(encoding="utf-8")))
        return prof


def pick_show(name=None):
    name = name or os.environ.get("BILIEN_SHOW")
    if name:
        return Show(name)
    have = shows()
    if len(have) == 1:
        return Show(have[0])
    if not have:
        sys.exit('[ERROR] No show yet. Add --show "Show Name".')
    sys.exit('[ERROR] More than one show in ' + str(root()) + '. Add --show "Name". Shows: ' + ", ".join(have))


def cli(usage, argv=None):
    """Split argv into (Show, positional args, flags). Handles --show NAME."""
    argv = list(sys.argv[1:] if argv is None else argv)
    name = None
    if "--show" in argv:
        i = argv.index("--show")
        if i + 1 >= len(argv):
            sys.exit(usage)
        name = argv[i + 1]
        del argv[i:i + 2]
    pos = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    return pick_show(name), pos, flags


# ---- bilibili link -> episode map, read by the browser overlay ----
def index_add(key, show, ep):
    p = work() / "index.json"
    idx = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    idx[key] = {"show": show.name, "ep": int(ep),
                "srt": show.en_srt(ep).relative_to(root()).as_posix()}
    p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
