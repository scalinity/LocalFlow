"""The Scratchpad note workspace (V2 M12, Spec S20/S08).

Two layers over the single-writer store (schema v8):

- ``NoteStore`` — notes, immutable parent-linked revisions, managed
  image attachments, pinning, local search and deletion with evidence
  propagation. The architecture contract: a revision is NEVER mutated;
  a transform or a restore creates a new version (``restore`` copies
  the old content forward — the current revision stays in the chain,
  M12-AC02).
- ``NotesEditorModel`` — the pure-Python editor buffer (AppKit-free,
  headless-testable): debounced autosave, immediate flushes for
  dictated/transform arrivals, serialized concurrent flushes, and the
  unsaved-tail-risk marker (M12-AC01).

Region provenance (S20/S29.8): revisions carry word-origin spans
(``dictated``/``transform``) that survive only while edits leave them
untouched; an edit intersecting a span drops it and records a
content-free local-edit observation — attribution stops honestly when
it becomes unreliable. Typed additions are never labeled dictated
speech (M12-AC05): only a dictation ``source_job_id`` or a transform
``task_key`` create attributed spans.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time

from . import ids
from .store import Store

# Revision origin vocabulary (S20: preserve the distinction between
# typed additions, dictated text, snippets and transforms).
ORIGIN_CREATED = "created"
ORIGIN_TYPED = "typed"
ORIGIN_DICTATED = "dictated"
ORIGIN_TRANSFORM = "transform"
ORIGIN_SNIPPET = "snippet"
ORIGIN_RESTORE = "restore"
ORIGIN_ATTACHMENT = "attachment"
ORIGINS = (ORIGIN_CREATED, ORIGIN_TYPED, ORIGIN_DICTATED,
           ORIGIN_TRANSFORM, ORIGIN_SNIPPET, ORIGIN_RESTORE,
           ORIGIN_ATTACHMENT)

# How the revision came to be — an autosave-debounce snapshot differs
# from an explicit user snapshot (origin says WHO changed the note,
# trigger says HOW it was persisted).
TRIGGER_SYSTEM = "system"
TRIGGER_AUTOSAVE = "autosave"
TRIGGER_EXPLICIT = "explicit"
TRIGGERS = (TRIGGER_SYSTEM, TRIGGER_AUTOSAVE, TRIGGER_EXPLICIT)

# Origins that create attributed spans (everything else is typed
# content — never counted as dictated speech).
_SPAN_ORIGINS = (ORIGIN_DICTATED, ORIGIN_TRANSFORM)

_ATTACHMENT_RE = re.compile(r"!\[([^\]]*)\]\(attachment:([^)]+)\)")

_AUTOSAVE_DEBOUNCE_SEC = 1.5   # engine constant (WINDOW_MAX_WORDS
#                                  precedent), not a config knob
_TITLE_MAX = 60


def word_count(text: str) -> int:
    return len(text.split())


def derive_title(content: str) -> str:
    """First non-empty line, heading markers stripped, bounded."""
    for line in content.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:_TITLE_MAX]
    return ""


def attachment_ids(content: str) -> list[str]:
    """Attachment ids referenced by the content's inline markers."""
    return [m[1] for m in _ATTACHMENT_RE.findall(content)]


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- region spans (word-offset, origin-tagged) ---------------------------

def _words(text: str) -> list[str]:
    return text.split()


def rebase_spans(parent_text: str, parent_spans: list, new_text: str):
    """Carry word-origin spans across one edit. A span survives only
    when every word it covers maps through an unmodified (equal) block
    of the word diff; an edit touching any covered word drops the span
    and reports it — attribution stops where it becomes unreliable
    (S29.8). Returns ``(surviving, edited)`` with edited entries
    content-free (origin + word counts)."""
    if not parent_spans:
        return [], []
    a, b = _words(parent_text), _words(new_text)
    # Shift of parent word index -> new word index inside equal blocks.
    mapping = {}
    edited = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k
    surviving = []
    for span in parent_spans:
        s, e, origin = int(span[0]), int(span[1]), span[2]
        covered = list(range(s, e))
        if all(w in mapping for w in covered):
            shift = mapping[s] - s
            if all(mapping[w] == w + shift for w in covered):
                surviving.append([s + shift, e + shift, origin])
                continue
        edited.append({"origin": origin, "words_before": e - s})
    return surviving, edited


def insert_span(spans, start_word, n_words, origin):
    """A fresh attributed region (dictation/transform output)."""
    spans.append([start_word, start_word + n_words, origin])


class NoteStore:
    """Note/revision/attachment persistence (schema v8, the
    vocabulary_store pattern: one ``Store.submit`` op per operation)."""

    def __init__(self, store: Store, *, on_evidence=None):
        self.store = store
        # Called AFTER the writer op returns (never nested — a nested
        # Store call deadlocks the writer) with each evidence event a
        # revision produced. Installed by the coordinator.
        self.on_evidence = on_evidence

    @property
    def attachments_dir(self):
        return self.store.db_path.parent / "v2-notes"

    # ---- reads -----------------------------------------------------------

    def note(self, note_id):
        def op(db):
            row = db.execute(
                "SELECT note_id, title, pinned, current_revision_id,"
                " dirty_at_utc, created_at_utc, updated_at_utc FROM notes"
                " WHERE note_id=?", (note_id,)).fetchone()
            return _note_row(row)
        return self.store.submit(op)

    def notes(self, pinned_first=True):
        def op(db):
            order = ("n.pinned DESC, n.updated_at_utc DESC, n.rowid DESC"
                     if pinned_first
                     else "n.updated_at_utc DESC, n.rowid DESC")
            rows = db.execute(
                "SELECT n.note_id, n.title, n.pinned, n.current_revision_id,"
                " n.dirty_at_utc, n.created_at_utc, n.updated_at_utc,"
                " r.word_count,"
                " (SELECT COUNT(*) FROM note_revisions v WHERE v.note_id ="
                "  n.note_id) AS revision_count"
                f" FROM notes n LEFT JOIN note_revisions r ON"
                f" r.revision_id = n.current_revision_id ORDER BY {order}"
            ).fetchall()
            return [_note_row(r) for r in rows]
        return self.store.submit(op)

    def search(self, text):
        """Local full-text search over the CURRENT revision of every
        note (title + content), the History LIKE discipline with
        escaping."""
        pat = f"%{_like_escape(text)}%"
        return self.store.submit(lambda db: [
            _note_row(r) for r in db.execute(
                "SELECT n.note_id, n.title, n.pinned, n.current_revision_id,"
                " n.dirty_at_utc, n.created_at_utc, n.updated_at_utc,"
                " r.word_count,"
                " (SELECT COUNT(*) FROM note_revisions v WHERE v.note_id ="
                "  n.note_id) AS revision_count"
                " FROM notes n JOIN note_revisions r ON"
                " r.revision_id = n.current_revision_id"
                " WHERE (n.title LIKE ? ESCAPE '\\' OR r.content_text LIKE ?"
                " ESCAPE '\\') ORDER BY n.pinned DESC, n.updated_at_utc DESC",
                (pat, pat)).fetchall()])

    def open_note(self, note_id):
        """Everything the editor needs: note header, current revision
        content, versions, attachments and the honest unsaved-tail-risk
        marker (M12-AC01)."""
        def op(db):
            row = db.execute(
                "SELECT note_id, title, pinned, current_revision_id,"
                " dirty_at_utc, created_at_utc, updated_at_utc FROM notes"
                " WHERE note_id=?", (note_id,)).fetchone()
            if row is None:
                return None
            note = _note_row(row)
            rev = None
            if note["current_revision_id"]:
                r = db.execute(
                    "SELECT revision_id, content_text, word_count,"
                    " spans_json, created_at_utc, origin, trigger_kind"
                    " FROM note_revisions WHERE"
                    " revision_id=? AND purged=0",
                    (note["current_revision_id"],)).fetchone()
                if r is not None:
                    rev = {"revision_id": r[0], "content": r[1],
                           "word_count": r[2],
                           "spans": json.loads(r[3] or "[]"),
                           "created_at_utc": r[4], "origin": r[5],
                           "trigger": r[6]}
            note["revision"] = rev
            note["versions"] = [
                {"revision_id": v[0], "origin": v[1],
                 "trigger": v[2], "word_count": v[3],
                 "restore_of": v[4], "created_at_utc": v[5]}
                for v in db.execute(
                    "SELECT revision_id, origin, trigger_kind, word_count,"
                    " restore_of, created_at_utc FROM note_revisions"
                    " WHERE note_id=? AND purged=0 ORDER BY rowid DESC"
                    " LIMIT ?", (note_id, VERSIONS_MAX + 1)).fetchall()]
            note["versions_truncated"] = len(note["versions"]) > VERSIONS_MAX
            note["versions"] = note["versions"][:VERSIONS_MAX]
            note["attachments"] = self._attachment_rows(db, note_id)
            if note["dirty_at_utc"]:
                note["unsaved_tail_risk"] = {
                    "editing_started_utc": note["dirty_at_utc"],
                    "last_saved_utc": (rev or {}).get("created_at_utc"),
                    "last_saved_words": (rev or {}).get("word_count", 0),
                }
            else:
                note["unsaved_tail_risk"] = None
            return note
        return self.store.submit(op)

    def _attachment_rows(self, db, note_id, include_purged=False):
        where = "" if include_purged else " AND purged=0"
        return [
            {"attachment_id": r[0], "note_id": r[1], "kind": r[2],
             "mime": r[3], "filename": r[4], "bytes": r[5], "sha256": r[6],
             "purged": bool(r[7]), "created_at_utc": r[8]}
            for r in db.execute(
                "SELECT attachment_id, note_id, kind, mime, filename, bytes,"
                f" sha256, purged, created_at_utc FROM note_attachments"
                f" WHERE note_id=?{where} ORDER BY rowid",
                (note_id,)).fetchall()]

    def attachment_payload(self, attachment_id):
        def op(db):
            return db.execute(
                "SELECT content_path FROM note_attachments WHERE"
                " attachment_id=? AND purged=0", (attachment_id,)
            ).fetchone()
        row = self.store.submit(op)
        if row is None or not row[0]:
            return None
        try:
            return (self.attachments_dir / row[0]).read_bytes()
        except OSError:
            return None

    def revision_content(self, revision_id):
        def op(db):
            return db.execute(
                "SELECT content_text FROM note_revisions WHERE revision_id=?"
                " AND purged=0", (revision_id,)).fetchone()
        row = self.store.submit(op)
        return row[0] if row else None

    # ---- writes ----------------------------------------------------------

    def create_note(self, content="", *, origin=ORIGIN_CREATED,
                    source_job_id=None, task_key=None, transform_id=None,
                    transform_revision=None, title=None):
        note_id = ids.new_id("note")
        rev = self._append(note_id, content, origin=origin,
                           trigger=TRIGGER_SYSTEM, create=True,
                           source_job_id=source_job_id, task_key=task_key,
                           transform_id=transform_id,
                           transform_revision=transform_revision,
                           title_override=title)
        return {"note_id": note_id, "revision": rev["revision_id"]}

    def append_revision(self, note_id, content, *, origin, trigger,
                        source_job_id=None, task_key=None,
                        transform_id=None, transform_revision=None,
                        inserted_at_chars=None, inserted_text=None,
                        title=None):
        """Append one immutable revision. Returns the revision view; the
        evidence event (if any) is dispatched to ``on_evidence`` after
        the writer op commits."""
        return self._append(
            note_id, content, origin=origin, trigger=trigger,
            source_job_id=source_job_id, task_key=task_key,
            transform_id=transform_id,
            transform_revision=transform_revision,
            inserted_at_chars=inserted_at_chars,
            inserted_text=inserted_text, title_override=title)

    def restore(self, note_id, revision_id):
        """Restore an earlier version by COPYING its content into a new
        revision (origin=restore) — the current revision stays in the
        chain, nothing is silently discarded (M12-AC02)."""
        def op(db):
            row = db.execute(
                "SELECT content_text, spans_json FROM note_revisions"
                " WHERE revision_id=? AND note_id=? AND purged=0",
                (revision_id, note_id)).fetchone()
            return row
        row = self.store.submit(op)
        if row is None:
            raise KeyError(f"no revision {revision_id} for note {note_id}")
        content, spans = row[0], json.loads(row[1] or "[]")
        return self._append(
            note_id, content, origin=ORIGIN_RESTORE,
            trigger=TRIGGER_EXPLICIT, restore_of=revision_id,
            spans_override=spans)

    def set_pinned(self, note_id, pinned: bool):
        """Pin/unpin — a list-ordering flag only, never retention."""
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                "UPDATE notes SET pinned=?, updated_at_utc=? WHERE"
                " note_id=?", (1 if pinned else 0, now, note_id))
        self.store.submit(op)

    def mark_dirty(self, note_id):
        """Arm the unsaved-tail-risk marker: called on the FIRST edit of
        a burst (cheap single UPDATE), cleared by the next persisted
        revision. After a forced interruption the marker says edits
        began and no save followed (M12-AC01)."""
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                "UPDATE notes SET dirty_at_utc=? WHERE note_id=?",
                (now, note_id))
        self.store.submit(op)

    def clear_dirty(self, note_id):
        """Clear the marker when the buffer returned to the saved
        content without a revision (typed then deleted — a false AC01
        alarm otherwise)."""
        def op(db):
            db.execute(
                "UPDATE notes SET dirty_at_utc=NULL WHERE note_id=?",
                (note_id,))
        self.store.submit(op)

    # ---- attachments -----------------------------------------------------

    def add_attachment(self, note_id, data: bytes, mime: str, filename: str):
        """Copy an image into managed private storage (0700/0600, the
        artifacts discipline) and record the row. The note content's
        inline marker is the caller's revision."""
        if not data:
            raise ValueError("attachment payload is empty")
        ext = _ext_for(mime, filename)
        attachment_id = ids.new_id("att")
        rel = f"{attachment_id}.{ext}"
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.attachments_dir, 0o700)
        except OSError:
            pass
        path = self.attachments_dir / rel
        path.write_bytes(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                "INSERT INTO note_attachments(attachment_id, note_id, kind,"
                " mime, filename, bytes, sha256, content_path, purged,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (attachment_id, note_id, "image", mime, filename,
                 len(data), ids.sha256_bytes(data), rel, now))
            return attachment_id
        try:
            self.store.submit(op)
        except Exception:
            # Never orphan a payload file whose row never landed.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return {"attachment_id": attachment_id, "marker":
                f"![{_marker_alt(filename)}](attachment:{attachment_id})",
                "bytes": len(data)}

    def attachments(self, note_id):
        return self.store.submit(
            lambda db: self._attachment_rows(db, note_id))

    def delete_attachment(self, attachment_id):
        """Purge one attachment (row + file). The content's marker is
        removed by the caller's revision; evidence propagation rides the
        revision event."""
        def op(db):
            row = db.execute(
                "SELECT content_path FROM note_attachments WHERE"
                " attachment_id=? AND purged=0", (attachment_id,)
            ).fetchone()
            if row is None:
                return False
            db.execute(
                "UPDATE note_attachments SET purged=1, content_path=NULL"
                " WHERE attachment_id=?", (attachment_id,))
            if row[0]:
                try:
                    (self.attachments_dir / row[0]).unlink(missing_ok=True)
                except OSError:
                    pass
            return True
        return bool(self.store.submit(op))

    # ---- deletion ----------------------------------------------------------

    def delete_note(self, note_id):
        """Delete a note: purge attachment payloads, blank every
        revision's content (origins/counts/hashes stay as the content-
        free record), drop the note row and tombstone it. Returns the
        evidence-closure payload (example ids whose note references
        close — the caller feeds the collector so deletion propagates
        to evidence references, M12-AC05)."""
        def op(db):
            if db.execute("SELECT 1 FROM notes WHERE note_id=?",
                          (note_id,)).fetchone() is None:
                return None
            paths = [r[0] for r in db.execute(
                "SELECT content_path FROM note_attachments WHERE note_id=?"
                " AND purged=0", (note_id,)).fetchall() if r[0]]
            db.execute(
                "UPDATE note_attachments SET purged=1, content_path=NULL"
                " WHERE note_id=?", (note_id,))
            db.execute(
                "UPDATE note_revisions SET content_text='', purged=1"
                " WHERE note_id=?", (note_id,))
            now = ids.now_utc_iso()
            # M14 (S29.14): learning candidates mined from this note's
            # edits lose their payload (the edited words) and, when
            # still open, go stale — deleted note text never survives
            # in a suggestion.
            revs = ("SELECT revision_id FROM note_revisions WHERE"
                    " note_id=?")
            for (aid,) in db.execute(
                    "SELECT after_artifact_id FROM learning_candidates"
                    " WHERE source='note_revision' AND after_artifact_id"
                    f" IS NOT NULL AND observation_id IN ({revs})",
                    (note_id,)).fetchall():
                db.execute(
                    "UPDATE artifact_leases SET revoked_at_utc=? WHERE"
                    " artifact_id=? AND revoked_at_utc IS NULL", (now, aid))
                db.execute(
                    "UPDATE artifacts SET content_text=NULL,"
                    " content_path=NULL, purged=1 WHERE artifact_id=?",
                    (aid,))
            db.execute(
                "UPDATE learning_candidates SET status='stale',"
                " proposed_alias=NULL, proposed_canonical=NULL,"
                " changed_spans_json='[]', updated_at_utc=? WHERE"
                " source='note_revision' AND status IN ('pending',"
                f"'suppressed','dismissed') AND observation_id IN ({revs})",
                (now, note_id))
            db.execute(
                "UPDATE learning_candidates SET changed_spans_json='[]',"
                " updated_at_utc=? WHERE source='note_revision' AND status"
                f" IN ('approved','rejected') AND observation_id IN ({revs})",
                (now, note_id))
            closed = [
                {"example_id": r[0], "job_id": r[1]} for r in db.execute(
                    "SELECT example_id, job_id FROM note_evidence_links"
                    " WHERE note_id=? AND closed_utc IS NULL",
                    (note_id,)).fetchall()]
            db.execute(
                "UPDATE note_evidence_links SET closed_utc=?,"
                " close_reason='note_deleted' WHERE note_id=? AND"
                " closed_utc IS NULL", (now, note_id))
            db.execute("DELETE FROM notes WHERE note_id=?", (note_id,))
            db.execute(
                "INSERT INTO deletion_tombstones(tombstone_id, target_kind,"
                " target_id, reason, created_at_utc) VALUES(?,?,?,?,?)",
                (ids.new_id("tomb"), "note", note_id, "user_request", now))
            for p in paths:
                try:
                    (self.attachments_dir / p).unlink(missing_ok=True)
                except OSError:
                    pass
            return {"note_id": note_id, "purged_attachments": len(paths),
                    "closed_examples": closed}
        return self.store.submit(op)

    # ---- the one revision writer ------------------------------------------

    def _append(self, note_id, content, *, origin,
                trigger, create=False, source_job_id=None, task_key=None,
                transform_id=None, transform_revision=None,
                restore_of=None, spans_override=None,
                inserted_at_chars=None, inserted_text=None,
                title_override=None):
        if origin not in ORIGINS:
            raise ValueError(f"unknown note revision origin: {origin}")
        if trigger not in TRIGGERS:
            raise ValueError(f"unknown note revision trigger: {trigger}")
        revision_id = ids.new_id("nrev")
        now = ids.now_utc_iso()
        content = content or ""

        def op(db):
            if create:
                db.execute(
                    "INSERT INTO notes(note_id, title, pinned,"
                    " current_revision_id, dirty_at_utc, created_at_utc,"
                    " updated_at_utc) VALUES(?,?,0,NULL,NULL,?,?)",
                    (note_id, title_override or "", now, now))
            note = db.execute(
                "SELECT current_revision_id FROM notes WHERE note_id=?",
                (note_id,)).fetchone()
            if note is None:
                raise KeyError(f"no note {note_id}")
            parent_id = note[0]
            parent_content = ""
            parent_spans = []
            if parent_id is not None:
                p = db.execute(
                    "SELECT content_text, spans_json FROM note_revisions"
                    " WHERE revision_id=? AND purged=0", (parent_id,)
                ).fetchone()
                if p is not None:
                    parent_content, parent_spans = p[0], json.loads(
                        p[1] or "[]")
            # Region provenance: survivors rebased through the word
            # diff; a dictation/transform region starts attributed. A
            # transform's replaced spans are already dropped by the
            # rebase (their words are not in equal blocks) and surface
            # as edited_spans — attribution never survives a rewrite.
            edited = []
            if spans_override is not None:
                spans = [list(s) for s in spans_override]
            else:
                spans, edited = rebase_spans(parent_content, parent_spans,
                                             content)
                if origin in _SPAN_ORIGINS:
                    if inserted_text:
                        start_word = len(
                            parent_content[:inserted_at_chars or 0].split())
                        insert_span(spans, start_word,
                                    word_count(inserted_text), origin)
                    elif not parent_content:
                        # A note CREATED from attributed text (History
                        # copy, Save-to-Scratchpad): the whole content
                        # is the attributed region.
                        insert_span(spans, 0, word_count(content), origin)
            meta = {"edited_spans": edited} if edited else {}
            db.execute(
                "INSERT INTO note_revisions(revision_id, note_id,"
                " parent_revision_id, origin, trigger_kind, content_text,"
                " content_sha256, word_count, source_job_id, task_key,"
                " transform_id, transform_revision, restore_of,"
                " spans_json, meta_json, purged, created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (revision_id, note_id, parent_id, origin, trigger, content,
                 ids.sha256_text(content), word_count(content),
                 source_job_id, task_key, transform_id, transform_revision,
                 restore_of, json.dumps(spans),
                 json.dumps(meta, ensure_ascii=False), now))
            title = title_override if title_override is not None \
                else derive_title(content)
            db.execute(
                "UPDATE notes SET current_revision_id=?, title=?,"
                " dirty_at_utc=NULL, updated_at_utc=? WHERE note_id=?",
                (revision_id, title, now, note_id))
            return {"revision_id": revision_id, "note_id": note_id,
                    "parent_revision_id": parent_id, "origin": origin,
                    "trigger": trigger, "word_count": word_count(content),
                    "source_job_id": source_job_id, "task_key": task_key,
                    "transform_id": transform_id,
                    "transform_revision": transform_revision,
                    "restore_of": restore_of,
                    "edited_spans": edited,
                    "created_at_utc": now}
        rev = self.store.submit(op)
        event = self._evidence_event(rev)
        if event is not None and self.on_evidence is not None:
            try:
                self.on_evidence(event)
            except Exception:
                pass  # evidence never blocks a note write
        return rev

    @staticmethod
    def _evidence_event(rev):
        """Which revisions produce an evidence observation: attributed
        arrivals (dictation/transform), typed edits that touched an
        attributed region (local correction candidates, S29.8) and
        restores (a changed-intent candidate for M14 — classified
        there, never here). A pure typed edit elsewhere is note
        bookkeeping only — it never becomes an ASR observation
        (M12-AC05)."""
        if rev["origin"] in (ORIGIN_DICTATED, ORIGIN_TRANSFORM):
            return dict(rev, kind="note_region_arrival")
        if rev["origin"] == ORIGIN_TYPED and rev["edited_spans"]:
            return dict(rev, kind="note_region_edited")
        if rev["origin"] == ORIGIN_RESTORE:
            return dict(rev, kind="note_region_restored")
        return None


def _note_row(r):
    return {"note_id": r[0], "title": r[1] or "", "pinned": bool(r[2]),
            "current_revision_id": r[3], "dirty_at_utc": r[4],
            "created_at_utc": r[5], "updated_at_utc": r[6],
            **({"word_count": r[7]} if len(r) > 7 and r[7] is not None
               else {"word_count": 0}),
            **({"revision_count": r[8]} if len(r) > 8 else {})}


def _ext_for(mime, filename):
    mime_map = {"image/png": "png", "image/jpeg": "jpg",
                "image/gif": "gif", "image/webp": "webp",
                "image/tiff": "tiff"}
    ext = mime_map.get((mime or "").lower())
    if ext is None and filename and "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()[:8] or "img"
    return re.sub(r"[^a-z0-9]", "", ext or "img") or "img"


# ---- the editor buffer (pure Python; AppKit binds in ui/scratchpad) -------

class NotesEditorModel:
    """One open note's editing state. Thread discipline: ``edit`` runs
    on the main thread (cheap, in-memory); ``flush`` runs on a worker
    thread through the store writer and is SERIALIZED — a flush while
    one is in flight marks a reflush, never interleaves two revisions
    of the same buffer state (EV-14 concurrent autosave)."""

    def __init__(self, note_id, revision_id, content, *, on_dirty=None,
                 debounce_sec=_AUTOSAVE_DEBOUNCE_SEC, clock=time.monotonic):
        self.note_id = note_id
        self.revision_id = revision_id
        self.content = content
        self.saved_content = content
        self.dirty = False
        self.last_edit = None
        self.deadline = None
        self.on_dirty = on_dirty
        self.debounce_sec = debounce_sec
        self.clock = clock
        self._flush_lock = threading.Lock()
        self._flushing = False
        self.reflush = False
        self.pending = None  # immediate-flush payload (dictation/…)
        self.closed = False

    # ---- editing (main thread) ------------------------------------------

    def edit(self, content):
        """Buffer a typed edit; the FIRST edit of a burst arms the
        store's dirty marker (unsaved-tail-risk, M12-AC01)."""
        if self.closed:
            return
        self.content = content
        now = self.clock()
        self.last_edit = now
        self.deadline = now + self.debounce_sec
        if not self.dirty:
            self.dirty = True
            if self.on_dirty is not None:
                self.on_dirty(self.note_id)

    def receive(self, content, *, origin, trigger=TRIGGER_SYSTEM,
                source_job_id=None, task_key=None, transform_id=None,
                transform_revision=None, inserted_at_chars=None,
                inserted_text=None):
        """An attributed arrival (dictation/transform/snippet): buffer
        AND mark for immediate flush — this content is never left only
        in memory behind a debounce."""
        if self.closed:
            return
        self.content = content
        self.pending = {
            "origin": origin, "trigger": trigger,
            "source_job_id": source_job_id, "task_key": task_key,
            "transform_id": transform_id,
            "transform_revision": transform_revision,
            "inserted_at_chars": inserted_at_chars,
            "inserted_text": inserted_text,
        }
        self.dirty = True
        self.deadline = 0.0  # due immediately

    def due(self, now=None):
        if self.closed or not self.dirty:
            return False
        if self.pending is not None:
            return True
        now = self.clock() if now is None else now
        return self.deadline is not None and now >= self.deadline

    # ---- persistence (worker thread) -------------------------------------

    def flush(self, store: NoteStore, *, trigger=TRIGGER_AUTOSAVE):
        """Persist the buffer if it changed. Serialized: concurrent
        callers either run this flush or schedule one reflush; each
        committed revision parents the previous one in call order."""
        with self._flush_lock:
            if self.closed:
                return {"outcome": "closed"}
            if self._flushing:
                self.reflush = True
                return {"outcome": "already_flushing"}
            self._flushing = True
        try:
            while True:
                result = self._flush_once(store, trigger)
                with self._flush_lock:
                    if self.reflush and not self.closed:
                        self.reflush = False
                        continue
                    self._flushing = False
                return result
        except BaseException:
            with self._flush_lock:
                self._flushing = False
                self.reflush = False
            raise

    def _flush_once(self, store: NoteStore, trigger):
        content = self.content
        pending, self.pending = self.pending, None
        try:
            if pending is not None:
                origin = pending["origin"]
                trig = pending["trigger"]
            else:
                origin, trig = ORIGIN_TYPED, trigger
            if content == self.saved_content and origin == ORIGIN_TYPED:
                # Back to the saved content before the debounce fired
                # (typed then deleted): nothing to persist — and the
                # unsaved-tail-risk marker must clear too, or every
                # later open shows a false AC01 alarm.
                if self.content == content:
                    self.dirty = False
                store.clear_dirty(self.note_id)
                return {"outcome": "no_change"}
            rev = store.append_revision(
                self.note_id, content, origin=origin, trigger=trig,
                source_job_id=(pending or {}).get("source_job_id"),
                task_key=(pending or {}).get("task_key"),
                transform_id=(pending or {}).get("transform_id"),
                transform_revision=(pending or {}).get("transform_revision"),
                inserted_at_chars=(pending or {}).get("inserted_at_chars"),
                inserted_text=(pending or {}).get("inserted_text"))
        except BaseException:
            # A failed write keeps the arrival's attribution for the
            # retry — a dictation must never degrade to origin=typed.
            if pending is not None:
                self.pending = pending
            raise
        self.saved_content = content
        self.revision_id = rev["revision_id"]
        if self.content == content:
            self.dirty = False
        return {"outcome": "flushed", "revision_id": rev["revision_id"],
                "origin": origin, "trigger": trig}

    def close(self):
        self.closed = True


def _marker_alt(filename: str) -> str:
    """Alt text that cannot break the inline marker's round trip
    (']'/')' would end the link syntax early)."""
    return (filename or "image").replace("]", "").replace(")", "")[:48]


# How many version headers open_note materializes (the versions popup
# and the M12 benchmark path); older revisions stay queryable in the
# store — the flag below says the list was cut.
VERSIONS_MAX = 200
