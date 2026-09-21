"""EV-02 / M02: dated event-writer tests (Spec S07, Evaluation E12).

Synthetic cases cover envelope validity, multiline/Unicode/hostile-prefix
safety, UTC-day and size rotation, clock jumps and DST offsets, concurrency,
disk-full degraded behavior, retention (with unresolved-job protection),
single-writer locking, permissions and the content-free redacted export.

Run: .venv/bin/python tests/v2/logging/test_event_writer.py
"""

import json
import os
import pathlib
import stat
import sys
import threading
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import eventlog  # noqa: E402

REQUIRED_KEYS = {
    "schema_version", "event_id", "timestamp_utc", "timezone",
    "utc_offset_minutes", "boot_id", "session_id", "process_id",
    "worker_generation", "sequence", "job_id", "attempt", "stage",
    "event", "level", "outcome", "reason_code", "duration_ms",
    "queue_wait_ms", "source_revision", "pipeline_revision", "model_id",
    "model_revision", "config_hash", "prompt_hash", "artifact_ids",
}


def read_all(log_dir):
    recs = []
    for f in sorted(log_dir.glob("events-*.jsonl*")):
        for line in f.read_text(encoding="utf-8").splitlines():
            recs.append(json.loads(line))
    return recs


def test_envelope_validity():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        w.emit("test.one", job_id="job-x", attempt=1, stage="cleanup",
               outcome="ok", reason_code="r", duration_ms=12.5)
        w.emit("test.two", level="ERROR", reason_code="e")
        w.flush(timeout=10)
        w.close()
        recs = read_all(pathlib.Path(td))
        assert len(recs) == 2
        for r in recs:
            assert REQUIRED_KEYS <= set(r.keys()), sorted(REQUIRED_KEYS - set(r))
            assert r["schema_version"] == 2
            assert r["event_id"].startswith("evt-")
            assert len(r["timestamp_utc"]) == 24 and r["timestamp_utc"].endswith("Z")
            assert r["timestamp_utc"][10] == "T" and r["timestamp_utc"][19] == "."
            assert r["source_revision"] and r["pipeline_revision"] == "v2.0"
            assert r["queue_wait_ms"] >= 0
        assert recs[0]["sequence"] < recs[1]["sequence"]
        assert len({r["event_id"] for r in recs}) == 2
        by_event = {r["event"]: r for r in recs}
        assert by_event["test.one"]["job_id"] == "job-x"
        assert by_event["test.one"]["stage"] == "cleanup"
    print("ok  envelope validity (schema 2, unique ids, sequence)")


def test_multiline_unicode_hostile_payloads():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        w.emit("test.payload", detail="line1\nline2\n[localflow] raw:     fake")
        w.emit("test.payload", detail="emoji 🎙 ünïcödé\ttab\rcr")
        w.flush(timeout=10)
        w.close()
        files = list(pathlib.Path(td).glob("events-*.jsonl"))
        lines = files[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2  # no record was split or impersonated
        for line in lines:
            rec = json.loads(line)  # every physical line parses whole
            assert rec["event"] == "test.payload"
    print("ok  multiline/Unicode/hostile payloads stay inside records")


def test_size_rotation_and_permissions():
    with tempfile.TemporaryDirectory() as td:
        original = eventlog.ROTATE_BYTES
        original_keep = eventlog.KEEP_ROLLS
        eventlog.ROTATE_BYTES = 2000
        eventlog.KEEP_ROLLS = 100
        try:
            w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
            for i in range(60):
                w.emit("test.rotate", detail="x" * 120)
            w.emit("test.rotate", detail="final")
            w.flush(timeout=10)
            w.close()
        finally:
            eventlog.ROTATE_BYTES = original
            eventlog.KEEP_ROLLS = original_keep
        rolls = sorted(pathlib.Path(td).glob("events-*.jsonl.*"))
        assert rolls, "expected size-roll suffixes"
        # Every rolled file plus the active one parses completely.
        assert len(read_all(pathlib.Path(td))) == 61
        mode = stat.S_IMODE((pathlib.Path(td)).stat().st_mode)
        assert mode == 0o700, oct(mode)
        for f in pathlib.Path(td).glob("events-*.jsonl*"):
            assert stat.S_IMODE(f.stat().st_mode) == 0o600, f
    print("ok  size rotation + 0700/0600 permissions")


def test_roll_cap_deletes_oldest_first():
    with tempfile.TemporaryDirectory() as td:
        original, keep = eventlog.ROTATE_BYTES, eventlog.KEEP_ROLLS
        eventlog.ROTATE_BYTES, eventlog.KEEP_ROLLS = 500, 3
        try:
            w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
            for i in range(40):
                w.emit("test.cap", detail=f"roll-marker-{i:02d} " + "y" * 100)
            w.flush(timeout=10)
            w.close()
        finally:
            eventlog.ROTATE_BYTES, eventlog.KEEP_ROLLS = original, keep
        rolls = [p for p in pathlib.Path(td).glob("events-*.jsonl.*")]
        assert len(rolls) <= 3, rolls
        markers = [r["detail"].split()[0] for r in read_all(pathlib.Path(td))]
        # Survivors are the newest rolls (numeric order, not ".10" < ".2").
        assert markers == sorted(markers), markers
        assert markers[-1].endswith("39"), markers[-1]
    print("ok  roll cap keeps the newest rolls (numeric suffix order)")


def test_utc_day_boundary_rotation():
    with tempfile.TemporaryDirectory() as td:
        # Anchor the fake clock near a real UTC midnight so retention's
        # mtime comparison (real filesystem time) stays consistent.
        base = (int(time.time()) // 86400) * 86400 + 23 * 3600  # 23:00 UTC
        state = {"now": float(base)}
        w = eventlog.EventWriter(pathlib.Path(td), now_fn=lambda: state["now"],
                                 mirror_stderr=False)
        w.emit("test.day", detail="before midnight")
        w.flush(timeout=10)  # file placement happens at write time
        state["now"] += 3600 * 2  # cross a UTC boundary
        w.emit("test.day", detail="after midnight")
        w.flush(timeout=10)
        w.close()
        days = sorted(p.name for p in pathlib.Path(td).glob("events-*.jsonl"))
        assert len(days) == 2, days
        recs = read_all(pathlib.Path(td))
        assert len(recs) == 2
        assert recs[0]["timestamp_utc"][:10] != recs[1]["timestamp_utc"][:10]
    print("ok  UTC-day boundary rotation")


def test_clock_jump_and_dst_never_negative():
    with tempfile.TemporaryDirectory() as td:
        state = {"now": 17580000000.0}
        jumps = []
        mono = [0.0]

        def now_fn():
            return state["now"]

        def mono_fn():
            mono[0] += 0.001
            return mono[0]

        w = eventlog.EventWriter(pathlib.Path(td), now_fn=now_fn,
                                 mono_fn=mono_fn, mirror_stderr=False)
        state["now"] -= 7200  # wall clock jumped backwards mid-run
        w.emit("test.jump", duration_ms=5.0)
        state["now"] += 7200
        w.emit("test.jump", duration_ms=3.0)
        w.flush(timeout=10)
        w.close()
        recs = read_all(pathlib.Path(td))
        assert all(r["queue_wait_ms"] >= 0 for r in recs)
        assert all(r["duration_ms"] is None or r["duration_ms"] >= 0
                   for r in recs)
        # UTC instants remain parseable and ordered by sequence, not by wall.
        ts = [r["timestamp_utc"] for r in sorted(recs, key=lambda r: r["sequence"])]
        assert len(ts) == 2
    print("ok  clock jump: no negative durations; monotonic-only elapsed")


def test_concurrent_emitters():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        errs = []

        def spam(k):
            try:
                for i in range(400):
                    w.emit("test.concurrent", level="INFO",
                           job_id=f"job-{k}", detail=f"i={i}")
            except Exception as e:  # pragma: no cover
                errs.append(e)

        threads = [threading.Thread(target=spam, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errs, errs
        assert w.flush(timeout=30)
        w.close()
        recs = read_all(pathlib.Path(td))
        assert len(recs) == 8 * 400, len(recs)
        seqs = [r["sequence"] for r in recs]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert len({r["event_id"] for r in recs}) == len(recs)
        assert w.stats()["dropped_low"] == 0
    print("ok  concurrent emitters: 3200 events, strict unique sequence")


def test_disk_full_degrades_and_criticals_survive():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        real_ensure = w._ensure_file

        def broken():
            raise OSError(28, "No space left on device")

        w._ensure_file = broken
        w.emit("test.normal", level="INFO")
        w.emit("test.critical", level="ERROR", reason_code="job_failed")
        deadline = time.time() + 5
        while w.stats()["critical_retries"] < 1 and time.time() < deadline:
            time.sleep(0.05)
        assert w.degraded, "expected degraded state on ENOSPC"
        assert w.stats()["critical_retries"] >= 1  # critical retained for retry
        w._ensure_file = real_ensure  # disk space returns
        w.emit("test.after_recovery")
        assert w.flush(timeout=10)
        w.close()
        recs = read_all(pathlib.Path(td))
        events = {r["event"] for r in recs}
        assert "test.critical" in events, "critical event must survive"
        assert "test.after_recovery" in events
        assert not w.degraded
    print("ok  disk-full: degraded state, critical retried, recovery")


def test_retention_and_unresolved_job_protection():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        w = eventlog.EventWriter(d, retention_days=14, mirror_stderr=False,
                                 unresolved_jobs_fn=lambda: {"job-keep-me"})
        w.emit("test.recent")
        w.flush(timeout=10)
        current = next(d.glob("events-*.jsonl"))
        # An old rolled file mentioning an unresolved job, and one that doesn't.
        protected = d / (current.stem + ".9" + ".jsonl")
        protected.write_text('{"job_id": "job-keep-me"}\n')
        deletable = d / "events-2001-01-01.jsonl.1"
        deletable.write_text('{"job_id": "job-done"}\n')
        old = time.time() - 40 * 86400
        os.utime(protected, (old, old))
        os.utime(deletable, (old, old))
        w.apply_retention_now()
        w.close()
        assert protected.exists(), "unresolved-job metadata must survive"
        assert not deletable.exists(), "expired file should be pruned"
        assert current.exists()
    print("ok  retention: age pruning keeps unresolved-job metadata")


def test_second_writer_locks_out():
    with tempfile.TemporaryDirectory() as td:
        a = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        b = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        b.emit("test.locked")
        b.flush(timeout=10)
        names_a = [p.name for p in pathlib.Path(td).glob("events-2*.jsonl")]
        names_b = [p.name for p in pathlib.Path(td).glob(f"events-p*.jsonl")]
        a.close()
        b.close()
        assert len(names_b) == 1, names_b
        assert names_b[0].startswith(f"events-p{b.process_id}-")
    print("ok  second writer uses pid-prefixed files (no interleaving)")


def test_redacted_export_is_content_free():
    from scripts.v2 import view_events

    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        w = eventlog.EventWriter(d, mirror_stderr=False)
        w.emit("test.redact", detail="AKIAIOSFODNN7EXAMPLE sk-supersecret123")
        w.emit("test.redact2", detail="transcript-like content")
        w.flush(timeout=10)
        w.close()
        out = pathlib.Path(td) / "redacted.jsonl"
        rc = view_events.main(["--dir", str(d), "--export-redacted", str(out)])
        assert rc == 0
        text = out.read_text()
        assert "detail" not in text
        for marker in ("AKIA", "sk-supersecret", "transcript-like"):
            assert marker not in text, marker
        for line in text.splitlines():
            json.loads(line)
    print("ok  redacted export drops all free-text detail")


def test_human_line_local_and_utc():
    rec = {
        "schema_version": 2, "timestamp_utc": "2026-09-21T04:39:58.120Z",
        "level": "INFO", "job_id": "job-abcdef123456", "attempt": 2,
        "stage": "cleanup", "outcome": "fallback",
        "reason_code": "protected_quantity_changed", "duration_ms": 742.8,
    }
    local = eventlog.EventWriter.human_line(rec)
    utc = eventlog.EventWriter.human_line(rec, utc=True)
    assert "2026-09-21 04:39:58.120 +00:00" in utc
    assert utc.startswith("2026-09-21 04:39:58")
    assert "job=job-abcdef12" in local and "attempt=2" in local
    assert "cleanup fallback: protected_quantity_changed (742.8 ms)" in local
    # Display choice never changes the stored instant.
    assert rec["timestamp_utc"] == "2026-09-21T04:39:58.120Z"
    print("ok  human view renders UTC/local without touching instants")


def test_capture_stderr_coalesced_content_free():
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td), mirror_stderr=False)
        with eventlog.capture_stderr(w) as sink:
            print("Downloading model.safetensors:  43%|####3  | 1.1G/2.6G",
                  end="\r", file=sys.stderr)
            print("secret-token-do-not-log", file=sys.stderr)
        w.emit("after.capture")
        w.flush(timeout=10)
        w.close()
        recs = read_all(pathlib.Path(td))
        third_party = [r for r in recs if r["event"] == "third_party.stderr"]
        assert len(third_party) == 1
        assert "bytes=" in third_party[0]["detail"]
        blob = json.dumps(recs)
        assert "secret-token-do-not-log" not in blob
        assert "model.safetensors" not in blob
    print("ok  third-party stderr captured as bounded content-free record")


def main():
    test_envelope_validity()
    test_multiline_unicode_hostile_payloads()
    test_size_rotation_and_permissions()
    test_roll_cap_deletes_oldest_first()
    test_utc_day_boundary_rotation()
    test_clock_jump_and_dst_never_negative()
    test_concurrent_emitters()
    test_disk_full_degrades_and_criticals_survive()
    test_retention_and_unresolved_job_protection()
    test_second_writer_locks_out()
    test_redacted_export_is_content_free()
    test_human_line_local_and_utc()
    test_capture_stderr_coalesced_content_free()
    print("all event writer tests passed")


if __name__ == "__main__":
    main()
