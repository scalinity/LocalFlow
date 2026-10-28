"""Idle unload of the cleanup model: how the Hub watches the engine states.

The companion re-reads the Home engine states every two seconds, but only
while a model is loading. A resting (``unloaded``) cleanup model is
deliberate and quiet: it must not start that polling while the window is
open. The unload, the reload and its ready reach an open Hub through one
flush each instead (``AppDelegate._setEngineStatus_``, tested in
``tests/v2/lifecycle/test_idle_unload_app.py``); once the reload shows as
``loading`` the existing recheck follows it to ``ready``.

Run: .venv/bin/python tests/v2/ui/test_idle_unload_display.py
"""

from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

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


def main():
    test_a_resting_cleanup_model_is_not_polled()
    test_a_reload_is_followed_until_ready()
    print("all idle unload display tests passed (2)")


if __name__ == "__main__":
    main()
