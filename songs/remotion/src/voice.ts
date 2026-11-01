import {Timeline} from './types';

/** Per-frame voice lookups built once per timeline. */
export const makeVoice = (tl: Timeline) => {
  const n = tl.energy.length;
  // light smoothing so the glow breathes rather than flickers
  const sm = tl.energy.map((_, i) => {
    let s = 0;
    let w = 0;
    for (let k = -3; k <= 3; k++) {
      const j = i + k;
      if (j < 0 || j >= n) continue;
      const ww = 4 - Math.abs(k);
      s += tl.energy[j] * ww;
      w += ww;
    }
    return s / w;
  });
  const voiced = tl.pitch.map((p) => (p === null ? 0 : 1));
  const cum: number[] = [0];
  for (let i = 0; i < voiced.length; i++) cum.push(cum[i] + voiced[i]);
  const at = (arr: number[], f: number) => arr[Math.max(0, Math.min(arr.length - 1, Math.round(f)))] ?? 0;

  return {
    energy: (f: number) => at(sm, f),
    pitch: (f: number) => {
      const i = Math.round(f);
      return i >= 0 && i < tl.pitch.length ? tl.pitch[i] : null;
    },
    /** How far through line `li` the singing is at frame f, counted in voiced frames (pauses don't advance it). */
    progress: (li: number, f: number) => {
      const l = tl.lines[li];
      const a = Math.round(l.start * tl.fps);
      const b = Math.round(l.end * tl.fps);
      const total = cum[Math.min(b, cum.length - 1)] - cum[Math.min(a, cum.length - 1)];
      if (f <= a) return 0;
      if (f >= b || total <= 0) return f >= b ? 1 : 0;
      return (cum[Math.min(Math.round(f), cum.length - 1)] - cum[a]) / total;
    },
  };
};

export type Voice = ReturnType<typeof makeVoice>;
