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
import io
import json
import queue
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import librosa
import numpy as np
import sounddevice as sd
import soundfile as sf

import analyze
from common import poem_dir, load_poem

PORT = 9400
RATE = 48000


class Ear:
    """An always-open output stream to the earbud. It plays silence between cues, so a Bluetooth earbud stays
    awake and the start of the guide isn't swallowed."""

    def __init__(self, device):
        self.buf, self.pos, self.lock = None, 0, threading.Lock()
        self.gain = 1.0
        self.stream = sd.OutputStream(samplerate=RATE, channels=2, device=device, dtype="float32", callback=self._fill)
        self.stream.start()

    def _fill(self, out, n, t, status):
        out[:] = 0
        with self.lock:
            if self.buf is not None:
                chunk = self.buf[self.pos:self.pos + n]
                out[:len(chunk)] = chunk * self.gain
                self.pos += len(chunk)
                if self.pos >= len(self.buf):
                    self.buf = None

    def play(self, audio):
        with self.lock:
            self.buf, self.pos = audio, 0

    def stop(self):
        with self.lock:
            self.buf = None

    def close(self):
        self.stream.close()


def beep(hz=880, length=0.25, vol=0.25):
    t = np.arange(int(length * RATE)) / RATE
    return np.column_stack([vol * np.sin(2 * np.pi * hz * t)] * 2).astype("float32")


def tanpura(sa, secs, ma):
    """Tanpura loop on Sa: Pa (or Ma) - Sa - Sa - low Sa."""
    from score import SR, tanpura_pluck
    first = sa * 2 ** (5 / 12) / 2 if ma else sa * 0.75
    strings = [(first, -0.35), (sa, 0.1), (sa * 1.0009, 0.25), (sa / 2, -0.1)]
    plucks = [[tanpura_pluck(f, sweep=s, seed=10 * i + j) for j, s in enumerate((1.1, 1.4, 1.7))]
              for i, (f, _) in enumerate(strings)]
    n = int(secs * SR)
    bus = np.zeros((2, n + 6 * SR))
    rng = np.random.default_rng(0)
    t, k = 0.1, 0
    while t < secs:
        i = k % 4
        p = plucks[i][rng.integers(3)] * (0.8 if i == 3 else 1.0)
        a = int(t * SR)
        th = (strings[i][1] + 1) * np.pi / 4
        bus[0, a:a + len(p)] += p * np.cos(th)
        bus[1, a:a + len(p)] += p * np.sin(th)
        t += 0.62 if i < 3 else 1.24
        k += 1
    bus = bus[:, :n] * np.clip(np.arange(n) / (1.5 * SR), 0, 1)
    bus = librosa.resample(bus, orig_sr=SR, target_sr=RATE)
    return (bus / np.abs(bus).max()).T.astype("float32")


class Studio:
    def __init__(self, pid, ear_name, mic_name):
        self.pid, self.want_ear, self.mic_name = pid, ear_name, mic_name
        self.poem = load_poem(pid)
        self.takes_dir = poem_dir(pid) / "takes"
        self.takes_dir.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.stage = "idle"  # idle | rolling | singing | marking
        self.n_lines = len(self.poem["sung"])
        self.line, self.marks = -1, []
        self.level, self.peak, self.frames = -90.0, -90.0, 0
        self.q, self.out, self.recording = queue.Queue(), None, False
        self.take, self.guide_at, self.note = None, None, ""
        self.mode, self.start_at, self.mix_orig = "both", 0.0, 0.7
        self.ear, self.ear_name, self.last_cb = None, None, 0.0
        self._load_guide()
        self._open_ear()
        self._open_mic()
        threading.Thread(target=self._writer, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ---- guide ---------------------------------------------------------------
    def _load_guide(self):
        ref = self.poem["music"].get("reference")
        self.orig = self.karaoke = None
        self.sa, self.ma = None, False
        if ref and (poem_dir(self.pid) / ref).exists():
            y, _ = librosa.load(poem_dir(self.pid) / ref, sr=RATE, mono=False)
            y = np.atleast_2d(y)
            self.orig = np.column_stack([y[0], y[-1]]).astype("float32")
            self.orig /= np.abs(self.orig).max() + 1e-9
            kar = (poem_dir(self.pid) / ref).with_name(Path(ref).stem + "_no_vocals.wav")
            if kar.exists():
                k, _ = librosa.load(kar, sr=RATE, mono=False)
                k = np.atleast_2d(k)
                self.karaoke = np.column_stack([k[0], k[-1]]).astype("float32")
                self.karaoke /= np.abs(self.karaoke).max() + 1e-9
            try:
                an = json.loads((analyze.build_dir(self.pid) / "analysis.json").read_text())
                if an.get("reference"):
                    self.sa = an["reference"]["sa_hz"]
                    self.ma = 7 not in an["reference"]["notes"]
            except FileNotFoundError:
                pass
        if self.sa is None:
            self.sa = self.poem["music"].get("tonic_hz") or 204.0
        secs = (len(self.orig) / RATE if self.orig is not None else 240) + 30
        self.tan = tanpura(self.sa, secs, self.ma)
        self.note = (f"Guide Sa {self.sa:.1f} Hz ({librosa.hz_to_note(self.sa)}), drone on "
                     f"{'Ma' if self.ma else 'Pa'}.")

    def guide(self):
        a = int(self.start_at * RATE)
        tan = self.tan[a:] * 0.55
        if self.mode == "tanpura" or self.orig is None:
            return tan
        karaoke = self.mode.startswith("karaoke") and self.karaoke is not None
        o = (self.karaoke if karaoke else self.orig)[a:]
        if self.mode in ("original", "karaoke"):
            return o * 0.9
        n = max(len(o), len(tan))
        mix = np.zeros((n, 2), "float32")
        mix[:len(o)] += o * self.mix_orig
        mix[:len(tan)] += tan * (1 - 0.5 * self.mix_orig)
        return mix / max(1.0, np.abs(mix).max())

    # ---- devices -------------------------------------------------------------
    def outputs(self):
        return [d["name"] for d in sd.query_devices()
                if d["max_output_channels"] and self.mic_name.lower() not in d["name"].lower()]

    def _open_ear(self):
        """The earbud asked for (any part of its name). Never the mic's own headphone jack: closing an output
        stream on the mic's device kills the mic's input stream on macOS."""
        name = next((o for o in self.outputs() if self.want_ear.lower() in o.lower()), None)
        if name == self.ear_name and self.ear:
            return
        if self.ear:
            self.ear.close()
        self.ear, self.ear_name = (Ear(name), name) if name else (None, None)

    def _open_mic(self):
        self.mic = sd.InputStream(samplerate=RATE, channels=1, device=self.mic_name, callback=self._on_audio)
        self.mic.start()

    def rescan(self):
        """PortAudio lists devices once at start-up; buds that connected later need a restart of it."""
        with self.lock:
            if self.stage != "idle":
                return
            self.mic.close()
            if self.ear:
                self.ear.close()
            self.ear, self.ear_name = None, None
            sd._terminate()
            sd._initialize()
            self._open_mic()
            self._open_ear()

    def set_ear(self, name):
        with self.lock:
            if self.stage == "idle":
                self.want_ear = name
                self._open_ear()

    def _watchdog(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                if self.stage == "idle" and time.time() - self.last_cb > 1.0:
                    try:
                        self.mic.close()
                        self._open_mic()
                    except Exception as e:
                        self.note = f"Mic won't open: {e}"

    def _on_audio(self, indata, n, t, status):
        self.last_cb = time.time()
        x = indata[:, 0]
        p = float(np.abs(x).max())
        self.level = max(20 * np.log10(p + 1e-9), self.level - 3)
        if self.recording:
            self.q.put(x.copy())
            self.frames += n
            self.peak = max(self.peak, 20 * np.log10(p + 1e-9))

    def _writer(self):
        while True:
            block = self.q.get()
            if block is None:
                self.out.close()
                self.out = None
            else:
                self.out.write(block)

    # ---- takes ---------------------------------------------------------------
    def next_name(self):
        n = 1 + max([int(p.stem[4:6]) for p in self.takes_dir.glob("take[0-9][0-9].wav")] or [0])
        return f"take{n:02d}"

    def step(self):
        if self.stage == "preview":
            self.preview()  # stop it; the same scroll then starts the take
        with self.lock:
            if self.stage == "idle":
                if time.time() - self.last_cb > 0.5:
                    self.note = "The mic isn't sending audio. Check the fifine's USB cable."
                    return
                self.take = self.next_name()
                self.out = sf.SoundFile(self.takes_dir / f"{self.take}.wav", "w", RATE, 1, "PCM_24")
                self.frames, self.peak, self.guide_at = 0, -90.0, None
                self.line, self.marks = -1, []
                self.recording, self.stage = True, "rolling"
                self.note = "Recording. Say the hook if you have one, then start the guide."
            elif self.stage == "rolling":
                self.guide_at = self.frames
                if self.ear:
                    self.ear.play(self.guide())
                self.stage = "singing"
                self.note = "Guide playing. Scroll as you start each line."
            elif self.line < self.n_lines - 1:
                now = (self.ear.pos / RATE - 0.15) if self.stage == "marking" else self.frames / RATE
                self.line += 1
                self.marks.append(round(max(0.0, now), 3))
                self.note = ("Last line. Scroll once more when you've finished it." if self.line == self.n_lines - 1
                             else f"Line {self.line + 1} of {self.n_lines}.")
            elif self.stage == "marking":
                self._finish_marking()
            else:
                self._finish(save=True)

    def preview(self):
        """Play (or stop) the guide in the earbud without recording."""
        with self.lock:
            if self.stage == "preview":
                if self.ear:
                    self.ear.stop()
                self.stage, self.note = "idle", "Preview stopped."
            elif self.stage == "idle":
                if not self.ear:
                    self.note = "No earbud connected: connect it, then Rescan devices."
                    return
                self.ear.play(self.guide())
                self.stage, self.note = "preview", "Previewing the guide. Nothing is being recorded."

    def back(self):
        with self.lock:
            if self.stage in ("singing", "marking") and self.marks:
                self.marks.pop()
                self.line -= 1
                self.note = f"Undid that mark: back on line {self.line + 1}." if self.line >= 0 else "Undid line 1."

    def start_marking(self):
        """Play vocals.wav in the earbud; each scroll marks where a line starts."""
        with self.lock:
            src = poem_dir(self.pid) / "vocals.wav"
            if self.stage != "idle" or not self.ear or not src.exists():
                self.note = "Needs the earbud connected and a vocals.wav." if self.stage == "idle" else self.note
                return
            y, _ = librosa.load(src, sr=RATE, mono=True)
            self.ear.play(np.column_stack([y, y]).astype("float32") / (np.abs(y).max() + 1e-9) * 0.8)
            self.marking_src = src
            self.line, self.marks, self.stage = -1, [], "marking"
            self.note = "Playing your take. Scroll as each line starts (not the spoken hook)."

    def _finish_marking(self):
        end = self.ear.pos / RATE if self.ear and self.ear.buf is not None else None
        if self.ear:
            self.ear.stop()
        self._write_marks(self.marking_src, self.marks, end)
        self.note = f"Saved {len(self.marks)} line marks for vocals.wav. Run ./render.sh {self.pid} --retime"
        self.stage = "idle"

    def _write_marks(self, vocals, starts, end, guide_sa=None):
        m = {"vocals_bytes": vocals.stat().st_size, "line_starts": starts, "end": end}
        if guide_sa:
            m["guide_sa_hz"] = guide_sa  # the tanpura the take was sung to
        (poem_dir(self.pid) / "marks.json").write_text(json.dumps(m, indent=1))

    def abort(self):
        with self.lock:
            if self.stage in ("marking", "preview"):
                if self.ear:
                    self.ear.stop()
                self.stage, self.note = "idle", "Marking cancelled."
            elif self.stage != "idle":
                self._finish(save=False)

    def _finish(self, save):
        if self.ear:
            self.ear.stop()
        self.recording = False
        self.q.put(None)
        while self.out is not None:
            time.sleep(0.02)
        wav = self.takes_dir / f"{self.take}.wav"
        if save:
            meta = {"take": wav.name, "rate": RATE, "guide": self.mode, "guide_from_s": self.start_at,
                    "guide_start_s": round(self.guide_at / RATE, 3) if self.guide_at is not None else None,
                    "seconds": round(self.frames / RATE, 2), "peak_dbfs": round(self.peak, 1), "sa_hz": self.sa,
                    "line_starts": self.marks}
            (self.takes_dir / f"{self.take}.json").write_text(json.dumps(meta, indent=1))
            self.note = (f"Saved {self.take}: {meta['seconds']:.0f} s, peak {meta['peak_dbfs']:.1f} dBFS"
                         + (" (clipping: turn the gain down)" if self.peak > -1 else
                            " (quiet: gain up or move closer)" if self.peak < -18 else ""))
        else:
            wav.unlink(missing_ok=True)
            self.note = "Take aborted."
        self.stage = "idle"

    def use_take(self, name):
        with self.lock:
            src = self.takes_dir / f"{name}.wav"
            meta = json.loads((self.takes_dir / f"{name}.json").read_text())
            dst = poem_dir(self.pid) / "vocals.wav"
            if dst.exists():
                shutil.move(dst, self.takes_dir / f"vocals_before_{name}_{int(time.time())}.wav")
            shutil.copy(src, dst)
            if meta.get("line_starts"):
                self._write_marks(dst, meta["line_starts"], meta["seconds"], meta.get("sa_hz"))
            else:
                (poem_dir(self.pid) / "marks.json").unlink(missing_ok=True)
            p = poem_dir(self.pid) / "poem.json"
            poem = json.loads(p.read_text())
            gs = meta.get("guide_start_s")
            if gs and gs > 1.5 and poem.get("spoken_intro"):
                poem["spoken_intro"]["until"] = round(gs, 2)  # everything before the guide is the spoken hook
            elif poem.get("spoken_intro"):
                poem["spoken_intro"]["until"] = 0
            p.write_text(json.dumps(poem, indent=2, ensure_ascii=False) + "\n")
            self.note = f"{name} is now vocals.wav. Run ./render.sh {self.pid} --retime"

    def delete_take(self, name):
        """Move a take (wav + json) to takes/deleted/, out of the list but still recoverable."""
        with self.lock:
            trash = self.takes_dir / "deleted"
            trash.mkdir(exist_ok=True)
            for ext in (".wav", ".json"):
                f = self.takes_dir / f"{name}{ext}"
                if f.exists():
                    shutil.move(f, trash / f"{name}_{int(time.time())}{ext}")
            self.note = f"Deleted {name} (kept in takes/deleted/ in case you want it back)."

    def takes(self):
        out = []
        for j in sorted(self.takes_dir.glob("take[0-9][0-9].json"), reverse=True):
            m = json.loads(j.read_text())
            out.append({"name": j.stem, "seconds": m["seconds"], "peak": m["peak_dbfs"], "guide": m["guide"]})
        return out

    def state(self):
        if self.stage == "preview" and self.ear and self.ear.buf is None:
            self.stage = "idle"
        return {"stage": self.stage, "level": round(self.level, 1), "peak": round(self.peak, 1),
                "seconds": round(self.frames / RATE, 1), "note": self.note, "ear": self.ear_name,
                "want_ear": self.want_ear, "mic_ok": time.time() - self.last_cb < 0.5, "mode": self.mode,
                "start_at": self.start_at, "mix": self.mix_orig, "takes": self.takes(),
                "has_orig": self.orig is not None, "line": self.line}


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Singing Studio</title>
<style>
html,body{height:100%;overflow:hidden}
body{margin:0;background:#120d18;color:#f3e9d6;font:18px/1.4 "Avenir Next",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:18px 24px;height:100%;box-sizing:border-box;display:flex;flex-direction:column}
#lyr{flex:1;overflow-y:auto;min-height:120px}
#takes{max-height:22vh;overflow-y:auto}
.hint{color:#998;font-size:14px}
h1{font:600 26px "Hoefler Text",serif;color:#e8c27a;margin:0 0 4px}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0}
button{background:#2a2036;color:#f3e9d6;border:1px solid #e8c27a66;border-radius:10px;padding:10px 16px;font-size:17px;cursor:pointer}
button.big{background:#e8c27a;color:#1a1020;font-weight:700;font-size:22px;padding:16px 28px}
select,input{background:#2a2036;color:#f3e9d6;border:1px solid #555;border-radius:8px;padding:8px;font-size:16px}
#meter{height:14px;background:#2a2036;border-radius:7px;overflow:hidden;width:320px}
#bar{height:100%;background:linear-gradient(90deg,#6c6,#ec6,#e66);width:0}
#note{color:#e8c27a;min-height:1.4em}
.stage{font-size:30px;font-weight:700}
.lyrics{margin-top:20px;border-top:1px solid #e8c27a33;padding-top:12px}
.l{margin:10px 0;padding:6px 12px;border-radius:10px;opacity:.55}.l.on{opacity:1;background:#2a2036;box-shadow:0 0 0 1px #e8c27a88}.l .t{font:italic 24px "Hoefler Text",serif}.l .m{color:#bba;font-size:15px}
.take{display:flex;gap:10px;align-items:center;margin:4px 0}
</style></head><body><div class="wrap">
<h1>Singing Studio · TITLE</h1>
<div class="row"><span class="stage" id="stage">idle</span><span id="secs"></span>
<div id="meter"><div id="bar"></div></div><span id="lvl"></span></div>
<div id="note"></div>
<div class="row"><button class="big" id="go" onclick="post('step')">Start take</button>
<button id="pv" onclick="post('preview')">Preview guide</button><button onclick="post('abort')">Abort (Esc)</button><button onclick="post('mark')">Mark lines on vocals.wav</button><button onclick="post('beep')">Test beep (T)</button></div>
<div class="row">Guide <select id="mode" onchange="post('set',{mode:this.value})">
<option value="both">Original + tanpura</option><option value="original">Original only</option>
<option value="karaoke+tanpura">Karaoke (voice removed) + tanpura</option><option value="karaoke">Karaoke only</option>
<option value="tanpura">Tanpura only</option></select>
original level <input id="mix" type="range" min="0.2" max="1" step="0.05" onchange="post('set',{mix:+this.value})">
start the original at <input id="start" type="number" step="0.5" style="width:80px" onchange="post('set',{start_at:+this.value})"> s</div>
<div class="row">Earbud <select id="ear" onchange="post('ear',{name:this.value})"></select>
<button onclick="post('rescan')">Rescan devices</button> volume
<input type="range" min="0.1" max="1.5" step="0.05" value="1" onchange="post('set',{gain:+this.value})"></div>
<div id="takes"></div>
<div class="hint">Scroll down anywhere outside the lyrics to step: start take → start guide → each line → stop.
Scroll up during a take undoes a line mark. Over the lyrics, the wheel scrolls them while idle.</div>
<div class="lyrics" id="lyr">LYRICS</div>
</div><script>
const labels={idle:'Start take',rolling:'Start guide',singing:'Next line',marking:'Next line',preview:'Start take'};
async function post(a,b={}){await fetch('/'+a,{method:'POST',body:JSON.stringify(b)});tick()}
let lastWheel=0;
let stage='idle';
// The wheel is a remote only while a take (or line marking) is running; otherwise it just scrolls the page.
// The wheel is the remote (a click would be heard on the take). The page itself never scrolls; while idle, the
// wheel over the lyrics box scrolls the lyrics, and anywhere else it is the next step (starting with Start take).
addEventListener('wheel',e=>{
 const overLyrics=document.getElementById('lyr').contains(e.target);
 if((stage=='idle'||stage=='preview')&&overLyrics)return;
 e.preventDefault();
 if(Math.abs(e.deltaY)>30&&Date.now()-lastWheel>600){lastWheel=Date.now();
  const busy=['rolling','singing','marking'].includes(stage);
  if(e.deltaY>0)post('step'); else if(busy)post('back');}},{passive:false});
addEventListener('keydown',e=>{if(e.target.tagName=='INPUT')return;
 if(e.key=='Enter'||e.key=='ArrowRight'){e.preventDefault();post('step')}
 if(e.key=='ArrowLeft')post('back'); if(e.key=='Escape')post('abort'); if(e.key=='t'||e.key=='T')post('beep')});
let outs=null, lastTakes='';
async function tick(){const s=await (await fetch('/state')).json(); stage=s.stage;
 document.getElementById('pv').textContent=s.stage=='preview'?'Stop preview':'Preview guide';
 document.getElementById('stage').textContent=s.stage+(s.mic_ok?'':' · mic not sending');
 document.getElementById('go').textContent=(s.stage=='singing'||s.stage=='marking')&&s.line==N-1?'Stop':labels[s.stage];
 document.querySelectorAll('.l').forEach(r=>{const i=+r.dataset.i;
  const on=(s.stage=='rolling'&&i==-1)||((s.stage=='singing'||s.stage=='marking')&&i==s.line);
  r.classList.toggle('on',on); if(on&&r.dataset.cur!='1'){r.scrollIntoView({block:'center',behavior:'smooth'})} r.dataset.cur=on?'1':'0';});
 document.getElementById('secs').textContent=s.stage=='idle'?'':s.seconds+' s';
 document.getElementById('bar').style.width=Math.max(0,Math.min(100,(s.level+60)/60*100))+'%';
 document.getElementById('lvl').textContent=s.level.toFixed(0)+' dB';
 document.getElementById('note').textContent=s.note;
 const m=document.getElementById('mode'); if(document.activeElement!=m) m.value=s.mode;
 const st=document.getElementById('start'); if(document.activeElement!=st) st.value=s.start_at;
 const mx=document.getElementById('mix'); if(document.activeElement!=mx) mx.value=s.mix;
 if(!outs){outs=await (await fetch('/outputs')).json();const e=document.getElementById('ear');
  e.innerHTML=outs.map(o=>`<option>${o}</option>`).join('');}
 document.getElementById('ear').value=s.ear||'';
 const tk=JSON.stringify(s.takes); if(tk!=lastTakes){lastTakes=tk;
 document.getElementById('takes').innerHTML=s.takes.map(t=>`<div class="take"><b>${t.name}</b> ${t.seconds.toFixed(0)} s,
  peak ${t.peak} dB, ${t.guide} <audio controls src="/take/${t.name}.wav" preload="none"></audio>
  <button onclick="post('use',{name:'${t.name}'})">Use for video</button>
  <button onclick="post('delete',{name:'${t.name}'})">Delete</button></div>`).join('');}}
setInterval(tick,250);tick();
</script></body></html>"""


_playable = {}


def playable(path):
    """The take as 16-bit WAV (browsers won't all play 24-bit), cached until the file changes."""
    key = (path, path.stat().st_mtime)
    if key not in _playable:
        y, sr = sf.read(path, dtype="float32")
        buf = io.BytesIO()
        sf.write(buf, y, sr, format="WAV", subtype="PCM_16")
        _playable[key] = buf.getvalue()
    return _playable[key]


def make_page(studio):
    p = studio.poem
    lines = {l["id"]: l for l in p["lines"]}
    rows = []
    if p.get("spoken_intro"):
        rows.append(f'<div class="l" data-i="-1"><div class="t">(spoken) {p["spoken_intro"]["text"]}</div></div>')
    for i, lid in enumerate(p["sung"]):
        l = lines[lid]
        rows.append(f'<div class="l" data-i="{i}"><div class="t">{i + 1}. {l["translit"]}</div>'
                    f'<div class="m">{l["meaning"]}</div></div>')
    return (PAGE.replace("TITLE", p["title"]).replace("LYRICS", "".join(rows))
            .replace("<script>", f"<script>const N={len(p['sung'])};", 1))


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

        def _send_audio(self, data):
            """Browsers (Safari especially) only play media from servers that answer Range requests."""
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                a = int(a or 0)
                b = min(int(b) if b else len(data) - 1, len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
                chunk = data[a:b + 1]
            else:
                self.send_response(200)
                chunk = data
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)

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
