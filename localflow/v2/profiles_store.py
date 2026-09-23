"""Persistent style rules over the single-writer store (V2 M10).

The M05 ``vocabulary_store`` pattern: versioned rows plus a monotonic
state counter in ``profiles_meta`` so the app's frozen rule snapshots
invalidate on edit; every mutation is one writer transaction that bumps
the counter. Rules are configuration content, never usage data — no
event or error channel ever carries a rule's name.
"""

from __future__ import annotations

from typing import Optional

from . import ids
from . import profiles
from .store import Store

_RULE_COLS = (
    "rule_id", "name", "scope_kind", "scope_value", "mode",
    "number_policy", "profile_name", "enabled", "revision",
    "created_at_utc", "updated_at_utc",
)

_EDITABLE = ("name", "scope_kind", "scope_value", "mode",
             "number_policy", "profile_name", "enabled")


def _row_to_rule(row) -> profiles.StyleRule:
    d = dict(zip(_RULE_COLS, row))
    return profiles.StyleRule(
        rule_id=d["rule_id"], name=d["name"], scope_kind=d["scope_kind"],
        scope_value=d["scope_value"], mode=d["mode"],
        number_policy=d["number_policy"], profile_name=d["profile_name"],
        enabled=bool(d["enabled"]), revision=d["revision"])


class StyleRuleStore:
    """Style-rule persistence (store schema v6, additive)."""

    def __init__(self, store: Store):
        self.store = store

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
            return [_row_to_rule(r) for r in rows]
        return self.store.submit(op)

    def rule(self, rule_id: str) -> Optional[profiles.StyleRule]:
        for r in self.rules():
            if r.rule_id == rule_id:
                return r
        return None

    # ---- writes ----------------------------------------------------------

    def _bump(self, cur) -> None:
        cur.execute(
            "INSERT INTO profiles_meta VALUES('style_rules','1')"
            " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def add_rule(self, *, name: str, scope_kind: str = "global",
                 scope_value: Optional[str] = None, mode: str = "clean",
                 number_policy: str = "inherit",
                 profile_name: Optional[str] = None,
                 enabled: bool = True,
                 rule_id: Optional[str] = None) -> str:
        rule = profiles.StyleRule(
            rule_id=rule_id or ids.new_id("style"), name=name.strip(),
            scope_kind=scope_kind, scope_value=scope_value, mode=mode,
            number_policy=number_policy, profile_name=profile_name,
            enabled=enabled, revision=1)
        now = ids.now_utc_iso()

        def op(db):
            db.execute(
                f"INSERT INTO style_rules({', '.join(_RULE_COLS)})"
                f" VALUES({', '.join('?' * len(_RULE_COLS))})",
                (rule.rule_id, rule.name, rule.scope_kind, rule.scope_value,
                 rule.mode, rule.number_policy, rule.profile_name,
                 int(rule.enabled), 1, now, now))
            self._bump(db.cursor())
        self.store.submit(op)
        return rule.rule_id

    def update_rule(self, rule_id: str, **changes) -> profiles.StyleRule:
        unknown = set(changes) - set(_EDITABLE)
        if unknown:
            raise ValueError(f"unknown rule fields: {sorted(unknown)}")
        current = self.rule(rule_id)
        if current is None:
            raise KeyError(f"no style rule {rule_id}")
        if not changes:
            return current
        merged = {
            "name": current.name, "scope_kind": current.scope_kind,
            "scope_value": current.scope_value, "mode": current.mode,
            "number_policy": current.number_policy,
            "profile_name": current.profile_name,
            "enabled": current.enabled,
        }
        merged.update(changes)
        # Construct for validation (scope rules, mode vocabulary…).
        profiles.StyleRule(rule_id=rule_id, revision=current.revision + 1,
                           **merged)
        now = ids.now_utc_iso()
        sets, vals = [], []
        for col in _EDITABLE:
            if col in changes:
                sets.append(f"{col}=?")
                v = changes[col]
                if col == "enabled":
                    v = int(bool(v))
                vals.append(v)
        sets.append("revision=revision+1")
        sets.append("updated_at_utc=?")
        vals.extend([now, rule_id])

        def op(db):
            db.execute(
                f"UPDATE style_rules SET {', '.join(sets)} WHERE rule_id=?",
                vals)
            self._bump(db.cursor())
        self.store.submit(op)
        out = self.rule(rule_id)
        assert out is not None
        return out

    def delete_rule(self, rule_id: str):
        if self.rule(rule_id) is None:
            raise KeyError(f"no style rule {rule_id}")

        def op(db):
            db.execute("DELETE FROM style_rules WHERE rule_id=?",
                       (rule_id,))
            self._bump(db.cursor())
        self.store.submit(op)

    def set_enabled(self, rule_id: str, enabled: bool):
        return self.update_rule(rule_id, enabled=enabled)
