"""M02 remediation regressions: typed-allowlist redacted export, roll-cap
eviction protection, closed admission, declared view ordering
(M02-AUDIT-12/13/15/20).

Synthetic markers and hand-written records only.

Run: .venv/bin/python tests/v2/logging/test_m02_remediation_events.py
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from localflow.v2 import eventlog, ids  # noqa: E402

SECRET = "sk-" + "Qq1Ww2Ee3Rr4Tt5Yy6Uu7Ii8"


def viewer():
    spec = importlib.util.spec_from_file_location(
        "view_events", ROOT / "scripts" / "v2" / "view_events.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_viewer(ve, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ve.main(argv)
    return code, out.getvalue(), err.getvalue()


def test_redacted_export_is_a_typed_allowlist():
    ve = viewer()
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td) / "logs"
        d.mkdir()
        job = ids.new_id("job")
        art = ids.new_id("art")
        good = {"schema_version": 2, "event_id": ids.new_id("evt"),
                "timestamp_utc": "2026-09-24T12:00:00.000Z",
                "timezone": "America/New_York", "utc_offset_minutes": -240,
                "boot_id": ids.new_id("boot"),
                "session_id": ids.new_id("session"), "process_id": 42,
                "worker_generation": 1, "sequence": 7, "job_id": job,
                "attempt": 2, "stage": "cleaning", "event": "stage.completed",
                "level": "INFO", "outcome": "llm",
                "reason_code": "TimeoutError", "duration_ms": 12.5,
                "queue_wait_ms": 0.1, "model_id": "mlx-community/Qwen3-4B",
                "config_hash": "ab12cd34ef", "artifact_ids": [art]}
        hostile = dict(good, event_id=ids.new_id("evt"), sequence=8,
                       detail="MARK_DETAIL secret", context="MARK_TOP",
                       error={"msg": ["MARK_NESTED"]},
                       reason_code="has spaces MARK_SPACE",
                       outcome=["MARK_LIST"], stage={"x": "MARK_OBJ"},
                       job_id="job-MARK_BADID", attempt="2",
                       model_id=SECRET, artifact_ids=["MARK_ART"],
                       duration_ms=True)
        (d / "events-2026-09-24.jsonl").write_text(
            json.dumps(good) + "\n" + json.dumps(hostile) + "\n")
        out = pathlib.Path(td) / "red.jsonl"
        code, _, _ = run_viewer(ve, ["--dir", str(d), "--export-redacted",
                                     str(out)])
        assert code == 0
        body = out.read_text()
        for marker in ("MARK_", SECRET, "secret"):
            assert marker not in body, marker
        recs = [json.loads(line) for line in body.splitlines()]
        assert len(recs) == 2
        a, b = recs
        # Every useful safe field survives on the well-formed record.
        for key in good:
            assert a[key] == good[key], key
        assert a["redaction_version"] == 1 and a["omitted_fields"] == 0
        # The hostile record keeps only fields that passed their checks.
        assert b["omitted_fields"] == 11, b  # detail, context, error,
        # reason_code, outcome, stage, job_id, attempt, model_id,
        # artifact_ids, duration_ms
        assert b["event"] == "stage.completed" and "job_id" not in b
        assert set(b) <= set(ve.REDACTION_ALLOWLIST) | {
            "redaction_version", "omitted_fields"}
    print("ok  12 redacted export: unknown/nested/wrong-type/secret-shaped"
          " values omitted and counted; safe identifiers kept")


def test_roll_cap_keeps_unresolved_evidence():
    with tempfile.TemporaryDirectory() as td:
        job = ids.new_id("job")
        unresolved = {job}
        old = eventlog.ROTATE_BYTES
        eventlog.ROTATE_BYTES = 2048
        try:
            w = eventlog.EventWriter(pathlib.Path(td) / "logs",
                                     mirror_stderr=False,
                                     unresolved_jobs_fn=lambda: set(unresolved))
            w.emit("capture.started", job_id=job, reason_code="marker")
            w.flush()
            for i in range(400):
                w.emit("filler.event", reason_code=f"r{i}")
            w.flush()
            files = list((pathlib.Path(td) / "logs").glob("events-*"))
            holders = [p for p in files if job in p.read_text()]
            assert len(holders) == 1, "protected roll evicted"
            assert w.stats()["protected_rolls_kept"] == 1
            rolls = [p for p in files if p.name.rsplit(".", 1)[-1].isdigit()]
            assert len(rolls) == eventlog.KEEP_ROLLS + 1  # cap + protected
            # Once the job resolves, the next rotation may evict it.
            unresolved.clear()
            for i in range(60):
                w.emit("filler.event", reason_code=f"s{i}")
            w.flush()
            files = list((pathlib.Path(td) / "logs").glob("events-*"))
            assert not any(job in p.read_text() for p in files)
            assert w.stats()["protected_rolls_kept"] == 0
            w.close()
        finally:
            eventlog.ROTATE_BYTES = old
    print("ok  13 roll cap keeps the roll carrying an unresolved job; evicts"
          " it once resolved")


def test_protection_fails_safe_when_unknown():
    with tempfile.TemporaryDirectory() as td:
        def broken():
            raise RuntimeError("store is closed")
        old = eventlog.ROTATE_BYTES
        eventlog.ROTATE_BYTES = 2048
        try:
            w = eventlog.EventWriter(pathlib.Path(td) / "logs",
                                     mirror_stderr=False,
                                     unresolved_jobs_fn=broken)
            for i in range(300):
                w.emit("filler.event", reason_code=f"r{i}")
            w.flush()
            w.close()
        finally:
            eventlog.ROTATE_BYTES = old
        rolls = [p for p in (pathlib.Path(td) / "logs").glob("events-*")
                 if p.name.rsplit(".", 1)[-1].isdigit()]
        assert len(rolls) > eventlog.KEEP_ROLLS
    print("ok  13 unknown protection state keeps rolls instead of deleting")


def test_emit_after_close_is_refused():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td) / "logs",
                                 mirror_stderr=False)
        for i in range(100):
            w.emit("before.close", reason_code=f"r{i}")
        status = w.close()
        assert status == {"drained": True, "pending": 0}, status
        assert w.emit("late.event", level="ERROR") is False
        assert w.stats()["dropped_after_close"] == 1
        text = "".join(p.read_text() for p in
                       (pathlib.Path(td) / "logs").glob("events-*"))
        assert text.count("before.close") == 100 and "late.event" not in text
    print("ok  15 event writer: accepted events drained at close; emit after"
          " close refused and counted")


def _rec(t, seq, tag, stream="a"):
    return json.dumps({"schema_version": 2, "event_id": ids.new_id("evt"),
                       "timestamp_utc": t, "sequence": seq,
                       "boot_id": f"boot-{stream}",
                       "session_id": f"session-{stream}",
                       "process_id": {"a": 1, "b": 2}[stream],
                       "event": tag, "level": "INFO",
                       "reason_code": tag}) + "\n"


def test_view_ordering_policy():
    ve = viewer()
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        day = "2026-09-24"
        (d / f"events-{day}.jsonl.2").write_text(
            _rec(f"{day}T01:00:00.000Z", 1, "e1"))
        (d / f"events-{day}.jsonl.10").write_text(
            _rec(f"{day}T02:00:00.000Z", 2, "e2"))
        (d / f"events-{day}.jsonl").write_text(
            _rec(f"{day}T04:00:00.000Z", 4, "e4"))
        # A second process's stream interleaves by wall clock.
        (d / f"events-p99-{day}.jsonl").write_text(
            _rec(f"{day}T03:00:00.000Z", 1, "p3", "b")
            + _rec(f"{day}T05:00:00.000Z", 2, "p5", "b"))
        code, out, err = run_viewer(ve, ["--dir", str(d), "--utc"])
        order = [line.split()[-1] for line in out.splitlines()]
        assert order == ["e1", "e2", "p3", "e4", "p5"], order
        code, out, _ = run_viewer(ve, ["--dir", str(d), "--utc", "--last",
                                       "2"])
        assert [line.split()[-1] for line in out.splitlines()] == \
            ["e4", "p5"]
        assert err == ""
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        day = "2026-09-24"
        # Wall clock rolled back inside one stream: sequence governs.
        (d / f"events-{day}.jsonl").write_text(
            _rec(f"{day}T10:00:00.000Z", 1, "s1")
            + _rec(f"{day}T09:00:00.000Z", 2, "s2")
            + _rec(f"{day}T09:30:00.000Z", 3, "s3"))
        code, out, err = run_viewer(ve, ["--dir", str(d), "--utc",
                                         "--last", "1"])
        assert out.split()[-1] == "s3"
        assert "went backwards" in err and "ambiguous" in err
    print("ok  20 view order: sequence within a stream, UTC merge across"
          " streams and rolls (.2/.10/active); clock rollback reported")


def main():
    tests = [test_redacted_export_is_a_typed_allowlist,
             test_roll_cap_keeps_unresolved_evidence,
             test_protection_fails_safe_when_unknown,
             test_emit_after_close_is_refused,
             test_view_ordering_policy]
    for t in tests:
        t()
    print(f"all m02 remediation event tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
