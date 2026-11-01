import React from 'react';
import {Arm, Gaze} from './pose';

export const deg = (d: number) => (d * Math.PI) / 180;

export type Pt = [number, number];

/** Shoulder -> elbow -> wrist for an arm hanging from S (angles from straight down, + = toward the face). */
export const armJoints = (S: Pt, a: Arm, upper: number, fore: number) => {
  const d1: Pt = [Math.sin(deg(a.sh)), Math.cos(deg(a.sh))];
  const E: Pt = [S[0] + upper * d1[0], S[1] + upper * d1[1]];
  const fa = a.sh + a.el;
  const d2: Pt = [Math.sin(deg(fa)), Math.cos(deg(fa))];
  const W: Pt = [E[0] + fore * d2[0], E[1] + fore * d2[1]];
  return {E, W, fa, handAngle: fa + a.wr};
};

/** A tapered limb from a to b as a smooth closed path (rounded at both ends). */
export const limb = (a: Pt, b: Pt, wa: number, wb: number) => {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const p1 = [a[0] + nx * wa / 2, a[1] + ny * wa / 2];
  const p2 = [b[0] + nx * wb / 2, b[1] + ny * wb / 2];
  const p3 = [b[0] - nx * wb / 2, b[1] - ny * wb / 2];
  const p4 = [a[0] - nx * wa / 2, a[1] - ny * wa / 2];
  // slight muscle swell in the middle
  const m1 = [(p1[0] + p2[0]) / 2 + nx * wa * 0.08, (p1[1] + p2[1]) / 2 + ny * wa * 0.08];
  const m2 = [(p3[0] + p4[0]) / 2 - nx * wa * 0.08, (p3[1] + p4[1]) / 2 - ny * wa * 0.08];
  return `M${p1[0]},${p1[1]} Q${m1[0]},${m1[1]} ${p2[0]},${p2[1]} A${wb / 2},${wb / 2} 0 0 1 ${p3[0]},${p3[1]} Q${m2[0]},${m2[1]} ${p4[0]},${p4[1]} A${wa / 2},${wa / 2} 0 0 1 ${p1[0]},${p1[1]} Z`;
};

/** An open, graceful hand (side view), wrist at the origin, fingers along +y, thumb toward +x. */
export const Hand: React.FC<{at: Pt; angle: number; skin: string; line: string; scale?: number; cup?: number}> = ({at, angle, skin, line, scale = 1, cup = 0}) => (
  <g transform={`translate(${at[0]},${at[1]}) rotate(${-angle}) scale(${scale})`}>
    <path
      d={`M-8,-2 C-11,8 -12,20 -11,30 C-10,40 -7,50 ${-2 + cup * 4},${56 - cup * 6}
          C${2 + cup * 4},${57 - cup * 6} 5,${50 - cup * 3} 7,42 C9,34 10,27 14,22 C18,17 22,12 19,8
          C16,5 12,9 9,12 C8,7 8,2 8,-2 Z`}
      fill={skin} stroke={line} strokeWidth={1.1} strokeLinejoin="round" />
    <path d="M-3,34 C-2,42 -1,48 0,52 M1,32 C2,40 3,45 3,49" fill="none" stroke={line} strokeWidth={0.7} strokeOpacity={0.7} />
  </g>
);

/** Almond eye in profile (facing +x). Coordinates are head-local. */
export const Eye: React.FC<{
  id: string; g: Gaze; blink: number; front: Pt; back: Pt; peak: number; low: number; iris: string; line: string;
  kohl?: number;
}> = ({id, g, blink, front: F, back: B, peak, low, iris, line, kohl = 1}) => {
  const lid = Math.min(1, g.lid + (1 - g.lid) * blink);
  const mx = B[0] + (F[0] - B[0]) * 0.55;
  const cornerY = (B[1] + F[1]) / 2;
  const upPeak = low - 1 + (peak - (low - 1)) * (1 - lid);
  const cu = 2 * upPeak - cornerY;
  const cl = 2 * low - cornerY;
  const upper = `M${B[0]},${B[1]} Q${mx},${cu} ${F[0]},${F[1]}`;
  const white = `${upper} Q${mx},${cl} ${B[0]},${B[1]} Z`;
  const ix = F[0] - (F[0] - B[0]) * 0.3 + g.px;
  const iy = (peak + low) / 2 - 0.5 + g.py;
  const r = (low - peak) * 0.47;
  return (
    <g>
      <defs>
        <clipPath id={`${id}-eye`}><path d={white} /></clipPath>
      </defs>
      <path d={white} fill="#fbf4ea" />
      <g clipPath={`url(#${id}-eye)`}>
        <circle cx={ix} cy={iy} r={r} fill={iris} />
        <circle cx={ix + 0.6} cy={iy} r={r * 0.55} fill="#0b0708" />
        <circle cx={ix + r * 0.35} cy={iy - r * 0.4} r={r * 0.22} fill="#fff" opacity={0.85} />
        {/* the upper lid's shadow on the eyeball */}
        <path d={`${upper} L${F[0]},${F[1] - 8} L${B[0]},${B[1] - 8} Z`} fill="none" stroke="#000" strokeOpacity={0.25} strokeWidth={3} />
      </g>
      {/* lash line, extended back as a kohl wing */}
      <path d={`${upper}`} fill="none" stroke={line} strokeWidth={2.4} strokeLinecap="round" />
      <path d={`M${B[0] + 2},${B[1] - 0.5} Q${B[0] - 5},${B[1] - 2} ${B[0] - 11 * kohl},${B[1] - 4.5 * kohl}`} fill="none" stroke={line} strokeWidth={1.8} strokeLinecap="round" />
      <path d={`M${B[0]},${B[1]} Q${mx},${cl} ${F[0]},${F[1]}`} fill="none" stroke={line} strokeWidth={1.1} strokeOpacity={0.8} />
      {/* crease */}
      <path d={`M${B[0] + 3},${B[1] - 5} Q${mx},${cu - 6 - 4 * (1 - lid)} ${F[0] - 3},${F[1] - 5}`} fill="none" stroke={line} strokeWidth={0.9} strokeOpacity={0.45 * (1 - lid * 0.6)} />
    </g>
  );
};

/** A small four-point sparkle. */
export const Glint: React.FC<{x: number; y: number; s: number; o: number}> = ({x, y, s, o}) =>
  o <= 0.01 ? null : (
    <path transform={`translate(${x},${y}) scale(${s})`} d="M0,-6 L1.2,-1.2 L6,0 L1.2,1.2 L0,6 L-1.2,1.2 L-6,0 L-1.2,-1.2 Z" fill="#fffbe8" opacity={o} />
  );

/** Points along a quadratic curve, for strands of pearls and flowers. */
export const alongQuad = (a: Pt, c: Pt, b: Pt, n: number): Pt[] =>
  Array.from({length: n}, (_, i) => {
    const t = i / (n - 1);
    const u = 1 - t;
    return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
  });
