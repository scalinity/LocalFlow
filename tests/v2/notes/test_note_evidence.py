"""EV-19/EV-20 producer cases + M12-AC05 (Spec S20/S29.8/S29.14).

The note family through the real EvidenceCollector: mixed typed/dictated
notes, restored versions, changed regions, deleted notes and deleted
attachments. The boundary discipline: note revisions are local
observations — they never mint training examples, never label typed
additions as dictated speech, never duplicate dictated-word counts, and
deletion propagates to the evidence references (the note_evidence_links
close with a final content-free observation).

Run: .venv/bin/python tests/v2/notes/test_note_evidence.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod, training  # noqa: E402
from localflow.v2.notes import (NoteStore, ORIGIN_ATTACHMENT,  # noqa: E402
                                ORIGIN_CREATED, ORIGIN_DICTATED,
                                ORIGIN_RESTORE, ORIGIN_TRANSFORM,
                                ORIGIN_TYPED, TRIGGER_AUTOSAVE,
                                TRIGGER_EXPLICIT, TRIGGER_SYSTEM)


def make(tmp, collecting=True):
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    emits = []

    def emit(name, **kw):
        emits.append((name, kw))

    consent = training.ConsentManager(s, emit)
    if collecting:
        consent.set("enabled")
    collector = training.EvidenceCollector(
        s, emit, consent, pipeline_info=lambda: {})
    ns = NoteStore(s, on_evidence=collector.on_note_revision)
    return s, ns, collector, consent, emits


def seed_example(s, job_id):
    job_id, fam = (job_id, None) if job_id.startswith("job-seed") else \
        s.create_job(captured_at_utc="2026-09-23T07:00:00.000Z",
                     state="insertion_confirmed")
    ex = s.upsert_example(job_id=job_id, family_id=fam or "fam-x")
    s.append_revision(ex, {
        "example_id": ex, "job_id": job_id, "family_id": fam or "fam-x",
        "task_kind": "dictation", "origin": "live_capture",
        "artifact_ids": {}, "missing_reasons": {},
        "outcome": {"correctness": "unreviewed"}, "annotations": []})
    return job_id, ex


def notes_of(s, ex):
    latest = s.latest_revision(ex) or {}
    return latest.get("notes") or []


def test_arrival_links_and_content_free():
    with tempfile.TemporaryDirectory() as td:
        s, ns, collector, _consent, emits = make(pathlib.Path(td))
        try:
            job_id, ex = seed_example(s, "job-arr-1")
            out = ns.create_note("the dictated opening", origin=ORIGIN_CREATED)
            ns.append_revision(
                out["note_id"], "the dictated opening plus typed tail",
                origin=ORIGIN_DICTATED, trigger=TRIGGER_SYSTEM,
                source_job_id=job_id, inserted_at_chars=0,
                inserted_text="the dictated opening")
            obs = notes_of(s, ex)
            assert len(obs) == 1 and obs[0]["kind"] == \
                "note_region_arrival"
            assert obs[0]["asr_example"] is False
            assert obs[0]["evidence_status"] == \
                "reliable_target_observation"
            # Content-free: no note text anywhere in the envelope.
            env_text = json.dumps(s.latest_revision(ex))
            for forbidden in ("dictated opening", "typed tail"):
                assert forbidden not in env_text, "note text leaked"
            # The link exists and is open.
            link = s.submit(lambda db: db.execute(
                "SELECT closed_utc FROM note_evidence_links WHERE"
                " note_id=? AND example_id=?",
                (out["note_id"], ex)).fetchone())
            assert link is not None and link[0] is None
            # No new example, no new job — one logical dictation only.
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM training_examples").fetchone()
            )[0] == 1
        finally:
            s.close()
    print("ok  arrival links the example; envelope stays content-free")


def test_repeated_revisions_no_duplicates():
    """M12-AC05: repeated saved versions of the same dictated content
    create no duplicate dictated-word counts and no false ASR
    examples; typed additions are never labeled dictated speech."""
    with tempfile.TemporaryDirectory() as td:
        s, ns, collector, _c, _e = make(pathlib.Path(td))
        try:
            job_id, ex = seed_example(s, "job-rep-1")
            out = ns.create_note("draft sentence", origin=ORIGIN_CREATED)
            ns.append_revision(
                out["note_id"], "draft sentence", origin=ORIGIN_DICTATED,
                trigger=TRIGGER_SYSTEM, source_job_id=job_id,
                inserted_at_chars=0, inserted_text="draft sentence")
            examples_after_arrival = s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM training_examples").fetchone())[0]
            # Autosave the SAME content repeatedly plus typed edits
            # elsewhere in the note.
            for i in range(5):
                ns.append_revision(
                    out["note_id"],
                    f"draft sentence typed filler {i}",
                    origin=ORIGIN_TYPED, trigger=TRIGGER_AUTOSAVE)
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM training_examples").fetchone()
            )[0] == examples_after_arrival, "examples duplicated"
            obs = notes_of(s, ex)
            assert len(obs) == 1, \
                f"repeated/typed revisions spammed observations: {obs}"
            # The word counts of the note never feed usage analytics:
            # no usage_facts/daily aggregates exist for notes at all.
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                " AND name IN ('usage_facts','daily_aggregates')"
            ).fetchone())[0] == 0  # M13 owns those tables
            # Typed additions carry no source_job_id and no dictated
            # span: the last revision's spans are exactly the dictated
            # region.
            note = ns.open_note(out["note_id"])
            assert note["revision"]["spans"], "dictated span lost"
            assert all(sp[2] == ORIGIN_DICTATED
                       for sp in note["revision"]["spans"])
        finally:
            s.close()
    print("ok  AC05: repeated revisions duplicate nothing; typed stays"
          " typed")


def test_edited_region_and_restore_observations():
    with tempfile.TemporaryDirectory() as td:
        s, ns, collector, _c, _e = make(pathlib.Path(td))
        try:
            job_id, ex = seed_example(s, "job-edit-1")
            out = ns.create_note("fix this wrogn word", origin=ORIGIN_DICTATED,
                                 source_job_id=job_id)
            base = ns.open_note(out["note_id"])
            # A typed edit touching the dictated region -> a local
            # correction OBSERVATION (candidate, never a label).
            ns.append_revision(
                out["note_id"], "fix this wrong word",
                origin=ORIGIN_TYPED, trigger=TRIGGER_EXPLICIT)
            kinds = [o["kind"] for o in notes_of(s, ex)]
            assert kinds == ["note_region_arrival", "note_region_edited"], \
                kinds
            edited = [o for o in notes_of(s, ex)
                      if o["kind"] == "note_region_edited"][0]
            assert edited["origin"] == ORIGIN_TYPED
            assert edited["asr_example"] is False
            assert edited["edited_spans"] == [
                {"origin": ORIGIN_DICTATED, "words_before": 4}]
            # The example's own correctness label is untouched.
            assert (s.latest_revision(ex).get("outcome") or {}).get(
                "correctness") == "unreviewed"
            # A restore (changed intent candidate for M14) records its
            # own observation; classification stays M14's job.
            ns.restore(out["note_id"], base["current_revision_id"])
            kinds = [o["kind"] for o in notes_of(s, ex)]
            assert kinds[-1] == "note_region_restored", kinds
        finally:
            s.close()
    print("ok  local correction + restore observations, never labels")


def test_deletion_propagates_to_evidence():
    with tempfile.TemporaryDirectory() as td:
        s, ns, collector, _c, emits = make(pathlib.Path(td))
        try:
            job_id, ex = seed_example(s, "job-del-1")
            out = ns.create_note("note with attachment", origin=ORIGIN_DICTATED,
                                 source_job_id=job_id)
            att = ns.add_attachment(out["note_id"], b"IMG", "image/png",
                                    "i.png")
            ns.append_revision(
                out["note_id"],
                f"note with attachment ![i](attachment:{att['attachment_id']})",
                origin=ORIGIN_ATTACHMENT, trigger=TRIGGER_EXPLICIT)
            payload = ns.delete_note(out["note_id"])
            assert payload["closed_examples"], "links not reported"
            # Attachment deletion propagated (payload purged with the
            # note) — recorded in the deletion payload.
            assert payload["purged_attachments"] == 1
            collector.on_note_deleted(payload)
            kinds = [o["kind"] for o in notes_of(s, ex)]
            assert kinds[-1] == "note_deleted", kinds
            assert notes_of(s, ex)[-1]["asr_example"] is False
            # The link is closed with the reason.
            closed = s.submit(lambda db: db.execute(
                "SELECT closed_utc, close_reason FROM"
                " note_evidence_links").fetchone())
            assert closed[0] is not None and \
                closed[1] == "note_deleted"
            # The mined note text is gone (revisions blanked) — the
            # observations remain as the content-free record.
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM note_revisions WHERE note_id=? AND"
                " purged=0", (out["note_id"],)).fetchone())[0] == 0
            # The example itself survives (deleting a note deletes the
            # note's references, not the dictation).
            assert s.submit(lambda db: db.execute(
                "SELECT state FROM training_examples WHERE example_id=?",
                (ex,)).fetchone())[0] == "captured_unreviewed"
        finally:
            s.close()
    print("ok  deletion closes evidence references; content purged")


def test_consent_off_collects_nothing():
    with tempfile.TemporaryDirectory() as td:
        s, ns, collector, consent, _e = make(pathlib.Path(td),
                                             collecting=False)
        try:
            job_id, ex = seed_example(s, "job-off-1")
            out = ns.create_note("nothing observed", origin=ORIGIN_DICTATED,
                                 source_job_id=job_id)
            assert notes_of(s, ex) == [], "observed without consent"
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM note_evidence_links").fetchone()
            )[0] == 0
            # The note itself still works (consent gates evidence, not
            # the product).
            assert ns.open_note(out["note_id"])["revision"]["content"] == \
                "nothing observed"
        finally:
            s.close()
    print("ok  consent off: no observations, product unaffected")


if __name__ == "__main__":
    test_arrival_links_and_content_free()
    test_repeated_revisions_no_duplicates()
    test_edited_region_and_restore_observations()
    test_deletion_propagates_to_evidence()
    test_consent_off_collects_nothing()
    print("all note evidence tests passed")
