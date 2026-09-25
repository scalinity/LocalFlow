"""M03 remediation: worker supervision regressions (EV-05, portable).

Real ``WorkerSupervisor`` + fresh subprocesses (the protocol fake, or the
production worker entry with shimmed model loaders), with latches instead
of sleeps at the interleavings the audit named:

  03  an old reader's finalizer can never fail a newer generation's request
  04  one lifecycle authority: closed admission, no respawn after shutdown,
      restart serialized with the retry's spawn, a waiting spawn woken
  05  a failed automatic retry carries the attempt that actually executed
  06  a second fatal failure / a runtime cleanup fallback retires its
      generation; a non-fatal refusal does not
  12  fault reason codes are controlled tokens (canary exception text never
      reaches events or the WorkerFailure)
  13  pending entries carry immutable expected identity; framing failures
      are generation-scoped; malformed frames never kill the reader
  16  stderr diagnostics are bytes-safe, byte-bounded, generation-owned and
      never change a request's disposition
  24  the retry budget is per stage (documented design; traced)

Each test asserts its adverse event actually happened (held finalizer,
gated spawn, delivered frame) and a positive population (a real result).

Run: .venv/bin/python tests/v2/lifecycle/test_m03_remediation_supervisor.py
"""

import io
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import (FAKE, Rec, alive, make_sup, run, tmpdir,  # noqa: E402
                         wav)
from localflow.v2 import supervisor as sup_mod  # noqa: E402
from localflow.v2.supervisor import WorkerFailure, WorkerSupervisor  # noqa: E402,E501

# The contract's byte cap (16 KiB); read from the module when it has one.
STDERR_TAIL_BYTES = getattr(sup_mod, "STDERR_TAIL_BYTES", 16 * 1024)


def _hold_finalizer(s, generation):
    hold, held = threading.Event(), threading.Event()
    real = s.emit

    def emit(event, level="INFO", **kw):
        if event == "worker.pipe_closed" \
                and kw.get("worker_generation") == generation:
            held.set()
            hold.wait(10)
        real(event, level=level, **kw)

    s.emit = emit
    return hold, held


def test_03_old_finalizer_cannot_fail_new_request():
    """R01: G1's reader is held inside its finally while G2 registers a
    request; releasing G1 must not resolve it."""
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-g.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:g1", "delay:1200|ok:g2"]})
        hold, held = _hold_finalizer(s, 1)
        try:
            assert s.transcribe(job_id="job-1", attempt=1,
                                audio_name=w.name)["text"] == "g1"
            s._proc.kill()
            assert held.wait(5), "G1 finalizer never reached (no race)"
            out = {}
            t = threading.Thread(target=lambda: out.update(
                res=s.transcribe(job_id="job-2", attempt=1,
                                 audio_name=w.name)))
            t.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with s._state_lock:
                    live = [p for p in s._pending.values()
                            if p.generation == 2]
                if live:
                    break
                time.sleep(0.005)
            assert live, "G2 request never registered"
            hold.set()  # G1's finalizer runs now, with G2's request live
            t.join(20)
            res = out["res"]
            assert res["text"] == "g2" and not res.get("retried")
            assert res["generation"] == 2
            assert rec.count("worker.spawned") == 2
            assert rec.count("worker.died") == 0
        finally:
            hold.set()
            s.shutdown()
    print("ok  03 held G1 finalizer vs live G2 request: G2 answered once,"
          " no retry, no death")


def test_03_finalizer_before_registration():
    """The other order: G1 finalizes fully before G2 exists; a request
    registered afterwards is served by G2 (not resolved by G1)."""
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-g.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:g1", "ok:g2"]})
        try:
            s.transcribe(job_id="job-1", attempt=1, audio_name=w.name)
            s._proc.kill()
            s._readers[1].join(5)
            assert not s._readers[1].is_alive()
            res = s.transcribe(job_id="job-2", attempt=1, audio_name=w.name)
            assert res["text"] == "g2" and res["generation"] == 2
            assert not res.get("retried")
        finally:
            s.shutdown()
    print("ok  03 finalizer before registration: fresh generation serves")


def test_04_closed_admission_is_permanent():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-x.wav")
        s, rec = make_sup(td, {"transcribe": ["ok:a"]})
        s.transcribe(job_id="job-x", attempt=1, audio_name=w.name)
        pid = s._proc.pid
        status = s.shutdown()
        assert status["closed"] and not alive(pid)
        spawned = rec.count("worker.spawned")
        for call in (lambda: s.transcribe(job_id="job-x", attempt=1,
                                          audio_name=w.name),
                     lambda: s.clean(job_id="job-x", attempt=1,
                                     raw_text="x"),
                     s.ensure_running, s.restart):
            try:
                call()
                raise AssertionError("accepted after shutdown")
            except WorkerFailure as e:
                assert e.reason_code == "supervisor_closed"
                assert e.fatal is False
        assert rec.count("worker.spawned") == spawned
        assert s._proc is None
    print("ok  04 closed admission: request/clean/ensure/restart refused,"
          " nothing spawned")


def test_04_shutdown_during_request_never_respawns():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-y.wav")
        s, rec = make_sup(td, {"transcribe": ["delay:5000|ok:late"]})
        procs = []
        real = sup_mod.subprocess.Popen

        def popen(*a, **kw):
            p = real(*a, **kw)
            procs.append(p)
            return p

        sup_mod.subprocess.Popen = popen
        try:
            s.ensure_running()
            out = {}

            def go():
                try:
                    s.transcribe(job_id="job-y", attempt=1,
                                 audio_name=w.name)
                except WorkerFailure as e:
                    out["e"] = e

            t = threading.Thread(target=go)
            t.start()
            deadline = time.monotonic() + 10
            while not s._pending and time.monotonic() < deadline:
                time.sleep(0.005)
            assert s._pending, "request never in flight"
            t0 = time.monotonic()
            s.shutdown(timeout=0.5)
            t.join(10)
            e = out["e"]
            assert e.reason_code == "supervisor_closed" and not e.fatal
            assert e.attempt == 1, "the admitted attempt is named"
            assert time.monotonic() - t0 < 5
            assert len(procs) == 1, "a closed supervisor respawned"
            assert all(p.poll() is not None for p in procs)
        finally:
            sup_mod.subprocess.Popen = real
            for p in procs:
                if p.poll() is None:
                    p.kill()
    print("ok  04 shutdown mid-request: bounded refusal, no respawn, reaped")


def test_04_restart_serialized_with_retry_spawn():
    """R02: the automatic retry's spawn is held; a manual restart cannot
    run until it finishes, and no child is orphaned."""
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-z.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:Injected", "ok:after"]})
        procs = []
        gate, entered = threading.Event(), threading.Event()
        real = sup_mod.subprocess.Popen

        def popen(*a, **kw):
            if len(procs) == 1:
                entered.set()
                gate.wait(10)
            p = real(*a, **kw)
            procs.append(p)
            return p

        sup_mod.subprocess.Popen = popen
        try:
            s.ensure_running()
            out = {}
            t = threading.Thread(target=lambda: out.update(
                res=s.transcribe(job_id="job-z", attempt=1,
                                 audio_name=w.name)))
            t.start()
            assert entered.wait(10), "retry spawn never reached"
            rt = threading.Thread(target=s.restart)
            rt.start()
            rt.join(0.8)
            assert rt.is_alive(), "restart ran inside the retry's spawn"
            gate.set()
            rt.join(20)
            t.join(20)
            assert out["res"]["text"] == "after"
            s.shutdown()
            assert all(p.poll() is not None for p in procs), \
                "orphaned worker child"
            assert len(procs) == 3
        finally:
            gate.set()
            sup_mod.subprocess.Popen = real
            for p in procs:
                if p.poll() is None:
                    p.kill()
    print("ok  04 restart waits for the retry's spawn; zero orphans")


def test_04_shutdown_wakes_a_spawn_waiting_for_hello():
    with tmpdir() as td:
        s = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="x",
            emit=Rec(), worker_cmd=[sys.executable, "-c",
                                    "import time; time.sleep(60)"],
            hello_timeout=30.0)
        out = {}

        def go():
            try:
                s.ensure_running()
            except WorkerFailure as e:
                out["e"] = e

        t = threading.Thread(target=go)
        t.start()
        deadline = time.monotonic() + 5
        while s._proc is None and time.monotonic() < deadline:
            time.sleep(0.01)
        child = s._proc
        assert child is not None
        t0 = time.monotonic()
        s.shutdown(timeout=1.0)
        t.join(10)
        assert out["e"].reason_code == "supervisor_closed"
        assert time.monotonic() - t0 < 5, "shutdown waited for hello"
        assert child.poll() is not None, "the unanswered child survived"
    print("ok  04 shutdown wakes a spawn waiting for hello; child killed")


def test_05_failed_retry_carries_executed_attempt():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-a.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:A", "fault:B"]})
        sent = []
        real = s._send

        def send(msg, **kw):
            if msg.get("op") == "transcribe":
                sent.append((msg["attempt"], msg["generation"]))
            return real(msg, **kw)

        s._send = send
        try:
            try:
                s.transcribe(job_id="job-a", attempt=1, audio_name=w.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert sent == [(1, 1), (2, 2)], sent
                assert e.attempt == 2 and e.generation == 2
                assert e.retried is True and e.fatal is True
        finally:
            s.shutdown()
    print("ok  05 failed retry: WorkerFailure names executed attempt 2 /"
          " generation 2 (sent [1, 2])")


def test_05_retry_never_admitted_keeps_first_attempt():
    """The retry's spawn fails before any request reaches it: the executed
    attempt is still 1 (never an unexecuted 2)."""
    with tmpdir() as td:
        marker = pathlib.Path(td) / "second-spawn"
        script = (f'if [ -e "{marker}" ]; then exit 3; fi; touch "{marker}";'
                  f' exec "{sys.executable}" "{FAKE}" "$@"')
        w = wav(pathlib.Path(td) / "audio", "job-b.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:A"]},
                          worker_cmd=["sh", "-c", script, "sh"],
                          hello_timeout=3.0)
        try:
            try:
                s.transcribe(job_id="job-b", attempt=1, audio_name=w.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code == "hello_timeout", e.reason_code
                assert e.attempt == 1 and e.generation == 1
                assert e.retried is False
        finally:
            s.shutdown()
    print("ok  05 retry spawn failed: executed attempt stays 1")


def test_06_second_fatal_failure_retires_generation():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-f.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:F", "fault:F",
                                              "ok:next job"]})
        try:
            try:
                s.transcribe(job_id="job-f", attempt=1, audio_name=w.name)
            except WorkerFailure:
                pass
            assert s._proc is None, "the second failed child was kept"
            assert rec.count("worker.retired") >= 2
            res = s.transcribe(job_id="job-n", attempt=1, audio_name=w.name)
            assert res["text"] == "next job" and res["generation"] == 3
            assert s.supervisor_state != "failed", \
                "retirement is not the breaker"
        finally:
            s.shutdown()
    print("ok  06 second fatal failure retired below the breaker;"
          " next job on generation 3")


def test_06_runtime_cleanup_fallback_retires_generation():
    """Production worker: an exception escaping the cleanup engine keeps
    the text but retires the process; a healthy result does not."""
    with tmpdir() as td:
        s, rec = make_sup(td, {"clean": ["ok:clean one",
                                         "raise:boom in generation",
                                         "ok:after retire"]}, prod=True)
        try:
            s.ensure_running()
            assert s.wait_engine("cleanup", 15) == "ready"
            ok = s.clean(job_id="j1", attempt=1, raw_text="clean one")
            assert ok["path"] == "llm" and not ok.get("retired_generation")
            gen = s.generation
            out = s.clean(job_id="j2", attempt=1, raw_text="keep me")
            assert out["text"] == "keep me"
            assert out["path"] == "llm_fallback_normalized"
            assert out["retired_generation"] is True
            assert s._consecutive_deaths == 1, "fallback counted healthy"
            assert s._proc is None
            after = s.clean(job_id="j3", attempt=1, raw_text="x")
            assert s.generation == gen + 1
            assert after["op"] == "result"
        finally:
            s.shutdown()
    print("ok  06 runtime cleanup exception: text kept, generation retired,"
          " death counted; healthy control untouched")


def test_06_nonfatal_refusal_keeps_generation():
    with tmpdir() as td:
        s, rec = make_sup(td, {}, prod=True)
        try:
            s.ensure_running()
            s.wait_engine("asr", 15)
            gen, pid = s.generation, s._proc.pid
            try:
                s.transcribe(job_id="j", attempt=1,
                             audio_name="job-missing.wav")
                raise AssertionError("expected refusal")
            except WorkerFailure as e:
                assert e.reason_code == "audio_missing", e.reason_code
                assert e.fatal is False and e.retried is False
            assert s.generation == gen and s._proc.pid == pid
            assert rec.count("worker.died") == 0
            assert rec.count("worker.spawned") == 1
        finally:
            s.shutdown()
    print("ok  06 input refusal: no kill, no retry, no death")


CANARY = "CANARY-/Users/someone/private transcript-words sk-TOKEN123"


def test_12_fault_reason_codes_are_content_free():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-c.wav")
        s, rec = make_sup(td, {"transcribe": ["raise:" + CANARY,
                                              "raise:" + CANARY]},
                          prod=True)
        try:
            try:
                s.transcribe(job_id="job-c", attempt=1, audio_name=w.name)
                raise AssertionError("expected WorkerFailure")
            except WorkerFailure as e:
                assert e.reason_code == "stage_exception"
                assert e.detail == "RuntimeError"
                assert "CANARY" not in str(e)
            faults = rec.named("worker.fault")
            assert len(faults) == 2, "both faults delivered"
            assert all(f["reason_code"] == "stage_exception" for f in faults)
            assert "CANARY" not in rec.blob()
        finally:
            s.shutdown()
    # a parent-side sanitizer backs it: foreign text never becomes a code
    assert sup_mod.safe_code("Path /Users/x failed") == "unspecified"
    assert sup_mod.safe_code("injected_fault") == "injected_fault"
    print("ok  12 canary exception text absent from events and failures;"
          " type kept separately")


def _pending(s, req, **kw):
    p = s._new_pending(req, **kw)
    with s._state_lock:
        s._pending[req] = p
    return p


def test_13_expected_identity_matrix():
    with tmpdir() as td:
        s, rec = make_sup(td, {})
        try:
            s.ensure_running()
            g = s.generation
            base = {"v": 1, "op": "result", "kind": "asr", "job_id": "job-A",
                    "attempt": 1, "generation": g, "text": "x"}
            cases = {"wrong_job": {"job_id": "job-B"},
                     "old_attempt": {"attempt": 0},
                     "wrong_kind": {"kind": "clean"},
                     "echoes_old_generation": {"generation": g - 1}}
            for name, patch in cases.items():
                p = _pending(s, "req-" + name, op="transcribe",
                             job_id="job-A", attempt=1, generation=g)
                s._handle_message(dict(base, req_id="req-" + name, **patch),
                                  g, s._proc)
                assert p.event.is_set() and p.msg["op"] == "fault", name
            # positive control: the matching frame resolves as a result
            p = _pending(s, "req-ok", op="transcribe", job_id="job-A",
                         attempt=1, generation=g)
            s._handle_message(dict(base, req_id="req-ok"), g, s._proc)
            assert p.msg["op"] == "result" and p.msg["text"] == "x"
            # a duplicate after resolution is discarded
            before = rec.count("worker.stale_result_discarded")
            s._handle_message(dict(base, req_id="req-ok"), g, s._proc)
            assert rec.count("worker.stale_result_discarded") == before + 1
            # another generation's reader can neither resolve nor fault it
            p = _pending(s, "req-foreign", op="transcribe", job_id="job-A",
                         attempt=1, generation=g)
            s._handle_message(dict(base, req_id="req-foreign"), g + 7, None)
            s._handle_message({"v": 1, "op": "fault",
                               "req_id": "req-foreign"}, g + 7, None)
            assert not p.event.is_set()
            # non-object / versionless frames never raise
            for frame in ([1, 2], "str", {"op": "result"}, None):
                s._handle_message(frame, g, None)
            assert rec.count("worker.protocol_error") >= 3
            with s._state_lock:
                s._pending.clear()
        finally:
            s.shutdown()
    print("ok  13 expected identity: wrong job/attempt/kind/echo → fault;"
          " duplicate discarded; foreign generation inert")


class _Dribble:
    """A pipe that returns at most 3 bytes per read: every frame arrives
    split across many reads (headers included)."""

    def __init__(self, data):
        self._b = io.BytesIO(data)
        self.reads = 0

    def read(self, n):
        self.reads += 1
        return self._b.read(min(n, 3))


class _Proc:
    def __init__(self, data):
        self.stdout = _Dribble(data)


def _frame(obj):
    import json
    b = json.dumps(obj).encode()
    return len(b).to_bytes(4, "big") + b


def test_13_reader_framing_is_generation_scoped():
    with tmpdir() as td:
        _reader_framing(td)


def _reader_framing(td):
    s = WorkerSupervisor(audio_root=pathlib.Path(td) / "a",
                         asr_model="x", emit=Rec())
    s.generation = 1
    other = _pending(s, "req-g2", op="transcribe", job_id="j", attempt=1,
                     generation=2)
    mine = _pending(s, "req-g1", op="transcribe", job_id="j", attempt=1,
                    generation=1)
    good = _frame({"v": 1, "op": "result", "kind": "asr", "req_id": "req-g1",
                   "job_id": "j", "attempt": 1, "generation": 1, "text": "t"})
    bad_json = b"\x00\x00\x00\x05{nope"
    data = bad_json + good + _frame({"v": 1, "op": "x"})
    data += (100).to_bytes(4, "big") + b"{\"trunc"  # EOF mid-frame
    proc = _Proc(data)
    s._read_loop(proc, 1)
    assert proc.stdout.reads > len(good) // 3, "frames were not split"
    assert mine.msg["op"] == "result" and mine.msg["text"] == "t"
    assert not other.event.is_set(), "G1 framing failure touched G2"
    reasons = [kw["reason_code"] for kw in s.emit.named(
        "worker.protocol_error")]
    assert "unparsable_frame" in reasons and "truncated_frame" in reasons
    closed = s.emit.named("worker.pipe_closed")
    assert closed and closed[-1]["reason_code"] == "truncated_frame"
    print("ok  13 reader: bad JSON skipped, split frame joined, truncated"
          " frame ends only its own generation")


def test_16_diagnostics_bytes_bounded_owned():
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-d.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:Injected", "ok:after"]})
        try:
            s.ensure_running()
            s._stderr_tails[1].feed(b"Traceback (most recent call last)\n")
            res = s.transcribe(job_id="job-d", attempt=1, audio_name=w.name)
            assert res["text"] == "after" and res["retried"]
            f = rec.named("worker.fault")
            assert f and "traceback=yes" in f[0]["detail"], f
            assert f[0]["reason_code"] == "injected_fault"
            # a newline-free 4 MiB stream stays within the byte cap
            s._stderr_tails[s.generation].feed(b"x" * (4 << 20))
            assert s._stderr_tails[s.generation].size() <= STDERR_TAIL_BYTES
            # an old generation's late stderr never enters the new tail
            cur = s.generation
            before = s._stderr_tails[cur].size()

            class Old:
                class stderr:
                    chunks = [b"late old line\n"]

                    @classmethod
                    def read1(cls, n):
                        return cls.chunks.pop() if cls.chunks else b""

            s._drain_stderr(Old(), cur - 1)
            assert s._stderr_tails[cur].size() == before
            # a broken tail never raises out of the digest
            s._stderr_tails[cur] = object()
            assert s._fault_detail(cur) == "stderr_digest_unavailable"
        finally:
            s.shutdown()
    print("ok  16 bytes-safe digest, 16 KiB cap, generation-owned tails,"
          " non-throwing diagnostics")


def test_24_retry_budget_is_per_stage():
    """Design decision (documented): one automatic retry per stage
    request. A dictation whose ASR and cleanup each fault once executes
    four requests with attempts 1, 2, 2, 3 — one logical job."""
    with tmpdir() as td:
        w = wav(pathlib.Path(td) / "audio", "job-r.wav")
        s, rec = make_sup(td, {"transcribe": ["fault:A", "ok:asr"],
                               "clean": ["fault:B", "ok:clean"]})
        sent = []
        real = s._send

        def send(msg, **kw):
            if msg.get("op") in ("transcribe", "clean"):
                sent.append((msg["op"], msg["attempt"]))
            return real(msg, **kw)

        s._send = send
        try:
            r1 = s.transcribe(job_id="job-r", attempt=1, audio_name=w.name)
            r2 = s.clean(job_id="job-r", attempt=r1["attempt"],
                         raw_text="x")
            assert sent == [("transcribe", 1), ("transcribe", 2),
                            ("clean", 2), ("clean", 3)], sent
            assert r2["attempt"] == 3
        finally:
            s.shutdown()
    print("ok  24 per-stage retry budget traced: attempts 1,2,2,3")


def main():
    run([test_03_old_finalizer_cannot_fail_new_request,
         test_03_finalizer_before_registration,
         test_04_closed_admission_is_permanent,
         test_04_shutdown_during_request_never_respawns,
         test_04_restart_serialized_with_retry_spawn,
         test_04_shutdown_wakes_a_spawn_waiting_for_hello,
         test_05_failed_retry_carries_executed_attempt,
         test_05_retry_never_admitted_keeps_first_attempt,
         test_06_second_fatal_failure_retires_generation,
         test_06_runtime_cleanup_fallback_retires_generation,
         test_06_nonfatal_refusal_keeps_generation,
         test_12_fault_reason_codes_are_content_free,
         test_13_expected_identity_matrix,
         test_13_reader_framing_is_generation_scoped,
         test_16_diagnostics_bytes_bounded_owned,
         test_24_retry_budget_is_per_stage],
        "m03 remediation supervisor tests")


if __name__ == "__main__":
    main()
