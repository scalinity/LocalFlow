"""Idle unload of the cleanup model: how the Hub watches the engine states.

The companion re-reads the Home engine states every two seconds, but only
while a model is loading. A resting (``unloaded``) cleanup model is
deliberate and quiet: it must not start that polling while the window is
open. The unload, the reload and its ready reach an open Hub through
``CompanionController.engine_changed`` instead (called by
``AppDelegate._setEngineStatus_``, see
``tests/v2/lifecycle/test_idle_unload_app.py``): the sidebar is rebuilt
from the live states, and the Models engine card, which caches its block
when it loads, is reloaded while it is showing. Once the reload shows as
``loading`` the existing recheck follows it to ``ready``.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_idle_unload_display.py
"""

from __future__ import annotations

import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

from localflow.v2.ui.companion import controller as ctl_mod  # noqa: E402


class _Window:
    def isVisible(self):
        return True


class _Controller:
    """Only what ``_schedule_engine_recheck`` reads and writes."""

    def __init__(self):
        self.state = types.SimpleNamespace(visible=True)
        self.host = types.SimpleNamespace(window=_Window())
        self._engine_recheck = False
        self._pushed = {"home": "pushed"}
        self.flushes = 0

    def request_flush(self):
        self.flushes += 1


def _shell(asr, cleanup):
    return {"engine": {"asr": asr, "cleanup": cleanup}}


def _recheck(ctl, shell, timers):
    real = ctl_mod.AppHelper
    ctl_mod.AppHelper = types.SimpleNamespace(
        callLater=lambda delay, fn: timers.append((delay, fn)))
    try:
        ctl_mod.CompanionController._schedule_engine_recheck(ctl, shell)
    finally:
        ctl_mod.AppHelper = real


def test_a_resting_cleanup_model_is_not_polled():
    for cleanup in ("unloaded", "ready", "failed"):
        timers = []
        _recheck(_Controller(), _shell("ready", cleanup), timers)
        assert timers == [], f"{cleanup} must not arm the recheck"
    print("ok  unloaded, like ready and failed, arms no recheck")


def test_a_reload_is_followed_until_ready():
    ctl = _Controller()
    timers = []
    _recheck(ctl, _shell("ready", "loading"), timers)
    assert [d for d, _ in timers] == [2.0], timers
    _recheck(ctl, _shell("ready", "loading"), timers)
    assert len(timers) == 1, "one recheck at a time"
    timers[0][1]()  # the two seconds pass
    assert ctl.flushes == 1 and "home" not in ctl._pushed
    assert ctl._engine_recheck is False
    _recheck(ctl, _shell("ready", "ready"), timers)
    assert len(timers) == 1, "ready ends the rechecks"
    print("ok  a reload (loading) is rechecked every two seconds until"
          " ready, one timer at a time")


class _MenuItem:
    def setTitle_(self, title):
        pass


def test_models_engine_card_follows_the_cleanup_engine():
    """The real Hub, state and coordinator (the bridge tests' world): the
    Models page shows Resting, then Loading, then Ready, and so does the
    sidebar, without the page being reselected."""
    from test_companion_bridge import CWorld
    with CWorld() as w:
        w.d.model_menu_item = _MenuItem()
        states = w.d.supervisor.engine_state

        def card():
            return w.host.latest("models")["data"]["engine"]["cleanup_state"]

        def sidebar():
            snaps = [m for m in w.host.pushed if m.get("type") == "snapshot"]
            return snaps[-1]["shell"]["engine"]["cleanup"]

        w.select("models")
        assert card() == "ready" and sidebar() == "ready"
        for state in ("unloaded", "loading", "ready"):
            states["cleanup"] = state
            w.d._setEngineStatus_(("cleanup", state))
            w.drain()
            assert card() == state, (state, card())
            assert sidebar() == state, (state, sidebar())
        # Opening the page while resting shows Resting, and the reload
        # that follows is shown without leaving the page.
        w.select("home")
        states["cleanup"] = "unloaded"
        w.d._setEngineStatus_(("cleanup", "unloaded"))
        w.drain()
        w.select("models")
        assert card() == "unloaded"
        states["cleanup"] = "ready"
        w.d._setEngineStatus_(("cleanup", "ready"))
        w.drain()
        assert card() == "ready"
        # Another page showing: its own data is not reloaded for this.
        w.select("history")
        before = w.ctl.state.query_stats()
        states["cleanup"] = "unloaded"
        w.d._setEngineStatus_(("cleanup", "unloaded"))
        w.drain()
        assert w.ctl.state.query_stats() == before, \
            "an unrelated page was reloaded for an engine change"
        assert sidebar() == "unloaded"
    print("ok  the Models engine card and the sidebar follow unloaded ->"
          " loading -> ready on an open Hub; other pages are not reloaded")


def main():
    test_a_resting_cleanup_model_is_not_polled()
    test_a_reload_is_followed_until_ready()
    test_models_engine_card_follows_the_cleanup_engine()
    print("all idle unload display tests passed (3)")


if __name__ == "__main__":
    main()
