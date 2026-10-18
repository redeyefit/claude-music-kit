#!/usr/bin/env bash
# Split a song into stems with Demucs (htdemucs). First run downloads the model (~80 MB).
#   tools/stems.sh IN [OUTDIR] [--two]     --two = vocals + no_vocals only (faster, best for acapellas/instrumentals)
# Output: OUTDIR/htdemucs/<song>/{drums,bass,other,vocals}.wav   (default OUTDIR: projects/stems)
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 1 ] || { echo "usage: tools/stems.sh IN [OUTDIR] [--two]"; exit 2; }
two=0; args=()
for a in "$@"; do [ "$a" = "--two" ] && two=1 || args+=("$a"); done
in="${args[0]}"; out="${args[1]:-$KIT/projects/stems}"; extra=()
[ "$two" = 1 ] && extra=(--two-stems vocals)
mkdir -p "$out"
"${PY:-$KIT/venv/bin/python}" -m demucs -n htdemucs ${extra[@]+"${extra[@]}"} -o "$out" "$in"
echo "stems -> $out/htdemucs/$(basename "${in%.*}")/"
