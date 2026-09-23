"""EV-14 / M12: the note store (Spec S20/S08, schema v8).

Immutable parent-linked revisions with origin/trigger tags, version
restore that discards nothing (M12-AC02), the unsaved-tail-risk marker
(M12-AC01), managed attachment lifecycle, pinning, local search with
LIKE escaping, deletion that purges payloads and closes evidence
links, and the additive/idempotent v8 migration over a v7 database.

Run: .venv/bin/python tests/v2/notes/test_note_store.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.notes import (NoteStore, attachment_ids,  # noqa: E402
                                ORIGIN_ATTACHMENT, ORIGIN_CREATED,
                                ORIGIN_DICTATED, ORIGIN_RESTORE,
                                ORIGIN_TRANSFORM, ORIGIN_TYPED,
                                TRIGGER_AUTOSAVE, TRIGGER_EXPLICIT,
                                TRIGGER_SYSTEM, rebase_spans)


def make_store(tmp, **kw):
    kw.setdefault("backup_dir", tmp / "backups")
    return store_mod.Store(tmp / "v2.db", **kw)


def test_migration_v8_additive_and_repair():
    """v8 is additive over a v7 database, idempotent, and the v8 tables
    join the torn-write repair set."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        db = tmp / "v2.db"
        # Build a v7-shaped database by hand (the M11 schema), then
        # open it with the current store: the migration must be v7→v8.
        import sqlite3
        pre = sqlite3.connect(db)
        # A GENUINE v7 database: the real v1–v7 DDL, version stamped 7
        # (a hand-shaped stand-in would be malformed in ways the
        # idempotent repair DDL legitimately cannot fix).
        for v in range(1, 8):
            for stmt in store_mod._MIGRATIONS[v]:
                pre.execute(stmt)
        pre.execute(
            "INSERT OR REPLACE INTO schema_meta"
            " VALUES('schema_version','7')")
        pre.commit()
        pre.close()
        backup_before = tmp / "backups"
        s = make_store(tmp, backup_dir=backup_before)
        try:
            assert s.submit(lambda db: db.execute(
                "SELECT value FROM schema_meta WHERE"
                " key='schema_version'").fetchone())[0] == "8"
            for table in ("notes", "note_revisions", "note_attachments",
                          "note_evidence_links"):
                assert s.submit(lambda db, t=table: db.execute(
                    f"SELECT 1 FROM sqlite_master WHERE type='table'"
                    f" AND name=?", (t,)).fetchone()), table
            # notes_meta was cut in review (dead schema — nothing
            # reads it; the minimalism rule).
            assert not s.submit(lambda db: db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND"
                " name='notes_meta'").fetchone())
            assert s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM transforms").fetchone())[0] == 0
            assert any(backup_before.glob("v2-pre-migrate-*.db")), \
                "no pre-migration backup taken"
            # v1–v7 data survives verbatim (a real v7 row).
            s.submit(lambda db: db.execute(
                "INSERT INTO transforms(transform_id, name, mode, origin,"
                " description, prompt, edit_types_json, examples_json,"
                " shortcut, target_profiles_json, auto_apply, enabled,"
                " revision, usage_count, source_locator, legacy_key,"
                " created_at_utc, updated_at_utc)"
                " VALUES('t1','T','custom','user','','', '[]','[]',NULL,"
                "'[]',0,1,1,0,NULL,NULL,'2026-01-01T00:00:00.000Z',"
                "'2026-01-01T00:00:00.000Z')"))
            # Idempotent: a second Store over the same db re-runs
            # nothing and repairs nothing.
            s2 = make_store(tmp, backup_dir=backup_before)
            try:
                assert s2.submit(lambda db: db.execute(
                    "SELECT value FROM schema_meta WHERE"
                    " key='schema_version'").fetchone())[0] == "8"
                assert s2.submit(lambda db: db.execute(
                    "SELECT COUNT(*) FROM transforms").fetchone())[0] == 1
            finally:
                s2.close()
        finally:
            s.close()
        # Torn-write repair: drop the v8 tables, reopen — the repair
        # path re-creates them from the idempotent DDL.
        post = sqlite3.connect(db)
        for t in ("notes", "note_revisions", "note_attachments",
                  "note_evidence_links"):
            post.execute(f"DROP TABLE IF EXISTS {t}")
        post.commit()
        post.close()
        s3 = make_store(tmp, backup_dir=backup_before)
        try:
            assert s3.submit(lambda db: db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND"
                " name='notes'").fetchone()), "v8 tables not repaired"
        finally:
            s3.close()
    print("ok  v8 migration additive/idempotent over v7; repair set")


def test_revisions_immutable_parent_linked():
    with tempfile.TemporaryDirectory() as td:
        s = make_store(pathlib.Path(td))
        try:
            ns = NoteStore(s)
            out = ns.create_note("# Title\n\nbody")
            note_id = out["note_id"]
            r2 = ns.append_revision(
                note_id, "# Title\n\nbody two", origin=ORIGIN_TYPED,
                trigger=TRIGGER_AUTOSAVE)
            r3 = ns.append_revision(
                note_id, "# Title\n\nbody two three", origin=ORIGIN_TYPED,
                trigger=TRIGGER_EXPLICIT)
            assert r2["parent_revision_id"] == out["revision"]
            assert r3["parent_revision_id"] == r2["revision_id"]
            # Appending never mutates an earlier revision: the chain is
            # immutable by construction — every revision's content is
            # still readable and byte-identical.
            assert ns.revision_content(out["revision"]) == \
                "# Title\n\nbody"
            assert ns.revision_content(r2["revision_id"]) == \
                "# Title\n\nbody two"
            detail = ns.open_note(note_id)
            assert detail["revision"]["content"] == \
                "# Title\n\nbody two three"
            assert [v["origin"] for v in reversed(
                detail["versions"])] == ["created", "typed", "typed"]
            assert [v["trigger"] for v in reversed(
                detail["versions"])] == ["system", "autosave",
                                         "explicit"]
            assert detail["title"] == "Title"
            # Unknown origin/trigger refuse at write time.
            for bad in ({"origin": "dictated-ish",
                         "trigger": TRIGGER_SYSTEM},
                        {"origin": ORIGIN_TYPED, "trigger": "lazy"}):
                try:
                    ns.append_revision(note_id, "x", **bad)
                    raise AssertionError("bad revision accepted")
                except ValueError:
                    pass
        finally:
            s.close()
    print("ok  revisions immutable, parent-linked, origin/trigger gated")


def test_restore_copies_forward_nothing_discarded():
    """M12-AC02: restoring an earlier version creates a NEW revision
    with the old content; the current one stays in the chain."""
    with tempfile.TemporaryDirectory() as td:
        s = make_store(pathlib.Path(td))
        try:
            ns = NoteStore(s)
            out = ns.create_note("v1 text")
            r2 = ns.append_revision(
                out["note_id"], "v1 text v2", origin=ORIGIN_TYPED,
                trigger=TRIGGER_EXPLICIT)
            r3 = ns.restore(out["note_id"], out["revision"])
            assert r3["origin"] == ORIGIN_RESTORE
            assert r3["restore_of"] == out["revision"]
            assert r3["parent_revision_id"] == r2["revision_id"]
            detail = ns.open_note(out["note_id"])
            assert detail["revision"]["content"] == "v1 text"
            assert any(v["revision_id"] == r2["revision_id"]
                       for v in detail["versions"]), \
                "the superseded revision was discarded"
            assert ns.revision_content(r2["revision_id"]) == "v1 text v2"
            # Restoring a foreign revision refuses.
            try:
                ns.restore(out["note_id"], "nrev-nope")
                raise AssertionError("foreign restore accepted")
            except KeyError:
                pass
        finally:
            s.close()
    print("ok  AC02: restore copies forward; nothing silently discarded")


def test_unsaved_tail_risk_marker():
    """M12-AC01: a forced interruption restores the last persisted
    version and IDENTIFIES the unsaved tail risk."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            ns = NoteStore(s)
            out = ns.create_note("saved body")
            assert ns.open_note(out["note_id"])["unsaved_tail_risk"] \
                is None
            # A burst of typing begins (the editor arms the marker on
            # the FIRST edit) and the process dies before autosave.
            ns.mark_dirty(out["note_id"])
            detail = ns.open_note(out["note_id"])
            risk = detail["unsaved_tail_risk"]
            assert risk is not None and \
                risk["editing_started_utc"] is not None and \
                risk["last_saved_words"] == len("saved body".split())
            assert detail["revision"]["content"] == "saved body", \
                "reopen must restore the last persisted version"
            # The next persisted revision clears the marker.
            ns.append_revision(out["note_id"], "saved body typed tail",
                               origin=ORIGIN_TYPED,
                               trigger=TRIGGER_AUTOSAVE)
            assert ns.open_note(out["note_id"])["unsaved_tail_risk"] \
                is None
        finally:
            s.close()
    print("ok  AC01: reopen restores last persisted + names tail risk")


def test_attachments_managed_lifecycle():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = make_store(tmp)
        try:
            ns = NoteStore(s)
            out = ns.create_note("note with an image")
            note_id = out["note_id"]
            att = ns.add_attachment(note_id, b"\x89PNG-fake-bytes",
                                    "image/png", "screen shot.png")
            marker = att["marker"]
            assert attachment_ids(marker) == [att["attachment_id"]]
            # Managed private storage: 0700 dir, 0600 file, inside the
            # app-support tree (never the repo).
            import os
            assert str(ns.attachments_dir).startswith(str(tmp))
            assert oct(os.stat(ns.attachments_dir).st_mode & 0o777) \
                == "0o700"
            payload_path = ns.attachments_dir / \
                f"{att['attachment_id']}.png"
            assert oct(os.stat(payload_path).st_mode & 0o777) == "0o600"
            assert ns.attachment_payload(att["attachment_id"]) == \
                b"\x89PNG-fake-bytes"
            # The content references the attachment; deleting the note
            # propagates to it (payload purged, file unlinked).
            ns.append_revision(note_id, f"note with an image\n\n{marker}",
                               origin=ORIGIN_ATTACHMENT,
                               trigger=TRIGGER_EXPLICIT)
            d = ns.delete_note(note_id)
            assert d["purged_attachments"] == 1
            assert not payload_path.exists()
            assert ns.attachment_payload(att["attachment_id"]) is None
            # Individual attachment deletion (row purged + unlinked).
            out2 = ns.create_note("second")
            att2 = ns.add_attachment(out2["note_id"], b"GIF-fake",
                                     "image/gif", "a.gif")
            assert ns.delete_attachment(att2["attachment_id"]) is True
            assert not (ns.attachments_dir /
                        f"{att2['attachment_id']}.gif").exists()
            assert ns.delete_attachment(att2["attachment_id"]) is False
            # An empty payload refuses honestly.
            try:
                ns.add_attachment(out2["note_id"], b"", "image/png",
                                  "x.png")
                raise AssertionError("empty attachment accepted")
            except ValueError:
                pass
        finally:
            s.close()
    print("ok  attachments: 0700/0600 managed storage, deletion purges")


def test_pinning_search_deletion_tombstones():
    with tempfile.TemporaryDirectory() as td:
        s = make_store(pathlib.Path(td))
        try:
            ns = NoteStore(s)
            a = ns.create_note("alpha needle note")
            b = ns.create_note("beta note")
            c = ns.create_note("gamma 100% _under_score_")
            ns.set_pinned(c["note_id"], True)
            rows = ns.notes()
            assert rows[0]["note_id"] == c["note_id"] and \
                rows[0]["pinned"] is True
            assert {r["note_id"] for r in ns.search("needle")} == \
                {a["note_id"]}
            # LIKE metacharacters stay literals (the History escape).
            assert {r["note_id"] for r in ns.search("100%")} == \
                {c["note_id"]}
            assert {r["note_id"] for r in ns.search("_under_score_")} == \
                {c["note_id"]}
            assert ns.search("zzz-not-there") == []
            # Deletion: revisions blanked, note row gone, tombstone.
            d = ns.delete_note(b["note_id"])
            assert d["note_id"] == b["note_id"]
            assert ns.open_note(b["note_id"]) is None
            blanks = s.submit(lambda db: db.execute(
                "SELECT COUNT(*) FROM note_revisions WHERE purged=1 AND"
                " content_text='' AND note_id=?",
                (b["note_id"],)).fetchone())[0]
            assert blanks >= 1, "revision payloads not purged on delete"
            tombs = [t for t in s.tombstones()
                     if t[1] == "note" and t[2] == b["note_id"]]
            assert tombs, "no note tombstone"
            assert ns.delete_note(b["note_id"]) is None  # idempotent
        finally:
            s.close()
    print("ok  pinning, escaped search, deletion tombstones")


def test_span_provenance_rebase():
    """Region origins survive only untouched edits; an edit touching a
    dictated/transformed region drops attribution honestly."""
    parent = "the quick brown fox jumps"
    spans = [[1, 3, "dictated"]]  # "quick brown"
    # Untouched edit later in the text: span shifts.
    keep, edited = rebase_spans(parent, spans,
                                "the quick brown fox leaps high")
    assert keep == [[1, 3, "dictated"]] and edited == []
    # Edit inside the span: attribution stops.
    keep, edited = rebase_spans(parent, spans,
                                "the QUICK brown fox jumps")
    assert keep == [] and edited == [{"origin": "dictated",
                                      "words_before": 2}]
    # Deletion of the region: attribution stops.
    keep, edited = rebase_spans(parent, spans, "the fox jumps")
    assert keep == [] and edited == [{"origin": "dictated",
                                      "words_before": 2}]
    # A dictation arrival creates the span; the transform consumes the
    # spans it replaces (verified end-to-end below).
    with tempfile.TemporaryDirectory() as td:
        s = make_store(pathlib.Path(td))
        try:
            ns = NoteStore(s)
            out = ns.create_note("intro words")
            note_id = out["note_id"]
            ns.append_revision(
                note_id, "intro words dictated tail", origin=ORIGIN_TYPED,
                trigger=TRIGGER_AUTOSAVE)
            ns.append_revision(
                note_id, "intro words dictated tail more",
                origin=ORIGIN_DICTATED, trigger=TRIGGER_SYSTEM,
                source_job_id="job-1", inserted_at_chars=12,
                inserted_text="dictated tail")
            note = ns.open_note(note_id)
            assert [s_[:2] for s_ in note["revision"]["spans"]] == \
                [[2, 4]]
            assert all(s_[2] == ORIGIN_DICTATED
                       for s_ in note["revision"]["spans"])
            # Transform replaces the dictated region: a transform span
            # replaces the dictated one.
            ns.append_revision(
                note_id, "intro words TRANSFORMED more",
                origin=ORIGIN_TRANSFORM, trigger=TRIGGER_EXPLICIT,
                task_key="ttask:x", transform_id="builtin:polish",
                transform_revision=1, inserted_at_chars=12,
                inserted_text="TRANSFORMED")
            note = ns.open_note(note_id)
            origins = sorted(s_[2] for s_ in note["revision"]["spans"])
            assert origins == [ORIGIN_TRANSFORM], \
                f"dictated span survived its own rewrite: {origins}"
        finally:
            s.close()
    print("ok  word-origin spans rebase/stop honestly across edits")


if __name__ == "__main__":
    test_migration_v8_additive_and_repair()
    test_revisions_immutable_parent_linked()
    test_restore_copies_forward_nothing_discarded()
    test_unsaved_tail_risk_marker()
    test_attachments_managed_lifecycle()
    test_pinning_search_deletion_tombstones()
    test_span_provenance_rebase()
    print("all note store tests passed")
