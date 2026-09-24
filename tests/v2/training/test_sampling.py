"""EV-19.4 sampling (V2 M14, S29.9): deterministic seeded stream,
hard-trigger enrichment with dedup, decision-ledger bookkeeping and
honest probabilities.

Run: .venv/bin/python tests/v2/training/test_sampling.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.curation import sampling  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")


def add_example(s, i, *, attempt=1, correctness="unreviewed",
                duration=12.0, language="en", family=None, seq=None):
    seq = seq or i
    job, fam = s.create_job(family_id=family)
    raw = s.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript",
        text=f"synthetic utterance number {i}", retention_class="training")
    ex = s.upsert_example(job_id=job, family_id=fam)
    s.append_revision(ex, {
        "example_id": ex, "job_id": job, "family_id": fam,
        "attempt": attempt, "artifact_ids": {"source_text": raw},
        "outcome": {"correctness": correctness},
        "capture": {"duration_sec": duration},
        "recognition": {"language": language},
        "annotations": [], "missing_reasons": {}})
    return ex, job


def test_deterministic_and_idempotent():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(30):
                add_example(s, i, attempt=2 if i % 6 == 0 else 1,
                            correctness="incorrect" if i % 9 == 0
                            else "unreviewed",
                            duration=2.0 if i % 7 == 0 else 12.0,
                            language="es" if i % 11 == 0 else "en")
            sm = sampling.SamplingService(s, emit=lambda *a, **k: None)
            r1 = sm.refresh(percent=20.0)
            assert r1["population"] == 30
            rows1 = s.submit(lambda c: c.execute(
                "SELECT example_id, stratum, inclusion_reason,"
                " inclusion_probability FROM sampling_decisions ORDER"
                " BY example_id").fetchall())
            # Idempotent under the same policy.
            assert sm.refresh(percent=20.0)["population"] == 0
            # Deterministic: wipe the ledger, redraw — identical rows.
            s.submit(lambda c: c.execute(
                "DELETE FROM sampling_decisions"))
            sm.refresh(percent=20.0)
            rows2 = s.submit(lambda c: c.execute(
                "SELECT example_id, stratum, inclusion_reason,"
                " inclusion_probability FROM sampling_decisions ORDER"
                " BY example_id").fetchall())
            assert rows1 == rows2
            # Hard triggers: every triggered example included, one row.
            cov = sm.coverage()
            assert cov["one_inclusion_per_example"]
            assert cov["decisions_distinct_examples"] == 30
            # 11 triggered examples: the 4 explicitly marked incorrect
            # are the explicit stratum, the other 7 hard triggers.
            assert cov["by_stratum"]["explicit"] == 4
            assert cov["by_stratum"]["hard_trigger"] == 7
            # Representative rows carry the known probability; enriched
            # selections never fabricate one (S29.9).
            for ex, stratum, reason, prob in rows1:
                if stratum == "representative":
                    assert prob == 0.2 and reason == "seeded_bernoulli"
                elif stratum in ("hard_trigger", "explicit"):
                    assert prob is None and reason
                elif stratum == "supplemental":
                    assert prob is None
            # A different policy draws independently — every example
            # is undecided under p2, so p2 decides all 30.
            sm.refresh(percent=100.0, policy="p2", seed="alt")
            total = s.submit(lambda c: c.execute(
                "SELECT COUNT(*) FROM sampling_decisions WHERE"
                " policy='p2'").fetchone()[0])
            assert total == 30, total
            # not_included is recorded, never re-drawn.
            assert sm.refresh(percent=100.0, policy="p2",
                              seed="alt")["population"] == 0
            print("ok  deterministic seeded stream; hard triggers with"
                  " dedup; honest probabilities; excluded draws"
                  " recorded once")
        finally:
            s.close()


def test_state_move_and_triggers():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            ids_added = [add_example(s, i) for i in range(8)]
            sm = sampling.SamplingService(s, emit=lambda *a, **k: None)
            sm.refresh(percent=100.0)  # everything included
            states = s.submit(lambda c: c.execute(
                "SELECT state, COUNT(*) FROM training_examples GROUP"
                " BY state").fetchall())
            assert dict(states).get("review_candidate") == 8
            # Trigger derivation over envelopes.
            from localflow.v2.curation.sampling import hard_trigger_reasons
            assert "explicit_incorrect" in hard_trigger_reasons(
                {"outcome": {"correctness": "incorrect"}})
            assert "retry" in hard_trigger_reasons({"attempt": 2})
            assert "cleanup_fallback" in hard_trigger_reasons(
                {"cleanup": {"fallback_reason": "model_refusal"}})
            assert "short_utterance" in hard_trigger_reasons(
                {"capture": {"duration_sec": 1.5}})
            assert "capture_discontinuity" in hard_trigger_reasons(
                {"capture": {"journal_dropped_blocks": 2}})
            assert not hard_trigger_reasons(
                {"outcome": {"correctness": "unreviewed"},
                 "capture": {"duration_sec": 10.0}})
            # Multiple triggers collapse into ONE row with all reasons.
            ex, _job = add_example(s, 99, attempt=3,
                                   correctness="incorrect", seq=99)
            out = sm.refresh(percent=0.0, policy="multi")
            row = s.submit(lambda c: c.execute(
                "SELECT inclusion_reason FROM sampling_decisions WHERE"
                " example_id=?", (ex,)).fetchone())
            assert row and ";" in row[0], row
            print("ok  included examples move to review_candidate;"
                  " trigger derivation; multi-trigger collapse")
        finally:
            s.close()


def test_late_triggers_and_configured_percent():
    """Triggers usually arrive after the first draw: an example drawn
    not_included that is later marked incorrect, retried or corrected
    gets ONE late decision (never a redraw, never a second inclusion);
    a taught correction lands in the explicit stratum. The service's
    default percent is the configured knob."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            added = [add_example(s, i) for i in range(4)]
            sm = sampling.SamplingService(s, emit=lambda *a, **k: None,
                                          percent=0.0)
            first = sm.refresh()
            assert first["percent"] == 0.0
            assert first["included"]["not_included"] == 4
            (ex0, job0), (ex1, _j1) = added[0], added[1]
            # A later explicit incorrect mark (a new revision)...
            env = s.submit(lambda c: c.execute(
                "SELECT envelope_json FROM training_revisions WHERE"
                " example_id=? ORDER BY rowid DESC LIMIT 1",
                (ex0,)).fetchone())[0]
            import json as _json
            env = _json.loads(env)
            parent = env.pop("revision_id")
            env["outcome"] = {"correctness": "incorrect"}
            s.append_revision(ex0, env, parent_revision_id=parent)
            # ...and a taught correction linked to another example.
            s.submit(lambda c: c.execute(
                "INSERT INTO learning_candidates(candidate_id,"
                " example_id, job_id, source, status,"
                " classification_json, created_at_utc, updated_at_utc)"
                " VALUES('cand-late', ?, 'job-x', 'explicit_teach',"
                " 'pending', '{}', 'now', 'now')", (ex1,)))
            second = sm.refresh()
            assert second["population"] == 0
            assert second["late_inclusions"] == 2, second
            rows = dict(s.submit(lambda c: c.execute(
                "SELECT example_id, stratum FROM sampling_decisions"
                " WHERE inclusion_reason LIKE 'late_trigger:%'"
            ).fetchall()))
            assert rows == {ex0: "explicit", ex1: "explicit"}, rows
            assert sm.refresh()["late_inclusions"] == 0  # once only
            cov = sm.coverage()
            assert cov["one_inclusion_per_example"]
            assert cov["late_inclusions"] == 2
            states = dict(s.submit(lambda c: c.execute(
                "SELECT example_id, state FROM training_examples"
            ).fetchall()))
            assert states[ex0] == states[ex1] == "review_candidate"
            print("ok  late triggers: one late decision, explicit"
                  " stratum, never a redraw; configured percent")
        finally:
            s.close()


if __name__ == "__main__":
    test_deterministic_and_idempotent()
    test_state_move_and_triggers()
    test_late_triggers_and_configured_percent()
    print("all sampling tests passed")
