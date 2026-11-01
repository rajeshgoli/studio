import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame} from 'remotion';
import {Timeline} from './types';
import {Voice} from './voice';
import {Krishna} from './characters/Krishna';
import {Radha} from './characters/Radha';
import {ARMS, Arm, GAZES, Gaze, blendArm, blendGaze} from './characters/pose';
import {fbm, lerp, ramp, rand} from './lib';
import {Hand, limb} from './characters/parts';

const K_SKIN = '#4a6fb8';
const K_LINE = '#16234a';
const EMB_HAND_ANGLE = 18;

type KP = {tilt: number; gaze: Gaze; arm: Arm; smile: number; garland: number};
type RP = {tilt: number; gaze: Gaze; arm: Arm; smile: number; turn: number};
type Look = {mult: [number, number, number]; glow: string};
type Pose = {k: KP; r: RP; look: Look; emb: number};

const soft = (g: Gaze, lid: number): Gaze => ({...g, lid});

/** Each scene's pose as a function of seconds since the scene began (s) and its length (d). */
const SCENES: Record<string, (s: number, d: number, lines: {a: number; b: number}[]) => Pose> = {
  // "If you would speak, even a little..." — she has turned away; he pleads gently
  kaumudi: () => ({
    k: {tilt: 0, gaze: soft(GAZES.ahead, 0.22), arm: ARMS.plead, smile: 0.1, garland: 0},
    r: {tilt: -7, gaze: GAZES.down, arm: ARMS.rest, smile: 0, turn: 0},
    look: {mult: [0.62, 0.7, 0.95], glow: '#8fa3d9'}, emb: 0,
  }),
  // "Let the moon of your face..." — he looks up at her as at the moon; her head lifts a little
  chakora: (s, d) => ({
    k: {tilt: 9, gaze: GAZES.up, arm: {sh: 10, el: 78, wr: -10}, smile: 0.25, garland: 0},
    r: {tilt: lerp(-4, 5, ramp(s, d * 0.35, d * 0.85)), gaze: soft(GAZES.ahead, 0.3), arm: ARMS.rest, smile: 0, turn: 0},
    look: {mult: [0.78, 0.84, 1.0], glow: '#c9d4f2'}, emb: 0,
  }),
  // "Beloved, lovely of heart" — he offers jasmine; her eye glances back
  mandala: (s, d) => ({
    k: {tilt: 2, gaze: soft(GAZES.ahead, 0.18), arm: ARMS.offer, smile: 0.35, garland: ramp(s, 0.2, 1.4)},
    r: {tilt: 1, gaze: blendGaze(soft(GAZES.ahead, 0.3), GAZES.back, ramp(s, d * 0.35, d * 0.5)), arm: ARMS.rest,
      smile: 0.12 * ramp(s, d * 0.4, d * 0.6), turn: 0},
    look: {mult: [0.98, 0.86, 0.95], glow: '#e3a6c2'}, emb: 0,
  }),
  // "let go of this anger" — her chin rises in pride; he reaches toward her
  mana: () => ({
    k: {tilt: 0, gaze: soft(GAZES.ahead, 0.15), arm: ARMS.reach, smile: 0, garland: 0},
    r: {tilt: 11, gaze: {lid: 0.38, px: 0.5, py: -0.6}, arm: ARMS.rest, smile: 0, turn: 0},
    look: {mult: [0.72, 0.9, 0.95], glow: '#9fd0d8'}, emb: 0,
  }),
  // "the fire of love burns in my heart" — hand on heart, eyes closed; at the end she softens
  madana: (s, d) => {
    const soften = ramp(s, d * 0.62, d * 0.92);
    return {
      k: {tilt: 5, gaze: GAZES.closed, arm: ARMS.heart, smile: 0, garland: 0},
      r: {tilt: lerp(6, -2, soften), gaze: blendGaze(soft(GAZES.ahead, 0.3), GAZES.back, soften), arm: ARMS.rest,
        smile: 0.15 * soften, turn: 0},
      look: {mult: [1.05, 0.78, 0.6], glow: '#ff9a52'}, emb: 0,
    };
  },
  // "Give me the honey of your lotus face" — she turns to him, slowly; after the line, they embrace
  lotus: (s, _d, lines) => {
    const L8 = lines[0] ?? {a: 0.3, b: 6};
    const t0 = L8.a + 0.15; // she begins to turn as "dehi mukha kamala" begins
    const T = 1.8;
    const turn = ramp(s, t0, t0 + T, Easing.inOut(Easing.sin));
    const after = ramp(s, t0 + T * 0.7, t0 + T + 1.0); // gaze lifts as she completes the turn
    const smileIn = ramp(s, t0 + T + 0.2, t0 + T + 1.8);
    const emb = ramp(s, t0 + T + 2.0, t0 + T + 4.0, Easing.inOut(Easing.sin)); // ~2 s after she has turned
    const close = ramp(s, L8.b + 1.2, L8.b + 2.4);
    const k: KP = {tilt: lerp(1, -13, emb), gaze: blendGaze(soft(GAZES.ahead, 0.15), {lid: 0.92, px: 0, py: 1.5}, close),
      arm: blendArm({sh: 14, el: 100, wr: -30}, {sh: 16, el: 50, wr: -4}, emb), smile: lerp(0.5 * smileIn, 0.35, emb), garland: 0};
    const rg = blendGaze(blendGaze(GAZES.down, {lid: 0.12, px: 0.6, py: -1.2}, after), {lid: 0.95, px: 0, py: 1.5}, close);
    const r: RP = {tilt: lerp(lerp(-6, 3, after), -20, emb), gaze: rg,
      arm: blendArm({sh: 8, el: 64, wr: 0}, {sh: 6, el: 34, wr: 4}, emb), smile: lerp(0.6 * smileIn, 0.45, emb), turn};
    return {k, r, look: {mult: [1.02, 0.9, 0.86], glow: '#ffd29a'}, emb};
  },
};

const blendPose = (a: Pose, b: Pose, t: number): Pose => ({
  k: {tilt: lerp(a.k.tilt, b.k.tilt, t), gaze: blendGaze(a.k.gaze, b.k.gaze, t), arm: blendArm(a.k.arm, b.k.arm, t),
    smile: lerp(a.k.smile, b.k.smile, t), garland: lerp(a.k.garland, b.k.garland, t)},
  r: {tilt: lerp(a.r.tilt, b.r.tilt, t), gaze: blendGaze(a.r.gaze, b.r.gaze, t), arm: blendArm(a.r.arm, b.r.arm, t),
    smile: lerp(a.r.smile, b.r.smile, t), turn: lerp(a.r.turn, b.r.turn, t)},
  emb: lerp(a.emb, b.emb, t),
  look: {mult: a.look.mult.map((v, i) => lerp(v, b.look.mult[i], t)) as [number, number, number], glow: t < 0.5 ? a.look.glow : b.look.glow},
});

const scenePose = (tl: Timeline, si: number, t: number): Pose => {
  const sc = tl.scenes[si];
  const fn = SCENES[sc.motif] ?? SCENES.kaumudi;
  const d = sc.end - sc.start;
  const s = Math.max(0, Math.min(d, t - sc.start));
  return fn(s, d, sc.lines.map((i) => ({a: tl.lines[i].start - sc.start, b: tl.lines[i].end - sc.start})));
};

/** The pose at time t, gliding from one scene's pose to the next across each boundary. */
export const poseAt = (tl: Timeline, t: number): Pose => {
  let si = tl.scenes.findIndex((s) => t >= s.start && t < s.end);
  if (si < 0) si = t < tl.scenes[0].start ? 0 : tl.scenes.length - 1;
  const GL = 0.9;
  let p = scenePose(tl, si, t);
  const sc = tl.scenes[si];
  if (si + 1 < tl.scenes.length && t > sc.end - GL) {
    p = blendPose(p, scenePose(tl, si + 1, t), 0.5 * ramp(t, sc.end - GL, sc.end));
  } else if (si > 0 && t < sc.start + GL) {
    p = blendPose(scenePose(tl, si - 1, t), p, 0.5 + 0.5 * ramp(t, sc.start, sc.start + GL));
  }
  return p;
};

/** Flowering creeper sprays that hide where the figures dissolve. */
const Foliage: React.FC<{frame: number; side: 1 | -1; tint: string}> = ({frame, side, tint}) => {
  const leaves = React.useMemo(
    () =>
      Array.from({length: 34}, (_, i) => ({
        x: rand(i * 2.7 + side) * 330,
        y: 890 + rand(i * 5.3 + side) * 120,
        rot: -70 + rand(i * 1.9 + side) * 140,
        s: 0.7 + rand(i * 8.1 + side) * 0.7,
        flower: rand(i * 3.3 + side) > 0.78,
      })),
    [side],
  );
  return (
    <g transform={side === 1 ? undefined : 'translate(1080,0) scale(-1,1)'}>
      {leaves.map((l, i) => {
        const sw = fbm(frame / 30 * 0.4 + i, i) * 5;
        return (
          <g key={i} transform={`translate(${l.x},${l.y}) rotate(${l.rot + sw}) scale(${l.s})`} opacity={l.y > 990 ? 0.75 : 0.95}>
            {l.flower ? (
              <g>
                {[0, 72, 144, 216, 288].map((d) => <ellipse key={d} rx={4} ry={8} transform={`rotate(${d}) translate(0,-7)`} fill="#fbeff0" opacity={0.92} />)}
                <circle r={3} fill="#f2c94c" />
              </g>
            ) : (
              <g>
                <path d="M0,0 C10,-12 30,-14 44,0 C30,12 10,12 0,0 Z" fill="#1f3d2a" stroke={tint} strokeOpacity={0.55} strokeWidth={1} />
                <path d="M2,0 L40,0" stroke={tint} strokeOpacity={0.45} strokeWidth={0.8} />
              </g>
            )}
          </g>
        );
      })}
    </g>
  );
};

export const Duet: React.FC<{tl: Timeline; voice: Voice}> = ({tl, voice}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  const p = poseAt(tl, t);
  const e = voice.energy(frame);
  const [mr, mg, mb] = p.look.mult;
  const matrix = `${mr} 0 0 0 0  0 ${mg} 0 0 0  0 0 ${mb} 0 0  0 0 0 1 0`;

  // darkness veils them at first and lifts with the moonlight (end of scene 0)
  const s0 = tl.scenes[0];
  const l1 = tl.lines[s0.lines[0]];
  const lLast = tl.lines[s0.lines[s0.lines.length - 1]];
  const haze = 1 - ramp(t, l1.start + 1.0, lLast.end - 1.0);
  const enter = ramp(t, 0.6, 3.5); // fade up from the void under the title

  const SC = 0.9; // figure scale
  const TOP = 425;
  const KX = 40;
  const RX = 1080 - 40 - 460 * SC;

  // Radha's turn: a slow 2D turn about her body's centre. She narrows, flips facing at the thinnest point, widens.
  const u = p.r.turn;
  const facingR = u < 0.5;
  const narrow = facingR ? ramp(u, 0, 0.5) : 1 - ramp(u, 0.5, 1);
  const sx = 1 - 0.85 * narrow;
  const BODY_CX = facingR ? 285 : 460 - 285; // torso centre in figure coords
  const awayCx = RX - 34 + 285 * SC; // where her torso sits while she looks away (face off the frame edge)
  const towardCx = RX + (460 - 285) * SC;
  const em = p.emb;
  const rCx = lerp(awayCx, towardCx, u) - 128 * em; // ...and in the embrace she glides to him
  const rLean = -3 * Math.sin(u * Math.PI) - 7 * em; // degrees, about her base, toward him
  const rDrop = 128 * em; // she settles lower, her head against his chest
  const swing = 26 * Math.sin(u * Math.PI) * (facingR ? 1 : -1) * 0.8;
  const kDx = 78 * em;
  const kLean = 2 * em;

  const radhaProps = {headTilt: p.r.tilt, gaze: p.r.gaze, arm: p.r.arm, smile: p.r.smile, seed: 5, swing};
  const kProps = {facing: 'right' as const, headTilt: p.k.tilt, gaze: p.k.gaze, arm: p.k.arm, smile: p.k.smile, garland: p.k.garland, seed: 1};
  const kT = `translate(${KX + kDx},${TOP}) scale(${SC}) rotate(${kLean},300,600)`;
  const rT = `translate(${rCx},${TOP + rDrop}) rotate(${rLean},0,${600 * SC}) scale(${SC * sx},${SC}) translate(${-BODY_CX},0)`;
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <defs>
          <linearGradient id="duet-fade" x1="0" y1="0" x2="0" y2="1920" gradientUnits="userSpaceOnUse">
            <stop offset={900 / 1920} stopColor="#fff" />
            <stop offset={1005 / 1920} stopColor="#000" />
          </linearGradient>
          <mask id="duet-mask" maskUnits="userSpaceOnUse" x="0" y="0" width="1080" height="1920">
            <rect width="1080" height="1920" fill="url(#duet-fade)" />
          </mask>
          <filter id="duet-look" x="-20%" y="-20%" width="140%" height="140%">
            <feColorMatrix type="matrix" values={matrix} result="tinted" />
            <feGaussianBlur in="SourceAlpha" stdDeviation="14" result="blur" />
            <feFlood floodColor={p.look.glow} floodOpacity={0.18 + 0.3 * e} />
            <feComposite in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="tinted" />
            </feMerge>
          </filter>
        </defs>
        <g mask="url(#duet-mask)" opacity={enter}>
          <g filter="url(#duet-look)">
            <g transform={kT}>
              <Krishna id="kr" {...kProps} />
            </g>
            {/* his arm passes behind her; only the hand shows, resting just past the far edge of her veil */}
            {em > 0.5 && (
              <g transform={rT} opacity={ramp(em, 0.6, 0.9)}>
                <path d={limb([240, 252], [348, 270], 26, 22)} fill={K_SKIN} stroke={K_LINE} strokeWidth={2.2} />
                <path d={limb([240, 252], [348, 270], 26, 22)} fill={K_SKIN} />
                <Hand at={[350, 270]} angle={EMB_HAND_ANGLE} skin={K_SKIN} line={K_LINE} scale={1.15} cup={0.4} />
              </g>
            )}
            <g transform={rT}>
              <Radha id="ra" facing={facingR ? 'right' : 'left'} {...radhaProps} />
            </g>
          </g>
          {haze > 0.001 && (
            <g opacity={haze}>
              {[0, 1, 2, 3, 4].map((i) => (
                <ellipse key={i} cx={200 + i * 170 + fbm(t * 0.15, i) * 60} cy={680 + fbm(t * 0.1 + 5, i) * 40}
                  rx={260} ry={300} fill="#070a1f" opacity={0.55} style={{filter: 'blur(40px)'}} />
              ))}
            </g>
          )}
        </g>
        <g opacity={enter}>
          <Foliage frame={frame} side={1} tint={p.look.glow} />
          <Foliage frame={frame} side={-1} tint={p.look.glow} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};
