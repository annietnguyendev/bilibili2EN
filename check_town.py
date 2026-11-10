"""
check_town.py - check the optional "variant" word from the show profile
(e.g. a running joke where the English must match what was said).
For every audio line that says it, shows the English at that time and flags mismatches.

  python3 check_town.py 2 --show "Show Name"
  python3 check_town.py all
"""
import re, sys
from show import cli

PAD = 0.5


def secs(t):
    h, m, s = t.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(s)


def cues(p):
    out = []
    for blk in re.split(r"\n\s*\n", p.read_text(encoding="utf-8").strip()):
        ln = blk.strip().splitlines()
        tl = next((i for i, l in enumerate(ln) if "-->" in l), None)
        if tl is None: continue
        a, b = [secs(x.strip()) for x in ln[tl].split("-->")]
        out.append((a, b, " ".join(ln[tl + 1:])))
    return out


def check(show, ep, heard):
    ja_p, en_p = show.ja_srt(ep), show.en_srt(ep)
    if not (ja_p.exists() and en_p.exists()): return None
    ja, en = cues(ja_p), cues(en_p)
    bad = hits = 0
    for a, b, t in ja:
        said = [k for k, rx in heard.items() if rx.search(t)]
        if not said: continue
        hits += 1
        eng = " / ".join(x for s, e, x in en if s < b + PAD and e > a - PAD) or "(no English here)"
        ok = all(k.lower() in eng.lower() for k in said)
        if not ok: bad += 1
        print(f"  {'OK ' if ok else 'FIX'} {show.tag(ep)} {int(a//60):02d}:{a%60:04.1f}  "
              f"heard[{'+'.join(said)}] {t}  ->  EN: {eng}")
    if hits == 0: print(f"  {show.tag(ep)}: not said")
    return bad


if __name__ == "__main__":
    show, args, flags = cli(__doc__)
    if not args: sys.exit(__doc__)
    v = show.profile().get("variant")
    if not v:
        sys.exit(f"[SKIP] No \"variant\" in {show.profile_path.name}; nothing to check.")
    heard = {k: re.compile(r) for k, r in v["heard"].items()}
    total = sum(check(show, ep, heard) or 0 for ep in show.parse_eps(args[0]))
    print(f"\n{total} line(s) to fix." if total else "\nAll lines OK.")
