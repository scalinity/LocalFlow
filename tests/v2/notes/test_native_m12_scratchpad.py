"""NATIVE functional qualification of the Scratchpad (M12 remediation,
corpus N001–N012 and S022's native half) — real AppKit/PyObjC, the real
HubController and ScratchpadEditor over a synthetic temporary store, the
real coordinator (the lifecycle Harness).

Ownership and safety: this process owns the windows it drives, placed
off-screen; every event is BUILT for its own window and DELIVERED
through this application's own dispatch (M10's ``Driver``: nothing is
posted to the system event stream). Under ``run_isolated`` the general
pasteboard is a private one. No real note, attachment, History row or
clipboard content is read or written.

Two tiers (M10's). PASSIVE (default): the app is never activated and
the frontmost application is checked unchanged after every case.
ACTIVE (``--activate``, only with the owner's go-ahead, hands off the
keyboard and mouse): run as a launched app by
``scripts/v2/native_m12_active.py`` — key equivalents, popups, buttons
and the real key-window PTT binding need an active app. The previously
frontmost application is re-activated at the end.

The editor's autosave is proven by running the ORDINARY run loop; the
test never calls ``autosave_tick``. Programmatic ``setString_`` is used
for fixtures only; the behaviour under test is driven by events.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/notes/test_native_m12_scratchpad.py [--json OUT] [-k NAME]
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "ui"))

from test_native_m10_panes import (APP, ACTIVE, LAUNCHED, Driver,  # noqa
                                   frontmost_pid, pump)
import m12_world as w  # noqa: E402

from AppKit import (NSEventModifierFlagControl,  # noqa: E402
                    NSEventModifierFlagShift, NSEventTypeKeyDown,
                    NSEventTypeKeyUp, NSMakePoint, NSMakeSize, NSEvent,
                    NSFont, NSPanel, NSMakeRect, NSTimer, NSButton,
                    NSPopUpButton)
from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop  # noqa: E402

from localflow.v2.notes import ORIGIN_DICTATED  # noqa: E402

CASES = []


def case(corpus_id, tier="passive"):
    def deco(fn):
        fn.tier = tier
        fn.corpus_id = corpus_id
        CASES.append(fn)
        return fn
    return deco


class KeyDriver(Driver):
    """M10's driver plus modifier keys (shift/control) and arrows."""

    def key_mod(self, chars, code, flags):
        for t in (NSEventTypeKeyDown, NSEventTypeKeyUp):
            APP.sendEvent_(self._key(t, chars, code, flags))
            self.sent["key"] += 1
        pump()

    def arrow(self, direction, shift=False, times=1):
        code, ch = {"left": (123, ""), "right": (124, ""),
                    "down": (125, ""), "up": (126, "")}[direction]
        flags = NSEventModifierFlagShift if shift else 0
        for _ in range(times):
            self.key_mod(ch, code, flags | (1 << 23))  # function-key flag


class NativeWorld:
    def __init__(self, active=False, consent=False):
        self.active = active
        restore = os.environ.get("LF_NATIVE_RESTORE_PID", "")
        self.front = int(restore) if active and restore.isdigit() \
            else frontmost_pid()
        self.hw = w.HubWorld(consent=consent, durations=(1.0,) * 8)
        self.hub, self.h, self.d = self.hw.hub, self.hw.h, self.hw.d
        self.win = self.hub.window
        self.win.setFrameOrigin_(NSMakePoint(-20000, -20000))
        if active:
            APP.activateIgnoringOtherApps_(True)
            self.win.makeKeyAndOrderFront_(None)
            deadline = time.monotonic() + (8.0 if LAUNCHED else 3.0)
            while not (APP.isActive() and self.win.isKeyWindow()) \
                    and time.monotonic() < deadline:
                pump(0.05)
            if not self.win.isKeyWindow():
                key = APP.keyWindow()
                print(f"[diag] active={bool(APP.isActive())}"
                      f" key_window={type(key).__name__ if key else None}"
                      f" visible_windows={sum(1 for x in APP.windows() if x.isVisible())}"
                      f" front_is_self={frontmost_pid() == os.getpid()}",
                      flush=True)
            assert self.win.isKeyWindow(), "the owned window is not key"
        else:
            self.win.orderFrontRegardless()
        pump()
        self.k = KeyDriver(self.win)

    def drain(self):
        self.hw.drain()

    def note(self, text):
        n = self.hw.notes.create_note(text)["note_id"]
        self.hw.open_note(n)
        return n

    def run_loop(self, seconds):
        """The ORDINARY default-mode run loop, as the app's own."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            NSRunLoop.currentRunLoop().runMode_beforeDate_(
                NSDefaultRunLoopMode,
                NSDate.dateWithTimeIntervalSinceNow_(0.05))

    def close(self):
        was_active = bool(APP.isActive())
        try:
            self.win.orderOut_(None)
        finally:
            self.hw.close()
        if self.active:
            return      # focus is handed back once, after the run
        assert not was_active, "the test app became active"
        assert frontmost_pid() == self.front, \
            "the frontmost application changed"


def _latest(hw, n):
    row = hw.store.submit(lambda db: db.execute(
        "SELECT r.content_text, r.trigger_kind, r.origin FROM notes x"
        " JOIN note_revisions r ON r.revision_id = x.current_revision_id"
        " WHERE x.note_id=?", (n,)).fetchone())
    return row


def actions(hub):
    pane = hub._built_views["scratchpad"]
    return {str(v.title()): v for v in pane.subviews()  # not popups
            if isinstance(v, NSButton) and v.action()
            and not isinstance(v, NSPopUpButton)}


# ---------------------------------------------------------------------------
# PASSIVE tier
# ---------------------------------------------------------------------------

@case("LF-M12-N009")
def n09_every_control_reachable_at_default_minimum_and_large_font():
    from localflow.v2.ui import hub as hub_mod
    nw = NativeWorld()
    try:
        hub = nw.hub
        nw.note("geometry note")
        misses = []
        for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
            nw.win.setContentSize_(NSMakeSize(*size))
            pump()
            controls = dict(actions(hub))
            controls.update({"editor": hub.editor.text,
                             "search": hub.scratchpad_search,
                             "versions": hub.scratchpad_versions,
                             "transforms": hub.scratchpad_transforms,
                             "list": hub.scratchpad_table})
            misses += [(size, n) for n, v in controls.items()
                       if not nw.k.hit(v)]
        # Enlarged control text (the system text-scale setting is not
        # changeable from automation): larger fonts keep every action
        # inside the pane and hittable at the minimum size.
        for b in actions(hub).values():
            b.setFont_(NSFont.systemFontOfSize_(
                NSFont.systemFontSize() * 1.5))
        pump()
        misses += [("large-font", n) for n, v in actions(hub).items()
                   if not nw.k.hit(v)]
        assert not misses, f"unreachable: {misses}"
        assert len(actions(hub)) == 9, sorted(actions(hub))
    finally:
        nw.close()


@case("LF-M12-N001", "active")
def n01_click_type_and_ordinary_loop_autosave():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        n = nw.note("native base")
        nw.k.click(hub.editor.text, nw.k.centre(hub.editor.text))
        assert nw.win.firstResponder() is hub.editor.text, \
            "a click did not focus the editor"
        hub.editor.text.setSelectedRange_((len("native base"), 0))
        nw.k.type(" typed")
        assert str(hub.editor.current_content()) == "native base typed", \
            str(hub.editor.current_content())
        calls = {"tick": 0}
        real = hub.editor.autosave_tick

        def counting():
            calls["tick"] += 1
            return real()
        hub.editor.autosave_tick = counting
        nw.run_loop(3.0)                  # debounce 1.5 s + 0.5 s ticks
        hub.editor.drain()
        got = _latest(nw.hw, n)
        assert calls["tick"] >= 1, "the installed timer never fired"
        assert got[0] == "native base typed" and got[1] == "autosave", got
    finally:
        nw.close()


@case("LF-M12-N010", "active")
def n10_reopened_hub_keeps_one_editor_and_timer():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        ed = hub.editor
        timer = ed.timer
        nw.win.orderOut_(None)            # the retained Hub hides
        hub.showWindow_(None)
        nw.win.setFrameOrigin_(NSMakePoint(-20000, -20000))
        nw.win.orderFrontRegardless()
        pump()
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("scratchpad"))
        nw.drain()
        assert hub.editor is ed, "reopening built a second editor"
        assert ed.timer is timer and timer.isValid(), "timer replaced"
        status = ed.shutdown(2.0)
        assert ed.timer is None and not timer.isValid(), \
            "shutdown left the timer running"
        assert status["drained"], status
    finally:
        nw.close()


# ---------------------------------------------------------------------------
# ACTIVE tier (launched app, owner's go-ahead)
# ---------------------------------------------------------------------------

@case("LF-M12-N002", "active")
def n02_select_all_arrows_and_unicode_selection_at_ptt():
    """⌘A, arrows and shift-arrows over 'A😀B 👩‍💻 C'; the native range
    against the encoder; then a REAL key-window PTT captures that
    selection's start and the dictation lands there (S022)."""
    text = "A😀B 👩‍💻 C"
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        n = nw.note(text)
        k.click(hub.editor.text, k.centre(hub.editor.text))
        k.key("a", 0, cmd=True)
        r = hub.editor._native_range()
        assert r == (0, len(text.encode("utf-16-le")) // 2), f"⌘A {r}"
        k.arrow("left")                    # caret to the start
        k.arrow("right", times=2)          # over 'A' and the emoji
        assert hub.editor._native_range() == (3, 0), \
            hub.editor._native_range()
        k.arrow("right", shift=True)       # select 'B'
        assert hub.editor._native_range() == (3, 1)
        assert hub.editor.selection() == ("range", (2, 3))
        assert hub.editor.selected_text() == "B"
        assert hub.scratchpad_editor_active(), "the editor is not key"
        nw.h.press()
        target = (nw.d._job or {}).get("note_target")
        nw.h.release()
        assert target and target["insertion_point"] == 2, target
        fn, args = nw.h.run_coordinator()
        fn(*args)
        hub.editor.drain()
        nw.drain()
        final = args[1]["final_text"]
        got = _latest(nw.hw, n)[0]
        assert got == "A😀" + final + "B 👩‍💻 C", repr(got)
    finally:
        nw.close()


@case("LF-M12-N003", "active")
def n03_tab_inserts_and_control_tab_leaves_the_editor():
    """Declared convention (NSTextView): Tab inserts a tab character in
    the note; Control-Tab moves focus to the next control (no dead
    loop — Tab from the search field moves on too)."""
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        n = nw.note("tab")
        k.click(hub.editor.text, k.centre(hub.editor.text))
        hub.editor.text.setSelectedRange_((3, 0))
        k.key("\t", 48)
        assert str(hub.editor.current_content()) == "tab\t", \
            repr(str(hub.editor.current_content()))
        k.key_mod("\t", 48, NSEventModifierFlagControl)
        assert nw.win.firstResponder() is not hub.editor.text, \
            "Control-Tab did not leave the editor"
        k.click(hub.scratchpad_search)
        before = nw.win.firstResponder()
        k.key("\t", 48)
        assert nw.win.firstResponder() is not before, "dead focus loop"
        hub.editor.drain()
        assert n
    finally:
        nw.close()


@case("LF-M12-N004", "active")
def n04_first_responder_matrix_at_ptt():
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        nw.note("matrix note")
        bound = {}

        def ptt(label):
            nw.h.press()
            bound[label] = "note_target" in (nw.d._job or {})
            nw.h.release()
            fn, args = nw.h.run_coordinator()
            fn(*args)
            hub.editor.drain()
            nw.drain()
        k.click(hub.editor.text, k.centre(hub.editor.text))
        ptt("editor")
        k.click(hub.scratchpad_search)
        ptt("search_field")
        nw.win.makeFirstResponder_(hub.scratchpad_table)
        ptt("notes_list")
        nw.win.makeFirstResponder_(hub.scratchpad_transforms)
        ptt("popup")
        helper = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(-19000, -19000, 200, 100), 1, 2, False)
        helper.makeKeyAndOrderFront_(None)
        pump(0.2)
        ptt("owned_helper_window")
        helper.orderOut_(None)
        assert bound == {"editor": True, "search_field": False,
                         "notes_list": False, "popup": False,
                         "owned_helper_window": False}, bound
    finally:
        nw.close()


@case("LF-M12-N006", "active")
def n06_picker_selection_and_whole_note_transforms():
    nw = NativeWorld(active=True, consent=True)
    try:
        hub, k = nw.hub, nw.k
        n = nw.note("alpha beta gamma")
        titles = list(hub.scratchpad_transforms.itemTitles())
        assert len(titles) >= 2, titles
        got = k.popup(hub.scratchpad_transforms, titles[-1])
        assert got == titles[-1], f"picker shows {got!r}, wanted {titles[-1]!r}"
        chosen = hub._scratchpad_transform_ids[-1]
        k.click(hub.editor.text, k.centre(hub.editor.text))
        hub.editor.text.setSelectedRange_((6, 0))
        k.arrow("right", shift=True, times=4)          # 'beta'
        k.click(actions(hub)["Transform…"])
        w.wait_for(lambda: nw.d._tf_active is None, 10)
        nw.drain()
        st = nw.d._tf_panel._state
        dest = st["capture"]["destination"]
        assert st["defn"].transform_id == chosen, \
            f"ran {st['defn'].transform_id}, chose {chosen}"
        assert (tuple(dest["range"]), dest["scope"], dest["text"]) == \
            ((6, 10), "selection", "beta"), dest
        pk = Driver(nw.d._tf_panel.panel)
        pk.click(nw.d._tf_panel._buttons["panelAccept:"])
        hub.editor.drain()
        nw.drain()
        got = _latest(nw.hw, n)[0]
        assert got == "alpha TRANSFORMED OUTPUT gamma", repr(got)
        # Whole note: a caret only.
        k.click(hub.editor.text, k.centre(hub.editor.text))
        k.arrow("left")
        k.click(actions(hub)["Transform…"])
        w.wait_for(lambda: nw.d._tf_active is None, 10)
        nw.drain()
        dest = nw.d._tf_panel._state["capture"]["destination"]
        assert dest["scope"] == "whole", dest
        pk.click(nw.d._tf_panel._buttons["panelAccept:"])
        hub.editor.drain()
        nw.drain()
        got = _latest(nw.hw, n)[0]
        assert got == "TRANSFORMED OUTPUT", repr(got)
    finally:
        nw.close()


@case("LF-M12-N007", "active")
def n07_snapshot_versions_popup_and_restore():
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        n = nw.note("version one")
        k.click(hub.editor.text, k.centre(hub.editor.text))
        k.key("a", 0, cmd=True)
        k.type("version two")
        k.click(actions(hub)["Snapshot"])
        nw.drain()
        got = _latest(nw.hw, n)
        assert got[:2] == ("version two", "explicit"), got
        titles = list(hub.scratchpad_versions.itemTitles())
        assert titles, "no versions offered"
        assert k.popup(hub.scratchpad_versions, titles[-1]) == titles[-1]
        k.click(actions(hub)["Restore"])
        nw.drain()
        assert _latest(nw.hw, n)[:3] == ("version one", "explicit",
                                         "restore")
        assert str(hub.editor.current_content()) == "version one"
    finally:
        nw.close()


@case("LF-M12-N008", "active")
def n08_pin_and_delete_act_on_the_rendered_note():
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        other = nw.hw.notes.create_note("other note")["note_id"]
        n = nw.note("rendered note")
        k.click(actions(hub)["Pin"])
        nw.drain()
        pins = dict(nw.hw.store.submit(lambda db: db.execute(
            "SELECT note_id, pinned FROM notes").fetchall()))
        assert pins == {n: 1, other: 0}, pins
        k.click(actions(hub)["Delete"])
        nw.drain()
        left = [r[0] for r in nw.hw.store.submit(lambda db: db.execute(
            "SELECT note_id FROM notes").fetchall())]
        assert left == [other], left
    finally:
        nw.close()


@case("LF-M12-N011", "active")
def n11_autosave_during_menu_tracking_and_a_modal_panel():
    nw = NativeWorld(active=True)
    try:
        hub, k = nw.hub, nw.k
        n = nw.note("modes")
        k.click(hub.editor.text, k.centre(hub.editor.text))
        hub.editor.text.setSelectedRange_((5, 0))
        k.type(" menu")
        seen = {}

        def during_menu(t):
            seen["menu"] = _latest(nw.hw, n)[0]
            hub.scratchpad_transforms.menu().cancelTracking()
        t1 = NSTimer.timerWithTimeInterval_repeats_block_(
            3.0, False, during_menu)
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            t1, "NSEventTrackingRunLoopMode")
        nw.win.makeFirstResponder_(hub.scratchpad_transforms)
        k.key(" ", 49)                     # opens the popup's menu
        t1.invalidate()
        k.click(hub.editor.text, k.centre(hub.editor.text))
        hub.editor.text.setSelectedRange_((10, 0))
        k.type(" modal")
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(-19000, -19000, 200, 100), 1, 2, False)

        def during_modal(t):
            seen["modal"] = _latest(nw.hw, n)[0]
            APP.stopModal()
        t2 = NSTimer.timerWithTimeInterval_repeats_block_(
            3.0, False, during_modal)
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            t2, "NSModalPanelRunLoopMode")
        APP.runModalForWindow_(panel)
        t2.invalidate()
        panel.orderOut_(None)
        hub.editor.drain()
        assert seen.get("menu") == "modes menu", seen
        assert seen.get("modal") == "modes menu modal", seen
    finally:
        nw.close()


@case("LF-M12-N012", "active")
def n12_quit_right_after_an_accepted_note_transform():
    nw = NativeWorld(active=True, consent=True)
    db = nw.hw.store.db_path
    try:
        hub, k = nw.hub, nw.k
        n = nw.note("quit source")
        k.click(actions(hub)["Transform…"])
        w.wait_for(lambda: nw.d._tf_active is None, 10)
        nw.drain()
        Driver(nw.d._tf_panel.panel).click(
            nw.d._tf_panel._buttons["panelAccept:"])
        nw.hw.mq.discard()
        nw.d.applicationWillTerminate_(None)   # immediately after accept
    finally:
        nw.win.orderOut_(None)
        nw.hw.mq.__exit__(None, None, None)
    from localflow.v2 import store as store_mod
    s = store_mod.Store(db)
    try:
        row = s.submit(lambda d: d.execute(
            "SELECT r.content_text, r.origin FROM notes x JOIN"
            " note_revisions r ON r.revision_id = x.current_revision_id"
            " WHERE x.note_id=?", (n,)).fetchone())
    finally:
        s.close()
        nw.h._tmp.cleanup()
    assert row == ("TRANSFORMED OUTPUT", "transform"), row


# Runs LAST in the active tier: another application takes the front.
@case("LF-M12-N005", "active")
def n05_another_app_in_front_removes_the_note_binding():
    nw = NativeWorld(active=True)
    helper = None
    try:
        hub, k = nw.hub, nw.k
        nw.note("front note")
        k.click(hub.editor.text, k.centre(hub.editor.text))
        assert hub.scratchpad_editor_active()
        # macOS activation is cooperative: the active app yields to the
        # owned helper so the helper's own activation request is granted.
        yield_to = getattr(APP, "yieldActivationToApplicationWithBundle"
                                "Identifier_", None)
        if yield_to is not None:
            yield_to("local.localflow.m12-helper")
        helper = _launch_helper_app()
        # The system's own record of the frontmost app decides; then the
        # pending app-level events are dispatched as NSApp.run would, so
        # this process's AppKit state (isActive, key window) catches up.
        from AppKit import NSEventMaskAny
        deadline = time.monotonic() + 12.0
        while frontmost_pid() == os.getpid() \
                and time.monotonic() < deadline:
            pump(0.1)
        while APP.isActive() and time.monotonic() < deadline:
            ev = APP.nextEventMatchingMask_untilDate_inMode_dequeue_(
                NSEventMaskAny, NSDate.dateWithTimeIntervalSinceNow_(0.05),
                NSDefaultRunLoopMode, True)
            if ev is not None:
                APP.sendEvent_(ev)
        if APP.isActive():
            helper.wait(20)
            log = _launch_helper_app.log
            detail = log.read_text()[-300:] if log.is_file() else "no log"
            raise AssertionError("the owned helper app never came front"
                                 f" ({detail!r})")
        nw.h.press()
        bound = "note_target" in (nw.d._job or {})
        nw.h.release()
        fn, args = nw.h.run_coordinator()
        fn(*args)
        hub.editor.drain()
        assert not bound, "a dictation bound to the note in a background app"
    finally:
        if helper is not None:
            helper.terminate()
            helper.wait(10)
        nw.close()


HELPER_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.localflow.m12-helper</string>
<key>CFBundleName</key><string>LF-M12-Helper</string>
<key>CFBundleExecutable</key><string>run</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
</dict></plist>
"""

HELPER_RUN = """#!/bin/zsh
exec "$1" -c 'import time, sys
from AppKit import NSApplication, NSWindow, NSMakeRect
app = NSApplication.sharedApplication(); app.setActivationPolicy_(1)
app.finishLaunching()
w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(-18000, -18000, 200, 100), 1, 2, False)
w.makeKeyAndOrderFront_(None)
act = getattr(app, "activate", None)
act() if act is not None else app.activateIgnoringOtherApps_(True)
from Foundation import NSRunLoop, NSDate
end = time.time() + 12
while time.time() < end:
    NSRunLoop.currentRunLoop().runUntilDate_(
        NSDate.dateWithTimeIntervalSinceNow_(0.1))
print("helper active at exit:", app.isActive())' > "$2" 2>&1
"""


def _launch_helper_app():
    """An owned helper app (a temporary bundle LaunchServices opens, so
    it is activated at launch) that shows an off-screen window and
    exits by itself within 12 s."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="lf-m12-helper-"))
    app = tmp / "LF-M12-Helper.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text(HELPER_PLIST)
    run = app / "Contents" / "MacOS" / "run"
    run.write_text(HELPER_RUN)
    run.chmod(0o755)
    _launch_helper_app.log = tmp / "helper.log"
    return subprocess.Popen(["open", "-W", "-n", str(app), "--args",
                             sys.executable, str(tmp / "helper.log")])


# ---------------------------------------------------------------------------

def production_tree(root):
    def git(*a):
        p = subprocess.run(["git", "-C", str(root), *a],
                           capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    return {"localflow_tree": git("rev-parse", "HEAD:localflow"),
            "production_tree_modified": bool(git(
                "status", "--porcelain", "--untracked-files=no", "--",
                "localflow"))}


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = argv[argv.index("-k") + 1] if "-k" in argv \
        else (os.environ.get("LF_NATIVE_ONLY") or None)
    results = []
    activated = None
    if LAUNCHED:
        deadline = time.monotonic() + 8.0
        while not APP.isActive() and time.monotonic() < deadline:
            pump(0.05)
        activated = bool(APP.isActive())
    for fn in CASES:
        if only and not any(o in fn.__name__ for o in only.split(",")):
            continue
        rec = {"id": fn.__name__, "corpus_id": fn.corpus_id,
               "tier": fn.tier}
        t0 = time.monotonic()
        if fn.tier == "active" and not ACTIVE:
            results.append({**rec, "status": "NOT_RUN",
                            "note": "needs --activate (owner go-ahead,"
                                    " hands off the keyboard)"})
            print(f"NOT_RUN {fn.__name__}: needs --activate")
            continue
        if fn.tier == "passive" and LAUNCHED:
            results.append({**rec, "status": "NOT_RUN",
                            "note": "passive cases run unlaunched"})
            continue
        if fn.tier == "active" and LAUNCHED and not activated:
            results.append({**rec, "status": "ERROR",
                            "note": "launch activation not granted"})
            continue
        try:
            fn()
            status, note = "PASS", ""
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            status, note = "FAIL", str(e)[:400]
            print(f"FAIL {fn.__name__}: {note}")
        except Exception as e:  # noqa: BLE001
            status, note = "ERROR", f"{type(e).__name__}: {e}"[:400]
            print(f"ERROR {fn.__name__}: {note}")
            traceback.print_exc()
        results.append({**rec, "status": status, "note": note,
                        "seconds": round(time.monotonic() - t0, 2)})
    restored = None
    if LAUNCHED:
        from AppKit import NSRunningApplication
        front = int(os.environ["LF_NATIVE_RESTORE_PID"])
        prev = NSRunningApplication \
            .runningApplicationWithProcessIdentifier_(front)
        if prev is not None:
            prev.activateWithOptions_(0)
        deadline = time.monotonic() + 3.0
        while frontmost_pid() != front and time.monotonic() < deadline:
            pump(0.05)
        restored = frontmost_pid() == front
    passed = sum(r["status"] == "PASS" for r in results)
    ran = sum(r["status"] != "NOT_RUN" for r in results)
    print(f"{passed}/{ran} native M12 Scratchpad cases passed"
          f" ({len(results) - ran} not run)")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            **w.code_stamp("tests/v2/notes/test_native_m12_scratchpad.py"),
            **production_tree(w.ROOT),
            "kind": "NATIVE_AUTOMATED",
            "active_tier_run": ACTIVE, "launched_as_app": LAUNCHED,
            "launch_activation_granted": activated,
            "prior_frontmost_restored": restored,
            "window": "owned by this process, off-screen; events via this"
                      " app's own dispatch (nothing posted to the system"
                      " event stream); the passive tier never activates the"
                      " app; the active tier runs as a launched app and"
                      " restores the prior frontmost application",
            "cases": results, "passed": passed, "ran": ran,
            "total": len(results)}, indent=2) + "\n")
    return 0 if passed == ran else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
