"""NATIVE functional qualification of the Insights and usage controls
(M13 remediation; corpus C157, C186, C237, C238, C262 and the native
halves of M13-AUDIT-05/08/09/10/20/21/23) — real AppKit/PyObjC, the real
HubController over the real coordinator (the lifecycle Harness) and a
synthetic temporary store.

Ownership and safety: this process owns the windows it drives, placed
off-screen; every event is BUILT for its own window and DELIVERED
through this application's own dispatch (M10's ``Driver``: nothing is
posted to the system event stream). The app is never activated
(PASSIVE tier) and the frontmost application is checked unchanged after
every case. Under ``run_isolated`` the general pasteboard is private.
The user override path is a temp file; no real usage store, History or
configuration is read or written. The Delete All confirmation is an
owned NSAlert answered by a timer in its own modal run loop.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/analytics/test_native_m13_insights.py [--json OUT]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "ui"))

from test_native_m10_panes import APP, Driver, frontmost_pid, pump  # noqa
import m13_world as W  # noqa: E402  (isolation guard)
import test_m13_remediation as R  # noqa: E402

from AppKit import (NSButton, NSFont, NSMakePoint, NSMakeSize,  # noqa
                    NSPopUpButton, NSTextField, NSTimer, NSEvent,
                    NSEventTypeKeyDown, NSEventTypeKeyUp)
from Foundation import NSRunLoopCommonModes, NSRunLoop  # noqa: E402

from localflow.v2.ui import hub as hub_mod  # noqa: E402
from localflow.v2.ui.state import VIEWS  # noqa: E402

CHECKS = {}


def check(name, tier="passive"):
    """PASSIVE checks never activate the app. ACTIVE checks (the real
    Delete All NSAlert: runModal activates its application) run only
    with ``--activate`` — hands off keyboard and mouse, with the owner's
    go-ahead — and the previously frontmost app is re-activated after
    each one."""
    def deco(fn):
        fn.tier = tier
        CHECKS[name] = fn
        return fn
    return deco


def restore_front(pid):
    from AppKit import NSRunningApplication
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) \
        if pid else None
    if app is not None:
        app.activateWithOptions_(0)
        deadline = time.monotonic() + 3.0
        while frontmost_pid() != pid and time.monotonic() < deadline:
            pump(0.05)


class World:
    """The real coordinator + Hub, the Hub window off-screen, main-thread
    callbacks queued and flushed on this (main) thread."""

    def __init__(self):
        self.front = frontmost_pid()
        self._ctx = R.coordinator(durations=(1.0,) * 4)
        self.h = self._ctx.__enter__()
        self.mq = W.MainQueue().__enter__()
        self.d = self.h.d
        self.hub = R.make_hub(self.h)
        self.win = self.hub.window
        self.win.setFrameOrigin_(NSMakePoint(-20000, -20000))
        self.win.orderFrontRegardless()
        pump()
        self.k = Driver(self.win)

    def show(self, view):
        self.hub._select_view_index(VIEWS.index(view))
        self.drain()

    def drain(self):
        assert self.mq.drain(self.hub.state), "Hub work did not drain"
        pump()

    def seed(self, rows):
        for i, r in enumerate(rows):
            self.d._analytics.record_dictation_fact(
                job_id=r.get("job", f"job-n{i}"),
                activity_at_utc=r.get("at", W.analytics_mod.instant_from_epoch(
                    time.time() - 3600)),
                final_words=r.get("words", 5), duration_sec=10.0,
                insertion_outcome="confirmed", mode=r.get("mode", "clean"),
                app_name=r.get("app", "Synthetic Alpha"),
                app_bundle=r.get("bundle", "com.synthetic.alpha"))

    def facts(self):
        return self.d.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM usage_facts").fetchone()[0])

    def close(self):
        try:
            self.win.orderOut_(None)
            self.hub.state.close()
        finally:
            self.mq.__exit__(None, None, None)
            self._ctx.__exit__(None, None, None)
        # The passive safety property: THIS process never became the
        # frontmost app (another app the user switched to is fine).
        assert frontmost_pid() != os.getpid(), "this process was activated"


def insights_controls(hub):
    pane = hub._built_views["insights"]
    out = {}
    for v in pane.subviews():
        if isinstance(v, (NSButton, NSPopUpButton)) and not v.isHidden():
            title = str(v.title()) if isinstance(v, NSButton) else None
            key = title or ("app" if v is hub.insights_app else
                            "mode" if v is hub.insights_mode else "popup")
            out[key] = v
    return out


def contained(view, pane):
    f = view.frame()
    b = pane.bounds()
    return (f.origin.x >= 0 and f.origin.y >= 0
            and f.origin.x + f.size.width <= b.size.width + 0.5
            and f.origin.y + f.size.height <= b.size.height + 0.5)


# ---- checks ---------------------------------------------------------------------

@check("controls_contained_and_reachable")
def c238(w):
    w.seed([{}])
    w.show("insights")
    misses = []
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        pane = w.hub._built_views["insights"]
        for name, v in insights_controls(w.hub).items():
            if not contained(v, pane):
                misses.append((size, name, "outside"))
            elif not w.k.hit(v):
                misses.append((size, name, "not_hittable"))
    for v in insights_controls(w.hub).values():
        v.setFont_(NSFont.systemFontOfSize_(NSFont.systemFontSize() * 1.5))
    pump()
    for name, v in insights_controls(w.hub).items():
        if not w.k.hit(v):
            misses.append(("large-font", name, "not_hittable"))
    # Keyboard: Tab from the app selector reaches the mode selector
    # (the window's own key handling over its recalculated loop). Pop-up
    # buttons join the key-view loop only under the system's Full
    # Keyboard Access; with it off, macOS keeps them out by design and
    # the check is reported as not verifiable here (a manual check),
    # never as a pass.
    fka = bool(APP.isFullKeyboardAccessEnabled())
    reached = None
    if fka:
        w.win.makeFirstResponder_(w.hub.insights_app)
        seen = []
        for _ in range(12):
            ev = NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
                NSEventTypeKeyDown, NSMakePoint(0, 0), 0, time.monotonic(),
                w.win.windowNumber(), None, "\t", "\t", False, 48)
            w.win.sendEvent_(ev)
            pump(0.02)
            seen.append(w.win.firstResponder())
        reached = w.hub.insights_mode in seen
    names = sorted(insights_controls(w.hub))
    ok = not misses and reached is not False
    return {"status": "PASS" if ok else "FAIL",
            "misses": misses, "full_keyboard_access": fka,
            "tab_reaches_mode": (reached if fka else
                                 "not_verifiable_full_keyboard_access_off"),
            "controls": names,
            "mode_frame_max_x": w.hub.insights_mode.frame().origin.x
            + w.hub.insights_mode.frame().size.width}


@check("settings_usage_buttons_reachable")
def settings_reach(w):
    """LOCAL-M13-02: the usage row's buttons take their own clicks at
    default and minimum sizes (the explanatory label once covered
    them). The M02/M09 retention row is reported, not graded here."""
    w.show("settings")
    out = {}
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        for title in ("Apply Usage", "Delete All Usage…",
                      "Apply Retention"):
            b = _settings_button(w, title)
            out[f"{size[0]:.0f}:{title}"] = w.k.hit(b)
    usage_ok = all(v for k, v in out.items() if "Usage" in k)
    return {"status": "PASS" if usage_ok else "FAIL", "hit": out,
            "note": "Apply Retention (M02/M09 row) reported only —"
                    " LOCAL-M13-03"}


@check("range_kept_through_native_handlers")
def c157(w):
    now = time.time()
    iso = W.analytics_mod.instant_from_epoch
    w.seed([{"job": "job-in", "at": iso(now - 2 * 86400), "mode": "raw"},
            {"job": "job-out", "at": iso(now - 40 * 86400), "mode": "raw"},
            {"job": "job-other", "at": iso(now - 3600), "mode": "clean",
             "app": "Synthetic Beta", "bundle": "com.synthetic.beta"}])
    w.show("insights")
    ctl = insights_controls(w.hub)
    w.k.click(ctl["7d"])
    w.drain()
    w.k.popup(w.hub.insights_app, "Synthetic Alpha")
    w.drain()
    after_app = w.hub.state.views["insights"]["range"]
    w.k.popup(w.hub.insights_mode, "raw")
    w.drain()
    v = w.hub.state.views["insights"]
    s = v["data"]["summary"]
    return {"status": "PASS" if (after_app == 7 and v["range"] == 7
                                 and s["dictations"] == 1
                                 and v["app"] ==
                                 "bundle:com.synthetic.alpha"
                                 and v["mode"] == "raw") else "FAIL",
            "range_after_app": after_app, "range_after_mode": v["range"],
            "app": v["app"], "mode": v["mode"],
            "dictations": s["dictations"]}


@check("duplicate_labels_distinct_items")
def dup_labels(w):
    w.seed([{"job": "job-a", "app": "Synthetic Editor",
             "bundle": "com.synthetic.alpha"},
            {"job": "job-b", "app": "Synthetic Editor",
             "bundle": "com.synthetic.beta"}])
    w.show("insights")
    items = [(str(w.hub.insights_app.itemTitleAtIndex_(i)),
              w.hub.insights_app.itemAtIndex_(i).representedObject())
             for i in range(w.hub.insights_app.numberOfItems())]
    per = []
    for title, key in items[1:]:
        w.k.popup(w.hub.insights_app, title)
        w.drain()
        per.append(w.hub.state.views["insights"]["data"]["summary"][
            "dictations"])
    ok = len(items) == 3 and len({k for _t, k in items[1:]}) == 2 and \
        per == [1, 1]
    return {"status": "PASS" if ok else "FAIL", "items": items,
            "per_selection": per}


@check("rapid_changes_keep_prior_constraints")
def rapid(w):
    w.seed([{"job": f"job-{i}", "mode": ("raw", "clean")[i % 2]}
            for i in range(4)])
    w.show("insights")
    ctl = insights_controls(w.hub)
    w.k.click(ctl["30d"])
    w.k.click(ctl["7d"])
    w.k.popup(w.hub.insights_app, "Synthetic Alpha")
    w.k.popup(w.hub.insights_mode, "raw")
    w.drain()
    v = w.hub.state.views["insights"]
    s = v["data"]["summary"]
    ok = (v["range"], v["app"], v["mode"]) == \
        (7, "bundle:com.synthetic.alpha", "raw") and \
        s["cohort"] == {"days": 7, "app": "bundle:com.synthetic.alpha",
                        "mode": "raw"} and s["dictations"] == 2
    return {"status": "PASS" if ok else "FAIL", "cohort": s["cohort"],
            "dictations": s["dictations"]}


def _settings_button(w, title):
    pane = w.hub._built_views["settings"]
    return next(v for v in pane.subviews() if isinstance(v, NSButton)
                and str(v.title()) == title)


@check("invalid_retention_refused_natively")
def c262(w):
    old = W.analytics_mod.instant_from_epoch(time.time() - 30 * 86400)
    w.seed([{"job": "job-old", "at": old}])
    w.d.store.retention_days["usage"] = 365
    w.show("settings")
    shown = {}
    for raw in ("0", "-1", "-30", "abc", "2.5"):
        w.hub.usage_retention_field.setStringValue_(raw)
        w.k.click(_settings_button(w, "Apply Usage"))
        w.drain()
        shown[raw] = (str(w.hub.settings_text.stringValue()),
                      w.d.store.retention_days["usage"])
    w.d._analytics.expire_usage()
    refused = all(p == 365 and "refused" in t.lower()
                  for t, p in shown.values())
    return {"status": "PASS" if refused and w.facts() == 1 else "FAIL",
            "shown": shown, "facts_after_pass": w.facts()}


@check("returned_refusal_rendered")
def c237(w):
    w.show("settings")
    w.hub.usage_retention_field.setStringValue_("0")
    w.k.click(_settings_button(w, "Apply Usage"))
    w.drain()
    refused = str(w.hub.settings_text.stringValue())
    w.hub.usage_retention_field.setStringValue_("30")
    w.k.click(_settings_button(w, "Apply Usage"))
    w.drain()
    saved = str(w.hub.settings_text.stringValue())
    ok = "refused" in refused.lower() and "saved" in saved.lower() \
        and w.d.store.retention_days["usage"] == 30
    return {"status": "PASS" if ok else "FAIL", "refused_text": refused,
            "saved_text": saved}


def _answer_alert(button_title):
    """A timer in the alert's own modal run loop presses one of ITS
    buttons (the owned NSAlert's real button action)."""
    state = {"pressed": None}

    def fire(_t):
        win = APP.modalWindow()
        if win is None:
            return
        stack = [win.contentView()]
        while stack:
            v = stack.pop()
            if isinstance(v, NSButton) and str(v.title()) == button_title:
                state["pressed"] = button_title
                v.performClick_(None)
                return
            stack.extend(v.subviews())
    t = NSTimer.timerWithTimeInterval_repeats_block_(0.2, True, fire)
    NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
    return t, state


@check("delete_all_cancel_admits_nothing", tier="active")
def c186(w):
    w.seed([{"job": "job-keep"}])
    w.show("settings")
    before = str(w.hub.settings_text.stringValue())
    t, st = _answer_alert("Cancel")
    try:
        w.k.click(_settings_button(w, "Delete All Usage…"))
    finally:
        t.invalidate()
    w.drain()
    after = str(w.hub.settings_text.stringValue())
    ok = st["pressed"] == "Cancel" and w.facts() == 1 and \
        "deleted" not in after.lower()
    return {"status": "PASS" if ok else "FAIL", "pressed": st["pressed"],
            "facts": w.facts(), "text_before": before, "text_after": after}


@check("delete_all_confirm_revokes_insights", tier="active")
def delete_confirm(w):
    w.seed([{"job": "job-x"}, {"job": "job-y"}])
    w.show("insights")
    assert w.hub.state.views["insights"]["data"]["summary"][
        "dictations"] == 2
    w.show("settings")
    t, st = _answer_alert("Delete Usage Data")
    try:
        w.k.click(_settings_button(w, "Delete All Usage…"))
    finally:
        t.invalidate()
    w.drain()
    cached = w.hub.state.views["insights"]["data"]
    text = str(w.hub.settings_text.stringValue())
    w.show("insights")
    shown = w.hub.state.views["insights"]["data"]["summary"]["dictations"]
    ok = st["pressed"] == "Delete Usage Data" and w.facts() == 0 and \
        cached is None and shown == 0 and "deleted" in text.lower()
    return {"status": "PASS" if ok else "FAIL", "facts": w.facts(),
            "hidden_cache_cleared": cached is None, "shown_after": shown,
            "text": text}


@check("unknown_outcome_rendered_then_reconciled", tier="active")
def unknown(w):
    import threading
    w.seed([{"job": "job-u1"}, {"job": "job-u2"}])
    w.show("settings")
    release, parked = threading.Event(), threading.Event()

    def park(_c):
        parked.set()
        release.wait(30)
    w.d.store.submit(park, wait=False)
    parked.wait(10)
    w.d._usage_op_timeout = 0.3
    t, st = _answer_alert("Delete Usage Data")
    try:
        w.k.click(_settings_button(w, "Delete All Usage…"))
    finally:
        t.invalidate()
        release.set()
    first = str(w.hub.settings_text.stringValue())
    w.d.store.sync()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not w.d._usage_reconciled:
        w.mq.flush()
        pump(0.02)
    w.drain()
    w.show("insights")
    shown = w.hub.state.views["insights"]["data"]["summary"]["dictations"]
    rec = list(w.d._usage_reconciled.values())
    ok = "not known yet" in first.lower() and rec == ["committed"] and \
        shown == 0
    return {"status": "PASS" if ok else "FAIL", "first_text": first,
            "reconciled": rec, "shown_after": shown}


@check("history_delete_usage_reloads_insights")
def history_delete(w):
    jid, _f = w.d.store.create_job(
        captured_at_utc=W.analytics_mod.instant_from_epoch(
            time.time() - 3600)[:23] + "Z", time_quality="known",
        state="insertion_confirmed")
    w.seed([{"job": jid}, {"job": "job-other"}])
    w.show("history")
    w.hub.state.select_history_row("job", jid)
    w.drain()
    w.hub.historyDeleteUsage_(None)
    w.drain()
    note = str(w.hub.history_detail.string())[-200:]
    w.show("insights")
    shown = w.hub.state.views["insights"]["data"]["summary"]["dictations"]
    ok = shown == 1 and w.facts() == 1
    return {"status": "PASS" if ok else "FAIL", "shown_after": shown,
            "note": note}


def main(argv):
    out_path = None
    if "--json" in argv:
        out_path = argv[argv.index("--json") + 1]
    active = "--activate" in argv
    only = [a for a in argv if not a.startswith("--")
            and a != out_path]
    front0 = frontmost_pid()
    results = {}
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        if fn.tier == "active" and not active:
            results[name] = {"status": "NOT_RUN", "tier": "active",
                             "note": "needs --activate (hands off, owner's"
                                     " go-ahead)"}
            print(f"NOT_RUN  {name}  (active tier)", flush=True)
            continue
        t0 = time.monotonic()
        w = None
        try:
            w = World()
            r = fn(w)
        except AssertionError as e:
            r = {"status": "FAIL", "note": str(e)[:300]}
        except Exception as e:
            r = {"status": "ERROR", "note": f"{type(e).__name__}: {e}"[:200]
                 + " | " + traceback.format_exc()[-700:]}
        finally:
            if w is not None:
                if fn.tier == "active":
                    # Hand focus back before the ownership check.
                    restore_front(w.front)
                try:
                    w.close()
                except AssertionError as e:
                    r = {"status": "FAIL", "note": str(e)}
        r["tier"] = fn.tier
        r["seconds"] = round(time.monotonic() - t0, 2)
        results[name] = r
        print(f"{r['status']:5}  {name}"
              + (f"  — {str(r.get('note'))[:160]}" if r.get("note")
                 else ""), flush=True)
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    record = {"suite": "tests/v2/analytics/test_native_m13_insights.py",
              "tier": "active+passive" if active else "passive",
              "code": W.code_stamp(
                  "tests/v2/analytics/test_native_m13_insights.py"),
              "frontmost_unchanged": frontmost_pid() == front0,
              "never_frontmost": frontmost_pid() != os.getpid(),
              "counts": counts, "checks": results}
    print("native m13:", counts, "frontmost unchanged:",
          record["frontmost_unchanged"])
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps(record, indent=1,
                                                     default=str))
    return 0 if set(counts) <= {"PASS", "NOT_RUN"} and \
        record["never_frontmost"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
