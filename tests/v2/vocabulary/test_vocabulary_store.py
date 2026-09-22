"""EV-03/EV-07 store half / M05: dictionary persistence over the
single-writer store.

Covers M05-AC01 (the seven legacy terms are adopted verbatim and
import/reopen preserves spelling and settings; JSON round trips and
re-imports are idempotent), AC03 (edits version entries with history;
snapshots are immutable and a job's captured state survives later
edits), hit recording (approved/enabled only) and the visible Claude
suggestions.

Run: .venv/bin/python tests/v2/vocabulary/test_vocabulary_store.py
"""

import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import vocabulary as V  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

LEGACY_TERMS = ["Qwen", "MLX", "Parakeet", "LocalFlow", "Wispr Flow",
                "PyObjC", "MacBook"]


def new_store(td):
    return store_mod.Store(pathlib.Path(td) / "v2.db")


def test_schema_v3_tables_exist():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        con = sqlite3.connect(st.db_path)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"vocabulary_entries", "vocabulary_aliases",
                "vocabulary_history", "vocabulary_meta"} <= tables
        assert st._schema_version() == 3
        st.close()
    print("ok  schema v3: vocabulary tables live in the single store")


def test_legacy_terms_adopted_and_reopen_preserves():
    """M05-AC01: the seven terms adopt as approved global entries;
    closing and reopening the store preserves spelling and settings."""
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        vs = VocabularyStore(st)
        result = vs.seed_legacy_terms(LEGACY_TERMS)
        assert result == {"imported": 7, "skipped": 0}
        # Idempotent: re-seed adopts nothing new.
        assert vs.seed_legacy_terms(LEGACY_TERMS) == \
            {"imported": 0, "skipped": 7}
        st.close()

        st2 = store_mod.Store(db)
        vs2 = VocabularyStore(st2)
        entries = {e.canonical: e for e in vs2.entries()}
        assert set(entries) == set(LEGACY_TERMS), sorted(entries)
        for e in entries.values():
            assert e.approved and e.enabled and e.scope_kind == "global"
            assert e.origin == "legacy_import"
            assert e.verification == "explicit"
        st2.close()
    print("ok  AC01: 7 legacy terms adopted; reopen preserves spelling"
          " and settings; re-seed idempotent")


def test_seed_from_legacy_artifacts():
    """The live adoption path reads the M02-imported legacy artifacts."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        for term in LEGACY_TERMS[:3]:
            st.import_legacy_text(
                text=term, role="legacy_dictionary_term",
                kind="legacy_dictionary_term", retention_class="legacy",
                meta=None, source_kind="dictionary",
                source_sha="a" * 64, locator=f"term:{term}",
                time_quality="unknown")
        vs = VocabularyStore(st)
        assert vs.seed_from_legacy_artifacts() == \
            {"imported": 3, "skipped": 0}
        assert vs.seed_from_legacy_artifacts() == \
            {"imported": 0, "skipped": 3}
        assert {e.canonical for e in vs.entries()} == set(
            LEGACY_TERMS[:3])
        st.close()
    print("ok  legacy artifact seeding adopts the imported terms")


def test_suggested_coding_terms_visible_not_applied():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        assert vs.seed_suggested_coding_terms() == \
            {"added": 2, "skipped": 0}
        assert vs.seed_suggested_coding_terms() == \
            {"added": 0, "skipped": 2}
        snap = vs.snapshot(V.ScopeContext(profile="coding"))
        assert not snap.match_index, "unapproved suggestions never match"
        listed = {e.canonical for e in vs.entries()}
        assert {"Claude", "Claude Code"} <= listed
        # A dismissed (disabled) suggestion does not reappear on re-seed.
        cc = next(e for e in vs.entries()
                  if e.canonical == "Claude Code")
        vs.set_enabled(cc.entry_id, False)
        assert vs.seed_suggested_coding_terms() == \
            {"added": 0, "skipped": 2}
        assert vs.entry(cc.entry_id).enabled is False
        st.close()
    print("ok  Claude/Claude Code suggested visibly, never applied;"
          " dismissed suggestions stay dismissed")


def test_versioned_updates_with_history():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Servo", ["survo"], approved=True)
        rev0 = vs.revision()
        entry0 = vs.entry(eid)
        assert entry0.revision == 1
        updated = vs.update_entry(eid, pinned=True, priority=5)
        assert updated.revision == 2 and updated.pinned
        assert vs.revision() > rev0
        hist = vs.history(eid)
        assert [h["action"] for h in hist] == ["created", "updated"]
        assert hist[1]["change"] == {"pinned": True, "priority": 5}
        # Unknown fields and bad values are rejected loudly.
        try:
            vs.update_entry(eid, bogus=1)
            raise AssertionError("unknown field accepted")
        except ValueError:
            pass
        try:
            vs.update_entry(eid, scope_kind="workspace")  # needs value
            raise AssertionError("scopeless workspace accepted")
        except ValueError:
            pass
        st.close()
    print("ok  edits version entries with append-only history;"
          " invalid edits rejected")


def test_snapshot_immutability_and_ac03():
    """M05-AC03: rule editing changes only future jobs — a snapshot (and
    the policy/context built from it) is immutable; a mid-flight edit
    bumps the store counter and the revision for the NEXT snapshot."""
    from localflow.v2.normalize import (ContextSnapshot,
                                        NormalizationPolicy, normalize)
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Claude Code", ["clod code"],
                           scope_kind="workspace", scope_value="projx",
                           approved=True)
        snap1 = vs.snapshot(V.ScopeContext(workspace="projx"))
        pol1 = NormalizationPolicy(
            registered_skills=dict(snap1.skills))
        ctx1 = ContextSnapshot(vocabulary=snap1)
        out1 = normalize("use clod code now", pol1, ctx1).text
        assert out1 == "use Claude Code now"
        # Edit mid-flight: the in-flight job's captured objects are
        # unchanged and replay identically.
        vs.set_enabled(eid, False)
        assert normalize("use clod code now", pol1, ctx1).text == out1
        assert vs.revision() >= 2
        snap2 = vs.snapshot(V.ScopeContext(workspace="projx"))
        assert snap2.revision != snap1.revision
        pol2 = NormalizationPolicy(registered_skills=dict(snap2.skills))
        out2 = normalize("use clod code now", pol2,
                         ContextSnapshot(vocabulary=snap2)).text
        assert out2 == "use clod code now"
        st.close()
    print("ok  AC03: in-flight revision retained; edits affect only"
          " future jobs")


def test_approve_entry_all_aliases():
    """Review DB1-C1 regression: approve_entry passes (alias, approved)
    tuples into update_entry — the path that crashed before the fix.
    Approval must land for the entry AND every alias (S11 one-click)."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Claude Code", ["clod code"],
                           scope_kind="profile", scope_value="coding",
                           approved=False)
        vs.approve_entry(eid)
        e = vs.entry(eid)
        assert e.approved and e.verification == "explicit"
        assert e.aliases and all(a.approved for a in e.aliases)
        # And the approved entry now matches in its scope.
        snap = vs.snapshot(V.ScopeContext(profile="coding"))
        assert "clod code" in snap.match_index
        st.close()
    print("ok  approve_entry lands for entry + all aliases (DB1-C1"
          " regression)")


def test_record_hits():
    """Hits update usage for the applied rule ids the ledger hands over
    (duplicates in one batch collapse to one use). Usage is statistics,
    not matching state: a hit must NOT bump the store revision or the
    snapshot revision — otherwise every applied match would force a
    snapshot rebuild on the next dictation (review CA1-W2)."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        a = vs.add_entry("MLX", [], approved=True)
        b = vs.add_entry("Qwen", [], approved=True)
        assert vs.record_hits([a, b, a]) == 2
        assert vs.entry(a).usage_count == 1
        assert vs.entry(b).usage_count == 1
        assert vs.entry(a).last_used_utc
        assert vs.record_hits([]) == 0
        # Usage never invalidates the cached snapshot state.
        rev_before = vs.revision()
        snap_before = vs.snapshot(None).revision
        assert vs.record_hits([a]) == 1
        assert vs.revision() == rev_before
        assert vs.snapshot(None).revision == snap_before
        st.close()
    print("ok  hits record applied usage (batch-deduped); usage never"
          " invalidates the snapshot revision")


def test_json_import_export_round_trip():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Claude Code", ["clod code"],
                           scope_kind="workspace", scope_value="projx",
                           approved=True, pinned=True)
        vs.record_hits([eid] * 3)
        doc = vs.export_json()
        path = pathlib.Path(td) / "dict.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        # Re-import into a fresh store: spellings/settings preserved,
        # usage stays with the original store (a file never fabricates
        # usage), and re-import is idempotent.
        st2 = new_store(td + "-2")
        vs2 = VocabularyStore(st2)
        r1 = vs2.import_json(path)
        assert r1 == {"created": 1, "updated": 0, "unchanged": 0}
        e = next(e for e in vs2.entries()
                 if e.canonical == "Claude Code")
        assert e.scope_kind == "workspace" and e.scope_value == "projx"
        assert e.pinned and e.approved
        assert e.usage_count == 0, "usage is observed data, not file data"
        r2 = vs2.import_json(path)
        assert r2 == {"created": 0, "updated": 0, "unchanged": 1}
        # An edited field updates in place.
        doc["entries"][0]["pinned"] = False
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert vs2.import_json(path)["updated"] == 1
        assert vs2.entry(e.entry_id).pinned is False
        st.close()
        st2.close()
    print("ok  JSON import/export round trip preserves settings;"
          " idempotent; usage never fabricated")


def test_duplicate_canonical_in_scope_rejected():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        vs.add_entry("Servo", ["survo"], approved=True)
        try:
            # The caller-thread probe raises a plain ValueError whose
            # message carries no dictionary content (event hygiene).
            vs.add_entry("Servo", ["survo again"],
                         scope_kind="global", approved=True)
            raise AssertionError("duplicate accepted")
        except ValueError as e:
            assert "already exists" in str(e)
            assert "Servo" not in str(e)
        try:
            # Case variants are the same spelling per the NOCASE index.
            vs.add_entry("servo", ["survo three"], approved=True)
            raise AssertionError("case-variant duplicate accepted")
        except ValueError as e:
            assert "already exists" in str(e)
        # Same canonical in a DIFFERENT scope is a distinct entry.
        assert vs.add_entry("Servo", [], scope_kind="workspace",
                            scope_value="web", approved=True)
        st.close()
    print("ok  duplicate canonical per scope rejected (case-"
          "insensitively); cross-scope coexists")


def test_aliases_only_update_versions_entry():
    """Review corroborated warning (DB1-W2/CA1-W1): an aliases-only
    change must version the entry row — the history's revision sequence
    and the row's must never diverge. An empty update is a no-op that
    appends nothing."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Servo", ["survo"], approved=True)
        assert vs.entry(eid).revision == 1
        updated = vs.update_entry(eid, aliases=["survo", "surve"])
        assert updated.revision == 2
        assert sorted(a.alias for a in updated.aliases) == \
            ["surve", "survo"]
        assert [h["revision"] for h in vs.history(eid)] == [1, 2]
        # A later column update continues the sequence cleanly.
        again = vs.update_entry(eid, pinned=True)
        assert again.revision == 3
        assert [h["revision"] for h in vs.history(eid)] == [1, 2, 3]
        # Empty update: no new history, no revision bump.
        same = vs.update_entry(eid)
        assert same.revision == 3
        assert len(vs.history(eid)) == 3
        # Invalid None for a non-nullable field is rejected loudly.
        try:
            vs.update_entry(eid, canonical=None)
            raise AssertionError("None canonical accepted")
        except ValueError:
            pass
        st.close()
    print("ok  aliases-only updates version the entry; empty/invalid"
          " updates are honest no-ops/rejections")


def test_language_and_aliases_combined_update():
    """Review DB1-W4: rewritten alias rows must carry the UPDATED
    language, not the pre-update one."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Servo", ["survo"], language="en",
                           approved=True)
        vs.update_entry(eid, language="es", aliases=["survo", "surve"])
        e = vs.entry(eid)
        assert e.language == "es"
        assert all(a.language == "es" for a in e.aliases), \
            [a.language for a in e.aliases]
        st.close()
    print("ok  alias rows follow an updated language")


def test_delete_entry_and_set_scope():
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        eid = vs.add_entry("Servo", ["survo"],
                           scope_kind="workspace", scope_value="web",
                           approved=True)
        snap = vs.snapshot(V.ScopeContext(workspace="web"))
        assert "survo" in snap.match_index
        # Rescoping out of the active context removes the match and
        # surfaces the cross-scope relationship.
        vs.set_scope(eid, "workspace", "mobile")
        snap2 = vs.snapshot(V.ScopeContext(workspace="web"))
        assert "survo" not in snap2.match_index
        assert vs.snapshot(V.ScopeContext(workspace="mobile")) \
            .match_index.get("survo")
        # Delete removes row + aliases, keeps the audit trail, frees
        # the canonical for reuse.
        vs.delete_entry(eid)
        assert vs.entry(eid) is None
        assert [h["action"] for h in vs.history(eid)] == \
            ["created", "updated", "deleted"]
        assert vs.add_entry("Servo", ["survo"], approved=True)
        st.close()
    print("ok  set_scope moves matching; delete clears rows, keeps"
          " history, frees the canonical")


def test_import_json_updates_aliases():
    """Review DB1-C1 second trace: an import whose alias list differs
    from the stored entry must update it (previously crashed)."""
    with tempfile.TemporaryDirectory() as td:
        st = new_store(td)
        vs = VocabularyStore(st)
        vs.add_entry("Claude Code", ["clod code"],
                     scope_kind="workspace", scope_value="projx",
                     approved=True)
        doc = {"entries": [{
            "entry_id": "any", "canonical": "Claude Code",
            "scope": ["workspace", "projx"],
            "aliases": [{"alias": "clod code", "approved": True},
                        {"alias": "cloud code", "approved": True}],
            "approved": True}]}
        path = pathlib.Path(td) / "d.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        r = vs.import_json(path)
        assert r == {"created": 0, "updated": 1, "unchanged": 0}, r
        e = next(x for x in vs.entries() if x.canonical == "Claude Code")
        assert sorted(a.alias for a in e.aliases) == ["clod code",
                                                     "cloud code"]
        st.close()
    print("ok  import updates differing aliases (DB1-C1 second trace)")


def test_store_repair_recreates_vocabulary_tables():
    """Review DB1-S2/CA1-S5: a torn external write that drops a
    vocabulary table is repaired by the idempotent-DDL path."""
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        st.close()
        con = sqlite3.connect(db)
        con.execute("DROP TABLE vocabulary_entries")
        con.execute("DROP TABLE vocabulary_aliases")
        con.commit()
        con.close()
        st2 = store_mod.Store(db)
        con = sqlite3.connect(db)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"vocabulary_entries", "vocabulary_aliases"} <= tables
        VocabularyStore(st2).add_entry("Qwen", approved=True)
        st2.close()
    print("ok  torn-write repair recreates the v3 vocabulary tables")


def test_snapshot_immutability_real_check():
    """Replaces the vacuous revision==revision assert (review CA1-W5):
    snapshot state is frozen — mutating the entries it was built from
    cannot change the built snapshot's index or revision."""
    entries = [V.VocabularyEntry(entry_id="im-1", canonical="Servo",
                                 aliases=(V.Alias("survo"),),
                                 approved=True)]
    snap = V.VocabularySnapshot(entries)
    rev, idx = snap.revision, dict(snap.match_index)
    entries.append(V.VocabularyEntry(entry_id="im-2", canonical="Qwen",
                                     approved=True))
    entries[0] = V.VocabularyEntry(entry_id="im-1", canonical="Changed",
                                   approved=True)
    assert snap.revision == rev and dict(snap.match_index) == idx
    assert V.VocabularySnapshot(entries).revision != rev
    print("ok  snapshots frozen against post-construction mutation")


if __name__ == "__main__":
    test_schema_v3_tables_exist()
    test_legacy_terms_adopted_and_reopen_preserves()
    test_seed_from_legacy_artifacts()
    test_suggested_coding_terms_visible_not_applied()
    test_versioned_updates_with_history()
    test_snapshot_immutability_and_ac03()
    test_record_hits()
    test_approve_entry_all_aliases()
    test_aliases_only_update_versions_entry()
    test_language_and_aliases_combined_update()
    test_delete_entry_and_set_scope()
    test_import_json_updates_aliases()
    test_json_import_export_round_trip()
    test_duplicate_canonical_in_scope_rejected()
    test_store_repair_recreates_vocabulary_tables()
    test_snapshot_immutability_real_check()
    print("all vocabulary store tests passed")
