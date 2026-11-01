import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, fbm, mixColor, ramp, rand} from '../lib';

const CX = 540;
const CY = 610; // bud centre
const RING = 250;
const N_SHARDS = 22;

/** Pointed lotus petal rising from (0,0) to (0,-len). */
const petal = (len: number, w: number) =>
  `M0,0 C${w},${-len * 0.32} ${w * 0.62},${-len * 0.82} 0,${-len} C${-w * 0.62},${-len * 0.82} ${-w},${-len * 0.32} 0,0 Z`;

/** Long faceted ice shard pointing toward +y from its root. */
const shard = (len: number, w: number) => `M0,0 L${w},${len * 0.18} L${w * 0.08},${len} L${-w * 0.4},${len * 0.5} L${-w},${len * 0.14} Z`;

/** māna: a closed bud fenced in by ice-thorns that crack, melt and drift off as petals. */
export const Mana: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const l = lines[0];
  const a = l?.from ?? 15;
  const b = l?.to ?? durationInFrames - 15;
  const len = Math.max(30, b - a);
  const p = ramp(f, a, b + len * 0.15); // story progress across the line
  const crack = ramp(f, a + len * 0.05, a + len * 0.35);
  const warm = ramp(f, a + len * 0.3, durationInFrames);
  const open = ramp(f, a + len * 0.45, durationInFrames + 20);

  const iceA = mixColor('#bfeaf0', '#f2d6cf', warm);
  const glow = mixColor('#7fd3dc', '#ffb7a0', warm);
  const budDeep = mixColor('#6f8fa8', '#d9708e', warm);
  const budLight = mixColor('#c7dbe6', '#ffd3dc', warm);

  const breathe = 1 + 0.015 * Math.sin(f * 0.07) + 0.02 * e;

  const shards = Array.from({length: N_SHARDS}, (_, i) => {
    const ang = (i / N_SHARDS) * Math.PI * 2 + 0.12 * Math.sin(i * 2.3);
    const L = 130 + 70 * rand(i * 3.7);
    const W = 9 + 7 * rand(i * 5.1);
    // each shard lets go at its own moment in the second half of the line
    const t0 = a + len * (0.3 + 0.55 * rand(i * 9.13));
    const melt = ramp(f, t0, t0 + 22);
    const drift = Math.max(0, f - t0 - 14);
    return {i, ang, L, W, melt, drift, t0};
  });

  const frost = Array.from({length: 70}, (_, i) => {
    const sp = 0.3 + rand(i * 2.1) * 0.6;
    const y = 980 - ((f * sp + rand(i * 7.3) * 900) % 900);
    const x = 140 + rand(i * 4.9) * 800 + 30 * Math.sin(f * 0.02 + i);
    return {x, y, r: 0.8 + rand(i * 1.9) * 2, tw: 0.4 + 0.6 * Math.abs(Math.sin(f * 0.06 + i * 1.7))};
  });

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="mana-glow" cx={CX} cy={CY} r={460} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor={glow} stopOpacity={0.42 + 0.15 * e} />
            <stop offset="0.45" stopColor={glow} stopOpacity={0.12} />
            <stop offset="1" stopColor={glow} stopOpacity={0} />
          </radialGradient>
          <linearGradient id="mana-bud" x1="0" y1="0" x2="0" y2="-1" gradientUnits="objectBoundingBox">
            <stop offset="0" stopColor={budDeep} />
            <stop offset="1" stopColor={budLight} />
          </linearGradient>
          <linearGradient id="mana-bud2" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor={budDeep} />
            <stop offset="0.85" stopColor={budLight} />
          </linearGradient>
          <linearGradient id="mana-ice" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#ffffff" stopOpacity={0.9} />
            <stop offset="0.5" stopColor={iceA} stopOpacity={0.55} />
            <stop offset="1" stopColor="#3f8fa0" stopOpacity={0.35} />
          </linearGradient>
          <radialGradient id="mana-mist" cx={CX} cy={CY + 40} r={480} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#bfe8ee" stopOpacity={0.14} />
            <stop offset="1" stopColor="#bfe8ee" stopOpacity={0} />
          </radialGradient>
          <filter id="mana-soft" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="14" />
          </filter>
          <filter id="mana-blur3" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>

        <circle cx={CX} cy={CY} r={460} fill="url(#mana-glow)" />

        {/* gold halo rings, Pichwai style */}
        {[300, 330].map((r, k) => (
          <circle key={k} cx={CX} cy={CY} r={r * breathe} fill="none" stroke={GOLD}
            strokeOpacity={(0.12 + 0.25 * warm) * (k ? 0.6 : 1)} strokeWidth={k ? 1 : 1.6}
            strokeDasharray={k ? '2 10' : undefined} />
        ))}

        {/* stem and pad */}
        <path d={`M${CX},${CY + 60} C${CX + 18},${CY + 200} ${CX - 22},${CY + 300} ${CX + 6},${980}`} stroke={mixColor('#3f6f6a', '#5f8a55', warm)}
          strokeWidth={9} fill="none" strokeLinecap="round" />
        <g transform={`translate(${CX + 6},${975})`}>
          <ellipse rx={150} ry={22} fill={mixColor('#1f4a4c', '#3c6a45', warm)} opacity={0.8} />
          <ellipse rx={150} ry={22} fill="none" stroke={GOLD} strokeOpacity={0.35} strokeWidth={1.2} />
          <path d="M0,0 L-150,-4" stroke={GOLD} strokeOpacity={0.25} />
          {[0, 1, 2].map((k) => {
            const rr = ((f * 0.8 + k * 40) % 120) / 120;
            return <ellipse key={k} rx={150 + rr * 120} ry={22 + rr * 14} fill="none" stroke={CREAM} strokeOpacity={0.18 * (1 - rr)} />;
          })}
        </g>

        {/* the bud */}
        <g transform={`translate(${CX},${CY + 95}) scale(${1.3 * breathe})`}>
          <ellipse cx={0} cy={-90} rx={70} ry={100} fill={glow} opacity={0.25 + 0.2 * open} filter="url(#mana-soft)" />
          {[-1, 1].map((s) => (
            <path key={`b${s}`} d={petal(175, 62)} fill="url(#mana-bud2)" opacity={0.85}
              transform={`rotate(${s * (10 + 22 * open + 2 * Math.sin(f * 0.05))})`} stroke={GOLD} strokeOpacity={0.35} strokeWidth={1.2} />
          ))}
          {[-1, 1].map((s) => (
            <path key={`m${s}`} d={petal(185, 55)} fill="url(#mana-bud2)"
              transform={`rotate(${s * (4 + 12 * open)})`} stroke={GOLD} strokeOpacity={0.5} strokeWidth={1.3} />
          ))}
          <path d={petal(195, 50)} fill="url(#mana-bud2)" stroke={GOLD} strokeOpacity={0.6} strokeWidth={1.4} />
          {/* veins */}
          {[-0.5, 0, 0.5].map((v, k) => (
            <path key={k} d={`M${v * 6},-10 Q${v * 30},-100 ${v * 8},-185`} fill="none" stroke={CREAM} strokeOpacity={0.3} strokeWidth={1} />
          ))}
          {/* a golden glint inside as the tips part */}
          <ellipse cx={0} cy={-150} rx={10 + 14 * open} ry={18 + 10 * open} fill={GOLD} opacity={0.5 * open} filter="url(#mana-blur3)" />
          {/* sepals */}
          {[-1, 1].map((s) => (
            <path key={`s${s}`} d={petal(70, 34)} fill={mixColor('#2f5f5a', '#4f7a48', warm)} transform={`rotate(${s * 48})`} opacity={0.9} />
          ))}
        </g>

        {/* the ring of ice-thorns */}
        {shards.map((s) => {
          const rot = Math.sin(f * 0.03 + s.i) * 2 + 4 * (f / durationInFrames);
          const angDeg = (s.ang * 180) / Math.PI + rot;
          const r = RING + 10 * Math.sin(f * 0.04 + s.i * 1.3) - 18 * crack * (1 - s.melt);
          const x = CX + Math.cos((angDeg * Math.PI) / 180) * r;
          const y = CY + Math.sin((angDeg * Math.PI) / 180) * r;
          const tremble = crack * (1 - s.melt) * 2.5 * Math.sin(f * 1.7 + s.i);
          const shardScale = 1 - 0.85 * s.melt;
          // pointing inward at the bud
          const pointDeg = angDeg + 90;
          return (
            <g key={s.i}>
              {s.melt < 1 && (
                <g transform={`translate(${x + tremble},${y}) rotate(${pointDeg}) scale(${shardScale},${1 - 0.5 * s.melt})`}
                  opacity={1 - s.melt * 0.6}>
                  <path d={shard(s.L, s.W)} fill="url(#mana-ice)" stroke="#e8fbff" strokeOpacity={0.8} strokeWidth={1.4} strokeLinejoin="round" />
                  <path d={`M0,0 L${s.W * 0.25},${s.L}`} stroke="#ffffff" strokeOpacity={0.5} strokeWidth={1} />
                  {crack > 0 && (
                    <path d={`M${-s.W * 0.6},${s.L * 0.3} L${s.W * 0.1},${s.L * 0.42} L${-s.W * 0.1},${s.L * 0.55} L${s.W * 0.5},${s.L * 0.66}`}
                      fill="none" stroke="#ffffff" strokeWidth={1.3} strokeOpacity={crack * 0.9}
                      strokeDasharray={`${crack * 80} 200`} />
                  )}
                </g>
              )}
              {/* a drop as it melts, then a petal drifting off */}
              {s.melt > 0.2 && (() => {
                const dropY = y + Math.min(40, s.drift * 2.2);
                const d = s.drift;
                const k = ramp(d, 6, 26);
                const outward = d * (1.4 + rand(s.i * 1.7));
                const px = x + Math.cos(s.ang) * outward + 30 * fbm(d * 0.03, s.i) * k;
                const py = dropY - d * (0.5 + 0.6 * rand(s.i * 3.3)) * k + 12 * Math.sin(d * 0.08 + s.i);
                const fade = 1 - ramp(d, 70, 130);
                const petalCol = mixColor('#ffd9e0', '#f6b0c0', rand(s.i));
                return (
                  <g opacity={fade}>
                    <ellipse cx={x} cy={dropY} rx={4 * (1 - k)} ry={6 * (1 - k)} fill="#e8fbff" opacity={0.85} />
                    <g transform={`translate(${px},${py}) rotate(${d * (2 + 3 * rand(s.i * 5.5)) + s.i * 40}) scale(${k})`}>
                      <path d={petal(30, 13)} fill={petalCol} opacity={0.9} stroke={GOLD} strokeOpacity={0.4} strokeWidth={0.8} />
                    </g>
                  </g>
                );
              })()}
            </g>
          );
        })}

        {/* frost motes, warming to pollen */}
        {frost.map((m, i) => (
          <circle key={i} cx={m.x} cy={m.y} r={m.r} fill={mixColor('#dffaff', '#ffe2b0', warm)} opacity={m.tw * (m.y > 1000 ? 0.3 : 0.75)} />
        ))}

        {/* faint cold mist at the start */}
        <circle cx={CX} cy={CY + 40} r={480} fill="url(#mana-mist)" opacity={1 - p} />
      </svg>
    </AbsoluteFill>
  );
};
