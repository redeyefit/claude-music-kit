#!/usr/bin/env bash
# One-time setup on a Mac. Safe to re-run (skips what's already there).
#   ./setup.sh            installs: ffmpeg (with rubberband), whisper.cpp, Python venv + audio libs, Whisper model
# Needs Homebrew (https://brew.sh). Takes ~5 min, ~2 GB (mostly PyTorch for Demucs + the Whisper model).
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
KIT="$(cd "$(dirname "$0")" && pwd)"
cd "$KIT"
log() { echo "[$(date '+%H:%M:%S')] $*"; }

command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
for f in ffmpeg whisper-cpp python@3.14; do
  if brew list --formula "$f" >/dev/null 2>&1; then log "have $f"; else log "installing $f"; brew install "$f"; fi
done
# fit.py conforms tempo/key with ffmpeg's rubberband filter; Homebrew's ffmpeg includes it, check anyway
ffmpeg -hide_banner -filters 2>/dev/null | grep -q rubberband || { echo "ffmpeg lacks the rubberband filter"; exit 1; }

PY="$(brew --prefix python@3.14)/bin/python3.14"
if [ ! -x venv/bin/python ]; then log "creating venv"; "$PY" -m venv venv; fi
log "installing Python packages"
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

M=models/ggml-small.bin
if [ ! -s "$M" ]; then
  log "downloading Whisper model (small, ~490 MB)"
  curl -L --fail -o "$M.part" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
  mv "$M.part" "$M"
fi
[ -f .env ] || { cp .env.example .env; chmod 600 .env; log "created .env: paste your ElevenLabs key into it"; }
log "done. Check it: ./test.sh"
