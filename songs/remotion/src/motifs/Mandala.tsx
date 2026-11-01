import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, rand, ramp} from '../lib';

const CX = 540;
const CY = 400; // lifted and scaled to bloom above the two figures
const S = 0.62;

/** Pointed lotus petal, base at the origin, pointing up. */
const lotusPetal = (len: number, w: number) =>
  `M 0 0 C ${w} ${-len * 0.22} ${w * 0.75} ${-len * 0.72} 0 ${-len} C ${-w * 0.75} ${-len * 0.72} ${-w} ${-len * 0.22} 0 0 Z`;
/** Rounded jasmine petal. */
const roundPetal = (len: number, w: number) =>
  `M 0 0 C ${w} ${-len * 0.1} ${w * 1.05} ${-len * 0.85} 0 ${-len} C ${-w * 1.05} ${-len * 0.85} ${-w} ${-len * 0.1} 0 0 Z`;

type Ring = {n: number; r: number; len: number; w: number; kind: 'lotus' | 'round'; dir: 1 | -1; fill: string};

// inner rings first; each blooms in turn across the line (the first half for the first "priye cāruśīle")
const RINGS: Ring[] = [
  {n: 8, r: 14, len: 56, w: 20, kind: 'round', dir: 1, fill: '#fff6ea'},
  {n: 12, r: 40, len: 72, w: 26, kind: 'lotus', dir: -1, fill: '#f7c9d8'},
  {n: 16, r: 86, len: 84, w: 33, kind: 'lotus', dir: 1, fill: '#f2b3c9'},
  {n: 24, r: 150, len: 64, w: 28, kind: 'round', dir: -1, fill: '#fff3e2'},
  {n: 24, r: 196, len: 96, w: 42, kind: 'lotus', dir: 1, fill: '#e9a1bd'},
  {n: 32, r: 270, len: 80, w: 38, kind: 'lotus', dir: -1, fill: '#f6dbe6'},
];

/** Five-petal jasmine flower for the falling blossoms. */
const Jasmine: React.FC<{s: number}> = ({s}) => (
  <g transform={`scale(${s})`}>
    {[0, 1, 2, 3, 4].map((i) => (
      <path key={i} d={roundPetal(16, 6)} transform={`rotate(${i * 72})`} fill="#fffaf0" stroke={GOLD} strokeOpacity={0.5} strokeWidth={0.8} />
    ))}
    <circle r={2.6} fill={GOLD} />
  </g>
);

const FALL = Array.from({length: 9}, (_, i) => ({
  x: 90 + rand(i * 4.7) * 900,
  t0: rand(i * 2.9) * 200 - 30,
  sp: 1.6 + rand(i * 6.3) * 1.4,
  sway: 20 + rand(i * 8.1) * 30,
  rot: rand(i * 3.3) * 360,
  s: 0.8 + rand(i * 5.1) * 0.6,
}));

export const Mandala: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const L = lines[0] ?? {from: 20, to: durationInFrames - 30};
  const span = Math.max(60, L.to - L.from);
  const glow = ramp(f, 0, 40);
  const pulse = 1 + 0.035 * e;

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="m-glow" cx={CX} cy={CY} r={520} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#ffd9e6" stopOpacity={0.45} />
            <stop offset="0.4" stopColor="#d58fb4" stopOpacity={0.16} />
            <stop offset="1" stopColor="#7a3d6a" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="m-bindu">
            <stop offset="0" stopColor="#fffbe8" />
            <stop offset="0.5" stopColor={GOLD} />
            <stop offset="1" stopColor={GOLD} stopOpacity={0} />
          </radialGradient>
          {RINGS.map((rg, i) => (
            <linearGradient key={i} id={`m-p${i}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0" stopColor={rg.fill} stopOpacity={0.9} />
              <stop offset="1" stopColor={rg.fill} stopOpacity={0.35} />
            </linearGradient>
          ))}
          <filter id="m-blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="18" /></filter>
          <filter id="m-blur-s" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" /></filter>
        </defs>

        <circle cx={CX} cy={CY} r={520} fill="url(#m-glow)" opacity={glow * (0.75 + 0.35 * e)} />

        <g transform={`translate(${CX},${CY}) scale(${pulse * S})`}>
          {/* outer rings drawn first so inner petals sit on top */}
          {RINGS.map((rg, ri) => ri).reverse().map((ri) => {
            const rg = RINGS[ri];
            const a = L.from - 25 + (ri / RINGS.length) * span * 0.85;
            const bloom = ramp(f, a, a + 50, Easing.out(Easing.back(1.4)));
            const lift = ramp(f, a, a + 50);
            if (lift <= 0) return null;
            const rot = rg.dir * f * (0.12 + ri * 0.02) + (ri % 2 ? 180 / rg.n : 0);
            const ringR = rg.r * (0.6 + 0.4 * lift);
            return (
              <g key={ri} transform={`rotate(${rot})`} opacity={Math.min(1, lift * 1.5)}>
                {/* filigree: a dotted ring past the petal tips and a fine gold rule at their base */}
                <circle r={rg.r + rg.len + 12} fill="none" stroke={GOLD} strokeOpacity={0.4 * lift} strokeWidth={1.2}
                  strokeDasharray={`1.5 ${ri % 2 ? 7 : 11}`} />
                {Array.from({length: rg.n}, (_, i) => {
                  const ang = (i / rg.n) * 360;
                  const breathe = 1 + 0.05 * Math.sin(f * 0.07 + i * 0.6 + ri) * (0.4 + e);
                  const P = rg.kind === 'lotus' ? lotusPetal : roundPetal;
                  return (
                    <g key={i} transform={`rotate(${ang}) translate(0,${-ringR}) scale(${bloom * breathe})`}>
                      <path d={P(rg.len, rg.w)} fill={`url(#m-p${ri})`} stroke={GOLD} strokeWidth={1.3} strokeOpacity={0.85} />
                      <path d={`M 0 -4 L 0 ${-rg.len * 0.78}`} stroke={GOLD} strokeOpacity={0.45} strokeWidth={0.9} />
                      {rg.kind === 'lotus' && (
                        <path d={P(rg.len * 0.62, rg.w * 0.5)} fill="none" stroke="#fff" strokeOpacity={0.35} strokeWidth={0.8} />
                      )}
                      <circle cy={-rg.len - 9} r={ri > 3 ? 2 : 2.6} fill={GOLD} opacity={0.5 + 0.5 * Math.sin(f * 0.12 + i)} />
                    </g>
                  );
                })}
                <circle r={ringR} fill="none" stroke={GOLD} strokeOpacity={0.55 * lift} strokeWidth={1.2} />
              </g>
            );
          })}
          {/* bindu at the heart */}
          <circle r={34 + 14 * e} fill="url(#m-bindu)" opacity={glow} />
          <circle r={9} fill="#fffaf0" opacity={glow} />
          <circle r={16} fill="none" stroke={GOLD} strokeWidth={1.4} opacity={glow} />
        </g>

        {/* gentle bright pulse from the centre each time the voice swells */}
        <circle cx={CX} cy={CY} r={(120 + 260 * ((f % 75) / 75)) * S} fill="none" stroke={CREAM}
          strokeOpacity={0.18 * (1 - (f % 75) / 75) * glow * (0.5 + e)} strokeWidth={2} />

        {/* jasmine flowers drifting down */}
        {FALL.map((j, i) => {
          const age = f - j.t0;
          if (age < 0) return null;
          const y = 120 + age * j.sp;
          if (y > 1060) return null;
          const x = j.x + Math.sin(age * 0.03 + i) * j.sway;
          const op = Math.min(1, age / 20) * Math.min(1, (1060 - y) / 120) * glow;
          return (
            <g key={i} transform={`translate(${x},${y}) rotate(${j.rot + age * 1.2})`} opacity={op * 0.85}>
              <circle r={22 * j.s} fill="#fff" opacity={0.12} filter="url(#m-blur-s)" />
              <Jasmine s={j.s} />
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
