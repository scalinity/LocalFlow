"""EV-19/EV-20 (UI halves) / M09: the Models → Training Data inspector.

Partial annotation (M09-AC05: correcting one token does not verify the
whole recording), deleted audio, correct-intent-only references kept
separate from verbatim, hidden/secure context display, persistent
pin/exclusion, delete-everywhere, and accurate incomplete-data display
(M09-AC06). All data synthetic.

Run: .venv/bin/python tests/v2/ui/test_training_data.py
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.store import Store  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402


class Env:
    """A temp store with synthetic captured examples built the way the
    live collector leaves them (envelope + lease-governed artifacts)."""

    def __init__(self, now_fn=None):
        self._now_fn = now_fn

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.store = Store(self.tmp / "v2.db",
                           artifacts_dir=self.tmp / "arts",
                           backup_dir=self.tmp / "bk",
                           now_fn=self._now_fn or __import__("time").time)
        self.events = []
        self.svc = TrainingDataService(
            self.store, emit=lambda *a, **k: self.events.append((a, k)))
        return self

    def __exit__(self, *exc):
        self.store.close()
        self._tmp.cleanup()

    def add_example(self, raw="clod code deployed friday",
                    applied="Clod code deployed Friday.",
                    with_audio=True, context_block=None,
                    extra_missing=None, captured="2026-09-22T10:00:00.000Z"):
        job_id, family_id = self.store.create_job(
            captured_at_utc=captured, time_quality="known",
            state="insertion_unverified")
        raw_id = self.store.write_text_artifact(
            job_id=job_id, stage="asr", role="raw_transcript",
            text=raw, retention_class="training")
        applied_id = self.store.write_text_artifact(
            job_id=job_id, stage="cleanup", role="applied_output",
            text=applied, retention_class="training",
            parent_artifact_id=raw_id)
        self.store.grant_lease(raw_id, "training", days=30)
        self.store.grant_lease(applied_id, "training", days=30)
        audio_id = None
        if with_audio:
            audio_id = self.store.write_audio_artifact(
                job_id=job_id, stage="capture",
                samples=np.linspace(-0.5, 0.5, 16000).astype(np.float32),
                sample_rate=16000)
            self.store.grant_lease(audio_id, "training", days=30)
        example_id = self.store.upsert_example(
            job_id=job_id, family_id=family_id)
        envelope = {
            "training_schema_version": 1,
            "example_id": example_id,
            "revision_id": None,
            "job_id": job_id,
            "family_id": family_id,
            "attempt": 1,
            "origin": "live_capture",
            "task_kind": "dictation",
            "captured_at_utc": captured,
            "time_quality": "known",
            "consent_revision_id": "consent-1",
            "capture": {"device": "synthetic", "sample_rate": 16000},
            "recognition": {"model_id": "synthetic"},
            "artifact_ids": {"source_text": raw_id,
                             "applied_output": applied_id,
                             "original_audio": audio_id},
            "missing_reasons": {"normalization": "not_captured_at_stage",
                                **(extra_missing or {})},
            "context": context_block,
            "cleanup": {"passes": [], "applied_path": "llm"},
            "outcome": {"insertion": "posted_unverified",
                        "correctness": "unreviewed"},
            "annotations": [],
            "state": "captured_unreviewed",
        }
        self.store.append_revision(example_id, envelope)
        return example_id


def test_span_correction_is_partial():
    """M09-AC05: a span correction appends a versioned annotation with
    explicit partial coverage; the whole-example correctness is NOT
    touched by correcting one token."""
    with Env() as e:
        ex = e.add_example()
        before = e.svc.example_detail(ex)
        assert before["correctness"] == "unreviewed"
        # "clod" is code points [0,4) of the raw text.
        ann_id = e.svc.add_span_correction(
            ex, "source_text", 0, 4, "Claude")
        detail = e.svc.example_detail(ex)
        assert detail["correctness"] == "unreviewed", \
            "correcting one token must not verify the whole recording"
        ann = detail["annotations"][-1]
        assert ann["kind"] == "span_correction"
        assert ann["coverage"] == "partial"
        assert ann["span"] == [0, 4]
        assert ann["annotation_id"] == ann_id
        # The correction payload is a lease-governed artifact; the
        # envelope entry is content-free.
        art = e.store.artifact(ann["artifact_id"])
        assert art["role"] == "span_correction"
        assert "Claude" not in json.dumps(ann)
        # Versioned: a new revision with the previous one as parent.
        chain = detail["revision_chain"]
        assert len(chain) == 2
        assert chain[1]["parent_revision_id"] == chain[0]["revision_id"]
        assert detail["state"] == "annotated"
        # Out-of-range spans refuse.
        try:
            e.svc.add_span_correction(ex, "source_text", 0, 9999, "x")
            raise AssertionError("bad span accepted")
        except ValueError:
            pass
        print("ok  AC05: span correction partial + versioned; correctness"
              " untouched")


def test_verbatim_requires_listening_and_separates_intended():
    """E14/EV-20: verbatim needs listened audio; an intention-only
    correct mark never becomes an audio-reviewed verbatim reference."""
    with Env() as e:
        ex = e.add_example()
        try:
            e.svc.set_verbatim(ex, "Clod code deployed Friday.",
                               listened_audio=False)
            raise AssertionError("verbatim saved without listening")
        except ValueError as err:
            assert "listen_before_verbatim" in str(err)
        # Correct-intent-only reference first.
        e.svc.mark_intended(ex, correct=True)
        detail = e.svc.example_detail(ex)
        assert detail["correctness"] == "correct"
        assert detail["outcome"]["correctness_provenance"] == \
            "user_explicit_intended_writing"
        assert detail["annotations"] == [], \
            "an intended mark is not a verbatim annotation"
        # Now a real audio-reviewed verbatim, after listening.
        e.svc.set_verbatim(ex, "clod code deployed friday",
                           listened_audio=True)
        detail = e.svc.example_detail(ex)
        verbatim = [a for a in detail["annotations"]
                    if a["kind"] == "verbatim_reference"]
        assert len(verbatim) == 1
        assert verbatim[0]["coverage"] == "full"
        assert verbatim[0]["listened_audio"] is True
        # The two objects stay separate: the verbatim artifact is not
        # the applied output, and the intended mark did not create one.
        art = e.store.artifact(verbatim[0]["artifact_id"])
        assert art["role"] == "verbatim_reference"
        r = e.svc.readiness()
        assert r["dataset_coverage"]["verbatim_reviewed_examples"] == 1
        assert r["dataset_coverage"]["intended_writing_marked"] == 1
        assert r["dataset_coverage"]["explicitly_correct"] == 1
        print("ok  verbatim gated on listening; intended-only kept"
              " separate")


def test_deleted_audio_downgrades_availability():
    """EV-19 UI: deleted audio reports unavailable with a reason; the
    example remains inspectable (text-side) — no fabricated replay."""
    with Env() as e:
        ex = e.add_example()
        detail = e.svc.example_detail(ex)
        assert detail["audio"]["available"] is True
        audio_id = detail["audio"]["artifact_id"]
        # Purge just the audio (delete_everywhere on the artifact via
        # the store's purge path through delete of the example is too
        # broad; simulate retention expiry of the audio payload).
        e.store.submit(lambda conn: conn.execute(
            "UPDATE artifacts SET purged=1, content_path=NULL,"
            " content_text=NULL WHERE artifact_id=?", (audio_id,)))
        (e.tmp / "arts" / f"{audio_id}.wav").unlink(missing_ok=True)
        detail = e.svc.example_detail(ex)
        assert detail["audio"] == {"available": False,
                                   "reason": "purged"}
        assert detail["stages"][0]["available"] is True  # raw text kept
        r = e.svc.readiness()
        assert r["dataset_coverage"]["retained_audio_examples"] == 0
        print("ok  deleted audio → honest unavailable; text stays")


def test_secure_context_displayed_content_free():
    """EV-19 UI: an example whose destination was a secure field shows
    the recorded omission reason only — no field content anywhere."""
    with Env() as e:
        ex = e.add_example(context_block={
            "hint_set": {"hint_set_id": "hs-1", "offered_terms": 2},
            "destination": {
                "app_bundle": "com.example.bank",
                "app_name": "BankApp",
                "category": "finance",
                "field_classification": "secure",
                "field_omission_reason": "secure_field",
                "retained": True,
            },
        })
        detail = e.svc.example_detail(ex)
        ctx = detail["context_block"]
        assert ctx["present"] is True
        dest = ctx["destination"]
        assert dest["field_classification"] == "secure"
        assert dest["field_omission_reason"] == "secure_field"
        blob = json.dumps(detail)
        assert "password" not in blob and "secret" not in blob
        print("ok  secure destination shows its omission reason only")


def test_incomplete_data_display():
    """EV-19: missing field families are surfaced with reasons (the
    context payload not retained case), never silently dropped."""
    with Env() as e:
        ex = e.add_example(context_block={
            "hint_set": None,
            "hint_set_missing_reason": "not_captured_at_stage",
            "destination": {
                "app_bundle": "com.example.app", "retained": False,
                "retention_reason":
                    "training_context_retention_disabled",
            },
        }, extra_missing={"context_snapshot_payload":
                          "consent_disabled"})
        detail = e.svc.example_detail(ex)
        assert detail["missing_reasons"][
            "context_snapshot_payload"] == "consent_disabled"
        ctx = detail["context_block"]
        assert ctx["destination"]["retained"] is False
        assert ctx["destination"]["retention_reason"] == \
            "training_context_retention_disabled"
        assert "normalization" in detail["missing_reasons"]
        print("ok  incomplete-data display carries reasons")


def test_pin_scopes_away_annotation_leases():
    """Review regression: annotation payload leases are review
    retention, not user pins — unpinning must never revoke them, and an
    annotated example must not display as user-pinned."""
    with Env() as e:
        ex = e.add_example()
        e.svc.set_verbatim(ex, "clod code deployed friday",
                           listened_audio=True)
        detail = e.svc.example_detail(ex)
        assert detail["pinned"] is False, \
            "an annotation is review retention, not a pin"
        # A user pin on top; unpin removes only the pin.
        e.svc.pin(ex, True)
        assert e.svc.example_detail(ex)["pinned"] is True
        e.svc.pin(ex, False)
        detail = e.svc.example_detail(ex)
        assert detail["pinned"] is False
        ann = detail["annotations"][-1]
        lease_live = e.store.submit(lambda conn: conn.execute(
            "SELECT COUNT(*) FROM artifact_leases WHERE artifact_id=?"
            " AND revoked_at_utc IS NULL AND expires_at_utc IS NULL",
            (ann["artifact_id"],)).fetchone()[0])
        assert lease_live == 1, "unpin revoked the annotation lease"
        # The annotation payload survives a buffer-expiry pass (reviewed
        # evidence is retained until explicitly removed, S29.14).
        real_now = e.store.now_fn
        e.store.now_fn = lambda: dt.datetime(
            2026, 10, 1, tzinfo=dt.timezone.utc).timestamp()
        try:
            e.store.prune_training()
        finally:
            e.store.now_fn = real_now
        art = e.store.artifact(ann["artifact_id"])
        assert art["purged"] == 0, "review-retained payload was evicted"
    print("ok  pin scoped to user pins; annotation retention survives")


def test_exclude_restore_refuses_terminal_states():
    with Env() as e:
        ex = e.add_example()
        e.svc.exclude(ex, True)
        assert e.svc.example_detail(ex)["state"] == "excluded"
        assert e.svc.exclude(ex, False) == "captured_unreviewed"
        # An expired example must not be silently re-eligibled.
        e.store.set_example_state(ex, "expired")
        assert e.svc.exclude(ex, False) == "expired"
        e.store.set_example_state(ex, "quarantined_sensitive")
        assert e.svc.exclude(ex, False) == "quarantined_sensitive"
    print("ok  exclude restore refuses expired/quarantined states")


def test_persistent_pin_and_exclusion():
    """EV-19/EV-20: a pinned example survives the 30-day buffer expiry;
    exclusion persists and stays out of the eligible population."""
    past = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp()
    with Env(now_fn=lambda: past) as e:
        ex_keep = e.add_example(captured="2026-08-01T10:00:00.000Z")
        ex_drop = e.add_example(captured="2026-08-01T11:00:00.000Z")
        e.svc.pin(ex_keep, True)
        assert e.svc.example_detail(ex_keep)["pinned"] is True
        # Buffer expiry far in the future of the captured dates.
        far = dt.datetime(2026, 10, 1,
                          tzinfo=dt.timezone.utc).timestamp()
        e.store.prune_training(now=far)
        states = {r["example_id"]: r["state"]
                  for r in e.svc.examples()}
        assert states[ex_keep] == "captured_unreviewed", "pin survived"
        assert states[ex_drop] == "expired", "unpinned expired"
        # Exclusion persists and reads honestly.
        e.svc.exclude(ex_keep, True)
        assert e.svc.example_detail(ex_keep)["state"] == "excluded"
        r = e.svc.readiness()
        assert r["examples_by_state"].get("excluded") == 1
        e.svc.exclude(ex_keep, False)  # restore → its annotations decide
        assert e.svc.example_detail(ex_keep)["state"] == \
            "captured_unreviewed"
        e.svc.pin(ex_keep, False)  # unpin revokes the pinned lease
        assert e.svc.example_detail(ex_keep)["pinned"] is False
        print("ok  pin survives expiry; exclusion persists and restores")


def test_delete_everywhere_and_inspection_without_engine():
    """M09-AC06: inspect/exclude/delete work with no training engine or
    provider anywhere; delete purges payloads and leaves a tombstone."""
    with Env() as e:
        ex = e.add_example()
        detail = e.svc.example_detail(ex)
        raw_id = detail["stages"][0]["artifact_id"]
        out = e.svc.delete_everywhere(ex)
        assert out["purged_artifacts"] >= 3
        assert e.store.artifact(raw_id)["purged"] == 1
        rows = [r for r in e.svc.examples() if r["example_id"] == ex]
        assert rows == [], "deleted example left the inspector list"
        tombs = e.store.tombstones()
        assert any(t[2] == ex for t in tombs)
        assert any(t[2] == raw_id for t in tombs), \
            "purged artifacts carry content-free tombstones"
        print("ok  AC06: delete-everywhere purges + tombstones;")


def test_readiness_triad_honest():
    with Env() as e:
        e.add_example()
        e.add_example(with_audio=False)
        r = e.svc.readiness(consent_state="enabled")
        assert r["infrastructure_ready"] is True
        assert r["observed_model_improvement"] is None
        assert r["observed_model_improvement_reason"] == \
            "post_v2_training_only"
        cov = r["dataset_coverage"]
        assert cov["retained_audio_examples"] == 1
        assert cov["unreviewed_outcomes"] == 2
        assert cov["verbatim_reviewed_examples"] == 0
        assert r["consent_state"] == "enabled"
        assert r["storage_bytes"] > 0
        print("ok  readiness separates infrastructure / coverage /"
              " improvement (improvement: post-V2)")


def test_readiness_aggregates_m13():
    """M13's E19.4 aggregates: the five outcome classes stay DISTINCT
    (AC05), every metric carries a denominator, the join coverage can
    actually fall below 100%, and not-available stays explicit — never
    a fabricated number or rate."""
    with Env() as e:
        ex1 = e.add_example()                 # audio + unreviewed
        ex2 = e.add_example(with_audio=False)  # no audio, unreviewed
        # A verified positive and a verified failure (intended marks).
        e.svc.mark_intended(ex1, True)
        e.svc.mark_intended(ex2, False)
        # An excluded example leaves the capture-completeness base but
        # stays its own class.
        e.svc.exclude(ex2)
        r = e.svc.readiness()
        balance = r["outcome_balance"]
        assert set(balance) == {"unreviewed", "verified_positive",
                                "verified_failure", "unobserved",
                                "excluded", "note"}
        assert balance["verified_positive"] == 1
        assert balance["verified_failure"] == 1
        assert balance["excluded"] == 1
        assert "never rates" in balance["note"]  # no population WER
        m = r["readiness_metrics"]
        # Denominators present and honest.
        assert m["capture_completeness"]["denominator"] == 1  # live only
        assert m["exact_audio_join_coverage"]["denominator"] == 1
        assert m["exact_audio_join_coverage"]["joined"] == 1
        assert "definition" in m["exact_audio_join_coverage"]
        # A dangling audio id (envelope names an id with no row) lowers
        # the join coverage — never a tautological 100%.
        import json as _json
        def _dangle(db):
            db.execute(
                "UPDATE training_revisions SET envelope_json=? WHERE"
                " example_id=(SELECT example_id FROM training_revisions"
                " ORDER BY rowid DESC LIMIT 1)",
                (_json.dumps({
                    "example_id": "ex-dangle", "job_id": "job-dangle",
                    "family_id": "fam-dangle",
                    "artifact_ids": {"original_audio":
                                     "art-does-not-exist"},
                    "outcome": {"correctness": "unreviewed"}}),))
        e.store.submit(_dangle)
        r2 = e.svc.readiness()
        j = r2["readiness_metrics"]["exact_audio_join_coverage"]
        assert j["denominator"] == 2 and j["joined"] == 1, j
        # Task eligibility: separate definitions, never merged.
        for key in ("asr_supervised", "cleanup_supervised",
                    "transform_supervised", "preference_pairs"):
            assert "definition" in m["task_eligibility"][key]
        # Not-available stays explicit; nearing-expiry is null, not 0.
        na = m["not_available"]
        assert na["split_contamination"] == "not_available_until_m14"
        assert na["comparator_coverage"] == "not_available_until_m15"
        assert na["population_wer"] == "no_references_no_population_claims"
        assert m["retention_health"]["nearing_expiry"] is None
        print("ok  M13 readiness aggregates: five classes, denominators,"
              " honest join coverage, explicit not-available")


def test_examples_text_search():
    with Env() as e:
        e.add_example(raw="alpha synthetic", applied="Alpha synthetic.")
        e.add_example(raw="beta synthetic", applied="Beta synthetic.")
        rows = e.svc.examples(text="alpha")
        assert len(rows) == 1
        assert rows[0]["families"]  # completeness summary populated
        print("ok  evidence text search over retained artifacts")


def test_replay_service_over_real_store():
    """ReplayService over a real store artifact: availability reasons,
    one-at-a-time playback (S19), and the in-memory PCM16 rendering."""
    from localflow.v2.ui.replay import ReplayService, pcm16_wav_bytes
    sounds = []

    class Sound:
        def __init__(self, data):
            self.data = data
            self.stopped = False

        def play(self):
            sounds.append(self)
            return True

        def stop(self):
            self.stopped = True

        def isPlaying(self):
            return False

    replay = ReplayService(sound_factory=Sound)
    with Env() as e:
        ex = e.add_example()
        audio_id = e.svc.example_detail(ex)["audio"]["artifact_id"]
        # pcm16 rendering: 44-byte RIFF header + 1600 samples × 2 bytes.
        import numpy as np
        blob = pcm16_wav_bytes(np.zeros(1600, dtype=np.float32), 16000)
        assert len(blob) == 44 + 3200 and blob[:4] == b"RIFF"
        out = replay.play_artifact(e.store, audio_id)
        assert out["status"] == "playing"
        out2 = replay.play_artifact(e.store, audio_id)
        assert out2["status"] == "playing"
        assert len(sounds) == 2
        assert sounds[0].stopped, "new replay stopped the previous item"
        # Missing/purged audio reports honest reasons.
        assert replay.availability(e.store, None) == {
            "available": False, "reason": "no_audio_artifact"}
        e.store.submit(lambda conn: conn.execute(
            "UPDATE artifacts SET purged=1, content_path=NULL WHERE"
            " artifact_id=?", (audio_id,)))
        assert replay.availability(e.store, audio_id) == {
            "available": False, "reason": "purged"}
    print("ok  replay: one-at-a-time, honest reasons, PCM16 rendering")


if __name__ == "__main__":
    test_span_correction_is_partial()
    test_verbatim_requires_listening_and_separates_intended()
    test_deleted_audio_downgrades_availability()
    test_secure_context_displayed_content_free()
    test_incomplete_data_display()
    test_pin_scopes_away_annotation_leases()
    test_exclude_restore_refuses_terminal_states()
    test_persistent_pin_and_exclusion()
    test_delete_everywhere_and_inspection_without_engine()
    test_readiness_triad_honest()
    test_examples_text_search()
    test_replay_service_over_real_store()
    print("all training data inspector tests passed")
