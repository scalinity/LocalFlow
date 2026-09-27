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
from .store import Store, read_managed_file, unlink_managed_file
from .store import managed_name_ok

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


def utf16_range_to_codepoints(text: str, location: int,
                              length: int) -> tuple[int, int]:
    """Convert an AppKit ``NSRange`` (UTF-16 code units) over ``text``
    to a half-open Python code-point range. A character outside the
    Basic Multilingual Plane (an emoji) is two UTF-16 units but one
    Python character, so slicing a Python string with raw NSRange
    offsets addresses the wrong text.

    M12-AUDIT-22: the one validated boundary. Integers only (no bools),
    nonnegative location and length, the end within the text, and
    neither endpoint inside a surrogate pair — otherwise ``ValueError``.
    Refusal never widens scope: a caller treats it as "no usable
    selection", never as the whole note or a neighbouring slice. Code
    points, not grapheme clusters: a ZWJ sequence is several."""
    for v in (location, length):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("native range values must be integers")
    if location < 0 or length < 0:
        raise ValueError("native range is negative")
    end_units = location + length
    boundaries = {0: 0}
    units = 0
    for i, ch in enumerate(text):
        units += 2 if ord(ch) > 0xFFFF else 1
        boundaries[units] = i + 1
    if location not in boundaries or end_units not in boundaries:
        raise ValueError("native range is outside the text or splits a"
                         " surrogate pair")
    return boundaries[location], boundaries[end_units]


def note_destination_check(dest, open_note_id, content):
    """Scratchpad transform acceptance authority (S20/S16): the output
    may replace only the region it was generated for — the SAME note
    and the SAME text at the captured code-point range. ``dest`` is
    the immutable destination captured with the transform request
    (``note_id``, ``revision_id``, ``range``, ``text``, ``scope``); a
    chained Transform Output keeps it unchanged. Returns
    ``(ok, reason)``.

    M12-AUDIT-13: a WHOLE-NOTE destination (``scope == "whole"``) was
    authorized over the entire note, so the entire note must still be
    exactly the captured text — a note that grew or changed anywhere
    refuses (``note_content_changed``). A SELECTION destination keeps
    the numeric-range rule: edits outside the exact range are allowed."""
    if not dest or dest.get("range") is None:
        return False, "no_destination"
    if open_note_id is None:
        return False, "note_not_open"
    if dest.get("note_id") != open_note_id:
        return False, "note_changed"
    if content is None:
        return False, "note_range_changed"
    if dest.get("scope") == "whole":
        if content != dest.get("text"):
            return False, "note_content_changed"
        return True, None
    s, e = (int(x) for x in dest["range"])
    if content[s:e] != dest.get("text"):
        return False, "note_range_changed"
    return True, None


def attachment_ids(content: str) -> list[str]:
    """Attachment ids referenced by the content's inline markers."""
    return [m[1] for m in _ATTACHMENT_RE.findall(content)]


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- region spans (word-offset, origin-tagged) ---------------------------

def _words(text: str) -> list[str]:
    return text.split()


def _occurrences(words, seq):
    n = len(seq)
    return [i for i in range(len(words) - n + 1)
            if words[i:i + n] == seq] if n else []


def rebase_spans(parent_text: str, parent_spans: list, new_text: str):
    """Carry word-origin spans across one edit. A span survives only
    when every word it covers maps through an unmodified (equal) block
    of the word diff; an edit touching any covered word drops the span
    and reports it — attribution stops where it becomes unreliable
    (S29.8). Returns ``(surviving, edited)`` with edited entries
    content-free (origin + word counts).

    M12-AUDIT-17: a word diff over text cannot tell WHICH copy of a
    repeated word sequence survived an edit (delete the first "echo" of
    "echo echo" and the diff keeps "the first"). A span whose covered
    words occur a different number of times after the edit, or whose
    occurrence rank changes, is ambiguous: it abstains (dropped,
    reported with ``reason: ambiguous``) rather than guessing."""
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
        if covered and all(w in mapping for w in covered):
            shift = mapping[s] - s
            if all(mapping[w] == w + shift for w in covered):
                seq = a[s:e]
                occ_a, occ_b = _occurrences(a, seq), _occurrences(b, seq)
                if len(occ_a) == len(occ_b) and \
                        occ_a.index(s) == occ_b.index(s + shift):
                    # Extra elements (the producing job) ride along.
                    surviving.append([s + shift, e + shift, origin,
                                      *span[3:]])
                    continue
                edited.append({"origin": origin, "words_before": e - s,
                               "reason": "ambiguous"})
                continue
        edited.append({"origin": origin, "words_before": e - s})
    return surviving, edited


def arrival_span(content: str, char_start: int, char_len: int):
    """The word range (half-open, whitespace-split words of ``content``)
    that lies WHOLLY inside the arrival's characters
    ``[char_start, char_start + char_len)``. A word that merges arrival
    characters with neighbouring typed ones is not attributed (the
    mid-word case abstains instead of labelling a typed word); None when
    no whole word arrived."""
    end = char_start + char_len
    first = last = None
    for i, m in enumerate(re.finditer(r"\S+", content)):
        if m.start() >= char_start and m.end() <= end:
            if first is None:
                first = i
            last = i
        elif m.start() >= end:
            break
    return None if first is None else (first, last + 1)


def insert_span(spans, start_word, n_words, origin, job_id=None):
    """A fresh attributed region (dictation/transform output). A
    dictated region records the job that produced it, so a later edit
    in a note holding several dictations is attributable to one."""
    span = [start_word, start_word + n_words, origin]
    if job_id:
        span.append(job_id)
    spans.append(span)


class NoteMissing(KeyError):
    """The note is not live (never existed, or deleted): nothing was
    written."""


class NoteOutcomeUnknown(RuntimeError):
    """A mutation was admitted to the store writer but its caller stopped
    waiting before the answer (M02: a timeout never cancels the op). The
    op may still commit; ``ident`` is the preallocated identity that a
    later read reconciles — never retry under a new identity, never
    describe it as failed."""

    def __init__(self, op, ident):
        super().__init__(f"{op} outcome unknown")
        self.op = op
        self.ident = ident


def failure_kind(exc) -> str:
    """How a failed store call ended (M12-AUDIT-24): ``unknown`` (admitted,
    unanswered — it may still commit), ``refused`` (never admitted: the
    store is closing) or ``failed`` (the op ran and rolled back)."""
    if isinstance(exc, (TimeoutError, NoteOutcomeUnknown)):
        return "unknown"
    if isinstance(exc, RuntimeError) and str(exc).startswith("store is "):
        return "refused"
    return "failed"


def _note_live(db, note_id) -> bool:
    return db.execute("SELECT 1 FROM notes WHERE note_id=?",
                      (note_id,)).fetchone() is not None


def _purge_note_transform_graph(db, note_id, now) -> int:
    """Writer-op only (M12-AUDIT-15): purge the managed transform
    artifacts derived from a note — each candidate whose source artifact
    names the note (``transform_note`` captures), its output artifact,
    and their children (the rendered prompt carries the source text; the
    decision carries review excerpts). Text artifacts hold no payload
    file; their leases are revoked and their text removed. The candidate
    rows (ids and hashes only) stay as the content-free record. Returns
    how many artifacts were purged."""
    roots = set()
    for src, out in db.execute(
            "SELECT c.source_artifact_id, c.output_artifact_id FROM"
            " transform_candidates c JOIN artifacts a ON a.artifact_id ="
            " c.source_artifact_id WHERE json_extract(a.meta_json,"
            " '$.note_id') = ?", (note_id,)).fetchall():
        roots.update(x for x in (src, out) if x)
    purged = 0
    frontier = list(roots)
    seen = set()
    while frontier:
        aid = frontier.pop()
        if aid in seen:
            continue
        seen.add(aid)
        frontier.extend(r[0] for r in db.execute(
            "SELECT artifact_id FROM artifacts WHERE parent_artifact_id=?",
            (aid,)).fetchall())
        db.execute(
            "UPDATE artifact_leases SET revoked_at_utc=? WHERE"
            " artifact_id=? AND revoked_at_utc IS NULL", (now, aid))
        purged += db.execute(
            "UPDATE artifacts SET content_text=NULL, purged=1 WHERE"
            " artifact_id=? AND purged=0 AND content_path IS NULL",
            (aid,)).rowcount
    return purged


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
        return self.store.notes_dir

    # ---- reads -----------------------------------------------------------

    def note(self, note_id):
        """The note header, or None when it does not exist."""
        def op(db):
            row = db.execute(
                "SELECT note_id, title, pinned, current_revision_id,"
                " dirty_at_utc, created_at_utc, updated_at_utc FROM notes"
                " WHERE note_id=?", (note_id,)).fetchone()
            return _note_row(row) if row is not None else None
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
        # A persisted name is data, not authority: only a plain regular
        # file directly inside the managed directory is ever read.
        return read_managed_file(self.attachments_dir, row[0])

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
                    transform_revision=None, title=None, note_id=None):
        """Create a note. ``note_id`` may be preallocated by a caller that
        must reconcile an unknown outcome by reading it back; a timeout
        raises ``NoteOutcomeUnknown`` carrying that id."""
        note_id = note_id or ids.new_id("note")
        try:
            rev = self._append(note_id, content, origin=origin,
                               trigger=TRIGGER_SYSTEM, create=True,
                               source_job_id=source_job_id,
                               task_key=task_key,
                               transform_id=transform_id,
                               transform_revision=transform_revision,
                               title_override=title)
        except TimeoutError:
            raise NoteOutcomeUnknown("create_note", note_id) from None
        return {"note_id": note_id, "revision": rev["revision_id"]}

    def append_revision(self, note_id, content, *, origin, trigger,
                        source_job_id=None, task_key=None,
                        transform_id=None, transform_revision=None,
                        inserted_at_chars=None, inserted_text=None,
                        title=None, revision_id=None, preimage=None,
                        clear_dirty=None):
        """Append one immutable revision. Returns the revision view; the
        evidence event (if any) is dispatched to ``on_evidence`` after
        the writer op commits.

        ``revision_id`` preallocates the revision's identity: appending
        the same id again returns the committed revision instead of a
        second one (the retry after an unknown outcome). ``preimage`` is
        the exact text an attributed arrival was inserted into (the
        editor buffer at arrival) — its span is placed against it, and
        attribution abstains when the writer-current parent is not that
        text. ``clear_dirty`` (a callable run inside the writer op)
        decides whether this commit settles the unsaved-tail marker; by
        default every commit does. A note that is not live raises
        ``NoteMissing`` with nothing written."""
        return self._append(
            note_id, content, origin=origin, trigger=trigger,
            source_job_id=source_job_id, task_key=task_key,
            transform_id=transform_id,
            transform_revision=transform_revision,
            inserted_at_chars=inserted_at_chars,
            inserted_text=inserted_text, title_override=title,
            revision_id=revision_id, preimage=preimage,
            clear_dirty=clear_dirty)

    def restore(self, note_id, revision_id, *, new_revision_id=None):
        """Restore an earlier version by COPYING its content into a new
        revision (origin=restore) — the current revision stays in the
        chain, nothing is silently discarded (M12-AC02). The copy parents
        the writer-current revision (D02)."""
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
        try:
            return self._append(
                note_id, content, origin=ORIGIN_RESTORE,
                trigger=TRIGGER_EXPLICIT, restore_of=revision_id,
                spans_override=spans, revision_id=new_revision_id)
        except TimeoutError:
            raise NoteOutcomeUnknown("restore", new_revision_id) from None

    def set_pinned(self, note_id, pinned: bool):
        """Pin/unpin — a list-ordering flag only, never retention.
        Idempotent (setting a state), so a retry after an unknown outcome
        is safe. Returns whether the note exists."""
        now = ids.now_utc_iso()

        def op(db):
            return db.execute(
                "UPDATE notes SET pinned=?, updated_at_utc=? WHERE"
                " note_id=?", (1 if pinned else 0, now, note_id)).rowcount
        try:
            return bool(self.store.submit(op))
        except TimeoutError:
            raise NoteOutcomeUnknown("set_pinned", note_id) from None

    def mark_dirty(self, note_id):
        """Arm the unsaved-tail-risk marker: called on the FIRST edit of
        a burst (cheap single UPDATE), cleared by the commit that saves
        the newest generation. After a forced interruption the marker
        says edits began and no save followed (M12-AC01). Returns False
        for a note that no longer exists (an honest no-op)."""
        now = ids.now_utc_iso()

        def op(db):
            return db.execute(
                "UPDATE notes SET dirty_at_utc=? WHERE note_id=?",
                (now, note_id)).rowcount
        return bool(self.store.submit(op))

    def clear_dirty(self, note_id, only_if=None):
        """Clear the marker when the buffer returned to the saved
        content without a revision (typed then deleted — a false AC01
        alarm otherwise). ``only_if`` (run inside the writer op) lets
        the editor clear it only while no newer generation exists.
        Returns whether a marker row was cleared."""
        def op(db):
            if only_if is not None and not only_if():
                return 0
            return db.execute(
                "UPDATE notes SET dirty_at_utc=NULL WHERE note_id=?",
                (note_id,)).rowcount
        return bool(self.store.submit(op))

    # ---- attachments -----------------------------------------------------

    def add_attachment(self, note_id, data: bytes, mime: str, filename: str,
                       *, attachment_id=None):
        """Copy an image into managed private storage (0700/0600, the
        artifacts discipline) and record the row. The note content's
        inline marker is the caller's revision.

        M12-AUDIT-06: the owner must be live at admission AND at
        publication; the payload file is durably owned before it exists
        (a staging purge intent — a crash between the write and the row
        leaves an intent the next open finishes, never an ownerless
        file); the row and the retirement of that intent commit
        together. Cleanup runs only after a KNOWN noncommit: an
        admitted publication whose answer never came raises
        ``NoteOutcomeUnknown`` and leaves the payload in place (the row
        may still commit; its id reconciles it)."""
        if not data:
            raise ValueError("attachment payload is empty")
        ext = _ext_for(mime, filename)
        attachment_id = attachment_id or ids.new_id("att")
        rel = f"{attachment_id}.{ext}"
        if not managed_name_ok(rel):
            raise ValueError("attachment id is not a managed name")
        intent_id = ids.new_id("purge")
        now = ids.now_utc_iso()

        def admit(db):
            if not _note_live(db, note_id):
                raise NoteMissing(note_id)
            db.execute(
                "INSERT INTO purge_intents(intent_id, artifact_id, job_id,"
                " root, path, reason, created_at_utc) VALUES(?,?,?,?,?,?,?)",
                (intent_id, attachment_id, None, "notes", rel,
                 "attachment_staging", now))
        try:
            self.store.submit(admit)
        except TimeoutError:
            # Nothing is on disk; a late intent drains harmlessly at open.
            raise NoteOutcomeUnknown("add_attachment", attachment_id) \
                from None
        self._write_payload(rel, data)   # O_EXCL; raises on failure

        def publish(db):
            if not _note_live(db, note_id):
                raise NoteMissing(note_id)
            db.execute(
                "INSERT INTO note_attachments(attachment_id, note_id, kind,"
                " mime, filename, bytes, sha256, content_path, purged,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (attachment_id, note_id, "image", mime, filename,
                 len(data), ids.sha256_bytes(data), rel, now))
            db.execute(
                "UPDATE purge_intents SET completed_at_utc=?, last_error=NULL"
                " WHERE intent_id=?", (now, intent_id))
            return attachment_id
        try:
            self.store.submit(publish)
        except TimeoutError:
            raise NoteOutcomeUnknown("add_attachment", attachment_id) \
                from None
        except Exception:
            # Known noncommit (the op rolled back, or was never admitted):
            # the payload is ours and unowned — remove it and retire the
            # staging intent (if that cannot run, the next open does).
            unlink_managed_file(self.attachments_dir, rel)
            try:
                self.store.submit(lambda db: db.execute(
                    "UPDATE purge_intents SET completed_at_utc=?,"
                    " last_error=NULL WHERE intent_id=?",
                    (ids.now_utc_iso(), intent_id)))
            except Exception:
                pass
            raise
        return {"attachment_id": attachment_id, "marker":
                f"![{_marker_alt(filename)}](attachment:{attachment_id})",
                "bytes": len(data)}

    def _write_payload(self, rel, data):
        """Create ``rel`` (exclusively, no-follow, 0600) inside the
        managed 0700 directory. A partial file this call created is
        removed before the error propagates."""
        d = self.attachments_dir
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        dfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
            except BaseException:
                os.close(fd)
                os.unlink(rel, dir_fd=dfd)
                raise
            os.close(fd)
        finally:
            os.close(dfd)

    def attachments(self, note_id):
        return self.store.submit(
            lambda db: self._attachment_rows(db, note_id))

    def delete_attachment(self, attachment_id):
        """Purge one attachment (row + file). The content's marker is
        removed by the caller's revision; evidence propagation rides the
        revision event.

        M12-AUDIT-05: the file is removed only AFTER the row change
        commits — a durable purge intent commits with it and the store
        keeps it pending until the payload is really gone (M02). A
        rollback leaves the live row with its payload. Returns False when
        nothing was live, else ``{"deleted": True, "pending_purges": n,
        "refused_paths": n}``."""
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
            intents, refused = self._purge_intents_for(db, [row[0]],
                                                       "attachment_deleted")
            return {"deleted": True, "_purge_intents": intents,
                    "refused_paths": refused}
        return self.store.submit(op)

    def _purge_intents_for(self, db, paths, reason):
        """Writer-op only: one durable intent per managed payload name.
        A persisted name that is not a plain managed name is REFUSED —
        never unlinked, counted (content-free)."""
        intents, refused = [], 0
        for p in paths:
            if not p:
                continue
            if not managed_name_ok(p):
                refused += 1
                continue
            intents.append(self.store._record_purge_intent(
                None, None, "notes", p, reason))
        return intents, refused

    # ---- deletion ----------------------------------------------------------

    def delete_note(self, note_id):
        """Delete a note: purge attachment payloads, blank every
        revision's content (origins/counts/hashes stay as the content-
        free record), drop the note row and tombstone it. Returns the
        evidence-closure payload (example ids whose note references
        close — the caller feeds the collector so deletion propagates
        to evidence references, M12-AC05).

        Payload files are removed only after the commit, through durable
        purge intents (M12-AUDIT-05); ``pending_purges`` reports any
        still on disk. The note-derived managed transform graph (the
        candidate source/output artifacts of transforms run over this
        note, and their prompt/decision children) is purged in the same
        op (M12-AUDIT-15); an original dictation the note copied is not
        note-derived and stays."""
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
            intents, refused = self._purge_intents_for(db, paths,
                                                       "note_deleted")
            db.execute(
                "UPDATE note_revisions SET content_text='', purged=1"
                " WHERE note_id=?", (note_id,))
            now = ids.now_utc_iso()
            purged_graph = _purge_note_transform_graph(db, note_id, now)
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
            return {"note_id": note_id, "purged_attachments": len(paths),
                    "closed_examples": closed, "_purge_intents": intents,
                    "refused_paths": refused,
                    "purged_transform_artifacts": purged_graph}
        return self.store.submit(op)

    # ---- the one revision writer ------------------------------------------

    def _append(self, note_id, content, *, origin,
                trigger, create=False, source_job_id=None, task_key=None,
                transform_id=None, transform_revision=None,
                restore_of=None, spans_override=None,
                inserted_at_chars=None, inserted_text=None,
                title_override=None, revision_id=None, preimage=None,
                clear_dirty=None):
        if origin not in ORIGINS:
            raise ValueError(f"unknown note revision origin: {origin}")
        if trigger not in TRIGGERS:
            raise ValueError(f"unknown note revision trigger: {trigger}")
        revision_id = revision_id or ids.new_id("nrev")
        now = ids.now_utc_iso()
        content = content or ""

        def op(db):
            done = db.execute(
                "SELECT note_id FROM note_revisions WHERE revision_id=?",
                (revision_id,)).fetchone()
            if done is not None:
                # The retry of an admitted append whose answer was lost:
                # the revision is already committed — one logical effect.
                return {"_already": True}
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
                return {"_missing": True}   # nothing written
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
            meta = {}
            if spans_override is not None:
                spans = [list(s) for s in spans_override]
            else:
                spans, edited = rebase_spans(parent_content, parent_spans,
                                             content)
                if origin in _SPAN_ORIGINS:
                    if inserted_text:
                        # M12-AUDIT-04: the arrival's offset refers to the
                        # buffer it landed in. Place its span in THAT
                        # text; when the committed parent is not it,
                        # the offset means nothing here — abstain.
                        base = parent_content if preimage is None \
                            else preimage
                        if base == parent_content:
                            span = arrival_span(
                                content, inserted_at_chars or 0,
                                len(inserted_text))
                            if span is not None:
                                insert_span(spans, span[0],
                                            span[1] - span[0], origin,
                                            job_id=source_job_id)
                        else:
                            meta["attribution"] = "abstained_parent_moved"
                    elif not parent_content:
                        # A note CREATED from attributed text (History
                        # copy, Save-to-Scratchpad): the whole content
                        # is the attributed region.
                        insert_span(spans, 0, word_count(content), origin,
                                    job_id=source_job_id)
            if edited:
                meta["edited_spans"] = edited
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
            # M12-AUDIT-18: only the commit that saves the newest
            # generation settles the unsaved-tail marker; the editor's
            # check runs HERE, inside the op, so an edit cannot slip
            # between the decision and the write.
            settle = True if clear_dirty is None else bool(clear_dirty())
            db.execute(
                "UPDATE notes SET current_revision_id=?, title=?,"
                " dirty_at_utc=CASE WHEN ? THEN NULL ELSE dirty_at_utc END,"
                " updated_at_utc=? WHERE note_id=?",
                (revision_id, title, 1 if settle else 0, now, note_id))
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
        if rev.get("_missing"):
            raise NoteMissing(note_id)
        if rev.get("_already"):
            return self._revision_view(revision_id)
        event = self._evidence_event(rev)
        if event is not None and self.on_evidence is not None:
            try:
                self.on_evidence(event)
            except Exception:
                pass  # evidence never blocks a note write
        return rev

    def _revision_view(self, revision_id):
        def op(db):
            return db.execute(
                "SELECT revision_id, note_id, parent_revision_id, origin,"
                " trigger_kind, word_count, source_job_id, task_key,"
                " transform_id, transform_revision, restore_of,"
                " created_at_utc FROM note_revisions WHERE revision_id=?",
                (revision_id,)).fetchone()
        r = self.store.submit(op)
        return {"revision_id": r[0], "note_id": r[1],
                "parent_revision_id": r[2], "origin": r[3],
                "trigger": r[4], "word_count": r[5], "source_job_id": r[6],
                "task_key": r[7], "transform_id": r[8],
                "transform_revision": r[9], "restore_of": r[10],
                "edited_spans": [], "created_at_utc": r[11],
                "reconciled": True}

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

_RETRY_BACKOFF_SEC = (1.0, 2.0, 5.0, 10.0, 30.0)
_MAX_PASSES = 16


class Arrival:
    """One attributed arrival into a note buffer (dictation, transform,
    snippet, attachment marker), IMMUTABLE once admitted: the exact
    buffer it landed in (``preimage``), the buffer it produced
    (``content``), the generation that produced it and its provenance
    (M12-AUDIT-09). It is also the arrival's RECEIPT (M12-AUDIT-07):
    being returned means only that the text is in the editor buffer;
    ``outcome`` settles to ``committed`` — with ``revision_id``, the
    revision that holds exactly this arrival — when that revision
    commits, to ``discarded`` when its note was deleted, or to
    ``failed`` when the editor shut down without committing it. A
    failed ATTEMPT does not settle it: the arrival stays queued and is
    retried under the same preallocated revision id (so a retry after
    an unknown outcome is one logical effect). Callbacks registered
    with ``on_settled`` run once, on the settling thread."""

    def __init__(self, *, note_id, generation, preimage, content, origin,
                 trigger, source_job_id=None, task_key=None,
                 transform_id=None, transform_revision=None,
                 char_start=0, text=""):
        self.op_id = ids.new_id("nop")
        self.revision_id = ids.new_id("nrev")
        self.note_id = note_id
        self.generation = generation
        self.preimage = preimage
        self.content = content
        self.origin = origin
        self.trigger = trigger
        self.source_job_id = source_job_id
        self.task_key = task_key
        self.transform_id = transform_id
        self.transform_revision = transform_revision
        self.char_start = char_start
        self.text = text
        self.outcome = None
        self.reason = None
        self.attempts = 0
        self.last_error = None
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._callbacks = []

    @property
    def settled(self) -> bool:
        return self.outcome is not None

    def on_settled(self, fn):
        with self._lock:
            if self.outcome is None:
                self._callbacks.append(fn)
                return
        fn(self)

    def wait(self, timeout=None) -> bool:
        return self._done.wait(timeout)

    def _settle(self, outcome, reason=None):
        with self._lock:
            if self.outcome is not None:
                return
            self.outcome, self.reason = outcome, reason
            callbacks, self._callbacks = self._callbacks, []
        self._done.set()
        for fn in callbacks:
            try:
                fn(self)
            except Exception:
                pass


class NotesEditorModel:
    """One open note's editing state (M12-AUDIT-03/08/09/18).

    Every buffer change advances ``generation``. Typed edits only change
    the buffer; an attributed arrival additionally appends an immutable
    ``Arrival`` (its preimage, content and provenance captured under the
    same lock as the buffer change). A flush commits, in order, each
    arrival — preceded by the typed text it landed in when that was not
    yet saved, as its own ``typed`` revision — and then the typed tail:
    every revision pairs exactly the text and provenance that produced
    it. Flushes are SERIALIZED: a flush that finds another in progress
    waits for it and then persists what is left (a durable barrier for
    the generation current at its call), bounded by ``timeout`` —
    ``pending`` is returned only when that bound expires first.

    A failed attempt keeps everything admitted (arrivals, typed tail);
    the next attempt retries under the same preallocated revision ids.
    ``close`` refuses new input and never discards admitted work;
    ``discard`` (the note was deleted) settles arrivals as discarded.

    The unsaved-tail marker (``notes.dirty_at_utc``) is armed by the
    first change after a clean state and settled only by a commit that
    saves the NEWEST generation — decided inside the writer op."""

    def __init__(self, note_id, revision_id, content, *, on_dirty=None,
                 debounce_sec=_AUTOSAVE_DEBOUNCE_SEC, clock=time.monotonic):
        self.note_id = note_id
        self.revision_id = revision_id
        self.content = content
        self.saved_content = content
        self.generation = 0
        self.saved_generation = 0
        self.arrivals = []
        self.on_dirty = on_dirty
        self.debounce_sec = debounce_sec
        self.clock = clock
        self.last_edit = None
        self.deadline = None
        self.closed = False
        self.deleted = False
        self.marker_armed = False
        self.last_error = None      # content-free kind of the last failure
        self.retry_at = None        # monotonic backoff for the autosave tick
        self._failures = 0
        self._typed_ids = {}        # generation -> preallocated revision id
        self._lock = threading.Condition()
        self._flushing = False

    # ---- state -------------------------------------------------------------

    def _pending_locked(self) -> bool:
        return bool(self.arrivals) or self.saved_generation < self.generation

    @property
    def dirty(self) -> bool:
        with self._lock:
            return not self.deleted and self._pending_locked()

    @property
    def flushing(self) -> bool:
        with self._lock:
            return self._flushing

    # ---- editing (main thread) ------------------------------------------

    def _changed_locked(self, content):
        self.content = content
        self.generation += 1
        arm = not self.marker_armed
        self.marker_armed = True
        return arm

    def edit(self, content):
        """Buffer a typed edit; the first change after a clean state arms
        the store's unsaved-tail marker (M12-AC01)."""
        with self._lock:
            if self.closed or self.deleted or content == self.content:
                return
            arm = self._changed_locked(content)
            now = self.clock()
            self.last_edit = now
            self.deadline = now + self.debounce_sec
        if arm and self.on_dirty is not None:
            self.on_dirty(self.note_id)

    def receive(self, content, *, origin, trigger=TRIGGER_SYSTEM,
                source_job_id=None, task_key=None, transform_id=None,
                transform_revision=None, inserted_at_chars=None,
                inserted_text=None):
        """An attributed arrival (dictation/transform/snippet) that
        produced the full buffer ``content``: buffered AND queued for an
        immediate flush — never left only in memory behind a debounce.
        Returns its ``Arrival`` receipt (None when the model is closed)."""
        return self._admit(lambda base: (content, inserted_at_chars or 0),
                           origin=origin, trigger=trigger,
                           source_job_id=source_job_id, task_key=task_key,
                           transform_id=transform_id,
                           transform_revision=transform_revision,
                           text=inserted_text or "")

    def insert(self, text, *, at=None, replace=None, origin,
               trigger=TRIGGER_SYSTEM, **provenance):
        """Insert ``text`` at code point ``at`` (or replace the code-point
        range ``replace``) of the CURRENT buffer, computed under the same
        lock that captures the arrival. Returns the receipt, or None when
        closed or the range does not fit the buffer."""
        def build(base):
            if replace is not None:
                s, e = int(replace[0]), int(replace[1])
                if not 0 <= s <= e <= len(base):
                    return None
            else:
                s = e = max(0, min(int(at or 0), len(base)))
            return base[:s] + text + base[e:], s
        return self._admit(build, origin=origin, trigger=trigger,
                           text=text, **provenance)

    def _admit(self, build, *, origin, trigger, text, source_job_id=None,
               task_key=None, transform_id=None, transform_revision=None):
        with self._lock:
            if self.closed or self.deleted:
                return None
            built = build(self.content)
            if built is None:
                return None
            content, start = built
            arrival = Arrival(
                note_id=self.note_id, generation=self.generation + 1,
                preimage=self.content, content=content, origin=origin,
                trigger=trigger, source_job_id=source_job_id,
                task_key=task_key, transform_id=transform_id,
                transform_revision=transform_revision, char_start=start,
                text=text)
            arm = self._changed_locked(content)
            self.arrivals.append(arrival)
            self.deadline = 0.0
        if arm and self.on_dirty is not None:
            self.on_dirty(self.note_id)
        return arrival

    def due(self, now=None) -> bool:
        with self._lock:
            if self.deleted or not self._pending_locked():
                return False
            if self.retry_at is not None \
                    and time.monotonic() < self.retry_at:
                return False
            if self.arrivals:
                return True
            now = self.clock() if now is None else now
            return self.deadline is not None and now >= self.deadline

    # ---- persistence (worker thread) -------------------------------------

    def flush(self, store: NoteStore, *, trigger=TRIGGER_AUTOSAVE,
              timeout=None):
        """Persist everything admitted, at least up to the generation
        current at this call. Returns ``{outcome, generation,
        revision_id, …}``: ``flushed`` (with the last committed
        revision's origin/trigger), ``no_change``, ``closed`` (closed
        with nothing admitted), ``failed`` / ``unknown`` (the attempt
        did not / may not have committed; everything stays admitted),
        ``note_deleted``, or ``pending`` (another flush still owned
        persistence when ``timeout`` expired)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            target = self.generation
            while self._flushing:
                if deadline is None:
                    self._lock.wait()
                    continue
                left = deadline - time.monotonic()
                if left <= 0:
                    return {"outcome": "pending", "generation": target,
                            "saved_generation": self.saved_generation}
                self._lock.wait(left)
            if self.deleted:
                return {"outcome": "note_deleted"}
            if not self._pending_locked():
                return {"outcome": "closed" if self.closed else "no_change",
                        "generation": self.saved_generation,
                        "revision_id": self.revision_id}
            self._flushing = True
        try:
            return self._persist(store, trigger)
        finally:
            with self._lock:
                self._flushing = False
                self._lock.notify_all()

    def _persist(self, store, trigger):
        result = {"outcome": "no_change"}
        for _ in range(_MAX_PASSES):
            with self._lock:
                arrival = self.arrivals[0] if self.arrivals else None
                content, gen = self.content, self.generation
                saved = self.saved_content
                if arrival is None and self.saved_generation >= gen:
                    break
            try:
                if arrival is not None:
                    if arrival.preimage != saved:
                        self._commit_typed(store, arrival.preimage,
                                           arrival.generation - 1, trigger)
                    rev = self._commit_arrival(store, arrival)
                    result = {"outcome": "flushed", "origin": arrival.origin,
                              "trigger": arrival.trigger}
                elif content != saved:
                    rev = self._commit_typed(store, content, gen, trigger)
                    result = {"outcome": "flushed", "origin": ORIGIN_TYPED,
                              "trigger": trigger}
                else:
                    # Typed back to the saved text: nothing to persist;
                    # the marker clears only if no newer change exists.
                    store.clear_dirty(self.note_id,
                                      only_if=lambda g=gen:
                                      self._settles_marker(g))
                    with self._lock:
                        self.saved_generation = max(self.saved_generation,
                                                    gen)
                    continue
            except NoteMissing:
                self.discard("note_deleted")
                return {"outcome": "note_deleted"}
            except Exception as e:  # noqa: BLE001 — every failure is kept
                kind = failure_kind(e)
                with self._lock:
                    self._failures += 1
                    self.last_error = kind
                    self.retry_at = time.monotonic() + _RETRY_BACKOFF_SEC[
                        min(self._failures, len(_RETRY_BACKOFF_SEC)) - 1]
                    if arrival is not None:
                        arrival.attempts += 1
                        arrival.last_error = kind
                    saved_gen = self.saved_generation
                return {"outcome": "unknown" if kind == "unknown"
                        else "failed", "error": kind,
                        "generation": saved_gen}
            with self._lock:
                self._failures = 0
                self.last_error = None
                self.retry_at = None
            result["revision_id"] = rev["revision_id"]
        with self._lock:
            result["generation"] = self.saved_generation
            result.setdefault("revision_id", self.revision_id)
        return result

    def _settles_marker(self, gen) -> bool:
        """Runs INSIDE the writer op of the commit saving ``gen``: only
        the newest generation, with no arrival after it, settles the
        unsaved-tail marker."""
        with self._lock:
            if gen >= self.generation and not any(
                    a.generation > gen for a in self.arrivals):
                self.marker_armed = False
                return True
            return False

    def _commit_typed(self, store, content, gen, trigger):
        with self._lock:
            rid = self._typed_ids.setdefault(gen, ids.new_id("nrev"))
        rev = store.append_revision(
            self.note_id, content, origin=ORIGIN_TYPED, trigger=trigger,
            revision_id=rid,
            clear_dirty=lambda: self._settles_marker(gen))
        with self._lock:
            self._typed_ids.pop(gen, None)
            self.saved_content = content
            self.saved_generation = max(self.saved_generation, gen)
            self.revision_id = rev["revision_id"]
        return rev

    def _commit_arrival(self, store, a):
        rev = store.append_revision(
            self.note_id, a.content, origin=a.origin, trigger=a.trigger,
            source_job_id=a.source_job_id, task_key=a.task_key,
            transform_id=a.transform_id,
            transform_revision=a.transform_revision,
            inserted_at_chars=a.char_start, inserted_text=a.text,
            revision_id=a.revision_id, preimage=a.preimage,
            clear_dirty=lambda: self._settles_marker(a.generation))
        with self._lock:
            if self.arrivals and self.arrivals[0] is a:
                self.arrivals.pop(0)
            self.saved_content = a.content
            self.saved_generation = max(self.saved_generation, a.generation)
            self.revision_id = rev["revision_id"]
        a._settle("committed")
        return rev

    # ---- lifecycle -------------------------------------------------------------

    def close(self):
        """Refuse new input. Admitted work stays and still flushes."""
        with self._lock:
            self.closed = True

    def discard(self, reason="note_deleted"):
        """The note is gone (deleted): nothing here can be saved into it.
        Queued arrivals settle as discarded (their callers record that
        honestly); the buffer is released."""
        with self._lock:
            self.deleted = True
            self.closed = True
            arrivals, self.arrivals = self.arrivals, []
            self.saved_generation = self.generation
        for a in arrivals:
            a._settle("discarded", reason)

    def fail_pending(self, reason):
        """Settle every still-queued arrival as failed (shutdown after
        the final attempt did not commit them). The buffer is kept."""
        with self._lock:
            arrivals = list(self.arrivals)
        for a in arrivals:
            a._settle("failed", reason)


def _marker_alt(filename: str) -> str:
    """Alt text that cannot break the inline marker's round trip
    (']'/')' would end the link syntax early)."""
    return (filename or "image").replace("]", "").replace(")", "")[:48]


# How many version headers open_note materializes (the versions popup
# and the M12 benchmark path); older revisions stay queryable in the
# store — the flag below says the list was cut.
VERSIONS_MAX = 200
