"""Persistent scoped-vocabulary store (V2 M05, Spec S08/S11).

``VocabularyStore`` owns the dictionary tables inside the single-writer
SQLite ``Store`` (schema v3 tables, current store schema 11): versioned
canonical/alias records, an append-only edit history, a monotonic state
counter for snapshot invalidation, and usage (hit) recording. Every
mutation is one writer transaction that also bumps the counter and
appends history, so an edit either fully lands or never happened.

M05 remediation (M05-AUDIT-06): every read-modify-write — update,
approve, delete and each import upsert — reads the AUTHORITATIVE row,
merges, validates and versions it INSIDE its writer operation, so a
caller's stale read can never commit an invalid combined scope, reuse a
next revision, orphan alias/history rows after a delete or approve a
stale alias list. ``expected_revision`` adds explicit compare-and-swap
for callers that act on something the user saw (the Dictionary panel).
Expected outcomes (missing, stale, duplicate, invalid) come back from
the op as statuses and are raised on the CALLER thread as typed,
content-free errors — they never become ``store.write_failed`` events.

The seven legacy dictionary terms are adopted, not replaced: they seed
approved global entries from the legacy artifacts M02 imported, and the
Claude/Claude Code coding suggestions ship visible-but-unapproved (S11).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import string
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
_BOOL_FIELDS = ("pinned", "enabled", "approved")
_STR_FIELDS = ("kind", "matching_mode", "scope_kind", "origin",
               "verification")
_ROW_FIELDS = ("canonical", "language", "kind", "matching_mode",
               "scope_kind", "scope_value", "priority", "pinned", "origin",
               "enabled", "approved", "verification")

# The declared import identity is SQLite NOCASE — ASCII case only, the
# exact rule of the unique index (M05-AUDIT-11 / design D6). "Claude" and
# "CLAUDE" are one identity; "Éclair" and "éclair" are two, exactly as
# the database sees them. No broader Unicode equivalence is claimed.
_ASCII_FOLD = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class StaleEntryError(ValueError):
    """The entry changed since the caller read it (compare-and-swap)."""


class ImportRejected(ValueError):
    """A whole import file refused before any write (content-free)."""

    def __init__(self, code: str, where: Optional[str] = None):
        self.code = code
        self.where = where
        super().__init__(f"import rejected: {code}"
                         + (f" at {where}" if where else ""))


def identity_key(canonical: str, scope_kind: str, scope_value) -> tuple:
    return (canonical.translate(_ASCII_FOLD), scope_kind, scope_value or "")


def _normalize_alias_items(aliases) -> list[tuple[str, bool, Optional[str]]]:
    """Aliases arrive as str | (text[, approved[, language]]) tuples |
    Alias records | {"alias", "approved", "language"} objects; normalize
    to validated (text, approved, language) triples. ``language`` None
    means inherit the entry's language. Booleans are strict — a string
    or integer flag is refused, never truth-coerced (M05-AUDIT-07)."""
    # A list or tuple only (review R7): a mapping would iterate its keys
    # and silently drop the flags; a set has no stable order.
    if not isinstance(aliases, (list, tuple)):
        raise vocab.AdmissionError("not_a_list", "aliases")
    out = []
    seen = set()
    for a in aliases:
        if isinstance(a, str):
            text, flag, lang = a, True, None
        elif isinstance(a, tuple) and 1 <= len(a) <= 3:
            text = a[0]
            flag = a[1] if len(a) > 1 else True
            lang = a[2] if len(a) > 2 else None
        elif isinstance(a, vocab.Alias):
            text, flag, lang = a.alias, a.approved, a.language
        elif isinstance(a, dict):
            text = a.get("alias")
            flag = a.get("approved", True)
            lang = a.get("language")
        else:
            raise vocab.AdmissionError("invalid_alias_item", "aliases")
        vocab.require_bool("aliases[].approved", flag)
        vocab.require_opt_str("aliases[].language", lang)
        norm = vocab._validate_alias(text)
        if norm.lower() in seen:
            raise vocab.AdmissionError("duplicate_alias", "aliases")
        seen.add(norm.lower())
        out.append((norm, flag, lang))
    return out


def _row_to_entry(row, alias_rows) -> vocab.VocabularyEntry:
    d = dict(zip(_ENTRY_COLS, row))
    return vocab.VocabularyEntry(
        entry_id=d["entry_id"], canonical=d["canonical"],
        language=d["language"], kind=d["kind"],
        matching_mode=d["matching_mode"], scope_kind=d["scope_kind"],
        # A legacy global row carrying a value reads as the one global
        # identity it always behaved as (review R6).
        scope_value=None if d["scope_kind"] == "global"
        else d["scope_value"], priority=d["priority"],
        pinned=bool(d["pinned"]), usage_count=d["usage_count"],
        last_used_utc=d["last_used_utc"], origin=d["origin"],
        enabled=bool(d["enabled"]), approved=bool(d["approved"]),
        verification=d["verification"], revision=d["revision"],
        aliases=tuple(vocab.Alias(alias=a[0], approved=bool(a[1]),
                                  language=a[2]) for a in alias_rows))


def _read_entry(db, entry_id) -> Optional[vocab.VocabularyEntry]:
    row = db.execute(
        f"SELECT {', '.join(_ENTRY_COLS)} FROM vocabulary_entries"
        f" WHERE entry_id=?", (entry_id,)).fetchone()
    if row is None:
        return None
    alias_rows = db.execute(
        "SELECT alias, approved, language FROM vocabulary_aliases"
        " WHERE entry_id=? ORDER BY alias COLLATE NOCASE, alias",
        (entry_id,)).fetchall()
    return _row_to_entry(row, alias_rows)


def _find_identity(db, canonical, scope_kind, scope_value,
                   exclude: Optional[str] = None) -> Optional[str]:
    row = db.execute(
        "SELECT entry_id FROM vocabulary_entries WHERE canonical=?"
        " COLLATE NOCASE AND scope_kind=? AND (scope_kind='global' OR"
        " IFNULL(scope_value,'')=IFNULL(?,''))"
        + (" AND entry_id<>?" if exclude else ""),
        (canonical, scope_kind, scope_value)
        + ((exclude,) if exclude else ())).fetchone()
    return row[0] if row else None


def _alias_identity(entry: vocab.VocabularyEntry) -> list:
    """Order-insensitive alias state (M05-AUDIT-10): text, approval and
    STORED language — None (inherit) and an explicit override are
    different states even when they currently resolve to the same
    language (review R3) — storage order is never identity."""
    return sorted((a.alias.casefold(), a.alias, a.approved,
                   a.language or "") for a in entry.aliases)


_INHERIT_KEY = "alias_language_inherit_v1"


def _inherit_migrated(db) -> bool:
    return db.execute("SELECT 1 FROM vocabulary_meta WHERE key=?",
                      (_INHERIT_KEY,)).fetchone() is not None


class VocabularyStore:
    """Dictionary persistence over the single-writer Store."""

    def __init__(self, store: Store):
        self.store = store
        self.last_written_revision = 0
        try:
            self.migrate_alias_language()
        except Exception:
            # Best effort: until it runs, the legacy inheritance rule
            # stays in force (the store works either way).
            pass

    def migrate_alias_language(self) -> int:
        """One-time, idempotent (review R4): stores before the M05
        remediation MATERIALIZED each alias's language as a copy of its
        entry's; those rows become NULL (inherit), which is what they
        meant — the effective language of every alias is unchanged.
        From then on a stored value is an explicit override, even when it
        equals the entry's language. Returns the rows converted."""
        def op(db):
            if _inherit_migrated(db):
                return 0
            cur = db.cursor()
            cur.execute(
                "UPDATE vocabulary_aliases SET language=NULL WHERE"
                " language IS NOT NULL AND language=(SELECT e.language"
                " FROM vocabulary_entries e WHERE"
                " e.entry_id=vocabulary_aliases.entry_id)")
            changed = cur.rowcount
            cur.execute("INSERT INTO vocabulary_meta VALUES(?, '1')",
                        (_INHERIT_KEY,))
            if changed:
                self._bump(cur)
            return changed
        return self.store.submit(op)

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
                " FROM vocabulary_aliases ORDER BY alias COLLATE NOCASE, alias"
            ).fetchall()
            by_entry: dict[str, list] = {}
            for r in alias_rows:
                by_entry.setdefault(r[0], []).append((r[1], r[2], r[3]))
            return [_row_to_entry(row, by_entry.get(row[0], ()))
                    for row in rows]
        return self.store.submit(op)

    def entry(self, entry_id: str) -> Optional[vocab.VocabularyEntry]:
        return self.store.submit(lambda db: _read_entry(db, entry_id))

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

    def integrity_report(self) -> dict:
        """Content-free counts that tell a TORN dictionary from a healthy
        one after the store's schema repair (M05-AUDIT-18): entries that
        vanished without ever being deleted (the entries table was lost
        while their history/aliases survive), alias rows without an
        entry, and entries whose recorded alias set is gone (the alias
        table was lost). A repaired empty table is never a recovery."""
        def op(db):
            # Vanished = never deleted, no entry row, but evidence it
            # existed: its history OR its surviving alias rows (review
            # R11 — entries and history lost together leave orphans).
            vanished = db.execute(
                "SELECT count(*) FROM (SELECT entry_id FROM"
                " vocabulary_history UNION SELECT entry_id FROM"
                " vocabulary_aliases) AS known WHERE entry_id NOT IN"
                " (SELECT entry_id FROM vocabulary_entries) AND entry_id"
                " NOT IN (SELECT entry_id FROM vocabulary_history WHERE"
                " action='deleted')"
            ).fetchone()[0]
            orphans = db.execute(
                "SELECT count(*) FROM vocabulary_aliases WHERE entry_id"
                " NOT IN (SELECT entry_id FROM vocabulary_entries)"
            ).fetchone()[0]
            bare = {r[0] for r in db.execute(
                "SELECT entry_id FROM vocabulary_entries e WHERE NOT EXISTS"
                " (SELECT 1 FROM vocabulary_aliases a WHERE"
                " a.entry_id=e.entry_id)")}
            latest: dict[str, list] = {}
            if bare:
                for eid, cj in db.execute(
                        "SELECT entry_id, change_json FROM"
                        " vocabulary_history ORDER BY history_id"):
                    if eid in bare and '"aliases"' in cj:
                        ch = json.loads(cj)
                        if "aliases" in ch:
                            latest[eid] = ch["aliases"]
            missing = sum(1 for v in latest.values() if v)
            return {"vanished_entries": vanished,
                    "orphan_alias_rows": orphans,
                    "entries_missing_aliases": missing}
        return self.store.submit(op)

    # ---- writer-side helpers (run INSIDE one writer op) ------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO vocabulary_meta VALUES('revision','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
        # The newest revision THIS process wrote (review Q2): a caller
        # holding state read at an older revision knows it is stale even
        # when a later read fails. A rolled-back op only makes it look
        # newer — the conservative direction.
        row = cur.execute("SELECT value FROM vocabulary_meta WHERE"
                          " key='revision'").fetchone()
        if row is not None:
            self.last_written_revision = max(self.last_written_revision,
                                             int(row[0]))

    def _history(self, cur, entry_id: str, revision: int, action: str,
                 change: dict) -> None:
        cur.execute(
            "INSERT INTO vocabulary_history(entry_id, revision, action,"
            " change_json, created_at_utc) VALUES(?,?,?,?,?)",
            (entry_id, revision, action,
             json.dumps(change, ensure_ascii=False, sort_keys=True),
             ids.now_utc_iso()))

    def _insert(self, db, entry: vocab.VocabularyEntry, now: str) -> None:
        db.execute(
            f"INSERT INTO vocabulary_entries({', '.join(_ENTRY_COLS)})"
            f" VALUES({', '.join('?' * len(_ENTRY_COLS))})",
            (entry.entry_id, entry.canonical, entry.language, entry.kind,
             entry.matching_mode, entry.scope_kind, entry.scope_value,
             entry.priority, int(entry.pinned), 0, None, entry.origin,
             int(entry.enabled), int(entry.approved), entry.verification,
             1, now, now))
        for a in entry.aliases:
            db.execute(
                "INSERT INTO vocabulary_aliases(entry_id, alias,"
                " language, approved) VALUES(?,?,?,?)",
                (entry.entry_id, a.alias, a.language, int(a.approved)))
        self._history(db.cursor(), entry.entry_id, 1, "created", {
            "canonical": entry.canonical,
            "scope": [entry.scope_kind, entry.scope_value],
            "aliases": [a.alias for a in entry.aliases],
            "origin": entry.origin, "approved": entry.approved})
        self._bump(db.cursor())

    def _apply_update(self, db, cur: vocab.VocabularyEntry, fields: dict,
                      now: str):
        """Merge ``fields`` into the AUTHORITATIVE current entry, validate
        the merged state, version and write it. Returns a status tuple."""
        merged = {k: getattr(cur, k) for k in (
            "entry_id", "canonical", "language", "kind", "matching_mode",
            "scope_kind", "scope_value", "priority", "pinned",
            "usage_count", "last_used_utc", "origin", "enabled",
            "approved", "verification")}
        fields = dict(fields)
        if fields.get("scope_kind") == "global" \
                and "scope_value" not in fields:
            fields["scope_value"] = None     # one global identity (R6)
        merged.update({k: v for k, v in fields.items() if k != "aliases"})
        triples = fields.get("aliases")
        aliases = tuple(vocab.Alias(t, f, lang) for t, f, lang in triples) \
            if triples is not None else cur.aliases
        new_revision = cur.revision + 1
        try:
            valid = vocab.VocabularyEntry(**merged, aliases=aliases,
                                          revision=new_revision)
        except (ValueError, TypeError) as e:
            return ("invalid", str(e))
        if "scope_value" in fields:
            fields["scope_value"] = valid.scope_value
            merged["scope_value"] = valid.scope_value
        if any(k in fields for k in ("canonical", "scope_kind",
                                     "scope_value")) and _find_identity(
                db, merged["canonical"], merged["scope_kind"],
                merged["scope_value"], exclude=cur.entry_id):
            return ("duplicate", None)
        c = db.cursor()
        sets, vals = [], []
        for col in _ROW_FIELDS:
            if col in fields:
                sets.append(f"{col}=?")
                v = fields[col]
                vals.append(int(v) if col in _BOOL_FIELDS else v)
        sets += ["revision=?", "updated_at_utc=?"]
        vals += [new_revision, now, cur.entry_id, cur.revision]
        c.execute(f"UPDATE vocabulary_entries SET {', '.join(sets)}"
                  f" WHERE entry_id=? AND revision=?", vals)
        if c.rowcount != 1:
            return ("stale", None)
        if triples is not None:
            c.execute("DELETE FROM vocabulary_aliases WHERE entry_id=?",
                      (cur.entry_id,))
            for text, flag, lang in triples:
                c.execute(
                    "INSERT INTO vocabulary_aliases(entry_id, alias,"
                    " language, approved) VALUES(?,?,?,?)",
                    (cur.entry_id, text, lang, int(flag)))
        elif "language" in fields and fields["language"] != cur.language \
                and cur.language is not None \
                and not _inherit_migrated(c):
            # Alias language inheritance (M05-AUDIT-12) on a store the
            # one-time migration has not reached: a row equal to the
            # entry's PREVIOUS language was materialized by the old
            # store, so it follows the entry. After the migration NULL
            # alone means inherit and every value is an explicit
            # override, kept across language changes (review R4).
            c.execute("UPDATE vocabulary_aliases SET language=NULL"
                      " WHERE entry_id=? AND language=?",
                      (cur.entry_id, cur.language))
        change = {k: v for k, v in fields.items() if k != "aliases"}
        if triples is not None:
            change["aliases"] = [t for t, _, _ in triples]
        self._history(c, cur.entry_id, new_revision, "updated", change)
        self._bump(c)
        return ("ok", None)

    @staticmethod
    def _raise_for(status, detail=None):
        if status == "missing":
            raise KeyError("no such vocabulary entry")
        if status == "stale":
            raise StaleEntryError(
                "vocabulary entry changed since it was read"
                + (f" (now at revision {detail})" if detail else ""))
        if status == "duplicate":
            raise ValueError("an entry with this canonical spelling"
                             " already exists in the requested scope")
        if status == "duplicate_id":
            raise ValueError("an entry with this id already exists")
        if status == "invalid":
            raise ValueError(f"invalid vocabulary entry: {detail}")

    # ---- writes ----------------------------------------------------------

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
        for name, value in (("pinned", pinned), ("enabled", enabled),
                            ("approved", approved)):
            vocab.require_bool(name, value)
        vocab.require_int("priority", priority)
        vocab.require_opt_str("language", language)
        vocab.require_opt_str("scope_value", scope_value)
        vocab.require_opt_str("entry_id", entry_id)
        if verification is None:
            verification = ("explicit" if approved else "suggested")
        # Construct once for validation before touching the database.
        entry = vocab.VocabularyEntry(
            entry_id=entry_id or ids.new_id("vocab"), canonical=canonical,
            language=language, kind=kind, matching_mode=matching_mode,
            scope_kind=scope_kind, scope_value=scope_value,
            priority=priority, pinned=pinned, origin=origin,
            enabled=enabled, approved=approved, verification=verification,
            aliases=tuple(vocab.Alias(t, f, lang)
                          for t, f, lang in alias_records))
        # Duplicate probe BEFORE the writer keeps the common rejection
        # cheap; the in-op check below is the authoritative one (two
        # concurrent adds that both passed the probe resolve there, as
        # a status — never a raised write failure in the event log).
        scope_value = entry.scope_value      # canonical form (review Q5)
        if self._canonical_exists(canonical, scope_kind, scope_value):
            self._raise_for("duplicate")
        now = ids.now_utc_iso()

        def op(db):
            if _find_identity(db, canonical, scope_kind, scope_value):
                return "duplicate"
            if db.execute("SELECT 1 FROM vocabulary_entries WHERE"
                          " entry_id=?", (entry.entry_id,)).fetchone():
                return "duplicate_id"
            self._insert(db, entry, now)
            return "ok"
        self._raise_for(self.store.submit(op))
        return entry.entry_id

    def _validated_fields(self, changes: dict) -> dict:
        unknown = set(changes) - set(_EDITABLE)
        if unknown:
            raise ValueError(f"unknown entry fields: {sorted(unknown)}")
        fields = {}
        for k, v in changes.items():
            # language/scope_value are genuinely nullable; anything else
            # passed as None is a caller bug, not a silent no-op.
            if v is None and k not in ("language", "scope_value"):
                raise ValueError(f"field {k!r} may not be None")
            if k in _BOOL_FIELDS:
                vocab.require_bool(k, v)
            elif k == "priority":
                vocab.require_int(k, v)
            elif k in ("language", "scope_value"):
                vocab.require_opt_str(k, v)
            elif k in _STR_FIELDS:
                if not isinstance(v, str):
                    raise vocab.AdmissionError("not_a_string", k)
            elif k == "canonical":
                v = vocab._validate_canonical(v)
            elif k == "aliases":
                v = _normalize_alias_items(v)
            fields[k] = v
        return fields

    def update_entry(self, entry_id: str, *,
                     expected_revision: int | None = None,
                     **changes) -> vocab.VocabularyEntry:
        """Edit fields of one entry. The current row is read, merged,
        validated and versioned inside ONE writer operation; with
        ``expected_revision`` the edit is refused (StaleEntryError) when
        the row moved on since the caller read it."""
        fields = self._validated_fields(changes)
        if expected_revision is not None:
            vocab.require_int("expected_revision", expected_revision)
        now = ids.now_utc_iso()

        def op(db):
            cur = _read_entry(db, entry_id)
            if cur is None:
                return ("missing", None, None)
            if expected_revision is not None \
                    and cur.revision != expected_revision:
                return ("stale", cur.revision, None)
            if not fields:
                return ("ok", None, cur)  # nothing requested: no history
            status, detail = self._apply_update(db, cur, fields, now)
            return (status, detail, _read_entry(db, entry_id)
                    if status == "ok" else None)
        status, detail, out = self.store.submit(op)
        self._raise_for(status, detail)
        return out

    def set_enabled(self, entry_id: str, enabled: bool, *,
                    expected_revision: int | None = None):
        return self.update_entry(entry_id, enabled=enabled,
                                 expected_revision=expected_revision)

    def approve_entry(self, entry_id: str, *,
                      expected_revision: int | None = None):
        """Approve the entry and every alias (one-click approval, S11):
        from here the rule may rewrite text and its applications count
        as hits (AC04). The alias set approved is the one CURRENT inside
        the writer op — a concurrent alias edit is never lost and a
        stale alias list is never written back (M05-AUDIT-06)."""
        if expected_revision is not None:
            vocab.require_int("expected_revision", expected_revision)
        now = ids.now_utc_iso()

        def op(db):
            cur = _read_entry(db, entry_id)
            if cur is None:
                return ("missing", None, None)
            if expected_revision is not None \
                    and cur.revision != expected_revision:
                return ("stale", cur.revision, None)
            fields = {"approved": True, "verification": "explicit",
                      "aliases": [(a.alias, True, a.language)
                                  for a in cur.aliases]}
            status, detail = self._apply_update(db, cur, fields, now)
            return (status, detail, _read_entry(db, entry_id)
                    if status == "ok" else None)
        status, detail, out = self.store.submit(op)
        self._raise_for(status, detail)
        return out

    def set_scope(self, entry_id: str, scope_kind: str,
                  scope_value: str | None, *,
                  expected_revision: int | None = None):
        return self.update_entry(entry_id, scope_kind=scope_kind,
                                 scope_value=scope_value,
                                 expected_revision=expected_revision)

    def delete_entry(self, entry_id: str, *,
                     expected_revision: int | None = None):
        if expected_revision is not None:
            vocab.require_int("expected_revision", expected_revision)

        def op(db):
            row = db.execute(
                "SELECT revision, canonical FROM vocabulary_entries WHERE"
                " entry_id=?", (entry_id,)).fetchone()
            if row is None:
                return ("missing", None)
            if expected_revision is not None and row[0] != expected_revision:
                return ("stale", row[0])
            cur = db.cursor()
            cur.execute("DELETE FROM vocabulary_entries WHERE entry_id=?",
                        (entry_id,))
            cur.execute("DELETE FROM vocabulary_aliases WHERE entry_id=?",
                        (entry_id,))
            self._history(cur, entry_id, row[0] + 1, "deleted",
                          {"canonical": row[1]})
            self._bump(cur)
            return ("ok", None)
        self._raise_for(*self.store.submit(op))

    def record_hits(self, entry_ids: list[str]) -> int:
        """Record applied approved matches as usage (S11 ranking, task 5):
        usage feeds frequency/recency retrieval; suggestions never reach
        here because only approved aliases can produce edits. The caller
        contract is the ledger's applied rule ids — approval was checked
        at match time under the job's frozen revision, so an entry
        disabled after the job started still records its applied use
        (and an entry deleted meanwhile updates no row — harmless).
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
        does not reappear (a DELETED one is re-seeded: delete is not
        dismiss)."""
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
        return self.store.submit(lambda db: _find_identity(
            db, canonical, scope_kind, scope_value) is not None)

    # ---- JSON import/export (bulk, S11 dictionary UI) ---------------------

    def export_json(self) -> dict:
        return vocab.entries_to_doc(self.entries())

    def import_json(self, source, *, additive_only: bool = True) -> dict:
        """Bulk import (S11), one WHOLE-FILE transaction (M05-AUDIT-11,
        design D6). The file is parsed and validated completely first —
        strict types, alias words, and no two rows with one identity
        (the declared SQLite-NOCASE canonical+scope key) — and refused
        with a content-free ``ImportRejected`` before any write; then
        every upsert runs inside ONE writer operation, so a fault part
        way commits nothing. Upsert by (canonical, scope): the canonical
        spelling IS the key, so imports update settings (aliases,
        scope-independent fields) but never re-key an entry; new rows
        get freshly minted ids. Observed usage (count/last-use) stays
        with the store — a file never fabricates usage history.
        Idempotent: re-importing the same document, in any alias order,
        changes nothing (M05-AUDIT-10)."""
        try:
            doc = json.loads(pathlib.Path(source).read_text(
                encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            raise ImportRejected("unreadable_file") from None
        except json.JSONDecodeError:
            raise ImportRejected("not_json") from None
        if not isinstance(doc, dict) \
                or not isinstance(doc.get("entries", []), list):
            raise ImportRejected("invalid_document")
        parsed = []
        provided = []
        for i, d in enumerate(doc.get("entries", [])):
            try:
                parsed.append(vocab.VocabularyEntry.from_json(d))
                provided.append(frozenset(d))
            except vocab.AdmissionError as e:
                raise ImportRejected(e.code, f"entries[{i}].{e.field}") \
                    from None
            except (ValueError, TypeError, KeyError):
                raise ImportRejected("invalid_entry", f"entries[{i}]") \
                    from None
        seen: dict[tuple, int] = {}
        for i, e in enumerate(parsed):
            key = identity_key(e.canonical, e.scope_kind, e.scope_value)
            if key in seen:
                raise ImportRejected("duplicate_identity_in_file",
                                     f"entries[{seen[key]}],entries[{i}]")
            seen[key] = i
        now = ids.now_utc_iso()

        def op(db):
            created = updated = unchanged = 0
            for e, keys in zip(parsed, provided):
                cur_id = _find_identity(db, e.canonical, e.scope_kind,
                                        e.scope_value)
                if cur_id is None:
                    self._insert(db, dataclasses.replace(
                        e, entry_id=ids.new_id("vocab"), usage_count=0,
                        last_used_utc=None, revision=1), now)
                    created += 1
                    continue
                cur = _read_entry(db, cur_id)
                changes = {}
                # A field the row OMITS keeps the stored value (review
                # Q4): a partial file never de-approves, unpins or
                # re-kinds an existing entry through admission defaults.
                for col in ("language", "kind", "matching_mode", "priority",
                            "pinned", "origin", "enabled", "approved",
                            "verification"):
                    if col in keys and getattr(e, col) != getattr(cur, col):
                        changes[col] = getattr(e, col)
                if "aliases" in keys \
                        and _alias_identity(e) != _alias_identity(cur):
                    changes["aliases"] = [(a.alias, a.approved, a.language)
                                          for a in e.aliases]
                if not changes:
                    unchanged += 1
                    continue
                status, detail = self._apply_update(db, cur, changes, now)
                if status != "ok":
                    # Validated up front; anything else aborts the WHOLE
                    # transaction (raised inside the op → rolled back).
                    raise ImportRejected("conflicting_row")
                updated += 1
            return {"created": created, "updated": updated,
                    "unchanged": unchanged}
        try:
            return self.store.submit(op)
        except RuntimeError as e:
            raise ImportRejected("write_failed") from e
