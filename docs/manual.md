# Manual steps and extras

Back to [README](../README.md).

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


## Download options

**A chosen range — use a list file:**

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

**Check what's missing:**

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

## Check the run log

```bash
grep -E "FAIL|UNTRANSLATED|ERROR|MISSING" ~/BiliEN/_Work/run_all.log
```

## Show profile keys

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


## Check names by hand


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


## Example name table (Doctor-Y)


| Character / place | Japanese | Chinese subs | English |
|---|---|---|---|
| Main character | 加地秀樹 | 加地秀树 | Hideki Kaji (Dr. Kaji) |
| *Doctor-X* lead | 大門未知子 | 大门未知子 / 未知子 | Michiko Daimon |
| Nickname for Michiko | デーモン | 恶魔 / 魔鬼 | Demon |
| University | 帝都 | 帝都 | Teito Medical University |
| Patient | 三船遥 | 三船遥 | Haruka Mifune |
| Others | 神原晶 / 城之内 / 海老名 / 那須 | | Akira Kanbara / Jonouchi / Ebina / Nasu |
| Town joke | 大洗 | 大洗 | Ōarai (Michiko says "Daisen") |


## Fix single lines by hand (Aegisub)


1. Install Aegisub: https://aegisub.org
2. Open `~/BiliEN/<Show> - Subtitle Files/<Show> EPNN EN.ass`, then **Video → Open Video** → the matching `(CN sub).mp4`.
3. Fix lines. Save.
4. Re-burn that episode:

```bash
python3 fix_names.py 7 --show "$SHOW" --burn
```

Tip: to check a line without reading Chinese, pause the original in QuickTime, drag over the Chinese, then right-click → **Translate** (Live Text).

Note: re-running `run_hybrid.py` on that episode **erases** hand edits. Put repeat fixes in the profile `fixes` instead.


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


## Watch on bilibili.com (overlay)

Shows your English `.srt` on top of the Bilibili player.

1. Install Tampermonkey in Chrome. Add `bili-english-overlay.user.js`.
2. Share the BiliEN folder:

```bash
cd ~/BiliEN && python3 -m http.server 8765
```

3. In Tampermonkey's menu, click **Set BiliEN server** → `http://127.0.0.1:8765/`.
4. Open the episode on bilibili.com. The script finds it through `_Work/index.json`.


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
