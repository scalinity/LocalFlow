"""Audio replay for the Hub (V2 M09, Spec S19 History/Training Data).

One replay at a time: starting a new item stops the previous one (S19).
Playback is a monitoring derivative only — the float32 original
artifact is never touched; a PCM16 WAV is rendered in memory for the
sound backend and discarded. Missing/purged/expired audio reports an
honest reason and never fabricates a substitute (M09-AC02).
"""

from __future__ import annotations

import struct

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
        self._factory = sound_factory if sound_factory is not None \
            else self._nssound_factory
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
            return avail
        try:
            payload = store.artifact_payload(artifact_id)
            if payload is None:
                return {"available": False, "reason": "payload_missing"}
            # artifact_payload returns the ndarray for audio; the sample
            # rate rides the artifact meta.
            art = store.artifact(artifact_id)
            import json as _json
            rate = int(_json.loads(art["meta_json"] or "{}").get(
                "sample_rate") or 16000)
            data = pcm16_wav_bytes(payload, rate)
            sound = self._factory(data)
            self.stop()
            self._sound = sound
            self.last_played_artifact = artifact_id
            if not sound.play():
                self._sound = None
                return {"available": False, "reason": "playback_failed"}
            return {"available": True, "status": "playing",
                    "artifact_id": artifact_id}
        except Exception as e:
            return {"available": False, "reason": type(e).__name__}

    def stop(self):
        if self._sound is not None:
            try:
                self._sound.stop()
            except Exception:
                pass
            self._sound = None

    def is_playing(self) -> bool:
        try:
            return bool(self._sound and self._sound.isPlaying())
        except Exception:
            return False
