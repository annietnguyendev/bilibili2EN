# Windows and Linux

Back to [README](../README.md).

The scripts pick the right tools by themselves:

| Stage | Mac | Windows / Linux |
|---|---|---|
| OCR (`ocr_zh.py`) | Apple Vision (`ocrmac`) | RapidOCR (`rapidocr_onnxruntime`) |
| Audio (`whisper_ja.py`) | `mlx-whisper` | `faster-whisper` (NVIDIA GPU if you have one, else CPU) |
| Download, translate, burn | same | same |

> Not yet tested on a real Windows PC. Without an NVIDIA GPU, Whisper and the 14B model are slow. For a faster test: `BILIEN_WHISPER=medium` (smaller Whisper) and `"model": "qwen2.5:7b"` in the profile.

## Windows — Option A: WSL2 (recommended)

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

## Windows — Option B: native (PowerShell)

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

## Linux

```bash
sudo apt install -y ffmpeg python3-pip
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b
python3 -m pip install --user --break-system-packages \
  "yt-dlp[default,curl-cffi]" rapidocr_onnxruntime faster-whisper requests
```

## Command swaps

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

## Notes

- **Chrome login on Windows:** newer Chrome encrypts cookies so yt-dlp often can't read them. Log in to bilibili.com in **Firefox** and use `--browser firefox`.
- **Whisper size:** default `large-v3`. Set a smaller one with `BILIEN_WHISPER=medium` (Linux/WSL) or `$env:BILIEN_WHISPER="medium"` (PowerShell).
- **First run downloads models:** RapidOCR (small) and Whisper large-v3 (~3 GB).
- **NVIDIA GPU:** `faster-whisper` uses it automatically if CUDA 12 + cuDNN are installed. Otherwise it uses the CPU.


