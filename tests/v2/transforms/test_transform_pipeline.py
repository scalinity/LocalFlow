"""EV-13 / EV-20 / M11: transforms through the REAL coordinator.

Drives the shared lifecycle pattern (real AppDelegate + real worker
loop) with a scripted supervisor and the instrumented fixture target:
the dictation auto-apply path (transform before insertion, Clean
artifact retained — M11-AC04), the honest opt-out (auto-apply disabled
runs Clean with the reason), uncertain coverage falling back to Clean
with the proposal recorded, selected-text execution over the real
insertion queue including the changed-selection race (M11-AC03: a
changed selection is never overwritten), the S29.10 same-task
preference invariants (M11-AC05) and the worker protocol's transform
op through the real supervisor + fake worker subprocess.

Run: .venv/bin/python tests/v2/transforms/test_transform_pipeline.py
"""

import json
import pathlib
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "insertion"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "lifecycle"))

import localflow.app as app_mod  # noqa: E402
from localflow.app import AppDelegate  # noqa: E402
from localflow.hotkey import HotkeyListener  # noqa: E402
from localflow.v2 import ids, store as store_mod  # noqa: E402
from localflow.v2.context.snapshot import (  # noqa: E402
    ContextSnapshot as CtxSnap, FieldContext, TargetSnapshot)
from localflow.v2.insertion.service import InsertionService  # noqa: E402
from fixture_target import FixtureTargetApp  # noqa: E402

CFG = {
    "model": "test", "hotkey": "fn", "sample_rate": 16000,
    "min_duration_sec": 0.3, "max_duration_sec": 0, "append_space": False,
    "restore_clipboard": False, "input_device": None, "cleanup": "llm",
    "cleanup_model": "test-llm", "log_transcripts": True,
    "capture_journal": True, "hands_free": "off", "mouse_trigger": None,
    "cleanup_not_ready_policy": "basic",
    "normalization_profile": "technical", "normalization_locale": "en-US",
    "context_enabled": False,
    "skill_manifest_paths": [], "workspace_skill_dirs": [],
    "outcome_observation_sec": 0,
}


class FakeRecorder:
    def __init__(self, durations):
        self.durations = list(durations)
        self.recording = False
        self.journal = None
        self.stats = {}

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        dur = self.durations.pop(0)
        journal, self.journal = self.journal, None
        js = journal.finalize() if journal is not None else {}
        self.stats = {
            "duration_sec": dur, "device": "fake", "voiced_pct": 50.0,
            "trailing_silence_sec": 0.0, "overflow_blocks": 0,
            "journal_dropped_blocks": js.get("queue_dropped", 0),
            "incomplete_tail": js.get("finalized") is False,
        }
        return np.zeros(int(dur * 16000), dtype=np.float32)


class FakeOverlay:
    def __init__(self):
        self.visible = False
        self.mode = None

    def showWithMode_(self, mode):
        self.visible = True
        self.mode = mode

    def setMode_(self, mode):
        self.mode = mode

    def hide(self):
        self.visible = False


class M11Supervisor:
    """Scripted worker: clean echoes the normalized text; transform is
    scriptable per call (output/path)."""

    def __init__(self, asr_text, transform_outputs=None):
        self.asr_text = asr_text
        self.transform_outputs = list(transform_outputs or
                                      [("polished output", "applied")])
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"
        self.transform_calls = []
        self.clean_calls = 0

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "decode_ranges": [[0, 16000]],
                "text": self.asr_text}

    def clean(self, *, job_id, attempt, raw_text, **kwargs):
        self.clean_calls += 1
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
                "text": raw_text, "observations": []}

    def transform(self, **payload):
        self.transform_calls.append(payload)
        output, path = self.transform_outputs.pop(0) \
            if self.transform_outputs else ("", "applied")
        src = payload.get("source") or ""
        cov = {"atoms": 0, "covered": 0, "uncertain": 0, "missing": 0}
        return {
            "attempt": payload.get("attempt", 1),
            "generation": self.generation,
            "output": output,
            "coverage": [],
            "review_excerpts": ([] if path == "applied" else [src[:30]]),
            "task_manifest": {"task_key": "ttask:fixture"},
            "result": {"path": path, "reason": None if path == "applied"
                       else "requirement_coverage_uncertain",
                       "output_tokens": 20, "limit_hit": False,
                       "duration_ms": 1.0, "coverage": cov,
                       "diff": None},
            "prompt": "<fixture transform prompt>",
        }

    def wait_engine(self, engine, timeout):
        return "ready"

    def shutdown(self, timeout=5.0):
        pass


class StubInsertionService:
    def __init__(self, delegate):
        self.d = delegate
        self.pastes = []

    def submit(self, text, job, on_done, on_observation=None):
        from localflow.v2.insertion import InsertionResult
        self.pastes.append(text)
        self.d._insertionDone_(
            InsertionResult.legacy_posted(len(text)), job)

    def note_new_dictation(self):
        pass

    def note_session_locked(self):
        pass

    def note_session_unlocked(self):
        pass

    @property
    def busy(self):
        return False

    def undo_last(self, on_done=None):
        return {"outcome": "nothing_to_undo"}

    def paste_again(self):
        return {"outcome": "nothing_to_paste"}

    def paste_text(self, text, job_id=None, on_done=None):
        return {"outcome": "nothing_to_paste"}


class FakeContextCollector:
    def __init__(self, bundle, category):
        self.bundle = bundle
        self.category = category

    def capture_identity(self):
        return TargetSnapshot(
            target_snapshot_id=ids.new_id("tgt"),
            app_bundle=self.bundle, app_name=self.bundle, app_pid=42,
            category=self.category)

    def begin(self, identity):
        return ("handle", identity)

    def abandon(self):
        pass

    def finalize(self, *, coll=None, job_id, target_snapshot_id=None):
        return CtxSnap(
            context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
            target=TargetSnapshot(
                target_snapshot_id=target_snapshot_id
                or ids.new_id("tgt"),
                app_bundle=self.bundle, app_name=self.bundle, app_pid=42,
                category=self.category),
            field=FieldContext(role="AXTextArea", classification="text"))

    def take_downstream(self, handle):
        return None


class Harness:
    def __init__(self, durations, cfg=None, supervisor=None,
                 context=None):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        app_mod.V2_DB = tmp / "v2.db"
        app_mod.V2_ARTIFACTS = tmp / "artifacts"
        app_mod.V2_BACKUPS = tmp / "backups"
        app_mod.V2_EVENTS_DIR = tmp / "events"
        app_mod.V2_JOURNAL = tmp / "journal"
        self.tmp = tmp
        merged = dict(CFG)
        merged.update(cfg or {})
        d = AppDelegate.alloc().init()
        d.configure(merged)
        d.recorder = FakeRecorder(durations)
        d.overlay = FakeOverlay()
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation,
                            d.cancelDictation)
        hk.physically_down = lambda: True
        d.hotkey = hk
        d.supervisor = supervisor
        d._insertion = StubInsertionService(d)
        if context is not None:
            d._context = context
        self.d = d
        self.hk = hk

    def close(self):
        self.d.store.sync()
        self.d.store.close()
        self.d.v2log.close()
        self._tmp.cleanup()

    def press_release(self):
        self.hk.held = True
        self.hk.on_press()
        self.hk.held = False
        self.hk.on_release()

    def run_coordinator(self, timeout=15.0):
        results = []
        real_after = app_mod.AppHelper.callAfter

        def fake_after(fn, *a):
            results.append((fn, a))

        app_mod.AppHelper.callAfter = fake_after
        try:
            t = threading.Thread(target=self.d._worker, daemon=True)
            t.start()
            deadline = time.monotonic() + timeout
            while not results and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.05)
        finally:
            app_mod.AppHelper.callAfter = real_after
        assert results, "coordinator did not finish the job"
        for fn, a in results:
            if fn == self.d._finishWithText_:
                return (fn, a)
        raise AssertionError("no finish callback captured")


def latest_envelope(store):
    row = store.latest_example()
    assert row, "no training example"
    return row[0], store.latest_revision(row[0])


def art_texts(store, job_id, role):
    def op(db):
        return [r[0] for r in db.execute(
            "SELECT content_text FROM artifacts WHERE job_id=? AND"
            " role=? AND purged=0", (job_id, role)).fetchall()]
    return store.submit(op)


def test_auto_apply_transforms_before_insertion():
    """M11-AC04: with the opt-in, the transform runs pre-insertion;
    the Clean artifact is retained beside the transform output."""
    sup = M11Supervisor("please review the parser fix",
                        transform_outputs=[("Please review the parser"
                                           " fix — polished.", "applied")])
    h = Harness([1.0], supervisor=sup,
                context=FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        # The transform output is what inserts…
        assert text == "Please review the parser fix — polished.", text
        assert sup.transform_calls and sup.transform_calls[0][
            "source_kind"] == "dictation"
        # …and the Clean intermediate is the retained cleanup artifact
        # (AC04), with the transform output in its own stage artifact.
        assert art_texts(h.d.store, job["job_id"], "applied_output") == \
            ["please review the parser fix"]
        assert "polished." in "".join(art_texts(
            h.d.store, job["job_id"], "transform_output"))
        assert job.get("transform_note") is None
        assert job["transform_result"].path == "applied"
    finally:
        h.close()
    print("ok  AC04: auto-apply transforms pre-insertion, Clean retained")


def test_auto_apply_disabled_runs_clean_with_reason():
    """M11-AC04 (opt-in): without the definition's opt-in the mode
    resolves Clean, no generation runs, the reason is recorded."""
    sup = M11Supervisor("please review the parser fix")
    h = Harness([1.0], supervisor=sup,
                context=FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d.consent.set("enabled", note="test")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "Please review the parser fix." \
            or text == "please review the parser fix", text
        assert sup.transform_calls == [], "generation ran without opt-in"
        assert job["transform_note"] == \
            "transform_auto_apply_disabled:polish"
        _ex, env = latest_envelope(h.d.store)
        assert env["missing_reasons"]["transform"] == \
            "transform_auto_apply_disabled:polish"
        assert env["profile"]["mode"] == "polish"
    finally:
        h.close()
    print("ok  AC04: opt-out runs Clean, reason in menu line + envelope")


def test_uncertain_coverage_falls_back_to_clean():
    """The stop condition: an uncertain requirement map keeps the Clean
    text and records the proposal — never silently dropped."""
    sup = M11Supervisor("fix the parser and give me two options",
                        transform_outputs=[("Fix it.", "needs_review")])
    h = Harness([1.0], supervisor=sup,
                context=FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.d.consent.set("enabled", note="test")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        # Clean inserted (normalized text), transform recorded as review.
        assert "fix the parser" in text.lower(), text
        assert job["transform_result"].path == "needs_review"
        assert job["transform_note"] == "requirement_coverage_uncertain"
        _ex, env = latest_envelope(h.d.store)
        assert env["transform"]["path"] == "needs_review"
        assert env["transform"]["applied"] is False
        # The S29.10 candidate exists; the dictation path records no
        # preference judgment (an automatic application is not one).
        task = env["transform"]["task_key"]
        cands = h.d._tf_store.candidates_for_task(task)
        assert cands, "no candidate recorded"
        assert h.d._tf_store.observations_for_task(task) == []
    finally:
        h.close()
    print("ok  uncertain coverage: Clean kept, proposal recorded")


def _fixture_service(d, target):
    rec = _Recorder()
    d._insertion = InsertionService(
        host=target, pasteboard=target.pb, keyboard=target,
        store=d.store, emit=rec, restore_clipboard=False,
        observation_window_sec=0, settle_sec=0.05)
    return d._insertion


class _Recorder:
    def __call__(self, *a, **k):
        pass


def test_selection_transform_accept_replaces_through_queue():
    """S16 selected-text execution: capture → transform → accept
    replaces the selection through the real M08 queue (revalidated)."""
    tgt = FixtureTargetApp()
    tgt.set_content("maybe rewrite this rough sentence for me")
    tgt.selection = (6, 33)
    tgt.caret = 33
    sup = M11Supervisor("", transform_outputs=[(
        "rewrite this refined sentence", "applied")])
    h = Harness([1.0], supervisor=sup)
    try:
        _fixture_service(h.d, tgt)
        capture, reason = h.d._m11_capture_selection()
        assert capture is not None, reason
        assert capture["source"] == "rewrite this rough sentence"
        defn = h.d._transforms_snapshot().by_id("builtin:polish")
        result = h.d._m11_run_transform(
            defn, capture["source"], source_kind="selection",
            selection=capture["range"])
        assert result.path == "applied"
        real_after = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        try:
            h.d.tfAcceptTransform(result, capture, "cand-1")
        finally:
            app_mod.AppHelper.callAfter = real_after
        deadline = time.monotonic() + 5
        while tgt.content == "maybe rewrite this rough sentence for me" \
                and time.monotonic() < deadline:
            time.sleep(0.02)
        assert "refined" in tgt.content, tgt.content
        assert tgt.content.startswith("maybe "), tgt.content
    finally:
        h.close()
    print("ok  selection accept: replaced through the revalidated queue")


def test_changed_selection_never_overwritten():
    """M11-AC03: the user edits the selection between capture and
    accept — revalidation fails, the result routes to the copy offer,
    the changed selection is not overwritten."""
    tgt = FixtureTargetApp()
    tgt.set_content("rewrite this rough sentence today")
    tgt.selection = (0, 27)
    tgt.caret = 27
    sup = M11Supervisor("", transform_outputs=[(
        "rewrite this refined sentence", "applied")])
    h = Harness([1.0], supervisor=sup)
    try:
        _fixture_service(h.d, tgt)
        capture, _ = h.d._m11_capture_selection()
        assert capture["source"] == "rewrite this rough sentence"
        # The user edits the field (selection gone) while the transform
        # generation runs.
        tgt.set_content("the user typed something entirely different")
        tgt.selection = (0, 0)
        tgt.caret = 55
        defn = h.d._transforms_snapshot().by_id("builtin:polish")
        result = h.d._m11_run_transform(
            defn, capture["source"], source_kind="selection",
            selection=capture["range"])
        real_after = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        try:
            h.d.tfAcceptTransform(result, capture, "cand-1")
        finally:
            app_mod.AppHelper.callAfter = real_after
        time.sleep(0.3)
        assert tgt.content == \
            "the user typed something entirely different", tgt.content
        # The honest outcome: saved, offered on the clipboard; a
        # jobless transform accept records no attribution row (the M09
        # repaste pattern) — the outcome is the event + the clipboard.
        assert tgt.pb.current_string() == "rewrite this refined sentence"

        def ins(db):
            return db.execute(
                "SELECT COUNT(*) FROM insertions").fetchone()[0]
        assert h.d.store.submit(ins) == 0
    finally:
        h.close()
    print("ok  AC03: changed selection preserved; result saved + offered")


def test_preference_same_task_invariants():
    """M11-AC05 / S29.10: same-task candidates accept explicit
    judgments; different-task candidates refuse to pair."""
    from localflow.v2 import transforms as tf
    h = Harness([1.0], supervisor=M11Supervisor("x"))
    try:
        ts = h.d._tf_store
        d = tf.TransformDefinition(transform_id="t", name="T",
                                   mode="polish")

        def result_for(source, kind="selection"):
            job = tf.job_for_definition(d, source, source_kind=kind)
            return tf.TransformResult(
                job=job, output=source + "!", path="applied")
        c1 = ts.record_candidate(result_for("same source"),
                                 source_artifact_text="same source",
                                 output_artifact_text="same source!")
        c2 = ts.record_candidate(result_for("same source"),
                                 source_artifact_text="same source",
                                 output_artifact_text="same source? "
                                 "retry")
        task = result_for("same source").job.task_key()
        obs = ts.record_observation(task_key=task, candidate_id=c1,
                                    judgment="accept")
        assert obs
        # A genuine A/B pair on the same task records with the
        # displayed order preserved.
        obs2 = ts.record_observation(task_key=task, candidate_id=c1,
                                     candidate_b_id=c2,
                                     judgment="prefer_b")
        assert obs2
        # A changed-source retry is a DIFFERENT task: pairing refuses
        # (the writer surfaces the refusal as a RuntimeError envelope).
        c3 = ts.record_candidate(result_for("changed source"))
        task3 = result_for("changed source").job.task_key()
        assert task3 != task
        try:
            ts.record_observation(task_key=task, candidate_id=c1,
                                  candidate_b_id=c3,
                                  judgment="prefer_a")
            raise AssertionError("cross-task judgment accepted")
        except RuntimeError:
            pass
        # Undo after accept is its own observation, never a rejection.
        obs3 = ts.record_observation(task_key=task, candidate_id=c1,
                                     judgment="undo")
        assert ts.observations_for_task(task)[0]["judgment"] == "accept"
        assert ts.observations_for_task(task)[-1]["judgment"] == "undo"
    finally:
        h.close()
    print("ok  AC05: same-task pairs only; undo/accept distinct")


def test_worker_transform_op_through_supervisor():
    """The real supervisor ↔ worker protocol carries the transform op
    (the fake worker script answers it; GPU serialization is the
    supervisor's existing lock)."""
    from localflow.v2.supervisor import WorkerSupervisor
    fake = pathlib.Path(__file__).resolve().parents[1] / "lifecycle" / \
        "fake_worker.py"
    with tempfile.TemporaryDirectory() as td:
        plan_path = pathlib.Path(td) / "plan.json"
        plan_path.write_text(json.dumps({
            "asr": "ready", "cleanup": "ready",
            "transform": ["ok:TRANSFORMED OUTPUT"]}))
        rec = _Recorder()
        sup = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio",
            asr_model="fake-asr", cleanup_mode="llm",
            cleanup_model="fake-llm", emit=rec,
            worker_cmd=[sys.executable, str(fake)],
            spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan_path)},
            hello_timeout=15.0, ready_timeout=30.0, request_timeout=30.0)
        try:
            sup.ensure_running()
            assert sup.wait_engine("cleanup", 15) == "ready"
            res = sup.transform(
                job_id=None, transform_id="builtin:polish",
                transform_revision=1, prompt_revision="m11:x",
                mode="polish", source="rough text",
                source_kind="selection")
            assert res["output"] == "TRANSFORMED OUTPUT", res
            assert res["result"]["path"] == "applied"
        finally:
            sup.shutdown()
    # The parent-side rebuild round-trips through the message shape.
    from localflow.v2.transforms import TransformJob
    job = TransformJob(transform_id="builtin:polish",
                       transform_revision=1, prompt_revision="m11:x",
                       mode="polish", source="rough text",
                       source_kind="selection")
    msg = {"output": "TRANSFORMED OUTPUT",
           "coverage": [], "review_excerpts": [],
           "result": {"path": "applied", "reason": None,
                      "output_tokens": 5, "limit_hit": False,
                      "duration_ms": 0.5,
                      "coverage": {"atoms": 0, "covered": 0,
                                   "uncertain": 0, "missing": 0}}}
    result = AppDelegate._m11_result_from_message(job, msg)
    assert result.path == "applied" and result.output == \
        "TRANSFORMED OUTPUT"
    assert result.job.task_key() == job.task_key()
    print("ok  worker transform op: protocol + parent rebuild")


def test_panel_constructs_and_shows():
    """Review C1 class regression: the preview panel must construct
    the way production constructs it (alloc().init_panel through
    _tfShowResult_) — a direct class call raises TypeError under
    PyObjC and would leave the entire review surface dead while the
    suites stayed green."""
    tgt = FixtureTargetApp()
    tgt.set_content("polish this sentence please")
    tgt.selection = (0, 26)
    sup = M11Supervisor("", transform_outputs=[(
        "Polish this sentence, please.", "applied")])
    h = Harness([1.0], supervisor=sup)
    try:
        _fixture_service(h.d, tgt)
        capture, reason = h.d._m11_capture_selection()
        assert capture is not None, reason
        defn = h.d._transforms_snapshot().by_id("builtin:polish")
        result = h.d._m11_run_transform(
            defn, capture["source"], source_kind="selection",
            selection=capture["range"])
        real_after = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        try:
            h.d._tfShowResult_(result, capture, defn)
        finally:
            app_mod.AppHelper.callAfter = real_after
        assert h.d._tf_panel is not None, "panel never constructed"
        st = h.d._tf_panel._state
        assert st["result"] is result and st["defn"] is defn
        assert "Polish this sentence" in h.d._tf_panel.text.string()
        assert h.d._tf_panel._buttons["panelRetry:"].isEnabled()
        # A refused job (no task) disables retry honestly.
        refused = type(result)(
            job=None, output=result.output, path="fallback_original",
            reason="transform_refused:oversized")
        h.d._tf_panel.show(refused, capture, defn, None)
        assert not h.d._tf_panel._buttons["panelRetry:"].isEnabled()
    finally:
        h.close()
    print("ok  review C1 regression: panel constructs via alloc/init")


def test_oversized_selection_refuses_without_wedging():
    """Review C2 regression: a >12k-char selection must surface the
    honest refusal AND clear ``_tf_active`` — an unguarded exception
    in the work thread would lock out every future transform."""
    tgt = FixtureTargetApp()
    tgt.set_content("word " * 4000)   # 20,000 chars > SOURCE_CHAR_LIMIT
    tgt.selection = (0, 19999)
    sup = M11Supervisor("", transform_outputs=[("never run", "applied")])
    h = Harness([1.0], supervisor=sup)
    try:
        _fixture_service(h.d, tgt)

        class Item:
            def representedObject(self):
                return "builtin:polish"

        real_after = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        try:
            h.d.runTransform_(Item())
            deadline = time.monotonic() + 5
            while h.d._tf_active is not None and time.monotonic() \
                    < deadline:
                time.sleep(0.02)
        finally:
            app_mod.AppHelper.callAfter = real_after
        assert h.d._tf_active is None, "_tf_active wedged"
        assert sup.transform_calls == [], "generation ran anyway"
        # A second run is not refused as busy — no lockout — and the
        # oversized source surfaces the honest refusal at job build.
        result = h.d._m11_run_transform(
            h.d._transforms_snapshot().by_id("builtin:polish"),
            "word " * 4000, source_kind="selection")
        assert result.path == "fallback_original"
        assert result.reason.startswith("transform_refused:"), \
            result.reason
        assert result.job is None
        assert result.to_json()["task_key"] is None
    finally:
        h.close()
    print("ok  review C2 regression: oversized selection refuses,"
          " no wedge")


def test_cleanup_off_records_gate_reason():
    """A transform-backed mode with cleanup off honestly records the
    gate reason in the envelope (never a silent Clean)."""
    sup = M11Supervisor("hello there")
    h = Harness([1.0], cfg={"cleanup": "off"}, supervisor=sup,
                context=FakeContextCollector("com.apple.mail", "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.d.consent.set("enabled", note="test")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "hello there"
        assert job.get("transform_note") == "transform_requires_cleanup"
        _ex, env = latest_envelope(h.d.store)
        assert env["missing_reasons"]["transform"] == \
            "transform_requires_cleanup"
    finally:
        h.close()
    print("ok  cleanup-off gate reason recorded in job + envelope")


if __name__ == "__main__":
    test_auto_apply_transforms_before_insertion()
    test_auto_apply_disabled_runs_clean_with_reason()
    test_uncertain_coverage_falls_back_to_clean()
    test_selection_transform_accept_replaces_through_queue()
    test_changed_selection_never_overwritten()
    test_preference_same_task_invariants()
    test_worker_transform_op_through_supervisor()
    test_panel_constructs_and_shows()
    test_oversized_selection_refuses_without_wedging()
    test_cleanup_off_records_gate_reason()
    print("all transform pipeline tests passed")
