import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, fbm, lerp, mixColor, ramp, rand} from '../lib';

const CX = 540;
const BY = 760; // base of the flower

/** Pointed lotus petal from (0,0) to (0,-len). */
const petal = (len: number, w: number) =>
  `M0,0 C${w},${-len * 0.3} ${w * 0.66},${-len * 0.8} 0,${-len} C${-w * 0.66},${-len * 0.8} ${-w},${-len * 0.3} 0,0 Z`;

type Layer = {n: number; len: number; w: number; spread: number; closed: number; deep: string; light: string; stagger: number};

// back to front; spread = final half-angle of the fan (deg)
const LAYERS: Layer[] = [
  {n: 9, len: 300, w: 92, spread: 84, closed: 14, deep: '#b84d78', light: '#f3b7c9', stagger: 0},
  {n: 7, len: 290, w: 96, spread: 62, closed: 10, deep: '#d0618a', light: '#ffd0dc', stagger: 0.25},
  {n: 5, len: 260, w: 90, spread: 38, closed: 6, deep: '#e27a9c', light: '#fff0f2', stagger: 0.5},
];

/** dehi mukha-kamala-madhu-pānam: a lotus opens at dawn and a bee comes to drink. */
export const Lotus: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const l = lines[0];
  const a = l?.from ?? 20;
  const b = l?.to ?? Math.min(durationInFrames - 30, a + 150);
  const len = Math.max(40, b - a);
  const dawn = ramp(f, 0, durationInFrames);
  const land = b + 6; // bee settles just after the line ends

  const petalOpen = (layer: number, i: number, n: number) => {
    const order = Math.abs(i - (n - 1) / 2) / ((n - 1) / 2 || 1); // outermost open first
    const s = a + len * (LAYERS[layer].stagger + 0.2 * (1 - order) + 0.08 * rand(layer * 11 + i));
    return ramp(f, s, s + len * 0.7);
  };
  const heartOpen = ramp(f, a + len * 0.4, a + len * 1.0);
  const sway = Math.sin(f * 0.035) * 1.2;

  // bee path: loops around the flower, then spirals into the heart
  const bee = (() => {
    const flyT = f / 30;
    const loopX = CX + 300 * Math.sin(flyT * 0.9) + 40 * Math.sin(flyT * 2.3);
    const loopY = 470 + 130 * Math.sin(flyT * 1.8) + 30 * fbm(flyT * 0.6, 3);
    const heartX = CX + 2 * Math.sin(f * 0.05);
    const heartY = BY - 175 + 2 * Math.sin(f * 0.07);
    const k = ramp(f, land - 70, land);
    // spiral in: shrink loop radius as k grows
    const x = lerp(loopX, heartX, k) + (1 - k) * 0;
    const y = lerp(loopY, heartY, k);
    const nx = CX + 300 * Math.sin((flyT + 0.05) * 0.9) + 40 * Math.sin((flyT + 0.05) * 2.3);
    const ny = 470 + 130 * Math.sin((flyT + 0.05) * 1.8) + 30 * fbm((flyT + 0.05) * 0.6, 3);
    const dir = Math.atan2(lerp(ny, heartY, k) - y, lerp(nx, heartX, k) - x);
    const tilt = (1 - k) * ((dir * 180) / Math.PI) * 0.25;
    const facing = (1 - k) * (nx > loopX ? 1 : -1) + k * 1;
    const settled = f >= land;
    const flap = settled ? (Math.sin(f * 0.15) > 0.92 ? Math.sin(f * 2.4) : 0.2) : Math.sin(f * 2.6);
    return {x, y, tilt, facing: facing >= 0 ? 1 : -1, flap, scale: lerp(1.6, 1.25, k)};
  })();

  const pollen = Array.from({length: 46}, (_, i) => {
    const sp = 0.25 + rand(i * 2.3) * 0.5;
    const r0 = 120 + rand(i * 5.1) * 300;
    const ang = rand(i * 7.7) * Math.PI * 2 + f * 0.004 * (rand(i) > 0.5 ? 1 : -1);
    const y = BY - 160 - ((f * sp + rand(i * 3.9) * 600) % 600);
    const x = CX + Math.cos(ang) * r0 * 0.9 + 20 * Math.sin(f * 0.03 + i);
    return {x, y, r: 1 + rand(i * 9.1) * 2.4, op: (0.3 + 0.6 * heartOpen) * (0.4 + 0.6 * Math.abs(Math.sin(f * 0.05 + i)))};
  });

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="lot-sun" cx={CX} cy={BY - 190} r={560} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#fff1c8" stopOpacity={0.55 + 0.2 * dawn + 0.1 * e} />
            <stop offset="0.3" stopColor="#ffc98a" stopOpacity={0.28} />
            <stop offset="1" stopColor="#ff9a7a" stopOpacity={0} />
          </radialGradient>
          {LAYERS.map((L, k) => (
            <linearGradient key={k} id={`lot-p${k}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={L.light} />
              <stop offset="0.75" stopColor={L.deep} />
              <stop offset="1" stopColor={mixColor(L.deep, '#5a1a3a', 0.4)} />
            </linearGradient>
          ))}
          <radialGradient id="lot-heart" cx="0.5" cy="0.4" r="0.6">
            <stop offset="0" stopColor="#fff6c8" />
            <stop offset="0.6" stopColor="#f2c24e" />
            <stop offset="1" stopColor="#b8802a" />
          </radialGradient>
          <filter id="lot-blur" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="20" />
          </filter>
          <filter id="lot-blur3" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>

        <circle cx={CX} cy={BY - 190} r={560} fill="url(#lot-sun)" />
        {/* sun disc rays, Pichwai style */}
        <g transform={`translate(${CX},${BY - 190})`} opacity={0.35 + 0.25 * dawn}>
          <circle r={330 + 6 * Math.sin(f * 0.04)} fill="none" stroke={GOLD} strokeOpacity={0.45} strokeWidth={1.5} />
          <circle r={352} fill="none" stroke={GOLD} strokeOpacity={0.25} strokeDasharray="2 8" />
          {Array.from({length: 48}, (_, k) => (
            <line key={k} x1={0} y1={-360} x2={0} y2={-(380 + (k % 2 ? 0 : 18) + 8 * Math.sin(f * 0.05 + k))} stroke={GOLD}
              strokeOpacity={0.35} strokeWidth={1.2} transform={`rotate(${k * 7.5 + f * 0.08})`} />
          ))}
        </g>

        {/* water and pads */}
        <g>
          {[0, 1, 2].map((k) => {
            const rr = ((f * 0.6 + k * 50) % 150) / 150;
            return <ellipse key={k} cx={CX} cy={BY + 40} rx={200 + rr * 300} ry={26 + rr * 36} fill="none" stroke={CREAM}
              strokeOpacity={0.22 * (1 - rr)} strokeWidth={1.2} />;
          })}
          {[[-290, 70, 120, 1], [300, 60, 110, -1], [-120, 130, 90, 1], [180, 140, 80, -1]].map(([dx, dy, r, s], k) => (
            <g key={k} transform={`translate(${CX + dx + 4 * Math.sin(f * 0.02 + k)},${BY + dy}) scale(1,0.28)`}>
              <circle r={r} fill={mixColor('#2f5a3a', '#4f7a3e', dawn)} opacity={0.85} />
              <path d={`M0,0 L${r * s},${-r * 0.15} A${r},${r} 0 0 ${s > 0 ? 0 : 1} ${r * 0.9 * s},${-r * 0.45} Z`} fill="#1c3a28" opacity={0.9} />
              <circle r={r} fill="none" stroke={GOLD} strokeOpacity={0.4} strokeWidth={3} />
              {[0, 60, 120, 180, 240, 300].map((ang) => (
                <line key={ang} x1={0} y1={0} x2={r * 0.85 * Math.cos((ang * Math.PI) / 180)} y2={r * 0.85 * Math.sin((ang * Math.PI) / 180)}
                  stroke={GOLD} strokeOpacity={0.2} strokeWidth={2} />
              ))}
            </g>
          ))}
        </g>

        {/* the flower */}
        <g transform={`rotate(${sway},${CX},${BY + 40})`}>
          <ellipse cx={CX} cy={BY - 150} rx={200} ry={160} fill="#ffd9a0" opacity={0.25 * heartOpen + 0.08 * e} filter="url(#lot-blur)" />
          {/* sepals */}
          {[-1, 1].map((s) => (
            <path key={s} d={petal(120, 50)} fill="#4f7a3e" stroke={GOLD} strokeOpacity={0.4}
              transform={`translate(${CX},${BY + 20}) rotate(${s * (60 + 20 * ramp(f, a, b))})`} />
          ))}
          {LAYERS.map((L, k) => (
            <g key={k}>
              {Array.from({length: L.n}, (_, i) => {
                const u = L.n === 1 ? 0 : i / (L.n - 1) - 0.5; // -0.5..0.5
                const o = petalOpen(k, i, L.n);
                const ang = u * 2 * lerp(L.closed, L.spread, o) + Math.sin(f * 0.05 + i + k) * 0.8 * o;
                const breathe = 1 + 0.012 * Math.sin(f * 0.06 + i) + 0.015 * e;
                const lenK = L.len * (0.92 + 0.08 * o) * breathe;
                const wK = L.w * (0.75 + 0.25 * o);
                return (
                  <g key={i} transform={`translate(${CX},${BY}) rotate(${ang})`}>
                    <path d={petal(lenK, wK)} fill={`url(#lot-p${k})`} stroke={GOLD} strokeWidth={1.3} strokeOpacity={0.55} />
                    {[-0.35, 0, 0.35].map((v, j) => (
                      <path key={j} d={`M${v * 8},-6 Q${v * wK * 0.9},${-lenK * 0.5} ${v * 6},${-lenK * 0.93}`} fill="none"
                        stroke="#fff6f2" strokeOpacity={0.35} strokeWidth={1} />
                    ))}
                  </g>
                );
              })}
              {/* the golden heart sits between the middle and front layers */}
              {k === 1 && (
                <g transform={`translate(${CX},${BY - 150})`} opacity={heartOpen}>
                  <circle r={60 + 30 * e} fill={GOLD} opacity={0.35} filter="url(#lot-blur3)" />
                  {Array.from({length: 26}, (_, s) => {
                    const ang = (s / 26) * Math.PI * 2;
                    const r1 = 52 + 6 * Math.sin(f * 0.1 + s);
                    return <line key={s} x1={Math.cos(ang) * 30} y1={Math.sin(ang) * 16} x2={Math.cos(ang) * r1} y2={Math.sin(ang) * r1 * 0.55 - 8}
                      stroke="#ffe08a" strokeWidth={2} strokeLinecap="round" />;
                  })}
                  <ellipse rx={38} ry={22} fill="url(#lot-heart)" stroke="#a87020" strokeWidth={1} />
                  {[[-14, -4], [0, -8], [14, -4], [-7, 5], [7, 5]].map(([x, y], s) => (
                    <circle key={s} cx={x} cy={y} r={3.2} fill="#8a5a18" opacity={0.7} />
                  ))}
                </g>
              )}
            </g>
          ))}
          {/* stem below */}
          <path d={`M${CX},${BY + 20} C${CX + 6},${BY + 60} ${CX - 4},${BY + 90} ${CX},${BY + 120}`} stroke="#3f6a3a" strokeWidth={10} fill="none" />
        </g>

        {/* honey glow from the heart once the bee arrives */}
        <circle cx={CX} cy={BY - 150} r={90 + 20 * Math.sin(f * 0.08)} fill="#ffcf5a" opacity={0.25 * ramp(f, land, land + 30)} filter="url(#lot-blur)" />

        {/* pollen */}
        {pollen.map((m, i) => (
          <circle key={i} cx={m.x} cy={m.y} r={m.r} fill="#ffe6a0" opacity={m.op} />
        ))}

        {/* bhramara: the bee */}
        <g transform={`translate(${bee.x},${bee.y}) rotate(${bee.tilt}) scale(${bee.facing * bee.scale},${bee.scale})`}>
          <path d={`M-90,0 Q-60,${-6 + 4 * Math.sin(f * 0.3)} -30,0`} stroke={GOLD} strokeOpacity={f < land ? 0.25 : 0} strokeWidth={2} fill="none" strokeDasharray="2 6" />
          {[-1, 1].map((s) => (
            <ellipse key={s} cx={-4} cy={-18} rx={13} ry={24} fill="#fff8ea" fillOpacity={0.45} stroke={CREAM} strokeOpacity={0.8} strokeWidth={1}
              transform={`rotate(${-25 * s + bee.flap * 30 * s - 10},-4,-4) scale(1,${0.6 + 0.4 * Math.abs(bee.flap)})`} />
          ))}
          <ellipse cx={0} cy={0} rx={24} ry={14} fill="#1e140c" stroke={GOLD} strokeWidth={1.4} />
          {[-10, 0, 10].map((x, s) => (
            <path key={s} d={`M${x},-13 Q${x + 4},0 ${x},13`} stroke={GOLD} strokeWidth={4} fill="none" />
          ))}
          <circle cx={26} cy={-2} r={9} fill="#1e140c" stroke={GOLD} strokeWidth={1.2} />
          <path d="M31,-9 Q38,-20 44,-22 M28,-10 Q32,-22 36,-26" stroke={GOLD} strokeWidth={1.2} fill="none" />
          <circle cx={29} cy={-4} r={1.6} fill={CREAM} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};
