"""M05 remediation regressions at the APP seams (declared non-native shims).

Drives the REAL ``AppDelegate`` — hotkey-down identity → the M05 trio
(``_vocab_job_state``) → release/M06 finalize (``_finalize_job_context``)
→ M10 finalize → coordinator normalization → cleanup inputs — with a
scripted M06 context service and a scripted supervisor, plus the real
Dictionary panel controller logic with recorded stand-in fields. AppKit,
PyObjC, Quartz and sounddevice are the DECLARED shims of
tests/v2/lifecycle/native_shims.py: every pass is portable orchestration
evidence, never native AppKit/Accessibility/microphone/model evidence
(VERIFICATION.html M05 keeps those pending).

Each test fails on the audited base 267d1c2 (see
docs/v2/acceptance/M05/remediation/) and pairs the unsafe case with its
intended-use positive.

Run: .venv/bin/python tests/v2/vocabulary/test_m05_remediation_app.py
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m05_helpers import (  # noqa: E402
    AppRun,
    TempStore,
    V,
    helpers,
    normalize,
    panel,
)


def _fault_revision(d):
    real = d._vocab.revision

    def boom():
        raise RuntimeError("injected revision read failure")
    d._vocab.revision = boom
    return lambda: setattr(d._vocab, "revision", real)


# ---------------------------------------------------------------------------
# 02 — failure paths never grant another job's scope
# ---------------------------------------------------------------------------

def test_02_refresh_failure_never_reuses_another_apps_dictionary():
    r = AppRun("ask clod now")
    try:
        v = r.d._vocab
        v.add_entry("Claude", ["clod"], scope_kind="app",
                    scope_value="app.A", approved=True)
        v.add_entry("code-review", ["code review"], kind="skill",
                    scope_kind="app", scope_value="app.A", approved=True)
        v.add_entry("GlobalTerm", ["glob term"], approved=True)
        a = r.job("app.A")
        assert a["text"] == "ask Claude now", a["text"]       # warm cache
        restore = _fault_revision(r.d)
        b = r.job("app.B")
        # Matched positive: the SAME app after a refresh failure keeps
        # its own valid scope (rebuilt from the last good entry set).
        a2 = r.job("app.A")
        restore()
    finally:
        r.close()
    assert b["finished"] and b["text"] == "ask clod now", b["text"]
    assert not any(p[0] == "clod" for p in b["pairs"]), b["pairs"]
    assert ("glob term", "GlobalTerm") in b["pairs"], \
        "B keeps the globally valid vocabulary"
    skills = dict(b["job"]["norm_policy"].registered_skills)
    assert "code review" not in skills, skills
    hs = b["job"].get("hint_set")
    assert hs is None or all(t.canonical != "Claude" for t in hs.terms)
    assert "Claude" not in b["relevant"], b["relevant"]
    assert a2["text"] == "ask Claude now", a2["text"]
    outcomes = [e.get("outcome") for e in r.events
                if e["event"] == "vocabulary.refresh_failed"]
    assert outcomes and "last_good_state" not in outcomes, outcomes
    print("ok  02 refresh failure: job B never gets app A's rule, skill,"
          " hint or cleanup pair; app A itself stays correct")


def test_02_refresh_failure_on_cold_start_degrades_honestly():
    r = AppRun("ask clod now")
    try:
        r.d._vocab.add_entry("Claude", ["clod"], approved=True)
        restore = _fault_revision(r.d)
        j = r.job("app.A")
        restore()
    finally:
        r.close()
    assert j["finished"] and j["text"] == "ask clod now", j["text"]
    assert not j["pairs"]
    outcomes = [e.get("outcome") for e in r.events
                if e["event"] == "vocabulary.refresh_failed"]
    assert "vocabulary_off" in outcomes, outcomes
    print("ok  02 cold-start refresh failure: dictation delivered,"
          " vocabulary off with a precise outcome")


def test_02_selector_failure_does_not_block_the_scope_upgrade():
    r = AppRun("ask clod now")
    try:
        v = r.d._vocab
        v.add_entry("GlobalName", ["clod"], approved=True)
        v.add_entry("WorkspaceName", ["clod"], scope_kind="workspace",
                    scope_value="wsx", approved=True)
        ctl = r.job("app.C", workspace="wsx")

        def boom(*a, **k):
            raise RuntimeError("injected selector failure")
        real = r.d._hint_selector.select
        r.d._hint_selector.select = boom
        j = r.job("app.C", workspace="wsx")
        r.d._hint_selector.select = real
        k = r.job("app.C")
    finally:
        r.close()
    assert ctl["text"] == "ask WorkspaceName now"
    assert j["text"] == "ask WorkspaceName now", j["text"]
    assert ("clod", "WorkspaceName") in j["pairs"], j["pairs"]
    assert j["job"].get("hint_set") is None
    assert j["job"].get("scope_upgraded") is True
    assert k["text"] == "ask GlobalName now", k["text"]
    print("ok  02 selector failure: the frozen-entry scope upgrade still"
          " runs; only the optional hint set is absent")


def test_02b_capture_failure_fallback_is_unscoped():
    r = AppRun("ask clod now glob term")
    try:
        v = r.d._vocab
        v.add_entry("Claude", ["clod"], scope_kind="app",
                    scope_value="app.A", approved=True)
        v.add_entry("GlobalTerm", ["glob term"], approved=True)
        a = r.job("app.A")
        real = r.d._m10_freeze

        def boom(*a, **k):
            raise RuntimeError("injected hotkey-down capture failure")
        r.d._m10_freeze = boom
        b = r.job("app.B")
        r.d._m10_freeze = real
    finally:
        r.close()
    assert a["text"] == "ask Claude now GlobalTerm", a["text"]
    assert b["finished"] and b["text"] == "ask clod now GlobalTerm", \
        b["text"]
    assert b["job"].get("norm_source", "current_default") == \
        "current_default"
    print("ok  02b a job whose capture failed runs on the unscoped"
          " default, never the previous job's cached context")


def test_02_workspace_alternation_with_a_mid_failure():
    r = AppRun("clod")
    try:
        v = r.d._vocab
        v.add_entry("GlobalName", ["clod"], approved=True)
        v.add_entry("XName", ["clod"], scope_kind="workspace",
                    scope_value="X", approved=True)
        v.add_entry("YName", ["clod"], scope_kind="workspace",
                    scope_value="Y", approved=True)
        v.add_entry("AppOnly", ["clod"], scope_kind="app",
                    scope_value="app.one", approved=True)
        got = [r.job("app.one", workspace="X")["text"]]
        restore = _fault_revision(r.d)
        got.append(r.job("app.two", workspace="Y")["text"])
        got.append(r.job("app.two")["text"])
        restore()
        got.append(r.job("app.one")["text"])
    finally:
        r.close()
    assert got == ["XName", "YName", "GlobalName", "AppOnly"], got
    print("ok  02 workspace/app alternation across a refresh failure:"
          " every job chooses only its own scope winner")


# ---------------------------------------------------------------------------
# 08 — panel actions address a stable entry identity
# ---------------------------------------------------------------------------

def _select_beta(ctl):
    ctl.search.v = "beta"
    ctl.searchChanged_(None)
    ctl.phrase.v = "1"
    ctl.runSandbox_(None)


def test_08_panel_selection_is_a_stable_entry_id():
    for variant in ("clear_filter", "insert_before", "rename_before",
                    "delete_selected", "changed_since_selection"):
        with TempStore() as t:
            t.vs.add_entry("Alpha", ["alfa"], approved=False)
            b = t.vs.add_entry("Beta", ["beeta"], approved=False)
            ctl = panel(t.vs)
            _select_beta(ctl)
            ctl.search.v = ""
            if variant == "clear_filter":
                ctl.searchChanged_(None)
            elif variant == "insert_before":
                t.vs.add_entry("Aardvark", ["ardvark"], approved=False)
                ctl.refresh()
            elif variant == "rename_before":
                alpha = next(e for e in t.vs.entries()
                             if e.canonical == "Alpha")
                t.vs.update_entry(alpha.entry_id, canonical="Beetle")
                ctl.refresh()
            elif variant == "delete_selected":
                t.vs.delete_entry(b)
                ctl.refresh()
            else:
                t.vs.update_entry(b, aliases=[("beeta", False),
                                              ("beta two", False)])
            ctl.approveEntry_(None)
            approved = sorted(e.canonical for e in t.vs.entries()
                              if e.approved)
            msg = ctl.sandbox.v
        if variant == "delete_selected":
            assert approved == [], (variant, approved)
            assert "no longer" in msg or "select" in msg, msg
        else:
            assert approved == ["Beta"], (variant, approved, msg)
    # Toggle/pin/delete also act on the selected id.
    with TempStore() as t:
        a = t.vs.add_entry("Alpha", ["alfa"], approved=True)
        b = t.vs.add_entry("Beta", ["beeta"], approved=True)
        ctl = panel(t.vs)
        _select_beta(ctl)
        ctl.search.v = ""
        ctl.searchChanged_(None)
        ctl.pinEntry_(None)
        ctl.toggleEntry_(None)
        assert t.vs.entry(b).pinned and not t.vs.entry(b).enabled
        assert not t.vs.entry(a).pinned and t.vs.entry(a).enabled
        ctl.deleteEntry_(None)
        assert t.vs.entry(b) is None and t.vs.entry(a) is not None
    print("ok  08 panel: approve/pin/toggle/delete act on the selected"
          " entry id across filter, insert, rename, delete and edits")


# ---------------------------------------------------------------------------
# 09 — the app path keeps dictionary skill provenance and counts its use
# ---------------------------------------------------------------------------

def test_09_app_skill_provenance_and_hits():
    r = AppRun("slash code review")
    try:
        d = r.d
        d.consent.set("enabled", note="m05 remediation test")
        eid = d._vocab.add_entry("code-review", ["code review"],
                                 kind="skill", approved=True)
        j = r.job("app.X")
        d.store.sync()
        env = d.store.latest_revision(d.store.latest_example()[0])
        e = d._vocab.entry(eid)
    finally:
        r.close()
    assert j["text"] == "/code-review", j["text"]
    vb = env["normalization"]["vocabulary"]
    assert vb["applied_skill_rule_ids"] == [eid], vb
    assert e.usage_count == 1, "an applied dictionary skill is a hit"
    print("ok  09 live path: /code-review carries its approving entry in"
          " evidence and records one usage hit")


# ---------------------------------------------------------------------------
# 13 — panel sandbox tests an explicit, labeled scope
# ---------------------------------------------------------------------------

def test_13_panel_sandbox_scope_is_explicit():
    with TempStore() as t:
        t.vs.add_entry("GlobalName", ["clod"], approved=True)
        t.vs.add_entry("WorkspaceName", ["clod"], scope_kind="workspace",
                       scope_value="X", approved=True)
        ctl = panel(t.vs)
        ctl.phrase.v = "ask clod now"
        ctl.runSandbox_(None)
        glob = ctl.sandbox.v
        ctl.scope_popup.v = "workspace"
        ctl.scope_value.v = "X"
        ctl.runSandbox_(None)
        ws = ctl.sandbox.v
        before = [(e.usage_count, e.revision) for e in t.vs.entries()]
    assert glob.splitlines()[0] == "→ ask GlobalName now", glob
    assert "scope: global" in glob, glob
    assert ws.splitlines()[0] == "→ ask WorkspaceName now", ws
    assert "workspace=X" in ws, ws
    assert all(u == 0 for u, _ in before)
    print("ok  13 panel sandbox: tests the chosen scope and says which")


# ---------------------------------------------------------------------------
# 18 — a torn entries table never boots as a healthy empty dictionary
# ---------------------------------------------------------------------------

def test_18_app_refuses_a_torn_dictionary():
    h = helpers()
    from localflow.v2 import store as store_mod
    from localflow.v2 import vocabulary_store as VS
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        st = store_mod.Store(db)
        vs = VS.VocabularyStore(st)
        vs.add_entry("Claude", ["clod"], approved=True)
        st.close()
        con = sqlite3.connect(db)
        con.execute("DROP TABLE vocabulary_entries")
        con.commit()
        con.close()
        events = []
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            vocab_off = d._vocab is None
            con = sqlite3.connect(db)
            orphans = con.execute("SELECT count(*) FROM"
                                  " vocabulary_aliases").fetchone()[0]
            seeded = con.execute("SELECT count(*) FROM"
                                 " vocabulary_entries").fetchone()[0]
            con.close()
            log = pathlib.Path(td) / "ev"
            blob = "".join(p.read_text() for p in log.rglob("*")
                           if p.is_file())
        finally:
            a.close()
    assert vocab_off, "a torn dictionary must not run as a healthy one"
    assert orphans == 1 and seeded == 0, \
        "surviving rows untouched, nothing seeded over the torn state"
    assert "vocabulary.integrity_failed" in blob, blob[-2000:]
    assert "clod" not in blob and "Claude" not in blob
    print("ok  18 app start: vanished entries → vocabulary off with a"
          " content-free integrity event; survivors untouched, no seeding")


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
    import sys as _s
    _s.stdout.flush()
    if failed:
        print(f"{failed} of {len(tests)} M05 app-seam tests FAILED")
        os._exit(1)
    print(f"all {len(tests)} M05 app-seam tests passed")
    os._exit(0)


if __name__ == "__main__":
    main()
