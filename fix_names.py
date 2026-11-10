"""
fix_names.py - apply "fixes" from _Work/<Show> profile.json to the English subs,
then burn the English onto the raw video -> <Show> - English Sub/<Show> EPNN (EN sub).mp4

  python3 fix_names.py 3 --show "Show Name"    # fix, burn only if something changed or no video yet
  python3 fix_names.py 3 --burn                # always burn
  python3 fix_names.py all
"""
import sys
import subprocess
from show import cli


def apply_fixes(file_path, fixes):
    if not file_path.exists():
        print(f"[WARN] Not found: {file_path}")
        return False
    text = file_path.read_text(encoding="utf-8")
    new = text
    for bad, good in fixes.items():
        new = new.replace(bad, good)
    if new != text:
        file_path.write_text(new, encoding="utf-8")
        print(f"[OK] Updated {file_path.name}")
        return True
    print(f"[INFO] No changes needed in {file_path.name}")
    return False


def burn(show, ep):
    video_in, video_out, ass = show.raw(ep), show.en_video(ep), show.en_ass(ep)
    if not video_in.exists():
        print(f"[ERROR] Original video not found: {video_in}"); return
    if not ass.exists():
        print(f"[ERROR] ASS subtitle file not found: {ass}"); return
    show.make_dirs()
    cmd = ["ffmpeg", "-y", "-i", str(video_in),
           "-vf", f"subtitles='{ass.name}'",     # run inside the subtitle folder so spaces in paths are safe
           "-c:a", "copy", str(video_out)]
    print(f"[BURN] {show.tag(ep)}...")
    subprocess.run(cmd, cwd=str(ass.parent), check=True)
    print(f"[DONE] {video_out}")


def main():
    show, args, flags = cli(__doc__)
    if not args:
        sys.exit(__doc__)
    fixes = show.profile()["fixes"]
    for ep in show.parse_eps(args[0]):
        changed = (apply_fixes(show.en_srt(ep), fixes) | apply_fixes(show.en_ass(ep), fixes)) if fixes else False
        if changed or "--burn" in flags or not show.en_video(ep).exists():
            burn(show, ep)
        else:
            print("[SKIP] Video not re-burned. Add --burn to force it.")


if __name__ == "__main__":
    main()
