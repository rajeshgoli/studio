"""Shared paths and helpers for the lyric-shorts pipeline."""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Songs (words, timings, takes) and everything built from them live in a separate content checkout, not in this repo.
CONTENT = Path(os.environ.get("STUDIO_CONTENT", ROOT.parent.parent / "studio-content")).expanduser().resolve()
SR = 44100
FPS = 30

VOWEL = re.compile(r"ai|au|[aāiīuūṛṝḷeo]")


def poem_dir(pid):
    return CONTENT / "songs" / pid


def build_dir(pid):
    d = CONTENT / "build" / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_poem(pid):
    return json.loads((poem_dir(pid) / "poem.json").read_text())


def vocals_path(pid):
    """The singer's take. Falls back to the synthetic test take so the pipeline runs end to end."""
    d = poem_dir(pid)
    for name in ("vocals.wav", "vocals.flac", "vocals.mp3", "vocals.m4a"):
        if (d / name).exists():
            return d / name
    # any other recording dropped in the folder (QuickTime saves "Untitled.m4a"): newest wins
    takes = sorted((f for f in d.iterdir() if f.suffix.lower() in (".wav", ".m4a", ".mp3", ".flac", ".aif", ".aiff")
                    and f.name != "test_vocals.wav"), key=lambda f: f.stat().st_mtime)
    if takes:
        return takes[-1]
    t = d / "test_vocals.wav"
    if t.exists():
        print(f"[warn] no vocals.* in {d}; using the synthetic test take", file=sys.stderr)
        return t
    sys.exit(f"put the vocal take at {d}/vocals.wav")


def load_vocals(pid, sr):
    """The take as mono at `sr`, silenced outside poem.json "vocal_trim" {"start": s, "end": s} (chatter, count-ins)."""
    import librosa
    src = vocals_path(pid)
    shift = load_poem(pid)["music"].get("vocal_shift_cents")
    if shift:  # retune the whole take with Rubber Band (R3, formants kept), cached per take and amount
        dst = build_dir(pid) / f"vocals_shift{shift:+d}c_{src.stat().st_size}.wav"
        if not dst.exists():
            import subprocess
            import soundfile as sf
            y0, sr0 = librosa.load(src, sr=None, mono=True)
            tmp = build_dir(pid) / "vocals_unshifted.wav"
            sf.write(tmp, y0, sr0)
            subprocess.run(["rubberband", "--fine", "--formant", "-p", f"{shift / 100:.3f}", str(tmp), str(dst)],
                           check=True, capture_output=True)
        src = dst
    y, _ = librosa.load(src, sr=sr, mono=True)
    trim = load_poem(pid).get("vocal_trim") or {}
    a = int(trim.get("start", 0) * sr)
    b = int(trim["end"] * sr) if trim.get("end") else len(y)
    y[:a] = 0
    y[b:] = 0
    return y


def syllables(translit):
    return max(1, len(VOWEL.findall(translit.lower())))


def load_analysis(pid):
    return json.loads((build_dir(pid) / "analysis.json").read_text())


def load_timing(pid):
    return json.loads((poem_dir(pid) / "timing.json").read_text())


HOOK_LEAD = 0.8  # seconds of drone before the spoken hook


def hook_shift(poem, analysis):
    """Seconds added to vocal time for the spoken hook, or None when the take has none."""
    sp = analysis.get("spoken")
    return HOOK_LEAD - sp["start"] if sp else None


def video_shift(poem, analysis):
    """Seconds added to vocal time to get video time for the singing. The intro (title card, flute prelude) plays
    before the first sung phrase, after the spoken hook if there is one."""
    first = analysis["phrases"][0]["start"]
    intro = poem["music"].get("intro_s", 5.0)
    sp = analysis.get("spoken")
    if sp:
        return sp["end"] + hook_shift(poem, analysis) + intro - first
    return intro - first


def segments(poem, analysis):
    """(vocal_from, vocal_to, shift) pieces of the take that make it into the video, in order."""
    out = []
    sp = analysis.get("spoken")
    first = analysis["phrases"][0]["start"]
    if sp:
        out.append((max(0.0, sp["start"] - 0.3), sp["end"] + 0.35, hook_shift(poem, analysis)))
    out.append((max(0.0, first - 0.35), analysis["duration"], video_shift(poem, analysis)))
    return out


def hook_video(poem, analysis):
    """Spoken hook as (start, end) in video time, or None."""
    sp = analysis.get("spoken")
    if not sp:
        return None
    k = hook_shift(poem, analysis)
    return sp["start"] + k, sp["end"] + k


def video_duration(poem, analysis):
    last = analysis["phrases"][-1]["end"]
    return last + video_shift(poem, analysis) + poem["music"].get("outro_s", 5.0)
