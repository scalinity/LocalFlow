"""Audio replay for the Hub (V2 M09, Spec S19 History/Training Data).

One replay at a time: starting a new item stops the previous one (S19),
and so does a request for an item that turns out to be unavailable —
the sound playing is always the item last asked for, or nothing.
Playback is a monitoring derivative only — the float32 original
artifact is never touched; a PCM16 WAV is rendered in memory for the
sound backend and discarded. Missing/purged/expired audio reports an
honest reason and never fabricates a substitute (M09-AC02).

Revocation: delete-everywhere reaches ``revoke_job`` from the store's
deletion listener (writer thread, flags only). A prepared buffer of a
revoked job never starts; an active one is stopped on the main thread
through ``stop_revoked`` and its sound/buffer references are dropped.
A successful ``play()`` start is what the caller may treat as the
listening gate — never proof the whole recording was heard.
"""

from __future__ import annotations

import struct
import threading

import numpy as np


def pcm16_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Render a PCM16 WAV in memory (playback-only derivative)."""
    data = (np.clip(np.asarray(samples), -1.0, 1.0) * 32767).astype(
        "<i2").tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1, int(sample_rate),
        int(sample_rate) * 2, 2, 16,
        b"data", len(data))
    return header + data


class ReplayService:
    """``play_artifact`` loads the retained audio through the store's
    sanctioned read path and hands PCM16 bytes to the sound backend
    (NSSound by default; tests inject a fake)."""

    def __init__(self, sound_factory=None):
        self._sound = None
        self._current = None  # {"job_id", "artifact_id"} of _sound
        self._factory = sound_factory if sound_factory is not None \
            else self._nssound_factory
        self._lock = threading.RLock()
        self._revoked_jobs = set()
        self.last_played_artifact = None

    @staticmethod
    def _nssound_factory(wav_bytes: bytes):
        from AppKit import NSSound
        sound = NSSound.soundWithData_(wav_bytes)
        if sound is None:
            raise ValueError("sound backend rejected the wav data")
        return sound

    def availability(self, store, artifact_id) -> dict:
        if not artifact_id:
            return {"available": False, "reason": "no_audio_artifact"}
        art = store.artifact(artifact_id)
        if art is None:
            return {"available": False, "reason": "artifact_missing"}
        if art.get("job_id") in self._revoked_jobs:
            return {"available": False, "reason": "deleted"}
        if art["purged"]:
            return {"available": False, "reason": "purged"}
        if not art["content_path"]:
            return {"available": False, "reason": "payload_missing"}
        return {"available": True}

    def play_artifact(self, store, artifact_id) -> dict:
        """Stop whatever is playing, then play this artifact's audio.
        Returns the honest status; a failure never raises into the UI."""
        avail = self.availability(store, artifact_id)
        if not avail["available"]:
            self.stop()
            return avail
        try:
            payload = store.artifact_payload(artifact_id)
            if payload is None:
                self.stop()
                return {"available": False, "reason": "payload_missing"}
            # artifact_payload returns the ndarray for audio; the sample
            # rate rides the artifact meta.
            art = store.artifact(artifact_id)
            import json as _json
            rate = int(_json.loads(art["meta_json"] or "{}").get(
                "sample_rate") or 16000)
            data = pcm16_wav_bytes(payload, rate)
            sound = self._factory(data)
            with self._lock:
                # The revocation check and the start are one step: a
                # deletion that landed while the buffer was prepared
                # discards it here, before anything plays.
                if art.get("job_id") in self._revoked_jobs:
                    self._stop_locked()
                    return {"available": False, "reason": "deleted"}
                self._stop_locked()
                self._sound = sound
                self._current = {"job_id": art.get("job_id"),
                                 "artifact_id": artifact_id}
                self.last_played_artifact = artifact_id
                started = sound.play()
                if not started:
                    self._sound = None
                    self._current = None
                    self.last_played_artifact = None
            if not started:
                return {"available": False, "reason": "playback_failed"}
            return {"available": True, "status": "playing",
                    "artifact_id": artifact_id}
        except Exception as e:
            self.stop()
            return {"available": False, "reason": type(e).__name__}

    def revoke_job(self, job_id) -> bool:
        """Deletion listener side (writer thread): flags only. Returns
        True when the current sound belongs to the job — the caller
        then schedules ``stop_revoked`` on the main thread."""
        if not job_id:
            return False
        with self._lock:
            self._revoked_jobs.add(job_id)
            return bool(self._current
                        and self._current.get("job_id") == job_id)

    def stop_revoked(self):
        """Main thread: stop and drop a sound whose job was revoked."""
        with self._lock:
            if self._current and self._current.get("job_id") in \
                    self._revoked_jobs:
                self._stop_locked()

    def stop_unavailable(self, store):
        """Main thread, after a retention pass: stop and drop a sound
        whose artifact is no longer available (purged or gone)."""
        with self._lock:
            current = self._current
        if current is None:
            return
        avail = self.availability(store, current.get("artifact_id"))
        if not avail.get("available"):
            with self._lock:
                if self._current is current:
                    self._stop_locked()

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        if self._sound is not None:
            try:
                self._sound.stop()
            except Exception:
                pass
        self._sound = None
        self._current = None

    def is_playing(self) -> bool:
        try:
            return bool(self._sound and self._sound.isPlaying())
        except Exception:
            return False
