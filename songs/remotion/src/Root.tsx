import React from 'react';
import {CalculateMetadataFunction, Composition, staticFile} from 'remotion';
import {LyricShort} from './LyricShort';
import {Timeline} from './types';
import {Thumbnail, ThumbProps} from './Thumbnail';

type Props = {poem: string; tl: Timeline | null};

const calc: CalculateMetadataFunction<Props> = async ({props}) => {
  const tl: Timeline = await (await fetch(staticFile(`${props.poem}/timeline.json`))).json();
  return {durationInFrames: tl.durationInFrames, fps: tl.fps, width: tl.width, height: tl.height, props: {...props, tl}};
};

const calcThumb: CalculateMetadataFunction<ThumbProps> = async ({props}) => {
  const tl: Timeline = await (await fetch(staticFile(`${props.poem}/timeline.json`))).json();
  return {durationInFrames: tl.durationInFrames, fps: tl.fps, width: tl.width, height: tl.height, props: {...props, tl}};
};

export const Root: React.FC = () => (
  <>
  <Composition id="Thumbnail" component={Thumbnail as React.FC<ThumbProps>} calculateMetadata={calcThumb}
    defaultProps={{poem: 'demo', tl: null, at: 0, headline: 'Headline', sub: 'Subtitle'}}
    durationInFrames={1} fps={30} width={1080} height={1920} />
  <Composition id="LyricShort" component={LyricShort as React.FC<Props>} calculateMetadata={calc}
    defaultProps={{poem: 'demo', tl: null}} durationInFrames={300} fps={30} width={1080} height={1920} />
  </>
);
