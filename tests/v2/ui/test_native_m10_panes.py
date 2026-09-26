"""NATIVE functional qualification of the Hub's Styles and Snippets panes
(M10-AUDIT-26) — real AppKit/PyObjC, the real HubController over the
real M10 stores (synthetic temporary store; the profiles-pipeline
Harness supplies the real coordinator).

Ownership and safety: this process owns the one window it drives, placed
off-screen; every event is BUILT for that window and DELIVERED through
this application's own dispatch (``NSApp.sendEvent_``; a click's
mouse-up is queued on this app's event queue first so control tracking
ends). Nothing is posted to the system event stream and nothing reads or
writes the user's clipboard. All work runs on the main thread.

Two tiers. PASSIVE (default): the app is never activated — the
frontmost application is checked unchanged after every case (a read-only
query). An inactive app's window is not key, so AppKit spends a first
click on activation for controls that do not accept first mouse (table
rows, push buttons) and routes no menu key equivalents: those paths can
only be observed ACTIVE. ACTIVE (``--activate``, run only with the
owner's go-ahead and hands off the keyboard and mouse): the app is
activated and the Hub window made key for the run; afterwards the
previously frontmost application is re-activated and checked.

What is proven per pane: a click at an input's centre reaches that input
(hit-testing through the pane), the field becomes first responder and
receives typed text, ⌘A selects the whole value, Tab moves focus,
popups change by their own menu (opened by a click, driven by keys
queued for it), the checkbox toggles, and Add / Update / Enable-Disable
/ Delete / Collisions / Preview deliver their actions to the stores
with the right stable ids — then a resize, and the geometry and a typed
edit again.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/ui/test_native_m10_panes.py [--json OUT] [-k NAME]
(the desktop isolation changes nothing this suite needs: it never uses
Accessibility, event posting or the general pasteboard)
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parents[1] / "profiles"))

from AppKit import (NSApplication, NSEvent,  # noqa: E402
                    NSEventMaskLeftMouseUp, NSEventModifierFlagCommand,
                    NSEventTypeKeyDown, NSEventTypeKeyUp,
                    NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp,
                    NSMakePoint, NSMakeSize, NSTimer, NSWorkspace)
from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop  # noqa: E402

import m10_world as w  # noqa: E402

APP = NSApplication.sharedApplication()
APP.setActivationPolicy_(1)  # accessory: never takes the menu bar

CASES = []
ACTIVE = "--activate" in sys.argv
# Launched as an app by the active tier's launcher (which names the app
# to restore): the system activated this process at launch, so the run
# keeps that activation for every case and hands focus back once, at
# the end — a per-case hand-back cannot be re-requested (macOS
# activation is cooperative). The passive cases run unlaunched.
LAUNCHED = ACTIVE and os.environ.get("LF_NATIVE_RESTORE_PID",
                                     "").isdigit()


def case(tier="passive"):
    def deco(fn):
        fn.tier = tier
        CASES.append(fn)
        return fn
    return deco


def pump(sec=0.04):
    NSRunLoop.currentRunLoop().runUntilDate_(
        NSDate.dateWithTimeIntervalSinceNow_(sec))


def frontmost_pid():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.processIdentifier() if app is not None else None


class Driver:
    """Events for one owned window, through this app's own dispatch."""

    def __init__(self, win):
        self.win = win
        self.sent = {"mouse": 0, "key": 0, "late_mouse_up": 0}

    def _key(self, t, chars, code, flags):
        return NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
            t, NSMakePoint(0, 0), flags, time.monotonic(),
            self.win.windowNumber(), None, chars, chars, False, code)

    def key(self, chars, code=0, cmd=False):
        flags = NSEventModifierFlagCommand if cmd else 0
        for t in (NSEventTypeKeyDown, NSEventTypeKeyUp):
            APP.sendEvent_(self._key(t, chars, code, flags))
            self.sent["key"] += 1
        pump()

    def type(self, text):
        for ch in text:
            self.key(ch, 49 if ch == " " else 0)

    def queued_keys(self, specs):
        """Key events queued on this app's queue (consumed by the next
        tracking loop — a popup's menu)."""
        for chars, code in specs:
            for t in (NSEventTypeKeyDown, NSEventTypeKeyUp):
                APP.postEvent_atStart_(self._key(t, chars, code, 0), False)
                self.sent["key"] += 1

    def centre(self, view):
        b = view.bounds()
        return view.convertPoint_toView_(
            NSMakePoint(b.size.width / 2, b.size.height / 2), None)

    def hit(self, view):
        p = self.centre(view)
        theme = self.win.contentView().superview()
        h = theme.hitTest_(p)
        return h is not None and (h is view or h.isDescendantOf_(view))

    def click(self, view, point=None):
        p = point if point is not None else self.centre(view)

        def mk(t):
            return NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                t, p, 0, time.monotonic(), self.win.windowNumber(), None, 0,
                1, 1.0)
        APP.postEvent_atStart_(mk(NSEventTypeLeftMouseUp), False)
        APP.sendEvent_(mk(NSEventTypeLeftMouseDown))
        self.sent["mouse"] += 2
        # A control that decided the click without a tracking loop (a
        # table row in an active window) leaves the mouse-up queued. The
        # run loop pumped here never dispatches queued events, so deliver
        # it now as the app's event loop would — a stray mouse-up must
        # not be taken by the NEXT control's tracking as its own.
        late = APP.nextEventMatchingMask_untilDate_inMode_dequeue_(
            NSEventMaskLeftMouseUp, NSDate.distantPast(),
            NSDefaultRunLoopMode, True)
        if late is not None:
            self.sent["late_mouse_up"] += 1
            APP.sendEvent_(late)
        pump()

    def editing(self, field):
        fr = self.win.firstResponder()
        return fr is field or (hasattr(fr, "delegate")
                               and fr.delegate() is field)

    def selected_range(self):
        fr = self.win.firstResponder()
        r = fr.selectedRange() if hasattr(fr, "selectedRange") else None
        return (r.location, r.length) if r is not None else None

    def popup(self, popup, title):
        """Open the popup's own menu and choose ``title`` with arrow keys
        + Return queued for its tracking loop (a timer in the tracking
        mode cancels it if it ever stalls). Inactive, a click opens the
        menu; in an ACTIVE app a mouse-opened menu tracks the real cursor
        and ignores queued keys, so the menu is opened from the keyboard
        (Space on the focused popup) — measured on the reference Mac."""
        titles = list(popup.itemTitles())
        cur = titles.index(popup.titleOfSelectedItem())
        tgt = titles.index(title)
        arrow = ("", 125) if tgt > cur else ("", 126)
        self.queued_keys([arrow] * abs(tgt - cur) + [("\r", 36)])
        guard = NSTimer.timerWithTimeInterval_repeats_block_(
            3.0, False, lambda t: popup.menu().cancelTracking())
        NSRunLoop.currentRunLoop().addTimer_forMode_(
            guard, "NSEventTrackingRunLoopMode")
        if APP.isActive():
            self.win.makeFirstResponder_(popup)
            self.key(" ", 49)
        else:
            self.click(popup)
        guard.invalidate()
        return popup.titleOfSelectedItem()


def button(pane, title):
    return next(v for v in pane.subviews()
                if hasattr(v, "title") and v.title() == title)


class NativeWorld:
    def __init__(self, active=False):
        self.active = active
        # Launched as an app (the active tier's launcher), this process
        # is itself frontmost at start: the launcher names the app that
        # was in front before the launch, which is the one to restore.
        restore = os.environ.get("LF_NATIVE_RESTORE_PID", "")
        self.front = int(restore) if active and restore.isdigit() \
            else frontmost_pid()
        self.h, self.sup, _ = w.harness()
        self.mq = w.MainQueue().__enter__()
        self.hub = __import__("test_m10_remediation")._hub(self.h)
        self.mq.drain(self.hub.state)
        self.win = self.hub.window
        self.win.setFrameOrigin_(NSMakePoint(-20000, -20000))
        if active:
            APP.activateIgnoringOtherApps_(True)
            self.win.makeKeyAndOrderFront_(None)
            # A launched app's activation arrives asynchronously.
            deadline = time.monotonic() + (8.0 if LAUNCHED else 3.0)
            while not (APP.isActive() and self.win.isKeyWindow()) \
                    and time.monotonic() < deadline:
                pump(0.05)
            assert self.win.isKeyWindow(), "the owned window is not key"
        else:
            self.win.orderFrontRegardless()
        pump()
        self.d = Driver(self.win)

    def open(self, view, index):
        self.hub._select_view_index(index)
        self.hub.state.select_view(view)
        self.mq.drain(self.hub.state)
        return self.hub._built_views[view]

    def drain(self):
        self.mq.drain(self.hub.state)

    def close(self):
        was_active = bool(APP.isActive())
        try:
            self.win.orderOut_(None)
            self.mq.discard()
            self.mq.__exit__(None, None, None)
        finally:
            self.h.close()
        if self.active and LAUNCHED:
            return          # focus is handed back once, after the run
        if self.active:
            # Hand focus back to whichever app had it before the run.
            from AppKit import NSRunningApplication
            prev = NSRunningApplication \
                .runningApplicationWithProcessIdentifier_(self.front) \
                if self.front is not None else None
            if prev is not None:
                prev.activateWithOptions_(0)
            deadline = time.monotonic() + 3.0
            while frontmost_pid() != self.front \
                    and time.monotonic() < deadline:
                pump(0.05)
            assert frontmost_pid() == self.front, \
                "the previously frontmost application was not restored"
            return
        assert not was_active, "the test app became active"
        assert frontmost_pid() == self.front, \
            "the frontmost application changed"


def rows(h, table, key):
    return w.raw_rows(h.d.store, table, key)


def select_row(nw, table, id_key, rid):
    rendered = nw.hub._rendered_rows.get(table) or []
    idx = next(i for i, r in enumerate(rendered) if r.get(id_key) == rid)
    tv = getattr(nw.hub, table)
    rect = tv.rectOfRow_(idx)
    p = tv.convertPoint_toView_(
        NSMakePoint(rect.origin.x + 20, rect.origin.y + rect.size.height
                    / 2), None)
    nw.d.click(tv, p)
    nw.drain()


# ---------------------------------------------------------------------------

@case()
def n01_every_input_is_hittable_in_both_panes():
    nw = NativeWorld()
    try:
        hub = nw.hub
        pane = nw.open("styles", 2)
        f = pane.frame()
        assert f.size.width > 0 and f.size.height > 0, \
            f"styles pane has a zero frame: {tuple(f.size)}"
        misses = [n for n, v in (
            ("style_name", hub.style_name),
            ("style_scope", hub.style_scope),
            ("style_scope_value", hub.style_scope_value),
            ("style_mode", hub.style_mode),
            ("style_numbers", hub.style_numbers),
            ("style_phrase", hub.style_phrase),
            ("Add", button(pane, "Add"))) if not nw.d.hit(v)]
        pane = nw.open("snippets", 3)
        misses += [n for n, v in (
            ("snip_trigger", hub.snip_trigger),
            ("snip_name", hub.snip_name),
            ("snip_kind", hub.snip_kind),
            ("snip_rewrite", hub.snip_rewrite),
            ("snip_content", hub.snip_content),
            ("Add", button(pane, "Add"))) if not nw.d.hit(v)]
        assert not misses, f"a click cannot reach: {misses}"
    finally:
        nw.close()


@case()
def n02p_click_focus_typing_and_popup_while_inactive():
    """The passive tier: a click focuses a text field and typed text
    lands in it; a popup changes through its own menu — without the app
    ever becoming active (controls that spend a first click on
    activation are the active tier's)."""
    nw = NativeWorld()
    try:
        hub = nw.hub
        nw.open("snippets", 3)
        nw.d.click(hub.snip_trigger)
        assert nw.d.editing(hub.snip_trigger), \
            "a click did not focus the Trigger field"
        nw.d.type("native reply")
        assert hub.snip_trigger.stringValue() == "native reply", \
            hub.snip_trigger.stringValue()
        assert nw.d.popup(hub.snip_kind, "code") == "code"
    finally:
        nw.close()


@case()
def n02t_tab_moves_focus_while_inactive():
    """Tab leaves a focused field for the pane's next control: the Hub
    window derives its key-view loop from the views it shows."""
    nw = NativeWorld()
    try:
        hub = nw.hub
        nw.open("styles", 2)
        nw.d.click(hub.style_name)
        assert nw.d.editing(hub.style_name), \
            "a click did not focus the Name field"
        nw.d.type("Tab probe")
        nw.d.key("\t", 48)
        assert not nw.d.editing(hub.style_name), "Tab did not move focus"
        assert hub.style_name.stringValue() == "Tab probe", \
            hub.style_name.stringValue()
    finally:
        nw.close()


@case("active")
def n02_styles_text_entry_select_all_and_tab():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        nw.open("styles", 2)
        nw.d.click(hub.style_name)
        assert nw.d.editing(hub.style_name), \
            "a click did not focus the Name field"
        nw.d.type("Native One")
        assert hub.style_name.stringValue() == "Native One", \
            hub.style_name.stringValue()
        nw.d.key("a", 0, cmd=True)
        assert nw.d.selected_range() == (0, len("Native One")), \
            f"⌘A did not select the value: {nw.d.selected_range()}"
        nw.d.type("Native Two")
        assert hub.style_name.stringValue() == "Native Two", \
            hub.style_name.stringValue()
        nw.d.key("\t", 48)
        assert not nw.d.editing(hub.style_name), "Tab did not move focus"
    finally:
        nw.close()


@case("active")
def n03_styles_add_from_the_controls():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        pane = nw.open("styles", 2)
        nw.d.click(hub.style_name)
        nw.d.type("Native Rule")
        assert nw.d.popup(hub.style_scope, "app") == "app"
        nw.d.click(hub.style_scope_value)
        nw.d.type("com.example.native")
        assert nw.d.popup(hub.style_mode, "raw") == "raw"
        assert nw.d.popup(hub.style_numbers, "standard") == "standard"
        nw.d.click(button(pane, "Add"))
        nw.drain()
        got = [r[1:8] for r in rows(nw.h, "style_rules", "rule_id")]
        assert got == [("Native Rule", "app", "com.example.native", "raw",
                        "standard", None, 1)], got
    finally:
        nw.close()


@case("active")
def n04_styles_update_toggle_delete_by_rendered_row():
    nw = NativeWorld(active=True)
    try:
        hub, h = nw.hub, nw.h
        a = h.d._styles.add_rule(name="Alpha", scope_kind="app",
                                 scope_value="com.example.a", mode="raw")
        b = h.d._styles.add_rule(name="Beta", mode="clean")
        pane = nw.open("styles", 2)
        select_row(nw, "styles_table", "rule_id", a)
        assert hub.style_name.stringValue() == "Alpha", \
            "clicking the row did not fill the editor"
        nw.d.click(hub.style_name)
        nw.d.key("a", 0, cmd=True)
        nw.d.type("Alpha Renamed")
        nw.d.click(button(pane, "Update"))
        nw.drain()
        rs = {r[0]: r for r in rows(h, "style_rules", "rule_id")}
        assert rs[a][1:5] == ("Alpha Renamed", "app", "com.example.a",
                              "raw") and rs[a][8] == 2, rs[a]
        assert rs[b][1] == "Beta" and rs[b][8] == 1, rs[b]
        nw.d.click(button(pane, "Enable/Disable"))
        nw.drain()
        assert rows(h, "style_rules", "rule_id")[0][7] in (0,) or \
            {r[0]: r for r in rows(h, "style_rules", "rule_id")}[a][7] == 0
        nw.d.click(button(pane, "Delete"))
        nw.drain()
        ids = [r[0] for r in rows(h, "style_rules", "rule_id")]
        assert ids == [b], ids
        assert hub.style_name.stringValue() == "", \
            "the deleted rule's editor was not cleared"
    finally:
        nw.close()


@case("active")
def n05_snippets_add_from_the_controls():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        pane = nw.open("snippets", 3)
        nw.d.click(hub.snip_trigger)
        nw.d.type("native reply")
        nw.d.click(hub.snip_name)
        nw.d.type("Native")
        assert nw.d.popup(hub.snip_kind, "code") == "code"
        nw.d.click(hub.snip_rewrite)
        assert hub.snip_rewrite.state() == 1, "checkbox did not toggle"
        nw.d.click(hub.snip_content)
        assert nw.win.firstResponder() is hub.snip_content, \
            "the content editor did not take focus"
        nw.d.type("ACK line")
        nw.d.click(button(pane, "Add"))
        nw.drain()
        got = [r[1:7] for r in rows(nw.h, "snippets", "snippet_id")]
        assert got == [("native reply", "Native", "code", "ACK line", 1,
                        1)], got
    finally:
        nw.close()


@case("active")
def n06_snippets_collisions_update_toggle_delete():
    nw = NativeWorld(active=True)
    try:
        hub, h = nw.hub, nw.h
        sid = h.d._snip_store.add_snippet(trigger="native reply",
                                          name="n", content="OLD")
        pane = nw.open("snippets", 3)
        select_row(nw, "snippets_table", "snippet_id", sid)
        assert hub.snip_trigger.stringValue() == "native reply"
        nw.d.click(button(pane, "Collisions"))
        detail = hub.snippets_detail.string()
        assert "duplicate_trigger" not in detail, detail  # never itself
        nw.d.click(hub.snip_content)
        nw.d.key("a", 0, cmd=True)
        nw.d.type("NEW")
        nw.d.click(button(pane, "Update"))
        nw.drain()
        r = rows(h, "snippets", "snippet_id")[0]
        assert (r[4], r[7]) == ("NEW", 2), r
        nw.d.click(button(pane, "Enable/Disable"))
        nw.drain()
        assert rows(h, "snippets", "snippet_id")[0][6] == 0
        nw.d.click(button(pane, "Delete"))
        nw.drain()
        assert rows(h, "snippets", "snippet_id") == []
        assert hub.snip_trigger.stringValue() == ""
    finally:
        nw.close()


@case("active")
def n07_phrase_sandbox_preview_button():
    nw = NativeWorld(active=True)
    try:
        hub, h = nw.hub, nw.h
        h.d._snip_store.add_snippet(trigger="native reply", name="n",
                                    content="ACK")
        pane = nw.open("styles", 2)
        nw.d.click(hub.style_phrase)
        nw.d.type("native reply")
        nw.d.click(button(pane, "Preview"))
        text = hub.styles_detail.string()
        assert text.startswith("→ ACK"), text
        assert "global only" in text, text
    finally:
        nw.close()


@case("active")
def n08_resize_and_repeat():
    nw = NativeWorld(active=True)
    try:
        hub = nw.hub
        pane = nw.open("snippets", 3)
        base = nw.win.contentView().bounds().size
        nw.win.setContentSize_(NSMakeSize(base.width + 200,
                                          base.height + 120))
        pump()
        pf, cf = pane.frame().size, hub.content.bounds().size
        assert (round(pf.width), round(pf.height)) == \
            (round(cf.width), round(cf.height)), (tuple(pf), tuple(cf))
        assert nw.d.hit(hub.snip_trigger) and nw.d.hit(hub.snip_rewrite)
        nw.d.click(hub.snip_trigger)
        nw.d.type("after resize")
        assert hub.snip_trigger.stringValue() == "after resize"
        nw.win.setContentSize_(NSMakeSize(base.width, base.height))
        pump()
        assert nw.d.hit(hub.snip_trigger)
    finally:
        nw.close()


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = argv[argv.index("-k") + 1] if "-k" in argv else None
    results = []
    activated = None
    if LAUNCHED:
        deadline = time.monotonic() + 8.0
        while not APP.isActive() and time.monotonic() < deadline:
            pump(0.05)
        activated = bool(APP.isActive())
    for fn in CASES:
        if only and only not in fn.__name__:
            continue
        t0 = time.monotonic()
        if fn.tier == "active" and not ACTIVE:
            results.append({"case": fn.__name__, "tier": fn.tier,
                            "status": "not_run",
                            "detail": "needs --activate (owner go-ahead,"
                                      " hands off the keyboard)",
                            "seconds": 0.0})
            print(f"NOT_RUN {fn.__name__}: needs --activate")
            continue
        if fn.tier == "passive" and LAUNCHED:
            results.append({"case": fn.__name__, "tier": fn.tier,
                            "status": "not_run",
                            "detail": "passive cases run unlaunched (a"
                                      " launched app is active by design)",
                            "seconds": 0.0})
            print(f"NOT_RUN {fn.__name__}: passive tier runs unlaunched")
            continue
        if fn.tier == "active" and LAUNCHED and not activated:
            results.append({"case": fn.__name__, "tier": fn.tier,
                            "status": "error",
                            "detail": "the launched app was never"
                                      " activated (harness, not product)",
                            "seconds": 0.0})
            print(f"ERROR {fn.__name__}: launch activation not granted")
            continue
        try:
            fn()
            status, detail = "pass", None
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            status, detail = "fail", str(e)[:400]
            print(f"FAIL {fn.__name__}: {detail}")
        except Exception as e:
            status, detail = "error", f"{type(e).__name__}: {e}"[:400]
            print(f"ERROR {fn.__name__}: {detail}")
            traceback.print_exc()
        results.append({"case": fn.__name__, "tier": fn.tier,
                        "status": status, "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
    restored = None
    if LAUNCHED:
        # The single hand-back: the app that was in front before launch.
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
    passed = sum(r["status"] == "pass" for r in results)
    ran = sum(r["status"] != "not_run" for r in results)
    print(f"{passed}/{ran} native M10 pane cases passed"
          f" ({len(results) - ran} not run)")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            **w.code_stamp("tests/v2/ui/test_native_m10_panes.py"),
            "kind": "NATIVE_AUTOMATED",
            "active_tier_run": ACTIVE,
            "launched_as_app": LAUNCHED,
            "launch_activation_granted": activated,
            "prior_frontmost_restored": restored,
            "window": "owned by this process, off-screen; events via"
                      " this app's own dispatch; passive tier never"
                      " activates the app, the active tier (--activate)"
                      " activates it and restores the prior frontmost"
                      " application afterwards",
            "results": results, "passed": passed, "ran": ran,
            "total": len(results)}, indent=2) + "\n")
    return 0 if passed == ran else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
