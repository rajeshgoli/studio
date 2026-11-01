// Render thumbnail candidates: node thumbs.mjs <poem> <out_dir> '<json list of {at, headline, sub, name}>'
import {createRequire} from 'module';
import path from 'path';
import fs from 'fs';
const here = path.dirname(new URL(import.meta.url).pathname);
const req = createRequire(path.join(here, 'remotion/package.json'));
const {bundle} = req('@remotion/bundler');
const {renderStill, selectComposition} = req('@remotion/renderer');
const [poem, outDir, list] = process.argv.slice(2);
fs.mkdirSync(outDir, {recursive: true});
const serveUrl = await bundle({entryPoint: path.join(here, 'remotion/src/index.ts')});
for (const c of JSON.parse(list)) {
  const inputProps = {poem, tl: null, ...c};
  const composition = await selectComposition({serveUrl, id: 'Thumbnail', inputProps});
  const out = path.join(outDir, `${c.name}.png`);
  await renderStill({composition, serveUrl, output: out, frame: Math.round(c.at * 30), inputProps});
  console.log(out);
}
