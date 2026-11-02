"""Shared earbud output, microphone recovery and device selection."""
import threading
import time
import numpy as np
import sounddevice as sd

RATE = 48000

class Ear:
    """An always-open output stream to the earbud. It plays silence between cues, so a Bluetooth earbud stays
    awake and the start of the guide isn't swallowed."""

    def __init__(self, device):
        self.buf, self.pos, self.lock = None, 0, threading.Lock()
        self.gain = 1.0
        self.stream = sd.OutputStream(samplerate=RATE, channels=2, device=device, dtype="float32", callback=self._fill)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

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


class Devices:
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
        self.ear, self.ear_name = None, None
        if name:
            self.ear, self.ear_name = Ear(name), name

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
        while not self._closed.wait(1.0):
            with self.lock:
                if self._closed.is_set():
                    return
                if self.stage == "idle" and time.time() - self.last_cb > 1.0:
                    try:
                        self.mic.close()
                        self._open_mic()
                    except Exception as e:
                        self.note = f"Mic won't open: {e}"

