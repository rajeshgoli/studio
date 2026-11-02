"""Local room lifecycle and validated singing commands (no audio imports at startup)."""
import json
import math
import re
import socket

TAKE = re.compile(r"take[0-9]{2,3}")


class RoomConflict(Exception):
    pass


def legacy_running():
    try:
        with socket.create_connection(("127.0.0.1", 9400), timeout=0.2):
            return True
    except ConnectionRefusedError:
        return False


def open_singing(productions, body):
    if body.get("kind") != "sing":
        raise ValueError("kind must be sing")
    pid = body.get("production")
    if not isinstance(pid, str):
        raise ValueError("production must name a listed song")
    folder = productions.song_dir(pid)
    # Room writes must never follow a takes directory into another production.
    if (folder / "takes").resolve() != folder / "takes":
        raise ValueError("takes must not be a symbolic link")
    if legacy_running():
        raise RoomConflict("An old studio is answering on port 9400; close it first")
    try:
        config = json.loads((productions.root / "studio.json").read_text())
        mic, ear = config["mic"], config["ear"]
        if not all(isinstance(n, str) and n.strip() for n in (mic, ear)):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('studio.json must provide nonempty "mic" and "ear" device names')
    from songs.sing_room import Studio
    return Studio(pid, ear, mic, content=productions.root)


def take_path(room, name, extension=".wav"):
    if not isinstance(name, str) or not TAKE.fullmatch(name):
        raise ValueError("name must match takeNN or takeNNN")
    path = room.takes_dir / (name + extension)
    if path.resolve() != path or not path.is_file():
        raise ValueError("take does not exist or is a symbolic link")
    return path


def command(room, action, body):
    if action in {"step", "back", "preview", "mark", "abort", "rescan"}:
        if body:
            raise ValueError("this action takes no arguments")
        getattr(room, "start_marking" if action == "mark" else action)()
    elif action == "beep":
        from .devices import beep
        if room.ear and room.stage == "idle":
            room.ear.play(beep())
    elif action == "ear":
        if body.get("name") not in room.outputs():
            raise ValueError("ear must be a name from outputs")
        room.set_ear(body["name"])
    elif action in {"use", "delete"}:
        if room.stage != "idle":
            raise RoomConflict("Finish or abort the current activity first")
        name = body.get("name")
        take_path(room, name)
        take_path(room, name, ".json")
        getattr(room, action + "_take")(name)
    elif action == "set":
        if not body or body.keys() - {"mode", "start_at", "mix", "gain"}:
            raise ValueError("unknown or empty settings")
        if "mode" in body and body["mode"] not in {"both", "original", "karaoke+tanpura", "karaoke", "tanpura"}:
            raise ValueError("unknown guide mode")
        for key, low, high in (("start_at", 0, len(room.tan) / 48000 - 1 / 48000),
                               ("mix", 0.2, 1), ("gain", 0.1, 1.5)):
            if key in body:
                value = body[key]
                if (type(value) not in (int, float) or not math.isfinite(value)
                        or not low <= value <= high):
                    raise ValueError(f"{key} must be between {low:g} and {high:g}")
        if room.stage == "idle":
            room.mode = body.get("mode", room.mode)
            room.start_at = body.get("start_at", room.start_at)
            room.mix_orig = body.get("mix", room.mix_orig)
        if "gain" in body and room.ear:
            room.ear.gain = body["gain"]
    else:
        raise FileNotFoundError(action)
