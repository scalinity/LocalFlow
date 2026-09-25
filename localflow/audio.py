"""Microphone capture with a live level meter for the overlay."""

import math
import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate=16000, input_device=None, block_ms=50,
                 notifier=None):
        self.sample_rate = sample_rate
        self.input_device = input_device
        self.blocksize = int(sample_rate * block_ms / 1000)
        # V2 hook (M02): routes device-resolution warnings into the dated
        # event log instead of a bare print. Optional; None keeps the
        # previous behavior.
        self.notifier = notifier
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
        # M03: per-dictation capture journal (set by the app before start;
        # None keeps the pre-M03 memory-only behavior). The callback only
        # enqueues into it — never disk work on the audio thread.
        self.journal = None
        self.callback_error = None
        self._device_index = None
        # M03: a capture discontinuity (device loss) recorded by the app
        # watchdog; stop() folds it into stats so it survives the rebuild.
        self.discontinuity = None
        self.teardown_error = None

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
        if self.notifier is not None:
            self.notifier(f"input device {self.input_device!r} not found,"
                          " using default")
        else:
            print(f"[localflow] input device {self.input_device!r} not found, using default")
        return None

    def _callback(self, indata, frames, time_info, status):
        try:
            if status and status.input_overflow:
                # PortAudio dropped mic frames — that stretch of speech is gone
                self._overflow_blocks += 1
            data = indata[:, 0].copy()
            if self.journal is not None:
                self.journal.handoff_block(data)  # bounded, non-blocking
        except Exception as e:  # device loss mid-callback must not kill the
            # PortAudio thread silently: record it; the app watchdog ends
            # capture at its next tick, preserving everything so far.
            self.callback_error = type(e).__name__
            return
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
        self.callback_error = None
        self.teardown_error = None
        device = self._resolve_device()
        self._device_index = device
        # M03-AUDIT-11: the stream is owned only once it has started. A
        # constructor or start() failure closes what was built and leaves
        # no stale reference behind, so the next start() really opens a
        # fresh stream instead of returning early on a dead one.
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=device,
            latency="high",
            callback=self._callback,
        )
        try:
            stream.start()
        except BaseException:
            try:
                stream.close()
            except Exception:
                pass
            raise
        self._stream = stream
        try:
            self.device_name = sd.query_devices(self._stream.device)["name"]
        except Exception:
            self.device_name = str(self._stream.device)

    def stop(self) -> np.ndarray:
        """Stop capture and return the recorded mono float32 buffer.

        Exception-safe (M03-AUDIT-11): a stream stop/close failure (a
        device that vanished mid-teardown) never discards the buffered
        speech or skips the journal finalization — the failure is recorded
        as ``stream_teardown_error`` (exception class only) and the capture
        still returns everything the callback delivered."""
        stream, self._stream = self._stream, None
        teardown = []
        if stream is not None:
            try:
                stream.stop()
            except Exception as e:
                teardown.append(type(e).__name__)
            try:
                stream.close()
            except Exception as e:
                teardown.append(type(e).__name__)
        self.teardown_error = teardown[0] if teardown else None
        self.level = 0.0
        with self._lock:
            frames, self._frames = self._frames, []
        journal, self.journal = self.journal, None
        journal_stats = {}
        if journal is not None:
            try:
                journal_stats = journal.finalize()
            except Exception as e:
                journal_stats = {"degraded": True,
                                 "degrade_reason": type(e).__name__}
        buf = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        block_sec = self.blocksize / self.sample_rate
        self.stats = {
            "duration_sec": len(buf) / self.sample_rate,
            "device": self.device_name,
            "overflow_blocks": self._overflow_blocks,
            "voiced_pct": 100.0 * self._voiced_blocks / self._blocks if self._blocks else 0.0,
            "trailing_silence_sec": self._silent_run * block_sec,
            # The live capture is this in-memory buffer — complete even
            # when the crash journal dropped blocks or has not finished
            # writing. Journal state is crash-recovery diagnostics only,
            # never a discontinuity of the audio used (M03-AUDIT-08/19).
            "crash_journal": {
                "enabled": journal is not None,
                "queue_dropped": journal_stats.get("queue_dropped", 0),
                "degraded": journal_stats.get("degraded", False),
                "finalized": journal_stats.get("finalized"),
                "writer_alive": journal_stats.get("writer_alive"),
            },
        }
        if teardown:
            self.stats["stream_teardown_error"] = teardown[0]
        if self.discontinuity is not None:
            self.stats["device_discontinuity"] = self.discontinuity
            self.discontinuity = None
        return buf

    @property
    def recording(self):
        return self._stream is not None

    def capture_health(self) -> dict:
        """Device/callback health for the app watchdog (M03 task 5): a dead
        stream, a captured callback exception, or an input device that
        vanished from the system while recording. Reported, never guessed —
        the caller decides how to end the capture."""
        if self._stream is None:
            return {"ok": True}
        try:
            active = bool(self._stream.active)
        except Exception:
            active = False
        device_gone = False
        if self._device_index is not None:
            try:
                dev = sd.query_devices(self._device_index)
                device_gone = dev["max_input_channels"] < 1
            except Exception:
                device_gone = True  # index no longer exists
        return {
            "ok": active and self.callback_error is None and not device_gone,
            "stream_active": active,
            "callback_error": self.callback_error,
            "device_gone": device_gone,
            "device": self.device_name,
        }
