# Studio

Tools for making videos with agents: songs and talking videos.

- `songs/` - song shorts. A singer records a song; the pipeline finds its home note and raga, writes a light
  background score that follows the singer, and animates two vector characters acting out the meaning of each line,
  with the English meaning as the headline. See `songs/README.md`.

Productions (words, takes, renders) live in a separate content checkout, `$STUDIO_CONTENT`, not in this repo.

Setup:

```bash
cd songs && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
(cd remotion && npm install)
```

Needs ffmpeg and Rubber Band (`brew install ffmpeg rubberband`).
