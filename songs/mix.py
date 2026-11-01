"""Lay the vocals over the score: light vocal polish, gentle ducking, loudness to -14 LUFS.

Writes build/<poem>/mix.wav, then refreshes the studio timeline (prepare.py) so Remotion picks it up.
usage: .venv/bin/python mix.py <song> [--score-db 0] [--vocal-reverb 0.16]
"""
import argparse
import subprocess

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from scipy.signal import fftconvolve

import prepare
from common import SR, build_dir, load_analysis, load_poem, load_vocals, segments, video_duration
from score import db, highpass, reverb_ir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("poem")
    ap.add_argument("--score-db", type=float, default=0.0, help="raise/lower the whole score")
    ap.add_argument("--vocal-reverb", type=float, default=0.16)
    a = ap.parse_args()
    poem, an = load_poem(a.poem), load_analysis(a.poem)
    out = build_dir(a.poem)
    dur = video_duration(poem, an)
    N = int(dur * SR)

    y = load_vocals(a.poem, SR)
    y = highpass(y, 75)
    # gentle leveling: tame peaks, keep the dynamics of the singing
    env = np.sqrt(gaussian_filter1d(y ** 2, SR * 0.05)) + 1e-6
    ref = np.percentile(env[env > env.max() * 0.05], 90)
    y = y * np.minimum(1.0, (ref / env) ** 0.35)
    voc = np.zeros(N)
    segs = segments(poem, an)
    sung_rms = None
    for si in reversed(range(len(segs))):  # singing first, so the hook can be matched to it
        va, vb, k = segs[si]
        a0, b0 = int(va * SR), min(int(vb * SR), len(y))
        piece = y[a0:b0].copy()
        r = np.sqrt(np.mean(piece[np.abs(piece) > 0.02 * np.abs(y).max()] ** 2) + 1e-12)
        if sung_rms is None:
            sung_rms = r
        else:  # spoken hook: bring it level with the singing, a touch under
            piece *= min(4.0, sung_rms / r * db(-1.5))
        fade = int(0.03 * SR)
        piece[:fade] *= np.linspace(0, 1, fade)
        piece[-fade:] *= np.linspace(1, 0, fade)
        dst = int(round((va + k) * SR))
        n = min(len(piece), N - dst)
        voc[dst:dst + n] += piece[:n]
    voc *= db(-3) / (np.abs(voc).max() + 1e-9)
    ir = reverb_ir(2.2, seed=5)
    voc2 = np.stack([voc + a.vocal_reverb * fftconvolve(voc, ir[c])[:N] for c in range(2)])

    if poem["music"].get("score") == "none":
        mix = voc2
        mix /= np.abs(mix).max() + 1e-9
        return finish(a.poem, out, mix, dur)
    score, _ = sf.read(out / "score.wav", always_2d=True)
    score = score.T[:, :N]
    if score.shape[1] < N:
        score = np.pad(score, ((0, 0), (0, N - score.shape[1])))
    # duck the score ~3 dB under the voice
    venv = gaussian_filter1d(np.abs(voc), SR * 0.15)
    duck = 1 - 0.3 * np.clip(venv / (np.percentile(venv, 95) + 1e-9), 0, 1)
    mix = voc2 + score * db(-7 + poem["music"].get("score_db", 0.0) + a.score_db) * duck
    mix /= np.abs(mix).max() + 1e-9
    finish(a.poem, out, mix, dur)


def finish(pid, out, mix, dur):
    raw = out / "mix_raw.wav"
    sf.write(raw, (mix * db(-1)).T.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                    "-ar", str(SR), str(out / "mix.wav")], check=True)
    print(f"{out / 'mix.wav'}  {dur:.1f}s")
    prepare.main(pid)


if __name__ == "__main__":
    main()
