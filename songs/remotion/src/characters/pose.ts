import {fbm, rand} from '../lib';

export type Facing = 'left' | 'right';
export type GazeName = 'ahead' | 'down' | 'up' | 'closed' | 'back';
export type ArmName = 'rest' | 'plead' | 'offer' | 'heart' | 'reach';

/** Numeric eye state: lid 0 open .. 1 closed, pupil offset in head units (+x toward the nose). */
export type Gaze = {lid: number; px: number; py: number};
/** Arm angles in degrees: shoulder from straight down (+ = forward), elbow bend (+ = forward), wrist. */
export type Arm = {sh: number; el: number; wr: number};

export const GAZES: Record<GazeName, Gaze> = {
  ahead: {lid: 0.08, px: 0, py: 0},
  down: {lid: 0.5, px: 0.6, py: 2.4},
  up: {lid: 0, px: 0.8, py: -2.6},
  closed: {lid: 1, px: 0, py: 1.5},
  back: {lid: 0.22, px: -3.6, py: 0.6},
};

export const ARMS: Record<ArmName, Arm> = {
  rest: {sh: 4, el: 30, wr: 6},
  plead: {sh: 18, el: 118, wr: -40},
  offer: {sh: 26, el: 96, wr: -20},
  heart: {sh: 6, el: 140, wr: -82},
  reach: {sh: 52, el: 30, wr: -20},
};

export type CharProps = {
  facing?: Facing;
  headTilt?: number; // degrees, + = chin up
  gaze?: GazeName | Gaze;
  arm?: ArmName | Arm;
  smile?: number; // 0..1
  /** 0..1 how much the jasmine garland is in hand (Krishna's 'offer'). */
  garland?: number;
  /** Seed so two figures don't blink in step. */
  seed?: number;
  /** Krishna: draw only the body+head or only the arm, so the arm can pass in front of Radha in the embrace. */
  layer?: 'all' | 'body' | 'arm';
  /** Radha: extra veil swing (in px at the hem), e.g. while she turns. */
  swing?: number;
  /** Unique prefix for SVG ids. */
  id: string;
};

export const gazeOf = (g: GazeName | Gaze | undefined): Gaze => (typeof g === 'string' ? GAZES[g] : g ?? GAZES.ahead);
export const armOf = (a: ArmName | Arm | undefined): Arm => (typeof a === 'string' ? ARMS[a] : a ?? ARMS.rest);

const L = (a: number, b: number, t: number) => a + (b - a) * t;
export const blendGaze = (a: Gaze, b: Gaze, t: number): Gaze => ({lid: L(a.lid, b.lid, t), px: L(a.px, b.px, t), py: L(a.py, b.py, t)});
export const blendArm = (a: Arm, b: Arm, t: number): Arm => ({sh: L(a.sh, b.sh, t), el: L(a.el, b.el, t), wr: L(a.wr, b.wr, t)});

/** 0..1 eyelid closure from natural, irregular blinks (about every 2.5-6 s, 0.17 s long). */
export const blinkAt = (frame: number, fps: number, seed: number): number => {
  const t = frame / fps;
  let at = 0.8 + rand(seed * 3.1) * 2;
  for (let k = 0; at < t + 1; k++) {
    const d = t - at;
    if (d >= 0 && d < 0.17) return Math.sin((d / 0.17) * Math.PI);
    // now and then a quick double blink
    if (rand(seed + k * 7.3) > 0.85) {
      const d2 = t - (at + 0.3);
      if (d2 >= 0 && d2 < 0.15) return Math.sin((d2 / 0.15) * Math.PI);
    }
    at += 2.5 + rand(seed * 11 + k * 1.37) * 3.5;
  }
  return 0;
};

/** Slow idle motion: breath 0..1 phase-ish value and gentle sways in [-1, 1]. */
export const idle = (frame: number, fps: number, seed: number) => {
  const t = frame / fps;
  return {
    breath: Math.sin((t / 4.6) * Math.PI * 2 + seed),
    sway: fbm(t * 0.35, seed),
    sway2: fbm(t * 0.6 + 10, seed + 3),
    t,
  };
};
