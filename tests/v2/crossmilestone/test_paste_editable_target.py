"""Owner's September 29 POLICY-D03 editable-click regressions.

Run through context/run_isolated.py; every insertion uses the M08 world.
The resolver seam represents the actual AX hit, never the focused field.
"""
from types import SimpleNamespace

from test_xm_paste_again import Env, CASES, case, main

# Keep this suite's ledger separate from the existing 15 cases.
CASES.clear()


def hit(e, app="A"):
    el = e.w.focused_element_for(e.w.apps[app]["pid"])
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


@case("PA-EDIT-07 same-app field change at M08 admission refuses")
def pa_edit_07_changed_field():
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.w.focus("A", "F2")
        e.picker.resolve = lambda pid, point: hit(e)
        real = e.a.svc.paste_text
        def moved(*args, **kwargs):
            e.w.focus("A", "F1")
            return real(*args, **kwargs)
        e.a.svc.paste_text = moved
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert not e.writes(since), e.writes(since)
    finally:
        e.close()


@case("PA-EDIT-08 target invalidated while click settles refuses")
def pa_edit_08_invalid_during_settle():
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.w.focus("A", "F2")
        e.picker.resolve = lambda pid, point: hit(e)
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.w.fields["F2"].settable = False
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert not e.writes(since), e.writes(since)
        assert e.ended == ["editable_destination_changed"], e.ended
    finally:
        e.close()


@case("PA-EDIT-09 non-editable click then editable click inserts once")
def pa_edit_09_retry_after_noneditable():
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        e.w.focus("A", "F1")
        since = e.stamp()
        e.picker.resolve = lambda pid, point: None
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        assert e.picker.active and e.monitors == ["on"]
        e.w.focus("A", "F2")
        e.picker.resolve = lambda pid, point: hit(e)
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert len(e.writes(since, ("F2",))) == 1
        assert not e.writes(since, ("F1", "FB"))
        assert e.monitors == ["on", "off"]
    finally:
        e.close()


@case("PA-EDIT-10 timeout during click settling revokes authority")
def pa_edit_10_timeout_while_settling():
    e = Env()
    try:
        jid, text, aid = e.dictation()
        e.w.focus("A", "F2")
        e.picker.resolve = lambda pid, point: hit(e)
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.picker.mouse_down(e.w.apps["A"]["pid"])
        e.sched.run(e.pp.PICK_TIMEOUT_SEC)
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert not e.writes(since) and e.ended == ["timed_out"]
        assert not e.picker.active and e.monitors == ["on", "off"]
    finally:
        e.close()


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
