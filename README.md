# bili2en — English subtitles for Bilibili videos

Download a Bilibili video or series, read the **burned-in Chinese subtitles** with OCR, listen to the original audio for **names**, translate to English with a **local LLM**, and draw the English over the Chinese at the same timing. Original audio is kept.

Everything runs locally. No paid API, no API keys.

> **For personal viewing only.** Respect Bilibili's terms and the rights holders. Do not redistribute output videos.

---

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Folder layout](#folder-layout)
- [Workflow (step by step)](#workflow-step-by-step)
  - [Step 0 — Open Terminal and set variables](#step-0--open-terminal-and-set-variables)
  - [Step 1 — Download](#step-1--download)
  - [Step 2 — Test one episode](#step-2--test-one-episode)
  - [Step 3 — Set up the show profile (AI)](#step-3--set-up-the-show-profile-ai)
  - [Step 4 — Make the rest of the episodes](#step-4--make-the-rest-of-the-episodes)
  - [Step 5 — Check and fix names (AI)](#step-5--check-and-fix-names-ai)
  - [Step 6 — Fix single lines (AI, optional)](#step-6--fix-single-lines-ai-optional)
  - [Step 7 — Watch](#step-7--watch)
- [Run one stage by hand](#run-one-stage-by-hand)
- [Videos with no Chinese subs (audio only)](#videos-with-no-chinese-subs-audio-only)
- [Subtitle any other video file](#subtitle-any-other-video-file)
- [Windows and Linux](#windows-and-linux)
- [Scripts](#scripts)
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## How it works

One command (`bilien.py`) runs every stage. Each stage is also its own script.

| Stage | Script | Tool | Output |
|---|---|---|---|
| 1. Download | `bilien.py` → `bili2en.download()` | `yt-dlp` + `curl_cffi` (Chrome impersonation on the file download only, CDN mirror fallback) | `<Show> EP01 (CN sub).mp4` |
| 2. OCR | `ocr_zh.py` | Mac: Apple Vision (`ocrmac`) + optional RapidOCR backup. Windows/Linux: RapidOCR | `_Work/<Show> EP01 ZH ocr.srt` |
| 3. Audio | `whisper_ja.py` | Mac: `mlx-whisper`. Windows/Linux: `faster-whisper`. large-v3, word timing | `JA (whisper).srt` + `_Work/… JA whisper words.json` |
| 4. Translate | `run_hybrid.py` | Ollama + `qwen2.5:14b`; audio decides names | `<Show> EP01 EN.srt` / `EN.ass` |
| 5. Fix + burn | `fix_names.py --burn` | profile `fixes` + `ffmpeg subtitles=` | `<Show> EP01 (EN sub).mp4` |
| 6. Check (optional) | `check_town.py` | profile `variant` | log only |

Show settings (title, names, notes, fixes) live in **one file per show**: `_Work/<Show> profile.json`. No show details are hard-coded in the scripts.

**Who does what:** the scripts do every stage above by themselves. Jobs that need judgment are **given to an AI assistant** (e.g. Claude in Cowork with `~/BiliEN` connected): filling in the show profile (Step 3), checking names (Step 5) and fixing single lines (Step 6). Copy-paste requests are in those steps.

---

## Requirements

- **macOS on Apple Silicon** (tested: MacBook Pro M5, 32 GB RAM, zsh). Windows and Linux: see below.
  - Windows and Linux also work, with other OCR and Whisper tools. See [Windows and Linux](#windows-and-linux).
- Python 3.10+
- Homebrew: https://brew.sh
- ~10 GB free disk for the 14B model, ~3 GB for Whisper large-v3, plus space for videos.
- A Bilibili account logged in to Chrome (needed for 1080p).

---

## Install

Run each line in Terminal.

```bash
# 1. Get the code (or use your local "run subs" folder)
git clone https://github.com/<your-username>/bili2en.git
cd bili2en

# 2. System tools
brew install ffmpeg ollama

# 3. Python packages
python3 -m pip install --user --break-system-packages \
  "yt-dlp[default,curl-cffi]" ocrmac mlx-whisper requests

# 4. (Optional) second OCR reader for lines Apple Vision misses
python3 -m pip install --user --break-system-packages rapidocr_onnxruntime

# 5. Start Ollama and download the translation model
brew services start ollama
ollama pull qwen2.5:14b

# 6. Make user-installed commands work (one time only)
echo "export PATH=\"$(python3 -m site --user-base)/bin:\$PATH\"" >> ~/.zshrc
source ~/.zshrc

# 7. Create the working folder
mkdir -p ~/BiliEN
```

Check the install:

```bash
ffmpeg -version | head -1
yt-dlp --version
ollama list | grep qwen2.5:14b
python3 -c "import ocrmac, mlx_whisper, curl_cffi, requests; print('python ok')"
curl -s http://localhost:11434/api/tags >/dev/null && echo "ollama ok"
```

> Use `python3 -m pip`, not `pip`. If you see `externally-managed-environment`, add `--user --break-system-packages`.

---

## Folder layout

**Code:** the repo folder (e.g. `~/Downloads/subtitles/run subs/`).
**All videos and output:** `~/BiliEN/` (change with `export BILIEN_ROOT=/other/path`).

```
~/BiliEN/
├── <Show> - Chinese Sub (raw)/   <Show> EP01 (CN sub).mp4      ← downloaded video
├── <Show> - Subtitle Files/      <Show> EP01 EN.srt
│                                 <Show> EP01 EN.ass
│                                 <Show> EP01 JA (whisper).srt
├── <Show> - English Sub/         <Show> EP01 (EN sub).mp4      ← finished video
└── _Work/                        <Show> profile.json            ← show settings
                                  <Show> EP01 ZH ocr.srt         ← Chinese OCR
                                  <Show> EP01 JA whisper words.json
                                  run_all.log, index.json, backups
```

- Episode numbers are 2 digits: `EP01`, `EP30`.
- `index.json` maps each Bilibili ID + part (`BV…_p30`) to show + episode, for the browser overlay.

---

## Workflow (step by step)

### Step 0 — Open Terminal and set variables

Set these once per Terminal window.

```bash
cd ~/Downloads/subtitles/"run subs"     # where the scripts are
SHOW="Doctor Y"                          # any name; becomes the folder/file name
URL="https://www.bilibili.com/video/BV1a5ECzqE4B/"
```

> Always put URLs and names with spaces in quotes.

Start Ollama if it is not running (translation stops without it):

```bash
brew services start ollama
```

### Step 1 — Download

`bilien.py` downloads into `<Show> - Chinese Sub (raw)/`. Already-downloaded episodes are skipped.

**1a. One episode** (the `?p=` number becomes the episode number):

```bash
python3 bilien.py "${URL}?p=3" --show "$SHOW" --browser chrome --download-only
```

**1b. A whole series** (link with no `?p=` = every part):

```bash
python3 bilien.py "$URL" --show "$SHOW" --browser chrome --download-only
```

**1c. A chosen range — use a list file.** This is how episodes 30–53 were done.

```bash
for n in $(seq 30 53); do echo "${URL}?p=$n"; done > ~/BiliEN/doctory_30-53.txt
python3 bilien.py --list ~/BiliEN/doctory_30-53.txt --show "$SHOW" --browser chrome --download-only
```

List file format: one URL per line. Optional episode number after the URL (`URL 12`). Lines starting with `#` are skipped.

Options:

| Flag | What it does |
|---|---|
| `--browser chrome` | Use your Bilibili login from Chrome (needed for 1080p). Also `safari`, `firefox`. |
| `--quality 720` | Max height: `480`, `720`, `1080` (default `1080`). |
| `--ep 12` | Save a single URL as episode 12. |
| `--download-only` | Download now, translate later (Ollama not needed). |

**1d. Check what's missing:**

```bash
for n in $(seq 1 53); do
  f=$(printf "%s EP%02d (CN sub).mp4" "$SHOW" "$n")
  [[ -f ~/BiliEN/"$SHOW - Chinese Sub (raw)"/"$f" ]] || echo "missing $n"
done
find ~/BiliEN/_Work -name "*.part" -size -1M -delete     # remove broken partial files
```

**If you get blocked** (every CDN fails, ~509-byte files): stop. Wait 1–2 hours. Retrying right away can extend the block. Then update yt-dlp and re-run the same command (done episodes are skipped):

```bash
python3 -m pip install -U --user --break-system-packages "yt-dlp[default,curl-cffi]"
```

### Step 2 — Test one episode

Makes the files the AI needs in Step 3 (Chinese OCR, Whisper transcript) and an empty `_Work/<Show> profile.json`.

```bash
python3 bilien.py 1 --show "$SHOW"
```

### Step 3 — Set up the show profile (AI)

No script fills in the profile. **Give this job to an AI assistant that can read and edit your files**, e.g. Claude in Cowork with `~/BiliEN` connected.

Copy, change `<Show>`, and send:

> Fill in `~/BiliEN/_Work/<Show> profile.json` for the show `<Show>`.
> Use the Chinese OCR (`_Work/<Show> EP01 ZH ocr.srt`), the Whisper transcript (`<Show> - Subtitle Files/<Show> EP01 JA (whisper).srt`) and the English subs.
> Add the show title, every main character's name (what the audio says → English), and translation notes for anything the English got wrong.
> Then re-run episode 1 with `python3 bilien.py 1 --show "<Show>" --force` and check the English.

Repeat until episode 1 looks right.

<details>
<summary>Do it by hand: profile keys</summary>

```bash
open -e ~/BiliEN/_Work/"$SHOW profile.json"
```

| Key | What it is | Example |
|---|---|---|
| `title` | Show title, given to the translator | `"the Japanese medical comedy \"Doctor-Y\""` |
| `audio_lang` | Spoken language for Whisper | `"ja"` |
| `model` | Ollama model | `"qwen2.5:14b"` |
| `notes` | Extra translation rules, one string each | `"未知子 = Michiko (a name, never \"unknown\")."` |
| `names` | Regex of what the audio says → English name | `"秀樹\|ひでき": "Hideki"` |
| `safe_fixes` | `[regex, replacement]` run on every English line during translation | `["\\bHideo\\b", "Hideki"]` |
| `fixes` | `"wrong": "right"` text swaps before burning | `"Big Gate": "Daimon"` |
| `variant` | Optional running-joke word decided by the audio (see `check_town.py`) | `null` |
| `audio_only` | `true` if the video has no Chinese subs | `false` |

The starter file is made for you on the first run (Step 2). Fill in the keys above.

Then re-run: `python3 bilien.py 1 --show "$SHOW" --force`

</details>

### Step 4 — Make the rest of the episodes

**4a. A range** (skips finished episodes; logs to `_Work/run_all.log`):

```bash
caffeinate -i python3 bilien.py 2-53 --show "$SHOW"
```

Episode formats: `5`, `2-10`, `1,3,7`, `all` (every downloaded episode). `caffeinate -i` keeps the Mac awake. `bash run_all.sh 2-53 --show "$SHOW"` does the same thing.

**4b. Download + translate in one go** (no `--download-only`):

```bash
python3 bilien.py --list ~/BiliEN/doctory_30-53.txt --show "$SHOW" --browser chrome
```

**4c. Redo an episode that is already done:**

```bash
python3 bilien.py 7 --show "$SHOW" --force
```

**4d. Check for problems:**

```bash
grep -E "FAIL|UNTRANSLATED|ERROR|MISSING" ~/BiliEN/_Work/run_all.log
```

What `bilien.py` runs for each episode (skipping finished stages):

```
ocr_zh.py N → whisper_ja.py N → run_hybrid.py N
  → fix_names.py N --burn → check_town.py N (only if "variant" is set)
```

### Step 5 — Check and fix names (AI)

Chinese subs write Japanese names in Chinese characters, so the local model can guess the reading wrong (秀树 → "Hideo" instead of "Hideki"). **Give this job to an AI assistant** (e.g. Claude in Cowork with `~/BiliEN` connected).

Copy, change `<Show>` and the episodes, and send:

> Check the English subs for `<Show>` episodes 2–53 against the Whisper transcripts in `<Show> - Subtitle Files/`.
> Find wrong names and wrong words. Add fixes to `~/BiliEN/_Work/<Show> profile.json`.
> Re-burn the changed episodes (re-translate first if you changed `names`, `notes` or `safe_fixes`).
> Also fix any `[UNTRANSLATED]` lines in `_Work/run_all.log`.

Do this again after each new batch of episodes.

<details>
<summary>Do it by hand: commands</summary>

**List every name-like word in the English subs:**

```bash
grep -h -v -- "-->" ~/BiliEN/"$SHOW - Subtitle Files"/*EN.srt \
  | grep -o -E "\b[A-Z][a-z]+\b" | sort | uniq -c | sort -rn > ~/Desktop/names_found.txt
open ~/Desktop/names_found.txt
```

**Find name lines in the Whisper transcript:**

```bash
grep -E "[ァ-ヴー]{3,}|さん|様|くん|ちゃん|殿|先生" \
  ~/BiliEN/"$SHOW - Subtitle Files"/"$SHOW EP01 JA (whisper).srt"
```

Use Whisper for names only; it mishears sound-alikes.

**Where to put the fix:**

| Problem | Put it in | Then run |
|---|---|---|
| Wrong English word after translation | `fixes` | `python3 fix_names.py all --show "$SHOW"` |
| Audio says a name the model reads wrong | `names` | `run_hybrid.py N` + `fix_names.py N --burn` |
| Model keeps writing a wrong word | `safe_fixes` or `notes` | `run_hybrid.py N` + `fix_names.py N --burn` |

`run_hybrid.py` **overwrites hand edits** in the `.ass` file.

```bash
python3 run_hybrid.py 7 --show "$SHOW"
python3 fix_names.py 7 --show "$SHOW" --burn
```

</details>

<details>
<summary>Example name table (Doctor-Y)</summary>

| Character / place | Japanese | Chinese subs | English |
|---|---|---|---|
| Main character | 加地秀樹 | 加地秀树 | Hideki Kaji (Dr. Kaji) |
| *Doctor-X* lead | 大門未知子 | 大门未知子 / 未知子 | Michiko Daimon |
| Nickname for Michiko | デーモン | 恶魔 / 魔鬼 | Demon |
| University | 帝都 | 帝都 | Teito Medical University |
| Patient | 三船遥 | 三船遥 | Haruka Mifune |
| Others | 神原晶 / 城之内 / 海老名 / 那須 | | Akira Kanbara / Jonouchi / Ebina / Nasu |
| Town joke | 大洗 | 大洗 | Ōarai (Michiko says "Daisen") |

</details>

### Step 6 — Fix single lines (AI, optional)

While watching, note any bad line: episode, time, what it says. **Give the list to an AI assistant** (e.g. Claude in Cowork with `~/BiliEN` connected).

Copy, fill in, and send:

> Fix these lines in `<Show>`, then re-burn those episodes:
> - EP07 at 12:34 — says "This guy is dead", should be "He hung up on me"
> - EP30 at 05:10 — still in Chinese
> If the same mistake can happen in other episodes, add it to `fixes` in `_Work/<Show> profile.json` too.

The AI edits `<Show> EPNN EN.ass` and runs `python3 fix_names.py N --show "<Show>" --burn`.

<details>
<summary>Do it by hand: Aegisub</summary>

1. Install Aegisub: https://aegisub.org
2. Open `~/BiliEN/<Show> - Subtitle Files/<Show> EPNN EN.ass`, then **Video → Open Video** → the matching `(CN sub).mp4`.
3. Fix lines. Save.
4. Re-burn that episode:

```bash
python3 fix_names.py 7 --show "$SHOW" --burn
```

Tip: to check a line without reading Chinese, pause the original in QuickTime, drag over the Chinese, then right-click → **Translate** (Live Text).

Note: re-running `run_hybrid.py` on that episode **erases** hand edits. Put repeat fixes in the profile `fixes` instead.

</details>

### Step 7 — Watch

```bash
open ~/BiliEN/"$SHOW - English Sub"/"$SHOW EP01 (EN sub).mp4"
```

---

## Run one stage by hand

Every script takes an episode spec (`5`, `2-10`, `1,3,7`, `all`) and `--show`. `--show` can be left out if there is only one show in `~/BiliEN`.

```bash
python3 ocr_zh.py 7 --show "$SHOW"            # OCR (add --redo to overwrite)
python3 whisper_ja.py 7 --show "$SHOW"        # audio transcript + word timing
python3 run_hybrid.py 7 --show "$SHOW"        # translate
python3 fix_names.py 7 --show "$SHOW" --burn  # apply fixes + burn
python3 check_town.py 7 --show "$SHOW"        # optional "variant" check
```

What to re-run after a change:

| You changed… | Run |
|---|---|
| The `.ass` by hand | `fix_names.py N --burn` |
| `fixes` in the profile | `fix_names.py N` (re-burns only if text changed) |
| `names`, `notes`, `safe_fixes`, `title` | `run_hybrid.py N`, then `fix_names.py N --burn` |
| OCR area (`CROP` / `TOP_CROP` in `ocr_zh.py`) | `ocr_zh.py N --redo`, then `run_hybrid.py N`, then burn |

OCR notes (`ocr_zh.py`):

- Reads 2 frames per second. Bottom area: `CROP`. Top area: `TOP_CROP`.
- If subs move to the **top** during end credits (2+ s, 3+ changing lines), the top is used and the bottom (credits) is ignored.
- Text that never changes (an uploader watermark) and promo lines (微博, 字幕组, 转载…) are dropped.

---

## Videos with no Chinese subs (audio only)

1. Name the input `<Show> EP01 (raw).mp4` and put it in `~/BiliEN/<Show> - Chinese Sub (raw)/`.
2. Run:

```bash
python3 bilien.py 1 --show "$SHOW" --audio-only
```

- Stages: `whisper_ja.py` → `run_audio.py` → `fix_names.py --burn`.
- English is drawn as outlined text, **no black box**.
- To make it the default for a show, set `"audio_only": true` in the profile.
- Spoken language comes from `"audio_lang"` (default `ja`).

---

## Subtitle any other video file

**Easiest:** treat it as a show. Copy it into the layout, then run `bilien.py`.

```bash
SHOW="My Video"
mkdir -p ~/BiliEN/"$SHOW - Chinese Sub (raw)"
cp ~/Downloads/myvideo.mp4 ~/BiliEN/"$SHOW - Chinese Sub (raw)"/"$SHOW EP01 (CN sub).mp4"
python3 bilien.py 1 --show "$SHOW"                 # has burned-in Chinese
# or: name it "(raw).mp4" and add --audio-only    # no Chinese subs
```

**You already have an `.srt`:**

```bash
cd ~/BiliEN
# Soft subs (toggle on/off, no re-encode)
ffmpeg -i myvideo.mp4 -i myvideo.srt -c copy -c:s mov_text myvideo_subbed.mp4
# Burned-in subs (always visible)
ffmpeg -y -i myvideo.mp4 -vf "subtitles=myvideo.srt" -c:a copy myvideo_EN.mp4
```

Remove spaces from the file name first when using `subtitles=` directly (`mv "my video.mp4" myvideo.mp4`). No-code option: same folder + same name, open in VLC.

---

## Watch on bilibili.com (overlay)

Shows your English `.srt` on top of the Bilibili player.

1. Install Tampermonkey in Chrome. Add `bili-english-overlay.user.js`.
2. Share the BiliEN folder:

```bash
cd ~/BiliEN && python3 -m http.server 8765
```

3. In Tampermonkey's menu, click **Set BiliEN server** → `http://127.0.0.1:8765/`.
4. Open the episode on bilibili.com. The script finds it through `_Work/index.json`.

---

## Windows and Linux

The scripts pick the right tools by themselves:

| Stage | Mac | Windows / Linux |
|---|---|---|
| OCR (`ocr_zh.py`) | Apple Vision (`ocrmac`) | RapidOCR (`rapidocr_onnxruntime`) |
| Audio (`whisper_ja.py`) | `mlx-whisper` | `faster-whisper` (NVIDIA GPU if you have one, else CPU) |
| Download, translate, burn | same | same |

> Not yet tested on a real Windows PC. Without an NVIDIA GPU, Whisper and the 14B model are slow. For a faster test: `BILIEN_WHISPER=medium` (smaller Whisper) and `"model": "qwen2.5:7b"` in the profile.

### Windows — Option A: WSL2 (recommended)

WSL2 runs Ubuntu inside Windows. Then every command in this README works as written, using the Linux column below.

1. Open **PowerShell as Administrator**. Run:

```powershell
wsl --install
```

2. Restart the PC. Open **Ubuntu** from the Start menu. Make a username and password.
3. In Ubuntu, run:

```bash
sudo apt update && sudo apt install -y ffmpeg python3-pip git
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b
python3 -m pip install --user --break-system-packages \
  "yt-dlp[default,curl-cffi]" rapidocr_onnxruntime faster-whisper requests
git clone https://github.com/<your-username>/bili2en.git && cd bili2en
mkdir -p ~/BiliEN
```

4. Use `--browser firefox` in Step 1 (see the Chrome note below).
5. Your videos are in `\\wsl$\Ubuntu\home\<you>\BiliEN` in File Explorer.

### Windows — Option B: native (PowerShell)

1. Install tools:

```powershell
winget install Python.Python.3.12 Gyan.FFmpeg Ollama.Ollama Git.Git
```

2. Close and reopen PowerShell. Then:

```powershell
ollama pull qwen2.5:14b
py -m pip install "yt-dlp[default,curl-cffi]" rapidocr_onnxruntime faster-whisper requests
git clone https://github.com/<your-username>/bili2en.git; cd bili2en
mkdir $HOME\BiliEN
```

3. Set variables (PowerShell syntax):

```powershell
$SHOW = "Doctor Y"
$URL  = "https://www.bilibili.com/video/BV1a5ECzqE4B/"
```

4. Run the same steps with `py` instead of `python3`:

```powershell
py bilien.py "$URL" --show "$SHOW" --browser firefox --download-only
py bilien.py 1 --show "$SHOW"
py bilien.py 2-53 --show "$SHOW"
```

### Linux

```bash
sudo apt install -y ffmpeg python3-pip
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b
python3 -m pip install --user --break-system-packages \
  "yt-dlp[default,curl-cffi]" rapidocr_onnxruntime faster-whisper requests
```

### Command swaps

| macOS | Linux / WSL2 | Windows (PowerShell) |
|---|---|---|
| `brew install ffmpeg ollama` | `sudo apt install ffmpeg` + Ollama script | `winget install Gyan.FFmpeg Ollama.Ollama` |
| `brew services start ollama` | `sudo systemctl start ollama` or `ollama serve` | Ollama starts with Windows (tray icon) |
| `python3` | `python3` | `py` |
| `SHOW="Doctor Y"` | same | `$SHOW = "Doctor Y"` |
| `~/BiliEN` | `~/BiliEN` | `$HOME\BiliEN` |
| `open video.mp4` | `xdg-open video.mp4` | `start video.mp4` |
| `open -e file` | `nano file` | `notepad file` |
| `caffeinate -i cmd` | `systemd-inhibit cmd` | Settings → System → Power → Sleep: Never |
| `grep -E "FAIL\|ERROR" file` | same | `Select-String "FAIL\|ERROR" file` |
| `--browser chrome` | `--browser chrome` or `firefox` | `--browser firefox` |
| `~/.zshrc` | `~/.bashrc` | — |

### Notes

- **Chrome login on Windows:** newer Chrome encrypts cookies so yt-dlp often can't read them. Log in to bilibili.com in **Firefox** and use `--browser firefox`.
- **Whisper size:** default `large-v3`. Set a smaller one with `BILIEN_WHISPER=medium` (Linux/WSL) or `$env:BILIEN_WHISPER="medium"` (PowerShell).
- **First run downloads models:** RapidOCR (small) and Whisper large-v3 (~3 GB).
- **NVIDIA GPU:** `faster-whisper` uses it automatically if CUDA 12 + cuDNN are installed. Otherwise it uses the CPU.

---

## Scripts

| File | What it does |
|---|---|
| `bilien.py` | **Main entry.** Download (URL, series, or `--list`) + run every stage per episode. |
| `show.py` | Only place that knows folders/file names. Creates the profile. |
| `ocr_zh.py` | Chinese OCR (ocrmac on Mac, RapidOCR elsewhere), bottom + top of frame, watermark/promo filter → `ZH ocr.srt`. |
| `whisper_ja.py` | Audio transcript + word timing (mlx-whisper on Mac, faster-whisper elsewhere; anti-loop settings). |
| `run_hybrid.py` | Chinese + audio → English with Ollama. Audio decides names. |
| `run_audio.py` | Audio-only translation (`--audio-only`). |
| `fix_names.py` | Applies profile `fixes`; `--burn` makes the video. |
| `check_town.py` | Flags lines where the profile `variant` word doesn't match the audio. |
| `run_all.sh` | Shortcut for `python3 bilien.py "$@"`. |
| `bili2en.py` | Downloader (`download()`, `clean_url()`), `.ass` writer, older all-in-one pipeline. |
| `bili-english-overlay.user.js` | Tampermonkey: shows the `.srt` over bilibili.com. |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Ollama is not running` | `brew services start ollama`, or add `--download-only` |
| `More than one show … Add --show` | Add `--show "Name"` |
| `No show yet` | Add `--show "Name"` on the first run |
| `[MISSING] …(CN sub).mp4` | Download first, or check the file name (`EP01`, 2 digits) |
| `[UNTRANSLATED]` in log | Garbled OCR or unknown name. Kept in Chinese. Ask the AI to fix it (Step 5/6). |
| `zsh: command not found: pip` | Use `python3 -m pip ...` |
| `externally-managed-environment` | Add `--user --break-system-packages` |
| `command not found: mlx_whisper` | Do Install step 6 (PATH) |
| `No OCR found` | Mac: `pip install ocrmac`. Windows/Linux: `pip install rapidocr_onnxruntime` |
| `No Whisper found` | Mac: `pip install mlx-whisper`. Windows/Linux: `pip install faster-whisper` |
| Chrome cookies fail on Windows | Use `--browser firefox` |
| `curl_cffi not installed` warning | `python3 -m pip install --user --break-system-packages "yt-dlp[default,curl-cffi]"` |
| HTTP 567 | Bilibili firewall. Script tries other CDN mirrors automatically. |
| "No video formats found" | Impersonation must be on the download only (already handled in `bili2en.py`). Update yt-dlp. |
| ~509 bytes read, all CDNs fail | Rate-limited. Wait 1–2 hours, then re-run. Done episodes are skipped. |
| Only 480p/720p downloaded | Add `--browser chrome` and be logged in to bilibili.com in Chrome. |
| End credits show as subtitles | Fixed by top-of-frame detection. Re-run `ocr_zh.py N --redo`. |
| Channel watermark in subs | Auto-dropped. If not, add the text to `PROMO` in `ocr_zh.py` and `--redo`. |
| Lines missing in OCR | `pip install rapidocr_onnxruntime` (backup reader), then `--redo`. |
| Fixes lost after re-translating | `run_hybrid.py` overwrites `EN.ass`. Keep repeat fixes in the profile `fixes`. |
| Terminal shows `heredoc>` | The `EOF` line has leading spaces. Ctrl+C and re-paste. |
| `zsh: no matches found` | A glob matched nothing. Quote it or remove it. |
| Output cut off | `… > ~/Desktop/out.txt; open ~/Desktop/out.txt` |

---

## References

- yt-dlp: https://github.com/yt-dlp/yt-dlp (HTTP 567 / impersonation: issue #17847)
- curl_cffi: https://github.com/lexiforest/curl_cffi
- ocrmac: https://github.com/straussmaximilian/ocrmac
- RapidOCR: https://github.com/RapidAI/RapidOCR
- mlx-whisper: https://github.com/ml-explore/mlx-examples/tree/main/whisper
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Ollama: https://ollama.com
- Qwen2.5: https://github.com/QwenLM/Qwen2.5
- FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- ASS override tags: https://aegisub.org/docs/latest/ass_tags/
- Bilibili's exact rate limits: unknown.
