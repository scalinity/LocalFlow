"""The Hub's Dock tile and quit semantics (headless).

While the Hub is open the bundled app is a regular app with a Dock tile;
closing the Hub returns it to the menu bar only. ⌘Q in the Hub and the
Dock's Quit close the Hub — dictation keeps running; only an explicit
Quit LocalFlow (or a logout/shutdown) ends the app. A source checkout has
no bundle icon, so it keeps the menu-bar-only shell (and this suite never
puts a Dock tile on the desktop).

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_hub_dock.py
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2.ui.companion import host as host_mod  # noqa: E402
from test_lifecycle import Harness  # noqa: E402


class _Window:
    def __init__(self, visible):
        self.visible = visible
        self.closed = 0

    def isVisible(self):
        return self.visible

    def performClose_(self, sender):
        self.closed += 1
        self.visible = False


class _Hub:
    def __init__(self, visible=True):
        self.window = _Window(visible)


def test_only_an_explicit_quit_ends_the_app():
    h = Harness(durations=[1.0])
    try:
        d = h.d
        d._hub = _Hub(visible=True)
        # ⌘Q or the Dock's Quit: the Hub closes, the app keeps running.
        assert d.applicationShouldTerminate_(None) == 0
        assert d._hub.window.closed == 1
        # With the Hub already closed nothing else happens.
        assert d.applicationShouldTerminate_(None) == 0
        assert d._hub.window.closed == 1
        # The explicit Quit LocalFlow is allowed through.
        d._quit_requested = True
        assert d.applicationShouldTerminate_(None) == 1
        assert app_mod._system_is_quitting() is False  # no Apple event now
    finally:
        h.close()
    print("ok  quit: ⌘Q and the Dock's Quit close the Hub; Quit LocalFlow"
          " ends the app")


def test_dock_tile_reopens_the_hub_and_stays_off_in_a_checkout():
    h = Harness(durations=[1.0])
    try:
        d = h.d
        opened = []
        d.openHub_ = lambda sender: opened.append(sender)
        assert d.applicationShouldHandleReopen_hasVisibleWindows_(None, False)
        assert opened == [None]
        app = NSApplication.sharedApplication()
        before = app.activationPolicy()
        assert app_mod._bundle_icon() is None  # a source checkout
        d._hub_dock(True)
        assert app.activationPolicy() == before
        d.hubWindowClosed()
        assert app.activationPolicy() == before
    finally:
        h.close()
    print("ok  dock: the tile reopens the Hub; a checkout never shows one")


def test_status_menu_quit_is_the_explicit_quit():
    """Read from the builder's source: building the status item here would
    put a second icon in the real menu bar."""
    import inspect
    src = inspect.getsource(app_mod.AppDelegate._setup_status_item)
    assert '"Quit LocalFlow", "quitLocalFlow:"' in src.replace("\n", " ") \
        or ('"Quit LocalFlow"' in src and '"quitLocalFlow:"' in src)
    assert "quit_item.setTarget_(self)" in src
    print("ok  status menu: Quit LocalFlow is the explicit quit")


def test_app_menu_leads_and_command_q_closes_the_hub():
    main = host_mod.companion_menu()
    titles = [main.itemAtIndex_(i).title() for i in range(main.numberOfItems())]
    assert titles == ["LocalFlow", "Edit", "Window"], titles
    app_menu = main.itemAtIndex_(0).submenu()
    q = [app_menu.itemAtIndex_(i) for i in range(app_menu.numberOfItems())
         if app_menu.itemAtIndex_(i).keyEquivalent() == "q"]
    assert len(q) == 1 and q[0].action() == "performClose:" \
        and q[0].title() == "Close Hub", q
    print("ok  menus: the LocalFlow app menu leads; ⌘Q closes the Hub")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)}/{len(tests)} passed")
