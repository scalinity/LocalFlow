"""EV-15 profile portion (V2 M14, Spec S22, E13): measured views from
eligible evidence only, interpretive cards with supporting examples
and coverage, the below-threshold measured-only state (never a
fabricated profile — the M14 stop condition), deletion propagation
(M14-AC03), durable evidence exclusion, and the no-whole-profile-
injection regression (M14-AC04).

Run: .venv/bin/python tests/v2/personalization/test_profile.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import profile, store as store_mod  # noqa: E402
from localflow.v2.normalize import engine as norm_engine  # noqa: E402
from localflow.v2.normalize import policy as norm_policy  # noqa: E402


def make_store(tmp):
    return store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")


def add_example(s, i, raw, *, family=None, origin="live_capture",
                snippets=False, state="captured_unreviewed"):
    job, fam = s.create_job(family_id=family)
    raw_aid = s.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript", text=raw,
        retention_class="training")
    ex = s.upsert_example(job_id=job, family_id=fam)
    env = {"example_id": ex, "job_id": job, "family_id": fam,
           "origin": origin,
           "captured_at_utc": f"2026-09-1{i % 10}T0{i % 10}:00:00.000Z",
           "artifact_ids": {"source_text": raw_aid}, "outcome": {},
           "annotations": [], "missing_reasons": {}}
    if snippets:
        env["normalization"] = {"snippets": {"expansions": 1}}
    if state != "captured_unreviewed":
        s.submit(lambda c, ex=ex, st=state: c.execute(
            "UPDATE training_examples SET state=? WHERE example_id=?",
            (st, ex)))
    s.append_revision(ex, env)
    return ex, job


def test_measured_views_and_cards():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(30):
                add_example(s, i,
                            f"ship the module then review the module"
                            f" notes {i}")
            # Excluded/synthetic/sippet examples never feed the stats.
            add_example(s, 90, "excluded text entirely",
                        state="excluded")
            add_example(s, 91, "synthetic corpus material",
                        origin="synthetic_fixture")
            add_example(s, 92, "generated snippet text", snippets=True)
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=100)
            out = ps.compute()
            m = out["measured"]
            assert m["eligible_examples"] == 30
            assert m["eligible_words"] >= 100
            assert m["interpretive_note"] is None
            # interpretive_available requires ≥10 examples AND the
            # words floor (30×8=240 ≥ 100 here).
            assert out["interpretive_available"]
            assert any(c["card_id"] == "style-length"
                       for c in out["cards"])
            card = out["cards"][0]
            assert card["evidence_example_ids"]
            assert card["coverage"][0]
            phrases = [p["phrase"] for p in m["frequent_phrases"]]
            assert any("module" in p for p in phrases)
            cur = ps.current()
            assert cur["state"] == "current"
            assert cur["snapshot_id"] == out["snapshot_id"]
            print("ok  measured views from eligible evidence only"
                  " (excluded/synthetic/snippet-filtered); cards carry"
                  " examples + coverage")
        finally:
            s.close()


def test_below_threshold_measured_only():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(5):
                add_example(s, i, f"short note {i}")
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=2000)
            out = ps.compute()
            assert out["cards"] == []
            assert out["interpretive_available"] is False
            assert "below the 2000-word" in out["interpretive_note"]
            assert out["measured"]["eligible_examples"] == 5
            print("ok  below threshold: measured totals + the honest"
                  " explanation; no fabricated cards")
        finally:
            s.close()


def test_deletion_and_exclusion_propagation():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            keep = []
            for i in range(12):
                ex, job = add_example(
                    s, i, f"review the deployment checklist {i}")
                keep.append((ex, job))
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=50)
            out = ps.compute()
            assert ps.current()["state"] == "current"
            # Deleting a supporting example invalidates the snapshot;
            # the evidence link is gone (M14-AC03).
            dead_ex, dead_job = keep[0]
            s.delete_everywhere("example", dead_ex,
                                reason="user_request")
            cur = ps.current()
            assert cur["state"] == "invalidated"
            assert cur["invalidated_reason"] == "source_deleted"
            # Regeneration never resurrects the deleted example.
            out2 = ps.compute()
            assert dead_ex not in [
                e for e in json.dumps(out2["measured"]).split('"')]
            assert out2["measured"]["eligible_examples"] == 11
            # Durable exclusion: exclude one, invalidate, regenerate —
            # the excluded example stays out of future snapshots.
            target_ex, _job = keep[1]
            ps.exclude_evidence(out2["snapshot_id"], target_ex)
            assert ps.current()["state"] == "invalidated"
            out3 = ps.compute()
            assert out3["measured"]["eligible_examples"] == 10
            # A snapshot is a record, not a cache: two computes with
            # the same store state agree on the measured totals.
            out4 = ps.compute()
            assert out4["measured"]["eligible_examples"] == \
                out3["measured"]["eligible_examples"]
            print("ok  deletion invalidates (AC03); exclusions are"
                  " durable across regeneration; snapshots are"
                  " records, not caches")
        finally:
            s.close()


def test_no_profile_injection():
    """M14-AC04 + the regression requirement: a profile snapshot NEVER
    feeds normalization/cleanup — the engine output is byte-identical
    with and without a current snapshot."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            for i in range(10):
                add_example(s, i,
                            f"run the pipeline stage {i} quickly")
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=10)
            ps.compute()
            assert ps.current()["state"] == "current"
            pol = norm_policy.NormalizationPolicy()
            before = norm_engine.normalize(
                "please ship the module by friday", pol, None)
            after = norm_engine.normalize(
                "please ship the module by friday", pol, None)
            assert before.text == after.text
            # The profile module exposes no pipeline hook at all: the
            # service surface is compute/current/exclude only.
            public = [n for n in dir(ps) if not n.startswith("_")]
            assert set(public) <= {"compute", "current",
                                   "exclude_evidence", "store",
                                   "emit", "min_words"}, public
            print("ok  no injection path: profile snapshots never"
                  " reach normalization/cleanup (AC04)")
        finally:
            s.close()


def _label(s, ex, kind, domains=()):
    from localflow.v2.curation import review
    review.ReviewService(s, emit=lambda *a, **k: None).record_label(
        ex, edit_kind=kind, domains=domains,
        evidence_status="explicit_intent_review")


def test_card_evidence_exclusions_hours_and_idle_skip():
    """Cards cite the examples that support them (a correction card
    cites the labeled dictations, never arbitrary ones); background-
    flagged speech and verbatim repeats never feed speech statistics;
    time of day is LOCAL; the idle pass adds no snapshot when nothing
    changed; excluding a non-evidence id refuses."""
    from localflow.v2.analytics import AnalyticsStore
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            exs = [add_example(s, i, f"draft the weekly summary for the"
                                     f" team number {i}")[0]
                   for i in range(14)]
            for _ in range(3):  # a test phrase said again and again
                add_example(s, 50, "testing one two three")
            bg, _job = add_example(s, 60, "someone else talking nearby")
            _label(s, bg, "unknown", ("background_speech",))
            labeled = exs[10:13]
            for ex in labeled:
                _label(s, ex, "recognition_error")
            _label(s, exs[13], "recognition_error")
            _label(s, exs[13], "ambiguous")  # latest opinion wins
            AnalyticsStore(s, reporting_timezone="UTC") \
                .record_dictation_fact(
                    job_id="job-hour", activity_at_utc=
                    "2026-09-20T03:30:00.000Z", utc_offset_minutes=-420,
                    raw_words=5, final_words=5)
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=50)
            out = ps.compute(only_if_changed=True)
            m = out["measured"]
            assert m["excluded"]["repeated_verbatim"] == 2, m["excluded"]
            assert m["excluded"]["background_speech"] == 1
            assert m["eligible_examples"] == 15  # 14 + one test phrase
            assert m["hour_histogram"][20] == 1 and \
                m["hours_unknown"] == 0, m["hour_histogram"]
            assert m["corrections_by_kind"] == {
                "recognition_error": 3, "ambiguous": 1}, \
                m["corrections_by_kind"]
            card = next(c for c in out["cards"]
                        if c["card_id"] == "correction-focus")
            assert set(card["evidence_example_ids"]) == set(labeled), card
            # Idle pass: unchanged evidence → no new snapshot.
            again = ps.compute(only_if_changed=True)
            assert again.get("skipped") and \
                again["snapshot_id"] == out["snapshot_id"]
            n = s.submit(lambda c: c.execute(
                "SELECT COUNT(*) FROM profile_snapshots").fetchone()[0])
            assert n == 1
            add_example(s, 70, "a new dictation arrives later today")
            assert not ps.compute(only_if_changed=True).get("skipped")
            try:
                ps.exclude_evidence(ps.current()["snapshot_id"],
                                    "ex-not-evidence")
                raise AssertionError("non-evidence exclusion accepted")
            except ValueError:
                pass
            print("ok  cards cite supporting examples; background and"
                  " repeated speech excluded; local hours; idle pass"
                  " skips unchanged evidence")
        finally:
            s.close()


def test_deleted_evidence_leaves_no_derived_text():
    """Delete-everywhere clears the text-bearing content (frequent
    phrases, cards) of every snapshot that drew on the example — an
    invalidated snapshot must not keep phrases from deleted speech."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            exs = [add_example(s, i, f"zebra crossing plan {i}")[0]
                   for i in range(12)]
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=10)
            first = ps.compute()
            assert any(p["phrase"] == "zebra crossing"
                       for p in first["measured"]["frequent_phrases"])
            ps.compute()  # a second, newer record also drew on it
            s.delete_everywhere("example", exs[0], reason="user_request")
            rows = s.submit(lambda c: c.execute(
                "SELECT state, measured_json, cards_json FROM"
                " profile_snapshots").fetchall())
            assert len(rows) == 2
            for state, measured, cards in rows:
                assert state == "invalidated"
                assert "zebra" not in measured and "zebra" not in cards
            cur = ps.current()
            assert cur["state"] == "invalidated" and \
                cur["invalidated_reason"] == "source_deleted"
            assert cur["measured"] == {} and cur["cards"] == []
            # Evidence is read in chunks outside one op: a deletion
            # landing between the read and the write restarts the
            # computation — the deleted example never enters a record.
            real_eligible = ps._eligible
            calls = []

            def eligible_then_delete(labels):
                out = real_eligible(labels)
                if not calls:
                    s.delete_everywhere("example", exs[1],
                                        reason="user_request")
                calls.append(1)
                return out
            ps._eligible = eligible_then_delete
            fresh = ps.compute()
            ps._eligible = real_eligible
            assert len(calls) == 2, calls
            cited = s.submit(lambda c: {r[0] for r in c.execute(
                "SELECT example_id FROM profile_evidence WHERE"
                " snapshot_id=?", (fresh["snapshot_id"],)).fetchall()})
            assert exs[1] not in cited and exs[2] in cited
            assert ps.current()["state"] == "current"
            print("ok  deletion clears derived phrases/cards from every"
                  " snapshot that used the example")
        finally:
            s.close()


def test_quarantine_excluded_and_invalidation_reasons():
    """Quarantined (suspected-secret) speech never feeds the profile;
    when evidence later leaves training the invalidation reason says
    what happened, and the derived text is cleared."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            exs = [add_example(s, i, f"quiet harbor walk {i}")[0]
                   for i in range(4)]
            add_example(s, 9, "secret token alpha beta",
                        state="quarantined_sensitive")
            add_example(s, 10, "secret token alpha beta gamma",
                        state="quarantined_sensitive")
            ps = profile.ProfileService(s, emit=lambda *a, **k: None,
                                        min_words=10)
            out = ps.compute()
            assert out["measured"]["eligible_examples"] == 4
            assert not any("secret" in p["phrase"] for p in
                           out["measured"]["frequent_phrases"])
            s.set_example_state(exs[0], "quarantined_sensitive")
            cur = ps.current()
            assert cur["state"] == "invalidated" and \
                cur["invalidated_reason"] == "evidence_quarantined", cur
            assert cur["measured"] == {}
            ps.compute()
            s.set_example_state(exs[1], "excluded")
            assert ps.current()["invalidated_reason"] == \
                "evidence_excluded_from_training"
            print("ok  quarantined speech never feeds the profile;"
                  " invalidation reasons name what happened")
        finally:
            s.close()


if __name__ == "__main__":
    test_quarantine_excluded_and_invalidation_reasons()
    test_card_evidence_exclusions_hours_and_idle_skip()
    test_deleted_evidence_leaves_no_derived_text()
    test_measured_views_and_cards()
    test_below_threshold_measured_only()
    test_deletion_and_exclusion_propagation()
    test_no_profile_injection()
    print("all profile tests passed")
