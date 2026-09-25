"""M02 remediation, independent-review round: regressions for the defects
an adversarial reviewer found in the first remediation pass.

R1 one deleted job no longer fails the whole note-mining pass;
R2 verify() never mistakes missing-reason keys for references;
R3 a deleted example cannot be excluded/restored back to life;
R4 the consent cache follows the committed store, not the request;
R5 delete_everywhere reports honestly even when close() races it;
R6 envelope keys containing '.' or '[' do not break publication;
R7 losing an additive v11 table is repaired (barrier backfilled), and
   pre-v11 deletions get their barrier on upgrade;
R8 a transform of text from a deleted job is detached, not refused.

Synthetic data and temp directories only.

Run: .venv/bin/python tests/v2/storage/test_m02_review_round.py
"""

import json
import pathlib
import sqlite3
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from localflow.v2 import ids, learning, training, training_data  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402


def new_store(td, **kw):
    return store_mod.Store(pathlib.Path(td) / "v2.db", **kw)


def q(db_path, sql, args=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def test_r1_mining_skips_deleted_job():
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        ls = learning.LearningService(s, emit=lambda *a, **k: None,
                                      vocabulary=VocabularyStore(s))
        job_a, fam_a = s.create_job()
        raw = s.write_text_artifact(job_id=job_a, stage="asr",
                                    role="raw_transcript",
                                    text="hello there",
                                    retention_class="training")
        ex_a = s.upsert_example(job_id=job_a, family_id=fam_a)
        s.append_revision(ex_a, {"job_id": job_a, "missing_reasons": {},
                                 "artifact_ids": {"source_text": raw}})
        job_b, _ = s.create_job()
        s.write_text_artifact(job_id=job_b, stage="cleanup",
                              role="applied_output",
                              text="ship the clod branch",
                              retention_class="history")
        s.sync()
        s.delete_everywhere("job", job_b, reason="moved_to_scratchpad")
        now = "2026-09-23T10:00:00.000Z"

        def note_op(conn):
            conn.execute("INSERT INTO notes(note_id, created_at_utc,"
                         " updated_at_utc) VALUES('note-y', ?, ?)",
                         (now, now))
            spans = [[0, 4, "dictated", job_b], [4, 6, "dictated", job_a]]
            for rid, origin, text in (
                    ("nrev-1", "dictated", "ship the clod branch hello there"),
                    ("nrev-2", "typed",
                     "ship the Claude branch hello there")):
                conn.execute(
                    "INSERT INTO note_revisions(revision_id, note_id, origin,"
                    " content_text, content_sha256, spans_json,"
                    " created_at_utc) VALUES(?,?,?,?,?,?,?)",
                    (rid, "note-y", origin, text, "0" * 64,
                     json.dumps(spans), now))
            conn.execute("INSERT INTO note_evidence_links(note_id,"
                         " example_id, job_id, first_seen_utc)"
                         " VALUES('note-y',?,?,?)", (ex_a, job_a, now))
        s.submit(note_op)
        for _ in range(2):
            assert ls.mine_observation_candidates() == 0
        # Nothing was minted for the deleted job.
        assert q(s.db_path, "SELECT COUNT(*) FROM artifacts WHERE job_id=?"
                 " AND purged=0", (job_b,))[0][0] == 0
        assert q(s.db_path, "SELECT COUNT(*) FROM learning_candidates WHERE"
                 " job_id=?", (job_b,))[0][0] == 0
        s.close()
    print("ok  R1 note mining skips a deleted job; the pass never fails")


def test_r2_missing_reason_keys_are_not_references():
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        job, fam = s.create_job()
        env = {"job_id": job,
               "artifact_ids": {"original_audio": "art-" + "a" * 32},
               "audio_preparation": {"artifact_id": "art-" + "b" * 32,
                                     "decode_ranges": [[0, 10]]},
               "cleanup": {"v2": {"context_artifact_id": "art-" + "c" * 32}},
               "missing_reasons": {"skill_registry_artifact_id": "x"}}
        ack = s.publish_example(job_id=job, family_id=fam, envelope=env)
        assert sorted(ack["uncommitted"]) == [
            "artifact_ids.original_audio", "audio_preparation.artifact_id",
            "cleanup.v2.context_artifact_id"], ack
        v = s.verify()
        assert v["ok"], v["issues"]
        s.close()
    print("ok  R2 missing-reason keys never read as references; incomplete"
          " captures verify clean")


def test_r3_deleted_example_stays_deleted():
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        job, fam = s.create_job()
        ex = s.publish_example(job_id=job, family_id=fam,
                               envelope={"artifact_ids": {}})["example_id"]
        assert not s.job_deleted(job)
        s.delete_everywhere("example", ex)
        assert s.job_deleted(job) and not s.job_deleted(None)
        svc = training_data.TrainingDataService(s)
        assert svc.exclude(ex, True) == "deleted"
        assert svc.exclude(ex, False) == "deleted"
        assert q(s.db_path, "SELECT state FROM training_examples") == \
            [("deleted",)]
        assert s.verify()["ok"]
        s.close()
    print("ok  R3 exclude/restore never resurrects a deleted example")


def test_r4_consent_cache_follows_committed_store():
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        events = []
        cm = training.ConsentManager(
            s, lambda e, level="INFO", **k: events.append((e, level, k)))
        cm.snapshot_now("startup")
        s.submit(lambda db: db.execute(
            "CREATE TRIGGER t BEFORE INSERT ON consent_revisions BEGIN"
            " SELECT RAISE(ABORT, 'io'); END"))
        assert cm.set("enabled") is None
        snap = cm.capture_snapshot()
        assert snap.state == "disabled" and not snap.collecting
        assert events[-1][1] == "ERROR" and \
            events[-1][2]["outcome"] == "not_recorded"
        s.submit(lambda db: db.execute("DROP TRIGGER t"))
        cid = cm.set("enabled")
        assert cid and cm.capture_snapshot().revision_id == cid
        s.close()
    print("ok  R4 a failed consent write never leaves a phantom enabled"
          " snapshot")


def test_r5_delete_reports_while_close_races():
    with tempfile.TemporaryDirectory() as td:
        emitted = []
        s = new_store(td, emit=lambda e, **k: emitted.append((e, k)))
        job, _ = s.create_job()
        s.write_audio_artifact(job_id=job, stage="capture",
                               samples=__import__("numpy").zeros(16),
                               sample_rate=16000)  # a file -> an intent
        s.sync()
        gate = threading.Event()
        s.submit(lambda db: gate.wait(10), wait=False)
        result = {}
        t = threading.Thread(target=lambda: result.update(
            s.delete_everywhere("job", job)))
        t.start()
        closer = threading.Thread(target=lambda: s.close(timeout=10))
        # delete is queued behind the gate; close starts, then release.
        import time
        time.sleep(0.2)
        closer.start()
        time.sleep(0.2)
        gate.set()
        t.join(10)
        closer.join(10)
        assert result.get("complete") is True, result
        assert result["payload_files"] == 1 and result["pending_purges"] == 0
        assert not list((pathlib.Path(td) / "v2-artifacts").glob("*.wav"))
        assert any(e == "training.deleted_everywhere" for e, _ in emitted)
        assert q(pathlib.Path(td) / "v2.db", "SELECT COUNT(*) FROM"
                 " job_deletions")[0][0] == 1
    print("ok  R5 delete_everywhere accepted before close reports and emits"
          " after the drain")


def test_r6_keys_with_dots_and_brackets():
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        job, fam = s.create_job()
        env = {"artifact_ids": {},
               "odd": {"v2.x": {"a[0]": {"artifact_id": "art-" + "d" * 32}}}}
        ack = s.publish_example(job_id=job, family_id=fam, envelope=env)
        assert ack["uncommitted"] == ["odd.v2.x.a[0].artifact_id"], ack
        stored = s.latest_revision(ack["example_id"])
        assert stored["odd"]["v2.x"]["a[0]"]["artifact_id"] is None
        s.close()
    print("ok  R6 keys containing '.'/'[' publish and null correctly")


def test_r7_additive_tables_repaired_and_backfilled():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        s = new_store(td)
        job, fam = s.create_job()
        s.write_audio_artifact(job_id=job, stage="capture",
                               samples=__import__("numpy").zeros(16),
                               sample_rate=16000)
        s.sync()
        s.delete_everywhere("job", job)
        s.close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("DROP TABLE job_deletions")
        con.execute("DROP TABLE purge_intents")
        con.commit()
        con.close()
        s = new_store(td, backup_dir=td / "b")  # repaired, not refused
        assert q(td / "v2.db", "SELECT job_id, reason FROM job_deletions") \
            == [(job, "pre_v11_deletion")]
        assert list((td / "b").glob("v2-pre-repair-*.db"))
        # The rebuilt barrier works.
        s.write_text_artifact(job_id=job, stage="asr", role="r", text="late")
        s.sync()
        assert q(td / "v2.db", "SELECT COUNT(*) FROM artifacts WHERE"
                 " purged=0")[0][0] == 0
        s.close()
    # Upgrade from v10: a deletion made before v11 gets its barrier.
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        s = new_store(td)
        job, fam = s.create_job()
        ex = s.publish_example(job_id=job, family_id=fam,
                               envelope={"artifact_ids": {}})["example_id"]
        s.delete_everywhere("example", ex)
        s.close()
        con = sqlite3.connect(td / "v2.db")
        con.execute("DROP TABLE job_deletions")
        con.execute("UPDATE schema_meta SET value='10' WHERE"
                    " key='schema_version'")
        con.commit()
        con.close()
        new_store(td).close()
        assert q(td / "v2.db", "SELECT job_id FROM job_deletions") == [(job,)]
    print("ok  R7 lost additive tables repaired with backfilled barrier;"
          " pre-v11 deletions barred on upgrade")


def test_r8_transform_of_deleted_job_text_is_detached():
    from localflow.v2 import transforms as tf
    from localflow.v2.transforms_store import TransformStore
    with tempfile.TemporaryDirectory() as td:
        s = new_store(td)
        ts = TransformStore(s)
        job, _ = s.create_job()
        s.delete_everywhere("job", job, reason="moved_to_scratchpad")
        d = tf.TransformDefinition(transform_id="t", name="T", mode="polish")
        job_t = tf.job_for_definition(d, "note text", source_kind="note",
                                      parent_job_id=job)
        cand = ts.record_candidate(
            tf.TransformResult(job=job_t, output="Note text.",
                               path="applied"),
            source_artifact_text="note text",
            output_artifact_text="Note text.")
        assert cand
        rows = q(s.db_path, "SELECT job_id FROM artifacts WHERE purged=0")
        assert rows == [(None,), (None,)], rows
        s.close()
    print("ok  R8 transform of a deleted job's text: candidate recorded,"
          " artifacts detached from the deleted job")


def main():
    tests = [test_r1_mining_skips_deleted_job,
             test_r2_missing_reason_keys_are_not_references,
             test_r3_deleted_example_stays_deleted,
             test_r4_consent_cache_follows_committed_store,
             test_r5_delete_reports_while_close_races,
             test_r6_keys_with_dots_and_brackets,
             test_r7_additive_tables_repaired_and_backfilled,
             test_r8_transform_of_deleted_job_text_is_detached]
    for t in tests:
        t()
    print(f"all m02 review-round tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
