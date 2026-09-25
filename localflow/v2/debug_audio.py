"""Transcript-logging debug audio copies, owned by their job (M02-AUDIT-02).

With ``log_transcripts`` on, the app keeps a PCM16 copy of the newest few
dictations under ``~/Library/Logs/LocalFlow-audio`` for replaying a bad
transcript. Before the M02 remediation those files were named by
timestamp only, so delete-everywhere could not find a job's copy. The
name now carries the job id after the timestamp (the newest-N rotation
still sorts by timestamp), and the app registers the directory with the
store's job-scoped deletion using ``job_pattern``. Legacy timestamp-only
files are left to the unchanged rotation: their owner is unknown, and
ownership is never guessed.

The copy is a quantized DERIVATIVE, never the original evidence (the
float32 artifact is — S29.5).
"""

import os
import pathlib
import time

import numpy as np

from .store import write_wav_pcm16

PREFIX = "dictation-"


def debug_name(job_id, seq, stamp=None) -> str:
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    owner = job_id if job_id else "nojob"
    return f"{PREFIX}{stamp}-{seq:03d}-{owner}.wav"


def job_pattern(job_id) -> str:
    """Glob matching exactly this job's debug copies."""
    return f"{PREFIX}*-{job_id}.wav"


def write_debug_copy(directory, job_id, audio, sample_rate, *, keep=5,
                     seq=1, publish=None) -> pathlib.Path:
    """Write one debug copy. It is staged under a name the job's
    ``job_pattern`` and the rotation glob both own (so a crash-left staged
    file is deleted with its job and rotated away — M03 review R2), then
    published by ``publish(staged, final)`` — the app passes the store's
    deletion arbitration (M03-AUDIT-02); a refused publish (False) removes
    the staged file and returns None."""
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = directory / debug_name(job_id, seq, stamp)
    owner = job_id if job_id else "nojob"
    staged = directory / (f"{PREFIX}{stamp}-{seq:03d}-part"
                          f"{os.getpid()}{time.monotonic_ns() % 10**8}"
                          f"-{owner}.wav")
    try:
        write_wav_pcm16(staged, np.asarray(audio, dtype=np.float32),
                        int(sample_rate), atomic=False)
        ok = publish(staged, path) if publish is not None \
            else (os.replace(staged, path) or True)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    if not ok:
        staged.unlink(missing_ok=True)
        return None
    for old in sorted(directory.glob(f"{PREFIX}*.wav"))[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    return path
