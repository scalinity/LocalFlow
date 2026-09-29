"""GATE-G06 mandatory drivers, batch C part 1 (cross-milestone cases
XM-C094 XM-MH22 XM-MH23 XM-MH29 XM-R05 XM-R06 XM-C104 XM-C106 XM-C107
XM-C108 XM-C109).

Every driver crosses the real producer and consumer its case names —
the real coordinator ``_worker``/``_retry_job``/``_recover_journals``
(``test_lifecycle.Harness``), the real Hub controller headless, the real
M08 InsertionService, the real Store writer, HistoryQueryService,
ProfileService, NoteStore — and grades it with an independent oracle:
raw rows, the private pasteboard, what a spy saw the service receive,
literal texts the witness chose. Fakes are only the model worker
(Scripted/M11-style supervisors), the OS (the private pasteboard, the
M08 synthetic host/keyboard, a fake sound factory) and a shifted store
clock for the retention pass. Orderings are decided by latches, the
writer hold and MainQueue.drain, never by sleeps.

Run (AppKit headless, desktop isolated — a private pasteboard):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_g06_c1.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
import traceback
import types

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import NEW_FINAL, OLD_RAW, WriterHold, caller_timeout, one, \
    rows  # noqa: E402

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle",
          ROOT / "tests" / "v2" / "insertion",
          ROOT / "tests" / "v2" / "notes",
          ROOT / "tests" / "v2" / "transforms"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import CFG, FakeOverlay, FakeRecorder, Harness  # noqa: E402
from m09_world import (Latch as SvcLatch, MainQueue, World,  # noqa: E402
                       advance_stage, build_hub, seed_example)
import m12_world as W12  # noqa: E402
from test_xm_remediation import (Scripted, _board,  # noqa: E402
                                 _transform_result, attempt_final, dictate,
                                 examples_of, retry)

from localflow.v2.history_queries import (HistoryQueryService,  # noqa: E402
                                          final_text)
from localflow.v2.profile import ProfileService  # noqa: E402

CASES = []


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# =============================================================================
# shared helpers
# =============================================================================

def spy(obj, name, forward=True, result=None):
    """Record every call of ``obj.name`` (args, kwargs, returned value)
    and forward it to the real method (the seam stays real)."""
    calls = []
    real = getattr(obj, name)

    def wrapped(*a, **kw):
        out = real(*a, **kw) if forward else result
        calls.append((a, kw, out))
        return out
    setattr(obj, name, wrapped)
    return calls


def open_history(hub, mq):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index("history"))
    hub.state.select_view("history")
    assert mq.drain(hub.state, 60), "History did not drain"


def select_job(hub, mq, job_id):
    hub.state.select_history_row("job", job_id)
    assert mq.drain(hub.state, 60), "selection did not drain"
    rendered = hub._rendered.get("history_detail")
    assert rendered is not None and rendered.get("job_id") == job_id, (
        "fixture: the selected job's detail is not rendered")
    return rendered


def pane(hub):
    return str(hub.history_detail.string())


def job_row(store, job_id):
    return one(store, "SELECT state, state_reason, attempt FROM jobs WHERE"
               " job_id=?", (job_id,))


def live_text_artifacts(store, job_id):
    return rows(store, "SELECT artifact_id, role FROM artifacts WHERE"
                " job_id=? AND purged=0 AND content_text IS NOT NULL",
                (job_id,))


def note_rows(store):
    return rows(store, "SELECT n.note_id, r.content_text, r.origin FROM"
                " notes n JOIN note_revisions r ON r.revision_id ="
                " n.current_revision_id ORDER BY n.rowid")


def candidates(store):
    return rows(store, "SELECT candidate_id, job_id, before_artifact_id"
                " FROM learning_candidates ORDER BY rowid")


def texts_of(store, job_id, role):
    return sorted(t for (t,) in rows(
        store, "SELECT content_text FROM artifacts WHERE job_id=? AND"
        " role=? AND purged=0", (job_id, role)))


# =============================================================================
# XM-C094 — a note-bound dictation's receipt is note delivery
# =============================================================================

def _note_dictation(hw, note_id):
    """A note-bound PTT through the real coordinator: the editor is the
    focused destination (the headless focus seam of the M12 suite)."""
    hw.open_note(note_id)
    assert hw.focus(), "fixture: editor focus seam unavailable"
    hw.h.press()
    hw.h.release()
    fn, args = hw.h.run_coordinator()
    fn(*args)
    hw.settle_notes()
    hw.drain()
    return args[1]["job_id"]


def _usage(store, job_id):
    return rows(store, "SELECT insertion_outcome, meta_json FROM"
                " usage_facts WHERE job_id=? AND kind='dictation'",
                (job_id,))


@case("G06 XM-C094 (a note-bound dictation's receipt is note delivery,"
      " never an external AX/readback confirmation)")
def g06_xm_c094_note_delivery_receipt_is_labeled_note():
    with W12.HubWorld() as hw:
        store = hw.store
        n = hw.notes.create_note("dictate here")["note_id"]
        gen0 = _board()[0]
        job = _note_dictation(hw, n)
        assert hw.h.pastes == [], (
            f"note-bound dictation reached the external insertion host:"
            f" {hw.h.pastes!r}")
        assert _board()[0] == gen0, "note-bound dictation wrote the board"
        facts = _usage(store, job)
        assert len(facts) == 1, f"fixture: usage facts {facts}"
        outcome, meta = facts[0][0], json.loads(facts[0][1] or "{}")
        assert outcome == "confirmed", f"fixture: note never committed" \
            f" ({outcome})"
        assert meta.get("destination") == "scratchpad_note" and \
            "method" not in meta, (
                "the usage fact of a note delivery is not labeled as note"
                f" delivery (or carries an insertion method): {meta}")
        assert not rows(store, "SELECT 1 FROM insertions WHERE job_id=?",
                        (job,)), "a note delivery wrote an insertion row"
        state = job_row(store, job)
        assert state[:2] == ("insertion_confirmed", "scratchpad_note"), (
            f"job row does not name the note destination: {state}")
        detail = HistoryQueryService(store).job_detail(job)
        assert detail.get("state_reason") == "scratchpad_note" and \
            detail.get("insertion") is None, (
                "History detail presents the note delivery as an external"
                f" insertion: reason={detail.get('state_reason')}"
                f" insertion={detail.get('insertion')}")
        open_history(hw.hub, hw.mq)
        select_job(hw.hub, hw.mq, job)
        text = pane(hw.hub)
        assert "(scratchpad_note)" in text and "insertion:" not in text, (
            "the rendered History detail does not show the note"
            f" destination: {text[:300]!r}")


@case("G06 XM-C094 control (an external dictation records its external"
      " outcome)", kind="control")
def c_g06_xm_c094_external_dictation_records_external_outcome():
    with W12.HubWorld() as hw:
        store = hw.store
        hw.h.press()
        hw.h.release()
        fn, args = hw.h.run_coordinator()
        fn(*args)
        hw.drain()
        job = args[1]["job_id"]
        assert len(hw.h.pastes) == 1, hw.h.pastes
        facts = _usage(store, job)
        meta = json.loads(facts[0][1] or "{}")
        assert facts[0][0] == "posted_unverified" and \
            meta.get("destination") is None, (facts, meta)
        assert job_row(store, job)[0] == "insertion_unverified", \
            job_row(store, job)


# =============================================================================
# XM-MH22 — delayed-source-deletion Move, then a downstream refresh
# =============================================================================

MH22_TOKEN = "mhprofcanary"


def _profile_job(h):
    h.d.consent.set("enabled")
    h.d.cfg["log_transcripts"] = True
    sup = Scripted(asr=lambda j, a: " ".join(
        f"{MH22_TOKEN}{i} spoken" for i in range(15)))
    h.d.supervisor = sup
    return dictate(h), sup


def _evidence_citing(store, example_ids):
    if not example_ids:
        return []
    marks = ",".join("?" * len(example_ids))
    return rows(store, "SELECT snapshot_id, example_id, role FROM"
                f" profile_evidence WHERE example_id IN ({marks})",
                tuple(example_ids))


@case("G06 XM-MH22 (a Move with a delayed source deletion yields one"
      " note, a truthful status and no resurrected source downstream)")
def g06_xm_mh22_delayed_move_never_resurrects_source_in_profile():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        job, sup = _profile_job(h)
        final = attempt_final(sup, job, 1)
        exs = [e for (e,) in examples_of(store, job)]
        prof = ProfileService(store, min_words=1)
        prof.compute()
        assert _evidence_citing(store, exs), (
            "fixture (control): the profile before the move does not"
            " cite the job's example")
        real = store.delete_everywhere
        held = []

        def hooked(*a, **kw):
            hold = WriterHold(store, "delete_phase")
            hold.__enter__()
            held.append(hold)
            with caller_timeout(store):
                return real(*a, **kw)
        store.delete_everywhere = hooked
        try:
            first = h.d.hubSaveHistoryRow("job", job, move=True)
        finally:
            store.delete_everywhere = real
            for hold in held:
                hold.release()
        store.sync()
        assert held, "fixture: the move never reached its delete phase"
        assert one(store, "SELECT 1 FROM job_deletions WHERE job_id=?",
                   (job,)), "fixture: the admitted deletion did not commit"
        assert first.get("outcome") == "source_deletion_unknown", (
            f"phase status not truthful for an admitted deletion: {first}")
        second = h.d.hubSaveHistoryRow("job", job, move=True)
        assert second.get("outcome") == "moved" and \
            second.get("note_id") == first.get("note_id"), (first, second)
        prof.compute()
        cur = prof.current()
        notes = note_rows(store)
        assert len(notes) == 1 and notes[0][1] == final, (
            f"destination duplicated or wrong: {notes}")
        prov = rows(store, "SELECT source_job_id FROM note_revisions WHERE"
                    " note_id=?", (notes[0][0],))
        assert [p for (p,) in prov] == [job], f"note provenance: {prov}"
        assert HistoryQueryService(store).job_detail(job) is None
        assert not live_text_artifacts(store, job), (
            "the moved source's text was recreated: "
            f"{live_text_artifacts(store, job)}")
        cited = _evidence_citing(store, exs)
        blobs = rows(store, "SELECT snapshot_id, measured_json, cards_json"
                     " FROM profile_snapshots")
        leaked = [s for s, m, c in blobs
                  if MH22_TOKEN in (m + c).lower()]
        assert not cited and not leaked, (
            "after the reconciled Move the profile still cites the moved"
            f" source: evidence={cited} snapshots_with_text={leaked}")
        assert cur is None or MH22_TOKEN not in json.dumps(cur).lower(), \
            "ProfileService.current() still carries the moved text"
    finally:
        h.close()


# =============================================================================
# XM-MH23 — an unknown Save-to-Scratchpad opens as its one note
# =============================================================================

def _panel(hw, text):
    from localflow.v2.ui.transforms_panel import TransformPreviewPanel
    result = _transform_result(text)
    defn = types.SimpleNamespace(name="Witness transform")
    panel = TransformPreviewPanel.alloc().init_panel(hw.d)
    hw.d._tf_panel = panel
    panel.show(result, {"source": "panel source text"}, defn, None)
    return panel


@case("G06 XM-MH23 (an admitted-then-unknown transform Save resolves to"
      " one note id, stays unknown until settled, and opens as that"
      " note)")
def g06_xm_mh23_unknown_save_opens_its_one_note():
    with W12.HubWorld() as hw:
        store = hw.store
        text = "MH23SAVECANARY transform output"
        panel = _panel(hw, text)
        opened = spy(hw.hub, "scratchpad_note_created")
        with X.hold_at(store, "_append") as held:
            panel.panelSaveToScratchpad_(None)
            assert held.reached, "fixture: the create was never admitted"
            title = str(panel.panel.title())
            assert "unknown" in title.lower(), (
                f"an admitted, unanswered Save is not shown unknown:"
                f" {title!r}")
            assert opened == [], (
                "a note was opened before the save's outcome was known:"
                f" {[c[0] for c in opened]}")
        store.sync()
        assert "unknown" in str(panel.panel.title()).lower(), (
            "the unknown status was dropped before the repeat settled it")
        assert opened == [], "a note opened without a settled save"
        panel.panelSaveToScratchpad_(None)  # the repeat the panel offers
        store.sync()
        hw.drain()
        got = [r for r in note_rows(store) if r[1] == text]
        assert len(got) == 1, f"one logical Save made {len(got)} notes"
        note_id = got[0][0]
        ids_opened = [c[0][0] for c in opened]
        assert ids_opened == [note_id], (
            f"the settled Save opened {ids_opened}, the stored note is"
            f" {note_id}")
        sel = hw.hub.state.views["scratchpad"].get("selected_id")
        assert sel == note_id and hw.hub.editor.note_id == note_id, (
            f"the Hub selected {sel} / editor bound "
            f"{hw.hub.editor.note_id}, not the saved note {note_id}")


@case("G06 XM-MH23 control (an unheld Save opens its new note once)",
      kind="control")
def c_g06_xm_mh23_unheld_save_opens_once():
    with W12.HubWorld() as hw:
        text = "MH23CONTROLCANARY output"
        panel = _panel(hw, text)
        opened = spy(hw.hub, "scratchpad_note_created")
        panel.panelSaveToScratchpad_(None)
        hw.store.sync()
        hw.drain()
        got = [r for r in note_rows(hw.store) if r[1] == text]
        assert len(got) == 1 and [c[0][0] for c in opened] == \
            [got[0][0]], (got, opened)
        assert hw.hub.editor.note_id == got[0][0]


# =============================================================================
# XM-MH29 — every local copy caller respects a pending payload; the
# reconciled outcome never overclaims consumption
# =============================================================================

class _SystemBoardView:
    """What the (fake) target reads when it finally consumes the ⌘V:
    the process's general pasteboard (private under run_isolated) — the
    board the real SystemPasteboard adapter publishes to."""

    def plain(self):
        return _board()[1]


def _pending_service(store, job_id):
    """The REAL M08 InsertionService over the general pasteboard with
    the M08 synthetic host; the keyboard holds the posted ⌘V (gate) so
    the payload stays readback_pending until the target consumes it
    late (``kb.release``)."""
    from m08_world import standard_world
    from test_m08_remediation import job as m08_job, snap
    from localflow.v2.insertion.hosts import SystemPasteboard
    from localflow.v2.insertion.service import InsertionService
    w, _pb, kb = standard_world(text_f1="abc", sel_f1=(3, 3))
    kb.pb = _SystemBoardView()
    for fid in ("F1", "FB"):
        w.fields[fid].settable = False  # the clipboard method
    svc = InsertionService(host=w, pasteboard=SystemPasteboard(),
                           keyboard=kb, store=store,
                           emit=lambda *a, **k: None,
                           restore_clipboard=True,
                           observation_window_sec=0.0, settle_sec=0.1)
    kb.mode = "gate"

    def submit(text, jid):
        done = threading.Event()
        box = {}
        svc.submit(text, m08_job(jid, snap(w)),
                   lambda r: (box.setdefault("r", r), done.set()))
        assert done.wait(10), "insertion never finished"
        return box["r"]
    return svc, w, kb, submit(NEW_FINAL, job_id), submit


def _history_outcome(store, job_id):
    ins = HistoryQueryService(store).job_detail(job_id)["insertion"] or {}
    return ins.get("state"), ins.get("reason_code")


@case("G06 XM-MH29 (copyLastRaw_, hubCopyText and tfCopyTransform all"
      " respect a pending payload; the reconciled History outcome never"
      " overclaims consumption)")
def g06_xm_mh29_copy_callers_respect_pending_and_outcome_is_honest():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        job1, _ = store.create_job(state="ready_to_insert")
        job2, _ = store.create_job(state="ready_to_insert")
        job3, _ = store.create_job(state="ready_to_insert")
        svc, w, kb, r1, submit = _pending_service(store, job1)
        assert r1.reason_code == "readback_pending", r1.reason_code
        assert svc.clipboard_payload_pending, "fixture: nothing pending"
        gen0, text0 = _board()
        assert text0 == NEW_FINAL, f"fixture: board holds {text0!r}"
        h.d._insertion = svc
        failed, _fam = store.create_job(state="failed_recoverable")
        h.d._last_failed = {"job_id": failed, "raw": OLD_RAW, "wav": None,
                            "attempt": 1}
        moved = []
        callers = (
            ("copyLastRaw_", lambda: h.d.copyLastRaw_(None)),
            ("hubCopyText", lambda: h.d.hubCopyText("HUBCOPYCANARY")),
            ("tfCopyTransform", lambda: h.d.tfCopyTransform(
                _transform_result("TFCOPYCANARY"))))
        for name, call in callers:
            call()
            if _board() != (gen0, text0):
                moved.append((name, _board()))
        assert not moved, (
            "a local copy replaced the payload reserved for a pending"
            f" insertion: {moved}")
        assert svc.clipboard_payload_pending
        # Reconcile while NOT consumed: the next insertion finds the
        # payload still owed; job1's History outcome stays unconfirmed.
        r2 = submit("SECOND PAYLOAD", job2)
        assert r2.reason_code == "clipboard_payload_pending", (
            f"fixture: the reconcile did not see the pending payload:"
            f" {r2.state}/{r2.reason_code}")
        unconsumed = _history_outcome(store, job1)
        assert unconsumed == ("posted_unverified", "readback_pending"), (
            "with no consumption observed the History outcome claims"
            f" more than posted/readback_pending: {unconsumed}")
        # The target consumes the payload late; the next insertion
        # reconciles it.
        kb.release(wait=True)
        assert NEW_FINAL in w.text("F1"), "fixture: no late consumption"
        kb.mode = "sync"
        r3 = submit("THIRD PAYLOAD", job3)
        assert not svc.clipboard_payload_pending, (
            f"fixture: the observed consumption was not reconciled"
            f" ({r3.state}/{r3.reason_code})")
        consumed = _history_outcome(store, job1)
        assert consumed[0] in ("confirmed", "posted_unverified"), (
            f"after an observed consumption History shows {consumed}")
    finally:
        h.close()


@case("G06 XM-MH29 control (with nothing pending each caller copies"
      " once)", kind="control")
def c_g06_xm_mh29_each_caller_copies_when_nothing_pending():
    h = Harness(durations=[1.0])
    try:
        failed, _fam = h.d.store.create_job(state="failed_recoverable")
        h.d._last_failed = {"job_id": failed, "raw": OLD_RAW, "wav": None,
                            "attempt": 1}
        seen = []
        for want, call in (
                (OLD_RAW, lambda: h.d.copyLastRaw_(None)),
                ("HUBCOPYCANARY", lambda: h.d.hubCopyText("HUBCOPYCANARY")),
                ("TFCOPYCANARY", lambda: h.d.tfCopyTransform(
                    _transform_result("TFCOPYCANARY")))):
            gen = _board()[0]
            call()
            after = _board()
            seen.append((want, after[1], after[0] > gen))
        assert all(w == got and adv for w, got, adv in seen), seen
    finally:
        h.close()


# =============================================================================
# XM-R05 — History actions stay bound to the rendered job/revision
# =============================================================================

R05_ASR = {1: "alpha bravo charlie delta", 2: "echo foxtrot golf hotel",
           3: "india juliet kilo lima"}


def _r05_world():
    w = World(durations=[1.0] * 4, build=False).__enter__()
    try:
        w.d.consent.set("enabled")
        order = []

        def asr(job_id, attempt):
            if job_id not in order:
                order.append(job_id)
            return R05_ASR[order.index(job_id) + 1]
        w.d.supervisor = Scripted(asr=asr)
        j1 = dictate(w.h)
        j2 = dictate(w.h)
        w.hub, w.sounds = build_hub(w.d)
        w.drain()
        open_history(w.hub, w.mq)
        return w, j1, j2
    except BaseException:
        w.__exit__(*sys.exc_info())
        raise


def _flat_ids(entries):
    return [None if e.get("__group__") else e["id"] for e in entries]


def _r05_actions(w, j1):
    """Copy, Teach and → Scratchpad against the rendered row."""
    w.hub.historyCopy_(None)
    w.hub.historyTeach_(None)
    w.hub.historyToScratchpad_(None)


@case("G06 XM-R05 (a History action acts on the rendered job and"
      " revision or refuses; a reordered backing list never redirects"
      " it)")
def g06_xm_r05_reordered_history_never_redirects_actions():
    w, j1, j2 = _r05_world()
    try:
        store = w.store
        rendered = select_job(w.hub, w.mq, j1)
        k = _flat_ids(w.hub._history_flat).index(j1)
        f1 = final_text(rendered)
        other = {final_text(HistoryQueryService(store).job_detail(j2))}
        w.hub.teach_field.setStringValue_(f1.replace("DELTA", "DELTAS"))
        copies = spy(w.d, "hubCopyText")
        saves = spy(w.d, "hubSaveHistoryRow")
        lat = SvcLatch(w.hub.spec["learning_service"])
        w.hub.spec["learning_service"] = lat
        # A newer capture lands and History reloads; the Hub has not
        # repainted: the backing list now puts J2 at the rendered row.
        j3 = dictate(w.h)
        w.hub.state.reload_history()
        w.hub.state.wait_for_queries(30)
        data = w.hub.state.views["history"]["data"]
        flat_now = []
        for g in data["groups"]:
            flat_now.append(None)
            flat_now.extend(r["id"] for r in g["rows"])
        assert j3 in flat_now and flat_now[k] == j2, (
            f"fixture: the reload did not put J2 at row {k}: {flat_now}")
        _r05_actions(w, j1)   # before the repaint
        pre = {"copy": len(copies), "save": len(saves),
               "teach": len(lat.calls)}
        print(f"  XM-R05 before repaint: service calls {pre}")
        assert w.mq.drain(w.hub.state, 60)
        flat = _flat_ids(w.hub._history_flat)
        assert flat[k] == j2, f"fixture: repaint did not reorder: {flat}"
        _r05_actions(w, j1)   # after the repaint (selection kept by id)
        store.sync()
        wrong = []
        for a, _kw, out in copies:
            if a[0] != f1:
                wrong.append(("copy", a[0]))
        for name, a, kw, _t in lat.calls:
            if name == "teach_correction" and (
                    a[0] != j1 or kw.get("expected_final_artifact_id")
                    != next(s["artifact"]["artifact_id"]
                            for s in rendered["lineage"]
                            if s["stage"] == "cleaned")):
                wrong.append(("teach", a[0], kw))
        for a, kw, out in saves:
            if a[1] != j1:
                wrong.append(("save", a[1], out))
        for cid, job, before in candidates(store):
            if job != j1:
                wrong.append(("candidate", job))
        for nid, content, _o in note_rows(store):
            if content != f1 or content in other:
                wrong.append(("note", content))
        assert not wrong, (
            f"an action acted on a row other than the rendered J1: {wrong}")
        assert copies or saves or lat.calls, \
            "fixture: every action refused (nothing reached a service)"
        # J1's final changes after the render: the transfer refuses.
        ex = [e for (e,) in examples_of(store, j1)][-1]
        advance_stage(store, ex, "applied_output", "CHANGED FINAL J1")
        before = len(note_rows(store))
        w.hub.historyToScratchpad_(None)
        store.sync()
        last = saves[-1][2] if saves else {}
        assert last.get("outcome") == "history_changed" and \
            len(note_rows(store)) == before, (
                "a transfer after J1's final changed was not refused:"
                f" {last}; notes {before} -> {len(note_rows(store))}")
    finally:
        w.__exit__(None, None, None)


@case("G06 XM-R05 control (no reorder: each action acts on J1 once)",
      kind="control")
def c_g06_xm_r05_actions_act_on_rendered_row_once():
    w, j1, _j2 = _r05_world()
    try:
        store = w.store
        rendered = select_job(w.hub, w.mq, j1)
        f1 = final_text(rendered)
        w.hub.teach_field.setStringValue_(f1.replace("DELTA", "DELTAS"))
        copies = spy(w.d, "hubCopyText")
        _r05_actions(w, j1)
        store.sync()
        assert [c[0][0] for c in copies] == [f1], copies
        assert [c[1] for c in candidates(store)] == [j1], candidates(store)
        assert [n[1] for n in note_rows(store)] == [f1], note_rows(store)
    finally:
        w.__exit__(None, None, None)


# =============================================================================
# XM-R06 — Teach bound to F1 refuses after a real retry commits F2
# =============================================================================

class _Unsettled:
    """The insertion host of a process that dies after posting: the
    submission is recorded, its outcome never arrives."""

    busy = False

    def __init__(self):
        self.submits = []

    def note_new_dictation(self):
        pass

    def note_session_locked(self):
        pass

    def note_session_unlocked(self):
        pass

    def submit(self, text, job, on_done, on_observation=None):
        self.submits.append(text)


def _relaunch(w, cfg):
    """The app dies after posting attempt 1 (its store and locks gone
    with the process); a new AppDelegate over the same files runs the
    real startup scan, which makes the unresolved job a recoverable
    item. Returns the new delegate (also installed as the harness's)."""
    import localflow.app as app_mod
    from localflow.app import AppDelegate
    from localflow.hotkey import HotkeyListener
    d1 = w.h.d
    settling = w.h._settling
    d1.store.sync()
    d1.store.close()
    d1.v2log.close()
    for attr in ("_journal_root_lock", "_boot_lock"):
        fd = getattr(d1, attr, None)
        if fd is not None:
            os.close(fd)
            setattr(d1, attr, None)
    d2 = AppDelegate.alloc().init()
    merged = dict(CFG)
    merged.update(cfg)
    d2.configure(merged)
    d2.recorder = FakeRecorder([])
    d2.overlay = FakeOverlay()
    hk = HotkeyListener("fn", d2.startDictation, d2.finishDictation,
                        d2.cancelDictation)
    hk.physically_down = lambda: False
    d2.hotkey = hk
    d2._insertion = settling
    w.h.d = d2
    w.d = d2
    w.store = d2.store
    assert app_mod.V2_DB.exists()
    d2._recover_journals()
    return d2


def _r06_world(collection_on):
    cfg = {"log_transcripts": True}
    w = World(durations=[1.0], build=False).__enter__()
    try:
        w.d.cfg.update(cfg)
        w.d.consent.set("enabled" if collection_on else "disabled")
        sup = Scripted(asr=lambda j, a: "alpha attempt one words"
                       if a == 1 else "beta attempt two words")
        w.d.supervisor = sup
        w.h._settling = w.d._insertion
        w.d._insertion = _Unsettled()
        job = dictate(w.h)
        assert w.d._insertion.submits, "fixture: attempt 1 never posted"
        d2 = _relaunch(w, cfg)
        d2.supervisor = sup
        row = job_row(d2.store, job)
        assert row[0] == "failed_recoverable", (
            f"fixture: the relaunch scan did not recover the job: {row}")
        w.hub, w.sounds = build_hub(d2)
        w.drain()
        open_history(w.hub, w.mq)
        rendered = select_job(w.hub, w.mq, job)
        f1 = next(s["artifact"] for s in rendered["lineage"]
                  if s["stage"] == "cleaned")
        assert f1 and f1.get("text") == attempt_final(sup, job, 1), (
            f"fixture: attempt 1's final is not rendered: {f1}")
        w.hub.teach_field.setStringValue_(
            f1["text"].replace("WORDS", "WORLDS"))
        lat = SvcLatch(w.hub.spec["learning_service"])
        w.hub.spec["learning_service"] = lat
        return w, job, sup, f1, lat
    except BaseException:
        w.__exit__(*sys.exc_info())
        raise


def _current_applied(store, job):
    detail = HistoryQueryService(store).job_detail(job)
    art = next(s["artifact"] for s in detail["lineage"]
               if s["stage"] == "cleaned")
    return art["artifact_id"] if art else None


@case("G06 XM-R06 (Teach rendered against attempt-1 final F1 refuses"
      " stale_final after a real retry commits F2; collection on and"
      " off)")
def g06_xm_r06_teach_after_real_retry_is_stale():
    problems = []
    for collection_on in (True, False):
        w, job, sup, f1, lat = _r06_world(collection_on)
        try:
            store = w.store
            n0 = len(candidates(store))
            out = w.d.hubRetryJob(job)
            assert out is None or out.get("outcome") in (
                None, "requeued", "queued"), f"fixture: retry {out}"
            fn, a = w.h.run_coordinator()
            fn(*a)
            store.sync()
            assert job_row(store, job)[2] == 2, \
                f"fixture: no attempt 2 ({job_row(store, job)})"
            f2 = _current_applied(store, job)
            assert f2 and f2 != f1["artifact_id"], (
                f"fixture: the retry committed no new final ({f2})")
            w.hub.historyTeach_(None)
            store.sync()
            seen = [kw.get("expected_final_artifact_id")
                    for name, _a, kw, _t in lat.calls
                    if name == "teach_correction"]
            note = pane(w.hub)
            tag = "collection " + ("on" if collection_on else "off")
            if len(candidates(store)) != n0:
                problems.append(f"{tag}: a candidate was created against"
                                f" the retried job: {candidates(store)}")
            if seen != [f1["artifact_id"]]:
                problems.append(f"{tag}: the service saw {seen}, not the"
                                " rendered F1")
            if "stale_final" not in note:
                problems.append(f"{tag}: the History note does not say"
                                f" stale_final: {note[-160:]!r}")
        finally:
            w.__exit__(None, None, None)
    assert not problems, "; ".join(problems)


@case("G06 XM-R06 control (without the retry the same Teach creates one"
      " candidate whose before is F1)", kind="control")
def c_g06_xm_r06_teach_without_retry_creates_one_candidate():
    got = {}
    for collection_on in (True, False):
        w, job, _sup, f1, _lat = _r06_world(collection_on)
        try:
            w.hub.historyTeach_(None)
            w.store.sync()
            got[collection_on] = ([c[1:] for c in candidates(w.store)],
                                  f1["artifact_id"], pane(w.hub)[-160:])
            assert [c[1:] for c in candidates(w.store)] == \
                [(job, f1["artifact_id"])], got[collection_on]
        finally:
            w.__exit__(None, None, None)


# =============================================================================
# XM-C104 — one applied auto-transform is the delivered final everywhere
# =============================================================================

C104_ASR = "please review the parser fix today"
C104_T = "Polished witness output for the parser fix"


class _M11Sup(Scripted):
    """Scripted ASR/cleanup (cleanup appends a mark so Clean differs
    from raw) plus the M11 transform op with a witness-chosen output."""

    def __init__(self, output):
        super().__init__(asr=lambda j, a: C104_ASR)
        self.output = output
        self.transform_calls = []

    def clean(self, *, job_id, attempt, raw_text, **ctx):
        out = super().clean(job_id=job_id, attempt=attempt,
                            raw_text=raw_text, **ctx)
        out["text"] = raw_text + " cleanmark"
        return out

    def transform(self, **payload):
        self.transform_calls.append(payload)
        return {"attempt": payload.get("attempt", 1),
                "generation": self.generation, "output": self.output,
                "coverage": [], "review_excerpts": [],
                "task_manifest": {"task_key": "ttask:g06"},
                "result": {"path": "applied", "reason": None,
                           "output_tokens": 20, "limit_hit": False,
                           "duration_ms": 1.0,
                           "coverage": {"atoms": 0, "covered": 0,
                                        "uncertain": 0, "missing": 0},
                           "diff": None},
                "prompt": "<g06 transform prompt>"}


def _c104_run(collection_on, auto_apply):
    """Returns {consumer: payload} plus the witness texts."""
    from test_transform_pipeline import FakeContextCollector
    w = World(durations=[1.0], build=False).__enter__()
    try:
        d = w.d
        d.cfg["log_transcripts"] = True
        d.consent.set("enabled" if collection_on else "disabled")
        sup = _M11Sup(C104_T)
        d.supervisor = sup
        d._context = FakeContextCollector("com.apple.mail", "mail")
        d._styles.add_rule(name="Mail polish", scope_kind="category",
                           scope_value="email", mode="polish")
        if auto_apply:
            d._tf_store.update_transform("builtin:polish", auto_apply=True)
        job = dictate(w.h)
        w.store.sync()
        assert len(sup.clean_inputs) == 1, sup.clean_inputs
        clean = sup.clean_inputs[0][2] + " cleanmark"
        out = {"inserted": list(w.h.pastes)}
        w.hub, w.sounds = build_hub(d)
        w.drain()
        open_history(w.hub, w.mq)
        rendered = select_job(w.hub, w.mq, job)
        out["history_final"] = final_text(rendered)
        copies = spy(d, "hubCopyText")
        pastes = spy(d, "hubPasteText")
        w.hub.historyCopy_(None)
        out["board"] = _board()[1]
        w.hub.historyPasteAgain_(None)
        w.hub.historyToScratchpad_(None)
        w.store.sync()
        out["copy"] = [c[0][0] for c in copies][:1]
        out["paste_again"] = [c[0][0] for c in pastes]
        out["note"] = [n[1] for n in note_rows(w.store)]
        fw = rows(w.store, "SELECT final_words FROM usage_facts WHERE"
                  " job_id=? AND kind='dictation'", (job,))
        out["final_words"] = [x for (x,) in fw]
        out["applied_output"] = texts_of(w.store, job, "applied_output")
        out["raw_transcript"] = texts_of(w.store, job, "raw_transcript")
        out["transform_calls"] = len(sup.transform_calls)
        return out, clean
    finally:
        w.__exit__(None, None, None)


def _c104_check(out, clean, final):
    # The inserted text carries the configured trailing space
    # (append_space, test_lifecycle CFG); the final itself does not.
    sep = " " if CFG.get("append_space") else ""
    want = {"inserted": [final + sep], "history_final": final,
            "board": final,
            "copy": [final], "paste_again": [final], "note": [final],
            "final_words": [len(final.split())],
            "applied_output": [clean], "raw_transcript": [C104_ASR]}
    return {k: (out.get(k), v) for k, v in want.items() if out.get(k) != v}


@case("G06 XM-C104 (an applied auto-transform output is the one"
      " delivered final for History, Copy, Paste Again, the Scratchpad"
      " transfer and usage final_words; raw and Clean kept apart)")
def g06_xm_c104_applied_transform_is_the_delivered_final():
    bad = {}
    for collection_on in (True, False):
        out, clean = _c104_run(collection_on, auto_apply=True)
        assert out["transform_calls"] == 1, (
            f"fixture: the auto transform did not run: {out}")
        diff = _c104_check(out, clean, C104_T)
        if diff:
            bad["collection " + ("on" if collection_on else "off")] = diff
    assert not bad, f"consumers disagree on the delivered final: {bad}"


@case("G06 XM-C104 control (auto-apply off: every consumer carries"
      " Clean)", kind="control")
def c_g06_xm_c104_clean_is_the_final_without_auto_apply():
    bad = {}
    for collection_on in (True, False):
        out, clean = _c104_run(collection_on, auto_apply=False)
        assert out["transform_calls"] == 0, out
        diff = _c104_check(out, clean, clean)
        if diff:
            bad["collection " + ("on" if collection_on else "off")] = diff
    assert not bad, bad


# =============================================================================
# XM-C106 — a purge after render revokes History content actions
# =============================================================================

C106_FINAL = "PURGEDFINALCANARY final words here"
C106_FIX = "PURGEDFINALCANARY final worlds here"


def _c106_world():
    w = World(durations=[1.0]).__enter__()
    try:
        w.d._hub = w.hub  # the retention pass revalidates this Hub
        c = seed_example(w.store, "purge raw words", applied=C106_FINAL,
                         audio=False)
        # An independent History lease keeps the row (and its raw text)
        # listed; only the final stage expires (test_r09's fixture).
        w.store.grant_lease(c["raw"], "history", days=400)
        w.store.sync()
        open_history(w.hub, w.mq)
        rendered = select_job(w.hub, w.mq, c["job_id"])
        assert final_text(rendered) == C106_FINAL, "fixture: final"
        w.hub.teach_field.setStringValue_(C106_FIX)
        rec = {"copy": spy(w.d, "hubCopyText"),
               "paste": spy(w.d, "hubPasteText")}
        return w, c, rec
    except BaseException:
        w.__exit__(*sys.exc_info())
        raise


def _age_store(store):
    """The retention pass's clock, moved past the training buffer (a
    clock fake — the purge itself is the production pass)."""
    days = store.retention_days["training_buffer"]
    real = store.now_fn
    store.now_fn = lambda: real() + (days + 2) * 86400


def _press_all(w):
    w.hub.historyCopy_(None)
    w.hub.historyPasteAgain_(None)
    w.hub.historyTeach_(None)


def _admitted(w, c, rec):
    w.store.sync()
    got = [(k, a[0]) for k, calls in rec.items() for a, _kw, _o in calls
           if C106_FINAL in str(a[0])]
    cands = rows(w.store, "SELECT candidate_id FROM learning_candidates"
                 " WHERE job_id=?", (c["job_id"],))
    return got, len(cands)


def _purged(w, c):
    return one(w.store, "SELECT purged FROM artifacts WHERE artifact_id=?",
               (c["applied"],))[0] == 1


@case("G06 XM-C106 (after the rendered final is purged, Copy, Paste"
      " Again and Teach have no effect with the purged text; the detail"
      " is revalidated) [suspected defect]")
def g06_xm_c106_purge_after_render_revokes_content_actions():
    results = {}
    # (a) inside the retention pass: purge committed, revalidate not yet
    w, c, rec = _c106_world()
    try:
        gate = {"arrived": threading.Event(), "go": threading.Event()}
        real = w.store.prune_metadata

        def held(*a, **kw):
            gate["arrived"].set()
            assert gate["go"].wait(30), "retention gate never released"
            return real(*a, **kw)
        w.store.prune_metadata = held
        _age_store(w.store)
        t = threading.Thread(target=w.d._retention_pass, daemon=True)
        t.start()
        assert gate["arrived"].wait(30), "fixture: pass never reached gate"
        assert _purged(w, c), "fixture: the pass did not purge the final"
        _press_all(w)
        results["a_before_revalidate"] = _admitted(w, c, rec)
        gate["go"].set()
        t.join(30)
    finally:
        w.__exit__(None, None, None)
    # (b) revalidate ran, its detail reload not yet published
    w, c, rec = _c106_world()
    try:
        lat = SvcLatch(w.hub.state.history_service)
        w.hub.state.history_service = lat
        g = lat.hold("job_detail", after=False)
        _age_store(w.store)
        t = threading.Thread(target=w.d._retention_pass, daemon=True)
        t.start()
        assert g.arrived.wait(30), "fixture: no detail reload after pass"
        assert _purged(w, c), "fixture: the pass did not purge the final"
        _press_all(w)
        results["b_reload_in_flight"] = _admitted(w, c, rec)
        g.release.set()
        t.join(30)
    finally:
        w.__exit__(None, None, None)
    # (c) the pass and its revalidation fully settled
    w, c, rec = _c106_world()
    try:
        _age_store(w.store)
        t = threading.Thread(target=w.d._retention_pass, daemon=True)
        t.start()
        t.join(30)
        w.drain()
        assert _purged(w, c), "fixture: the pass did not purge the final"
        _press_all(w)
        results["c_revalidated"] = _admitted(w, c, rec)
        shown = pane(w.hub) + json.dumps(w.hub._history_flat)
        if "PURGEDFINALCANARY" in shown:
            results["c_widgets"] = ("purged text still rendered", 0)
    finally:
        w.__exit__(None, None, None)
    bad = {k: v for k, v in results.items() if v[0] or v[1]}
    assert not bad, (
        "a History content action admitted the purged final text"
        f" (variant: [(action, text)], candidates): {bad}")


@case("G06 XM-C106 control (on an unpurged rendered row each action"
      " admits once)", kind="control")
def c_g06_xm_c106_unpurged_row_admits_once():
    w, c, rec = _c106_world()
    try:
        _press_all(w)
        got, cands = _admitted(w, c, rec)
        kinds = sorted(k for k, _t in got)
        # Paste Again admits once (hubPasteText); it never turns into a
        # copy (POLICY-D03), so Copy is the only copy.
        assert kinds == ["copy", "paste"] and cands == 1, (
            got, cands)
    finally:
        w.__exit__(None, None, None)


# =============================================================================
# XM-C107 — searching an old attempt's text (declared policy)
# =============================================================================

C107_OLD = "oldtokenqz"
C107_NEW = "newtokenqz"


def _c107_job(h, collection_off):
    h.d.consent.set("enabled")
    h.d.cfg["log_transcripts"] = True
    sup = Scripted(asr=lambda j, a: f"{C107_OLD} spoken first"
                   if a == 1 else f"{C107_NEW} spoken second",
                   fail_clean={1})
    h.d.supervisor = sup
    job = dictate(h)
    assert h.job_state(job) == "failed_recoverable", h.job_state(job)
    info = dict(h.d._last_failed)
    if collection_off:
        h.d.consent.set("disabled")
    retry(h, info)
    return job, sup


def _hit(svc, text, job):
    got = [r for g in svc.search(text=text)["groups"] for r in g["rows"]
           if r["id"] == job]
    return got[0] if got else None


@case("G06 XM-C107 (an old-attempt-only token may find the job under the"
      " declared retained-artifact search policy; the opened result shows"
      " the current attempt's final, never the old text)")
def g06_xm_c107_old_attempt_search_opens_current_final():
    """Policy (recorded, not invented): docs/v2/contracts/hub.md History
    filters — free text over the retained raw/normalized/applied
    artifacts; merged_ledger.json non-finding 'History search may match
    retained historical-stage content'; decisions.json D06 — History
    shows the CURRENT attempt and never an earlier attempt's text. So a
    hit is permitted, not required; what it shows is decided."""
    bad = {}
    policy = {}
    for collection_off in (False, True):
        tag = "tagged" if collection_off else "manifest"
        h = Harness(durations=[1.0])
        try:
            job, sup = _c107_job(h, collection_off)
            store = h.d.store
            attempt = job_row(store, job)[2]
            assert attempt == 2, f"fixture: attempt {attempt}"
            assert rows(store, "SELECT 1 FROM artifacts WHERE job_id=? AND"
                        " purged=0 AND content_text LIKE ?",
                        (job, f"%{C107_OLD}%")), \
                "fixture: attempt 1's text is not retained"
            svc = HistoryQueryService(store)
            hit = _hit(svc, C107_OLD, job)
            policy[tag] = "matched" if hit else "not_matched"
            detail = svc.job_detail(job)
            lineage = json.dumps([(s.get("artifact") or {}).get("text")
                                  for s in detail["lineage"]]).lower()
            want = attempt_final(sup, job, 2)
            problems = []
            if hit is not None and C107_OLD in (hit["preview"] or
                                                "").lower():
                problems.append(f"preview shows the old attempt:"
                                f" {hit['preview']!r}")
            if detail.get("lineage_attempt") != attempt:
                problems.append(f"lineage_attempt"
                                f" {detail.get('lineage_attempt')}")
            if final_text(detail) != want:
                problems.append(f"final {final_text(detail)!r} != {want!r}")
            if C107_OLD in lineage:
                problems.append("old-attempt text in the detail lineage")
            ctl = _hit(svc, C107_NEW, job)
            if ctl is None or C107_NEW not in (ctl["preview"] or
                                               "").lower():
                problems.append(f"control: current token search {ctl}")
            if problems:
                bad[tag] = problems
        finally:
            h.close()
    sys.stderr.write(f"XM-C107 search policy observed: {policy}\n")
    assert not bad, bad


# =============================================================================
# XM-C108 — replaying an item whose audio is gone stops A, reports why
# =============================================================================

def _playing(sounds):
    live = {}
    for ev in sounds.events:
        if ev[0] == "play":
            live[ev[1]] = True
        elif ev[0] == "stop":
            live[ev[1]] = False
    return [sid for sid, on in live.items() if on]


def _replay_world(b_kind):
    w = World().__enter__()
    try:
        a = seed_example(w.store, "replay item alpha",
                         captured="2026-09-22T10:00:00.000Z")
        b = seed_example(w.store, "replay item bravo",
                         audio=b_kind != "no_artifact",
                         captured="2026-09-22T10:05:00.000Z")
        if b_kind == "purged":
            def op():
                w.store._purge_artifact(b["audio"], reason="retention")
                w.store._purge_pending = True
            w.store._submit(op, wait=True)
        open_history(w.hub, w.mq)
        select_job(w.hub, w.mq, a["job_id"])
        w.hub.historyReplay_(None)
        a_sid = _playing(w.sounds)
        assert len(a_sid) == 1, f"fixture: A not playing ({w.sounds.events})"
        rendered = select_job(w.hub, w.mq, b["job_id"])
        w.hub.historyReplay_(None)
        return w, a_sid[0], rendered
    except BaseException:
        w.__exit__(*sys.exc_info())
        raise


@case("G06 XM-C108 (replaying B whose audio is purged or absent while A"
      " plays stops A, starts nothing and reports B's reason)")
def g06_xm_c108_unavailable_replay_stops_and_reports_reason():
    bad = {}
    for kind in ("purged", "no_artifact"):
        w, a_sid, rendered = _replay_world(kind)
        try:
            reason = (rendered.get("audio") or {}).get("reason")
            assert reason, f"fixture: B's audio is available ({rendered})"
            live = _playing(w.sounds)
            text = pane(w.hub)
            problems = []
            if live or w.hub.replay.is_playing():
                problems.append(f"still playing {live}")
            if f"Replay unavailable ({reason})" not in text:
                shown = [ln for ln in text.splitlines()
                         if "Replay unavailable" in ln]
                problems.append(f"B's reason {reason!r} not reported;"
                                f" shown {shown}")
            if problems:
                bad[kind] = problems
        finally:
            w.__exit__(None, None, None)
    assert not bad, bad


@case("G06 XM-C108 control (B with audio: A stops and B plays)",
      kind="control")
def c_g06_xm_c108_available_replay_switches_to_b():
    w, a_sid, _rendered = _replay_world("present")
    try:
        live = _playing(w.sounds)
        assert live and a_sid not in live and w.hub.replay.is_playing(), (
            live, w.sounds.events)
    finally:
        w.__exit__(None, None, None)


# =============================================================================
# XM-C109 — a moved note stays independent; transforming it never
# revives the source job
# =============================================================================

def _c109_world(consent, move):
    hw = W12.HubWorld(consent=consent)
    try:
        hw.d.cfg["log_transcripts"] = True
        hw.h.press()
        hw.h.release()
        fn, args = hw.h.run_coordinator()
        fn(*args)
        hw.drain()
        job = args[1]["job_id"]
        final = final_text(HistoryQueryService(hw.store).job_detail(job))
        assert final, "fixture: the dictation left no History final"
        out = hw.d.hubSaveHistoryRow("job", job, move=move)
        hw.drain()
        assert out.get("outcome") == ("moved" if move else "copied"), \
            f"fixture: {out}"
        return hw, job, final, out["note_id"]
    except BaseException:
        hw.close()
        raise


def _whole_note_transform(hw, note_id):
    hw.open_note(note_id)
    assert hw.focus(), "fixture: editor focus seam unavailable"
    hw.hub.scratchpad_transforms.selectItemAtIndex_(0)
    hw.hub.scratchpadTransform_(None)
    assert hw.d._tf_active is not None, "fixture: no transform started"
    # The transform thread posts its result to the main queue; the
    # drain then runs it on "main".
    assert W12.wait_for(lambda: not any(
        t.name == "localflow-transform" and t.is_alive()
        for t in threading.enumerate()), 10), \
        "fixture: the transform thread never finished"
    hw.drain()
    assert hw.d._tf_active is None, "fixture: the result never arrived"
    panel = hw.d._tf_panel
    result = panel._state["result"]
    assert result is not None, "fixture: no transform result shown"
    panel.panelAccept_(None)
    hw.settle_notes()
    hw.drain()
    return result.output


def _job_snapshot(store, job):
    return (rows(store, "SELECT artifact_id, purged FROM artifacts WHERE"
                 " job_id=? ORDER BY rowid", (job,)),
            job_row(store, job),
            bool(one(store, "SELECT 1 FROM job_deletions WHERE job_id=?",
                     (job,))))


@case("G06 XM-C109 (a note moved from History stays live and independent"
      " after its source job is deleted; a whole-note transform never"
      " recreates the job; consent on and off)")
def g06_xm_c109_transform_of_moved_note_never_revives_job():
    bad = {}
    for consent in (False, True):
        hw, job, final, note_id = _c109_world(consent, move=True)
        try:
            store = hw.store
            jobs0 = one(store, "SELECT COUNT(*) FROM jobs")[0]
            assert one(store, "SELECT 1 FROM job_deletions WHERE job_id=?",
                       (job,)), "fixture: the move did not delete the job"
            before_live = live_text_artifacts(store, job)
            output = _whole_note_transform(hw, note_id)
            store.sync()
            cur = one(store, "SELECT r.content_text, r.origin FROM notes n"
                      " JOIN note_revisions r ON r.revision_id ="
                      " n.current_revision_id WHERE n.note_id=?",
                      (note_id,))
            prov = [p for (p,) in rows(
                store, "SELECT source_job_id FROM note_revisions WHERE"
                " note_id=? ORDER BY rowid", (note_id,))]
            problems = []
            if before_live or live_text_artifacts(store, job):
                problems.append("live text rows for the deleted job:"
                                f" {live_text_artifacts(store, job)}")
            if one(store, "SELECT COUNT(*) FROM jobs")[0] != jobs0:
                problems.append("a job row appeared")
            if HistoryQueryService(store).job_detail(job) is not None:
                problems.append("the deleted job resolves in History")
            if cur is None or cur[0] != output:
                problems.append(f"note current revision {cur} is not the"
                                f" transform output {output!r}")
            if not prov or prov[0] != job:
                problems.append(f"note provenance lost: {prov}")
            if problems:
                bad["consent " + ("on" if consent else "off")] = problems
        finally:
            hw.close()
    assert not bad, bad


@case("G06 XM-C109 control (Copy then a transform leaves the job live and"
      " unchanged)", kind="control")
def c_g06_xm_c109_copied_row_job_stays_unchanged():
    hw, job, final, note_id = _c109_world(False, move=False)
    try:
        store = hw.store
        snap0 = _job_snapshot(store, job)
        output = _whole_note_transform(hw, note_id)
        store.sync()
        assert _job_snapshot(store, job) == snap0, (snap0,
                                                    _job_snapshot(store,
                                                                  job))
        assert final_text(HistoryQueryService(store).job_detail(job)) == \
            final
        assert one(store, "SELECT r.content_text FROM notes n JOIN"
                   " note_revisions r ON r.revision_id ="
                   " n.current_revision_id WHERE n.note_id=?",
                   (note_id,))[0] == output
    finally:
        hw.close()


# =============================================================================
# runner (the harness runner of test_xm_remediation.py)
# =============================================================================

def redact(text):
    import re
    import tempfile
    if not text:
        return text
    tmp = tempfile.gettempdir()
    for real, mark in ((str(ROOT), "<repo>"),
                       ("/private" + tmp, "<tmp>"), (tmp, "<tmp>"),
                       (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


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
            tb = traceback.format_exc()
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + tb[-1200:])
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
    print("xm g06 c1:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_g06_c1.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_g06_c1.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
