"""Idle unload of the cleanup model: the app side (ticket 05).

The real ``AppDelegate`` (under the declared non-native shims) with a
supervisor stand-in that records ``prepare_cleanup``:

  1  every hotkey and mouse press asks for the cleanup model, from a
     daemon thread, so a supervisor that blocks never holds up the press
  2  no ask when cleanup is not an LLM, or when the app is closing
  3  the menu-bar title says ``resting`` for an unloaded cleanup model
  4  an open Hub is flushed on each cleanup engine change (the unload, the
     reload and its ready), and never fails when there is no such Hub
  5  the cleanup wait policy reaches the worker through ``wait_engine``,
     which asks for a resting model itself (no wait of its own added)

Run: .venv/bin/python tests/v2/lifecycle/test_idle_unload_app.py
"""

import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import App, GateSup, run, tmpdir  # noqa: E402


class PrepareSup(GateSup):
    """Records the thread each ``prepare_cleanup`` runs on; optionally
    blocks inside it until ``hold`` is set."""

    def __init__(self, hold=None):
        super().__init__()
        self.hold = hold
        self.threads = []
        self.called = threading.Event()

    def prepare_cleanup(self):
        self.threads.append(threading.current_thread())
        self.called.set()
        if self.hold is not None:
            self.hold.wait(10)
        return True


def _settle(sup, calls, timeout=5.0):
    deadline = time.monotonic() + timeout
    while len(sup.threads) < calls and time.monotonic() < deadline:
        time.sleep(0.01)


def test_1_each_press_asks_off_the_main_thread():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        hold = threading.Event()
        try:
            d = a.d
            sup = PrepareSup(hold=hold)
            a.set_sup(sup)
            t0 = time.monotonic()
            a.dictate(release=False)  # returns although the ask is blocked
            assert time.monotonic() - t0 < 5.0
            assert sup.called.wait(5), "the press never asked"
            assert len(sup.threads) == 1
            thread = sup.threads[0]
            assert thread is not threading.main_thread()
            assert thread is not threading.current_thread()
            assert thread.daemon, "the ask must never keep the app alive"
            hold.set()
            a.phys = False
            d.finishDictation()
            # A second hotkey press and a mouse press ask again, one each.
            a.dictate()
            _settle(sup, 2)
            assert len(sup.threads) == 2, sup.threads
            d.startDictation(source="mouse")
            _settle(sup, 3)
            assert len(sup.threads) == 3, sup.threads
            d.cancelDictation()
        finally:
            hold.set()
            a.close()
    print("ok  1 hotkey and mouse presses each ask from a daemon thread;"
          " a blocked ask does not hold up the press")


def test_2_no_ask_for_a_non_llm_cleanup_or_a_closing_app():
    with tmpdir() as td:
        a = App(td, cfg={"cleanup": "off"}, start_coordinator=False)
        try:
            sup = PrepareSup()
            a.set_sup(sup)
            a.dictate()
            time.sleep(0.3)
            assert sup.threads == [], "asked although cleanup is off"
        finally:
            a.close()
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            sup = PrepareSup()
            a.set_sup(sup)
            a.d._closing = True
            a.d.startDictation()
            time.sleep(0.3)
            assert sup.threads == [], "asked while quitting"
            a.d._closing = False
            a.dictate()  # control: the same app asks once it is open
            assert sup.called.wait(5), "control press never asked"
        finally:
            a.close()
    print("ok  2 no ask when cleanup is not llm or the app is closing")


class _MenuItem:
    def __init__(self):
        self.titles = []

    def setTitle_(self, title):
        self.titles.append(title)


class _Hub:
    def __init__(self):
        self.flushes = 0

    def request_flush(self):
        self.flushes += 1


def test_3_menu_title_says_resting():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.model_menu_item = item = _MenuItem()
            sup = GateSup()
            a.set_sup(sup)
            for cleanup, shown in (("unloaded", "resting"),
                                   ("ready", "ready"),
                                   ("loading", "loading"),
                                   ("failed", "failed")):
                sup.engine_state = {"asr": "ready", "cleanup": cleanup}
                d._setEngineStatus_(("cleanup", cleanup))
                assert item.titles[-1] == f"ASR: ready · Cleanup: {shown}", \
                    item.titles[-1]
            sup.engine_state = {"asr": "unloaded", "cleanup": "ready"}
            d._setEngineStatus_(("asr", "unloaded"))
            assert item.titles[-1] == "ASR: unloaded · Cleanup: ready", \
                "only the cleanup state is renamed"
        finally:
            a.close()
    print("ok  3 the menu-bar title shows resting for an unloaded cleanup"
          " model and nothing else changes")


def test_4_open_hub_is_flushed_on_cleanup_changes():
    with tmpdir() as td:
        a = App(td, start_coordinator=False)
        try:
            d = a.d
            d.model_menu_item = _MenuItem()
            sup = GateSup()
            a.set_sup(sup)
            d._hub = hub = _Hub()
            for state in ("unloaded", "loading", "ready"):
                before = hub.flushes
                sup.engine_state = {"asr": "ready", "cleanup": state}
                d._setEngineStatus_(("cleanup", state))
                assert hub.flushes == before + 1, state
            before = hub.flushes
            d._setEngineStatus_(("asr", "ready"))
            assert hub.flushes == before, "a speech change needs no flush"
            # No Hub yet, or the AppKit Hub (no request_flush): no failure.
            d._hub = None
            d._setEngineStatus_(("cleanup", "unloaded"))
            d._hub = object()
            d._setEngineStatus_(("cleanup", "unloaded"))
        finally:
            a.close()
    print("ok  4 an open Hub is flushed on each cleanup engine change;"
          " no Hub and the AppKit Hub are left alone")


class _WaitSup(GateSup):
    """wait_engine as the real supervisor does it for a resting model:
    it asks for the reload itself and reports the state it ends in."""

    def __init__(self):
        super().__init__()
        self.engine_state = {"asr": "ready", "cleanup": "unloaded"}
        self.asks = 0
        self.waits = []

    def prepare_cleanup(self):
        self.asks += 1
        self.engine_state["cleanup"] = "ready"
        return True

    def wait_engine(self, engine, timeout):
        self.waits.append((engine, timeout))
        if engine == "cleanup" and self.engine_state[engine] == "unloaded":
            self.prepare_cleanup()
        return self.engine_state[engine]


def test_5_wait_policy_goes_through_wait_engine():
    with tmpdir() as td:
        a = App(td, cfg={"cleanup_not_ready_policy": "wait",
                         "cleanup_wait_timeout_sec": 7},
                start_coordinator=False)
        try:
            sup = _WaitSup()
            a.set_sup(sup)
            a.start_coordinator()
            jid, _ = a.dictate()
            assert a.wait_call("_finishWithText_", 10), "job never finished"
            assert ("cleanup", 7.0) in sup.waits, sup.waits
            # One ask per press (the stand-in's wait asked for the model
            # because it was still resting; the press's own ask came first).
            assert sup.asks >= 1
            assert sup.engine_state["cleanup"] == "ready"
            assert ("clean", 1, None, None) in sup.calls
        finally:
            a.close()
    print("ok  5 the wait policy waits through supervisor.wait_engine for"
          " the cleanup model, then cleans")


def main():
    run([test_1_each_press_asks_off_the_main_thread,
         test_2_no_ask_for_a_non_llm_cleanup_or_a_closing_app,
         test_3_menu_title_says_resting,
         test_4_open_hub_is_flushed_on_cleanup_changes,
         test_5_wait_policy_goes_through_wait_engine],
        "idle unload app tests")


if __name__ == "__main__":
    main()
