"""Reusable scroll-driven talking room; production data stays in the content checkout."""
import html
import json
import os
import queue
import re
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from server.devices import Devices, Ear, RATE
from .phone import Phone
from .config import safe_path, choices

REDO_WINDOW = 1.5
SILENT = "Silent (read Claude on screen)"


def open_mic(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        return sf.SoundFile(fd, "w", RATE, 1, "PCM_24", format="WAV", closefd=True)
    except Exception:
        os.close(fd)
        raise


def save_metadata(path, meta):
    with path.open('x') as out:
        out.write(json.dumps(meta, indent=2) + '\n')

class SilentEar:
    """No sound: Claude's line shows on the prompter for as long as its clip runs. For recording
    without earphones, so nothing from the speakers lands on the mic."""

    class _NoStream:
        def close(self):
            pass

    def __init__(self):
        self.stream, self.until = self._NoStream(), 0.0

    def play(self, audio):
        self.until = time.time() + len(audio) / RATE

    def stop(self):
        self.until = 0.0

    def busy(self):
        return time.time() < self.until

    def close(self):
        self.stop()

    def wait(self):
        while self.busy():
            time.sleep(0.05)


class Studio(Devices):
    """Scroll-driven: each scroll down means "I finished my line". A Claude line plays
    its clip when the prompter reaches it; when Claude finishes, the prompter moves on."""
    kind = "talk"

    def __init__(self, folder, config, devices):
        self.folder, self.config = folder, config
        self.mic_name = devices['mic']
        ear_name = devices['ear']
        self.phone = Phone(devices['phone'])
        self.script_dir = safe_path(folder, config['script_dir'])
        self.takes_dir = safe_path(folder, config['takes_dir'])
        self.choices = choices(config)
        self.set_session(self.choices[0][0])
        self._closed = threading.Event()
        self.capture_lock = threading.Lock()
        self.write_error = None
        self.run_id = 0
        self.save_thread = None
        self.ear_for = {True: SILENT, False: ear_name}   # by self.video: no earbud on camera, earbuds for audio
        self.want_ear = self.ear_for[self.video]
        self.ear, self.ear_name = None, None
        self.clips, self.missing = self.load_clips()
        self.lock = threading.Lock()
        self.stage = "idle"          # idle | rolling | saving
        self.line = 0
        self.claude_playing = False
        self.take = None
        self.take_t0 = None
        self.events = []
        self.frames = 0
        self.level = -90.0
        self.peak = -90.0
        self.out = None
        self.recording = False
        self.q = queue.Queue()
        self.note = ""
        self.line_t0 = 0.0             # when the current line of yours started (or restarted)
        self.backed = (0.0, "")        # last scroll up: (time, "redo" | "previous")
        self.start_line = 0            # click a line while idle to start the next take there (a pickup)
        self.rehearse = False        # rehearsal: Claude plays and the prompter runs, nothing is recorded
        self.takes = self._scan_takes()
        self.preview = None
        self.last_cb = 0.0
        self.mic_restarts = 0
        self.mic = None
        try:
            self._open_ear()
            self._open_mic()
        except Exception:
            if self.mic:
                self.mic.close()
            if self.ear:
                self.ear.close()
            raise
        self.threads = [threading.Thread(target=fn, daemon=True) for fn in
                        (self._watchdog, self._preview_loop, self._writer)]
        for thread in self.threads:
            thread.start()

    def _open_ear(self):
        """The output asked for (any part of its name), else silent. Never the mic's own headphone
        jack: closing an output stream on the mic's device kills the mic's input stream on macOS."""
        outs = super().outputs()
        if self.want_ear == SILENT:
            name = SILENT
        else:
            name = next((o for o in outs if self.want_ear.lower() in o.lower()), SILENT)
        if name == self.ear_name:
            return
        if self.ear is not None:
            self.ear.close()
        self.ear, self.ear_name = (SilentEar() if name == SILENT else Ear(name)), name

    def outputs(self):
        return [SILENT] + super().outputs()

    def mic_alive(self):
        return time.time() - self.last_cb < 0.5

    def _rescan(self):
        # Called with the room lock already held.
        self.mic.close()
        self.ear.close()
        self.ear, self.ear_name = None, None
        sd._terminate()
        sd._initialize()
        self._open_mic()
        self._open_ear()

    def _want_missing(self):
        return self.want_ear != SILENT and self.want_ear.lower() not in (self.ear_name or "").lower()

    def set_ear(self, name):
        with self.lock:
            if self.stage == "idle":
                self.want_ear = self.ear_for[self.video] = name
                self._open_ear()

    def switch(self, choice):
        with self.lock:
            if self.stage != "idle":
                return
            self.set_session(choice)
            self.want_ear = self.ear_for[self.video]
            self._open_ear()
            self.clips, self.missing = self.load_clips()
            self.takes, self.line, self.note, self.preview = self._scan_takes(), 0, "", None
            self.start_line = 0

    # ---- audio ---------------------------------------------------------------
    def _on_audio(self, indata, n, t, status):
        with self.capture_lock:
            self._capture(indata, n)

    def _capture(self, indata, n):
        self.last_cb = time.time()
        x = indata[:, 0]
        p = float(np.abs(x).max())
        self.level = max(20 * np.log10(p + 1e-9), self.level - 3)  # meter with a little fall-off
        if self.recording:
            self.q.put(x.copy())
            self.frames += n
            self.peak = max(self.peak, 20 * np.log10(p + 1e-9))

    def _writer(self):
        while True:
            block = self.q.get()
            if block is False:
                return
            try:
                if block is None:
                    self.out.close()
                    self.out = None
                elif self.write_error is None:
                    self.out.write(block)
            except Exception as exc:
                self.write_error = str(exc)
                if block is None:
                    self.out = None

    def _preview_loop(self):
        while not self._closed.is_set():
            if self.video:
                try:
                    self.preview = self.phone.preview()
                except Exception:
                    self.preview = None
            self._closed.wait(1.5 if self.stage == 'rolling' else .5)

    # ---- the wheel -----------------------------------------------------------
    def _log(self, kind):
        l = self.lines[self.line]
        self.events.append({"line": self.line, "part": l["part"], "idx": l["idx"], "event": kind,
                            "sample": self.frames})

    def step(self, direction):
        with self.lock:
            if self.stage == "idle":
                if direction > 0:
                    self._start_take()
                return
            if self.stage != "rolling" or self.claude_playing:
                return
            if direction < 0:
                now = time.time()
                if now - self.line_t0 > REDO_WINDOW:
                    self.backed = (now, "redo")       # first scroll up: this line again
                else:
                    prev = [k for k in range(self.line) if self.lines[k]["speaker"] == "RAJESH"]
                    if prev:                          # a second one soon after: your previous line
                        self.line = prev[-1]
                        self.backed = (now, "previous")
                    else:
                        self.backed = (now, "redo")   # nothing of yours before this: redo it
                self.line_t0 = now
                self._log("back")
                return
            if self.line == len(self.lines) - 1:
                self._log("end")
                threading.Thread(target=self._cut, args=(self.run_id, 1.5), daemon=True).start()
                return
            self.line += 1
            self._enter_line()

    def _enter_line(self):
        if self.lines[self.line]["speaker"] == "CLAUDE":
            self.claude_playing = True
            self._log("claude")
            self.ear.play(self.clips[self.line])
            threading.Thread(target=self._after_claude, args=(self.run_id, self.line), daemon=True).start()
        else:
            self.line_t0 = time.time()
            self._log("rajesh")

    def _after_claude(self, take, line):
        time.sleep(0.2)
        while self.ear.busy():
            if self._closed.wait(.05) or self.run_id != take:
                return
        time.sleep(0.4)
        with self.lock:
            if self.stage != "rolling" or self.run_id != take or self.line != line:
                return
            self.claude_playing = False
            if line < len(self.lines) - 1:
                self.line += 1
                self._enter_line()       # Claude's next line chains on; your next line just appears

    def abort(self):
        with self.lock:
            if self.stage == "rolling":
                self._log("abort")
                self._stop()

    def _cut(self, take, hold):
        time.sleep(hold)
        with self.lock:
            if self.stage == "rolling" and self.run_id == take:
                self._stop()

    def _stop(self):
        self.ear.stop()
        self.claude_playing = False
        if self.take == "rehearsal":
            self.stage = "idle"
            return
        self.stage = "saving"
        try:
            if self.video:
                self.phone.toggle_record()
        except Exception as exc:
            self.note = f"Phone stop failed: {exc}. Check the phone's record button."
        finally:
            with self.capture_lock:
                self.recording = False
                self.q.put(None)
            self.save_thread = threading.Thread(target=self._save, daemon=True)
            self.save_thread.start()

    def _start_take(self):
        self.clips, self.missing = self.load_clips()
        self.run_id += 1
        if self._want_missing():
            self._rescan()           # the earbuds may have connected since the studio started
        if not self.mic_alive():
            self.note = "The mic isn't sending audio yet (reconnecting). Check the mic's USB cable, then scroll again."
            return
        if self.missing:
            self.note = f"{len(self.missing)} Claude clips aren't generated yet (first: {self.missing[0]}). Try again once they are."
            return
        if self.rehearse:
            self.take, self.frames, self.note, self.events = "rehearsal", 0, "", []
            self.take_t0 = time.time()
            self.stage, self.line = "rolling", self.start_line
            self._enter_line()
            return
        if self.video:
            try:
                self.phone.check_camera()
            except Exception as exc:
                self.note = str(exc)
                return
        self.takes_dir.mkdir(parents=True, exist_ok=True)
        self.take = self.next_take()
        self.frames, self.peak, self.note, self.events = 0, -90.0, "", []
        self.out = open_mic(self.takes_dir / f"{self.take}_mic.wav")
        self.write_error = None
        with self.capture_lock:
            self.recording = True
        try:
            if self.video:
                self.phone.toggle_record()
        except Exception as exc:
            with self.capture_lock:
                self.recording = False
                self.q.put(None)
            self.stage = 'saving'
            self.note = f"Phone start failed: {exc}. Check the phone before trying again."
            self.save_thread = threading.Thread(target=self._save, kwargs={'pull_phone': False}, daemon=True)
            self.save_thread.start()
            return
        self.take_t0 = time.time()
        self.stage, self.line = "rolling", self.start_line
        self._enter_line()           # a part can open on a Claude line (Round 1 does)

    def _save(self, pull_phone=True):
        name = self.take
        try:
            while self.out is not None:
                time.sleep(0.05)
            meta = {"mic": f"{name}_mic.wav", "parts": sorted({l["part"] for l in self.lines}, key=[l["part"] for l in self.lines].index),
                    "script": self.config["script_dir"]}
            meta.update({"rate": RATE, "mic_peak_dbfs": round(self.peak, 1), "claude_on": self.ear_name,
                    "complete": any(e["event"] == "end" for e in self.events),
                    "start_line": self.events[0]["line"] if self.events else 0,
                    "events": self.events})
            if self.write_error:
                meta['write_error'] = self.write_error
                self.note = f"Mic write failed: {self.write_error}"
            try:
                if self.video and pull_phone:
                    time.sleep(2)
                    video = self.phone.newest_video()
                    self.phone.pull_video(video, self.takes_dir / f"{name}_phone.mp4")
                    meta.update(phone=f"{name}_phone.mp4", phone_original=video)
            except Exception as exc:
                meta['phone_error'] = str(exc)
                self.note = f"Phone video was not pulled: {exc}"
            save_metadata(self.takes_dir / f"{name}.json", meta)
        except Exception as e:
            self.note = f"Saving {name} failed: {e}"
        finally:
            with self.lock:
                self.takes = self._scan_takes()
                self.stage = "idle"

    def _scan_takes(self):
        rows = []
        prefix = "take" if self.video else f"{self.label}_take"
        pattern = re.compile(re.escape(prefix) + r"[0-9]+\.json")
        try:
            entries = sorted(self.takes_dir.iterdir())
        except FileNotFoundError:
            return rows
        for j in entries:
            if not pattern.fullmatch(j.name):
                continue
            try:
                if j.is_symlink():
                    continue
                m = json.loads(j.read_text())
                mic = safe_path(self.takes_dir, m["mic"])
                secs = sf.info(mic).duration if mic.exists() else 0
                rows.append({"name": j.stem, "secs": round(secs), "peak": m.get("mic_peak_dbfs"),
                             "res": _resolution(safe_path(self.takes_dir, m["phone"])) if "phone" in m else "audio",
                             "complete": m.get("complete", True)})
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                continue
        return rows

    def state(self):
        return {
            "stage": self.stage, "take": self.take, "rehearse": self.rehearse, "start": self.start_line, "phone": self.preview is not None, "phone_note": "" if self.preview else "no phone", "mic_ok": self.mic_alive(),
            "backed": self.backed[1] if time.time() - self.backed[0] < 2 else "", "line": self.line, "note": self.note,
            "claude": self.claude_playing, "last": len(self.lines) - 1,
            "elapsed": round(time.time() - self.take_t0, 1) if self.stage == "rolling" else 0,
            "level": round(self.level, 1) if self.mic_alive() else -90.0, "peak": round(self.peak, 1),
            "takes": self.takes, "next_take": self.next_take(), "missing": len(self.missing),
            "session": self.session, "ear": self.ear_name, "want_ear": self.want_ear,
        }


    @property
    def active_stage(self):
        return "saving" if self.phone.pulling else self.stage

    def close(self):
        self.abort()
        if self.save_thread:
            self.save_thread.join()
        self._closed.set()
        self.mic.close()
        self.ear.close()
        self.q.put(False)
        for thread in self.threads:
            thread.join()

    def set_session(self, choice):
        if choice not in dict(self.choices):
            raise ValueError("unknown session")
        name, _, start = choice.partition('@')
        parts = self.config['sessions'].get(name, [name])
        if start:
            parts = parts[parts.index(start):]
        lines = []
        for part in parts:
            data = json.loads(safe_path(self.script_dir, part + '/lines.json').read_text())
            for idx, line in enumerate(data['lines']):
                lines.append({**line, 'part': part, 'idx': idx, 'card': data.get('card', [part.upper()])})
        if not lines:
            raise ValueError("session has no lines")
        self.lines = lines
        self.video = any(p in self.config['camera_parts'] for p in parts)
        self.label = name + ('-from-' + start if start else '')
        self.session = choice

    def load_clips(self):
        clips, missing = {}, []
        for idx, line in enumerate(self.lines):
            if line['speaker'] != 'CLAUDE':
                continue
            path = safe_path(self.script_dir, f"{line['part']}/clips/{line['idx']:02d}_claude.wav")
            if not path.exists():
                missing.append(f"{line['part']}/{path.name}")
                continue
            audio, rate = sf.read(path, dtype='float32', always_2d=True)
            audio = audio.mean(axis=1)
            if rate != RATE:
                audio = np.interp(np.arange(0, len(audio), rate / RATE), np.arange(len(audio)), audio).astype('float32')
            clips[idx] = np.column_stack([audio, audio])
        return clips, missing

    def next_take(self):
        prefix = 'take' if self.video else self.label + '_take'
        pattern = re.compile(re.escape(prefix) + r'([0-9]+)(?:[_.]|$)')
        numbers = [int(m.group(1)) for path in self.takes_dir.glob('*')
                   if (m := pattern.match(path.name))]
        return f"{prefix}{max(numbers, default=0) + 1:02d}"


def _resolution(path):
    try:
        import av
        with av.open(str(path)) as c:
            v = c.streams.video[0]
            return f"{v.width}x{v.height}"
    except Exception:
        return "?"


def render_line(text):
    t = html.escape(text)
    t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
    return re.sub(r"\(([^)]*)\)", r'<span class="dir">(\1)</span>', t)


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Talking Studio</title>
<style>
:root{--bg:#0b0b0d;--panel:#16161a;--fg:#f4f4f5;--dim:#8b8b93;--accent:#e07a3f;--rec:#ef4444;--ok:#22c55e;--warn:#eab308}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font-family:-apple-system,"Helvetica Neue",Arial,sans-serif}
body{display:grid;grid-template-columns:1fr 420px;grid-template-rows:auto 1fr;height:100vh}
header{grid-column:1/3;display:flex;align-items:center;gap:20px;padding:12px 20px;background:var(--panel);border-bottom:1px solid #222}
#status{font-size:22px;font-weight:700;display:flex;align-items:center;gap:10px}
.dot{width:16px;height:16px;border-radius:50%;background:#444}.dot.on{background:var(--rec);animation:blink 1s infinite}
@keyframes blink{50%{opacity:.35}}
#hint{color:var(--dim);font-size:16px}
.ln{display:inline-block;min-width:2.2em;font-size:.45em;color:#555;font-style:normal;font-weight:400;vertical-align:middle}
#startlab{font-size:15px;color:var(--dim);display:flex;gap:6px;align-items:center}
#startat{width:4.5em;background:#222;color:var(--fg);border:1px solid #444;border-radius:6px;font-size:15px;padding:4px 6px}
#rehlab{font-size:15px;color:var(--dim);display:flex;gap:6px;align-items:center}body.rehearse .dot.on{background:var(--accent)}
#micdead{display:none;position:fixed;top:64px;left:0;right:420px;z-index:5;background:var(--rec);color:#fff;font-weight:700;font-size:22px;padding:14px 20px;text-align:center}
#partsel{background:#222;color:var(--fg);border:1px solid #444;border-radius:6px;font-size:15px;padding:6px 8px}#note{color:var(--warn);font-size:16px;margin-left:auto}
main{overflow:hidden;padding:4vh 4vw;display:flex;flex-direction:column;justify-content:center;gap:2.5vh}
.line{font-size:clamp(22px,2.2vw,34px);line-height:1.3;color:#55555c;transition:all .25s}
.line.claude{font-style:italic;font-size:clamp(18px,1.6vw,24px)}
.line.claude::before{content:"CLAUDE  ";font-style:normal;font-weight:700;letter-spacing:.06em;font-size:.75em}
.line.cur{color:var(--fg);font-size:clamp(34px,3.6vw,60px);font-weight:600}
.line.cur.claude{color:var(--accent);font-size:clamp(24px,2.2vw,36px);font-weight:500}
.line.next{color:#8b8b93}
.part{font-size:14px;letter-spacing:.12em;color:var(--accent);font-weight:700;text-transform:uppercase;border-top:1px solid #333;padding-top:8px}
.face{font-size:.7em;margin-left:.3em;opacity:.8}
body.audio #phonebox{display:none}
em{color:var(--accent);font-style:normal}.dir{color:var(--dim);font-style:italic;font-weight:400}
aside{background:var(--panel);border-left:1px solid #222;padding:16px;display:flex;flex-direction:column;gap:16px;overflow:auto}
#preview{width:100%;aspect-ratio:{{PHONEASPECT}};background:#000;border-radius:8px;object-fit:contain}
#nophone{display:none;width:100%;aspect-ratio:{{PHONEASPECT}};background:#111;border:1px dashed #333;border-radius:8px;color:var(--dim);font-size:15px;align-items:center;justify-content:center}
body.nophone #preview{display:none}body.nophone #nophone{display:flex}
#earsel{width:100%;background:#222;color:var(--fg);border:1px solid #444;border-radius:6px;font-size:15px;padding:6px 8px}
h3{margin:0 0 6px;font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em}
#meter{position:relative;height:22px;background:#222;border-radius:4px;overflow:hidden}
#meterfill{height:100%;width:0;background:var(--ok)}
#zone{position:absolute;top:0;bottom:0;left:70%;width:20%;border-left:1px dashed #fff6;border-right:1px dashed #fff6}
#meterlabel{font-size:14px;color:var(--dim);margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid #222}th{color:var(--dim);font-weight:500}
.keys{font-size:14px;color:var(--dim);line-height:1.7}.keys b{color:var(--fg);background:#2a2a30;border-radius:4px;padding:1px 6px}

/* strip mode: a small movable box beside the lens with 3-4 words at a time */
body.strip{display:block;background:#000}
body.strip header,body.strip main,body.strip aside{display:none}
#strip{display:none;position:fixed;left:40%;top:40%;padding:10px 18px;background:#000;border:1px solid #333;border-radius:10px;cursor:move;user-select:none;min-width:200px}
body.strip #strip{display:block}
#strip .txt{font-weight:700;line-height:1.1;white-space:nowrap;color:#fff}
#strip .txt.claude{color:var(--accent);font-weight:500;font-style:italic;font-size:.5em}
#strip .txt .dir{font-size:.6em}
#strip .meta{display:flex;gap:10px;align-items:center;font-size:13px;color:#666;margin-top:6px}
#strip .meta .dot{width:10px;height:10px}
.mirror main,.mirror #strip .inner{transform:scaleX(-1)}
</style></head><body>
<header><select id="partsel" title="Which part to record">{{CHOICES}}</select><div id="status"><span class="dot" id="dot"></span><span id="stage">Ready</span></div><label id="startlab">Start at line <input type="number" id="startat" min="1" value="1"></label><label id="rehlab"><input type="checkbox" id="reh"> Rehearse (nothing recorded)</label><div id="hint"></div><div id="note"></div></header>
<div id="micdead">MIC IS NOT SENDING AUDIO. Abort the take (Esc); the studio reconnects it.</div>
<main id="prompter">{{LINES}}</main>
<div id="strip"><div class="inner"><div class="txt" id="striptxt"></div></div><div class="meta"><span class="dot" id="sdot"></span><span id="smeta"></span></div></div>
<aside>
  <div id="phonebox"><h3>Phone</h3><img id="preview" alt="phone preview"><div id="nophone">No phone connected</div></div>
  <div><h3>Claude plays on</h3><select id="earsel"></select></div>
  <div><h3>Mic</h3><div id="meter"><div id="meterfill"></div><div id="zone"></div></div><div id="meterlabel"></div></div>
  <div><h3>Takes</h3><table id="takes"></table></div>
  <div class="keys"><b>Wheel ↓</b> start take · done with my line · cut (on the last line)<br><b>Wheel ↑</b> redo this line<br><b>Wheel ↑↑</b> back to my previous line<br><b>Wheel ↑↑↑</b> abort the take<br>Keys: <b>→</b> / <b>←</b> same as the wheel · <b>Esc</b> abort · <b>T</b> test beep<br><b>S</b> strip mode (drag the box next to the lens, <b>+</b>/<b>−</b> text size) · <b>M</b> mirror for teleprompter glass</div>
</aside>
<script>
const HINT={idle:"Scroll down to start the take.",
 rolling:"Scroll down when you finish a line. Scroll up = redo this line, twice = previous line, three quick = abort.",
 saving:{{SAVING}}};
let st={stage:"idle",line:0},lastStep=0,ups=[];
const LINES={{LINESJSON}};
// 3-4 word chunks for strip mode, breaking after punctuation; stage directions get their own chunk
function chunk(text){const out=[];let cur=[];
  const toks=text.replace(/\*/g,'').match(/\([^)]*\)|\S+/g)||[];
  for(const t of toks){if(t.startsWith('(')){if(cur.length)out.push(cur.join(' '));out.push(t);cur=[];continue;}
    cur.push(t);if(cur.length>=4||(/[.?!,]$/.test(t)&&cur.length>=2)){out.push(cur.join(' '));cur=[];}}
  if(cur.length)out.push(cur.join(' '));return out;}
const CHUNKS=LINES.map(l=>l.speaker==='RAJESH'?chunk(l.text):[l.text]);
let ci=0,ciLine=-1;
const pref=(k,d)=>{try{const v=localStorage.getItem(k);return v===null?d:JSON.parse(v);}catch(e){return d;}};
const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}};
let strip=pref('strip',false),mirror=pref('mirror',false),sfont=pref('sfont',64),spos=pref('spos',null);
function applyModes(){document.body.classList.toggle('strip',strip);document.body.classList.toggle('mirror',mirror);
  const box=document.getElementById('strip');document.getElementById('striptxt').style.fontSize=sfont+'px';
  if(spos){box.style.left=spos[0]+'px';box.style.top=spos[1]+'px';}}
function curLine(){return st.stage==='idle'?(st.start||0):st.line;}
function renderStrip(){const i=curLine();if(i!==ciLine){ciLine=i;ci=0;}
  const l=LINES[i],c=CHUNKS[i],el=document.getElementById('striptxt');
  el.className='txt'+(l.speaker==='CLAUDE'?' claude':'');
  el.textContent=l.speaker==='CLAUDE'?'Claude…':c[ci];
  document.getElementById('sdot').classList.toggle('on',st.stage==='rolling');
  document.getElementById('smeta').textContent=st.stage==='rolling'?`${st.take} · line ${i+1}/${st.last+1}`+(l.speaker==='RAJESH'?` · ${ci+1}/${c.length}`:''):st.stage==='saving'?'saving…':'scroll down to start';}
(function drag(){const box=document.getElementById('strip');let d=null;
  box.addEventListener('mousedown',e=>{d=[e.clientX-box.offsetLeft,e.clientY-box.offsetTop];});
  addEventListener('mousemove',e=>{if(!d)return;box.style.left=(e.clientX-d[0])+'px';box.style.top=(e.clientY-d[1])+'px';});
  addEventListener('mouseup',()=>{if(d){spos=[box.offsetLeft,box.offsetTop];save('spos',spos);}d=null;});})();
applyModes();
const lines=[...document.querySelectorAll('.line')];
const heads=[...document.querySelectorAll('.part')];
// click a line while idle: the next take starts there (pickups); click the first line to go back to the top
lines.forEach((el,k)=>el.addEventListener('click',()=>{if(st.stage==='idle')post('start',{line:k});}));
document.getElementById('prompter').style.cursor='pointer';
const startat=document.getElementById('startat');startat.max=lines.length;
startat.addEventListener('change',()=>{post('start',{line:Math.max(1,+startat.value||1)-1});startat.blur();});
startat.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Enter')startat.blur();});
if({{AUDIO}})document.body.classList.add('audio');
let refreshingRoom=false;
function refreshRoom(){
 if(refreshingRoom)return;refreshingRoom=true;
 if(window.studioRefreshRoom){Promise.resolve(window.studioRefreshRoom()).catch(e=>{refreshingRoom=false;flash(e.message);});}
 else location.reload();
}
const sel=document.getElementById('partsel');sel.value={{SESSIONJSON}};
sel.addEventListener('change',async()=>{if(await post('part',{name:sel.value}))refreshRoom();});
// keep the wheel and arrow keys on the prompter, not the dropdown
sel.addEventListener('keydown',e=>e.stopPropagation());
const reh=document.getElementById('reh');
reh.addEventListener('change',()=>{post('rehearse',{on:reh.checked});reh.blur();});
function show(i){lines.forEach((el,k)=>{el.classList.toggle('cur',k===i);el.classList.toggle('next',k===i+1);
  el.style.display=(k<i-1||k>i+3)?'none':''});
  heads.forEach(h=>{const k=+h.dataset.at;h.style.display=(k<i-1||k>i+3)?'none':'';});}
function flash(msg){const n=document.getElementById('note');n.textContent=msg;n.dataset.until=Date.now()+1500;}
async function post(p,body={}){const r=await fetch('/room/talk/'+p.replace(/^\//,''),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){flash((await r.json()).error);return false;}tick();return true;}
function step(dir){
  // strip mode pages through the chunks of Rajesh's line before moving the take on
  if(strip&&st.stage==='rolling'&&LINES[st.line].speaker==='RAJESH'){
    const n=CHUNKS[st.line].length;
    if(dir>0&&ci<n-1){ci++;renderStrip();return;}
    if(dir<0&&ci>0){ci--;renderStrip();return;}}
  if(dir<0&&st.stage==='rolling'){const now=Date.now();ups=ups.filter(t=>now-t<1500);ups.push(now);
    if(ups.length>=3){ups=[];post('/abort');return;}}
  if(dir>0&&st.claude){flash('Claude is talking…');return;}
  post('step',{dir});
}
addEventListener('wheel',e=>{e.preventDefault();const now=performance.now();if(now-lastStep<250)return;lastStep=now;step(e.deltaY>0?1:-1);},{passive:false});
addEventListener('keydown',e=>{
  if(['ArrowRight','ArrowDown','Enter',' '].includes(e.key)){e.preventDefault();step(1);}
  else if(['ArrowLeft','ArrowUp'].includes(e.key)){e.preventDefault();step(-1);}
  else if(e.key==='Escape'){post('/abort');}
  else if(e.key==='t'||e.key==='T'){post('/beep');}
  else if(e.key==='s'||e.key==='S'){strip=!strip;save('strip',strip);applyModes();}
  else if(e.key==='m'||e.key==='M'){mirror=!mirror;save('mirror',mirror);applyModes();}
  else if(e.key==='+'||e.key==='='){sfont=Math.min(160,sfont+6);save('sfont',sfont);applyModes();}
  else if(e.key==='-'||e.key==='_'){sfont=Math.max(24,sfont-6);save('sfont',sfont);applyModes();}
});
async function tick(){
  try{st=await (await fetch('/room/talk/state')).json();}catch(e){return;}
  const rolling=st.stage==='rolling';
  document.getElementById('micdead').style.display=st.mic_ok?'none':'block';
  startat.disabled=st.stage!=='idle';if(document.activeElement!==startat)startat.value=(st.start||0)+1;
  sel.disabled=st.stage!=='idle';earsel.disabled=st.stage!=='idle';
  document.body.classList.toggle('nophone',!st.phone);
  if(document.activeElement!==earsel&&st.ear&&earsel.value!==st.ear&&[...earsel.options].some(o=>o.value===st.ear))earsel.value=st.ear;reh.disabled=st.stage!=='idle';reh.checked=st.rehearse;
  document.body.classList.toggle('rehearse',st.rehearse);
  if(st.session!=={{SESSIONJSON}}){refreshRoom();return;}
  if(st.missing&&!rolling&&!st.note)st.note=`${st.missing} Claude clips not generated yet`;
  else if(!st.rehearse&&!st.note&&/speaker/i.test(st.ear||''))st.note='Claude is on the speakers and will bleed into the mic: pick Silent (or earbuds) to record';
  else if(!rolling&&!st.note&&st.ear!==SILENT_NAME&&!st.ear.toLowerCase().includes(st.want_ear.toLowerCase()))st.note=`Claude plays on ${st.ear} (${st.want_ear} not connected yet)`;
  document.getElementById('stage').textContent=(rolling?`${st.take==='rehearsal'?'REHEARSAL':'REC · '+st.take} · ${Math.floor(st.elapsed/60)}:${String(Math.floor(st.elapsed%60)).padStart(2,'0')}`:st.stage==='saving'?'Saving':'Ready')+(rolling?'':(st.start?` · starts at line ${st.start+1} (click line 1 for the top)`:'')+(st.rehearse?' · rehearsal, nothing is recorded':` · next: ${st.next_take}`));
  document.getElementById('dot').classList.toggle('on',rolling);
  document.getElementById('hint').textContent=rolling&&st.line===st.last?'Last line. Scroll down to cut.':HINT[st.stage];
  const note=document.getElementById('note');if(!(note.dataset.until>Date.now()))note.textContent=st.note||'';
  if(st.backed)note.textContent=st.backed==='redo'?'↺ Redo this line':'↑ Back to your previous line';
  show(curLine());
  renderStrip();
  const pct=Math.max(0,Math.min(100,(st.level+60)/60*100));
  const f=document.getElementById('meterfill');f.style.width=pct+'%';
  f.style.background=st.level>-3?'var(--rec)':st.level>-18?'var(--ok)':'var(--warn)';
  document.getElementById('meterlabel').textContent=`${st.level.toFixed(0)} dBFS now`+(st.stage!=='idle'?` · take peak ${st.peak.toFixed(0)}`:'')+' · aim for the dashed zone (−18 to −6) when you talk';
  document.getElementById('takes').innerHTML='<tr><th>Take</th><th>Length</th><th>Peak</th><th>Video</th></tr>'+
    st.takes.slice().reverse().map(t=>`<tr><td>${t.name}${t.complete?'':' (aborted)'}</td><td>${t.secs}s</td><td>${t.peak??''}</td><td style="color:${t.res==='3840x2160'?'inherit':'var(--warn)'}">${t.res}</td></tr>`).join('');
}
setInterval(tick,200);tick();
let previewBusy=false,previewUrl=null;
if(!{{AUDIO}})setInterval(async()=>{if(!st.phone||previewBusy)return;previewBusy=true;try{
 const r=await fetch('/room/talk/preview.jpg');if(!r.ok)return;
 const url=URL.createObjectURL(await r.blob());document.getElementById('preview').src=url;
 if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;
}catch(e){}finally{previewBusy=false;}},700);
const earsel=document.getElementById('earsel');const SILENT_NAME={{SILENTJSON}};
async function loadOutputs(rescan){
  if(rescan)await post('rescan');
  const r=await (await fetch('/room/talk/outputs')).json();
  earsel.innerHTML=r.outputs.map(o=>`<option>${o.replace(/</g,'&lt;')}</option>`).join('');
  earsel.value=r.current;}
earsel.addEventListener('mousedown',()=>{if(st.stage==='idle')loadOutputs(true);});
earsel.addEventListener('change',()=>{post('ear',{name:earsel.value});earsel.blur();});
earsel.addEventListener('keydown',e=>e.stopPropagation());
loadOutputs(false);
</script></body></html>"""


def face_text(face):
    # Scripts give a face as one emoji, or as cues like [{"emoji": "😳", "after_word": 0}].
    if isinstance(face, str):
        return face
    if isinstance(face, list):
        return " ".join(c["emoji"] if isinstance(c, dict) else c for c in face
                        if isinstance(c, str) or isinstance(c, dict) and isinstance(c.get("emoji"), str))
    return ""


def make_page(room):
    rows = []
    for k, l in enumerate(room.lines):
        if k == 0 or l["part"] != room.lines[k - 1]["part"]:
            rows.append(f'<div class="part" data-at="{k}">{html.escape(" · ".join(l["card"][:2]))}</div>')
        face = face_text(l.get("face"))
        face = f'<span class="face">{html.escape(face)}</span>' if face else ""
        rows.append(f'<div class="line{" claude" if l["speaker"] == "CLAUDE" else ""}"><span class="ln">{k + 1}</span>{render_line(l["text"])}{face}</div>')
    lines_html = "\n".join(rows)
    choices = "".join(f'<option value="{html.escape(v, quote=True)}">{html.escape(t)}</option>' for v, t in room.choices)
    return PAGE.replace("{{PHONEASPECT}}", f"{room.phone.size[0]}/{room.phone.size[1]}").replace("{{SILENTJSON}}", json.dumps(SILENT)).replace("{{CHOICES}}", choices).replace("{{SESSIONJSON}}", json.dumps(room.session)).replace("{{AUDIO}}", "false" if room.video else "true").replace(
        "{{SAVING}}", json.dumps("Saving and pulling the video from the phone…" if room.video else "Saving…")).replace(
        "{{LINES}}", lines_html).replace(
        "{{LINESJSON}}", json.dumps([{"speaker": l["speaker"], "text": l["text"]} for l in room.lines]).replace("<", "\\u003c"))
