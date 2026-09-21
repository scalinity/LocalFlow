#!/usr/bin/env python
"""Download the Parakeet model and verify end-to-end transcription — no mic needed.

Uses macOS `say` to synthesize a spoken sample, then transcribes it.
"""

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from localflow.config import load  # noqa: E402
from localflow.stt import Transcriber  # noqa: E402


def main():
    cfg = load()
    t = Transcriber(cfg["model"])
    print(f"Loading {cfg['model']} (first run downloads ~1.2 GB)...", flush=True)
    t.load()
    print("Model loaded and warmed up.", flush=True)

    aiff = pathlib.Path(tempfile.mkdtemp()) / "sample.aiff"
    phrase = "Hello world. This is a private, local dictation test."
    subprocess.run(["say", "-o", str(aiff), phrase], check=True)

    audio, sr = sf.read(str(aiff), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != cfg["sample_rate"]:
        import librosa

        audio = librosa.resample(audio, orig_sr=sr, target_sr=cfg["sample_rate"])

    text = t.transcribe(np.asarray(audio, dtype=np.float32))
    print(f"Spoken:      {phrase}")
    print(f"Transcribed: {text}")
    if not text:
        sys.exit("FAIL: empty transcription")
    print("OK")


if __name__ == "__main__":
    main()
