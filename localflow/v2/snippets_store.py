"""Persistent snippets over the single-writer store (V2 M10).

The M05 ``vocabulary_store`` pattern: versioned rows (the revision
counter is the snippet's version, M10-AC02) plus a monotonic state
counter in ``profiles_meta`` so the app's frozen snippet registry
invalidates on edit. The NOCASE unique trigger index keeps the stored
set unambiguous (a duplicate trigger would be ambiguous at match
time); the caller-thread probe raises a plain ValueError so store
content never reaches the event channel. Usage statistics ride the
same rows and — like vocabulary usage — never bump the state counter.
"""

from __future__ import annotations

import json
import pathlib
from typing import Optional

from . import ids
from . import snippets as snip_mod
from .store import Store

_SNIPPET_COLS = (
    "snippet_id", "trigger", "name", "kind", "content", "content_rtf",
    "allow_rewrite", "enabled", "revision", "usage_count",
    "last_used_utc", "created_at_utc", "updated_at_utc",
)

_EDITABLE = ("trigger", "name", "kind", "content", "content_rtf",
             "allow_rewrite", "enabled")


def _row_to_snippet(row) -> snip_mod.Snippet:
    d = dict(zip(_SNIPPET_COLS, row))
    return snip_mod.Snippet(
        snippet_id=d["snippet_id"], trigger=d["trigger"], name=d["name"],
        kind=d["kind"], content=d["content"], content_rtf=d["content_rtf"],
        allow_rewrite=bool(d["allow_rewrite"]), enabled=bool(d["enabled"]),
        revision=d["revision"])


class SnippetStore:
    """Snippet persistence (store schema v6, additive)."""

    def __init__(self, store: Store):
        self.store = store

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
            return [_row_to_snippet(r) for r in rows]
        return self.store.submit(op)

    def snippet(self, snippet_id: str) -> Optional[snip_mod.Snippet]:
        for s in self.snippets():
            if s.snippet_id == snippet_id:
                return s
        return None

    # ---- writes ----------------------------------------------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO profiles_meta VALUES('snippets','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def _trigger_exists(self, trigger: str,
                        exclude_id: Optional[str] = None) -> bool:
        def op(db):
            row = db.execute(
                "SELECT 1 FROM snippets WHERE trigger=? COLLATE NOCASE"
                " AND snippet_id IS NOT ?",
                (snip_mod.validate_trigger(trigger), exclude_id or "")
            ).fetchone()
            return row is not None
        return self.store.submit(op)

    def add_snippet(self, *, trigger: str, name: str, content: str,
                    kind: str = "plain", content_rtf: Optional[str] = None,
                    allow_rewrite: bool = False, enabled: bool = True,
                    snippet_id: Optional[str] = None) -> str:
        snippet = snip_mod.Snippet(
            snippet_id=snippet_id or ids.new_id("snip"),
            trigger=trigger, name=name, content=content, kind=kind,
            content_rtf=content_rtf, allow_rewrite=allow_rewrite,
            enabled=enabled, revision=1)
        if self._trigger_exists(snippet.trigger):
            raise ValueError(
                "another snippet already uses this trigger (the engine"
                " would keep both literal)")
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                f"INSERT INTO snippets({', '.join(_SNIPPET_COLS)})"
                f" VALUES({', '.join('?' * len(_SNIPPET_COLS))})",
                (snippet.snippet_id, snippet.trigger, snippet.name,
                 snippet.kind, snippet.content, snippet.content_rtf,
                 int(snippet.allow_rewrite), int(snippet.enabled), 1, 0,
                 None, now, now))
            self._bump(db.cursor())
        self.store.submit(op)
        return snippet.snippet_id

    def update_snippet(self, snippet_id: str, **changes
                       ) -> snip_mod.Snippet:
        unknown = set(changes) - set(_EDITABLE)
        if unknown:
            raise ValueError(f"unknown snippet fields: {sorted(unknown)}")
        current = self.snippet(snippet_id)
        if current is None:
            raise KeyError(f"no snippet {snippet_id}")
        if not changes:
            return current
        merged = {
            "trigger": current.trigger, "name": current.name,
            "kind": current.kind, "content": current.content,
            "content_rtf": current.content_rtf,
            "allow_rewrite": current.allow_rewrite,
            "enabled": current.enabled,
        }
        merged.update(changes)
        # Construct for validation (trigger tokens, kind, placeholders).
        snip_mod.Snippet(snippet_id=snippet_id,
                         revision=current.revision + 1, **merged)
        if "trigger" in changes and self._trigger_exists(
                merged["trigger"], exclude_id=snippet_id):
            raise ValueError(
                "another snippet already uses this trigger (the engine"
                " would keep both literal)")
        now = ids.now_utc_iso()
        sets, vals = [], []
        for col in _EDITABLE:
            if col in changes:
                sets.append(f"{col}=?")
                v = changes[col]
                if col in ("allow_rewrite", "enabled"):
                    v = int(bool(v))
                vals.append(v)
        sets.append("revision=revision+1")
        sets.append("updated_at_utc=?")
        vals.extend([now, snippet_id])

        def op(db):
            db.execute(
                f"UPDATE snippets SET {', '.join(sets)} WHERE snippet_id=?",
                vals)
            self._bump(db.cursor())
        self.store.submit(op)
        out = self.snippet(snippet_id)
        assert out is not None
        return out

    def delete_snippet(self, snippet_id: str):
        if self.snippet(snippet_id) is None:
            raise KeyError(f"no snippet {snippet_id}")

        def op(db):
            db.execute("DELETE FROM snippets WHERE snippet_id=?",
                       (snippet_id,))
            self._bump(db.cursor())
        self.store.submit(op)

    def set_enabled(self, snippet_id: str, enabled: bool):
        return self.update_snippet(snippet_id, enabled=enabled)

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
        with the store. Idempotent."""
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
