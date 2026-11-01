import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {MotifLine, Timeline} from './types';
import {makeVoice} from './voice';
import {Sky} from './Sky';
import {Glosses, Lyrics} from './Lyrics';
import {Ribbon} from './Ribbon';
import {ClosingCard, Frame, HookCard, TitleCard} from './Cards';
import {motifFor} from './motifs';
import {ramp} from './lib';
import {Duet} from './Duet';

const XF = 1.0; // seconds scenes overlap while crossfading

const SceneLayer: React.FC<{tl: Timeline; si: number; voice: ReturnType<typeof makeVoice>}> = ({tl, si, voice}) => {
  const sc = tl.scenes[si];
  const fps = tl.fps;
  const from = Math.max(0, Math.round((sc.start - (si > 0 ? XF / 2 : 0)) * fps));
  const to = Math.min(tl.durationInFrames, Math.round((sc.end + (si < tl.scenes.length - 1 ? XF / 2 : 0)) * fps));
  const dur = Math.max(1, to - from);
  const lines: MotifLine[] = sc.lines.map((i) => ({
    ...tl.lines[i],
    from: Math.round(tl.lines[i].start * fps) - from,
    to: Math.round(tl.lines[i].end * fps) - from,
  }));
  const Motif = motifFor(sc.motif);
  return (
    <Sequence from={from} durationInFrames={dur} name={`scene ${si}: ${sc.motif}`}>
      <Fade dur={dur} fin={si > 0 ? XF * fps : 0} fout={si < tl.scenes.length - 1 ? XF * fps : 0}>
        <Motif durationInFrames={dur} lines={lines} voice={(f) => voice.energy(f + from)} pitch={(f) => voice.pitch(f + from)} />
      </Fade>
    </Sequence>
  );
};

const Fade: React.FC<{dur: number; fin: number; fout: number; children: React.ReactNode}> = ({dur, fin, fout, children}) => {
  const f = useCurrentFrame();
  const a = Math.min(fin > 0 ? ramp(f, 0, fin) : 1, fout > 0 ? 1 - ramp(f, dur - fout, dur) : 1);
  return <AbsoluteFill style={{opacity: a}}>{children}</AbsoluteFill>;
};

/** `bare` drops every text layer, the pitch thread and the audio: just the painting (for thumbnails). */
export const LyricShort: React.FC<{tl: Timeline | null; bare?: boolean}> = ({tl, bare}) => {
  const voice = React.useMemo(() => (tl ? makeVoice(tl) : null), [tl]);
  if (!tl || !voice) return <AbsoluteFill style={{background: '#000'}} />;
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <Sky tl={tl} />
      {tl.scenes.map((_, i) => <SceneLayer key={i} tl={tl} si={i} voice={voice} />)}
      <Duet tl={tl} voice={voice} />
      {!bare && (
        <>
          <Ribbon tl={tl} voice={voice} />
          <Glosses tl={tl} voice={voice} />
          <Lyrics tl={tl} voice={voice} />
          <HookCard tl={tl} energy={voice.energy} />
          <TitleCard tl={tl} />
          <ClosingCard tl={tl} />
        </>
      )}
      <Frame />
      {tl.audio && !bare && <Audio src={staticFile(tl.audio)} />}
    </AbsoluteFill>
  );
};
