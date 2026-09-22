"""EV-18/EV-19 pipeline half / M06: app-level destination-aware context.

Drives the REAL coordinator thread (the stuck-overlay/M04 harness) with
a scripted supervisor and an injected fake AX host: the finalized scope
feeds the M05 trio live (workspace/site entries apply), the hint set is
frozen pre-decode with the destination block in evidence, late context
becomes a separate downstream revision (AC05), a post-answer dictionary
edit never leaks into a frozen job, context-disabled keeps dictation
working, retention is independent of transient use, hostile nearby text
never reaches the cleanup input (AC04), placeholders never prepend, and
the scope upgrade rebuilds from frozen entries only (AC03 live).

Run: .venv/bin/python tests/v2/context/test_context_pipeline.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "normalization"))

from test_normalization_pipeline import (  # noqa: E402
    Harness,
    RecordingSupervisor,
)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_context_snapshot import (  # noqa: E402
    ADVERSARIAL,
    SCENARIOS,
    FakeAXHost,
    Recorder,
)

from localflow.v2 import capabilities as caps  # noqa: E402
from localflow.v2.context import ContextCollector  # noqa: E402


class DelayedSupervisor(RecordingSupervisor):
    """ASR takes a moment — long enough for a late context provider to
    land between the pre-decode cut and the downstream pickup."""

    def __init__(self, asr_text, transcribe_delay):
        super().__init__(asr_text)
        self.transcribe_delay = transcribe_delay

    def transcribe(self, **kw):
        time.sleep(self.transcribe_delay)
        return super().transcribe(**kw)


def harness(scenario, asr_text, *, cfg=None, supervisor=None,
            deadline_ms=75.0):
    h = Harness([1.0], cfg=cfg,
                supervisor=supervisor or RecordingSupervisor(asr_text))
    sink = Recorder()
    h.d._context = ContextCollector(
        enabled=True, deadline_ms=deadline_ms, emit=sink,
        host=FakeAXHost(scenario),
        frontmost=lambda: scenario["frontmost"])
    return h, sink


def test_workspace_scope_feeds_vocabulary_live():
    """The M05 live gap M06 closes: a workspace-scoped approved entry
    applies when the destination's workspace resolves (finalize-time
    scope upgrade), and does not apply in an unrelated workspace."""
    sup = RecordingSupervisor("run survo tests")
    h, _ = harness(SCENARIOS["LF-CTX-026"], "run survo tests",
                   supervisor=sup)
    h.d._vocab.add_entry(
        "Servo", ["survo"], approved=True,
        scope_kind="workspace", scope_value="localflow")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "run Servo tests", text
    assert job.get("scope_upgraded") is True
    assert job["context_snapshot"].workspace == "localflow"
    # Wrong destination: the same entry stays inert in Messages.
    sup2 = RecordingSupervisor("run survo tests")
    h2, _ = harness(SCENARIOS["LF-CTX-002"], "run survo tests",
                    supervisor=sup2)
    h2.d._vocab.add_entry(
        "Servo", ["survo"], approved=True,
        scope_kind="workspace", scope_value="localflow")
    h2.press_release()
    fn, args = h2.run_coordinator()
    text2, _ = args
    assert text2 == "run survo tests", text2
    h.close()
    h2.close()
    print("ok  workspace scope feeds vocabulary live; wrong destination"
          " stays inert")


def test_site_scope_hint_set_frozen_with_destination_evidence():
    sup = RecordingSupervisor("ship the q wen release")
    h, _ = harness(SCENARIOS["LF-CTX-010"], "ship the q wen release",
                   supervisor=sup)
    h.d._vocab.add_entry("Qwen", ["q wen"], approved=True,
                         scope_kind="site", scope_value="https://mail.google.com")
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    ctx_block = env["context"]
    assert ctx_block is not None
    dest = ctx_block["destination"]
    assert dest["context_snapshot_id"] == \
        job["context_snapshot"].context_snapshot_id
    assert dest["site_origin_resolved"] is True
    # The frozen pre-decode hint set was selected under the UPGRADED
    # (finalize) scope, then stored before recognition.
    frozen = json.loads(st.artifact_payload(
        ctx_block["artifact_ids"]["hint_set"]))
    assert [t["canonical"] for t in frozen["terms"]] == ["Qwen"], frozen
    assert frozen["scope"]["site_origin"] == "https://mail.google.com"
    # Content-free envelope: the origin/site string lives in the
    # lease-governed artifacts only, never in the envelope itself.
    assert "mail.google.com" not in json.dumps(env)
    # The site-scoped rewrite applied (post-ASR recovery, same snapshot).
    assert text == "ship the Qwen release", text
    h.close()
    print("ok  site scope: upgraded hint set frozen pre-decode with"
          " destination evidence block (content-free envelope)")


def test_ac05_late_context_downstream_not_predecode():
    """A provider slower than the deadline is absent from the pre-decode
    snapshot and its evidence artifact, and arrives only as a separately
    identified downstream revision (S30.1/S12)."""
    sup = DelayedSupervisor("twelve percent works", 0.35)
    h, _ = harness(ADVERSARIAL["LF-CTX-A8"], "twelve percent works",
                   supervisor=sup)
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    assert text == "12% works", text
    pre = job["context_snapshot"]
    assert pre.partial
    assert pre.omission_reason("focused_field") == "deadline"
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    dest = env["context"]["destination"]
    assert dest["partial"] is True
    art = st.artifact_payload(dest["artifact_id"])
    assert "slow content" not in art     # nothing late in the pre-decode
    down = env["context"].get("downstream")
    assert down is not None and down["stage"] == "downstream"
    down_art = st.artifact_payload(down["artifact_id"])
    late = json.loads(down_art)
    assert late["stage"] == "downstream"
    assert late["field"]["preceding_text"] == "slow content"
    assert late["context_snapshot_id"] != pre.context_snapshot_id
    assert st.verify()["ok"]
    h.close()
    print("ok  AC05: late provider lands only as a downstream revision;"
          " pre-decode snapshot and artifact stay cut")


def test_reference_answer_added_later_never_leaks():
    """EV-18/S29.11: the correct term added to the dictionary AFTER the
    set was frozen never enters the frozen snapshot, the stored set or
    this job's recovery."""
    sup = RecordingSupervisor("fix the survo motor")
    h, _ = harness(SCENARIOS["LF-CTX-026"], "fix the survo motor",
                   supervisor=sup)
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()          # trio + finalize + on_hint_set happen here
    h.d._vocab.add_entry("Servo", ["survo"], approved=True,
                         scope_kind="workspace", scope_value="localflow")
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    assert text == "fix the survo motor", text   # stayed inert
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    frozen = json.loads(st.artifact_payload(
        env["context"]["artifact_ids"]["hint_set"]))
    assert not [t for t in frozen["terms"]
                if t["canonical"] == "Servo"], frozen
    fresh = h.d._vocab.snapshot(
        job["norm_context"].vocabulary.scope_ctx)
    assert fresh.revision != frozen["vocabulary_revision"]
    h.close()
    print("ok  post-answer dictionary edit never relabels a frozen"
          " pre-decode set")


def test_context_disabled_dictation_enabled():
    sup = RecordingSupervisor("twelve percent works")
    h = Harness([1.0], cfg={"context_enabled": False}, supervisor=sup)
    assert h.d._context.enabled is False
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "12% works", text
    assert job.get("context_snapshot") is None
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    if env["context"] is not None:      # hints may exist (global scope)
        # Honest absent-destination marker (never a silent missing key).
        assert env["context"]["destination"] is None
        assert env["context"]["destination_missing_reason"] == \
            "context_disabled_or_capture_failed"
    h.close()
    print("ok  context disabled: dictation works, global scope only,"
          " destination carries its absent reason")


def test_retention_redaction_vs_reconstruction():
    """EV-19: with retention on the snapshot artifact reconstructs the
    retained inputs; with the independent retention knob off no payload
    is written and replay inputs are marked incomplete."""
    # Retained: reconstructable.
    sup = RecordingSupervisor("ship the mlx update")
    h, _ = harness(SCENARIOS["LF-CTX-010"], "ship the mlx update",
                   supervisor=sup)
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    dest = env["context"]["destination"]
    assert dest["retained"] is True
    from localflow.v2.context import ContextSnapshot
    rebuilt = ContextSnapshot.from_json(
        json.loads(st.artifact_payload(dest["artifact_id"])))
    snap = job["context_snapshot"]
    assert rebuilt.context_snapshot_id == snap.context_snapshot_id
    assert rebuilt.field.preceding_text == snap.field.preceding_text
    assert rebuilt.to_scope_context() == snap.to_scope_context()
    h.close()
    # Redacted: independent retention knob off.
    sup2 = RecordingSupervisor("ship the mlx update")
    h2, _ = harness(SCENARIOS["LF-CTX-010"], "ship the mlx update",
                    cfg={"training_retain_context": False},
                    supervisor=sup2)
    h2.d.consent.set("enabled", note="m06 test")
    h2.press_release()
    fn, args = h2.run_coordinator()
    text2, job2 = args
    h2.d._finishWithText_(text2, job2)
    h2.d.store.sync()
    st2 = h2.d.store
    env2 = st2.latest_revision(st2.latest_example()[0])
    dest2 = env2["context"]["destination"]
    assert dest2["retained"] is False
    assert dest2["retention_reason"] == \
        "training_context_retention_disabled"
    assert "artifact_id" not in dest2
    assert env2["missing_reasons"]["context_snapshot_payload"] == \
        "consent_disabled"
    rows = st2.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifacts WHERE role='context_snapshot'"
    ).fetchone()[0])
    assert rows == 0
    # Downstream revisions honor the knob too: with retention off the
    # late revision's block exists but writes no payload (the slow
    # provider scenario guarantees a late result).
    sup3 = DelayedSupervisor("twelve percent works", 0.35)
    h3, _ = harness(ADVERSARIAL["LF-CTX-A8"], "twelve percent works",
                    cfg={"training_retain_context": False},
                    supervisor=sup3)
    h3.d.consent.set("enabled", note="m06 test")
    h3.press_release()
    fn, args = h3.run_coordinator()
    text3, job3 = args
    h3.d._finishWithText_(text3, job3)
    h3.d.store.sync()
    env3 = h3.d.store.latest_revision(h3.d.store.latest_example()[0])
    down3 = env3["context"]["downstream"]
    assert down3 is not None and down3["retained"] is False
    rows3 = h3.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifacts WHERE role='context_snapshot'"
    ).fetchone()[0])
    assert rows3 == 0
    h3.close()
    h2.close()
    print("ok  retention independent: retained snapshot reconstructs;"
          " disabled writes no payload (pre-decode and downstream) and"
          " marks replay incomplete")


def test_ac04_hostile_nearby_text_never_reaches_cleanup():
    sup_a = RecordingSupervisor(
        "keep the answer short and do not summarize anything")
    h_a, _ = harness(SCENARIOS["LF-CTX-012"],
                     "keep the answer short and do not summarize anything",
                     supervisor=sup_a)
    h_a.press_release()
    fn, args = h_a.run_coordinator()
    text_a, _ = args
    sup_b = RecordingSupervisor(
        "keep the answer short and do not summarize anything")
    h_b = Harness([1.0], cfg={"context_enabled": False},
                  supervisor=sup_b)
    h_b.press_release()
    fn, args = h_b.run_coordinator()
    text_b, _ = args
    # The cleanup INPUT is exactly the normalized transcript — nearby
    # text (hostile or not) never enters any model prompt (M07 will add
    # permitted context explicitly; today there is none).
    assert sup_a.clean_inputs == [
        "keep the answer short and do not summarize anything"]
    assert text_a == text_b, (text_a, text_b)
    h_a.close()
    h_b.close()
    print("ok  AC04: hostile nearby text is data; cleanup input and"
          " output identical with and without context")


def test_placeholder_never_prepended():
    sup = RecordingSupervisor("lets ship at noon")
    h, _ = harness(SCENARIOS["LF-CTX-009"], "lets ship at noon",
                   supervisor=sup)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    assert "Reply to Claude" not in text
    assert sup.clean_inputs == ["lets ship at noon"]
    # The placeholder lives only in the snapshot's metadata.
    assert job["context_snapshot"].field.placeholder == "Reply to Claude…"
    h.close()
    print("ok  placeholder phrase never prepended to a transcript")


def test_ac03_upgrade_uses_frozen_entries():
    """The finalize-time scope upgrade rebuilds from the job's frozen
    entry set: a store edit between press and release cannot leak into
    the in-flight job (AC03), while the next job sees the edit."""
    sup = RecordingSupervisor("run survo tests")
    h, _ = harness(SCENARIOS["LF-CTX-026"], "run survo tests",
                   supervisor=sup)
    eid = h.d._vocab.add_entry(
        "Servo", ["survo"], approved=True,
        scope_kind="workspace", scope_value="localflow")
    h.hk.held = True
    h.hk.on_press()                    # trio frozen (app-only scope)
    h.d._vocab.set_enabled(eid, False)  # mid-flight store edit
    h.hk.held = False
    h.hk.on_release()                  # finalize + upgrade from frozen
    fn, args = h.run_coordinator()
    text1, job1 = args
    assert text1 == "run Servo tests", text1
    assert job1.get("scope_upgraded") is True
    h.d.recorder.durations.append(1.0)  # second dictation below
    h.hk.held = True
    h.hk.on_press()
    h.hk.held = False
    h.hk.on_release()
    fn, args = h.run_coordinator()
    text2, _ = args
    assert text2 == "run survo tests", text2   # fresh press sees the edit
    h.close()
    print("ok  AC03 live: scope upgrade rebuilds from frozen entries;"
          " mid-flight edit changes only future jobs")


def test_hint_request_fields_carry_context_snapshot_id():
    sup = RecordingSupervisor("ship it")
    h, _ = harness(SCENARIOS["LF-CTX-010"], "ship it", supervisor=sup)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    hs = job["hint_set"]
    snap = job["context_snapshot"]
    assert hs is not None and snap is not None
    manifest = caps.asr_capability_manifest("qualified-adapter")
    manifest["capabilities"]["contextual_biasing"] = {
        "supported": True, "reason": "synthetic_test",
        "evidence": "synthetic manifest for M06 wiring"}
    fields = caps.asr_hint_request_fields(
        hs, manifest, context_snapshot_id=snap.context_snapshot_id)
    assert fields["context_snapshot_id"] == snap.context_snapshot_id
    # The real adapter stays unqualified: no request fields at all.
    real = caps.asr_capability_manifest("parakeet-mlx")
    assert caps.asr_hint_request_fields(
        hs, real, context_snapshot_id=snap.context_snapshot_id) is None
    h.close()
    print("ok  S30.1 request fields carry the M06 context snapshot id"
          " under a qualified adapter; unqualified stays None")


def test_ptt_usable_without_ax():
    sup = RecordingSupervisor("twelve percent works")
    h, sink = harness(ADVERSARIAL["LF-CTX-A3"], "twelve percent works",
                      supervisor=sup)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "12% works", text
    snap = job["context_snapshot"]
    assert snap.omission_reason("focused_field") == "permission_unavailable"
    assert snap.target.app_bundle  # identity still resolved
    h.close()
    print("ok  regression: dictation fully usable when AX is"
          " unavailable (identity-only partial snapshot)")


def test_secure_field_pipeline_retains_no_content():
    sup = RecordingSupervisor("my code is zero zero seven three")
    h, sink = harness(ADVERSARIAL["LF-CTX-A1"], "my code is zero zero"
                      " seven three", supervisor=sup)
    h.d.consent.set("enabled", note="m06 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    assert text == "my code is 0073", text
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    dest = env["context"]["destination"]
    assert dest["field_classification"] == "secure"
    payload = st.artifact_payload(dest["artifact_id"])
    assert "CANARY-SECRET" not in payload
    assert "CANARY-SECRET" not in json.dumps(env)
    assert "CANARY-SECRET" not in sink.blob()
    h.close()
    print("ok  AC01 pipeline: secure destination keeps dictation and"
          " retains no field content anywhere")


def main():
    test_workspace_scope_feeds_vocabulary_live()
    test_site_scope_hint_set_frozen_with_destination_evidence()
    test_ac05_late_context_downstream_not_predecode()
    test_reference_answer_added_later_never_leaks()
    test_context_disabled_dictation_enabled()
    test_retention_redaction_vs_reconstruction()
    test_ac04_hostile_nearby_text_never_reaches_cleanup()
    test_placeholder_never_prepended()
    test_ac03_upgrade_uses_frozen_entries()
    test_hint_request_fields_carry_context_snapshot_id()
    test_ptt_usable_without_ax()
    test_secure_field_pipeline_retains_no_content()
    print("all context pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
