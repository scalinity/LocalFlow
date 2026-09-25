"""M03 remediation: the PRODUCTION worker's scheduling and input boundary.

Unlike ``fake_worker.py`` (a protocol re-implementation), these tests run
``localflow.v2.worker`` itself — ``Worker.serve``, its control/GPU thread
split, framing, fault codes and input checks — either in a subprocess
through ``prod_worker_harness.py`` (only the two model LOADERS are
shimmed; a latch file holds the cleanup load) or in-process for the input
boundary. Model quality is not measured: no MLX, Parakeet or Qwen runs.

  07  "basic now" is served NOW while the cleanup load is latched; the
      bounded hold returns at its bound; a spawn made for a waiting request
      serves that request before the cleanup load; ASR queued behind an
      in-progress cleanup load is reported
  09  a sample-rate mismatch is refused, never relabeled
  10  a truncated WAV is refused at the worker boundary (complete control)
  12  fault reason codes are controlled tokens
  13  write-all framing under short writes; a malformed request body is
      refused and the NEXT request is still served
  14  symlink/FIFO/directory/traversal inputs are refused without blocking

Run: .venv/bin/python tests/v2/lifecycle/test_m03_remediation_worker.py
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, make_sup, run, tmpdir, wav  # noqa: E402
from localflow.cleanup import basic_cleanup  # noqa: E402
from localflow.v2 import worker as wm  # noqa: E402
from localflow.v2.supervisor import WorkerFailure  # noqa: E402


def _records(path):
    p = pathlib.Path(path)
    return [json.loads(x) for x in p.read_text().splitlines()] \
        if p.exists() else []


def test_07_basic_now_while_cleanup_load_is_latched():
    with tmpdir() as td:
        latch = pathlib.Path(td) / "release"
        recf = pathlib.Path(td) / "rec.jsonl"
        s, rec = make_sup(td, {"cleanup_load_latch": str(latch),
                               "clean": ["ok:ENGINE TEXT"],
                               "record": str(recf)}, prod=True)
        try:
            s.ensure_running()  # launch warm-up: no request waiting
            assert s.wait_engine("asr", 15) == "ready"
            deadline = time.monotonic() + 10
            while s.engine_state["cleanup"] != "loading" \
                    and time.monotonic() < deadline:
                time.sleep(0.01)
            assert s.engine_state["cleanup"] == "loading"
            assert any(r["event"] == "cleanup_load_started"
                       for r in _records(recf)), "load not latched"
            # bounded hold: returns at its bound with the honest state
            t0 = time.monotonic()
            assert s.wait_engine("cleanup", 0.5) == "loading"
            assert 0.4 <= time.monotonic() - t0 < 3.0
            # basic now: answered while the load is still latched
            t0 = time.monotonic()
            out = s.clean(job_id="j", attempt=1, raw_text="um keep this")
            assert time.monotonic() - t0 < 2.0, "basic-now waited on load"
            assert out["text"] == "um keep this"  # V2: unchanged input
            assert out["path"] == "llm_fallback_normalized"
            assert out["fallback_reason"] == "cleanup_not_ready"
            assert s.engine_state["cleanup"] == "loading"
            # release: the engine takes over (positive control)
            latch.write_text("go")
            assert s.wait_engine("cleanup", 15) == "ready"
            out = s.clean(job_id="j", attempt=1, raw_text="um keep this")
            assert out["path"] == "llm" and out["text"] == "ENGINE TEXT"
            assert rec.count("worker.spawned") == 1
        finally:
            latch.write_text("go")
            s.shutdown()
    print("ok  07 cleanup load latched: hold bounded at 0.5 s, basic-now"
          " answered < 2 s honestly labeled; engine after release")


def test_07_v1_basic_now_is_the_basic_pass():
    with tmpdir() as td:
        latch = pathlib.Path(td) / "release"
        s, rec = make_sup(td, {"cleanup_load_latch": str(latch)}, prod=True)
        s.cleanup_implementation = "v1"
        try:
            s.ensure_running()
            s.wait_engine("asr", 15)
            out = s.clean(job_id="j", attempt=1,
                          raw_text="um so like hello there")
            assert out["path"] == "basic"
            assert out["fallback_reason"] == "cleanup_not_ready"
            assert out["text"] == basic_cleanup("um so like hello there")
        finally:
            latch.write_text("go")
            s.shutdown()
    print("ok  07 v1 basic-now: the basic pass, labeled basic")


def test_07_request_spawn_serves_request_before_cleanup_load():
    """A worker spawned FOR a waiting transcribe defers the cleanup load
    until that request arrived: the ASR result is produced before the
    cleanup load starts (GPU work stays one-at-a-time)."""
    with tmpdir() as td:
        latch = pathlib.Path(td) / "release"
        recf = pathlib.Path(td) / "rec.jsonl"
        w = wav(pathlib.Path(td) / "audio", "job-a.wav")
        s, rec = make_sup(td, {"cleanup_load_latch": str(latch),
                               "transcribe": ["ok:asr first"],
                               "record": str(recf)}, prod=True)
        try:
            res = s.transcribe(job_id="job-a", attempt=1, audio_name=w.name)
            assert res["text"] == "asr first"
            deadline = time.monotonic() + 10
            events = []
            while time.monotonic() < deadline:
                events = [r["event"] for r in _records(recf)]
                if "cleanup_load_started" in events:
                    break
                time.sleep(0.01)
            # both happened, in this order (the deferred load still runs)
            assert events.index("transcribe") \
                < events.index("cleanup_load_started"), events
        finally:
            latch.write_text("go")
            s.shutdown()
    print("ok  07 request-made spawn: ASR served before the cleanup load")


def test_07_asr_behind_inflight_load_is_reported():
    with tmpdir() as td:
        latch = pathlib.Path(td) / "release"
        recf = pathlib.Path(td) / "rec.jsonl"
        w = wav(pathlib.Path(td) / "audio", "job-q.wav")
        s, rec = make_sup(td, {"cleanup_load_latch": str(latch),
                               "transcribe": ["ok:queued asr"],
                               "record": str(recf)}, prod=True)
        try:
            s.ensure_running()
            s.wait_engine("asr", 15)
            deadline = time.monotonic() + 10
            while s.engine_state["cleanup"] != "loading" \
                    and time.monotonic() < deadline:
                time.sleep(0.01)
            threading.Timer(0.6, lambda: latch.write_text("go")).start()
            t0 = time.monotonic()
            res = s.transcribe(job_id="job-q", attempt=1, audio_name=w.name)
            waited = time.monotonic() - t0
            assert res["text"] == "queued asr" and not res.get("retried")
            assert waited >= 0.4, "ASR ran concurrently with a load?"
            ev = rec.named("worker.request_queued_behind_load")
            assert ev and ev[0]["reason_code"] == "cleanup_load_in_progress"
        finally:
            latch.write_text("go")
            s.shutdown()
    print("ok  07 ASR behind an in-progress cleanup load: waits for the one"
          " GPU owner, reported by event")


def test_10_truncated_input_refused_complete_served():
    with tmpdir() as td:
        root = pathlib.Path(td) / "audio"
        full = wav(root, "job-full.wav", n=16000)
        cut = wav(root, "job-cut.wav", n=16000)
        raw = cut.read_bytes()
        cut.write_bytes(raw[:44 + 8000 * 4])
        recf = pathlib.Path(td) / "rec.jsonl"
        s, rec = make_sup(td, {"transcribe": ["ok:full"],
                               "record": str(recf)}, prod=True)
        try:
            res = s.transcribe(job_id="job-full", attempt=1,
                               audio_name=full.name, sample_rate=16000)
            assert res["sample_count"] == 16000
            try:
                s.transcribe(job_id="job-cut", attempt=1,
                             audio_name=cut.name, sample_rate=16000)
                raise AssertionError("truncated input accepted")
            except WorkerFailure as e:
                assert e.reason_code == "audio_incomplete" and not e.fatal
            sizes = [r["samples"] for r in _records(recf)
                     if r["event"] == "transcribe"]
            assert sizes == [16000], sizes
        finally:
            s.shutdown()
    print("ok  10 worker: truncated WAV refused (audio_incomplete); complete"
          " control transcribed with all 16000 samples")


class _T:
    last_decode_ranges = None

    def __init__(self, model_rate=None):
        self._rate = model_rate
        self.seen = []

    def model_sample_rate(self):
        return self._rate

    def transcribe(self, samples):
        self.seen.append(int(samples.size))
        return "text"


def _capture(fn):
    sent = []
    real = wm._write_msg
    wm._write_msg = sent.append
    try:
        fn()
    finally:
        wm._write_msg = real
    return sent


def test_09_rate_is_refused_not_relabeled():
    with tmpdir() as td:
        root = pathlib.Path(td)
        wav(root, "job-8k.wav", n=800, rate=8000)
        w = wm.Worker(str(root))
        w.transcriber = _T(model_rate=16000)
        for declared, code in ((16000, "audio_rate_mismatch"),
                               (None, "audio_unsupported_rate")):
            try:
                w._transcribe({"req_id": "r", "audio": {"name":
                                                        "job-8k.wav"},
                               "sample_rate": declared})
                raise AssertionError("mis-rated input accepted")
            except wm.InputError as e:
                assert e.code == code, (declared, e.code)
        assert w.transcriber.seen == []
        wav(root, "job-16k.wav", n=800, rate=16000)
        sent = _capture(lambda: w._transcribe(
            {"req_id": "r", "audio": {"name": "job-16k.wav"},
             "sample_rate": 16000}))
        assert sent[0]["sample_rate"] == 16000 and w.transcriber.seen == [800]
    print("ok  09 worker: rate mismatch / unsupported model rate refused;"
          " matching control transcribed")


def test_14_input_path_matrix():
    with tmpdir() as td:
        td = pathlib.Path(td)
        root = td / "audio"
        root.mkdir()
        wav(td, "outside.wav", n=800)
        wav(root, "job-inside.wav", n=800)
        os.symlink(td / "outside.wav", root / "job-link-out.wav")
        os.symlink(root / "job-inside.wav", root / "job-link-in.wav")
        os.mkfifo(root / "job-fifo.wav")
        (root / "job-dir.wav").mkdir()
        w = wm.Worker(str(root))
        w.transcriber = _T()
        expect = {"job-link-out.wav": "audio_symlink_refused",
                  "job-link-in.wav": "audio_symlink_refused",
                  "job-fifo.wav": "audio_not_regular_file",
                  "job-dir.wav": "audio_not_regular_file",
                  "../outside.wav": "unsafe_audio_reference",
                  "/etc/passwd": "unsafe_audio_reference",
                  "a/b.wav": "unsafe_audio_reference",
                  "..": "unsafe_audio_reference",
                  "job-absent.wav": "audio_missing"}
        for name, code in expect.items():
            t0 = time.monotonic()
            try:
                w._transcribe({"req_id": "r", "audio": {"name": name}})
                raise AssertionError(f"{name} accepted")
            except wm.InputError as e:
                assert e.code == code, (name, e.code)
            assert time.monotonic() - t0 < 1.0, f"{name} blocked"
        assert w.transcriber.seen == [], "a refused input reached the model"
        sent = _capture(lambda: w._transcribe(
            {"req_id": "r", "audio": {"name": "job-inside.wav"}}))
        assert sent[0]["op"] == "result" and w.transcriber.seen == [800]
    print("ok  14 symlink (in/out), FIFO, directory, traversal, missing:"
          " refused without blocking; regular control read")


def test_13_write_all_and_frame_cap():
    buf = bytearray()
    real = wm.os.write

    def short(fd, data):
        chunk = bytes(data[:5])
        buf.extend(chunk)
        return len(chunk)

    wm.os.write = short
    try:
        wm._write_msg({"v": 1, "op": "result", "text": "x" * 300})
    finally:
        wm.os.write = real
    n = int.from_bytes(buf[:4], "big")
    assert len(buf) == 4 + n and json.loads(buf[4:])["text"] == "x" * 300
    real_max = wm.MAX_FRAME
    wm.MAX_FRAME = 64
    try:
        try:
            wm._write_msg({"text": "y" * 200})
            raise AssertionError("oversized frame written")
        except wm.ProtocolError as e:
            assert e.code == "response_too_large"
    finally:
        wm.MAX_FRAME = real_max
    print("ok  13 worker write-all under 5-byte writes; oversized frame"
          " refused before any byte")


def _send(p, obj):
    body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
    p.stdin.write(len(body).to_bytes(4, "big") + body)
    p.stdin.flush()


def _recv(p):
    n = int.from_bytes(p.stdout.read(4), "big")
    return json.loads(p.stdout.read(n))


def test_13_malformed_request_then_next_served():
    with tmpdir() as td:
        plan = pathlib.Path(td) / "plan.json"
        plan.write_text(json.dumps({"transcribe": ["ok:after bad"]}))
        root = pathlib.Path(td) / "audio"
        w = wav(root, "job-m.wav")
        env = dict(os.environ, LOCALFLOW_PROD_WORKER_PLAN=str(plan),
                   PYTHONPATH=str(ROOT))
        p = subprocess.Popen([sys.executable, str(PROD), "--audio-root",
                              str(root)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env)
        try:
            assert _recv(p)["op"] == "hello"
            _send(p, {"v": 1, "op": "load", "asr_model": "a",
                      "cleanup_mode": "off"})
            seen = []
            _send(p, b"{not json")
            _send(p, [1, 2, 3])
            _send(p, {"v": 99, "op": "transcribe", "req_id": "r0"})
            _send(p, {"v": 1, "op": "transcribe", "req_id": 7,
                      "generation": 1})
            _send(p, {"v": 1, "op": "transcribe", "req_id": "r1",
                      "generation": 1, "attempt": 1, "job_id": "job-m",
                      "audio": {"name": w.name}})
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                m = _recv(p)
                seen.append(m)
                if m.get("op") == "result":
                    break
            faults = [m for m in seen if m.get("op") == "fault"]
            codes = [f["reason_code"] for f in faults]
            assert codes == ["unparsable_request", "non_object_request",
                             "protocol_version_mismatch",
                             "bad_request_fields"], codes
            assert all(f["fault_class"] == "protocol" for f in faults)
            assert faults[2]["req_id"] == "r0"
            assert seen[-1]["op"] == "result"
            assert seen[-1]["text"] == "after bad"
            assert p.poll() is None, "worker died on a malformed body"
        finally:
            p.kill()
            p.wait(5)
    print("ok  13 malformed bodies refused as protocol faults; the next"
          " request is served by the same process")


def test_12_fault_codes_are_controlled():
    sent = _capture(lambda: wm._fault(
        {"req_id": "r", "op": "transcribe", "job_id": "j"}, "Runtime Error",
        "Oops /Users/x/secret: transcript words"))
    f = sent[0]
    assert f["reason_code"] == "stage_exception"
    assert f["error_type"] == "Exception" and f["fault_class"] == "runtime"
    sent = _capture(lambda: wm._fault({"req_id": "r"}, "KeyError",
                                      "audio_missing", "input"))
    assert sent[0]["reason_code"] == "audio_missing"
    assert sent[0]["error_type"] == "KeyError"
    assert wm._reason(RuntimeError("secret text")) == "stage_exception"
    print("ok  12 worker fault codes: free text replaced, tokens kept")


def main():
    run([test_07_basic_now_while_cleanup_load_is_latched,
         test_07_v1_basic_now_is_the_basic_pass,
         test_07_request_spawn_serves_request_before_cleanup_load,
         test_07_asr_behind_inflight_load_is_reported,
         test_10_truncated_input_refused_complete_served,
         test_09_rate_is_refused_not_relabeled,
         test_14_input_path_matrix,
         test_13_write_all_and_frame_cap,
         test_13_malformed_request_then_next_served,
         test_12_fault_codes_are_controlled],
        "m03 remediation worker tests")


if __name__ == "__main__":
    main()
