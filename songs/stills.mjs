// Render a handful of frames fast (bundle once, renderStill in a loop), then tile a contact sheet.
// usage: node stills.mjs <poem> <out_dir> <t1> <t2> ...   (times in seconds; "s3" = middle of scene 3)
import {createRequire} from 'module';
import path from 'path';
import fs from 'fs';
import {execFileSync} from 'child_process';
const here = path.dirname(new URL(import.meta.url).pathname);
const req = createRequire(path.join(here, 'remotion/package.json'));
const {bundle} = req('@remotion/bundler');
const {renderStill, selectComposition} = req('@remotion/renderer');
const [poem, outDir, ...times] = process.argv.slice(2);
fs.mkdirSync(outDir, {recursive: true});
const tl = JSON.parse(fs.readFileSync(path.join(here, 'remotion/public', poem, 'timeline.json')));
const serveUrl = await bundle({entryPoint: path.join(here, 'remotion/src/index.ts')});
const inputProps = {poem, tl: null};
const composition = await selectComposition({serveUrl, id: 'LyricShort', inputProps});
const files = [];
for (const t of times) {
  let sec = t.startsWith('s') ? (() => { const s = tl.scenes[+t.slice(1)]; return (s.start + s.end) / 2; })() : +t;
  const frame = Math.min(composition.durationInFrames - 1, Math.round(sec * tl.fps));
  const out = path.join(outDir, `f${String(frame).padStart(5, '0')}.png`);
  await renderStill({composition, serveUrl, output: out, frame, inputProps});
  files.push([out, `${t} (${sec.toFixed(1)}s)`]);
}
execFileSync(path.join(here, '.venv/bin/python'), [path.join(here, 'sheet.py'), path.join(outDir, 'sheet.png'), ...files.flat()], {stdio: 'inherit'});
