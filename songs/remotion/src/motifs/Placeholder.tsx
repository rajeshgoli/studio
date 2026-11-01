import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {MotifProps} from '../types';
import {ART, FONTS, GOLD} from '../lib';

/** Stand-in until a motif exists: a breathing ring with the motif's name. */
export const placeholder = (name: string): React.FC<MotifProps> => ({voice}) => {
  const f = useCurrentFrame();
  const e = voice(f);
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute'}}>
        <circle cx={ART.cx} cy={ART.cy} r={180 + 60 * e} fill="none" stroke={GOLD} strokeOpacity={0.5} strokeWidth={2} />
      </svg>
      <div style={{position: 'absolute', top: ART.cy - 30, width: 1080, textAlign: 'center', fontFamily: FONTS.serif,
        fontSize: 48, color: GOLD, opacity: 0.6}}>{name}</div>
    </AbsoluteFill>
  );
};
