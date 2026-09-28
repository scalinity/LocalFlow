"""M09 remediation regressions (2026-09-26 read-only audit at 7cd1111).

One or more cases per reproducible finding M09-AUDIT-01..29 (plus the
local findings recorded during adjudication), each driven through the
REAL Hub actions, HubState, services and — where the finding lives
there — the real coordinator (lifecycle Harness: real AppDelegate over
a temporary store), the real InsertionService over the fixture target
and the real store writer. Fixtures are synthetic (``m09_world``).

Ordering is decided by latches (``Latch``/events), never by sleeps.
Hub refreshes and completions run through ``MainQueue``: a deferred
AppHelper.callAfter drained on this script's main thread, so every
AppKit mutation happens on main as with the real run loop.

The same file runs on the audited base (where each defect case is
expected to FAIL on the defect it names — a behavioral witness through
entry points the base already has, never an absent-API error) and on
the repaired code. Cases marked ``control`` pin accepted behavior and
must pass on both.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/ui/test_m09_remediation.py [--json OUT] [-k NAME]
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

from m09_world import (APP_A, APP_B, CANARY_A, CANARY_B,  # noqa: E402
                       CANARY_C, Latch, MainQueue, World, advance_stage,
                       code_stamp, event, history_rows, iso, is_main,
                       join_work, open_view, rendered_text, seed_example,
                       seed_job, seed_legacy_db, seed_legacy_pair,
                       thread_oracle, write_events)

try:
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
except Exception:  # pragma: no cover — non-macOS guard
    NSApplication = None

CASES = []
T0 = 1790000000.0  # 2026-09-21T... (fixed synthetic epoch)


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# ---- small helpers -----------------------------------------------------------

def open_training(w):
    open_view(w.hub, w.mq, "models")
    w.hub.state.select_models_subview("training")
    w.drain()


def select_training(w, ex):
    w.hub.state.select_training_example(ex)
    w.drain()


def select_history(w, kind, rid):
    w.hub.state.select_history_row(kind, rid)
    w.drain()


def latch_training(w):
    lat = Latch(w.hub.spec["training_service"])
    w.hub.spec["training_service"] = lat
    w.hub.state.training_service = lat
    return lat


def latch_history(w):
    lat = Latch(w.hub.state.history_service)
    w.hub.state.history_service = lat
    return lat


def record_coordinator(d, name, result):
    calls = []
    real = getattr(d, name)

    def fake(*a, **kw):
        calls.append((a, kw))
        return result(*a, **kw) if callable(result) else result
    setattr(d, name, fake)
    return calls, real


def mutations(lat):
    return [c for c in lat.calls if c[0] in (
        "mark_intended", "set_verbatim", "add_span_correction", "pin",
        "exclude", "delete_everywhere")]


def example_state(store, ex):
    return store.submit(lambda c: c.execute(
        "SELECT state FROM training_examples WHERE example_id=?",
        (ex,)).fetchone()[0])


def annotation_kinds(store, ex):
    env = store.latest_revision(ex) or {}
    return [a.get("kind") for a in env.get("annotations") or []]


def everything_rendered(hub):
    """Every string the built Hub currently renders (text views, fields,
    labels, the rendered History table cells)."""
    out = []
    for name in ("history_detail", "training_detail", "verbatim_field",
                 "span_corrected", "teach_field", "review_text",
                 "diag_text", "models_text"):
        v = getattr(hub, name, None)
        if v is None:
            continue
        try:
            out.append(str(v.string()))
        except Exception:
            out.append(str(v.stringValue()))
    for e in getattr(hub, "_history_flat", []) or []:
        out.append(json.dumps(e))
    return "\n".join(out)


class FakeAlertFactory:
    """Stand-in for AppKit's NSAlert inside an action (no modal). The
    value runModal returns for the confirming button is the REAL
    button tag each API produces (measured natively: the legacy
    alertWithMessageText: Delete button has tag 1, a modern alert's
    first added button has tag 1000). ``during_modal`` runs while the
    'modal' is open — a queued callback changing selection."""

    def __init__(self, during_modal=None, confirm=True):
        self.during_modal = during_modal
        self.confirm = confirm
        self.shown = 0
        outer = self

        class _Alert:
            def __init__(self, legacy):
                self.legacy = legacy
                self.buttons = []

            def addButtonWithTitle_(self, t):
                self.buttons.append(t)

            def setMessageText_(self, t):
                pass

            def setInformativeText_(self, t):
                pass

            def setAlertStyle_(self, s):
                pass

            def runModal(self):
                outer.shown += 1
                if outer.during_modal is not None:
                    outer.during_modal()
                if self.legacy:
                    return 1 if outer.confirm else 0
                return 1000 if outer.confirm else 1001

        class _AlertClass:
            @staticmethod
            def alertWithMessageText_defaultButton_alternateButton_otherButton_informativeTextWithFormat_(*a):  # noqa: E501
                return _Alert(True)

            @staticmethod
            def alloc():
                class _A:
                    @staticmethod
                    def init():
                        return _Alert(False)
                return _A

        self.cls = _AlertClass


def patch_appkit(name, value):
    import AppKit
    real = getattr(AppKit, name)
    setattr(AppKit, name, value)
    return lambda: setattr(AppKit, name, real)


# ---- M09-AUDIT-01: selection / rendered identity ------------------------------

@case("M09-AUDIT-01")
def test_a01_history_actions_during_selection_interval():
    """C002: A loaded, B selected with its detail held — Paste Again,
    Retry and Copy must not act on A; after B binds they act on B."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0),
                            state="failed_recoverable")
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60),
                            state="failed_recoverable")
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", ja)
        assert CANARY_A in rendered_text(w.hub.history_detail), \
            "precondition: A detail rendered"
        pastes, _ = record_coordinator(w.d, "hubPasteText",
                                       {"outcome": "repaste_queued"})
        retries, _ = record_coordinator(w.d, "hubRetryJob",
                                        {"outcome": "requeued"})
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        gate = lat.hold("job_detail", when=lambda jid: jid == jb,
                        after=False)
        w.hub.state.select_history_row("job", jb)
        assert gate.arrived.wait(5)
        w.mq.flush()  # render whatever the interval state is
        w.hub.historyPasteAgain_(None)
        w.hub.historyRetry_(None)
        w.hub.historyCopy_(None)
        wrong = [c for c in pastes + retries + copies
                 if ja in json.dumps(c) or CANARY_A in json.dumps(c)]
        gate.release.set()
        w.drain()
        assert not wrong, f"wrong-record action on A while B selected: {wrong}"
        # Positive control: B bound and rendered — the same actions act on B.
        assert CANARY_B in rendered_text(w.hub.history_detail)
        w.hub.historyPasteAgain_(None)
        w.hub.historyRetry_(None)
        assert pastes and pastes[-1][0][0] == CANARY_B \
            and pastes[-1][1].get("job_id") == jb, pastes
        assert retries and retries[-1][0][0] == jb, retries


@case("M09-AUDIT-01")
def test_a01_training_mark_during_selection_interval():
    """C002/C024: A rendered, B selected with its detail held — Mark
    Correct must not attach a judgment made on A's visible text to B."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        open_training(w)
        lat = latch_training(w)
        select_training(w, a["example_id"])
        assert CANARY_A in rendered_text(w.hub.training_detail)
        gate = lat.hold("example_detail",
                        when=lambda ex: ex == b["example_id"], after=False)
        w.hub.state.select_training_example(b["example_id"])
        assert gate.arrived.wait(5)
        w.mq.flush()
        w.hub.trainingMarkCorrect_(None)
        w.hub.trainingPin_(None)
        w.hub.trainingExclude_(None)
        interval = mutations(lat)
        gate.release.set()
        w.drain()
        assert not interval, \
            f"mutation while rendered A and selected B disagree: {interval}"
        # Positive control: B rendered → the mark lands on B only.
        assert CANARY_B in rendered_text(w.hub.training_detail)
        w.hub.trainingMarkCorrect_(None)
        w.drain()
        marks = [c for c in lat.calls if c[0] == "mark_intended"]
        assert marks and marks[-1][1][0] == b["example_id"], marks
        env_a = w.store.latest_revision(a["example_id"])
        assert env_a["outcome"]["correctness"] == "unreviewed"


@case("M09-AUDIT-01")
def test_a01_training_editor_buffers_bound_to_rendered_example():
    """C024: span/verbatim buffers typed for A are not saved onto B
    while B's detail is pending."""
    with World() as w:
        a = seed_example(w.store, "alpha beta " + CANARY_A)
        b = seed_example(w.store, "gamma delta " + CANARY_B)
        open_training(w)
        lat = latch_training(w)
        select_training(w, a["example_id"])
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_corrected.setStringValue_("ALPHA")
        gate = lat.hold("example_detail",
                        when=lambda ex: ex == b["example_id"], after=False)
        w.hub.state.select_training_example(b["example_id"])
        assert gate.arrived.wait(5)
        w.mq.flush()
        w.hub.trainingSpan_(None)
        gate.release.set()
        w.drain()
        # And after B binds, A's buffers must not silently apply to B.
        w.hub.trainingSpan_(None)
        w.drain()
        spans = [c for c in lat.calls if c[0] == "add_span_correction"]
        assert not spans, f"A's span buffer saved onto B: {spans}"
        assert "span_correction" not in annotation_kinds(
            w.store, b["example_id"])


@case("M09-AUDIT-01")
def test_a01_training_table_click_uses_rendered_row():
    """C025: the table still shows [A, B]; the backing list was replaced
    by [B, A] but not yet rendered — clicking row 0 selects A (the
    rendered row) or refuses; never B."""
    from Foundation import NSIndexSet
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        open_training(w)
        rendered = [w.hub.tableView_objectValueForTableColumn_row_(
            w.hub.training_table, w.hub.training_table.tableColumns()[0], i)
            for i in range(w.hub.numberOfRowsInTableView_(
                w.hub.training_table))]
        assert rendered[0].startswith(b["example_id"][:20]), rendered
        # Replace the backing list with the reverse order; do NOT flush.
        real = w.hub.state.training_service.examples
        w.hub.state.training_service.examples = \
            lambda **kw: list(reversed(real(**kw)))
        w.hub.state.reload_training()
        join_work(5)
        w.hub.state.wait_for_queries(5)
        # AppKit has not reloaded; the user clicks the rendered row 0.
        w.hub.training_table.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(0), False)
        sel = w.hub.state.views["models"]["selected_id"]
        w.drain()
        assert sel in (b["example_id"], None), \
            f"click on rendered row 0 ({b['example_id'][:12]}) selected {sel}"


@case("M09-AUDIT-01")
def test_a01_history_teach_buffer_bound_to_rendered_row():
    """C128 (local): a correction typed against History row A is not
    carried to row B, where Teach would submit it against B."""
    with World() as w:
        a = seed_example(w.store, "buffer " + CANARY_A)
        b = seed_example(w.store, "buffer " + CANARY_B)
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", a["job_id"])
        w.hub.teach_field.setStringValue_("typed for " + CANARY_A)
        select_history(w, "job", b["job_id"])
        assert CANARY_A not in str(w.hub.teach_field.stringValue()), \
            "A's typed correction carried to row B"


@case("M09-AUDIT-02")
def test_a02_history_teach_buffer_cleared_on_delete():
    """C128: deleting the selected job clears the correction typed
    against it, although the revocation's own queued refresh has
    already cleared the rendered detail."""
    with World() as w:
        a = seed_example(w.store, "buffer " + CANARY_A)
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", a["job_id"])
        w.hub.teach_field.setStringValue_("typed for " + CANARY_A)
        w.store.delete_everywhere("job", a["job_id"])
        w.drain()
        assert CANARY_A not in everything_rendered(w.hub), \
            "a deleted row's typed correction survived"


@case("M09-AUDIT-01", kind="control")
def test_a01_history_teach_buffer_survives_same_row_reload():
    """Control: a reload of the same row keeps what the user typed."""
    with World() as w:
        a = seed_example(w.store, "buffer " + CANARY_A)
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", a["job_id"])
        w.hub.teach_field.setStringValue_("typed for " + CANARY_A)
        w.hub.state.reload_history()
        w.drain()
        assert str(w.hub.teach_field.stringValue()) == \
            "typed for " + CANARY_A


@case("M09-LOCAL-01")
def test_local01_training_delete_confirm_deletes_confirmed_identity():
    """C026 + local finding: the real Delete Everywhere button with the
    confirmation's REAL confirm tag deletes the example that was
    selected when the confirmation opened — even if a queued callback
    changes selection while the modal runs — and nothing else."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        open_training(w)
        select_training(w, a["example_id"])
        fake = FakeAlertFactory(during_modal=lambda: (
            w.hub.state.select_training_example(b["example_id"]),
            w.drain()))
        undo = patch_appkit("NSAlert", fake.cls)
        try:
            w.hub.trainingDelete_(None)
        finally:
            undo()
        w.drain()
        assert fake.shown == 1, "confirmation never shown"
        assert example_state(w.store, a["example_id"]) == "deleted", \
            "confirmed Delete did not delete the confirmed example"
        assert example_state(w.store, b["example_id"]) != "deleted", \
            "deleted the example selected during the modal"


@case("M09-LOCAL-01", kind="control")
def test_local01_training_delete_cancel_deletes_nothing():
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        fake = FakeAlertFactory(confirm=False)
        undo = patch_appkit("NSAlert", fake.cls)
        try:
            w.hub.trainingDelete_(None)
        finally:
            undo()
        w.drain()
        assert example_state(w.store, a["example_id"]) != "deleted"


# ---- M09-AUDIT-02: deletion revokes cached plaintext ------------------------

@case("M09-AUDIT-02")
def test_a02_training_delete_clears_detail_and_editor():
    """C089: after the delete action A's text is gone from state,
    rendered detail and editor buffers — immediately and after the
    background reload."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        seed_example(w.store, CANARY_B)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.verbatim_field.setStringValue_(CANARY_A + " typed")
        w.hub.span_corrected.setStringValue_(CANARY_A + " span")
        w.hub._delete_example()
        now = json.dumps(w.hub.state.views["models"], default=str)
        w.drain()
        assert CANARY_A not in now, "deleted text still in Training state"
        assert CANARY_A not in json.dumps(
            w.hub.state.views, default=str), "deleted text cached in state"
        assert CANARY_A not in everything_rendered(w.hub), \
            "deleted text still rendered"


@case("M09-AUDIT-02")
def test_a02_cross_view_history_cache_after_training_delete():
    """C090: A loaded in History (detail + list preview); A deleted from
    Training while History is not selected; revisiting History never
    shows A's text again."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        w.store.set_job_target(a["job_id"], "Notes", APP_A)
        w.store.sync()
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", a["job_id"])
        assert CANARY_A in rendered_text(w.hub.history_detail)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub._delete_example()
        w.drain()
        cached = json.dumps(w.hub.state.views["history"], default=str)
        open_view(w.hub, w.mq, "history")
        assert CANARY_A not in cached, "History cache kept deleted text"
        assert CANARY_A not in everything_rendered(w.hub)
        assert CANARY_A not in json.dumps(w.hub.state.views, default=str)


@case("M09-AUDIT-02")
def test_a02_late_detail_publication_after_delete():
    """C011: A's detail materialized before deletion, published after —
    the late result never reaches state or screen."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("job_detail", when=lambda jid: jid == ja,
                        after=True)
        w.hub.state.select_history_row("job", ja)
        assert gate.arrived.wait(5), "A detail never read"
        w.store.delete_everywhere("job", ja)
        gate.release.set()
        w.drain()
        assert CANARY_A not in json.dumps(w.hub.state.views, default=str), \
            "late pre-deletion detail republished deleted text"
        assert CANARY_A not in everything_rendered(w.hub), \
            "deleted text rendered from a late publication"
        # A captured action cannot copy/paste the revoked text either.
        pastes, _ = record_coordinator(w.d, "hubPasteText", {})
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        w.hub.historyPasteAgain_(None)
        w.hub.historyCopy_(None)
        assert CANARY_A not in json.dumps(pastes + copies)


@case("M09-AUDIT-02", kind="control")
def test_a02_independent_history_lease_survives_training_expiry():
    """C082 control: a training-interest expiry does not purge text a
    History lease still retains (no blanket purge in the repair)."""
    with World() as w:
        c = seed_example(w.store, CANARY_C, applied=CANARY_C + " applied")
        w.store.grant_lease(c["raw"], "history", days=400)
        days = w.store.retention_days["training_buffer"]
        out = w.store.prune_training(now=time.time() + (days + 2) * 86400)
        assert out["expired"] == 1 and out["kept_by_other_interest"] >= 1
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", c["job_id"])
        shown = rendered_text(w.hub.history_detail)
        assert CANARY_C in shown, "History-leased text purged with training"
        assert CANARY_C + " applied" not in shown


# ---- M09-AUDIT-03: atomic publication; errors guarded -----------------------

class _HoldAtLockEntry:
    """The state lock, except that the publishing thread flagged by
    ``_publish_probe`` pauses just BEFORE acquiring it — after any
    generation check placed outside the lock, before the mutation."""

    def __init__(self, real, probe, local):
        self._real, self._probe, self._local = real, probe, local

    def __enter__(self):
        if getattr(self._local, "hold", False):
            self._local.hold = False
            self._probe["arrived"].set()
            self._probe["release"].wait(10)
        return self._real.__enter__()

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)


def _publish_probe(state):
    """Hold a publication whose data contains a marker in the last
    window before its mutation that does not hold the state lock: at
    lock entry inside the guarded publication, or — where publication
    takes no lock (the base) — at its entry, after the loader's check.
    A check outside the atomic boundary is stale by then."""
    real = state._publish_locked
    probe = {"hold": None, "arrived": threading.Event(),
             "release": threading.Event(), "seen": []}
    local = threading.local()
    locked = hasattr(state, "_lock")
    if locked:
        state._lock = _HoldAtLockEntry(state._lock, probe, local)

    def wrapped(view, *a, **kw):
        blob = json.dumps(kw.get("data"), default=str)
        probe["seen"].append((view, blob[:200]))
        marker = probe["hold"]
        hold = bool(marker and marker in blob
                    and not probe["release"].is_set())
        if hold and not locked:
            probe["arrived"].set()
            probe["release"].wait(10)
        local.hold = hold and locked
        try:
            return real(view, *a, **kw)
        finally:
            local.hold = False
    state._publish_locked = wrapped
    return probe


@case("M09-AUDIT-03")
def test_a03_publication_check_and_mutation_atomic():
    """C023/C001: A passes validation, pauses before mutating; B is
    admitted and published; A resumes — A must not overwrite B."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        open_view(w.hub, w.mq, "history")
        probe = _publish_probe(w.hub.state)
        probe["hold"] = ja
        w.hub.state.set_history_search(CANARY_A)
        assert probe["arrived"].wait(5)
        w.hub.state.set_history_search(CANARY_B)
        deadline = time.monotonic() + 5
        while not any(jb in s for _v, s in probe["seen"]) \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        assert any(jb in s for _v, s in probe["seen"]), \
            "B never reached publication while A was held"
        probe["release"].set()
        w.drain()
        ids = [r["id"] for r in history_rows(w.hub)]
        assert ids == [jb], f"stale A overwrote newer B: {ids}"


@case("M09-AUDIT-03")
def test_a03_old_error_after_new_success():
    """C021: A raises after B succeeded — B data and a clear error
    survive."""
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **kw: kw.get("text") ==
                        CANARY_A, after=False,
                        error=RuntimeError("synthetic A failure"))
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.hub.state.set_history_search(CANARY_B)
        deadline = time.monotonic() + 5
        while [r["id"] for r in history_rows(w.hub)] != [jb] \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [r["id"] for r in history_rows(w.hub)] == [jb], \
            "B never published while A was held"
        gate.release.set()
        w.drain()
        view = w.hub.state.views["history"]
        assert [r["id"] for r in history_rows(w.hub)] == [jb]
        assert not view.get("error"), \
            f"stale A error overwrote B: {view.get('error')}"
        assert "query failed" not in rendered_text(w.hub.history_detail)


@case("M09-AUDIT-03", kind="control")
def test_a03_old_success_after_new_error():
    """C022 control: B's error stays authoritative; A's late success
    does not masquerade as B."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        seed_job(w.store, CANARY_C, captured=iso(T0 + 60))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate_a = lat.hold("search", when=lambda **kw: kw.get("text") ==
                          CANARY_A, after=True)
        lat.fail("search", RuntimeError("B failed"),
                 when=lambda **kw: kw.get("text") == CANARY_B)
        w.hub.state.set_history_search(CANARY_A)
        assert gate_a.arrived.wait(5)
        w.hub.state.set_history_search(CANARY_B)
        deadline = time.monotonic() + 5
        while not w.hub.state.views["history"].get("error") \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        assert w.hub.state.views["history"].get("error"), \
            "B's error never published while A was held"
        gate_a.release.set()
        w.drain()
        view = w.hub.state.views["history"]
        assert view.get("error"), "B's error lost"
        # The browse before the searches listed both rows; A's search
        # result is exactly [A] — it must never become the current data.
        assert [r["id"] for r in history_rows(w.hub)] != [ja], \
            "A's late search result published over B's error"


@case("M09-AUDIT-03")
def test_a03_old_detail_error_after_newer_detail():
    """A's detail read fails after B's detail was published: the History
    pane keeps B and shows no stale failure."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("job_detail", when=lambda jid: jid == ja,
                        after=False, error=RuntimeError("A detail failed"))
        w.hub.state.select_history_row("job", ja)
        assert gate.arrived.wait(5)
        w.hub.state.select_history_row("job", jb)
        deadline = time.monotonic() + 5
        while (w.hub.state.views["history"].get("detail") or {}).get(
                "job_id") != jb and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (w.hub.state.views["history"].get("detail") or {}).get(
            "job_id") == jb, "B's detail never published while A was held"
        gate.release.set()
        w.drain()
        view = w.hub.state.views["history"]
        assert (view.get("detail") or {}).get("job_id") == jb
        assert not view.get("error") and not view.get("detail_error"), \
            (view.get("error"), view.get("detail_error"))
        assert "failed" not in rendered_text(w.hub.history_detail)


# ---- M09-AUDIT-10: bounded query work ---------------------------------------

@case("M09-AUDIT-10")
def test_a10_hundred_searches_bounded_and_fully_drained():
    """C019: 100 search changes behind a held first query. Admission is
    bounded (threads and service calls), the latest result is correct
    and every admitted task drains."""
    with World() as w:
        jids = [seed_job(w.store, f"row{i} common", captured=iso(T0 + i))[0]
                for i in range(3)]
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        # Every search but the last is held: at most the two a slot started
        # can reach the store before row2, whatever the scheduling.
        gate = lat.hold("search", when=lambda **kw: kw.get("text") != "row2",
                        after=False)
        before = {t.ident for t in threading.enumerate()}
        w.hub.state.set_history_search("q0")
        assert gate.arrived.wait(5)
        peak = 0
        for i in range(1, 100):
            w.hub.state.set_history_search(f"q{i}")
            live = [t for t in threading.enumerate()
                    if t.ident not in before and t.is_alive()]
            peak = max(peak, len(live))
        w.hub.state.set_history_search("row2")
        live = [t for t in threading.enumerate()
                if t.ident not in before and t.is_alive()]
        peak = max(peak, len(live))
        gate.release.set()
        assert w.mq.drain(w.hub.state, 20), "admitted work did not drain"
        searches = [c for c in lat.calls if c[0] == "search"]
        ids = [r["id"] for r in history_rows(w.hub)]
        assert ids == [jids[2]], ids
        assert peak <= 2, f"{peak} query threads admitted for 101 searches"
        assert len(searches) <= 3, \
            f"{len(searches)} superseded searches still ran on the store"
        stats = w.hub.state.query_stats()
        assert stats["started"] + stats["superseded_before_start"] == \
            stats["admitted"] and w.hub.state.queries_idle(), stats


# ---- M09-AUDIT-22: truthful loading / refusal / failure ---------------------

@case("M09-AUDIT-10")
def test_a10_held_query_in_one_view_never_blocks_another():
    """C003 (local): a Training load held inside its service must not
    delay History — another key's latest request still runs and
    publishes while the held one waits."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        seed_example(w.store, CANARY_C)
        open_view(w.hub, w.mq, "history")
        lat = latch_training(w)
        gate = lat.hold("examples", after=False)
        w.hub.state.select_view("models")
        w.hub.state.select_models_subview("training")
        assert gate.arrived.wait(5), "Training load never started"
        w.hub.state.set_history_search(CANARY_A)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and \
                [r["id"] for r in history_rows(w.hub)] != [ja]:
            time.sleep(0.005)
        published = [r["id"] for r in history_rows(w.hub)]
        gate.release.set()
        w.drain()
        assert published == [ja], \
            "History waited behind a held Training load"


@case("M09-AUDIT-03")
def test_a03_newest_request_runs_while_stale_one_is_held():
    """C001 (local): request A for History is held inside the service;
    the newer B for the same key runs and publishes without waiting
    for A, and A's late result is refused."""
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **kw: kw.get("text") ==
                        CANARY_A, after=True)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.hub.state.set_history_search(CANARY_B)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and \
                [r["id"] for r in history_rows(w.hub)] != [jb]:
            time.sleep(0.005)
        published = [r["id"] for r in history_rows(w.hub)]
        gate.release.set()
        w.drain()
        assert published == [jb], "B waited behind the held stale A"
        assert [r["id"] for r in history_rows(w.hub)] == [jb]


@case("M09-AUDIT-22")
def test_a22_empty_history_is_an_honest_empty_state():
    """C127: an empty store says so, and a filter matching nothing says
    that — never "select a row" over an empty table."""
    with World() as w:
        open_view(w.hub, w.mq, "history")
        txt = rendered_text(w.hub.history_detail)
        assert "No history yet" in txt, txt
        seed_job(w.store, CANARY_A, captured=iso(T0))
        w.hub.state.set_history_search("M09_NO_SUCH_TEXT")
        w.drain()
        txt = rendered_text(w.hub.history_detail)
        assert "Nothing matches" in txt, txt


@case("M09-AUDIT-22")
def test_a22_loading_is_a_real_transition():
    """C112: a held query shows loading; completion clears it."""
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **kw: kw.get("text") ==
                        CANARY_A, after=False)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        loading = w.hub.state.views["history"].get("loading")
        gate.release.set()
        w.drain()
        assert loading is True, "admitted outstanding query not loading"
        assert w.hub.state.views["history"].get("loading") is False


@case("M09-AUDIT-22")
def test_a22_retry_and_paste_refusals_are_visible():
    """C066/C071: the actual Retry / Paste Again buttons surface the
    coordinator's refusal for the selected row."""
    with World() as w:
        jid, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0),
                             state="saved_not_inserted")
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", jid)
        before = rendered_text(w.hub.history_detail).lower()
        assert "retry" not in before, "precondition: no retry wording yet"
        w.hub.historyRetry_(None)
        w.drain()
        shown = rendered_text(w.hub.history_detail).lower()
        assert "retry" in shown and ("not retryable" in shown
                                     or "refused" in shown), \
            "Retry refusal invisible"
        w.h.press()  # recording
        try:
            w.hub.historyPasteAgain_(None)
            w.drain()
            shown = rendered_text(w.hub.history_detail)
        finally:
            w.h.release(delivered=False)
        assert "recording" in shown.lower(), "Paste refusal invisible"


@case("M09-AUDIT-22")
def test_a22_models_failure_is_visible_not_stale_success():
    """C111: Training had good data; the next load fails — the pane says
    so instead of presenting the previous rows as current."""
    with World() as w:
        seed_example(w.store, CANARY_A)
        open_training(w)
        assert w.hub.numberOfRowsInTableView_(w.hub.training_table) == 1
        svc = w.hub.state.training_service

        def boom(**kw):
            raise RuntimeError("synthetic examples failure")
        svc.examples = boom
        w.hub.state.reload_training()
        w.drain()
        shown = str(w.hub.training_ready.stringValue()) + \
            rendered_text(w.hub.training_detail)
        assert "RuntimeError" in shown or "failed" in shown.lower(), \
            f"failure invisible: {shown[:200]!r}"


# ---- M09-AUDIT-25: native thread identity (independent oracle) ---------------

@case("M09-AUDIT-25", kind="control")
def test_a25_refresh_and_completions_run_on_main():
    """C020/C122: every Hub refresh and long-action completion (success
    and error) runs on the main thread through the real dispatch path."""
    with World() as w:
        seed_example(w.store, CANARY_A)
        log = thread_oracle(w.hub)
        done_threads = []
        real_bg = w.hub._in_background

        def bg(work, done, *a, **kw):
            def wrapped_done(*x, **y):
                done_threads.append(is_main())
                return done(*x, **y)
            return real_bg(work, wrapped_done, *a, **kw)
        w.hub._in_background = bg
        open_training(w)
        for tab in ("evidence", "review", "splits", "export"):
            w.hub.state.select_training_tab(tab)
            w.drain()
        w.hub.state.select_training_tab("review")
        w.drain()
        w.hub.reviewMine_(None)  # success path
        w.drain()
        lat = Latch(w.hub.spec["learning_service"])
        lat.fail("mine_observation_candidates",
                 RuntimeError("synthetic mine failure"))
        w.hub.spec["learning_service"] = lat
        w.hub.reviewMine_(None)  # error path
        w.drain()
        assert "synthetic mine failure" in rendered_text(
            w.hub.review_text) or "RuntimeError" in rendered_text(
            w.hub.review_text), "error completion never rendered"
        open_view(w.hub, w.mq, "insights")
        w.hub.state.select_insights_subview("voice")
        w.drain()
        assert log and all(e["main"] for e in log), \
            [e for e in log if not e["main"]]
        assert len(done_threads) == 2 and all(done_threads), done_threads


@case("M09-AUDIT-25", kind="control")
def test_a25_inline_dispatch_negative_control_is_intercepted():
    """C118: an intentionally inline dispatcher delivers a refresh on a
    query thread; the pre-mutation guard records it and the real
    refresh never runs off-main."""
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        open_view(w.hub, w.mq, "history")
        log = thread_oracle(w.hub, guard=True)
        w.mq.inline = True
        try:
            w.hub.state.set_history_search(CANARY_A)
            join_work(5)
            w.hub.state.wait_for_queries(5)
        finally:
            w.mq.inline = False
        w.drain()
        off = [e for e in log if not e["main"]]
        assert off, "inline control never produced an off-main delivery"


# ---- M09-AUDIT-04/05: lifecycle restrictions are monotone -------------------

@case("M09-AUDIT-04")
def test_a04_quarantine_survives_exclude_then_restore_via_hub():
    """C083: quarantine → (Hub) Exclude → (Hub) Include never makes the
    example live again."""
    with World() as w:
        a = seed_example(w.store, CANARY_A, state="quarantined_sensitive")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingExclude_(None)
        w.drain()
        w.hub.trainingExclude_(None)
        w.drain()
        st = example_state(w.store, a["example_id"])
        assert st == "quarantined_sensitive", \
            f"quarantine laundered through exclusion: {st}"


@case("M09-AUDIT-04")
def test_a04_expired_survives_exclude_then_restore():
    """C084 (service path, the Hub button calls the same op)."""
    from localflow.v2.training_data import TrainingDataService
    with World(build=False) as w:
        a = seed_example(w.store, CANARY_A, state="expired")
        svc = TrainingDataService(w.store)
        svc.exclude(a["example_id"], True)
        svc.exclude(a["example_id"], False)
        st = example_state(w.store, a["example_id"])
        assert st == "expired", f"expired evidence reactivated: {st}"


@case("M09-AUDIT-04", kind="control")
def test_a04_ordinary_exclusion_stays_reversible():
    from localflow.v2.training_data import TrainingDataService
    with World(build=False) as w:
        a = seed_example(w.store, CANARY_A)
        svc = TrainingDataService(w.store)
        assert svc.exclude(a["example_id"], True) == "excluded"
        assert svc.exclude(a["example_id"], False) == "captured_unreviewed"


@case("M09-AUDIT-05")
def test_a05_span_save_never_reincludes_excluded():
    """C086: a valid span on an excluded example through the Hub refuses
    (no artifact/lease/revision) and the example stays excluded."""
    with World() as w:
        a = seed_example(w.store, "alpha beta " + CANARY_A, state="excluded")
        open_training(w)
        select_training(w, a["example_id"])
        before = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM artifacts").fetchone()[0])
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_corrected.setStringValue_("ALPHA")
        w.hub.trainingSpan_(None)
        w.drain()
        after = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM artifacts").fetchone()[0])
        st = example_state(w.store, a["example_id"])
        assert st == "excluded", f"span save re-included: {st}"
        assert after == before, "annotation artifact written on excluded"


@case("M09-AUDIT-05")
def test_a05_verbatim_save_never_reincludes_excluded():
    """C087: with a legitimate replay of THIS example, a verbatim save on
    an excluded example refuses and the example stays excluded."""
    with World() as w:
        a = seed_example(w.store, CANARY_A, state="excluded")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        w.hub.verbatim_field.setStringValue_("heard words")
        w.hub.trainingVerbatim_(None)
        w.drain()
        st = example_state(w.store, a["example_id"])
        assert st == "excluded", f"verbatim save re-included: {st}"
        assert "verbatim_reference" not in annotation_kinds(
            w.store, a["example_id"])


@case("M09-AUDIT-05")
def test_a05_intended_mark_refuses_non_reviewable():
    """C088: intended-writing marks refuse on every non-reviewable state;
    an active control succeeds with intended provenance only."""
    from localflow.v2.training_data import TrainingDataService
    with World(build=False) as w:
        svc = TrainingDataService(w.store)
        wrote = {}
        for st in ("excluded", "expired", "quarantined_sensitive"):
            ex = seed_example(w.store, CANARY_A, state=st)["example_id"]
            n0 = len(w.store.submit(lambda c, e=ex: c.execute(
                "SELECT 1 FROM training_revisions WHERE example_id=?",
                (e,)).fetchall()))
            try:
                svc.mark_intended(ex, True)
            except Exception:
                pass  # a writer-op refusal surfaces as the store's error
            n1 = len(w.store.submit(lambda c, e=ex: c.execute(
                "SELECT 1 FROM training_revisions WHERE example_id=?",
                (e,)).fetchall()))
            wrote[st] = (n1 - n0, example_state(w.store, ex))
        ok = seed_example(w.store, CANARY_B)["example_id"]
        svc.mark_intended(ok, True)
        env = w.store.latest_revision(ok)
        assert env["outcome"]["correctness_provenance"] == \
            "user_explicit_intended_writing"
        assert not any(v[1] == "annotated" for v in wrote.values()), wrote
        assert all(v[0] == 0 for v in wrote.values()), \
            f"judgment written on non-reviewable evidence: {wrote}"


# ---- M09-AUDIT-06: spans bind to the reviewed immutable stage ----------------

def _span_rows(store, ex):
    env = store.latest_revision(ex) or {}
    out = []
    for a in env.get("annotations") or []:
        if a.get("kind") != "span_correction":
            continue
        art = store.artifact(a["artifact_id"])
        out.append(json.loads(art["content_text"]))
    return out


@case("M09-AUDIT-06")
def test_a06_span_after_same_length_stage_replacement():
    """C014: R1 'alpha beta' rendered; R2 'gamma beta' published without
    a reload; saving [0,5)→'delta' must refuse as stale or bind to R1 —
    never record 'gamma' as what was reviewed."""
    with World() as w:
        a = seed_example(w.store, "alpha beta")
        open_training(w)
        select_training(w, a["example_id"])
        assert "alpha beta" in rendered_text(w.hub.training_detail)
        advance_stage(w.store, a["example_id"], "source_text", "gamma beta")
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("delta")
        w.hub.trainingSpan_(None)
        w.drain()
        spans = _span_rows(w.store, a["example_id"])
        assert not any(s["original"] == "gamma" for s in spans), \
            f"R1 offsets reinterpreted against R2: {spans}"


@case("M09-AUDIT-06", kind="control")
def test_a06_unrelated_revision_keeps_same_reviewed_artifact():
    """C079 control: a later revision that leaves the reviewed source
    artifact unchanged does not force a refusal."""
    from localflow.v2.training_data import TrainingDataService
    with World() as w:
        a = seed_example(w.store, "alpha beta")
        open_training(w)
        select_training(w, a["example_id"])
        TrainingDataService(w.store).pin(a["example_id"], True)  # no revision
        w.store.update_latest_revision(
            a["example_id"], lambda e: dict(e, outcome=dict(
                e["outcome"], insertion="insertion_confirmed")))
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("delta")
        w.hub.trainingSpan_(None)
        w.drain()
        spans = _span_rows(w.store, a["example_id"])
        assert [s["original"] for s in spans] == ["alpha"], spans
        env = w.store.latest_revision(a["example_id"])
        assert env["outcome"]["insertion"] == "insertion_confirmed", \
            "the newer unrelated metadata was overwritten"


@case("M09-AUDIT-06", kind="control")
def test_a06_emoji_code_point_offsets():
    """C077 control: offsets are code points ('A🧠BC' [2,3) is 'B')."""
    with World() as w:
        a = seed_example(w.store, "A🧠BC")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.span_start.setStringValue_("2")
        w.hub.span_end.setStringValue_("3")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("b")
        w.hub.trainingSpan_(None)
        w.drain()
        assert [s["original"] for s in _span_rows(
            w.store, a["example_id"])] == ["B"]


# ---- M09-AUDIT-24: atomic annotation; timeout is not cancellation -----------

def _table_snapshot(store, ex):
    def op(c):
        return {
            "artifacts": c.execute("SELECT COUNT(*) FROM artifacts")
            .fetchone()[0],
            "leases": c.execute("SELECT COUNT(*) FROM artifact_leases")
            .fetchone()[0],
            "revisions": c.execute(
                "SELECT COUNT(*) FROM training_revisions WHERE"
                " example_id=?", (ex,)).fetchone()[0],
            "row": c.execute(
                "SELECT state, latest_revision_id FROM training_examples"
                " WHERE example_id=?", (ex,)).fetchone()}
    return store.submit(op)


class _FailAfterOp:
    """Store proxy: runs the op, then raises inside the same writer op
    (the 'after state update' failpoint — rollback must undo it all)."""

    def __init__(self, store):
        self._store = store

    def submit(self, fn, wait=True, timeout=15.0):
        def boom(conn):
            fn(conn)
            raise RuntimeError("failpoint after_state")
        return self._store.submit(boom, wait=wait, timeout=timeout)

    def __getattr__(self, n):
        return getattr(self._store, n)


@case("M09-AUDIT-24", kind="control")
def test_a24_annotation_failpoints_roll_back_completely():
    """C013: failure after artifact / lease / revision / state stage —
    every table and the latest pointer are exactly as before."""
    from localflow.v2 import training_data as td
    with World(build=False) as w:
        results = []
        for point in ("after_artifact", "after_lease", "after_revision",
                      "after_state"):
            for kind in ("verbatim", "span"):
                ex = seed_example(w.store, "alpha beta")["example_id"]
                svc = td.TrainingDataService(w.store)
                before = _table_snapshot(w.store, ex)
                restore = []
                if point == "after_artifact":
                    real = td.grant_lease_row

                    def fail(*a, **k):
                        raise RuntimeError("failpoint after_artifact")
                    td.grant_lease_row = fail
                    restore.append(lambda r=real: setattr(
                        td, "grant_lease_row", r))
                elif point in ("after_lease", "after_revision"):
                    real = td.conn_append_revision

                    def fail(*a, _p=point, _r=real, **k):
                        if _p == "after_revision":
                            _r(*a, **k)
                        raise RuntimeError("failpoint " + _p)
                    td.conn_append_revision = fail
                    restore.append(lambda r=real: setattr(
                        td, "conn_append_revision", r))
                else:
                    svc.store = _FailAfterOp(w.store)
                try:
                    if kind == "verbatim":
                        svc.set_verbatim(ex, "words", listened_audio=True)
                    else:
                        svc.add_span_correction(ex, "source_text", 0, 5, "X")
                    raised = False
                except Exception:
                    raised = True
                finally:
                    for r in restore:
                        r()
                after = _table_snapshot(w.store, ex)
                results.append((point, kind, raised, before == after))
        bad = [r for r in results if not (r[2] and r[3])]
        assert not bad, f"partial annotation survived a failpoint: {bad}"


class _SlowCaller:
    """Store proxy that shortens the CALLER's wait (the writer is held by
    the test): the op stays queued and may commit later."""

    def __init__(self, store, timeout):
        self._store = store
        self._timeout = timeout

    def submit(self, fn, wait=True, timeout=15.0):
        return self._store.submit(fn, wait=wait,
                                  timeout=min(timeout, self._timeout))

    def __getattr__(self, n):
        return getattr(self._store, n)


@case("M09-AUDIT-24")
def test_a24_timeout_is_unknown_not_failure_and_retry_is_idempotent():
    """C075: the writer is held past the caller's wait; the verbatim save
    commits later. The Hub must not claim 'not saved'; the committed
    annotation is discoverable; retrying the same save adds nothing."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        svc = w.hub.spec["training_service"]
        real_store = svc.store
        svc.store = _SlowCaller(real_store, 0.3)
        hold = threading.Event()
        real_store.submit(lambda c: hold.wait(10), wait=False)
        w.hub.verbatim_field.setStringValue_("heard words")
        w.hub.trainingVerbatim_(None)
        shown = rendered_text(w.hub.training_detail)
        hold.set()
        real_store.sync()
        svc.store = real_store
        w.drain()
        assert "not saved" not in shown.lower(), \
            f"timeout reported as certain failure: {shown[:160]!r}"
        kinds = annotation_kinds(w.store, a["example_id"])
        assert kinds.count("verbatim_reference") == 1, kinds
        # The user retries the same save after the unknown outcome.
        w.hub.verbatim_field.setStringValue_("heard words")
        if w.hub.state.views["models"].get("listened_for") != \
                a["example_id"]:
            w.hub.trainingReplay_(None)
        w.hub.trainingVerbatim_(None)
        w.drain()
        kinds = annotation_kinds(w.store, a["example_id"])
        assert kinds.count("verbatim_reference") == 1, \
            f"retry after a late commit duplicated the annotation: {kinds}"


# ---- M09-AUDIT-07: replay revocation ----------------------------------------

def _playing(sounds):
    live = {}
    for ev in sounds.events:
        if ev[0] == "play":
            live[ev[1]] = True
        elif ev[0] == "stop":
            live[ev[1]] = False
    return [sid for sid, on in live.items() if on]


@case("M09-AUDIT-07")
def test_a07_delete_stops_active_replay_and_refuses_again():
    """C012: A is playing; deleting A through the Hub stops it and drops
    the buffer; a later Replay refuses."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        assert _playing(w.sounds), "precondition: A playing"
        wav = w.store.artifact(a["audio"])["content_path"]
        w.hub._delete_example()
        w.drain()
        assert not _playing(w.sounds), "A still playing after delete"
        assert getattr(w.hub.replay, "_sound", None) is None, \
            "A's sound/buffer still retained"
        n = len(w.sounds.events)
        w.hub.trainingReplay_(None)
        w.hub.replay.play_artifact(w.store, a["audio"])
        assert not [e for e in w.sounds.events[n:] if e[0] == "play"]
        assert wav is not None


@case("M09-AUDIT-07")
def test_a07_prepared_buffer_cannot_start_after_delete():
    """C062: A's bytes are decoded, the sound is not yet created/played;
    A is deleted; the late start refuses."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        arrived, release = threading.Event(), threading.Event()
        real_factory = w.sounds.factory

        def gated(wav):
            arrived.set()
            release.wait(10)
            return real_factory(wav)
        w.hub.replay._factory = gated
        out = {}
        t = threading.Thread(target=lambda: out.update(
            w.hub.replay.play_artifact(w.store, a["audio"])))
        t.start()
        assert arrived.wait(5), "decode never reached the sound factory"
        w.store.delete_everywhere("job", a["job_id"])
        release.set()
        t.join(10)
        w.drain()
        assert not _playing(w.sounds), f"deleted audio started: {out}"
        assert out.get("status") != "playing", out


@case("M09-AUDIT-07")
def test_a07_unavailable_replacement_stops_previous():
    """C061: A playing, B unavailable — A is stopped (the documented
    policy: a replay request for another item ends the current one) and
    nothing claims B is playing."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B, audio=False)
        out_a = w.hub.replay.play_artifact(w.store, a["audio"])
        assert out_a.get("status") == "playing"
        out_b = w.hub.replay.play_artifact(w.store, None)
        assert out_b.get("available") is False
        assert not _playing(w.sounds), "A kept playing as if it were B"
        assert w.hub.replay.is_playing() is False
        assert b["example_id"]


@case("M09-AUDIT-07", kind="control")
def test_a07_failed_playback_grants_no_listening():
    """C008 control: factory exception / play()==False never open the
    verbatim gate."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        w.sounds.fail_play = True
        w.hub.trainingReplay_(None)
        assert w.hub.state.views["models"].get("listened_for") is None

        def boom(wav):
            raise ValueError("synthetic backend rejection")
        w.hub.replay._factory = boom
        w.sounds.fail_play = False
        w.hub.trainingReplay_(None)
        assert w.hub.state.views["models"].get("listened_for") is None


@case("M09-AUDIT-07", kind="control")
def test_a07_listen_gate_is_per_example_through_current_hub():
    """C007 control (historical critical): replay A → select B → B
    verbatim refuses; replay B → B saves (only B audio-reviewed)."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        select_training(w, b["example_id"])
        w.hub.verbatim_field.setStringValue_("fabricated")
        w.hub.trainingVerbatim_(None)
        w.drain()
        assert annotation_kinds(w.store, b["example_id"]) == []
        w.hub.trainingReplay_(None)
        w.hub.verbatim_field.setStringValue_("heard b")
        w.hub.trainingVerbatim_(None)
        w.drain()
        assert annotation_kinds(w.store, b["example_id"]) == \
            ["verbatim_reference"]
        assert annotation_kinds(w.store, a["example_id"]) == []


# ---- M09-AUDIT-09/17: authoritative lineage ----------------------------------

def _publish_attempt(store, job_id, fam, attempt, raw, applied, *,
                     transform=None):
    raw_id = store.write_text_artifact(job_id=job_id, stage="asr",
                                       role="raw_transcript", text=raw,
                                       retention_class="training")
    app_id = store.write_text_artifact(
        job_id=job_id, stage="cleanup", role="applied_output", text=applied,
        retention_class="training", parent_artifact_id=raw_id,
        meta={"cleanup_path": "llm"})
    env = {"training_schema_version": 1, "job_id": job_id,
           "family_id": fam, "attempt": attempt, "origin": "live_capture",
           "task_kind": "dictation", "captured_at_utc": iso(T0),
           "time_quality": "known",
           "artifact_ids": {"source_text": raw_id,
                            "applied_output": app_id},
           "missing_reasons": {}, "annotations": [],
           "outcome": {"insertion": "posted_unverified",
                       "correctness": "unreviewed"}}
    if transform is not None:
        out_id = store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_output",
            text=transform["output"], retention_class="training",
            parent_artifact_id=app_id,
            meta={"transform_id": "tf-m09", "path": transform["path"]})
        dec_id = store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_decision",
            text=json.dumps({"path": transform["path"],
                             "reason": transform["reason"]}),
            kind="transform_decision_json", retention_class="training",
            parent_artifact_id=out_id,
            meta={"transform_id": "tf-m09", "path": transform["path"]})
        env["transform"] = {"transform_id": "tf-m09", "path":
                            transform["path"], "reason": transform["reason"],
                            "applied": transform["applied"],
                            "artifact_ids": {"output": out_id,
                                             "decision": dec_id}}
    ack = store.publish_example(job_id=job_id, family_id=fam, envelope=env)
    store.sync()
    return {"raw": raw_id, "applied": app_id, "example": ack["example_id"]}


@case("M09-AUDIT-09")
def test_a09_history_shows_current_attempt_not_first_row():
    """C055/C056 (documented same-job immutable-stage fixture through the
    store's real publish path): attempt 2's envelope names the current
    stages; History shows them, even after attempt 1's raw is purged."""
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        jid, fam = w.store.create_job(captured_at_utc=iso(T0),
                                      time_quality="known",
                                      state="insertion_confirmed")
        one = _publish_attempt(w.store, jid, fam, 1, "attempt one raw",
                               "attempt one applied")
        w.store.bump_job_attempt(jid, at_least=2, wait=True)
        _publish_attempt(w.store, jid, fam, 2, "attempt two raw",
                         "attempt two applied")
        svc = HistoryQueryService(w.store)

        def stage_texts():
            d = svc.job_detail(jid)
            return {s["stage"]: (s.get("artifact") or {}).get("text")
                    for s in d["lineage"]}
        got = stage_texts()
        assert got["source"] == "attempt two raw" and \
            got["cleaned"] == "attempt two applied", got
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_text=NULL WHERE"
            " artifact_id=?", (one["raw"],)))
        got = stage_texts()
        assert got["source"] == "attempt two raw", \
            f"purged attempt-1 row shadows the current stage: {got}"
        row = [r for r in svc.search()["groups"][0]["rows"]
               if r["id"] == jid][0]
        assert "attempt two" in (row["preview"] or ""), row["preview"]


@case("M09-AUDIT-17")
def test_a17_transform_decision_is_displayed_and_final_text_authorized():
    """C057: fallback_original / needs_review show their recorded
    decision (never an undifferentiated 'Transformed' stage) and final
    text actions paste what was authorized: the transform output only
    when it was applied."""
    with World() as w:
        cases = {}
        for n, (path, applied, reason) in enumerate((
                ("applied", True, "validated"),
                ("fallback_original", False, "generation_failed"),
                ("needs_review", False, "uncertain_coverage"))):
            jid, fam = w.store.create_job(
                captured_at_utc=iso(T0 + n), time_quality="known",
                state="insertion_confirmed")
            word = ("first", "second", "third")[n]
            _publish_attempt(
                w.store, jid, fam, 1, f"{word} raw", f"{word} CLEAN",
                transform={"output": f"{word} PROPOSAL", "path": path,
                           "reason": reason, "applied": applied})
            cases[path] = jid
        pastes, _ = record_coordinator(w.d, "hubPasteText",
                                       {"outcome": "repaste_queued"})
        open_view(w.hub, w.mq, "history")
        shown = {}
        for path, jid in cases.items():
            select_history(w, "job", jid)
            shown[path] = rendered_text(w.hub.history_detail)
            w.hub.historyPasteAgain_(None)
        for path in ("fallback_original", "needs_review"):
            assert path in shown[path] and "not applied" in \
                shown[path].lower(), \
                f"{path} transform shown without its decision"
        texts = [p[0][0] for p in pastes]
        assert texts == ["first PROPOSAL", "second CLEAN", "third CLEAN"], \
            f"final-text actions ignore the recorded decision: {texts}"


# ---- M09-AUDIT-12/13: chronology and zone ------------------------------------

@case("M09-AUDIT-12")
def test_a12_same_day_merge_is_by_instant_with_one_limit():
    """C039: two jobs whose id order opposes their capture order and a
    dated legacy row between them — newest-first by instant, and the
    merged limit keeps the newest two."""
    import datetime as dt
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        day = "2026-09-26T"
        old_id = "job-" + "f" * 32   # lexically largest, captured first
        new_id = "job-" + "0" * 32   # lexically smallest, captured last
        for jid, t in ((old_id, "16:00"), (new_id, "18:00")):
            w.store.create_job(job_id=jid, captured_at_utc=day + t +
                               ":00.000Z", time_quality="known",
                               state="insertion_confirmed")
        mid = dt.datetime(2026, 9, 26, 17, tzinfo=dt.timezone.utc)
        seed_legacy_db(w.store, 5, raw="legacy raw", cleaned="legacy clean",
                       ts=mid.timestamp())
        w.store.sync()
        svc = HistoryQueryService(w.store, tz=dt.timezone.utc)
        ids = [r["id"] for g in svc.search(limit=10)["groups"]
               for r in g["rows"]]
        assert ids == [new_id, "legacy-db:5", old_id], ids
        ids2 = [r["id"] for g in svc.search(limit=2)["groups"]
                for r in g["rows"]]
        assert ids2 == [new_id, "legacy-db:5"], ids2


class _SqlLog:
    """A connection proxy recording each statement's SQL text."""

    def __init__(self, conn, log):
        self._conn, self._log = conn, log

    def execute(self, sql, params=()):
        self._log.append(sql)
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@case("M09-LOCAL-02")
def test_local02_pairs_fetched_only_with_room_and_hydrated_in_batch():
    """Full benchmark (50k jobs): browse p95 1.5 s. Every returned legacy
    log pair was hydrated by its own unindexed parent_artifact_id scan,
    although Undated pairs sort after every other row and could not
    appear once those fill the limit. Pairs are fetched only for the
    room left under the limit and a page is hydrated in batch."""
    import datetime as dt
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        for i in range(30):
            seed_job(w.store, f"dated row {i}", captured=iso(T0 + i))
        for i in range(40):
            seed_legacy_pair(w.store, f"pair raw {i}", f"pair clean {i}",
                             f"log:local02:{i}")
        w.store.sync()
        svc = HistoryQueryService(w.store, tz=dt.timezone.utc)
        sql = []
        real = w.store.submit
        w.store.submit = lambda op: real(lambda conn: op(_SqlLog(conn, sql)))

        def hydration():
            return [s for s in sql if "parent_artifact_id=?" in s
                    or "parent_artifact_id IN" in s]
        try:
            rows = [r for g in svc.search(limit=20)["groups"]
                    for r in g["rows"]]
            assert [r["kind"] for r in rows] == ["job"] * 20
            assert not hydration(), \
                f"{len(hydration())} pair lookups for 0 visible pairs"
            sql.clear()
            rows = [r for g in svc.search(limit=50)["groups"]
                    for r in g["rows"]]
            pairs = [r for r in rows if r["kind"] == "legacy_log"]
            assert len(pairs) == 20 and all(r["preview"] for r in pairs)
            assert len(hydration()) <= 1, \
                f"{len(hydration())} pair lookups for one page of 20"
        finally:
            w.store.submit = real


@case("M09-AUDIT-13")
def test_a13_default_zone_honors_historical_dst():
    """C041: the production default resolver groups an instant from the
    other DST season on its true local date (America/New_York)."""
    import datetime as dt
    import zoneinfo
    from localflow.v2.history_queries import HistoryQueryService
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        with World(build=False) as w:
            probe = ("2026-01-15T04:30:00.000Z"
                     if time.localtime().tm_isdst > 0
                     else "2026-07-15T04:30:00.000Z")
            expected = dt.datetime.strptime(
                probe, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=dt.timezone.utc).astimezone(
                zoneinfo.ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            jid, _fam = w.store.create_job(captured_at_utc=probe,
                                           time_quality="known")
            w.store.sync()
            svc = HistoryQueryService(w.store)  # production default zone
            rows = [r for g in svc.search()["groups"] for r in g["rows"]
                    if r["id"] == jid]
            assert rows and rows[0]["date"] == expected, \
                (probe, expected, rows and rows[0]["date"])
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


@case("M09-AUDIT-13")
def test_a13_explicit_offset_timestamp_policy():
    """C043: an explicit-offset instant groups like its canonical-Z
    equivalent (the adjudicated policy); malformed stays Undated."""
    import datetime as dt
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        a, _ = w.store.create_job(captured_at_utc="2026-09-26T00:10:00.000Z",
                                  time_quality="known")
        b, _ = w.store.create_job(captured_at_utc="2026-09-25T20:10:00-04:00",
                                  time_quality="known")
        c, _ = w.store.create_job(captured_at_utc="not-a-date",
                                  time_quality="known")
        w.store.sync()
        svc = HistoryQueryService(w.store, tz=dt.timezone.utc)
        dates = {r["id"]: r["date"] for g in svc.search()["groups"]
                 for r in g["rows"]}
        assert dates[a] == dates[b] == "2026-09-26", dates
        assert dates[c] is None, dates


# ---- M09-AUDIT-14/15/16: sources, identity, reachable filters ----------------

@case("M09-AUDIT-14")
def test_a14_legacy_db_row_detail_and_jobless_actions():
    """C051: an imported legacy database row selects, shows its retained
    raw/cleaned text and copies/pastes the cleaned text jobless."""
    with World() as w:
        rid = seed_legacy_db(w.store, 7, raw="legacy raw " + CANARY_A,
                             cleaned="legacy cleaned " + CANARY_B,
                             ts=T0, app="Mail", bundle=APP_A)
        pastes, _ = record_coordinator(w.d, "hubPasteText",
                                       {"outcome": "repaste_queued"})
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        open_view(w.hub, w.mq, "history")
        row = [r for r in history_rows(w.hub) if r["id"] == rid]
        assert row and row[0]["kind"] == "legacy_db", history_rows(w.hub)
        select_history(w, "legacy_db", rid)
        shown = rendered_text(w.hub.history_detail)
        assert CANARY_A in shown and CANARY_B in shown, shown[:200]
        w.hub.historyCopy_(None)
        w.hub.historyPasteAgain_(None)
        assert copies and copies[-1][0][0] == "legacy cleaned " + CANARY_B
        assert pastes and pastes[-1][0][0] == "legacy cleaned " + CANARY_B \
            and pastes[-1][1].get("job_id") is None, pastes


@case("M09-AUDIT-15")
def test_a15_legacy_pair_identity_stable_across_matching_half():
    """C052: raw-only and cleaned-only matches name the same pair and
    the detail carries both retained halves."""
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        seed_legacy_pair(w.store, "raw words M09_R_ONLY",
                         "cleaned words M09_C_ONLY", "log:1")
        svc = HistoryQueryService(w.store)

        def ids(text):
            return [r["id"] for g in svc.search(text=text)["groups"]
                    for r in g["rows"] if r["kind"] == "legacy_log"]
        by_raw, by_clean, browse = ids("M09_R_ONLY"), ids("M09_C_ONLY"), \
            ids(None)
        assert by_raw == by_clean == browse and len(browse) == 1, \
            (by_raw, by_clean, browse)
        d = svc.legacy_detail(by_raw[0])
        texts = {s["stage"]: (s["artifact"] or {}).get("text")
                 for s in d["lineage"]}
        assert texts == {"source": "raw words M09_R_ONLY",
                         "cleaned": "cleaned words M09_C_ONLY"}, texts


def _controls(view):
    out = []
    stack = [view]
    while stack:
        v = stack.pop()
        for s in v.subviews():
            stack.append(s)
            act = getattr(s, "action", None)
            if act is None:
                continue
            try:
                sel = act()
            except Exception:
                continue
            if sel:
                out.append((str(sel if isinstance(sel, str)
                                else sel.decode() if isinstance(sel, bytes)
                                else sel), s))
    return out


@case("M09-AUDIT-16")
def test_a16_history_app_and_mode_controls_reachable():
    """C047: the History pane has labeled app and mode controls; driving
    them filters the rendered rows through a background query and each
    clears."""
    with World() as w:
        ja, _, _ = seed_job(w.store, "one " + CANARY_A, captured=iso(T0),
                            app="Mail", bundle=APP_A, mode="llm")
        jb, _, _ = seed_job(w.store, "two " + CANARY_B,
                            captured=iso(T0 + 60), app="Notes",
                            bundle=APP_B, mode="basic")
        open_view(w.hub, w.mq, "history")
        ctrls = dict(_controls(w.hub._built_views["history"]))
        app_ctrl = next((c for s, c in ctrls.items() if "App" in s), None)
        mode_ctrl = next((c for s, c in ctrls.items() if "Mode" in s), None)
        assert app_ctrl is not None and mode_ctrl is not None, \
            f"no app/mode filter control in History: {sorted(ctrls)}"
        app_ctrl.setStringValue_("Mail")
        app_ctrl.sendAction_to_(app_ctrl.action(), app_ctrl.target())
        w.drain()
        assert [r["id"] for r in history_rows(w.hub)] == [ja]
        app_ctrl.setStringValue_("")
        app_ctrl.sendAction_to_(app_ctrl.action(), app_ctrl.target())
        mode_ctrl.selectItemWithTitle_("basic")
        mode_ctrl.sendAction_to_(mode_ctrl.action(), mode_ctrl.target())
        w.drain()
        assert [r["id"] for r in history_rows(w.hub)] == [jb]
        mode_ctrl.selectItemAtIndex_(0)
        mode_ctrl.sendAction_to_(mode_ctrl.action(), mode_ctrl.target())
        w.drain()
        assert sorted(r["id"] for r in history_rows(w.hub)) == \
            sorted([ja, jb])


@case("M09-AUDIT-29", kind="design")
def test_a29_deleted_job_leaves_history_immediately():
    """C092 (adjudicated policy): after delete-everywhere the job's
    metadata-only row and app target no longer surface in History;
    independent usage facts are untouched."""
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        jid, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0),
                             app="Mail", bundle=APP_A)
        usage = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM usage_facts").fetchone()[0])
        w.store.delete_everywhere("job", jid)
        svc = HistoryQueryService(w.store)
        by_app = [r["id"] for g in svc.search(app="Mail")["groups"]
                  for r in g["rows"]]
        browse = [r["id"] for g in svc.search()["groups"]
                  for r in g["rows"]]
        assert jid not in by_app and jid not in browse, (by_app, browse)
        assert svc.job_detail(jid) is None
        assert w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM usage_facts").fetchone()[0]) == usage


# ---- M09-AUDIT-08/18/19/20: diagnostics --------------------------------------

def _events_dir(w):
    import localflow.app as app_mod
    return pathlib.Path(app_mod.V2_EVENTS_DIR)


def _fake_save_panel(path):
    class _URL:
        def path(self):
            return str(path)

    class _Panel:
        def setAllowedFileTypes_(self, t):
            pass

        def setNameFieldStringValue_(self, t):
            pass

        def runModal(self):
            return 1

        def URL(self):
            return _URL()

    class _Cls:
        @staticmethod
        def savePanel():
            return _Panel()
    return _Cls


@case("M09-AUDIT-08")
def test_a08_hub_export_uses_typed_allowlist():
    """C100/C101: the actual Export Redacted action writes only typed,
    allowlisted fields — no unknown/nested/wrong-type/detail canary —
    with the redaction version and omission count on each record."""
    with World() as w:
        ed = _events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(1, "2026-09-26T10:00:00.000Z", job="job-" + "a" * 32,
                  private_text="M09_PRIVATE_CANARY",
                  payload={"text": "M09_NESTED_CANARY"},
                  reason_code={"x": "M09_WRONGTYPE_CANARY"},
                  detail="M09_DETAIL_CANARY"),
            event(2, "2026-09-26T10:00:01.000Z")])
        open_view(w.hub, w.mq, "diagnostics")
        out = w.h.tmp / "export.jsonl"
        undo = patch_appkit("NSSavePanel", _fake_save_panel(out))
        try:
            w.hub.diagnosticsExport_(None)
            w.drain()
        finally:
            undo()
        text = out.read_text()
        for canary in ("M09_PRIVATE_CANARY", "M09_NESTED_CANARY",
                       "M09_WRONGTYPE_CANARY", "M09_DETAIL_CANARY"):
            assert canary not in text, f"{canary} survived Hub export"
        recs = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        assert recs and all("redaction_version" in r and
                            "omitted_fields" in r for r in recs), recs[:1]


@case("M09-AUDIT-08")
def test_a08_model_path_never_exports_but_hub_id_does():
    """C102 (local): a locally configured model directory in
    ``model_id`` carries a home path; the support export omits it and
    counts the omission, while a hub id ("org/name") survives."""
    with World() as w:
        ed = _events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(9001, "2026-09-26T10:00:00.000Z",
                  model_id="/Users/m09-someone/models/private-model"),
            event(9002, "2026-09-26T10:00:01.000Z",
                  model_id="mlx-community/Qwen3-4B")])
        open_view(w.hub, w.mq, "diagnostics")
        out = w.h.tmp / "export.jsonl"
        undo = patch_appkit("NSSavePanel", _fake_save_panel(out))
        try:
            w.hub.diagnosticsExport_(None)
            w.drain()
        finally:
            undo()
        text = out.read_text()
        assert "m09-someone" not in text, "a home path left in the export"
        recs = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        # Keyed by the fixture's own event ids (the app writes events too).
        by_id = {r["event_id"]: r for r in recs}
        path_rec = by_id["evt-" + f"{9001:032x}"]
        hub_rec = by_id["evt-" + f"{9002:032x}"]
        assert "model_id" not in path_rec and \
            path_rec["omitted_fields"] >= 1, path_rec
        assert hub_rec["model_id"] == "mlx-community/Qwen3-4B", hub_rec


@case("M09-AUDIT-18")
def test_a18_ordering_is_stream_aware_and_filename_independent():
    """C094: two writer streams with overlapping sequences — the last-N
    window and a job timeline follow the accepted per-stream/UTC merge,
    identically after the rotated files swap names."""
    from localflow.v2 import diagnostics as diag
    import tempfile
    job = "job-" + "c" * 32
    a = [event(i, f"2026-09-26T10:00:0{2 * i - 1}.000Z", boot="a", job=job)
         for i in (1, 2, 3)]
    b = [event(i, f"2026-09-26T10:00:0{2 * i}.000Z", boot="b", job=job)
         for i in (1, 2, 3)]
    expected = [r["event_id"] + r["boot_id"][-1] for r in
                sorted(a + b, key=lambda r: r["timestamp_utc"])]
    with tempfile.TemporaryDirectory() as td:
        for names in (("events-1.jsonl", "events-2.jsonl"),
                      ("events-2.jsonl", "events-1.jsonl")):
            for f in pathlib.Path(td).glob("events-*"):
                f.unlink()
            write_events(td, names[0], a)
            write_events(td, names[1], b)
            got = [r["event_id"] + r["boot_id"][-1]
                   for r in diag.load_events(td, last=4)]
            assert got == expected[-4:], (names, got, expected[-4:])
            tl = diag.job_timeline(diag.load_events(td), job)
            order = [ln.split()[1] for ln in tl]
            assert len(tl) == 6, tl
            stamps = [ln.split()[1] for ln in tl]
            assert stamps == sorted(stamps), (names, order)


@case("M09-AUDIT-19")
def test_a19_level_all_resets_filter_via_popup():
    """C097: choose ERROR, then 'All levels' in the actual popup — every
    level is visible again."""
    with World() as w:
        ed = _events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(1, "2026-09-26T10:00:00.000Z", level="INFO",
                  name="m09.info"),
            event(2, "2026-09-26T10:00:01.000Z", level="ERROR",
                  name="m09.error")])
        open_view(w.hub, w.mq, "diagnostics")
        w.hub.diag_level.selectItemWithTitle_("ERROR")
        w.hub.diagnosticsFiltersChanged_(w.hub.diag_level)
        w.drain()
        assert w.hub.state.views["diagnostics"]["level_filter"] == "ERROR"
        w.hub.diag_level.selectItemAtIndex_(0)
        w.hub.diagnosticsFiltersChanged_(w.hub.diag_level)
        w.drain()
        assert w.hub.state.views["diagnostics"]["level_filter"] is None, \
            "All levels left the ERROR filter in place"
        assert "m09.info" in rendered_text(w.hub.diag_text)


@case("M09-AUDIT-19")
def test_a19_non_object_json_lines_are_skipped_safely():
    """C096: syntax errors, null, arrays, numbers and a JSON string
    between valid events — valid events survive; nothing private is
    echoed; no query failure."""
    with World() as w:
        ed = _events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(1, "2026-09-26T10:00:00.000Z", name="m09.valid.one"),
            event(2, "2026-09-26T10:00:01.000Z", name="m09.valid.two")],
            raw_lines=("{", "null", "[]", "123",
                       json.dumps("M09_PRIVATE_CANARY")))
        open_view(w.hub, w.mq, "diagnostics")
        view = w.hub.state.views["diagnostics"]
        shown = rendered_text(w.hub.diag_text)
        assert not view.get("error"), view.get("error")
        assert "m09.valid.one" in shown and "m09.valid.two" in shown
        assert "M09_PRIVATE_CANARY" not in shown


@case("M09-AUDIT-19")
def test_a19_utc_toggle_applies_to_job_timeline():
    """C098: with a job filter and UTC on, the timeline is shown in UTC
    like the event list."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        with World() as w:
            job = "job-" + "d" * 32
            write_events(_events_dir(w), "events-20260926-m09.jsonl", [
                event(1, "2026-09-26T03:30:00.000Z", job=job,
                      name="m09.t1")])
            open_view(w.hub, w.mq, "diagnostics")
            w.hub.diag_job_field.setStringValue_(job)
            w.hub.diag_utc.setState_(1)
            w.hub.diagnosticsFiltersChanged_(w.hub.diag_utc)
            w.drain()
            tl = w.hub.state.views["diagnostics"]["data"]["timeline"]
            assert tl and all("+00:00" in ln for ln in tl), tl
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


@case("M09-AUDIT-20")
def test_a20_export_is_the_displayed_snapshot_and_parses_off_main():
    """C016/C103: events appended after S1 was displayed are not in the
    export, and the export never parses the log on the main thread."""
    from localflow.v2 import diagnostics as diag
    with World() as w:
        ed = _events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(i, f"2026-09-26T10:00:0{i}.000Z", name=f"m09.s1.{i}")
            for i in (1, 2, 3)])
        open_view(w.hub, w.mq, "diagnostics")
        shown_ids = {r.get("event_id") for r in
                     (w.hub.state.views["diagnostics"]["data"].get(
                         "records") or [])}
        with open(ed / "events-20260926-m09.jsonl", "a") as f:
            f.write(json.dumps(event(9, "2026-09-26T10:00:09.000Z",
                                     name="m09.s2.late")) + "\n")
        main_parses = []
        real = diag.load_events

        def spy(*a, **k):
            main_parses.append(is_main())
            return real(*a, **k)
        diag.load_events = spy
        out = w.h.tmp / "snap.jsonl"
        undo = patch_appkit("NSSavePanel", _fake_save_panel(out))
        try:
            w.hub.diagnosticsExport_(None)
            w.drain()
        finally:
            undo()
            diag.load_events = real
        recs = [json.loads(ln) for ln in out.read_text().splitlines()
                if ln.strip()]
        names = [r.get("event") for r in recs]
        assert "m09.s2.late" not in names, \
            f"export re-queried past the displayed snapshot: {names}"
        assert not any(main_parses), "event log parsed on the main thread"
        if shown_ids - {None}:
            assert {r.get("event_id") for r in recs} <= shown_ids


# ---- M09-AUDIT-21: long-action completions belong to their action -----------

@case("M09-AUDIT-21")
def test_a21_mine_completion_never_forces_review_tab():
    """C105: Mine started in Review; the user moves to Export; the late
    completion does not navigate back."""
    with World() as w:
        open_training(w)
        w.hub.state.select_training_tab("review")
        w.drain()
        lat = Latch(w.hub.spec["learning_service"])
        gate = lat.hold("mine_observation_candidates", after=False)
        w.hub.spec["learning_service"] = lat
        w.hub.reviewMine_(None)
        assert gate.arrived.wait(5)
        w.hub.state.select_training_tab("export")
        w.hub.state.wait_for_queries(5)  # Mine is still held: no full drain
        w.mq.flush()
        gate.release.set()
        w.drain()
        tab = w.hub.state.views["models"].get("training_tab")
        assert tab == "export", f"late Mine completion navigated to {tab}"


class _FakeExport:
    """Export service stand-in with the real ordering: ``last_export``
    is the most recently STARTED build (export_manifests by rowid)."""

    def __init__(self):
        self.gates = {}
        self.started = []
        self.finished = set()

    def build(self, dest, task_views=(), export_id=None):
        # export_id mirrors DatasetExporter.build (M14-AUDIT-17).
        eid = f"exp-{pathlib.Path(dest).name}"
        self.started.append(eid)
        g = self.gates.get(dest)
        if g is not None:
            g[0].set()
            g[1].wait(10)
        self.finished.add(eid)
        return {"state": "finalized", "export_id": eid, "counts": {},
                "fingerprint": "f" * 16}

    def last_export(self):
        if not self.started:
            return None
        eid = self.started[-1]
        return {"export_id": eid, "state": ("finalized" if eid in
                                            self.finished else "building"),
                "task_views": [], "finalized_at_utc": None,
                "examples_count": 0, "excluded_count": 0,
                "fingerprint": "f" * 16}


@case("M09-AUDIT-21")
def test_a21_older_export_cannot_overwrite_newer_status():
    """C106: exports A then B; B completes first, A last — the moment A's
    late completion runs, the pane must not present A as the current
    export (and the settled pane shows B)."""
    with World() as w:
        fx = _FakeExport()
        w.hub.spec["export_service"] = fx
        w.hub.state.export_service = fx
        after_done = []
        real_bg = w.hub._in_background

        def bg(work, done, *a, **kw):
            def wrapped(out, err, *x, **y):
                r = done(out, err, *x, **y)
                after_done.append(((out or {}).get("export_id"),
                                   rendered_text(w.hub.export_text)))
                return r
            return real_bg(work, wrapped, *a, **kw)
        w.hub._in_background = bg
        open_training(w)
        w.hub.state.select_training_tab("export")
        w.drain()
        dest = {n: str(w.h.tmp / n) for n in ("A", "B")}
        for n in dest:
            fx.gates[dest[n]] = (threading.Event(), threading.Event())
        w.hub.export_dest.setStringValue_(dest["A"])
        w.hub.exportRun_(None)
        assert fx.gates[dest["A"]][0].wait(5)
        w.hub.export_dest.setStringValue_(dest["B"])
        w.hub.exportRun_(None)
        assert fx.gates[dest["B"]][0].wait(5)
        fx.gates[dest["B"]][1].set()
        deadline = time.monotonic() + 5
        while not any(e == "exp-B" for e, _ in after_done) \
                and time.monotonic() < deadline:
            w.hub.state.wait_for_queries(1)
            w.mq.flush()
            time.sleep(0.01)
        assert any(e == "exp-B" for e, _ in after_done), \
            "the newer export never completed while the older was held"
        fx.gates[dest["A"]][1].set()
        w.drain()
        at_a = [s for e, s in after_done if e == "exp-A"]
        assert at_a, "A's completion never ran"
        assert "exp-A" not in at_a[0], \
            f"older export presented as current: {at_a[0][:120]!r}"
        shown = rendered_text(w.hub.export_text)
        assert "exp-B" in shown and "exp-A" not in shown, shown[:160]


# ---- M09-AUDIT-11: deferred Open Hub liveness ---------------------------------

class _HeldTarget:
    """Fixture target whose first frontmost() read (inside the queued
    repaste, with busy already true) waits for the test."""

    def __new__(cls, **kw):
        from fixture_target import FixtureTargetApp

        class Held(FixtureTargetApp):
            def __init__(self, **k):
                super().__init__(**k)
                self.hold = threading.Event()
                self.arrived = threading.Event()
                self._held = False

            def frontmost(self):
                if not self._held:
                    self._held = True
                    self.arrived.set()
                    self.hold.wait(10)
                return super().frontmost()
        return Held(**kw)


def _real_insertion(w, tgt):
    from localflow.v2.insertion.service import InsertionService
    w.d._insertion = InsertionService(
        host=tgt, pasteboard=tgt.pb, keyboard=tgt, store=w.store,
        emit=lambda *a, **k: None, settle_sec=0.05)
    return w.d._insertion


def _wait_idle(svc, timeout=5.0):
    deadline = time.monotonic() + timeout
    while svc.busy and time.monotonic() < deadline:
        time.sleep(0.01)


@case("M09-AUDIT-11")
def test_a11_noop_repaste_still_delivers_deferred_open():
    """C034/C006: Open Hub twice during a repaste whose reconciliation
    finds the text already present (no transaction, no on_done) — the
    deferred show is delivered once after the service settles and no
    insertion fact is fabricated."""
    with World(build=False) as w:
        tgt = _HeldTarget(settable=False, ax_readable=True)
        tgt.set_content("before hello m09 after")
        svc = _real_insertion(w, tgt)
        assert w.d.hubPasteText("hello m09")["outcome"] == "repaste_queued"
        assert tgt.arrived.wait(5) and svc.busy
        w.d.openHub_(None)
        w.d.openHub_(None)
        assert w.d._hub is None and w.d._hub_show_pending
        tgt.hold.set()
        _wait_idle(svc)
        w.drain()
        assert w.d._hub is not None and w.d._hub.state.visible, \
            "deferred Open Hub never delivered after a no-op repaste"
        assert not w.d._hub_show_pending
        rows = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM insertions").fetchone()[0])
        assert rows == 0, "a no-op reconciliation recorded an insertion"
        w.d._insertion = None


@case("M09-AUDIT-11")
def test_a11_flush_before_busy_decrement_is_not_lost():
    """C035: when the first deferred-show wake-up is posted while the
    worker still counts the operation as busy, main runs that flush
    before the decrement (the probe holds the worker there) — the
    deferred show must still land once the service is truly idle. If
    the first wake-up is only posted after the decrement, the hazard
    cannot occur and delivery is checked the same way."""
    with World(build=False) as w:
        tgt = _HeldTarget(settable=False, ax_readable=True)
        svc = _real_insertion(w, tgt)
        posted, flushed = threading.Event(), threading.Event()
        first = {}

        def on_post(fn, a):
            if getattr(fn, "__name__", "") == "_flush_pending_hub_show" \
                    and threading.current_thread().name == \
                    "localflow-v2-insertion" and not posted.is_set():
                first["busy"] = svc.busy
                posted.set()
                if first["busy"]:
                    flushed.wait(10)  # hold the worker before its decrement
        w.mq.on_post = on_post
        assert w.d.hubPasteText("fresh m09 text")["outcome"] == \
            "repaste_queued"
        assert tgt.arrived.wait(5)
        w.d.openHub_(None)
        assert w.d._hub_show_pending
        tgt.hold.set()
        assert posted.wait(10), "no deferred-show wake-up was ever posted"
        w.mq.flush()  # main runs the first flush (while busy, if so)
        flushed.set()
        _wait_idle(svc)
        w.drain()
        assert w.d._hub is not None and w.d._hub.state.visible, \
            ("deferred show lost: the only flush saw busy"
             if first.get("busy") else "deferred show not delivered")
        w.d._insertion = None


# ---- independent review round (first pass 4166806) ---------------------------

@case("M09-AUDIT-11")
def test_r01_idle_between_pending_read_and_flag_still_shows_hub():
    """Review R-01: Open Hub reads ``pending`` (True); the queue thread
    finishes its last operation — a no-op reconciliation — before
    openHub_ records the deferred show. The idle wake-up must still
    deliver the show."""
    from localflow.v2.insertion.service import InsertionService

    class RacePending(InsertionService):
        hook = None

        @property
        def pending(self):
            value = InsertionService.pending.fget(self)
            hook, self.hook = self.hook, None
            if hook is not None:
                hook()
            return value

    with World(build=False) as w:
        tgt = _HeldTarget(settable=False, ax_readable=True)
        tgt.set_content("text already here m09")  # nothing to paste
        svc = RacePending(host=tgt, pasteboard=tgt.pb, keyboard=tgt,
                          store=w.store, emit=lambda *a, **k: None,
                          settle_sec=0.05)
        w.d._insertion = svc
        try:
            assert w.d.hubPasteText("already here m09")["outcome"] == \
                "repaste_queued"
            assert tgt.arrived.wait(5) and svc.pending
            idle = threading.Event()

            def finish_between_read_and_flag():
                # Registered after the coordinator's own listener, so it
                # fires once that listener has already run.
                svc.add_idle_listener(idle.set)
                tgt.hold.set()
                assert idle.wait(5), "the queue never went idle"
            svc.hook = finish_between_read_and_flag
            w.d.openHub_(None)
            w.drain()
            shown = w.d._hub is not None and w.d._hub.state.visible
        finally:
            w.d._insertion = None
        assert shown, "deferred Open Hub lost: the service went idle" \
            " between the pending read and the deferred flag"


def _readmission_window(state):
    """Hold the query worker when it re-admits a request OUTSIDE the
    state lock — the only place a request admitted by the user can slip
    in between the re-admission decision and the re-admission. Inside
    the lock there is no window, and nothing is held."""
    real = state._spawn
    gate = {"arrived": threading.Event(), "release": threading.Event()}

    def spawn(key, fn, **inputs):
        if threading.current_thread().name.startswith(
                "localflow-hub-query") and not state._lock._is_owned() \
                and not gate["arrived"].is_set():
            gate["arrived"].set()
            gate["release"].wait(10)
        return real(key, fn, **inputs)
    state._spawn = spawn
    return gate


@case("M09-AUDIT-03")
def test_r02_readmitted_detail_never_overrides_newer_selection():
    """Review R-02: A's detail read raced an unrelated revocation, so its
    publication re-admits it. B is selected around that re-admission; B's
    detail must be the one that renders."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        jc, _, _ = seed_job(w.store, "unrelated row", captured=iso(T0 + 1))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate_a = lat.hold("job_detail", when=lambda jid: jid == ja,
                          after=True)
        w.hub.state.select_history_row("job", ja)
        assert gate_a.arrived.wait(5)
        w.store.delete_everywhere("job", jc)          # epoch advances
        window = _readmission_window(w.hub.state)
        gate_b = lat.hold("job_detail", when=lambda jid: jid == jb,
                          after=False)

        def reads_of_a():
            return sum(1 for c in lat.calls
                       if c[0] == "job_detail" and c[1] == (ja,))
        gate_a.release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not window["arrived"].is_set() \
                and reads_of_a() < 2:
            time.sleep(0.005)
        w.hub.state.select_history_row("job", jb)     # the user clicks B
        assert gate_b.arrived.wait(5), "B's detail never started"
        window["release"].set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and reads_of_a() < 2:
            time.sleep(0.005)
        gate_b.release.set()
        w.drain()
        view = w.hub.state.views["history"]
        assert (view.get("detail") or {}).get("job_id") == jb, \
            f"B selected, detail {(view.get('detail') or {}).get('job_id')}" \
            f" loading={view.get('detail_loading')}"
        assert CANARY_B in rendered_text(w.hub.history_detail)


@case("M09-AUDIT-03")
def test_r02_readmitted_search_never_overrides_newer_search():
    """Review R-02 (list): search A raced a revocation and is re-admitted;
    the user's newer search B must keep the list."""
    with World() as w:
        ja, _, _ = seed_job(w.store, "one " + CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, "two " + CANARY_B,
                            captured=iso(T0 + 60))
        jc, _, _ = seed_job(w.store, "unrelated row", captured=iso(T0 + 1))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **kw: kw.get("text") ==
                        CANARY_A, after=True)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.store.delete_everywhere("job", jc)
        window = _readmission_window(w.hub.state)

        def searches_of_a():
            return sum(1 for c in lat.calls if c[0] == "search"
                       and c[2].get("text") == CANARY_A)
        gate.release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not window["arrived"].is_set() \
                and searches_of_a() < 2:
            time.sleep(0.005)
        w.hub.state.set_history_search(CANARY_B)
        window["release"].set()
        w.drain()
        view = w.hub.state.views["history"]
        ids = [r["id"] for r in history_rows(w.hub)]
        assert view["search"] == CANARY_B and ids == [jb], \
            f"search {view['search'][:20]!r} shows {ids}"


class _QueueReview:
    def __init__(self, rows):
        self.rows = rows

    def queue(self):
        return list(self.rows)

    def preference_pairs(self):
        return []


class _RecordingLearning:
    def __init__(self):
        self.approved, self.rejected = [], []

    # operation_id mirrors LearningService (M14-AUDIT-17).
    def approve(self, cid, counterexamples=(), operation_id=None):
        self.approved.append(cid)
        return {"flips": []}

    def reject(self, cid, operation_id=None):
        self.rejected.append(cid)
        return {}


@case("M09-AUDIT-01")
def test_r03_approve_refuses_when_selection_has_no_queue_row():
    """Review: example A is selected; the rendered queue holds only X's
    candidate. Approve/Reject must refuse — never act on X, a row the
    user did not select."""
    other = {"example_id": "ex-" + "7" * 32, "job_id": "job-" + "7" * 32,
             "kind": "candidate", "candidate_id": "cand-other",
             "candidate_status": "pending", "classification": {},
             "suggestion": None}
    learning = _RecordingLearning()
    with World(review_service=_QueueReview([other]),
               learning_service=learning) as w:
        a = seed_example(w.store, CANARY_A)
        w.hub.state.review_service = w.hub.spec["review_service"]
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.state.select_training_tab("review")
        w.drain()
        w.hub.reviewApprove_(None)
        w.hub.reviewReject_(None)
        w.drain()
        assert not learning.approved and not learning.rejected, \
            f"acted on an unselected row: {learning.approved}" \
            f" {learning.rejected}"


@case("M09-AUDIT-20")
def test_r04_export_is_the_rendered_window_not_newer_state():
    """Review: window S1 is on screen; a reload has published S2 to state
    but its refresh has not run yet when the user clicks Export — the
    file must be S1, the window the user sees."""
    with World() as w:
        ed = _events_dir(w)
        log = "events-20260926-m09.jsonl"
        write_events(ed, log, [event(i, f"2026-09-26T10:00:0{i}.000Z",
                                     name=f"m09.shown.{i}")
                               for i in (1, 2, 3)])
        open_view(w.hub, w.mq, "diagnostics")
        with open(pathlib.Path(ed) / log, "a", encoding="utf-8") as f:
            f.write(json.dumps(event(9, "2026-09-26T10:00:09.000Z",
                                     name="m09.not.yet.shown")) + "\n")
        w.hub.state.reload_current()
        assert w.hub.state.wait_for_queries(5)    # S2 in state, not drawn
        assert "m09.not.yet.shown" not in rendered_text(w.hub.diag_text)
        out = w.h.tmp / "export.jsonl"
        undo = patch_appkit("NSSavePanel", _fake_save_panel(out))
        try:
            w.hub.diagnosticsExport_(None)
        finally:
            undo()
        w.drain()
        names = [json.loads(ln).get("event")
                 for ln in out.read_text().splitlines() if ln.strip()]
        assert "m09.shown.1" in names and "m09.not.yet.shown" not in names, \
            names


@case("M09-AUDIT-06")
def test_r05_span_fields_clear_when_the_stage_under_them_changes():
    """Review: offsets typed against R1 'alpha beta'; the source stage
    becomes R2 'gamma beta' and the same example re-renders. The typed
    span must not be saved as a correction of R2's 'gamma'."""
    with World() as w:
        a = seed_example(w.store, "alpha beta")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("delta")   # typed vs 'alpha'
        advance_stage(w.store, a["example_id"], "source_text", "gamma beta")
        w.hub.state.reload_current(detail_only=True)   # same example
        w.drain()
        assert "gamma beta" in rendered_text(w.hub.training_detail)
        w.hub.trainingSpan_(None)
        w.drain()
        assert annotation_kinds(w.store, a["example_id"]) == [], \
            "R1-typed offsets were saved against R2"


@case("M09-AUDIT-06", kind="control")
def test_r05_span_fields_survive_an_unrelated_revision():
    """Control: a revision that leaves the displayed stages unchanged
    keeps what the user typed, and the span saves."""
    with World() as w:
        a = seed_example(w.store, "alpha beta")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("delta")
        env = json.loads(json.dumps(w.store.latest_revision(
            a["example_id"])))
        parent = env.pop("revision_id", None)
        env["outcome"] = dict(env.get("outcome") or {}, note="m09")
        w.store.append_revision(a["example_id"], env,
                                parent_revision_id=parent)
        w.store.sync()
        w.hub.state.reload_current(detail_only=True)
        w.drain()
        assert str(w.hub.span_corrected.stringValue()) == "delta"
        w.hub.trainingSpan_(None)
        w.drain()
        assert annotation_kinds(w.store, a["example_id"]) == \
            ["span_correction"]


@case("M09-AUDIT-12")
def test_r06_merged_limit_follows_instants_not_strings():
    """Review: the per-source SQL cut must follow the same instants as
    the merge — an explicit-offset timestamp is placed by its instant,
    and a malformed or zone-less value never takes a dated row's
    place under the limit."""
    import datetime as dt
    from localflow.v2.history_queries import HistoryQueryService
    with World(build=False) as w:
        newest, _ = w.store.create_job(
            captured_at_utc="2026-09-25T23:30:00-04:00",  # 03:30Z on 26th
            time_quality="known")
        w.store.create_job(captured_at_utc="2026-09-26T01:00:00.000Z",
                           time_quality="known")
        w.store.sync()
        svc = HistoryQueryService(w.store, tz=dt.timezone.utc)
        one = [r["id"] for g in svc.search(limit=1)["groups"]
               for r in g["rows"]]
        assert one == [newest], "offset instant cut by string order"
    with World(build=False) as w:
        dated, _ = w.store.create_job(
            captured_at_utc="2026-09-26T10:00:00.000Z", time_quality="known")
        for bad in ("not-a-date", "2026-09-26T12:00:00"):
            w.store.create_job(captured_at_utc=bad, time_quality="known")
        w.store.sync()
        svc = HistoryQueryService(w.store, tz=dt.timezone.utc)
        one = [r["id"] for g in svc.search(limit=1)["groups"]
               for r in g["rows"]]
        assert one == [dated], "an undated value displaced the dated row"


@case("M09-AUDIT-02")
def test_r07_retention_pass_keeps_a_hidden_selection_usable():
    """Review: a row is selected in History; the user is on another view
    when a retention pass revalidates; back in History the still
    highlighted row shows its detail again and its actions work."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", ja)
        open_view(w.hub, w.mq, "home")
        w.hub.state.revalidate()
        w.drain()
        open_view(w.hub, w.mq, "history")
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        w.hub.historyCopy_(None)
        assert CANARY_A in rendered_text(w.hub.history_detail), \
            rendered_text(w.hub.history_detail)[:80]
        assert copies, "the highlighted row's actions refuse"


@case("M09-AUDIT-17")
def test_r08_teach_refuses_when_the_final_text_is_a_transform():
    """Review: the displayed final text is an applied transform, while
    Teach measures a correction against the cleaned output. Teach must
    refuse visibly rather than record the transform's rewrite as the
    user's correction."""
    with World() as w:
        jid, fam = w.store.create_job(captured_at_utc=iso(T0),
                                      time_quality="known",
                                      state="insertion_confirmed")
        _publish_attempt(
            w.store, jid, fam, 1, "please send the report today",
            "please send the report today",
            transform={"output": "Please send the quarterly report today.",
                       "path": "applied", "reason": "validated",
                       "applied": True})
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", jid)
        calls = []
        svc = w.hub.spec["learning_service"]
        real = svc.teach_correction
        svc.teach_correction = lambda *a, **k: calls.append(a) or real(
            *a, **k)
        try:
            w.hub.teach_field.setStringValue_(
                "Please send the quarterly report tomorrow.")
            w.hub.historyTeach_(None)
        finally:
            svc.teach_correction = real
        assert not calls, "teach measured against text the user never saw"
        assert "Teach" in rendered_text(w.hub.history_detail)


@case("M09-AUDIT-17")
def test_r09_final_text_is_never_the_source_transcript():
    """Review: the cleaned output expired while an independent History
    lease keeps the raw transcript. Copy and Paste Again must refuse —
    the raw transcript is not the text that was inserted."""
    with World() as w:
        c = seed_example(w.store, "raw words " + CANARY_C,
                         applied="Cleaned Words " + CANARY_C)
        w.store.grant_lease(c["raw"], "history", days=400)
        days = w.store.retention_days["training_buffer"]
        w.store.prune_training(now=time.time() + (days + 2) * 86400)
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", c["job_id"])
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        pastes, _ = record_coordinator(w.d, "hubPasteText",
                                       {"outcome": "repaste_queued"})
        w.hub.historyCopy_(None)
        w.hub.historyPasteAgain_(None)
        assert not copies and not pastes, (copies, pastes)
        assert "raw words" in rendered_text(w.hub.history_detail)


@case("M09-AUDIT-02")
def test_r10_hidden_training_detail_is_cleared_on_delete():
    """Review: A's detail was rendered in Training, then the Models view
    switched to Engines; deleting A clears the hidden detail too."""
    with World() as w:
        a = seed_example(w.store, "hidden " + CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.state.select_models_subview("engines")
        w.drain()
        w.store.delete_everywhere("job", a["job_id"])
        w.drain()
        assert CANARY_A not in everything_rendered(w.hub), \
            "a hidden widget kept the deleted transcript"


@case("M09-AUDIT-02")
def test_r10_voice_pane_drops_a_profile_invalidated_by_delete():
    """A generated Your Voice profile lists a phrase drawn from example
    A; deleting A drops the cached profile, and the pane stops showing
    it instead of keeping the old rendering."""
    phrase = "weekly budget summary"
    with World() as w:
        exs = [seed_example(w.store, f"send the {phrase} now {i}")
               for i in range(3)]
        open_view(w.hub, w.mq, "insights")
        w.hub.state.select_insights_subview("voice")
        w.drain()
        w.hub.voiceGenerate_(None)
        w.drain()
        w.hub.state.reload_insights()
        w.drain()
        before = str(w.hub.voice_pane.text.string())
        assert phrase in before, f"precondition: no phrase shown: {before}"
        w.store.delete_everywhere("job", exs[0]["job_id"])
        w.drain()
        assert phrase not in str(w.hub.voice_pane.text.string()), \
            "the invalidated profile is still rendered"


@case("M09-AUDIT-07")
def test_r11_retention_purge_stops_active_replay():
    """Review (AUDIT-07 retention half): A's audio plays; a retention
    pass purges it and revalidates the Hub. Playback stops and the
    buffer is released."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        assert _playing(w.sounds), "precondition: A playing"
        days = w.store.retention_days["training_buffer"]
        w.store.prune_training(now=time.time() + (days + 2) * 86400)
        assert w.store.artifact(a["audio"])["purged"]
        w.hub.state.revalidate()
        w.drain()
        assert not _playing(w.sounds), "purged audio still playing"
        assert w.hub.replay._sound is None


@case("M09-AUDIT-03")
def test_r02_older_admission_never_displaces_a_newer_pending_one():
    """Review R-02 (second route): two searches hold the key's running
    slots, so the user's newest search B waits pending. A reload
    admitted on another thread (as a retention pass does) took its
    generation before B but reaches the executor after it; B must still
    run and render, never be displaced by the older request."""
    with World() as w:
        seed_job(w.store, "held one", captured=iso(T0))
        jb, _, _ = seed_job(w.store, "two " + CANARY_B, captured=iso(T0 + 9))
        lat = latch_history(w)
        open_view(w.hub, w.mq, "history")
        state = w.hub.state
        held = [lat.hold("search", when=lambda t=t, **kw: kw.get("text") == t,
                         after=False) for t in ("m09held1", "m09held2")]
        for t, g in zip(("m09held1", "m09held2"), held):
            state.set_history_search(t)
            assert g.arrived.wait(5)
        real_submit = state._executor.submit
        gap = {"arrived": threading.Event(), "release": threading.Event()}

        def submit(req, before_run):
            if threading.current_thread().name == "m09-second-admitter" \
                    and not state._lock._is_owned():
                gap["arrived"].set()
                gap["release"].wait(10)
            return real_submit(req, before_run)
        state._executor.submit = submit
        t = threading.Thread(target=state.reload_history,
                             name="m09-second-admitter", daemon=True)
        t.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and t.is_alive() and \
                not gap["arrived"].is_set():
            time.sleep(0.005)
        state.set_history_search(CANARY_B)       # newest; pending
        gap["release"].set()
        t.join(5)
        for g in held:
            g.release.set()
        w.drain()
        view = state.views["history"]
        ids = [r["id"] for r in history_rows(w.hub)]
        assert ids == [jb] and view.get("loading") is False, \
            f"newest search displaced: rows {ids}, loading" \
            f" {view.get('loading')}"


@case("M09-LOCAL-01")
def test_r13_delete_is_refused_when_confirmation_cannot_show():
    """Review R-13: if the confirmation alert cannot be created, Delete
    Everywhere must not proceed unconfirmed."""
    class _NoAlert:
        @staticmethod
        def alloc():
            raise RuntimeError("synthetic: no alert available")
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        select_training(w, a["example_id"])
        undo = patch_appkit("NSAlert", _NoAlert)
        try:
            w.hub.trainingDelete_(None)
        finally:
            undo()
        w.drain()
        state = w.store.submit(lambda c: c.execute(
            "SELECT state FROM training_examples WHERE example_id=?",
            (a["example_id"],)).fetchone()[0])
        assert state != "deleted", "deleted without a confirmation"
        assert "nothing was deleted" in rendered_text(w.hub.training_detail)


@case("M09-AUDIT-24")
def test_r13_span_preread_timeout_is_a_refusal_not_unknown():
    """Review R-13: a timeout in the span save's range pre-read happens
    before anything is submitted — the save is not saved, and must not
    be reported as a write that may still complete."""
    with World() as w:
        a = seed_example(w.store, "alpha beta")
        open_training(w)
        select_training(w, a["example_id"])
        w.hub.span_start.setStringValue_("0")
        w.hub.span_end.setStringValue_("5")
        w.hub.span_stage.selectItemWithTitle_("source_text")
        w.hub.span_corrected.setStringValue_("delta")
        real = w.store.submit

        def submit(op, *args, **kw):
            if getattr(op, "__name__", "") == "span_op":
                raise TimeoutError("synthetic: store busy")
            return real(op, *args, **kw)
        w.store.submit = submit
        try:
            w.hub.trainingSpan_(None)
        finally:
            w.store.submit = real
        w.drain()
        pane = rendered_text(w.hub.training_detail)
        assert "not saved" in pane and "may still complete" not in pane, \
            pane[-200:]
        assert annotation_kinds(w.store, a["example_id"]) == []


@case("M09-AUDIT-19")
def test_r13_timeline_header_names_the_loaded_filter():
    """Review R-13: the job-timeline header names the filter the shown
    records were loaded with, not a filter typed since."""
    with World() as w:
        job = "job-" + "d" * 32
        write_events(_events_dir(w), "events-20260926-m09.jsonl",
                     [event(1, "2026-09-26T10:00:01.000Z", job=job)])
        open_view(w.hub, w.mq, "diagnostics")
        w.hub.state.set_diagnostics_filters(job=job)
        w.drain()
        w.hub.state.views["diagnostics"]["job_filter"] = "job-" + "e" * 32
        w.hub._refresh_diagnostics_view()
        text = rendered_text(w.hub.diag_text)
        assert f"job timeline ({job})" in text, text[:200]


@case("M09-AUDIT-08")
def test_r13_redaction_shapes_are_whole_value_matches():
    """Review R-13: a typed field matches its whole value — a trailing
    newline does not pass, and model_id never carries a dot-only path
    segment."""
    from localflow.v2.event_view import redact
    base = {"schema_version": 1, "event": "stage.done", "level": "INFO"}
    for field, value in (("reason_code", "valid_code\n"),
                         ("model_id", "mlx-community/x\n"),
                         ("model_id", "../.."),
                         ("model_id", "./models"),
                         ("event_id", "evt-" + "a" * 32 + "\n")):
        out = redact(dict(base, **{field: value}))
        assert field not in out, (field, value, out)
    out = redact(dict(base, model_id="mlx-community/Qwen3-4B",
                      reason_code="valid_code"))
    assert out["model_id"] == "mlx-community/Qwen3-4B" and \
        out["reason_code"] == "valid_code"


class _RecordingReview(_QueueReview):
    def __init__(self):
        super().__init__([])
        self.labels = []

    def record_label(self, example_id, edit_kind=None, abstained=False,
                     operation_id=None):
        # abstained and operation_id mirror ReviewService.record_label
        # (M14-AUDIT-17; the Hub records "unknown" as an abstention).
        self.labels.append(example_id)
        return {}


@case("M09-AUDIT-01")
def test_r14_label_during_selection_interval_attaches_to_nothing():
    """Review (AUDIT-01 residue): with the example field empty, Record
    Label uses the rendered example — while B is selected and A still
    rendered it refuses rather than labeling either."""
    review = _RecordingReview()
    with World(review_service=review) as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        open_training(w)
        lat = latch_training(w)
        select_training(w, a["example_id"])
        gate = lat.hold("example_detail",
                        when=lambda ex: ex == b["example_id"], after=False)
        w.hub.state.select_training_example(b["example_id"])
        assert gate.arrived.wait(5)
        w.mq.flush()
        w.hub.reviewLabel_(None)
        interval = list(review.labels)
        gate.release.set()
        w.drain()
        assert not interval, f"labeled during the interval: {interval}"
        w.hub.reviewLabel_(None)                   # B rendered now
        assert review.labels == [b["example_id"]], review.labels


@case("M09-AUDIT-22")
def test_r15_store_timeout_on_an_action_is_unknown_not_failed():
    """Review (AUDIT-22 residue): a store timeout on Pin/Exclude/Mark may
    still commit — the pane says the outcome is unknown, not failed."""
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        open_training(w)
        lat = latch_training(w)
        select_training(w, a["example_id"])
        for name, action in (("pin", w.hub.trainingPin_),
                             ("exclude", w.hub.trainingExclude_),
                             ("mark_intended", w.hub.trainingMarkCorrect_)):
            lat.fail(name, TimeoutError("synthetic: store busy"))
            action(None)
            pane = rendered_text(w.hub.training_detail)
            assert "unknown" in pane and "action failed" not in pane, \
                (name, pane[-160:])


@case("M09-AUDIT-17")
def test_r16_applied_transform_without_its_output_has_no_final_text():
    """Review R-06 (related): the recorded decision says a transform was
    applied but its output artifact no longer resolves. The final text
    was that output — Copy and Paste Again refuse rather than use the
    cleaned text, which was not what was inserted."""
    with World() as w:
        jid, fam = w.store.create_job(captured_at_utc=iso(T0),
                                      time_quality="known",
                                      state="insertion_confirmed")
        out = _publish_attempt(w.store, jid, fam, 1, "raw words m09",
                               "Cleaned words " + CANARY_B)
        env = json.loads(json.dumps(w.store.latest_revision(out["example"])))
        parent = env.pop("revision_id", None)
        env["transform"] = {"transform_id": "tf-m09", "path": "applied",
                            "reason": "validated", "applied": True,
                            "artifact_ids": {"output": "art-" + "e" * 32}}
        w.store.append_revision(out["example"], env,
                                parent_revision_id=parent)
        w.store.sync()
        open_view(w.hub, w.mq, "history")
        select_history(w, "job", jid)
        copies, _ = record_coordinator(w.d, "hubCopyText", None)
        pastes, _ = record_coordinator(w.d, "hubPasteText",
                                       {"outcome": "repaste_queued"})
        w.hub.historyCopy_(None)
        w.hub.historyPasteAgain_(None)
        assert not copies and not pastes, \
            f"cleaned text used as the final text: {copies} {pastes}"


@case("M09-AUDIT-02")
def test_r10_hidden_review_queue_is_cleared_on_delete():
    """Review R-10 (same shape): the Review queue rendered a candidate of
    job A with its suggested words; the user moved to Evidence; deleting
    A clears the hidden queue text too."""
    with World() as w:
        a = seed_example(w.store, "review " + CANARY_A)
        row = {"example_id": a["example_id"], "job_id": a["job_id"],
               "kind": "candidate", "candidate_id": "cand-m09-r10",
               "candidate_status": "pending", "classification": {},
               "suggestion": {"alias": "m09aliasword",
                              "canonical": CANARY_A}}
        w.hub.spec["review_service"] = _QueueReview([row])
        w.hub.state.review_service = w.hub.spec["review_service"]
        open_training(w)
        w.hub.state.select_training_tab("review")
        w.drain()
        assert CANARY_A in str(w.hub.review_text.string()), \
            "precondition: the queue shows the suggestion"
        w.hub.state.select_training_tab("evidence")
        w.drain()
        w.store.delete_everywhere("job", a["job_id"])
        w.drain()
        assert CANARY_A not in str(w.hub.review_text.string()), \
            "the hidden review queue kept the deleted job's words"


# ---- runner ----------------------------------------------------------------

def main(argv):
    out_json = None
    only = None
    if "--json" in argv:
        out_json = argv[argv.index("--json") + 1]
    if "-k" in argv:
        only = argv[argv.index("-k") + 1]
    results = []
    for fn in CASES:
        if only and only not in fn.__name__:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "pass", None
            print(f"ok  {fn.finding} {fn.__name__}")
        except AssertionError as e:
            status, detail = "fail", str(e)[:500]
            print(f"FAIL {fn.finding} {fn.__name__}: {detail}")
        except Exception as e:
            status = "error"
            detail = f"{type(e).__name__}: {e}"[:500]
            print(f"ERROR {fn.finding} {fn.__name__}: {detail}")
            traceback.print_exc()
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 3)})
    passed = sum(r["status"] == "pass" for r in results)
    print(f"{passed}/{len(results)} m09 remediation cases passed")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            **code_stamp("tests/v2/ui/test_m09_remediation.py"),
            "results": results, "passed": passed, "total": len(results),
        }, indent=2) + "\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
