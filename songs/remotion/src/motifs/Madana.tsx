import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {CREAM, GOLD, fbm, ramp, rand} from '../lib';

const CX = 540;
const BASE_Y = 800; // where the flame sits on the lamp wick

/** A flame tongue as a closed path: teardrop of height h and half-width w, licked sideways by noise. */
const tongue = (h: number, w: number, t: number, seed: number, sway: number, dx = 0, lean = 0) => {
  const N = 22;
  const pts: string[] = [];
  const side = (s: number) => {
    for (let k = 0; k <= N; k++) {
      const u = s > 0 ? k / N : 1 - k / N; // 0 at base, 1 at tip
      const width = w * Math.sin(Math.PI * Math.pow(u, 0.62)) * (1 - 0.15 * u);
      const lick = fbm(u * 2.2 - t * 1.6, seed) * 40 * u * u * sway + Math.sin(t * 2.3 + seed) * 10 * u * u * sway;
      const x = CX + dx + s * width + lick + lean * u * u * h;
      const y = BASE_Y - u * h + (1 - u) * 0;
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
  };
  side(1);
  side(-1);
  return `M${pts.join(' L')} Z`;
};

/** Five-petal blossom (Kama's arrows are tipped with flowers). */
const Blossom: React.FC<{r: number; col: string}> = ({r, col}) => (
  <g>
    {[0, 1, 2, 3, 4].map((k) => (
      <ellipse key={k} cx={0} cy={-r * 0.55} rx={r * 0.34} ry={r * 0.6} fill={col} stroke={GOLD} strokeWidth={0.8} strokeOpacity={0.7}
        transform={`rotate(${k * 72})`} />
    ))}
    <circle r={r * 0.28} fill={GOLD} />
  </g>
);

/** madana-anala: the fire of love, a lamp flame that swells with the voice, sparks, and flower-tipped arrows. */
export const Madana: React.FC<MotifProps> = ({durationInFrames, lines, voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  const l = lines[0];
  const a = l?.from ?? 15;
  const b = l?.to ?? durationInFrames - 15;
  const build = ramp(f, 0, b); // intensity builds through the line
  const t = f / 30;
  const heat = 0.55 + 0.35 * build + 0.25 * e;

  const H = 300 + 170 * build + 90 * e;
  const W = 78 + 26 * build + 14 * e;

  const embers = Array.from({length: 70}, (_, i) => {
    const life = 70 + rand(i * 3.1) * 70;
    const t0 = rand(i * 7.9) * life;
    const age = (f + t0) % life;
    const u = age / life;
    const x0 = CX + (rand(i * 1.3) - 0.5) * (60 + 60 * build);
    const x = x0 + fbm(age * 0.03, i) * 90 * u + (rand(i * 4.1) - 0.5) * 200 * u;
    const y = BASE_Y - 120 - u * (520 + 200 * rand(i * 2.7)) * (0.7 + 0.5 * build);
    const r = (1.2 + rand(i * 6.2) * 2.6) * (1 - u * 0.6);
    const op = Math.sin(Math.PI * u) * (0.5 + 0.5 * heat) * (0.6 + 0.4 * Math.sin(age * 0.5 + i));
    return {x, y, r, op, hot: rand(i * 8.8) > 0.5};
  });

  // arrows: three passes at fixed beats of the line
  const passes = [
    {at: a + (b - a) * 0.12, from: [-140, 330], to: [1220, 520], col: '#ffd0dc'},
    {at: a + (b - a) * 0.5, from: [1220, 260], to: [-140, 470], col: '#fff1c4'},
    {at: a + (b - a) * 0.82, from: [-140, 560], to: [1220, 300], col: '#ffb3c6'},
  ];
  const ARROW_DUR = 34;

  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <radialGradient id="mad-glow" cx={CX} cy={BASE_Y - H * 0.45} r={560} gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#ffb25a" stopOpacity={0.55 * heat} />
            <stop offset="0.35" stopColor="#ff6a2a" stopOpacity={0.22 * heat} />
            <stop offset="1" stopColor="#ff3a10" stopOpacity={0} />
          </radialGradient>
          <linearGradient id="mad-outer" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#ff5a1a" />
            <stop offset="0.6" stopColor="#d8261a" />
            <stop offset="1" stopColor="#7a0f18" stopOpacity={0.7} />
          </linearGradient>
          <linearGradient id="mad-mid" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#ffd06a" />
            <stop offset="0.7" stopColor="#ff8a2a" />
            <stop offset="1" stopColor="#ff5a1a" />
          </linearGradient>
          <linearGradient id="mad-core" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#fffaf0" />
            <stop offset="1" stopColor="#ffe08a" />
          </linearGradient>
          <linearGradient id="mad-lamp" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f3cf7e" />
            <stop offset="0.5" stopColor="#b9792e" />
            <stop offset="1" stopColor="#5a3412" />
          </linearGradient>
          <filter id="mad-blur" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="18" />
          </filter>
          <filter id="mad-blur4" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
          <filter id="mad-heat" x="-30%" y="-30%" width="160%" height="160%">
            <feTurbulence type="fractalNoise" baseFrequency="0.008 0.025" numOctaves={2} seed={Math.floor(f / 3) % 50} result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale={4 + 4 * heat} xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>

        <circle cx={CX} cy={BASE_Y - H * 0.45} r={560} fill="url(#mad-glow)" />

        {/* Pichwai halo behind the flame: concentric rays and rings */}
        <g transform={`translate(${CX},${BASE_Y - 220})`} opacity={0.5 + 0.3 * heat}>
          {Array.from({length: 36}, (_, k) => {
            const ang = (k / 36) * 360 + t * 4;
            const r0 = 250;
            const r1 = 300 + 18 * Math.sin(t * 2 + k) + 30 * e;
            return (
              <line key={k} x1={0} y1={-r0} x2={0} y2={-r1} stroke={GOLD} strokeOpacity={k % 2 ? 0.25 : 0.5} strokeWidth={k % 2 ? 1 : 2}
                transform={`rotate(${ang})`} strokeLinecap="round" />
            );
          })}
          <circle r={240} fill="none" stroke={GOLD} strokeOpacity={0.4} strokeWidth={1.4} />
          <circle r={320 + 30 * e} fill="none" stroke={GOLD} strokeOpacity={0.18} strokeDasharray="3 9" />
        </g>

        {/* the flame, with heat shimmer */}
        <g filter="url(#mad-heat)">
          <path d={tongue(H * 1.08, W * 1.5, t * 0.9, 5, 1.3)} fill="#ff4a14" opacity={0.45} filter="url(#mad-blur)" />
          <path d={tongue(H * 0.55, W * 0.55, t * 1.3 + 11, 7, 1.4, -W * 0.55, -0.22)} fill="url(#mad-outer)" opacity={0.75} />
          <path d={tongue(H * 0.6, W * 0.55, t * 1.25 + 17, 9, 1.4, W * 0.55, 0.2)} fill="url(#mad-outer)" opacity={0.75} />
          <path d={tongue(H, W * 1.15, t, 1, 1.1)} fill="url(#mad-outer)" opacity={0.9} />
          <path d={tongue(H * 0.82, W * 0.82, t * 1.1 + 3, 2, 0.9)} fill="url(#mad-mid)" opacity={0.95} />
          <path d={tongue(H * 0.55, W * 0.5, t * 1.2 + 7, 3, 0.6)} fill="url(#mad-core)" />
          <path d={tongue(H * 0.98, W * 1.15, t, 1, 1.1)} fill="none" stroke={GOLD} strokeWidth={1.5} strokeOpacity={0.6} />
        </g>
        <ellipse cx={CX} cy={BASE_Y - 40} rx={W * 0.5} ry={34} fill="#fffaf0" opacity={0.7} filter="url(#mad-blur4)" />

        {/* the diya */}
        <g transform={`translate(${CX},${BASE_Y + 6})`}>
          <path d="M-190,0 C-170,90 -70,120 0,120 C70,120 170,90 190,0 C120,22 -120,22 -190,0 Z" fill="url(#mad-lamp)" stroke={GOLD} strokeWidth={2} />
          <path d="M190,0 C230,-12 260,-30 272,-52 C240,-30 215,-18 180,-8 Z" fill="url(#mad-lamp)" stroke={GOLD} strokeWidth={1.5} />
          <ellipse cx={0} cy={2} rx={186} ry={18} fill="#3a1608" stroke={GOLD} strokeOpacity={0.8} strokeWidth={1.5} />
          <ellipse cx={0} cy={2} rx={150} ry={12} fill="#ffb24a" opacity={0.25 + 0.2 * heat} />
          {[-120, -60, 0, 60, 120].map((x, k) => (
            <circle key={k} cx={x} cy={62 + Math.abs(x) * -0.12} r={6} fill="none" stroke={GOLD} strokeOpacity={0.7} strokeWidth={1.4} />
          ))}
          <path d="M-150,38 C-80,70 80,70 150,38" fill="none" stroke={GOLD} strokeOpacity={0.6} strokeWidth={1.2} strokeDasharray="2 6" />
          <path d="M-60,120 L-40,150 L40,150 L60,120" fill="url(#mad-lamp)" stroke={GOLD} strokeWidth={1.5} />
        </g>

        {/* embers */}
        {embers.map((m, i) => (
          <circle key={i} cx={m.x} cy={m.y} r={m.r} fill={m.hot ? '#ffe9a8' : '#ff8a3a'} opacity={m.op} />
        ))}

        {/* Kama's flower-tipped arrows */}
        {passes.map((ps, k) => {
          const u = (f - ps.at) / ARROW_DUR;
          if (u < 0 || u > 1.25) return null;
          const uu = Math.min(1, u);
          const at = (q: number) => {
            const e2 = q * q * (3 - 2 * q) * 0.4 + q * 0.6;
            return [ps.from[0] + (ps.to[0] - ps.from[0]) * e2, ps.from[1] + (ps.to[1] - ps.from[1]) * e2 - Math.sin(Math.PI * q) * 40];
          };
          const [x, y] = at(uu);
          // point along the actual direction of travel (the arc included): flower first, fletching last
          const [x2, y2] = at(Math.min(1, uu + 0.01));
          const [x1, y1] = at(Math.max(0, uu - 0.01));
          const ang = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
          const fade = 1 - ramp(u, 0.95, 1.25);
          return (
            <g key={k} opacity={fade}>
              <g transform={`translate(${x},${y}) rotate(${ang}) scale(1.6)`}>
                <line x1={-420} y1={0} x2={-160} y2={0} stroke={CREAM} strokeOpacity={0.12} strokeWidth={10} strokeLinecap="round" filter="url(#mad-blur4)" />
                <line x1={-150} y1={0} x2={0} y2={0} stroke={GOLD} strokeWidth={3} strokeLinecap="round" />
                {/* fletching: soft feather vanes attached at their front ends, sweeping back and out (chevrons point at the flower) */}
                {[-1, 1].map((sd) =>
                  [0, 1, 2].map((v) => {
                    const x0 = -112 - v * 13;
                    const tip = [x0 - 30, sd * (11 + v)];
                    return (
                      <g key={`${sd}${v}`} opacity={0.9 - v * 0.12}>
                        <path d={`M${x0},0 Q${x0 - 10},${sd * 9} ${tip[0]},${tip[1]} Q${x0 - 18},${sd * 3} ${x0 - 6},0 Z`}
                          fill={ps.col} stroke={GOLD} strokeOpacity={0.6} strokeWidth={0.6} />
                        {[0.3, 0.55, 0.8].map((q) => (
                          <path key={q} d={`M${x0 - 6 - q * 16},${sd * q * 2} l${-6},${sd * (3 + q * 5)}`} stroke={GOLD} strokeOpacity={0.45} strokeWidth={0.5} />
                        ))}
                      </g>
                    );
                  }),
                )}
                <g transform={`translate(8,0) rotate(${f * 6})`}>
                  <Blossom r={18} col={ps.col} />
                </g>
              </g>
              {/* a few falling petals in its wake */}
              {[0, 1, 2, 3].map((j) => {
                const ut = Math.max(0, uu - 0.15 - j * 0.12);
                if (ut <= 0) return null;
                const px = ps.from[0] + (ps.to[0] - ps.from[0]) * (ut * 0.9);
                const py = ps.from[1] + (ps.to[1] - ps.from[1]) * (ut * 0.9) + (uu - ut) * 160;
                return <ellipse key={j} cx={px} cy={py} rx={5} ry={9} fill={ps.col} opacity={0.7 * (1 - (uu - ut))}
                  transform={`rotate(${f * 5 + j * 50},${px},${py})`} />;
              })}
            </g>
          );
        })}

      </svg>
    </AbsoluteFill>
  );
};
