# bili2en — English subtitles for Bilibili videos

Download a Bilibili video, read the **burned-in Chinese subtitles** with OCR, use the audio for **names**, translate with a **local LLM**, and draw English over the Chinese. Runs fully local. No API keys.

> **Personal viewing only.** Do not redistribute output videos.

More docs: [Manual steps and extras](docs/manual.md) · [Windows and Linux](docs/windows-linux.md) · [Troubleshooting](docs/troubleshooting.md)

---

## How it works

`bilien.py` runs every stage for each episode, skipping finished ones:

| Stage | Script | Output |
|---|---|---|
| Download | `bilien.py` (yt-dlp) | `<Show> EP01 (CN sub).mp4` |
| OCR | `ocr_zh.py` | `_Work/<Show> EP01 ZH ocr.srt` |
| Audio | `whisper_ja.py` | `JA (whisper).srt` |
| Translate | `run_hybrid.py` (Ollama `qwen2.5:14b`) | `EN.srt` / `EN.ass` |
| Fix + burn | `fix_names.py --burn` | `<Show> EP01 (EN sub).mp4` |

Show settings (title, names, fixes) live in `~/BiliEN/_Work/<Show> profile.json`. Jobs that need judgment (profile, name checks) go to an AI assistant with `~/BiliEN` connected.

---

## Install (macOS, Apple Silicon)

Needs Python 3.10+, [Homebrew](https://brew.sh), ~15 GB free disk, and a Bilibili login in Chrome (for 1080p). Windows/Linux: see [docs/windows-linux.md](docs/windows-linux.md).

```bash
brew install ffmpeg ollama
python3 -m pip install --user --break-system-packages \
  "yt-dlp[default,curl-cffi]" ocrmac mlx-whisper requests rapidocr_onnxruntime
brew services start ollama
ollama pull qwen2.5:14b
echo "export PATH=\"$(python3 -m site --user-base)/bin:\$PATH\"" >> ~/.zshrc && source ~/.zshrc
mkdir -p ~/BiliEN
```

---

## Use

**1. Set variables** (once per Terminal window, from the repo folder):

```bash
SHOW="Doctor Y"
URL="https://www.bilibili.com/video/BV1a5ECzqE4B/"
```

**2. Download** (no `?p=` = whole series; `"${URL}?p=3"` = one episode):

```bash
python3 bilien.py "$URL" --show "$SHOW" --browser chrome --download-only
```

**3. Test episode 1** (also creates the empty profile):

```bash
python3 bilien.py 1 --show "$SHOW"
```

**4. Fill in the profile with an AI assistant.** Send:

> Fill in `~/BiliEN/_Work/<Show> profile.json` for `<Show>` using the EP01 Chinese OCR, Whisper transcript and English subs. Add the show title, main character names, and notes for mistakes. Then re-run `python3 bilien.py 1 --show "<Show>" --force` and check the English.

**5. Do the rest:**

```bash
caffeinate -i python3 bilien.py 2-53 --show "$SHOW"
```

Episode formats: `5`, `2-10`, `1,3,7`, `all`. Add `--force` to redo.

**6. Check names with an AI assistant.** Send:

> Check the English subs for `<Show>` episodes 2–53 against the Whisper transcripts. Add fixes to the profile, re-burn changed episodes, and fix any `[UNTRANSLATED]` lines in `_Work/run_all.log`.

**7. Watch:**

```bash
open ~/BiliEN/"$SHOW - English Sub"/"$SHOW EP01 (EN sub).mp4"
```

Doing these by hand, audio-only videos, other video files, and the bilibili.com overlay: [docs/manual.md](docs/manual.md).
