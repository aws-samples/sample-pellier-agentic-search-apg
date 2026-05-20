#!/usr/bin/env bash
# mov-to-gif.sh — convert a QuickTime .mov to lab-content/builders/static/imgs/chatui.gif
#
# Usage:
#   scripts/demo/mov-to-gif.sh ~/Desktop/pellier-demo.mov
#   scripts/demo/mov-to-gif.sh ~/Desktop/pellier-demo.mov 1080 10   # custom width / fps
#
# Defaults: 1280 px wide, 12 fps, two-pass palette encode.
# Requires: ffmpeg (brew install ffmpeg)

set -euo pipefail

INPUT="${1:?usage: $0 <input.mov> [width=1280] [fps=12]}"
WIDTH="${2:-1280}"
FPS="${3:-12}"

if [[ ! -f "$INPUT" ]]; then
  echo "no such file: $INPUT" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO_ROOT/lab-content/builders/static/imgs/chatui.gif"
PALETTE="$(mktemp -t chatui-palette).png"
# Apple Silicon QuickTime tags screen recordings with Display P3 primaries
# even though the content is plain SDR. Without an explicit colorspace
# conversion, palettegen reads the YUV in the wrong primaries and the GIF
# comes out desaturated or grayscale. We use `colorspace` (built into every
# ffmpeg) to force a bt709 SDR conversion, then format=rgb24 for the palette.
FILTER_PRE="fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,colorspace=all=bt709:iall=bt470bg:fast=1,format=rgb24"

mkdir -p "$(dirname "$OUT")"

echo "[mov-to-gif] input  : $INPUT"
echo "[mov-to-gif] output : $OUT"
echo "[mov-to-gif] width  : ${WIDTH}px @ ${FPS} fps"

# Pass 1: build palette (full color stats to keep saturation)
ffmpeg -hide_banner -loglevel error -y \
  -i "$INPUT" \
  -vf "${FILTER_PRE},palettegen=stats_mode=full" \
  "$PALETTE"

# Pass 2: encode using palette
ffmpeg -hide_banner -loglevel error -y \
  -i "$INPUT" -i "$PALETTE" \
  -lavfi "${FILTER_PRE} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4" \
  "$OUT"

rm -f "$PALETTE"

echo
echo "--- chatui.gif ---"
ls -lh "$OUT"
ffprobe -v error -count_frames \
  -select_streams v:0 \
  -show_entries stream=width,height,nb_read_frames,r_frame_rate,duration \
  -of default=nw=1 \
  "$OUT"

SIZE_BYTES=$(stat -f '%z' "$OUT" 2>/dev/null || stat -c '%s' "$OUT")
SIZE_MB=$(awk -v b="$SIZE_BYTES" 'BEGIN { printf "%.2f", b/1024/1024 }')
echo "size_mb=${SIZE_MB}"

if (( $(echo "$SIZE_MB > 10" | bc -l) )); then
  echo
  echo "[mov-to-gif] over 10 MB. Try a smaller width or lower fps:"
  echo "    $0 $INPUT 1080 10"
fi
