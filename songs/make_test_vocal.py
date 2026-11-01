"""Synthesize a stand-in vocal take (formant-synth 'aa-ee-oo' singing) so the pipeline can run before a real take exists.

It sings each line of the poem as one breath phrase in a raga-like scale, with glides, gamakas and held endings.
Not meant to sound good; it gives analyze.py realistic pitch, phrasing and gaps to chew on.

usage: .venv/bin/python make_test_vocal.py <song> [--tonic 146.8]
"""
import argparse

import numpy as np
import soundfile as sf
from scipy.signal import lfilter

from common import SR, load_poem, poem_dir, syllables, VOWEL

# Kharaharapriya-ish: S R2 G2 M1 P D2 N2
SCALE = [0, 2, 3, 5, 7, 9, 10]
FORMANTS = {  # F1..F3 (Hz), bandwidths
    "a": (750, 1150, 2600), "ā": (750, 1150, 2600), "i": (300, 2200, 2950), "ī": (300, 2200, 2950),
    "u": (330, 800, 2300), "ū": (330, 800, 2300), "e": (450, 1900, 2600), "o": (480, 850, 2500),
    "ai": (600, 1700, 2600), "au": (600, 950, 2450), "ṛ": (450, 1350, 1700),
}
BW = (90, 110, 160)


def phrase_notes(rng, n):
    """Arch-shaped walk over scale degrees (in semitones from Sa), ending on a resting note."""
    deg = rng.choice([0, 2, 4])
    notes = []
    for i in range(n):
        up = i < n * 0.6
        deg += rng.choice([1, 1, 0, -1] if up else [-1, -1, 0, 1])
        deg = int(np.clip(deg, -2, 9))
        notes.append(deg)
    notes[-1] = rng.choice([0, 0, 0, 4, 7])
    return [12 * (d // 7) + SCALE[d % 7] for d in notes]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("poem")
    ap.add_argument("--tonic", type=float, default=146.8)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    poem = load_poem(a.poem)
    rng = np.random.default_rng(a.seed)
    lines = {l["id"]: l for l in poem["lines"]}

    f0_t, vow_t, amp_t = [], [], []
    def silence(sec):
        n = int(sec * SR)
        f0_t.append(np.full(n, a.tonic)); vow_t.extend(["a"] * n); amp_t.append(np.zeros(n))
    silence(1.2)
    for lid in poem["sung"]:
        text = lines[lid]["translit"].lower()
        vowels = VOWEL.findall(text)
        n = len(vowels)
        notes = phrase_notes(rng, n)
        durs = rng.uniform(0.26, 0.42, n)
        durs[-1] = rng.uniform(1.1, 1.6)
        for k in rng.choice(n - 1, size=max(1, n // 6), replace=False):
            durs[k] += rng.uniform(0.4, 0.8)  # a few stretched syllables
        semis = np.concatenate([np.full(int(d * SR), s, float) for d, s in zip(durs, notes)])
        # portamento: one-pole glide toward each target
        alpha = 1 - np.exp(-1 / (0.05 * SR))
        semis = lfilter([alpha], [1, alpha - 1], semis, zi=[semis[0] * (1 - alpha)])[0]
        t = np.arange(len(semis)) / SR
        # gamaka on stretched notes: oscillate up to the next note; vibrato on the tail
        pos = 0
        for d, s in zip(durs, notes):
            m = int(d * SR)
            if d > 0.6:
                seg = np.arange(m) / SR
                semis[pos:pos + m] += 0.9 * (0.5 - 0.5 * np.cos(2 * np.pi * 4.5 * seg)) * np.clip(seg / 0.2, 0, 1)
            pos += m
        semis += 0.15 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - t[-1] + 1.0), 0, 1)
        f0_t.append(a.tonic * 2 ** (semis / 12))
        for d, v in zip(durs, vowels):
            vow_t.extend([v] * int(d * SR))
        env = np.ones(len(semis))
        pos = 0
        for d in durs:  # consonant dips between syllables
            m = int(d * SR)
            k = min(int(0.045 * SR), m // 3)
            env[pos:pos + k] *= np.linspace(0.15, 1, k)
            pos += m
        att, rel = int(0.08 * SR), int(0.35 * SR)
        env[:att] *= np.linspace(0, 1, att); env[-rel:] *= np.linspace(1, 0, rel)
        amp_t.append(env)
        silence(rng.uniform(0.7, 1.4))
    silence(0.8)

    f0 = np.concatenate(f0_t); amp = np.concatenate(amp_t)
    vow = np.array(vow_t[: len(f0)])
    # vowel formant tracks, smoothed so the vowel changes glide
    F = np.array([FORMANTS.get(v, FORMANTS["a"]) for v in vow], float)
    sm = int(0.03 * SR)
    ker = np.ones(sm) / sm
    F = np.stack([np.convolve(F[:, i], ker, mode="same") for i in range(3)], 1)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    out = np.zeros(len(f0))
    for k in range(1, 50):
        fk = k * f0
        live = fk < 7000
        if not live.any():
            break
        gain = np.zeros(len(f0))
        for i in range(3):
            gain += (1.0, 0.6, 0.25)[i] / (1 + ((fk - F[:, i]) / BW[i]) ** 2)
        out += np.where(live, gain * k ** -0.6 * np.sin(k * phase), 0)
    out += 0.004 * rng.standard_normal(len(out))  # breath
    out *= amp
    out = 0.3 * out / np.abs(out).max()
    out += 0.0008 * rng.standard_normal(len(out))  # room noise
    dst = poem_dir(a.poem) / "test_vocals.wav"
    sf.write(dst, out.astype(np.float32), SR)
    print(f"{dst}  {len(out) / SR:.1f}s  tonic {a.tonic} Hz")


if __name__ == "__main__":
    main()
