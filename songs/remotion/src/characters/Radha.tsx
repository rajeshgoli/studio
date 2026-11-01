import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {CharProps, armOf, blinkAt, gazeOf, idle} from './pose';
import {Eye, Glint, Hand, Pt, alongQuad, armJoints, limb} from './parts';

const SKIN = '#f1c896';
const SKIN_HI = '#fde3bf';
const SKIN_LO = '#d49c6c';
const LINE = '#6b3b22';
const HAIR = '#0d0b10';
const GOLD = '#e2ae48';
const GOLD_HI = '#ffe6a6';
const GOLD_LO = '#9a6a22';
const VEIL = '#a3182f';
const VEIL_LO = '#6a0c1f';
const CHOLI = '#2f7a4f';
const CHOLI_LO = '#1d5435';
const SKIRT = '#d9577a';
const LIP = '#b23a4a';

export const FIG_W = 460;
export const FIG_H = 600;
const HEAD: Pt = [292, 200];
const NECK_PIVOT: Pt = [0, 90];
const HEAD_SCALE = 1.22;

/** A gentler profile than Krishna's: finer nose, softer chin, fuller lips. */
const HEAD_PATH = `M36,-60 C46,-52 51,-38 53,-24 C55,-14 58,-4 63,8 L71,21 C74,26 72,30 67,30 C65,31 63,31 62,32
  C63,35 66,37 65,39 C63,41 61,42 60,43 C62,45 64,47 62,50 C60,53 57,54 56,55 C58,59 58,64 54,68
  C48,74 36,75 26,72 L24,110 L-28,112 L-32,58 C-58,40 -64,0 -58,-30 C-48,-66 0,-80 36,-60 Z`;
/** The same outline without the neck's bottom edge, for the ink line. */
const HEAD_INK = `M36,-60 C46,-52 51,-38 53,-24 C55,-14 58,-4 63,8 L71,21 C74,26 72,30 67,30 C65,31 63,31 62,32
  C63,35 66,37 65,39 C63,41 61,42 60,43 C62,45 64,47 62,50 C60,53 57,54 56,55 C58,59 58,64 54,68
  C48,74 36,75 26,72 L24,110`;

/** Gold border with a dotted inner line, drawn along a path. */
const Border: React.FC<{d: string; w?: number}> = ({d, w = 6}) => (
  <g>
    <path d={d} fill="none" stroke={GOLD} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
    <path d={d} fill="none" stroke={GOLD_HI} strokeWidth={w * 0.3} strokeDasharray={`${w * 0.4} ${w * 0.7}`} strokeLinecap="round" />
  </g>
);

export const Radha: React.FC<CharProps> = ({facing = 'right', headTilt = 0, gaze, arm, smile = 0, seed = 2, id, swing = 0}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = gazeOf(gaze);
  const a = armOf(arm);
  const {breath, sway, sway2, t} = idle(frame, fps, seed);
  const blink = blinkAt(frame, fps, seed);
  const gp = ((t + seed * 2.3) % 8) / 1.8;
  const glint = gp < 1 ? gp : -1;
  const rise = breath * 1.4;
  const tilt = headTilt + sway * 1.0;
  const S: Pt = [226, 356 + rise * 0.5];
  const {E, W, fa, handAngle} = armJoints(S, a, 118, 108);
  const v = sway2 * 6 + swing; // veil flutter

  const defs = (
    <defs>
      <radialGradient id={`${id}-skin`} cx="330" cy="380" r="200" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor={SKIN_HI} />
        <stop offset="0.6" stopColor={SKIN} />
        <stop offset="1" stopColor={SKIN_LO} />
      </radialGradient>
      <radialGradient id={`${id}-face`} cx="36" cy="14" r="88" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor={SKIN_HI} />
        <stop offset="0.65" stopColor={SKIN} />
        <stop offset="1" stopColor={SKIN_LO} />
      </radialGradient>
      <radialGradient id={`${id}-cheek`} cx="30" cy="30" r="22" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#e9877a" stopOpacity={0.45} />
        <stop offset="1" stopColor="#e9877a" stopOpacity={0} />
      </radialGradient>
      <linearGradient id={`${id}-veil`} x1="0" y1="0" x2="0" y2="600" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor={VEIL} />
        <stop offset="1" stopColor={VEIL_LO} />
      </linearGradient>
      <linearGradient id={`${id}-choli`} x1="200" y1="330" x2="380" y2="460" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor={CHOLI_LO} />
        <stop offset="0.6" stopColor={CHOLI} />
        <stop offset="1" stopColor="#3f9a66" />
      </linearGradient>
    </defs>
  );

  // the odhni falling behind her, from the crown of the head to below the waist
  const backVeil = (
    <g>
      <path d={`M246,96 C186,110 150,170 140,250 C128,350 ${112 + v},470 ${96 + v * 1.6},600 L262,600 C252,500 246,400 250,320 C252,250 262,170 286,120 Z`}
        fill={`url(#${id}-veil)`} />
      <Border d={`M${96 + v * 1.6},598 C${112 + v},470 128,350 140,250 C150,170 186,110 246,96`} w={7} />
      {/* small woven buti motifs */}
      {[[170, 300], [150, 400], [190, 380], [136, 500], [178, 480], [210, 540]].map(([x, y], i) => (
        <circle key={i} cx={x + v * (y / 600)} cy={y} r={2.4} fill={GOLD} opacity={0.7} />
      ))}
    </g>
  );

  const body = (
    <g transform={`translate(0,${-rise}) scale(1,${1 + breath * 0.004})`} style={{transformOrigin: '280px 600px'}}>
      <path d={`M300,252 L322,318 C340,328 360,340 370,362 C384,392 382,428 366,452 C360,470 352,520 352,600
        L210,600 C202,540 196,480 194,430 C192,390 196,356 212,334 C230,316 250,306 262,268 Z`}
        fill={`url(#${id}-skin)`} stroke={LINE} strokeWidth={1.2} />
      {/* choli */}
      <path d="M214,334 C240,326 300,326 324,322 C344,332 362,344 371,365 C384,394 382,428 366,452 C320,466 250,466 196,454 C192,410 196,360 214,334 Z"
        fill={`url(#${id}-choli)`} stroke={CHOLI_LO} strokeWidth={1} />
      <path d="M196,454 C250,466 320,466 366,452" fill="none" stroke={GOLD} strokeWidth={4} />
      <path d="M330,372 C346,394 362,404 376,402" fill="none" stroke={CHOLI_LO} strokeWidth={1} opacity={0.6} />
      {/* ghagra waist */}
      <path d="M204,540 C250,552 310,552 354,540 L354,600 L210,600 Z" fill={SKIRT} />
      <path d="M204,540 C250,552 310,552 354,540" fill="none" stroke={GOLD} strokeWidth={5} />
      {/* necklace: gold collar with drops, and a long pearl strand */}
      <path d="M264,300 C276,330 306,338 326,320" fill="none" stroke={GOLD} strokeWidth={5} strokeLinecap="round" />
      {alongQuad([268, 312], [296, 344], [326, 324], 7).map(([x, y], i) => (
        <path key={i} d={`M${x},${y} l-2.4,6 l2.4,4 l2.4,-4 Z`} fill={GOLD} stroke={GOLD_LO} strokeWidth={0.5} />
      ))}
      {alongQuad([266, 316], [300, 420], [366, 360], 28).map(([x, y], i) => <circle key={`p${i}`} cx={x} cy={y} r={2.1} fill="#fbf3e2" />)}
    </g>
  );

  // the odhni's front fall: over the shoulder, sheer across the back of the torso
  const frontVeil = (
    <g transform={`translate(0,${-rise})`}>
      <path d={`M262,268 C236,300 206,326 196,370 C186,420 ${190 + v * 0.6},500 ${200 + v},600 L250,600 C246,530 240,470 238,420 C236,370 250,320 280,290 Z`}
        fill={VEIL} opacity={0.82} />
      <Border d={`M280,290 C250,320 236,370 238,420 C240,470 246,530 250,600`} w={5} />
    </g>
  );

  const head = (
    <g transform={`translate(${HEAD[0]},${HEAD[1] - rise}) rotate(${-tilt},${NECK_PIVOT[0]},${NECK_PIVOT[1]}) translate(${NECK_PIVOT[0]},${NECK_PIVOT[1]}) scale(${HEAD_SCALE}) translate(${-NECK_PIVOT[0]},${-NECK_PIVOT[1]})`}>
      {/* braid falling down her back */}
      <g transform={`rotate(${sway * 2},-40,50)`}>
        {Array.from({length: 12}, (_, i) => {
          const y = 48 + i * 15;
          const x = -46 - i * 1.6;
          return <path key={i} d={`M${x - 8},${y} Q${x},${y + 12} ${x + 8},${y} Q${x},${y + 4} ${x - 8},${y} Z`} fill={HAIR} stroke="#2a2232" strokeWidth={0.8} />;
        })}
        <path d="M-66,228 l-5,24 M-64,228 l0,26 M-62,228 l5,24" stroke="#c41e3a" strokeWidth={2.4} strokeLinecap="round" />
        <circle cx={-64} cy={226} r={4} fill={GOLD} />
      </g>
      <path d={HEAD_PATH} fill={`url(#${id}-face)`} />
      <path d={HEAD_INK} fill="none" stroke={LINE} strokeWidth={1.2} strokeLinejoin="round" />
      <circle cx={30} cy={30} r={22} fill={`url(#${id}-cheek)`} />
      {/* hair showing beneath the veil at forehead and temple */}
      <path d="M36,-61 C27,-48 19,-36 16,-24 C13,-10 10,4 3,18 L-10,26 C-4,4 6,-22 14,-42 C21,-54 28,-62 32,-66 Z" fill={HAIR} />
      {/* maang tikka */}
      <path d="M33,-62 C36,-56 38,-52 37,-48" fill="none" stroke={GOLD} strokeWidth={1} />
      <circle cx={37} cy={-46} r={3} fill={GOLD} stroke={GOLD_LO} strokeWidth={0.6} />
      {/* veil over the head */}
      <path d={`M32,-68 C0,-96 -60,-84 -78,-34 C-90,8 -88,60 ${-82 + v * 0.3},104 L-20,108 C-24,80 -20,50 -12,28 C-4,4 6,-22 14,-42 C20,-54 26,-62 32,-68 Z`}
        fill={`url(#${id}-veil)`} />
      <path d="M-30,-70 C-50,-56 -64,-30 -66,0" fill="none" stroke={VEIL_LO} strokeWidth={1.4} opacity={0.6} />
      <Border d="M32,-68 C26,-62 20,-54 14,-42 C6,-22 -4,4 -12,28 C-20,50 -24,80 -20,108" w={6} />
      {/* jhumka just below the veil */}
      <g transform={`translate(-12,30) rotate(${sway * 7})`}>
        <path d="M0,0 L0,6" stroke={GOLD} strokeWidth={1.2} />
        <path d="M-7,16 C-7,8 7,8 7,16 Z" fill={GOLD} stroke={GOLD_LO} strokeWidth={0.6} />
        {[-5, -2, 1, 4].map((x) => <circle key={x} cx={x + 0.5} cy={18} r={1.3} fill="#fbf3e2" />)}
      </g>
      {/* bindi, brow, eye */}
      <circle cx={50} cy={-27} r={2.1} fill="#c41e3a" />
      <path d="M14,-24 Q34,-35 55,-25 Q34,-30 14,-24 Z" fill={HAIR} />
      <Eye id={`${id}-r`} g={g} blink={blink} back={[17, -7]} front={[51, -10]} peak={-17} low={-4} iris="#2a1a10" line={HAIR} kohl={1.3} />
      <path d="M62,26 C60,28 61,29 64,29" fill="none" stroke={LINE} strokeWidth={0.9} />
      {/* lips, with the smile lifting the corner */}
      <path d="M62,32 C63,35 66,37 65,39 C63,41 61,42 60,43 L56,42 C58,38 60,35 62,32 Z" fill={LIP} />
      <path d="M60,43 C62,45 64,47 62,50 C60,53 57,53 55,51 C57,48 58,45 60,43 Z" fill={LIP} opacity={0.92} />
      <path d={`M60,43 Q57,${43 - smile * 1.6} ${53 - smile * 1.5},${42 - smile * 3}`} fill="none" stroke={LINE} strokeWidth={1} strokeLinecap="round" />
      {/* nath: a fine gold ring from the nostril with a pearl, chained back to the veil */}
      <circle cx={58} cy={36} r={9.5} fill="none" stroke={GOLD} strokeWidth={1.4} />
      <circle cx={53} cy={44} r={2.2} fill="#fbf3e2" />
      <path d="M48,34 Q20,26 -8,10" fill="none" stroke="#fbf3e2" strokeWidth={1.4} strokeDasharray="1.5 2.5" />
      <Glint x={58 - glint * 10} y={26 + glint * 20} s={0.8} o={Math.sin(Math.max(0, glint) * Math.PI)} />
    </g>
  );

  const armEl = (
    <g transform={`translate(0,${-rise * 0.6})`}>
      <path d={limb(S, E, 38, 30)} fill={SKIN} stroke={LINE} strokeWidth={2.2} />
      <path d={limb(E, W, 30, 22)} fill={SKIN} stroke={LINE} strokeWidth={2.2} />
      <path d={limb(S, E, 38, 30)} fill={SKIN} />
      <path d={limb(E, W, 30, 22)} fill={SKIN} />
      {/* bangles: gold and red, stacked at the wrist */}
      {Array.from({length: 6}, (_, i) => {
        const tt = 0.72 + i * 0.045;
        const q: Pt = [E[0] + (W[0] - E[0]) * tt, E[1] + (W[1] - E[1]) * tt];
        return <rect key={i} x={-13} y={-1.6} width={26} height={3.2} rx={1.6} transform={`translate(${q[0]},${q[1]}) rotate(${-fa})`}
          fill={i % 2 ? '#c41e3a' : GOLD} />;
      })}
      <Glint x={E[0] + (W[0] - E[0]) * 0.8} y={E[1] + (W[1] - E[1]) * 0.8} s={0.7} o={Math.sin(Math.max(0, glint - 0.2) * Math.PI) * 0.8} />
      <Hand at={W} angle={handAngle} skin={SKIN} line={LINE} scale={1.15} cup={a.el > 120 ? 0.6 : 0} />
    </g>
  );

  return (
    <g transform={facing === 'left' ? `translate(${FIG_W},0) scale(-1,1)` : undefined}>
      {defs}
      {backVeil}
      {body}
      {head}
      {armEl}
      {frontVeil}
    </g>
  );
};
