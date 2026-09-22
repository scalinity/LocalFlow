"""EV-05 / M03: worker protocol, faults, generations, stale results.

Drives the real WorkerSupervisor against the test-owned fake worker
(fake_worker.py) — fresh subprocesses, the length-framed JSON protocol, and
deterministic fault injection covering the M03 acceptance items:

  M03-AC01  one injected fault → fresh worker → retry succeeds; a second
            fault → recoverable failure, no infinite restart loop
  M03-AC02  stale-generation results are discarded; cancelled jobs never
            insert or double-count
  (readiness races / cleanup fallback labeling: test_lifecycle.py + the
   honest-path assertions here on the clean result's `path`)

Run: .venv/bin/python tests/v2/lifecycle/test_worker_protocol.py
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store, supervisor as sup_mod  # noqa: E402
from localflow.v2.supervisor import WorkerFailure, WorkerSupervisor  # noqa: E402

FAKE = pathlib.Path(__file__).resolve().parent / "fake_worker.py"


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, kw))

    def count(self, name):
        return sum(1 for e, _ in self.events if e == name)

    def last(self, name):
        for e, kw in reversed(self.events):
            if e == name:
                return kw
        return None


def make_sup(td, plan, **kw):
    plan_path = pathlib.Path(td) / "plan.json"
    plan_path.write_text(json.dumps(plan))
    rec = Rec()
    s = WorkerSupervisor(
        audio_root=pathlib.Path(td) / "audio",
        asr_model="fake-asr", cleanup_mode="llm", cleanup_model="fake-llm",
        emit=rec, worker_cmd=[sys.executable, str(FAKE)],
        spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan_path)},
        hello_timeout=15.0, ready_timeout=30.0, request_timeout=30.0, **kw)
    return s, rec


def test_protocol_handshake_and_result():
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-a.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(1600, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["ok:hello from fake"],
                               "clean": ["ok:CLEANED|path=llm|obs=2"]})
        try:
            res = s.transcribe(job_id="job-a", attempt=1,
                               audio_name=wav.name)
            assert res["text"] == "hello from fake"
            assert res["generation"] == 1 and res["attempt"] == 1
            assert s.engine_state["asr"] == "ready"
            out = s.clean(job_id="job-a", attempt=1, raw_text="um hello")
            assert out["text"] == "CLEANED" and out["path"] == "llm"
            assert len(out["observations"]) == 2
            assert all("prompt" in o for o in out["observations"])
        finally:
            s.shutdown()
        print("ok  protocol: handshake, engines, transcribe, clean")


def test_injected_fault_recovers_once():
    """M03-AC01: fault → fresh worker generation → retry succeeds with
    attempt+1; audio preserved is the caller's journal concern (the file
    the worker reads is untouched by the fault)."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-b.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.linspace(-0.1, 0.1, 16000,
                                             dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["fault:InjectedMetalError",
                                              "ok:recovered after restart"],
                               "clean": ["ok:OK|path=llm"]})
        try:
            res = s.transcribe(job_id="job-b", attempt=1,
                               audio_name=wav.name)
            assert res["text"] == "recovered after restart"
            assert res["retried"] is True
            assert res["attempt"] == 2, "the retry is a new attempt"
            assert s.generation == 2, "a fresh worker process handled it"
            assert rec.count("worker.spawned") == 2
            assert rec.last("worker.fault")["reason_code"] == "injected_fault"
            # The input audio survived the fault untouched.
            arr, rate = store.read_wav_f32(wav)
            assert arr.size == 16000 and rate == 16000
        finally:
            s.shutdown()
        print("ok  injected Metal fault: one restart, retry succeeds (AC01)")


def test_second_fault_is_recoverable_not_looping():
    """M03-AC01: the retry faulting too raises WorkerFailure — no third
    spawn for the job, no loop."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-c.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(100, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["fault:InjectedMetalError",
                                              "fault:InjectedMetalError"],
                               "clean": []})
        try:
            try:
                s.transcribe(job_id="job-c", attempt=1, audio_name=wav.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code == "injected_fault"
            assert s.generation == 2
            assert rec.count("worker.spawned") == 2, \
                "exactly one automatic restart, then it stops"
        finally:
            s.shutdown()
        print("ok  second fault: recoverable failure, restart loop stopped")


def test_circuit_breaker_fails_fast():
    """Repeated deaths with zero successful stages trip the breaker; work
    fails fast afterwards; a manual restart re-arms it."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-d.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(100, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["crash"] * 3, "clean": []})
        try:
            # Request 1: crash → death 1 → retry on a fresh worker → crash
            # → death 2 → WorkerFailure (this is M03-AC01's loop stop).
            try:
                s.transcribe(job_id="job-d", attempt=1, audio_name=wav.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure:
                pass
            # Request 2: fresh worker → crash → death 3 trips the breaker.
            try:
                s.transcribe(job_id="job-d", attempt=1, audio_name=wav.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code in ("supervisor_breaker_tripped",
                                         "worker_process_exited"), \
                    e.reason_code
            assert s.supervisor_state == "failed"
            spawns_before = rec.count("worker.spawned")
            # Request 3 fails fast — no further spawning.
            try:
                s.transcribe(job_id="job-d", attempt=1, audio_name=wav.name)
                raise AssertionError("expected fail-fast")
            except WorkerFailure as e:
                assert e.reason_code == "supervisor_breaker_tripped"
            assert rec.count("worker.spawned") == spawns_before, \
                "fail-fast spawns nothing"
            # Manual restart re-arms (the plan is exhausted → distinct
            # result, proving the fresh worker answered).
            s.restart()
            assert s.supervisor_state == "running"
            res = s.transcribe(job_id="job-d", attempt=1,
                               audio_name=wav.name)
            assert res["text"] == "plan-exhausted"
        finally:
            s.shutdown()
        print("ok  circuit breaker: trips, fails fast, manual restart re-arms")


def test_stale_generation_result_discarded():
    """M03-AC02: an unsolicited result naming an old request/generation is
    discarded with an event and never resolves or double-counts."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-e.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(100, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["stale:evil stale text"],
                               "clean": []})
        try:
            res = s.transcribe(job_id="job-e", attempt=1,
                               audio_name=wav.name)
            assert res["text"] == "after-stale", \
                "the stale frame must not satisfy the request"
            assert rec.count("worker.stale_result_discarded") == 1
            stale = rec.last("worker.stale_result_discarded")
            assert stale["reason_code"] == "unknown_request"
        finally:
            s.shutdown()
        print("ok  stale worker result discarded, never inserted (AC02)")


def test_stale_generation_echo_resolves_as_fault():
    """M03-AC02 (live req_id, old generation): the supervisor discards the
    echo and resolves the request as a StaleGeneration fault — the retried
    request then succeeds on a fresh worker."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-echo.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(100, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"transcribe": ["staleecho:spoofed",
                                              "ok:real answer"],
                               "clean": []})
        try:
            res = s.transcribe(job_id="job-echo", attempt=1,
                               audio_name=wav.name)
            assert res["text"] == "real answer"
            assert res["retried"] is True and res["attempt"] == 2
            # The spoof was discarded as stale (the real answer that
            # follows resolves the retried request, and a later frame for
            # the already-resolved req_id is a second discard).
            codes = [kw["reason_code"] for e, kw in rec.events
                     if e == "worker.stale_result_discarded"]
            assert "stale_generation" in codes, codes
        finally:
            s.shutdown()
        print("ok  stale-generation echo on a live request resolves as fault")


def test_cleanup_wait_and_engine_wait_override():
    """DB1-W5/CA1-W4: the wait policy is bounded by the caller's timeout
    (not the supervisor's internal ready timeout), and clean() never
    blocks on a still-loading cleanup engine — it answers in basic mode
    honestly."""
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "audio" / "job-w.wav"
        wav.parent.mkdir(parents=True)
        store.write_wav_f32(wav, np.zeros(100, dtype=np.float32), 16000)
        s, rec = make_sup(td, {"asr": "ready",
                               "cleanup": "loading_forever",
                               "transcribe": ["ok:t"],
                               "clean": ["ok:fallback|path=basic"
                                         "|reason=cleanup_not_ready"]})
        try:
            # The app only waits after a transcribe has booted the worker.
            assert s.transcribe(job_id="job-w", attempt=1,
                                audio_name=wav.name)["text"] == "t"
            t0 = time.monotonic()
            state = s.wait_engine("cleanup", 0.5)
            waited = time.monotonic() - t0
            assert state == "loading", state
            assert 0.4 <= waited < 5.0, f"wait not bounded: {waited:.2f}s"
            t0 = time.monotonic()
            out = s.clean(job_id="job-w", attempt=1, raw_text="um hi")
            elapsed = time.monotonic() - t0
            assert elapsed < 5.0, \
                f"clean blocked on the loading engine: {elapsed:.2f}s"
            assert out["path"] == "basic"
            assert out["fallback_reason"] == "cleanup_not_ready"
        finally:
            s.shutdown()
        print("ok  cleanup wait bounded; clean never blocks on engine load")


def test_two_queued_captures_fifo():
    """Two jobs submitted while the first is slow: serialized GPU order,
    results in dictation order, no interleave."""
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "audio"
        root.mkdir(parents=True)
        for name in ("job-f1.wav", "job-f2.wav"):
            store.write_wav_f32(root / name, np.zeros(100, dtype=np.float32),
                               16000)
        s, rec = make_sup(td, {"transcribe": ["delay:400|ok:first result",
                                              "ok:second result"],
                               "clean": []})
        done = []

        def run(name, job):
            out = s.transcribe(job_id=job, attempt=1, audio_name=name)
            done.append((time.monotonic(), job, out["text"]))

        try:
            t1 = threading.Thread(target=run, args=("job-f1.wav", "job-f1"))
            t1.start()
            time.sleep(0.05)
            t2 = threading.Thread(target=run, args=("job-f2.wav", "job-f2"))
            t2.start()
            t1.join(30)
            t2.join(30)
            assert len(done) == 2
            # Serialized execution: whichever job ran first consumed the
            # delayed behavior and completed first; the second followed.
            # Requests never swap or share results (req_id matching).
            by_time = [text for _t, _job, text in sorted(done)]
            assert by_time == ["first result", "second result"], by_time
            texts = {text for _t, _job, text in done}
            assert texts == {"first result", "second result"}
        finally:
            s.shutdown()
        print("ok  two queued captures: serialized GPU, ordered results")


def test_worker_cannot_request_insertion():
    """The protocol's dispatch ignores unknown worker→parent ops —
    including anything resembling an insertion request (S06: only the
    parent's coordinator inserts). Verified by feeding one straight
    through the dispatch."""
    with tempfile.TemporaryDirectory() as td:
        s, rec = make_sup(td, {})
        try:
            s._handle_message({"v": 1, "op": "insert_text", "text": "x"},
                              s.generation or 1, None)
            assert rec.count("worker.protocol_error") == 1
            assert rec.last("worker.protocol_error")[
                "reason_code"] == "unknown_op"
        finally:
            s.shutdown()
        print("ok  no insertion op exists; unknown ops ignored")


def test_engine_failure_fails_fast_without_respawn_loop():
    """A model that cannot load (cache miss) fails the engine once — no
    spawn/reload loop — and transcribe raises a structured failure."""
    with tempfile.TemporaryDirectory() as td:
        s, rec = make_sup(td, {"asr": "failed"})
        try:
            try:
                s.transcribe(job_id="job-g", attempt=1, audio_name="x.wav")
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code.startswith("asr_engine_failed"), \
                    e.reason_code
            assert rec.count("worker.spawned") == 1, \
                "a load failure must not trigger restarts"
        finally:
            s.shutdown()
        print("ok  engine load failure: structured, no restart loop")


def test_cleanup_engine_not_ready_reports_basic_honestly():
    """M03-AC04 (protocol half): with the cleanup engine failed, clean()
    still answers — and the worker-reported path says basic with a
    fallback reason, never 'llm'."""
    with tempfile.TemporaryDirectory() as td:
        s, rec = make_sup(td, {"asr": "ready", "cleanup": "failed",
                               "clean": ["ok:fallback text|path=basic"
                                         "|reason=cleanup_engine_failed"]})
        try:
            out = s.clean(job_id="job-h", attempt=1, raw_text="um hi")
            assert out["path"] == "basic"
            assert out["fallback_reason"] == "cleanup_engine_failed"
            assert out["text"] == "fallback text"
        finally:
            s.shutdown()
        print("ok  cleanup not ready: basic path reported honestly")


def main():
    test_protocol_handshake_and_result()
    test_injected_fault_recovers_once()
    test_second_fault_is_recoverable_not_looping()
    test_circuit_breaker_fails_fast()
    test_stale_generation_result_discarded()
    test_stale_generation_echo_resolves_as_fault()
    test_cleanup_wait_and_engine_wait_override()
    test_two_queued_captures_fifo()
    test_worker_cannot_request_insertion()
    test_engine_failure_fails_fast_without_respawn_loop()
    test_cleanup_engine_not_ready_reports_basic_honestly()
    print("all worker protocol tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
