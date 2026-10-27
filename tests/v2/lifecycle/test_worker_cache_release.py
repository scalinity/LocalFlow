"""Worker allocator release: one ``mx.clear_cache`` after each engine's load.

Runs the PRODUCTION worker (``Worker.serve``) through
``prod_worker_harness.py`` — only the two model loaders are shimmed, and the
harness traces every ``mx.clear_cache`` call and every frame the worker
writes, with the calling thread. Nothing here measures a model or a footprint;
these checks prove WHERE the release runs, not how much it frees.

  * Once after the ASR load and warmup, once after the cleanup load and
    warmup, each before that engine's ``ready`` frame, both on the GPU
    thread, and never on the control thread.
  * No release while a request runs: a session with a transcription and a
    cleanup still holds exactly those two.
  * The frame stream is the same with and without the memory switch (the
    release does not depend on it), and carries no frame of its own.
  * A release that raises does not fail the engine it follows.

Run: .venv/bin/python tests/v2/lifecycle/test_worker_cache_release.py
"""

import json
import os
import pathlib
import subprocess
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, run, tmpdir, wav  # noqa: E402

GPU_THREAD = "localflow-worker-gpu"
LOAD_ORDER = ["asr_loaded", "clear_cache", "engine:asr:ready",
              "cleanup_loaded", "clear_cache", "engine:cleanup:ready"]
FRAME_STREAM = ["hello", "engine:asr:loading", "engine:asr:warming",
                "engine:asr:ready", "engine:cleanup:loading",
                "engine:cleanup:ready", "result", "result"]


def _send(proc, msg):
    data = json.dumps(msg).encode()
    proc.stdin.write(len(data).to_bytes(4, "big") + data)
    proc.stdin.flush()


def _recv(proc):
    head = proc.stdout.read(4)
    if len(head) < 4:
        return None
    return json.loads(proc.stdout.read(int.from_bytes(head, "big")))


def _session(memory_diag=None, clear_fails=False, code_root=ROOT):
    """One load, one transcription, one cleanup, shutdown. Returns the frames
    the worker wrote and the harness trace (shim events, clears and frames
    in call order)."""
    with tmpdir() as td:
        td = pathlib.Path(td)
        wav(td / "audio", "clip.wav")
        record = td / "record.jsonl"
        plan = td / "plan.json"
        plan.write_text(json.dumps({
            "transcribe": ["ok:asr text"], "clean": ["ok:CLEANED"],
            "record": str(record), "trace_clears": True,
            "clear_cache_fails": clear_fails}))
        env = dict(os.environ, LOCALFLOW_PROD_WORKER_PLAN=str(plan),
                   LOCALFLOW_CODE_ROOT=str(code_root))
        env.pop("LOCALFLOW_WORKER_MEMORY_DIAG", None)
        if memory_diag is not None:
            env["LOCALFLOW_WORKER_MEMORY_DIAG"] = memory_diag
        proc = subprocess.Popen(
            [sys.executable, str(PROD), "--audio-root", str(td / "audio")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, cwd=code_root)
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
        trace = [json.loads(line) for line in
                 record.read_text().splitlines()]
        return frames, trace


def _clears(trace):
    return [e for e in trace if e["event"] == "clear_cache"]


def _load_order(trace, with_samples=False):
    """The trace reduced to the load-time events whose order matters."""
    out = []
    for e in trace:
        if e["event"] in ("asr_loaded", "cleanup_loaded", "clear_cache"):
            out.append(e["event"])
        elif e["event"] == "frame" and e["op"] == "engine" \
                and e["state"] == "ready":
            out.append(f"engine:{e['engine']}:ready")
        elif with_samples and e["event"] == "frame" and e["op"] == "diag" \
                and e["label"] in ("asr_warmed", "cleanup_warmed"):
            out.append(f"diag:{e['label']}")
    return out


def _shape(frames):
    """Each non-diag frame as its protocol shape, in order."""
    out = []
    for f in frames:
        if f["op"] == "diag":
            continue
        out.append(f"engine:{f['engine']}:{f['state']}"
                   if f["op"] == "engine" else f["op"])
    return out


def test_one_clear_after_each_engine_load_before_its_ready_frame():
    _, trace = _session()
    assert _load_order(trace) == LOAD_ORDER, _load_order(trace)
    print("ok  one clear after each engine load, before that engine's ready"
          " frame")


def test_clears_run_on_the_gpu_thread_never_the_control_thread():
    _, trace = _session()
    control = [e["thread"] for e in trace
               if e["event"] == "frame" and e["op"] == "hello"]
    assert control and control[0] != GPU_THREAD, control
    threads = [e["thread"] for e in _clears(trace)]
    assert threads == [GPU_THREAD, GPU_THREAD], threads
    print("ok  both clears ran on the GPU thread, not the control thread")


def test_no_clear_runs_while_a_request_runs():
    _, trace = _session()
    assert len(_clears(trace)) == 2, _clears(trace)
    names = [e["event"] if e["event"] != "frame" else
             f"frame:{e['op']}" for e in trace]
    first_request = names.index("transcribe")
    assert "clear_cache" not in names[first_request:], names
    print("ok  a transcription and a cleanup add no clear")


def test_frame_stream_and_clear_placement_ignore_the_memory_switch():
    off_frames, off_trace = _session(None)
    on_frames, on_trace = _session("1")
    assert _shape(off_frames) == FRAME_STREAM, _shape(off_frames)
    assert _shape(on_frames) == FRAME_STREAM, _shape(on_frames)
    assert not [f for f in off_frames if f["op"] == "diag"]
    assert _load_order(off_trace) == LOAD_ORDER
    assert _load_order(on_trace) == LOAD_ORDER
    print("ok  frame stream and clear placement equal with the memory switch"
          " on and off")


def test_memory_samples_after_a_warmup_follow_its_clear():
    _, trace = _session("1")
    assert _load_order(trace, with_samples=True) == [
        "asr_loaded", "clear_cache", "diag:asr_warmed", "engine:asr:ready",
        "cleanup_loaded", "clear_cache", "diag:cleanup_warmed",
        "engine:cleanup:ready"], _load_order(trace, with_samples=True)
    print("ok  warmed-label counters read the state after the clear")


def test_a_failing_clear_does_not_fail_the_engine():
    frames, trace = _session(clear_fails=True)
    assert len(_clears(trace)) == 2, _clears(trace)
    assert _shape(frames) == FRAME_STREAM, _shape(frames)
    assert not [f for f in frames if f.get("state") == "failed"]
    print("ok  a clear that raises leaves both engines ready")


def main():
    run([test_one_clear_after_each_engine_load_before_its_ready_frame,
         test_clears_run_on_the_gpu_thread_never_the_control_thread,
         test_no_clear_runs_while_a_request_runs,
         test_frame_stream_and_clear_placement_ignore_the_memory_switch,
         test_memory_samples_after_a_warmup_follow_its_clear,
         test_a_failing_clear_does_not_fail_the_engine],
        "worker cache release tests")


if __name__ == "__main__":
    main()
