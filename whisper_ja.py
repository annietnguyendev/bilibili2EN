"""
whisper_ja.py - transcript of the spoken audio (with word timing) for each episode.
Language comes from "audio_lang" in _Work/<Show> profile.json (default ja).

  python3 whisper_ja.py 2 --show "Show Name"
  python3 whisper_ja.py 2-4  |  all
"""
import os, sys, json
from show import cli


def t(s):
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02}:{m:02}:{sec:02},{int(s % 1 * 1000):03}"


def transcribe(src, lang):
    """Mac: mlx-whisper. Windows/Linux: faster-whisper (uses an NVIDIA GPU if there is one).
    Returns segments as dicts: start, end, text, words[start, end, word]."""
    opts = dict(language=lang, task="transcribe", condition_on_previous_text=False,
                word_timestamps=True, hallucination_silence_threshold=2.0)
    try:
        import mlx_whisper
    except ImportError:
        mlx_whisper = None
    if mlx_whisper:
        return mlx_whisper.transcribe(str(src), path_or_hf_repo="mlx-community/whisper-large-v3-mlx", **opts)["segments"]
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("[ERROR] No Whisper found. Mac: pip install mlx-whisper. Windows/Linux: pip install faster-whisper")
    size = os.environ.get("BILIEN_WHISPER", "large-v3")   # smaller/faster: medium, small
    segs, _ = WhisperModel(size, device="auto", compute_type="default").transcribe(str(src), **opts)
    return [{"start": s.start, "end": s.end, "text": s.text,
             "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])]}
            for s in segs]


def run(show, ep, lang):
    src, out, words_out = show.raw(ep), show.ja_srt(ep), show.ja_words(ep)
    if not src.exists():
        print(f"[ERROR] Video not found: {src}"); return
    show.make_dirs()
    segments = transcribe(src, lang)
    last = None; n = 0
    with open(out, "w", encoding="utf-8") as f:
        for s in segments:
            text = s["text"].strip()
            if not text or text == last:
                continue
            last = text; n += 1
            f.write(f"{n}\n{t(s['start'])} --> {t(s['end'])}\n{text}\n\n")
    words = [{"s": w["start"], "e": w["end"], "w": w["word"]}
             for s in segments for w in s.get("words", [])]
    with open(words_out, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)
    print("done:", n, "lines,", len(words), "words ->", out)


if __name__ == "__main__":
    show, args, flags = cli(__doc__)
    lang = show.profile()["audio_lang"]
    for ep in show.parse_eps(args[0] if args else "1"):
        run(show, ep, lang)
