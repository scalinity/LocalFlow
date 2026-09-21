"""Microphone capture with a live level meter for the overlay."""

import math
import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate=16000, input_device=None, block_ms=50):
        self.sample_rate = sample_rate
        self.input_device = input_device
        self.blocksize = int(sample_rate * block_ms / 1000)
        # 0..1 speech level for the visualizer, updated from the audio thread
        self.level = 0.0
        # Capture diagnostics for the last recording, filled in by stop()
        self.stats = {}
        self.device_name = "?"
        # Adaptive meter range (dB), tracked per session
        self._floor_db = -55.0
        self._peak_db = -30.0
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._overflow_blocks = 0
        self._blocks = 0
        self._voiced_blocks = 0
        self._silent_run = 0

    def _resolve_device(self):
        if self.input_device is None:
            return None
        if isinstance(self.input_device, int):
            return self.input_device
        for i, dev in enumerate(sd.query_devices()):
            if (
                dev["max_input_channels"] > 0
                and str(self.input_device).lower() in dev["name"].lower()
            ):
                return i
        print(f"[localflow] input device {self.input_device!r} not found, using default")
        return None

    def _callback(self, indata, frames, time_info, status):
        if status and status.input_overflow:
            # PortAudio dropped mic frames — that stretch of speech is gone
            self._overflow_blocks += 1
        data = indata[:, 0].copy()
        with self._lock:
            self._frames.append(data)
        rms = float(np.sqrt(np.mean(np.square(data))))
        db = 20.0 * math.log10(rms + 1e-9)
        # Auto-gain with a noise gate: scale relative to a tracked ambient
        # floor (fast down, very slow up so speech can't drag it along) and
        # speech peak (instant up, ~3 dB/s decay, kept well above floor).
        # Anything within 9 dB of the floor — or below -58 dB absolute —
        # is treated as silence so the bars sit still in a quiet room.
        k = 0.3 if db < self._floor_db else 0.003
        self._floor_db += (db - self._floor_db) * k
        self._peak_db = max(self._peak_db - 0.15, db, self._floor_db + 24.0)
        gate = max(self._floor_db + 9.0, -58.0)
        span = max(self._peak_db - gate, 14.0)
        self.level = min(1.0, max(0.0, (db - gate) / span)) ** 0.85
        self._blocks += 1
        if db > gate:
            self._voiced_blocks += 1
            self._silent_run = 0
        else:
            self._silent_run += 1

    def start(self):
        if self._stream is not None:
            return
        with self._lock:
            self._frames = []
        self.level = 0.0
        self._floor_db = -55.0
        self._peak_db = -30.0
        self._overflow_blocks = 0
        self._blocks = 0
        self._voiced_blocks = 0
        self._silent_run = 0
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=self._resolve_device(),
            latency="high",
            callback=self._callback,
        )
        self._stream.start()
        try:
            self.device_name = sd.query_devices(self._stream.device)["name"]
        except Exception:
            self.device_name = str(self._stream.device)

    def stop(self) -> np.ndarray:
        """Stop capture and return the recorded mono float32 buffer."""
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        self.level = 0.0
        with self._lock:
            frames, self._frames = self._frames, []
        buf = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        block_sec = self.blocksize / self.sample_rate
        self.stats = {
            "duration_sec": len(buf) / self.sample_rate,
            "device": self.device_name,
            "overflow_blocks": self._overflow_blocks,
            "voiced_pct": 100.0 * self._voiced_blocks / self._blocks if self._blocks else 0.0,
            "trailing_silence_sec": self._silent_run * block_sec,
        }
        return buf

    @property
    def recording(self):
        return self._stream is not None
