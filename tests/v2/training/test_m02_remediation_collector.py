"""M02 remediation regressions: live evidence publication, consent
boundary, revision atomicity, retry identity, reviewed retention and the
benchmark's population oracle (M02-AUDIT-01/03/05/06/08/09/16/17).

Synthetic content only; deterministic barriers (threading.Event), no
sleeps as the ordering mechanism. Oracles read SQLite and the filesystem
directly.

Run: .venv/bin/python tests/v2/training/test_m02_remediation_collector.py
"""

import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import threading

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from localflow.v2 import ids, store, training, training_data  # noqa: E402

DAY = 86400.0
T0 = 1_790_000_000.0
SECRET = "sk-" + "Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2"  # synthetic; scanner-shaped


class Events:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))

    def named(self, name):
        return [e for e in self.events if e[0] == name]


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def env(td, clock=None):
    td = pathlib.Path(td)
    ev = Events()
    st = store.Store(td / "v2.db", now_fn=clock or __import__("time").time,
                     emit=ev)
    consent = training.ConsentManager(st, ev)
    col = training.EvidenceCollector(st, ev, consent, lambda: {"p": 1})
    return st, ev, consent, col


def q(st, sql, args=()):
    con = sqlite3.connect(st.db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def start(col, snapshot=None, attempt=1):
    return col.job_started(ids.new_id("job"), ids.new_id("fam"),
                           captured_at_utc=ids.now_utc_iso(), timezone="UTC",
                           utc_offset_minutes=0, attempt=attempt,
                           consent_snapshot=snapshot)


def feed(col, ctx, raw="alpha beta", applied="Alpha beta."):
    col.bind_current(ctx)
    col.attach_capture_meta(ctx, {"device": "synthetic"}, 16000)
    col.on_audio(ctx, np.linspace(-0.1, 0.1, 1600, dtype=np.float32),
                 16000, {})
    col.on_asr_result(ctx, raw, model_id="asr", model_revision="r",
                      stage_duration_ms=1.0, worker_generation=1)
    col.on_cleaner_observation({"kind": "cleanup", "input": raw,
                                "system_prompt": "S", "prompt": "P:" + raw,
                                "max_tokens": 8, "output": applied})
    col.on_cleanup_result(ctx, applied)
    col.clear_current()


# ---- M02-AUDIT-01 -------------------------------------------------------

def test_delete_before_finalize_blocks_late_producer():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        col.bind_current(ctx)
        col.attach_capture_meta(ctx, {"device": "s"}, 16000)
        col.on_audio(ctx, np.zeros(160, np.float32), 16000, {})
        st.sync()  # payload staged and committed
        res = st.delete_everywhere("job", ctx.job_id)
        assert res["complete"] and res["purged_artifacts"] == 1
        feed(col, ctx)  # late callbacks
        assert col.finalize(ctx) is None
        st.sync()
        assert q(st, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                     " purged=0", (ctx.job_id,))[0][0] == 0
        assert q(st, "SELECT COUNT(*) FROM training_examples")[0][0] == 0
        assert not list(st.artifacts_dir.glob("*.wav"))
        refused = [e for e in ev.named("training.capture_failed")
                   if e[2].get("outcome") == "publish_refused"]
        assert refused and refused[0][2]["reason_code"] == "job_deleted"
        assert not ev.named("training.revision_saved")
        st.close()
    print("ok  01 delete before finalize: no late artifact/example/file;"
          " publish refused and reported")


def test_late_outcome_after_example_delete_refused():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        feed(col, ctx)
        ex = col.finalize(ctx)
        st.delete_everywhere("example", ex)
        assert col.on_insertion(ctx, True, 10) is None
        assert col.on_observation_closed(ctx, None, None) is None
        st.sync()
        assert q(st, "SELECT COUNT(*) FROM training_revisions")[0][0] == 0
        assert q(st, "SELECT state FROM training_examples") == [("deleted",)]
        st.close()
    print("ok  01 late outcome/observation on a deleted example refused")


# ---- M02-AUDIT-03 -------------------------------------------------------

def test_quarantine_is_the_first_visible_state():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        assert training.scan_secrets("key " + SECRET)  # positive control
        ctx = start(col)
        feed(col, ctx, raw="my key " + SECRET, applied="My key " + SECRET)
        trace = []
        st._db.set_trace_callback(trace.append)
        ex = col.finalize(ctx)
        st.sync()
        st._db.set_trace_callback(None)
        inserts = [s for s in trace if s.startswith("INSERT INTO"
                                                     " training_examples")]
        assert len(inserts) == 1 and "quarantined_sensitive" in inserts[0]
        assert not [s for s in trace if s.startswith(
            "UPDATE training_examples SET state")]
        # Example, revision and pointer are in ONE transaction.
        idx = [i for i, s in enumerate(trace) if s in ("COMMIT", "BEGIN ")
               or s.startswith("BEGIN")]
        ins_i = trace.index(inserts[0])
        rev_i = next(i for i, s in enumerate(trace)
                     if s.startswith("INSERT INTO training_revisions"))
        assert not any(ins_i < i < rev_i for i in idx
                       if trace[i] == "COMMIT"), "split publication"
        assert q(st, "SELECT state FROM training_examples WHERE example_id=?",
                 (ex,)) == [("quarantined_sensitive",)]
        env_ = st.latest_revision(ex)
        assert env_["state"] == "quarantined_sensitive"
        assert ev.named("training.secret_quarantined")
        blob = json.dumps([e[2] for e in ev.events], default=str)
        assert SECRET not in blob
        st.close()
    print("ok  03 suspected secret: the only example INSERT is already"
          " quarantined; example+revision commit together")


def test_publish_fault_leaves_no_example():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        feed(col, ctx, raw="k " + SECRET)
        real = store.conn_append_revision

        def boom(*a, **k):
            raise sqlite3.OperationalError("injected revision failure")
        store.conn_append_revision = boom
        try:
            assert col.finalize(ctx) is None
        finally:
            store.conn_append_revision = real
        st.sync()
        assert q(st, "SELECT COUNT(*) FROM training_examples")[0][0] == 0
        assert [e for e in ev.named("training.capture_failed")
                if e[2].get("outcome") == "publish_failed"]
        st.close()
    print("ok  03 a fault inside publication rolls back the example too")


# ---- M02-AUDIT-05 -------------------------------------------------------

def test_uncommitted_artifact_is_reported_not_claimed():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        real = store.insert_text_artifact_row

        def faulty(conn, **kw):
            if kw.get("role") == "raw_transcript":
                raise sqlite3.OperationalError("injected raw insert failure")
            return real(conn, **kw)
        store.insert_text_artifact_row = faulty
        try:
            ctx = start(col)
            feed(col, ctx)
            ex = col.finalize(ctx)  # dictation-level call does not raise
        finally:
            store.insert_text_artifact_row = real
        assert ex is not None
        env_ = st.latest_revision(ex)
        assert env_["artifact_ids"]["source_text"] is None
        assert env_["missing_reasons"]["source_text"] == \
            "not_captured_at_stage"
        assert env_["completeness"] == {
            "complete": False,
            "uncommitted_references": ["artifact_ids.source_text"]}
        saved = ev.named("training.revision_saved")
        assert len(saved) == 1
        assert saved[0][2]["reason_code"] == "capture_incomplete"
        assert saved[0][1] == "WARNING"
        # Committed pieces are still published and consistent.
        assert env_["artifact_ids"]["original_audio"]
        assert env_["artifact_ids"]["applied_output"]
        assert st.verify(deep=True)["ok"]
        st.close()
    print("ok  05 failed raw insert: envelope nulls it with a reason,"
          " completeness false, event says capture_incomplete")


def test_complete_publication_is_acknowledged_after_commit():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        feed(col, ctx)
        ex = col.finalize(ctx)
        saved = ev.named("training.revision_saved")
        assert saved[0][2]["reason_code"] == "capture_complete"
        assert saved[0][2]["outcome"] == "committed"
        # The event names only artifacts that exist, and they exist now.
        for aid in saved[0][2]["artifact_ids"]:
            assert q(st, "SELECT purged FROM artifacts WHERE artifact_id=?",
                     (aid,)) == [(0,)]
        env_ = st.latest_revision(ex)
        assert env_["completeness"]["complete"] is True
        roles = sorted(r[0] for r in q(st, "SELECT role FROM artifacts"))
        assert roles == ["applied_output", "cleanup_input_cleanup",
                         "cleanup_proposal", "original_audio",
                         "raw_transcript"], roles
        st.close()
    print("ok  05 complete capture: event after commit, positive population")


# ---- M02-AUDIT-06 -------------------------------------------------------

def test_consent_is_decided_at_capture_start():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        # Disabled at PTT down, enabled before release: not collected.
        snap = consent.capture_snapshot()
        consent.set("enabled")
        ctx = start(col, snapshot=snap)
        feed(col, ctx)
        assert col.finalize(ctx) is None and not ctx.collecting
        st.sync()
        assert q(st, "SELECT COUNT(*) FROM artifacts")[0][0] == 0
        assert not list(st.artifacts_dir.glob("*.wav"))
        # Enabled at PTT down, paused before release: the in-flight
        # capture keeps its capture-time permission (documented policy).
        snap = consent.capture_snapshot()
        cid = snap.revision_id
        consent.set("paused")
        ctx = start(col, snapshot=snap)
        feed(col, ctx)
        ex = col.finalize(ctx)
        env_ = st.latest_revision(ex)
        assert env_["consent_revision_id"] == cid
        assert env_["consent_snapshot_point"] == "ptt_down"
        assert q(st, "SELECT state FROM consent_revisions WHERE"
                     " consent_revision_id=?", (cid,)) == [("enabled",)]
        # Paused at PTT down: nothing.
        ctx = start(col, snapshot=consent.capture_snapshot())
        feed(col, ctx)
        assert col.finalize(ctx) is None
        st.close()
    print("ok  06 consent decided at PTT down in both directions; recorded"
          " revision is the capture-time enabled revision")


def test_state_and_revision_read_together():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        real = st.current_consent_id

        def interleaved():  # a consent write between two separate reads
            st.append_consent("paused")
            return real()
        st.current_consent_id = interleaved
        try:
            ctx = start(col)
        finally:
            st.current_consent_id = real
        # The repaired path never pairs two separate reads.
        assert ctx.collecting
        assert q(st, "SELECT state FROM consent_revisions WHERE"
                     " consent_revision_id=?",
                 (ctx.consent_revision_id,)) == [("enabled",)]
        # Real race: writers toggling while snapshots are taken; every
        # snapshot's state must be the state OF the revision it names.
        stop = threading.Event()

        def toggler():
            for i in range(200):  # bounded: interleaves with the reads
                if stop.is_set():
                    break
                consent.set(("enabled", "paused")[i % 2])
                if i % 4 == 0:
                    st.sync()
        t = threading.Thread(target=toggler)
        t.start()
        snaps = [consent.snapshot_now() for _ in range(60)]
        stop.set()
        t.join()
        by_id = dict((r[1], r[0]) for r in q(
            st, "SELECT state, consent_revision_id FROM consent_revisions"))
        collected = [s for s in snaps if s.collecting]
        assert collected and all(by_id[s.revision_id] == "enabled"
                                 for s in collected)
        assert all(s.revision_id is None for s in snaps if not s.collecting)
        st.close()
    print("ok  06 consent state and revision come from one read (60"
          " snapshots under concurrent toggling, all coherent)")


def test_retry_uses_original_capture_permission():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        # Original capture while disabled -> retry after enabling: none.
        ctx = start(col)
        snap = col.retry_snapshot(ctx.job_id)
        consent.set("enabled")
        assert not col.retry_snapshot(ctx.job_id).collecting
        assert not snap.collecting
        # Original capture enabled (example exists) -> retry while enabled
        # reuses the ORIGINAL revision; retry while paused collects none.
        orig = start(col)
        feed(col, orig)
        col.on_failure(orig, "WorkerFailure")
        cid = orig.consent_revision_id
        consent.set("enabled")  # a newer revision exists now
        r = col.retry_snapshot(orig.job_id)
        assert r.collecting and r.revision_id == cid
        assert r.point == "retry_original_capture"
        consent.set("paused")
        assert not col.retry_snapshot(orig.job_id).collecting
        st.close()
    print("ok  06 retry: original capture permission AND current enabled;"
          " never today's consent attached to old audio")


# ---- M02-AUDIT-08 -------------------------------------------------------

def test_outcome_and_annotation_serialize():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        feed(col, ctx)
        ex = col.finalize(ctx)
        svc = training_data.TrainingDataService(st)
        in_mutate, release = threading.Event(), threading.Event()
        real = st.update_latest_revision

        def gated(example_id, mutate, **kw):
            def slow(e):
                in_mutate.set()
                release.wait(10)
                return mutate(e)
            return real(example_id, slow, **kw)
        st.update_latest_revision = gated
        t = threading.Thread(target=lambda: col.on_insertion(ctx, True, 11))
        t.start()
        assert in_mutate.wait(10)
        # The human annotation arrives while the outcome op is mid-flight.
        ann = threading.Thread(target=lambda: svc.mark_intended(ex, True))
        ann.start()
        release.set()
        t.join(10)
        ann.join(10)
        st.update_latest_revision = real
        latest = st.latest_revision(ex)
        assert latest["outcome"]["correctness"] == "correct"
        assert latest["outcome"]["insertion"] == "posted_unverified"
        chain = q(st, "SELECT revision_id, parent_revision_id FROM"
                      " training_revisions WHERE example_id=? ORDER BY rowid",
                  (ex,))
        assert len(chain) == 3 and chain[0][1] is None
        assert chain[1][1] == chain[0][0] and chain[2][1] == chain[1][0]
        # Other order: annotation first, outcome keeps it.
        ctx2 = start(col)
        feed(col, ctx2)
        ex2 = col.finalize(ctx2)
        svc.mark_intended(ex2, False)
        col.on_insertion(ctx2, False, 0)
        l2 = st.latest_revision(ex2)
        assert l2["outcome"]["correctness"] == "incorrect"
        assert l2["outcome"]["insertion"] == "not_attempted"
        st.close()
    print("ok  08 outcome/annotation interleave: both kept, linear parent"
          " chain, in both orders")


# ---- M02-AUDIT-09 -------------------------------------------------------

def test_retry_attempt_and_stage_generations():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        st.create_job(job_id=ctx.job_id)
        feed(col, ctx)  # ASR from generation 1
        # The worker restarted during cleanup: attempt 2, generation 2.
        st.bump_job_attempt(ctx.job_id)
        col.note_attempt(ctx, 2, stage="cleanup", worker_generation=2)
        ex = col.finalize(ctx)
        env_ = st.latest_revision(ex)
        assert env_["attempt"] == st.job(ctx.job_id)["attempt"] == 2
        assert env_["stage_generations"] == {"asr": 1, "cleanup": 2}
        assert env_["worker_generation"] == 1  # ASR stays ASR's
        saved = ev.named("training.revision_saved")[0][2]
        assert saved["attempt"] == 2
        st.close()
    print("ok  09 envelope attempt follows the retry; generations recorded"
          " per stage, never relabeled")


# ---- M02-AUDIT-16 -------------------------------------------------------

def test_menu_mark_matches_hub_mark_and_is_retained():
    with tempfile.TemporaryDirectory() as td:
        clock = Clock()
        st, ev, consent, col = env(td, clock)
        consent.set("enabled")
        svc = training_data.TrainingDataService(st)
        a = start(col)
        feed(col, a)
        ex_a = col.finalize(a)
        col.mark_last_correct()           # legacy menu
        b = start(col)
        feed(col, b)
        ex_b = col.finalize(b)
        svc.mark_intended(ex_b, True)     # Hub
        c = start(col)
        feed(col, c)
        ex_c = col.finalize(c)            # unreviewed control
        for ex in (ex_a, ex_b):
            out = st.latest_revision(ex)["outcome"]
            assert out["correctness"] == "correct"
            assert out["correctness_provenance"] == \
                "user_explicit_intended_writing"
        st.prune_training(now=T0 + 31 * DAY)
        st.prune(now=T0 + 31 * DAY)
        states = dict(q(st, "SELECT example_id, state FROM"
                            " training_examples"))
        assert states[ex_a] == states[ex_b] == "annotated"
        assert states[ex_c] == "expired"
        for ctx, alive in ((a, 5), (b, 5), (c, 0)):
            n = q(st, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                      " purged=0", (ctx.job_id,))[0][0]
            assert n == alive, (ctx.job_id, n)
        # The exporter's intended-writing predicate is satisfied equally.
        from localflow.v2.curation import export as ex_mod
        src = pathlib.Path(ex_mod.__file__).read_text()
        assert "user_explicit_intended_writing" in src
        st.close()
    print("ok  16 menu mark == Hub mark (provenance + annotated); reviewed"
          " evidence retained past the buffer, unreviewed expires")


def test_mark_never_reincludes_or_upgrades_history():
    with tempfile.TemporaryDirectory() as td:
        st, ev, consent, col = env(td)
        consent.set("enabled")
        ctx = start(col)
        feed(col, ctx)
        ex = col.finalize(ctx)
        # A pre-remediation revision recorded as plain user_explicit.
        st.update_latest_revision(ex, lambda e: dict(e, outcome=dict(
            e["outcome"], correctness="correct",
            correctness_provenance="user_explicit")))
        before = q(st, "SELECT envelope_json FROM training_revisions ORDER"
                       " BY rowid")
        st.set_example_state(ex, "excluded")
        col.mark_last_correct()
        assert q(st, "SELECT state FROM training_examples") == [("excluded",)]
        after = q(st, "SELECT envelope_json FROM training_revisions ORDER"
                      " BY rowid")
        assert after[:len(before)] == before  # history untouched
        provs = [json.loads(r[0])["outcome"].get("correctness_provenance")
                 for r in after]
        assert provs[1] == "user_explicit"
        st.close()
    print("ok  16 mark keeps an excluded example excluded; old user_explicit"
          " revisions are never rewritten")


# ---- M02-AUDIT-17 -------------------------------------------------------

def _bench():
    spec = importlib.util.spec_from_file_location(
        "benchmark_m02", ROOT / "scripts" / "v2" / "benchmark_m02.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_benchmark_refuses_unbound_or_empty_collection():
    bench = _bench()
    for kwargs in ({"n": 3, "bind": False}, {"n": 0}):
        try:
            bench.bench_collection_paired(**kwargs)
            raise AssertionError(f"benchmark certified {kwargs}")
        except bench.BenchmarkPopulationError as e:
            assert "enabled" in str(e) or "disabled" in str(e)
    res = bench.bench_collection_paired(n=3)
    assert res["certified"] is True
    assert "acknowledged" in res["timing_scope"]
    assert res["meets_s2916_target"] == (res["delta_p95_ms"] <= 25)
    pops = res["enabled"]["populations"]
    assert pops["artifacts_by_role"] == {r: 3 for r in bench.EXPECTED_ROLES}
    assert pops["examples"] == 3 and pops["revisions"] == 6
    assert pops["model_input_artifacts"] == 3
    assert res["disabled"]["populations"]["examples"] == 0
    assert not any(res["disabled"]["populations"]["artifacts_by_role"]
                   .values())
    print("ok  17 benchmark refuses unbound and empty collection; bound run"
          " proves every stage population (3 prompts/proposals) and states"
          " its timing scope")


def main():
    tests = [
        test_delete_before_finalize_blocks_late_producer,
        test_late_outcome_after_example_delete_refused,
        test_quarantine_is_the_first_visible_state,
        test_publish_fault_leaves_no_example,
        test_uncommitted_artifact_is_reported_not_claimed,
        test_complete_publication_is_acknowledged_after_commit,
        test_consent_is_decided_at_capture_start,
        test_state_and_revision_read_together,
        test_retry_uses_original_capture_permission,
        test_outcome_and_annotation_serialize,
        test_retry_attempt_and_stage_generations,
        test_menu_mark_matches_hub_mark_and_is_retained,
        test_mark_never_reincludes_or_upgrades_history,
        test_benchmark_refuses_unbound_or_empty_collection,
    ]
    for t in tests:
        t()
    print(f"all m02 remediation collector tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
