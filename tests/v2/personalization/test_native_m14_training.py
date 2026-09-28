"""NATIVE functional qualification of the M14 Hub surfaces (M14
remediation; corpus C211–C219 and the native halves of M14-AUDIT-11/16/
17/18/29) — real AppKit/PyObjC, the real HubController over the real
coordinator (the lifecycle Harness) and a synthetic temporary store.

Ownership and safety: this process owns the window it drives, placed
off-screen; every event is BUILT for its own window and DELIVERED
through this application's own dispatch (M10's ``Driver``: nothing is
posted to the system event stream). The app is never activated
(PASSIVE tier — no M14 flow opens a modal alert) and the frontmost
application is checked unchanged after every check. Under
``run_isolated`` the general pasteboard is private. No real store,
History, notes, usage or configuration is read or written; exports go
to temporary folders. Text fields are filled with their own setter (the
handlers read the field value); buttons and pop-ups are operated with
synthetic events so the real action methods run.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/personalization/test_native_m14_training.py [--json OUT]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "ui"))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))

from test_native_m10_panes import APP, Driver, frontmost_pid, pump  # noqa
import m14_world as W  # noqa: E402
from test_lifecycle import Harness  # noqa: E402
from m09_world import MainQueue  # noqa: E402

from AppKit import (NSButton, NSFont, NSMakePoint, NSMakeSize,  # noqa
                    NSPopUpButton, NSTextField)

from localflow.v2 import ids  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.ui import hub as hub_mod  # noqa: E402
from localflow.v2.ui.state import VIEWS  # noqa: E402

CHECKS = {}
TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"


def check(name, cases):
    def deco(fn):
        fn.cases = cases
        CHECKS[name] = fn
        return fn
    return deco


class World:
    """The real coordinator + Hub, the Hub window off-screen, main-thread
    callbacks queued and flushed on this (main) thread."""

    def __init__(self):
        self.front = frontmost_pid()
        self.h = Harness(durations=[1.0] * 4)
        self.mq = MainQueue().__enter__()
        self.d = self.h.d
        import test_m14_remediation as R
        self.hub = R._make_hub(self.h)
        self.win = self.hub.window
        self.win.setFrameOrigin_(NSMakePoint(-20000, -20000))
        self.win.orderFrontRegardless()
        self.drain()
        self.k = Driver(self.win)
        # m14_world's producer-shaped seeding, bound to this store.
        mw = object.__new__(W.MWorld)
        mw.store = self.d.store
        mw._seq = 0
        mw.training = TrainingDataService(self.d.store)
        mw.review = self.d._review
        mw.learning = self.d._learning
        self.mw = mw
        self.d.store.append_consent("enabled", note="m14-native")

    def drain(self, timeout=60):
        assert self.mq.drain(self.hub.state, timeout), "Hub work stuck"
        pump()

    def wait_text(self, view, changed_from, timeout=60):
        """Wait for a background action's completion to reach ``view``."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.hub.state.wait_for_queries(0.2)
            self.mq.flush()
            pump(0.02)
            if str(view.string()) != changed_from:
                return str(view.string())
        raise AssertionError("background action never reported")

    def show(self, view):
        self.hub._select_view_index(VIEWS.index(view))
        self.drain()

    def training_tab(self, tab):
        self.show("models")
        self.hub.state.select_models_subview("training")
        self.drain()
        self.hub.state.select_training_tab(tab)
        self.drain()

    def button(self, title, root=None):
        root = root or self.win.contentView()
        found = []

        def walk(v):
            if isinstance(v, NSButton) and not isinstance(
                    v, NSPopUpButton) and str(v.title()) == title \
                    and not v.isHiddenOrHasHiddenAncestor():
                found.append(v)
            for s in v.subviews():
                walk(s)
        walk(root)
        assert found, f"no visible button {title!r}"
        return found[0]

    def rows(self, sql, args=()):
        return self.d.store.submit(lambda c: c.execute(sql, args).fetchall())

    def close(self):
        try:
            self.win.orderOut_(None)
            self.hub.state.close()
        finally:
            self.mq.__exit__(None, None, None)
            self.h.close()
        assert frontmost_pid() != os.getpid(), "this process was activated"


def teach(w, raw=TEACH_RAW, fix=TEACH_FIX, *, example=True):
    j = W.MWorld.job(w.mw, raw, example=example, audio=False)
    cid = w.d._learning.teach_correction(j["job_id"], fix)["candidate_id"]
    return j, cid


def choose_candidate(w, cid):
    popup = w.hub.review_candidate_popup
    titles = list(popup.itemTitles())
    idx = next(i for i in range(popup.numberOfItems())
               if popup.itemAtIndex_(i).representedObject() == cid)
    got = w.k.popup(popup, titles[idx])
    return popup.selectedItem().representedObject() == cid, got


def status(w, cid):
    return w.rows("SELECT status FROM learning_candidates WHERE"
                  " candidate_id=?", (cid,))[0][0]


# ---- checks ---------------------------------------------------------------------

@check("review_candidate_approve_reject_label", ["LF-M14-C211"])
def c211(w):
    j1, c1 = teach(w)
    j2, c2 = teach(w, "ship the clod branch now", "ship the Claude branch now")
    w.training_tab("review")
    ok1, _ = choose_candidate(w, c1)
    w.k.click(w.button("Approve Cand."))
    w.drain()
    ok2, _ = choose_candidate(w, c2)
    w.k.click(w.button("Reject Cand."))
    w.drain()
    w.k.popup(w.hub.review_kind, "recognition_error")
    w.hub.review_example.setStringValue_(j1["example_id"])
    w.k.click(w.button("Record Label"))
    w.drain()
    labels = w.rows("SELECT edit_kind FROM correction_labels WHERE"
                    " example_id=?", (j1["example_id"],))
    got = (status(w, c1), status(w, c2), labels)
    ok = ok1 and ok2 and got == ("approved", "rejected",
                                 [("recognition_error",)])
    return {"status": "PASS" if ok else "FAIL", "observed": got}


@check("reorder_after_render_acts_on_rendered_item", ["LF-M14-C212"])
def c212(w):
    _j1, c1 = teach(w)
    w.training_tab("review")
    popup = w.hub.review_candidate_popup
    before = [popup.itemAtIndex_(i).representedObject()
              for i in range(popup.numberOfItems())]
    # A newer candidate arrives after render (it would sort first).
    _j2, c2 = teach(w, "ping the clod room", "ping the Claude room")
    ok_sel, _ = choose_candidate(w, c1)
    w.k.click(w.button("Approve Cand."))
    w.drain()
    got = (status(w, c1), status(w, c2))
    ok = ok_sel and c2 not in before and got == ("approved", "pending")
    return {"status": "PASS" if ok else "FAIL", "observed": got}


@check("deletion_while_form_open_refuses", ["LF-M14-C213"])
def c213(w):
    j1, c1 = teach(w)
    w.training_tab("review")
    choose_candidate(w, c1)
    w.d.store.delete_everywhere("job", j1["job_id"])
    w.k.click(w.button("Approve Cand."))
    w.drain()
    shown = str(w.hub.review_text.string())
    entries = w.rows("SELECT COUNT(*) FROM vocabulary_entries WHERE"
                     " canonical='module'")[0][0]
    ok = status(w, c1) == "stale" and entries == 0 and \
        TEACH_RAW not in shown
    return {"status": "PASS" if ok else "FAIL",
            "observed": {"candidate": status(w, c1), "entries": entries}}


@check("job_only_candidate_selectable", ["LF-M14-C214"])
def c214(w):
    _j, cid = teach(w, example=False)
    w.training_tab("review")
    ok_sel, _ = choose_candidate(w, cid)
    w.k.click(w.button("Approve Cand."))
    w.drain()
    examples = w.rows("SELECT COUNT(*) FROM training_examples")[0][0]
    got = (status(w, cid), examples)
    ok = ok_sel and got == ("approved", 0)
    return {"status": "PASS" if ok else "FAIL", "observed": got}


@check("ab_pair_shows_texts_and_binds_order", ["LF-M14-C215"])
def c215(w):
    t1 = W.transform_task(w.d.store, "shared source alpha",
                          ["Alpha output one", "Alpha output two"])
    w.training_tab("review")
    w.hub.review_pair_task.setStringValue_(t1["task_key"])
    w.hub.state.select_training_tab("review")
    w.drain()
    shown = str(w.hub.review_text.string())
    visible = all(s in shown for s in ("shared source alpha",
                                       "Alpha output one",
                                       "Alpha output two"))
    a, b = (c["candidate_id"] for c in t1["candidates"])
    w.k.click(w.button("prefer B"))
    w.drain()
    # The second task shows B first (display order swapped).
    t2 = W.transform_task(w.d.store, "shared source bravo",
                          ["Bravo shown second", "Bravo shown first"],
                          display=[1, 0])
    w.hub.review_pair_task.setStringValue_(t2["task_key"])
    w.hub.state.select_training_tab("review")
    w.drain()
    first, second = t2["candidates"][1]["candidate_id"], \
        t2["candidates"][0]["candidate_id"]
    recorded = {}
    for title, judgment in (("Pair: prefer A", "prefer_a"), ("tie", "tie"),
                            ("neither", "neither"),
                            ("uncertain", "uncertain")):
        w.k.click(w.button(title))
        w.drain()
        recorded[judgment] = w.rows(
            "SELECT candidate_id, candidate_b_id FROM"
            " preference_observations WHERE task_key=? AND judgment=?",
            (t2["task_key"], judgment))
    r1 = w.rows("SELECT candidate_id, candidate_b_id, judgment FROM"
                " preference_observations WHERE task_key=?",
                (t1["task_key"],))
    ok = visible and r1 == [(a, b, "prefer_b")] and all(
        v == [(first, second)] for v in recorded.values())
    return {"status": "PASS" if ok else "FAIL", "visible": visible,
            "t1": r1, "t2": recorded}


@check("split_assign_export_validate_and_refusal", ["LF-M14-C216"])
def c216(w):
    for i in range(10):
        W.MWorld.ready_asr(w.mw, f"native asr witness {i} words")
    w.training_tab("splits")
    w.k.click(w.button("Assign (new version)"))
    w.drain()
    version = w.rows("SELECT COUNT(*) FROM split_assignments")[0][0]
    w.hub.state.select_training_tab("export")
    w.drain()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="m14-native-"))
    try:
        dest = tmp / "dataset"
        w.hub.export_dest.setStringValue_(str(dest))
        before = str(w.hub.export_text.string())
        w.k.click(w.button("Export", root=w.hub.export_pane))
        done = w.wait_text(w.hub.export_text, before)
        if "exporting" in done:
            done = w.wait_text(w.hub.export_text, done)
        built = (dest / "dataset_manifest.json").is_file()
        # The completion's own Training refresh publishes first (a
        # person cannot click within it); then Validate.
        w.drain()
        w.k.click(w.button("Validate"))
        w.drain()
        valid = "valid: True" in str(w.hub.export_text.string())
        # A folder of the user's own files: refused, untouched.
        user = tmp / "mine"
        user.mkdir()
        (user / "keep.txt").write_text("keep me")
        w.hub.export_dest.setStringValue_(str(user))
        before = str(w.hub.export_text.string())
        w.k.click(w.button("Export", root=w.hub.export_pane))
        refusal = w.wait_text(w.hub.export_text, before)
        if "exporting" in refusal:
            refusal = w.wait_text(w.hub.export_text, refusal)
        kept = (user / "keep.txt").read_text() == "keep me" and \
            sorted(p.name for p in user.iterdir()) == ["keep.txt"]
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    ok = (version == 1 and built and "complete" in done and valid
          and "destination exists" in refusal and kept)
    return {"status": "PASS" if ok else "FAIL", "versions": version,
            "built": built, "valid": valid, "refused_kept": kept}


@check("your_voice_generate_and_exclude", ["LF-M14-C217"])
def c217(w):
    words = [f"n{i}w{k}" for i in range(10) for k in range(205)]
    examples = []
    for i in range(10):
        chunk = " ".join(words[i * 205:(i + 1) * 205])
        examples.append(W.MWorld.job(w.mw, chunk, audio=False))
    w.show("insights")
    w.hub.state.select_insights_subview("voice")
    w.drain()
    before = str(w.hub.voice_pane.text.string())
    w.k.click(w.button("Generate"))
    shown = w.wait_text(w.hub.voice_pane.text, before)
    snap = w.d._profile.current()
    cards = snap and snap["cards"]
    target = cards[0]["evidence_example_ids"][0] if cards else None
    if target is None:
        return {"status": "FAIL", "note": "no evidence-linked card"}
    w.hub.voice_pane.exclude_field.setStringValue_(target)
    w.k.click(w.button("Exclude"))
    w.drain()
    after = w.d._profile.current()
    state = w.rows("SELECT state FROM training_examples WHERE"
                   " example_id=?", (target,))[0][0]
    ok = "Interpretive cards" in shown and after["state"] == \
        "invalidated" and state != "deleted"
    return {"status": "PASS" if ok else "FAIL",
            "cards": len(cards or []), "after": after["state"],
            "training_state": state}


def _controls(view):
    out = []

    def walk(v):
        if isinstance(v, (NSButton, NSPopUpButton, NSTextField)) and \
                not v.isHiddenOrHasHiddenAncestor() and (
                    not isinstance(v, NSTextField) or v.isEditable()):
            out.append(v)
        for s in v.subviews():
            walk(s)
    walk(view)
    return out


def _contained(v, pane):
    """Inside the pane AND inside the window's visible content (the
    Training panes keep a fixed frame wider than the visible area at the
    minimum window size, so the pane alone is not the boundary)."""
    content = pane.window().contentView()
    for box, ref in ((v.convertRect_toView_(v.bounds(), pane),
                      pane.bounds()),
                     (v.convertRect_toView_(v.bounds(), content),
                      content.bounds())):
        if not (box.origin.x >= -0.5 and box.origin.y >= -0.5
                and box.origin.x + box.size.width <= ref.size.width + 0.5
                and box.origin.y + box.size.height
                <= ref.size.height + 0.5):
            return False
    return True


@check("controls_contained_hittable_and_scaled", ["LF-M14-C218"])
def c218(w):
    misses = []
    panes = {}
    for tab in ("review", "splits", "export"):
        w.training_tab(tab)
        panes[tab] = getattr(w.hub, f"{tab}_pane")
        for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
            w.win.setContentSize_(NSMakeSize(*size))
            pump()
            for v in _controls(panes[tab]):
                if not _contained(v, panes[tab]):
                    misses.append((tab, size[0], type(v).__name__,
                                   str(getattr(v, "title", lambda: "")()),
                                   "outside"))
                elif not w.k.hit(v):
                    misses.append((tab, size[0], type(v).__name__,
                                   str(getattr(v, "title", lambda: "")()),
                                   "not_hittable"))
    w.show("insights")
    w.hub.state.select_insights_subview("voice")
    w.drain()
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        for v in _controls(w.hub.voice_pane.view):
            if not w.k.hit(v):
                misses.append(("voice", size[0], type(v).__name__,
                               "not_hittable"))
    # Enlarged text on the review pane's controls.
    w.training_tab("review")
    for v in _controls(w.hub.review_pane):
        v.setFont_(NSFont.systemFontOfSize_(NSFont.systemFontSize() * 1.5))
    pump()
    for v in _controls(w.hub.review_pane):
        if not w.k.hit(v):
            misses.append(("review-large", type(v).__name__,
                           "not_hittable"))
    fka = bool(APP.isFullKeyboardAccessEnabled())
    return {"status": "PASS" if not misses else "FAIL",
            "misses": misses[:20],
            "keyboard_traversal": ("checked" if fka else
                                   "not_verifiable_full_keyboard_access_off"
                                   )}


@check("unknown_outcome_reconciles_without_duplicate", ["LF-M14-C219"])
def c219(w):
    _j, cid = teach(w)
    w.training_tab("review")
    learning = w.d._learning
    real = learning.approve
    calls = []

    def late(*a, **kw):
        calls.append(kw.get("operation_id"))
        out = real(*a, **kw)
        if len(calls) == 1:
            raise TimeoutError("synthetic: the store answered late")
        return out
    learning.approve = late
    try:
        choose_candidate(w, cid)
        w.k.click(w.button("Approve Cand."))
        w.drain()
        first = str(w.hub.review_text.string())
        entries_after_first = w.rows("SELECT entry_id, revision FROM"
                                     " vocabulary_entries")
        # The user's retry: the same visible action again (an unknown
        # outcome leaves the rendered queue and selection in place).
        w.k.click(w.button("Approve Cand."))
        w.drain()
    finally:
        learning.approve = real
    entries = w.rows("SELECT entry_id, revision FROM vocabulary_entries")
    ok = "unknown" in first and len(calls) == 2 and \
        calls[0] == calls[1] and entries == entries_after_first and \
        status(w, cid) == "approved"
    return {"status": "PASS" if ok else "FAIL", "first_note": first[:120],
            "same_operation_id": len(calls) == 2 and calls[0] == calls[1],
            "entries": len(entries)}


@check("history_teach_binds_rendered_final", ["LF-M14-C005"])
def teach_native(w):
    s = w.d.store
    job, _fam = s.create_job()
    s.write_text_artifact(job_id=job, stage="asr", role="raw_transcript",
                          text=TEACH_RAW, retention_class="history")
    f1 = s.write_text_artifact(job_id=job, stage="cleanup",
                               role="applied_output", text=TEACH_RAW,
                               retention_class="history")
    s.update_job_state(job, "confirmed")
    seen = {}
    learning = w.d._learning
    real = learning.teach_correction

    def spy(job_id, corrected, **kw):
        seen.update(kw)
        return real(job_id, corrected, **kw)
    learning.teach_correction = spy
    try:
        w.show("history")
        w.hub.state.select_history_row("job", job)
        w.drain()
        w.hub.teach_field.setStringValue_(TEACH_FIX)
        w.k.click(w.button("Teach"))
        w.drain()
    finally:
        learning.teach_correction = real
    made = w.rows("SELECT COUNT(*) FROM learning_candidates WHERE"
                  " job_id=?", (job,))[0][0]
    ok = seen.get("expected_final_artifact_id") == f1 and \
        seen.get("expected_final_sha256") == ids.sha256_text(TEACH_RAW) \
        and made == 1
    return {"status": "PASS" if ok else "FAIL", "bound": bool(seen),
            "candidates": made}


def main(argv):
    out_path = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = [a for a in argv if not a.startswith("--") and a != out_path]
    front0 = frontmost_pid()
    results = {}
    for name, fn in CHECKS.items():
        if only and name not in only:
            continue
        t0 = time.monotonic()
        w = None
        try:
            w = World()
            r = fn(w)
        except AssertionError as e:
            r = {"status": "FAIL", "note": str(e)[:300]}
        except Exception as e:  # noqa: BLE001
            r = {"status": "ERROR", "note": f"{type(e).__name__}: {e}"[:200]
                 + " | " + traceback.format_exc()[-700:]}
        finally:
            if w is not None:
                try:
                    w.close()
                except AssertionError as e:
                    r = {"status": "FAIL", "note": str(e)}
        r["cases"] = fn.cases
        r["tier"] = "passive"
        r["seconds"] = round(time.monotonic() - t0, 2)
        results[name] = r
        print(f"{r['status']:5}  {name}"
              + (f"  — {str(r.get('note'))[:160]}" if r.get("note")
                 else ""), flush=True)
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    record = {"suite": "tests/v2/personalization/test_native_m14_training.py",
              "tier": "passive",
              "code": W.code_stamp(
                  "tests/v2/personalization/test_native_m14_training.py"),
              "frontmost_unchanged": frontmost_pid() == front0,
              "never_frontmost": frontmost_pid() != os.getpid(),
              "full_keyboard_access": bool(
                  APP.isFullKeyboardAccessEnabled()),
              "counts": counts, "checks": results}
    print("native m14:", counts, "frontmost unchanged:",
          record["frontmost_unchanged"])
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps(record, indent=1,
                                                     default=str))
    return 0 if set(counts) <= {"PASS"} and record["never_frontmost"] \
        else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
