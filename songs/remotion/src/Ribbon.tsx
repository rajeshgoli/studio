import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Timeline} from './types';
import {Voice} from './voice';
import {GOLD} from './lib';

const SA_Y = 1010; // where Sa sits
const PX = 5; // pixels per semitone
const WIN = 3.6; // seconds of melody visible
const NOW_X = 860;
const LEFT_X = 120;

/** A thin gold thread drawn by the singer's pitch: the melody itself, scrolling to the left. */
export const Ribbon: React.FC<{tl: Timeline; voice: Voice}> = ({tl, voice}) => {
  const frame = useCurrentFrame();
  const n = Math.round(WIN * tl.fps);
  const segs: string[][] = [];
  let cur: string[] = [];
  for (let k = n; k >= 0; k--) {
    const f = frame - k;
    const p = voice.pitch(f);
    if (p === null) {
      if (cur.length > 1) segs.push(cur);
      cur = [];
      continue;
    }
    const x = NOW_X - (k / n) * (NOW_X - LEFT_X);
    const y = SA_Y - Math.max(-9, Math.min(21, p)) * PX;
    cur.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  if (cur.length > 1) segs.push(cur);
  const live = voice.pitch(frame);
  const e = voice.energy(frame);
  const yNow = live === null ? null : SA_Y - Math.max(-9, Math.min(21, live)) * PX;
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <linearGradient id="rib" x1={LEFT_X} x2={NOW_X} y1={0} y2={0} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor={GOLD} stopOpacity={0} />
            <stop offset="0.6" stopColor={GOLD} stopOpacity={0.55} />
            <stop offset="1" stopColor="#fff3d6" stopOpacity={0.95} />
          </linearGradient>
          <filter id="ribglow" x="-20%" y="-50%" width="140%" height="200%">
            <feGaussianBlur stdDeviation="5" />
          </filter>
        </defs>
        {segs.map((s, i) => (
          <g key={i}>
            <polyline points={s.join(' ')} fill="none" stroke={GOLD} strokeOpacity={0.35} strokeWidth={8} filter="url(#ribglow)" />
            <polyline points={s.join(' ')} fill="none" stroke="url(#rib)" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
          </g>
        ))}
        {yNow !== null && (
          <g>
            <circle cx={NOW_X} cy={yNow} r={10 + 16 * e} fill={GOLD} opacity={0.25} filter="url(#ribglow)" />
            <circle cx={NOW_X} cy={yNow} r={3.5 + 2 * e} fill="#fff6e0" />
          </g>
        )}
      </svg>
    </AbsoluteFill>
  );
};
