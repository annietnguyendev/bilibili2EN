"""
ocr_zh.py - read burned-in Chinese subs -> _Work/<Show> EPNN ZH ocr.srt
Uses Apple Vision OCR (ocrmac) on a Mac, RapidOCR on Windows/Linux, + ffmpeg.

  python3 ocr_zh.py 2 --show "Show Name"     # one episode
  python3 ocr_zh.py 2-4                      # range (--show can be left out if there is only one show)
  python3 ocr_zh.py all                      # every downloaded episode (skips ones already done)
  add --redo to overwrite an existing OCR file
"""
import difflib, re, subprocess, sys, tempfile
from pathlib import Path

from show import cli
FPS = 2
CROP = "crop=iw*0.76:ih*0.13:iw*0.12:ih*0.85"
# End credits: the Chinese subs move to the TOP of the frame and the credits roll at the bottom.
TOP_CROP = "crop=iw*0.76:ih*0.09:iw*0.12:0"
TOP_MIN_SEC = 2.0      # top text must last this long in total to count
TOP_MIN_LINES = 3      # ...and change at least this often: real subs change, a sign/caption/website stays the same
TOP_HOLD = 10.0        # ignore bottom text (credits) up to this long after the last top sub




def ts(sec):
    ms = int(round(sec * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_RAPID = None


def rapid():
    """Second reader (RapidOCR) for frames Apple's reader finds empty. Optional."""
    global _RAPID
    if _RAPID is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID = RapidOCR()
        except ImportError:
            print("    tip: pip install rapidocr_onnxruntime  (catches lines Apple's OCR misses)")
            _RAPID = False
    return _RAPID


def clean(t):
    t = re.sub(r"\s+", "", t)
    if re.search(PROMO, t):
        return ""
    return t if re.search(r"[一-鿿]", t) else ""


_APPLE = None


def apple():
    """Apple Vision OCR (macOS only). False on Windows/Linux."""
    global _APPLE
    if _APPLE is None:
        try:
            from ocrmac import ocrmac
            _APPLE = ocrmac
        except ImportError:
            _APPLE = False
    return _APPLE


def read_line(png):
    t = ""
    if apple():
        res = apple().OCR(str(png), language_preference=["zh-Hans"]).recognize()
        res = [r for r in res if r[1] > 0.4]
        res.sort(key=lambda r: r[2][0])
        t = clean("".join(r[0] for r in res))
    if not t and rapid():
        out, _ = rapid()(str(png))
        t = clean("".join(str(r[1]) for r in (out or []) if float(r[2]) > 0.6))   # score can come back as text
    return t


def frames(video, crop, d):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video),
                    "-vf", f"fps={FPS},{crop}", f"{d}/%06d.png"], check=True)
    return sorted(Path(d).glob("*.png"))


PROMO = r"微博|更多作品|更多作晶|字幕组|转载"   # uploader ads, not dialogue
WATERMARK_SHARE = 0.15  # text seen in this share of all frames = channel watermark, not a sub


def drop_watermark(lines, where):
    """Blank out text that never changes (an uploader's logo/watermark)."""
    from collections import Counter
    seen = [t for t in lines if t]
    if not seen:
        return lines
    common, n = Counter(seen).most_common(1)[0]
    if n < WATERMARK_SHARE * len(lines):
        return lines
    print(f"    ignoring {where} watermark: {common}")
    out = []
    for t in lines:
        if t and (common in t or difflib.SequenceMatcher(None, t, common).ratio() > 0.6):
            t = t.replace(common, "")
            if len(t) < 2 or difflib.SequenceMatcher(None, t, common).ratio() > 0.6:
                t = ""
        out.append(t)
    return out


def top_regions(top):
    """Times where subs sit at the top (end credits). Returns [(start, end)] in seconds."""
    hits = [i / FPS for i, t in enumerate(top) if len(t) >= 3]
    runs = []
    for t in hits:
        if runs and t - runs[-1][1] <= TOP_HOLD:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    keep = []
    for a, b in runs:
        n = sum(1 for t in hits if a <= t <= b)
        lines, prev = 0, ""
        for i in range(int(a * FPS), int(b * FPS) + 1):
            cur = top[i] if len(top[i]) >= 3 else ""
            if cur and (not prev or difflib.SequenceMatcher(None, cur, prev).ratio() < 0.6):
                lines += 1
            if cur:
                prev = cur
        if n / FPS >= TOP_MIN_SEC and lines >= TOP_MIN_LINES:
            keep.append((a, b + TOP_HOLD))
    return keep


def ocr_cues(video):
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        bot_f, top_f = frames(video, CROP, d1), frames(video, TOP_CROP, d2)
        print(f"    checking {len(bot_f)} frames (bottom + top)...")
        bot = []
        for i, f in enumerate(bot_f):
            if i and i % 600 == 0:
                print(f"    bottom {i}/{len(bot_f)}")
            bot.append(read_line(f))
        top = [read_line(f) for f in top_f]
    top = drop_watermark(top, "top")
    bot = drop_watermark(bot, "bottom")
    regions = top_regions(top)
    for a, b in regions:
        print(f"    subs at TOP from {ts(a)} to {ts(b)} (bottom text there = credits, ignored)")

    def pick(i):
        t = i / FPS
        if any(a <= t <= b for a, b in regions):
            return top[i] if i < len(top) and len(top[i]) >= 3 else ""   # credits roll at the bottom: ignore it
        return bot[i]

    cues, cur = [], None
    for i in range(len(bot)):
        t, txt = i / FPS, pick(i)
        same = cur and txt and difflib.SequenceMatcher(None, txt, cur[2]).ratio() > 0.7
        if same:
            cur[1] = t + 1 / FPS
            if len(txt) > len(cur[2]):
                cur[2] = txt
        else:
            if cur:
                cues.append(tuple(cur))
            cur = [t, t + 1 / FPS, txt] if txt else None
    if cur:
        cues.append(tuple(cur))
    return [c for c in cues if c[1] - c[0] >= 0.4]


def main():
    show, args, flags = cli(__doc__)
    if not args:
        sys.exit(__doc__)
    redo = "--redo" in flags
    if not apple() and not rapid():
        sys.exit("[ERROR] No OCR found. Mac: pip install ocrmac. Windows/Linux: pip install rapidocr_onnxruntime")
    for ep in show.parse_eps(args[0]):
        out, vid = show.zh_ocr(ep), show.raw(ep)
        if out.exists() and not redo:
            print(f"[SKIP] {out.name} already exists"); continue
        if not vid.exists():
            print(f"[MISSING] {vid}"); continue
        print(f"{show.tag(ep)}: OCR {vid.name}")
        cues = ocr_cues(vid)
        if not cues:
            print(f"[ERROR] {show.tag(ep)}: OCR read nothing"); continue
        with open(out, "w", encoding="utf-8") as f:
            for i, (a, b, t) in enumerate(cues, 1):
                f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n")
        print(f"    wrote {len(cues)} lines -> {out}")


if __name__ == "__main__":
    main()
