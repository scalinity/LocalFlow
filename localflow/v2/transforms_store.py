"""Transform persistence over the single-writer store (V2 M11).

The M10 ``snippets_store`` pattern: versioned rows plus a monotonic
state counter in ``transform_meta`` so the coordinator's frozen
``TransformSnapshot`` invalidates on edit. Every mutation appends a
preserved revision to ``transform_revisions`` — an old transform
definition is never erased (S16/M11-AC01). The two uploaded V1
definitions materialize from the M02 legacy artifacts as
``origin="legacy"`` rows (prompt verbatim, legacy key recorded, never
bound as a shortcut).

Same-task preference evidence (S29.10): candidates record the exact
task manifest (hashes/ids only — source and output texts live in
lease-governed artifacts written inside the same writer op); explicit
accept/reject/tie/undo observations refuse to join two candidates
whose task keys differ (a retry with new instructions/source is a
different task, never a preference pair — M11-AC05).
"""

from __future__ import annotations

import json
import time
from typing import Optional

from . import ids
from . import transforms as tf
from .store import Store, grant_lease_row, insert_text_artifact_row

_COLS = ("transform_id", "name", "mode", "origin", "description",
         "prompt", "edit_types_json", "examples_json", "shortcut",
         "target_profiles_json", "auto_apply", "enabled", "revision",
         "usage_count", "source_locator", "legacy_key",
         "created_at_utc", "updated_at_utc")

_EDITABLE = ("name", "mode", "description", "prompt", "edit_types",
             "examples", "shortcut", "target_profiles",
             "auto_apply", "enabled")

# Friendly field → store column (JSON-valued fields serialize here).
_COL_FOR = {"edit_types": "edit_types_json",
            "examples": "examples_json",
            "target_profiles": "target_profiles_json"}

_JUDGMENTS = ("accept", "reject", "undo", "prefer_a", "prefer_b",
              "tie", "neither", "uncertain")


def _row_to_def(row) -> tf.TransformDefinition:
    d = dict(zip(_COLS, row))
    return tf.TransformDefinition(
        transform_id=d["transform_id"], name=d["name"],
        mode=d["mode"], origin=d["origin"],
        description=d["description"], prompt=d["prompt"],
        edit_types=tuple(json.loads(d["edit_types_json"] or "[]")),
        examples=tuple(tuple(ex) for ex in
                       json.loads(d["examples_json"] or "[]")),
        shortcut=d["shortcut"],
        target_profiles=tuple(json.loads(
            d["target_profiles_json"] or "[]")),
        auto_apply=bool(d["auto_apply"]), enabled=bool(d["enabled"]),
        revision=d["revision"], source_locator=d["source_locator"],
        legacy_key=d["legacy_key"])


class TransformStore:
    """Transform definition + preference persistence (schema v7)."""

    def __init__(self, store: Store):
        self.store = store

    # ---- reads -----------------------------------------------------------

    def revision(self) -> int:
        def op(db):
            row = db.execute(
                "SELECT value FROM transform_meta WHERE key='transforms'"
            ).fetchone()
            return int(row[0]) if row else 0
        return self.store.submit(op) or 0

    def definitions(self) -> list[tf.TransformDefinition]:
        def op(db):
            rows = db.execute(
                f"SELECT {', '.join(_COLS)} FROM transforms"
                f" ORDER BY origin, name COLLATE NOCASE, transform_id"
            ).fetchall()
            return [_row_to_def(r) for r in rows]
        return self.store.submit(op)

    def definition(self, transform_id: str) -> Optional[tf.TransformDefinition]:
        for d in self.definitions():
            if d.transform_id == transform_id:
                return d
        return None

    def revisions_of(self, transform_id: str) -> list[dict]:
        """Every preserved revision (append-only history, AC01)."""
        def op(db):
            rows = db.execute(
                "SELECT revision, definition_json, created_at_utc FROM"
                " transform_revisions WHERE transform_id=?"
                " ORDER BY revision", (transform_id,)).fetchall()
            return [{"revision": r, "definition": json.loads(js),
                     "created_at_utc": t} for r, js, t in rows]
        return self.store.submit(op)

    # ---- writes ----------------------------------------------------------

    def _bump(self, db) -> None:
        db.execute(
            "INSERT INTO transform_meta VALUES('transforms','1')"
            " ON CONFLICT(key) DO UPDATE SET"
            " value=CAST(value AS INTEGER)+1")

    def _append_revision(self, db, defn: tf.TransformDefinition, now):
        db.execute(
            "INSERT OR IGNORE INTO transform_revisions(transform_id,"
            " revision, definition_json, created_at_utc)"
            " VALUES(?,?,?,?)",
            (defn.transform_id, defn.revision,
             json.dumps(defn.to_json(), ensure_ascii=False,
                        sort_keys=True), now))

    def _insert(self, db, defn: tf.TransformDefinition, now):
        db.execute(
            f"INSERT INTO transforms({', '.join(_COLS)})"
            f" VALUES({', '.join('?' * len(_COLS))})",
            (defn.transform_id, defn.name, defn.mode, defn.origin,
             defn.description, defn.prompt,
             json.dumps(list(defn.permitted_edits())),
             json.dumps([list(ex) for ex in defn.examples]),
             defn.shortcut, json.dumps(list(defn.target_profiles)),
             int(defn.auto_apply), int(defn.enabled), defn.revision, 0,
             defn.source_locator, defn.legacy_key, now, now))
        self._append_revision(db, defn, now)

    def seed_built_ins(self) -> dict:
        """Idempotent: the strengthened built-in contracts exist as
        rows (their preserved revisions start at 1 and are never
        rewritten by seeding)."""
        have = {d.transform_id for d in self.definitions()}
        missing = [d for d in tf.built_ins()
                   if d.transform_id not in have]
        if not missing:
            return {"seeded": 0}
        now = ids.now_utc_iso()

        def op(db):
            for d in missing:
                self._insert(db, d, now)
            self._bump(db)
        self.store.submit(op)
        return {"seeded": len(missing)}

    def add_transform(self, *, name: str, mode: str, description: str = "",
                      prompt: str = "", examples=(), shortcut=None,
                      target_profiles=(), auto_apply: bool = False,
                      enabled: bool = True,
                      transform_id: Optional[str] = None,
                      origin: str = "user",
                      source_locator: Optional[str] = None,
                      legacy_key: Optional[str] = None
                      ) -> tf.TransformDefinition:
        defn = tf.TransformDefinition(
            transform_id=transform_id or ids.new_id("tf"),
            name=name, mode=mode, origin=origin,
            description=description, prompt=prompt,
            examples=tuple(tuple(ex) for ex in examples),
            shortcut=shortcut,
            target_profiles=tuple(target_profiles),
            auto_apply=auto_apply, enabled=enabled, revision=1,
            source_locator=source_locator, legacy_key=legacy_key)
        self._check_shortcut(defn.shortcut)
        now = ids.now_utc_iso()

        def op(db):
            self._insert(db, defn, now)
            self._bump(db)
        self.store.submit(op)
        return defn

    def update_transform(self, transform_id: str, **changes
                         ) -> tf.TransformDefinition:
        current = self.definition(transform_id)
        if current is None:
            raise KeyError(f"no transform {transform_id}")
        if current.origin == "legacy":
            # A preserved legacy revision is frozen: its definition is
            # the migrated V1 bytes. Users who want to iterate create a
            # custom transform (the legacy row stays available, AC01).
            raise ValueError(
                "legacy transform definitions are preserved revisions"
                " and cannot be edited")
        if current.origin == "builtin" and "mode" in changes \
                and changes["mode"] != current.mode:
            # A built-in IS its mode (the mode executors bind by
            # id+mode) — an edit can never silently rebind it.
            raise ValueError(
                "a built-in transform's mode is fixed")
        unknown = set(changes) - set(_EDITABLE)
        if unknown:
            raise ValueError(f"unknown transform fields: {sorted(unknown)}")
        if not changes:
            return current
        merged = {
            "name": current.name, "mode": current.mode,
            "description": current.description, "prompt": current.prompt,
            "edit_types": current.permitted_edits(),
            "examples": current.examples, "shortcut": current.shortcut,
            "target_profiles": current.target_profiles,
            "auto_apply": current.auto_apply, "enabled": current.enabled,
        }
        for k, v in changes.items():
            if k.endswith("_json"):
                raise ValueError("internal column names are not editable")
            merged[k] = v
        if all(merged[k] == current.__dict__[k]
               for k in _EDITABLE):
            # A no-op update appends nothing — the append-only history
            # records real changes only.
            return current
        self._check_shortcut(merged["shortcut"], exclude=transform_id)
        now = ids.now_utc_iso()
        sets, vals = [], []
        for field in _EDITABLE:
            if field not in changes:
                continue
            col = _COL_FOR.get(field, field)
            v = changes[field]
            if col.endswith("_json"):
                v = json.dumps([list(ex) for ex in v]
                               if field == "examples" else list(v))
            elif field in ("auto_apply", "enabled"):
                v = int(bool(v))
            sets.append(f"{col}=?")
            vals.append(v)
        sets += ["revision=revision+1", "updated_at_utc=?"]
        vals += [now, transform_id]

        def op(db):
            # The next revision is read INSIDE the writer op — two
            # interleaved updates can never append the same revision
            # number to the preserved history.
            row = db.execute(
                "SELECT revision FROM transforms WHERE transform_id=?",
                (transform_id,)).fetchone()
            if row is None:
                raise KeyError(f"no transform {transform_id}")
            updated = tf.TransformDefinition(
                transform_id=current.transform_id,
                name=merged["name"], mode=merged["mode"],
                origin=current.origin,
                description=merged["description"],
                prompt=merged["prompt"],
                edit_types=tuple(merged["edit_types"]),
                examples=tuple(tuple(ex) for ex in merged["examples"]),
                shortcut=merged["shortcut"],
                target_profiles=tuple(merged["target_profiles"]),
                auto_apply=bool(merged["auto_apply"]),
                enabled=bool(merged["enabled"]),
                revision=int(row[0]) + 1,
                source_locator=current.source_locator,
                legacy_key=current.legacy_key)
            db.execute(
                f"UPDATE transforms SET {', '.join(sets)}"
                f" WHERE transform_id=?", vals)
            self._append_revision(db, updated, now)
            self._bump(db)
        self.store.submit(op)
        out = self.definition(transform_id)
        assert out is not None
        return out

    def delete_transform(self, transform_id: str):
        """Disable-and-forget, never erase: the row's preserved
        revisions stay (old transform definitions are never erased,
        S16); deletion marks the definition disabled."""
        self.update_transform(transform_id, enabled=False)

    def set_enabled(self, transform_id: str, enabled: bool):
        return self.update_transform(transform_id, enabled=enabled)

    def record_hits(self, transform_ids) -> int:
        """Applied transforms as usage statistics (never matching
        state — the vocabulary/snippets discipline)."""
        now = ids.now_utc_iso()
        uniq = sorted(set(transform_ids))
        if not uniq:
            return 0

        def op(db):
            cur = db.cursor()
            n = 0
            for tid in uniq:
                cur.execute(
                    "UPDATE transforms SET usage_count=usage_count+1,"
                    " updated_at_utc=? WHERE transform_id=?", (now, tid))
                n += cur.rowcount
            return n
        return self.store.submit(op)

    def _check_shortcut(self, shortcut: Optional[str],
                        exclude: Optional[str] = None):
        if shortcut is None:
            return
        conflicts = tf.shortcut_conflicts([
            d for d in self.definitions()
            if d.transform_id != exclude] + [
            tf.TransformDefinition(
                transform_id="pending", name="pending", mode="custom",
                shortcut=shortcut)])
        if conflicts:
            raise ValueError(
                f"shortcut {shortcut!r} collides with another transform")

    # ---- legacy migration (M11-AC01) --------------------------------------

    def materialize_legacy(self) -> dict:
        """The two uploaded V1 definitions (already imported by the M02
        path as ``legacy_transform_definition`` artifacts) become
        preserved legacy rows — prompt verbatim, revision frozen at 1,
        the legacy key recorded and never bound. Idempotent per
        source revision; re-imported edited definitions materialize as
        their own rows (append-only, nothing overwritten)."""
        def read(db):
            return db.execute(
                "SELECT i.source_locator, i.source_sha256,"
                " a.content_text FROM imports i"
                " JOIN artifacts a ON a.artifact_id = i.imported_id"
                " WHERE i.source_kind='transforms_json'").fetchall()
        rows = self.store.submit(read) or []
        materialized = skipped = 0
        for locator, sha, content in rows:
            transform_id = f"legacy:{locator}:{sha[:8]}"
            if self.definition(transform_id) is not None:
                skipped += 1
                continue
            try:
                obj = json.loads(content)
                defn = tf.from_legacy_json(obj, locator)
            except (json.JSONDecodeError, TypeError, ValueError):
                # One malformed legacy row never disables the transform
                # service — skip it, count it, keep materializing.
                skipped += 1
                continue
            defn = tf.TransformDefinition(
                transform_id=transform_id, name=defn.name,
                mode="custom", origin="legacy",
                description=defn.description, prompt=defn.prompt,
                edit_types=defn.edit_types, examples=defn.examples,
                shortcut=None, target_profiles=(),
                auto_apply=False, enabled=True, revision=1,
                source_locator=locator, legacy_key=defn.legacy_key)
            now = ids.now_utc_iso()

            def op(db, d=defn, n=now):
                self._insert(db, d, n)
                self._bump(db)
            self.store.submit(op)
            materialized += 1
        return {"rows": len(rows), "materialized": materialized,
                "skipped": skipped}

    # ---- same-task preference evidence (S29.10) ---------------------------

    def record_candidate(self, result: tf.TransformResult, *,
                         task_kind: str = "transform_selection",
                         source_artifact_text: Optional[str] = None,
                         output_artifact_text: Optional[str] = None,
                         model_id: Optional[str] = None,
                         display_order: int = 0,
                         parent_artifact_id: Optional[str] = None,
                         lease_days: Optional[int] = None
                         ) -> Optional[str]:
        """Record one candidate with its exact task inputs. Source and
        output texts are lease-governed artifacts written inside the
        SAME writer op as the row (the M09 annotation pattern)."""
        manifest = result.job.task_manifest()
        candidate_id = ids.new_id("tcand")
        src_art = out_art = None
        now_epoch = time.time()
        now = ids.now_utc_iso(now_epoch)
        days = lease_days if lease_days is not None \
            else self.store.retention_days["training_buffer"]

        def op(db):
            nonlocal src_art, out_art
            if source_artifact_text is not None:
                src_art = insert_text_artifact_row(
                    db, artifact_id=ids.new_id("art"),
                    job_id=result.job.parent_job_id, stage="transform",
                    role="transform_source", text=source_artifact_text,
                    kind="text", retention_class="training",
                    meta={"task_key": manifest["task_key"],
                          "source_kind": manifest["source_kind"]},
                    parent_artifact_id=parent_artifact_id,
                    created_at_utc=now)
                grant_lease_row(db, src_art, "training", days=days,
                                granted_at_epoch=now_epoch)
            if output_artifact_text is not None:
                out_art = insert_text_artifact_row(
                    db, artifact_id=ids.new_id("art"),
                    job_id=result.job.parent_job_id, stage="transform",
                    role="transform_output", text=output_artifact_text,
                    kind="text", retention_class="training",
                    meta={"task_key": manifest["task_key"],
                          "path": result.path},
                    parent_artifact_id=parent_artifact_id,
                    created_at_utc=now)
                grant_lease_row(db, out_art, "training", days=days,
                                granted_at_epoch=now_epoch)
            db.execute(
                "INSERT INTO transform_candidates(candidate_id, task_key,"
                " task_kind, transform_id, transform_revision,"
                " prompt_revision, source_sha256, instructions_sha256,"
                " examples_revision, source_artifact_id,"
                " output_artifact_id, path, display_order, model_id,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, manifest["task_key"], task_kind,
                 manifest["transform_id"], manifest["transform_revision"],
                 manifest["prompt_revision"], manifest["source_sha256"],
                 manifest["instructions_sha256"],
                 manifest["examples_revision"], src_art, out_art,
                 result.path, display_order, model_id, now))
            return candidate_id
        return self.store.submit(op)

    def record_observation(self, *, task_key: str, candidate_id: str,
                           judgment: str,
                           candidate_b_id: Optional[str] = None,
                           provenance: str = "user_action",
                           reason_code: Optional[str] = None,
                           source_event_id: Optional[str] = None
                           ) -> str:
        """One explicit preference observation (accept/reject/tie/undo/
        prefer). The same-task invariant is enforced at write time:
        both candidates must carry exactly this task key — a judgment
        across different tasks refuses (M11-AC05)."""
        if judgment not in _JUDGMENTS:
            raise ValueError(f"unknown judgment: {judgment}")

        def op(db):
            keys = [r[0] for r in db.execute(
                "SELECT task_key FROM transform_candidates WHERE"
                " candidate_id IN (?, ?)", (candidate_id,
                                            candidate_b_id)).fetchall()]
            if task_key not in keys or len(keys) != (
                    2 if candidate_b_id else 1) \
                    or any(k != task_key for k in keys):
                raise ValueError(
                    "preference observation refused: candidates do not"
                    " share the task key (a different source or"
                    " instruction set is a different task, S29.10)")
            observation_id = ids.new_id("pref")
            db.execute(
                "INSERT INTO preference_observations(observation_id,"
                " task_key, candidate_id, candidate_b_id, judgment,"
                " provenance, reason_code, source_event_id,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (observation_id, task_key, candidate_id, candidate_b_id,
                 judgment, provenance, reason_code, source_event_id,
                 ids.now_utc_iso()))
            return observation_id
        return self.store.submit(op)

    def candidates_for_task(self, task_key: str) -> list[dict]:
        def op(db):
            rows = db.execute(
                "SELECT candidate_id, transform_id, transform_revision,"
                " prompt_revision, path, display_order, model_id,"
                " created_at_utc FROM transform_candidates"
                " WHERE task_key=? ORDER BY created_at_utc",
                (task_key,)).fetchall()
            return [dict(zip(
                ("candidate_id", "transform_id", "transform_revision",
                 "prompt_revision", "path", "display_order", "model_id",
                 "created_at_utc"), r)) for r in rows]
        return self.store.submit(op) or []

    def observations_for_task(self, task_key: str) -> list[dict]:
        def op(db):
            rows = db.execute(
                "SELECT observation_id, candidate_id, candidate_b_id,"
                " judgment, provenance, reason_code, source_event_id,"
                " created_at_utc FROM preference_observations"
                " WHERE task_key=? ORDER BY created_at_utc",
                (task_key,)).fetchall()
            return [dict(zip(
                ("observation_id", "candidate_id", "candidate_b_id",
                 "judgment", "provenance", "reason_code",
                 "source_event_id", "created_at_utc"), r))
                for r in rows]
        return self.store.submit(op) or []
