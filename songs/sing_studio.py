#!/usr/bin/env python3
"""Singing studio in one browser page: a guide in your earbud, the fifine recording, the lyrics on screen.

  Start take      the mic starts recording. Say the spoken hook now, if the poem has one.
  Start guide     the guide starts in your earbud: the original song, the original with the voice removed (karaoke,
                  from reference/<name>_no_vocals.wav, made with Demucs), a tanpura on its Sa, or a mix.
  Next line       scroll as you START each line: the page lights it up and the take remembers when it began
                  (scroll up to undo one). After the last line, one more scroll stops and saves the take to
                  $STUDIO_CONTENT/songs/<song>/takes/takeNN.wav (+ .json with the guide start and the line starts).
  Mark lines      for a take that's already vocals.wav: it plays back in your earbud and you scroll at each line
                  start. The marks go to $STUDIO_CONTENT/songs/<song>/marks.json, which analyze.py uses for the line timing.
  Use for video   copies that take to $STUDIO_CONTENT/songs/<song>/vocals.wav (the old one is kept in takes/) and points the spoken
                  hook at the time the guide started, so `./render.sh <poem> --retime` picks it all up.
The mouse wheel is the remote, because a click would be heard on the take: wheel down (or Enter / →) is the next
step, wheel up (or ←) undoes a line mark. The page doesn't scroll; while idle, the wheel over the lyrics box scrolls
the lyrics instead of starting a take. Preview guide plays the guide without recording. Esc aborts; T test beep.
Marks don't need to be exact: analyze.py snaps each one to the nearest breath.

The guide's Sa comes from the poem's reference recording (poem.json music.reference): the tanpura is tuned to it,
with a Ma string when the raga has no Pa. Singing with it in your ear keeps the take on one Sa, which is what lets
the generated score sit under it.

Run:  .venv/bin/python sing_studio.py <song> [--ear EarFun] [--mic fifine]   then open http://localhost:9400
"""

import argparse
import sys
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.media import playable, _send_audio

PORT = 9400
from songs.sing_room import Studio, beep, make_page as room_page


def make_page(studio):
    # The legacy launcher remains usable until its separate retirement ticket.
    return room_page(studio).replace("/room/sing/", "/")


def make_handler(studio):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        _send_audio = _send_audio

        def do_GET(self):
            if self.path == "/":
                self._send(make_page(studio).encode(), "text/html; charset=utf-8")
            elif self.path == "/state":
                self._send(json.dumps(studio.state()).encode(), "application/json")
            elif self.path == "/outputs":
                self._send(json.dumps(studio.outputs()).encode(), "application/json")
            elif self.path.startswith("/take/"):
                f = studio.takes_dir / self.path.split("/")[-1]
                if f.exists() and f.suffix == ".wav":
                    self._send_audio(playable(f))
                else:
                    self._send(b"", "text/plain", 404)
            else:
                self._send(b"", "text/plain", 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            a = self.path.strip("/")
            if a == "step":
                studio.step()
            elif a == "preview":
                studio.preview()
            elif a == "abort":
                studio.abort()
            elif a == "back":
                studio.back()
            elif a == "mark":
                studio.start_marking()
            elif a == "beep" and studio.ear and studio.stage == "idle":
                studio.ear.play(beep())
            elif a == "ear":
                studio.set_ear(body["name"])
            elif a == "rescan":
                studio.rescan()
            elif a == "delete" and studio.stage == "idle":
                studio.delete_take(body["name"])
            elif a == "use":
                studio.use_take(body["name"])
            elif a == "set" and studio.stage == "idle":
                studio.mode = body.get("mode", studio.mode)
                studio.start_at = float(body.get("start_at", studio.start_at))
                studio.mix_orig = float(body.get("mix", studio.mix_orig))
                if "gain" in body and studio.ear:
                    studio.ear.gain = float(body["gain"])
            elif a == "set" and "gain" in body and studio.ear:
                studio.ear.gain = float(body["gain"])
            self._send(b"{}", "application/json")
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("poem")
    ap.add_argument("--ear", default="EarFun", help="earbud output device, any part of its name")
    ap.add_argument("--mic", default="fifine", help="USB mic, any part of its name")
    a = ap.parse_args()
    studio = Studio(a.poem, a.ear, a.mic)
    print(f"{studio.note}  Earbud: {studio.ear_name or 'not found (connect it, then Rescan devices)'}")
    print(f"open http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(studio)).serve_forever()


if __name__ == "__main__":
    main()
