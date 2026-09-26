"""Case and metamorphic-relation drivers for the M09 corpus runner
(``m09_corpus_runner.py``). Each driver runs one supplied case's
schedule over synthetic fixtures (``m09_world``) through the real Hub
actions, HubState, services, coordinator and store, and asserts the
case's oracle against values taken from the fixture definition — never
from the output under test. Registries and decorators live here so the
runner (run as ``__main__``) and the drivers share one module object.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

import test_m09_remediation as R  # noqa: E402  (also initializes NSApp)
from m09_world import (APP_A, APP_B, CANARY_A, CANARY_B,  # noqa: E402
                       CANARY_C, Latch, MainQueue, World, advance_stage,
                       event, history_rows, iso, is_main, join_work,
                       open_view, rendered_text, seed_example, seed_job,
                       seed_legacy_db, seed_legacy_pair, thread_oracle,
                       write_events)

T0 = R.T0

CASE_DRIVERS = {}
MR_DRIVERS = {}


class Narrowed(Exception):
    """The automatable part passed; ``remainder`` needs another
    environment or a person."""

    def __init__(self, detail, remainder):
        super().__init__(detail)
        self.remainder = remainder


def case(*ids, env="portable_real_framework"):
    def deco(fn):
        for i in ids:
            assert i not in CASE_DRIVERS, i
            CASE_DRIVERS[i] = (fn, env)
        return fn
    return deco


def relation(mr_id):
    def deco(fn):
        MR_DRIVERS[mr_id] = fn
        return fn
    return deco


def regression(name):
    """A driver that is exactly one regression case."""
    fn = getattr(R, name)

    def run():
        fn()
        return {"regression": name}
    run.__name__ = name
    return run


# ---- cases covered one-to-one by a regression --------------------------

_REG = {
    "M09-C002": ["test_a01_history_actions_during_selection_interval",
                 "test_a01_training_mark_during_selection_interval"],
    "M09-C006": ["test_a11_noop_repaste_still_delivers_deferred_open"],
    "M09-C007": ["test_a07_listen_gate_is_per_example_through_current_hub"],
    "M09-C008": ["test_a07_failed_playback_grants_no_listening"],
    "M09-C011": ["test_a02_late_detail_publication_after_delete"],
    "M09-C012": ["test_a07_delete_stops_active_replay_and_refuses_again"],
    "M09-C013": ["test_a24_annotation_failpoints_roll_back_completely"],
    "M09-C014": ["test_a06_span_after_same_length_stage_replacement"],
    "M09-C016": ["test_a20_export_is_the_displayed_snapshot_and_parses_off_main"],
    "M09-C017": ["test_a21_mine_completion_never_forces_review_tab"],
    "M09-C019": ["test_a10_hundred_searches_bounded_and_fully_drained"],
    "M09-C020": ["test_a25_refresh_and_completions_run_on_main"],
    "M09-C021": ["test_a03_old_error_after_new_success"],
    "M09-C022": ["test_a03_old_success_after_new_error"],
    "M09-C023": ["test_a03_publication_check_and_mutation_atomic"],
    "M09-C024": ["test_a01_training_editor_buffers_bound_to_rendered_example"],
    "M09-C025": ["test_a01_training_table_click_uses_rendered_row"],
    "M09-C026": ["test_local01_training_delete_confirm_deletes_confirmed_identity",
                 "test_local01_training_delete_cancel_deletes_nothing"],
    "M09-C034": ["test_a11_noop_repaste_still_delivers_deferred_open"],
    "M09-C035": ["test_a11_flush_before_busy_decrement_is_not_lost"],
    "M09-C039": ["test_a12_same_day_merge_is_by_instant_with_one_limit"],
    "M09-C041": ["test_a13_default_zone_honors_historical_dst"],
    "M09-C043": ["test_a13_explicit_offset_timestamp_policy"],
    "M09-C047": ["test_a16_history_app_and_mode_controls_reachable"],
    "M09-C051": ["test_a14_legacy_db_row_detail_and_jobless_actions"],
    "M09-C052": ["test_a15_legacy_pair_identity_stable_across_matching_half"],
    "M09-C056": ["test_a09_history_shows_current_attempt_not_first_row"],
    "M09-C057": ["test_a17_transform_decision_is_displayed_and_final_text_authorized"],
    "M09-C061": ["test_a07_unavailable_replacement_stops_previous"],
    "M09-C062": ["test_a07_prepared_buffer_cannot_start_after_delete"],
    "M09-C075": ["test_a24_timeout_is_unknown_not_failure_and_retry_is_idempotent"],
    "M09-C077": ["test_a06_emoji_code_point_offsets"],
    "M09-C079": ["test_a06_unrelated_revision_keeps_same_reviewed_artifact"],
    "M09-C082": ["test_a02_independent_history_lease_survives_training_expiry"],
    "M09-C083": ["test_a04_quarantine_survives_exclude_then_restore_via_hub"],
    "M09-C084": ["test_a04_expired_survives_exclude_then_restore"],
    "M09-C086": ["test_a05_span_save_never_reincludes_excluded"],
    "M09-C087": ["test_a05_verbatim_save_never_reincludes_excluded"],
    "M09-C088": ["test_a05_intended_mark_refuses_non_reviewable"],
    "M09-C089": ["test_a02_training_delete_clears_detail_and_editor"],
    "M09-C092": ["test_a29_deleted_job_leaves_history_immediately"],
    "M09-C094": ["test_a18_ordering_is_stream_aware_and_filename_independent"],
    "M09-C096": ["test_a19_non_object_json_lines_are_skipped_safely"],
    "M09-C097": ["test_a19_level_all_resets_filter_via_popup"],
    "M09-C098": ["test_a19_utc_toggle_applies_to_job_timeline"],
    "M09-C100": ["test_a08_hub_export_uses_typed_allowlist"],
    "M09-C105": ["test_a21_mine_completion_never_forces_review_tab"],
    "M09-C106": ["test_a21_older_export_cannot_overwrite_newer_status"],
    "M09-C111": ["test_a22_models_failure_is_visible_not_stale_success"],
    "M09-C112": ["test_a22_loading_is_a_real_transition"],
    "M09-C118": ["test_a25_inline_dispatch_negative_control_is_intercepted"],
}

_NATIVE_REG = {"M09-C002", "M09-C006", "M09-C007", "M09-C012", "M09-C016",
               "M09-C017", "M09-C020", "M09-C024", "M09-C025", "M09-C026",
               "M09-C034", "M09-C035", "M09-C047", "M09-C051", "M09-C089",
               "M09-C097", "M09-C098", "M09-C105", "M09-C106", "M09-C111",
               "M09-C118"}

for _cid, _names in _REG.items():
    def _make(names):
        def run():
            for n in names:
                getattr(R, n)()
            return {"regressions": names}
        return run
    CASE_DRIVERS[_cid] = (_make(_names),
                          "native_appkit_main_queue" if _cid in _NATIVE_REG
                          else "portable_real_framework")

# ---- human-only and environment-bound remainders ---------------------------

DEPENDENCIES = {
    "M09-C129": ("MANUAL_PENDING", "M09-V001 — full layout, scale,"
                 " appearance (Daniel)"),
    "M09-C130": ("MANUAL_PENDING", "M09-V002 — real keyboard/focus"
                 " (Daniel)"),
    "M09-C131": ("MANUAL_PENDING", "M09-V003 — audible replay and retry"
                 " experience (Daniel)"),
    "M09-C132": ("MANUAL_PENDING", "M09-V004 — History Paste Again into a"
                 " real destination, observed focus (Daniel)"),
    "M09-C133": ("MANUAL_PENDING", "M09-V005 — move/resize/relaunch and"
                 " display change (Daniel)"),
    "M09-C134": ("MANUAL_PENDING", "M09-V006 — Training review"
                 " experience (Daniel)"),
    "M09-C135": ("MANUAL_PENDING", "M09-V007 — Diagnostics filters and"
                 " redacted export usability (Daniel)"),
}




# ---- query generation / lifecycle -------------------------------------------

def _ids(hub):
    return [r["id"] for r in history_rows(hub)]


_SURFACES = ("history_detail", "training_detail", "verbatim_field",
             "span_corrected", "teach_field", "review_text", "diag_text",
             "models_text")


def _where(hub, token, skip=()):
    """Every state key and rendered surface still carrying ``token``
    (``skip`` names state keys that legitimately hold it, e.g. the
    user's own typed query)."""
    hits = []
    for view, st in hub.state.views.items():
        for k, v in st.items():
            if f"{view}.{k}" not in skip and \
                    token in json.dumps(v, default=str):
                hits.append(f"state.{view}.{k}")
    for name in _SURFACES:
        v = getattr(hub, name, None)
        if v is None:
            continue
        try:
            s = str(v.string())
        except Exception:
            s = str(v.stringValue())
        if token in s:
            hits.append(name)
    if token in json.dumps(getattr(hub, "_history_flat", []) or []):
        hits.append("history_table")
    return hits


def _wait(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.005)
    return True


@case("M09-C001")
def c001_history_late_completion():
    """A held after its result exists; B admitted and published; A
    released — B stays, and nothing after B changes data/error/loading/
    selection/detail."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **k: k.get("text") ==
                        CANARY_A, after=True)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.hub.state.set_history_search(CANARY_B)
        assert _wait(lambda: _ids(w.hub) == [jb])
        snap = json.dumps({k: w.hub.state.views["history"].get(k) for k in
                           ("data", "error", "loading", "selected_id",
                            "detail")}, default=str)
        gate.release.set()
        w.drain()
        after = json.dumps({k: w.hub.state.views["history"].get(k) for k in
                            ("data", "error", "loading", "selected_id",
                             "detail")}, default=str)
        assert after == snap, "a late A completion changed B's state"
        # positive control: the same search without the adverse order
        w.hub.state.set_history_search(CANARY_A)
        w.drain()
        assert _ids(w.hub) == [ja]
    return {"final": "B"}


@case("M09-C003")
def c003_history_result_after_switch_to_training():
    """History A held; the user switches to Models/Training which loads;
    A is released — Training is untouched, the view stays Training, and
    the History result (per-key policy) is History's own newest result."""
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        seed_example(w.store, CANARY_C)
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **k: k.get("text") ==
                        CANARY_A, after=True)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        open_view(w.hub, w.mq, "models")
        w.hub.state.select_models_subview("training")
        w.hub.state.wait_for_queries(5)
        w.mq.flush()
        models_before = json.dumps(w.hub.state.views["models"].get("data"),
                                   default=str)
        gate.release.set()
        w.drain()
        assert w.hub.state.selected_view == "models"
        assert json.dumps(w.hub.state.views["models"].get("data"),
                          default=str) == models_before
        # History kept its newest (and only) request's result, labeled by
        # its own key; revisiting shows it without a permanent loading.
        open_view(w.hub, w.mq, "history")
        view = w.hub.state.views["history"]
        assert view.get("loading") is False and _ids(w.hub) == [ja]
    return {"policy": "per-key generations"}


@case("M09-C004", env="native_appkit_main_queue")
def c004_close_reopen_during_query():
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        w.hub.showWindow_(None)
        gate = lat.hold("search", when=lambda **k: k.get("text") ==
                        CANARY_A, after=True)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.hub.windowShouldClose_(None)
        assert w.hub.state.visible is False
        assert not w.hub.window.isVisible(), "hidden window still visible"
        gate.release.set()
        w.drain()
        assert not w.hub.window.isVisible(), \
            "a completion while hidden re-showed the window"
        controller, window = w.hub, w.hub.window
        w.hub.showWindow_(None)
        w.drain()
        assert w.hub is controller and w.hub.window is window
        assert w.hub.state.visible is True
        assert w.d.state == "idle" or w.d.state is not None
    return {"controllers": 1}


@case("M09-C027")
def c027_search_removes_current_selection():
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        pastes, _ = R.record_coordinator(w.d, "hubPasteText", {})
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", ja)
        w.hub.state.set_history_search(CANARY_B)
        w.drain()
        view = w.hub.state.views["history"]
        assert view["selected_id"] is None and view["detail"] is None, \
            "hidden row still selected"
        w.hub.historyPasteAgain_(None)
        assert not pastes, f"action on a row no longer listed: {pastes}"
    return {}


@case("M09-C028")
def c028_revisit_after_cross_view_switch():
    with World() as w:
        ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("search", when=lambda **k: k.get("text") ==
                        CANARY_A, after=False)
        w.hub.state.set_history_search(CANARY_A)
        assert gate.arrived.wait(5)
        w.hub.state.select_view("models")
        gate.release.set()
        w.drain()
        w.hub.state.select_view("history")
        w.drain()
        view = w.hub.state.views["history"]
        assert view["loading"] is False, "permanent loading after revisit"
        assert _ids(w.hub) == [ja]
    return {}


@case("M09-C029")
def c029_request_inputs_captured_at_admission():
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        # Occupy the worker so A is queued, not started.
        hold = lat.hold("home_summary", after=False)
        w.hub.state._spawn(("home", "list"), w.hub.state._load_home)
        assert hold.arrived.wait(5)
        n0 = len(lat.calls)
        w.hub.state.set_history_search(CANARY_A)  # admitted, not started
        w.hub.state.set_history_search(CANARY_B)
        hold.release.set()
        w.drain()
        calls = [c for c in lat.calls[n0:] if c[0] == "search"]
        texts = [c[2].get("text") for c in calls]
        assert CANARY_A not in texts or texts.index(CANARY_A) == 0, texts
        assert texts[-1] == CANARY_B and _ids(w.hub) == [jb], texts
    return {"search_calls": len(calls)}


@case("M09-C030")
def c030_on_update_outside_publication_lock():
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        open_view(w.hub, w.mq, "history")
        st = w.hub.state
        seen = []
        real = st.on_update

        def probe(state):
            # Another thread must be able to take the state lock while
            # this notification runs: publication is outside the lock.
            got = []
            t = threading.Thread(target=lambda: got.append(
                st._lock.acquire(timeout=1.0) and (st._lock.release()
                                                   or True)))
            t.start()
            t.join(2)
            seen.append(bool(got and got[0]))
            _ = st.views["history"].get("data")  # reentrant read
            return real(state)
        st.on_update = probe
        st.set_history_search(CANARY_A)
        w.drain()
        st.on_update = real
        assert seen and all(seen), f"notification ran under the lock: {seen}"
    return {"notifications": len(seen)}


@case("M09-C037", env="native_appkit_main_queue")
def c037_one_controller_across_repeated_opens():
    with World(build=False) as w:
        w.d.openHub_(None)
        first = w.d._hub
        for _ in range(3):
            w.d.openHub_(None)
            w.d.quickOpenScratchpad_(None)
        w.drain()
        first.windowShouldClose_(None)
        w.d.openHub_(None)
        w.drain()
        assert w.d._hub is first and first is not None
        from localflow.v2.ui import HubController
        import gc
        live = [o for o in gc.get_objects()
                if isinstance(o, HubController) and o is not first
                and getattr(o, "spec", {}).get("store") is w.store]
        assert not live, f"{len(live)} extra controllers"
    return {"controllers": 1}


@case("M09-C038", env="native_appkit_main_queue")
def c038_shutdown_accounts_for_every_query_tail():
    with World() as w:
        seed_job(w.store, CANARY_A, captured=iso(T0))
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        hold = lat.hold("search", when=lambda **k: k.get("text") == "old0",
                        after=False)
        w.hub.state.set_history_search("old0")
        assert hold.arrived.wait(5)
        for i in range(1, 3):
            w.hub.state.set_history_search(f"old{i}")
        w.hub.state.set_history_search("latest")
        w.hub.windowShouldClose_(None)
        w.hub.state.shutdown()
        hold.release.set()
        assert w.hub.state.wait_for_queries(10)
        stats = w.hub.state.query_stats()
        w.mq.flush()
        accounted = stats["started"] + stats["superseded_before_start"]
        assert accounted == stats["admitted"], stats
        assert stats["threads_started"] <= stats["max_workers"] and \
            stats["peak_running_per_key"] <= stats["per_key"], stats
    return {"stats": stats}


@case("M09-C036", env="native_appkit_main_queue")
def c036_quit_cancels_deferred_show():
    with World(build=False) as w:
        w.h.press()  # recording blocks activation
        w.d.openHub_(None)
        w.d.quickOpenScratchpad_(None)
        assert w.d._hub_show_pending
        w.d._closing = True  # the first step of applicationWillTerminate_
        w.h.release(delivered=False)
        w.d._flush_pending_hub_show()
        w.drain()
        assert w.d._hub is None, "window activated after quit began"
        assert not w.d._hub_show_pending
        w.d._closing = False
    return {}


# ---- focus admission (real InsertionService over the fixture target) --------

import queue as _queue  # noqa: E402


class _GatedQueue(_queue.Queue):
    """The insertion worker's queue, whose get() waits for a gate BEFORE
    dequeuing: an admitted operation sits queued while busy is False."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()

    def get(self, *a, **k):
        self.gate.wait(30)
        return super().get(*a, **k)


def _gate_worker(svc):
    """Steer the running worker onto a gated queue: the swap happens
    inside a real undo's completion (on the worker thread), so its next
    get() is the gated one and every admission stays counted."""
    gated = _GatedQueue()
    swapped = threading.Event()

    def on_done(_outcome):
        svc._q = gated
        swapped.set()
    svc.undo_last(on_done=on_done)
    assert swapped.wait(5), "undo never reached the worker"
    deadline = time.monotonic() + 5
    while (svc.busy or getattr(svc, "_outstanding", 0)) \
            and time.monotonic() < deadline:
        time.sleep(0.005)
    return gated


@case("M09-C005", env="portable_real_framework+fixture_target")
def c005_open_hub_while_insertion_executes():
    with World(build=False) as w:
        tgt = R._HeldTarget(settable=False, ax_readable=True)
        svc = R._real_insertion(w, tgt)
        done = threading.Event()
        svc.submit("m09 dictated text", {"job_id": None, "attempt": 1},
                   lambda r: done.set())
        assert tgt.arrived.wait(5) and svc.busy
        w.d.openHub_(None)
        w.d.openHub_(None)
        assert w.d._hub is None, "Hub activated mid-insertion"
        tgt.hold.set()
        assert done.wait(10)
        R._wait_idle(svc)
        w.drain()
        assert w.d._hub is not None and w.d._hub.state.visible
        assert not w.d._hub_show_pending
        assert "m09 dictated text" in tgt.content, "insertion changed"
        w.d._insertion = None
    raise Narrowed("deferred show delivered once after the transaction;"
                   " insertion unchanged (fixture target)",
                   "real window activation/focus against a native app:"
                   " M09-V004/M09-V005")


@case("M09-C031", env="portable_real_framework+fixture_target")
def c031_queued_before_busy():
    with World(build=False) as w:
        tgt = R._HeldTarget(settable=False, ax_readable=True)
        tgt.hold.set()
        svc = R._real_insertion(w, tgt)
        gated = _gate_worker(svc)
        out = w.d.hubPasteText("queued m09 text")
        assert out["outcome"] == "repaste_queued"
        assert not svc.busy, "precondition: queued, not executing"
        w.d.openHub_(None)
        shown_while_queued = w.d._hub is not None
        gated.gate.set()
        deadline = time.monotonic() + 10
        while svc.pending and time.monotonic() < deadline:
            time.sleep(0.01)
        w.drain()
        assert not shown_while_queued, \
            "Hub activated while insertion work was queued (busy=False)"
        assert w.d._hub is not None and w.d._hub.state.visible, \
            "deferred show never delivered after the queued work"
        w.d._insertion = None
    return {"policy": "queued work defers Hub activation"}


def _pending_payload_world(w, age_offset):
    """A finished transaction whose paste the target never consumed:
    M08 keeps the clipboard payload pending (no busy, no pending work)."""
    from fixture_target import FixtureTargetApp
    from localflow.v2.insertion.service import InsertionService
    tgt = FixtureTargetApp(settable=False, ax_readable=True)
    tgt.paste_drops = True
    base = [time.monotonic()]
    clock = lambda: base[0]  # noqa: E731
    svc = InsertionService(host=tgt, pasteboard=tgt.pb, keyboard=tgt,
                           store=w.store, emit=lambda *a, **k: None,
                           settle_sec=0.05, clock=clock)
    w.d._insertion = svc
    done = threading.Event()
    res = {}
    svc.submit("m09 dropped paste", {"job_id": None, "attempt": 1},
               lambda r: (res.update(r=r), done.set()))
    assert done.wait(10)
    R._wait_idle(svc)
    base[0] += age_offset
    return svc, tgt, res["r"]


@case("M09-C032", env="portable_real_framework+fixture_target")
def c032_pending_clipboard_young():
    with World(build=False) as w:
        svc, tgt, r = _pending_payload_world(w, age_offset=2.0)
        assert svc._pending_paste is not None, \
            f"precondition: payload pending ({r.state}/{r.reason_code})"
        ops0 = len(tgt.pb.ops)
        w.d.openHub_(None)
        w.drain()
        assert w.d._hub is not None, \
            "a pending clipboard payload blocked the Hub"
        assert len(tgt.pb.ops) == ops0, "opening the Hub published"
        assert svc._pending_paste is not None, "M08 pending policy changed"
        w.d._insertion = None
    return {}


@case("M09-C033", env="portable_real_framework+fixture_target")
def c033_lapsed_pending_clipboard():
    from localflow.v2.insertion.service import PENDING_PAYLOAD_SEC
    with World(build=False) as w:
        svc, tgt, _r = _pending_payload_world(
            w, age_offset=PENDING_PAYLOAD_SEC + 1.0)
        w.d.openHub_(None)
        w.drain()
        assert w.d._hub is not None, "lapsed payload blocked the Hub"
        # A later legitimate publication reconciles the lapsed payload
        # (M08) — the Hub never claimed a timer cleared it.
        assert svc._pending_paste is not None
        assert svc._resolve_pending() is True
        assert svc._pending_paste is None
        w.d._insertion = None
    return {}


# ---- Retry through the real button ----------------------------------------------

def _failed_job(w):
    w.h.press()
    w.d.willSleep_(None)  # failed_recoverable + journal wav
    return w.d._last_failed["job_id"]


@case("M09-C009", env="native_appkit_main_queue")
def c009_retry_double_click_one_claim():
    with World(durations=[5.0]) as w:
        jid = _failed_job(w)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", jid)
        w.hub.historyRetry_(None)
        first = rendered_text(w.hub.history_detail)
        w.hub.historyRetry_(None)
        second = rendered_text(w.hub.history_detail)
        assert "Retry queued" in first, first[-200:]
        assert "already being retried" in second, second[-200:]
        assert len(w.d._active_jobs) == 1
        job = w.d._active_jobs[0]
        fn, args = w.h.run_coordinator()
        fn(*args)
        w.drain()
        assert len(w.h.pastes) == 1, w.h.pastes
        assert job.get("norm_source") == "retry_unscoped_default"
    return {"retries_admitted": 1}


@case("M09-C066", env="native_appkit_main_queue")
def c066_retry_refusal_matrix():
    import localflow.app as app_mod
    with World(durations=[5.0]) as w:
        live = _failed_job(w)
        nonretry, _, _ = seed_job(w.store, "nr " + CANARY_A,
                                  captured=iso(T0), state="saved_not_inserted")
        noaudio, _, _ = seed_job(w.store, "na " + CANARY_B,
                                 captured=iso(T0 + 1),
                                 state="failed_recoverable")
        open_view(w.hub, w.mq, "history")
        shown = {}
        for name, jid in (("nonretryable", nonretry),
                          ("absent_audio", noaudio), ("valid", live)):
            R.select_history(w, "job", jid)
            w.hub.historyRetry_(None)
            shown[name] = rendered_text(w.hub.history_detail).lower()
        w.hub.historyRetry_(None)  # the valid job is now active
        shown["active"] = rendered_text(w.hub.history_detail).lower()
        # A row deleted while its detail is on screen: the captured
        # action refuses, the coordinator is never reached.
        gone, _, _ = seed_job(w.store, "gone " + CANARY_C,
                              captured=iso(T0 + 2),
                              state="failed_recoverable")
        w.hub.state.reload_history()
        w.drain()
        R.select_history(w, "job", gone)
        calls, _ = R.record_coordinator(w.d, "hubRetryJob", {})
        w.store.delete_everywhere("job", gone)
        w.drain()
        w.hub.historyRetry_(None)
        shown["deleted"] = rendered_text(w.hub.history_detail).lower()
        assert "not retryable (saved_not_inserted)" in shown["nonretryable"]
        assert "no recovery audio" in shown["absent_audio"]
        assert "retry queued" in shown["valid"]
        assert "already being retried" in shown["active"]
        assert not calls and ("deleted" in shown["deleted"] or
                              "select a row" in shown["deleted"])
        assert app_mod.V2_JOURNAL is not None
    return {"variants": sorted(shown)}


@case("M09-C067", env="portable_real_framework+coordinator")
def c067_retry_is_unscoped():
    with World(durations=[5.0]) as w:
        jid = _failed_job(w)
        # A different current Hub context: a History app filter and a
        # selected profile-bearing row must not reach the retry.
        open_view(w.hub, w.mq, "history")
        w.hub.state.set_history_filters(app="SomeOtherApp")
        w.drain()
        out = w.d.hubRetryJob(jid)
        assert out["outcome"] == "requeued", out
        job = w.d._active_jobs[-1]
        assert job.get("target") is None, "retry carries a destination"
        assert job.get("norm_source") == "retry_unscoped_default"
        assert job.get("from_retry") is True
    return {}


@case("M09-C068", env="portable_real_framework+coordinator")
def c068_retry_races_deletion():
    import localflow.app as app_mod
    with World(durations=[5.0]) as w:
        jid = _failed_job(w)
        assert w.d.hubRetryJob(jid)["outcome"] == "requeued"
        w.store.delete_everywhere("job", jid)
        captured = []
        real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: captured.append(
            (fn, a))
        try:
            # The requeued retry is already queued; the shutdown sentinel
            # behind it makes the worker return once that job is settled,
            # so the join is the latch (everything it posted is captured).
            w.d._jobs.put(None)
            t = threading.Thread(target=w.d._worker, daemon=True)
            t.start()
            t.join(30)
            assert not t.is_alive(), "worker never settled the retry"
        finally:
            app_mod.AppHelper.callAfter = real
        for fn, a in captured:
            if fn == w.d._finishWithText_:
                fn(*a)
        assert not w.h.pastes, f"deleted job re-delivered: {w.h.pastes}"
        state = w.h.job_state(jid)
        assert state not in ("inserted", "insertion_confirmed"), state
    return {"final_state": state}


# ---- Paste Again identity and refusals ---------------------------------------------

def _op_ids(svc):
    seen = []
    real_put = svc._q.put

    def put(item, *a, **k):
        if item and item[0] == "repaste":
            seen.append(item[1])
        return real_put(item, *a, **k)
    svc._q.put = put
    return seen


@case("M09-C010", env="native_appkit_main_queue+fixture_target")
def c010_two_deliberate_paste_agains():
    from fixture_target import FixtureTargetApp
    with World() as w:
        jid, _, _ = seed_job(w.store, "paste twice " + CANARY_A,
                             captured=iso(T0), state="insertion_confirmed")
        tgt = FixtureTargetApp()
        svc = R._real_insertion(w, tgt)
        ops = _op_ids(svc)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", jid)
        w.hub.historyPasteAgain_(None)       # one click
        assert len(ops) == 1, f"one click queued {len(ops)} ops"
        R._wait_idle(svc)
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        w.hub.historyPasteAgain_(None)       # a second deliberate click
        R._wait_idle(svc)
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        assert len(ops) == 2 and ops[0] != ops[1], ops
        rows = w.store.submit(lambda c: c.execute(
            "SELECT job_id FROM insertions").fetchall())
        assert rows and all(r[0] == jid for r in rows), rows
        w.d._insertion = None
    return {"op_ids_distinct": True, "insertion_rows": len(rows)}


@case("M09-C069", env="native_appkit_main_queue+fixture_target")
def c069_v2_paste_again_attribution():
    from fixture_target import FixtureTargetApp
    with World() as w:
        jid, _, _ = seed_job(w.store, "attributed " + CANARY_A,
                             captured=iso(T0), state="insertion_confirmed")
        tgt = FixtureTargetApp()
        svc = R._real_insertion(w, tgt)
        ops = _op_ids(svc)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", jid)
        w.hub.historyPasteAgain_(None)
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        assert ("attributed " + CANARY_A) in tgt.content
        rows = w.store.submit(lambda c: c.execute(
            "SELECT job_id FROM insertions").fetchall())
        assert rows == [(jid,)], rows
        assert len(ops) == 1 and ops[0].startswith("op-"), ops
        w.d._insertion = None
    return {}


@case("M09-C070", env="native_appkit_main_queue+fixture_target")
def c070_legacy_paste_again_jobless():
    from fixture_target import FixtureTargetApp
    with World() as w:
        rid = seed_legacy_db(w.store, 9, raw="legacy raw words",
                             cleaned="legacy cleaned words", ts=T0,
                             app="Mail")
        tgt = FixtureTargetApp()
        events = []
        from localflow.v2.insertion.service import InsertionService
        svc = InsertionService(host=tgt, pasteboard=tgt.pb, keyboard=tgt,
                               store=w.store, settle_sec=0.05,
                               emit=lambda *a, **k: events.append(a))
        w.d._insertion = svc
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "legacy_db", rid)
        w.hub.historyPasteAgain_(None)
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        assert "legacy cleaned words" in tgt.content
        rows = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM insertions").fetchone()[0])
        assert rows == 0, "a jobless repaste wrote an attributed row"
        assert not any("record_failed" in str(e) for e in events), events
        w.d._insertion = None
    return {}


@case("M09-C071", env="native_appkit_main_queue+fixture_target")
def c071_paste_refusals_visible():
    with World() as w:
        jid, _, _ = seed_job(w.store, "refusals " + CANARY_A,
                             captured=iso(T0))
        tgt = R._HeldTarget(settable=False, ax_readable=True)
        svc = R._real_insertion(w, tgt)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", jid)
        w.hub.historyPasteAgain_(None)       # queued, held in the target
        assert tgt.arrived.wait(5)
        w.hub.historyPasteAgain_(None)       # while the first runs
        busy_note = rendered_text(w.hub.history_detail).lower()
        tgt.hold.set()
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        w.h.press()
        w.hub.historyPasteAgain_(None)
        rec_note = rendered_text(w.hub.history_detail).lower()
        w.h.release(delivered=False)
        assert "insertion is in progress" in busy_note, busy_note[-160:]
        assert "recording" in rec_note, rec_note[-160:]
        w.d._insertion = None
    return {}


@case("M09-C072", env="native_appkit_main_queue+fixture_target")
def c072_late_deletion_revokes_queued_paste():
    with World() as w:
        jid, _, _ = seed_job(w.store, "revoked " + CANARY_A,
                             captured=iso(T0))
        tgt = R._HeldTarget(settable=False, ax_readable=True)
        svc = R._real_insertion(w, tgt)
        w.store.add_job_deletion_listener(svc.revoke_job)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", jid)
        w.hub.historyPasteAgain_(None)
        assert tgt.arrived.wait(5)
        w.store.delete_everywhere("job", jid)
        tgt.hold.set()
        while svc.pending:
            time.sleep(0.01)
        w.drain()
        assert CANARY_A not in tgt.content, "deleted text was inserted"
        assert CANARY_A not in json.dumps(tgt.pb.ops, default=str)
        w.d._insertion = None
    return {}


# ---- replay / listening ----------------------------------------------------------

def _wav_sha(store, audio_id):
    import hashlib
    p = store.artifact(audio_id)["content_path"]
    root = pathlib.Path(store.artifacts_dir) if hasattr(
        store, "artifacts_dir") else None
    path = pathlib.Path(p) if pathlib.Path(p).is_absolute() else \
        (root / p if root else pathlib.Path(p))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@case("M09-C060")
def c060_replacement_stops_prior():
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        sha_a, sha_b = _wav_sha(w.store, a["audio"]), \
            _wav_sha(w.store, b["audio"])
        assert w.hub.replay.play_artifact(w.store, a["audio"])["status"] \
            == "playing"
        assert w.hub.replay.play_artifact(w.store, b["audio"])["status"] \
            == "playing"
        playing = R._playing(w.sounds)
        assert len(playing) == 1, playing
        assert _wav_sha(w.store, a["audio"]) == sha_a
        assert _wav_sha(w.store, b["audio"]) == sha_b
    return {}


@case("M09-C063", env="portable_real_framework")
def c063_large_audio_rapid_switching():
    import tracemalloc
    from m09_world import audio_samples
    with World() as w:
        ids = []
        for secs in (1, 60, 600):
            jid, _f = w.store.create_job(state="insertion_unverified")
            ids.append(w.store.write_audio_artifact(
                job_id=jid, stage="capture",
                samples=audio_samples(seconds=secs), sample_rate=16000))
        shas = [_wav_sha(w.store, i) for i in ids]
        tracemalloc.start()
        base_cur, _ = tracemalloc.get_traced_memory()
        timings = {}
        for n in range(100):
            aid = ids[0] if n % 10 else ids[1]
            t0 = time.monotonic()
            w.hub.replay.play_artifact(w.store, aid)
            timings.setdefault(aid, []).append(time.monotonic() - t0)
        t0 = time.monotonic()
        w.hub.replay.play_artifact(w.store, ids[2])
        big = time.monotonic() - t0
        w.hub.replay.stop()
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        live = R._playing(w.sounds)
        assert not live, f"sounds still retained: {live}"
        assert w.hub.replay._sound is None
        assert [_wav_sha(w.store, i) for i in ids] == shas
        retained_mb = (cur - base_cur) / 1e6
        assert retained_mb < 5.0, f"{retained_mb:.1f} MB retained after stop"
    raise Narrowed(
        f"100 switches + one 600 s decode; retained after stop"
        f" {retained_mb:.2f} MB (tracemalloc current), peak"
        f" {(peak - base_cur) / 1e6:.1f} MB; 600 s decode+start"
        f" {big * 1000:.0f} ms on the calling thread; originals unchanged",
        "audible NSSound behavior and main-thread feel with real sound:"
        " M09-V003")


@case("M09-C064", env="native_appkit_main_queue")
def c064_selection_away_and_back_closes_gate():
    with World() as w:
        a = seed_example(w.store, CANARY_A)
        b = seed_example(w.store, CANARY_B)
        R.open_training(w)
        R.select_training(w, a["example_id"])
        w.hub.trainingReplay_(None)
        R.select_training(w, b["example_id"])
        R.select_training(w, a["example_id"])
        w.hub.verbatim_field.setStringValue_("heard a")
        w.hub.trainingVerbatim_(None)
        w.drain()
        assert R.annotation_kinds(w.store, a["example_id"]) == [], \
            "authorization survived selection away and back"
        w.hub.trainingReplay_(None)
        w.hub.verbatim_field.setStringValue_("heard a")
        w.hub.trainingVerbatim_(None)
        w.drain()
        assert R.annotation_kinds(w.store, a["example_id"]) == \
            ["verbatim_reference"]
    return {}


@case("M09-C065")
def c065_verbatim_and_intended_independent():
    from localflow.v2.training_data import TrainingDataService
    with World(build=False) as w:
        a = seed_example(w.store, CANARY_A)
        svc = TrainingDataService(w.store)
        svc.mark_intended(a["example_id"], True)
        env = w.store.latest_revision(a["example_id"])
        assert not any(x.get("listened_audio") for x in
                       env.get("annotations") or []), \
            "intended mark fabricated listening"
        try:
            svc.set_verbatim(a["example_id"], "w", listened_audio=False)
            raise AssertionError("verbatim saved without listening")
        except ValueError:
            pass
        svc.set_verbatim(a["example_id"], "heard", listened_audio=True)
        env = w.store.latest_revision(a["example_id"])
        assert env["outcome"]["correctness"] == "correct"
        assert env["outcome"]["correctness_provenance"] == \
            "user_explicit_intended_writing"
    return {}


# ---- History sources, search, lineage ---------------------------------------

def _svc(store, tz=dt.timezone.utc):
    from localflow.v2.history_queries import HistoryQueryService
    return HistoryQueryService(store, tz=tz)


def _flat(res):
    return [r for g in res["groups"] for r in g["rows"]]


@case("M09-C040")
def c040_equal_instants_stable_tiebreak():
    with World(build=False) as w:
        t = "2026-09-26T12:00:00.000Z"
        jobs = [w.store.create_job(job_id=f"job-{c * 32}", captured_at_utc=t,
                                   time_quality="known")[0]
                for c in ("b", "a")]
        seed_legacy_db(w.store, 3, raw="r", cleaned="c",
                       ts=dt.datetime(2026, 9, 26, 12, tzinfo=dt.timezone.utc)
                       .timestamp())
        svc = _svc(w.store)
        first = [r["id"] for r in _flat(svc.search())]
        again = [r["id"] for r in _flat(svc.search())]
        expected = sorted(jobs) + ["legacy-db:3"]
        assert first == again == expected, (first, again, expected)
    return {"tie_break": "V2 job before legacy row, then id"}


@case("M09-C042")
def c042_unknown_times_stay_undated():
    with World(build=False) as w:
        ok, _ = w.store.create_job(captured_at_utc="2026-09-26T00:10:00.000Z",
                                   time_quality="known")
        bad, _ = w.store.create_job(captured_at_utc="not-a-date",
                                    time_quality="known")
        none, _ = w.store.create_job(time_quality="unknown")
        naive, _ = w.store.create_job(captured_at_utc="2026-09-26T00:10:00",
                                      time_quality="known")
        seed_legacy_pair(w.store, "undated raw", "undated clean", "log:c042")
        res = _svc(w.store).search()
        labels = {r["id"]: g["label"] for g in res["groups"]
                  for r in g["rows"]}
        assert labels[ok] == "2026-09-26"
        for jid in (bad, none, naive):
            assert labels[jid] == "Undated", (jid, labels[jid])
        assert res["groups"][-1]["label"] == "Undated"
    return {}


@case("M09-C044")
def c044_merged_limit_across_sources():
    with World(build=False) as w:
        n = 250
        def op(c):
            for i in range(n):
                jid = f"job-{i:032x}"
                c.execute("INSERT INTO jobs(job_id, kind, family_id, state,"
                          " attempt, captured_at_utc, time_quality,"
                          " created_at_utc, updated_at_utc) VALUES(?,?,?,?,"
                          "?,?,?,?,?)",
                          (jid, "dictation", f"fam-{i:032x}",
                           "insertion_confirmed", 1,
                           iso(T0 + 2 * i), "known", iso(T0), iso(T0)))
        w.store.submit(op)
        for i in range(n):
            seed_legacy_db(w.store, 1000 + i, raw=f"lr{i}", cleaned=f"lc{i}",
                           ts=T0 + 2 * i + 1)
        for i in range(n):
            seed_legacy_pair(w.store, f"pr{i}", f"pc{i}", f"log:{i}")
        svc = _svc(w.store)
        for limit in (1, 7, 200):
            rows = _flat(svc.search(limit=limit))
            assert len(rows) == limit, (limit, len(rows))
            # newest instants first across both dated sources
            want_first = "legacy-db:1249"  # T0+499 is the newest instant
            assert rows[0]["id"] == want_first, rows[0]["id"]
        zero = _flat(svc.search(limit=0))
        assert len(zero) == 3 * n, len(zero)  # documented: 0 = no limit
        pair_rows = [r for r in zero if r["kind"] == "legacy_log"]
        assert all(r["preview"] for r in pair_rows)
    return {"limits": [1, 7, 200, 0]}


@case("M09-C045", env="native_appkit_main_queue")
def c045_like_specials_literal():
    with World() as w:
        texts = {"%": "100% sure", "_": "snake_case word",
                 "\\": "back\\slash here", "'": "it's quoted",
                 "M09_CANARY": "plain M09_CANARY text"}
        ids = {k: seed_job(w.store, v, captured=iso(T0 + i))[0]
               for i, (k, v) in enumerate(texts.items())}
        control = seed_job(w.store, "nothing special here",
                           captured=iso(T0 + 99))[0]
        svc = _svc(w.store)
        for q, jid in ids.items():
            got = [r["id"] for r in _flat(svc.search(text=q))]
            if q == "_":  # also inside M09_CANARY
                assert jid in got and control not in got, (q, got)
            else:
                assert got == [jid], (q, got)
        open_view(w.hub, w.mq, "history")
        w.hub.history_search.setStringValue_("%")
        w.hub.historySearchChanged_(w.hub.history_search)
        w.drain()
        assert [r["id"] for r in history_rows(w.hub)] == [ids["%"]]
    return {}


class _ParamLog:
    """A connection proxy recording each statement's bound-parameter
    count (C046: parameter construction must not scale with matches)."""

    def __init__(self, conn, log):
        self._conn, self._log = conn, log

    def execute(self, sql, params=()):
        self._log.append(len(params))
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@case("M09-C046")
def c046_common_substring_large_store():
    bench = _bench_module()
    jobs, token, limit = 50000, "M09_SHARED_TOKEN", 200
    with World(build=False) as w:
        bench.seed_history(w.store, jobs=jobs, common_token=token)
        svc = _svc(w.store)
        counts = []
        real_submit = w.store.submit
        w.store.submit = lambda op: real_submit(
            lambda conn: op(_ParamLog(conn, counts)))
        try:
            t0 = time.monotonic()
            rows = _flat(svc.search(text=token, limit=limit))
            dt_ms = (time.monotonic() - t0) * 1000
        finally:
            w.store.submit = real_submit
        # Every seeded job carries the token and captured time grows with
        # the seed index, so the newest ``limit`` indices are the answer.
        want = [bench.job_row(i)[0]
                for i in range(jobs - 1, jobs - 1 - limit, -1)]
        assert [r["id"] for r in rows] == want, [r["id"] for r in rows[:3]]
        for jid in (want[0], want[-1]):
            raw = svc.job_detail(jid)["lineage"][0]["artifact"]["text"]
            assert token in raw, (jid, raw)
        # No O(matches) parameter list: the largest statement stays under
        # SQLite's historical 999-variable floor with 50,000 matches.
        assert counts and max(counts) < 999, max(counts or [0])
        # positive control: a miss returns nothing through the same path
        assert _flat(svc.search(text="M09_ABSENT_TOKEN", limit=limit)) == []
    return {"jobs": jobs, "hits_returned": len(rows),
            "max_bound_params": max(counts), "statements": len(counts),
            "ms": round(dt_ms, 1)}


@case("M09-C048")
def c048_unknown_destination_and_legacy_privacy():
    with World(build=False) as w:
        known, _, _ = seed_job(w.store, "known dest", captured=iso(T0),
                               app="Mail", bundle="com.apple.mail")
        unknown, _, _ = seed_job(w.store, "unknown dest",
                                 captured=iso(T0 + 1))
        seed_legacy_db(w.store, 21, raw="legacy mail", cleaned="legacy mail",
                       ts=T0 + 2, app="Mail", bundle="com.apple.mail")
        seed_legacy_pair(w.store, "log raw", "log clean", "log:c048")
        svc = _svc(w.store)
        for q in ("mail", "MAIL", "com.apple.mail"):
            got = {r["id"] for r in _flat(svc.search(app=q))}
            assert got == {known, "legacy-db:21"}, (q, got)
        rows = {r["id"]: r for r in _flat(svc.search())}
        assert rows[unknown]["app"] is None
        assert all(r["app"] is None for r in rows.values()
                   if r["kind"] == "legacy_log")
    return {}


@case("M09-C049")
def c049_malformed_meta_and_future_mode():
    with World(build=False) as w:
        good, _, _ = seed_job(w.store, "good row", captured=iso(T0),
                              mode="llm")
        bad, _ = w.store.create_job(captured_at_utc=iso(T0 + 1),
                                    time_quality="known",
                                    state="insertion_confirmed")

        def op(c):
            c.execute("INSERT INTO artifacts(artifact_id, job_id, stage,"
                      " kind, role, content_text, sha256, bytes, meta_json,"
                      " retention_class, purged, created_at_utc) VALUES("
                      "?,?,?,?,?,?,?,?,?,?,0,?)",
                      ("art-" + "c" * 32, bad, "cleanup", "text",
                       "applied_output", "corrupt meta row", "x", 1, "{",
                       "history", iso(T0)))
        w.store.submit(op)
        svc = _svc(w.store)
        rows = {r["id"]: r for r in _flat(svc.search())}
        assert rows[bad]["mode"] is None, "corrupt meta became a known mode"
        assert [r["id"] for r in _flat(svc.search(mode="llm"))] == [good]
        try:
            svc.search(mode="future_mode_synthetic")
            raise AssertionError("unknown mode accepted")
        except ValueError:
            pass
    return {}


@case("M09-C050", env="native_appkit_main_queue")
def c050_purged_text_is_not_a_hit():
    with World() as w:
        jid, raw, app_id = seed_job(w.store, "purge me " + CANARY_A,
                                    captured=iso(T0))
        open_view(w.hub, w.mq, "history")
        w.hub.state.set_history_search(CANARY_A)
        w.drain()
        assert [r["id"] for r in history_rows(w.hub)] == [jid]
        w.store.prune(now=time.time() + 3650 * 86400)
        w.hub.state.revalidate()
        w.drain()
        # The typed query itself is the user's own input, not payload.
        leaks = _where(w.hub, CANARY_A, skip=("history.search",))
        assert not leaks, leaks
        assert history_rows(w.hub) == []
    return {}


@case("M09-C053")
def c053_legacy_pair_absent_or_purged_half():
    with World(build=False) as w:
        raw_id, clean_id = seed_legacy_pair(w.store, "half raw M09_R",
                                            "half clean M09_C", "log:c053")
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_text=NULL WHERE"
            " artifact_id=?", (clean_id,)))
        svc = _svc(w.store)
        rows = [r for r in _flat(svc.search()) if r["kind"] == "legacy_log"]
        assert [r["id"] for r in rows] == [raw_id]
        d = svc.legacy_detail(raw_id)
        halves = {s["stage"]: s["artifact"] for s in d["lineage"]}
        assert halves["cleaned"]["present"] is False and \
            halves["cleaned"]["text"] is None
        assert halves["source"]["text"] == "half raw M09_R"
        assert _flat(svc.search(text="M09_C")) == []
    return {}


@case("M09-C054")
def c054_four_distinct_stages():
    with World(build=False) as w:
        jid, fam = w.store.create_job(captured_at_utc=iso(T0),
                                      time_quality="known",
                                      state="insertion_confirmed")
        texts = {"raw_transcript": "stage one raw",
                 "normalized_text": "stage two normalized",
                 "applied_output": "stage three cleaned",
                 "transform_output": "stage four transformed"}
        art = {role: w.store.write_text_artifact(
            job_id=jid, stage=role, role=role, text=t,
            retention_class="history",
            meta={"path": "applied"} if role == "transform_output" else None)
            for role, t in texts.items()}
        w.store.sync()
        d = _svc(w.store).job_detail(jid)
        got = {s["stage"]: (s["artifact"] or {}) for s in d["lineage"]}
        assert got["source"]["text"] == texts["raw_transcript"]
        assert got["normalized"]["text"] == texts["normalized_text"]
        assert got["cleaned"]["text"] == texts["applied_output"]
        assert got["transformed"]["text"] == texts["transform_output"]
        ids_ = {got[k]["artifact_id"] for k in got}
        assert len(ids_) == 4 and ids_ == set(art.values())
        jid2, _ = w.store.create_job(captured_at_utc=iso(T0 + 1),
                                     time_quality="known")
        w.store.write_text_artifact(job_id=jid2, stage="asr",
                                    role="raw_transcript", text="only raw",
                                    retention_class="history")
        d2 = _svc(w.store).job_detail(jid2)
        stages = {s["stage"]: s for s in d2["lineage"]}
        assert stages["cleaned"]["artifact"] is None
        assert stages["transformed"]["reason"] == "not_applicable"
    return {}


@case("M09-C055", env="portable_service_with_declared_coordinator_fixture")
def c055_real_retry_current_attempt():
    """The real coordinator retry of a retained job (collection off,
    transcript logging on): attempt 2 writes History's stage artifacts
    tagged with its attempt; History shows attempt 2."""
    with World(durations=[5.0]) as w:
        w.d.cfg["log_transcripts"] = True
        jid = _failed_job(w)
        # An earlier attempt's retained History artifacts (as a completed
        # attempt 1 would have written them, tagged attempt 1).
        w.store.write_text_artifact(job_id=jid, stage="asr",
                                    role="raw_transcript",
                                    text="ATTEMPT ONE raw",
                                    retention_class="history",
                                    meta={"attempt": 1})
        assert w.d.hubRetryJob(jid)["outcome"] == "requeued"
        fn, args = w.h.run_coordinator()
        fn(*args)
        w.store.sync()
        d = _svc(w.store).job_detail(jid)
        texts = {s["stage"]: (s["artifact"] or {}).get("text")
                 for s in d["lineage"]}
        assert texts["source"] and "ATTEMPT ONE" not in texts["source"], \
            texts
        assert d["lineage_attempt"] == d["attempt"] == 2, \
            (d["lineage_attempt"], d["attempt"])
    return {"attempt": 2}


@case("M09-C058")
def c058_equal_texts_distinct_identities():
    with World(build=False) as w:
        jid, raw, app_id = seed_job(w.store, "same words",
                                    captured=iso(T0), applied="same words")
        d = _svc(w.store).job_detail(jid)
        stages = {s["stage"]: s["artifact"] for s in d["lineage"]}
        assert stages["source"]["artifact_id"] == raw
        assert stages["cleaned"]["artifact_id"] == app_id
        from localflow.v2.ui.hub import _stage_diff
        assert _stage_diff("same words", "same words") == "(no changes)"
    return {}


@case("M09-C059")
def c059_unicode_long_diff_private():
    from localflow.v2.ui.hub import _stage_diff
    events = []
    with World(build=False) as w:
        w.d.v2log.emit = lambda *a, **k: events.append((a, k))
        long = "A🧠é" + "x" * 200000
        jid, raw, app_id = seed_job(w.store, long, captured=iso(T0),
                                    applied=long + " edited")
        d = _svc(w.store).job_detail(jid)
        src = [s for s in d["lineage"] if s["stage"] == "source"][0]
        assert src["artifact"]["text"].startswith("A🧠é")
        diff = _stage_diff(long, long + " edited")
        assert "edited" in diff
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_text=NULL WHERE"
            " artifact_id=?", (app_id,)))
        d2 = _svc(w.store).job_detail(jid)
        cleaned = [s for s in d2["lineage"] if s["stage"] == "cleaned"][0]
        assert cleaned["artifact"]["present"] is False
        assert _stage_diff(long, None) == "(stage unavailable)"
        assert not any("🧠" in json.dumps(e, default=str) or
                       "x" * 50 in json.dumps(e, default=str)
                       for e in events), "private text reached events"
    return {}


# ---- annotation transactions and leases -------------------------------------

def _tds(store):
    from localflow.v2.training_data import TrainingDataService
    return TrainingDataService(store)


def _live_leases(store, job_id, roles):
    marks = ",".join("?" * len(roles))
    return store.submit(lambda c: c.execute(
        "SELECT a.role, l.expires_at_utc FROM artifact_leases l JOIN"
        " artifacts a ON a.artifact_id=l.artifact_id WHERE a.job_id=? AND"
        " l.revoked_at_utc IS NULL AND a.role IN (" + marks + ")",
        (job_id, *roles)).fetchall())


@case("M09-C015")
def c015_unpin_keeps_annotation_retention():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        svc.set_verbatim(a["example_id"], "alpha beta", listened_audio=True)
        svc.add_span_correction(a["example_id"], "source_text", 0, 5, "ALPHA")
        svc.pin(a["example_id"], True)
        svc.pin(a["example_id"], False)
        days = w.store.retention_days["training_buffer"]
        w.store.prune_training(now=time.time() + (days + 2) * 86400)
        leases = _live_leases(w.store, a["job_id"],
                              ("verbatim_reference", "span_correction"))
        assert sorted(r for r, _e in leases) == \
            ["span_correction", "verbatim_reference"], leases
        assert all(e is None for _r, e in leases)
        assert svc.example_detail(a["example_id"])["pinned"] is False
    return {}


@case("M09-C073")
def c073_complete_annotation_transaction():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        before = R._table_snapshot(w.store, a["example_id"])
        svc.set_verbatim(a["example_id"], "alpha beta", listened_audio=True)
        mid = R._table_snapshot(w.store, a["example_id"])
        svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
        after = R._table_snapshot(w.store, a["example_id"])
        for x, y in ((before, mid), (mid, after)):
            assert y["artifacts"] == x["artifacts"] + 1
            assert y["leases"] == x["leases"] + 1
            assert y["revisions"] == x["revisions"] + 1
        chain = w.store.submit(lambda c: c.execute(
            "SELECT revision_id, parent_revision_id FROM training_revisions"
            " WHERE example_id=? ORDER BY rowid",
            (a["example_id"],)).fetchall())
        assert all(chain[i + 1][1] == chain[i][0]
                   for i in range(len(chain) - 1))
        assert after["row"][0] == "annotated"
        assert after["row"][1] == chain[-1][0]
    return {}


@case("M09-C074")
def c074_writer_never_nests_submit():
    with World(build=False) as w:
        st = w.store
        writer = {}
        nested = []
        real = st._submit

        def guard(fn, wait=False, timeout=15.0):
            if threading.current_thread().ident == writer.get("id"):
                nested.append(getattr(fn, "__name__", "op"))
                raise AssertionError("nested Store submit on the writer")
            return real(fn, wait=wait, timeout=timeout)
        st.submit(lambda c: writer.update(
            id=threading.current_thread().ident))
        st._submit = guard
        try:
            a = seed_example(st, "alpha beta")
            svc = _tds(st)
            svc.mark_intended(a["example_id"], True)
            svc.set_verbatim(a["example_id"], "w", listened_audio=True)
            svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
            svc.pin(a["example_id"], True)
            svc.exclude(a["example_id"], True)
            svc.exclude(a["example_id"], False)
            svc.readiness()
            svc.delete_everywhere(a["example_id"])
        finally:
            st._submit = real
        assert not nested, nested
    return {}


@case("M09-C076")
def c076_stage_deleted_between_read_and_write():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        before = R._table_snapshot(w.store, a["example_id"])
        real_submit = w.store.submit
        calls = {"n": 0}

        def submit(fn, wait=True, timeout=15.0):
            calls["n"] += 1
            if calls["n"] == 2:  # the writer op, after the preliminary read
                real_submit(lambda c: c.execute(
                    "UPDATE artifacts SET purged=1, content_text=NULL"
                    " WHERE artifact_id=?", (a["raw"],)))
            return real_submit(fn, wait=wait, timeout=timeout)
        svc.store = type("S", (), {"submit": staticmethod(submit),
                                   "__getattr__": lambda s, n:
                                   getattr(w.store, n)})()
        try:
            svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
            raise AssertionError("span saved on a purged stage")
        except (ValueError, RuntimeError):
            pass
        after = R._table_snapshot(w.store, a["example_id"])
        assert after == before, (before, after)
    return {}


@case("M09-C078")
def c078_invalid_spans_refuse_atomically():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        before = R._table_snapshot(w.store, a["example_id"])
        for s, e in ((-1, 1), (1, 1), (3, 2), (0, 999999)):
            try:
                svc.add_span_correction(a["example_id"], "source_text", s,
                                        e, "X")
                raise AssertionError(f"span [{s},{e}) accepted")
            except (ValueError, RuntimeError):
                pass
        assert R._table_snapshot(w.store, a["example_id"]) == before
    return {}


@case("M09-C080")
def c080_partial_never_full_correctness():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
        env = w.store.latest_revision(a["example_id"])
        assert env["outcome"]["correctness"] == "unreviewed"
        spans = [x for x in env["annotations"]
                 if x["kind"] == "span_correction"]
        assert spans and all(x["coverage"] == "partial" for x in spans)
        ready = svc.readiness()
        assert ready["dataset_coverage"]["verbatim_reviewed_examples"] == 0
        assert ready["readiness_metrics"]["task_eligibility"][
            "asr_supervised"]["count"] == 0
    return {}


@case("M09-C081")
def c081_pin_never_double_pins_annotations():
    with World(build=False) as w:
        a = seed_example(w.store, "alpha beta")
        svc = _tds(w.store)
        svc.set_verbatim(a["example_id"], "alpha beta", listened_audio=True)
        svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
        roles = ("verbatim_reference", "span_correction")
        before = _live_leases(w.store, a["job_id"], roles)
        svc.pin(a["example_id"], True)
        assert _live_leases(w.store, a["job_id"], roles) == before
        svc.pin(a["example_id"], False)
        assert _live_leases(w.store, a["job_id"], roles) == before
    return {"annotation_leases": len(before)}


@case("M09-C085", env="native_appkit_main_queue")
def c085_deleted_is_terminal_through_every_mutation():
    with World() as w:
        a = seed_example(w.store, "alpha beta " + CANARY_A)
        R.open_training(w)
        R.select_training(w, a["example_id"])
        ctx = w.hub._rendered.get("training_detail")
        _tds(w.store).delete_everywhere(a["example_id"])
        w.drain()
        svc = _tds(w.store)
        for fn, args in ((svc.pin, (True,)), (svc.exclude, (False,)),
                         (svc.mark_intended, (True,)),
                         (svc.add_span_correction,
                          ("source_text", 0, 5, "X"))):
            try:
                fn(a["example_id"], *args)
            except Exception:
                pass
        try:
            svc.set_verbatim(a["example_id"], "w", listened_audio=True)
        except Exception:
            pass
        # captured old Hub actions refuse (the rendered context is gone)
        for action in (w.hub.trainingMarkCorrect_, w.hub.trainingPin_,
                       w.hub.trainingExclude_, w.hub.trainingSpan_,
                       w.hub.trainingVerbatim_):
            action(None)
        assert example_state(w.store, a["example_id"]) == "deleted"
        live = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
            (a["job_id"],)).fetchone()[0])
        assert live == 0, f"{live} artifacts resurrected"
        assert ctx is not None and w.hub._rendered.get(
            "training_detail") is None
    return {}


def example_state(store, ex):
    return R.example_state(store, ex)


@case("M09-C125")
def c125_delete_beats_inflight_annotation():
    with World(build=False) as w:
        svc = _tds(w.store)
        a = seed_example(w.store, "alpha beta")
        svc.set_verbatim(a["example_id"], "w", listened_audio=True)
        svc.delete_everywhere(a["example_id"])
        live = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
            (a["job_id"],)).fetchone()[0])
        assert live == 0
        b = seed_example(w.store, "gamma delta")
        svc.delete_everywhere(b["example_id"])
        before = R._table_snapshot(w.store, b["example_id"])
        try:
            svc.set_verbatim(b["example_id"], "w", listened_audio=True)
            raise AssertionError("annotation on a deleted example")
        except (ValueError, RuntimeError):
            pass
        leases = w.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM artifact_leases l JOIN artifacts a ON"
            " a.artifact_id=l.artifact_id WHERE a.job_id=? AND"
            " l.revoked_at_utc IS NULL", (b["job_id"],)).fetchone()[0])
        assert leases == 0
        assert R._table_snapshot(w.store, b["example_id"]) == before
    return {}


# ---- deletion / retention across views -----------------------------------

@case("M09-C090", env="native_appkit_main_queue")
def c090_cross_view_payload_and_profile_revoked():
    with World() as w:
        a = seed_example(w.store, "profile source " + CANARY_A)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", a["job_id"])
        open_view(w.hub, w.mq, "insights")
        w.hub.state.select_insights_subview("voice")
        w.drain()
        # A cached profile (whatever the floor allows) is present.
        had_profile = (w.hub.state.views["insights"].get("data") or {}) \
            .get("profile") is not None
        R.open_training(w)
        R.select_training(w, a["example_id"])
        w.hub._delete_example()
        w.drain()
        assert (w.hub.state.views["insights"].get("data") or {}).get(
            "profile") is None, "cached profile survived the deletion"
        for view in ("history", "insights", "models"):
            open_view(w.hub, w.mq, view)
            assert CANARY_A not in json.dumps(w.hub.state.views,
                                              default=str), view
            assert CANARY_A not in R.everything_rendered(w.hub), view
    return {"profile_cached_before": had_profile}


@case("M09-C091")
def c091_restriction_during_pending_read():
    with World() as w:
        c = seed_example(w.store, "expiring " + CANARY_C)
        lat = R.latch_history(w)
        open_view(w.hub, w.mq, "history")
        gate = lat.hold("job_detail", when=lambda j: j == c["job_id"],
                        after=True)
        w.hub.state.select_history_row("job", c["job_id"])
        assert gate.arrived.wait(5)
        days = w.store.retention_days["training_buffer"]
        w.store.prune_training(now=time.time() + (days + 2) * 86400)
        w.hub.state.revalidate()  # what the app's retention pass calls
        gate.release.set()
        w.drain()
        assert CANARY_C not in json.dumps(w.hub.state.views, default=str), \
            "expired payload published by a read taken before the purge"
        assert CANARY_C not in R.everything_rendered(w.hub)
    return {}


@case("M09-C093")
def c093_missing_and_orphan_targets():
    with World(build=False) as w:
        jid, _, _ = seed_job(w.store, "no target", captured=iso(T0))
        w.store.submit(lambda c_: c_.execute(
            "INSERT INTO job_targets(job_id, app_name, app_bundle,"
            " recorded_at_utc) VALUES(?,?,?,?)",
            ("job-" + "e" * 32, "Ghost", "com.example.ghost", iso(T0))))
        svc = _svc(w.store)
        rows = _flat(svc.search())
        assert [r["id"] for r in rows] == [jid], rows
        assert rows[0]["app"] is None
        assert _flat(svc.search(app="Ghost")) == []
        assert svc.job_detail("job-" + "e" * 32) is None
    return {}


@case("M09-C128", env="native_appkit_main_queue")
def c128_invalidated_action_buffers():
    with World() as w:
        a = seed_example(w.store, "buffer " + CANARY_A)
        pastes, _ = R.record_coordinator(w.d, "hubPasteText", {})
        copies, _ = R.record_coordinator(w.d, "hubCopyText", None)
        open_view(w.hub, w.mq, "history")
        R.select_history(w, "job", a["job_id"])
        w.hub.teach_field.setStringValue_("buffer corrected " + CANARY_A)
        w.store.delete_everywhere("job", a["job_id"])
        w.drain()
        w.hub.historyPasteAgain_(None)
        w.hub.historyCopy_(None)
        w.hub.historyTeach_(None)
        cands = w.d._learning.candidates(status="pending") \
            if w.d._learning else []
        assert CANARY_A not in json.dumps(pastes + copies)
        assert not cands, cands
        assert not _where(w.hub, CANARY_A), _where(w.hub, CANARY_A)
    return {}


# ---- diagnostics ----------------------------------------------------------------

@case("M09-C095")
def c095_clock_rollback_keeps_stream_causality():
    from localflow.v2 import diagnostics as diag
    import tempfile
    a = [event(1, "2026-09-26T10:00:05.000Z", boot="a"),
         event(2, "2026-09-26T10:00:03.000Z", boot="a"),  # clock back
         event(3, "2026-09-26T10:00:07.000Z", boot="a")]
    b = [event(1, "2026-09-26T10:00:04.000Z", boot="b"),
         event(2, "2026-09-26T10:00:06.000Z", boot="b")]
    with tempfile.TemporaryDirectory() as td:
        write_events(td, "events-1.jsonl", a)
        write_events(td, "events-2.jsonl", b)
        got = diag.load_events(td)
        a_order = [r["sequence"] for r in got if r["boot_id"].endswith("a")]
        assert a_order == [1, 2, 3], a_order
        assert len(got) == 5
    return {}


@case("M09-C099")
def c099_last_n_after_order_and_filters():
    from localflow.v2 import diagnostics as diag
    import tempfile
    job = "job-" + "f" * 32
    recs_a, recs_b = [], []
    for i in range(1, 7):
        recs_a.append(event(i, f"2026-09-26T10:00:{2 * i:02d}.000Z",
                            boot="a", job=job if i % 2 else None,
                            level="ERROR" if i in (1, 3, 5) else "INFO"))
        recs_b.append(event(i, f"2026-09-26T10:00:{2 * i + 1:02d}.000Z",
                            boot="b", job=job,
                            level="ERROR" if i % 2 == 0 else "INFO"))
    with tempfile.TemporaryDirectory() as td:
        write_events(td, "events-2.jsonl", recs_a)
        write_events(td, "events-1.jsonl", recs_b)
        got = diag.load_events(td, job_id=job, level="ERROR", last=3)
        matching = sorted([r for r in recs_a + recs_b
                           if r.get("job_id") == job and
                           r["level"] == "ERROR"],
                          key=lambda r: r["timestamp_utc"])[-3:]
        assert [r["event_id"] + r["boot_id"][-1] for r in got] == \
            [r["event_id"] + r["boot_id"][-1] for r in matching]
    return {}


@case("M09-C101")
def c101_known_field_wrong_type():
    from localflow.v2 import diagnostics as diag
    import tempfile
    variants = [event(1, "2026-09-26T10:00:01.000Z",
                      reason_code={"text": "M09_DICT_CANARY"}),
                event(2, "2026-09-26T10:00:02.000Z",
                      reason_code=["M09_LIST_CANARY"]),
                event(3, "2026-09-26T10:00:03.000Z",
                      stage="sk-M09SECRETCANARY0123456789abcdef"),
                event(4, "2026-09-26T10:00:04.000Z", outcome="ok",
                      reason_code="valid_code")]
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "x.jsonl"
        diag.redacted_export(variants, out)
        text = out.read_text()
        for canary in ("M09_DICT_CANARY", "M09_LIST_CANARY",
                       "M09SECRETCANARY"):
            assert canary not in text, canary
        recs = [json.loads(x) for x in text.splitlines()]
        assert recs[3]["reason_code"] == "valid_code" and \
            recs[3]["outcome"] == "ok", recs[3]
    return {}


@case("M09-C102", env="native_appkit_main_queue")
def c102_local_display_vs_export():
    with World() as w:
        ed = R._events_dir(w)
        write_events(ed, "events-20260926-m09.jsonl", [
            event(1, "2026-09-26T10:00:00.000Z",
                  model_id="/Users/someone/private/model",
                  app_name="SecretApp", path="/Users/someone/doc.txt")])
        open_view(w.hub, w.mq, "diagnostics")
        out = w.h.tmp / "support.jsonl"
        undo = R.patch_appkit("NSSavePanel", R._fake_save_panel(out))
        try:
            w.hub.diagnosticsExport_(None)
            w.drain()
        finally:
            undo()
        text = out.read_text()
        for leak in ("/Users/someone", "SecretApp", "doc.txt"):
            assert leak not in text, leak
        assert "engine" not in text  # the local engine block never exports
    return {}


@case("M09-C103", env="native_appkit_main_queue")
def c103_large_log_never_parsed_on_main():
    from localflow.v2 import diagnostics as diag
    with World() as w:
        ed = R._events_dir(w)
        write_events(ed, "events-20260926-big.jsonl",
                     [event(i, f"2026-09-26T{10 + i // 3600 % 10:02d}:"
                               f"{i // 60 % 60:02d}:{i % 60:02d}.000Z")
                      for i in range(1, 100001)])
        open_view(w.hub, w.mq, "diagnostics")
        assert w.hub.state.views["diagnostics"]["data"]["count"] == 500
        main_parses = []
        real = diag.load_events

        def spy(*a, **k):
            main_parses.append(is_main())
            return real(*a, **k)
        diag.load_events = spy
        out = w.h.tmp / "big.jsonl"
        undo = R.patch_appkit("NSSavePanel", R._fake_save_panel(out))
        try:
            t0 = time.monotonic()
            w.hub.diagnosticsExport_(None)
            click_ms = (time.monotonic() - t0) * 1000
            w.drain()
        finally:
            undo()
            diag.load_events = real
        assert not any(main_parses), "log parsed on the main thread"
        assert len(out.read_text().splitlines()) == 500
    return {"input_lines": 100000, "exported": 500,
            "export_click_main_ms": round(click_ms, 1)}


@case("M09-C104", env="native_appkit_main_queue")
def c104_export_failure_safe_item_bound():
    from localflow.v2 import diagnostics as diag
    with World() as w:
        write_events(R._events_dir(w), "events-20260926-m09.jsonl",
                     [event(1, "2026-09-26T10:00:00.000Z")])
        open_view(w.hub, w.mq, "diagnostics")
        real = diag.redacted_export
        gate = threading.Event()

        def failing(records, path):
            gate.wait(5)
            raise OSError("disk full M09_PRIVATE_PATH")
        diag.redacted_export = failing
        out = w.h.tmp / "fail.jsonl"
        undo = R.patch_appkit("NSSavePanel", R._fake_save_panel(out))
        events = []
        w.d.v2log.emit = lambda *a, **k: events.append((a, k))
        try:
            w.hub.diagnosticsExport_(None)
            w.hub.state.select_view("history")
            gate.set()
            w.drain()
        finally:
            undo()
            diag.redacted_export = real
        diag_text = rendered_text(w.hub.diag_text)
        assert "Export failed (OSError)" in diag_text, diag_text[:200]
        assert "M09_PRIVATE_PATH" not in diag_text
        assert "M09_PRIVATE_PATH" not in json.dumps(events, default=str)
        hist = rendered_text(w.hub.history_detail) \
            if hasattr(w.hub, "history_detail") else ""
        assert "Export failed" not in hist
    return {}


# ---- long actions and downstream editors ------------------------------------

@case("M09-C107", env="native_appkit_main_queue")
def c107_your_voice_completion_after_newer_generation():
    with World() as w:
        open_view(w.hub, w.mq, "insights")
        w.hub.state.select_insights_subview("voice")
        w.drain()
        lat = Latch(w.hub.spec["profile_service"])
        w.hub.spec["profile_service"] = lat

        def nth(n):
            return lambda *a, **k: sum(
                1 for c in lat.calls if c[0] == "compute") == n
        first = lat.hold("compute", when=nth(1), after=False,
                         error=RuntimeError("stale generation failure"))
        second = lat.hold("compute", when=nth(2), after=True)
        w.hub.voiceGenerate_(None)            # A (held, will fail)
        assert first.arrived.wait(5)
        w.hub.voiceGenerate_(None)            # B (really computes)
        assert second.arrived.wait(10), "B never computed"
        b_done = threading.Event()
        w.mq.on_post = lambda fn, a: b_done.set()
        second.release.set()
        assert b_done.wait(5), "B's completion was never posted"
        w.mq.on_post = None
        w.mq.flush()
        # positive control: B's success is B's — no failure note
        assert w.hub._action_notes.get("voice") is None, \
            w.hub._action_notes.get("voice")
        first.release.set()
        w.drain()
        shown = rendered_text(w.hub.voice_pane.text)
        assert "stale generation failure" not in shown, \
            "an older generation's failure was attributed to the newer one"
        assert w.hub._action_notes.get("voice") is None
    return {"schedule": "A held; B computed and published; A fails late"}


@case("M09-C108", env="native_appkit_main_queue")
def c108_approve_uses_rendered_queue():
    with World() as w:
        R.open_training(w)
        w.hub.state.select_training_tab("review")
        w.drain()
        rows = [{"example_id": f"ex-{c * 32}", "job_id": f"job-{c * 32}",
                 "kind": "candidate", "candidate_id": f"cand-{c * 32}",
                 "candidate_status": "pending", "classification": {},
                 "suggestion": None} for c in ("a", "b")]
        calls = []
        lat = Latch(w.hub.spec["learning_service"])
        lat.approve = lambda cid, **k: calls.append(cid) or {}
        w.hub.spec["learning_service"] = lat
        view = w.hub.state.views["models"]
        # Render the queue [A, B] with no selection (first-row fallback).
        view["data"] = {**(view.get("data") or {}), "queue": list(rows),
                        "training_tab": "review"}
        w.hub._refresh_models_view()
        # The backing queue is replaced by [B, A]; not yet rendered.
        view["data"] = {**view["data"], "queue": list(reversed(rows))}
        w.hub.reviewApprove_(None)
        assert calls in ([], [rows[0]["candidate_id"]]), \
            f"approved {calls}, not the rendered first row"
    return {"approved": calls}


@case("M09-C109", env="native_appkit_main_queue")
def c109_editor_selection_survives_refresh():
    from Foundation import NSIndexSet
    with World() as w:
        svc = w.hub.spec["styles_service"]
        for name, app in (("Rule A", "com.example.a"),
                          ("Rule B", "com.example.b")):
            svc.add_rule(name=name, scope_kind="app", scope_value=app,
                         mode="raw", number_policy="inherit")
        open_view(w.hub, w.mq, "styles")
        rows = w.hub._rendered_rows["styles_table"]
        ia = next(i for i, r in enumerate(rows) if r["name"] == "Rule A")
        w.hub.styles_table.selectRowIndexes_byExtendingSelection_(
            NSIndexSet.indexSetWithIndex_(ia), False)
        rid_a = w.hub.state.views["styles"]["selected_id"]
        real = svc.rules
        svc.rules = lambda: list(reversed(real()))
        w.hub.state.reload_styles()
        w.hub.state.wait_for_queries(5)  # published, not yet rendered
        w.hub.style_name.setStringValue_("Rule A edited")
        w.hub.stylesUpdate_(None)
        svc.rules = real
        w.drain()
        names = {r.rule_id: r.name for r in svc.rules()}
        assert names[rid_a] == "Rule A edited", names
        assert "Rule B" in names.values()
        rows = w.hub._rendered_rows["styles_table"]
        sel = w.hub.styles_table.selectedRow()
        assert rows[sel]["rule_id"] == rid_a, "highlight moved to another rule"
    return {}


@case("M09-C110", env="native_appkit_main_queue")
def c110_m12_note_revision_race_ownership():
    """Run the M12 Scratchpad suite (its own main-drained harness) a few
    times: the historical note-revision race is M12-owned unless it
    reproduces here through the shared M09 publication path."""
    import subprocess
    root = HERE.parents[3]
    runs, fails = 3, []
    for _ in range(runs):
        p = subprocess.run([sys.executable, str(root / "tests/v2/context/"
                            "run_isolated.py"),
                            str(root / "tests/v2/notes/"
                                "test_scratchpad_hub.py")],
                           capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            fails.append((p.stdout + p.stderr)[-400:])
    if fails:
        raise AssertionError(f"{len(fails)}/{runs} M12 runs failed:"
                             f" {fails[0]}")
    raise Narrowed(f"{runs}/{runs} M12 Scratchpad suite runs green on the"
                   " repaired shared shell (its note-transform acceptance"
                   " included); no shared-publication race observed",
                   "ownership of the historical intermittent revision"
                   " race stays with M12 (not reproduced here)")


def _stall_probe(w, hold_s):
    """Hold the store writer; measure a background History search and a
    synchronous annotation from the main thread separately."""
    a = seed_example(w.store, "stall " + CANARY_A)
    lat = R.latch_history(w)
    open_view(w.hub, w.mq, "history")
    R.open_training(w)
    R.select_training(w, a["example_id"])
    release = threading.Event()
    w.store.submit(lambda c: release.wait(hold_s + 5), wait=False)
    t0 = time.monotonic()
    w.hub.state.set_history_search("stall")  # admission only
    admit_ms = (time.monotonic() - t0) * 1000
    timer = threading.Timer(hold_s, release.set)
    timer.start()
    t1 = time.monotonic()
    w.hub.trainingMarkCorrect_(None)  # synchronous store write
    sync_ms = (time.monotonic() - t1) * 1000
    timer.join()
    w.drain()
    search_threads = {c[3] for c in lat.calls if c[0] == "search"}
    return {"hold_ms": hold_s * 1000, "search_admission_main_ms":
            round(admit_ms, 1), "sync_annotation_main_blocked_ms":
            round(sync_ms, 1), "search_threads": sorted(search_threads)}


@case("M09-C018", env="portable_real_framework")
def c018_slow_store_while_dictation_continues():
    with World() as w:
        probe = _stall_probe(w, 1.0)
        assert "MainThread" not in probe["search_threads"], probe
        assert probe["search_admission_main_ms"] < 50, probe
        # dictation through the coordinator after the stall still lands
        w.h.press()
        w.h.release()
        fn, args = w.h.run_coordinator()
        fn(*args)
        assert w.h.pastes, "dictation did not complete"
    raise Narrowed(
        f"History query ran off main (threads {probe['search_threads']});"
        f" search admission {probe['search_admission_main_ms']} ms on main;"
        f" a synchronous annotation blocked main"
        f" {probe['sync_annotation_main_blocked_ms']} ms for a"
        f" {probe['hold_ms']:.0f} ms writer hold (documented limitation,"
        " M09-AUDIT-27); dictation completed after the stall",
        "hotkey acknowledgement against a real stalled app: manual"
        " (not constructible headless)")


@case("M09-C113", env="portable_real_framework")
def c113_slow_sync_mutation_measured():
    results = []
    for hold in (0.1, 1.0):
        with World() as w:
            results.append(_stall_probe(w, hold))
    for r in results:
        assert r["sync_annotation_main_blocked_ms"] >= r["hold_ms"] * 0.8, r
        assert r["search_admission_main_ms"] < 50, r
    raise Narrowed(json.dumps(results),
                   "timeout-scale (15 s) hold not run to keep the suite"
                   " bounded; the timeout path itself is covered by C075")


# ---- main thread / degraded store ------------------------------------------------

@case("M09-C122", env="native_appkit_main_queue")
def c122_errors_render_on_main():
    with World() as w:
        seed_example(w.store, CANARY_A)
        log = thread_oracle(w.hub)
        lat = R.latch_history(w)
        lat.fail("search", RuntimeError("query failure"))
        open_view(w.hub, w.mq, "history")
        w.hub.state.set_history_search("x")
        w.drain()
        R.open_training(w)
        lat2 = Latch(w.hub.spec["learning_service"])
        lat2.fail("mine_observation_candidates", RuntimeError("mine failure"))
        w.hub.spec["learning_service"] = lat2
        w.hub.state.select_training_tab("review")
        w.drain()
        done_main = []
        real_finish = w.hub._finish_action

        def finish(*a):
            done_main.append(is_main())
            return real_finish(*a)
        w.hub._finish_action = finish
        w.hub.reviewMine_(None)
        w.drain()
        assert log and all(e["main"] for e in log), \
            [e for e in log if not e["main"]]
        assert done_main == [True], done_main
    return {"refreshes": len(log)}


@case("M09-C123", env="native_appkit_main_queue")
def c123_coordinator_to_hub_callbacks_on_main():
    """The coordinator's calls into the Hub (inventory: showWindow_,
    scratchpad_note_created, scratchpad_receive, scratchpad_apply_
    transform, scratchpad_editor_active, scratchpad_quick_open) run on
    the main thread from their real producers."""
    with World(build=False) as w:
        w.d.openHub_(None)
        hub = w.d._hub
        seen = {}
        for name in ("scratchpad_note_created", "scratchpad_quick_open",
                     "scratchpad_receive", "scratchpad_editor_active"):
            real = getattr(hub, name)

            def wrap(*a, _n=name, _r=real, **k):
                seen.setdefault(_n, []).append(is_main())
                return _r(*a, **k)
            setattr(hub, name, wrap)
        w.drain()
        jid, _, _ = seed_job(w.store, "to note " + CANARY_A,
                             captured=iso(T0))
        w.d.hubSaveHistoryRow("job", jid, move=False)
        w.d.quickOpenScratchpad_(None)
        w.drain()
        w.h.press()
        w.h.release()
        fn, args = w.h.run_coordinator()
        fn(*args)
        w.drain()
        assert seen.get("scratchpad_note_created") and \
            seen.get("scratchpad_quick_open"), seen
        assert all(v for vals in seen.values() for v in vals), seen
    return {"entry_points_observed": sorted(seen)}


@case("M09-C124", env="native_appkit_main_queue")
def c124_frame_within_visible_bounds():
    R_hub = __import__("test_hub_shell")
    with MainQueue() as mq:
        R_hub._MQ = mq
        try:
            R_hub.test_window_bounds_and_min_size()
        finally:
            mq.discard()
    raise Narrowed("build-time frame and minimum size clamp to the"
                   " visible screen (test_window_bounds_and_min_size)",
                   "restoring a saved frame after a display change/removal"
                   " needs a real display change: M09-V005")


@case("M09-C126")
def c126_pure_state_counts_are_separate():
    """The results file records, per case, the environment it ran in;
    no case whose corpus environment is native is reported as run by a
    pure-state driver."""
    corpus = json.loads((HERE.parent / "m09_audit_corpus.json").read_text())
    wrong = []
    for c in corpus["cases"]:
        entry = CASE_DRIVERS.get(c["id"])
        if entry is None:
            continue
        env = entry[1]
        if c["environment"] in ("native_appkit_adapter",) and \
                env == "portable_real_framework":
            wrong.append(c["id"])
    assert not wrong, f"native cases labeled pure-state: {wrong}"
    return {"checked": len(CASE_DRIVERS)}


@case("M09-C127", env="native_appkit_main_queue")
def c127_empty_store_is_honest():
    from localflow.v2.ui.state import VIEWS
    with World() as w:
        for view in VIEWS:
            open_view(w.hub, w.mq, view)
            st = w.hub.state.views[view]
            assert not (st.get("error") and "Error" in str(st["error"])), \
                (view, st.get("error"))
        open_view(w.hub, w.mq, "history")
        txt = rendered_text(w.hub.history_detail)
        assert "No history yet" in txt, txt[:300]
        assert w.d.state is not None
    return {"views": len(VIEWS)}


# ---- metamorphic relations -------------------------------------------------------

def _history_snapshot(hub):
    v = hub.state.views["history"]
    return json.dumps({k: v.get(k) for k in ("data", "error", "loading")},
                      default=str)


@relation("M09-MR01")
def mr01_newer_query_wins():
    """Permute A's completion (before/after B's publication, success or
    failure) — the final state is always B's alone."""
    outcomes = {}
    for variant in ("a_first", "a_after_b", "a_raises_after_b",
                    "a_after_b_error"):
        with World() as w:
            ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
            jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
            lat = R.latch_history(w)
            open_view(w.hub, w.mq, "history")
            err_a = RuntimeError("A fails") if variant == \
                "a_raises_after_b" else None
            gate = lat.hold("search", when=lambda **k: k.get("text") ==
                            CANARY_A, after=True, error=err_a)
            if variant == "a_after_b_error":
                lat.fail("search", RuntimeError("B fails"),
                         when=lambda **k: k.get("text") == CANARY_B)
            w.hub.state.set_history_search(CANARY_A)
            assert gate.arrived.wait(5)
            if variant == "a_first":
                gate.release.set()
                w.drain()
            w.hub.state.set_history_search(CANARY_B)
            w.drain() if variant == "a_first" else _wait(
                lambda: not w.hub.state.views["history"]["loading"]
                or w.hub.state.views["history"].get("error"), 5)
            gate.release.set()
            w.drain()
            v = w.hub.state.views["history"]
            if variant == "a_after_b_error":
                ok = v.get("error") and _ids(w.hub) != [ja]
            else:
                ok = _ids(w.hub) == [jb] and not v.get("error") and \
                    v.get("loading") is False
            outcomes[variant] = bool(ok)
    assert all(outcomes.values()), outcomes
    return outcomes


@relation("M09-MR02")
def mr02_selection_binding():
    """Change the selection while detail/action work is outstanding —
    authority is refused or follows the new record, never migrates."""
    outcomes = {}
    for variant in ("detail_held", "detail_done", "reselect_same"):
        with World() as w:
            ja, _, _ = seed_job(w.store, CANARY_A, captured=iso(T0))
            jb, _, _ = seed_job(w.store, CANARY_B, captured=iso(T0 + 60))
            pastes, _ = R.record_coordinator(w.d, "hubPasteText", {})
            lat = R.latch_history(w)
            open_view(w.hub, w.mq, "history")
            R.select_history(w, "job", ja)
            gate = lat.hold("job_detail", when=lambda j: j == jb,
                            after=False)
            w.hub.state.select_history_row("job", jb)
            if variant == "reselect_same":
                w.hub.state.select_history_row("job", jb)
            assert gate.arrived.wait(5)
            if variant != "detail_held":
                gate.release.set()
                w.drain()
            w.mq.flush()
            w.hub.historyPasteAgain_(None)
            gate.release.set()
            w.drain()
            targets = [c[1].get("job_id") for c in pastes]
            outcomes[variant] = targets
            assert ja not in targets, (variant, targets)
            assert all(t == jb for t in targets), (variant, targets)
    return outcomes


def _payload_count(w, canary):
    blob = json.dumps(w.hub.state.views, default=str) + \
        R.everything_rendered(w.hub)
    playing = len(R._playing(w.sounds))
    return blob.count(canary) + playing


@relation("M09-MR03")
def mr03_delete_monotone():
    """Insert the deletion at successive barriers; after revocation the
    renderable/replayable payload count never increases."""
    series = {}
    for barrier in ("before_read", "after_read", "after_publish",
                    "during_replay"):
        with World() as w:
            a = seed_example(w.store, "mono " + CANARY_A)
            lat = R.latch_history(w)
            R.open_training(w)
            R.select_training(w, a["example_id"])
            if barrier == "during_replay":
                w.hub.trainingReplay_(None)
            open_view(w.hub, w.mq, "history")
            gate = lat.hold("job_detail", when=lambda j: j == a["job_id"],
                            after=(barrier != "before_read"))
            if barrier in ("before_read", "after_read"):
                w.hub.state.select_history_row("job", a["job_id"])
                assert gate.arrived.wait(5)
                w.store.delete_everywhere("job", a["job_id"])
                gate.release.set()
            else:
                gate.release.set()
                R.select_history(w, "job", a["job_id"])
                w.store.delete_everywhere("job", a["job_id"])
            counts = []
            for _ in range(3):
                w.drain()
                counts.append(_payload_count(w, CANARY_A))
            series[barrier] = counts
            assert counts == sorted(counts, reverse=True) and \
                counts[-1] == 0, (barrier, counts)
    return series


@relation("M09-MR04")
def mr04_listening_isolation():
    outcomes = {}
    for variant in ("replay_other", "replay_fails", "replay_self"):
        with World() as w:
            a = seed_example(w.store, CANARY_A)
            b = seed_example(w.store, CANARY_B)
            R.open_training(w)
            R.select_training(w, a["example_id"])
            if variant == "replay_other":
                w.hub.trainingReplay_(None)
                R.select_training(w, b["example_id"])
            else:
                R.select_training(w, b["example_id"])
                w.sounds.fail_play = variant == "replay_fails"
                w.hub.trainingReplay_(None)
                w.sounds.fail_play = False
            w.hub.verbatim_field.setStringValue_("heard")
            w.hub.trainingVerbatim_(None)
            w.drain()
            saved = R.annotation_kinds(w.store, b["example_id"])
            outcomes[variant] = saved
            expect = ["verbatim_reference"] if variant == "replay_self" \
                else []
            assert saved == expect, (variant, saved)
            assert R.annotation_kinds(w.store, a["example_id"]) == []
    return outcomes


@relation("M09-MR05")
def mr05_retry_idempotence():
    outcomes = {}
    for clicks in (1, 2, 3):
        with World(durations=[5.0]) as w:
            jid = _failed_job(w)
            open_view(w.hub, w.mq, "history")
            R.select_history(w, "job", jid)
            for _ in range(clicks):
                w.hub.historyRetry_(None)
            admitted = len(w.d._active_jobs)
            fn, args = w.h.run_coordinator()
            fn(*args)
            w.drain()
            outcomes[clicks] = (admitted, len(w.h.pastes))
            assert outcomes[clicks] == (1, 1), (clicks, outcomes[clicks])
    return {str(k): v for k, v in outcomes.items()}


@relation("M09-MR06")
def mr06_repaste_intent_identity():
    from fixture_target import FixtureTargetApp
    outcomes = {}
    for clicks in (1, 2):
        with World() as w:
            jid, _, _ = seed_job(w.store, f"intent {clicks} " + CANARY_A,
                                 captured=iso(T0))
            tgt = FixtureTargetApp()
            svc = R._real_insertion(w, tgt)
            ops = _op_ids(svc)
            open_view(w.hub, w.mq, "history")
            R.select_history(w, "job", jid)
            for _ in range(clicks):
                w.hub.historyPasteAgain_(None)
                while svc.pending:
                    time.sleep(0.01)
                w.drain()
            rows = w.store.submit(lambda c: c.execute(
                "SELECT DISTINCT job_id FROM insertions").fetchall())
            outcomes[clicks] = {"ops": len(ops), "distinct": len(set(ops)),
                                "attribution": [r[0] for r in rows]}
            assert len(ops) == clicks == len(set(ops)), outcomes[clicks]
            assert all(r[0] == jid for r in rows)
            w.d._insertion = None
    return {str(k): v for k, v in outcomes.items()}


@relation("M09-MR07")
def mr07_retention_cannot_manufacture_lineage():
    roles = {"source": "raw_transcript", "normalized": "normalized_text",
             "cleaned": "applied_output", "transformed": "transform_output"}
    outcomes = {}
    for removed in roles:
        with World(build=False) as w:
            jid, _ = w.store.create_job(captured_at_utc=iso(T0),
                                        time_quality="known",
                                        state="insertion_confirmed")
            ids_ = {}
            for stage, role in roles.items():
                ids_[stage] = w.store.write_text_artifact(
                    job_id=jid, stage=stage, role=role,
                    text=f"text of {stage}", retention_class="history",
                    meta={"path": "applied"} if stage == "transformed"
                    else None)
            w.store.submit(lambda c, a=ids_[removed]: c.execute(
                "UPDATE artifacts SET purged=1, content_text=NULL WHERE"
                " artifact_id=?", (a,)))
            d = _svc(w.store).job_detail(jid)
            got = {s["stage"]: s["artifact"] for s in d["lineage"]}
            for stage in roles:
                art = got[stage]
                if stage == removed:
                    assert art["present"] is False and art["text"] is None
                else:
                    assert art["text"] == f"text of {stage}", (stage, art)
                assert art["artifact_id"] == ids_[stage]
            outcomes[removed] = "absent, no borrowing"
    return outcomes


@relation("M09-MR08")
def mr08_main_thread_invariant():
    outcomes = {}
    for variant in ("drain_each", "accumulate_then_drain", "inline_guard"):
        with World() as w:
            seed_job(w.store, CANARY_A, captured=iso(T0))
            log = thread_oracle(w.hub, guard=(variant == "inline_guard"))
            open_view(w.hub, w.mq, "history")
            if variant == "inline_guard":
                w.mq.inline = True
            for q in ("a", "b", CANARY_A):
                w.hub.state.set_history_search(q)
                if variant == "drain_each":
                    w.drain()
            join_work(5)
            w.hub.state.wait_for_queries(5)
            w.mq.inline = False
            w.drain()
            off = [e for e in log if not e["main"]]
            outcomes[variant] = {"refreshes": len(log), "off_main": len(off)}
            if variant == "inline_guard":
                assert off, "inline control produced no off-main delivery"
            else:
                assert not off, (variant, off)
    return outcomes


@relation("M09-MR09")
def mr09_pin_lease_separation():
    outcomes = {}
    for seq in ((True,), (True, False), (False,), (True, True, False),
                (False, False)):
        with World(build=False) as w:
            a = seed_example(w.store, "alpha beta")
            svc = _tds(w.store)
            svc.set_verbatim(a["example_id"], "w", listened_audio=True)
            svc.add_span_correction(a["example_id"], "source_text", 0, 5, "X")
            roles = ("verbatim_reference", "span_correction")
            before = _live_leases(w.store, a["job_id"], roles)
            for p in seq:
                svc.pin(a["example_id"], p)
            after = _live_leases(w.store, a["job_id"], roles)
            pinned = svc.example_detail(a["example_id"])["pinned"]
            assert after == before, (seq, before, after)
            assert pinned is seq[-1], (seq, pinned)
            outcomes[str(seq)] = {"annotation_leases": len(after),
                                  "pinned": pinned}
    return outcomes


@relation("M09-MR10")
def mr10_legacy_search_identity():
    with World(build=False) as w:
        root, _c = seed_legacy_pair(w.store, "raw M09_RQ shared",
                                    "clean M09_CQ shared", "log:mr10")
        svc = _svc(w.store)
        variants = {}
        for q in ("M09_RQ", "M09_CQ", "shared", None):
            ids_ = [r["id"] for r in _flat(svc.search(text=q))
                    if r["kind"] == "legacy_log"]
            variants[str(q)] = ids_
            assert ids_ == [root], (q, ids_)
            d = svc.legacy_detail(ids_[0])
            texts = sorted((s["artifact"] or {}).get("text") or ""
                           for s in d["lineage"])
            assert texts == ["clean M09_CQ shared", "raw M09_RQ shared"]
    return variants


@relation("M09-MR11")
def mr11_filename_independent_diagnostics():
    from localflow.v2 import diagnostics as diag
    import itertools
    import tempfile
    job = "job-" + "9" * 32
    streams = {"a": [event(i, f"2026-09-26T10:00:{3 * i:02d}.000Z",
                           boot="a", job=job) for i in (1, 2, 3)],
               "b": [event(i, f"2026-09-26T10:00:{3 * i + 1:02d}.000Z",
                           boot="b", job=job, level="ERROR")
                     for i in (1, 2, 3)],
               "c": [event(i, f"2026-09-26T10:00:{3 * i + 2:02d}.000Z",
                           boot="c") for i in (1, 2, 3)]}
    results = set()
    for names in itertools.permutations(("events-1.jsonl",
                                         "events-2.jsonl",
                                         "events-3.jsonl.1")):
        with tempfile.TemporaryDirectory() as td:
            for name, key in zip(names, "abc"):
                write_events(td, name, streams[key])
            full = tuple(r["event_id"] + r["boot_id"][-1]
                         for r in diag.load_events(td))
            win = tuple(r["event_id"] + r["boot_id"][-1]
                        for r in diag.load_events(td, job_id=job, last=4))
            results.add((full, win))
    assert len(results) == 1, "order changed with filenames"
    return {"permutations": 6}


@relation("M09-MR12")
def mr12_redaction_extension_safety():
    """Adding unknown/nested/hostile fields to a valid event never adds
    exported content; the valid fields survive unchanged."""
    from localflow.v2.event_view import redact
    base = event(1, "2026-09-26T10:00:00.000Z", job="job-" + "1" * 32,
                 outcome="ok", reason_code="fine", duration_ms=12.5)
    clean = redact(base)
    extensions = [
        {"private_text": "M09_EXT_CANARY"},
        {"payload": {"nested": "M09_EXT_CANARY"}},
        {"future_field_v9": ["M09_EXT_CANARY"]},
        {"detail": "M09_EXT_CANARY"},
        {"app_name": "M09_EXT_CANARY"},
    ]
    for ext in extensions:
        out = redact({**base, **ext})
        assert "M09_EXT_CANARY" not in json.dumps(out), ext
        same = {k: v for k, v in out.items() if k != "omitted_fields"}
        want = {k: v for k, v in clean.items() if k != "omitted_fields"}
        assert same == want, (ext, same, want)
        assert out["omitted_fields"] == clean["omitted_fields"] + len(ext)
    return {"extensions": len(extensions)}


@relation("M09-MR13")
def mr13_lifecycle_restriction_monotone():
    """Interleave exclusion toggles and annotations with every
    restriction: quarantine/expiry/deletion are never erased; an
    annotation never restores a user exclusion (only Include does)."""
    ops = ("exclude_on", "exclude_off", "span", "verbatim", "mark")
    outcomes = {}
    with World(build=False) as w:
        svc = _tds(w.store)
        for start in ("quarantined_sensitive", "expired", "deleted",
                      "excluded"):
            for order in (ops, tuple(reversed(ops))):
                a = seed_example(w.store, "alpha beta")
                ex = a["example_id"]
                if start == "deleted":
                    svc.delete_everywhere(ex)
                else:
                    w.store.set_example_state(ex, start)
                    w.store.sync()
                trace = []
                for op in order:
                    try:
                        if op == "exclude_on":
                            svc.exclude(ex, True)
                        elif op == "exclude_off":
                            svc.exclude(ex, False)
                        elif op == "span":
                            svc.add_span_correction(ex, "source_text", 0, 5,
                                                    "X")
                        elif op == "verbatim":
                            svc.set_verbatim(ex, "w", listened_audio=True)
                        else:
                            svc.mark_intended(ex, True)
                    except Exception:
                        pass
                    st = example_state(w.store, ex)
                    trace.append((op, st))
                    if start != "excluded":
                        assert st == start, (start, order, trace)
                    elif op in ("span", "verbatim", "mark"):
                        # an annotation never flips excluded → live
                        prev = trace[-2][1] if len(trace) > 1 else start
                        if prev == "excluded":
                            assert st == "excluded", (order, trace)
                outcomes[f"{start}:{order[0]}"] = trace[-1][1]
    return outcomes


# ---- benchmark validity (records produced on this exact tree) -------------

def _bench_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "benchmark_m09", HERE.parents[3] / "scripts" / "v2" /
        "benchmark_m09.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _head():
    import subprocess
    return subprocess.run(["git", "-C", str(HERE.parents[3]), "rev-parse",
                           "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _bench_record(env_var, default_name):
    """A benchmark record, accepted only if it was produced by the tree
    under test (its control/run environment names HEAD with a clean
    production tree)."""
    import os
    path = os.environ.get(env_var)
    if not path:
        return None, f"set {env_var} to the {default_name} record"
    doc = json.loads(pathlib.Path(path).read_text())
    return doc, None


def _mutant_case(name):
    def run():
        import os
        doc, why = _bench_record("M09_BENCH_MUTATION_JSON",
                                 "m09_benchmark_mutation_check")
        if doc is None:
            raise RuntimeError(why)
        env = (doc.get("control_environment") or {})
        assert env.get("code_sha") == _head() and \
            env.get("production_tree_clean"), \
            f"mutation record is for {env.get('code_sha')}, not HEAD"
        r = doc["results"][name]
        assert r["outcome"] == "killed", r
        return {"mutant": name, "why": r["why"],
                "record": os.path.basename(os.environ[
                    "M09_BENCH_MUTATION_JSON"])}
    run.__name__ = f"bench_{name}"
    return run


for _cid, _mut in (("M09-C114", "empty_hit"), ("M09-C115", "skip_view"),
                   ("M09-C116", "zero_examples"),
                   ("M09-C117", "drop_publication"),
                   ("M09-C118", None), ("M09-C120", "memory_five_views")):
    if _mut is not None:
        CASE_DRIVERS[_cid] = (_mutant_case(_mut),
                              "benchmark_quick_isolated_process")


@case("M09-C119", env="benchmark_quick_isolated_process")
def c119_timer_covers_real_work():
    doc, why = _bench_record("M09_BENCH_MUTATION_JSON",
                             "m09_benchmark_mutation_check")
    if doc is None:
        raise RuntimeError(why)
    env = doc.get("control_environment") or {}
    assert env.get("code_sha") == _head(), "record not for HEAD"
    assert doc["results"]["enqueue_timer"]["outcome"] == "killed"
    t = doc["results"]["timer_sensitivity"]
    assert t["sensitive"], t
    return {"p50_delta_ms": t["p50_delta_ms"], "injected_ms":
            t["injected_ms"]}


@case("M09-C121", env="reference_mac_isolated")
def c121_reference_mac_qualification():
    doc, why = _bench_record("M09_BENCH_JSON", "full benchmark_m09")
    if doc is None:
        raise RuntimeError(why)
    env = doc["environment"]
    assert env["code_sha"] == _head() and env["production_tree_clean"], env
    assert not doc["quick"] and doc["mutant"] is None
    assert doc["work_valid"], doc["validity"]
    assert doc["timing_qualified"], "a budget was exceeded"
    return {"search_p95_ms": {k: v["p95_ms"] for k, v in
                              doc["history_search"].items()},
            "shell_full_pass_p95_ms": doc["shell"]["full_pass"]["p95_ms"]}


@relation("M09-MR14")
def mr14_benchmark_work_sensitivity():
    doc, why = _bench_record("M09_BENCH_MUTATION_JSON",
                             "m09_benchmark_mutation_check")
    if doc is None:
        raise RuntimeError(why)
    env = doc.get("control_environment") or {}
    assert env.get("code_sha") == _head(), "record not for HEAD"
    assert doc["results"]["control"]["work_valid"]
    outcomes = {k: v["outcome"] for k, v in doc["results"].items()
                if k not in ("control", "timer_sensitivity")}
    assert all(o == "killed" for o in outcomes.values()), outcomes
    return outcomes
