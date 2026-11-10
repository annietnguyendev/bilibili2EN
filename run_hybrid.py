"""
run_hybrid.py - Chinese OCR subs + spoken-audio transcript -> English subs.
The AUDIO decides names (and the optional "variant" word) for each line.
Show-specific settings live in _Work/<Show> profile.json.

  python3 run_hybrid.py 1 --show "Show Name"
  python3 run_hybrid.py 2-5  |  all
"""
import sys, json, re, requests
from pathlib import Path
from show import cli

PAD = 0.25  # seconds of audio slack around each Chinese line
MIN_DUR = 1.2  # shortest time a line stays on screen
GAP_FILL = 0.8  # blank gaps shorter than this get closed
CARRY = 3.0  # untagged line within this many seconds keeps the previous variant tag

# Filled from the show profile by load_profile()
MODEL, NAMES, SAFE_FIXES, PROMPT = "", {}, [], ""
VARIANT = None   # dict with compiled regexes, or None


def load_profile(prof):
    global MODEL, NAMES, SAFE_FIXES, PROMPT, VARIANT
    MODEL = prof["model"]
    NAMES = dict(prof["names"])
    SAFE_FIXES = [(a, b) for a, b in prof["safe_fixes"]]
    v = prof.get("variant")
    VARIANT = None
    if v:
        VARIANT = dict(v, replace_re=re.compile(v["replace"], re.I),
                       heard_re={k: re.compile(r) for k, r in v["heard"].items()})
    rules = ["Meaning comes from \"zh\" (Chinese fan subtitle).",
             "If an item has \"names\", spell those people exactly that way. "
             "Only use a character's name if it is in \"names\" or written in \"zh\". Never guess a name."]
    rules += prof["notes"]
    if VARIANT:
        rules += VARIANT.get("rules", [])
    rules += ["One answer per line. No \"or\", no slashes, no notes.",
              "Reply with JSON only: {{\"lines\": [...]}} with exactly {n} strings, same order."]
    title = prof["title"] or "a TV show"
    PROMPT = (f"You translate subtitles for {title}.\nWrite natural, short English TV subtitles.\n\nRules:\n"
              + "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1)) + "\n\nItems:\n{items}")


def to_sec(s):
    h, mi, rest = s.strip().split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(mi) * 60 + int(sec) + int(ms) / 1000.0


def fmt(t):
    h, r = divmod(int(t), 3600)
    m, sec = divmod(r, 60)
    return f"{h:02}:{m:02}:{sec:02},{int(round(t % 1 * 1000)) % 1000:03}"


def parse_srt(path):
    cues = []
    if not path.exists():
        return cues
    for blk in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = blk.strip().split("\n")
        if len(lines) >= 3 and " --> " in lines[1]:
            a, z = lines[1].split(" --> ")
            try:
                cues.append((to_sec(a), to_sec(z), lines[1], " ".join(lines[2:])))
            except Exception:
                pass
    return cues


def town_tag(heard):
    if not VARIANT:
        return None
    hits = [k for k, rx in VARIANT["heard_re"].items() if rx.search(heard)]
    return "both" if len(hits) > 1 else hits[0] if hits else None


def heard_names(heard):
    return sorted({en for pat, en in NAMES.items() if re.search(pat, heard)})


CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
JUNK_LINE = re.compile(r"^(Doctors? use|Use|Medical)?\s*PHS\.?$", re.I)
# on-screen "医療用PHS" phone label; OCR garbles 療 (瘵/燾/意/癡) and adds stray chars
PHS_ZH = re.compile(r"(?:医.|[食集應应医])?用\s*PHS?|A?PHS", re.I)
PHS_EN = re.compile(r"^\W*((the|a|an|for|doctors?'?s?|medical|use[ds]?|using|collect|e-therapy|aphs)\s*)*PHS\W*$", re.I)


def clean_zh(zh):
    """Strip the PHS label. Returns '' if nothing real is left."""
    rest = PHS_ZH.sub("", zh).strip()
    return rest if re.search(r"[\u4e00-\u9fff]", rest) else ""


def ask(chunk):
    send = []
    for c in chunk:
        d = {"zh": c["zh"]}
        if c["names"]:
            d["names"] = c["names"]
        if c["town"]:
            d[VARIANT.get("key", "variant")] = c["town"]
        send.append(d)
    try:
        res = query_llm(PROMPT.format(n=len(chunk), items=json.dumps(send, ensure_ascii=False)))
        arr = [clean_sub(str(x)) for x in res.get("lines", [])]
    except Exception as e:
        print(f"[WARN] LLM error: {e}")
        return None
    if len(arr) != len(chunk) or any(CJK.search(x) for x in arr):
        return None
    return arr


def translate(chunk):
    """Try the batch; if it fails, retry in 5s, then one line at a time. Never silently keep Chinese."""
    arr = ask(chunk)
    if arr:
        return arr
    if len(chunk) > 5:
        print(f"[RETRY] batch at {chunk[0]['timing']} -> smaller batches")
        return [x for j in range(0, len(chunk), 5) for x in translate(chunk[j:j + 5])]
    out = []
    for c in chunk:
        one = ask([c]) or ask([c])
        out.append(one[0] if one else c["zh"])
    return out


def query_llm(prompt):
    r = requests.post("http://localhost:11434/api/generate", timeout=300, json={
        "model": MODEL, "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0.2}})
    text = r.json().get("response", "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def clean_sub(line):
    line = line.strip().strip("\"'")
    if line.count(" or ") == 1:
        line = line.split(" or ")[0].strip(" \"'")
    return line


def fix_line(en, item):
    for pat, good in SAFE_FIXES:
        en = re.sub(pat, good, en)
    if not VARIANT:
        return en
    words, tag = VARIANT["replace_re"], item["town"]
    default, wrong = VARIANT.get("default"), VARIANT.get("corrected_from")
    hits = list(words.finditer(en))
    if wrong and default and len(hits) >= 2 and any("not " in en[max(0, m.start() - 5):m.start()].lower() for m in hits):
        # correction line: "It's <default>, not <wrong>"
        return words.sub(lambda m: wrong if "not " in en[max(0, m.start() - 5):m.start()].lower() else default, en)
    if tag in VARIANT["heard"]:
        en = words.sub(tag, en)               # audio wins
    elif tag is None and default and VARIANT["zh"] in item["zh"]:
        en = words.sub(default, en)           # shown but not heard -> default
        print(f"[CHECK] {item['timing']} {VARIANT['zh']} in Chinese but not heard in audio")
    return en                                 # "both": trust the model's order


def main(show, ep):
    zh_path, ja_path, out_srt = show.zh_ocr(ep), show.ja_srt(ep), show.en_srt(ep)
    if not zh_path.exists():
        print(f"[ERROR] Missing Chinese OCR file: {zh_path}"); return
    if out_srt.exists():  # keep a backup so hand edits are never lost
        (show.work_dir / (out_srt.name + ".bak")).write_bytes(out_srt.read_bytes())
    zh_cues, ja_cues = parse_srt(zh_path), parse_srt(ja_path)
    words_path = show.ja_words(ep)
    words = json.loads(words_path.read_text(encoding="utf-8")) if words_path.exists() else None
    print("Audio timing:", "word-level (exact)" if words else "sentence-level (rerun whisper_ja.py for exact)")
    print(f"Loaded {len(zh_cues)} Chinese cues, {len(ja_cues)} Japanese cues.")
    if not ja_cues:
        print("[WARN] No Japanese audio file. Run whisper_ja.py first or names will be guessed.")

    items = []
    for a, z, timing, zh in zh_cues:
        if "PH" in zh.upper():
            clean = clean_zh(zh)
            if not clean:
                print(f"[DROP] {timing} {zh}"); continue
            zh = clean
        if words:
            heard = "".join(w["w"] for w in words if w["s"] < z + PAD and w["e"] > a - PAD)
        else:
            heard = " ".join(t for s0, s1, _, t in ja_cues if s0 < z + PAD and s1 > a - PAD)
        it = {"a": a, "z": z, "timing": timing, "zh": zh, "heard": heard,
              "town": town_tag(heard), "names": heard_names(heard)}
        # untagged line that still shows the town: borrow the tag from a line just before
        if VARIANT and not it["town"] and VARIANT["zh"] in zh and items:
            prev = next((p for p in reversed(items) if p["town"] in VARIANT["heard"]), None)
            if prev and a - prev["z"] <= CARRY:
                it["town"] = prev["town"]
                print(f"[TOWN={it['town']} carried] {timing}")
        if it["town"]:
            print(f"[TOWN={it['town']}] {timing}  heard: {heard}")
        items.append(it)

    out = []
    for i in range(0, len(items), 15):
        chunk = items[i:i + 15]
        arr = translate(chunk)
        for c, en in zip(chunk, arr):
            en = fix_line(en, c)
            if not en or JUNK_LINE.match(en) or PHS_EN.match(en) or c["zh"].strip().upper() in ("PHS", "医用PHS"):
                print(f"[DROP] {c['timing']} {en or c['zh']}")
                continue
            if CJK.search(en):
                print(f"[UNTRANSLATED] {c['timing']} {en}")
            out.append((c["a"], c["z"], c["timing"], en))
            print(f"[{c['timing']}] {en}")

    # merge back-to-back repeats (OCR splits one line into several)
    merged = []
    for a, z, t, en in out:
        if merged and merged[-1][3] == en and a - merged[-1][1] <= 1.0:
            pa = merged[-1][0]
            merged[-1] = (pa, z, f"{fmt(pa)} --> {fmt(z)}", en)
        else:
            merged.append((a, z, t, en))
    out = merged

    # smooth timing: no flashing lines, no tiny blank gaps
    smooth = []
    for i, (a, z, t, en) in enumerate(out):
        nxt = out[i + 1][0] if i + 1 < len(out) else None
        z = max(z, a + MIN_DUR)                    # stay up long enough to read
        if nxt is not None:
            if nxt - z < GAP_FILL:
                z = nxt                            # close small gap
            z = min(z, nxt)                        # never overlap next line
        smooth.append((a, z, f"{fmt(a)} --> {fmt(z)}", en))
    out = smooth

    out_srt.write_text("\n".join(f"{n}\n{t}\n{en}\n" for n, (_, _, t, en) in enumerate(out, 1)),
                       encoding="utf-8")
    print(f"[DONE] {out_srt}")

    # Rebuild the .ass so fix_names.py / burn use the new text
    try:
        import bili2en as b
        video = show.raw(ep)
        ass = show.en_ass(ep)
        b.write_ass([(a, z, en) for a, z, _, en in out], ass, *b.video_size(video))
        print(f"[DONE] {ass}")
    except Exception as e:
        print(f"[WARN] .ass not rebuilt ({e}). Run from the folder with bili2en.py.")


if __name__ == "__main__":
    show, args, flags = cli(__doc__)
    load_profile(show.profile())
    for ep in show.parse_eps(args[0] if args else "1"):
        main(show, ep)
