"""Song metadata read through the same allowlist as served media."""
import json
import re
from pathlib import Path
from urllib.parse import quote


def read_json(productions, pid, relative):
    try:
        value = json.loads(productions.file(pid, relative).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def asset(productions, pid, relative):
    try:
        path = productions.file(pid, relative)
        stat = path.stat()
        return dict(name=Path(relative).name, path=relative,
                    url=f'/file/{pid}/{quote(relative)}',
                    modified=stat.st_mtime, bytes=stat.st_size)
    except OSError:
        return None


def renders(productions, pid):
    base = productions.root / 'build' / pid
    names = [f'build/{pid}_short.mp4']
    names += [f'build/options/{p.name}' for p in (base / 'options').glob('*')
              if p.suffix in {'.mp4', '.wav'}]
    return sorted(filter(None, (asset(productions, pid, n) for n in names)),
                  key=lambda a: (-a['modified'], a['path']))


def publishing(text):
    blocks = {}
    for match in re.finditer(r'^##\s+([^\n]+)\n(.*?)(?=^##\s|\Z)', text, re.M | re.S):
        heading, body = match.groups()
        for key in ('title', 'description'):
            if heading.strip().lower().startswith(key):
                blocks[key] = body.strip()
    return dict(text=text, title=blocks.get('title', ''), description=blocks.get('description', ''))


def song(productions, pid):
    folder = productions.song_dir(pid)
    poem = read_json(productions, pid, 'poem.json')
    marks = read_json(productions, pid, 'marks.json')
    timing = read_json(productions, pid, 'timing.json')
    takes = []
    vocals = asset(productions, pid, 'vocals.wav')
    for path in sorted((folder / 'takes').glob('take*.json'), reverse=True):
        if not re.fullmatch(r'take\d{2,3}', path.stem):
            continue
        meta = read_json(productions, pid, f'takes/{path.name}')
        if not meta:
            continue
        audio = asset(productions, pid, f'takes/{path.stem}.wav')
        takes.append(dict(name=path.stem, seconds=meta.get('seconds'), peak_dbfs=meta.get('peak_dbfs'),
                          guide=meta.get('guide'), sa_hz=meta.get('sa_hz'), audio=audio,
                          in_use=bool(audio and vocals and audio['bytes'] == vocals['bytes']
                                      == marks.get('vocals_bytes'))))
    images = [asset(productions, pid, 'build/contact_sheet.png')]
    images += [asset(productions, pid, f'build/thumbnails/{p.name}')
               for p in sorted((productions.root / 'build' / pid / 'thumbnails').glob('*'))
               if p.suffix in {'.png', '.jpg'}]
    try:
        text = productions.file(pid, 'youtube.md').read_text()
    except (OSError, ValueError):
        text = ''
    lines = poem.get('lines', [])
    lines = [line for line in lines if isinstance(line, dict)] if isinstance(lines, list) else []
    # Video order follows sung, which may repeat a line.
    by_id = {line['id']: line for line in lines if isinstance(line.get('id'), str)}
    order = poem.get('sung')
    if isinstance(order, list) and order and all(isinstance(i, str) and i in by_id for i in order):
        lines = [by_id[i] for i in order]
    return dict(id=pid, title=str(poem.get('title', pid)), lines=lines, takes=takes,
                vocals=vocals, marks=marks, timing=timing, renders=renders(productions, pid),
                images=list(filter(None, images)), publishing=publishing(text))


def page():
    return Path(__file__).with_name('viewer.html').read_text()
