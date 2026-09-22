"""EV-06 / M04: app-level normalization integration.

Drives the REAL coordinator thread (the stuck-overlay Harness pattern)
with a scripted supervisor: normalization runs between ASR and cleanup
in the parent process, the job passes through the `normalizing` state,
cleanup receives the normalized text, training evidence carries the
normalization field family with a replayable ledger artifact, and a
normalization failure passes the raw transcript through.

Run: .venv/bin/python tests/v2/normalization/test_normalization_pipeline.py
"""

import json
import pathlib
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

import localflow.app as app_mod  # noqa: E402
from localflow.app import AppDelegate  # noqa: E402
from localflow.hotkey import HotkeyListener  # noqa: E402
from localflow.v2 import ids, store as store_mod  # noqa: E402

CFG = {
    "model": "test", "hotkey": "fn", "sample_rate": 16000,
    "min_duration_sec": 0.3, "max_duration_sec": 0, "append_space": False,
    "restore_clipboard": False, "input_device": None, "cleanup": "llm",
    "cleanup_model": "test-llm", "log_transcripts": False,
    "capture_journal": True, "hands_free": "off", "mouse_trigger": None,
    "cleanup_not_ready_policy": "basic",
    "normalization_profile": "technical", "normalization_locale": "en-US",
}


class FakeRecorder:
    def __init__(self, durations):
        self.durations = list(durations)
        self.recording = False
        self.journal = None
        self.stats = {}
        self.health = {"ok": True}

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

    def capture_health(self):
        return dict(self.health)


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


class RecordingSupervisor:
    """Fake worker that records what the coordinator hands it."""

    def __init__(self, asr_text, cleaner=None):
        self.asr_text = asr_text
        self.cleaner = cleaner or (lambda t: t)
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"
        self.calls = []
        self.clean_inputs = []

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        self.calls.append("transcribe")
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "decode_ranges": [[0, 16000]],
                "text": self.asr_text}

    def clean(self, *, job_id, attempt, raw_text, **_m07_context):
        # M07: the coordinator passes permitted-context fields; the fake
        # ignores them.
        self.calls.append("clean")
        self.clean_inputs.append(raw_text)
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
                "text": self.cleaner(raw_text), "observations": []}

    def wait_engine(self, engine, timeout):
        return "ready"

    def shutdown(self, timeout=5.0):
        pass


class Harness:
    def __init__(self, durations, cfg=None, supervisor=None):
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
        self.d = d
        self.hk = hk
        self.phys = True

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


def test_coordinator_normalizes_between_asr_and_cleanup():
    """S06 pipeline order: ASR (worker) → normalization (parent) →
    cleanup (worker). Cleanup must receive the normalized text."""
    sup = RecordingSupervisor(
        "the timeout is thirty seconds and twelve percent")
    h = Harness([1.0], supervisor=sup)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert sup.calls == ["transcribe", "clean"], sup.calls
    assert sup.clean_inputs == [
        "the timeout is 30 seconds and 12%"], sup.clean_inputs
    h.close()
    print("ok  coordinator: ASR → normalize (parent) → clean "
          "with normalized text")


def test_job_state_sequence_includes_normalizing():
    sup = RecordingSupervisor("twelve retries failed")
    h = Harness([1.0], supervisor=sup)
    seen = []

    def spy(job_id, state, reason=None, retry=False):
        seen.append(state)
        return None

    real = h.d._job_state
    h.d._job_state = spy
    try:
        h.press_release()
        fn, args = h.run_coordinator()
    finally:
        h.d._job_state = real
    assert "normalizing" in seen, seen
    assert seen.index("transcribing") < seen.index("normalizing") < \
        seen.index("cleaning"), seen
    h.close()
    print(f"ok  job states: transcribing → normalizing → cleaning ({seen})")


def test_cleanup_off_uses_normalized_text():
    sup = RecordingSupervisor("twelve percent of the cache")
    h = Harness([1.0], cfg={"cleanup": "off"}, supervisor=sup)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "12% of the cache", text
    h.d._finishWithText_(text, job)
    h.close()
    print("ok  cleanup off: normalized text is the applied output")


def test_off_profile_skips_stage():
    sup = RecordingSupervisor("twelve percent stays words")
    h = Harness([1.0], cfg={"normalization_profile": "off"},
                supervisor=sup)
    h.press_release()
    seen = []

    def spy(job_id, state, reason=None, retry=False):
        seen.append(state)

    real = h.d._job_state
    h.d._job_state = spy
    try:
        fn, args = h.run_coordinator()
    finally:
        h.d._job_state = real
    text, job = args
    assert text == "twelve percent stays words"
    assert "normalizing" not in seen, seen
    h.close()
    print("ok  off profile: stage skipped honestly")


def test_normalization_failure_passes_raw_through():
    import localflow.v2.normalize as norm_mod
    sup = RecordingSupervisor("twelve percent")

    def boom(text, policy, context=None):
        raise RuntimeError("synthetic parser failure")

    real_normalize = norm_mod.normalize
    norm_mod.normalize = boom
    try:
        h = Harness([1.0], supervisor=sup)
        h.press_release()
        fn, args = h.run_coordinator()
        text, job = args
        assert text == "twelve percent", text
        assert sup.clean_inputs == ["twelve percent"], sup.clean_inputs
        h.close()
    finally:
        norm_mod.normalize = real_normalize
    print("ok  parser exception: raw transcript passes through")


def test_evidence_envelope_and_ledger_replay():
    """S29.4/M04-AC05: with collection enabled the envelope carries the
    normalization family; the ledger artifact replays against the raw
    transcript artifact to reproduce the normalized text."""
    sup = RecordingSupervisor(
        "set the retry count to twelve retries and twelve percent")
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m04 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    ex = st.latest_example()
    assert ex, "example was collected"
    env = st.latest_revision(ex[0])
    norm = env["normalization"]
    assert norm is not None, env.get("missing_reasons")
    assert "normalization" not in env["missing_reasons"]
    assert norm["edits_count"] == 2, norm
    assert norm["number_word_to_digit_count"] == 2
    assert norm["idempotent"] is True
    assert norm["policy_revision"].startswith("m04:")
    ledger_art = norm["artifact_ids"]["ledger"]
    raw_art = env["artifact_ids"]["source_text"]
    from localflow.v2.normalize.span_types import EditRecord
    ledger = json.loads(st.artifact_payload(ledger_art))
    raw = st.artifact_payload(raw_art)
    out = raw
    for e in sorted((EditRecord.from_json(d) for d in ledger["edits"]),
                    key=lambda e: e.input_span.start, reverse=True):
        out = out[:e.input_span.start] + e.output_text + \
            out[e.input_span.end:]
    assert out == text, (out, text)
    # Envelope hygiene: no transcript strings inside the envelope's
    # per-edit entries.
    for e in norm["edits"]:
        assert set(e) <= {"cls", "op", "input_span", "output_span",
                          "value", "unit", "layer", "reason"}, e
    assert st.verify()["ok"]
    h.close()
    print("ok  evidence: normalization family + replayable ledger artifact")


def test_evidence_without_normalization_keeps_missing_reason():
    """The M02 collector path (no normalization stage run) still reports
    the honest not_captured_at_stage reason."""
    import tempfile as _tf
    from localflow.v2 import training
    with _tf.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        rec = _Rec()
        consent = training.ConsentManager(st, rec)
        collector = training.EvidenceCollector(st, rec, consent,
                                               lambda: {"live": "x"})
        consent.set("enabled")
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(), timezone=None,
            utc_offset_minutes=None)
        collector.on_asr_result(ctx, "twelve percent", model_id="m",
                                model_revision=None, stage_duration_ms=0.0)
        collector.on_cleanup_result(ctx, "twelve percent")
        ex = collector.finalize(ctx)
        env = st.latest_revision(ex)
        assert env["normalization"] is None
        assert env["missing_reasons"]["normalization"] == \
            "not_captured_at_stage"
        st.close()
    print("ok  M02 path unchanged: honest not_captured_at_stage")


class _Rec:
    def __call__(self, *a, **k):
        pass


def main():
    test_coordinator_normalizes_between_asr_and_cleanup()
    test_job_state_sequence_includes_normalizing()
    test_cleanup_off_uses_normalized_text()
    test_off_profile_skips_stage()
    test_normalization_failure_passes_raw_through()
    test_evidence_envelope_and_ledger_replay()
    test_evidence_without_normalization_keeps_missing_reason()
    print("all normalization pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
