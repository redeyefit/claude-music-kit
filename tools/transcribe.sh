#!/usr/bin/env bash
# Lyrics / speech -> text with timestamps, via whisper.cpp (local, free, no upload).
#   tools/transcribe.sh IN [MODEL]     MODEL default: models/ggml-small.bin (setup.sh downloads it)
# Writes IN.txt (plain), IN.srt (timed lines) and IN.json (word timings) next to the input.
# Whisper needs 16 kHz mono WAV, so the input is converted first. Isolate the vocal with tools/stems.sh --two
# first if there's a beat under it: whisper hallucinates lyrics over loud music.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 1 ] || { echo "usage: tools/transcribe.sh IN [MODEL]"; exit 2; }
in="$1"; model="${2:-$KIT/models/ggml-small.bin}"
[ -f "$model" ] || { echo "model missing: $model (run ./setup.sh)"; exit 1; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT INT TERM
ffmpeg -hide_banner -loglevel error -y -i "$in" -ar 16000 -ac 1 -c:a pcm_s16le "$tmp/a.wav"
base="${in%.*}"
whisper-cli -m "$model" -f "$tmp/a.wav" -l auto --no-prints -otxt -osrt -oj -ojf -of "$base"
echo "-> $base.txt / .srt / .json"
