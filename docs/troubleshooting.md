# Troubleshooting

Back to [README](../README.md).

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


