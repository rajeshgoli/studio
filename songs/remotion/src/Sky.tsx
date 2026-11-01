import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Timeline} from './types';
import {mixColor, rand, ramp} from './lib';

/** Sky colours per motif: [zenith, horizon, glow]. The sky drifts between them as scenes change. */
export const PALETTES: Record<string, [string, string, string]> = {
  kaumudi: ['#05071a', '#141c46', '#8fa3d9'],
  chakora: ['#070a24', '#22285e', '#c9d4f2'],
  mandala: ['#12081f', '#3a1c48', '#e3a6c2'],
  mana: ['#06141d', '#16384a', '#9fd0d8'],
  madana: ['#140405', '#4a120c', '#ff9a52'],
  lotus: ['#1a0c1c', '#6b3346', '#ffd29a'],
  default: ['#07081a', '#1c2048', '#b8c3ea'],
};

const pal = (m: string) => PALETTES[m] ?? PALETTES.default;

export const Sky: React.FC<{tl: Timeline}> = ({tl}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  let idx = tl.scenes.findIndex((s) => t >= s.start && t < s.end);
  if (idx < 0) idx = tl.scenes.length - 1;
  const cur = pal(tl.scenes[idx].motif);
  const next = idx + 1 < tl.scenes.length ? pal(tl.scenes[idx + 1].motif) : cur;
  // blend over the last 1.5 s of a scene
  const k = idx + 1 < tl.scenes.length ? ramp(t, tl.scenes[idx].end - 1.5, tl.scenes[idx].end) : 0;
  const [z, h, g] = cur.map((c, i) => mixColor(c, next[i], k));

  const stars = React.useMemo(
    () =>
      Array.from({length: 140}, (_, i) => ({
        x: rand(i * 3.1) * 1080,
        y: rand(i * 7.7) * 1250,
        r: 0.6 + rand(i * 1.3) * 1.8,
        ph: rand(i * 9.2) * Math.PI * 2,
        sp: 0.5 + rand(i * 4.4) * 1.5,
      })),
    [],
  );
  // stars fade as the poem warms toward fire and dawn
  const starAlpha = ['madana', 'lotus'].includes(tl.scenes[idx].motif) ? 0.25 * (1 - k) : 1 - (['madana', 'lotus'].includes(tl.scenes[Math.min(idx + 1, tl.scenes.length - 1)].motif) ? 0.75 * k : 0);

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: `linear-gradient(180deg, ${z} 0%, ${h} 62%, ${mixColor(h, '#000000', 0.55)} 100%)`}} />
      <AbsoluteFill style={{background: `radial-gradient(ellipse 70% 45% at 50% 38%, ${g}33 0%, transparent 70%)`}} />
      <svg width={1080} height={1920} style={{position: 'absolute', opacity: starAlpha}}>
        {stars.map((s, i) => (
          <circle key={i} cx={s.x} cy={s.y} r={s.r} fill="#fff8e8"
            opacity={0.25 + 0.55 * (0.5 + 0.5 * Math.sin(frame * 0.05 * s.sp + s.ph))} />
        ))}
      </svg>
    </AbsoluteFill>
  );
};
