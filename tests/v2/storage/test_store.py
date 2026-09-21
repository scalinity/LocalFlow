"""EV-03 / M02: persistent store tests (Spec S08, Evaluation E12/E13).

Synthetic cases cover migration idempotence and torn-schema repair, the
single-writer discipline under concurrent submissions, the job state
machine's idempotence/stale-discard/terminal-finality rules, lossless
float32 audio artifacts, lease-gated retention, training-buffer expiry with
pinning, delete-everywhere tombstones, orphan sweeping and consistency
verification.

Run: .venv/bin/python tests/v2/storage/test_store.py
"""

import json
import pathlib
import sqlite3
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import ids  # noqa: E402


def new_store(td, **kw):
    return store_mod.Store(pathlib.Path(td) / "v2.db", **kw)


def test_migration_idempotent_and_backup():
    with tempfile.TemporaryDirectory() as td:
        backups = pathlib.Path(td) / "backups"
        st = new_store(td, backup_dir=backups)
        st.close()
        for _ in range(3):
            st = new_store(td, backup_dir=backups)
            st.close()
        db = pathlib.Path(td) / "v2.db"
        con = sqlite3.connect(db)
        version = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        con.close()
        assert version == str(max(store_mod._MIGRATIONS))
        assert {"jobs", "artifacts", "training_examples", "dictations"} <= tables
    print("ok  migration idempotent (schema v%s, compat view present)" % version)


def test_torn_schema_repaired():
    # Lost table at current version: repair re-creates it idempotently.
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        st.close()
        con = sqlite3.connect(db)
        con.execute("DROP TABLE training_examples")
        con.commit()
        con.close()
        st = store_mod.Store(db)
        assert st.verify()["ok"]
        st.close()
    # Malformed core table (present but wrong shape): refuse loudly.
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO schema_meta VALUES('schema_version','1')")
        con.execute("CREATE TABLE jobs(job_id TEXT)")
        con.commit()
        con.close()
        try:
            store_mod.Store(db)
            raise AssertionError("expected corruption refusal")
        except RuntimeError as e:
            assert "corrupt" in str(e)
    print("ok  lost table repaired; malformed core table blocks")


def test_concurrent_writes_single_writer():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        errs = []

        def spam(k):
            try:
                for i in range(150):
                    st.write_text_artifact(
                        job_id=None, stage="bench", role="row",
                        text=f"thread-{k}-{i}", retention_class="history")
            except Exception as e:
                errs.append(e)

        threads = [threading.Thread(target=spam, args=(k,)) for k in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        st.sync()
        assert not errs, errs
        assert st.artifact_count() == 4 * 150
        assert not list(st.last_errors)
        st.close()
    print("ok  concurrent submissions: 600 rows, one writer, no errors")


def test_job_state_machine():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job_id, fam = st.create_job(captured_at_utc="2026-09-21T10:00:00.000Z")
        for state in ("queued", "transcribing", "cleaning", "ready_to_insert",
                      "insertion_posted"):
            assert st.update_job_state(job_id, state)
        assert st.update_job_state(job_id, "insertion_posted") is True  # same-state no-op
        assert st.update_job_state(job_id, "cleaning") is False  # regression
        st.close()
    print("ok  job state machine basics")


def test_job_state_guards():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job_id, _ = st.create_job()
        st.update_job_state(job_id, "cleaning")
        assert st.update_job_state(job_id, "capturing") is False  # stale discard
        assert st.update_job_state(job_id, "cancelled", reason="user")
        assert st.update_job_state(job_id, "insertion_unverified") is False  # terminal final
        job = st.job(job_id)
        assert job["state"] == "cancelled" and job["state_reason"] == "user"
        assert st.update_job_state(job_id, "cancelled") is True  # idempotent
        st.close()
    print("ok  stale discard + exactly-one terminal outcome")


def test_audio_artifact_lossless():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job_id, _ = st.create_job()
        rng = np.random.default_rng(7)
        audio = (rng.random(16000 * 3) * 2 - 1).astype(np.float32)
        aid = st.write_audio_artifact(job_id=job_id, stage="capture",
                                      samples=audio, sample_rate=16000)
        st.sync()
        art = st.artifact(aid)
        assert art["kind"] == "audio_wav_f32" and not art["purged"]
        meta = json.loads(art["meta_json"])
        assert meta["sample_count"] == 48000 and meta["sample_rate"] == 16000
        assert meta["dtype"] == "float32" and meta["channels"] == 1
        back = st.artifact_payload(aid)
        assert isinstance(back, np.ndarray) and back.dtype == np.float32
        assert np.array_equal(back, audio), "payload must round-trip losslessly"
        st.close()
    print("ok  float32 WAV artifact round-trips bit-exact")


def test_history_expiry_respects_training_lease():
    """M02-AC06 part 1: a 7-day history expiry cannot remove content a
    visible 30-day training lease pins."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        st.retention_days = {"transcript": 30, "audio_success": 7,
                             "audio_failed": 30, "metadata": 14,
                             "training_buffer": 30}
        job_id, _ = st.create_job()
        st.update_job_state(job_id, "insertion_unverified")
        audio = np.zeros(1600, dtype=np.float32)
        aid = st.write_audio_artifact(job_id=job_id, stage="capture",
                                      samples=audio, sample_rate=16000,
                                      retention_class="training")
        st.grant_lease(aid, "history", days=7)
        st.grant_lease(aid, "training", days=30)
        st.sync()
        r = st.prune(now=time.time() + 10 * 86400)  # past history expiry
        assert r["kept_by_lease"] >= 1 and r["purged"] == 0
        assert st.artifact_payload(aid) is not None
        r2 = st.prune(now=time.time() + 31 * 86400)  # past the training lease
        assert st.artifact_payload(aid) is None
        assert st.artifact(aid)["purged"] == 1
        st.close()
    print("ok  history expiry keeps training-leased content (AC06)")


def test_delete_everywhere():
    """M02-AC06 part 2: delete-everywhere revokes every lease, purges every
    managed copy, leaves only content-free tombstones."""
    from localflow.v2 import training

    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        emit_calls = []
        collector = training.EvidenceCollector(
            st, lambda *a, **k: emit_calls.append((a, k)),
            training.ConsentManager(st, lambda *a, **k: None),
            lambda: {"bench": True})
        collector.consent.set("enabled")
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(), timezone="UTC",
            utc_offset_minutes=0)
        collector.on_audio(ctx, np.zeros(1600, dtype=np.float32), 16000, {})
        collector.on_asr_result(ctx, "secret free text", model_id="m",
                                model_revision=None, stage_duration_ms=1.0)
        collector.on_cleaner_observation(
            {"kind": "cleanup", "prompt": "p", "input": "i", "output": "o",
             "max_tokens": 8})
        collector.on_cleanup_result(ctx, "Secret free text.")
        ex_id = collector.finalize(ctx)
        st.sync()
        job_row = st.example_for_job(ctx.job_id)
        result = st.delete_everywhere("example", ex_id)
        assert result["purged_artifacts"] >= 3
        assert st.artifact_payload(ctx.audio_artifact) is None
        assert st.artifact_payload(ctx.raw_artifact) is None
        env = st.latest_revision(ex_id)
        assert env is None  # revision payload removed
        assert st.example_for_job(ctx.job_id)[1] == "deleted"
        tomb_kinds = {t[1] for t in st.tombstones()}
        assert {"example", "artifact"} <= tomb_kinds
        for t in st.tombstones():
            for field in t:
                assert "secret free text" not in str(field)
        st.close()
    print("ok  delete-everywhere purges payloads, tombstones content-free")


def test_training_buffer_expiry_and_pin():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        st.retention_days["training_buffer"] = 30
        job_id, _ = st.create_job()
        st.update_job_state(job_id, "insertion_unverified")
        aid = st.write_text_artifact(job_id=job_id, stage="cleanup",
                                     role="applied_output", text="x",
                                     retention_class="training")
        ex = st.upsert_example(job_id=job_id, family_id="fam-1")
        st.append_revision(ex, {"example_id": ex, "artifact_ids":
                                {"applied_output": aid}})
        st.grant_lease(aid, "training", days=30)  # unpinned: buffer lease
        st.sync()
        # Backdate the example creation past the buffer window.
        con = sqlite3.connect(st.db_path)
        con.execute(
            "UPDATE training_examples SET created_at_utc=? WHERE example_id=?",
            ("2026-01-01T00:00:00.000Z", ex))
        con.commit()
        con.close()
        r = st.prune_training()
        assert r["expired"] == 1
        assert st.artifact_payload(aid) is None
        # A pinned (no-expiry) training lease survives the same window.
        job2, _ = st.create_job()
        st.update_job_state(job2, "insertion_unverified")
        aid2 = st.write_text_artifact(job_id=job2, stage="cleanup",
                                      role="applied_output", text="y",
                                      retention_class="training")
        ex2 = st.upsert_example(job_id=job2, family_id="fam-2")
        st.append_revision(ex2, {"example_id": ex2, "artifact_ids":
                                 {"applied_output": aid2}})
        st.grant_lease(aid2, "training", days=None)  # pinned
        con = sqlite3.connect(st.db_path)
        con.execute(
            "UPDATE training_examples SET created_at_utc=? WHERE example_id=?",
            ("2026-01-01T00:00:00.000Z", ex2))
        con.commit()
        con.close()
        r2 = st.prune_training()
        assert r2["expired"] == 0
        assert st.artifact_payload(aid2) is not None
        st.close()
    print("ok  training buffer expiry: unpinned evicted, pinned survives")


def test_orphan_sweep_respects_grace():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        fresh = st.artifacts_dir / "art-fresh.wav"
        stale = st.artifacts_dir / "art-stale.wav"
        store_mod.write_wav_f32(fresh, np.zeros(16, dtype=np.float32), 16000)
        store_mod.write_wav_f32(stale, np.zeros(16, dtype=np.float32), 16000)
        old = time.time() - 7200
        import os

        os.utime(stale, (old, old))
        v = st.verify()
        assert set(v["orphan_files"]) == {"art-fresh.wav", "art-stale.wav"}
        assert st.sweep_orphans(grace_sec=3600) == ["art-stale.wav"]
        assert (st.artifacts_dir / "orphans" / "art-stale.wav").exists()
        assert fresh.exists()
        v2 = st.verify()
        assert v2["orphan_files"] == ["art-fresh.wav"]
        st.close()
    print("ok  orphan payload sweep honors in-flight grace period")


def test_verify_flags_dangling_references():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        job_id, _ = st.create_job()
        ex = st.upsert_example(job_id=job_id, family_id="fam")
        st.append_revision(ex, {"example_id": ex, "artifact_ids": {
            "applied_output": "art-does-not-exist"}})
        st.sync()
        v = st.verify()
        assert not v["ok"]
        assert any("art-does-not-exist" in i for i in v["issues"])
        # With a missing-reason the same envelope is consistent.
        con = sqlite3.connect(st.db_path)
        con.execute("DELETE FROM training_revisions")
        con.commit()
        con.close()
        st.append_revision(ex, {"example_id": ex, "artifact_ids": {
            "applied_output": "art-does-not-exist"},
            "missing_reasons": {"applied_output": "source_deleted"}})
        st.sync()
        assert st.verify()["ok"]
        st.close()
    print("ok  verify flags dangling artifacts without missing-reasons")


def test_prune_never_purges_legacy_imports():
    """Review C1/CA1-C1: retention must not destroy the lossless legacy
    import (Spec S08) — only delete-everywhere removes legacy content."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        for i in range(3):
            st.write_text_artifact(
                job_id=None, stage="legacy_log", role="raw_transcript",
                text=f"legacy pair {i}", kind="legacy_text",
                retention_class="legacy")
        st.sync()
        r = st.prune(now=time.time() + 3650 * 86400)  # ten years out
        assert r["purged"] == 0
        con = sqlite3.connect(st.db_path)
        n = con.execute("SELECT COUNT(*) FROM artifacts WHERE"
                        " purged=1").fetchone()[0]
        con.close()
        assert n == 0
        st.close()
    print("ok  prune never purges legacy-class artifacts")


def test_unresolved_job_ids_real_query():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        j1, _ = st.create_job()
        j2, _ = st.create_job()
        j3, _ = st.create_job()
        st.update_job_state(j1, "transcribing")
        st.update_job_state(j2, "insertion_unverified")
        st.update_job_state(j3, "cancelled")
        st.sync()
        unresolved = st.unresolved_job_ids()
        assert unresolved == {j1}, unresolved
        st.close()
    print("ok  unresolved_job_ids: real SQL, unresolved jobs only")


def test_migration_v2_adds_indexes():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)  # fresh store applies v1 + v2
        st.close()
        con = sqlite3.connect(db)
        version = con.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        con.close()
        assert version == "2"
        assert {"idx_artifact_leases_artifact", "idx_artifacts_job",
                "idx_training_revisions_example",
                "idx_imports_kind"} <= idx
        # A v1-era store upgrades in place.
        db2 = pathlib.Path(td) / "old.db"
        st2 = store_mod.Store(db2)
        st2.close()
        con = sqlite3.connect(db2)
        con.execute("UPDATE schema_meta SET value='1'"
                    " WHERE key='schema_version'")
        con.execute("DROP INDEX idx_artifact_leases_artifact")
        con.commit()
        con.close()
        st3 = store_mod.Store(db2)
        st3.close()
        con = sqlite3.connect(db2)
        idx2 = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        con.close()
        assert "idx_artifact_leases_artifact" in idx2
    print("ok  migration v2 adds hot-path indexes (fresh + upgrade)")


def test_op_failure_rolls_back_atomically():
    """A store op that fails partway leaves NO partial rows: each op is one
    transaction (the property import_legacy_text/pair rely on for crash
    convergence)."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)

        def torn():
            st._db.execute(
                "INSERT INTO artifacts(artifact_id, job_id, stage, kind,"
                " role, sha256, bytes, meta_json, retention_class,"
                " created_at_utc) VALUES('art-torn', NULL, 'import',"
                " 'legacy_text', 'raw_transcript', 'x', 1, '{}', 'legacy',"
                " '2026-09-21T00:00:00.000Z')")
            raise RuntimeError("torn mid-op")

        st._submit(torn)  # fire-and-forget: error lands in last_errors
        st.sync()
        assert any("torn mid-op" in e for e in st.last_errors)
        con = sqlite3.connect(st.db_path)
        n = con.execute("SELECT COUNT(*) FROM artifacts WHERE"
                        " artifact_id='art-torn'").fetchone()[0]
        con.close()
        assert n == 0, "failed op must roll back completely"
        assert st.verify()["ok"]
        st.close()
    print("ok  failed store op rolls back atomically")


def test_durability_across_close_and_reopen():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        job_id, fam = st.create_job()
        st.update_job_state(job_id, "insertion_unverified")
        aid = st.write_text_artifact(job_id=job_id, stage="cleanup",
                                     role="applied_output", text="persisted",
                                     retention_class="history")
        ex = st.upsert_example(job_id=job_id, family_id=fam)
        st.append_revision(ex, {"example_id": ex})
        st.sync()
        st.close()
        st2 = store_mod.Store(db)
        assert st2.job(job_id)["state"] == "insertion_unverified"
        assert st2.artifact_payload(aid) == "persisted"
        assert st2.latest_revision(ex) is not None
        st2.close()
    print("ok  writes durable across close/reopen")


def test_wav_f32_header_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "x.wav"
        samples = np.array([-1.0, -0.5, 0.0, 0.5, 0.999999], dtype=np.float32)
        store_mod.write_wav_f32(p, samples, 22050)
        back, rate = store_mod.read_wav_f32(p)
        assert rate == 22050 and np.array_equal(back, samples)
    print("ok  WAV float32 header writer/reader")


def main():
    test_migration_idempotent_and_backup()
    test_torn_schema_repaired()
    test_concurrent_writes_single_writer()
    test_job_state_machine()
    test_job_state_guards()
    test_audio_artifact_lossless()
    test_history_expiry_respects_training_lease()
    test_delete_everywhere()
    test_training_buffer_expiry_and_pin()
    test_orphan_sweep_respects_grace()
    test_verify_flags_dangling_references()
    test_prune_never_purges_legacy_imports()
    test_unresolved_job_ids_real_query()
    test_migration_v2_adds_indexes()
    test_op_failure_rolls_back_atomically()
    test_durability_across_close_and_reopen()
    test_wav_f32_header_roundtrip()
    print("all store tests passed")


if __name__ == "__main__":
    main()
