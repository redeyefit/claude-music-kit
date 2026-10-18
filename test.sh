#!/usr/bin/env bash
# Smoke test: proves the kit works on this Mac. ~30 s, offline, spends no credits.
#   ./test.sh            core: ffmpeg, mixlib master, fit.py tempo+key lock, whisper transcription
#   ./test.sh --stems    + Demucs on the test loop (first run downloads its model)
#   ./test.sh --eleven   + one 5-second ElevenLabs sound effect (spends a few credits)
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
KIT="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-$KIT/venv/bin/python}"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT INT TERM
pass=0; fail=0
ok()  { echo "  PASS $*"; pass=$((pass + 1)); }
bad() { echo "  FAIL $*"; fail=$((fail + 1)); }

echo "== tools"
for c in ffmpeg whisper-cli; do command -v "$c" >/dev/null && ok "$c" || bad "$c missing (./setup.sh)"; done
[ -x "$PY" ] && ok "python venv" || { bad "venv missing (./setup.sh)"; exit 1; }

echo "== fixture: 8-bar A minor loop at 100 BPM (kick + chords), to be locked to 97 BPM C#m"
"$PY" - "$T" "$KIT/tools" <<'PYEOF'
import sys, numpy as np
sys.path.insert(0, sys.argv[2])
from mixlib import SR, save
bpm, bars = 100.0, 8
beat = 60 / bpm
n = int(bars * 4 * beat * SR)
t = np.arange(n) / SR
y = np.zeros(n)
for b in range(bars * 4):                      # kick every beat
    i = int(b * beat * SR); k = np.arange(int(0.25 * SR)); kt = k / SR
    y[i:i + len(k)] += 0.8 * np.sin(2 * np.pi * (50 + 80 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
# Am Dm E Am (the E major chord's G# only exists in A minor) + a bass root, so the key reads unambiguously;
# Am F C G read as E minor here: the fixture was ambiguous, not fit.py
prog = [[45, 57, 60, 64], [38, 57, 62, 65], [40, 56, 59, 64], [45, 57, 60, 64]]
for bar in range(bars):
    i0, i1 = int(bar * 4 * beat * SR), int((bar + 1) * 4 * beat * SR)
    tt = t[i0:i1] - t[i0]
    for m in prog[bar % 4]:
        f = 440 * 2 ** ((m - 69) / 12)
        y[i0:i1] += 0.12 * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 0.8)
save(f"{sys.argv[1]}/loop.wav", np.stack([y, y]).astype(np.float32))
PYEOF
[ -s "$T/loop.wav" ] && ok "fixture rendered" || bad "fixture"

echo "== mixlib.master hits its loudness target"
out="$("$PY" - "$T/loop.wav" "$KIT/tools" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[2])
from mixlib import load, master, lufs
import numpy as np
y = master(load(sys.argv[1]), target_lufs=-12.0)
print(f"{lufs(y):.2f} {np.abs(y).max():.3f}")
PYEOF
)"
read -r L P <<< "$out"
awk -v l="$L" -v p="$P" 'BEGIN{exit !(l > -12.75 && l < -11.25 && p <= 0.90)}' \
  && ok "master: $L LUFS, peak $P" || bad "master: got '$out' (want -12 +-0.75 LUFS, peak <= 0.89)"

echo "== fit.py locks 100 BPM A minor -> 97 BPM C# minor"
line="$("$PY" "$KIT/tools/fit.py" "$T/loop.wav" --bpm 97 --key C#m -o "$T/fit.wav" 2>&1 | tail -1)"
echo "     $line"
echo "$line" | grep -q "shift +4 st" && ok "key: shifted +4 semitones" || bad "key shift (want +4)"
ob="$(echo "$line" | sed -n 's/.*out: \([0-9.]*\) BPM \([A-G#m]*\).*/\1 \2/p')"
read -r OB OK <<< "$ob"
awk -v b="${OB:-0}" 'BEGIN{exit !(b > 96.7 && b < 97.3)}' && ok "tempo out: $OB" || bad "tempo out: '$OB' (want 97)"
[ "${OK:-}" = "C#m" ] || [ "${OK:-}" = "E" ] && ok "key out: $OK" || bad "key out: '$OK' (want C#m)"

echo "== examples/song_template.py arranges + masters the fitted loop"
"$PY" "$KIT/examples/song_template.py" --bpm 97 --drums "$T/fit.wav" --keys "$T/fit.wav" -o "$T/song.wav" > "$T/song.log" 2>&1
sl="$(tail -1 "$T/song.log")"
echo "$sl" | grep -qE "\(1[0-9][0-9]\.[0-9] s, -1[01]\.[0-9] LUFS" && ok "song: ${sl#*  }" || bad "song template: $sl"

echo "== whisper transcribes speech"
say -o "$T/speech.aiff" "the quick brown fox jumps over the lazy dog" 2>/dev/null \
  && "$KIT/tools/transcribe.sh" "$T/speech.aiff" >/dev/null 2>&1
grep -qi "brown fox" "$T/speech.txt" 2>/dev/null && ok "whisper: '$(tr -d '\n' < "$T/speech.txt" | cut -c1-60)'" \
  || bad "whisper (model downloaded? ./setup.sh)"

for flag in "$@"; do case "$flag" in
  --stems)
    echo "== demucs splits stems"
    "$KIT/tools/stems.sh" "$T/loop.wav" "$T/stems" >/dev/null 2>&1
    ls "$T/stems/htdemucs/loop/"{drums,bass,other,vocals}.wav >/dev/null 2>&1 && ok "4 stems" || bad "demucs" ;;
  --eleven)
    echo "== elevenlabs sound effect (spends credits)"
    "$PY" "$KIT/tools/eleven.py" sfx "a single hand clap in a small room" --seconds 2 -o "$T/clap.mp3" >/dev/null 2>&1
    [ -s "$T/clap.mp3" ] && ok "elevenlabs sfx" || bad "elevenlabs (key in .env? credits?)" ;;
esac; done

echo "== $pass passed, $fail failed"
[ "$fail" = 0 ]
