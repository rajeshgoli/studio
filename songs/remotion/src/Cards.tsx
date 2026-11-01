import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Timeline} from './types';
import {CREAM, FONTS, GOLD, ramp} from './lib';

/** Title over the opening drone, gone just before the first sung line. */
export const TitleCard: React.FC<{tl: Timeline}> = ({tl}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  const first = tl.lines[0]?.start ?? 4;
  const t0 = tl.hook ? tl.hook.end + 0.5 : 0.4; // after the spoken hook, if there is one
  const a = Math.min(ramp(t, t0, t0 + 1.2), 1 - ramp(t, first - 1.0, first - 0.3));
  const b = Math.min(ramp(t, t0 + 0.8, t0 + 1.8), 1 - ramp(t, first - 1.0, first - 0.3));
  if (a <= 0 && b <= 0) return null;
  const devaTitle = (tl.lines[0]?.deva ?? '').split(' ').slice(0, 2).join(' ');
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 60, right: 60, top: 1180, textAlign: 'center'}}>
        <div style={{fontFamily: FONTS.deva, fontSize: 52, color: GOLD, opacity: a * 0.85}}>{devaTitle}</div>
        <div style={{opacity: a, fontFamily: FONTS.serif, fontSize: 108, color: GOLD, letterSpacing: 2, marginTop: 6,
          textShadow: `0 0 30px ${GOLD}55, 0 3px 16px rgba(0,0,0,0.7)`, transform: `translateY(${(1 - a) * 16}px)`}}>
          {tl.title}
        </div>
        <div style={{width: 220, height: 1, background: GOLD, margin: '26px auto', opacity: b * 0.6}} />
        <div style={{opacity: b, fontFamily: FONTS.serif, fontSize: 34, color: CREAM, letterSpacing: 3, textTransform: 'uppercase'}}>
          {tl.source}
        </div>
        <div style={{opacity: b, fontFamily: FONTS.serif, fontStyle: 'italic', fontSize: 40, color: CREAM, marginTop: 22, lineHeight: 1.35}}>
          {tl.context}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** The spoken hook, its words appearing as they are said. */
export const HookCard: React.FC<{tl: Timeline; energy: (f: number) => number}> = ({tl, energy}) => {
  const frame = useCurrentFrame();
  const h = tl.hook;
  if (!h) return null;
  const t = frame / tl.fps;
  const alpha = Math.min(ramp(t, h.start - 0.3, h.start), 1 - ramp(t, h.end + 0.25, h.end + 0.75));
  if (alpha <= 0) return null;
  // progress through the speech, counted in frames where the voice is sounding
  const a = Math.round(h.start * tl.fps);
  const b = Math.round(h.end * tl.fps);
  let total = 0;
  let done = 0;
  for (let f = a; f <= b; f++) {
    const on = energy(f) > 0.06 ? 1 : 0;
    total += on;
    if (f <= frame) done += on;
  }
  const p = total > 0 ? done / total : 0;
  const words = h.text.split(' ');
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 70, right: 70, top: 1200, textAlign: 'center', opacity: alpha}}>
        <div style={{fontFamily: FONTS.serif, fontSize: 66, lineHeight: 1.25, color: '#fff8ec',
          textShadow: '0 2px 18px rgba(0,0,0,0.85)'}}>
          {words.map((w, i) => {
            const k = Math.max(0, Math.min(1, (p * words.length - i) * 2.5 + 0.6));
            const hot = /song|upset|beloved/i.test(w);
            return (
              <span key={i} style={{opacity: 0.12 + 0.88 * k, color: hot ? GOLD : undefined}}>
                {w}{i < words.length - 1 ? ' ' : ''}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Closing thought after the last line, then a fade to black. */
export const ClosingCard: React.FC<{tl: Timeline}> = ({tl}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  const end = tl.durationInFrames / tl.fps;
  const lastEnd = tl.lines[tl.lines.length - 1]?.end ?? end - 4;
  const a = ramp(t, lastEnd + 1.6, lastEnd + 2.6);
  const black = ramp(t, end - 1.0, end);
  return (
    <AbsoluteFill>
      {a > 0 && (tl.closing || tl.credit) && (
        <div style={{position: 'absolute', left: 80, right: 80, top: 1230, textAlign: 'center', opacity: a * (1 - black)}}>
          <div style={{fontFamily: FONTS.serif, fontStyle: 'italic', fontSize: 46, color: CREAM, lineHeight: 1.4,
            textShadow: '0 2px 14px rgba(0,0,0,0.8)'}}>{tl.closing}</div>
          {tl.credit && (
            <div style={{fontFamily: FONTS.serif, fontSize: 30, color: GOLD, letterSpacing: 3, marginTop: 36, textTransform: 'uppercase'}}>
              {tl.credit}
            </div>
          )}
        </div>
      )}
      <AbsoluteFill style={{background: '#000', opacity: black}} />
    </AbsoluteFill>
  );
};

/** Painted-manuscript border and a fixed vignette. */
export const Frame: React.FC = () => (
  <AbsoluteFill style={{pointerEvents: 'none'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse 85% 70% at 50% 45%, transparent 55%, rgba(0,0,0,0.55) 100%)'}} />
    <svg width={1080} height={1920} style={{position: 'absolute'}}>
      <rect x={34} y={34} width={1012} height={1852} fill="none" stroke={GOLD} strokeOpacity={0.35} strokeWidth={1.5} rx={6} />
      <rect x={44} y={44} width={992} height={1832} fill="none" stroke={GOLD} strokeOpacity={0.18} strokeWidth={1} rx={4} />
      {[[44, 44], [1036, 44], [44, 1876], [1036, 1876]].map(([x, y], i) => (
        <g key={i} transform={`translate(${x},${y}) rotate(45)`}>
          <rect x={-7} y={-7} width={14} height={14} fill="none" stroke={GOLD} strokeOpacity={0.5} strokeWidth={1.2} />
          <circle r={2.2} fill={GOLD} fillOpacity={0.6} />
        </g>
      ))}
    </svg>
  </AbsoluteFill>
);
