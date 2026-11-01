# Songs

Vertical (1080×1920) song shorts about what a song means. A singer records the vocal. The pipeline reads its pitch
and phrasing, writes a light background score in the same raga and Sa (the home note), and animates vector
characters with the meaning of each line on screen. All audio and pictures are generated.

## Where songs live

Songs are not in this repo. Each one is a folder in a content checkout, `$STUDIO_CONTENT` (default
`../../studio-content` from here):

```
$STUDIO_CONTENT/
  songs/<song>/poem.json        words, meanings, scene per line, music settings
  songs/<song>/timing.json      when each sung line starts and ends (written by analyze.py; hand edits are kept)
  songs/<song>/marks.json       the singer's own line marks from the recording studio (preferred over guessing)
  songs/<song>/vocals.wav       the take (any recording in the folder works; the newest is used)
  songs/<song>/takes/           takes from the recording studio
  songs/<song>/reference/       the original recording, used to find Sa and the raga
  build/<song>/                 everything generated, including <song>_short.mp4
```

## Steps

| Step | File | What it does |
| --- | --- | --- |
| Analyze | `analyze.py` | Tracks pitch (pyin), takes Sa from the recording studio's guide or the reference recording (falling back to held notes and phrase endings), lists the swaras sung, finds breath phrases, and times each line from the singer's marks (or by matching phrases to syllable counts). A spoken hook before the singing (`spoken_intro`) is kept for the video and left out of the pitch analysis. |
| Score | `score.py` | Tanpura on Sa (a Pa string, or Ma if the raga has no Pa); a flute or violin that answers in the singer's pauses by replaying the phrase just sung; a swarmandal glissando through the raga's notes at scene changes; temple bells; optional mridangam. |
| Mix | `mix.py` | Light vocal leveling and reverb, optional Rubber Band retune of the voice, the score ducked under the voice, loudness to -14 LUFS, then `prepare.py` writes the timeline for the animation. |
| Animate | `remotion/` | `LyricShort` draws the sky, one motif scene per run of lines, the two characters acting out the song (`Duet.tsx`), a gold thread tracing the sung pitch, gloss chips, the lyrics (English meaning first, then Devanagari, then the transliteration lit as each word is sung), and the hook and title cards. `Thumbnail` renders a frame with the text hidden and a headline. |
| Record | `sing_studio.py` | A browser page on port 9400: previews a guide (original, karaoke, tanpura, or a mix) in the earbuds, records the USB mic, and takes line marks from the mouse wheel. |

`./render.sh <song>` runs analyze, score, mix and the render. It's heavy, so run it through the queue.

## Settings (`music` in poem.json)

| Setting | What it does |
| --- | --- |
| `reference` | path (inside the song folder) of the original recording: sets Sa and the raga's notes |
| `tonic_hz` | force Sa |
| `score` | `"none"` for voice only |
| `stems` | parts to keep, e.g. `["tanpura"]`; default all |
| `levels` | per-part trims in dB: `tanpura`, `follow`, `swarmandal`, `bells`, `percussion` |
| `score_db` | the whole score up or down |
| `drone_after_hook` | start the tanpura after the spoken hook |
| `tonic_offset_cents` | tune the score to where the take sits (100 cents = one semitone) |
| `vocal_shift_cents` | retune the voice instead (Rubber Band R3, formants kept) |
| `follow` | `flute`, `violin` or `none` |
| `percussion` | `null`, or `{"bpm", "offset", "pattern"}` |
| `intro_s` / `outro_s` | seconds before the first line and after the last |

## Tools

- `node stills.mjs <song> <out_dir> 3 12.5 s2` renders those times (or the middle of scene 2) and tiles them into `<out_dir>/sheet.png`.
- `node thumbs.mjs <song> <out_dir> '[{"name":"A","at":24,"headline":"…","sub":"…"}]'` renders thumbnail candidates.
- `make_test_vocal.py <song>` synthesizes a stand-in take so the pipeline runs before a real one exists.
- Karaoke guide (optional): run Demucs with `--two-stems=vocals` on the reference and save `no_vocals.wav` as `reference/<name>_no_vocals.wav`.
