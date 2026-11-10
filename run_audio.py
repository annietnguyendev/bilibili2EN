"""
run_audio.py - spoken-audio transcript -> English subs, for videos with NO Chinese subtitles.
Reads the Whisper transcript made by whisper_ja.py and translates it with Ollama.
Show settings (title, names, notes, fixes) come from _Work/<Show> profile.json.

  python3 run_audio.py 1 --show "Show Name"
  python3 run_audio.py 2-5  |  all

Usually run for you by:  python3 bilien.py 1 --show "Show Name" --audio-only
"""
import json, re
import run_hybrid as rh
from show import cli

BATCH = 15
MIN_DUR = 1.2     # shortest time a line stays on screen
GAP_FILL = 0.8    # blank gaps shorter than this get closed

LANGS = {"ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English",
         "es": "Spanish", "fr": "French", "de": "German"}

# Whisper often "hears" these in silence or music. Dropped before translating.
HALLUCINATIONS = re.compile(
    r"(ご視聴ありがとうございました|チャンネル登録|字幕|お疲れ様でした。?$|"
    r"请不吝点赞|订阅|谢谢观看|明镜与点点|시청해 주셔서|구독)")

PROMPT = ""


def build_prompt(prof):
    lang = LANGS.get(prof["audio_lang"], prof["audio_lang"])
    rules = [f"Meaning comes from \"src\": a {lang} speech-recognition transcript. "
             "It can have small hearing mistakes: use the context to pick the most likely meaning.",
             "If an item has \"names\", spell those people exactly that way. "
             "Never invent a name that was not said.",
             "Use \"before\" only as context. Do not translate it again."]
    rules += prof["notes"]
    rules += ["One answer per line. No \"or\", no slashes, no notes.",
              "Reply with JSON only: {{\"lines\": [...]}} with exactly {n} strings, same order."]
    title = prof["title"] or "a TV show"
    return (f"You translate {lang} subtitles for {title} into English.\n"
            "Write natural, short English TV subtitles.\n\nRules:\n"
            + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
            + "\n\nbefore: {before}\n\nItems:\n{items}")


def ask(chunk, before):
    send = []
    for c in chunk:
        d = {"src": c["src"]}
        if c["names"]:
            d["names"] = c["names"]
        send.append(d)
    try:
        res = rh.query_llm(PROMPT.format(n=len(chunk), before=json.dumps(before, ensure_ascii=False),
                                         items=json.dumps(send, ensure_ascii=False)))
        arr = [rh.clean_sub(str(x)) for x in res.get("lines", [])]
    except Exception as e:
        print(f"[WARN] LLM error: {e}")
        return None
    if len(arr) != len(chunk) or any(rh.CJK.search(x) for x in arr):
        return None
    return arr


def translate(chunk, before):
    """Try the batch; if it fails, retry in 5s, then one line at a time."""
    arr = ask(chunk, before)
    if arr:
        return arr
    if len(chunk) > 5:
        print(f"[RETRY] batch at {chunk[0]['timing']} -> smaller batches")
        out = []
        for j in range(0, len(chunk), 5):
            out += translate(chunk[j:j + 5], (before + out)[-3:])
        return out
    out = []
    for c in chunk:
        one = ask([c], (before + out)[-3:]) or ask([c], (before + out)[-3:])
        out.append(one[0] if one else c["src"])
    return out


def merge_short(cues):
    """Join tiny back-to-back pieces Whisper splits off ('ドクターX' + 'だぞ!')."""
    out = []
    for a, z, t, src in cues:
        if out:
            pa, pz, _, psrc = out[-1]
            if a - pz <= 0.3 and pz - pa < 1.5 and len(psrc) + len(src) <= 20:
                out[-1] = (pa, z, f"{rh.fmt(pa)} --> {rh.fmt(z)}", psrc + " " + src)
                continue
        out.append((a, z, t, src))
    return out


def main(show, ep):
    src_path, out_srt = show.ja_srt(ep), show.en_srt(ep)
    if not src_path.exists():
        print(f"[ERROR] Missing audio transcript: {src_path}. Run whisper_ja.py first."); return
    if out_srt.exists():  # keep a backup so hand edits are never lost
        (show.work_dir / (out_srt.name + ".bak")).write_bytes(out_srt.read_bytes())

    cues = []
    for a, z, t, src in rh.parse_srt(src_path):
        if HALLUCINATIONS.search(src):
            print(f"[DROP] {t} {src}  (likely Whisper hallucination)"); continue
        cues.append((a, z, t, src))
    cues = merge_short(cues)
    print(f"Loaded {len(cues)} spoken lines.")

    items = [{"a": a, "z": z, "timing": t, "src": src, "names": rh.heard_names(src)}
             for a, z, t, src in cues]

    out = []
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        arr = translate(chunk, [en for *_, en in out][-3:])
        for c, en in zip(chunk, arr):
            for pat, good in rh.SAFE_FIXES:
                en = re.sub(pat, good, en)
            if not en.strip():
                print(f"[DROP] {c['timing']} (empty)"); continue
            if rh.CJK.search(en):
                print(f"[UNTRANSLATED] {c['timing']} {en}")
            out.append((c["a"], c["z"], c["timing"], en))
            print(f"[{c['timing']}] {en}")

    # merge back-to-back repeats
    merged = []
    for a, z, t, en in out:
        if merged and merged[-1][3] == en and a - merged[-1][1] <= 1.0:
            merged[-1] = (merged[-1][0], z, "", en)
        else:
            merged.append((a, z, t, en))

    # smooth timing: readable length, no flashing, no tiny gaps, no overlap
    smooth = []
    for i, (a, z, _, en) in enumerate(merged):
        nxt = merged[i + 1][0] if i + 1 < len(merged) else None
        z = max(z, a + MIN_DUR)
        if nxt is not None:
            if nxt - z < GAP_FILL:
                z = nxt
            z = min(z, nxt)
        smooth.append((a, z, f"{rh.fmt(a)} --> {rh.fmt(z)}", en))

    out_srt.write_text("\n".join(f"{n}\n{t}\n{en}\n" for n, (_, _, t, en) in enumerate(smooth, 1)),
                       encoding="utf-8")
    print(f"[DONE] {out_srt}")

    try:
        import bili2en as b
        b.write_ass([(a, z, en) for a, z, _, en in smooth], show.en_ass(ep),
                    *b.video_size(show.raw(ep)), plain=True)
        print(f"[DONE] {show.en_ass(ep)}")
    except Exception as e:
        print(f"[WARN] .ass not rebuilt ({e}). Run from the folder with bili2en.py.")


if __name__ == "__main__":
    show, args, flags = cli(__doc__)
    prof = show.profile()
    rh.load_profile(prof)          # sets model, names, safe_fixes
    PROMPT = build_prompt(prof)
    for ep in show.parse_eps(args[0] if args else "1"):
        main(show, ep)
