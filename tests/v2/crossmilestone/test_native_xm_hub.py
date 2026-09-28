"""NATIVE functional qualification of the Hub surfaces the cross-milestone
remediation touched (GATE-G07; MERGED-X04/X08/X10/X12/X13/X15,
LOCAL-XM-01, the Settings Apply Retention geometry lead) — real
AppKit/PyObjC, the real HubController over the real coordinator (the
lifecycle Harness) and a synthetic temporary store.

The M14 native harness (tests/v2/personalization/test_native_m14_training
.py ``World``): this process owns the off-screen Hub window it drives;
every event is BUILT for its own window and DELIVERED through this
application's own dispatch (nothing is posted to the system event
stream); the app is never activated (PASSIVE tier) and the frontmost
application is checked unchanged. Under ``run_isolated`` the general
pasteboard is private. Text fields are filled with their own setters;
buttons, table rows and pop-ups are operated with synthetic events so
the real action methods run. A pop-up choice is verified after the
keyboard driver made it (the driver can overshoot by one item), never
assumed. Functional only — no visual judgment.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/crossmilestone/test_native_xm_hub.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (HERE.parent, ROOT / "tests" / "v2" / "personalization",
          ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import test_native_m14_training as N  # noqa: E402  (World, Driver)
from test_native_m10_panes import APP, frontmost_pid, pump  # noqa: E402
import xm_world as X  # noqa: E402

from AppKit import NSMakeSize  # noqa: E402

from localflow.v2.ui import hub as hub_mod  # noqa: E402

CHECKS = {}


def check(name, covers):
    def deco(fn):
        fn.covers = covers
        CHECKS[name] = fn
        return fn
    return deco


def click_row(w, table_name, key, value):
    """Select the rendered row through the real NSTableView's own
    selection call — AppKit then notifies the Hub delegate exactly as it
    does for a user's selection. (A MOUSE click selects a row only in an
    ACTIVE window; this passive tier never activates — the mouse path is
    the active-tier launcher's.) Returns whether the table selected it."""
    import Foundation
    table = getattr(w.hub, table_name)
    rows = (w.hub._history_flat if table_name == "history_table"
            else w.hub._rendered_rows.get(table_name)) or []
    idx = next((i for i, r in enumerate(rows) if r.get(key) == value),
               None)
    if idx is None:
        return False
    table.selectRowIndexes_byExtendingSelection_(
        Foundation.NSIndexSet.indexSetWithIndex_(idx), False)
    w.drain()
    return table.selectedRow() == idx


@check("transform_row_click_fills_instruction_and_update_keeps_it",
       ["LOCAL-XM-01", "MERGED-X04"])
def n_transform_editor(w):
    tfs = w.d._tf_store
    a = tfs.add_transform(name="Native A", mode="custom",
                          prompt="NATIVE INSTRUCTION ALPHA", auto_apply=True)
    b = tfs.add_transform(name="Native B", mode="custom",
                          prompt="NATIVE INSTRUCTION BETA", auto_apply=True)
    w.show("transforms")
    ok_a = click_row(w, "transforms_table", "transform_id", a.transform_id)
    ok_b = click_row(w, "transforms_table", "transform_id", b.transform_id)
    shown = str(w.hub.tf_prompt.string())
    # Another supported write opts B out while the editor is open.
    tfs.update_transform(b.transform_id, auto_apply=False)
    w.hub.tf_name.setStringValue_("Native B renamed")
    w.k.click(w.button("Update"))
    w.drain()
    row = w.rows("SELECT name, prompt, auto_apply FROM transforms WHERE"
                 " transform_id=?", (b.transform_id,))[0]
    ok = ok_a and ok_b and shown == "NATIVE INSTRUCTION BETA" and \
        row == ("Native B renamed", "NATIVE INSTRUCTION BETA", 0)
    return {"status": "PASS" if ok else "FAIL",
            "rows_selected": [ok_a, ok_b], "shown": shown[:40],
            "stored": list(row)}


@check("transform_add_unknown_then_add_again_is_one", ["MERGED-X08"])
def n_transform_add_unknown(w):
    w.show("transforms")
    w.hub.tf_name.setStringValue_("Native Add")
    w.hub.tf_prompt.setString_("Summarize in one line.")
    w.hub.tf_shortcut.setStringValue_("")
    with X.hold_at(w.d.store, "add_transform") as held:
        w.k.click(w.button("Add"))
        first = str(w.hub.transforms_status.stringValue())
        reached = held.reached
    w.d.store.sync()
    w.drain()
    w.k.click(w.button("Add"))
    w.drain()
    n = len(w.rows("SELECT 1 FROM transforms WHERE name='Native Add'"))
    ok = reached and "unknown" in first and n == 1
    return {"status": "PASS" if ok else "FAIL", "first": first[:80],
            "transforms": n, "admitted": reached}


def _invalid_dataset(root):
    root.mkdir()
    (root / "dataset_manifest.json").write_text('{"not": "a manifest"}')
    (root / "SHA256SUMS.txt").write_text("")
    return root


@check("export_validate_acknowledges_then_keeps_its_result",
       ["MERGED-X12", "MERGED-X13"])
def n_export_validate(w):
    w.training_tab("export")
    dest = _invalid_dataset(w.h.tmp / "native-invalid")
    w.hub.export_dest.setStringValue_(str(dest))
    t0 = time.monotonic()
    w.k.click(w.button("Validate"))
    ack = time.monotonic() - t0
    acknowledged = "validating" in str(w.hub.export_text.string())
    w.drain()
    first = str(w.hub.export_text.string())
    w.training_tab("review")
    w.training_tab("export")
    after = str(w.hub.export_text.string())
    ok = acknowledged and "valid: False" in first and \
        "valid: False" in after and ack < 1.0
    return {"status": "PASS" if ok else "FAIL",
            "ack_seconds": round(ack, 3), "acknowledged": acknowledged,
            "kept_across_tab_switch": "valid: False" in after}


@check("undo_approval_button_undoes_the_chosen_rule", ["MERGED-X15"])
def n_undo_approval(w):
    _j, cid = N.teach(w)
    eid = w.d._learning.approve(cid)["entry_id"]
    w.training_tab("review")
    popup = w.hub.review_approved_popup
    titles = list(popup.itemTitles())
    # The one approved rule is the last item (the driver overshoots by
    # one at most — the last item cannot be overshot).
    w.k.popup(popup, titles[-1])
    chosen = popup.selectedItem().representedObject() == cid
    w.k.click(w.button("Undo Approval"))
    w.drain()
    status = w.rows("SELECT status FROM learning_candidates WHERE"
                    " candidate_id=?", (cid,))[0][0]
    enabled = w.rows("SELECT enabled FROM vocabulary_entries WHERE"
                     " entry_id=?", (eid,))[0][0]
    ok = chosen and status == "pending" and enabled == 0
    return {"status": "PASS" if ok else "FAIL", "chosen": chosen,
            "candidate": status, "entry_enabled": enabled}


@check("history_move_unknown_deletion_then_move_again",
       ["MERGED-X10"])
def n_history_move(w):
    import test_xm_remediation as R
    w.h.d.cfg["log_transcripts"] = True
    w.d.supervisor = R.Scripted(asr=lambda j, a: "native move words")
    job = R.dictate(w.h)
    # The default size: this check is X10's (reachability at the minimum
    # width is the geometry check's).
    w.win.setContentSize_(NSMakeSize(*hub_mod.DEFAULT_SIZE))
    pump()
    w.show("history")
    w.drain()
    assert click_row(w, "history_table", "id", job), "row not selected"
    real = w.d.store.delete_everywhere
    holds = []

    def hooked(*a, **kw):
        hold = X.WriterHold(w.d.store, "delete_phase")
        hold.__enter__()
        holds.append(hold)
        with X.caller_timeout(w.d.store):
            return real(*a, **kw)
    w.d.store.delete_everywhere = hooked
    try:
        w.k.click(w.button("Move→Scratchpad"))
        # What the user reads, right after the click (a later refresh
        # redraws the detail).
        first_note = str(w.hub.history_detail.string())
    finally:
        w.d.store.delete_everywhere = real
        for hold in holds:
            hold.release()
    w.d.store.sync()
    w.drain()
    w.k.click(w.button("Move→Scratchpad"))
    second_note = str(w.hub.history_detail.string())
    w.drain()
    notes = len(w.rows("SELECT note_id FROM notes"))
    gone = bool(w.rows("SELECT 1 FROM job_deletions WHERE job_id=?",
                       (job,)))
    told = first_note.split("→ Scratchpad:")[-1]
    ok = bool(holds) and notes == 1 and gone and \
        "→ Scratchpad:" in first_note and "failed" not in told and \
        "pending" in told
    return {"status": "PASS" if ok else "FAIL", "notes": notes,
            "source_deleted": gone, "delete_admitted": bool(holds),
            "first_told": told.strip()[:120],
            "second_told": second_note.split("→ Scratchpad:")[-1]
            .strip()[:80]}


@check("touched_controls_contained_and_hittable_at_minimum_size",
       ["MERGED-X15", "LOCAL-XM-02 Apply Retention",
        "LOCAL-XM-03 History actions"])
def n_geometry(w):
    misses = []

    def probe(where, size, view, pane):
        if view is None:
            misses.append((where, size, "absent"))
        elif not N._contained(view, pane) or not w.k.hit(view):
            misses.append((where, size, str(
                getattr(view, "title", lambda: type(view).__name__)())))

    def find(title):
        try:
            return w.button(title)
        except AssertionError:
            return None
    w.training_tab("review")
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        probe("review", size[0], find("Undo Approval"), w.hub.review_pane)
        probe("review", size[0],
              getattr(w.hub, "review_approved_popup", None),
              w.hub.review_pane)
    w.show("settings")
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        b = find("Apply Retention")
        probe("settings", size[0], b, b.superview() if b else None)
    # History's action row (Move→Scratchpad is MERGED-X10's surface).
    w.show("history")
    for size in (hub_mod.DEFAULT_SIZE, hub_mod.MIN_SIZE):
        w.win.setContentSize_(NSMakeSize(*size))
        pump()
        for title in ("Replay", "Copy", "Paste Again", "Retry", "Diff",
                      "Save→Scratchpad", "Move→Scratchpad",
                      "Delete Usage"):
            b = find(title)
            probe("history", size[0], b, b.superview() if b else None)
    return {"status": "PASS" if not misses else "FAIL", "misses": misses}


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
            w = N.World()
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
        r["covers"] = fn.covers
        r["tier"] = "passive"
        r["seconds"] = round(time.monotonic() - t0, 2)
        results[name] = r
        print(f"{r['status']:5}  {name}"
              + (f"  — {json.dumps({k: v for k, v in r.items() if k not in ('status', 'covers', 'tier', 'seconds')})[:200]}"
                 if r["status"] != "PASS" else ""), flush=True)
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    record = {"suite": "tests/v2/crossmilestone/test_native_xm_hub.py",
              "tier": "passive",
              "code": X.code_stamp(
                  "tests/v2/crossmilestone/test_native_xm_hub.py"),
              "frontmost_unchanged": frontmost_pid() == front0,
              "never_frontmost": frontmost_pid() != os.getpid(),
              "full_keyboard_access": bool(
                  APP.isFullKeyboardAccessEnabled()),
              "counts": counts, "checks": results}
    print("native xm:", counts, "frontmost unchanged:",
          record["frontmost_unchanged"])
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps(record, indent=1,
                                                     default=str))
    return 0 if set(counts) <= {"PASS"} and record["never_frontmost"] \
        else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
