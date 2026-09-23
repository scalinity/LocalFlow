"""EV-13 / M11: transform definitions, the store and legacy migration.

The versioned definition surface (Spec S16, contracts/transforms.md):
built-in contracts seed idempotently; every edit appends a preserved
revision (an old definition is never erased — M11-AC01); the two
uploaded V1 definitions materialize as legacy revisions with their
prompt verbatim and their key recorded but never bound; shortcuts
detect collisions; auto-apply is opt-in per definition (AC04).

Run: .venv/bin/python tests/v2/transforms/test_transform_definitions.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import transforms as tf  # noqa: E402
from localflow.v2 import transforms_store as tstore  # noqa: E402


class Env:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.store = store_mod.Store(self.tmp / "v2.db",
                                     artifacts_dir=self.tmp / "arts",
                                     backup_dir=self.tmp / "bk")
        self.ts = tstore.TransformStore(self.store)
        return self

    def __exit__(self, *exc):
        self.store.close()
        self._tmp.cleanup()


def test_built_ins_seed_idempotently():
    with Env() as e:
        first = e.ts.seed_built_ins()
        assert first["seeded"] == 3, first
        again = e.ts.seed_built_ins()
        assert again["seeded"] == 0, again
        ids = [d.transform_id for d in e.ts.definitions()]
        assert ids == ["builtin:concise", "builtin:polish",
                       "builtin:prompt_engineer"], ids
        d = e.ts.definition("builtin:prompt_engineer")
        assert d.mode == "prompt_engineer" and d.revision == 1
        assert d.auto_apply is False  # opt-in default (AC04)
        assert d.prompt_revision.startswith("m11:")
        print("ok  built-ins seed once; auto-apply defaults off")


def test_versions_append_and_never_erase():
    with Env() as e:
        e.ts.seed_built_ins()
        e.ts.update_transform("builtin:polish", auto_apply=True)
        d = e.ts.definition("builtin:polish")
        assert d.revision == 2 and d.auto_apply is True
        revs = e.ts.revisions_of("builtin:polish")
        assert [r["revision"] for r in revs] == [1, 2], revs
        # The preserved revision 1 still carries the pre-edit state.
        assert revs[0]["definition"]["auto_apply"] is False
        # Another edit appends; revision 2 is never rewritten.
        e.ts.update_transform("builtin:polish", auto_apply=False)
        revs = e.ts.revisions_of("builtin:polish")
        assert [r["revision"] for r in revs] == [1, 2, 3]
        # Delete = disable-and-forget, the rows stay.
        tid = e.ts.add_transform(name="My rewrite", mode="custom",
                                 prompt="Make it friendlier").transform_id
        e.ts.delete_transform(tid)
        assert e.ts.definition(tid).enabled is False
        assert e.ts.revisions_of(tid)
        print("ok  edits append preserved revisions; nothing erased")


def test_legacy_definitions_materialize_preserved():
    with Env() as e:
        # The M02 legacy import path: two definitions in transforms.json
        # shape land as legacy_transform_definition artifacts.
        legacy = [{"key": "1", "name": "Polish",
                   "description": "Improve clarity and conciseness",
                   "prompt": "Rewrite the text to improve clarity."},
                  {"key": "2", "name": "Prompt Engineer",
                   "description": "Constructs optimal prompts",
                   "prompt": "Rewrite the text as a well-structured pr…"}]
        data = json.dumps(legacy).encode("utf-8")
        sha = store_mod.sha256_bytes(data) if hasattr(
            store_mod, "sha256_bytes") else None
        from localflow.v2 import ids as v2_ids
        sha = v2_ids.sha256_bytes(data)
        for d in legacy:
            e.store.import_legacy_text(
                text=json.dumps(d, ensure_ascii=False, indent=1),
                role="legacy_transform_definition",
                kind="legacy_transform_definition",
                retention_class="legacy", meta=None,
                source_kind="transforms_json", source_sha=sha,
                locator=f"transform:{d.get('key')}",
                time_quality="unknown")
        out = e.ts.materialize_legacy()
        assert out["materialized"] == 2 and out["skipped"] == 0, out
        # Idempotent: nothing re-materializes.
        again = e.ts.materialize_legacy()
        assert again["materialized"] == 0 and again["skipped"] == 2, again
        rows = [d for d in e.ts.definitions() if d.origin == "legacy"]
        assert len(rows) == 2
        for d in rows:
            assert d.mode == "custom" and d.prompt in (
                "Rewrite the text to improve clarity.",
                "Rewrite the text as a well-structured pr…")
            assert d.auto_apply is False and d.shortcut is None
            assert d.legacy_key in ("1", "2")  # recorded, never bound
            # A preserved legacy revision refuses edits (AC01).
            try:
                e.ts.update_transform(d.transform_id, name="x")
                raise AssertionError("legacy edit accepted")
            except ValueError:
                pass
        print("ok  legacy definitions preserved verbatim, never bound,"
              " never editable")


def test_shortcut_collision_detection():
    with Env() as e:
        e.ts.seed_built_ins()
        e.ts.update_transform("builtin:polish", shortcut="p")
        try:
            e.ts.add_transform(name="Other", mode="custom",
                               prompt="x", shortcut="P")
            raise AssertionError("colliding shortcut accepted")
        except ValueError:
            pass
        # Distinct keys are fine; conflicts surface through the pure
        # helper too (the Hub shows them without blocking the write
        # path's raise).
        conflicts = tf.shortcut_conflicts([
            tf.TransformDefinition(transform_id="a", name="A",
                                   mode="custom", shortcut="k"),
            tf.TransformDefinition(transform_id="b", name="B",
                                   mode="custom", shortcut="K"),
            tf.TransformDefinition(transform_id="c", name="C",
                                   mode="custom", shortcut="z")])
        assert conflicts == [{"shortcut": "K",
                              "transform_ids": ["a", "b"]}], conflicts
        print("ok  shortcut collisions detected (case-insensitive)")


def test_auto_apply_decision_matrix():
    with Env() as e:
        e.ts.seed_built_ins()
        snap = tf.TransformSnapshot(e.ts.definitions())
        # Off by default (opt-in, AC04).
        d, reason = snap.auto_apply_decision("polish", "default", None)
        assert reason == "transform_auto_apply_disabled:polish", reason
        # Opt-in with no target list applies everywhere.
        e.ts.update_transform("builtin:polish", auto_apply=True)
        snap = tf.TransformSnapshot(e.ts.definitions())
        d, reason = snap.auto_apply_decision("polish", "email", "email")
        assert reason is None and d.transform_id == "builtin:polish"
        # A target list that excludes the resolved profile declines.
        e.ts.update_transform("builtin:polish",
                              target_profiles=("coding",))
        snap = tf.TransformSnapshot(e.ts.definitions())
        d, reason = snap.auto_apply_decision("polish", "email", "email")
        assert reason == "transform_profile_not_targeted:email", reason
        d, reason = snap.auto_apply_decision("polish", "coding",
                                             "coding")
        assert reason is None
        # Disabled definitions never run; custom needs a unique bind.
        e.ts.update_transform("builtin:polish", enabled=False)
        snap = tf.TransformSnapshot(e.ts.definitions())
        d, reason = snap.auto_apply_decision("polish", "coding",
                                             "coding")
        assert reason == "transform_not_bound:polish", reason
        print("ok  auto-apply decision matrix (opt-in/targets/binding)")


def test_definitions_revision_and_validation():
    rev1 = tf.definitions_revision(tf.built_ins())
    rev2 = tf.definitions_revision(tf.built_ins())
    assert rev1 == rev2 and rev1.startswith("m11:")
    edited = [tf.TransformDefinition(
        transform_id="builtin:polish", name="Polish", mode="polish",
        auto_apply=True)]
    assert tf.definitions_revision(edited) != rev1
    for bad in (dict(transform_id="x", name="", mode="polish"),
                dict(transform_id="x", name="X", mode="shout"),
                dict(transform_id="x", name="X", mode="custom",
                     shortcut="ab"),
                dict(transform_id="x", name="X", mode="custom",
                     examples=[("only-one",)])):
        try:
            tf.TransformDefinition(**bad)
            raise AssertionError(f"bad definition accepted: {bad}")
        except ValueError:
            pass
    print("ok  definitions revision + validation")


def test_for_mode_binds_only_matching_builtin_mode():
    """Review W4: a built-in whose row mode was changed (only possible
    programmatically — the store refuses it) unbinds honestly; the
    store itself refuses the rebind attempt."""
    with Env() as e:
        e.ts.seed_built_ins()
        try:
            e.ts.update_transform("builtin:polish", mode="custom")
            raise AssertionError("builtin mode change accepted")
        except ValueError:
            pass
        # The direct-construction path (a snapshot over a mutated row)
        # still refuses to bind a mismatched built-in.
        mutated = [tf.TransformDefinition(
            transform_id="builtin:polish", name="Polish",
            mode="custom", auto_apply=True)]
        snap = tf.TransformSnapshot(mutated)
        d, reason = snap.auto_apply_decision("polish", None, None)
        assert d is None and reason == "transform_not_bound:polish"
        # A no-op update appends nothing (history records changes).
        before = e.ts.revisions_of("builtin:polish")
        e.ts.update_transform("builtin:polish", auto_apply=False)
        after = e.ts.revisions_of("builtin:polish")
        assert before == after, "no-op update appended a revision"
    print("ok  built-in mode binding is id-AND-mode; no-op updates"
          " append nothing")


def test_materialize_legacy_skips_malformed_rows():
    """One malformed legacy row never disables the service."""
    with Env() as e:
        from localflow.v2 import ids as v2_ids
        bad = [{"key": "9", "name": "   ", "prompt": "x"}]
        data = json.dumps(bad).encode("utf-8")
        sha = v2_ids.sha256_bytes(data)
        e.store.import_legacy_text(
            text=json.dumps(bad[0]), role="legacy_transform_definition",
            kind="legacy_transform_definition", retention_class="legacy",
            meta=None, source_kind="transforms_json", source_sha=sha,
            locator="transform:9", time_quality="unknown")
        out = e.ts.materialize_legacy()
        assert out["materialized"] == 0 and out["skipped"] == 1, out
    print("ok  malformed legacy row skipped, service intact")


if __name__ == "__main__":
    test_built_ins_seed_idempotently()
    test_versions_append_and_never_erase()
    test_legacy_definitions_materialize_preserved()
    test_shortcut_collision_detection()
    test_auto_apply_decision_matrix()
    test_definitions_revision_and_validation()
    test_for_mode_binds_only_matching_builtin_mode()
    test_materialize_legacy_skips_malformed_rows()
    print("all transform definition tests passed")
