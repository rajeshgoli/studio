"""Singing room: the original recording stages and page, hosted by server.app."""
import json
import queue
import re
import shutil
import sys
import threading
import time
from pathlib import Path

# The score pipeline still uses sibling imports when launched as scripts.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import librosa
import numpy as np
import soundfile as sf
from server.devices import Devices, RATE, beep

TAKE = re.compile(r"take[0-9]{2,3}")

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


class Studio(Devices):
    def __init__(self, pid, ear_name, mic_name, *, content=None):
        from server.productions import content_root
        self.content = Path(content) if content is not None else content_root()
        self._closed = threading.Event()
        self.pid, self.want_ear, self.mic_name = pid, ear_name, mic_name
        self.poem = json.loads((self.poem_dir() / "poem.json").read_text())
        self.takes_dir = self.poem_dir() / "takes"
        self.takes_dir.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.capture_lock = threading.Lock()
        self.write_error = None
        self.stage = "idle"  # idle | rolling | singing | marking
        self.n_lines = len(self.poem["sung"])
        self.line, self.marks = -1, []
        self.level, self.peak, self.frames = -90.0, -90.0, 0
        self.q, self.out, self.recording = queue.Queue(), None, False
        self.take, self.guide_at, self.note = None, None, ""
        self.mode, self.start_at, self.mix_orig = "both", 0.0, 0.7
        self.ear, self.ear_name, self.last_cb = None, None, 0.0
        self._load_guide()
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
        self.writer = threading.Thread(target=self._writer, daemon=True)
        self.watchdog = threading.Thread(target=self._watchdog, daemon=True)
        self.writer.start()
        self.watchdog.start()

    def poem_dir(self):
        return self.content / "songs" / self.pid

    def close(self):
        self._closed.set()
        self.watchdog.join()
        self.mic.close()
        if self.ear:
            self.ear.close()
        self.q.put(False)
        self.writer.join()


    # ---- guide ---------------------------------------------------------------
    def _load_guide(self):
        ref = self.poem["music"].get("reference")
        self.orig = self.karaoke = None
        self.sa, self.ma = None, False
        if ref and (self.poem_dir() / ref).exists():
            y, _ = librosa.load(self.poem_dir() / ref, sr=RATE, mono=False)
            y = np.atleast_2d(y)
            self.orig = np.column_stack([y[0], y[-1]]).astype("float32")
            self.orig /= np.abs(self.orig).max() + 1e-9
            kar = (self.poem_dir() / ref).with_name(Path(ref).stem + "_no_vocals.wav")
            if kar.exists():
                k, _ = librosa.load(kar, sr=RATE, mono=False)
                k = np.atleast_2d(k)
                self.karaoke = np.column_stack([k[0], k[-1]]).astype("float32")
                self.karaoke /= np.abs(self.karaoke).max() + 1e-9
            try:
                an = json.loads(((self.content / "build" / self.pid) / "analysis.json").read_text())
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
    def _on_audio(self, indata, n, t, status):
        self.last_cb = time.time()
        x = indata[:, 0]
        p = float(np.abs(x).max())
        self.level = max(20 * np.log10(p + 1e-9), self.level - 3)
        with self.capture_lock:
            if self.recording:
                self.q.put(x.copy())
                self.frames += n
                self.peak = max(self.peak, 20 * np.log10(p + 1e-9))

    def _writer(self):
        while True:
            block = self.q.get()
            if block is False:
                return
            if block is None:
                try:
                    self.out.close()
                except Exception as exc:
                    self.write_error = str(exc)
                finally:
                    self.out = None
            else:
                try:
                    if self.write_error is None:
                        self.out.write(block)
                except Exception as exc:
                    self.write_error = str(exc)

    # ---- takes ---------------------------------------------------------------
    def next_name(self):
        n = 1 + max([int(p.stem[4:]) for p in self.takes_dir.glob("take*.wav") if TAKE.fullmatch(p.stem)] or [0])
        if n > 999:
            raise ValueError("Take numbers exhausted")
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
                self.write_error = None
                with self.capture_lock:
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
            src = self.poem_dir() / "vocals.wav"
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
        (self.poem_dir() / "marks.json").write_text(json.dumps(m, indent=1))

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
        with self.capture_lock:
            self.recording = False
            self.q.put(None)
        while self.out is not None:
            time.sleep(0.02)
        wav = self.takes_dir / f"{self.take}.wav"
        if self.write_error:
            self.stage = "idle"
            self.note = f"Recording could not be saved completely: {self.write_error}"
            return
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
            trash = self.takes_dir / "deleted"
            trash.mkdir(exist_ok=True)
            shutil.move(wav, trash / f"{self.take}_aborted_{time.time_ns()}.wav")
            self.note = "Take aborted."
        self.stage = "idle"

    def use_take(self, name):
        with self.lock:
            src = self.takes_dir / f"{name}.wav"
            meta = json.loads((self.takes_dir / f"{name}.json").read_text())
            dst = self.poem_dir() / "vocals.wav"
            if dst.exists():
                shutil.move(dst, self.takes_dir / f"vocals_before_{name}_{int(time.time())}.wav")
            shutil.copy(src, dst)
            if meta.get("line_starts"):
                self._write_marks(dst, meta["line_starts"], meta["seconds"], meta.get("sa_hz"))
            else:
                (self.poem_dir() / "marks.json").unlink(missing_ok=True)
            p = self.poem_dir() / "poem.json"
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
        for j in sorted((p for p in self.takes_dir.glob("take*.json") if TAKE.fullmatch(p.stem)), reverse=True):
            m = json.loads(j.read_text())
            out.append({"name": j.stem, "seconds": m["seconds"], "peak": m["peak_dbfs"], "guide": m["guide"]})
        return out

    @property
    def active_stage(self):
        with self.lock:
            if self.stage == "preview" and self.ear and self.ear.buf is None:
                self.stage = "idle"
            return self.stage

    def state(self):
        stage = self.active_stage
        return {"stage": stage, "level": round(self.level, 1), "peak": round(self.peak, 1),
                "seconds": round(self.frames / RATE, 1), "note": self.note, "ear": self.ear_name,
                "want_ear": self.want_ear, "mic_ok": time.time() - self.last_cb < 0.5, "mode": self.mode,
                "start_at": self.start_at, "mix": self.mix_orig, "takes": self.takes(),
                "has_orig": self.orig is not None, "line": self.line}


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Singing Studio</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{color-scheme:dark;--bg:#121216;--panel:#1c1c23;--line:#35343f;--ink:#f4f0e8;--muted:#aaa6b4;--gold:#eccb87}
*{box-sizing:border-box}html,body{height:100%;overflow:hidden}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
.wrap{height:100%;max-width:1200px;margin:auto;display:flex;flex-direction:column;padding:20px 32px;gap:12px;min-height:0}
header{display:flex;justify-content:space-between;gap:24px;align-items:center;flex-shrink:0}h1{font:600 24px/1.2 Georgia,serif;margin:0;color:var(--gold)}.eyebrow{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
nav{display:flex;gap:6px}button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:10px 16px;cursor:pointer;min-height:44px}button:hover{border-color:var(--gold)}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:3px}button:disabled{opacity:.4;cursor:not-allowed}nav button[aria-selected=true]{color:var(--gold);border-color:var(--gold)}
.statusbar{display:flex;gap:12px;align-items:center;flex-shrink:0;color:var(--muted);font-size:13px}.stage{color:var(--ink);font-weight:600;text-transform:capitalize}#meter{height:6px;background:var(--line);border-radius:4px;overflow:hidden;width:130px}#bar{height:100%;background:var(--gold);width:0}#note{font-size:13px;color:var(--muted);min-height:20px;margin:0;flex-shrink:0}
.pane{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain}.pane[hidden]{display:none}#record-pane{display:flex;flex-direction:column;overflow:hidden}#record-pane[hidden]{display:none}#lyr{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:18px 0}.l{margin:0 0 24px;padding:16px 20px;border-radius:12px;color:var(--muted)}.l.on{background:var(--panel);box-shadow:inset 3px 0 var(--gold);color:var(--ink)}.l .t{font:italic clamp(22px,2.4vw,32px)/1.45 Georgia,serif}.l .m{font-size:16px;margin-top:6px;color:var(--muted)}
.controls{border-top:1px solid var(--line);padding-top:16px;flex-shrink:0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}button.big{background:var(--gold);color:#17151a;font-weight:700;border-color:var(--gold);min-width:170px}.hint{color:var(--muted);font-size:12px;margin:8px 0 0;flex-shrink:0}
.settings{max-width:720px;margin:12px auto;padding:20px;background:var(--panel);border:1px solid var(--line);border-radius:12px}.settings h2{font-size:18px;margin:0 0 16px}.field{display:grid;grid-template-columns:170px 1fr;gap:16px;align-items:center;margin:18px 0}.field label{color:var(--muted)}select,input{font:inherit;max-width:100%;min-width:0;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px}input[type=range]{accent-color:var(--gold);width:100%}.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}#takes{height:100%;overflow:auto;overscroll-behavior:contain;padding:12px 0}.take{padding:18px;margin:0 0 12px;background:var(--panel);border:1px solid var(--line);border-radius:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}audio{max-width:100%;height:40px}.empty{color:var(--muted);padding:40px 20px;text-align:center}
@media(max-width:700px){.wrap{padding:12px;gap:8px}header{gap:10px;align-items:start;flex-direction:column}h1{font-size:20px}.field{grid-template-columns:1fr;gap:4px}.l{padding:10px}.controls{gap:6px;padding-top:10px}button{padding:8px 12px}.statusbar{gap:8px}#meter{width:80px}}
</style></head><body><div class="wrap">
<header><div><div class="eyebrow">Singing room</div><h1>Singing Studio · TITLE</h1></div>
<nav aria-label="Singing workspace" role="tablist"><button role="tab" aria-selected="true" data-pane="record">Record</button><button role="tab" aria-selected="false" data-pane="setup">Setup</button><button role="tab" aria-selected="false" data-pane="takes">Saved takes</button></nav></header>
<div class="statusbar"><span class="stage" id="stage">idle</span><span id="secs"></span><span>Microphone</span><div id="meter"><div id="bar"></div></div><span id="lvl"></span></div>
<p id="note" role="status"></p>
<section class="pane" id="record-pane" aria-label="Record">
<div class="lyrics" id="lyr">LYRICS</div>
<div class="controls"><button class="big" id="go" onclick="post('step')">Start take</button><button id="pv" onclick="post('preview')">Preview guide</button><button id="abort" onclick="post('abort')">Abort (Esc)</button></div>
<p class="hint">Wheel on the recording surface: start → guide → mark each line → stop. Wheel up undoes a mark.<br>While idle, scroll over the lyrics to read them. Enter / arrow keys also control the take.</p>
</section>
<section class="pane" id="setup-pane" aria-label="Setup" hidden><div class="settings"><h2>What you hear</h2>
<div class="field"><label for="mode">Guide</label><select id="mode" onchange="post('set',{mode:this.value})"><option value="both">Original + tanpura</option><option value="original">Original only</option><option value="karaoke+tanpura">Karaoke + tanpura</option><option value="karaoke">Karaoke only</option><option value="tanpura">Tanpura only</option></select></div>
<p class="hint">Tanpura is a steady home-note guide. Karaoke removes the original singer.</p>
<div class="field"><label for="mix">Original level</label><input id="mix" type="range" min="0.2" max="1" step="0.05" onchange="post('set',{mix:+this.value})"></div>
<div class="field"><label for="start">Guide starts at (seconds)</label><input id="start" type="number" step="0.5" onchange="post('set',{start_at:+this.value})"></div>
<div class="field"><label for="ear">Earbuds</label><select id="ear" onchange="post('ear',{name:this.value})"></select></div>
<div class="field"><label for="volume">Earbud volume</label><input id="volume" type="range" min="0.1" max="1.5" step="0.05" value="1" onchange="post('set',{gain:+this.value})"></div>
<div class="row"><button onclick="post('rescan')">Rescan devices</button><button onclick="post('beep')">Test beep</button></div></div>
<div class="settings"><h2>Existing vocal</h2><p class="hint">Play the voice already selected for the video and mark where each line starts.</p><button onclick="showPane('record');post('mark')">Mark lines on vocals.wav</button></div></section>
<section class="pane" id="takes-pane" aria-label="Saved takes" hidden><div id="takes"></div></section>
</div><script>
async function loadTake(button,name){
 button.disabled=true;
 try{const r=await fetch('/room/sing/take/'+name+'.wav');if(!r.ok)throw Error('Playback unavailable');
 const audio=button.nextElementSibling;const url=URL.createObjectURL(await r.blob());audio.src=url;button.remove();
 addEventListener('unload',()=>URL.revokeObjectURL(url),{once:true});
 }catch(e){button.disabled=false;document.getElementById('note').textContent=e.message;}
}
const labels={idle:'Start take',rolling:'Start guide',singing:'Next line',marking:'Next line',preview:'Start take'};
async function post(a,b={}){const r=await fetch('/room/sing/'+a,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});if(!r.ok){document.getElementById('note').textContent=(await r.json()).error;return;}tick()}
let lastWheel=0;
let stage='idle', pane='record';
function showPane(name){
 if(!['idle','preview'].includes(stage)&&name!=='record')return;
 pane=name;
 document.querySelectorAll('[data-pane]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.pane===name)));
 for(const n of ['record','setup','takes'])document.getElementById(n+'-pane').hidden=n!==name;
}
document.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>showPane(b.dataset.pane));
// The wheel is the remote (a click would be heard on the take). The page itself never scrolls; while idle, the
// wheel over lyrics or saved takes scrolls that list; elsewhere it starts a take.
addEventListener('wheel',e=>{
 if(pane!=='record'||e.target.closest('button,select,input,nav'))return;
 const browsing=document.getElementById('lyr').contains(e.target);
 if((stage=='idle'||stage=='preview')&&browsing)return;
 e.preventDefault();
 if(Math.abs(e.deltaY)>30&&Date.now()-lastWheel>600){lastWheel=Date.now();
  const busy=['rolling','singing','marking'].includes(stage);
  if(e.deltaY>0)post('step'); else if(busy)post('back');}},{passive:false});
addEventListener('keydown',e=>{
 if(pane!=='record')return;
 if(e.key==='Escape'){e.preventDefault();post('abort');return;}
 if(e.target.closest('input,select,textarea,a')||e.target.isContentEditable)return;
 // Enter on a button uses its native click once. Recording buttons retain
 // Escape/arrow shortcuts after a click; navigation buttons do not record.
 if(e.target.closest('button')&&(e.key==='Enter'||!e.target.closest('.controls')))return;
 if(e.key=='Enter'||e.key=='ArrowRight'){e.preventDefault();post('step')}
 if(e.key=='ArrowLeft')post('back'); if(e.key=='Escape')post('abort'); if(e.key=='t'||e.key=='T')post('beep')});
let outs=null, lastTakes='';
async function tick(){const s=await (await fetch('/room/sing/state')).json(); stage=s.stage;
 const busy=!['idle','preview'].includes(stage);
 document.querySelectorAll('[data-pane]').forEach(b=>b.disabled=busy);
 if(busy&&pane!=='record')showPane('record');
 document.getElementById('abort').disabled=stage==='idle';
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
 if(!outs){outs=await (await fetch('/room/sing/outputs')).json();const e=document.getElementById('ear');
  e.innerHTML=outs.map(o=>`<option>${o}</option>`).join('');}
 document.getElementById('ear').value=s.ear||'';
 const tk=JSON.stringify(s.takes); if(tk!=lastTakes){lastTakes=tk;
 document.getElementById('takes').innerHTML=s.takes.map(t=>`<div class="take"><b>${t.name}</b> ${t.seconds.toFixed(0)} s,
  peak ${t.peak} dB, ${t.guide} <button onclick="loadTake(this,'${t.name}')">Load playback</button><audio controls preload="none"></audio>
  <button onclick="post('use',{name:'${t.name}'})">Use for video</button>
  <button onclick="post('delete',{name:'${t.name}'})">Delete</button></div>`).join('')||'<p class="empty">No saved takes yet. Record a take to review it here.</p>';}}
setInterval(tick,250);tick();
</script></body></html>"""


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


