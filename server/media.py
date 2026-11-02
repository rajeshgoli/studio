"""Bounded-memory file streaming, byte ranges, and a disk-backed 16-bit WAV cache."""
import io
import mimetypes
import re
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

_cache = OrderedDict()
_lock = threading.Lock()
_cache_dir = None


def _open_playable(path):
    global _cache_dir
    path = Path(path).resolve()
    stat = path.stat()
    key = (path, stat.st_mtime_ns, stat.st_size)
    with _lock:
        if key not in _cache:
            import soundfile as sf  # No audio/device dependencies on viewer startup.
            if _cache_dir is None:
                _cache_dir = tempfile.TemporaryDirectory(prefix="studio-wav-")
            with tempfile.NamedTemporaryFile(dir=_cache_dir.name, suffix=".wav", delete=False) as tmp:
                output = Path(tmp.name)
            try:
                with sf.SoundFile(path) as source, sf.SoundFile(
                        output, mode="w", samplerate=source.samplerate,
                        channels=source.channels, format="WAV", subtype="PCM_16") as dest:
                    for block in source.blocks(blocksize=65536, dtype="float32"):
                        dest.write(block)
            except Exception:
                output.unlink()
                raise
            _cache[key] = output
            while len(_cache) > 8:
                _, old = _cache.popitem(last=False)
                old.unlink()
        _cache.move_to_end(key)
        return _cache[key].open("rb")


def playable(path):
    """Compatibility for the singing studio: return the take as 16-bit WAV bytes."""
    with _open_playable(path) as source:
        return source.read()


def byte_range(value, size):
    """Return inclusive bounds; reject malformed, multipart, or unsatisfiable ranges."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()) or size == 0:
        raise ValueError("invalid range")
    first, last = match.groups()
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError("empty suffix")
        return max(0, size - length), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("unsatisfiable range")
    return start, end


def _send_stream(handler, source, ctype):
    source.seek(0, 2)
    size = source.tell()
    start, end, code = 0, size - 1, 200
    ranges = handler.headers.get_all("Range", [])
    if ranges:
        try:
            if len(ranges) != 1:
                raise ValueError("duplicate range")
            start, end = byte_range(ranges[0], size)
            code = 206
        except ValueError:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "private, no-cache")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    if code == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    source.seek(start)
    remaining = end - start + 1
    while remaining:
        chunk = source.read(min(65536, remaining))
        if not chunk:
            break
        handler.wfile.write(chunk)
        remaining -= len(chunk)


def _send_audio(handler, data):
    _send_stream(handler, io.BytesIO(data), "audio/wav")


def send_file(handler, path):
    source = _open_playable(path) if path.suffix == ".wav" else path.open("rb")
    with source:
        _send_stream(handler, source, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
