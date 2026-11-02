"""Read-only, bounded access to the sm queue."""
import json
import re
import subprocess
import threading
import time

PREFIXES = ('song-', 'talk-', 'demucs-', 'sing-studio', 'magnetar')


class QueueUnavailable(Exception):
    pass


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self._at = float('-inf')
        self._jobs = []

    @staticmethod
    def _run(args):
        try:
            return subprocess.run(['sm', 'queue', *args], capture_output=True,
                                  text=True, timeout=10, check=True).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise QueueUnavailable('Job queue is unavailable. Retrying automatically.') from exc

    def list(self):
        with self._lock:
            if time.monotonic() - self._at >= 1:
                try:
                    jobs = json.loads(self._run(['list', '--all', '--json', '--limit', '50']))
                    if not isinstance(jobs, list) or any(not isinstance(j, dict) for j in jobs):
                        raise ValueError('invalid queue list')
                    self._jobs = [{key: j.get(key) for key in
                                   ('id', 'label', 'state', 'started_at', 'finished_at', 'memory_bytes')}
                                  for j in jobs[:50]]
                    self._at = time.monotonic()
                except ValueError as exc:
                    raise QueueUnavailable('Job queue returned an unreadable list.') from exc
            return [dict(j, studio=str(j.get('label') or '').startswith(PREFIXES)) for j in self._jobs]

    def log(self, job):
        # Always resolve to an ID from the fresh list; never pass user flags or labels
        # to the CLI, even when a listed label happens to start with a dash.
        jobs = self.list()
        matches = [j for j in jobs if job == j['id'] or job == j['label']]
        if len(matches) != 1 or not re.fullmatch(r'[A-Za-z0-9_]+', str(matches[0]['id'])):
            raise FileNotFoundError(job)
        return '\n'.join(self._run(['log', matches[0]['id']]).splitlines()[-200:])
