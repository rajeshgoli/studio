"""Song discovery and the viewer's explicit file allowlist."""
import json
import os
import re
from pathlib import Path

ID = re.compile(r"[a-z0-9_]{1,64}")
EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".png", ".jpg", ".json", ".md"}
TOP_FILES = {"vocals.wav", "poem.json", "marks.json", "timing.json", "youtube.md"}


def content_root():
    return Path(os.environ.get("STUDIO_CONTENT", Path(__file__).resolve().parents[2] / "studio-content")).expanduser().resolve()


class Productions:
    def __init__(self, root=None):
        self.root = Path(root).resolve() if root is not None else content_root()

    def song_dir(self, pid):
        if not ID.fullmatch(pid):
            raise FileNotFoundError(pid)
        path = self.root / "songs" / pid
        # A production cannot redirect discovery outside the content checkout.
        if path.resolve() != path or not (path / "poem.json").is_file():
            raise FileNotFoundError(pid)
        if (path / "poem.json").resolve().parent != path:
            raise FileNotFoundError(pid)
        return path

    def list(self):
        result = []
        for path in sorted((self.root / "songs").glob("*/poem.json")):
            try:
                folder = self.song_dir(path.parent.name)
                poem = json.loads((folder / "poem.json").read_text())
                title = poem.get("title", folder.name)
                result.append({"id": folder.name, "kind": "song", "title": str(title)})
            except (OSError, ValueError, AttributeError):
                continue
        return result

    @staticmethod
    def allowed(parts):
        if not parts or any(not p or p.startswith(".") or "\\" in p for p in parts):
            return False
        if Path(parts[-1]).suffix not in EXTENSIONS:
            return False
        if len(parts) == 1:
            return parts[0] in TOP_FILES
        if parts[0] in {"takes", "reference"}:
            return len(parts) == 2
        if parts[0] == "build":
            return len(parts) == 2 or (len(parts) == 3 and parts[1] in {"options", "thumbnails"})
        return False

    def file(self, pid, relative):
        song = self.song_dir(pid)
        parts = relative.split("/")
        if not self.allowed(parts):
            raise FileNotFoundError(relative)
        base = self.root / "build" / pid if parts[0] == "build" else song
        path = base.joinpath(*(parts[1:] if parts[0] == "build" else parts))
        resolved = path.resolve()
        # Validate the target's policy too: a link must not expose deleted takes,
        # intermediate build files, hidden files, or another production.
        if not resolved.is_relative_to(base) or base.resolve() != base:
            raise FileNotFoundError(relative)
        target = list(resolved.relative_to(base).parts)
        if parts[0] == "build":
            target.insert(0, "build")
        if not self.allowed(target) or not resolved.is_file():
            raise FileNotFoundError(relative)
        return resolved
