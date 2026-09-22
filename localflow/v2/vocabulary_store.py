"""Persistent scoped-vocabulary store (V2 M05, Spec S08/S11).

``VocabularyStore`` owns the dictionary tables inside the single-writer
SQLite ``Store`` (schema v3): versioned canonical/alias records, an
append-only edit history, a monotonic state counter for snapshot
invalidation, and usage (hit) recording. Every mutation is one writer
transaction that also bumps the counter and appends history, so an edit
either fully lands or never happened.

The seven legacy dictionary terms are adopted, not replaced: they seed
approved global entries from the legacy artifacts M02 imported, and the
Claude/Claude Code coding suggestions ship visible-but-unapproved (S11).
"""

from __future__ import annotations

import json
import pathlib
from typing import Optional

from . import ids
from . import vocabulary as vocab
from .store import Store

_ENTRY_COLS = (
    "entry_id", "canonical", "language", "kind", "matching_mode",
    "scope_kind", "scope_value", "priority", "pinned", "usage_count",
    "last_used_utc", "origin", "enabled", "approved", "verification",
    "revision", "created_at_utc", "updated_at_utc",
)

# Editable fields update_entry accepts (everything but identity/timestamps).
_EDITABLE = (
    "canonical", "language", "kind", "matching_mode", "scope_kind",
    "scope_value", "priority", "pinned", "origin", "enabled", "approved",
    "verification", "aliases",
)


def _normalize_alias_items(aliases) -> list[tuple[str, bool]]:
    """Aliases arrive as str | (text, approved) tuples | Alias records
    (``approve_entry``/``import_json`` pass tuples); normalize to
    validated (text, approved) pairs."""
    out = []
    seen = set()
    for a in aliases:
        if isinstance(a, str):
            text, flag = a, True
        elif isinstance(a, tuple):
            text, flag = a[0], (a[1] if len(a) > 1 else True)
        else:
            text, flag = a.alias, a.approved
        norm = vocab._validate_alias(text)
        if norm.lower() in seen:
            raise ValueError(f"duplicate alias: {norm!r}")
        seen.add(norm.lower())
        out.append((norm, bool(flag)))
    return out


def _row_to_entry(row, alias_rows) -> vocab.VocabularyEntry:
    d = dict(zip(_ENTRY_COLS, row))
    d["aliases"] = [
        vocab.Alias(alias=a[0], approved=bool(a[1]), language=a[2])
        for a in alias_rows]
    return vocab.VocabularyEntry(
        entry_id=d["entry_id"], canonical=d["canonical"],
        language=d["language"], kind=d["kind"],
        matching_mode=d["matching_mode"], scope_kind=d["scope_kind"],
        scope_value=d["scope_value"], priority=d["priority"],
        pinned=bool(d["pinned"]), usage_count=d["usage_count"],
        last_used_utc=d["last_used_utc"], origin=d["origin"],
        enabled=bool(d["enabled"]), approved=bool(d["approved"]),
        verification=d["verification"], revision=d["revision"],
        aliases=tuple(d["aliases"]))


class VocabularyStore:
    """Dictionary persistence over the single-writer Store."""

    def __init__(self, store: Store):
        self.store = store

    # ---- reads -----------------------------------------------------------

    def revision(self) -> int:
        def op(db):
            row = db.execute(
                "SELECT value FROM vocabulary_meta WHERE key='revision'"
            ).fetchone()
            return int(row[0]) if row else 0
        return self.store.submit(op) or 0

    def entries(self) -> list[vocab.VocabularyEntry]:
        def op(db):
            rows = db.execute(
                f"SELECT {', '.join(_ENTRY_COLS)} FROM vocabulary_entries"
                f" ORDER BY canonical COLLATE NOCASE, entry_id"
            ).fetchall()
            alias_rows = db.execute(
                "SELECT entry_id, alias, approved, language"
                " FROM vocabulary_aliases ORDER BY alias COLLATE NOCASE"
            ).fetchall()
            by_entry: dict[str, list] = {}
            for r in alias_rows:
                by_entry.setdefault(r[0], []).append((r[1], r[2], r[3]))
            return [_row_to_entry(row, by_entry.get(row[0], ()))
                    for row in rows]
        return self.store.submit(op)

    def entry(self, entry_id: str) -> Optional[vocab.VocabularyEntry]:
        for e in self.entries():
            if e.entry_id == entry_id:
                return e
        return None

    def history(self, entry_id: str) -> list[dict]:
        def op(db):
            rows = db.execute(
                "SELECT revision, action, change_json, created_at_utc"
                " FROM vocabulary_history WHERE entry_id=?"
                " ORDER BY history_id", (entry_id,)).fetchall()
            return [{"revision": r[0], "action": r[1],
                     "change": json.loads(r[2]), "created_at_utc": r[3]}
                    for r in rows]
        return self.store.submit(op)

    def snapshot(self, scope_ctx: vocab.ScopeContext | None = None,
                 ) -> vocab.VocabularySnapshot:
        """The immutable, scope-filtered state a job captures. Row reads
        run on the writer thread; snapshot construction is pure and runs
        on the caller so the writer is never blocked on hashing."""
        return vocab.VocabularySnapshot(self.entries(), scope_ctx)

    # ---- writes ----------------------------------------------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO vocabulary_meta VALUES('revision','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def _history(self, cur, entry_id: str, revision: int, action: str,
                 change: dict) -> None:
        cur.execute(
            "INSERT INTO vocabulary_history(entry_id, revision, action,"
            " change_json, created_at_utc) VALUES(?,?,?,?,?)",
            (entry_id, revision, action,
             json.dumps(change, ensure_ascii=False, sort_keys=True),
             ids.now_utc_iso()))

    def add_entry(self, canonical: str, aliases=(), *,
                  language: str | None = None, kind: str = "term",
                  matching_mode: str = "phrase",
                  scope_kind: str = "global",
                  scope_value: str | None = None, priority: int = 0,
                  pinned: bool = False, origin: str = "user",
                  enabled: bool = True, approved: bool = False,
                  verification: str | None = None,
                  entry_id: str | None = None) -> str:
        canonical = vocab._validate_canonical(canonical)
        alias_records = _normalize_alias_items(aliases)
        if verification is None:
            verification = ("explicit" if approved else "suggested")
        # Construct once for validation before touching the database.
        entry = vocab.VocabularyEntry(
            entry_id=entry_id or ids.new_id("vocab"), canonical=canonical,
            language=language, kind=kind, matching_mode=matching_mode,
            scope_kind=scope_kind, scope_value=scope_value,
            priority=priority, pinned=pinned, origin=origin,
            enabled=enabled, approved=approved, verification=verification,
            aliases=tuple(vocab.Alias(alias=t, approved=f, language=language)
                          for t, f in alias_records))
        # Duplicate probe BEFORE the writer: a rejection raised here is
        # a plain ValueError on the caller thread and never reaches the
        # store's error channel, whose event detail must stay free of
        # dictionary content. (Panel edits are main-thread serialized,
        # and the in-op probe below remains as the backstop.)
        if self._canonical_exists(canonical, scope_kind, scope_value):
            raise ValueError(
                "an entry with this canonical spelling already exists"
                " in the requested scope")
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                f"INSERT INTO vocabulary_entries({', '.join(_ENTRY_COLS)})"
                f" VALUES({', '.join('?' * len(_ENTRY_COLS))})",
                (entry.entry_id, canonical, language, kind, matching_mode,
                 scope_kind, scope_value, priority, int(pinned), 0, None,
                 origin, int(enabled), int(approved), verification, 1,
                 now, now))
            for text, flag in alias_records:
                db.execute(
                    "INSERT INTO vocabulary_aliases(entry_id, alias,"
                    " language, approved) VALUES(?,?,?,?)",
                    (entry.entry_id, text, language, int(flag)))
            self._history(db.cursor(), entry.entry_id, 1, "created", {
                "canonical": canonical, "scope": [scope_kind, scope_value],
                "aliases": [t for t, _ in alias_records],
                "origin": origin, "approved": approved})
            self._bump(db.cursor())
        self.store.submit(op)
        return entry.entry_id

    def update_entry(self, entry_id: str, **changes) -> vocab.VocabularyEntry:
        unknown = set(changes) - set(_EDITABLE)
        if unknown:
            raise ValueError(f"unknown entry fields: {sorted(unknown)}")
        for k, v in changes.items():
            # language/scope_value are genuinely nullable; anything else
            # passed as None is a caller bug, not a silent no-op.
            if v is None and k not in ("language", "scope_value"):
                raise ValueError(f"field {k!r} may not be None")
        current = self.entry(entry_id)
        if current is None:
            raise KeyError(f"no vocabulary entry {entry_id}")
        fields = dict(changes)
        if not fields:
            return current  # nothing requested: no history, no bump
        if "canonical" in fields:
            fields["canonical"] = vocab._validate_canonical(
                fields["canonical"])
        if "aliases" in fields:
            fields["aliases"] = _normalize_alias_items(fields["aliases"])
        merged = dataclass_values(current)
        merged.update(fields)
        # Construct for validation (scope value rules, enum values…).
        vocab.VocabularyEntry(**merged)
        now = ids.now_utc_iso()

        def op(db):
            cur = db.cursor()
            sets, vals = [], []
            for col in ("canonical", "language", "kind", "matching_mode",
                        "scope_kind", "scope_value", "priority", "pinned",
                        "origin", "enabled", "approved", "verification"):
                if col in fields:
                    sets.append(f"{col}=?")
                    v = fields[col]
                    if col in ("pinned", "enabled", "approved"):
                        v = int(bool(v))
                    vals.append(v)
            # Any real change — columns OR aliases — versions the entry:
            # the row's revision must always track its history.
            new_revision = current.revision + 1
            sets.append("revision=?")
            vals.append(new_revision)
            sets.append("updated_at_utc=?")
            vals.append(now)
            vals.append(entry_id)
            cur.execute(
                f"UPDATE vocabulary_entries SET {', '.join(sets)}"
                f" WHERE entry_id=?", vals)
            if "aliases" in fields:
                cur.execute(
                    "DELETE FROM vocabulary_aliases WHERE entry_id=?",
                    (entry_id,))
                for text, flag in fields["aliases"]:
                    cur.execute(
                        "INSERT INTO vocabulary_aliases(entry_id, alias,"
                        " language, approved) VALUES(?,?,?,?)",
                        (entry_id, text,
                         fields.get("language", current.language),
                         int(flag)))
            change = dict(fields)
            if "aliases" in change:
                change["aliases"] = [t for t, _ in fields["aliases"]]
            self._history(cur, entry_id, new_revision, "updated", change)
            self._bump(cur)
        self.store.submit(op)
        out = self.entry(entry_id)
        assert out is not None
        return out

    def set_enabled(self, entry_id: str, enabled: bool):
        return self.update_entry(entry_id, enabled=enabled)

    def approve_entry(self, entry_id: str):
        """Approve the entry and every alias (one-click approval, S11):
        from here the rule may rewrite text and its applications count
        as hits (AC04)."""
        current = self.entry(entry_id)
        if current is None:
            raise KeyError(f"no vocabulary entry {entry_id}")
        aliases = [(a.alias, True) for a in current.aliases]
        return self.update_entry(
            entry_id, approved=True, verification="explicit",
            aliases=aliases)

    def set_scope(self, entry_id: str, scope_kind: str,
                  scope_value: str | None):
        return self.update_entry(entry_id, scope_kind=scope_kind,
                                 scope_value=scope_value)

    def delete_entry(self, entry_id: str):
        current = self.entry(entry_id)
        if current is None:
            raise KeyError(f"no vocabulary entry {entry_id}")

        def op(db):
            cur = db.cursor()
            cur.execute(
                "DELETE FROM vocabulary_entries WHERE entry_id=?",
                (entry_id,))
            cur.execute(
                "DELETE FROM vocabulary_aliases WHERE entry_id=?",
                (entry_id,))
            self._history(cur, entry_id, current.revision + 1, "deleted",
                          {"canonical": current.canonical})
            self._bump(cur)
        self.store.submit(op)

    def record_hits(self, entry_ids: list[str]) -> int:
        """Record applied approved matches as usage (S11 ranking, task 5):
        usage feeds frequency/recency retrieval; suggestions never reach
        here because only approved aliases can produce edits. The caller
        contract is the ledger's applied rule ids — approval was checked
        at match time under the job's frozen revision, so an entry
        disabled after the job started still records its applied use.
        Usage is statistics, not matching state: it deliberately does
        NOT bump the store revision (and is excluded from the snapshot
        revision hash), so a hit never forces a snapshot rebuild on the
        next job — selector ranking sees the last-edited snapshot."""
        ids_now = ids.now_utc_iso()
        uniq = sorted(set(entry_ids))
        if not uniq:
            return 0

        def op(db):
            cur = db.cursor()
            n = 0
            for entry_id in uniq:
                cur.execute(
                    "UPDATE vocabulary_entries SET usage_count="
                    "usage_count+1, last_used_utc=? WHERE entry_id=?",
                    (ids_now, entry_id))
                n += cur.rowcount
            return n
        return self.store.submit(op)

    # ---- seeding (legacy adoption + visible suggestions) -----------------

    def seed_legacy_terms(self, terms: list[str]) -> dict:
        """Adopt legacy dictionary terms as approved global entries
        (AC01). Idempotent per canonical; existing entries are never
        rewritten."""
        imported = skipped = 0
        for term in terms:
            if self._canonical_exists(term, "global", None):
                skipped += 1
                continue
            self.add_entry(
                canonical=term, aliases=(), origin="legacy_import",
                approved=True, verification="explicit")
            imported += 1
        return {"imported": imported, "skipped": skipped}

    def seed_from_legacy_artifacts(self) -> dict:
        """Seed from the legacy dictionary artifacts M02 imported (the
        live path — the seven terms travel with the store, not a file)."""

        def op(db):
            rows = db.execute(
                "SELECT content_text FROM artifacts WHERE"
                " role='legacy_dictionary_term' AND purged=0"
                " ORDER BY artifact_id").fetchall()
            return [r[0] for r in rows if r[0]]
        terms = self.store.submit(op)
        return self.seed_legacy_terms(terms)

    def seed_suggested_coding_terms(self) -> dict:
        """Claude/Claude Code as visible suggested coding entries (S11,
        task 3): unapproved, profile-scoped 'coding' — they never rewrite
        text until approved, and a dismissed suggestion (disabled entry)
        does not reappear."""
        added = skipped = 0
        for canonical, alias in (("Claude", "clod"),
                                 ("Claude Code", "clod code")):
            if self._canonical_exists(canonical, "profile", "coding"):
                skipped += 1
                continue
            self.add_entry(
                canonical=canonical, aliases=[alias],
                scope_kind="profile", scope_value="coding",
                origin="suggested", approved=False,
                verification="suggested")
            added += 1
        return {"added": added, "skipped": skipped}

    def _canonical_exists(self, canonical: str, scope_kind: str,
                           scope_value) -> bool:
        def op(db):
            return db.execute(
                "SELECT 1 FROM vocabulary_entries WHERE canonical=?"
                " COLLATE NOCASE AND scope_kind=? AND"
                " IFNULL(scope_value,'')=IFNULL(?,'')",
                (canonical, scope_kind, scope_value)).fetchone() is not None
        return self.store.submit(op)

    # ---- JSON import/export (bulk, S11 dictionary UI) ---------------------

    def export_json(self) -> dict:
        return vocab.entries_to_doc(self.entries())

    def import_json(self, source, *, additive_only: bool = True) -> dict:
        """Bulk import (S11). Upsert by (canonical, scope) — the
        canonical spelling IS the key, so imports update settings
        (aliases, scope-independent fields) but never re-key an entry;
        re-spelling goes through update_entry. Observed usage (count/
        last-use) stays with the store — a file never fabricates usage
        history. Idempotent: re-importing the same document changes
        nothing."""
        doc = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
        entries = [vocab.VocabularyEntry.from_json(d)
                   for d in doc.get("entries", [])]
        created = updated = unchanged = 0
        # Case-insensitive key, matching the DB's NOCASE uniqueness: a
        # file's "servo" updates the stored "Servo", never forks it.
        existing = {(e.canonical.lower(), e.scope_kind, e.scope_value or ""): e
                    for e in self.entries()}
        for e in entries:
            key = (e.canonical.lower(), e.scope_kind, e.scope_value or "")
            cur = existing.get(key)
            if cur is None:
                self.add_entry(
                    canonical=e.canonical,
                    aliases=[vocab.Alias(a.alias, a.approved, a.language)
                             for a in e.aliases],
                    language=e.language, kind=e.kind,
                    matching_mode=e.matching_mode,
                    scope_kind=e.scope_kind, scope_value=e.scope_value,
                    priority=e.priority, pinned=e.pinned, origin=e.origin,
                    enabled=e.enabled, approved=e.approved,
                    verification=e.verification)
                created += 1
                continue
            changes = {}
            for col in ("language", "kind", "matching_mode", "priority",
                        "pinned", "origin", "enabled", "approved",
                        "verification"):
                if getattr(e, col) != getattr(cur, col):
                    changes[col] = getattr(e, col)
            new_aliases = [(a.alias, a.approved) for a in e.aliases]
            old_aliases = [(a.alias, a.approved) for a in cur.aliases]
            if new_aliases != old_aliases:
                changes["aliases"] = new_aliases
            if changes:
                self.update_entry(cur.entry_id, **changes)
                updated += 1
            else:
                unchanged += 1
        return {"created": created, "updated": updated,
                "unchanged": unchanged}


def dataclass_values(entry: vocab.VocabularyEntry) -> dict:
    d = {k: getattr(entry, k) for k in (
        "entry_id", "canonical", "language", "kind", "matching_mode",
        "scope_kind", "scope_value", "priority", "pinned", "usage_count",
        "last_used_utc", "origin", "enabled", "approved", "verification",
        "revision")}
    d["aliases"] = [(a.alias, a.approved) for a in entry.aliases]
    return d
