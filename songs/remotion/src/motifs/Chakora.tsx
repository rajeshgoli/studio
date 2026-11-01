import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, fbm, rand, ramp} from '../lib';

const MX = 540;
const MY = 505;
const MR = 180;

/** Pointed lotus petal pointing up from the origin. */
const petal = (len: number, w: number) =>
  `M 0 0 C ${w} ${-len * 0.25} ${w * 0.7} ${-len * 0.75} 0 ${-len} C ${-w * 0.7} ${-len * 0.75} ${-w} ${-len * 0.25} 0 0 Z`;

/** Chakora (partridge) in profile facing right, body centred near the origin; wing drawn separately. */
const BODY =
  'M -66 4 C -64 -26 -34 -44 2 -44 C 18 -46 30 -58 44 -62 C 58 -66 70 -58 72 -48 L 86 -42 L 72 -38 ' +
  'C 70 -30 64 -24 58 -18 C 58 4 40 28 6 32 C -24 35 -50 26 -62 14 L -88 10 L -84 -2 Z';
const WING = 'M 0 0 C 18 -18 62 -22 92 -8 C 70 2 34 8 0 0 Z';

const Bird: React.FC<{x: number; y: number; s: number; flip: boolean; flap: number; tilt: number; glow: number}> = ({x, y, s, flip, flap, tilt, glow}) => (
  <g transform={`translate(${x},${y}) scale(${flip ? -s : s},${s}) rotate(${tilt})`}>
    <path d={BODY} fill={GOLD} opacity={0.18 * glow} transform="scale(1.12)" filter="url(#c-blur-s)" />
    {/* far wing */}
    <g transform={`translate(-6,-26) rotate(${-150 - flap * 40}) scale(1, ${0.9})`}>
      <path d={WING} fill="#141233" stroke={GOLD} strokeWidth={1.4} strokeOpacity={0.6} />
    </g>
    <path d={BODY} fill="#1a1838" stroke={GOLD} strokeWidth={2} strokeLinejoin="round" />
    {/* miniature-style markings: barred flank, eye stripe, collar */}
    {[0, 1, 2, 3, 4].map((i) => (
      <path key={i} d={`M ${-30 + i * 12} ${-4 + i * 1.5} q 5 9 2 18`} fill="none" stroke={CREAM} strokeOpacity={0.55} strokeWidth={1.4} strokeLinecap="round" />
    ))}
    <path d="M 46 -48 C 56 -52 64 -50 70 -46" fill="none" stroke={CREAM} strokeOpacity={0.8} strokeWidth={1.6} />
    <path d="M 40 -38 C 50 -28 58 -26 62 -30" fill="none" stroke={GOLD} strokeOpacity={0.8} strokeWidth={2} />
    <circle cx={58} cy={-50} r={3} fill={CREAM} />
    <path d="M 72 -46 L 86 -42 L 72 -39 Z" fill="#c9533e" />
    {/* near wing */}
    <g transform={`translate(-10,-24) rotate(${-160 - flap * 55})`}>
      <path d={WING} fill="#211e46" stroke={GOLD} strokeWidth={1.8} />
      {[0, 1, 2].map((i) => (
        <path key={i} d={`M ${30 + i * 18} ${-10 + i} l 14 6`} stroke={CREAM} strokeOpacity={0.5} strokeWidth={1.2} />
      ))}
    </g>
  </g>
);

const SPARKS = Array.from({length: 60}, (_, i) => ({
  a: rand(i * 3.3) * Math.PI * 2,
  r: MR + 110 + rand(i * 5.7) * 260,
  sp: 0.002 + rand(i * 1.1) * 0.004,
  ph: rand(i * 9.9) * 6.28,
  s: 0.8 + rand(i * 2.2) * 1.6,
}));

export const Chakora: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const L3 = lines[0] ?? {from: durationInFrames * 0.05, to: durationInFrames * 0.5};
  const L4 = lines[1] ?? {from: durationInFrames * 0.55, to: durationInFrames * 0.9};
  const halo = ramp(f, 0, 60);
  const nectar = ramp(f, L3.from, L3.from + 40);

  // Nectar drops: each forms on the moon's rim, trembles, swells, and falls.
  const PERIOD = 17;
  const drops: React.ReactNode[] = [];
  const start = L3.from;
  for (let k = 0; k < 60; k++) {
    const t0 = start + k * PERIOD + Math.floor(rand(k * 4.4) * 10);
    const age = f - t0;
    if (age < 0 || age > 110) continue;
    const xs = MX + (rand(k * 7.1) - 0.5) * 220;
    const rimY = MY + Math.sqrt(Math.max(0, MR * MR - (xs - MX) ** 2)) - 4;
    const form = Math.min(1, age / 30);
    const fall = Math.max(0, age - 30);
    const y = rimY + 0.045 * fall * fall + fall * 1.2;
    const tremble = age < 30 ? Math.sin(age * 1.3) * 1.5 * (0.5 + e) : 0;
    const op = Math.min(1, (980 - y) / 160) * nectar;
    if (op <= 0) continue;
    const r = 5 + 4 * form + rand(k) * 2.5;
    drops.push(
      <g key={k} transform={`translate(${xs + tremble},${y})`} opacity={op}>
        <circle r={r * 3.2} fill="#eef3ff" opacity={0.35 + 0.2 * e} filter="url(#c-blur-s)" />
        <path d={`M 0 ${-r * (age < 30 ? 1.4 : 2.6)} C ${r} ${-r * 0.4} ${r} ${r} 0 ${r} C ${-r} ${r} ${-r} ${-r * 0.4} 0 ${-r * (age < 30 ? 1.4 : 2.6)} Z`} fill="#f6f8ff" stroke={GOLD} strokeWidth={1.3} strokeOpacity={0.8} />
      </g>,
    );
  }

  // Birds rise during L4 in a long arc, then hover under the moon, beaks lifted to the falling light.
  const rise = ramp(f, L4.from - 45, L4.from + (L4.to - L4.from) * 0.7, Easing.inOut(Easing.sin));
  const birdIn = ramp(f, L4.from - 45, L4.from - 15);
  const flapRate = 0.55 - 0.25 * rise;
  const birds = [
    {sx: 60, sy: 1000, ex: 492, ey: 735, flip: false, ph: 0},
    {sx: 1030, sy: 1020, ex: 596, ey: 752, flip: true, ph: 2.1},
  ].map((b, i) => {
    const u = rise;
    const x = b.sx + (b.ex - b.sx) * u + Math.sin(f * 0.04 + b.ph) * 8 * u;
    const y = b.sy + (b.ey - b.sy) * u - Math.sin(u * Math.PI) * 120 + Math.sin(f * 0.06 + b.ph) * 6 * u;
    const flap = Math.sin(f * flapRate + b.ph) * (1 - 0.6 * u);
    const tilt = -10 - 18 * u + Math.sin(f * 0.05 + b.ph) * 3;
    return <Bird key={i} x={x} y={y} s={i ? 0.9 : 0.95} flip={b.flip} flap={flap} tilt={tilt} glow={0.5 + 0.5 * e + u * 0.5} />;
  });

  const sheenX = MX + fbm(f * 0.01, 3) * 60 - 40;
  const sheenY = MY + fbm(f * 0.01, 6) * 50 - 50;

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="c-glow" cx={MX} cy={MY} r={560} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#eef2ff" stopOpacity={0.5} />
            <stop offset="0.35" stopColor="#b9c6f0" stopOpacity={0.18} />
            <stop offset="1" stopColor="#6070b0" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="c-moon" cx="45%" cy="42%" r="62%">
            <stop offset="0" stopColor="#fffef8" />
            <stop offset="0.75" stopColor="#eceff9" />
            <stop offset="1" stopColor="#c6cfee" />
          </radialGradient>
          <radialGradient id="c-sheen" cx={sheenX} cy={sheenY} r={150} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#ffffff" stopOpacity={0.55} />
            <stop offset="1" stopColor="#ffffff" stopOpacity={0} />
          </radialGradient>
          <linearGradient id="c-petal" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#dfe6ff" stopOpacity={0.28} />
            <stop offset="1" stopColor="#dfe6ff" stopOpacity={0.02} />
          </linearGradient>
          <clipPath id="c-clip"><circle cx={MX} cy={MY} r={MR} /></clipPath>
          <filter id="c-blur-l" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="22" /></filter>
          <filter id="c-blur-s" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4" /></filter>
        </defs>

        <circle cx={MX} cy={MY} r={560} fill="url(#c-glow)" opacity={0.8 + 0.3 * e} />

        {/* lotus-petal halo: two rings turning against each other */}
        <g opacity={halo}>
          <g transform={`translate(${MX},${MY}) rotate(${f * 0.08})`}>
            {Array.from({length: 16}, (_, i) => (
              <g key={i} transform={`rotate(${(i / 16) * 360}) translate(0,${-MR - 18})`}>
                <path d={petal(108 + 10 * e, 42)} fill="url(#c-petal)" stroke={GOLD} strokeOpacity={0.55} strokeWidth={1.5} />
                <path d={petal(70, 20)} fill="none" stroke={CREAM} strokeOpacity={0.25} strokeWidth={1} />
              </g>
            ))}
          </g>
          <g transform={`translate(${MX},${MY}) rotate(${-f * 0.12 + 11.25})`}>
            {Array.from({length: 16}, (_, i) => (
              <g key={i} transform={`rotate(${(i / 16) * 360}) translate(0,${-MR - 8})`}>
                <path d={petal(70, 26)} fill="none" stroke={GOLD} strokeOpacity={0.35} strokeWidth={1.1} />
                <circle cy={-78} r={2.4} fill={GOLD} opacity={0.6 + 0.4 * Math.sin(f * 0.1 + i)} />
              </g>
            ))}
          </g>
          <circle cx={MX} cy={MY} r={MR + 140 + 8 * e} fill="none" stroke={GOLD} strokeOpacity={0.22} strokeWidth={1}
            strokeDasharray="2 9" />
        </g>

        {/* the moon of the face */}
        <circle cx={MX} cy={MY} r={MR + 24} fill="#e6ebff" opacity={0.45 + 0.25 * e} filter="url(#c-blur-l)" />
        <circle cx={MX} cy={MY} r={MR} fill="url(#c-moon)" />
        <g clipPath="url(#c-clip)">
          {[[-55, -40, 46], [50, 30, 58], [-30, 75, 30], [80, -70, 24], [-95, 35, 22]].map(([dx, dy, r], i) => (
            <circle key={i} cx={MX + dx} cy={MY + dy} r={r} fill="#9aa4cf" opacity={0.08} filter="url(#c-blur-s)" />
          ))}
          <circle cx={MX} cy={MY} r={MR} fill="url(#c-sheen)" />
          {/* shimmer bands drifting across the surface */}
          {[0, 1, 2].map((i) => (
            <ellipse key={i} cx={MX + ((f * (0.6 + i * 0.3) + i * 140) % (MR * 2 + 200)) - MR - 100} cy={MY - 60 + i * 60}
              rx={30} ry={MR * 1.2} fill="#ffffff" opacity={0.06 + 0.06 * e} filter="url(#c-blur-l)" />
          ))}
        </g>
        <circle cx={MX} cy={MY} r={MR} fill="none" stroke={GOLD} strokeOpacity={0.5} strokeWidth={1.5} />

        {/* floating silver sparks around the halo */}
        {SPARKS.map((s, i) => {
          const a = s.a + f * s.sp;
          return (
            <circle key={i} cx={MX + Math.cos(a) * s.r} cy={MY + Math.sin(a) * s.r * 0.95} r={s.s}
              fill="#f4f6ff" opacity={(0.25 + 0.5 * Math.sin(f * 0.06 + s.ph) ** 2) * halo} />
          );
        })}

        {drops}
        <g opacity={birdIn}>{birds}</g>
      </svg>
    </AbsoluteFill>
  );
};
