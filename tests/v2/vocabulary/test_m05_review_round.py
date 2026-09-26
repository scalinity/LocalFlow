"""M05 remediation — regressions from the independent review round.

The first-pass repair (a164456) was frozen and reviewed by a separate,
read-only reviewer in its own worktree; every finding it reported was
re-run on a164456 before any fix. Each test here fails on a164456 and
passes on the final code (per-test records under
docs/v2/acceptance/M05/remediation/). ``R*`` tests come from the
reviewer; ``A*`` tests are defects the author found while the review ran.

Pure-Python tests run directly; the panel test uses the declared
non-native shims (tests/v2/lifecycle/native_shims.py) — portable
orchestration evidence, never native AppKit evidence.

Run: .venv/bin/python tests/v2/vocabulary/test_m05_review_round.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m05_helpers import (  # noqa: E402
    TempStore,
    V,
    ent,
    panel,
    run,
    vocab_edits,
)


def _stable(text, entries, scope=None):
    """(pass 1 text, pass 2 text, pass 2 vocabulary edits)."""
    p1 = run(text, entries, scope)
    p2 = run(p1.text, entries, scope)
    return p1.text, p2.text, vocab_edits(p2)


# ---------------------------------------------------------------------------
# R1 / R2 / R17 — canonical claims keep the first pass's winner
# ---------------------------------------------------------------------------

def test_R1_claim_is_as_strong_as_its_entry():
    # The winning alias is LONGER than its canonical: on pass 2 the
    # canonical must still beat the alias that lost on pass 1.
    right = [ent("vx", "Red Status", ["reddish status"]),
             ent("vy", "Orange Page", ["status page"])]
    for text, want in (("reddish status page", "Red Status page"),
                       ("the reddish status page is up",
                        "the Red Status page is up")):
        p1, p2, e2 = _stable(text, right)
        assert (p1, p2, e2) == (want, want, []), (text, p1, p2, e2)
    left = [ent("va", "Orange Status", ["red status"]),
            ent("vb", "Status Up", ["status paging now"])]
    p1, p2, e2 = _stable("red status paging now", left)
    assert (p1, p2, e2) == ("red Status Up", "red Status Up", []), \
        (p1, p2, e2)
    # Positive controls: each alias alone still applies.
    assert run("reddish status", right).text == "Red Status"
    assert run("status page", right).text == "Orange Page"
    assert run("red status", left).text == "Orange Status"
    print("ok  R1 a canonical claim is as strong as its entry's longest"
          " form: left and right overlaps stay idempotent")


def test_R2_a_defeated_claim_suppresses_nothing():
    E = [ent("E-C", "Bb Cc"), ent("E-P", "Zz", ["aaaaaa bb"]),
         ent("E-Q", "Yy", ["cc dd"])]
    upper = run("aaaaaa Bb Cc dd", E)
    lower = run("aaaaaa bb cc dd", E)
    assert upper.text == lower.text == "Zz Yy", (upper.text, lower.text)
    assert [r for _, _, r in vocab_edits(upper)] == ["E-P", "E-Q"]
    assert run(upper.text, E).text == "Zz Yy"
    # Equal-length right overlap: the earlier claim wins by start, as
    # its proposal did on pass 1 (claim-tie mutation witness).
    T = [ent("E-A", "Alpha Beta"), ent("E-B", "Zeta Q", ["beta gamma"])]
    p1, p2, e2 = _stable("alpha beta gamma", T)
    assert (p1, p2, e2) == ("Alpha Beta gamma", "Alpha Beta gamma", []), \
        (p1, p2, e2)
    # Same span: already-canonical text beats a proposal on that span.
    p1, p2, e2 = _stable("Alpha Beta", T)
    assert (p1, p2, e2) == ("Alpha Beta", "Alpha Beta", [])
    print("ok  R2 claims arbitrate with proposals: a beaten claim"
          " suppresses nothing; ties by start; same span keeps the"
          " canonical")


def test_R17_no_second_pass_drift_through_a_canonical():
    ws = V.ScopeContext(workspace="W")
    chain = [ent("E-G", "Cloud", ["clod"]),
             ent("E-W", "Claude", ["cloud"], scope_kind="workspace",
                 scope_value="W")]
    assert _stable("ask clod now", chain, ws) == \
        ("ask Cloud now", "ask Cloud now", [])
    # The narrower entry still owns its alias in lower case.
    assert run("ask cloud now", chain, ws).text == "ask Claude now"
    masked = [ent("E-X", "Claude Code", ["clod code"]),
              ent("E-Y", "Clawed Code", ["claude code"]),
              ent("E-Z", "Kode", ["code"])]
    assert _stable("use clod code", masked) == \
        ("use Claude Code", "use Claude Code", [])
    # Positive control: the short alias applies outside the canonical.
    assert run("write code", masked).text == "write Kode"
    # An unapproved or disabled entry's canonical claims nothing.
    off = [ent("E-X", "Claude Code", ["clod code"], enabled=False),
           ent("E-Z", "Kode", ["code"])]
    assert run("use Claude Code", off).text == "use Claude Kode"
    print("ok  R17 exact canonical spellings of approved in-scope terms"
          " are claims even when their key is shadowed or masked")


def test_R17_declared_residual_chain_is_flagged_not_hidden():
    # A canonical that, with the next word, spells ANOTHER entry's longer
    # alias chains on a later pass. Declared residual (contract): the
    # result must say so rather than claim idempotence.
    from m05_helpers import ContextSnapshot, NormalizationPolicy, normalize
    E = [ent("E-G", "Cloud", ["clod"]),
         ent("E-N", "CloudOps", ["cloud ops"])]
    pol = NormalizationPolicy()
    ctx = ContextSnapshot(vocabulary=V.VocabularySnapshot(E))
    r = normalize("ask clod ops now", pol, ctx)
    assert r.text == "ask Cloud ops now"
    assert r.is_idempotent(pol, ctx) is False
    print("ok  R17 declared residual: a cross-entry chain through a"
          " canonical is reported as not idempotent")


def test_R18_unit_separator_is_a_barrier_unicode_spaces_are_not():
    E = [ent("E-CC", "Claude Code", ["clod code"])]
    assert run("clod\x1fcode", E).text == "clod\x1fcode"
    for sp in ("\u2003", "\u3000", "\u202f", "\u2009", "\u205f"):
        out = run(f"use clod{sp}code", E).text
        assert out == "use Claude Code", (hex(ord(sp)), out)
    print("ok  R18 U+001F is a barrier like U+001C..U+001E; Unicode space"
          " separators stay benign word gaps")


# ---------------------------------------------------------------------------
# Store, import and admission (R3–R7, R11, R12, R16, Q4, Q5)
# ---------------------------------------------------------------------------

def _import(t, doc, name="f.json"):
    import json
    p = t.dir / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return t.vs.import_json(p)


def _refused(fn):
    try:
        fn()
    except (ValueError, TypeError) as e:
        return e
    raise AssertionError("expected a refusal")


def test_R3_R4_explicit_alias_language_survives_language_changes():
    with TempStore() as t:
        # R4: an explicit override EQUAL to the entry language is kept.
        eid = t.vs.add_entry("Claude", [("clod", True, "en"), "klod"],
                             language="en", approved=True)
        t.vs.update_entry(eid, language="fr")
        langs = {a.alias: a.language for a in t.vs.entry(eid).aliases}
        assert langs == {"clod": "en", "klod": None}, langs
        # R3: a file that changes the entry language and names an
        # explicit override equal to the OLD language keeps it; the same
        # file re-imports as unchanged.
        t.vs.add_entry("Kube", ["kube"], language="en", approved=True)
        doc = {"entries": [{"entry_id": "x", "canonical": "Kube",
                            "language": "fr", "approved": True,
                            "verification": "explicit",
                            "aliases": [{"alias": "kube",
                                         "language": "en"}]}]}
        first = _import(t, doc)
        second = _import(t, doc, "g.json")
        kube = [e for e in t.vs.entries() if e.canonical == "Kube"][0]
    assert first == {"created": 0, "updated": 1, "unchanged": 0}, first
    assert second == {"created": 0, "updated": 0, "unchanged": 1}, second
    assert [(a.alias, a.language) for a in kube.aliases] == \
        [("kube", "en")] and kube.language == "fr"
    print("ok  R3/R4 an explicit alias language (even equal to the entry's)"
          " survives language changes; re-import is unchanged")


def test_R4_legacy_materialized_languages_migrate_once_to_inherit():
    import sqlite3
    with TempStore() as t:
        eid = t.vs.add_entry("Claude", ["clod"], language="en",
                             approved=True)
        t.store.sync()
        con = sqlite3.connect(t.path)
        # The pre-remediation store: materialized alias language, no
        # migration marker.
        con.execute("UPDATE vocabulary_aliases SET language='en'")
        con.execute("DELETE FROM vocabulary_meta WHERE key LIKE"
                    " 'alias_language_inherit%'")
        con.commit()
        con.close()
        vs2 = type(t.vs)(t.store)          # reopen: runs the migration
        assert [a.language for a in vs2.entry(eid).aliases] == [None]
        assert vs2.migrate_alias_language() == 0   # idempotent
        vs2.update_entry(eid, language="fr")
        assert [a.language for a in vs2.entry(eid).aliases] == [None]
    print("ok  R4 legacy materialized alias languages migrate once to"
          " inherit; the migration is idempotent")


def test_R5_import_refuses_duplicate_aliases_before_any_write():
    with TempStore() as t:
        rev = t.vs.revision()
        for aliases in ([{"alias": "clod"}, {"alias": "clod"}],
                        [{"alias": "Clod"}, {"alias": "clod"}]):
            e = _refused(lambda: _import(t, {"entries": [
                {"entry_id": "x", "canonical": "Claude",
                 "aliases": aliases}]}))
            assert getattr(e, "code", None) == "duplicate_alias", e
        assert t.vs.revision() == rev and t.vs.entries() == []
        assert not [x for x in t.events
                    if x["event"] == "store.write_failed"], t.events
    print("ok  R5 duplicate / case-variant aliases in one import row are"
          " refused up front (content-free, no write, no write_failed)")


def test_R6_a_global_entry_takes_no_scope_value():
    with TempStore() as t:
        a = t.vs.add_entry("Claude", ["clod"], approved=True)
        _refused(lambda: t.vs.add_entry("Claude", ["klod"], approved=True,
                                        scope_value="anything"))
        _refused(lambda: t.vs.add_entry("Cloud", ["clod"], approved=True,
                                        scope_value="x"))
        w = t.vs.add_entry("Wterm", ["w term"], scope_kind="workspace",
                           scope_value="W", approved=True)
        # Moving to global clears the value; the identity is THE global.
        t.vs.update_entry(w, scope_kind="global")
        assert t.vs.entry(w).scope_value is None
        _refused(lambda: _import(t, {"entries": [
            {"entry_id": "x", "canonical": "Zed",
             "scope": ["global", "x"]}]}))
        # Preview and committed snapshot agree on a same-scope clash.
        c = V.VocabularyEntry(entry_id="c", canonical="Cloud",
                              aliases=(V.Alias("clod"),), approved=True,
                              verification="explicit")
        prev = V.preview_entry_conflicts(c, t.vs.entries())
        snap = V.VocabularySnapshot(list(t.vs.entries()) + [c])
    assert any(p["alias"] == "clod" and p["kind"] == "same_scope_mask"
               for p in prev), prev
    assert any(x["alias"] == "clod" for x in snap.conflicts)
    assert a
    print("ok  R6 global entries take no scope value (add, update, import);"
          " preview matches the committed mask")


def test_R7_alias_containers_are_lists_or_tuples():
    with TempStore() as t:
        for bad in ({"clod": False}, {}, {"clod"}, "clod"):
            e = _refused(lambda: t.vs.add_entry("Claude", bad,
                                                approved=True))
            assert getattr(e, "code", None) == "not_a_list", (bad, e)
        z = t.vs.add_entry("Zeta", ["zeeta"], approved=True)
        _refused(lambda: t.vs.update_entry(z, aliases={"zed": False}))
        assert [a.alias for a in t.vs.entry(z).aliases] == ["zeeta"]
        assert t.vs.add_entry("Omega", [], approved=True)
    print("ok  R7 alias containers must be lists/tuples: a mapping never"
          " drops its flags into an approved alias")


def test_R11_orphan_aliases_prove_vanished_entries():
    import sqlite3
    with TempStore() as t:
        keep = t.vs.add_entry("Keep", ["keep"], approved=True)
        gone = t.vs.add_entry("Gone", ["gone"], approved=True)
        t.vs.delete_entry(gone)
        t.store.sync()
        con = sqlite3.connect(t.path)
        # A delete left no orphans; a lost entries+history pair does.
        con.execute("INSERT INTO vocabulary_aliases(entry_id, alias,"
                    " language, approved) VALUES('ghost','boo',NULL,1)")
        con.execute("DELETE FROM vocabulary_history WHERE entry_id='ghost'")
        con.commit()
        con.close()
        rep = t.vs.integrity_report()
        assert rep["vanished_entries"] == 1 and rep["orphan_alias_rows"] == 1
        # An orphan left behind by a recorded delete is not "vanished".
        con = sqlite3.connect(t.path)
        con.execute("INSERT INTO vocabulary_aliases(entry_id, alias,"
                    " language, approved) VALUES(?,'old',NULL,1)", (gone,))
        con.commit()
        con.close()
        rep2 = t.vs.integrity_report()
    assert rep2["vanished_entries"] == 1 and rep2["orphan_alias_rows"] == 2
    assert keep
    print("ok  R11 alias rows of a never-deleted, missing entry count as a"
          " vanished entry (orphans of a recorded delete do not)")


def test_R11_app_refuses_torn_entries_and_history():
    import sqlite3
    import tempfile
    from m05_helpers import helpers
    from localflow.v2 import store as store_mod
    h = helpers()
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        from localflow.v2 import vocabulary_store as VS
        vs = VS.VocabularyStore(st)
        vs.add_entry("Kubectl", ["cube cuddle"], approved=True)
        st.close()
        con = sqlite3.connect(db)
        con.execute("DROP TABLE vocabulary_entries")
        con.execute("DROP TABLE vocabulary_history")
        con.commit()
        con.close()
        a = h.App(td, start_coordinator=False)
        try:
            on = a.d._vocab is not None
        finally:
            a.close()
        con = sqlite3.connect(db)
        seeded = con.execute(
            "SELECT count(*) FROM vocabulary_entries").fetchone()[0]
        con.close()
    assert not on and seeded == 0, (on, seeded)
    print("ok  R11 the app refuses a dictionary whose entries and history"
          " were both lost; nothing is seeded over it")


def test_R12_hint_budget_config_is_strict_and_never_disables():
    import tempfile
    from m05_helpers import helpers
    h = helpers()
    got = {}
    for val in (0, "abc", True, 2.9, "7", 7):
        with tempfile.TemporaryDirectory() as td:
            a = h.App(td, cfg={"hint_term_limit": val},
                      start_coordinator=False)
            try:
                got[repr(val)] = (a.d._vocab is not None,
                                  a.d._hint_selector.max_terms)
            finally:
                a.close()
    assert got == {"0": (True, 100), "'abc'": (True, 100),
                   "True": (True, 100), "2.9": (True, 100),
                   "'7'": (True, 100), "7": (True, 7)}, got
    print("ok  R12 hint_term_limit: a positive integer or the default 100"
          " with its own event; the dictionary stays on")


def test_R16_alias_order_is_deterministic_for_case_variants():
    import sqlite3
    orders = set()
    for rows in ((("Clod",), ("clod",)), (("clod",), ("Clod",))):
        with TempStore() as t:
            eid = t.vs.add_entry("Claude", ["klod"], approved=True)
            t.store.sync()
            con = sqlite3.connect(t.path)
            for (alias,) in rows:          # legacy case-variant rows
                con.execute("INSERT INTO vocabulary_aliases(entry_id,"
                            " alias, language, approved) VALUES(?,?,NULL,1)",
                            (eid, alias))
            con.commit()
            con.close()
            orders.add((tuple(a.alias for a in t.vs.entry(eid).aliases),
                        tuple(a.alias for a in t.vs.entries()[0].aliases)))
    assert orders == {(("Clod", "clod", "klod"),) * 2}, orders
    print("ok  R16 alias order is deterministic (NOCASE, then binary) for"
          " identical content in any insertion order")


def test_Q4_import_omitted_fields_keep_stored_values():
    with TempStore() as t:
        eid = t.vs.add_entry("code-review", ["code review"], kind="skill",
                             pinned=True, priority=3, approved=True)
        res = _import(t, {"entries": [{"entry_id": "x",
                                       "canonical": "code-review",
                                       "aliases": [{"alias": "code review"},
                                                   {"alias": "review it"}]}]})
        e = t.vs.entry(eid)
    assert res["updated"] == 1, res
    assert (e.kind, e.approved, e.pinned, e.priority) == \
        ("skill", True, True, 3), e
    assert sorted(a.alias for a in e.aliases) == ["code review", "review it"]
    print("ok  Q4 an import row's omitted fields keep the stored values"
          " (never de-approved, unpinned or re-kinded by defaults)")


def test_Q5_scope_values_have_one_canonical_form():
    with TempStore() as t:
        t.vs.add_entry("GitHubTerm", ["git hub term"], scope_kind="site",
                       scope_value="https://GitHub.com/", approved=True)
        t.vs.add_entry("PadTerm", ["pad term"], scope_kind="app",
                       scope_value=" com.apple.Terminal ", approved=True)
        t.vs.add_entry("WsTerm", ["ws term"], scope_kind="workspace",
                       scope_value=" Proj ", approved=True)
        # A bundle-id case variant is the SAME identity.
        _refused(lambda: t.vs.add_entry(
            "PadTerm", ["pad term"], scope_kind="app",
            scope_value="COM.APPLE.TERMINAL", approved=True))
        ctx = V.ScopeContext(app_bundle="com.apple.Terminal",
                             site_origin="https://github.com",
                             workspace="Proj")
        snap = t.vs.snapshot(ctx)
        out = run("git hub term pad term ws term", (), snapshot=snap).text
        other = run("ws term", (), snapshot=t.vs.snapshot(
            V.ScopeContext(workspace="proj"))).text
    assert out == "GitHubTerm PadTerm WsTerm", out
    assert other == "ws term", other     # workspace names stay exact
    print("ok  Q5 scope values compare in one canonical form (trimmed;"
          " bundle ids case-insensitive; origins lower-case, no trailing"
          " slash; workspace names exact)")


# ---------------------------------------------------------------------------
# Identity, panel, Hub and failure paths (R13, R14, R15, Q1, Q2, Q3)
# ---------------------------------------------------------------------------

def test_R13_hint_sets_hold_only_immutable_scalars():
    import json
    snap = V.VocabularySnapshot([ent("E-1", "One"), ent("E-2", "Two")])
    sel = V.RelevantVocabularySelector(1)
    hs = sel.select(snap, now_utc="t")
    t0 = hs.terms[0]
    for bad_score in (([1],), ({"a": 1},), (1.5,), (True,)):
        _refused(lambda: V.HintTerm(
            canonical=t0.canonical, entry_id=t0.entry_id,
            scope_kind=t0.scope_kind, scope_value=t0.scope_value,
            source=t0.source, score=bad_score))
    for scope, omitted in (({"workspace": ["w"]}, []),
                           (dict(hs.scope), [{"reason": ["budget_limit"]}])):
        _refused(lambda: V.HintSet(
            hint_set_id=None, selector_revision=hs.selector_revision,
            vocabulary_revision=hs.vocabulary_revision, scope=scope,
            terms=list(hs.terms), omitted=omitted, created_utc="t",
            term_limit=1))
    # The memo is a read-only view: nothing a caller can reach through
    # it changes what select() returns under a trusted id.
    import operator
    _refused(lambda: operator.setitem(
        snap._select_memo, (sel.SELECTOR_REVISION, 1),
        ("m05hs:000000000000", {}, (), ())))
    again = sel.select(snap, now_utc="t")
    assert again.hint_set_id == hs.hint_set_id == V._hint_set_id(
        again.selector_revision, again.vocabulary_revision, again.scope,
        again.terms, again.omitted, again.term_limit)
    assert json.dumps(again.to_json()) == json.dumps(hs.to_json())
    print("ok  R13 hint terms/sets hold only immutable scalars; the"
          " selection memo is not caller-writable")


def test_R14_panel_add_preview_reads_the_store_now():
    with TempStore() as t:
        ctl = panel(t.vs)                 # listing read: empty store
        t.vs.add_entry("Cloud", ["clod"], approved=True)   # elsewhere
        ctl.canonical.v, ctl.alias.v = "Claude", "clod"
        ctl.scope_popup.v = "global"
        ctl.addEntry_(None)
        msg = ctl.sandbox.v
    assert "clod: same_scope_mask" in msg, msg
    print("ok  R14 the add preview reports a contender added since the"
          " panel's last refresh")


def test_R15_hub_preview_has_an_explicit_scope():
    r = __import__("m05_helpers").AppRun("ask clod now")
    try:
        r.d._vocab.add_entry("Claude", ["clod"], scope_kind="app",
                             scope_value="app.A", approved=True)
        r.d._vocab.add_entry("GlobalTerm", ["glob term"], approved=True)
        outs = []
        for bundle in ("app.A", "app.B"):
            r.job(bundle)
            outs.append(r.d.hubPreviewPhrase("ask clod now glob term"))
    finally:
        r.close()
    assert [o["output"] for o in outs] == ["ask clod now GlobalTerm"] * 2, \
        outs
    assert all(o["scope"] == "global only" for o in outs), outs
    print("ok  R15 the Hub preview tests the unscoped default and says so;"
          " the last dictation's destination never leaks into it")


def test_Q1_self_attested_qualification_is_refused():
    import copy
    from localflow.v2 import capabilities as cap
    base = cap.asr_capability_manifest("m", model_revision="rev-A",
                                       runtime={"mlx": "0.1"})

    def selfq(evidence=None, rev=None, model=None):
        m = copy.deepcopy(base)
        if rev is not None:
            m["model_revision"] = rev
        if model is not None:
            m["model_id"] = model
        c = m["capabilities"]["contextual_biasing"]
        c["supported"] = True
        c["qualified_identity"] = {
            "adapter": m["adapter"], "model_id": m["model_id"],
            "model_revision": m["model_revision"], "runtime": m["runtime"]}
        if evidence is not None:
            c["evidence"] = evidence
        return m
    assert not cap.biasing_qualified(selfq())          # baseline text
    assert not cap.biasing_qualified(selfq(".", rev=" "))
    assert not cap.biasing_qualified(selfq(" . ", rev="rev-A"))
    assert not cap.biasing_qualified(selfq("record", model=" "))
    assert cap.biasing_qualified(selfq("qualification run 2026-09"))
    print("ok  Q1 baseline 'no qualified implementation' evidence, blank"
          " checkpoints/models and content-free evidence never qualify")


def test_Q2_failed_read_never_resurrects_a_disabled_rule():
    r = __import__("m05_helpers").AppRun("ask clod now")
    try:
        eid = r.d._vocab.add_entry("Claude", ["clod"], approved=True)
        first = r.job("app.X")["text"]
        r.d._vocab.set_enabled(eid, False)       # this process's write
        real = r.d._vocab.revision

        def boom():
            raise RuntimeError("injected revision read failure")
        r.d._vocab.revision = boom
        second = r.job("app.X")["text"]
        r.d._vocab.revision = real
        usage = r.d._vocab.entry(eid).usage_count
        outcomes = [e.get("outcome") for e in r.events
                    if e["event"] == "vocabulary.refresh_failed"]
    finally:
        r.close()
    assert first == "ask Claude now" and second == "ask clod now", \
        (first, second)
    assert usage == 1, usage
    assert "vocabulary_off_stale_last_good" in outcomes, outcomes
    print("ok  Q2 a failed read never rescopes from a last-good set this"
          " process has since superseded (no resurrected rule, no hit)")


def test_Q3_panel_actions_bind_to_what_the_user_selected():
    with TempStore() as t:
        b = t.vs.add_entry("Beta", ["beeta"], approved=False)
        ctl = panel(t.vs)
        ctl.phrase.v = "1"
        ctl.runSandbox_(None)             # the user sees Beta (beeta)
        t.vs.update_entry(b, aliases=[("beeta", False),
                                      ("bay tah", False)])  # elsewhere
        ctl.approveEntry_(None)
        first = (t.vs.entry(b).approved, ctl.sandbox.v)
        ctl.approveEntry_(None)           # second press: after review
        second = t.vs.entry(b).approved
        text = run("say bay tah", (), snapshot=t.vs.snapshot()).text
        # The panel's own write does not invalidate its selection.
        ctl.pinEntry_(None)
        ctl.toggleEntry_(None)
        e = t.vs.entry(b)
    assert first[0] is False and "changed since you selected" in first[1]
    assert second is True and text == "say Beta"
    assert e.pinned and not e.enabled
    print("ok  Q3 panel actions compare-and-swap against the revision the"
          " user selected; a change made elsewhere waits for a fresh look")


# ---------------------------------------------------------------------------
# R8 — witnesses for mutations that survived every first-pass tool
# ---------------------------------------------------------------------------

def test_R8_score_is_part_of_hint_identity():
    snap = V.VocabularySnapshot([ent("E-1", "One"), ent("E-2", "Two")])
    hs = V.RelevantVocabularySelector(5).select(snap, now_utc="t")
    forged = [V.HintTerm(canonical=t.canonical, entry_id=t.entry_id,
                         scope_kind=t.scope_kind, scope_value=t.scope_value,
                         source=t.source, score=(9, 9, "9", 9, 9))
              for t in hs.terms]
    _refused(lambda: V.HintSet(
        hint_set_id=hs.hint_set_id, selector_revision=hs.selector_revision,
        vocabulary_revision=hs.vocabulary_revision, scope=dict(hs.scope),
        terms=forged, omitted=[dict(o) for o in hs.omitted],
        created_utc="t", term_limit=hs.term_limit))
    print("ok  R8 a forged score under the same hint_set_id is refused")


def test_R8_snapshot_revision_encodes_its_scope():
    ents = [ent("E-W", "WsTerm", ["wuss"], scope_kind="workspace",
                scope_value="A"), ent("E-G", "Glob", ["glob"])]
    ra = V.VocabularySnapshot(ents, V.ScopeContext(workspace="A")).revision
    rb = V.VocabularySnapshot(ents, V.ScopeContext(workspace="B")).revision
    rg = V.VocabularySnapshot(ents, None).revision
    assert len({ra, rb, rg}) == 3, (ra, rb, rg)
    print("ok  R8 the snapshot revision encodes the scope it was filtered"
          " for")


def test_R8_sandbox_reports_a_would_be_masked_suggestion():
    out = V.sandbox_phrase("use clod code", V.VocabularySnapshot(
        [ent("E-U", "Claude Code", ["clod code"], approved=False),
         ent("E-A", "Cloud Code", ["clod code"])]))
    m = [x for x in out["suggestions"] if x["entry_id"] == "E-U"]
    assert m and all(x.get("masked") for x in m), out["suggestions"]
    assert out["output"] == "use Cloud Code", out["output"]
    print("ok  R8 the sandbox reports a suggestion an active contender"
          " would mask")


def test_R8_applied_rule_manifest_holds_only_applied_rules():
    import json
    import tempfile
    import test_m05_remediation as T
    from m05_helpers import ContextSnapshot, NormalizationPolicy, normalize
    from localflow.v2 import vocabulary_store as VS
    with tempfile.TemporaryDirectory() as td:
        st, col, events, ctx, job = T._collector(td)
        vs = VS.VocabularyStore(st)
        a = vs.add_entry("Zeta", ["zeeta"], approved=True)
        for i in range(3):
            vs.add_entry(f"Pin{i}", [], pinned=True, approved=True)
        snap = vs.snapshot(None)
        col.on_asr_result(ctx, "say zeeta", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        cctx = ContextSnapshot(vocabulary=snap)
        r = normalize("say zeeta", NormalizationPolicy(), cctx)
        col.on_normalization_result(ctx, r, source_text="say zeeta",
                                    policy=NormalizationPolicy(),
                                    context=cctx)
        col.on_cleanup_result(ctx, r.text)
        env = st.latest_revision(col.finalize(ctx))
        vb = env["normalization"]["vocabulary"]
        rules = json.loads(st.artifact_payload(
            vb["applied_rules_artifact"]))["rules"]
        st.close()
    assert [x["entry_id"] for x in rules] == [a], rules
    print("ok  R8 the applied-rule manifest holds exactly the applied"
          " rules, never the dictionary")


def test_R9_selection_identity_fast_path_equals_generic():
    # The selector hashes cached per-entry omission fragments; the id
    # must equal the generic (checked-constructor) encoding exactly,
    # including non-ASCII and quoted canonicals, and repeat selections
    # over the same frozen entries must reuse the same records.
    ents = [ent(f"E{i}", c) for i, c in enumerate(
        ["Éclair", 'Quo"te', "日本語", "Plain", "Back\\slash"])]
    for lim in (1, 2, 4, 5):
        a = V.RelevantVocabularySelector(lim).select(
            V.VocabularySnapshot(ents), now_utc="t")
        assert a.hint_set_id == V._hint_set_id(
            a.selector_revision, a.vocabulary_revision, a.scope, a.terms,
            a.omitted, a.term_limit), lim
        b = V.RelevantVocabularySelector(lim).select(
            V.VocabularySnapshot(ents), now_utc="t")
        assert b.hint_set_id == a.hint_set_id
        assert all(x is y for x, y in zip(a.omitted, b.omitted))
    print("ok  R9 the selector's fast identity equals the generic encoding;"
          " omission records are reused across fresh snapshots")


def test_R10_a_crashed_control_is_never_green():
    import importlib.util
    import json
    import subprocess
    import tempfile
    import m05_helpers
    root = m05_helpers.ROOT          # the code root under test
    spec = importlib.util.spec_from_file_location(
        "m05_mut", root / "scripts" / "v2" / "m05_mutation_check.py")
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    real = subprocess.run

    def fake(cmd, *a, **kw):
        # git and the apply-only check succeed; every tool run crashes
        # before writing a result.
        if cmd and cmd[0] == "git" or (len(cmd) > 2 and "runpy" not in
                                       cmd[2]):
            return real(cmd, *a, **kw)
        return subprocess.CompletedProcess(cmd, 1, stdout="",
                                           stderr="ImportError: boom")
    mc.subprocess.run = fake
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "m.json"
        import sys as _sys
        argv = _sys.argv
        _sys.argv = ["m05_mutation_check.py", "--output", str(out),
                     "--only", "control_unmodified,identity_matcher"]
        try:
            rc = mc.main()
        finally:
            _sys.argv = argv
            mc.subprocess.run = real
        rep = json.loads(out.read_text())
    assert rc != 0 and rep["control_green"] is False, rep["control_green"]
    ctl = rep["mutations"]["control_unmodified"]["tools"]["corpus"]
    assert ctl["complete"] is False and ctl["killed"] is True, ctl
    print("ok  R10 a crashed control (no result file, non-zero exit) is"
          " never reported green")


# ---------------------------------------------------------------------------
# A1 — the panel tells the user how selection actually works
# ---------------------------------------------------------------------------

def test_A1_panel_listing_describes_the_real_selection_method():
    # The listing said "click a line to select", but the listing is a
    # read-only text field: selection is the entry's line number typed
    # into Test phrase (a stable entry id from then on, AUDIT-08).
    with TempStore() as t:
        t.vs.add_entry("Parakeet", [], approved=True)
        ctl = panel(t.vs)
        header = ctl.listing.v.splitlines()[0]
        ctl.phrase.v = "1"
        ctl.runSandbox_(None)
        selected = ctl.sandbox.v
    assert "click a line" not in header, header
    assert "line number" in header and "Test" in header, header
    assert selected.startswith("selected: Parakeet"), selected
    print("ok  A1 panel listing names the real selection method (line"
          " number in Test phrase)")


# ---------------------------------------------------------------------------
# A2 — a disposition never contradicts itself
# ---------------------------------------------------------------------------

def _hint_set(n=2):
    ents = [V.VocabularyEntry(entry_id=f"E{i}", canonical=f"Term{i}",
                              approved=True, verification="explicit")
            for i in range(n)]
    return V.RelevantVocabularySelector().select(V.VocabularySnapshot(ents))


def test_A2_qualified_disposition_is_not_ignored_with_a_reason():
    from localflow.v2 import capabilities as caps
    hs = _hint_set()
    unq = caps.hint_disposition(None, hs)
    assert unq["ignored"] is True and unq["offered_terms"] == 2
    assert unq["ignored_reason"] == "disabled_until_qualified"
    assert unq["accepted_terms"] == 0
    manifest = caps.asr_capability_manifest(
        "qualified-adapter", model_revision="synthetic-rev",
        runtime={"runtime": "synthetic"})
    manifest["capabilities"]["contextual_biasing"] = {
        "supported": True, "reason": "synthetic_test",
        "evidence": "synthetic qualification record",
        "qualified_identity": {
            "adapter": manifest["adapter"],
            "model_id": "qualified-adapter",
            "model_revision": "synthetic-rev",
            "runtime": {"runtime": "synthetic"}}}
    assert caps.biasing_qualified(manifest)
    q = caps.hint_disposition(manifest, hs)
    assert q["offered_terms"] == 2 and q["ignored"] is False, q
    # Not ignored → no ignored reason; acceptance is the adapter's to
    # report after decoding, never a fabricated zero.
    assert q["ignored_reason"] is None, q
    assert q["accepted_terms"] is None, q
    none = caps.hint_disposition(manifest, None)
    assert none["offered_terms"] == 0 and none["ignored"] is False
    assert none["ignored_reason"] is None
    print("ok  A2 hint disposition: unqualified → ignored"
          " (disabled_until_qualified); qualified → not ignored, no reason,"
          " acceptance not fabricated")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}"[:700])
    import os
    sys.stdout.flush()
    if failed:
        print(f"{failed} of {len(tests)} M05 review-round tests FAILED")
        os._exit(1)
    print(f"all {len(tests)} M05 review-round tests passed")
    os._exit(0)


if __name__ == "__main__":
    main()
