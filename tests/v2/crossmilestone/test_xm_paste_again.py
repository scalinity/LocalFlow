"""POLICY-D03 — History Paste Again's explicit one-shot destination pick.

Invoking Paste Again authorizes nothing: the Hub steps aside and only the
user's next deliberate click names the destination, captured then as a
fresh M08 target; the History source is revalidated and the paste runs
through the app's own InsertionService. Every case drives the real
AppDelegate and InsertionService over the M08 world (synthetic apps A and
B, fields F1/F2/FB); the picker's NSEvent monitors are replaced by the
test acting as the user (focus moves, a click, Esc), and its timers by a
manual scheduler. No real application, window or clipboard is touched.

Run (AppKit headless, desktop isolated):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_paste_again.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

import xm_world as X  # noqa: E402
from xm_world import one, rows  # noqa: E402

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication()

CASES = []
_WRITES = ("ax_set_text", "ax_set_range", "paste_consumed", "ax_set_noop")


def case(finding, kind="regression"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


class Sched:
    """The picker's timers, run only when the test says so."""

    def __init__(self):
        self.calls = []

    def add(self, delay, fn):
        self.calls.append((delay, fn))

    def run(self, delay):
        due = [f for d, f in self.calls if d == delay]
        self.calls = [(d, f) for d, f in self.calls if d != delay]
        for f in due:
            f()


class Hint:
    def __init__(self):
        self.shown = []

    def show(self, text):
        self.shown.append(text)

    def hide(self):
        self.shown.append(None)


class Env:
    def __init__(self):
        from test_m08_remediation import AppEnv
        import localflow.app as app_mod
        from localflow.v2.ui import paste_picker
        self.pp = paste_picker
        self.a = a = AppEnv(consent=True, window=0.3)
        app_mod.AUDIO_DEBUG_DIR = a.h.tmp / "dbg"
        a.d.recorder.durations.extend([1.0] * 8)
        self.d, self.w, self.store = a.d, a.w, a.d.store
        self.sched = Sched()
        self.monitors = []
        self.picker = paste_picker.DestinationPicker(
            schedule=self.sched.add,
            install=lambda m, k: self.monitors.append("on") or ["mon"],
            remove=lambda h: self.monitors.append("off"))
        self.d._paste_picker, self.d._paste_hint = self.picker, Hint()
        self.ended = []
        real_end = self.d._paste_pick_ended
        self.d._paste_pick_ended = lambda o, show_hub: (
            self.ended.append(o), real_end(o, show_hub))

    def dictation(self, words="hello app"):
        """A normal PTT dictation of ``words`` into F1 (then F1 is
        cleared); returns (job_id, final text, final artifact id)."""
        self.d.supervisor.asr_text = words
        self.w.focus("A", "F1")
        job = self.a.dictate()
        self.idle()
        jid = job["job_id"]
        aid, text = one(self.store, "SELECT artifact_id, content_text FROM"
                        " artifacts WHERE job_id=? AND role="
                        "'applied_output' ORDER BY rowid DESC", (jid,))
        assert self.w.text("F1").strip() == text, "fixture: dictation"
        f1 = self.w.fields["F1"]
        f1.text, f1.sel = "", (0, 0)
        return jid, text, aid

    def invoke(self, jid, text, aid):
        return self.d.hubPasteText(text, job_id=jid,
                                   source={"artifact_id": aid}) or {}

    def click(self, app, fid):
        """The user's deliberate click: focus lands in (app, fid), the
        monitor sees the mouse-down, the settle timer fires."""
        self.w.focus(app, fid)
        self.picker.mouse_down(self.w.apps[app]["pid"])
        self.sched.run(self.pp.CLICK_SETTLE_SEC)
        self.idle()

    def idle(self):
        from m08_world import wait_for
        assert wait_for(lambda: not self.a.svc.pending, 10), "service busy"
        self.store.sync()

    def stamp(self):
        return self.w.effects[-1][0] if self.w.effects else 0

    def writes(self, since, fids=None):
        return [e[:3] for e in self.w.effects if e[0] > since
                and e[1] in _WRITES and (fids is None or e[2] in fids)]

    def repastes(self):
        return one(self.store, "SELECT COUNT(*) FROM usage_facts WHERE"
                   " kind='repaste'")[0]

    def close(self):
        self.picker.cancel("test_end")
        self.a.close()


def _with_env(fn):
    e = Env()
    try:
        return fn(e)
    finally:
        e.close()


@case("POLICY-D03 1 (invoking Paste Again and an app merely coming to the"
      " front pastes nothing)")
def d03_invoke_and_incidental_front_app_paste_nothing():
    def run(e):
        jid, text, aid = e.dictation()
        since = e.stamp()
        out = e.invoke(jid, text, aid)
        e.w.focus("A", "F1")          # A comes to the front on its own
        time.sleep(0.3)
        e.idle()
        assert out.get("outcome") == "choosing_destination" \
            and e.picker.active and e.monitors == ["on"], (out, e.monitors)
        assert not e.writes(since), e.writes(since)
    _with_env(run)


@case("POLICY-D03 2 (a deliberate click on field F2 of app A captures a"
      " fresh target and pastes the History text there, once)")
def d03_click_in_app_pastes_there():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.click("A", "F2")
        f2 = e.writes(since, ("F2",))
        assert len(f2) == 1 and not e.writes(since, ("F1", "FB")) \
            and e.w.text("F2").startswith(text), (
                f"writes {e.writes(since)}, F2 {e.w.text('F2')!r}")
        assert e.ended == ["repaste_queued"] and not e.picker.active \
            and e.monitors == ["on", "off"], (e.ended, e.monitors)
    _with_env(run)


@case("POLICY-D03 3 (another app coming to the front before any click"
      " pastes nothing)")
def d03_focus_change_without_click_pastes_nothing():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.w.focus("B", "FB")
        time.sleep(0.3)
        e.idle()
        assert not e.writes(since) and e.picker.active, e.writes(since)
    _with_env(run)


@case("POLICY-D03 4 (the paste goes only to the destination clicked, here"
      " field FB of app B)")
def d03_click_in_other_app_pastes_only_there():
    def run(e):
        jid, text, aid = e.dictation()
        e.w.fields["FB"].text, e.w.fields["FB"].sel = "", (0, 0)
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.click("B", "FB")
        assert e.w.text("FB").strip() == text \
            and len(e.writes(since, ("FB",))) == 1 \
            and not e.writes(since, ("F1", "F2")), (
                f"writes {e.writes(since)}, FB {e.w.text('FB')!r}")
    _with_env(run)


@case("POLICY-D03 5 (Esc, or the timeout, before a click pastes nothing,"
      " and a later click does nothing)")
def d03_cancel_before_click_pastes_nothing():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.picker.key_down(e.pp.ESC_KEY_CODE)
        e.click("A", "F2")
        e.invoke(jid, text, aid)
        e.sched.run(e.pp.PICK_TIMEOUT_SEC)
        e.click("B", "FB")
        assert not e.writes(since) and e.ended == ["cancelled",
                                                   "timed_out"], (
            e.writes(since), e.ended)
    _with_env(run)


@case("POLICY-D03 6 (a destination that changes after the click is refused"
      " by M08 revalidation — no fallback target)")
def d03_target_changed_after_pick_is_refused():
    def run(e):
        jid, text, aid = e.dictation()
        real = e.a.svc.paste_text

        def moved(*a, **kw):
            e.w.focus("A", "F1")      # focus leaves the clicked FB
            return real(*a, **kw)
        e.a.svc.paste_text = moved
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.click("B", "FB")
        states = [r[0] for r in rows(e.store, "SELECT state FROM insertions"
                                     " WHERE job_id=? ORDER BY rowid",
                                     (jid,))]
        assert not e.writes(since) and states[-1] in (
            "target_changed", "saved_not_inserted"), (
            f"writes {e.writes(since)}, insertion states {states}")
    _with_env(run)


@case("POLICY-D03 7 (a source deleted, or purged, while the destination is"
      " being chosen is refused; nothing stale is pasted)")
def d03_source_deleted_or_purged_while_choosing():
    import localflow.app as app_mod

    def run(e):
        jid, text, aid = e.dictation()
        jid2, text2, aid2 = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda f, *a: f(*a)
        try:
            e.store.delete_everywhere("job", jid)
        finally:
            app_mod.AppHelper.callAfter = real
        assert not e.picker.active and e.ended == ["source_deleted"], (
            "deleting the source did not end the pick", e.ended)
        e.click("A", "F2")
        e.invoke(jid2, text2, aid2)
        e.store.submit(lambda db: e.store._purge_artifact(aid2))
        e.click("A", "F2")
        assert not e.writes(since) and e.ended == [
            "source_deleted", "source_purged"], (e.writes(since), e.ended)
    _with_env(run)


@case("POLICY-D03 8 (the pick stays bound to the History source invoked,"
      " whatever History renders or selects meanwhile)")
def d03_pick_bound_to_invoked_source():
    def run(e):
        from m09_world import MainQueue
        from test_xm_g06_c2 import make_hub, show_history_row
        jid, text, aid = e.dictation()
        with MainQueue() as mq:
            hub = make_hub(e.a.h)
            e.d._hub = hub
            show_history_row(hub, mq, jid)
            hub.historyPasteAgain_(None)
            # A newer dictation arrives and History moves to it.
            jid2, text2, _aid2 = e.dictation("later words here")
            show_history_row(hub, mq, jid2)
            e.w.fields["FB"].text, e.w.fields["FB"].sel = "", (0, 0)
            e.click("B", "FB")
        assert text != text2 and e.w.text("FB").strip() == text, (
            f"pasted {e.w.text('FB')!r}; invoked {text!r}, later {text2!r}")
    _with_env(run)


@case("POLICY-D03 9 (a successful paste is one insertion and one repaste"
      " activity fact, never repeated)")
def d03_success_is_counted_once():
    def run(e):
        jid, text, aid = e.dictation()
        ins0 = one(e.store, "SELECT COUNT(*) FROM insertions")[0]
        rep0 = e.repastes()
        e.invoke(jid, text, aid)
        e.click("A", "F2")
        e.picker.mouse_down()          # a stray second click
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        ins = one(e.store, "SELECT COUNT(*) FROM insertions")[0] - ins0
        dictations = one(e.store, "SELECT COUNT(*) FROM usage_facts WHERE"
                         " kind='dictation'")[0]
        assert (ins, e.repastes() - rep0, dictations) == (1, 1, 1), (
            f"insertions +{ins}, repaste facts +{e.repastes() - rep0},"
            f" dictation facts {dictations}")
    _with_env(run)


@case("POLICY-D03 10 (normal push-to-talk dictation after a pick still"
      " inserts automatically into its captured destination)")
def d03_normal_dictation_unchanged():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        e.click("A", "F2")
        e.w.focus("A", "F1")          # the user is back in F1 to dictate
        since = e.stamp()
        job = e.a.dictate()
        e.idle()
        state = one(e.store, "SELECT state FROM jobs WHERE job_id=?",
                    (job["job_id"],))[0]
        assert state == "insertion_confirmed" \
            and len(e.writes(since, ("F1",))) == 1 \
            and not e.writes(since, ("F2", "FB")) \
            and not e.picker.active, (state, e.writes(since))
    _with_env(run)


@case("POLICY-D03 review 1 (a click owned by an app that does not come to"
      " the front — a menu-bar item, a banner — pastes nothing into the"
      " app that is in front)")
def d03_click_not_owned_by_front_app_pastes_nothing():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.w.focus("A", "F1")          # A is in front ...
        e.picker.mouse_down(e.w.apps["B"]["pid"])   # ... B's item clicked
        e.sched.run(e.pp.CLICK_SETTLE_SEC)
        e.idle()
        assert not e.writes(since) and e.ended == [
            "destination_not_in_front"], (e.writes(since), e.ended)
    _with_env(run)


@case("POLICY-D03 review 2a (reopening the Hub cancels a waiting pick; a"
      " later click pastes nothing)")
def d03_reopening_hub_cancels_the_pick():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        e.d._hub_blocks_show = lambda: True   # defer the show: no window
        e.d.openHub_(None)
        e.click("A", "F2")
        assert not e.picker.active and not e.writes(since) \
            and e.ended == ["reopened"], (e.writes(since), e.ended)
    _with_env(run)


@case("POLICY-D03 review 2b (a second Paste Again replaces the first pick"
      " and pastes its own source)")
def d03_second_paste_again_replaces_the_first():
    def run(e):
        jid, text, aid = e.dictation()
        jid2, text2, aid2 = e.dictation("later words here")
        e.w.fields["FB"].text, e.w.fields["FB"].sel = "", (0, 0)
        e.invoke(jid, text, aid)
        e.invoke(jid2, text2, aid2)
        e.click("B", "FB")
        assert e.w.text("FB").strip() == text2 and e.ended == [
            "superseded", "repaste_queued"], (e.w.text("FB"), e.ended)
    _with_env(run)


@case("POLICY-D03 review 3 (a busy store during the source check ends the"
      " pick honestly; nothing is pasted)")
def d03_source_check_timeout_ends_the_pick():
    def run(e):
        jid, text, aid = e.dictation()
        e.invoke(jid, text, aid)
        since = e.stamp()
        real = e.store.submit

        def busy(*a, **k):
            raise TimeoutError("store writer did not respond")
        e.store.submit = busy
        try:
            e.click("A", "F2")
        finally:
            e.store.submit = real
        assert not e.writes(since) and not e.picker.active \
            and e.ended == ["source_unverified"], (e.writes(since), e.ended)
    _with_env(run)


@case("POLICY-D03 review 4 (a pick that ends on its own never brings the"
      " Hub forward, and nothing does while a dictation is in flight)")
def d03_pick_ending_never_steals_focus_from_dictation():
    def run(e):
        jid, text, aid = e.dictation()
        import types
        opened = []
        e.d._hub = types.SimpleNamespace(
            window=types.SimpleNamespace(orderOut_=lambda s: None),
            pasteAgainEnded=lambda outcome: None)
        e.d.openHub_ = lambda sender: opened.append(sender)
        e.invoke(jid, text, aid)
        e.sched.run(e.pp.PICK_TIMEOUT_SEC)          # ends on its own
        timed_out = list(opened)
        e.invoke(jid, text, aid)
        e.w.focus("A", "F1")
        e.a.h.press_release()                       # a dictation starts
        e.picker.key_down(e.pp.ESC_KEY_CODE)        # Esc mid-dictation
        during = list(opened)
        from test_xm_g06_c2 import _run_inline
        _run_inline(e.a, snapshot=True)
        state = one(e.store, "SELECT state FROM jobs ORDER BY rowid DESC")[0]
        e.invoke(jid, text, aid)
        e.picker.key_down(e.pp.ESC_KEY_CODE)        # Esc while idle
        assert (timed_out, during, state, len(opened)) == (
            [], [], "insertion_confirmed", 1), (
            timed_out, during, state, opened)
    _with_env(run)


# =============================================================================
# runner (the cross-milestone suites' record shape)
# =============================================================================

def main(argv):
    out_path = None
    if "--json" in argv:
        i = argv.index("--json")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = set(argv)
    results = []
    for fn in CASES:
        if names and fn.__name__ not in names:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", (str(e) or "assertion")[:600]
        except Exception as e:  # noqa: BLE001
            status = "ERROR"
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + traceback.format_exc()[-1200:])
        from test_xm_g06_c2 import redact
        detail = redact(detail)
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("xm paste again:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_paste_again.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_paste_again.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
