import {interpolate, Easing} from 'remotion';

/** Deterministic pseudo-random in [0,1) from an integer/float seed (no Math.random in renders). */
export const rand = (seed: number): number => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

/** Smooth 1D value noise in [-1,1]. */
export const noise1 = (x: number, seed = 0): number => {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  const a = rand(i + seed * 101.7) * 2 - 1;
  const b = rand(i + 1 + seed * 101.7) * 2 - 1;
  return a + (b - a) * u;
};

/** Layered noise, still in about [-1,1]. */
export const fbm = (x: number, seed = 0, oct = 3): number => {
  let v = 0;
  let amp = 0.5;
  let f = 1;
  let norm = 0;
  for (let o = 0; o < oct; o++) {
    v += amp * noise1(x * f, seed + o * 17);
    norm += amp;
    amp *= 0.5;
    f *= 2.03;
  }
  return v / norm;
};

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** 0→1 between frames a and b with ease in-out. */
export const ramp = (frame: number, a: number, b: number, ease = Easing.inOut(Easing.cubic)) =>
  interpolate(frame, [a, b], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease});

/** Fade in over `inF` frames after `a`, out over `outF` before `b`. */
export const window01 = (frame: number, a: number, b: number, inF = 15, outF = 15) =>
  Math.min(ramp(frame, a, a + inF), 1 - ramp(frame, b - outF, b));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Mix two #rrggbb colors. */
export const mixColor = (c1: string, c2: string, t: number): string => {
  const p = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const a = p(c1);
  const b = p(c2);
  const m = a.map((v, i) => Math.round(lerp(v, b[i], clamp01(t))));
  return `#${m.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
};

/** Words of a transliterated line with their syllable spans, for the sung-word highlight. */
const VOWEL = /ai|au|[aāiīuūṛṝḷeo]/g;
export const sylCount = (s: string) => Math.max(1, (s.toLowerCase().match(VOWEL) ?? []).length);

export const ART = {top: 140, bottom: 1160, cx: 540, cy: 640}; // where motifs draw; lyrics live below

export const FONTS = {
  serif: '"Hoefler Text", "Baskerville", "Palatino", Georgia, serif',
  deva: '"Kohinoor Devanagari", "ITF Devanagari", "Devanagari Sangam MN", sans-serif',
  sans: '"Avenir Next", "Helvetica Neue", sans-serif',
};

export const GOLD = '#e8c27a';
export const CREAM = '#f6ecd9';
