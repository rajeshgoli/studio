"""Read-only talking productions and their narrowly scoped file policy."""
import fnmatch
import json
import re
from pathlib import Path
from urllib.parse import quote

from .productions import ID
from .viewer import publishing


def safe_relative(value):
    return (isinstance(value, str) and bool(value)
            and all(p and not p.startswith('.') and '\\' not in p
                    for p in value.split('/')))


def matches(relative, pattern):
    # Match one path component at a time: '*' must never include a slash.
    return (safe_relative(pattern) and '**' not in pattern
            and len(relative.split('/')) == len(pattern.split('/'))
            and all(fnmatch.fnmatchcase(p, rule)
                    for p, rule in zip(relative.split('/'), pattern.split('/'))))


class Talks:
    def __init__(self, root):
        self.root = Path(root)

    def config(self, pid):
        if not ID.fullmatch(pid):
            raise FileNotFoundError(pid)
        folder = self.root / 'talks' / pid
        path = folder / 'production.json'
        if folder.resolve() != folder or path.resolve() != path:
            raise FileNotFoundError(pid)
        config = json.loads(path.read_text())
        if not isinstance(config, dict):
            raise ValueError('production must be an object')
        return folder, config

    @staticmethod
    def allowed(relative, config):
        if not safe_relative(relative):
            return False
        parts = relative.split('/')
        takes = config.get('takes_dir', 'takes')
        if (safe_relative(takes) and relative.startswith(takes + '/')
                and len(parts) == len(takes.split('/')) + 1
                and Path(relative).suffix in {'.wav', '.mp4', '.json'}):
            return True
        if relative == config.get('publish'):
            return True
        patterns = config.get('renders', [])
        return isinstance(patterns, list) and any(matches(relative, p) for p in patterns)

    def file(self, pid, relative):
        folder, config = self.config(pid)
        if not self.allowed(relative, config):
            raise FileNotFoundError(relative)
        resolved = (folder / relative).resolve()
        if (not resolved.is_relative_to(folder) or not resolved.is_file()
                or not self.allowed(resolved.relative_to(folder).as_posix(), config)):
            raise FileNotFoundError(relative)
        return resolved

    def asset(self, pid, relative):
        try:
            path = self.file(pid, relative)
            stat = path.stat()
            return dict(name=Path(relative).name, path=relative,
                        url=f'/file/talk:{pid}/{quote(relative)}',
                        modified=stat.st_mtime, bytes=stat.st_size)
        except (OSError, ValueError):
            return None

    def renders(self, pid, folder, config):
        patterns = config.get('renders', [])
        names = set()
        for pattern in patterns if isinstance(patterns, list) else []:
            if not safe_relative(pattern) or '**' in pattern:
                continue
            for path in folder.glob(pattern):
                names.add(path.relative_to(folder).as_posix())
        return sorted(filter(None, (self.asset(pid, n) for n in names)),
                      key=lambda a: (-a['modified'], a['path']))

    def list(self):
        result = []
        for path in sorted((self.root / 'talks').glob('*/production.json')):
            try:
                pid = path.parent.name
                folder, config = self.config(pid)
                media = self.renders(pid, folder, config)
                result.append(dict(id=pid, kind='talk', title=str(config.get('title', pid)),
                                   newest_render=media[0] if media else None))
            except (OSError, ValueError):
                continue
        return result

    def detail(self, pid):
        folder, config = self.config(pid)
        parts = config.get('parts', [])
        parts = [p for p in parts if isinstance(p, str)] if isinstance(parts, list) else []
        groups = {p: [] for p in parts}
        takes = config.get('takes_dir', 'takes')
        if safe_relative(takes):
            names = set()
            for path in (folder / takes).glob('*'):
                match = re.fullmatch(r'((?:[a-zA-Z0-9_][a-zA-Z0-9_-]*_)?take\d+)(?:_mic\.wav|_phone\.mp4|\.json)', path.name)
                if match:
                    names.add(match[1])
            for name in sorted(names, reverse=True):
                mic = self.asset(pid, f'{takes}/{name}_mic.wav')
                phone = self.asset(pid, f'{takes}/{name}_phone.mp4')
                if not mic and not phone:
                    continue
                try:
                    meta = json.loads(self.file(pid, f'{takes}/{name}.json').read_text())
                    labels = meta.get('parts', []) if isinstance(meta, dict) else []
                except (OSError, ValueError):
                    labels = []
                labels = [p for p in labels if isinstance(p, str) and p in groups] if isinstance(labels, list) else []
                if not labels:
                    prefix = name.rsplit('_take', 1)[0] if '_take' in name else None
                    sessions = config.get('sessions', {})
                    fallback = sessions.get(prefix, []) if isinstance(sessions, dict) else []
                    if prefix in groups:
                        labels = [prefix]
                    elif isinstance(fallback, list):
                        labels = [p for p in fallback if isinstance(p, str) and p in groups]
                    camera = config.get('camera_parts', [])
                    if not prefix and isinstance(camera, list) and len(camera) == 1 and isinstance(camera[0], str) and camera[0] in groups:
                        labels = camera
                for label in dict.fromkeys(labels or ['Unassigned']):
                    groups.setdefault(label, []).append(dict(name=name, mic=mic, phone=phone))
        try:
            text = self.file(pid, config.get('publish', '')).read_text()
        except (OSError, ValueError):
            text = ''
        return dict(id=pid, title=str(config.get('title', pid)),
                    parts=[dict(name=p, takes=rows) for p, rows in groups.items()],
                    renders=self.renders(pid, folder, config), publishing=publishing(text))
