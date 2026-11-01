#!/bin/zsh
# Whole pipeline for one song: analyze the take -> score -> mix -> Remotion -> $STUDIO_CONTENT/build/<song>/<song>_short.mp4
# usage: ./render.sh <song>            (add --retime to re-derive $STUDIO_CONTENT/songs/<song>/timing.json)
# Heavy: run through the queue, e.g.
#   sm queue run --type background --memory 16G --timeout 60m --label song-<song> --cwd $PWD -- zsh -lc './render.sh <song>'
set -euo pipefail
cd "${0:A:h}"
P=${1:?poem}; shift
.venv/bin/python analyze.py "$P" "$@"
.venv/bin/python score.py "$P"
.venv/bin/python mix.py "$P"
OUT=$(.venv/bin/python -c "from common import build_dir; print(build_dir('$P'))")
(cd remotion && npx remotion render LyricShort "out/${P}_raw.mp4" --props="{\"poem\":\"$P\",\"tl\":null}" \
  --codec=h264 --crf=18 --timeout=180000 ${CONCURRENCY:+--concurrency=$CONCURRENCY})
ffmpeg -v error -y -i "remotion/out/${P}_raw.mp4" -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$OUT/${P}_short.mp4"
echo "done -> $OUT/${P}_short.mp4"
