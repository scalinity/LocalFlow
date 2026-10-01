"""The default replay backend must build a real NSSound from WAV bytes.

Every other replay test injects a fake sound factory, so the real one was
never exercised: it called an NSSound class method that does not exist
and the Hub's Play button failed with an AttributeError. This builds the
sound without playing it (silent, no audio device needed).

Run: .venv/bin/python tests/v2/ui/test_replay_real_backend.py
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.ui.replay import ReplayService, pcm16_wav_bytes  # noqa: E402


def test_default_factory_builds_a_sound():
    samples = np.zeros(1600, dtype="float32")  # 0.1 s of silence
    wav = pcm16_wav_bytes(samples, 16000)
    sound = ReplayService._nssound_factory(wav)
    assert sound is not None
    assert 0.05 < sound.duration() < 0.2, sound.duration()


def test_default_factory_rejects_garbage():
    try:
        ReplayService._nssound_factory(b"not a wav file")
    except ValueError:
        return
    raise AssertionError("garbage bytes must raise ValueError")


if __name__ == "__main__":
    tests = (test_default_factory_builds_a_sound,
             test_default_factory_rejects_garbage)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} replay backend tests passed")
