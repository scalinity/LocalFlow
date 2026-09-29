"""Desktop companion — the page itself in the real WKWebView.

The real CompanionController and host over the lifecycle Harness (a
temporary store, synthetic History rows). The window is placed off-screen
and ordered front without activating the app (accessory policy), so
nothing on the desktop changes; the page is driven by evaluating
JavaScript, and what it sends crosses the real bridge. Covers route
transitions, keyboard navigation, modal cancellation and focus, window
resize, theme (explicit, live system change, relaunch) and stale
publications. Every string is synthetic.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_page.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

import AppKit  # noqa: E402
from AppKit import NSAppearance, NSApplication  # noqa: E402
from Foundation import NSDate, NSRunLoop  # noqa: E402

# The real coordinator and page run here; the general pasteboard must be
# the isolating runner's private one.
if type(AppKit.NSPasteboard).__name__ != "_PasteboardClass":
    sys.exit("companion suites: run under tests/v2/context/run_isolated.py"
             " (the desktop-isolating runner); refusing to start")

import m09_world as W  # noqa: E402

ROUTES = {"home": "Home", "history": "History", "insights": "Insights",
          "dictionary": "Dictionary", "snippets": "Snippets",
          "styles": "Styles", "transforms": "Transforms",
          "scratchpad": "Scratchpad", "models": "Models",
          "diagnostics": "Diagnostics"}
SENTENCES = ("Move the design review to Thursday afternoon.",
             "Add oat milk and lemons to the shopping list.",
             "The build finished and every check passed.")
CANVAS = {"light": "#fcfcfb", "dark": "#1a1917"}


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.02))


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


class PWorld:
    def __init__(self, prefs=None):
        self.prefs = prefs

    def __enter__(self):
        from test_lifecycle import Harness
        from localflow.v2.ui.companion.controller import CompanionController
        NSApplication.sharedApplication().setActivationPolicy_(1)
        self.h = Harness(durations=[1.0], cfg={"hub_ui": "companion"})
        d = self.d = self.h.d
        now = dt.datetime.now(dt.timezone.utc)
        for i, text in enumerate(SENTENCES):
            W.seed_job(d.store, text.lower(), applied=text,
                       captured=iso(now - dt.timedelta(minutes=7 * i + 1)))
        spec, _ = W.hub_spec(d)
        self.prefs_path = self.h.tmp / "companion.json"
        if self.prefs is not None:
            self.prefs_path.write_text(json.dumps(self.prefs))
        spec.update(vocabulary_store=d._vocab, display_name="Alex",
                    prefs_path=self.prefs_path)
        self.spec = spec
        self.ctl = CompanionController(spec)
        d._hub = self.ctl
        self.host = self.ctl.host
        self.win = self.open(self.ctl)
        return self

    @staticmethod
    def open(ctl):
        host = ctl.host
        try:
            # Off-screen counts as occluded; WebKit would then pause.
            host.webview._setWindowOcclusionDetectionEnabled_(False)
        except Exception:
            pass
        win = host.window
        win.setFrame_display_(((-4000, 300), (1150, 715)), True)
        win.orderFront_(None)
        ctl.state.show()
        deadline = time.monotonic() + 10
        while not host._loaded and time.monotonic() < deadline:
            pump(0.05)
        assert host._loaded, "page never loaded"
        pump(1.0)
        return win

    def js(self, src, wait=2.0):
        box = {}
        self.host.webview.evaluateJavaScript_completionHandler_(
            src, lambda res, err: box.update(res=res, err=err))
        end = time.monotonic() + wait
        while "res" not in box and time.monotonic() < end:
            pump(0.02)
        assert box.get("err") is None, box.get("err")
        return box.get("res")

    def nav(self, route):
        ok = self.js("(() => { const b = [...document.querySelectorAll("
                     "'nav button')].find(x => x.textContent.trim() === "
                     + json.dumps(ROUTES[route]) + "); if (!b) return false;"
                     " b.click(); return true; })()")
        assert ok, f"no nav item for {route}"
        pump(1.0)

    def click(self, label):
        ok = self.js("(() => { const b = [...document.querySelectorAll("
                     "'button')].find(x => x.textContent.trim() === "
                     + json.dumps(label) + "); if (!b) return false;"
                     " b.click(); return true; })()")
        assert ok, f"no button {label!r}"
        pump(0.6)

    def key(self, key, target="document.activeElement", shift=False):
        self.js(f"({target}).dispatchEvent(new KeyboardEvent('keydown', "
                f"{{key: {json.dumps(key)}, shiftKey: {json.dumps(shift)},"
                " bubbles: true, cancelable: true})); 1")
        pump(0.5)

    def canvas(self):
        return (self.js("getComputedStyle(document.documentElement)"
                        ".getPropertyValue('--canvas')") or "").strip().lower()

    def __exit__(self, *exc):
        try:
            self.ctl.state.shutdown()
            self.win.orderOut_(None)
            self.win.close()
            pump(0.2)
        finally:
            NSApplication.sharedApplication().setAppearance_(None)
            self.h.close()
        return False


def test_routes_switch_and_publish():
    with PWorld() as w:
        for route, label in ROUTES.items():
            w.nav(route)
            current = w.js("document.querySelector('nav [aria-current="
                           "\"page\"]')?.textContent.trim()")
            assert current == label, (route, current)
            assert w.ctl.state.selected_view == route, \
                (route, w.ctl.state.selected_view)
            text = w.js("document.querySelector('main')?.innerText.length"
                        " || 0")
            assert text > 20, f"{route} rendered nothing"
        assert w.js("document.querySelectorAll('[role=dialog]').length") \
            == 0
    print("ok  routes: every nav item selects its route in the page and in"
          " Python, and renders")


def test_history_arrow_keys_move_the_selection():
    with PWorld() as w:
        w.nav("history")
        rows = W.history_rows(w.ctl)
        assert len(rows) >= 2, rows
        w.js("document.querySelector('[data-row]').focus(); 1")
        w.key("ArrowDown")
        pump(0.6)
        view = w.ctl.state.views["history"]
        assert view.get("selected_id") == rows[1]["id"], \
            (view.get("selected_id"), rows[1]["id"])
        assert w.js("document.activeElement === document.querySelectorAll("
                    "'[data-row]')[1]")
        w.key("ArrowUp")
        pump(0.6)
        assert w.ctl.state.views["history"].get("selected_id") \
            == rows[0]["id"]
        # A segmented control is one tab stop; arrows move its selection.
        w.nav("models")
        w.js("[...document.querySelectorAll('[role=tab]')].find(b =>"
             " b.textContent.trim() === 'Training data').click(); 1")
        pump(0.8)
        stops = w.js("[...document.querySelectorAll('[role=radio]')]"
                     ".filter(b => b.tabIndex === 0).length")
        assert stops == 1, stops
        w.js("document.querySelector('[role=radio][tabindex=\"0\"]')"
             ".focus(); 1")
        before = w.ctl.state.views["models"].get("training_tab")
        w.key("ArrowRight")
        pump(0.6)
        after = w.ctl.state.views["models"].get("training_tab")
        assert after != before and w.js(
            "document.activeElement.getAttribute('aria-checked')") \
            == "true", (before, after)
    print("ok  keyboard: arrow keys move focus and the selection through"
          " History")


def test_modal_cancels_without_writing_and_returns_focus():
    with PWorld() as w:
        w.nav("dictionary")
        before = len(w.d._vocab.entries())
        # Keyboard activation: the opener has focus when it fires (a
        # mouse click on a WebKit button does not focus it).
        w.js("[...document.querySelectorAll('button')].find(b => "
             "b.textContent.trim() === 'Add new').focus(); 1")
        w.click("Add new")
        assert w.js("!!document.querySelector('[role=dialog]')")
        assert w.js("document.querySelector('[role=dialog]').contains("
                    "document.activeElement)"), "focus not in the dialog"
        # text entry reaches the field
        w.js("(() => { const i = document.querySelector('[role=dialog] "
             "input'); i.value = 'Kubernetes'; i.dispatchEvent(new Event("
             "'input', {bubbles: true})); return 1; })()")
        pump(0.3)
        assert w.js("document.querySelector('[role=dialog] input').value")\
            == "Kubernetes"
        # Tab from the last control wraps to the first
        w.js("(() => { const p = document.querySelector('[role=dialog]');"
             " const f = [...p.querySelectorAll('button:not([disabled]),"
             " input:not([disabled]), select:not([disabled])')].filter("
             "e => e.offsetParent); f[f.length - 1].focus(); return 1; })()")
        w.key("Tab", target="document.querySelector('[role=dialog]')")
        assert w.js("(() => { const p = document.querySelector("
                    "'[role=dialog]'); const f = [...p.querySelectorAll("
                    "'button:not([disabled]), input:not([disabled]),"
                    " select:not([disabled])')].filter(e => e.offsetParent);"
                    " return document.activeElement === f[0]; })()"), \
            "Tab did not wrap inside the dialog"
        w.key("Escape", target="window")
        pump(0.4)
        assert not w.js("!!document.querySelector('[role=dialog]')"), \
            "Escape did not close"
        assert w.js("document.activeElement?.textContent.trim()") \
            == "Add new", "focus did not return to the opener"
        w.click("Add new")
        # A window shortcut waits while a modal is open: typed input is
        # never thrown away by navigating under it.
        w.js("window.dispatchEvent(new KeyboardEvent('keydown', {key: '3',"
             " metaKey: true, bubbles: true})); 1")
        pump(0.4)
        assert w.js("!!document.querySelector('[role=dialog]')") and \
            w.ctl.state.selected_view == "dictionary", "⌘3 left the modal"
        w.click("Cancel")
        assert not w.js("!!document.querySelector('[role=dialog]')")
        assert len(w.d._vocab.entries()) == before, "cancel wrote"
    print("ok  modal: focus moves in and wraps, Escape and Cancel close"
          " without writing, focus returns to the opener")


def test_every_route_fits_the_minimum_and_a_large_window():
    from localflow.v2.ui.companion.host import MIN_SIZE
    with PWorld() as w:
        for size in (MIN_SIZE, (1600.0, 1000.0)):
            w.win.setFrame_display_(((-4000, 300), size), True)
            pump(0.6)
            for route in ROUTES:
                w.nav(route)
                over = w.js(
                    "(() => { const out = []; const d = document"
                    ".documentElement; if (d.scrollWidth > d.clientWidth + 1)"
                    " out.push('document'); for (const e of document"
                    ".querySelectorAll('main, main *')) { const s ="
                    " getComputedStyle(e); if (/(auto|scroll)/.test("
                    "s.overflowY) && e.scrollWidth > e.clientWidth + 1 &&"
                    " s.overflowX !== 'hidden') out.push(e.className ||"
                    " e.tagName); } return out; })()")
                assert not over, (size, route, over)
    print("ok  resize: no route scrolls sideways at the minimum or a large"
          " window")


def test_theme_explicit_live_and_relaunch():
    app = NSApplication.sharedApplication()
    with PWorld(prefs={"theme": "system"}) as w:
        # System follows the app's effective appearance live.
        app.setAppearance_(NSAppearance.appearanceNamed_(
            "NSAppearanceNameDarkAqua"))
        pump(0.6)
        assert w.canvas() == CANVAS["dark"], w.canvas()
        app.setAppearance_(NSAppearance.appearanceNamed_(
            "NSAppearanceNameAqua"))
        pump(0.6)
        assert w.canvas() == CANVAS["light"], w.canvas()
        # Explicit Dark while the system is light, chosen in the page.
        out = w.js("window.webkit.messageHandlers.lf.postMessage("
                   "JSON.stringify({bridge_version: 1, request_id: 't1',"
                   " command: 'prefs.set_theme', payload: {theme: 'dark'}}))"
                   " && 1")
        pump(0.6)
        assert out is not None
        assert w.canvas() == CANVAS["dark"], w.canvas()
        assert json.loads(w.prefs_path.read_text())["theme"] == "dark"
        # Explicit Light while the system is dark.
        app.setAppearance_(NSAppearance.appearanceNamed_(
            "NSAppearanceNameDarkAqua"))
        w.host.set_theme("light")
        pump(0.6)
        assert w.canvas() == CANVAS["light"], w.canvas()
        app.setAppearance_(None)
    # Relaunch: a new controller over the saved preference opens dark.
    with PWorld(prefs={"theme": "dark"}) as w:
        assert w.host.is_dark() and w.canvas() == CANVAS["dark"]
    print("ok  theme: system follows live; explicit Light/Dark override"
          " the system; the choice persists across a relaunch")


def test_quick_scratchpad_leaves_the_new_note_focused():
    focused = ("document.activeElement?.matches('textarea.note') && "
               "document.activeElement.value === ''")
    with PWorld() as w:
        w.nav("home")
        w.ctl.scratchpad_quick_open()
        pump(1.5)
        assert w.js(focused), "the new note's editor is not focused"
        assert w.ctl.state.selected_view == "scratchpad"
    # The first Quick Scratchpad after launch: the page is still loading
    # when the coordinator asks.
    with PWorld() as w:
        from localflow.v2.ui.companion.controller import CompanionController
        ctl = CompanionController(w.spec)
        w.d._hub = ctl
        ctl.scratchpad_quick_open()
        host = w.host = ctl.host
        w.win2 = PWorld.open(ctl)
        pump(1.0)
        assert w.js(focused), "the first quick-open lost its focus"
        ctl.state.shutdown()
        w.win2.orderOut_(None)
    print("ok  quick scratchpad: the new note's editor has focus, also on"
          " the first open while the page loads")


def test_stale_snapshot_is_ignored():
    with PWorld() as w:
        w.nav("home")
        marker = "STALE_MARKER_synthetic"
        stale = {"bridge_version": 1, "type": "snapshot", "view": "home",
                 "seq": 0, "data": {"loading": False, "error": marker,
                                    "data": None}}
        w.js("window.__lfBridge.receive(" + json.dumps(json.dumps(stale))
             + "); 1")
        pump(0.3)
        assert marker not in w.js("document.body.innerText"), \
            "an older snapshot replaced a newer one"
        # Control: the same message with a newer seq is applied.
        stale["seq"] = 10 ** 12
        w.js("window.__lfBridge.receive(" + json.dumps(json.dumps(stale))
             + "); 1")
        pump(0.3)
        assert marker in w.js("document.body.innerText")
    print("ok  stale publication: an older snapshot never replaces a newer"
          " one")


if __name__ == "__main__":
    for test in (
            test_routes_switch_and_publish,
            test_history_arrow_keys_move_the_selection,
            test_modal_cancels_without_writing_and_returns_focus,
            test_every_route_fits_the_minimum_and_a_large_window,
            test_theme_explicit_live_and_relaunch,
            test_quick_scratchpad_leaves_the_new_note_focused,
            test_stale_snapshot_is_ignored):
        test()
