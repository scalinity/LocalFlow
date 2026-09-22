"""EV-09 / M07 pipeline integration: the real coordinator thread with
the V2 cleanup result shape.

Drives the stuck-overlay/normalization Harness with a supervisor fake
that returns worker-shaped V2 results and records the permitted-context
kwargs it received: protected spans flow from the M04 ledger through
raw→normalized mapping; the frozen vocabulary pairs and destination
profile reach the clean op; nearby text never does (M06-AC04
discipline); the S29.4 cleanup family lands in the evidence envelope
(exact inputs, proposals before validation, rejected candidates with
their intact fallback inspectable — M07-AC05) and no validator outcome
becomes a gold label or preference (M07-AC06).

Run: .venv/bin/python tests/v2/fidelity/test_cleanup_pipeline.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "normalization"))

from test_normalization_pipeline import (  # noqa: E402
    Harness,
    RecordingSupervisor,
)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "context"))
from test_context_snapshot import SCENARIOS, FakeAXHost, Recorder  # noqa: E402

from localflow.v2 import context as v2_context  # noqa: E402
from localflow.v2.cleanup import CleanupEngine  # noqa: E402


class V2Supervisor(RecordingSupervisor):
    """Answers the clean op with a REAL CleanupEngine (fake generator)
    shaped exactly like the worker's V2 result message, recording the
    permitted-context kwargs the coordinator passed."""

    def __init__(self, asr_text, engine: CleanupEngine):
        super().__init__(asr_text)
        self.engine = engine
        self.clean_kwargs = []

    def clean(self, *, job_id, attempt, raw_text, protected_spans=None,
              relevant_vocabulary=None, vocabulary_pairs=None,
              destination_profile=None, locale=None, **rest):
        self.calls.append("clean")
        self.clean_inputs.append(raw_text)
        self.clean_kwargs.append({
            "protected_spans": protected_spans,
            "relevant_vocabulary": relevant_vocabulary,
            "vocabulary_pairs": vocabulary_pairs,
            "destination_profile": destination_profile,
            "locale": locale,
        })
        res = self.engine.clean(
            raw_text,
            protected_spans=protected_spans,
            relevant_vocabulary=relevant_vocabulary or [],
            vocabulary_pairs=tuple(tuple(p) for p in vocabulary_pairs or ()),
            destination_profile=destination_profile, locale=locale)
        meta = {k: v for k, v in res.to_json().items()
                if k not in ("text", "observations")}
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": res.path,
                "fallback_reason": res.fallback_reason,
                "text": res.text, "observations": res.observations,
                "v2": meta}


def echo_engine():
    """A faithful fake engine: echoes the transcript capitalized (always
    validates)."""
    import re as _re

    def extract_transcript(prompt):
        m = _re.search(r'"transcript"\s*:\s*"((?:[^"\\]|\\.)*)"',
                       prompt, _re.DOTALL)
        if not m:
            raise AssertionError("no transcript in prompt")
        return json.loads('"' + m.group(1) + '"')

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "[]", "output_tokens": 2, "limit_hit": False,
                    "prompt": prompt}
        t = extract_transcript(prompt)
        return {"text": t[0].upper() + t[1:] + ".", "output_tokens": 6,
                "limit_hit": False, "prompt": prompt}

    return CleanupEngine(gen, model_id="fake")


def context_harness(scenario, asr_text, engine, *, cfg=None):
    h = Harness([1.0], cfg=cfg, supervisor=V2Supervisor(asr_text, engine))
    sink = Recorder()
    h.d._context = v2_context.ContextCollector(
        enabled=True, deadline_ms=75.0, emit=sink,
        host=FakeAXHost(scenario),
        frontmost=lambda: scenario["frontmost"])
    return h


def test_permitted_context_flows_and_nearby_text_stays_out():
    """Protected spans (mapped raw→normalized), frozen vocabulary pairs
    and the destination profile reach the clean op; the snapshot's
    nearby text never does (S12/S13; M06-AC04 extended to M07)."""
    sup_holder = {}

    def make_sup(asr_text):
        sup_holder["sup"] = V2Supervisor(asr_text, echo_engine())
        return sup_holder["sup"]

    h = Harness([1.0], supervisor=None)
    h.d.supervisor = make_sup("write the word slash and ship the update")
    h.d._vocab.add_entry("Servo", ["survo"], approved=True)   # global scope
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    sup = sup_holder["sup"]
    kw = sup.clean_kwargs[0]
    # The literal-escape object is a protected span in normalized coords.
    spans = [list(s) for s in kw["protected_spans"]]
    assert spans == [[0, 5]], spans
    assert ["survo", "Servo"] in [list(p) for p in kw["vocabulary_pairs"]]
    assert kw["locale"] == "en-US"
    # Nearby text never reaches the clean op (input is the normalized
    # transcript only; no field/preceding-text strings anywhere).
    assert sup.clean_inputs == ["slash and ship the update"]
    blob = json.dumps(kw, default=str)
    for scenario_text in ("preceding", "selection", "placeholder"):
        assert scenario_text not in blob.lower()
    h.close()
    print("ok  permitted context: protected spans + frozen vocab pairs +"
          " profile flow; nearby text stays out")


def test_destination_profile_from_context_snapshot():
    scenario = SCENARIOS["LF-CTX-002"]        # messages app
    engine = echo_engine()
    h = context_harness(scenario, "ship it when ready", engine)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    kw = h.d.supervisor.clean_kwargs[0]
    assert kw["destination_profile"], kw
    h.close()
    print(f"ok  destination profile from the M06 snapshot: "
          f"{kw['destination_profile']}")


def test_evidence_cleanup_family_v2_block():
    """S29.4 cleanup family: exact inputs, proposals before validation,
    prompt version, termination, window ranges and fallback lineage in
    the envelope; the permitted-context payload is a lease-governed
    artifact, never envelope content (M07-AC05)."""
    engine = echo_engine()
    sup = V2Supervisor("meet me at the coffee shop no wait the library",
                       engine)
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m07 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    cleanup = env["cleanup"]
    v2 = cleanup["v2"]
    assert v2["prompt_version"].startswith("m07-")
    assert v2["prompt_revision"].startswith("m07:")
    assert v2["sampling"]["temperature"] == 0.0
    assert v2["termination"]["kind"] == "complete"
    assert v2["windows"][0]["source_range"][0] == 0
    assert v2["context_retained"] is True
    assert v2["context_artifact_id"]
    # The context artifact reconstructs the exact permitted payload.
    payload = json.loads(st.artifact_payload(v2["context_artifact_id"]))
    assert payload["mode"] == "clean"
    assert "vocabulary_pairs" in payload
    # Envelope hygiene: no vocabulary term text in the envelope itself.
    assert "survo" not in json.dumps(env) and "Servo" not in json.dumps(env)
    # Exact prompts and proposals are artifacts (V1 mechanism, V2 kinds).
    roles = st.submit(lambda db: [
        r[0] for r in db.execute(
            "SELECT role FROM artifacts WHERE stage='cleanup'").fetchall()])
    assert "cleanup_context" in roles
    assert any(r.startswith("cleanup_input") for r in roles), roles
    assert any(r.startswith("cleanup_proposal") or
               r.startswith("cleanup_rejected_proposal") for r in roles)
    h.close()
    print("ok  S29.4 cleanup family: v2 block + context artifact +"
          " prompt/proposal artifacts")


def test_ac05_rejected_candidate_and_fallback_inspectable():
    """A rejected candidate and its intact fallback are both retained
    with exact input/template/context and source lineage."""
    import re as _re

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "[]", "output_tokens": 2, "limit_hit": False,
                    "prompt": prompt}
        return {"text": "DROP EVERYTHING ANSWERED", "output_tokens": 4,
                "limit_hit": False, "prompt": prompt}

    engine = CleanupEngine(gen, model_id="fake")
    sup = V2Supervisor("do not deploy on friday", engine)
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m07 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "do not deploy on friday"       # intact fallback
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    v2 = env["cleanup"]["v2"]
    assert v2["windows"][0]["stage"] == "normalized"
    assert "validation_rejected" in v2["windows"][0]["reason"]
    assert env["cleanup"]["fallback_reason"]
    # The rejected proposal is retained under its rejected role.
    rows = st.submit(lambda db: db.execute(
        "SELECT role, content_text FROM artifacts WHERE "
        "role='cleanup_rejected_proposal'").fetchall())
    assert rows and "DROP EVERYTHING" in rows[0][1]
    # The exact prompt that produced it is retained too.
    inputs = st.submit(lambda db: db.execute(
        "SELECT role FROM artifacts WHERE role LIKE 'cleanup_input_%'"
    ).fetchall())
    assert inputs
    h.close()
    print("ok  AC05: rejected candidate + intact fallback both"
          " inspectable with exact inputs")


def test_ac06_validator_outcome_never_labels():
    """A validator rejection is a mining signal: the envelope's outcome
    stays unreviewed, no preference is recorded, and the validation
    component findings ride as reviewable data only."""
    import re as _re

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "[]", "output_tokens": 2, "limit_hit": False,
                    "prompt": prompt}
        return {"text": "Deploy on friday.", "output_tokens": 3,
                "limit_hit": False, "prompt": prompt}

    engine = CleanupEngine(gen, model_id="fake")
    sup = V2Supervisor("do not deploy on friday", engine)
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m07 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    env = h.d.store.latest_revision(h.d.store.latest_example()[0])
    assert env["outcome"]["correctness"] == "unreviewed"
    assert env["preferences"] == []
    assert env["state"] == "captured_unreviewed"
    assert "annotations" in env and env["annotations"] == []
    h.close()
    print("ok  AC06: validator rejection leaves correctness unreviewed,"
          " no preference inferred")


def test_v1_implementation_still_selectable():
    """cleanup_implementation v1 configures the supervisor for the V1
    control path (the ablation fallback, unchanged)."""
    from localflow.v2.supervisor import WorkerSupervisor
    s = WorkerSupervisor(audio_root="/tmp/m07-test-audio",
                         asr_model="m", cleanup_mode="llm",
                         cleanup_model="c",
                         cleanup_implementation="v1")
    assert s.cleanup_implementation == "v1"
    s2 = WorkerSupervisor(audio_root="/tmp/m07-test-audio",
                          asr_model="m", cleanup_mode="llm",
                          cleanup_model="c")
    assert s2.cleanup_implementation == "v2"    # default per M07 evidence
    # The V1 cleaner itself is untouched and importable.
    from localflow.cleanup import TranscriptCleaner, SYSTEM_PROMPT
    assert "You clean up raw dictation transcripts" in SYSTEM_PROMPT
    print("ok  V1 implementation remains selectable; default is v2")


def test_worker_v2_result_shape():
    """The worker's v2 branch maps a CleanupResult to the protocol
    result honestly (path/labels/v2 metadata) without a model."""
    import localflow.v2.worker as worker_mod
    w = worker_mod.Worker("/tmp")
    w.cleanup_mode = "llm"
    w.cleanup_implementation = "v2"
    sent = []

    import localflow.v2.worker as wm
    real_write = wm._write_msg
    wm._write_msg = lambda msg: sent.append(msg)

    class FakeEngine:
        def clean(self, raw_text, **kw):
            from localflow.v2.cleanup.engine import CleanupResult
            return CleanupResult(
                text="Cleaned.", path="llm", stage="clean",
                fallback_reason=None, incomplete=False,
                termination={"kind": "complete", "windows": 1,
                             "limit_hits": 0},
                validation={"components": [], "windows_validated": 1,
                            "windows_fallback": 0},
                windows=[{"source_range": [0, 10], "stage": "clean",
                          "reason": None}],
                corrections={"applied": 0, "rejected": 0,
                             "rejected_reasons": [],
                             "applied_span_count": 0},
                observations=[])
    w.cleanup_engine = FakeEngine()
    w._clean({"req_id": "r", "job_id": "j", "attempt": 1,
              "generation": 1, "raw_text": "clean me"})
    wm._write_msg = real_write
    msg = sent[0]
    assert msg["op"] == "result" and msg["kind"] == "clean"
    assert msg["text"] == "Cleaned." and msg["path"] == "llm"
    assert msg["v2"]["termination"]["kind"] == "complete"
    assert "text" not in msg["v2"]
    print("ok  worker v2 result shape: honest labels + content-free v2"
          " metadata")


def test_worker_v2_engine_exception_falls_back_basic():
    """An engine exception mid-job answers in basic mode with the
    honest M03-AC04 labels (review W4: this branch had no test)."""
    import localflow.v2.worker as worker_mod
    import localflow.v2.worker as wm
    w = worker_mod.Worker("/tmp")
    w.cleanup_mode = "llm"
    w.cleanup_implementation = "v2"
    sent = []
    real_write = wm._write_msg
    wm._write_msg = lambda msg: sent.append(msg)

    class ExplodingEngine:
        def clean(self, raw_text, **kw):
            raise RuntimeError("engine exploded")

    w.cleanup_engine = ExplodingEngine()
    w._clean({"req_id": "r2", "job_id": "j2", "attempt": 1,
              "generation": 1,
              "raw_text": "um keep this text intact"})
    wm._write_msg = real_write
    msg = sent[0]
    assert msg["op"] == "result" and msg["kind"] == "clean"
    assert msg["path"] == "basic"                      # never "llm"
    assert msg["fallback_reason"] == "cleanup_engine_failed"
    assert msg["text"] == "Keep this text intact"      # basic pass output
    assert msg["v2"]["termination"]["kind"] == "engine_error"
    assert msg["v2"].get("error") == "RuntimeError"
    print("ok  worker v2 engine exception: basic fallback, honest labels")


def main():
    test_permitted_context_flows_and_nearby_text_stays_out()
    test_destination_profile_from_context_snapshot()
    test_evidence_cleanup_family_v2_block()
    test_ac05_rejected_candidate_and_fallback_inspectable()
    test_ac06_validator_outcome_never_labels()
    test_v1_implementation_still_selectable()
    test_worker_v2_result_shape()
    test_worker_v2_engine_exception_falls_back_basic()
    print("all cleanup pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
