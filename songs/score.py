"""Synthesize a light background score that follows the singer: everything is generated, nothing to license.

  tanpura     Sa-Pa drone tuned to the singer's own Sa (Ma or Ni string if the raga drops Pa), with the jawari buzz sweep
  follow      a flute (or violin) that answers each line in the gap after it by replaying its closing phrase, the way
              a Carnatic violinist does; the intro is the first line's melody. It never plays under the voice.
  swarmandal  a harp-like glissando through the raga's notes at every scene change
  bells       a small temple bell at the start and after the last line
  percussion  optional soft mridangam theka (set music.percussion = {"bpm": 76, "offset": 5.2, "pattern": "adi"})

Everything is in video time (vocals start after the intro). Writes build/<poem>/score.wav and build/<poem>/stems/*.wav.
usage: .venv/bin/python score.py <song> [--follow flute|violin|none]
"""
import argparse
import json

import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter, gaussian_filter1d
from scipy.signal import butter, fftconvolve, sosfilt

from common import SR, build_dir, hook_video, load_analysis, load_poem, load_timing, video_duration, video_shift

RNG = np.random.default_rng(1)


def db(x):
    return 10 ** (x / 20)


def lowpass(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)


def highpass(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)


def place(bus, sig, t0, gain=1.0, pan=0.0):
    """Mix a mono signal into a stereo bus at time t0 (s) with constant-power pan (-1..1)."""
    i = int(round(t0 * SR))
    if i >= bus.shape[1]:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    n = min(len(sig), bus.shape[1] - i)
    th = (pan + 1) * np.pi / 4
    bus[0, i:i + n] += sig[:n] * gain * np.cos(th)
    bus[1, i:i + n] += sig[:n] * gain * np.sin(th)


# ---------------------------------------------------------------- instruments

def tanpura_pluck(f, dur=5.5, sweep=1.3, seed=0):
    """One tanpura string: warm harmonics with a soft resonance (the jawari shimmer) drifting down through the low
    partials. Kept dark on purpose: most of the energy sits under 2 kHz, like the real instrument heard from a seat
    away, not a buzzy close-mic'd string."""
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    kc = 3.5 + 9 * np.exp(-t / sweep)  # the travelling shimmer, in harmonic numbers
    det = 2 ** (r.uniform(-2, 2) / 1200)
    for k in range(1, 40):
        fk = k * f * det
        if fk > 6000:
            break
        width = 1.8 + 0.1 * k
        jaw = 1 + 1.2 * np.exp(-((k - kc) / width) ** 2)
        env = np.exp(-t / (4.5 / (1 + 0.09 * k))) * jaw / k ** 1.3
        out += env * np.sin(2 * np.pi * fk * t + r.uniform(0, 2 * np.pi))
    att = int(0.012 * SR)
    out[:att] *= np.linspace(0, 1, att) ** 2
    out[-int(0.4 * SR):] *= np.linspace(1, 0, int(0.4 * SR))
    out = lowpass(out, 3200)
    return out / np.abs(out).max()


def pluck(f, dur=3.0, bright=1.0):
    """Harp / swarmandal string."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k in range(1, 14):
        if k * f > 12000:
            break
        out += np.exp(-t * (1.2 + 0.9 * k / bright)) / k ** 1.1 * np.sin(2 * np.pi * k * f * t * (1 + 0.0004 * k * k))
    out[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return out / np.abs(out).max()


def bell(f, dur=6.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, tau in [(0.5, 0.35, 3.5), (1.0, 1.0, 2.8), (1.19, 0.45, 2.0), (1.56, 0.4, 1.7), (2.0, 0.5, 1.4),
                            (2.74, 0.3, 1.0), (3.76, 0.18, 0.7), (5.4, 0.1, 0.4)]:
        beat = 1 + 0.08 * np.sin(2 * np.pi * 1.7 * ratio * t)
        out += amp * beat * np.exp(-t / tau) * np.sin(2 * np.pi * f * ratio * t)
    out[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return out / np.abs(out).max()


def flute(f, amp):
    """Bansuri-like tone from a pitch track (Hz per sample) and an amplitude envelope."""
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.30 * np.sin(2 * ph + 0.4) + 0.10 * np.sin(3 * ph + 1.1) + 0.035 * np.sin(4 * ph)
    breath = highpass(RNG.standard_normal(len(f)), 1200) * (0.6 + 0.4 * np.sin(ph))
    # chiff where a note begins after silence
    on = np.clip(np.diff(np.r_[0, amp]) * SR / 30, 0, 1)
    chiff = gaussian_filter1d(on, SR * 0.01) * highpass(RNG.standard_normal(len(f)), 2500)
    out = amp * (tone + 0.07 * breath) + 0.25 * chiff * amp.max()
    return lowpass(out, 7000)


def violin(f, amp):
    """Bowed string: sawtooth-like partials shaped by a fixed body resonance."""
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = [(280, 90, 1.0), (460, 120, 0.8), (1100, 300, 0.5), (2800, 600, 0.9), (4200, 900, 0.4)]
    out = np.zeros(len(f))
    for k in range(1, 26):
        fk = k * f
        g = sum(a / (1 + ((fk - c) / w) ** 2) for c, w, a in body) + 0.08
        out += np.where(fk < 11000, g / k, 0) * np.sin(k * ph)
    bow = lowpass(highpass(RNG.standard_normal(len(f)), 2000), 6000) * 0.02
    return amp * (out / 3 + bow)


def mridangam(kind, f_sa):
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    if kind == "thom":  # bass, pitch drops
        out = np.sin(2 * np.pi * np.cumsum(f_sa / 2 * (1 + 0.6 * np.exp(-t / 0.03))) / SR) * np.exp(-t / 0.18)
    elif kind == "dhi":  # ringing right-head stroke at Sa
        out = sum(a * np.sin(2 * np.pi * f_sa * r * t) * np.exp(-t / tau) for r, a, tau in
                  [(1, 1, 0.35), (2, 0.6, 0.25), (3, 0.35, 0.18), (4, 0.2, 0.12)])
    elif kind == "nam":
        out = sum(a * np.sin(2 * np.pi * f_sa * r * t) * np.exp(-t / tau) for r, a, tau in
                  [(1, 0.5, 0.25), (2, 1, 0.3), (3, 0.5, 0.2), (5, 0.25, 0.1)])
    else:  # "ta": short damped slap
        out = highpass(RNG.standard_normal(n), 800) * np.exp(-t / 0.02) + 0.5 * np.sin(2 * np.pi * f_sa * 2 * t) * np.exp(-t / 0.04)
    out[: int(0.001 * SR)] *= np.linspace(0, 1, int(0.001 * SR))
    return out / np.abs(out).max()


PATTERNS = {  # one strokes-per-beat-subdivision cycle (4 per beat), "." = rest
    "adi": "thom . ta . dhi . nam . thom . ta . dhi . ta . nam . thom . dhi . ta . thom ta dhi . nam . ta . dhi . thom . nam .",
    "chapu": "thom . dhi . nam . thom . ta . dhi . nam .",
}


def reverb_ir(rt=2.6, seed=3):
    r = np.random.default_rng(seed)
    n = int(rt * SR)
    t = np.arange(n) / SR
    ir = np.zeros((2, n))
    for c in range(2):
        hi = r.standard_normal(n) * np.exp(-t / (rt / 9))
        lo = lowpass(r.standard_normal(n), 1800) * np.exp(-t / (rt / 6))
        ir[c] = hi * 0.5 + lo
        ir[c, : int(0.025 * SR)] = 0  # pre-delay
    return ir / np.sqrt((ir ** 2).sum(1, keepdims=True))


def reverb(bus, send):
    ir = reverb_ir()
    wet = np.stack([fftconvolve(bus[c], ir[c])[: bus.shape[1]] for c in range(2)])
    return bus + send * wet


# ---------------------------------------------------------------- pitch track in video time

def clean_track(f0, rms, tonic):
    """Fill consonant gaps, remove octave slips, and give each frame a playing amplitude."""
    voiced = f0 > 0
    semi = np.where(voiced, 12 * np.log2(np.where(voiced, f0, 1) / tonic), np.nan)
    idx = np.flatnonzero(voiced)
    if len(idx) == 0:
        return np.zeros_like(f0), np.zeros_like(f0)
    filled = semi.copy()
    gaps = np.flatnonzero(np.diff(idx) > 1)
    for g in gaps:
        a, b = idx[g], idx[g + 1]
        if b - a <= 9:  # under ~100 ms: a consonant, glide through it
            filled[a:b + 1] = np.linspace(semi[a], semi[b], b - a + 1)
    ok = np.isfinite(filled)
    med = median_filter(np.where(ok, filled, 0), 9)
    slip = ok & (np.abs(filled - med) > 7)
    filled[slip] = med[slip]
    filled[ok] = gaussian_filter1d(filled[ok], 1.2)
    amp = ok.astype(float)
    level = np.clip(rms / (np.percentile(rms[voiced], 95) + 1e-9), 0, 1) ** 0.5
    amp = gaussian_filter1d(amp * (0.35 + 0.65 * level), 2.5)
    return np.where(ok, filled, 0.0), amp


def to_audio(track_t, values, t_audio):
    return np.interp(t_audio, track_t, values, left=values[0] if len(values) else 0, right=0)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("poem")
    ap.add_argument("--follow", default=None, help="flute | violin | none (default: poem music.follow)")
    a = ap.parse_args()
    poem, an, timing = load_poem(a.poem), load_analysis(a.poem), load_timing(a.poem)
    music = poem["music"]
    if music.get("score") == "none":
        print("music.score is \"none\": voice only, no score generated")
        return
    follow = a.follow or music.get("follow", "flute")
    out = build_dir(a.poem)
    (out / "stems").mkdir(exist_ok=True)
    shift = video_shift(poem, an)
    dur = video_duration(poem, an)
    N = int(dur * SR) + SR
    tonic = an["tonic_hz"]
    ref = an.get("reference")
    semis = sorted(set(ref["notes"]) | {0}) if ref else sorted({n["semitone"] for n in an["scale"]} | {0})
    cents = {} if ref else {n["semitone"]: n["cents"] for n in an["scale"]}
    hz = lambda s, octv=0: tonic * 2 ** ((cents.get(s % 12, 100 * (s % 12)) / 100 + 12 * (s // 12) + 12 * octv) / 12)
    lines = [{**s, "start": s["start"] + shift, "end": s["end"] + shift} for s in timing["sung"]]
    first, last = lines[0]["start"], lines[-1]["end"]
    hook = hook_video(poem, an)  # spoken hook (video time) or None
    stems = {}

    # tanpura: Pa (or Ma, or Ni) - Sa - Sa - low Sa, about every 0.62 s, with a breath after each round
    drone = music.get("drone", "auto")
    if drone == "auto":
        drone = "P" if 7 in semis else "M" if 5 in semis else "N" if 11 in semis or 10 in semis else "P"
    first_string = {"P": tonic * 0.75 * 2 ** ((cents.get(7, 700) - 700) / 1200), "M": hz(5, -1),
                    "N": hz(11 if 11 in semis else 10, -1)}[drone]
    strings = [(first_string, -0.35), (tonic, 0.1), (tonic * 1.0009, 0.25), (tonic / 2, -0.1)]
    templates = [[tanpura_pluck(f, sweep=s, seed=10 * i + j) for j, s in enumerate((1.1, 1.4, 1.7))]
                 for i, (f, _) in enumerate(strings)]
    tan = np.zeros((2, N))
    t, k = 0.15, 0
    while t < dur:
        i = k % 4
        place(tan, templates[i][RNG.integers(3)], t + RNG.uniform(-0.015, 0.015),
              gain=RNG.uniform(0.85, 1.0) * (0.8 if i == 3 else 1.0), pan=strings[i][1])
        t += 0.62 if i < 3 else 1.24
        k += 1
    t_drone = hook[1] + 0.2 if hook and music.get("drone_after_hook") else 0.0  # leave the spoken hook dry
    fade = (np.clip((np.arange(N) / SR - t_drone) / 1.8, 0, 1)
            * np.clip((dur - np.arange(N) / SR) / 2.5, 0, 1))
    tan *= fade * db(-24) / (np.sqrt(np.mean(tan ** 2)) + 1e-9) * 0.5
    stems["tanpura"] = tan

    # follow instrument
    fz = np.load(out / "f0.npz")
    f0, rms, tt = fz["f0"], fz["rms"], fz["t"]
    semi_track, amp_track = clean_track(f0, rms, tonic)
    t_audio = np.arange(N) / SR
    fol = np.zeros((2, N))
    if follow != "none":
        octave = 12 if (follow == "flute" and an["median_f0"] < 270) or (follow == "violin" and np.nanpercentile(np.where(f0 > 0, f0, np.nan), 5) < 200) else 0
        inst = flute if follow == "flute" else violin
        vt = tt + shift  # video time of each pitch frame

        def render(src_a, src_b, dst, level, stretch=1.0):
            """Play the vocal melody from video time [src_a, src_b) starting at dst."""
            m = (vt >= src_a) & (vt < src_b)
            if m.sum() < 5:
                return
            st, sv, sa = vt[m] - src_a, semi_track[m], amp_track[m]
            n = int((src_b - src_a) * stretch * SR)
            ta = np.arange(n) / SR / stretch
            semi_a = np.interp(ta, st, sv)
            amp_a = np.interp(ta, st, sa)
            # hold pitch through silences so glides don't swoop through zero
            silent = np.interp(ta, st, (sa < 0.05).astype(float)) > 0.5
            if (~silent).any():
                last_v = np.where(~silent, np.arange(n), 0)
                np.maximum.accumulate(last_v, out=last_v)
                last_v[: np.argmax(~silent)] = np.argmax(~silent)
                held = semi_a[last_v]
            else:
                held = semi_a
            env = amp_a * np.clip(np.minimum(ta, ta[-1] - ta) / 0.12, 0, 1)
            sig = inst(tonic * 2 ** ((held + octave) / 12), env)
            place(fol, sig, dst, gain=level, pan=0.2)

        # intro: the first line's opening melody, once the drone has settled
        intro_from = hook[1] + 0.3 if hook else 0.9
        intro_len = min(first - intro_from - 0.5, 4.5, lines[0]["end"] - lines[0]["start"])
        if intro_len > 1.5:
            render(lines[0]["start"], lines[0]["start"] + intro_len, max(intro_from, first - intro_len - 0.5), db(-17))
        for i, l in enumerate(lines):
            # answer in the gap after the line: its closing phrase
            gap_end = lines[i + 1]["start"] if i + 1 < len(lines) else min(dur - 2.5, l["end"] + 4.0)
            room = gap_end - l["end"] - 0.25
            if room >= 0.9:
                ln = min(room, 3.0, l["end"] - l["start"])
                render(l["end"] - ln, l["end"], l["end"] + 0.12, db(-19))
        fol *= 1.0 / (np.abs(fol).max() + 1e-9) * db(-8) if np.abs(fol).max() > 0 else 1
    stems["follow"] = fol

    # swarmandal glissandi at scene changes (and to open)
    sw = np.zeros((2, N))
    gl = semis if ref else an.get("held") if len(an.get("held", [])) >= 4 else semis
    scale_up = [hz(s, o) for o in (0, 1, 2) for s in gl] + [hz(0, 3)]
    motifs = {l["line"]: None for l in lines}
    lines_by_id = {l["id"]: l for l in poem["lines"]}
    starts = [0.35] + ([hook[1] + 0.25] if hook else []) + [l["start"] - 0.9 for i, l in enumerate(lines)
                       if i > 0 and lines_by_id[l["line"]]["motif"] != lines_by_id[lines[i - 1]["line"]]["motif"]]
    for g, t0 in enumerate(starts):
        notes = scale_up[len(gl) // 2:] if g % 2 else scale_up
        for j, f in enumerate(notes):
            place(sw, pluck(f, 3.0, bright=1.5), t0 + j * 0.045 + RNG.uniform(0, 0.008),
                  gain=0.55 + 0.45 * j / len(notes), pan=-0.7 + 1.4 * j / len(notes))
    sw *= db(-15) / (np.abs(sw).max() + 1e-9)
    stems["swarmandal"] = sw
    del motifs

    # bells
    bl = np.zeros((2, N))
    place(bl, bell(hz(0, 2)), 0.1, 1.0, -0.2)
    place(bl, bell(hz(0, 2)), last + 1.4, 0.8, 0.2)
    place(bl, bell(hz(7, 1)), last + 1.9, 0.45, -0.3)
    bl *= db(-20) / (np.abs(bl).max() + 1e-9)
    stems["bells"] = bl

    # optional percussion
    perc = np.zeros((2, N))
    pc = music.get("percussion")
    if pc:
        beat = 60.0 / pc["bpm"]
        strokes = PATTERNS[pc.get("pattern", "adi")].split()
        kit = {k: mridangam(k, tonic) for k in ("thom", "dhi", "nam", "ta")}
        t0 = pc.get("offset", timing["sung"][0]["start"]) + shift
        while t0 - beat * len(strokes) / 4 > first - 0.5:
            t0 -= beat * len(strokes) / 4
        step, j = beat / 4, 0
        tcur = t0
        while tcur < last:
            s = strokes[j % len(strokes)]
            if s != "." and tcur >= first - 0.3:
                place(perc, kit[s], tcur, RNG.uniform(0.75, 1.0), 0.05)
            tcur += step
            j += 1
        env = np.clip((t_audio - first + 0.3) / 2.0, 0, 1) * np.clip((last + 0.6 - t_audio) / 1.0, 0, 1)
        perc *= env * db(-14) / (np.abs(perc).max() + 1e-9)
    stems["percussion"] = perc

    sends = {"tanpura": 0.22, "follow": 0.45, "swarmandal": 0.6, "bells": 0.5, "percussion": 0.15}
    levels = music.get("levels", {})  # per-stem trims in dB, e.g. {"follow": -3, "tanpura": 2}
    keep = music.get("stems")  # e.g. ["tanpura"] for a drone-only score; default is everything
    wets = {}
    for name, s in stems.items():
        if keep and name not in keep:
            s = s * 0
        wets[name] = reverb(s, sends[name])
        sf.write(out / "stems" / f"{name}.wav", wets[name].T.astype(np.float32), SR)
    # Normalise on the untrimmed sum, then apply the trims, so a trim really changes the level (normalising after
    # them undid a -12 dB tanpura completely when it was the only stem left).
    norm = db(-3) / max(1e-9, np.abs(sum(wets.values())).max())
    mix = sum(w * db(levels.get(name, 0.0)) for name, w in wets.items()) * norm
    mix = mix[:, : int(dur * SR)]
    sf.write(out / "score.wav", mix.T.astype(np.float32), SR)
    print(f"{out / 'score.wav'}  {dur:.1f}s  Sa {tonic} Hz, drone {drone}, follow {follow}, "
          f"notes {[n['swara'] for n in an['scale']]}, percussion {'on' if pc else 'off'}")


if __name__ == "__main__":
    main()
