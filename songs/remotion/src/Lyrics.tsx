import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {Line, Timeline} from './types';
import {Voice} from './voice';
import {CREAM, FONTS, GOLD, clamp01, ramp, sylCount} from './lib';

const strip = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/-/g, '').toLowerCase();

/** Tokens of the transliteration with their [from, to) share of the line's syllables. */
const tokens = (l: Line) => {
  const parts = l.translit.split(/(\s+|-)/).filter((p) => p.length > 0);
  const syl = parts.map((p) => (/^\s+$|^-$/.test(p) ? 0 : sylCount(p)));
  const total = syl.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  return parts.map((p, i) => {
    const from = acc / total;
    acc += syl[i];
    return {text: p, from, to: acc / total};
  });
};

/** When (as line progress 0..1) a glossed word is sung: the token sharing the longest prefix with it. */
const glossAt = (l: Line, w: string) => {
  const target = strip(w);
  let best = {score: 0, from: 0};
  for (const t of tokens(l)) {
    const s = strip(t.text);
    let k = 0;
    while (k < s.length && k < target.length && s[k] === target[k]) k++;
    if (k > best.score) best = {score: k, from: t.from};
  }
  // compound glosses like "madana-anala" begin at their first token; "danta-ruci" etc. likewise
  return best.from;
};

/** Index of the line on screen: from 0.25 s before it starts until the next one takes over. */
export const currentLine = (tl: Timeline, t: number) => {
  let cur = -1;
  tl.lines.forEach((l, i) => {
    if (t >= l.start - 0.25) cur = i;
  });
  return cur;
};

const LineBlock: React.FC<{tl: Timeline; li: number; voice: Voice; alpha: number; rise: number}> = ({tl, li, voice, alpha, rise}) => {
  const frame = useCurrentFrame();
  const l = tl.lines[li];
  const p = voice.progress(li, frame);
  const t = frame / tl.fps;
  // the meaning is the headline: it arrives with the line; the original sits beneath it
  const meaningIn = ramp(t, l.start - 0.25, l.start + 0.35);
  return (
    <div style={{position: 'absolute', left: 64, right: 64, top: 1170 + rise, opacity: alpha, textAlign: 'center'}}>
      <div style={{fontFamily: FONTS.serif, fontSize: 60, lineHeight: 1.22, color: '#fff8ec',
        opacity: meaningIn, transform: `translateY(${(1 - meaningIn) * 12}px)`,
        textShadow: '0 2px 18px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.6)'}}>
        {l.meaning}
      </div>
      <div style={{width: 120, height: 1, background: GOLD, opacity: 0.55, margin: '28px auto 22px'}} />
      <div style={{fontFamily: FONTS.deva, fontSize: 38, color: GOLD, opacity: 0.9, letterSpacing: 1, marginBottom: 10,
        textShadow: '0 2px 12px rgba(0,0,0,0.8)'}}>
        {l.deva}
      </div>
      <div style={{fontFamily: FONTS.serif, fontStyle: 'italic', fontSize: 36, lineHeight: 1.25, textShadow: '0 2px 12px rgba(0,0,0,0.8)'}}>
        {tokens(l).map((tk, i) => {
          const lit = clamp01((p - tk.from) / Math.max(0.001, tk.to - tk.from));
          const on = tk.to > tk.from ? lit : p >= tk.from ? 1 : 0;
          const glow = tk.to > tk.from && p >= tk.from && p < tk.to + 0.02;
          return (
            <span key={i} style={{
              color: on > 0 ? GOLD : CREAM,
              opacity: 0.55 + 0.45 * on,
              textShadow: glow ? `0 0 14px ${GOLD}aa, 0 2px 12px rgba(0,0,0,0.8)` : undefined,
              whiteSpace: 'pre',
            }}>{tk.text}</span>
          );
        })}
      </div>
    </div>
  );
};

export const Lyrics: React.FC<{tl: Timeline; voice: Voice}> = ({tl, voice}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  const cur = currentLine(tl, t);
  if (cur < 0) return null;
  const XF = 0.45; // seconds of crossfade between lines
  const l = tl.lines[cur];
  const next = tl.lines[cur + 1];
  const inA = ramp(t, l.start - 0.25, l.start - 0.25 + XF);
  // last line lingers, then yields to the closing card
  const lastOut = cur === tl.lines.length - 1 ? 1 - ramp(t, l.end + 1.2, l.end + 2.0) : 1;
  const blocks: React.ReactNode[] = [
    <LineBlock key={cur} tl={tl} li={cur} voice={voice} alpha={inA * lastOut} rise={(1 - inA) * 24} />,
  ];
  if (cur > 0 && inA < 1) {
    blocks.unshift(<LineBlock key={cur - 1} tl={tl} li={cur - 1} voice={voice} alpha={1 - inA} rise={-inA * 24} />);
  }
  void next;
  return <AbsoluteFill>{blocks}</AbsoluteFill>;
};

/** Small cards that name a word as it is sung: "kaumudī — moonlight". */
export const Glosses: React.FC<{tl: Timeline; voice: Voice}> = ({tl, voice}) => {
  const frame = useCurrentFrame();
  const t = frame / tl.fps;
  const cur = currentLine(tl, t);
  if (cur < 0) return null;
  const l = tl.lines[cur];
  const nextStart = tl.lines[cur + 1]?.start ?? l.end + 2.5;
  const p = voice.progress(cur, frame);
  const items = l.words.map((g) => ({...g, at: glossAt(l, g.w)})).sort((a, b) => a.at - b.at);
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: 0, right: 0, top: 1060, display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 10}}>
        {items.map((g, i) => {
          const shown = p >= g.at ? 1 : 0;
          const k = Math.min(shown * clamp01((p - g.at) * 12 + 0.0001) , 1 - ramp(t, nextStart - 0.6, nextStart - 0.25));
          return (
            <div key={i} style={{
              opacity: k, transform: `translateY(${(1 - k) * 10}px)`,
              display: 'flex', alignItems: 'baseline', gap: 14, padding: '8px 22px',
              border: `1px solid ${GOLD}66`, borderRadius: 999, background: 'rgba(10,8,20,0.45)',
            }}>
              <span style={{fontFamily: FONTS.serif, fontSize: 32, color: GOLD, letterSpacing: 0.5}}>{g.w}</span>
              <span style={{fontFamily: FONTS.serif, fontSize: 28, color: CREAM, fontStyle: 'italic', opacity: 0.9}}>{g.gloss}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
