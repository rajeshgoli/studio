import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {CharProps, armOf, blinkAt, gazeOf, idle} from './pose';
import {Eye, Glint, Hand, Pt, alongQuad, armJoints, limb} from './parts';
import {rand} from '../lib';

// Kangra palette
const SKIN = '#4a6fb8';
const SKIN_HI = '#7a9be0';
const SKIN_LO = '#2c4a8c';
const LINE = '#16234a';
const HAIR = '#0d0b14';
const GOLD = '#e2ae48';
const GOLD_HI = '#ffe6a6';
const GOLD_LO = '#9a6a22';
const PITA = '#f4c430';
const PITA_LO = '#d08d12';
const LIP = '#6e2346';

export const FIG_W = 460;
export const FIG_H = 600;
const HEAD: Pt = [292, 196]; // head-local origin in figure coords
const NECK_PIVOT: Pt = [0, 90]; // head rotates about this (head-local)
const HEAD_SCALE = 1.25;

/** Profile head outline, facing +x. */
const HEAD_PATH = `M36,-60 C46,-52 52,-36 54,-22 C56,-14 60,-4 66,8 L76,22 C80,27 78,31 72,32 C69,33 67,33 65,34
  C66,37 69,39 68,41 C66,43 63,44 62,45 C64,47 67,49 65,52 C63,55 60,56 59,58 C61,62 62,67 58,72
  C52,79 38,80 26,76 L28,110 L-30,112 L-34,60 C-60,40 -66,0 -60,-30 C-50,-66 0,-80 36,-60 Z`;
/** The same outline without the neck's bottom edge, for the ink line. */
const HEAD_INK = `M36,-60 C46,-52 52,-36 54,-22 C56,-14 60,-4 66,8 L76,22 C80,27 78,31 72,32 C69,33 67,33 65,34
  C66,37 69,39 68,41 C66,43 63,44 62,45 C64,47 67,49 65,52 C63,55 60,56 59,58 C61,62 62,67 58,72
  C52,79 38,80 26,76 L28,110`;

const Feather: React.FC<{sway: number; id: string}> = ({sway, id}) => {
  const barbs = Array.from({length: 22}, (_, i) => i / 21);
  return (
    <g transform={`rotate(${-18 + sway * 3})`}>
      <defs>
        <linearGradient id={`${id}-vane`} x1="0" y1="0" x2="0" y2="-170" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#2f6b4a" />
          <stop offset="0.7" stopColor="#3f8f6a" />
          <stop offset="1" stopColor="#8fbf5a" />
        </linearGradient>
      </defs>
      {/* vane: fine barbs either side of the shaft */}
      {barbs.map((t, i) => {
        const y = -20 - t * 140;
        const w = 4 + 16 * Math.sin(Math.PI * Math.min(1, t * 1.15));
        return <path key={i} d={`M0,${y} Q${-w * 0.8},${y - 6} ${-w},${y - 14} M0,${y} Q${w * 0.8},${y - 6} ${w},${y - 14}`}
          stroke={`url(#${id}-vane)`} strokeWidth={1.4} fill="none" opacity={0.9} />;
      })}
      <path d="M0,0 L0,-170" stroke={GOLD} strokeWidth={1.6} />
      {/* the eye */}
      <g transform="translate(0,-168)">
        <ellipse rx={19} ry={27} fill="#7aa848" opacity={0.85} />
        <ellipse rx={15} ry={22} fill="#b7863a" />
        <ellipse rx={12.5} ry={18} fill="#1f8a86" />
        <ellipse cy={2} rx={8.5} ry={12} fill="#2456b8" />
        <ellipse cy={4} rx={5} ry={7} fill="#0d1840" />
        <ellipse rx={19} ry={27} fill="none" stroke={GOLD} strokeWidth={0.8} strokeOpacity={0.7} />
      </g>
    </g>
  );
};

const Crown: React.FC<{id: string; glint: number}> = ({id, glint}) => (
  <g>
    <defs>
      <linearGradient id={`${id}-gold`} x1="-40" y1="-160" x2="40" y2="-50" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor={GOLD_HI} />
        <stop offset="0.45" stopColor={GOLD} />
        <stop offset="1" stopColor={GOLD_LO} />
      </linearGradient>
    </defs>
    {/* crown: a jewelled cap with a scalloped crest sweeping back, lotus-bud finial */}
    <path d="M-46,-46 C-50,-70 -42,-92 -26,-104 C-12,-114 6,-114 18,-104 C30,-94 38,-78 40,-58 Z" fill={`url(#${id}-gold)`} stroke={GOLD_LO} strokeWidth={1.2} />
    {[-40, -30, -18, -5, 8, 20, 31].map((x, i) => {
      const y = -66 - Math.sin(((i + 0.5) / 7) * Math.PI) * 40;
      return <path key={i} d={`M${x - 6},${y + 8} Q${x},${y - 12} ${x + 6},${y + 8}`} fill={GOLD_HI} stroke={GOLD_LO} strokeWidth={0.9} />;
    })}
    <path d="M-8,-114 C-14,-126 -10,-136 -4,-142 C2,-134 4,-124 -2,-114 Z" fill={GOLD_HI} stroke={GOLD_LO} strokeWidth={1} />
    <path d="M-42,-70 C-16,-86 14,-86 36,-70" fill="none" stroke={GOLD_LO} strokeWidth={1.3} />
    <path d="M-40,-62 C-16,-77 14,-77 36,-62" fill="none" stroke={GOLD_HI} strokeWidth={0.8} strokeDasharray="2 3" />
    <circle cx={-4} cy={-86} r={5.5} fill="#c41e3a" stroke={GOLD_HI} strokeWidth={1.2} />
    <circle cx={-22} cy={-84} r={3.2} fill="#1f8a5a" stroke={GOLD_HI} strokeWidth={0.8} />
    <circle cx={16} cy={-82} r={3.2} fill="#1f8a5a" stroke={GOLD_HI} strokeWidth={0.8} />
    {/* base band with pearls */}
    <path d="M-46,-48 C-20,-68 18,-70 40,-60 L39,-50 C18,-60 -18,-58 -44,-38 Z" fill={GOLD} stroke={GOLD_LO} strokeWidth={1} />
    {Array.from({length: 11}, (_, i) => {
      const t = i / 10;
      return <circle key={i} cx={-44 + t * 82} cy={-46 - Math.sin(t * Math.PI) * 9 - t * 6} r={2.2} fill="#fdf6e6" />;
    })}
    <Glint x={-20 + glint * 50} y={-74 - glint * 22} s={1.2} o={Math.sin(glint * Math.PI)} />
  </g>
);

export const Krishna: React.FC<CharProps> = ({facing = 'right', headTilt = 0, gaze, arm, smile = 0, garland = 0, seed = 1, id, layer = 'all'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = gazeOf(gaze);
  const a = armOf(arm);
  const {breath, sway, sway2, t} = idle(frame, fps, seed);
  const blink = blinkAt(frame, fps, seed);
  const glintPhase = ((t + seed) % 7) / 1.6; // a glint travels across the gold every 7 s
  const glint = glintPhase < 1 ? glintPhase : -1;

  const rise = breath * 1.6;
  const tilt = headTilt + sway * 1.2;
  const S: Pt = [214, 350 + rise * 0.5];
  const {E, W, fa, handAngle} = armJoints(S, a, 128, 118);

  // the garland: two strands from the neck meeting low on the chest
  const gSway = sway2 * 4;
  const left = alongQuad([262, 300], [238 + gSway, 470], [334 + gSway, 548], 22);
  const right = alongQuad([334, 324], [398 + gSway, 460], [334 + gSway, 548], 22);
  const flowers = [...left, ...right];

  const body = (
    <g>
      <defs>
        <radialGradient id={`${id}-chest`} cx="330" cy="400" r="220" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={SKIN_HI} />
          <stop offset="0.55" stopColor={SKIN} />
          <stop offset="1" stopColor={SKIN_LO} />
        </radialGradient>
        <radialGradient id={`${id}-face`} cx="40" cy="10" r="90" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={SKIN_HI} />
          <stop offset="0.6" stopColor={SKIN} />
          <stop offset="1" stopColor={SKIN_LO} />
        </radialGradient>
        <linearGradient id={`${id}-pita`} x1="0" y1="300" x2="0" y2="600" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={PITA} />
          <stop offset="1" stopColor={PITA_LO} />
        </linearGradient>
      </defs>

      {/* pitambara scarf falling behind the shoulder */}
      <path d={`M250,300 C214,312 176,330 162,362 C146,410 ${132 + sway * 6},500 ${122 + sway * 10},600 L176,600 C172,520 176,440 190,392 C204,356 236,330 268,318 Z`}
        fill={`url(#${id}-pita)`} stroke={PITA_LO} strokeWidth={1} />
      <path d={`M${126 + sway * 9},590 C${140 + sway * 6},500 150,420 170,372`} fill="none" stroke="#c0392b" strokeWidth={3} opacity={0.8} />

      {/* torso */}
      <g transform={`translate(0,${-rise}) scale(1,${1 + breath * 0.004})`} style={{transformOrigin: '280px 600px'}}>
        <path d={`M300,250 L326,318 C346,330 370,342 384,364 C398,388 398,424 388,452 C380,480 372,520 372,600
          L190,600 C182,540 176,470 176,420 C174,380 178,350 196,330 C214,314 240,304 258,266 Z`}
          fill={`url(#${id}-chest)`} stroke={LINE} strokeWidth={1.3} />
        <path d="M330,372 C350,392 372,402 392,400" fill="none" stroke={LINE} strokeWidth={0.9} strokeOpacity={0.5} />
        <path d="M362,520 q3,4 0,8" fill="none" stroke={LINE} strokeWidth={1} strokeOpacity={0.6} />
        {/* waist: yellow dhoti with an orange sash */}
        <path d="M178,548 C240,560 320,560 376,548 L376,600 L182,600 Z" fill={`url(#${id}-pita)`} stroke={PITA_LO} strokeWidth={1} />
        <path d="M178,548 C240,560 320,560 376,548 L376,562 C320,574 240,574 178,562 Z" fill="#d9533a" />
        {/* gold collar and pearl strands */}
        <path d="M262,300 C276,334 312,342 330,322" fill="none" stroke={GOLD} strokeWidth={6} strokeLinecap="round" />
        <path d="M262,300 C276,334 312,342 330,322" fill="none" stroke={GOLD_HI} strokeWidth={1.4} strokeDasharray="3 5" />
        <circle cx={300} cy={338} r={5} fill="#c41e3a" stroke={GOLD} strokeWidth={2} />
        {alongQuad([268, 312], [300, 410], [370, 356], 26).map(([x, y], i) => <circle key={`p${i}`} cx={x} cy={y} r={2.3} fill="#fbf3e2" opacity={0.95} />)}
        {alongQuad([264, 316], [292, 450], [384, 380], 30).map(([x, y], i) => <circle key={`q${i}`} cx={x} cy={y} r={2.1} fill="#fbf3e2" opacity={0.9} />)}
        {/* vanamala: jasmine, red blossoms and leaves */}
        <g>
          {flowers.map(([x, y], i) => {
            const r = rand(i * 5.1 + seed);
            return (
              <g key={`f${i}`} transform={`translate(${x},${y}) rotate(${r * 360})`}>
                <ellipse rx={7} ry={3} transform="rotate(35) translate(7,0)" fill="#3f8a3a" />
                {i % 3 === 0 ? (
                  <circle r={5.5} fill="#cf2d45" stroke="#8a1328" strokeWidth={0.8} />
                ) : (
                  [0, 72, 144, 216, 288].map((d) => <ellipse key={d} rx={2.6} ry={5} transform={`rotate(${d}) translate(0,-4)`} fill="#fdf8ee" stroke="#d8cdb6" strokeWidth={0.4} />)
                )}
                <circle r={1.6} fill="#f2c94c" />
              </g>
            );
          })}
        </g>
      </g>
    </g>
  );

  const head = (
    <g transform={`translate(${HEAD[0]},${HEAD[1] - rise}) rotate(${-tilt},${NECK_PIVOT[0]},${NECK_PIVOT[1]}) translate(${NECK_PIVOT[0]},${NECK_PIVOT[1]}) scale(${HEAD_SCALE}) translate(${-NECK_PIVOT[0]},${-NECK_PIVOT[1]})`}>
      {/* peacock feather behind the crown */}
      <g transform="translate(-30,-96)">
        <Feather sway={sway2} id={id} />
      </g>
      {/* fine locks falling behind to the shoulder */}
      {[0, 1, 2].map((k) => (
        <path key={k} d={`M${-30 - k * 9},50 C${-46 - k * 8},${80 + k * 6} ${-40 - k * 10 + sway * 3},${104 + k * 4} ${-50 - k * 8 + sway * 4},${128 + k * 8}
          c-5,8 3,15 9,10 c4,-4 -1,-9 -4,-6`} fill="none" stroke={HAIR} strokeWidth={5 - k} strokeLinecap="round" />
      ))}
      <path d={HEAD_PATH} fill={`url(#${id}-face)`} />
      <path d={HEAD_INK} fill="none" stroke={LINE} strokeWidth={1.3} strokeLinejoin="round" />
      {/* hair */}
      <path d="M34,-58 C26,-46 18,-36 16,-24 C14,-12 12,0 6,12 C2,20 -2,28 -8,36 C-16,48 -26,56 -36,58 C-56,46 -68,10 -62,-40 C-50,-70 0,-84 34,-58 Z" fill={HAIR} />
      <path d="M14,-20 C10,-6 8,6 2,16" fill="none" stroke="#2a2440" strokeWidth={1} opacity={0.8} />
      <path d="M6,8 c6,6 6,14 0,18" fill="none" stroke={HAIR} strokeWidth={4} strokeLinecap="round" />
      {/* ear and makara earring */}
      <path d="M-2,-6 C-14,-10 -18,6 -10,18 C-6,24 0,22 -1,14 C-4,10 -6,4 -2,-6 Z" fill={SKIN} stroke={LINE} strokeWidth={1} />
      <g transform={`translate(-9,22) rotate(${sway * 6})`}>
        <path d="M0,0 C8,6 10,16 4,24 C0,28 -6,26 -6,20 C-6,14 -2,10 0,0 Z" fill={GOLD} stroke={GOLD_LO} strokeWidth={0.8} />
        <circle cx={-1} cy={28} r={2.8} fill="#fbf3e2" />
      </g>
      {/* tilak */}
      <path d="M40,-50 C43,-42 45,-35 47,-29" fill="none" stroke="#f6e0a8" strokeWidth={2.2} strokeLinecap="round" />
      <circle cx={48} cy={-25} r={1.7} fill="#d0283e" />
      {/* brow, eye, nostril, lips */}
      <path d="M12,-25 Q34,-37 58,-26 Q34,-32 12,-25 Z" fill={HAIR} />
      <Eye id={`${id}-k`} g={g} blink={blink} back={[18, -7]} front={[53, -10]} peak={-17} low={-4} iris="#2a1a10" line={HAIR} />
      <path d="M66,28 C63,30 64,32 68,31" fill="none" stroke={LINE} strokeWidth={1} />
      <path d="M65,34 C66,37 69,39 68,41 C66,43 63,44 62,45 L58,44 C60,40 62,37 65,34 Z" fill={LIP} />
      <path d="M62,45 C64,47 67,49 65,52 C63,55 60,55 58,53 C60,50 60,47 62,45 Z" fill={LIP} opacity={0.9} />
      <path d={`M62,45 Q59,${45 - smile * 1.5} ${55 - smile * 1.5},${44 - smile * 3}`} fill="none" stroke={LINE} strokeWidth={1.1} strokeLinecap="round" />
      <Crown id={id} glint={glint} />
    </g>
  );

  // a jasmine garland held out, hanging in a loop below the hand
  const offerLoop = garland > 0.01 && (
    <g transform={`translate(${W[0] + 6},${W[1] + 4}) rotate(${sway2 * 4})`} opacity={garland}>
      {Array.from({length: 30}, (_, i) => {
        const th = (i / 30) * Math.PI * 2;
        const x = Math.sin(th) * 30 * garland;
        const y = (1 - Math.cos(th)) * 58 * garland;
        return (
          <g key={i} transform={`translate(${x},${y}) rotate(${i * 37})`}>
            {i % 6 === 3 ? <circle r={4.6} fill="#cf2d45" stroke="#8a1328" strokeWidth={0.6} /> :
              [0, 72, 144, 216, 288].map((d) => <ellipse key={d} rx={3} ry={5.6} transform={`rotate(${d}) translate(0,-4.4)`} fill="#fdf8ee" stroke="#d8cdb6" strokeWidth={0.4} />)}
            <circle r={1.7} fill="#f2c94c" />
          </g>
        );
      })}
      <path d={`M0,${116 * garland} l-4,16 M0,${116 * garland} l4,16`} stroke="#cf2d45" strokeWidth={2} opacity={garland} />
    </g>
  );

  const armEl = (
    <g transform={`translate(0,${-rise * 0.6})`}>
      {/* outline both segments first, then fill over them: one clean silhouette, no seam at the elbow */}
      <path d={limb(S, E, 46, 36)} fill={SKIN} stroke={LINE} strokeWidth={2.4} />
      <path d={limb(E, W, 36, 26)} fill={SKIN} stroke={LINE} strokeWidth={2.4} />
      <path d={limb(S, E, 46, 36)} fill={SKIN} />
      <path d={limb(E, W, 36, 26)} fill={SKIN} />
      {/* armlet and bangles */}
      {(() => {
        const t = 0.32;
        const p: Pt = [S[0] + (E[0] - S[0]) * t, S[1] + (E[1] - S[1]) * t];
        const q: Pt = [E[0] + (W[0] - E[0]) * 0.9, E[1] + (W[1] - E[1]) * 0.9];
        return (
          <g>
            <g transform={`translate(${p[0]},${p[1]}) rotate(${-(a.sh)})`}>
              <rect x={-23} y={-4} width={46} height={8} rx={3} fill={GOLD} stroke={GOLD_LO} strokeWidth={0.8} />
              <circle r={4} fill="#c41e3a" stroke={GOLD_HI} strokeWidth={0.8} />
            </g>
            <g transform={`translate(${q[0]},${q[1]}) rotate(${-fa})`}>
              <rect x={-14} y={-5} width={28} height={4} rx={2} fill={GOLD} />
              <rect x={-14} y={1} width={28} height={4} rx={2} fill={GOLD_HI} />
            </g>
          </g>
        );
      })()}
      {offerLoop}
      <Hand at={W} angle={handAngle} skin={SKIN} line={LINE} scale={1.3} cup={a.el > 120 ? 0.6 : 0} />
    </g>
  );

  return (
    <g transform={facing === 'left' ? `translate(${FIG_W},0) scale(-1,1)` : undefined}>
      {layer !== 'arm' && body}
      {layer !== 'arm' && head}
      {layer !== 'body' && armEl}
    </g>
  );
};
