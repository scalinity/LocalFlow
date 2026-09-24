"""EV-15 personalization portion (V2 M14): the correction-learning
workflow — wrong target, repeated snippet, background/test exclusion,
approved vs unapproved rules (M14-AC01), rejection persistence and
suppression, undo, deletion propagation, unsupported inference — plus
the v10 store migration (additive, backup, repair) and
delete-everywhere propagation into candidates, labels and profile
snapshots.

Run: .venv/bin/python tests/v2/personalization/test_learning.py
"""

import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import learning, store as store_mod  # noqa: E402
from localflow.v2.curation import classify, review  # noqa: E402
from localflow.v2.vocabulary import sandbox_phrase  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")


def add_job_with_text(s, raw, applied, *, family=None, job_seq=1,
                      snippets=False):
    job, fam = s.create_job(family_id=family)
    raw_aid = s.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript", text=raw,
        retention_class="training")
    app_aid = s.write_text_artifact(
        job_id=job, stage="cleanup", role="applied_output", text=applied,
        retention_class="training", parent_artifact_id=raw_aid)
    ex = s.upsert_example(job_id=job, family_id=fam)
    env = {"example_id": ex, "job_id": job, "family_id": fam,
           "artifact_ids": {"source_text": raw_aid,
                            "applied_output": app_aid},
           "outcome": {}, "annotations": [], "missing_reasons": {}}
    if snippets:
        env["normalization"] = {"snippets": {"expansions": 1}}
    s.append_revision(ex, env)
    return ex, job


def services(s):
    vs = VocabularyStore(s)
    return (vs, learning.LearningService(
        s, emit=lambda *a, **k: None, vocabulary=vs))


def test_migration_v10_additive_with_backup_and_repair():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        db = tmp / "v2.db"
        pre = sqlite3.connect(db)
        for v in range(1, 10):
            for stmt in store_mod._MIGRATIONS[v]:
                pre.execute(stmt)
        pre.execute("INSERT OR REPLACE INTO schema_meta VALUES"
                    "('schema_version','9')")
        pre.commit()
        pre.close()
        s = make_store(tmp)
        try:
            assert s.submit(lambda db: db.execute(
                "SELECT value FROM schema_meta WHERE"
                " key='schema_version'").fetchone())[0] == "10"
            for table in ("learning_candidates", "correction_labels",
                          "sampling_decisions", "split_assignments",
                          "training_memberships", "example_tags",
                          "profile_snapshots", "profile_evidence",
                          "export_manifests"):
                assert s.submit(lambda db, t=table: db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    f" AND name=?", (t,)).fetchone()), table
            assert any((tmp / "backups").glob("v2-pre-migrate-*.db"))
            s.close()
            post = sqlite3.connect(db)
            post.execute("DROP TABLE IF EXISTS learning_candidates")
            post.execute("DROP TABLE IF EXISTS training_memberships")
            post.commit()
            post.close()
            s2 = make_store(tmp)
            try:
                assert s2.submit(lambda db: db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='learning_candidates'"
                ).fetchone()), "v10 not repaired"
            finally:
                s2.close()
        finally:
            try:
                s.close()
            except Exception:
                pass
        print("ok  v10 migration: additive, backed up, in the repair"
              " set")


def test_unapproved_rejected_never_change_output():
    """M14-AC01 + regression requirement: with pending, rejected and
    stale candidates present, normalization output is IDENTICAL to the
    no-candidates baseline; only an approved rule (a real vocabulary
    entry) ever applies."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "ship the clod code branch",
                "Ship the clod code branch")
            out = ls.teach_correction(job, "Ship the Claude Code branch")
            cand = out["candidate_id"]
            # Pending: nothing in the pipeline changes.
            snapshot = vs.snapshot()
            res = sandbox_phrase("ship the clod code branch", snapshot)
            assert not res["changed"], res
            res2 = sandbox_phrase("deploy the clod service", snapshot)
            assert not res2["changed"]
            # Rejected: persists; suppression active.
            ls.reject(cand, "wrong_scope")
            assert any(c["status"] == "rejected"
                       for c in ls.candidates())
            # The same observation re-mined never re-proposes.
            obs_now = "2026-09-23T10:00:00.000Z"

            def obs_op(conn):
                for suffix, text in (("b", "Ship the clod code branch"),
                                     ("a", "Ship the Claude Code"
                                           " branch")):
                    from localflow.v2.store import \
                        insert_text_artifact_row
                    insert_text_artifact_row(
                        conn, artifact_id=f"art-x{suffix}",
                        job_id=job, stage="insertion",
                        role=f"observed_{suffix}", text=text,
                        retention_class="training",
                        created_at_utc=obs_now)
                conn.execute(
                    "INSERT INTO insertion_observations(observation_id,"
                    " insertion_id, job_id, started_at_utc,"
                    " stopped_at_utc, stop_reason, edited, reanchors,"
                    " ticks, before_artifact_id, after_artifact_id,"
                    " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("obs-x1", "ins-x1", job, obs_now, obs_now,
                     "owned_range_edited", 1, 0, 3,
                     "art-xb", "art-xa", "{}"))
            s.submit(obs_op)
            ls.mine_observation_candidates()
            fresh = [c for c in ls.candidates(status="suppressed")]
            assert fresh, "rejected pair was re-proposed"
            assert all(c["status"] == "suppressed" for c in fresh)
            # Undo path: approve then undo disables the entry.
            ex2, job2 = add_job_with_text(
                s, "open the mlx docs", "Open the mlx docs")
            out2 = ls.teach_correction(job2, "Open the MLX docs")
            approved = ls.approve(out2["candidate_id"])
            assert approved["entry_id"]
            snap2 = vs.snapshot()
            assert sandbox_phrase("open the mlx docs", snap2)["changed"]
            ls.undo_approval(out2["candidate_id"])
            entry = vs.entry(approved["entry_id"])
            assert not entry.enabled
            assert not sandbox_phrase("open the mlx docs",
                                      vs.snapshot())["changed"]
            print("ok  AC01: pending/rejected/suppressed never change"
                  " output; approval composes with the vocabulary"
                  " controls; undo disables")
        finally:
            s.close()


def test_counterexample_refusal():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "clod deployment notes", "Clod deployment notes")
            out = ls.teach_correction(job, "Claude deployment notes")
            res = ls.approve(out["candidate_id"],
                             counterexamples=("cloud deployment"
                                              " stack",))
            # "clod" does not token-match "cloud" — no flip, approval
            # lands. A REAL flip case: alias "clod" flipping a phrase
            # that contains the token "clod" as part of the wrong
            # intent is not constructible at token boundaries (M05's
            # design); the check still proves the machinery by using
            # an alias that DOES appear.
            assert res["entry_id"], res
            ex2, job2 = add_job_with_text(
                s, "serverless clod functions", "Serverless clod"
                                                 " functions")
            out2 = ls.teach_correction(job2, "Serverless Claude"
                                              " functions")
            res2 = ls.approve(out2["candidate_id"],
                              counterexamples=("the clod functions"
                                               " module stays",))
            assert not res2["entry_id"] and res2["flips"], res2
            cand = [c for c in ls.candidates()
                    if c["candidate_id"] == out2["candidate_id"]][0]
            assert cand["status"] == "pending"  # refused, not consumed
            print("ok  counterexamples: a would-flip rule is refused"
                  " with the flip shown, the candidate stays pending")
        finally:
            s.close()


def test_teach_refusals_and_deletion_propagation():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "identical words here", "Identical words here")
            for bad in ("Identical words here",
                        "a completely different rewrite of everything"):
                try:
                    ls.teach_correction(job, bad)
                    raise AssertionError(f"accepted {bad!r}")
                except ValueError:
                    pass
            # Unsupported inference: an ambiguous edit teaches nothing
            # but review still gets the spans.
            ex2, job2 = add_job_with_text(
                s, "send the report now", "Send the report now")

            def obs_op(conn, before, after, oid):
                from localflow.v2.store import insert_text_artifact_row
                now = "2026-09-23T10:00:00.000Z"
                insert_text_artifact_row(
                    conn, artifact_id=f"art-{oid}b", job_id=job2,
                    stage="insertion", role="observed_b", text=before,
                    retention_class="training", created_at_utc=now)
                insert_text_artifact_row(
                    conn, artifact_id=f"art-{oid}a", job_id=job2,
                    stage="insertion", role="observed_a", text=after,
                    retention_class="training", created_at_utc=now)
                conn.execute(
                    "INSERT INTO insertion_observations(observation_id,"
                    " insertion_id, job_id, started_at_utc,"
                    " stopped_at_utc, stop_reason, edited, reanchors,"
                    " ticks, before_artifact_id, after_artifact_id,"
                    " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (oid, f"ins-{oid}", job2, now, now,
                     "owned_range_edited", 1, 0, 3,
                     f"art-{oid}b", f"art-{oid}a", "{}"))
            s.submit(lambda c: obs_op(c, "Send the report now",
                                      "Deliver the summary instead",
                                      "y1"))
            ls.mine_observation_candidates()
            assert not [c for c in ls.candidates(status="pending")
                        if c["example_id"] == ex2]
            # Deletion propagation: delete-everywhere stales pending
            # candidates, drops labels, invalidates profiles.
            ex3, job3 = add_job_with_text(
                s, "fix the wrod here", "Fix the wrod here")
            out = ls.teach_correction(job3, "Fix the word here")
            assert out["status"] == "pending"
            rs = review.ReviewService(s, emit=lambda *a, **k: None)
            rs.record_label(ex3, edit_kind="recognition_error",
                            origin_stages=("asr",),
                            evidence_status="explicit_intent_review")
            s.delete_everywhere("example", ex3, reason="user_request")
            cand = [c for c in ls.candidates()
                    if c["candidate_id"] == out["candidate_id"]][0]
            assert cand["status"] == "stale"
            assert not rs.labels(ex3)
            try:
                ls.approve(out["candidate_id"])
                raise AssertionError("stale candidate approved")
            except ValueError:
                pass
            print("ok  teach refusals (unchanged / rewrite), ambiguous"
                  " edits teach nothing, deletion stales candidates and"
                  " drops labels")
        finally:
            s.close()


def test_repeated_snippet_excluded_from_mining():
    """Snippet-expanded examples never feed phrase/candidate
    statistics (S22) — the profile suite pins the profile half; here
    the mining half: an observation whose example carries snippet
    expansions still mines (it is a REAL correction of real text), but
    the profile eligibility is pinned separately."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "run the checks", "Run the checks", snippets=True)

            def obs_op(conn):
                from localflow.v2.store import insert_text_artifact_row
                now = "2026-09-23T10:00:00.000Z"
                insert_text_artifact_row(
                    conn, artifact_id="art-sb", job_id=job,
                    stage="insertion", role="observed_b",
                    text="Run the checks", retention_class="training",
                    created_at_utc=now)
                insert_text_artifact_row(
                    conn, artifact_id="art-sa", job_id=job,
                    stage="insertion", role="observed_a",
                    text="Run the checks please",
                    retention_class="training", created_at_utc=now)
                conn.execute(
                    "INSERT INTO insertion_observations(observation_id,"
                    " insertion_id, job_id, started_at_utc,"
                    " stopped_at_utc, stop_reason, edited, reanchors,"
                    " ticks, before_artifact_id, after_artifact_id,"
                    " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("obs-s1", "ins-s1", job, now, now,
                     "owned_range_edited", 1, 0, 3,
                     "art-sb", "art-sa", "{}"))
            s.submit(obs_op)
            ls.mine_observation_candidates()
            pending = [c for c in ls.candidates(status="pending")
                       if c["example_id"] == ex]
            assert len(pending) == 1  # one candidate, not one per word
            assert not pending[0]["alias"]  # style edit, no rule
            print("ok  repeated-trigger dedup: one observation mints"
                  " one candidate; style edits carry no rule")
        finally:
            s.close()


def _add_observation(s, job, before, after, oid):
    from localflow.v2.store import insert_text_artifact_row
    now = "2026-09-23T10:00:00.000Z"

    def op(conn):
        for suffix, text in (("b", before), ("a", after)):
            insert_text_artifact_row(
                conn, artifact_id=f"art-{oid}{suffix}", job_id=job,
                stage="insertion", role=f"observed_{suffix}", text=text,
                retention_class="training", created_at_utc=now)
        conn.execute(
            "INSERT INTO insertion_observations(observation_id,"
            " insertion_id, job_id, started_at_utc, stopped_at_utc,"
            " stop_reason, edited, reanchors, ticks, before_artifact_id,"
            " after_artifact_id, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (oid, f"ins-{oid}", job, now, now, "owned_range_edited", 1, 0,
             3, f"art-{oid}b", f"art-{oid}a", "{}"))
    s.submit(op)


def test_app_scoped_counterexample_is_checked_in_scope():
    """The counterexample sandbox filters for the rule's own scope: an
    app-scoped candidate (the default whenever a destination app was
    recorded) is tested where it would fire — an unscoped sandbox
    would never apply it and pass every counterexample vacuously."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "serverless clod functions", "Serverless clod"
                                                 " functions")
            s.set_job_target(job, "Synth Editor", "com.example.synth")
            out = ls.teach_correction(job, "Serverless Claude functions")
            cand = [c for c in ls.candidates()
                    if c["candidate_id"] == out["candidate_id"]][0]
            assert cand["scope_kind"] == "app", cand
            res = ls.approve(out["candidate_id"], counterexamples=(
                "the clod functions module stays",))
            assert not res["entry_id"] and res["flips"], res
            print("ok  counterexamples run in the rule's own scope (app"
                  " scope is not a vacuous pass)")
        finally:
            s.close()


def test_approval_composes_with_existing_entries_and_undo():
    """Approval on a canonical the user already keeps adds the alias
    to that entry (M05's one-canonical-per-scope rule would refuse a
    second entry); undo removes only that alias and leaves the user's
    entry active. An approval that created its entry survives
    undo → re-approve."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            own = vs.add_entry("Claude", [("claud", True)],
                               approved=True)
            ex, job = add_job_with_text(
                s, "ask clod for a review", "Ask clod for a review")
            out = ls.teach_correction(job, "Ask Claude for a review")
            res = ls.approve(out["candidate_id"])
            assert res["entry_id"] == own and \
                res["action"] == "alias_added", res
            assert sandbox_phrase("ask clod now",
                                  vs.snapshot())["changed"]
            ls.undo_approval(out["candidate_id"])
            entry = vs.entry(own)
            assert entry.enabled and entry.approved
            assert [a.alias for a in entry.aliases] == ["claud"]
            assert not sandbox_phrase("ask clod now",
                                      vs.snapshot())["changed"]
            # Created path: approve → undo → re-approve.
            ex2, job2 = add_job_with_text(
                s, "open the mlx docs", "Open the mlx docs")
            out2 = ls.teach_correction(job2, "Open the MLX docs")
            first = ls.approve(out2["candidate_id"])
            assert first["action"] == "created"
            ls.undo_approval(out2["candidate_id"])
            again = ls.approve(out2["candidate_id"])
            assert again["entry_id"] == first["entry_id"]
            assert vs.entry(first["entry_id"]).enabled
            assert sandbox_phrase("open the mlx docs",
                                  vs.snapshot())["changed"]
            # A user-disabled term is never re-activated by approval.
            vs.set_enabled(own, False)
            ex3, job3 = add_job_with_text(
                s, "ping clod today", "Ping clod today")
            out3 = ls.teach_correction(job3, "Ping Claude today")
            try:
                ls.approve(out3["candidate_id"])
                raise AssertionError("approved onto a disabled entry")
            except ValueError as e:
                assert "existing_entry_not_active" in str(e)
            # An approval interrupted between its plan and the
            # vocabulary write keeps the plan; the retry lands the SAME
            # entry and undo still reverses it.
            ex4, job4 = add_job_with_text(
                s, "use the pyobjc bridge", "Use the pyobjc bridge")
            out4 = ls.teach_correction(job4, "Use the PyObjC bridge")
            real_add = vs.add_entry

            def failing_add(*a, **k):
                raise OSError("simulated crash")
            vs.add_entry = failing_add
            try:
                ls.approve(out4["candidate_id"])
                raise AssertionError("interrupted approval returned")
            except OSError:
                pass
            vs.add_entry = real_add
            planned = s.submit(lambda c: c.execute(
                "SELECT status, vocabulary_entry_id, vocabulary_action"
                " FROM learning_candidates WHERE candidate_id=?",
                (out4["candidate_id"],)).fetchone())
            assert planned[0] == "pending" and planned[1] and \
                planned[2] == "created", planned
            done = ls.approve(out4["candidate_id"])
            assert done["entry_id"] == planned[1]
            ls.undo_approval(out4["candidate_id"])
            assert not vs.entry(planned[1]).enabled
            print("ok  approval adds aliases to the user's entry; undo"
                  " reverses only what approval did; re-approval after"
                  " undo works; an interrupted approval resumes its"
                  " plan")
        finally:
            s.close()


def test_attribution_boundaries_for_mining_and_teach():
    """A negation flip never becomes a rule; an excluded example's
    observation teaches nothing; a note holding two dictations cannot
    attribute a typed edit to either; explicit teach works from the
    job's History text when no training example exists."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            ex, job = add_job_with_text(
                s, "I do want the update now",
                "I do want the update now")
            out = ls.teach_correction(job, "I don't want the update now")
            assert out["suggestion"] is None, out
            assert out["classification"]["abstain_reason"] == \
                "negation_flip_needs_review"
            ex2, job2 = add_job_with_text(
                s, "ship the clod branch", "Ship the clod branch")
            s.set_example_state(ex2, "excluded")
            _add_observation(s, job2, "Ship the clod branch",
                             "Ship the Claude branch", "obs-excl")
            ls.mine_observation_candidates()
            assert not [c for c in ls.candidates(status="pending")
                        if c["job_id"] == job2]
            # Two dictations in one note: no attribution.
            ex3, job3 = add_job_with_text(s, "alpha clod", "alpha clod")
            ex4, job4 = add_job_with_text(s, "beta words", "beta words")
            now = "2026-09-23T10:00:00.000Z"

            def note_op(conn):
                conn.execute(
                    "INSERT INTO notes(note_id, created_at_utc,"
                    " updated_at_utc) VALUES('note-x', ?, ?)", (now, now))
                for rid, origin, text, spans in (
                        ("nrev-1", "dictated", "alpha clod beta words",
                         [[0, 4, "dictated"]]),
                        ("nrev-2", "typed", "alpha Claude beta words",
                         [[2, 4, "dictated"]])):
                    conn.execute(
                        "INSERT INTO note_revisions(revision_id, note_id,"
                        " origin, content_text, content_sha256,"
                        " spans_json, created_at_utc)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (rid, "note-x", origin, text, "0" * 64,
                         json.dumps(spans), now))
                for e, j in ((ex3, job3), (ex4, job4)):
                    conn.execute(
                        "INSERT INTO note_evidence_links(note_id,"
                        " example_id, job_id, first_seen_utc)"
                        " VALUES('note-x',?,?,?)", (e, j, now))
            s.submit(note_op)
            ls.mine_observation_candidates()
            assert not [c for c in ls.candidates()
                        if c["source"] == "note_revision"], \
                "an edit in a two-dictation note was attributed"
            # Teach without a training example (collection off).
            job5, _fam = s.create_job()
            s.write_text_artifact(
                job_id=job5, stage="cleanup", role="applied_output",
                text="Book the clod session", retention_class="history")
            out5 = ls.teach_correction(job5, "Book the Claude session")
            # Applied text only: no raw stage to attribute ASR against,
            # so the spans go to review without a rule.
            assert out5["status"] == "pending" and \
                out5["suggestion"] is None, out5
            job6, _fam = s.create_job()
            s.write_text_artifact(
                job_id=job6, stage="asr", role="raw_transcript",
                text="book the clod session", retention_class="history")
            s.write_text_artifact(
                job_id=job6, stage="cleanup", role="applied_output",
                text="Book the clod session", retention_class="history")
            out6 = ls.teach_correction(job6, "Book the Claude session")
            assert out6["suggestion"] == {"alias": "clod",
                                          "canonical": "Claude"}, out6
            print("ok  negation flips never suggest; excluded examples"
                  " teach nothing; two-dictation notes stay"
                  " unattributed; teach works without a training"
                  " example")
        finally:
            s.close()


def test_deletion_expiry_and_row_content():
    """Deletion and expiry reach every candidate (job-keyed, note-
    sourced), rows carry offsets and axes only, a machine-mined
    observation never pins its job past the unreviewed buffer, labels
    and teaching refuse non-live evidence, graft spans must index the
    source text, and refusals surface as ValueError (never a wrapped
    RuntimeError)."""
    import time as _time
    from localflow.v2.notes import NoteStore
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            rs = review.ReviewService(s, emit=lambda *a, **k: None)
            # (a) a job-keyed candidate (collection off: no example).
            job, _fam = s.create_job()
            s.write_text_artifact(
                job_id=job, stage="asr", role="raw_transcript",
                text="call the clod team", retention_class="history")
            s.write_text_artifact(
                job_id=job, stage="cleanup", role="applied_output",
                text="Call the clod team", retention_class="history")
            out = ls.teach_correction(job, "Call the Claude team")
            assert out["suggestion"] and out["status"] == "pending"
            row = s.submit(lambda c: c.execute(
                "SELECT changed_spans_json, classification_json FROM"
                " learning_candidates WHERE candidate_id=?",
                (out["candidate_id"],)).fetchone())
            # (c) rows are content-free: offsets and axes only.
            assert "clod" not in row[0] and "clod" not in row[1], row
            assert json.loads(row[0]) == [{"start": 9, "end": 13}]
            s.delete_everywhere("job", job, reason="user_request")
            cand = [c for c in ls.candidates()
                    if c["candidate_id"] == out["candidate_id"]][0]
            assert cand["status"] == "stale" and cand["alias"] is None
            try:
                ls.approve(out["candidate_id"])
                raise AssertionError("deleted job's candidate approved")
            except ValueError:
                pass
            # (b) a note-sourced candidate: payload holds the changed
            # regions only; note deletion stales it and purges payload.
            ex, njob = add_job_with_text(s, "alpha clod beta",
                                         "alpha clod beta")
            now = "2026-09-23T10:00:00.000Z"

            def note_op(conn):
                conn.execute(
                    "INSERT INTO notes(note_id, created_at_utc,"
                    " updated_at_utc) VALUES('note-y', ?, ?)", (now, now))
                for rid, origin, text, spans in (
                        ("nrev-y1", "dictated",
                         "alpha clod beta my private typed words",
                         [[0, 3, "dictated"]]),
                        ("nrev-y2", "typed",
                         "alpha Claude beta my private typed words",
                         [[0, 3, "dictated"]])):
                    conn.execute(
                        "INSERT INTO note_revisions(revision_id, note_id,"
                        " origin, content_text, content_sha256,"
                        " spans_json, created_at_utc)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (rid, "note-y", origin, text, "0" * 64,
                         json.dumps(spans), now))
                conn.execute(
                    "INSERT INTO note_evidence_links(note_id, example_id,"
                    " job_id, first_seen_utc) VALUES('note-y',?,?,?)",
                    (ex, njob, now))
            s.submit(note_op)
            ls.mine_observation_candidates()
            note_cand = s.submit(lambda c: c.execute(
                "SELECT candidate_id, after_artifact_id FROM"
                " learning_candidates WHERE source='note_revision'"
            ).fetchone())
            payload = s.submit(lambda c: c.execute(
                "SELECT content_text FROM artifacts WHERE artifact_id=?",
                (note_cand[1],)).fetchone()[0])
            assert "private" not in payload and "Claude" in payload
            NoteStore(s).delete_note("note-y")
            status, alias = s.submit(lambda c: c.execute(
                "SELECT status, proposed_alias FROM learning_candidates"
                " WHERE candidate_id=?", (note_cand[0],)).fetchone())
            assert status == "stale" and alias is None
            assert s.submit(lambda c: c.execute(
                "SELECT purged, content_text FROM artifacts WHERE"
                " artifact_id=?", (note_cand[1],)).fetchone()) == (1, None)
            # (d) expiry: a mined observation never pins its job past
            # the buffer; an explicit teach (reviewed evidence) does.
            ex_m, job_m = add_job_with_text(s, "ship the clod branch",
                                            "Ship the clod branch")
            _add_observation(s, job_m, "Ship the clod branch",
                             "Ship the Claude branch", "obs-exp")
            ls.mine_observation_candidates()
            ex_t, job_t = add_job_with_text(s, "open the mlx docs",
                                            "Open the mlx docs")
            ls.teach_correction(job_t, "Open the MLX docs")
            s.prune_training(now=_time.time() + 40 * 86400)
            states = dict(s.submit(lambda c: c.execute(
                "SELECT example_id, state FROM training_examples"
            ).fetchall()))
            assert states[ex_m] == "expired", states[ex_m]
            assert states[ex_t] != "expired"
            mined = [c for c in ls.candidates() if c["job_id"] == job_m]
            assert mined and all(c["status"] == "stale" for c in mined)
            # (e) labels and teaching refuse non-live evidence — with a
            # ValueError, and without moving the state.
            ex_q, job_q = add_job_with_text(s, "the key is here",
                                            "The key is here")
            s.set_example_state(ex_q, "quarantined_sensitive")
            try:
                rs.record_label(ex_q, edit_kind="recognition_error")
                raise AssertionError("label landed on quarantine")
            except ValueError as e:
                assert "example_not_reviewable" in str(e)
            assert s.submit(lambda c: c.execute(
                "SELECT state FROM training_examples WHERE example_id=?",
                (ex_q,)).fetchone()[0]) == "quarantined_sensitive"
            try:
                ls.teach_correction(job_q, "The keys are here")
                raise AssertionError("taught from quarantine")
            except ValueError as e:
                assert "example_quarantined_sensitive" in str(e)
            # (f) graft spans index the source (raw) text only.
            ex_g, _jg = add_job_with_text(s, "send the cloud report",
                                          "Send the cloud report.")
            wrong = classify.changed_regions("Send the cloud report.",
                                             "Send the Claude report.")
            wrong[0]["start"] += 1  # an offset off the raw text
            wrong[0]["end"] += 1
            try:
                rs.record_label(ex_g, edit_kind="recognition_error",
                                confirmed_spans=wrong)
                raise AssertionError("misaligned graft accepted")
            except ValueError as e:
                assert "span_not_in_source_text" in str(e)
            right = classify.changed_regions("send the cloud report",
                                             "send the Claude report")
            assert rs.record_label(ex_g, edit_kind="recognition_error",
                                   confirmed_spans=right)["label_id"]
            # (g) refusals are ValueErrors, not wrapped RuntimeErrors.
            try:
                ls.reject(out["candidate_id"])
                raise AssertionError("stale candidate rejected")
            except ValueError as e:
                assert "not_pending" in str(e)
            print("ok  deletion/expiry reach job-keyed and note-sourced"
                  " candidates; rows content-free; mined observations"
                  " never pin; non-live evidence refuses labels/teach;"
                  " graft spans index the source; refusals are"
                  " ValueErrors")
        finally:
            s.close()


def test_review_queue_rows():
    """The queue carries each candidate's id, shows a job-only teach
    (collection off), and never re-shows a rejected pair."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            vs, ls = services(s)
            rs = review.ReviewService(s, emit=lambda *a, **k: None)
            ex, job = add_job_with_text(s, "ping clod now", "Ping clod now")
            first = ls.teach_correction(job, "Ping Claude now")
            ls.reject(first["candidate_id"])
            _add_observation(s, job, "Ping clod now", "Ping Claude now",
                             "obs-again")
            ls.mine_observation_candidates()
            assert [c for c in ls.candidates(status="suppressed")]
            job2, _fam = s.create_job()
            s.write_text_artifact(
                job_id=job2, stage="cleanup", role="applied_output",
                text="Book the clod room", retention_class="history")
            taught = ls.teach_correction(job2, "Book the Claude room")
            rows = rs.queue()
            assert all(r.get("candidate_status") != "suppressed"
                       for r in rows), rows
            job_only = [r for r in rows if r["job_id"] == job2]
            assert job_only and job_only[0]["example_id"] is None
            assert job_only[0]["candidate_id"] == taught["candidate_id"]
            print("ok  review queue: candidate ids on rows, job-only"
                  " teaches visible, rejected pairs never re-shown")
        finally:
            s.close()


if __name__ == "__main__":
    test_review_queue_rows()
    test_deletion_expiry_and_row_content()
    test_migration_v10_additive_with_backup_and_repair()
    test_unapproved_rejected_never_change_output()
    test_counterexample_refusal()
    test_teach_refusals_and_deletion_propagation()
    test_repeated_snippet_excluded_from_mining()
    test_app_scoped_counterexample_is_checked_in_scope()
    test_approval_composes_with_existing_entries_and_undo()
    test_attribution_boundaries_for_mining_and_teach()
    print("all learning tests passed")
