"""Idle unload of the cleanup model: the supervisor side (ticket 05).

The worker may release the cleanup model after a long idle period and says
so with the engine frame ``unloaded``; a hotkey press asks for it back with
the ``ensure_cleanup`` request. These tests drive the real
``WorkerSupervisor`` with fake worker pipes (frames are written to a
recording stdin and delivered through ``_handle_message``), never a model:

  1  an ``unloaded`` frame is accepted: state, ``on_engine``, the event
  2  the cleanup latch is cleared by ``unloaded`` and by a following
     ``loading``/``warming``, set again by ``ready``/``failed``
  3  ``wait_engine("cleanup")`` during a reload waits for ``ready``
  4  ``wait_engine("cleanup")`` on ``unloaded`` sends one ``ensure_cleanup``
  5  a request's internal wait never blocks on ``unloaded``
  6  ``prepare_cleanup`` writes one frame per ask (a write still pending
     covers a further ask, see 13), only to a live worker of a cleanup
     that can unload
  7  a send to a dead pipe neither raises nor counts toward the breaker
  10 shutdown's wake-up of engine waiters is never erased by a late frame
  11 neither ``prepare_cleanup`` nor ``wait_engine`` waits on the pipe write
  12 the real worker loop (model loaders shimmed) behind the real supervisor:
     it unloads, ``wait_engine`` brings it back, a clean gets the real answer
  13 at most one ``ensure_cleanup`` write is in flight, however many asks
  14 a thread that cannot start is "nothing asked", never an exception
  8  a crash while ``unloaded`` and a respawn start from ``not_started``
  9  the protocol fake takes ``ensure_cleanup`` silently, as the worker does

Run: .venv/bin/python tests/v2/lifecycle/test_idle_unload_supervisor.py
"""

import json
import pathlib
import sys
import threading
import time
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, Rec, make_sup, run, tmpdir, wav  # noqa: E402,E501
from localflow.v2.supervisor import WorkerSupervisor  # noqa: E402

ENSURE = {"v": 1, "op": "ensure_cleanup"}


class _Stdin:
    """A worker's stdin: records every frame, optionally answers it."""

    def __init__(self, on_frame=None):
        self.frames = []
        self.on_frame = on_frame
        self.broken = False

    def write(self, data):
        if self.broken:
            raise BrokenPipeError("worker stdin closed")
        assert int.from_bytes(data[:4], "big") == len(data) - 4
        frame = json.loads(data[4:].decode("utf-8"))
        self.frames.append(frame)
        if self.on_frame is not None:
            self.on_frame(frame)

    def flush(self):
        pass


class _Proc:
    def __init__(self, on_frame=None):
        self.stdin = _Stdin(on_frame)
        self.returncode = None

    def poll(self):
        return self.returncode


def make(td, *, mode="llm", impl="v2", on_frame=None, on_engine=None):
    """A supervisor holding a fake live worker (generation 1, greeted)."""
    s = WorkerSupervisor(
        audio_root=pathlib.Path(td) / "audio", asr_model="x",
        cleanup_mode=mode, cleanup_model="m", cleanup_implementation=impl,
        emit=Rec(), on_engine=on_engine)
    s.generation = 1
    s._proc = _Proc(on_frame)
    s._hello.set()
    return s


def deliver(s, engine, state, generation=None):
    s._handle_message({"v": 1, "op": "engine", "engine": engine,
                       "state": state, "model_id": "m"},
                      generation or s.generation, s._proc)


def drain():
    """Wait for the short-lived writer threads of prepare_cleanup."""
    for t in threading.enumerate():
        if t.name == "localflow-ensure-cleanup":
            t.join(10)
            assert not t.is_alive(), "an ensure_cleanup write never ended"


def reload_after_ensure(s):
    """The worker's answer to ensure_cleanup: loading, then ready."""
    def on_frame(frame):
        if frame.get("op") == "ensure_cleanup":
            def answer():
                deliver(s, "cleanup", "loading")
                deliver(s, "cleanup", "ready")
            threading.Thread(target=answer, daemon=True).start()
    return on_frame


def test_1_unloaded_frame_updates_state_and_fires_on_engine():
    with tmpdir() as td:
        seen = []
        s = make(td, on_engine=lambda e, st, info: seen.append((e, st)))
        deliver(s, "asr", "ready")
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        assert s.engine_state == {"asr": "ready", "cleanup": "unloaded"}
        assert seen[-1] == ("cleanup", "unloaded"), seen
        events = s.emit.named("worker.engine_state")
        assert events[-1]["outcome"] == "unloaded", events
        assert events[-1]["model_id"] == "m"
        assert s.emit.count("worker.protocol_error") == 0
    print("ok  1 an unloaded frame updates engine_state, fires on_engine"
          " and is emitted as worker.engine_state")


def test_2_cleanup_latch_follows_unload_and_reload():
    with tmpdir() as td:
        s = make(td)
        cleanup, asr = s._engine_events["cleanup"], s._engine_events["asr"]
        deliver(s, "asr", "ready")
        deliver(s, "cleanup", "ready")
        assert cleanup.is_set() and asr.is_set()
        deliver(s, "cleanup", "unloaded")
        assert not cleanup.is_set(), "unloaded must clear the latch"
        assert asr.is_set(), "the speech latch is never touched"
        deliver(s, "cleanup", "loading")
        assert not cleanup.is_set()
        deliver(s, "cleanup", "ready")
        assert cleanup.is_set(), "ready sets it again"
        deliver(s, "cleanup", "unloaded")
        deliver(s, "cleanup", "loading")
        deliver(s, "cleanup", "warming")
        assert not cleanup.is_set(), "loading/warming after a ready clear it"
        deliver(s, "cleanup", "failed")
        assert cleanup.is_set(), "a failed reload is terminal too"
        # A late frame of a dying generation changes nothing.
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded", generation=7)
        assert s.engine_state["cleanup"] == "ready" and cleanup.is_set()
    print("ok  2 latch cleared by unloaded and by loading/warming after a"
          " ready, set by ready/failed, stale generation inert")


def test_3_wait_during_a_reload_waits_for_ready():
    with tmpdir() as td:
        s = make(td)
        deliver(s, "asr", "ready")
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        deliver(s, "cleanup", "loading")
        out = {}
        t = threading.Thread(target=lambda: out.update(
            state=s.wait_engine("cleanup", 10)))
        t.start()
        t.join(0.3)
        assert t.is_alive(), "returned while the reload was still running"
        deliver(s, "cleanup", "ready")
        t.join(5)
        assert not t.is_alive() and out["state"] == "ready", out
        assert s._proc.stdin.frames == [], \
            "a reload already in flight is not asked for again"
    print("ok  3 wait_engine(cleanup) during a reload blocks until ready,"
          " sends nothing")


def test_4_wait_on_unloaded_sends_one_ensure_cleanup():
    with tmpdir() as td:
        s = make(td)
        s._proc = _Proc(reload_after_ensure(s))
        deliver(s, "asr", "ready")
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        assert s.wait_engine("cleanup", 10) == "ready"
        drain()
        assert s._proc.stdin.frames == [ENSURE], s._proc.stdin.frames

        # The reload fails: the answer is the engine's real state.
        s = make(td)
        s._proc = _Proc(lambda f: f.get("op") == "ensure_cleanup"
                        and deliver(s, "cleanup", "failed"))
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        assert s.wait_engine("cleanup", 10) == "failed"
        drain()
        assert s._proc.stdin.frames == [ENSURE]

        # A worker that never answers: bounded, and still resting.
        s = make(td)
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        t0 = time.monotonic()
        assert s.wait_engine("cleanup", 0.3) == "unloaded"
        assert 0.25 <= time.monotonic() - t0 < 5.0
        drain()
        assert s._proc.stdin.frames == [ENSURE]

        # No worker to ask: nothing is written and nothing waits for it.
        s = make(td)
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        s._proc = None
        t0 = time.monotonic()
        assert s.wait_engine("cleanup", 5.0) == "unloaded"
        assert time.monotonic() - t0 < 1.0, "waited for a reload nobody runs"

        # Every other state is the plain wait: ready is ready, no frame.
        s = make(td)
        deliver(s, "cleanup", "ready")
        assert s.wait_engine("cleanup", 1) == "ready"
        assert s._proc.stdin.frames == []
    print("ok  4 wait_engine(cleanup) on unloaded sends exactly one"
          " ensure_cleanup and returns ready/failed/unloaded as it ends")


def test_5_internal_request_wait_never_blocks_on_unloaded():
    with tmpdir() as td:
        s = make(td)
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        t0 = time.monotonic()
        assert s._wait_engine("cleanup", 5.0) is False
        assert time.monotonic() - t0 < 1.0, \
            "a request waited out its timeout with nobody loading"
        assert s._proc.stdin.frames == [], \
            "the request path asks nothing; the worker reloads for a clean"
    print("ok  5 the internal wait returns at once on unloaded")


def test_6_prepare_cleanup_writes_one_frame_per_call_to_a_live_worker():
    with tmpdir() as td:
        s = make(td)
        deliver(s, "cleanup", "ready")
        assert s.prepare_cleanup() is True
        drain()
        assert s.prepare_cleanup() is True
        drain()
        assert s._proc.stdin.frames == [ENSURE, ENSURE]
        # Whatever the engine state, a press asks.
        for state in ("not_started", "loading", "warming", "unloaded",
                      "failed"):
            deliver(s, "cleanup", state)
            before = len(s._proc.stdin.frames)
            s.prepare_cleanup()
            drain()
            assert len(s._proc.stdin.frames) == before + 1, state

        def frames(s):
            return s._proc.stdin.frames if s._proc is not None else []

        cases = {}
        closed = make(td)
        with closed._state_lock:
            closed._closed = True
        cases["closed"] = closed
        tripped = make(td)
        tripped.supervisor_state = "failed"
        cases["breaker tripped"] = tripped
        cases["no worker process"] = make(td)
        cases["no worker process"]._proc = None
        dead = make(td)
        dead._proc.returncode = 1
        cases["worker exited"] = dead
        ungreeted = make(td)
        ungreeted._hello.clear()
        cases["worker not greeted"] = ungreeted
        cases["cleanup off"] = make(td, mode="off")
        cases["cleanup v1"] = make(td, impl="v1")
        for name, sup in cases.items():
            assert sup.prepare_cleanup() is False, name
            drain()
            assert frames(sup) == [], name
    print("ok  6 prepare_cleanup: one frame per call to a live worker, none"
          " when closed, tripped, absent, exited, not greeted, off or v1")


def test_7_a_dead_pipe_is_swallowed_and_not_counted():
    errors = []
    real_hook = threading.excepthook
    threading.excepthook = errors.append
    try:
        with tmpdir() as td:
            s = make(td)
            s._proc.stdin.broken = True
            s.prepare_cleanup()  # must not raise
            drain()
            assert s._consecutive_deaths == 0
            assert s.supervisor_state == "idle"
            assert s.emit.count("worker.died") == 0
            assert s.emit.count("worker.protocol_error") == 0
            # A closed stdin object is swallowed the same way.
            s._proc.stdin = None
            s.prepare_cleanup()
            drain()
            assert s._consecutive_deaths == 0
    finally:
        threading.excepthook = real_hook
    assert errors == [], "the writer thread let an exception escape"
    print("ok  7 a send to a dead pipe does not raise and counts no death")


# A worker that greets and then stays silent: a spawn resets the states and
# nothing else writes them, so the reset is observable.
SILENT_WORKER = (
    "import json, os, sys\n"
    "b = json.dumps({'v': 1, 'op': 'hello', 'pid': os.getpid()}).encode()\n"
    "sys.stdout.buffer.write(len(b).to_bytes(4, 'big') + b)\n"
    "sys.stdout.buffer.flush()\n"
    "sys.stdin.buffer.read()\n")


def test_8_crash_while_unloaded_then_respawn_resets_like_ready():
    with tmpdir() as td:
        s = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="x",
            cleanup_mode="llm", cleanup_model="m", emit=Rec(),
            worker_cmd=[sys.executable, "-c", SILENT_WORKER],
            hello_timeout=15.0)
        try:
            assert s.ensure_running()
            g1 = s.generation
            deliver(s, "asr", "ready")
            deliver(s, "cleanup", "ready")
            deliver(s, "cleanup", "unloaded")
            assert s.engine_state == {"asr": "ready", "cleanup": "unloaded"}
            assert not s._engine_events["cleanup"].is_set()
            s._proc.kill()
            s._readers[g1].join(5)
            assert g1 in s._finalized, "the crash was never seen"
            # Until the next spawn the state is stale, exactly as for ready.
            assert s.engine_state["cleanup"] == "unloaded"
            assert s.ensure_running()
            assert s.generation == g1 + 1
            assert s.engine_state == {"asr": "not_started",
                                      "cleanup": "not_started"}
            assert not s._engine_events["cleanup"].is_set()
            assert not s._engine_events["asr"].is_set()
            # The fresh generation loads as at start and is waited for.
            deliver(s, "asr", "ready")
            deliver(s, "cleanup", "ready")
            assert s.wait_engine("cleanup", 5) == "ready"
        finally:
            s.shutdown()
    print("ok  8 crash while unloaded, then respawn: not_started and the"
          " latch cleared, then ready as for a first load")


def test_9_ensure_cleanup_is_silent_on_the_protocol_fake():
    """No result and no fault, in any state: a request sent after it is
    answered and nothing was recorded for the frame itself."""
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-e.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:after"]})
        try:
            s.ensure_running()
            assert s.wait_engine("asr", 15) == "ready"
            assert s.prepare_cleanup() is True
            drain()
            res = s.transcribe(job_id="job-e", attempt=1, audio_name=w.name)
            assert res["text"] == "after" and not res.get("retried")
            assert rec.count("worker.fault") == 0, rec.named("worker.fault")
            assert rec.count("worker.protocol_error") == 0
            assert rec.count("worker.died") == 0
        finally:
            s.shutdown()
    print("ok  9 ensure_cleanup on a live fake worker: no fault, no result,"
          " the next request is served")


def test_10_shutdown_wake_up_survives_a_pending_engine_frame():
    """shutdown() sets every engine event so waiters wake. A frame the
    reader had already read must not clear that again: a waiter entering
    Event.wait() afterwards would sleep its whole timeout."""
    with tmpdir() as td:
        s = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="x",
            cleanup_mode="llm", cleanup_model="m", emit=Rec(),
            worker_cmd=[sys.executable, "-c", SILENT_WORKER],
            hello_timeout=15.0)
        assert s.ensure_running()
        deliver(s, "asr", "ready")
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        latch = s._engine_events["cleanup"]
        assert not latch.is_set(), "the adverse state needs a cleared latch"
        s.shutdown()
        assert latch.is_set(), "shutdown must wake the waiters"
        for state in ("loading", "warming", "unloaded"):
            deliver(s, "cleanup", state)
            assert latch.is_set(), f"a late {state} frame erased the wake-up"
        t0 = time.monotonic()
        assert latch.wait(5.0) is True
        assert s._wait_engine("cleanup", 5.0) is False
        assert time.monotonic() - t0 < 1.0
    print("ok  10 shutdown's wake-up survives loading/warming/unloaded"
          " frames that were already pending")


def test_11_nothing_waits_on_the_pipe_write():
    gate, entered = threading.Event(), threading.Event()

    class _BlockedStdin(_Stdin):
        def write(self, data):
            entered.set()
            gate.wait(10)
            super().write(data)

    with tmpdir() as td:
        s = make(td)
        s._proc.stdin = _BlockedStdin()
        deliver(s, "cleanup", "ready")
        deliver(s, "cleanup", "unloaded")
        try:
            t0 = time.monotonic()
            assert s.prepare_cleanup() is True
            assert time.monotonic() - t0 < 1.0, \
                "prepare_cleanup waited for the blocked write"
            assert entered.wait(5), "the write never started"
            # A worker that stopped reading: the wait's own timeout runs.
            t0 = time.monotonic()
            assert s.wait_engine("cleanup", 0.5) == "unloaded"
            took = time.monotonic() - t0
            assert 0.4 <= took < 3.0, f"wait_engine took {took:.2f}s"
            assert s._proc.stdin.frames == [], "the write is still blocked"
        finally:
            gate.set()
        drain()
        assert s._proc.stdin.frames == [ENSURE], \
            "the one pending frame arrives once the pipe is read again"
    print("ok  11 a blocked pipe write holds up neither prepare_cleanup nor"
          " wait_engine's own timeout; the frame arrives when released")


def _until_unloaded(s, timeout=20.0):
    deadline = time.monotonic() + timeout
    while s.engine_state["cleanup"] != "unloaded":
        assert time.monotonic() < deadline, "the worker never unloaded"
        time.sleep(0.02)


def test_12_the_real_worker_unloads_reloads_and_answers_a_clean():
    """Protocol and scheduling evidence only: the production worker loop
    with shimmed loaders, never a model."""
    with tmpdir() as td:
        plan = pathlib.Path(td) / "plan.json"
        plan.write_text(json.dumps({"asr_load": "ok", "cleanup_load": "ok"}))
        s = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="x",
            cleanup_mode="llm", cleanup_model="m", emit=Rec(),
            worker_cmd=[sys.executable, str(PROD)],
            spawn_env={"LOCALFLOW_PROD_WORKER_PLAN": str(plan),
                       "PYTHONPATH": str(ROOT),
                       "LOCALFLOW_WORKER_IDLE_UNLOAD_S": "0.6"},
            hello_timeout=15.0, ready_timeout=20.0, request_timeout=20.0)
        try:
            assert s.ensure_running()
            _until_unloaded(s)
            assert not s._engine_events["cleanup"].is_set()
            generation = s.generation
            assert s.wait_engine("cleanup", 20) == "ready"
            assert s.engine_state == {"asr": "ready", "cleanup": "ready"}
            _until_unloaded(s)
            res = s.clean(job_id="job-r", attempt=1, raw_text="um hello")
            assert res["path"] == "llm" and res["fallback_reason"] is None, res
            assert s.generation == generation
            for event in ("worker.died", "worker.fault",
                          "worker.protocol_error", "worker.retired"):
                assert s.emit.count(event) == 0, event
            assert s.emit.count("worker.spawned") == 1
        finally:
            s.shutdown()
    print("ok  12 real worker loop: unloads when idle, wait_engine reloads"
          " it, a clean on the resting model gets the real answer, no"
          " restart or fault")


def _writers():
    return [t for t in threading.enumerate()
            if t.name == "localflow-ensure-cleanup" and t.is_alive()]


def test_13_at_most_one_ensure_cleanup_write_is_in_flight():
    gate, entered = threading.Event(), threading.Event()

    class _BlockedStdin(_Stdin):
        def write(self, data):
            entered.set()
            gate.wait(10)
            super().write(data)

    with tmpdir() as td:
        s = make(td)
        s._proc.stdin = _BlockedStdin()
        sends = []
        real_send = s._send

        def counting_send(msg, **kw):
            sends.append(msg["op"])
            return real_send(msg, **kw)

        s._send = counting_send
        try:
            assert s.prepare_cleanup() is True
            assert entered.wait(5), "the write never started"
            for _ in range(10):
                assert s.prepare_cleanup() is True, \
                    "an ask covered by the pending frame still succeeds"
            assert len(_writers()) == 1, [t.name for t in _writers()]
            assert sends == ["ensure_cleanup"], sends
        finally:
            gate.set()
        drain()
        assert s._proc.stdin.frames == [ENSURE]
        assert _writers() == []
        # The write completed: the next ask is a new write.
        assert s.prepare_cleanup() is True
        drain()
        assert s._proc.stdin.frames == [ENSURE, ENSURE]
        assert sends == ["ensure_cleanup", "ensure_cleanup"], sends
    print("ok  13 ten asks behind one blocked write start no further thread;"
          " once it completes the next ask writes again")


def test_14_a_thread_that_cannot_start_is_nothing_asked():
    for failure in (RuntimeError("can't start new thread"),
                    OSError("resource temporarily unavailable")):
        with tmpdir() as td:
            s = make(td)
            deliver(s, "cleanup", "ready")
            deliver(s, "cleanup", "unloaded")
            with mock.patch.object(threading.Thread, "start",
                                   side_effect=failure):
                assert s.prepare_cleanup() is False
                t0 = time.monotonic()
                assert s.wait_engine("cleanup", 5.0) == "unloaded"
                assert time.monotonic() - t0 < 1.0, \
                    "waited for an ask that never started"
            assert s._proc.stdin.frames == []
            # Nothing is left marked in flight: the next ask writes.
            assert s.prepare_cleanup() is True
            drain()
            assert s._proc.stdin.frames == [ENSURE]
    print("ok  14 a thread-start failure returns False without raising,"
          " wait_engine returns at once, and the next ask still writes")


def main():
    run([test_1_unloaded_frame_updates_state_and_fires_on_engine,
         test_2_cleanup_latch_follows_unload_and_reload,
         test_3_wait_during_a_reload_waits_for_ready,
         test_4_wait_on_unloaded_sends_one_ensure_cleanup,
         test_5_internal_request_wait_never_blocks_on_unloaded,
         test_6_prepare_cleanup_writes_one_frame_per_call_to_a_live_worker,
         test_7_a_dead_pipe_is_swallowed_and_not_counted,
         test_8_crash_while_unloaded_then_respawn_resets_like_ready,
         test_9_ensure_cleanup_is_silent_on_the_protocol_fake,
         test_10_shutdown_wake_up_survives_a_pending_engine_frame,
         test_11_nothing_waits_on_the_pipe_write,
         test_12_the_real_worker_unloads_reloads_and_answers_a_clean,
         test_13_at_most_one_ensure_cleanup_write_is_in_flight,
         test_14_a_thread_that_cannot_start_is_nothing_asked],
        "idle unload supervisor tests")


if __name__ == "__main__":
    main()
