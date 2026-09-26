"""M05 remediation regressions (domain, store, evidence, capability).

One test group per confirmed audit finding. Every oracle is authored
independently of the code under test (exact strings, exact rule ids,
explicit row/history/revision expectations) and each group was run
against the audited base 267d1c2 first, where it FAILS; see
docs/v2/acceptance/M05/remediation/. Critical findings pair the unsafe
negative with a matched intended-use positive. Concurrency uses the
explicit turnstile of m05_helpers (both meaningful orders), never
sleeps. App-level seams live in test_m05_remediation_app.py.

Run: .venv/bin/python tests/v2/vocabulary/test_m05_remediation.py
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m05_helpers import (  # noqa: E402
    ROOT,
    TempStore,
    V,
    VS,
    ContextSnapshot,
    NormalizationPolicy,
    ent,
    normalize,
    race,
    run,
    vocab_edits,
)

CANARY = ("Claude", "clod", "AUDIT_CANARY")


def raises(fn, *types):
    try:
        fn()
    except types or Exception as e:  # noqa: B030
        return e
    raise AssertionError(f"expected {types or 'an exception'}")


# ---------------------------------------------------------------------------
# 01 — an alias owns word cores only, never a clause delimiter
# ---------------------------------------------------------------------------

SEPARATED = ["clod, code", "clod. code", "clod: code", "clod; code",
             "clod! code", "clod? code", "clod\ncode", "clod\rcode",
             "clod\r\ncode", "clod\x0bcode", "clod\x0ccode", "clod\x1ccode",
             "clod\x1dcode", "clod\x1ecode", "clod\x85code",
             "clod code", "clod code", "we met clod, code later"]


def test_01_alias_never_spans_a_delimiter():
    ents = [ent("E-CC", "Claude Code", ["clod code"])]
    for text in SEPARATED:
        res = run(text, ents)
        assert res.text == text and not vocab_edits(res), \
            (repr(text), res.text, vocab_edits(res))
    positives = {
        "clod code": "Claude Code",
        "clod code,": "Claude Code,",
        "use clod code today": "use Claude Code today",
        "use clod code.": "use Claude Code.",
        "clod code; then stop": "Claude Code; then stop",
        "clod code": "Claude Code",
        "clod\tcode": "Claude Code",
        "clod  code": "Claude Code",
    }
    for text, want in positives.items():
        res = run(text, ents)
        assert res.text == want, (repr(text), res.text)
        edits = [e for e in res.edits if e.cls == "vocabulary"]
        assert [(e.rule_id, e.output_text) for e in edits] == \
            [("E-CC", "Claude Code")], edits
        start = text.index("clod")
        end = text.index("code") + len("code")
        assert tuple(edits[0].input_span.as_pair()) == (start, end), \
            "the edit covers the word cores only"
    # Matched pair: the shorter approved rule still owns its own clause.
    both = [ent("E-CL", "Claude", ["clod"]),
            ent("E-CC", "Claude Code", ["clod code"])]
    res = run("clod, code", both)
    assert res.text == "Claude, code" and vocab_edits(res) == \
        [("clod", "Claude", "E-CL")], (res.text, vocab_edits(res))
    assert run("clod code", both).text == "Claude Code"
    print("ok  01 multiword alias: every delimiter blocks the phrase;"
          " edge punctuation/space/NBSP/tab positives still apply")


# ---------------------------------------------------------------------------
# 03 — canonical claims are order independent (idempotence)
# ---------------------------------------------------------------------------

def test_03_left_overlap_canonical_claim():
    ents = [ent("E-A", "Status Page"), ent("E-B", "Orange", ["red status"])]
    p1 = run("red status page", ents)
    assert p1.text == "red Status Page", p1.text
    assert vocab_edits(p1) == [("status page", "Status Page", "E-A")]
    p2 = run(p1.text, ents)
    assert p2.text == p1.text and not vocab_edits(p2), \
        (p2.text, vocab_edits(p2))
    # Intended positives of the competing rule.
    assert run("red status", ents).text == "Orange"
    assert run("the red status light", ents).text == "the Orange light"
    # Right overlap (the claim starts first) stays stable too.
    ents_r = [ent("E-A", "Status Page"), ent("E-C", "PageView",
                                              ["page view"])]
    q1 = run("status page view", ents_r)
    assert q1.text == "Status Page view", q1.text
    q2 = run(q1.text, ents_r)
    assert q2.text == q1.text and not vocab_edits(q2)
    assert run("open page view", ents_r).text == "open PageView"
    # A longer alias still beats a shorter canonical claim it contains
    # (same winner on the lowercase input and on the canonical text).
    ents_l = [ent("E-S", "Status"), ent("E-SP", "StatusPage",
                                        ["status page"])]
    assert run("status page", ents_l).text == "StatusPage"
    assert run("Status page", ents_l).text == "StatusPage"
    # Idempotence battery.
    battery = [ent("E-A", "Status Page"), ent("E-B", "Orange",
                                              ["red status"]),
               ent("E-C", "PageView", ["page view"]),
               ent("E-CL", "Claude", ["clod"]),
               ent("E-CC", "Claude Code", ["clod code"])]
    for text in ("red status page view", "clod code red status page",
                 "red status, page view", "status page view red status",
                 "Red Status Page", "clod, code and clod code"):
        a = run(text, battery)
        b = run(a.text, battery)
        assert b.text == a.text and not vocab_edits(b), \
            (text, a.text, b.text)
    print("ok  03 canonical claims arbitrate like proposals: left/right"
          " overlaps idempotent, competing positives intact")


# ---------------------------------------------------------------------------
# 04 — the snapshot is deeply immutable
# ---------------------------------------------------------------------------

def _snapshot_with_everything(caller_aliases):
    e = V.VocabularyEntry(entry_id="E-CL", canonical="Claude",
                          aliases=caller_aliases, approved=True,
                          verification="explicit")
    return V.VocabularySnapshot([
        e, ent("E-X1", "Cloud", ["klaud"]), ent("E-X2", "Clown", ["klaud"]),
        ent("E-SK", "code-review", ["code review"], kind="skill")])


def test_04_snapshot_deeply_immutable():
    caller = [V.Alias("clod")]
    snap = _snapshot_with_everything(caller)
    assert isinstance(snap.entries[0].aliases, tuple)
    rev = snap.revision
    ser = json.dumps(snap.to_json(), sort_keys=True)
    phrase = "ask clod and klod and klaud"
    before = run(phrase, (), snapshot=snap).text
    attempts = {
        "scope_ctx": lambda: setattr(snap, "scope_ctx",
                                     V.ScopeContext(workspace="x")),
        "match_index": lambda: setattr(snap, "match_index", {}),
        "entries": lambda: setattr(snap, "entries", ()),
        "revision": lambda: setattr(snap, "revision", "m05:x"),
        "skills": lambda: setattr(snap, "skills", {}),
        "conflicts": lambda: setattr(snap, "conflicts", ()),
        "index_item": lambda: snap.match_index.__setitem__("x", None),
        "skills_item": lambda: snap.skills.__setitem__("x", "y"),
        "conflict_item": lambda: snap.conflicts[0].__setitem__("alias",
                                                               "z"),
        "conflict_entries": lambda: snap.conflicts[0]["entries"].append(
            "z"),
        "entry_field": lambda: setattr(snap.entries[0], "canonical", "X"),
        "delete_attr": lambda: delattr(snap, "revision"),
    }
    accepted = []
    for name, fn in attempts.items():
        try:
            fn()
            accepted.append(name)
        except (AttributeError, TypeError,
                dataclasses.FrozenInstanceError):
            pass
    assert not accepted, f"accepted mutations: {accepted}"
    # A detached serialization never reaches the frozen object.
    doc = snap.to_json()
    doc["skills"]["zzz"] = "x"
    doc["conflicts"][0]["alias"] = "zzz"
    # Caller-owned alias list mutated after capture.
    caller.append(V.Alias("klod"))
    rescoped = V.VocabularySnapshot(snap.entries,
                                    V.ScopeContext(workspace="x"))
    assert snap.revision == rev
    assert json.dumps(snap.to_json(), sort_keys=True) == ser
    assert run(phrase, (), snapshot=snap).text == before == \
        run(phrase, (), snapshot=rescoped).text == \
        "ask Claude and klod and klaud", before
    assert dict(snap.skills) == {"code review": "code-review",
                                 "code-review": "code-review"}
    # Outer entry list mutation (inherited check) still isolated.
    outer = [ent("E-A", "Alpha", ["alfa"])]
    s2 = V.VocabularySnapshot(outer)
    outer.append(ent("E-B", "Beta", ["beeta"]))
    assert run("beeta", (), snapshot=s2).text == "beeta"
    print("ok  04 snapshot: attributes, indexes, conflicts, entries and"
          " caller alias lists cannot change a captured job")


# ---------------------------------------------------------------------------
# 05 — HintSet identity is bound to frozen content
# ---------------------------------------------------------------------------

def test_05_hintset_identity_bound_to_content():
    ents = [ent("E-A", "Alpha"), ent("E-B", "Beta"), ent("E-C", "Gamma")]
    snap = V.VocabularySnapshot(ents, V.ScopeContext(workspace="w"))
    sel = V.RelevantVocabularySelector(2)
    hs = sel.select(snap, now_utc="2026-09-25T00:00:00Z")
    hid, b0 = hs.hint_set_id, json.dumps(hs.to_json(), sort_keys=True)
    assert hs.omitted, "the case needs an omission"
    for fn in (lambda: hs.scope.__setitem__("workspace", "y"),
               lambda: hs.omitted[0].__setitem__("reason", "x"),
               lambda: setattr(hs.terms[0], "score", (9,)),
               lambda: setattr(hs, "terms", ())):
        raises(fn, TypeError, AttributeError,
               dataclasses.FrozenInstanceError)
    j = hs.to_json()
    j["scope"]["workspace"] = "z"
    j["terms"][0]["canonical"] = "z"
    j["omitted"][0]["reason"] = "z"
    assert json.dumps(hs.to_json(), sort_keys=True) == b0
    assert hs.hint_set_id == hid
    # created_utc stays OUT of identity (deterministic reconstruction).
    assert sel.select(snap, now_utc="2030-01-01T00:00:00Z").hint_set_id \
        == hid
    # Direct construction owns its inputs and cannot mislabel content.
    scope = {"app_bundle": None, "site_origin": None, "workspace": "w",
             "profile": None}
    terms = list(hs.terms)
    omitted = [dict(o) for o in hs.omitted]
    hs2 = V.HintSet(hint_set_id=hid, selector_revision=hs.selector_revision,
                    vocabulary_revision=hs.vocabulary_revision, scope=scope,
                    terms=terms, omitted=omitted, created_utc="t",
                    term_limit=2)
    c0 = json.dumps(hs2.to_json(), sort_keys=True)
    scope["workspace"] = "evil"
    terms.clear()
    omitted[0]["reason"] = "evil"
    assert json.dumps(hs2.to_json(), sort_keys=True) == c0
    raises(lambda: V.HintSet(
        hint_set_id=hid, selector_revision=hs.selector_revision,
        vocabulary_revision=hs.vocabulary_revision, scope=dict(scope,
                                                              workspace="x"),
        terms=list(hs.terms), omitted=[dict(o) for o in hs.omitted],
        created_utc="t", term_limit=2), ValueError)
    # Every identity-bearing difference yields a distinct id.
    variants = {
        "budget": V.RelevantVocabularySelector(3).select(snap),
        "scope": sel.select(V.VocabularySnapshot(
            ents, V.ScopeContext(workspace="v"))),
        "vocabulary": sel.select(V.VocabularySnapshot(
            ents[:2] + [ent("E-C", "Gamma", priority=5)],
            V.ScopeContext(workspace="w"))),
        "order": sel.select(V.VocabularySnapshot(
            [ent("E-A", "Alpha", pinned=True)] + ents[1:],
            V.ScopeContext(workspace="w"))),
    }
    ids = {hid} | {v.hint_set_id for v in variants.values()}
    assert len(ids) == 5, {k: v.hint_set_id for k, v in variants.items()}
    print("ok  05 HintSet: nested scope/omissions/terms frozen, detached"
          " JSON, direct construction owns inputs and is id-checked")


# ---------------------------------------------------------------------------
# 06 — read-modify-write inside the writer transaction
# ---------------------------------------------------------------------------

def _revs(t, eid="E-CL"):
    return t.sql("SELECT revision, action FROM vocabulary_history WHERE"
                 " entry_id=? ORDER BY history_id", (eid,))


def _add_cl(t, approved=True, aliases=("clod",)):
    return t.vs.add_entry("Claude", list(aliases), approved=approved,
                          entry_id="E-CL")


def test_06_concurrent_scope_update_never_commits_invalid_state():
    for order in (["A", "B", "A", "B"], ["B", "A", "B", "A"]):
        with TempStore() as t:
            _add_cl(t)
            res, ts = race(t.store, order, {
                "A": lambda: t.vs.update_entry(
                    "E-CL", scope_kind="workspace", scope_value="X"),
                "B": lambda: t.vs.update_entry("E-CL", scope_value=None)})
            assert ts.timeouts == 0
            kind, value, rev = t.sql(
                "SELECT scope_kind, scope_value, revision FROM"
                " vocabulary_entries")[0]
            assert not (kind != "global" and value is None), \
                (order, kind, value)
            revs = [r for r, _ in _revs(t)]
            assert revs == sorted(set(revs)) and revs[-1] == rev, revs
            t.vs.snapshot(None)          # never poisoned
            for name, r in res.items():
                assert r[0] == "ok" or r[1] in ("ValueError",
                                                "StaleEntryError"), res
    print("ok  06 concurrent scope edits: no workspace/None row, no"
          " duplicate revision, snapshots always build (both orders)")


def test_06_independent_edits_version_monotonically():
    with TempStore() as t:
        _add_cl(t)
        res, ts = race(t.store, ["A", "B", "A", "B"], {
            "A": lambda: t.vs.update_entry("E-CL", priority=5).revision,
            "B": lambda: t.vs.update_entry("E-CL", pinned=True).revision})
        assert sorted(r[1] for r in res.values()) == [2, 3], res
        assert _revs(t) == [(1, "created"), (2, "updated"),
                            (3, "updated")], _revs(t)
        e = t.vs.entry("E-CL")
        assert (e.priority, e.pinned, e.revision) == (5, True, 3)
    print("ok  06 two edits from one read commit revisions 2 and 3 with"
          " both changes")


def test_06_update_delete_race():
    for order in (["U", "D", "D", "U"], ["D", "D", "U", "U"],
                  ["U", "U", "D", "D"]):
        with TempStore() as t:
            _add_cl(t)
            res, ts = race(t.store, order, {
                "U": lambda: t.vs.update_entry(
                    "E-CL", aliases=["clod", "klod"]).revision,
                "D": lambda: t.vs.delete_entry("E-CL")})
            assert not t.sql("SELECT 1 FROM vocabulary_aliases"), order
            assert not t.sql("SELECT 1 FROM vocabulary_entries"), order
            acts = [a for _, a in _revs(t)]
            assert acts[-1] == "deleted" and acts.count("deleted") == 1, \
                (order, acts)
            revs = [r for r, _ in _revs(t)]
            assert revs == sorted(set(revs)), revs
            assert res["U"][0] == "ok" or res["U"][1] == "KeyError", res
    print("ok  06 update/delete race: no orphan alias or history after"
          " delete; the loser sees an explicit missing outcome")


def test_06_approve_uses_authoritative_alias_set():
    for order in (["P", "L", "L", "L", "P", "P"],
                  ["L", "L", "L", "P", "P", "P"]):
        with TempStore() as t:
            t.vs.add_entry("Claude", [("clod", False)], approved=False,
                           entry_id="E-CL")
            res, _ts = race(t.store, order, {
                "P": lambda: t.vs.approve_entry("E-CL").revision,
                "L": lambda: t.vs.update_entry(
                    "E-CL", aliases=[("clod", False),
                                     ("klod", False)]).revision})
            aliases = dict(t.sql("SELECT alias, approved FROM"
                                 " vocabulary_aliases"))
            assert "klod" in aliases, (order, aliases)
            revs = [r for r, _ in _revs(t)]
            assert revs == sorted(set(revs)), revs
            if order[0] == "L":
                assert aliases == {"clod": 1, "klod": 1}, aliases
    print("ok  06 approve reads the current alias set inside the writer"
          " (no lost alias, no stale whole-list approval)")


def test_06_compare_and_swap():
    with TempStore() as t:
        _add_cl(t)
        t.vs.update_entry("E-CL", priority=1)            # → revision 2
        e = raises(lambda: t.vs.update_entry("E-CL", expected_revision=1,
                                             priority=9),
                   VS.StaleEntryError)
        assert not any(c in str(e) for c in CANARY), str(e)
        assert t.vs.entry("E-CL").priority == 1
        assert t.vs.update_entry("E-CL", expected_revision=2,
                                 priority=9).revision == 3
        raises(lambda: t.vs.approve_entry("E-CL", expected_revision=2),
               VS.StaleEntryError)
        raises(lambda: t.vs.delete_entry("E-CL", expected_revision=1),
               VS.StaleEntryError)
        assert t.vs.entry("E-CL") is not None
        raises(lambda: t.vs.update_entry("nope", priority=1), KeyError)
        raises(lambda: t.vs.delete_entry("nope"), KeyError)
        # Expected outcomes never surface as store write failures.
        assert not [e for e in t.events
                    if e["event"] == "store.write_failed"], t.events
    print("ok  06 expected_revision compare-and-swap for update/approve/"
          "delete; missing/stale are typed caller errors")


# ---------------------------------------------------------------------------
# 07 — strict primitive admission
# ---------------------------------------------------------------------------

BAD = ["false", "true", 0, 1, None, [], {}]


def _doc(**over):
    e = {"entry_id": "x", "canonical": "Claude", "scope": ["global", None],
         "approved": True, "enabled": True, "pinned": False,
         "verification": "explicit",
         "aliases": [{"alias": "clod", "approved": True}]}
    alias_over = over.pop("alias_approved", "__absent__")
    e.update(over)
    if alias_over != "__absent__":
        e["aliases"][0]["approved"] = alias_over
    return {"entries": [e]}


def _import(t, doc, name="i.json"):
    p = t.dir / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return t.vs.import_json(p)


def test_07_import_rejects_malformed_booleans_before_any_write():
    for field in ("approved", "enabled", "pinned", "alias_approved"):
        for bad in BAD:
            with TempStore() as t:
                rev0 = t.vs.revision()
                e = raises(lambda: _import(t, _doc(**{field: bad})),
                           ValueError, TypeError)
                assert not any(c in str(e) for c in CANARY), str(e)
                assert not t.vs.entries() and t.vs.revision() == rev0
                assert not t.sql("SELECT 1 FROM vocabulary_history")
    # Positive/negative controls with real JSON booleans.
    with TempStore() as t:
        _import(t, _doc(approved=False))
        assert run("ask clod", (), snapshot=t.vs.snapshot()).text == \
            "ask clod"
    with TempStore() as t:
        _import(t, _doc())
        assert run("ask clod", (), snapshot=t.vs.snapshot()).text == \
            "ask Claude"
    with TempStore() as t:
        _import(t, _doc(alias_approved=False))
        snap = t.vs.snapshot()
        assert run("ask clod", (), snapshot=snap).text == "ask clod"
        assert run("ask claude", (), snapshot=snap).text == "ask Claude"
    # Documented defaults for OMITTED fields are unchanged.
    with TempStore() as t:
        doc = _doc()
        for k in ("approved", "enabled", "pinned"):
            doc["entries"][0].pop(k)
        doc["entries"][0]["aliases"][0].pop("approved")
        _import(t, doc)
        e = t.vs.entries()[0]
        assert (e.approved, e.enabled, e.pinned, e.aliases[0].approved) \
            == (False, True, False, True)
    print("ok  07 import: 28 malformed boolean cells rejected with no"
          " write and no content; real booleans and omitted defaults kept")


def test_07_public_api_and_constructor_are_strict():
    with TempStore() as t:
        eid = t.vs.add_entry("Claude", ["clod"], approved=False)
        rev = t.vs.revision()
        for kw in ({"approved": "false"}, {"enabled": 1},
                   {"pinned": "true"}, {"priority": True},
                   {"priority": "3"}, {"aliases": [("clod", "false")]},
                   {"aliases": [("clod", 1)]}):
            raises(lambda: t.vs.update_entry(eid, **kw), ValueError,
                   TypeError)
        assert t.vs.revision() == rev and not t.vs.entry(eid).approved
        for kw in ({"approved": "false"}, {"enabled": 0},
                   {"pinned": None}):
            raises(lambda: t.vs.add_entry("Other", ["other"], **kw),
                   ValueError, TypeError)
        assert [e.canonical for e in t.vs.entries()] == ["Claude"]
    raises(lambda: V.VocabularyEntry(entry_id="x", canonical="C",
                                     approved="false"), TypeError)
    raises(lambda: V.Alias("clod", approved="yes"), TypeError)
    raises(lambda: V.VocabularyEntry.from_json(
        {"entry_id": "x", "canonical": "C", "enabled": "false"}),
        ValueError, TypeError)
    print("ok  07 update/add/constructor/from_json refuse non-boolean"
          " flags and non-integer priorities")


# ---------------------------------------------------------------------------
# 09 — dictionary skill edits keep their approving entry
# ---------------------------------------------------------------------------

def test_09_dictionary_skill_provenance():
    from localflow.v2.developer import skills as sk
    snap = V.VocabularySnapshot([
        ent("E-SK", "code-review", ["code review"], kind="skill")])
    assert dict(snap.skill_provenance) == {
        "code review": ("E-SK", "explicit"),
        "code-review": ("E-SK", "explicit")}
    manifest = [sk.SkillRecord(name="brainstorm")]
    reg = sk.SkillRegistry(manifest, dict(snap.skills),
                           dictionary_provenance=snap.skill_provenance)
    pol = NormalizationPolicy(registered_skills=dict(reg.policy_skills),
                              skill_provenance=dict(reg.policy_provenance))
    ctx = ContextSnapshot(vocabulary=snap)
    res = normalize("slash code review", pol, ctx)
    assert res.text == "/code-review"
    assert [(e.cls, e.rule_id, e.reason) for e in res.edits] == \
        [("skill", "E-SK", "explicit")], res.edits
    res = normalize("slash brainstorm", pol, ctx)
    assert res.text == "/brainstorm" and res.edits[0].rule_id is None, \
        "manifest skills never receive a fabricated M05 id"
    # A policy without provenance (no dictionary) is unchanged.
    plain = NormalizationPolicy(registered_skills={"code review":
                                                   "code-review"})
    assert plain.policy_revision == NormalizationPolicy(
        registered_skills={"code review": "code-review"}).policy_revision
    assert plain.policy_revision != pol.policy_revision
    # Collision with a manifest name masks the alias (no rule applies).
    clash = sk.SkillRegistry([sk.SkillRecord(name="review",
                                             aliases=("code review",))],
                             dict(snap.skills),
                             dictionary_provenance=snap.skill_provenance)
    assert "code review" not in clash.policy_skills
    assert "code review" not in clash.policy_provenance
    # Evidence: the vocabulary block lists applied skill rules.
    from localflow.v2 import ids, store as store_mod, training
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        consent = training.ConsentManager(st, lambda *a, **k: None)
        col = training.EvidenceCollector(st, lambda *a, **k: None, consent,
                                         lambda: {"live": "x"})
        consent.set("enabled")
        cctx = col.job_started(ids.new_id("job"), ids.new_id("fam"),
                               captured_at_utc=ids.now_utc_iso(),
                               timezone=None, utc_offset_minutes=None)
        col.on_asr_result(cctx, "slash code review", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        r = normalize("slash code review", pol, ctx)
        col.on_normalization_result(cctx, r, source_text="slash code review",
                                    policy=pol, context=ctx)
        col.on_cleanup_result(cctx, r.text)
        env = st.latest_revision(col.finalize(cctx))
        st.close()
    vb = env["normalization"]["vocabulary"]
    assert vb["applied_skill_rule_ids"] == ["E-SK"], vb
    assert vb["revision"] == snap.revision
    print("ok  09 dictionary skill edit carries E-SK + verification through"
          " snapshot → registry → policy → ledger → evidence")


# ---------------------------------------------------------------------------
# 10 / 11 — import idempotence and identity policy
# ---------------------------------------------------------------------------

def _entry_doc(canonical, aliases, **over):
    d = {"entry_id": "x", "canonical": canonical, "scope": ["global", None],
         "approved": True, "enabled": True, "verification": "explicit",
         "aliases": [{"alias": a, "approved": True} for a in aliases]}
    d.update(over)
    return d


def test_10_repeated_import_is_unchanged():
    with TempStore() as t:
        doc = {"entries": [_entry_doc("Claude", ["zulu", "alpha"])]}
        first = _import(t, doc, "a.json")
        state = (t.vs.revision(), t.vs.entries()[0].revision,
                 len(t.vs.history(t.vs.entries()[0].entry_id)),
                 t.vs.snapshot().revision)
        for n in range(2):
            again = _import(t, doc, f"b{n}.json")
            assert again == {"created": 0, "updated": 0, "unchanged": 1}, \
                again
            assert (t.vs.revision(), t.vs.entries()[0].revision,
                    len(t.vs.history(t.vs.entries()[0].entry_id)),
                    t.vs.snapshot().revision) == state
        assert first["created"] == 1
        # A genuine alias change is still an update.
        doc2 = {"entries": [_entry_doc("Claude", ["zulu", "bravo"])]}
        assert _import(t, doc2, "c.json")["updated"] == 1
        # An approval flip on one alias is a genuine change too.
        doc3 = {"entries": [_entry_doc("Claude", ["zulu", "bravo"])]}
        doc3["entries"][0]["aliases"][1]["approved"] = False
        assert _import(t, doc3, "d.json")["updated"] == 1
    print("ok  10 alias order is not identity: repeat imports unchanged;"
          " real alias/approval changes still update")


def test_11_import_is_one_transaction_with_a_declared_identity():
    cases = {
        "duplicate_new": [_entry_doc("Claude", ["clod"]),
                          _entry_doc("Claude", ["klod"])],
        "ascii_case_variant": [_entry_doc("Claude", ["clod"]),
                               _entry_doc("CLAUDE", ["klod"])],
        "malformed_later_row": [_entry_doc("Claude", ["clod"]),
                                _entry_doc("Qwen", ["q wen"],
                                           approved="yes")],
    }
    for label, entries in cases.items():
        with TempStore() as t:
            rev0 = t.vs.revision()
            e = raises(lambda: _import(t, {"entries": entries}), ValueError)
            assert not any(c in str(e) for c in CANARY), (label, str(e))
            assert not t.vs.entries() and t.vs.revision() == rev0, label
    with TempStore() as t:
        t.vs.add_entry("Claude", ["clod"], approved=True)
        raises(lambda: _import(t, {"entries": [
            _entry_doc("claude", ["x"]), _entry_doc("Claude", ["y"])]}),
            ValueError)
        assert [[a.alias for a in e.aliases] for e in t.vs.entries()] == \
            [["clod"]]
    # Declared identity = SQLite NOCASE (ASCII case only): non-ASCII case
    # variants are distinct entries, exactly as the unique index sees them.
    with TempStore() as t:
        r = _import(t, {"entries": [_entry_doc("Éclair", ["eclair"]),
                                    _entry_doc("éclair", ["ekler"])]})
        assert r["created"] == 2
        again = _import(t, {"entries": [_entry_doc("Éclair", ["eclair"]),
                                        _entry_doc("éclair", ["ekler"])]},
                        "b.json")
        assert again == {"created": 0, "updated": 0, "unchanged": 2}, again
    # A writer fault mid-file commits nothing (whole-file transaction).
    with TempStore() as t:
        t.store.submit(lambda db: db.execute(
            "CREATE TRIGGER t_fail BEFORE INSERT ON vocabulary_entries"
            " WHEN NEW.canonical = 'Qwen' BEGIN SELECT RAISE(ABORT,"
            " 'synthetic'); END"))
        raises(lambda: _import(t, {"entries": [
            _entry_doc("Claude", ["clod"]), _entry_doc("Qwen", ["q wen"])]}))
        assert not t.vs.entries() and t.vs.revision() == 0
    print("ok  11 import: preflight + one transaction; duplicate/malformed"
          " files commit nothing; NOCASE (ASCII) identity declared")


# ---------------------------------------------------------------------------
# 12 — alias language inheritance
# ---------------------------------------------------------------------------

def test_12_alias_language_inherits_or_overrides():
    with TempStore() as t:
        eid = t.vs.add_entry("Claude", ["clod"], language="en",
                             approved=True)
        t.vs.update_entry(eid, language="es")
        e = t.vs.entry(eid)
        assert [(a.alias, a.language or e.language) for a in e.aliases] \
            == [("clod", "es")], e.aliases
        assert run("clod", (), snapshot=t.vs.snapshot()).text == "Claude"
        # Explicit override survives an entry-language change.
        t.vs.update_entry(eid, aliases=[V.Alias("clod", True, "de")])
        t.vs.update_entry(eid, language="fr")
        assert t.vs.entry(eid).aliases[0].language == "de"
    with TempStore() as t:
        doc = {"entries": [_entry_doc("Claude", ["clod", "klod"],
                                      language="en")]}
        doc["entries"][0]["aliases"][0]["language"] = "es"
        _import(t, doc)
        exp = t.vs.export_json()["entries"][0]
        eff = {a["alias"]: a["language"] or exp["language"]
               for a in exp["aliases"]}
        assert eff == {"clod": "es", "klod": "en"}, exp["aliases"]
        assert _import(t, {"entries": [exp]}, "b.json") == \
            {"created": 0, "updated": 0, "unchanged": 1}
    print("ok  12 alias language: inherited follows the entry, explicit"
          " overrides survive update and export/import")


# ---------------------------------------------------------------------------
# 13 — sandbox and conflict preview describe live behavior
# ---------------------------------------------------------------------------

def test_13_sandbox_suggestions_follow_the_engine():
    unapproved = [ent("E-U", "Claude Code", ["clod code"], approved=False)]
    for text in ('say " clod code " now', "```text\nclod code\n```",
                 "write the phrase clod code", "clod, code"):
        out = V.sandbox_phrase(text, V.VocabularySnapshot(unapproved))
        assert not out["suggestions"], (text, out["suggestions"])
    out = V.sandbox_phrase("use clod code today",
                           V.VocabularySnapshot(unapproved))
    assert [(s["text"], s["canonical"], s["entry_id"], s["in_scope"])
            for s in out["suggestions"]] == [
        ("clod code", "Claude Code", "E-U", True)], out["suggestions"]
    assert out["output"] == "use clod code today" and not out["applied"]
    # A suggestion whose alias an ACTIVE same-scope contender would mask
    # is not advertised as a rewrite.
    masked = unapproved + [ent("E-A", "Cloud Code", ["clod code"])]
    out = V.sandbox_phrase("use clod code", V.VocabularySnapshot(masked))
    assert all(s["entry_id"] != "E-U" or s.get("masked")
               for s in out["suggestions"]), out["suggestions"]
    # Out-of-scope suggestion: labeled, would-be output computed in its
    # own scope.
    ws = [ent("E-W", "WorkspaceName", ["clod"], approved=False,
              scope_kind="workspace", scope_value="X")]
    out = V.sandbox_phrase("ask clod", V.VocabularySnapshot(ws))
    assert [(s["canonical"], s["in_scope"]) for s in out["suggestions"]] \
        == [("WorkspaceName", False)], out["suggestions"]
    assert out["scope"] == V.ScopeContext().to_json()
    out = V.sandbox_phrase("ask clod", V.VocabularySnapshot(
        ws, V.ScopeContext(workspace="X")))
    assert out["scope"]["workspace"] == "X"
    assert out["suggestions"][0]["in_scope"] is True
    print("ok  13 sandbox: suggestions computed by the real engine under"
          " hypothetical approval (protection, barriers, masks, scope)")


def test_13_preview_distinguishes_active_from_hypothetical():
    cand = ent("E-NEW", "Claude", ["clod"])
    cases = {
        "active": (ent("E-OLD", "Cloud", ["clod"]), True, "ask clod now"),
        "disabled": (ent("E-OLD", "Cloud", ["clod"], enabled=False), False,
                     "ask Claude now"),
        "unapproved": (ent("E-OLD", "Cloud", ["clod"], approved=False),
                       False, "ask Claude now"),
        "alias_unapproved": (ent("E-OLD", "Cloud",
                                 [V.Alias("clod", approved=False)]),
                             False, "ask Claude now"),
    }
    for label, (other, active, committed) in cases.items():
        prev = V.preview_entry_conflicts(cand, [other])
        masks = [c for c in prev if c["kind"] == "same_scope_mask"]
        assert len(masks) == 1 and masks[0]["active"] is active, \
            (label, prev)
        assert run("ask clod now", [cand, other]).text == committed, label
    # Term vs skill on one alias: no mask (different layers) — the skill
    # wins only on its slash command span.
    skill = ent("E-SK", "review", ["clod"], kind="skill")
    prev = V.preview_entry_conflicts(cand, [skill])
    assert [c["kind"] for c in prev] == ["skill_wins"], prev
    assert run("ask clod now", [cand, skill]).text == "ask Claude now"
    # A candidate that is not yet active: every conflict is hypothetical.
    prev = V.preview_entry_conflicts(ent("E-NEW", "Claude", ["clod"],
                                         approved=False),
                                     [ent("E-OLD", "Cloud", ["clod"])])
    assert prev and all(c["active"] is False for c in prev), prev
    print("ok  13 conflict preview: active vs hypothetical labeled; term vs"
          " skill never reported as a mask")


def test_13_every_preview_kind_matches_committed_behavior():
    """Each of the four preview kinds, active and hypothetical, against
    what the committed dictionary actually does."""
    ws = V.ScopeContext(workspace="W")
    # scope_precedence: active → the narrower entry wins where both apply.
    cand = ent("E-N", "Klaude", ["clod"], scope_kind="workspace",
               scope_value="W")
    wide = ent("E-G", "Claude", ["clod"])
    prev = V.preview_entry_conflicts(cand, [wide])
    assert [(c["kind"], c["active"]) for c in prev] == \
        [("scope_precedence", True)], prev
    assert "workspace-scoped entry wins" in prev[0]["detail"]
    assert run("ask clod", [cand, wide], ws).text == "ask Klaude"
    assert run("ask clod", [cand, wide]).text == "ask Claude"
    prev = V.preview_entry_conflicts(cand, [ent("E-G", "Claude", ["clod"],
                                                approved=False)])
    assert [(c["kind"], c["active"]) for c in prev] == \
        [("scope_precedence", False)], prev
    # duplicate_canonical: both entries keep applying their own aliases.
    a = ent("E-1", "Claude", ["clod"])
    b = ent("E-2", "Claude", ["klod"], scope_kind="workspace",
            scope_value="W")
    prev = V.preview_entry_conflicts(b, [a])
    assert [(c["kind"], c["active"]) for c in prev] == \
        [("duplicate_canonical", True)], prev
    assert run("clod and klod", [a, b], ws).text == "Claude and Claude"
    # skill_wins: the skill owns its slash span, the term the bare word.
    term = ent("E-T", "Review Doc", ["code review"])
    skill = ent("E-SK", "code-review", ["code review"], kind="skill")
    prev = V.preview_entry_conflicts(term, [skill])
    assert [(c["kind"], c["active"]) for c in prev] == \
        [("skill_wins", True)], prev
    snap = V.VocabularySnapshot([term, skill])
    pol = NormalizationPolicy(registered_skills=dict(snap.skills),
                              skill_provenance=dict(snap.skill_provenance))
    assert normalize("slash code review", pol,
                     ContextSnapshot(vocabulary=snap)).text == "/code-review"
    assert normalize("a code review today", pol,
                     ContextSnapshot(vocabulary=snap)).text == \
        "a Review Doc today"
    prev = V.preview_entry_conflicts(term, [ent(
        "E-SK", "code-review", ["code review"], kind="skill",
        enabled=False)])
    assert [(c["kind"], c["active"]) for c in prev] == \
        [("skill_wins", False)], prev
    print("ok  13 preview kinds (mask, precedence, duplicate canonical,"
          " skill) each match committed behavior, active and hypothetical")


def test_17_hint_budget_matrix():
    sel = V.RelevantVocabularySelector(100)
    # Many pins starve an unpinned narrow entry at the budget (D4: rank
    # order is contractual — pin before scope — and stays as documented).
    pins = [ent(f"E-P{i:03d}", f"Pin{i:03d}", pinned=True)
            for i in range(120)]
    narrow = ent("E-W", "Narrow", scope_kind="workspace", scope_value="W")
    hs = sel.select(V.VocabularySnapshot(pins + [narrow],
                                         V.ScopeContext(workspace="W")))
    assert [t.entry_id for t in hs.terms] == \
        [f"E-P{i:03d}" for i in range(100)]
    assert [o["entry_id"] for o in hs.omitted] == \
        [f"E-P{i:03d}" for i in range(100, 120)] + ["E-W"]
    # Inactive entries are never offered; duplicates take separate slots;
    # a masked alias's canonicals are still offered (D3), none rewrite.
    ents = [ent("E-D", "Disabled", enabled=False),
            ent("E-O", "OtherScope", scope_kind="workspace",
                scope_value="X"),
            ent("E-S", "Suggested", approved=False),
            ent("E-C1", "Claude"), ent("E-C2", "Claude",
                                        scope_kind="workspace",
                                        scope_value="W"),
            ent("E-M1", "Cloud", ["clod"]), ent("E-M2", "Clown", ["clod"])]
    snap = V.VocabularySnapshot(ents, V.ScopeContext(workspace="W"))
    ids = [t.entry_id for t in sel.select(snap).terms]
    assert "E-D" not in ids and "E-O" not in ids, ids
    assert {"E-S", "E-C1", "E-C2", "E-M1", "E-M2"} <= set(ids), ids
    assert run("ask clod", (), snapshot=snap).text == "ask clod"
    print("ok  17 hint budget: pin starvation recorded, inactive excluded,"
          " duplicates and masked canonicals offered (never rewriting)")


# ---------------------------------------------------------------------------
# 14 / 15 — evidence
# ---------------------------------------------------------------------------

def _collector(td):
    from localflow.v2 import ids, store as store_mod, training
    st = store_mod.Store(pathlib.Path(td) / "v2.db")
    events = []

    def rec(name, **kw):
        events.append({"event": name, **kw})
    consent = training.ConsentManager(st, rec)
    col = training.EvidenceCollector(st, rec, consent, lambda: {"live": "x"})
    consent.set("enabled")
    job = ids.new_id("job")
    ctx = col.job_started(job, ids.new_id("fam"),
                          captured_at_utc=ids.now_utc_iso(), timezone=None,
                          utc_offset_minutes=None)
    return st, col, events, ctx, job


def test_14_hint_retention_failure_is_precise():
    from localflow.v2 import capabilities
    for fail_at in ("write", "lease"):
        with tempfile.TemporaryDirectory() as td:
            st, col, events, ctx, job = _collector(td)
            hs = V.RelevantVocabularySelector(10).select(
                V.VocabularySnapshot([ent("E-CL", "AUDIT_CANARY_CANON",
                                          ["audit canary alias"])]))
            real_w, real_l = st.write_text_artifact, st.grant_lease

            def w(**kw):
                if kw.get("role") == "hint_set" and fail_at == "write":
                    raise OSError("synthetic")
                return real_w(**kw)

            def lease(aid, holder, days=None):
                if st.artifact(aid).get("role") == "hint_set" \
                        and fail_at == "lease":
                    raise OSError("synthetic")
                return real_l(aid, holder, days=days)
            st.write_text_artifact, st.grant_lease = w, lease
            col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
            st.write_text_artifact, st.grant_lease = real_w, real_l
            col.on_asr_result(ctx, "x", model_id="m", model_revision=None,
                              stage_duration_ms=0.0)
            env = st.latest_revision(col.finalize(ctx))
            cb = env["context"]
            st.close()
        assert cb["hint_set_id"] == hs.hint_set_id
        assert cb["offered_terms"] == 1 and cb["omitted_terms"] == 0
        assert cb["hint_set_missing_reason"] == "retention_write_failed", cb
        assert "hint_set" not in cb["artifact_ids"], cb
        assert env["missing_reasons"]["hint_set_payload"] == \
            "retention_write_failed"
        assert "context" not in env["missing_reasons"]
        failed = [e for e in events if e["event"] == "training.capture_failed"]
        assert failed and failed[0]["outcome"] == "hint_set_not_retained" \
            and failed[0]["detail"] == f"hint_set_{fail_at}", failed
        blob = json.dumps(events, default=str) + json.dumps(env)
        assert "AUDIT_CANARY" not in blob and "audit canary" not in blob
    # A genuinely absent HintSet keeps the ordinary reason.
    with tempfile.TemporaryDirectory() as td:
        st, col, events, ctx, job = _collector(td)
        col.on_asr_result(ctx, "x", model_id="m", model_revision=None,
                          stage_duration_ms=0.0)
        env = st.latest_revision(col.finalize(ctx))
        st.close()
    assert env["missing_reasons"]["context"] == "not_captured_at_stage"
    print("ok  14 hint retention failure: id/counts kept, precise reason,"
          " failed step, no dangling reference, no content")


def test_15_applied_rule_state_reconstructable():
    from localflow.v2 import capabilities
    with tempfile.TemporaryDirectory() as td:
        st, col, events, ctx, job = _collector(td)
        vs = VS.VocabularyStore(st)
        eid = vs.add_entry("Zeta", ["zeeta", ("zed", False)],
                           scope_kind="workspace", scope_value="W1",
                           approved=True)
        vs.update_entry(eid, priority=2)
        sk = vs.add_entry("code-review", ["code review"], kind="skill",
                          approved=True)
        for i in range(3):
            vs.add_entry(f"Pin{i}", [], pinned=True, approved=True)
        snap = vs.snapshot(V.ScopeContext(workspace="W1"))
        hs = V.RelevantVocabularySelector(1).select(snap)
        assert all(t.entry_id not in (eid, sk) for t in hs.terms)
        col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
        text = "slash code review with zeeta"
        col.on_asr_result(ctx, text, model_id="m", model_revision=None,
                          stage_duration_ms=0.0)
        from localflow.v2.developer import skills as skmod
        reg = skmod.SkillRegistry((), dict(snap.skills),
                                  dictionary_provenance=snap.skill_provenance)
        pol = NormalizationPolicy(registered_skills=dict(reg.policy_skills),
                                  skill_provenance=dict(
                                      reg.policy_provenance))
        cctx = ContextSnapshot(vocabulary=snap)
        res = normalize(text, pol, cctx)
        assert res.text == "/code-review with Zeta", res.text
        col.on_normalization_result(ctx, res, source_text=text, policy=pol,
                                    context=cctx)
        col.on_cleanup_result(ctx, res.text)
        env = st.latest_revision(col.finalize(ctx))
        vs.update_entry(eid, aliases=[("zeeta", False)])
        vs.delete_entry(eid)
        vs.delete_entry(sk)
        vb = env["normalization"]["vocabulary"]
        # Clean reader: only the retained artifact named by the envelope.
        rules = json.loads(st.artifact_payload(vb["applied_rules_artifact"]))
        blob = json.dumps(env) + json.dumps(events, default=str)
        st.close()
    by_id = {r["entry_id"]: r for r in rules["rules"]}
    z = by_id[eid]
    assert (z["scope"], z["approved"], z["verification"], z["revision"]) \
        == (["workspace", "W1"], True, "explicit", 2), z
    assert sorted((a["alias"], a["approved"]) for a in z["aliases"]) == \
        [("zed", False), ("zeeta", True)]
    assert by_id[sk]["kind"] == "skill"
    assert rules["vocabulary_revision"] == snap.revision
    assert sorted(vb["applied_rule_ids"] + vb["applied_skill_rule_ids"]) \
        == sorted([eid, sk])
    # The envelope stays content-free (ids/revisions/counts only).
    assert "W1" not in blob and "zeeta" not in blob and "Zeta" not in blob
    print("ok  15 applied rules (term + skill) reconstructable from the"
          " retained lease-governed manifest after edit + delete")


# ---------------------------------------------------------------------------
# 16 — the benchmark gates actual vocabulary work before timing
# ---------------------------------------------------------------------------

def _bench(patch=None):
    """Run scripts/v2/benchmark_m05.py main() in-process on a small
    dictionary with a scripted clock (timing trivially met, so the exit
    code can only reflect WORK validity), optionally with a production
    mutation applied; everything patched is restored."""
    import contextlib
    import importlib.util
    import io
    import time as time_mod
    spec = importlib.util.spec_from_file_location(
        "bench_m05", ROOT / "scripts" / "v2" / "benchmark_m05.py")
    bench = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv
    sys.argv = ["benchmark_m05.py"]
    try:
        spec.loader.exec_module(bench)
    finally:
        sys.argv = saved_argv
    bench.ARGS.entries, bench.ARGS.reps = 800, 5
    clock = [0.0]

    def mono():
        clock[0] += 1e-6
        return clock[0]
    real_mono = time_mod.monotonic
    undo = patch() if patch else (lambda: None)
    time_mod.monotonic = mono
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return bench.main()
    finally:
        time_mod.monotonic = real_mono
        undo()


def test_16_benchmark_rejects_invalid_work():
    from localflow.v2.normalize import syntax as syn

    def identity_matcher():
        real = syn.grammar_vocabulary
        syn.grammar_vocabulary = lambda host: iter(())
        return lambda: setattr(syn, "grammar_vocabulary", real)

    def skip_fourth():
        real = syn.grammar_vocabulary

        def g(host):
            for i, p in enumerate(real(host)):
                if i % 4 != 3:
                    yield p
        syn.grammar_vocabulary = g
        return lambda: setattr(syn, "grammar_vocabulary", real)

    def wrong_scope_selector():
        real = V.RelevantVocabularySelector.select

        def sel(self, snap, scope_ctx=None, **kw):
            return real(self, V.VocabularySnapshot(snap.entries, None),
                        None, **kw)
        V.RelevantVocabularySelector.select = sel
        return lambda: setattr(V.RelevantVocabularySelector, "select",
                               real)

    def drop_rule_ids():
        real = syn.grammar_vocabulary

        def g(host):
            for p in real(host):
                yield dataclasses.replace(p, rule_id=None)
        syn.grammar_vocabulary = g
        return lambda: setattr(syn, "grammar_vocabulary", real)
    assert _bench() == 0, "the unmodified tree must be work-valid"
    for name, mut in (("identity_matcher", identity_matcher),
                      ("skip_every_fourth_edit", skip_fourth),
                      ("wrong_scope_selector", wrong_scope_selector),
                      ("drop_rule_ids", drop_rule_ids)):
        assert _bench(mut) == 2, f"{name} earned a non-invalid verdict"
    print("ok  16 benchmark: identity matcher, skipped edits, wrong-scope"
          " selection and dropped rule ids all exit 2 (work_invalid)")


def test_15_applied_rule_manifest_is_deleted_with_the_job():
    from localflow.v2 import capabilities  # noqa: F401
    with tempfile.TemporaryDirectory() as td:
        st, col, events, ctx, job = _collector(td)
        snap = V.VocabularySnapshot([ent("E-CL", "Claude", ["clod"])])
        col.on_asr_result(ctx, "ask clod", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        pol = NormalizationPolicy()
        cctx = ContextSnapshot(vocabulary=snap)
        res = normalize("ask clod", pol, cctx)
        col.on_normalization_result(ctx, res, source_text="ask clod",
                                    policy=pol, context=cctx)
        col.on_cleanup_result(ctx, res.text)
        env = st.latest_revision(col.finalize(ctx))
        aid = env["normalization"]["vocabulary"]["applied_rules_artifact"]
        assert st.artifact(aid)["role"] == "vocabulary_applied_rules"
        st.delete_everywhere("job", job)
        st.sync()
        con = sqlite3.connect(st.db_path)
        live = con.execute("SELECT count(*) FROM artifacts WHERE job_id=?"
                           " AND purged=0", (job,)).fetchone()[0]
        con.close()
        st.close()
    assert live == 0, "delete-everywhere must reach the rule manifest"
    print("ok  15 the applied-rule manifest is job-keyed: delete-everywhere"
          " removes it with the job")


# ---------------------------------------------------------------------------
# 18 — populated torn tables are never a silent healthy dictionary
# ---------------------------------------------------------------------------

def test_18_integrity_report_over_populated_torn_tables():
    from localflow.v2 import store as store_mod
    with tempfile.TemporaryDirectory() as td:
        seed = pathlib.Path(td) / "seed.db"
        st = store_mod.Store(seed)
        vs = VS.VocabularyStore(st)
        e1 = vs.add_entry("Claude", ["clod", ("klod", False)], approved=True)
        vs.add_entry("Cloud", ["clod"], approved=True)
        vs.update_entry(e1, priority=3)
        gone = vs.add_entry("Gone", ["gon"], approved=True)
        vs.delete_entry(gone)
        before = [(e.entry_id, e.canonical, e.revision, e.priority,
                   [(a.alias, a.approved) for a in e.aliases])
                  for e in vs.entries()]
        assert vs.integrity_report() == {
            "vanished_entries": 0, "orphan_alias_rows": 0,
            "entries_missing_aliases": 0}
        st.close()
        expect = {
            "drop_aliases": {"entries_missing_aliases": 2},
            "drop_history": {},
            "drop_entries": {"vanished_entries": 2,
                             "orphan_alias_rows": 3},
            "drop_unique_index": {},
            "drop_meta": {},
        }
        sql = {"drop_aliases": "DROP TABLE vocabulary_aliases",
               "drop_history": "DROP TABLE vocabulary_history",
               "drop_entries": "DROP TABLE vocabulary_entries",
               "drop_unique_index":
                   "DROP INDEX idx_vocabulary_canonical_scope",
               "drop_meta": "DROP TABLE vocabulary_meta"}
        for label, want in expect.items():
            copy = pathlib.Path(td) / f"{label}.db"
            copy.write_bytes(seed.read_bytes())
            con = sqlite3.connect(copy)
            con.execute(sql[label])
            con.commit()
            con.close()
            st2 = store_mod.Store(copy, backup_dir=pathlib.Path(td) / "bk")
            vs2 = VS.VocabularyStore(st2)
            rep = vs2.integrity_report()
            after = [(e.entry_id, e.canonical, e.revision, e.priority,
                      [(a.alias, a.approved) for a in e.aliases])
                     for e in vs2.entries()]
            st2.close()
            full = {"vanished_entries": 0, "orphan_alias_rows": 0,
                    "entries_missing_aliases": 0, **want}
            assert rep == full, (label, rep)
            if label in ("drop_history", "drop_unique_index", "drop_meta"):
                assert after == before, label
            if label == "drop_aliases":
                assert [x[:4] for x in after] == [x[:4] for x in before]
    print("ok  18 populated torn M05 tables: survivors byte-exact; lost"
          " aliases/entries reported by the integrity report, never silent")


# ---------------------------------------------------------------------------
# 19 — contextual-biasing qualification is identity-bound
# ---------------------------------------------------------------------------

def test_19_qualification_requires_identity():
    from localflow.v2 import capabilities as cap
    hs = V.RelevantVocabularySelector(5).select(
        V.VocabularySnapshot([ent("E-CL", "Claude", ["clod"])]))

    def manifest(**mut):
        m = cap.asr_capability_manifest("m", model_revision="rev1",
                                        runtime={"mlx": "1"})
        m = json.loads(json.dumps(m))
        cb = m["capabilities"]["contextual_biasing"]
        cb["supported"] = True
        cb["qualified_identity"] = {"adapter": m["adapter"],
                                    "model_id": "m",
                                    "model_revision": "rev1",
                                    "runtime": {"mlx": "1"}}
        cb["evidence"] = "synthetic qualification record (test only)"
        for k, v in mut.items():
            if k == "drop":
                cb.pop(v)
            elif k == "manifest":
                m.update(v)
            else:
                cb[k] = v
        return m
    ok_m = manifest()
    f = cap.asr_hint_request_fields(hs, ok_m, context_snapshot_id="ctx-1")
    assert f is not None and f["context_snapshot_id"] == "ctx-1"
    assert f["hint_set_id"] == hs.hint_set_id
    assert cap.hint_disposition(ok_m, hs)["ignored"] is False
    bad = {
        "flag_only": manifest(drop="qualified_identity"),
        "no_evidence": manifest(drop="evidence"),
        "missing_checkpoint": manifest(manifest={"model_revision": None}),
        "changed_checkpoint": manifest(manifest={"model_revision": "rev2"}),
        "changed_runtime": manifest(manifest={"runtime": {"mlx": "2"}}),
        "changed_model": manifest(manifest={"model_id": "other"}),
    }
    for label, m in bad.items():
        assert cap.asr_hint_request_fields(hs, m, "ctx-1") is None, label
        d = cap.hint_disposition(m, hs)
        assert d["ignored"] is True and d["accepted_terms"] == 0 \
            and d["ignored_reason"] == "disabled_until_qualified", (label, d)
    prod = cap.asr_capability_manifest("m", model_revision="rev1")
    assert cap.asr_hint_request_fields(hs, prod) is None
    raises(lambda: cap.asr_hint_request_fields(hs, ok_m,
                                               context_snapshot_id=7),
           TypeError)
    print("ok  19 hint request fields need a complete adapter/checkpoint/"
          "runtime identity + evidence; a bare supported flag is refused")


# ---------------------------------------------------------------------------
# Selector limits (17) and 20 — active documentation
# ---------------------------------------------------------------------------

def test_17_selector_limit_is_strict():
    for bad in (0, -1, "100", 1.5, True, None):
        raises(lambda: V.RelevantVocabularySelector(bad), ValueError,
               TypeError)
    assert V.RelevantVocabularySelector().max_terms == 100
    assert V.RelevantVocabularySelector(1).max_terms == 1
    print("ok  17 selector: malformed limits refused, documented default"
          " and positive limits kept")


def test_02c_scope_context_rejects_non_string_identity():
    # Found during first-pass validation: a destination identity whose
    # bundle is not a string made the snapshot's revision hash raise,
    # and the job lost EVERY entry (global ones included).
    class Opaque:
        def __bool__(self):
            return False
    for field in ("app_bundle", "site_origin", "workspace", "profile"):
        raises(lambda: V.ScopeContext(**{field: Opaque()}), TypeError)
        raises(lambda: V.ScopeContext(**{field: 7}), TypeError)

    class Bridged(str):  # PyObjC hands NSString over as a str subclass
        pass
    ctx = V.ScopeContext(app_bundle=Bridged("app.A"), workspace="ws")
    assert type(ctx.app_bundle) is str and ctx.app_bundle == "app.A"
    snap = V.VocabularySnapshot(
        [ent("E-A", "Claude", ["clod"], scope_kind="app",
             scope_value="app.A"),
         ent("E-G", "GlobalTerm", ["glob term"])], ctx)
    assert run("ask clod glob term", (), snapshot=snap).text == \
        "ask Claude GlobalTerm"
    assert snap.revision == V.VocabularySnapshot(
        snap.entries, V.ScopeContext(app_bundle="app.A",
                                     workspace="ws")).revision
    print("ok  02c scope context: non-string identity refused at"
          " construction; bridged strings normalized, scoped + global"
          " entries apply")


def test_20_active_statements_are_current():
    stale = {
        "docs/v2/contracts/vocabulary.md": [
            "`profile` stays unfed until a writing-profile subsystem",
            "Pre-M06 the live app filters with no destination context"],
        "docs/v2/contracts/asr_hints.md": ["not a consumer yet"],
        "tests/v2/vocabulary/test_hint_selection.py": [
            "cleanup deferred to M07 (not a consumer yet)"],
    }
    for rel, needles in stale.items():
        flat = " ".join((ROOT / rel).read_text(encoding="utf-8").split())
        for n in needles:
            assert " ".join(n.split()) not in flat, (rel, n)
    flat = " ".join((ROOT / "docs/v2/contracts/vocabulary.md").read_text(
        encoding="utf-8").split())
    for n in ("M05 remediation", "applied-rule manifest",
              "expected_revision"):
        assert n in flat, n
    print("ok  20 active contracts/tests describe the connected M06/M07/M10"
          " system (history kept in the handoffs)")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}"[:600])
    if failed:
        print(f"{failed} of {len(tests)} M05 remediation tests FAILED")
        return 1
    print(f"all {len(tests)} M05 remediation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
