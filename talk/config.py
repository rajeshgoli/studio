"""Validate private production configuration before opening devices."""
from pathlib import Path
import re

NAME = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}')


def safe_path(folder, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('expected a production-relative path')
    if any(p in {'.', '..'} or p.startswith('.') for p in relative.split('/')):
        raise ValueError('invalid production-relative path')
    path = folder / relative
    if path.resolve() != path or not path.is_relative_to(folder):
        raise ValueError('production paths must not follow symbolic links')
    return path


def choices(config):
    parts = config['parts']
    sessions = config['sessions']
    camera = config['camera_parts']
    if (not isinstance(parts, list) or not parts or
            any(not isinstance(p, str) or not NAME.fullmatch(p) for p in parts)
            or len(set(parts)) != len(parts)):
        raise ValueError('parts must be distinct names')
    if not isinstance(sessions, dict) or not isinstance(camera, list) or any(p not in parts for p in camera):
        raise ValueError('invalid sessions or camera parts')
    result = [(p, p + (' (camera)' if p in camera else ' (audio)')) for p in parts]
    for name, group in sessions.items():
        if (not NAME.fullmatch(name) or name in parts or not isinstance(group, list)
                or not group or any(p not in parts for p in group) or len(set(group)) != len(group)):
            raise ValueError('invalid session')
        result.append((name, name))
        result.extend((name + '@' + p, name + ' from ' + p) for p in group[1:])
    return result
