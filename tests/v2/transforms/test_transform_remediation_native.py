"""M11 remediation regressions — the native half (AppKit/PyObjC).

The coordinator, Hub, Scratchpad editor and preview panel cases of the
2026-09-24 M11 audit remediation, driven through the real AppDelegate
(test_transform_pipeline's Harness), the real Hub
(test_scratchpad_hub's harness) and the instrumented fixture target.
They need macOS with PyObjC; the portable half is
test_transform_remediation.py.

Threading rule: ``_tfShowResult_`` and every panel call run on the
main thread — AppHelper.callAfter is queued and the TEST flushes it
(never inline from the transform thread).

Run: .venv/bin/python tests/v2/transforms/test_transform_remediation_native.py
     [--json OUT.json] [--trace]
"""

import json
import pathlib
import sys
import time
import traceback
from dataclasses import replace
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))
sys.path.insert(0, str(HERE.parents[1] / "notes"))

import localflow.app as app_mod  # noqa: E402
import test_transform_pipeline as tp  # noqa: E402
import claude_fakes  # noqa: E402
from fixture_target import FixtureTargetApp  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


class Deferred:
    """Queue AppHelper.callAfter; the test flushes on the main thread."""

    def __init__(self, *modules):
        self.modules = modules or (app_mod,)

    def __enter__(self):
        self.queue = []
        self._real = [m.AppHelper.callAfter for m in self.modules]
        for m in self.modules:
            m.AppHelper.callAfter = lambda fn, *a: self.queue.append((fn, a))
        return self

    def flush(self):
        while self.queue:
            fn, a = self.queue.pop(0)
            fn(*a)

    def __exit__(self, *exc):
        for m, real in zip(self.modules, self._real):
            m.AppHelper.callAfter = real


def wait_idle(d, timeout=5.0):
    deadline = time.monotonic() + timeout
    while d._tf_active is not None and time.monotonic() < deadline:
        time.sleep(0.02)


def wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not pred() and time.monotonic() < deadline:
        time.sleep(0.02)
    return pred()


def selection_target(content="alpha rewrite this rough sentence omega",
                     sel=(6, 33), title="Doc A.txt", role="AXTextArea"):
    t = FixtureTargetApp(window_title=title, role=role)
    t.set_content(content)
    t.selection = sel
    t.caret = sel[1]
    return t


def show(h, result, capture, defn):
    with Deferred() as q:
        h.d._tfShowResult_(result, capture, defn)
        q.flush()
    return h.d._tf_panel._state["candidate_id"] \
        if h.d._tf_panel is not None else None


def accept(h, result, capture, candidate_id):
    with Deferred() as q:
        h.d.tfAcceptTransform(result, capture, candidate_id)
        time.sleep(0.4)
        q.flush()


def count(h, sql, args=()):
    return h.d.store.submit(lambda db: db.execute(sql, args).fetchone()[0])


# ---------------------------------------------------------------------------
# 03 — the coordinator sees the Claude result, not a fault
# ---------------------------------------------------------------------------

@case
def f03_coordinator_uses_claude_result_not_fault():
    """The real supervisor → Claude module → engine reply, rebuilt by the
    coordinator (ADR-0002: no worker on the transform path)."""
    src = "Give exactly three options."
    sup, client = claude_fakes.claude_supervisor(claude_fakes.pe_answer(
        "Give exactly three options, numbered.",
        [("Give exactly three options", "Give exactly three options")]))
    h = tp.Harness([1.0], supervisor=sup)
    try:
        defn = h.d._transforms_snapshot().by_id("builtin:prompt_engineer")
        res = h.d._m11_run_transform(defn, src, source_kind="selection")
        assert res.path == "applied", (res.path, res.reason)
        assert res.coverage and res.validator_revision
        model, reasoning = app_mod.v2_transforms.claude.recommended(
            "prompt_engineer")
        assert client.calls[0]["model"] == model
        assert (res.model, res.reasoning) == (model, reasoning)
    finally:
        h.close()


# ---------------------------------------------------------------------------
# 06 — selected-text replacement authority
# ---------------------------------------------------------------------------

def _captured(h, tgt, output="rewrite this refined sentence"):
    h.d.supervisor = tp.M11Supervisor("", transform_outputs=[
        (output, "applied")])
    tp._fixture_service(h.d, tgt)
    capture, reason = h.d._m11_capture_selection()
    assert capture is not None, reason
    defn = h.d._transforms_snapshot().by_id("builtin:polish")
    result = h.d._m11_run_transform(defn, capture["source"],
                                    source_kind="selection",
                                    selection=capture["range"])
    return capture, defn, result


@case
def forgotten_workspace_ancestor_blocks_apply_before_any_write():
    target = selection_target()
    h = tp.Harness([1.0])
    try:
        capture, _, result = _captured(h, target)
        old = {'fingerprint': 'forgotten-ancestor'}
        capture['_apply_contexts'] = (old, {})
        checks, notices = [], []
        h.d._tf_intelligence = SimpleNamespace(pack_valid=lambda pack: checks.append(pack) or pack != old)
        h.d._tf_status = notices.append
        before = target.content
        h.d.tfAcceptTransform(result, capture, None)
        assert checks == [old], checks
        assert notices and 'forgotten' in notices[0]
        assert target.content == before
        assert not capture.get('_apply_started')
        assert not h.d._insertion.pending
    finally:
        h.close()


@case
def preview_copy_checks_context_and_preserves_source_recovery():
    h = tp.Harness([1.0])
    try:
        _, _, result = _captured(h, selection_target())
        pack = {"fingerprint": "forgotten-preview"}
        result = replace(result, job=replace(result.job, context_pack=pack))
        notices, copies = [], []
        h.d._tf_intelligence = SimpleNamespace(pack_valid=lambda value: False)
        h.d._tf_status = notices.append
        h.d._guarded_copy = lambda text: copies.append(text) or True
        assert h.d.tfCopyTransform(result) is False
        assert not copies and "forgotten" in notices[-1]
        source = replace(result, output=result.job.source, path="fallback_original")
        assert h.d.tfCopyTransform(source) is True
        assert copies == [source.output]
        chained = replace(source, job=replace(source.job, source_kind="result"))
        assert h.d.tfCopyTransform(chained) is False
        assert copies == [source.output]
        h.d._tf_intelligence = SimpleNamespace(pack_valid=lambda value: True)
        assert h.d.tfCopyTransform(result) is True
        assert copies[-1] == result.output
    finally:
        h.close()


@case
def native_workspace_checks_forget_on_its_publication_writer():
    from localflow.v2.memory import MemoryStore
    from localflow.v2.transforms.intelligence import IntelligenceService, memory_callbacks
    from test_intelligence_memory import LexicalFixture
    h = tp.Harness([1.0])
    service = None
    try:
        capture, defn, result = _captured(h, selection_target())
        capture["operation_id"] = "native-forget-before-publication"
        memory = MemoryStore(h.d.store, embedding=LexicalFixture())
        record = memory.remember("The preview uses the cedar encoder.")
        pack = memory.search("cedar encoder").to_dict()
        assert pack["items"]
        result = replace(result, job=replace(result.job, context_pack=pack))
        service = IntelligenceService(h.d.store, h.d._tf_store, object(), **memory_callbacks(memory))
        h.d._tf_services = lambda: service
        notices, opened = [], []
        h.d._tf_status = notices.append
        h.d._tf_open_workspace = lambda *args: opened.append(args)
        append = service.sessions.append
        def forget_before_append(*args, **kwargs):
            memory.forget(record["id"])
            return append(*args, **kwargs)
        service.sessions.append = forget_before_append
        with Deferred() as q:
            h.d.tfRefineTransform(result, capture, defn)
            assert wait_until(lambda: bool(q.queue))
            q.flush()
        assert not opened and "forgotten" in notices[-1]
        saved = service.sessions.list()
        assert len(saved) == 1
        session = service.sessions.read(saved[0]["id"])
        assert session["prompt"] == capture["source"] and session["revision"] == 1
        # A chained model source must not be saved as independent user text.
        capture = dict(capture, operation_id="revoked-chain", source=result.output)
        result = replace(result, job=replace(result.job, source_kind="result", source=result.output))
        with Deferred() as q:
            h.d.tfRefineTransform(result, capture, defn)
            assert wait_until(lambda: bool(q.queue))
            q.flush()
        assert len(service.sessions.list()) == 1 and not opened
    finally:
        if service:
            service.close()
        h.close()


@case
def preview_save_refuses_new_revoked_text_but_reconciles_committed_note():
    from localflow.v2.memory import MemoryStore
    from localflow.v2.notes import NoteStore
    from localflow.v2.transforms.intelligence import IntelligenceService, memory_callbacks
    from test_intelligence_memory import LexicalFixture
    h = tp.Harness([1.0])
    service = None
    try:
        _, defn, result = _captured(h, selection_target())
        memory = MemoryStore(h.d.store, embedding=LexicalFixture())
        record = memory.remember('Cedar uses the serial encoder.')
        pack = memory.search('Cedar encoder').to_dict()
        result = replace(result, job=replace(result.job, context_pack=pack))
        service = IntelligenceService(h.d.store, h.d._tf_store, object(), **memory_callbacks(memory))
        h.d._tf_intelligence = service
        h.d._notes_store = NoteStore(h.d.store)
        notices = []
        h.d._tf_panel = SimpleNamespace(reoffer_save=lambda message, value: notices.append(message))
        h.d.tfSaveToScratchpad(result, defn)
        saved = h.d._notes_store.notes()
        assert len(saved) == 1
        memory.forget(record['id'])
        # A lost response to a save that already committed resolves to that note.
        key = (result.job.task_key(), app_mod.v2.ids.sha256_text(result.output))
        h.d._tf_pending_saves[key] = saved[0]['note_id']
        h.d.tfSaveToScratchpad(result, defn)
        assert not notices and not h.d._tf_pending_saves
        h.d.tfSaveToScratchpad(result, defn)
        assert 'forgotten' in notices[-1]
        assert len(h.d._notes_store.notes()) == 1
        assert h.d._notes_store.open_note(saved[0]['note_id'])['revision']['content'] == result.output
    finally:
        if service:
            service.close()
        h.close()


@case
def f06_same_app_other_document_not_replaced():
    for other_title, other_content in (
            ("Doc B.txt", "alpha rewrite this rough sentence omega"),
            ("Doc A.txt", "gamma rewrite this rough sentence delta")):
        tgt = selection_target()
        h = tp.Harness([1.0])
        try:
            capture, _defn, result = _captured(h, tgt)
            tgt.window_title = other_title          # FLOW-02
            tgt.set_content(other_content)
            tgt.selection = (6, 33)
            accept(h, result, capture, None)
            assert tgt.content == other_content, tgt.content
        finally:
            h.close()


@case
def f06_unreadable_selection_is_not_replacement_proof():
    tgt = selection_target()
    h = tp.Harness([1.0])
    try:
        capture, _defn, result = _captured(h, tgt)
        tgt.selection = (0, 5)                      # FLOW-03
        tgt.ax_readable = False
        before = tgt.content
        accept(h, result, capture, None)
        assert tgt.content == before, tgt.content
    finally:
        h.close()


@case
def f06_accept_replaces_with_positive_proof():
    tgt = selection_target()
    h = tp.Harness([1.0])
    try:
        capture, _defn, result = _captured(h, tgt)
        accept(h, result, capture, None)
        assert wait_until(lambda: "refined" in tgt.content), tgt.content
        assert tgt.content == "alpha rewrite this refined sentence omega"
    finally:
        h.close()


@case
def f06_secure_field_classified_before_any_content_read():
    tgt = selection_target(content="hunter2", sel=(0, 7),
                           role="AXSecureTextField")
    reads = []
    real_attr, real_range = tgt.attribute, tgt.string_for_range
    tgt.attribute = lambda el, n: (reads.append(n), real_attr(el, n))[1]
    tgt.string_for_range = lambda *a: (reads.append("range_text"),
                                       real_range(*a))[1]
    h = tp.Harness([1.0])
    try:
        tp._fixture_service(h.d, tgt)
        capture, reason = h.d._m11_capture_selection()
        assert capture is None and reason == "secure_field", reason
        assert "AXSelectedTextRange" not in reads and \
            "range_text" not in reads, reads
    finally:
        h.close()


# ---------------------------------------------------------------------------
# 07 — Scratchpad destination authority (real Hub)
# ---------------------------------------------------------------------------

def _hub_env():
    import test_scratchpad_hub as sh
    import localflow.v2.ui.hub as hub_mod
    h = sh.Harness(durations=[1.0], supervisor=sh.TFSupervisor())
    hub = sh.make_hub(h)
    h.d._hub = hub
    return sh, hub_mod, h, hub


def _open(hub, h, sh, note_id, q):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index("scratchpad"))
    hub.state.select_scratchpad_note(note_id)
    hub.state.wait_for_queries()
    q.flush()
    hub.editor.bind_note(h.d._notes_store.open_note(note_id))


def _content(h, note_id):
    return h.d._notes_store.open_note(note_id)["revision"]["content"]


@case
def f07_accept_checks_the_captured_note_identity():
    sh, hub_mod, h, hub = _hub_env()
    try:
        with Deferred(app_mod, hub_mod) as q:
            a = h.d._notes_store.create_note("alpha beta gamma")["note_id"]
            b = h.d._notes_store.create_note("alpha beta delta")["note_id"]
            _open(hub, h, sh, a, q)
            h.d.tfRunNoteTransform("builtin:polish", "alpha", (0, 5),
                                   {"note_id": a, "revision_id":
                                    hub.editor.model.revision_id})
            wait_idle(h.d)
            q.flush()
            st = h.d._tf_panel._state
            _open(hub, h, sh, b, q)                  # FLOW-04
            h.d._tf_panel.panelAccept_(None)
            q.flush()
            assert _content(h, b) == "alpha beta delta", _content(h, b)
            assert _content(h, a) == "alpha beta gamma"
            applied, reason = hub.scratchpad_apply_transform(
                st["result"], st["capture"])
            # M12 remediation: the first value is the arrival receipt when
            # applied, else None.
            assert not applied and reason == "note_changed", reason
    finally:
        h.close()


@case
def f07_chained_transform_keeps_destination_authority():
    sh, hub_mod, h, hub = _hub_env()
    try:
        with Deferred(app_mod, hub_mod) as q:
            a = h.d._notes_store.create_note("alpha beta gamma")["note_id"]
            _open(hub, h, sh, a, q)
            h.d.tfRunNoteTransform("builtin:polish", "alpha", (0, 5),
                                   {"note_id": a, "revision_id":
                                    hub.editor.model.revision_id})
            wait_idle(h.d)
            q.flush()
            st = h.d._tf_panel._state
            h.d.tfTransformOfResult(st["result"], st["capture"],
                                    "builtin:polish")   # FLOW-05
            wait_idle(h.d)
            q.flush()
            from AppKit import NSMakeRange
            hub.editor.text.setSelectedRange_(NSMakeRange(16, 0))
            h.d._tf_panel.panelAccept_(None)
            q.flush()
            got = _content(h, a)
            assert got in ("TRANSFORMED OUTPUT beta gamma",
                           "alpha beta gamma"), got
            assert not got.endswith("gammaTRANSFORMED OUTPUT"), got
    finally:
        h.close()


@case
def f07_selection_offsets_are_utf16_converted():
    sh, hub_mod, h, hub = _hub_env()
    try:
        with Deferred(app_mod, hub_mod) as q:
            a = h.d._notes_store.create_note("😀 alpha beta")["note_id"]
            _open(hub, h, sh, a, q)
            from AppKit import NSMakeRange
            hub.editor.text.setSelectedRange_(NSMakeRange(3, 5))
            assert hub.editor.selected_text() == "alpha", \
                hub.editor.selected_text()
            assert hub.editor.selected_range() == (2, 7)
    finally:
        h.close()


# ---------------------------------------------------------------------------
# 08 / 09 / 10 — evidence through the coordinator
# ---------------------------------------------------------------------------

@case
def f08_selected_preview_respects_collection_state():
    for state, expect in ((None, 0), ("disabled", 0), ("paused", 0),
                          ("enabled", 1)):
        tgt = selection_target()
        h = tp.Harness([1.0])
        try:
            if state:
                h.d.consent.set(state, note="test")
            capture, defn, result = _captured(h, tgt)
            cid = show(h, result, capture, defn)
            n = count(h, "SELECT COUNT(*) FROM transform_candidates")
            assert n == expect, (state, n)
            assert (cid is not None) == bool(expect)
            assert h.d._tf_panel is not None   # the preview still works
        finally:
            h.close()


@case
def f08_dictation_candidate_follows_captured_consent():
    sup = tp.M11Supervisor("please review the parser fix",
                           transform_outputs=[("Please review the parser"
                                               " fix.", "applied")])
    h = tp.Harness([1.0], supervisor=sup,
                   context=tp.FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.press_release()
        h.run_coordinator()
        assert count(h, "SELECT COUNT(*) FROM transform_candidates") == 0
    finally:
        h.close()


@case
def f09_selected_candidate_retains_decision_inputs():
    tgt = selection_target()
    h = tp.Harness([1.0])
    try:
        h.d.consent.set("enabled", note="test")
        capture, defn, result = _captured(h, tgt)
        cid = show(h, result, capture, defn)
        out_art = h.d.store.submit(lambda db: db.execute(
            "SELECT output_artifact_id FROM transform_candidates WHERE"
            " candidate_id=?", (cid,)).fetchone()[0])
        roles = dict(h.d.store.submit(lambda db: db.execute(
            "SELECT role, content_text FROM artifacts WHERE"
            " parent_artifact_id=?", (out_art,)).fetchall()))
        assert roles.get("transform_prompt") == result.prompt
        decision = json.loads(roles["transform_decision"])
        assert decision["path"] == result.path
    finally:
        h.close()


@case
def f09_dictation_decision_map_retained():
    sup = tp.M11Supervisor("please review the parser fix",
                           transform_outputs=[("Please review the parser"
                                               " fix.", "applied")])
    h = tp.Harness([1.0], supervisor=sup,
                   context=tp.FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d.consent.set("enabled", note="test")
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.press_release()
        _fn, (text, job) = h.run_coordinator()
        assert tp.art_texts(h.d.store, job["job_id"], "transform_decision")
    finally:
        h.close()


@case
def f09_note_candidate_records_destination_revision():
    sh, hub_mod, h, hub = _hub_env()
    try:
        h.d.consent.set("enabled", note="test")
        with Deferred(app_mod, hub_mod) as q:
            a = h.d._notes_store.create_note("alpha beta")["note_id"]
            _open(hub, h, sh, a, q)
            rev = hub.editor.model.revision_id
            h.d.tfRunNoteTransform("builtin:polish", "alpha", (0, 5),
                                   {"note_id": a, "revision_id": rev})
            wait_idle(h.d)
            q.flush()
        meta = json.loads(h.d.store.submit(lambda db: db.execute(
            "SELECT a.meta_json FROM artifacts a JOIN transform_candidates"
            " c ON c.source_artifact_id=a.artifact_id ORDER BY c.rowid"
            " DESC LIMIT 1").fetchone()[0]))
        assert meta["note_id"] == a and meta["note_revision_id"] == rev
    finally:
        h.close()


@case
def f09_selected_accept_is_attributed_to_its_candidate():
    tgt = selection_target()
    h = tp.Harness([1.0])
    try:
        h.d.consent.set("enabled", note="test")
        capture, defn, result = _captured(h, tgt)
        cid = show(h, result, capture, defn)
        accept(h, result, capture, cid)
        assert wait_until(lambda: "refined" in tgt.content)
        time.sleep(0.2)
        rows = h.d.store.submit(lambda db: db.execute(
            "SELECT job_id FROM insertions").fetchall())
        assert rows == [(cid,)], rows
    finally:
        h.close()


@case
def f10_retry_original_records_no_rejection():
    tgt = selection_target()
    h = tp.Harness([1.0])
    try:
        h.d.consent.set("enabled", note="test")
        capture, defn, result = _captured(h, tgt)
        h.d.supervisor.transform_outputs.append(("another rewrite",
                                                 "applied"))
        first = show(h, result, capture, defn)
        with Deferred() as q:
            h.d.tfRetryOriginal(result, capture, defn, first)
            wait_idle(h.d)
            q.flush()
        assert count(h, "SELECT COUNT(*) FROM preference_observations") \
            == 0
        meta = json.loads(h.d.store.submit(lambda db: db.execute(
            "SELECT a.meta_json FROM artifacts a JOIN transform_candidates"
            " c ON c.output_artifact_id=a.artifact_id ORDER BY c.rowid"
            " DESC LIMIT 1").fetchone()[0]))
        assert meta.get("retry_of") == first, meta
    finally:
        h.close()


# ---------------------------------------------------------------------------
# 11 — the preview panel's actions
# ---------------------------------------------------------------------------

@case
def f11_panel_actions_do_not_overlap_and_hit_test():
    from AppKit import NSMakePoint, NSSize
    from localflow.v2.ui.transforms_panel import TransformPreviewPanel
    h = tp.Harness([1.0])
    try:
        panel = TransformPreviewPanel.alloc().init_panel(h.d)
        for size in (None, (460.0, 360.0)):
            if size:
                panel.panel.setContentSize_(NSSize(*size))
            content = panel.panel.contentView()
            frames = {k: b.frame() for k, b in panel._buttons.items()}
            items = list(frames.items())
            for i, (ka, a) in enumerate(items):
                for kb, b in items[i + 1:]:
                    overlap = (a.origin.x < b.origin.x + b.size.width
                               and b.origin.x < a.origin.x + a.size.width
                               and a.origin.y < b.origin.y + b.size.height
                               and b.origin.y < a.origin.y + a.size.height)
                    assert not overlap, (ka, kb)
            for key, btn in panel._buttons.items():
                f = btn.frame()
                centre = NSMakePoint(f.origin.x + f.size.width / 2,
                                     f.origin.y + f.size.height / 2)
                hit = content.hitTest_(centre)
                assert hit is btn or (hit is not None
                                      and hit.isDescendantOf_(btn)), key
    finally:
        h.close()


def main():
    args = sys.argv[1:]
    out_json = args[args.index("--json") + 1] if "--json" in args else None
    results = []
    for fn in CASES:
        try:
            fn()
            status, detail = "pass", None
        except AssertionError as e:
            status, detail = "fail", str(e)[:400]
        except Exception as e:
            status, detail = "error", f"{type(e).__name__}: {str(e)[:360]}"
        if status != "pass" and "--trace" in args:
            traceback.print_exc()
        results.append({"case": fn.__name__, "status": status,
                         "detail": detail})
        print(f"{'ok  ' if status == 'pass' else status.upper():5}"
              f" {fn.__name__}" + (f" — {detail}" if detail else ""))
    passed = sum(r["status"] == "pass" for r in results)
    print(f"{passed}/{len(results)} passed")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps(
            {"suite": "tests/v2/transforms/"
                      "test_transform_remediation_native.py",
             "passed": passed, "total": len(results), "cases": results},
            indent=1, ensure_ascii=False))
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
