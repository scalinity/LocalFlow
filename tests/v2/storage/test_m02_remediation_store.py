"""M02 remediation regressions: store deletion barrier, durable purge
intents, lease independence, deep verification, lifecycle, schema repair
classification, retention config validation (M02-AUDIT-01/02/04/07/09/14/
15/18/19).

Synthetic content, temporary directories and disposable databases only.
Oracles inspect file bytes, rows and relationships independently of the
code under test (raw sqlite3 reads, filesystem listings).

Run: .venv/bin/python tests/v2/storage/test_m02_remediation_store.py
"""

import errno
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from localflow import config as config_mod  # noqa: E402
from localflow.v2 import ids  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402

DAY = 86400.0
T0 = 1_790_000_000.0


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def new_store(td, **kw):
    return store_mod.Store(pathlib.Path(td) / "v2.db", **kw)


def rows(db_path, sql, args=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def audio(st, job_id, value=0.25, n=160):
    aid = st.write_audio_artifact(job_id=job_id, stage="capture",
                                  samples=np.full(n, value, np.float32),
                                  sample_rate=16000)
    st.sync()
    return aid


def wavs(st):
    return sorted(p.name for p in st.artifacts_dir.rglob("*.wav"))


# ---- M02-AUDIT-01: the deletion barrier ---------------------------------

def test_deletion_barrier_refuses_every_late_write():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job, fam = st.create_job()
        a1 = audio(st, job)
        res = st.delete_everywhere("job", job)
        assert res["complete"] and res["purged_artifacts"] == 1
        assert rows(st.db_path, "SELECT reason FROM job_deletions WHERE"
                                " job_id=?", (job,)) == [("user_request",)]
        # Every late producer write is refused inside its op.
        st.write_text_artifact(job_id=job, stage="asr",
                               role="raw_transcript", text="late text")
        late_audio = st.write_audio_artifact(
            job_id=job, stage="capture", samples=np.ones(16, np.float32),
            sample_rate=16000)
        st.upsert_example(job_id=job, family_id=fam)
        try:
            st.publish_example(job_id=job, family_id=fam,
                               envelope={"artifact_ids": {}})
            raise AssertionError("publish after delete must be refused")
        except RuntimeError as e:
            assert "JobDeletedError" in str(e)
        try:
            st.grant_lease(a1, "history", days=5)
            st.sync()
        except RuntimeError:
            pass
        st.sync()
        live = rows(st.db_path, "SELECT COUNT(*) FROM artifacts WHERE"
                                " job_id=? AND purged=0", (job,))[0][0]
        exs = rows(st.db_path, "SELECT COUNT(*) FROM training_examples"
                               " WHERE job_id=?", (job,))[0][0]
        leases = rows(st.db_path, "SELECT COUNT(*) FROM artifact_leases"
                                  " WHERE revoked_at_utc IS NULL")[0][0]
        assert (live, exs, leases) == (0, 0, 0), (live, exs, leases)
        # The staged late audio file was removed, not left as an orphan.
        assert f"{late_audio}.wav" not in wavs(st) and wavs(st) == []
        # Refusal messages are content-free (no ids).
        assert all(job not in e for e in st.last_errors)
        st.close()
    print("ok  01 deletion barrier: late artifact/audio/example/publish/"
          "lease writes refused; staged file removed")


def test_deleted_example_is_final():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job, fam = st.create_job()
        ack = st.publish_example(job_id=job, family_id=fam,
                                 envelope={"job_id": job, "artifact_ids": {}})
        ex = ack["example_id"]
        st.delete_everywhere("example", ex)
        st.set_example_state(ex, "quarantined_sensitive")
        st.append_revision(ex, {"outcome": {"insertion": "posted"}})
        st.sync()
        try:
            st.update_latest_revision(ex, lambda env: env)
            raise AssertionError("expected refusal")
        except RuntimeError:
            pass
        assert rows(st.db_path, "SELECT state FROM training_examples"
                                " WHERE example_id=?", (ex,)) == [("deleted",)]
        assert rows(st.db_path, "SELECT COUNT(*) FROM training_revisions"
                                " WHERE example_id=?", (ex,))[0][0] == 0
        st.close()
    print("ok  01 deleted example: no state resurrection, no late revision")


def test_reason_is_a_code_not_free_text():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job, _ = st.create_job()
        audio(st, job)
        st.delete_everywhere("job", job, reason="Because my SSN is 123")
        reasons = {r[0] for r in rows(st.db_path, "SELECT reason FROM"
                                      " deletion_tombstones")}
        reasons |= {r[0] for r in rows(st.db_path, "SELECT reason FROM"
                                       " job_deletions")}
        assert reasons == {"unspecified"}, reasons
        st.close()
    print("ok  01 tombstone/deletion reasons are codes, never caller text")


# ---- M02-AUDIT-02/04: durable purge intents -----------------------------

def test_failed_unlink_stays_pending_then_retries():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job, _ = st.create_job()
        aid = audio(st, job)
        name = f"{aid}.wav"
        real = pathlib.Path.unlink

        def failing(self, *a, **k):
            if self.name == name:
                raise PermissionError(errno.EACCES, "injected")
            return real(self, *a, **k)
        pathlib.Path.unlink = failing
        try:
            res = st.delete_everywhere("job", job)
            # Honest: the row is purged but the file is pending.
            assert res == {"purged_artifacts": 1, "payload_files": 1,
                           "pending_purges": 1, "complete": False}, res
            assert name in wavs(st)
            row = rows(st.db_path, "SELECT attempts, last_error,"
                                   " completed_at_utc FROM purge_intents")[0]
            assert row == (1, "EACCES", None), row
            # The sweep never parks deletion work in orphans/.
            assert st.sweep_orphans(grace_sec=0) == []
            assert not (st.artifacts_dir / "orphans" / name).exists()
            v = st.verify()
            assert not v["ok"] and v["pending_purges"] == 1
            assert v["orphan_files"] == []
        finally:
            pathlib.Path.unlink = real
        assert st.reconcile_purges() == 0
        assert wavs(st) == []
        assert st.verify()["ok"]
        st.close()
    print("ok  02 failed unlink: pending (EACCES) not complete; sweep never"
          " orphans it; retry removes bytes")


def test_pending_intent_finishes_at_next_open():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        aid = audio(st, "job-p")
        real = pathlib.Path.unlink
        pathlib.Path.unlink = lambda self, *a, **k: (_ for _ in ()).throw(
            PermissionError(errno.EPERM, "injected"))
        try:
            st.delete_everywhere("job", "job-p")
        finally:
            pathlib.Path.unlink = real
        st.close()
        assert wavs(st) == [f"{aid}.wav"]
        st2 = new_store(td)  # the open drains pending intents first
        assert wavs(st2) == []
        assert rows(st2.db_path, "SELECT COUNT(*) FROM purge_intents WHERE"
                                 " completed_at_utc IS NULL")[0][0] == 0
        st2.close()
    print("ok  02 a pending purge completes at the next open")


def test_previously_orphaned_payload_of_deleted_artifact_removed():
    """A pre-remediation sweep may have moved a purged artifact's leftover
    into orphans/; the intent for that managed name removes it there."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        aid = audio(st, "job-o")
        name = f"{aid}.wav"
        (st.artifacts_dir / "orphans").mkdir()
        (st.artifacts_dir / name).rename(st.artifacts_dir / "orphans" / name)
        res = st.delete_everywhere("job", "job-o")
        assert res["complete"] and wavs(st) == []
        st.close()
    print("ok  02 deletion also removes the same managed file from orphans/")


def test_registered_job_dir_copies_deleted_and_others_kept():
    from localflow.v2 import debug_audio
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        dbg = pathlib.Path(td) / "LocalFlow-audio"
        mine, other = ids.new_id("job"), ids.new_id("job")
        p_mine = debug_audio.write_debug_copy(dbg, mine, np.zeros(8), 16000,
                                              seq=1)
        p_other = debug_audio.write_debug_copy(dbg, other, np.zeros(8),
                                               16000, seq=2)
        legacy = dbg / "dictation-20260101-000000-001.wav"  # owner unknown
        store_mod.write_wav_pcm16(legacy, np.zeros(8), 16000)
        st.register_job_payload_dir(dbg, debug_audio.job_pattern)
        journal = pathlib.Path(td) / "v2-journal"
        journal.mkdir()
        (journal / f"job-{mine}.wav").write_bytes(b"RIFF")
        (journal / f"job-{mine}.blk").write_bytes(b"blk")
        (journal / f"job-{other}.wav").write_bytes(b"RIFF")
        st.register_job_payload_dir(journal, lambda j: f"job-{j}.*")
        res = st.delete_everywhere("job", mine)
        assert res["complete"] and res["payload_files"] == 3, res
        assert not p_mine.exists() and p_other.exists() and legacy.exists()
        assert sorted(p.name for p in journal.iterdir()) == \
            [f"job-{other}.wav"]
        # The debug copy is a PCM16 derivative with 0600 permissions.
        assert (p_other.stat().st_mode & 0o777) == 0o600
        st.close()
    print("ok  02 job-scoped debug copy + recovery journal deleted with the"
          " job; other jobs' and unknown-owner files untouched")


def test_rollback_after_purge_keeps_payload():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        aid = audio(st, "job-r", value=0.5)
        before = (st.artifacts_dir / f"{aid}.wav").read_bytes()

        def op(db):
            st._purge_artifact(aid)
            raise RuntimeError("injected failure before commit")
        try:
            st.submit(op)
        except RuntimeError:
            pass
        row = rows(st.db_path, "SELECT purged, content_path FROM artifacts")
        assert row == [(0, f"{aid}.wav")]
        assert (st.artifacts_dir / f"{aid}.wav").read_bytes() == before
        assert rows(st.db_path, "SELECT COUNT(*) FROM purge_intents")[0][0] \
            == 0
        assert np.allclose(st.artifact_payload(aid, verify=True), 0.5)
        st.close()
    print("ok  04 rollback after purge: live row, intact bytes, no intent")


def _crash_child(td, when):
    return f"""
import sys, os, pathlib, numpy as np
sys.path.insert(0, {str(ROOT)!r})
from localflow.v2 import store as s
st = s.Store(pathlib.Path({str(td)!r}) / 'v2.db')
aid = st.write_audio_artifact(job_id='job-c', stage='capture',
    samples=np.ones(160, np.float32) * 0.1, sample_rate=16000)
st.sync()
if {when!r} == 'before_commit':
    def op(db):
        st._purge_artifact(aid)
        os._exit(3)
    st.submit(op)
else:
    # after commit, before the unlink
    st._drain_purge_intents = lambda: os._exit(4)
    st.delete_everywhere('job', 'job-c')
"""


def test_process_exit_around_the_purge_commit():
    for when, expect_live in (("before_commit", True),
                              ("after_commit", False)):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([sys.executable, "-c", _crash_child(td, when)],
                           timeout=60)
            st = new_store(td)  # reopen: pending intents drain
            (purged, path), = rows(st.db_path, "SELECT purged, content_path"
                                              " FROM artifacts")
            files = wavs(st)
            if expect_live:
                assert purged == 0 and files == [path], (purged, files)
            else:
                assert purged == 1 and path is None and files == [], files
                assert rows(st.db_path, "SELECT COUNT(*) FROM purge_intents"
                            " WHERE completed_at_utc IS NULL")[0][0] == 0
            assert st.verify(deep=True)["ok"]
            st.close()
    print("ok  04 process exit before commit keeps a live row + bytes; after"
          " commit the next open finishes the deletion")


# ---- M02-AUDIT-07: independent retention interests ----------------------

def _leased(st, job, holders):
    aid = audio(st, job)
    for holder, days in holders:
        st.grant_lease(aid, holder, days=days)
    st.upsert_example(job_id=job, family_id="fam-" + job)
    st.sync()
    return aid


def test_training_expiry_respects_other_interests():
    cases = [
        ("history90", [("history", 90), ("training", 30)], False),
        ("recovery60", [("recovery", 60), ("training", 30)], False),
        ("training_only", [("training", 30)], True),
        ("history_expired", [("history", 7), ("training", 30)], True),
    ]
    for name, holders, purged_expected in cases:
        with tempfile.TemporaryDirectory() as td:
            clock = Clock()
            st = new_store(td, now_fn=clock)
            aid = _leased(st, "job-" + name, holders)
            res = st.prune_training(now=T0 + 31 * DAY)
            assert res["expired"] == 1
            purged = rows(st.db_path, "SELECT purged FROM artifacts")[0][0]
            assert bool(purged) == purged_expected, (name, purged)
            live = {h for (h,) in rows(
                st.db_path, "SELECT holder FROM artifact_leases WHERE"
                " revoked_at_utc IS NULL")}
            assert "training" not in live
            for holder, days in holders:
                if holder != "training" and days > 31:
                    assert holder in live
            assert (f"{aid}.wav" in wavs(st)) == (not purged_expected)
            # The surviving interest then expires on its own schedule.
            if not purged_expected:
                st.prune(now=T0 + 120 * DAY)
                assert wavs(st) == []
            st.close()
    print("ok  07 training expiry revokes only the training interest;"
          " history/recovery keep the payload until they expire")


def test_pin_and_delete_precedence():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td, now_fn=Clock())
        aid = _leased(st, "job-pin", [("training", None), ("history", 7)])
        assert st.prune_training(now=T0 + 400 * DAY)["expired"] == 0
        st.prune(now=T0 + 400 * DAY)
        assert f"{aid}.wav" in wavs(st)
        res = st.delete_everywhere("job", "job-pin")
        assert res["complete"] and wavs(st) == []
        assert rows(st.db_path, "SELECT COUNT(*) FROM artifact_leases WHERE"
                                " revoked_at_utc IS NULL")[0][0] == 0
        st.close()
    print("ok  07 pin survives expiry; delete-everywhere overrides the pin")


# ---- M02-AUDIT-09: attempt fence ----------------------------------------

def test_expected_attempt_fence():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job, _ = st.create_job(state="transcribing")
        assert st.update_job_state(job, "failed_recoverable")
        st.bump_job_attempt(job)
        assert st.update_job_state(job, "queued", retry=True,
                                   expected_attempt=2)
        # A late writer still on attempt 1 cannot settle attempt 2.
        assert not st.update_job_state(job, "cancelled", expected_attempt=1)
        assert st.job(job)["state"] == "queued"
        assert st.update_job_state(job, "transcribing", expected_attempt=2)
        # Unfenced calls keep the historical semantics.
        assert st.update_job_state(job, "cleaning")
        st.close()
    print("ok  09 expected_attempt fences stale-attempt transitions;"
          " unfenced semantics unchanged")


# ---- M02-AUDIT-14: verification depth -----------------------------------

def _graph(st, job="job-g"):
    st.create_job(job_id=job)
    aid = audio(st, job)
    raw = st.write_text_artifact(job_id=job, stage="asr",
                                 role="raw_transcript", text="alpha")
    prompt = st.write_text_artifact(job_id=job, stage="cleanup",
                                    role="cleanup_input_cleanup",
                                    text="P:alpha", kind="model_input")
    st.sync()
    env = {"job_id": job, "artifact_ids": {"original_audio": aid,
                                           "source_text": raw},
           "cleanup": {"passes": [{"prompt_artifact_id": prompt}]},
           "missing_reasons": {}}
    ack = st.publish_example(job_id=job, family_id="fam", envelope=env)
    assert ack["complete"], ack
    return ack["example_id"], aid, raw, prompt


def test_deep_verify_detects_payload_and_relationship_damage():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        ex, aid, raw, prompt = _graph(st)
        assert st.verify(deep=True)["ok"]
        p = st.artifacts_dir / f"{aid}.wav"
        good = p.read_bytes()
        p.write_bytes(good[:-4] + b"\x00\x00\x80\x7f")
        assert st.verify()["ok"]  # structural mode never reads bytes
        v = st.verify(deep=True)
        assert not v["ok"] and any("hash mismatch" in i for i in v["issues"])
        try:
            st.artifact_payload(aid, verify=True)
            raise AssertionError("verify=True must refuse damaged bytes")
        except ValueError:
            pass
        p.unlink()
        assert any("payload file missing" in i
                   for i in st.verify(deep=True)["issues"])
        p.write_bytes(good)
        assert st.verify(deep=True)["ok"]
        # A nested reference repointed at another job's artifact.
        other = st.write_text_artifact(job_id="job-other", stage="asr",
                                       role="raw_transcript", text="o")
        st.sync()

        def rewire(db):
            rid, payload = db.execute(
                "SELECT revision_id, envelope_json FROM training_revisions"
                " WHERE example_id=?", (ex,)).fetchone()
            env = json.loads(payload)
            env["cleanup"]["passes"][0]["prompt_artifact_id"] = other
            db.execute("UPDATE training_revisions SET envelope_json=? WHERE"
                       " revision_id=?", (json.dumps(env), rid))
        st.submit(rewire)
        assert any("owned by another job" in i
                   for i in st.verify()["issues"])
        st.close()
    print("ok  14 deep verify: mutated/missing WAV and nested wrong-job"
          " reference reported; artifact_payload(verify=True) refuses")


def test_verify_revision_chain_and_tombstones():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        ex, *_ = _graph(st)
        st.update_latest_revision(ex, lambda e: dict(e, note=1))
        assert st.verify(deep=True)["ok"]
        st.submit(lambda db: db.execute(
            "UPDATE training_examples SET latest_revision_id='rev-x'"))
        assert any("latest pointer" in i for i in st.verify()["issues"])
        st.close()
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        ex, *_ = _graph(st)
        st.delete_everywhere("example", ex)
        v = st.verify(deep=True)
        assert v["ok"], v  # a valid tombstone is not corruption
        st.close()
    print("ok  14 revision chain/pointer checked; valid tombstone accepted")


# ---- M02-AUDIT-15: lifecycle ------------------------------------------

def test_close_admission_and_drain():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        gate = threading.Event()
        st.submit(lambda db: gate.wait(10), wait=False)
        st.append_consent("enabled", note="queued behind a stalled op")
        status = {}
        closer = threading.Thread(
            target=lambda: status.update(st.close(timeout=0.3)))
        closer.start()
        time.sleep(0.1)
        try:
            st.append_consent("paused")
            raise AssertionError("admission must be closed while closing")
        except RuntimeError as e:
            assert "closing" in str(e) or "closed" in str(e)
        closer.join()
        assert status == {"drained": False, "pending_ops": 2,
                          "writer_alive": True}, status
        gate.set()
        st._thread.join(5)
        # Accepted work was never dropped: the queued op committed.
        assert rows(st.db_path, "SELECT COUNT(*) FROM consent_revisions"
                    )[0][0] == 1
        try:
            st.sync()
            raise AssertionError("closed store must refuse")
        except RuntimeError:
            pass
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        for i in range(50):
            st.append_consent("enabled", note=str(i))
        assert st.close(timeout=10) == {"drained": True, "pending_ops": 0,
                                        "writer_alive": False}
        assert rows(st.db_path, "SELECT COUNT(*) FROM consent_revisions"
                    )[0][0] == 50
    print("ok  15 close: admission closed first, accepted ops drained or"
          " honestly reported pending, stalled writer never closed under")


def test_caller_timeout_is_not_cancellation():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        gate = threading.Event()
        st.submit(lambda db: gate.wait(10), wait=False)
        job, fam = "job-t", "fam-t"
        try:
            st.publish_example(job_id=job, family_id=fam, example_id="ex-t",
                               envelope={"artifact_ids": {}}, timeout=0.2)
            raise AssertionError("expected caller timeout")
        except TimeoutError:
            pass
        gate.set()
        st.sync()
        # The op still committed; its pre-allocated id identifies it.
        assert rows(st.db_path, "SELECT example_id FROM training_examples"
                    ) == [("ex-t",)]
        st.close()
    print("ok  15 a caller timeout does not cancel: the queued publish"
          " commits later under its pre-allocated id")


# ---- M02-AUDIT-18: schema repair classification --------------------------

def test_missing_core_table_with_dependents_refused_with_backup():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        st = new_store(td)
        _graph(st)
        st.close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("DROP TABLE training_examples")
        con.commit()
        con.close()
        try:
            new_store(td, backup_dir=td / "backups")
            raise AssertionError("missing core table must be refused")
        except RuntimeError as e:
            assert "training_examples" in str(e) and "corrupt" in str(e)
        backups = list((td / "backups").glob("v2-pre-repair-*.db"))
        assert len(backups) == 1
        assert rows(backups[0], "SELECT COUNT(*) FROM training_revisions"
                    )[0][0] == 1
        # Nothing was recreated in the original.
        assert not rows(td / "v2.db", "SELECT 1 FROM sqlite_master WHERE"
                                      " name='training_examples'")
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        new_store(td).close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("DROP TABLE vocabulary_meta")  # additive, no dependents
        con.execute("DROP INDEX idx_artifacts_job")
        con.commit()
        con.close()
        st = new_store(td)
        names = {r[0] for r in rows(td / "v2.db", "SELECT name FROM"
                                    " sqlite_master")}
        assert {"vocabulary_meta", "idx_artifacts_job"} <= names
        st.close()
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        new_store(td).close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("UPDATE schema_meta SET value='99' WHERE"
                    " key='schema_version'")
        con.commit()
        con.close()
        try:
            new_store(td)
            raise AssertionError("newer schema must be refused")
        except RuntimeError as e:
            assert "newer" in str(e)
    print("ok  18 populated missing core table refused (backup kept);"
          " additive table/index repaired; newer schema refused")


def test_migration_from_v10_adds_remediation_tables():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        st = new_store(td)
        st.close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("DROP TABLE job_deletions")
        con.execute("DROP TABLE purge_intents")
        con.execute("UPDATE schema_meta SET value='10' WHERE"
                    " key='schema_version'")
        con.commit()
        con.close()
        st = new_store(td, backup_dir=td / "b")
        assert list((td / "b").glob("v2-pre-migrate-*.db"))
        names = {r[0] for r in rows(td / "v2.db", "SELECT name FROM"
                                    " sqlite_master WHERE type='table'")}
        assert {"job_deletions", "purge_intents"} <= names
        assert rows(td / "v2.db", "SELECT value FROM schema_meta WHERE"
                    " key='schema_version'") == [("11",)]
        st.close()
    print("ok  18 v10 -> v11 additive migration with pre-migration backup")


# ---- M02-AUDIT-19: retention configuration -------------------------------

def test_retention_config_validation():
    table = [(None, "not_a_number"), ("30", "not_a_number"),
             ("abc", "not_a_number"), (True, "not_a_number"),
             (0, "out_of_range"), (-5, "out_of_range"),
             (10 ** 9, "out_of_range"), (2.5, "not_an_integer"),
             (float("nan"), "not_an_integer"), (45, None), (45.0, None)]
    for value, reason in table:
        cfg = dict(config_mod.DEFAULTS, retention_transcript_days=value)
        days, problems = config_mod.retention_policy(cfg)
        if reason:
            assert problems == [("retention_transcript_days", reason)], \
                (value, problems)
            assert days["transcript"] == 30
        else:
            assert problems == [] and days["transcript"] == 45
    days, problems = config_mod.retention_policy({})
    assert problems == [] and days == {
        "transcript": 30, "audio_success": 7, "audio_failed": 30,
        "metadata": 14, "training_buffer": 30, "usage": 365}
    ev, p = config_mod.event_retention_policy({"events_cap_mib": -1})
    assert ev["events_cap_mib"] == 100 and p == [("events_cap_mib",
                                                  "out_of_range")]
    # A rejected value never produces a destructive prune.
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td, now_fn=Clock())
        days, _ = config_mod.retention_policy(
            {"retention_transcript_days": -5})
        st.retention_days = days
        st.write_text_artifact(job_id=None, stage="x", role="r", text="fresh")
        st.sync()
        assert st.prune(now=T0 + DAY)["purged"] == 0
        # The upper bound is representable as an expiry instant.
        aid = st.write_text_artifact(job_id=None, stage="x", role="r2",
                                     text="t")
        st.grant_lease(aid, "history", days=36500)
        st.sync()
        assert not st.last_errors
        st.close()
    assert config_mod.validate_retention_value("training_buffer_days", 0) \
        is None
    assert config_mod.validate_retention_value("retention_usage_days", 60) \
        == 60
    print("ok  19 retention values validated (null/malformed/zero/negative/"
          "huge/fractional rejected -> default + reported); no destructive"
          " prune")


def main():
    tests = [
        test_deletion_barrier_refuses_every_late_write,
        test_deleted_example_is_final,
        test_reason_is_a_code_not_free_text,
        test_failed_unlink_stays_pending_then_retries,
        test_pending_intent_finishes_at_next_open,
        test_previously_orphaned_payload_of_deleted_artifact_removed,
        test_registered_job_dir_copies_deleted_and_others_kept,
        test_rollback_after_purge_keeps_payload,
        test_process_exit_around_the_purge_commit,
        test_training_expiry_respects_other_interests,
        test_pin_and_delete_precedence,
        test_expected_attempt_fence,
        test_deep_verify_detects_payload_and_relationship_damage,
        test_verify_revision_chain_and_tombstones,
        test_close_admission_and_drain,
        test_caller_timeout_is_not_cancellation,
        test_missing_core_table_with_dependents_refused_with_backup,
        test_migration_from_v10_adds_remediation_tables,
        test_retention_config_validation,
    ]
    for t in tests:
        t()
    print(f"all m02 remediation store tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
