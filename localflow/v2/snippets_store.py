"""Persistent snippets over the single-writer store (V2 M10).

The M05 ``vocabulary_store`` pattern: versioned rows (the revision
counter is the snippet's version, M10-AC02) plus a monotonic state
counter in ``profiles_meta`` so the app's frozen snippet registry
invalidates on edit. The NOCASE unique trigger index keeps the stored
set unambiguous (a duplicate trigger would be ambiguous at match time).
Usage statistics ride the same rows and — like vocabulary usage — never
bump the state counter.

Every mutation is ONE writer operation over the writer-current row: the
requested changes merge onto it and the merged snippet is validated as
a whole (kind and content are coupled — a URL snippet must stay one
address token), the trigger's uniqueness is checked in the same
operation, exactly one row must be affected, and only then does the
counter move (M10-AUDIT-04/05). Outcomes are the typed, content-free
ones of ``profiles_store`` (not found, stale revision, invalid,
outcome unknown after an admitted timeout — M10-AUDIT-21); an add
repeated with the same ``snippet_id`` is idempotent.
"""

from __future__ import annotations

import json
import pathlib
from typing import Optional

from . import ids
from . import snippets as snip_mod
from .profiles_store import (NotFoundError, OutcomeUnknownError,
                             StaleRevisionError)
from .store import Store
from .vocabulary import AdmissionError, require_bool, require_int

_SNIPPET_COLS = (
    "snippet_id", "trigger", "name", "kind", "content", "content_rtf",
    "allow_rewrite", "enabled", "revision", "usage_count",
    "last_used_utc", "created_at_utc", "updated_at_utc",
)

_EDITABLE = ("trigger", "name", "kind", "content", "content_rtf",
             "allow_rewrite", "enabled")

_IDENTITY = _EDITABLE

DUPLICATE_TRIGGER = ("another snippet already uses this trigger (the"
                     " engine would keep both literal)")
DUPLICATE_TRIGGER_DISABLED = ("a disabled snippet already uses this"
                              " trigger (rename or delete it first)")


def _row_to_snippet(row) -> snip_mod.Snippet:
    d = dict(zip(_SNIPPET_COLS, row))
    return snip_mod.Snippet(
        snippet_id=d["snippet_id"], trigger=d["trigger"], name=d["name"],
        kind=d["kind"], content=d["content"], content_rtf=d["content_rtf"],
        allow_rewrite=bool(d["allow_rewrite"]), enabled=bool(d["enabled"]),
        revision=d["revision"])


def _admit_changes(changes: dict) -> dict:
    unknown = set(changes) - set(_EDITABLE)
    if unknown:
        raise ValueError(f"unknown snippet fields: {sorted(unknown)}")
    for f, v in changes.items():
        if f in ("allow_rewrite", "enabled"):
            require_bool(f, v)
        elif f == "content_rtf":
            if v is not None and not isinstance(v, str):
                raise AdmissionError("not_a_string", f)
        elif not isinstance(v, str):
            raise AdmissionError("not_a_string", f)
    return dict(changes)


def _trigger_holder(db, trigger: str) -> Optional[tuple]:
    """(snippet_id, enabled) of the row already holding ``trigger``,
    folded exactly as the snapshot folds it (``str.lower``: Unicode case,
    not SQLite's ASCII-only NOCASE), else None."""
    fold = trigger.lower()
    for sid, trig, enabled in db.execute(
            "SELECT snippet_id, trigger, enabled FROM snippets"):
        if trig.lower() == fold:
            return sid, bool(enabled)
    return None


def _duplicate(holder) -> ValueError:
    return ValueError(DUPLICATE_TRIGGER if holder[1]
                      else DUPLICATE_TRIGGER_DISABLED)


class SnippetStore:
    """Snippet persistence (store schema v6, additive)."""

    def __init__(self, store: Store):
        self.store = store
        self.invalid_rows = 0

    # ---- reads -----------------------------------------------------------

    def revision(self) -> int:
        def op(db):
            row = db.execute(
                "SELECT value FROM profiles_meta WHERE key='snippets'"
            ).fetchone()
            return int(row[0]) if row else 0
        return self.store.submit(op) or 0

    def snippets(self) -> list[snip_mod.Snippet]:
        def op(db):
            rows = db.execute(
                f"SELECT {', '.join(_SNIPPET_COLS)} FROM snippets"
                f" ORDER BY trigger COLLATE NOCASE, snippet_id"
            ).fetchall()
            out, bad = [], 0
            for r in rows:
                try:
                    out.append(_row_to_snippet(r))
                except ValueError:
                    bad += 1
            return out, bad
        out, bad = self.store.submit(op)
        self.invalid_rows = bad
        return out

    def snippet(self, snippet_id: str) -> Optional[snip_mod.Snippet]:
        def op(db):
            return db.execute(
                f"SELECT {', '.join(_SNIPPET_COLS)} FROM snippets"
                f" WHERE snippet_id=?", (snippet_id,)).fetchone()
        row = self.store.submit(op)
        return _row_to_snippet(row) if row is not None else None

    # ---- writes ----------------------------------------------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO profiles_meta VALUES('snippets','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def _run(self, op, action: str, entity_id: Optional[str]):
        try:
            return self.store.submit(op)
        except TimeoutError:
            raise OutcomeUnknownError(action, entity_id) from None

    def add_snippet(self, *, trigger: str, name: str, content: str,
                    kind: str = "plain", content_rtf: Optional[str] = None,
                    allow_rewrite: bool = False, enabled: bool = True,
                    snippet_id: Optional[str] = None) -> str:
        require_bool("allow_rewrite", allow_rewrite)
        require_bool("enabled", enabled)
        snippet = snip_mod.Snippet(
            snippet_id=snippet_id or ids.new_id("snip"),
            trigger=trigger, name=name, content=content, kind=kind,
            content_rtf=content_rtf, allow_rewrite=allow_rewrite,
            enabled=enabled, revision=1)
        now = ids.now_utc_iso()

        def op(db):
            row = db.execute(
                f"SELECT {', '.join(_SNIPPET_COLS)} FROM snippets"
                f" WHERE snippet_id=?", (snippet.snippet_id,)).fetchone()
            if row is not None:
                cur = _row_to_snippet(row)
                same = all(getattr(cur, f) == getattr(snippet, f)
                           for f in _IDENTITY)
                return "already_applied" if same else "id_in_use"
            holder = _trigger_holder(db, snippet.trigger)
            if holder is not None:
                return ("duplicate_trigger", holder)
            db.execute(
                f"INSERT INTO snippets({', '.join(_SNIPPET_COLS)})"
                f" VALUES({', '.join('?' * len(_SNIPPET_COLS))})",
                (snippet.snippet_id, snippet.trigger, snippet.name,
                 snippet.kind, snippet.content, snippet.content_rtf,
                 int(snippet.allow_rewrite), int(snippet.enabled), 1, 0,
                 None, now, now))
            self._bump(db.cursor())
            return "created"
        outcome = self._run(op, "add", snippet.snippet_id)
        if isinstance(outcome, tuple):
            raise _duplicate(outcome[1])
        if outcome == "id_in_use":
            raise ValueError("id_in_use")
        return snippet.snippet_id

    def update_snippet(self, snippet_id: str, *,
                       expected_revision: Optional[int] = None,
                       **changes) -> snip_mod.Snippet:
        changes = _admit_changes(changes)
        if expected_revision is not None:
            require_int("expected_revision", expected_revision)
        now = ids.now_utc_iso()

        def op(db):
            row = db.execute(
                f"SELECT {', '.join(_SNIPPET_COLS)} FROM snippets"
                f" WHERE snippet_id=?", (snippet_id,)).fetchone()
            if row is None:
                return ("not_found", None)
            current = _row_to_snippet(row)
            if expected_revision is not None \
                    and current.revision != expected_revision:
                return ("stale", current.revision)
            if not changes:
                return ("unchanged", current)
            merged = {f: getattr(current, f) for f in _EDITABLE}
            merged.update(changes)
            try:
                updated = snip_mod.Snippet(
                    snippet_id=snippet_id, revision=current.revision + 1,
                    **merged)
            except ValueError as e:
                return ("invalid", e)
            holder = _trigger_holder(db, updated.trigger)
            if holder is not None and holder[0] != snippet_id:
                return ("invalid", _duplicate(holder))
            cols = [c for c in _EDITABLE if c in changes]
            vals = [int(getattr(updated, c))
                    if c in ("allow_rewrite", "enabled")
                    else getattr(updated, c) for c in cols]
            cur = db.execute(
                f"UPDATE snippets SET "
                f"{', '.join(f'{c}=?' for c in cols)}, revision=?,"
                f" updated_at_utc=? WHERE snippet_id=? AND revision=?",
                (*vals, updated.revision, now, snippet_id,
                 current.revision))
            if cur.rowcount != 1:
                return ("stale", None)
            self._bump(db.cursor())
            return ("updated", updated)
        outcome, value = self._run(op, "update", snippet_id)
        if outcome == "not_found":
            raise NotFoundError(f"no snippet {snippet_id}")
        if outcome == "stale":
            raise StaleRevisionError(snippet_id, value)
        if outcome == "invalid":
            raise value
        return value

    def delete_snippet(self, snippet_id: str, *,
                       expected_revision: Optional[int] = None):
        if expected_revision is not None:
            require_int("expected_revision", expected_revision)

        def op(db):
            row = db.execute(
                "SELECT revision FROM snippets WHERE snippet_id=?",
                (snippet_id,)).fetchone()
            if row is None:
                return ("not_found", None)
            if expected_revision is not None and row[0] != expected_revision:
                return ("stale", row[0])
            cur = db.execute("DELETE FROM snippets WHERE snippet_id=?",
                             (snippet_id,))
            if cur.rowcount != 1:
                return ("not_found", None)
            self._bump(db.cursor())
            return ("deleted", None)
        outcome, value = self._run(op, "delete", snippet_id)
        if outcome == "not_found":
            raise NotFoundError(f"no snippet {snippet_id}")
        if outcome == "stale":
            raise StaleRevisionError(snippet_id, value)

    def set_enabled(self, snippet_id: str, enabled: bool, *,
                    expected_revision: Optional[int] = None):
        require_bool("enabled", enabled)
        return self.update_snippet(snippet_id,
                                   expected_revision=expected_revision,
                                   enabled=enabled)

    def record_hits(self, snippet_ids) -> int:
        """Applied expansions as usage statistics (not matching state):
        like vocabulary hits, usage never bumps the state counter, so
        an applied snippet never forces a registry rebuild."""
        now = ids.now_utc_iso()
        uniq = sorted(set(snippet_ids))
        if not uniq:
            return 0

        def op(db):
            cur = db.cursor()
            n = 0
            for sid in uniq:
                cur.execute(
                    "UPDATE snippets SET usage_count=usage_count+1,"
                    " last_used_utc=? WHERE snippet_id=?", (now, sid))
                n += cur.rowcount
            return n
        return self.store.submit(op)

    # ---- JSON import/export ----------------------------------------------

    def export_json(self) -> dict:
        return snip_mod.snippets_to_doc(self.snippets())

    def import_json(self, source) -> dict:
        """Upsert by trigger (the trigger is the spoken key): imports
        update settings but never fork a trigger; observed usage stays
        with the store. Idempotent. Documents are admitted strictly."""
        doc = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
        incoming = [snip_mod.Snippet.from_json(d)
                    for d in doc.get("snippets", ())]
        existing = {s.trigger.lower(): s for s in self.snippets()}
        created = updated = unchanged = 0
        for s in incoming:
            cur = existing.get(s.trigger.lower())
            if cur is None:
                self.add_snippet(
                    trigger=s.trigger, name=s.name, content=s.content,
                    kind=s.kind, content_rtf=s.content_rtf,
                    allow_rewrite=s.allow_rewrite, enabled=s.enabled)
                created += 1
                continue
            changes = {}
            for col in ("name", "kind", "content", "content_rtf",
                        "allow_rewrite", "enabled"):
                if getattr(s, col) != getattr(cur, col):
                    changes[col] = getattr(s, col)
            if changes:
                self.update_snippet(cur.snippet_id, **changes)
                updated += 1
            else:
                unchanged += 1
        return {"created": created, "updated": updated,
                "unchanged": unchanged}
