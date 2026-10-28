"""Idle unload of the cleanup model: unload, reload, and the waiting rule.

Runs the PRODUCTION worker (``Worker.serve``) through
``prod_worker_harness.py`` — only the model loaders are shimmed, and the
harness traces every ``mx.clear_cache`` call, every frame the worker writes
and the moment the shim model's weights are released. Nothing here loads a
model or measures memory: these checks prove WHEN the worker unloads, WHAT
it writes, and that a request is never answered degraded because of a
reload, not how much memory comes back.

  * After the idle period, with nothing queued or running, the cleanup
    engine is dropped, the allocator cache cleared and one ``unloaded``
    engine frame written; a busy worker, or one that keeps receiving
    ``ensure_cleanup``, does not unload.
  * ``ensure_cleanup`` writes no frame of its own: no result, no fault.
    While unloaded it queues exactly one reload (``loading``, ``ready``).
  * A ``clean`` sent while unloaded, or during the reload, waits for it and
    gets the engine's real answer; a ``transcribe`` is served throughout
    and the speech engine never changes state.
  * Generation, job and attempt identity are echoed unchanged, no fault
    frame is written, and the process is never restarted.
  * A failed reload ends in the existing failed-engine behaviour.
  * ``LOCALFLOW_WORKER_IDLE_UNLOAD_S`` is read once at start; with unloading
    off the frame stream is the one the worker wrote before this feature.

Run: .venv/bin/python tests/v2/lifecycle/test_worker_idle_unload.py
"""

import contextlib
import gc
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time
import types
import weakref

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, run, tmpdir, wav  # noqa: E402
from localflow.v2 import worker  # noqa: E402

GPU_THREAD = "localflow-worker-gpu"
ENSURE = {"v": 1, "op": "ensure_cleanup"}
UNLOADED = {"v": 1, "op": "engine", "engine": "cleanup", "state": "unloaded",
            "model_id": "fake-llm"}


def _engine(engine, state):
    return lambda f: f["op"] == "engine" and f["engine"] == engine \
        and f["state"] == state


def _result(req_id):
    return lambda f: f["op"] == "result" and f["req_id"] == req_id


class Session:
    """One production worker process behind a reader thread, so a test can
    wait for a frame, or assert that none arrives within a window."""

    def __init__(self, td, plan, idle, latch):
        self.td = pathlib.Path(td)
        wav(self.td / "audio", "clip.wav")
        self.record = self.td / "record.jsonl"
        self.latch = self.td / "latch"
        plan = dict(plan, record=str(self.record), trace_clears=True)
        if latch:
            plan["cleanup_load_latch"] = str(self.latch)
            self.release_reload()
        (self.td / "plan.json").write_text(json.dumps(plan))
        env = dict(os.environ, LOCALFLOW_CODE_ROOT=str(ROOT),
                   LOCALFLOW_PROD_WORKER_PLAN=str(self.td / "plan.json"))
        env.pop("LOCALFLOW_WORKER_MEMORY_DIAG", None)
        env.pop("LOCALFLOW_WORKER_IDLE_UNLOAD_S", None)
        if idle is not None:
            env["LOCALFLOW_WORKER_IDLE_UNLOAD_S"] = idle
        self.proc = subprocess.Popen(
            [sys.executable, str(PROD), "--audio-root",
             str(self.td / "audio")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, cwd=ROOT)
        self.log = []           # (monotonic receive time, frame)
        self._queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        out = self.proc.stdout
        while True:
            head = out.read(4)
            if len(head) < 4:
                self._queue.put(None)
                return
            frame = json.loads(out.read(int.from_bytes(head, "big")))
            self._queue.put((time.monotonic(), frame))

    @property
    def frames(self):
        return [f for _, f in self.log]

    def send(self, msg):
        data = json.dumps(msg).encode()
        self.proc.stdin.write(len(data).to_bytes(4, "big") + data)
        self.proc.stdin.flush()

    def _take(self, timeout):
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is not None:
            self.log.append(item)
        return item

    def wait_for(self, pred, timeout=20.0):
        """Frames received up to and including the first one ``pred``
        accepts."""
        got, end = [], time.monotonic() + timeout
        while True:
            item = self._take(max(end - time.monotonic(), 0.0))
            assert item is not None, ("no matching frame", got)
            got.append(item[1])
            if pred(item[1]):
                return got

    def drain(self, seconds):
        """Every frame that arrives within ``seconds``."""
        got, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            item = self._take(max(end - time.monotonic(), 0.0))
            if item is not None:
                got.append(item[1])
        return got

    def time_of(self, frame):
        return next(t for t, f in self.log if f is frame)

    def start(self):
        """hello, load, both engines ready; returns the frames."""
        hello = self.wait_for(lambda f: f["op"] == "hello")
        self.send({"v": 1, "op": "load", "asr_model": "fake-asr",
                   "cleanup_model": "fake-llm", "cleanup_mode": "llm",
                   "cleanup_implementation": "v2"})
        return hello + self.wait_for(_engine("asr", "ready")) \
            + self.wait_for(_engine("cleanup", "ready"))

    def hold_reload(self):
        self.latch.unlink()

    def release_reload(self):
        self.latch.touch()

    def transcribe(self, req_id):
        self.send({"v": 1, "op": "transcribe", "req_id": req_id,
                   "generation": 7, "attempt": 2, "job_id": "j1",
                   "audio": {"name": "clip.wav"}, "sample_rate": 16000})

    def clean(self, req_id, text="um hello"):
        self.send({"v": 1, "op": "clean", "req_id": req_id,
                   "generation": 7, "attempt": 2, "job_id": "j1",
                   "raw_text": text})

    def trace(self):
        return [json.loads(line) for line in
                self.record.read_text().splitlines()]

    def close(self):
        with contextlib.suppress(OSError):
            self.send({"v": 1, "op": "shutdown"})
        try:
            while self._take(10.0) is not None:
                pass
            self.proc.wait(timeout=30)
        finally:
            self.proc.kill()
            self.proc.stdin.close()
            self.proc.stdout.close()


@contextlib.contextmanager
def session(plan=None, idle="0.6", latch=False):
    """A started-on-demand worker session. Leaving it checks that no fault
    frame was written and that the process was never restarted."""
    plan = dict({"transcribe": ["ok:asr text"] * 8,
                 "clean": ["ok:CLEANED"] * 8}, **(plan or {}))
    with tmpdir() as td:
        s = Session(td, plan, idle, latch)
        watchdog = threading.Timer(120, s.proc.kill)
        watchdog.start()
        try:
            yield s
            s.close()
            assert not [f for f in s.frames if f["op"] == "fault"], \
                [f for f in s.frames if f["op"] == "fault"]
            assert len([f for f in s.frames if f["op"] == "hello"]) == 1
        finally:
            watchdog.cancel()
            s.proc.kill()


def test_cleanup_unloads_after_the_idle_period_and_frees_the_model_first():
    with session(idle="1.0") as s:
        s.start()
        ready_at = time.monotonic()
        frames = s.wait_for(_engine("cleanup", "unloaded"))
        waited = time.monotonic() - ready_at
        trace = s.trace()
    assert frames == [UNLOADED], frames
    assert waited >= 0.9, waited
    order = [f"frame:{e['state']}" if e["event"] == "frame" else e["event"]
             for e in trace
             if e["event"] in ("weights_freed", "clear_cache")
             or (e["event"] == "frame" and e["state"] == "unloaded")]
    assert order[-3:] == ["weights_freed", "clear_cache", "frame:unloaded"], \
        order
    tail = [e for e in trace if e["event"] in ("clear_cache", "frame")][-2:]
    assert [e["thread"] for e in tail] == [GPU_THREAD, GPU_THREAD], tail
    print("ok  the cleanup model is released, the cache cleared, then one"
          " unloaded frame is written, after the idle period")


def test_a_busy_worker_unloads_only_after_its_last_task_and_an_empty_queue():
    # Both tasks run longer than the idle period; the clean is queued behind
    # the transcription. The idle period counts from the end of the last one.
    plan = {"transcribe": ["delay:1500|ok:asr text"],
            "clean": ["delay:1200|ok:CLEANED"]}
    with session(plan, idle="0.6") as s:
        s.start()
        s.transcribe("t1")
        s.clean("c1")
        frames = s.wait_for(_engine("cleanup", "unloaded"))
        assert [(f["op"], f.get("kind") or f.get("state")) for f in frames] \
            == [("result", "asr"), ("result", "clean"),
                ("engine", "unloaded")], frames
        assert frames[1]["path"] == "llm", frames[1]
        idle = s.time_of(frames[2]) - s.time_of(frames[1])
    assert idle >= 0.5, idle
    print("ok  no unload while a task runs or is queued; the idle period"
          " counts from the end of the last task")


def test_ensure_cleanup_on_a_ready_engine_writes_nothing_and_keeps_it_loaded():
    with session(idle="1.0") as s:
        s.start()
        end = time.monotonic() + 3.0
        while time.monotonic() < end:
            s.send(ENSURE)
            assert not s.drain(0.3), "ensure_cleanup wrote a frame"
        last = time.monotonic()
        frames = s.wait_for(_engine("cleanup", "unloaded"))
        waited = time.monotonic() - last
    assert frames == [UNLOADED], frames
    assert waited >= 0.6, waited
    print("ok  ensure_cleanup on a ready engine writes nothing and holds off"
          " the unload while it keeps arriving")


def _loads_started(s):
    return len([e for e in s.trace() if e["event"] == "cleanup_load_started"])


def test_ensure_cleanup_while_unloaded_reloads_once_however_often_it_is_sent():
    with session(idle="0.6", latch=True) as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.hold_reload()
        s.send(ENSURE)
        s.send(ENSURE)
        loading = s.wait_for(_engine("cleanup", "loading"))
        assert loading[-1]["model_id"] == "fake-llm", loading
        s.send(ENSURE)           # a third one, while the reload runs
        assert not s.drain(0.4), "the reload finished or wrote more early"
        s.release_reload()
        ready = s.wait_for(_engine("cleanup", "ready"))
        assert [f["state"] for f in loading + ready] == ["loading", "ready"]
        assert ready[-1]["model_id"] == "fake-llm", ready
        s.drain(0.3)
        assert _loads_started(s) == 2, "first load plus exactly one reload"
    print("ok  ensure_cleanup while unloaded: loading then ready, and one"
          " reload however often it is sent")


def _real_answer(frame):
    assert frame["op"] == "result" and frame["kind"] == "clean", frame
    assert frame["path"] == "llm" and frame["text"] == "CLEANED", frame
    assert frame["fallback_reason"] is None, frame
    assert (frame["generation"], frame["attempt"], frame["job_id"]) \
        == (7, 2, "j1"), frame


def test_a_clean_sent_while_unloaded_waits_for_the_reload_and_gets_the_real_answer():
    with session(idle="0.6", latch=True) as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.hold_reload()
        s.clean("c1")
        s.wait_for(_engine("cleanup", "loading"))
        s.clean("c2")             # a second one, during the reload
        assert not s.drain(0.4), "a clean was answered before the reload"
        s.release_reload()
        frames = s.wait_for(_result("c1"))
        assert [(f["op"], f.get("state") or f.get("req_id"))
                for f in frames] == [("engine", "ready"), ("result", "c1")]
        _real_answer(frames[-1])
        _real_answer(s.wait_for(_result("c2"))[-1])
        assert _loads_started(s) == 2
    print("ok  a clean sent while unloaded, and one sent during the reload,"
          " both get the real answer after the load")


def test_a_clean_sent_during_an_ensure_cleanup_reload_waits_for_it():
    with session(idle="0.6", latch=True) as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.hold_reload()
        s.send(ENSURE)
        s.wait_for(_engine("cleanup", "loading"))
        s.clean("c1")
        assert not s.drain(0.4), "the clean was answered during the reload"
        s.release_reload()
        frames = s.wait_for(_result("c1"))
        assert frames[0]["state"] == "ready", frames
        _real_answer(frames[-1])
        assert _loads_started(s) == 2
    print("ok  a clean that arrives mid-reload waits and is answered by the"
          " reloaded engine")


def _asr_states(s):
    return [f["state"] for f in s.frames
            if f["op"] == "engine" and f["engine"] == "asr"]


def test_a_transcribe_is_served_while_unloaded_and_during_a_reload():
    with session(idle="0.6", latch=True) as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.transcribe("t1")                      # unloaded: served, no reload
        got = s.wait_for(_result("t1"))
        assert got[-1]["kind"] == "asr" and got[-1]["text"] == "asr text", got
        assert not [f for f in s.drain(0.3) if f["op"] == "engine"]
        assert _loads_started(s) == 1, "a transcribe must not reload"
        s.hold_reload()
        s.send(ENSURE)
        s.wait_for(_engine("cleanup", "loading"))
        s.transcribe("t2")                      # mid-reload: served after it
        s.release_reload()
        got = s.wait_for(_result("t2"))
        assert got[0]["state"] == "ready" and got[-1]["kind"] == "asr", got
        assert _asr_states(s) == ["loading", "warming", "ready"], \
            _asr_states(s)
    print("ok  transcribe served while unloaded and mid-reload; the speech"
          " engine never changes state")


def test_a_transcribe_queued_ahead_of_a_clean_runs_before_the_reload():
    plan = {"transcribe": ["delay:800|ok:first", "ok:second"]}
    with session(plan, idle="0.6") as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.transcribe("t1")                      # keeps the GPU thread busy
        s.send(ENSURE)                          # reload queued behind it
        s.transcribe("t2")
        s.clean("c1")
        frames = s.wait_for(_result("c1"))
        assert [(f["op"], f.get("state") or f.get("req_id"))
                for f in frames] == [
            ("result", "t1"), ("result", "t2"), ("engine", "loading"),
            ("engine", "ready"), ("result", "c1")], frames
        _real_answer(frames[-1])
    print("ok  a transcribe queued ahead of a clean still runs before the"
          " reload, the clean after it")


def _failed_answer(frame, req_id):
    assert frame["op"] == "result" and frame["req_id"] == req_id, frame
    assert frame["path"] == "llm_fallback_normalized", frame
    assert frame["fallback_reason"] == "cleanup_engine_failed", frame
    assert frame["text"] == "um hello", frame


def test_a_failed_reload_ends_in_the_failed_engine_behaviour():
    with session({"cleanup_reload": "fail"}, idle="0.6") as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.clean("c1")                           # waits for the reload
        frames = s.wait_for(_result("c1"))
        assert [(f["op"], f.get("state")) for f in frames[:-1]] \
            == [("engine", "loading"), ("engine", "failed")], frames
        assert frames[1]["reason_code"] == "cleanup_engine_load_failed"
        assert frames[1]["model_id"] == "fake-llm", frames[1]
        _failed_answer(frames[-1], "c1")
        # Failed stays failed: no second reload, no further unload, and the
        # next clean takes the same degraded answer at once.
        s.send(ENSURE)
        s.clean("c2")
        got = s.wait_for(_result("c2"))
        assert len(got) == 1, got
        _failed_answer(got[0], "c2")
        assert not s.drain(1.5), "a failed engine reloaded or unloaded"
        assert _loads_started(s) == 2
    print("ok  a failed reload: failed engine frame, the existing degraded"
          " answer, no retry, no fault")


def test_unload_and_reload_never_change_identity_fault_or_restart_the_worker():
    with session(idle="0.6") as s:
        s.start()
        s.wait_for(_engine("cleanup", "unloaded"))
        s.send(ENSURE)
        s.wait_for(_engine("cleanup", "ready"))
        s.clean("c1")
        _real_answer(s.wait_for(_result("c1"))[-1])
        s.wait_for(_engine("cleanup", "unloaded"))
        s.clean("c2")                           # no ensure_cleanup this time
        _real_answer(s.wait_for(_result("c2"))[-1])
        s.transcribe("t1")
        done = s.wait_for(_result("t1"))[-1]
        assert (done["generation"], done["attempt"], done["job_id"]) \
            == (7, 2, "j1"), done
        engine_frames = [f for f in s.frames if f["op"] == "engine"]
        assert not [f for f in engine_frames
                    if {"generation", "req_id", "job_id"} & set(f)], \
            "an engine frame carries request identity"
        assert [f["state"] for f in engine_frames
                if f["engine"] == "cleanup"][:8] == [
            "loading", "ready", "unloaded", "loading", "ready", "unloaded",
            "loading", "ready"], engine_frames
    print("ok  two unload/reload cycles: identity echoed unchanged, no fault"
          " frame, one worker process throughout")


FRAME_STREAM = ["hello", "engine:asr:loading", "engine:asr:warming",
                "engine:asr:ready", "engine:cleanup:loading",
                "engine:cleanup:ready", "result", "result"]


class _Racing(worker.Worker):
    """A worker whose scheduler lets a test land a control-thread dispatch
    exactly after the unload decision (``after_unload_decision``)."""

    after_unload_decision = None

    def _next_task(self):
        task = super()._next_task()
        if task and task[0] == "unload_cleanup" \
                and self.after_unload_decision:
            hook, self.after_unload_decision = \
                self.after_unload_decision, None
            hook()
        return task


class InProcess:
    """The production ``Worker`` and its real GPU loop inside this process,
    with the harness's shim loaders and every frame it writes captured.
    Unloading starts switched off; a test arms it when it is ready."""

    def __init__(self, worker_cls):
        import prod_worker_harness as H
        import localflow.v2.cleanup as v2c
        self.frames = []
        self._lock = threading.Lock()
        H.PLAN = {"clean": ["ok:CLEANED"] * 8}
        H._cursor.clear()
        H._cleanup_loads = 0
        stt = types.ModuleType("localflow.stt")
        stt.Transcriber = H.ShimTranscriber
        self._undo = [
            (sys.modules, "localflow.stt", sys.modules.get("localflow.stt")),
            (v2c, "ModelRunner", v2c.ModelRunner),
            (worker, "_write_msg", worker._write_msg)]
        sys.modules["localflow.stt"] = stt
        v2c.ModelRunner = H.ShimRunner
        worker._write_msg = self._write
        self.w = worker_cls("unused")
        self.w._idle_unload_s = None
        self.gpu = threading.Thread(target=self.w._gpu_loop, daemon=True)
        self.gpu.start()

    def _write(self, msg):
        with self._lock:
            self.frames.append(msg)

    def wait(self, pred, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                hit = [f for f in self.frames if pred(f)]
            if hit:
                return hit[0]
            time.sleep(0.01)
        raise AssertionError(("no matching frame", list(self.frames)))

    def start(self):
        self.w._dispatch({"v": 1, "op": "load", "asr_model": "fake-asr",
                          "cleanup_model": "fake-llm", "cleanup_mode": "llm",
                          "cleanup_implementation": "v2"})
        self.wait(_engine("cleanup", "ready"))

    def arm(self):
        """Unloading on, idle period already over. Takes the worker's lock,
        so no scheduling decision sees a half-armed worker."""
        self.w._idle_unload_s = 0.01
        self.w._last_activity -= 5.0

    def clean(self, req_id):
        self.w._dispatch({"v": 1, "op": "clean", "req_id": req_id,
                          "generation": 7, "attempt": 2, "job_id": "j1",
                          "raw_text": "um hello"})

    def close(self):
        with self.w._cond:
            self.w._stopping = True
            self.w._cond.notify_all()
        self.gpu.join(10)
        for obj, name, value in reversed(self._undo):
            if obj is sys.modules and value is None:
                sys.modules.pop(name, None)
            elif obj is sys.modules:
                sys.modules[name] = value
            else:
                setattr(obj, name, value)


@contextlib.contextmanager
def in_process(worker_cls=worker.Worker):
    rig = InProcess(worker_cls)
    try:
        yield rig
    finally:
        rig.close()


def test_a_clean_dispatched_just_before_the_unload_decision_is_answered():
    with in_process() as rig:
        rig.start()
        with rig.w._cond:                       # no decision while we hold it
            rig.arm()
            rig.clean("c1")                     # the clean lands first
        got = rig.wait(_result("c1"))
        _real_answer(got)
        before = rig.frames[:rig.frames.index(got)]
        assert not [f for f in before if f.get("state") == "unloaded"], before
        assert not [f for f in rig.frames if f["op"] == "fault"]
    print("ok  a clean queued as the idle period expires makes the queue"
          " non-empty: it is answered and no unload comes first")


def test_a_clean_dispatched_just_after_the_unload_decision_waits_for_the_reload():
    with in_process(_Racing) as rig:
        rig.start()
        rig.w.after_unload_decision = lambda: rig.clean("c1")
        rig.arm()
        got = rig.wait(_result("c1"))
        _real_answer(got)
        states = [f["state"] for f in rig.frames
                  if f["op"] == "engine" and f["engine"] == "cleanup"]
        assert states[:4] == ["loading", "ready", "unloaded", "loading"], \
            states
        assert not [f for f in rig.frames if f["op"] == "fault"]
        assert not [f for f in rig.frames if f["op"] == "result"
                    and f["fallback_reason"]], "a degraded answer was written"
    print("ok  a clean dispatched right after the unload decision queues the"
          " reload and gets the real answer, not a fault or a degraded text")


def test_a_clean_that_finds_no_engine_on_the_llm_path_is_answered_not_raised():
    with in_process() as rig:
        rig.w._configure({"cleanup_mode": "llm", "cleanup_model": "fake-llm",
                          "cleanup_implementation": "v2"})
        rig.w._clean({"req_id": "c1", "generation": 7, "attempt": 2,
                      "job_id": "j1", "raw_text": "um hello"})
        out = rig.frames[-1]
    assert out["op"] == "result" and out["text"] == "um hello", out
    assert out["fallback_reason"] == "cleanup_not_ready", out
    assert out["path"] == "llm_fallback_normalized", out
    print("ok  _clean with no engine on the v2 llm path answers through the"
          " not-ready path instead of raising")


def test_dropping_the_real_engine_frees_the_model_it_was_built_on():
    from localflow.v2.cleanup import ModelRunner

    class Held:
        pass

    runner = ModelRunner("fake-llm")
    runner._model = Held()
    runner._prefix_caches[("p",)] = Held()
    refs = [weakref.ref(runner._model),
            weakref.ref(runner._prefix_caches[("p",)]), weakref.ref(runner)]
    runner.stream = lambda prompt, n: iter([types.SimpleNamespace(text="x")])
    engine = runner.engine()
    engine.clean("um hello world")              # one real pass through it
    held = [engine]
    del engine, runner
    assert all(r() is not None for r in refs), "freed while still held"
    held.clear()
    gc.collect()
    assert [r() for r in refs] == [None, None, None], \
        "the engine, runner, weights or prefix cache is still reachable"
    print("ok  the real CleanupEngine and ModelRunner free the model and its"
          " prefix cache once the engine is dropped")


def _shape(frames):
    return [f"engine:{f['engine']}:{f['state']}" if f["op"] == "engine"
            else f["op"] for f in frames]


def test_with_unloading_off_the_frame_stream_is_the_one_written_before():
    # Unset keeps the default period (600 s, far beyond this test); 0, a
    # negative number and a non-number turn unloading off. Either way one
    # load, one transcription and one cleanup produce exactly the old stream
    # and nothing follows it.
    for idle in (None, "0", "-1", "junk"):
        with session(idle=idle) as s:
            s.start()
            s.transcribe("t1")
            s.clean("c1")
            s.wait_for(_result("t1"))
            s.wait_for(_result("c1"))
            assert not s.drain(1.8), (idle, "a frame followed the results")
            assert _shape(s.frames) == FRAME_STREAM, (idle, _shape(s.frames))
    print("ok  default, 0, negative and junk periods: the frame stream equals"
          " the one written before unloading existed, and stays quiet")


def test_the_idle_period_is_read_once_at_start_from_the_environment():
    from localflow.v2 import worker
    assert worker.CLEANUP_IDLE_UNLOAD_S == 600.0
    cases = [(None, 600.0), ("30", 30.0), ("0.5", 0.5), ("1e2", 100.0),
             ("0", None), ("-5", None), ("abc", None), ("", None),
             ("nan", None)]
    saved = os.environ.get("LOCALFLOW_WORKER_IDLE_UNLOAD_S")
    try:
        for raw, want in cases:
            os.environ.pop("LOCALFLOW_WORKER_IDLE_UNLOAD_S", None)
            if raw is not None:
                os.environ["LOCALFLOW_WORKER_IDLE_UNLOAD_S"] = raw
            w = worker.Worker("unused")
            assert w._idle_unload_s == want, (raw, w._idle_unload_s)
        os.environ["LOCALFLOW_WORKER_IDLE_UNLOAD_S"] = "99"
        w = worker.Worker("unused")
        os.environ["LOCALFLOW_WORKER_IDLE_UNLOAD_S"] = "1"
        assert w._idle_unload_s == 99.0, "the period must not be re-read"
    finally:
        os.environ.pop("LOCALFLOW_WORKER_IDLE_UNLOAD_S", None)
        if saved is not None:
            os.environ["LOCALFLOW_WORKER_IDLE_UNLOAD_S"] = saved
    print("ok  idle period env: unset 600 s, a positive number replaces it,"
          " anything else turns unloading off, read once")


def main():
    run([test_cleanup_unloads_after_the_idle_period_and_frees_the_model_first,
         test_a_busy_worker_unloads_only_after_its_last_task_and_an_empty_queue,
         test_ensure_cleanup_on_a_ready_engine_writes_nothing_and_keeps_it_loaded,
         test_ensure_cleanup_while_unloaded_reloads_once_however_often_it_is_sent,
         test_a_clean_sent_while_unloaded_waits_for_the_reload_and_gets_the_real_answer,
         test_a_clean_sent_during_an_ensure_cleanup_reload_waits_for_it,
         test_a_transcribe_is_served_while_unloaded_and_during_a_reload,
         test_a_transcribe_queued_ahead_of_a_clean_runs_before_the_reload,
         test_a_failed_reload_ends_in_the_failed_engine_behaviour,
         test_unload_and_reload_never_change_identity_fault_or_restart_the_worker,
         test_with_unloading_off_the_frame_stream_is_the_one_written_before,
         test_the_idle_period_is_read_once_at_start_from_the_environment,
         test_a_clean_dispatched_just_before_the_unload_decision_is_answered,
         test_a_clean_dispatched_just_after_the_unload_decision_waits_for_the_reload,
         test_a_clean_that_finds_no_engine_on_the_llm_path_is_answered_not_raised,
         test_dropping_the_real_engine_frees_the_model_it_was_built_on],
        "worker idle unload tests")


if __name__ == "__main__":
    main()
