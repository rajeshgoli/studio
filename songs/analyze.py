"""Read the vocal take: pitch track, tonic (Sa), the swaras actually sung, breath phrases, and line timing.

Writes build/<poem>/analysis.json, build/<poem>/f0.npz, build/<poem>/frames.json (per-video-frame voice energy and
pitch for the animation), and $STUDIO_CONTENT/songs/<song>/timing.json (when one sung line starts and ends). timing.json is yours
to correct: it is only written when missing, or with --retime.

usage: .venv/bin/python analyze.py <song> [--retime]
"""
import argparse
import json

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d

from common import (FPS, build_dir, load_vocals, load_poem, poem_dir, segments, syllables, video_duration,
                    vocals_path)

AR = 22050
HOP = 256  # ~11.6 ms
SWARA = ["S", "R1", "R2/G1", "R3/G2", "G3", "M1", "M2", "P", "D1", "D2/N1", "D3/N2", "N3"]
# Arohana/avarohana union as 12-semitone sets. The name is a friendly guess, the score uses the detected notes.
RAGAS = {
    "Mukhari": {0, 2, 3, 5, 7, 8, 9, 10}, "Kharaharapriya": {0, 2, 3, 5, 7, 9, 10},
    "Shankarabharanam": {0, 2, 4, 5, 7, 9, 11}, "Kalyani": {0, 2, 4, 6, 7, 9, 11},
    "Mayamalavagowla": {0, 1, 4, 5, 7, 8, 11}, "Todi": {0, 1, 3, 5, 7, 8, 10},
    "Bhairavi": {0, 2, 3, 5, 7, 8, 9, 10}, "Kambhoji": {0, 2, 4, 5, 7, 9, 10, 11},
    "Harikambhoji": {0, 2, 4, 5, 7, 9, 10}, "Natabhairavi": {0, 2, 3, 5, 7, 8, 10},
    "Mohanam": {0, 2, 4, 7, 9}, "Hindolam": {0, 3, 5, 8, 10}, "Madhyamavati": {0, 2, 5, 7, 10},
    "Hamsadhwani": {0, 2, 4, 7, 11}, "Shivaranjani": {0, 2, 3, 7, 9}, "Abhogi": {0, 2, 3, 5, 9},
    "Sindhubhairavi": {0, 1, 2, 3, 4, 5, 7, 8, 10}, "Kapi": {0, 2, 3, 4, 5, 7, 9, 10, 11},
    "Ananda Bhairavi": {0, 2, 3, 5, 7, 9, 10, 8}, "Yamunakalyani": {0, 2, 4, 5, 6, 7, 9, 11},
    "Behag": {0, 4, 5, 6, 7, 9, 11, 2}, "Desh": {0, 2, 4, 5, 7, 9, 10, 11},
    "Charukesi": {0, 2, 4, 5, 7, 8, 10}, "Kiravani": {0, 2, 3, 5, 7, 8, 11},
    "Saveri": {0, 1, 5, 7, 8, 4, 11}, "Revati": {0, 1, 5, 7, 10}, "Vasantha": {0, 1, 4, 5, 9, 11},
}


def pitch_track(y):
    f0, voiced, prob = librosa.pyin(y, fmin=65, fmax=1100, sr=AR, frame_length=2048, hop_length=HOP)
    f0 = np.where(voiced & (prob > 0.3), f0, np.nan)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP)[0][: len(f0)]
    return f0, rms


def steady_mask(cents, min_len=12, tol=35):
    """Frames sitting on a note (within tol cents of a 140 ms running median): what the singer dwells on."""
    ok = np.isfinite(cents)
    med = np.full_like(cents, np.nan)
    c = np.where(ok, cents, 0)
    for i in range(len(c)):
        a, b = max(0, i - min_len // 2), i + min_len // 2 + 1
        w = cents[a:b]
        w = w[np.isfinite(w)]
        if len(w) >= min_len * 0.8:
            med[i] = np.median(w)
    return ok & np.isfinite(med) & (np.abs(c - np.nan_to_num(med)) < tol)


def find_tonic(f0, steady, weight, finals):
    cents = 1200 * np.log2(f0[steady] / 55.0)
    hist = np.bincount(np.mod(np.round(cents), 1200).astype(int), weights=weight[steady], minlength=1200)
    hist = gaussian_filter1d(hist, 12, mode="wrap")
    hist /= hist.max()
    H = lambda c: hist[int(round(c)) % 1200]
    peaks = [i for i in range(1200) if hist[i] >= hist[i - 1] and hist[i] >= hist[(i + 1) % 1200] and hist[i] > 0.15]
    # Sa is the most-held note, Pa a fifth above it is held too, and phrases come to rest on Sa.
    fin = np.mod(np.array(finals, float), 1200)
    F = lambda c: float(np.mean(np.abs((fin - c + 600) % 1200 - 600) < 50)) if len(fin) else 0.0
    scored = sorted(((H(c) + 0.5 * H(c + 702) + 1.2 * F(c), c) for c in peaks), reverse=True)
    sa_class = scored[0][1]
    # Octave: middle Sa sits near the low end of most singers' phrases (about the 25th percentile).
    lo = np.nanpercentile(f0, 25)
    cand = [55.0 * 2 ** ((sa_class + 1200 * o) / 1200) for o in range(-1, 5)]
    tonic = min(cand, key=lambda h: abs(np.log2(h / lo)))
    # Refine to the singer's own Sa: median of the held frames within 40 cents of it, in any octave.
    rel = np.mod(1200 * np.log2(f0[steady] / tonic) + 600, 1200) - 600
    near = np.abs(rel) < 40
    if near.sum() > 20:
        tonic *= 2 ** (np.median(rel[near]) / 1200)
    return tonic, hist, [(round(float(s), 3), round(55 * 2 ** (c / 1200), 2)) for s, c in scored[:4]]


def find_scale(f0, steady, tonic):
    rel = 1200 * np.log2(f0[steady] / tonic)
    fold = np.mod(rel + 50, 1200) - 50  # -50..1150
    deg = np.round(fold / 100).astype(int) % 12
    dev = fold - 100 * np.round(fold / 100)
    share = np.bincount(deg[np.abs(dev) < 45], minlength=12) / max(1, len(deg))
    notes = []
    for d in range(12):
        if share[d] >= 0.025 or d == 0:
            m = (deg == d) & (np.abs(dev) < 45)
            notes.append({"semitone": d, "swara": SWARA[d], "share": round(float(share[d]), 3),
                          "cents": round(float(100 * d + (np.median(dev[m]) if m.any() else 0)), 1)})
    # A faint note right next to a strong one is usually the glide into it, not a swara of the raga.
    keep = lambda d: d == 0 or not any(share[(d + o) % 12] >= 2.2 * share[d] and share[d] < 0.07 for o in (-1, 1))
    notes = [n for n in notes if keep(n["semitone"])]
    present = {n["semitone"] for n in notes}
    def score(name):
        s = RAGAS[name]
        return len(present & s) - 1.3 * len(present - s) - 0.6 * len(s - present)
    best = sorted(RAGAS, key=score, reverse=True)[:3]
    return notes, best, share


def held_swaras(f0, steady, tonic, hop_s):
    """Semitones the singer actually rests on (holds of 0.4 s+): a cleaner note set than the histogram, which also
    counts every gamaka and glide. Used for the swarmandal so its glissandi stay consonant."""
    c = 1200 * np.log2(f0 / tonic)
    count = np.zeros(12)
    i = 0
    while i < len(c):
        if steady[i]:
            j = i
            while j < len(c) and steady[j] and abs(c[j] - c[i]) < 60:
                j += 1
            d = (j - i) * hop_s
            if d >= 0.4:
                count[int(round(np.median(c[i:j]) / 100)) % 12] += 1 + (d >= 0.8)
            i = j
        else:
            i += 1
    keep = {k for k in range(12) if count[k] >= 2}
    # two neighbouring semitones both "held" is one wobbly note, keep the stronger
    keep = {k for k in keep if not any((k + o) % 12 in keep and count[(k + o) % 12] > count[k] for o in (-1, 1))}
    return sorted({0} | keep)


def pitch_profile(f0):
    """Pitch-class profile of held notes, 1-cent bins (relative to A1)."""
    c = 1200 * np.log2(f0 / 55.0)
    st = steady_mask(c)
    h = np.bincount(np.mod(np.round(c[st]), 1200).astype(int), minlength=1200).astype(float)
    return gaussian_filter1d(h, 20, mode="wrap") / max(1.0, h.sum()), st


def reference_tonic(ref_path, f0_take):
    """Sa from a reference recording of the song (the original), carried over to the take by matching the two
    pitch profiles. A professional recording with accompaniment pins Sa far better than one unaccompanied take."""
    y, _ = librosa.load(ref_path, sr=AR, mono=True)
    f0r, rmsr = pitch_track(y)
    tr = np.arange(len(f0r)) * HOP / AR
    pr, st = pitch_profile(f0r)
    ph = find_phrases(f0r, rmsr, tr)
    w = np.ones(len(f0r))
    finals = []
    cr = 1200 * np.log2(f0r / 55.0)
    for p in ph:
        w[(tr > p["end"] - 1.2) & (tr <= p["end"])] = 3.0
        m = st & (tr > p["end"] - 1.0) & (tr <= p["end"])
        if m.sum() > 5:
            finals.append(float(np.median(cr[m])))
    ref_sa, _, _ = find_tonic(f0r, st, w, finals)
    ref_notes, _, _ = find_scale(f0r, st, ref_sa)
    pu, _ = pitch_profile(f0_take)
    # cents to move the take onto the reference. Takes are sung with the reference (or its tanpura) as the guide, so
    # they share its key: only look within a semitone and a half, where a wider search lands on look-alike scales.
    shift = max(range(-150, 151, 5), key=lambda k: float(np.dot(np.roll(pu, k), pr)))
    take_sa = ref_sa * 2 ** (-shift / 1200)
    return take_sa, ref_sa, shift, sorted(n["semitone"] for n in ref_notes)


def find_phrases(f0, rms, t, gap=0.35, min_len=0.3):
    """Breath phrases: stretches of singing split by gaps of at least `gap` seconds."""
    live = rms[rms > 1e-6]  # ignore trimmed-out silence when judging the noise floor
    thr = max(np.percentile(live, 20) * 2.5, rms.max() * 0.04)
    active = (rms > thr) | np.isfinite(f0)
    active = gaussian_filter1d(active.astype(float), 3) > 0.4
    edges = np.flatnonzero(np.diff(np.r_[0, active.astype(int), 0]))
    segs = [[t[a], t[min(b, len(t) - 1)]] for a, b in zip(edges[::2], edges[1::2])]
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [{"start": round(a, 3), "end": round(b, 3)} for a, b in merged if b - a >= min_len]


def voiced_time(f0, t, a, b):
    m = (t >= a) & (t < b)
    return float(np.isfinite(f0[m]).sum() * HOP / AR)


def align(phrases, sung, lines, f0, t):
    """Give each sung line a contiguous run of phrases. DP over cut points, matching each line's share of the singing
    (by syllable count) to the share of voiced time it gets. One breath per line wins ties."""
    P, L = len(phrases), len(sung)
    w = np.array([syllables(lines[l]["translit"]) for l in sung], float)
    w /= w.sum()
    v = np.array([voiced_time(f0, t, p["start"], p["end"]) for p in phrases])
    if P < L:  # fewer breaths than lines: split long phrases evenly by syllables
        out, total = [], v.sum()
        cum = np.r_[0, np.cumsum(w)] * (phrases[-1]["end"] - phrases[0]["start"]) + phrases[0]["start"]
        return [{"line": l, "start": round(cum[i], 3), "end": round(cum[i + 1], 3)} for i, l in enumerate(sung)]
    vc = np.r_[0, np.cumsum(v)] / v.sum()
    INF = 1e18
    cost = np.full((L + 1, P + 1), INF)
    back = np.zeros((L + 1, P + 1), int)
    cost[0, 0] = 0
    for i in range(1, L + 1):
        for j in range(i, P - (L - i) + 1):
            for k in range(i - 1, j):
                if cost[i - 1, k] >= INF:
                    continue
                share = vc[j] - vc[k]
                c = cost[i - 1, k] + np.log((share + 1e-3) / (w[i - 1] + 1e-3)) ** 2 + 0.05 * (j - k - 1)
                if c < cost[i, j]:
                    cost[i, j], back[i, j] = c, k
    cuts, j = [], P
    for i in range(L, 0, -1):
        k = back[i, j]
        cuts.append((k, j))
        j = k
    cuts.reverse()
    return [{"line": l, "start": phrases[k]["start"], "end": phrases[j - 1]["end"]} for l, (k, j) in zip(sung, cuts)]


def from_marks(marks, phrases, sung, f0, t):
    """Line timing from the singer's own scroll marks, each snapped to the nearest breath-phrase start close by
    (taps land a little early or late), ending at the last sung (pitched) moment before the next line."""
    starts = []
    for m in marks["line_starts"]:
        near = [p["start"] for p in phrases if m - 1.5 <= p["start"] <= m + 0.8]
        starts.append(min(near, key=lambda s: abs(s - m)) if near else m)
    out = []
    for i, l in enumerate(sung):
        nxt = starts[i + 1] if i + 1 < len(starts) else (marks.get("end") or phrases[-1]["end"]) + 0.5
        sung_t = t[np.isfinite(f0) & (t > starts[i]) & (t < nxt - 0.1)]
        end = float(sung_t[-1]) + 0.1 if len(sung_t) else nxt - 0.2
        out.append({"line": l, "start": round(starts[i], 3), "end": round(max(end, starts[i] + 0.5), 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("poem")
    ap.add_argument("--retime", action="store_true", help="overwrite $STUDIO_CONTENT/songs/<song>/timing.json")
    a = ap.parse_args()
    poem = load_poem(a.poem)
    out = build_dir(a.poem)
    src = vocals_path(a.poem)
    y = load_vocals(a.poem, AR)
    f0, rms = pitch_track(y)
    t = librosa.frames_to_time(np.arange(len(f0)), sr=AR, hop_length=HOP)

    phrases = find_phrases(f0, rms, t)
    # A spoken hook before the singing (poem.json "spoken_intro") is kept for the video but left out of the music
    # analysis: speech pitch says nothing about Sa.
    spoken = None
    until = (poem.get("spoken_intro") or {}).get("until")
    if until:
        talk = [p for p in phrases if p["end"] <= until]
        phrases = [p for p in phrases if p["end"] > until]
        if talk:
            spoken = {"start": talk[0]["start"], "end": talk[-1]["end"], "text": poem["spoken_intro"]["text"]}
        f0 = np.where(t < phrases[0]["start"] - 0.05, np.nan, f0)
    steady = steady_mask(1200 * np.log2(f0 / 55.0))
    # Phrases come to rest on Sa (or Pa) far more often than anywhere else: count their endings three times over.
    weight = np.ones(len(f0))
    for p in phrases:
        weight[(t > p["end"] - 1.2) & (t <= p["end"])] = 3.0
    cents = 1200 * np.log2(f0 / 55.0)
    finals = []
    for p in phrases:
        m = steady & (t > p["end"] - 1.0) & (t <= p["end"])
        if m.sum() > 5:
            finals.append(float(np.median(cents[m])))
    tonic, _, cands = find_tonic(f0, steady, weight, finals)
    mpath = poem_dir(a.poem) / "marks.json"
    marks = json.loads(mpath.read_text()) if mpath.exists() else None
    if marks and marks.get("vocals_bytes") != src.stat().st_size:
        print(f"[warn] {mpath.name} was marked on a different take; ignoring it")
        marks = None
    ref = poem["music"].get("reference")
    ref_info = None
    if poem["music"].get("tonic_hz"):
        tonic = float(poem["music"]["tonic_hz"])
    elif ref and (poem_dir(a.poem) / ref).exists():
        tonic, ref_sa, shift, ref_notes = reference_tonic(poem_dir(a.poem) / ref, f0)
        ref_info = {"file": ref, "sa_hz": round(ref_sa, 2), "take_vs_ref_cents": -shift, "notes": ref_notes}
        if marks and marks.get("guide_sa_hz"):
            # sung in the studio to a tanpura on a known Sa: that beats any guess from the pitch profile
            tonic = marks["guide_sa_hz"]
            ref_info["take_vs_ref_cents"] = round(1200 * np.log2(tonic / ref_sa))
            ref_info["from_guide"] = True
    if poem["music"].get("tonic_offset_cents"):  # tune the score to where this take actually sits
        tonic *= 2 ** (poem["music"]["tonic_offset_cents"] / 1200)
    notes, ragas, _ = find_scale(f0, steady, tonic)
    held = held_swaras(f0, steady, tonic, HOP / AR)
    onset = librosa.onset.onset_strength(y=y, sr=AR, hop_length=HOP)
    tempo = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=onset, sr=AR, hop_length=HOP))[0])

    analysis = {
        "vocals": str(src), "duration": round(len(y) / AR, 3), "tonic_hz": round(tonic, 2),
        "tonic_candidates": cands, "tonic_note": librosa.hz_to_note(tonic), "scale": notes, "raga_guess": ragas, "held": held, "reference": ref_info, "tempo_bpm_guess": round(tempo, 1),
        "median_f0": round(float(np.nanmedian(f0)), 1), "phrases": phrases, "spoken": spoken,
    }
    (out / "analysis.json").write_text(json.dumps(analysis, indent=1, ensure_ascii=False))
    np.savez_compressed(out / "f0.npz", f0=np.nan_to_num(f0), t=t, rms=rms, hop=HOP, sr=AR)

    lines = {l["id"]: l for l in poem["lines"]}
    tpath = poem_dir(a.poem) / "timing.json"
    if marks and len(marks["line_starts"]) == len(poem["sung"]):
        timing = from_marks(marks, phrases, poem["sung"], f0, t)
        tpath.write_text(json.dumps({"vocals": src.name, "source": "marks", "sung": timing}, indent=1))
        print(f"wrote {tpath} from your line marks")
    elif a.retime or not tpath.exists():
        timing = align(phrases, poem["sung"], lines, f0, t)
        tpath.write_text(json.dumps({"vocals": src.name, "sung": timing}, indent=1))
        print(f"wrote {tpath}")
    else:
        print(f"kept {tpath} (use --retime to rebuild it)")
    timing = json.loads(tpath.read_text())["sung"]

    # Per-video-frame voice features for the animation (the pitch thread only follows the singing).
    n = int(np.ceil(video_duration(poem, analysis) * FPS))
    vid = np.arange(n) / FPS
    env_src = gaussian_filter1d(rms, 2) / (np.percentile(rms[rms > 0], 98) + 1e-9)
    semis = 12 * np.log2(np.where(np.isfinite(f0), f0, np.nan) / tonic)
    env = np.zeros(n)
    pitch = [None] * n
    segs = segments(poem, analysis)
    for si, (va, vb, k) in enumerate(segs):
        vt = vid - k
        m = (vt >= va) & (vt < vb)
        env[m] = np.interp(vt[m], t, env_src)
        if si == len(segs) - 1:
            for j in np.flatnonzero(m):
                i = min(int(round(vt[j] * AR / HOP)), len(f0) - 1)
                if np.isfinite(semis[i]):
                    pitch[j] = round(float(semis[i]), 2)
    env = np.clip(env, 0, 1)
    (out / "frames.json").write_text(json.dumps({"fps": FPS, "energy": [round(float(e), 3) for e in env],
                                                  "pitch": pitch}))

    print(f"vocals   {src}  {analysis['duration']}s, median f0 {analysis['median_f0']} Hz")
    if ref_info:
        how = ("the studio guide's Sa" if ref_info.get("from_guide") else f"matched to the reference {ref_info['file']}")
        print(f"tonic    Sa = {tonic:.1f} Hz ({librosa.hz_to_note(tonic)}), {how} "
              f"(the original's Sa {ref_info['sa_hz']} Hz; offset {ref_info['take_vs_ref_cents']:+d} cents)")
        print("ref      the original uses " + " ".join(SWARA[k] for k in ref_notes) + "  (the score uses these)")
    else:
        print(f"tonic    Sa = {tonic:.1f} Hz  ({librosa.hz_to_note(tonic)})   candidates {cands}")
    print("swaras   " + "  ".join(f"{n['swara']}({n['share']:.0%})" for n in notes))
    print("held     " + " ".join(SWARA[k] for k in held) + "  (notes you rest on; the swarmandal uses these)")
    print(f"raga     sounds closest to {', '.join(ragas)}  (a guess; the score uses the notes above)")
    print(f"tempo    ~{tempo:.0f} bpm onset guess (only used if music.percussion is set)")
    if spoken:
        print(f"spoken   {spoken['start']:.2f} - {spoken['end']:.2f}  \"{spoken['text']}\" (kept as the hook)")
    print(f"phrases  {len(phrases)} sung")
    for s in timing:
        print(f"  {s['line']}  {s['start']:7.2f} - {s['end']:7.2f}  {lines[s['line']]['translit']}")


if __name__ == "__main__":
    main()
