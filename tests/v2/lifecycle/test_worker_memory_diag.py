"""Worker memory diagnostics: one switch, six labels, numbers only.

Runs the PRODUCTION worker (``Worker.serve``) through
``prod_worker_harness.py`` — only the two model loaders are shimmed — and
reads the raw protocol frames. Nothing here measures a model: the counters
are the real ``mlx.core`` memory counters of the harness process, so these
checks prove the frames and their placement, not any footprint figure.

  * LOCALFLOW_WORKER_MEMORY_DIAG unset or not "1": the frame stream holds
    no memory diag frame at all.
  * LOCALFLOW_WORKER_MEMORY_DIAG=1: exactly six labels appear, in lifecycle
    order, each frame carrying the label and three byte counts and nothing
    else; every other frame is the frame the switch-off run produces.

Run: .venv/bin/python tests/v2/lifecycle/test_worker_memory_diag.py
"""

import json
import os
import pathlib
import subprocess
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, run, tmpdir, wav  # noqa: E402

LABELS = ["asr_loaded", "asr_warmed", "cleanup_loaded", "cleanup_warmed",
          "asr_result", "cleanup_result"]
MEMORY_KEYS = {"v", "op", "kind", "label", "active", "cached", "peak"}


def _send(proc, msg):
    data = json.dumps(msg).encode()
    proc.stdin.write(len(data).to_bytes(4, "big") + data)
    proc.stdin.flush()


def _recv(proc):
    head = proc.stdout.read(4)
    if len(head) < 4:
        return None
    return json.loads(proc.stdout.read(int.from_bytes(head, "big")))


def _session(memory_diag):
    """One load, one transcription, one cleanup, shutdown: every frame the
    worker wrote, in order. ``memory_diag`` is the env value or None."""
    with tmpdir() as td:
        td = pathlib.Path(td)
        wav(td / "audio", "clip.wav")
        plan = td / "plan.json"
        plan.write_text(json.dumps({"transcribe": ["ok:asr text"],
                                    "clean": ["ok:CLEANED"]}))
        env = dict(os.environ, LOCALFLOW_PROD_WORKER_PLAN=str(plan),
                   LOCALFLOW_CODE_ROOT=str(ROOT))
        env.pop("LOCALFLOW_WORKER_MEMORY_DIAG", None)
        if memory_diag is not None:
            env["LOCALFLOW_WORKER_MEMORY_DIAG"] = memory_diag
        proc = subprocess.Popen(
            [sys.executable, str(PROD), "--audio-root", str(td / "audio")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, cwd=ROOT)
        watchdog = threading.Timer(60, proc.kill)
        watchdog.start()
        frames = []
        try:
            frames.append(_recv(proc))  # hello
            _send(proc, {"v": 1, "op": "load", "asr_model": "fake-asr",
                         "cleanup_model": "fake-llm", "cleanup_mode": "llm",
                         "cleanup_implementation": "v2"})
            ready = set()
            while len(ready) < 2:
                f = _recv(proc)
                frames.append(f)
                if f["op"] == "engine" and f["state"] == "ready":
                    ready.add(f["engine"])
            _send(proc, {"v": 1, "op": "transcribe", "req_id": "r1",
                         "generation": 1, "attempt": 1, "job_id": "j1",
                         "audio": {"name": "clip.wav"}, "sample_rate": 16000})
            while True:
                f = _recv(proc)
                frames.append(f)
                if f["op"] == "result":
                    break
            _send(proc, {"v": 1, "op": "clean", "req_id": "r2",
                         "generation": 1, "attempt": 1, "job_id": "j1",
                         "raw_text": "um hello"})
            while True:
                f = _recv(proc)
                frames.append(f)
                if f["op"] == "result":
                    break
            _send(proc, {"v": 1, "op": "shutdown"})
            while True:
                f = _recv(proc)
                if f is None:
                    break
                frames.append(f)
            proc.wait(timeout=30)
        finally:
            watchdog.cancel()
            proc.kill()
            proc.stdin.close()
            proc.stdout.close()
        return frames


def _is_memory(frame):
    return frame["op"] == "diag" and frame.get("kind") == "memory"


def _memory(frames):
    return [f for f in frames if _is_memory(f)]


def _stable(frame):
    """A frame minus the fields that legitimately differ run to run."""
    return {k: v for k, v in frame.items()
            if k not in ("pid", "duration_ms", "python")}


def test_switch_off_writes_no_memory_frame():
    for value in (None, "0", ""):
        frames = _session(value)
        assert not _memory(frames), (value, _memory(frames))
        assert not [f for f in frames if f["op"] == "diag"], value
        engines = [(f["engine"], f["state"]) for f in frames
                   if f["op"] == "engine"]
        assert engines == [("asr", "loading"), ("asr", "warming"),
                           ("asr", "ready"), ("cleanup", "loading"),
                           ("cleanup", "ready")], engines
    print("ok  memory switch off (unset, 0, empty): no diag frame, engine"
          " states unchanged")


def test_switch_on_writes_exactly_six_labels_in_order():
    frames = _session("1")
    memory = _memory(frames)
    assert [f["label"] for f in memory] == LABELS, \
        [f["label"] for f in memory]
    for f in memory:
        assert set(f) == MEMORY_KEYS, set(f) ^ MEMORY_KEYS
        assert f["v"] == 1
        for k in ("active", "cached", "peak"):
            assert isinstance(f[k], int) and not isinstance(f[k], bool) \
                and f[k] >= 0, (f["label"], k, f[k])
    print("ok  memory switch on: six labels in lifecycle order, numbers only")


def test_switch_on_changes_nothing_but_the_memory_frames():
    off = [_stable(f) for f in _session(None)]
    on = [_stable(f) for f in _session("1") if not _is_memory(f)]
    assert on == off, "engine, result or hello frame differs with the switch on"
    print("ok  memory switch on: every non-memory frame equals the"
          " switch-off frame")


def main():
    run([test_switch_off_writes_no_memory_frame,
         test_switch_on_writes_exactly_six_labels_in_order,
         test_switch_on_changes_nothing_but_the_memory_frames],
        "worker memory diag tests")


if __name__ == "__main__":
    main()
