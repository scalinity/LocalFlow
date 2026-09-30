"""Owner's September 29 POLICY-D03 editable-click regressions.

Run through context/run_isolated.py; every insertion uses the M08 world.
The resolver seam represents the actual AX hit, never the focused field.
"""
from types import SimpleNamespace

from test_xm_paste_again import Env, CASES, case, main

# Keep this suite's ledger separate from the existing 15 cases.
CASES.clear()


def hit(e, app="A", fid="F2"):
    el = e.w.focused_element_for(e.w.apps[app]["pid"])
    # The caller focuses fid before resolving the synthetic click.
    return SimpleNamespace(pid=e.w.apps[app]["pid"], element=el,
                           window=e.w.attribute(el, "AXWindow"))


def refusal(kind, indirect_focus=False):
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.w.focus("A", "F1")  # old field remains focused
        e.picker.resolve = lambda pid, point: None  # non-editable AX hit
        e.invoke(jid, text, aid)
        since = e.stamp()
        if indirect_focus:
            e.w.focus("A", "F2")
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert not e.writes(since), (kind, "old focus reused", e.writes(since))
        assert e.picker.active, (kind, "non-editable click ended picker")
        assert not e.ended, (kind, "authority delivered", e.ended)
    finally:
        e.close()


@case("PA-EDIT-01 titlebar refusal with previously focused field")
def pa_edit_01_titlebar():
    refusal("titlebar")


@case("PA-EDIT-02 editable click grants one fresh validated insertion")
def pa_edit_02_editable():
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.w.focus("A", "F2")
        e.picker.resolve = lambda pid, point: hit(e)
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert len(e.writes(since, ("F2",))) == 1
        assert not e.writes(since, ("F1", "FB"))
        assert e.w.text("F2").startswith(text)
        assert e.ended == ["repaste_queued"] and not e.picker.active
    finally:
        e.close()


@case("PA-EDIT-03 static/background refusal")
def pa_edit_03_static_background():
    refusal("static/background")


@case("PA-EDIT-04 button/toolbar refusal")
def pa_edit_04_button_toolbar():
    refusal("button/toolbar")


@case("PA-EDIT-05 indirect/stale focus cannot repair non-editable hit")
def pa_edit_05_stale_focus():
    refusal("stale focus", indirect_focus=True)


@case("PA-EDIT-06 unsupported AX semantics abstain")
def pa_edit_06_unsupported():
    refusal("unsupported AX semantics")


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
