"""M02 remediation: content-free reproductions of M02-AUDIT-01..20.

Each probe drives the real store/collector/importer/event-writer code
with synthetic content in a temporary directory and reports what it
OBSERVED as booleans and counts — never ids, paths or text. The probes
use only APIs that already existed at the audited commit
(3ae0070d84730f8d750440f51097c4a53ff8bf02), so the same script runs
before and after the repair; where the repair adds the call-site wiring
the app itself performs (AppKit code the cloud cannot import), the probe
follows the new wiring when it exists and the old one otherwise, and
says which it used.

``reproduced: true`` means the defect's failure mechanism was observed.
Probes that depend on AppKit-only code (the app delegate) inspect the
app source with ``ast`` and say so (``kind: static_wiring``).

Usage:
    .venv/bin/python scripts/v2/m02_remediation_repro.py [--output PATH]
Exit code is always 0 (a reproduction is an observation, not a failure).
"""

import argparse
import ast
import errno
import io
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import contextlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from localflow.v2 import eventlog, ids, importer, store as store_mod  # noqa: E402
from localflow.v2 import training  # noqa: E402

DAY = 86400.0
SECRET = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"  # synthetic, matches the scanner


class Clock:
    def __init__(self, t=1_790_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Events:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))

    def named(self, name):
        return [e for e in self.events if e[0] == name]


def env(td, clock=None):
    td = pathlib.Path(td)
    ev = Events()
    st = store_mod.Store(td / "v2.db", backup_dir=td / "backups",
                         now_fn=clock or time.time, emit=ev)
    consent = training.ConsentManager(st, ev)
    col = training.EvidenceCollector(st, ev, consent, lambda: {"p": 1})
    return st, ev, consent, col


def q(st, sql, args=()):
    con = sqlite3.connect(st.db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def start_ctx(col, consent, job_id=None, attempt=1, snapshot=None):
    job_id = job_id or ids.new_id("job")
    kw = dict(captured_at_utc=ids.now_utc_iso(), timezone="UTC",
              utc_offset_minutes=0, attempt=attempt)
    if snapshot is not None:
        kw["consent_snapshot"] = snapshot
    return col.job_started(job_id, ids.new_id("fam"), **kw)


def feed(col, ctx, raw="alpha beta gamma", applied="Alpha beta gamma.",
         audio=True):
    col.bind_current(ctx)
    col.attach_capture_meta(ctx, {"device": "synthetic", "duration_sec": 1.0},
                            16000)
    if audio:
        col.on_audio(ctx, np.linspace(-0.1, 0.1, 1600, dtype=np.float32),
                     16000, {})
    col.on_asr_result(ctx, raw, model_id="asr", model_revision="r",
                      stage_duration_ms=1.0)
    col.on_cleaner_observation({"kind": "cleanup", "input": raw,
                                "system_prompt": "S", "prompt": "P:" + raw,
                                "max_tokens": 8, "output": applied})
    col.on_cleanup_result(ctx, applied)
    col.clear_current()


def live_job_rows(st, job_id):
    arts = q(st, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
             (job_id,))[0][0]
    exs = q(st, "SELECT COUNT(*) FROM training_examples WHERE job_id=? AND"
                " state!='deleted'", (job_id,))[0][0]
    wavs = sum(1 for p in st.artifacts_dir.glob("*.wav"))
    return arts, exs, wavs


# ---------------------------------------------------------------- probes

def p01(td):
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    col.bind_current(ctx)
    col.attach_capture_meta(ctx, {"device": "s"}, 16000)
    st.delete_everywhere("job", ctx.job_id, reason="user_request")
    # Producer resumes after the deletion (late callbacks).
    feed(col, ctx)
    try:
        col.finalize(ctx)
    except Exception:
        pass
    st.sync()
    arts, exs, wavs = live_job_rows(st, ctx.job_id)
    # Second ordering: example finalized, deleted, then a late outcome.
    ctx2 = start_ctx(col, consent)
    feed(col, ctx2)
    col.finalize(ctx2)
    st.sync()
    st.delete_everywhere("example", ctx2.example_id)
    try:
        col.on_insertion(ctx2, True, 5)
    except Exception:
        pass
    st.sync()
    late_revs = q(st, "SELECT COUNT(*) FROM training_revisions WHERE"
                      " example_id=?", (ctx2.example_id,))[0][0]
    st.close()
    return {"reproduced": bool(arts or exs or wavs or late_revs),
            "live_artifacts_after_delete": arts,
            "live_examples_after_delete": exs,
            "wav_files_after_delete": wavs,
            "revisions_on_deleted_example_after_late_outcome": late_revs}


def p02(td):
    st, ev, consent, col = env(td)
    st.write_audio_artifact(job_id="job-x", stage="capture",
                                  samples=np.zeros(160, np.float32),
                                  sample_rate=16000)
    st.sync()
    real_unlink = pathlib.Path.unlink

    def failing(self, *a, **k):
        if self.suffix == ".wav":
            raise PermissionError(errno.EACCES, "injected")
        return real_unlink(self, *a, **k)

    pathlib.Path.unlink = failing
    try:
        res = st.delete_everywhere("job", "job-x")
    finally:
        pathlib.Path.unlink = real_unlink
    file_left = any(st.artifacts_dir.glob("*.wav"))
    pending_reported = bool(res.get("pending_purges")) if isinstance(
        res, dict) else False
    has_intent_table = bool(q(st, "SELECT 1 FROM sqlite_master WHERE"
                                  " name='purge_intents'"))
    st.sweep_orphans(grace_sec=0)
    moved_to_orphans = any((st.artifacts_dir / "orphans").glob("*.wav"))
    still_anywhere = any(st.artifacts_dir.rglob("*.wav"))
    # Retry (the repaired store drains pending purges on reconcile).
    if hasattr(st, "reconcile_purges"):
        st.reconcile_purges()
    after_retry = any(st.artifacts_dir.rglob("*.wav"))
    st.close()
    # Debug copy inventory: the app's transcript-logging copy.
    debug = _debug_copy_probe(td)
    return {"reproduced": bool((file_left and not pending_reported)
                               or moved_to_orphans or after_retry
                               or debug["debug_copy_survives_job_delete"]),
            "file_left_after_failed_unlink": file_left,
            "pending_purge_reported": pending_reported,
            "durable_purge_intent_table": has_intent_table,
            "sweep_moved_deleted_payload_to_orphans": moved_to_orphans,
            "payload_present_before_retry": still_anywhere,
            "payload_present_after_retry": after_retry,
            **debug}


def _debug_copy_probe(td):
    """The app writes a PCM16 transcript-logging copy per dictation. The
    repaired helper names it by job and registers the directory with the
    store's job-scoped deletion; the base app names it by timestamp only."""
    d = pathlib.Path(td) / "debug-audio"
    st, ev, consent, col = env(pathlib.Path(td) / "dbg")
    job_id = ids.new_id("job")
    try:
        from localflow.v2 import debug_audio  # repaired helper
        debug_audio.write_debug_copy(d, job_id, np.zeros(160, np.float32),
                                     16000, keep=5)
        st.register_job_payload_dir(d, debug_audio.job_pattern)
        wiring = "repaired_helper"
    except ImportError:
        # Base: _dump_audio's naming (timestamp + sequence), no job link.
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + "-001"
        store_mod.write_wav_pcm16(d / f"dictation-{stamp}.wav",
                                  np.zeros(160, np.float32), 16000)
        wiring = "base_app_naming"
    st.delete_everywhere("job", job_id)
    survives = any(d.glob("*.wav"))
    st.close()
    return {"debug_copy_wiring": wiring,
            "debug_copy_survives_job_delete": survives}


def p03(td):
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    feed(col, ctx, raw="my key is " + SECRET, applied="My key is " + SECRET)
    detected = bool(training.scan_secrets("x " + SECRET))
    real = st.set_example_state
    st.set_example_state = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("injected fault before quarantine"))
    trace = []
    st._db.set_trace_callback(trace.append)
    try:
        col.finalize(ctx)
    except Exception:
        pass
    st.sync()
    st._db.set_trace_callback(None)
    st.set_example_state = real
    rows = q(st, "SELECT state FROM training_examples WHERE job_id=?",
             (ctx.job_id,))
    ordinary_insert_seen = any(
        "INSERT" in s and "training_examples" in s
        and "quarantined_sensitive" not in s for s in trace)
    states = [r[0] for r in rows]
    st.close()
    return {"reproduced": any(s != "quarantined_sensitive" for s in states)
            or (ordinary_insert_seen and "UPDATE training_examples" in
                " ".join(trace)),
            "scanner_detected_marker": detected,
            "examples": len(states),
            "non_quarantined_examples": sum(
                1 for s in states if s != "quarantined_sensitive")}


def p04(td):
    st, ev, consent, col = env(td)
    aid = st.write_audio_artifact(job_id="job-y", stage="capture",
                                  samples=np.ones(160, np.float32) * 0.1,
                                  sample_rate=16000)
    st.sync()

    def op(db):
        st._purge_artifact(aid)
        raise RuntimeError("injected failure before commit")
    try:
        st.submit(op)
    except RuntimeError:
        pass
    row = q(st, "SELECT purged, content_path FROM artifacts WHERE"
                " artifact_id=?", (aid,))[0]
    live = row[0] == 0 and row[1] is not None
    file_ok = bool(row[1]) and (st.artifacts_dir / row[1]).exists()
    st.close()
    # Process exit after the purge callback but before commit.
    td2 = pathlib.Path(td) / "crash"
    child = f"""
import sys, os, pathlib, numpy as np
sys.path.insert(0, {str(ROOT)!r})
from localflow.v2 import store as s
st = s.Store(pathlib.Path({str(td2)!r}) / 'v2.db')
aid = st.write_audio_artifact(job_id='job-z', stage='capture',
    samples=np.ones(160, np.float32) * 0.1, sample_rate=16000)
st.sync()
def op(db):
    st._purge_artifact(aid)
    os._exit(3)
st.submit(op)
"""
    subprocess.run([sys.executable, "-c", child], timeout=60)
    st2 = store_mod.Store(td2 / "v2.db")
    r2 = q(st2, "SELECT purged, content_path FROM artifacts")[0]
    live2 = r2[0] == 0 and r2[1] is not None
    file2 = bool(r2[1]) and (st2.artifacts_dir / r2[1]).exists()
    st2.close()
    return {"reproduced": (live and not file_ok) or (live2 and not file2),
            "rollback_live_row": live, "rollback_file_present": file_ok,
            "crash_live_row": live2, "crash_file_present": file2}


def p05(td):
    st, ev, consent, col = env(td)
    consent.set("enabled")
    real = store_mod.insert_text_artifact_row

    def faulty(conn, **kw):
        if kw.get("role") == "raw_transcript":
            raise sqlite3.OperationalError("injected raw insert failure")
        return real(conn, **kw)
    store_mod.insert_text_artifact_row = faulty
    try:
        ctx = start_ctx(col, consent)
        feed(col, ctx)
        col.finalize(ctx)
        st.sync()
    finally:
        store_mod.insert_text_artifact_row = real
    raw_row = q(st, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                    " role='raw_transcript'", (ctx.job_id,))[0][0]
    saved = ev.named("training.revision_saved")
    complete_claimed = any(e[2].get("reason_code") == "capture_complete"
                           for e in saved)
    env_ = st.latest_revision(ctx.example_id) if ctx.example_id else None
    dangling = bool(env_ and env_["artifact_ids"].get("source_text")
                    and not raw_row)
    st.close()
    return {"reproduced": bool(complete_claimed and not raw_row) or dangling,
            "raw_artifact_committed": bool(raw_row),
            "completion_event_claimed_complete": complete_claimed,
            "envelope_references_uncommitted_artifact": dangling}


def p06(td):
    st, ev, consent, col = env(td)
    # (a) disabled at capture start (PTT down), enabled before release.
    snap_fn = getattr(consent, "capture_snapshot", None)
    job_id = ids.new_id("job")
    snap = snap_fn() if snap_fn else None
    wiring = "capture_snapshot_at_ptt_down" if snap_fn else "base_job_started_at_release"
    late_cid = consent.set("enabled")
    ctx = start_ctx(col, consent, job_id=job_id, snapshot=snap)
    a_reproduced = ctx.collecting and ctx.consent_revision_id == late_cid
    # (b) state/revision read interleave: a consent write lands between
    # the state read and the revision-id read (if the path reads twice).
    consent.set("enabled")
    real = st.current_consent_id

    def interleaved():
        st.append_consent("paused")
        return real()
    st.current_consent_id = interleaved
    try:
        ctx2 = start_ctx(col, consent)  # the path without a PTT snapshot
    finally:
        st.current_consent_id = real
    rev_state = None
    if ctx2.consent_revision_id:
        rev_state = q(st, "SELECT state FROM consent_revisions WHERE"
                          " consent_revision_id=?",
                      (ctx2.consent_revision_id,))[0][0]
    b_reproduced = ctx2.collecting and rev_state != "enabled"
    st.close()
    return {"reproduced": bool(a_reproduced or b_reproduced),
            "wiring": wiring,
            "later_enable_attached_to_earlier_capture": bool(a_reproduced),
            "collecting_under_non_enabled_revision": bool(b_reproduced)}


def p07(td):
    clock = Clock()
    st, ev, consent, col = env(td, clock)
    aid = st.write_audio_artifact(job_id="job-h", stage="capture",
                                  samples=np.zeros(160, np.float32),
                                  sample_rate=16000)
    st.grant_lease(aid, "history", days=90)
    st.grant_lease(aid, "training", days=30)
    st.upsert_example(job_id="job-h", family_id="fam-h")
    st.sync()
    res = st.prune_training(now=clock.t + 31 * DAY)
    purged = q(st, "SELECT purged FROM artifacts WHERE artifact_id=?",
               (aid,))[0][0]
    live_history = q(st, "SELECT COUNT(*) FROM artifact_leases WHERE"
                         " holder='history' AND revoked_at_utc IS NULL")[0][0]
    st.close()
    return {"reproduced": bool(purged) or not live_history,
            "example_expired": res.get("expired"),
            "artifact_purged_despite_history_lease": bool(purged),
            "history_lease_revoked": not live_history}


def p08(td):
    from localflow.v2 import training_data
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    feed(col, ctx)
    col.finalize(ctx)
    st.sync()
    svc = training_data.TrainingDataService(st)
    real_latest = st.latest_revision
    state = {"annot": None, "done": False}

    def annotate_once():
        if not state["done"]:
            state["done"] = True
            state["annot"] = svc.mark_intended(ctx.example_id, True)

    def latest_then_annotation(ex):
        env_ = real_latest(ex)
        annotate_once()  # a human annotation lands after the read
        return env_
    st.latest_revision = latest_then_annotation
    # Repaired collector: the read happens inside one writer op; the
    # annotation cannot land between read and append — emulate the same
    # human action arriving just before the outcome op runs.
    try:
        col.on_insertion(ctx, True, 12)
    finally:
        st.latest_revision = real_latest
    annotate_once()
    st.sync()
    latest = st.latest_revision(ctx.example_id)
    rows = q(st, "SELECT revision_id, parent_revision_id FROM"
                 " training_revisions WHERE example_id=? ORDER BY rowid",
             (ctx.example_id,))
    chain_ok = all(rows[i][1] == rows[i - 1][0] for i in range(1, len(rows)))
    lost = latest["outcome"].get("correctness") != "correct"
    st.close()
    return {"reproduced": lost or not chain_ok,
            "annotation_lost_in_latest": lost,
            "parent_chain_follows_actual_order": chain_ok,
            "revisions": len(rows)}


def p09(td):
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    job_id = ctx.job_id
    st.create_job(job_id=job_id)
    # The app's automatic-retry handling: the worker reports retried=True.
    job = {"attempt": 1, "ctx": ctx}
    job["attempt"] += 1
    st.bump_job_attempt(job_id)
    wiring = "base_app"
    if hasattr(col, "note_attempt"):
        col.note_attempt(ctx, job["attempt"])  # repaired app wiring
        wiring = "repaired_app_wiring"
    feed(col, ctx)
    col.finalize(ctx)
    st.sync()
    env_ = st.latest_revision(ctx.example_id)
    store_attempt = st.job(job_id)["attempt"]
    # Store-level fence: a late update carrying a stale attempt.
    fenced = None
    try:
        ok = st.update_job_state(job_id, "cancelled", expected_attempt=1)
        fenced = not ok
    except TypeError:
        fenced = None  # no fence API at base
    st.close()
    return {"reproduced": env_["attempt"] != store_attempt,
            "wiring": wiring,
            "envelope_attempt": env_["attempt"],
            "store_attempt": store_attempt,
            "stale_attempt_update_rejected": fenced}


def _log(pairs, extra=0):
    lines = ["[localflow] ready — hold fn to dictate, release to insert text."]
    for i in range(pairs + extra):
        lines += ["[localflow] audio: 3.0s from 'mic', voiced 50%, trailing"
                  " silence 0.5s, overflows 0",
                  f"[localflow] raw:     synthetic utterance {i}",
                  f"[localflow] cleaned: Synthetic utterance {i}.",
                  "[localflow] timing: stt 0.2s, cleanup 0.4s",
                  "[localflow] inserted 20 chars"]
    return "\n".join(lines) + "\n"


def p10(td):
    td = pathlib.Path(td)
    st, ev, consent, col = env(td)
    imp = importer.LegacyImporter(st, td / "bk")
    log = td / "LocalFlow.log"
    log.write_text(_log(3))
    real = st.import_legacy_pair
    n = {"c": 0}

    def crash_after_first(*a, **k):
        n["c"] += 1
        if n["c"] > 1:
            raise RuntimeError("simulated crash")
        return real(*a, **k)
    st.import_legacy_pair = crash_after_first
    try:
        imp.import_log(log)
    except RuntimeError:
        pass
    st.import_legacy_pair = real
    st.sync()
    # Source grows (one more closed record) before the rerun.
    log.write_text(_log(3, extra=1))
    imp.import_log(log)
    st.sync()
    raws = [r[0] for r in q(st, "SELECT content_text FROM artifacts WHERE"
                                " role='raw_transcript' AND stage='legacy_log'")]
    dup = len(raws) - len(set(raws))
    st.close()
    return {"reproduced": dup > 0, "raw_pairs": len(raws),
            "expected_raw_pairs": 4, "duplicated_pairs": dup}


def _stats(path, rows):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE dictations(id INTEGER PRIMARY KEY, ts REAL,"
                " duration_sec REAL, raw_text TEXT, cleaned_text TEXT,"
                " raw_words INTEGER, cleaned_words INTEGER, fixed_words"
                " INTEGER, wpm REAL, app_name TEXT, app_bundle TEXT,"
                " kind TEXT)")
    con.executemany("INSERT INTO dictations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows)
    con.commit()
    con.close()


def p11(td):
    td = pathlib.Path(td)
    st, ev, consent, col = env(td)
    imp = importer.LegacyImporter(st, td / "bk")
    _stats(td / "a.db", [(1, 1783199742.8, 1.0, "one", "One.", 1, 1, 0, 1.0,
                          "T", "t", "dictation")])
    _stats(td / "b.db", [(1, 1783299742.8, 2.0, "other", "Other.", 1, 1, 0,
                          2.0, "T", "t", "dictation")])
    imp.import_stats_db(td / "a.db")
    rb = imp.import_stats_db(td / "b.db")
    st.sync()
    rows = q(st, "SELECT COUNT(*) FROM legacy_dictations")[0][0]
    b_marked = rb.get("rows_imported", 0)
    preserved = q(st, "SELECT COUNT(*) FROM artifacts WHERE"
                      " kind='legacy_stats_row_conflict'")[0][0] \
        if rows == 1 else rows - 1
    conflicts_reported = rb.get("rows_conflicted", 0)
    # Fault: the row insert fails; bookkeeping must not claim it.
    td3 = td / "fault"
    st3, *_ = env(td3)
    imp3 = importer.LegacyImporter(st3, td3 / "bk")
    _stats(td3 / "c.db", [(7, 1783199742.8, 1.0, "x", "X.", 1, 1, 0, 1.0,
                           "T", "t", "dictation")])

    def failing(row, sha):
        st3._submit(lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("injected")))
    st3.insert_legacy_dictation = failing
    real_submit_row = getattr(st3, "import_legacy_stats_row", None)
    if real_submit_row:
        st3.import_legacy_stats_row = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("injected row failure"))
    try:
        imp3.import_stats_db(td3 / "c.db")
    except Exception:
        pass
    st3.sync()
    booked = q(st3, "SELECT COUNT(*) FROM imports WHERE source_kind="
                    "'stats_db'")[0][0]
    rows3 = q(st3, "SELECT COUNT(*) FROM legacy_dictations")[0][0]
    st.close()
    st3.close()
    silent = bool(b_marked and not conflicts_reported and not preserved)
    return {"reproduced": bool(silent or (booked and not rows3)),
            "second_source_rows_marked_imported": b_marked,
            "conflicts_reported": conflicts_reported,
            "conflicting_source_row_preserved": bool(preserved),
            "fault_bookkeeping_without_row": bool(booked and not rows3)}


def p12(td):
    td = pathlib.Path(td)
    d = td / "logs"
    d.mkdir()
    rec = {"schema_version": 2, "event_id": ids.new_id("evt"),
           "timestamp_utc": "2026-09-24T12:00:00.000Z", "event": "x.y",
           "level": "INFO", "detail": "MARKER_DETAIL",
           "context": "MARKER_TOP", "error": {"msg": ["MARKER_NESTED"]},
           "reason_code": "ok_code", "job_id": ids.new_id("job")}
    (d / "events-2026-09-24.jsonl").write_text(json.dumps(rec) + "\n")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "view_events", ROOT / "scripts" / "v2" / "view_events.py")
    ve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ve)
    out = td / "red.jsonl"
    with contextlib.redirect_stdout(io.StringIO()):
        ve.main(["--dir", str(d), "--export-redacted", str(out)])
    body = out.read_text()
    leaked = sum(m in body for m in ("MARKER_TOP", "MARKER_NESTED",
                                     "MARKER_DETAIL"))
    kept_safe = "ok_code" in body and rec["job_id"] in body
    return {"reproduced": leaked > 0, "markers_leaked": leaked,
            "safe_identifiers_kept": kept_safe}


def p13(td):
    td = pathlib.Path(td)
    job = ids.new_id("job")
    old = eventlog.ROTATE_BYTES
    eventlog.ROTATE_BYTES = 2048
    try:
        w = eventlog.EventWriter(td / "logs", mirror_stderr=False,
                                 unresolved_jobs_fn=lambda: {job})
        w.emit("capture.started", job_id=job)
        w.flush()
        for i in range(400):
            w.emit("filler.event", reason_code=f"r{i}")
        w.flush()
        w.close()
    finally:
        eventlog.ROTATE_BYTES = old
    files = list((td / "logs").glob("events-*"))
    found = any(job in p.read_text() for p in files)
    return {"reproduced": not found, "files": len(files),
            "unresolved_job_record_survives": found}


def p14(td):
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    feed(col, ctx)
    col.finalize(ctx)
    st.sync()
    env_ = st.latest_revision(ctx.example_id)
    audio = st.artifact(env_["artifact_ids"]["original_audio"])
    path = st.artifacts_dir / audio["content_path"]
    deep = {"deep": True} if "deep" in st.verify.__code__.co_varnames else {}
    data = bytearray(path.read_bytes())
    data[-4:] = b"\x00\x00\x80\x7f"
    path.write_bytes(bytes(data))
    mutated_ok = st.verify(**deep)["ok"]
    path.unlink()
    missing_ok = st.verify(**deep)["ok"]
    # Wrong-job reference.
    other = st.write_text_artifact(job_id="job-other", stage="asr",
                                   role="raw_transcript", text="o")
    st.sync()

    def rewire(db):
        row = db.execute("SELECT revision_id, envelope_json FROM"
                         " training_revisions WHERE example_id=? ORDER BY"
                         " rowid DESC LIMIT 1", (ctx.example_id,)).fetchone()
        e = json.loads(row[1])
        e["artifact_ids"]["source_text"] = other
        db.execute("UPDATE training_revisions SET envelope_json=? WHERE"
                   " revision_id=?", (json.dumps(e), row[0]))
    st.submit(rewire)
    wrong_job_ok = not any("another job" in i
                           for i in st.verify(**deep)["issues"])
    # Legitimate tombstone.
    st2, *_ = env(pathlib.Path(td) / "t")
    c2 = training.ConsentManager(st2, lambda *a, **k: None)
    c2.set("enabled")
    col2 = training.EvidenceCollector(st2, lambda *a, **k: None, c2,
                                      lambda: {})
    ctx2 = start_ctx(col2, c2)
    feed(col2, ctx2)
    col2.finalize(ctx2)
    st2.sync()
    st2.delete_everywhere("example", ctx2.example_id)
    tomb_ok = st2.verify(**deep)["ok"]
    st.close()
    st2.close()
    return {"reproduced": mutated_ok or missing_ok or wrong_job_ok
            or not tomb_ok,
            "deep_mode_available": bool(deep),
            "mutated_audio_reported_ok": mutated_ok,
            "missing_audio_reported_ok": missing_ok,
            "wrong_job_reference_reported_ok": wrong_job_ok,
            "valid_tombstone_reported_ok": tomb_ok}


def p15(td):
    st, ev, consent, col = env(td)
    gate = threading.Event()
    st.submit(lambda db: gate.wait(10), wait=False)
    st.append_consent("enabled", note="queued behind the stalled op")
    closer = threading.Thread(target=lambda: st.close(timeout=0.3))
    closer.start()
    time.sleep(0.05)
    late_accepted = True
    try:
        st.append_consent("paused", note="submitted while closing")
    except RuntimeError:
        late_accepted = False
    closer.join()
    worker_alive_at_close = st._thread.is_alive()
    gate.set()
    time.sleep(0.5)
    con = sqlite3.connect(st.db_path)
    n = con.execute("SELECT COUNT(*) FROM consent_revisions").fetchone()[0]
    con.close()
    # Event writer: emit after close.
    w = eventlog.EventWriter(pathlib.Path(td) / "logs", mirror_stderr=False)
    w.close()
    accepted_after_close = w.emit("late.event") is True
    app_src = (ROOT / "localflow" / "app.py").read_text()
    tree = ast.parse(app_src)
    term = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                and n.name == "applicationWillTerminate_")
    body = ast.unparse(term)
    closes_store = "store.close" in body or "_shutdown_persistence" in body
    return {"reproduced": late_accepted or accepted_after_close
            or not closes_store or n < 1,
            "kind": "dynamic_store_writer + static_wiring(app)",
            "store_accepted_submission_while_closing": late_accepted,
            "writer_alive_when_close_returned": worker_alive_at_close,
            "queued_ops_committed_after_release": n,
            "event_emit_accepted_after_close": accepted_after_close,
            "app_terminate_drains_store_and_events": closes_store}


def p16(td):
    clock = Clock()
    st, ev, consent, col = env(td, clock)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    feed(col, ctx)
    col.finalize(ctx)
    st.sync()
    col.mark_last_correct()
    st.sync()
    state = q(st, "SELECT state FROM training_examples WHERE example_id=?",
              (ctx.example_id,))[0][0]
    prov = st.latest_revision(ctx.example_id)["outcome"].get(
        "correctness_provenance")
    st.prune_training(now=clock.t + 31 * DAY)
    st.prune(now=clock.t + 31 * DAY)
    after = q(st, "SELECT state FROM training_examples WHERE example_id=?",
              (ctx.example_id,))[0][0]
    audio_live = q(st, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                       " role='original_audio' AND purged=0",
                   (ctx.job_id,))[0][0]
    st.close()
    return {"reproduced": after == "expired" or not audio_live
            or prov != "user_explicit_intended_writing",
            "state_after_mark": state, "provenance": prov,
            "state_after_31_days": after,
            "reviewed_audio_retained_after_31_days": bool(audio_live)}


def p17(td):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bench", ROOT / "scripts" / "v2" / "benchmark_m02.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    counted = {}

    orig_write = store_mod.Store.write_text_artifact

    def counting(self, **kw):
        counted[kw.get("role")] = counted.get(kw.get("role"), 0) + 1
        return orig_write(self, **kw)
    store_mod.Store.write_text_artifact = counting
    refused = False
    try:
        res = bench.bench_collection_paired(n=3)
    except Exception as e:
        res = {"error": type(e).__name__}
        refused = True
    finally:
        store_mod.Store.write_text_artifact = orig_write
    prompts = sum(v for k, v in counted.items()
                  if k and k.startswith("cleanup_input"))
    ok_claim = (res.get("enabled") or {}).get("consistency_ok")
    return {"reproduced": bool(ok_claim) and prompts == 0,
            "prompt_artifacts_written": prompts,
            "proposal_artifacts_written": counted.get("cleanup_proposal", 0),
            "report_claims_consistency_ok": ok_claim,
            "benchmark_refused": refused,
            "populations_reported": "populations" in (res.get("enabled")
                                                      or {})}


def p18(td):
    td = pathlib.Path(td)
    st, ev, consent, col = env(td)
    consent.set("enabled")
    ctx = start_ctx(col, consent)
    feed(col, ctx)
    col.finalize(ctx)
    st.sync()
    st.close()
    con = sqlite3.connect(td / "v2.db")
    con.execute("DROP TABLE training_examples")
    con.commit()
    con.close()
    refused_missing_core = False
    try:
        s2 = store_mod.Store(td / "v2.db", backup_dir=td / "backups")
        v = s2.verify()["ok"]
        s2.close()
    except RuntimeError:
        refused_missing_core = True
        v = None
    backups = len(list((td / "backups").glob("*"))) if (
        td / "backups").exists() else 0
    # Newer, unsupported version.
    td2 = td / "future"
    s3 = store_mod.Store(td2 / "v2.db")
    s3.close()
    con = sqlite3.connect(td2 / "v2.db")
    con.execute("UPDATE schema_meta SET value='999' WHERE key='schema_version'")
    con.commit()
    con.close()
    refused_future = False
    try:
        store_mod.Store(td2 / "v2.db").close()
    except RuntimeError:
        refused_future = True
    # Missing index.
    td3 = td / "idx"
    s4 = store_mod.Store(td3 / "v2.db")
    s4.close()
    con = sqlite3.connect(td3 / "v2.db")
    con.execute("DROP INDEX idx_artifacts_job")
    con.commit()
    con.close()
    store_mod.Store(td3 / "v2.db").close()
    con = sqlite3.connect(td3 / "v2.db")
    idx_back = bool(con.execute("SELECT 1 FROM sqlite_master WHERE"
                                " name='idx_artifacts_job'").fetchone())
    con.close()
    return {"reproduced": (not refused_missing_core) or (not refused_future)
            or not idx_back,
            "missing_core_with_dependents_refused": refused_missing_core,
            "reopened_verify_ok": v,
            "backup_copies": backups,
            "future_version_refused": refused_future,
            "missing_index_restored": idx_back}


def p19(td):
    cases = {"null": None, "malformed": "abc", "negative": -5,
             "huge": 10 ** 9, "zero": 0}
    from localflow import config as cfg_mod
    validator = getattr(cfg_mod, "retention_policy", None)
    out = {}
    for name, val in cases.items():
        cfg = dict(cfg_mod.DEFAULTS)
        cfg["retention_transcript_days"] = val
        try:
            if validator:
                days, problems = validator(cfg)
                v = days["transcript"]
                out[name] = {"startup_error": None, "effective": v,
                             "rejected": bool(problems)}
            else:
                v = int(cfg.get("retention_transcript_days", 30))  # app.py
                out[name] = {"startup_error": None, "effective": v,
                             "rejected": False}
        except Exception as e:
            out[name] = {"startup_error": type(e).__name__}
    # Destructive interpretation: negative days purge a fresh transcript.
    clock = Clock()
    st, ev, consent, col = env(td, clock)
    eff = out["negative"].get("effective")
    if eff is not None:
        st.retention_days["transcript"] = eff
    st.write_text_artifact(job_id=None, stage="x", role="r", text="fresh")
    st.sync()
    res = st.prune(now=clock.t + 1)
    st.close()
    destructive = res["purged"] > 0
    errors = [k for k, v in out.items() if v.get("startup_error")]
    return {"reproduced": bool(errors) or destructive,
            "startup_errors": errors, "negative_purged_fresh": destructive,
            "cases": out}


def p20(td):
    d = pathlib.Path(td) / "logs"
    d.mkdir()

    def rec(t, seq, tag):
        return json.dumps({"schema_version": 2, "event_id": ids.new_id("evt"),
                           "timestamp_utc": t, "sequence": seq,
                           "boot_id": "boot-a", "session_id": "session-a",
                           "process_id": 1, "event": tag,
                           "level": "INFO"}) + "\n"
    day = "2026-09-24"
    # roll .2 is older than roll .10; the active file is newest.
    (d / f"events-{day}.jsonl.2").write_text(
        rec(f"{day}T01:00:00.000Z", 1, "oldest"))
    (d / f"events-{day}.jsonl.10").write_text(
        rec(f"{day}T02:00:00.000Z", 2, "middle"))
    (d / f"events-{day}.jsonl").write_text(
        rec(f"{day}T03:00:00.000Z", 3, "newest"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "view_events", ROOT / "scripts" / "v2" / "view_events.py")
    ve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ve)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ve.main(["--dir", str(d), "--last", "1", "--utc"])
    shown = buf.getvalue()
    return {"reproduced": "03:00:00" not in shown,
            "last_1_is_newest": "03:00:00" in shown}


PROBES = [("M02-AUDIT-%02d" % i, f) for i, f in enumerate(
    [p01, p02, p03, p04, p05, p06, p07, p08, p09, p10,
     p11, p12, p13, p14, p15, p16, p17, p18, p19, p20], start=1)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--only", help="comma-separated finding numbers")
    args = ap.parse_args(argv)
    only = {int(x) for x in args.only.split(",")} if args.only else None
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--",
                                 "localflow", "scripts"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    report = {"schema_version": 1, "tool": "m02_remediation_repro",
              "evaluated_utc": ids.now_utc_iso(),
              "code_sha": sha, "working_tree_modified": dirty,
              "python": sys.version.split()[0],
              "numpy": np.__version__, "sqlite": sqlite3.sqlite_version,
              "findings": {}}
    for name, fn in PROBES:
        if only and int(name[-2:]) not in only:
            continue
        with tempfile.TemporaryDirectory() as td:
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    report["findings"][name] = fn(td)
            except Exception as e:
                report["findings"][name] = {
                    "reproduced": None,
                    "probe_error": f"{type(e).__name__}"}
    out = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
