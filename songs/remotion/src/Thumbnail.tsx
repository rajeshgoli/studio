import React from 'react';
import {AbsoluteFill} from 'remotion';
import {LyricShort} from './LyricShort';
import {Timeline} from './types';
import {CREAM, FONTS, GOLD} from './lib';

export type ThumbProps = {poem: string; tl: Timeline | null; at: number; headline: string; sub: string};

/** A still from the short (text layers hidden) with a headline across the lower third. Render frame `at` * fps. */
export const Thumbnail: React.FC<ThumbProps> = ({tl, headline, sub}) => {
  if (!tl) return <AbsoluteFill style={{background: '#000'}} />;
  return (
    <AbsoluteFill>
      <LyricShort tl={tl} bare />
      <AbsoluteFill style={{background: 'linear-gradient(180deg, transparent 52%, rgba(10,4,12,0.78) 70%, rgba(10,4,12,0.9) 100%)'}} />
      <div style={{position: 'absolute', left: 60, right: 60, top: 1180, textAlign: 'center'}}>
        <div style={{fontFamily: FONTS.serif, fontSize: 118, lineHeight: 1.05, color: GOLD, fontWeight: 700,
          textShadow: `0 0 40px ${GOLD}55, 0 4px 20px rgba(0,0,0,0.9)`}}>{headline}</div>
        <div style={{width: 200, height: 2, background: GOLD, opacity: 0.6, margin: '36px auto 30px'}} />
        <div style={{fontFamily: FONTS.serif, fontStyle: 'italic', fontSize: 52, lineHeight: 1.25, color: CREAM,
          textShadow: '0 3px 16px rgba(0,0,0,0.9)'}}>{sub}</div>
      </div>
    </AbsoluteFill>
  );
};
