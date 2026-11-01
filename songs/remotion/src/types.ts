export type Gloss = {w: string; gloss: string};

export type Line = {
  id: string;
  motif: string;
  translit: string;
  deva: string;
  meaning: string;
  words: Gloss[];
  syl: number;
  start: number; // seconds, video time
  end: number;
};

export type Scene = {motif: string; lines: number[]; start: number; end: number};

export type Timeline = {
  poem: string;
  fps: number;
  durationInFrames: number;
  width: number;
  height: number;
  title: string;
  source: string;
  context: string;
  closing: string;
  credit: string;
  audio: string | null;
  /** Spoken line before the song, in video seconds. */
  hook: {text: string; start: number; end: number} | null;
  tonic: number;
  raga: string;
  lines: Line[];
  scenes: Scene[];
  energy: number[]; // per video frame, 0..1 voice loudness
  pitch: (number | null)[]; // per video frame, semitones above Sa, null when not singing
};

/** A line as a motif sees it: frames are relative to the scene's first frame. */
export type MotifLine = Line & {from: number; to: number};

export type MotifProps = {
  /** Scene length in frames (the motif's own Sequence starts at 0). */
  durationInFrames: number;
  /** The sung lines inside this scene, with local start/end frames. */
  lines: MotifLine[];
  /** Voice loudness 0..1 at a local frame (smoothed). */
  voice: (localFrame: number) => number;
  /** Sung pitch in semitones above Sa at a local frame, or null in silence. */
  pitch: (localFrame: number) => number | null;
};
