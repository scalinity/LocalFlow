"""Persistent style rules over the single-writer store (V2 M10).

The M05 ``vocabulary_store`` pattern: versioned rows plus a monotonic
state counter in ``profiles_meta`` so the app's frozen rule snapshots
invalidate on edit. Rules are configuration content, never usage data —
no event or error channel ever carries a rule's name.

Every mutation is ONE writer operation that reads the writer-current
row, merges the requested changes onto it, validates the merged rule as
a whole (correlated fields such as scope kind and scope value are
checked together against the row actually being written), writes only
when exactly one row is affected, and bumps the counter only then
(M10-AUDIT-03/05). Outcomes are typed and content-free:

- ``NotFoundError`` (a ``KeyError``): the row is gone — no write, no bump.
- ``StaleRevisionError``: an ``expected_revision`` no longer matches.
- ``ValueError``/``AdmissionError``: the merged rule is invalid.
- ``OutcomeUnknownError`` (a ``TimeoutError``): the operation was
  admitted to the writer but the caller stopped waiting — it may still
  commit. The store's writer is FIFO, so any read submitted afterwards
  observes it; an ``add_rule`` repeated with the same ``rule_id`` is
  idempotent (M10-AUDIT-21).
"""

from __future__ import annotations

from typing import Optional

from . import ids
from . import profiles
from .store import Store
from .vocabulary import AdmissionError, require_bool, require_int

_RULE_COLS = (
    "rule_id", "name", "scope_kind", "scope_value", "mode",
    "number_policy", "profile_name", "enabled", "revision",
    "created_at_utc", "updated_at_utc",
)

_EDITABLE = ("name", "scope_kind", "scope_value", "mode",
             "number_policy", "profile_name", "enabled")

# The fields that make two rule rows the same configured rule (an
# idempotent re-add compares these).
_IDENTITY = ("name", "scope_kind", "scope_value", "mode", "number_policy",
             "profile_name", "enabled")


class NotFoundError(KeyError):
    """The target row does not exist at mutation time."""


class StaleRevisionError(ValueError):
    """The row's revision moved since the caller read it."""

    def __init__(self, entity_id: str, current_revision: Optional[int]):
        self.entity_id = entity_id
        self.current_revision = current_revision
        super().__init__("stale_revision")


class OutcomeUnknownError(TimeoutError):
    """An admitted mutation outlived the caller's wait: it may still
    commit (the store never cancels a queued operation)."""

    def __init__(self, action: str, entity_id: Optional[str]):
        self.action = action
        self.entity_id = entity_id
        super().__init__(f"outcome_unknown: {action}")


def _row_to_rule(row) -> profiles.StyleRule:
    d = dict(zip(_RULE_COLS, row))
    # A stored blank profile name has always meant "the category's
    # identity" (no declared name); it reads back as None.
    profile_name = d["profile_name"]
    if isinstance(profile_name, str) and not profile_name.strip():
        profile_name = None
    return profiles.StyleRule(
        rule_id=d["rule_id"], name=d["name"], scope_kind=d["scope_kind"],
        scope_value=d["scope_value"], mode=d["mode"],
        number_policy=d["number_policy"], profile_name=profile_name,
        enabled=bool(d["enabled"]), revision=d["revision"])


def _admit_changes(changes: dict) -> dict:
    """Primitive types of a patch, refused before admission — a
    Boolean-looking string never becomes a Boolean (M10-AUDIT-06)."""
    unknown = set(changes) - set(_EDITABLE)
    if unknown:
        raise ValueError(f"unknown rule fields: {sorted(unknown)}")
    for f, v in changes.items():
        if f == "enabled":
            require_bool(f, v)
        elif f in ("scope_value", "profile_name"):
            if v is not None and not isinstance(v, str):
                raise AdmissionError("not_a_string", f)
        elif not isinstance(v, str):
            raise AdmissionError("not_a_string", f)
    return dict(changes)


class StyleRuleStore:
    """Style-rule persistence (store schema v6, additive)."""

    def __init__(self, store: Store):
        self.store = store
        # Rows that fail validation when read back (none can be written
        # any more; an older database might hold one) carry no
        # authority and are counted, never raised through every read.
        self.invalid_rows = 0

    # ---- reads -----------------------------------------------------------

    def revision(self) -> int:
        def op(db):
            row = db.execute(
                "SELECT value FROM profiles_meta WHERE key='style_rules'"
            ).fetchone()
            return int(row[0]) if row else 0
        return self.store.submit(op) or 0

    def rules(self) -> list[profiles.StyleRule]:
        def op(db):
            rows = db.execute(
                f"SELECT {', '.join(_RULE_COLS)} FROM style_rules"
                f" ORDER BY name COLLATE NOCASE, rule_id"
            ).fetchall()
            out, bad = [], 0
            for r in rows:
                try:
                    out.append(_row_to_rule(r))
                except ValueError:
                    bad += 1
            return out, bad
        out, bad = self.store.submit(op)
        self.invalid_rows = bad
        return out

    def rule(self, rule_id: str) -> Optional[profiles.StyleRule]:
        def op(db):
            return db.execute(
                f"SELECT {', '.join(_RULE_COLS)} FROM style_rules"
                f" WHERE rule_id=?", (rule_id,)).fetchone()
        row = self.store.submit(op)
        return _row_to_rule(row) if row is not None else None

    # ---- writes ----------------------------------------------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO profiles_meta VALUES('style_rules','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def _run(self, op, action: str, entity_id: Optional[str]):
        try:
            return self.store.submit(op)
        except TimeoutError:
            # submit() queues the op BEFORE waiting: a timeout here is
            # always after admission — the outcome is unknown.
            raise OutcomeUnknownError(action, entity_id) from None

    def add_rule(self, *, name: str, scope_kind: str = "global",
                 scope_value: Optional[str] = None, mode: str = "clean",
                 number_policy: str = "inherit",
                 profile_name: Optional[str] = None,
                 enabled: bool = True,
                 rule_id: Optional[str] = None) -> str:
        """Create a rule. With a caller-chosen ``rule_id`` the add is
        idempotent: repeating it after an unknown outcome returns the
        same id when the identical rule already committed, and refuses
        (``id_in_use``) when a different rule holds the id."""
        if not isinstance(name, str):
            raise AdmissionError("not_a_string", "name")
        require_bool("enabled", enabled)
        rule = profiles.StyleRule(
            rule_id=rule_id or ids.new_id("style"), name=name.strip(),
            scope_kind=scope_kind, scope_value=scope_value, mode=mode,
            number_policy=number_policy, profile_name=profile_name,
            enabled=enabled, revision=1)
        now = ids.now_utc_iso()

        def op(db):
            row = db.execute(
                f"SELECT {', '.join(_RULE_COLS)} FROM style_rules"
                f" WHERE rule_id=?", (rule.rule_id,)).fetchone()
            if row is not None:
                cur = _row_to_rule(row)
                same = all(getattr(cur, f) == getattr(rule, f)
                           for f in _IDENTITY)
                return "already_applied" if same else "id_in_use"
            db.execute(
                f"INSERT INTO style_rules({', '.join(_RULE_COLS)})"
                f" VALUES({', '.join('?' * len(_RULE_COLS))})",
                (rule.rule_id, rule.name, rule.scope_kind, rule.scope_value,
                 rule.mode, rule.number_policy, rule.profile_name,
                 int(rule.enabled), 1, now, now))
            self._bump(db.cursor())
            return "created"
        outcome = self._run(op, "add", rule.rule_id)
        if outcome == "id_in_use":
            raise ValueError("id_in_use")
        return rule.rule_id

    def update_rule(self, rule_id: str, *,
                    expected_revision: Optional[int] = None,
                    **changes) -> profiles.StyleRule:
        """Apply ``changes`` to the writer-current row. Only the named
        fields are written; the merged rule is validated as a whole
        against the row actually being changed, so two individually
        valid patches can never combine into an invalid committed rule.
        ``expected_revision`` (optional) refuses a stale caller."""
        changes = _admit_changes(changes)
        if expected_revision is not None:
            require_int("expected_revision", expected_revision)
        now = ids.now_utc_iso()

        def op(db):
            row = db.execute(
                f"SELECT {', '.join(_RULE_COLS)} FROM style_rules"
                f" WHERE rule_id=?", (rule_id,)).fetchone()
            if row is None:
                return ("not_found", None)
            current = _row_to_rule(row)
            if expected_revision is not None \
                    and current.revision != expected_revision:
                return ("stale", current.revision)
            if not changes:
                return ("unchanged", current)
            merged = {f: getattr(current, f) for f in _EDITABLE}
            merged.update(changes)
            try:
                updated = profiles.StyleRule(
                    rule_id=rule_id, revision=current.revision + 1,
                    **merged)
            except ValueError as e:
                return ("invalid", e)
            cols = [c for c in _EDITABLE if c in changes]
            vals = [int(updated.enabled) if c == "enabled"
                    else getattr(updated, c) for c in cols]
            cur = db.execute(
                f"UPDATE style_rules SET "
                f"{', '.join(f'{c}=?' for c in cols)}, revision=?,"
                f" updated_at_utc=? WHERE rule_id=? AND revision=?",
                (*vals, updated.revision, now, rule_id, current.revision))
            if cur.rowcount != 1:
                return ("stale", None)
            self._bump(db.cursor())
            return ("updated", updated)
        outcome, value = self._run(op, "update", rule_id)
        if outcome == "not_found":
            raise NotFoundError(f"no style rule {rule_id}")
        if outcome == "stale":
            raise StaleRevisionError(rule_id, value)
        if outcome == "invalid":
            raise value
        return value

    def delete_rule(self, rule_id: str, *,
                    expected_revision: Optional[int] = None):
        if expected_revision is not None:
            require_int("expected_revision", expected_revision)

        def op(db):
            row = db.execute(
                "SELECT revision FROM style_rules WHERE rule_id=?",
                (rule_id,)).fetchone()
            if row is None:
                return ("not_found", None)
            if expected_revision is not None and row[0] != expected_revision:
                return ("stale", row[0])
            cur = db.execute("DELETE FROM style_rules WHERE rule_id=?",
                             (rule_id,))
            if cur.rowcount != 1:
                return ("not_found", None)
            self._bump(db.cursor())
            return ("deleted", None)
        outcome, value = self._run(op, "delete", rule_id)
        if outcome == "not_found":
            raise NotFoundError(f"no style rule {rule_id}")
        if outcome == "stale":
            raise StaleRevisionError(rule_id, value)

    def set_enabled(self, rule_id: str, enabled: bool, *,
                    expected_revision: Optional[int] = None):
        require_bool("enabled", enabled)
        return self.update_rule(rule_id, expected_revision=expected_revision,
                                enabled=enabled)
