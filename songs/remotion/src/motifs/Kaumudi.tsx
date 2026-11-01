import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, fbm, rand, ramp} from '../lib';

const MX = 540;
const MY = 500;
const MR = 140;

/** A miniature-painting cloud: a cluster of round puffs (rounder in the middle) with a flat-ish belly. */
const puffs = (w: number, h: number, seed: number) => {
  const n = 6 + Math.floor(rand(seed) * 4);
  return Array.from({length: n}, (_, i) => {
    const u = n === 1 ? 0.5 : i / (n - 1);
    const arch = Math.sin(u * Math.PI);
    const r = h * (0.35 + 0.55 * arch) * (0.8 + 0.4 * rand(seed + i * 2.3));
    return {x: (u - 0.5) * w, y: -arch * h * 0.45 + r * 0.25, r};
  });
};

/** Curls inside a cloud: short spiral strokes, the way miniature painters line their clouds. */
const curl = (x: number, y: number, r: number) =>
  `M ${x - r} ${y} A ${r} ${r} 0 1 1 ${x + r * 0.2} ${y + r * 0.6} A ${r * 0.55} ${r * 0.55} 0 1 1 ${x - r * 0.1} ${y - r * 0.15}`;

type Cloud = {x: number; y: number; w: number; h: number; sp: number; seed: number; layer: number};

const CLOUDS: Cloud[] = Array.from({length: 14}, (_, i) => ({
  x: rand(i * 5.1) * 1300 - 110,
  y: 260 + rand(i * 2.7) * 560,
  w: 300 + rand(i * 8.3) * 340,
  h: 70 + rand(i * 1.9) * 70,
  sp: (0.25 + rand(i * 6.1) * 0.45) * (i % 2 ? 1 : -1),
  seed: i * 11.7,
  layer: i % 3,
}));

const FOG = Array.from({length: 16}, (_, i) => ({
  x: rand(i * 3.7 + 1) * 1080,
  y: 200 + rand(i * 9.1 + 2) * 800,
  rx: 260 + rand(i * 4.4) * 260,
  ry: 120 + rand(i * 7.2) * 120,
  sp: 0.2 + rand(i * 2.2) * 0.4,
}));

const MOTES = Array.from({length: 70}, (_, i) => ({
  x: rand(i * 13.1) * 1080,
  y0: rand(i * 17.3) * 900,
  sp: 0.4 + rand(i * 3.9) * 0.9,
  r: 0.8 + rand(i * 5.5) * 1.8,
  ph: rand(i * 2.1) * 6.28,
}));

export const Kaumudi: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const L1 = lines[0] ?? {from: durationInFrames * 0.25, to: durationInFrames * 0.6};
  const L2 = lines[1] ?? {from: durationInFrames * 0.62, to: durationInFrames * 0.95};
  const r1 = ramp(f, L1.from - 10, L1.to);
  const r2 = ramp(f, L2.from - 10, L2.to + 15);
  const light = 0.1 + 0.45 * r1 + 0.45 * r2; // how much moonlight is through
  const fog = 1 - 0.2 * r1 - 0.8 * r2; // how much darkness remains
  const glow = light * (0.85 + 0.25 * e);

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="k-halo" cx={MX} cy={MY} r={620} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#eef2ff" stopOpacity={0.55} />
            <stop offset="0.25" stopColor="#a9b8ea" stopOpacity={0.22} />
            <stop offset="1" stopColor="#5a6aa8" stopOpacity={0} />
          </radialGradient>
          <radialGradient id="k-moon" cx="42%" cy="40%" r="65%">
            <stop offset="0" stopColor="#fffdf6" />
            <stop offset="0.7" stopColor="#e9ecf8" />
            <stop offset="1" stopColor="#bfc9ea" />
          </radialGradient>
          <linearGradient id="k-ray" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#f4f6ff" stopOpacity={0.5} />
            <stop offset="1" stopColor="#f4f6ff" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="k-cloud" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1c2148" />
            <stop offset="1" stopColor="#070919" />
          </linearGradient>
          <filter id="k-blur-xl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="50" /></filter>
          <filter id="k-blur-m" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14" /></filter>
          <filter id="k-blur-s" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" /></filter>
        </defs>

        {/* moon halo and light spilling into the sky */}
        <circle cx={MX} cy={MY} r={620} fill="url(#k-halo)" opacity={glow} />

        {/* rays: long soft wedges turning slowly, each breaking through its own gap in the cloud */}
        <g opacity={Math.min(1, light * 1.3) * (0.6 + 0.4 * e)}>
          {Array.from({length: 18}, (_, i) => {
            const a = (i / 18) * 360 + f * 0.06 + fbm(i * 3.1, 2) * 8;
            const gap = Math.max(0, fbm(f * 0.012 + i * 1.7, 5) * 0.5 + 0.5 - 0.35 * (1 - r2));
            const len = 520 + 220 * rand(i * 4.2);
            const wdt = 30 + 40 * rand(i * 7.9);
            return (
              <path key={i} d={`M ${MR * 0.9} ${-wdt * 0.15} L ${len} ${-wdt} L ${len} ${wdt} L ${MR * 0.9} ${wdt * 0.15} Z`}
                fill="url(#k-ray)" opacity={gap * 0.5} transform={`translate(${MX},${MY}) rotate(${a})`} filter="url(#k-blur-m)" />
            );
          })}
        </g>

        {/* the moon itself, faint behind the veil, then clear */}
        <g opacity={0.25 + 0.75 * light}>
          <circle cx={MX} cy={MY} r={MR + 30} fill="#dfe6ff" opacity={0.35 * glow} filter="url(#k-blur-m)" />
          <circle cx={MX} cy={MY} r={MR} fill="url(#k-moon)" />
          {[[-40, -30, 32, 0.08], [35, 20, 42, 0.07], [-20, 55, 22, 0.06], [55, -50, 18, 0.05]].map(([dx, dy, r, o], i) => (
            <circle key={i} cx={MX + dx + fbm(f * 0.004 + i, 9) * 4} cy={MY + dy} r={r} fill="#8d97c4" opacity={o} filter="url(#k-blur-s)" />
          ))}
        </g>

        {/* gold dot ring, drawn in as the light arrives (Pichwai ornament) */}
        <g opacity={light} transform={`rotate(${f * 0.05}, ${MX}, ${MY})`}>
          <circle cx={MX} cy={MY} r={MR + 38} fill="none" stroke={GOLD} strokeOpacity={0.45} strokeWidth={1.2}
            strokeDasharray={`${2 * Math.PI * (MR + 38) * Math.min(1, r1 * 1.2 + 0.05)} 4000`} />
          {Array.from({length: 48}, (_, i) => {
            const show = i / 48 < r1 * 1.1;
            const a = (i / 48) * Math.PI * 2;
            return show ? (
              <circle key={i} cx={MX + Math.cos(a) * (MR + 56)} cy={MY + Math.sin(a) * (MR + 56)} r={i % 4 === 0 ? 3 : 1.6}
                fill={i % 4 === 0 ? GOLD : CREAM} opacity={0.5 + 0.4 * Math.sin(f * 0.08 + i)} />
            ) : null;
          })}
        </g>

        {/* deep fog (timira): huge blurred shapes drifting, thinning, pushed off-canvas in L2 */}
        <g filter="url(#k-blur-xl)" opacity={0.92 * fog}>
          {FOG.map((b, i) => {
            const dx = b.x + Math.sin(f * 0.004 * b.sp + i) * 120 + fbm(f * 0.003 + i, 3) * 60;
            const dir = dx < MX ? -1 : 1;
            const push = r2 * 600 * dir;
            return <ellipse key={i} cx={dx + push} cy={b.y + fbm(f * 0.004 + i * 2, 4) * 40} rx={b.rx} ry={b.ry} fill="#04050f" />;
          })}
        </g>

        {/* painted clouds with gold rims, scattering outward as the darkness is stolen away */}
        {CLOUDS.map((c, i) => {
          const drift = ((c.x + f * c.sp + 1400) % 1500) - 210;
          const dir = drift < MX ? -1 : 1;
          const push = r2 * (520 + 200 * rand(i)) * dir;
          const rise = -r2 * 60 * rand(i * 2);
          const o = Math.max(0, 1 - r2 * 1.2) * (0.6 + 0.4 * (2 - c.layer) / 2);
          const lit = light * (0.25 + 0.4 * e);
          return o > 0.01 ? (
            <g key={i} transform={`translate(${drift + push}, ${c.y + rise + Math.sin(f * 0.01 + i) * 6})`} opacity={o}>
              {puffs(c.w, c.h, c.seed).map((p, k) => (
                <circle key={`s${k}`} cx={p.x} cy={p.y} r={p.r + 2} fill={GOLD} fillOpacity={0.3 + lit} />
              ))}
              {puffs(c.w, c.h, c.seed).map((p, k) => (
                <circle key={`f${k}`} cx={p.x} cy={p.y} r={p.r} fill="url(#k-cloud)" />
              ))}
              {puffs(c.w * 0.7, c.h * 0.6, c.seed + 9).slice(1, -1).map((p, k) =>
                k % 2 === 0 ? (
                  <path key={`c${k}`} d={curl(p.x, p.y + c.h * 0.05, p.r * 0.45)} fill="none" stroke={GOLD}
                    strokeWidth={1.1} strokeOpacity={0.2 + lit * 0.6} strokeLinecap="round" />
                ) : null,
              )}
            </g>
          ) : null;
        })}

        {/* beams breaking through the gaps while the cloud still holds */}
        <g opacity={r1 * (1 - r2) * (0.55 + 0.45 * e)}>
          {Array.from({length: 7}, (_, i) => {
            const a = 40 + i * 16 + fbm(f * 0.006 + i * 2.3, 7) * 10;
            const open = Math.max(0, fbm(f * 0.01 + i * 4.1, 8) * 0.9 + 0.25);
            return (
              <path key={i} d={`M 0 -6 L 700 -46 L 700 46 L 0 6 Z`} fill="url(#k-ray)" opacity={open * 0.8}
                transform={`translate(${MX},${MY}) rotate(${a})`} filter="url(#k-blur-m)" />
            );
          })}
        </g>

        {/* moonlight dust drifting down once the light is in */}
        <g opacity={light * 0.9}>
          {MOTES.map((m, i) => {
            const y = (m.y0 + f * m.sp) % 900 + 140;
            const x = m.x + Math.sin(f * 0.02 + m.ph) * 14;
            const fade = Math.min(1, (y - 140) / 80) * Math.min(1, (1000 - y) / 140);
            return <circle key={i} cx={x} cy={y} r={m.r * (1 + 0.5 * e)} fill="#f2f4ff"
              opacity={Math.max(0, fade) * (0.35 + 0.45 * Math.sin(f * 0.07 + m.ph) ** 2)} />;
          })}
        </g>
      </svg>
    </AbsoluteFill>
  );
};

