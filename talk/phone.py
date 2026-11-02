"""Fixed Android debugging-tool operations; never accepts a command from HTTP."""
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

VIDEO = re.compile(r'[A-Za-z0-9_.-]+\.mp4')


class Phone:
    def __init__(self, config):
        self.package = config['camera_package']
        self.tap = config['record_tap']
        self.dcim = config['dcim']
        self.size = config['preview_size']
        serial = config.get('serial')
        if not isinstance(self.package, str) or not re.fullmatch(r'[A-Za-z0-9_.]+', self.package):
            raise ValueError('invalid camera package')
        if not isinstance(self.dcim, str) or not re.fullmatch(r'/[A-Za-z0-9_/-]+', self.dcim) or '..' in self.dcim:
            raise ValueError('invalid camera folder')
        for pair in (self.tap, self.size):
            if not isinstance(pair, list) or len(pair) != 2 or any(type(n) is not int or not 0 <= n <= 16384 for n in pair):
                raise ValueError('phone coordinates and preview size must be integer pairs')
        if not all(self.size):
            raise ValueError('preview size must be positive')
        if serial is not None and (not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]*', serial)):
            raise ValueError('invalid phone serial')
        self.base = ['adb'] + (['-s', serial] if serial else [])
        self.pulling = False

    def _run(self, *args, binary=False, timeout=5):
        return subprocess.run(self.base + list(args), capture_output=True, text=not binary,
                              check=True, timeout=timeout).stdout

    def connected(self):
        try:
            return self._run('get-state').strip() == 'device'
        except (OSError, subprocess.SubprocessError):
            return False

    def check_camera(self):
        if not self.connected():
            raise RuntimeError('no phone: connect the phone and allow Android debugging')
        top = self._run('shell', 'dumpsys', 'activity', 'activities')
        if self.package not in next((line for line in top.splitlines() if 'topResumedActivity' in line), ''):
            raise RuntimeError('The phone is not on the camera. Open its video camera, then try again.')

    def toggle_record(self):
        self._run('shell', 'input', 'tap', *map(str, self.tap))

    def newest_video(self):
        entries = self._run('shell', 'ls', '-t', self.dcim).splitlines()
        if not entries or not VIDEO.fullmatch(entries[0]):
            raise ValueError('newest phone file is not a safe MP4 filename')
        return entries[0]

    def pull_video(self, name, destination):
        if not isinstance(name, str) or not VIDEO.fullmatch(name):
            raise ValueError('invalid phone video filename')
        self.pulling = True
        try:
            # Download privately, then reserve the final filename without overwriting a take.
            with tempfile.TemporaryDirectory(prefix='studio-phone-', dir=destination.parent) as temp:
                downloaded = Path(temp) / 'phone.mp4'
                self._run('pull', self.dcim.rstrip('/') + '/' + name, str(downloaded), timeout=600)
                with downloaded.open('rb') as source, destination.open('xb') as target:
                    shutil.copyfileobj(source, target)
        finally:
            self.pulling = False

    def preview(self):
        if not self.connected():
            raise RuntimeError('no phone')
        raw = self._run('exec-out', 'screencap', binary=True)
        if len(raw) < 16:
            raise ValueError('incomplete phone picture')
        w, h, fmt = map(int, np.frombuffer(raw[:12], '<u4'))
        if not 0 < w <= 16384 or not 0 < h <= 16384 or fmt not in (1, 2):
            raise ValueError('unsupported phone picture')
        offset = len(raw) - w * h * 4
        if offset not in (12, 16):
            raise ValueError('incomplete phone pixels')
        pixels = np.frombuffer(raw[offset:], np.uint8).reshape(h, w, 4)[::3, ::3, :3]
        picture = Image.fromarray(np.ascontiguousarray(pixels))
        picture.thumbnail(tuple(self.size))
        out = io.BytesIO()
        picture.save(out, 'JPEG', quality=70)
        return out.getvalue()
