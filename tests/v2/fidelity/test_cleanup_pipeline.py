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


def extract_transcript(prompt):
    """The transcript of the FINAL user message — the job's payload. The
    rendered prompt carries few-shot examples first, so a search for the
    first "transcript" field would answer an example instead of the job
    (audit M07-AUDIT-12)."""
    body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
    return json.loads(body)["transcript"]


def echo_engine(template_revision=None):
    """A faithful fake engine: echoes the job's transcript capitalized
    with a final period (validates)."""

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "NONE", "output_tokens": 2, "limit_hit": False,
                    "prompt": prompt}
        t = extract_transcript(prompt)
        return {"text": t[0].upper() + t[1:] + ".", "output_tokens": 6,
                "limit_hit": False, "prompt": prompt}

    return CleanupEngine(gen, model_id="fake",
                         template_revision=template_revision)


def test_echo_fake_answers_the_job_not_an_example():
    """The fake must echo the unique source canary and produce a
    genuinely accepted clean result — a fallback-rescued run does not
    establish the successful path."""
    res = echo_engine().clean("zqx canary seventeen ships")
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert res.text == "Zqx canary seventeen ships.", res.text
    dec = [o for o in res.observations if o.get("kind") == "cleanup_decision"]
    assert len(dec) == 1 and dec[0]["accepted"] is True
    main = [o for o in res.observations if o.get("kind") == "cleanup"]
    assert main[0]["input"] == "zqx canary seventeen ships"
    print("ok  echo fake answers the job's final payload (canary, path=llm,"
          " accepted)")


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
    # The literal-escape object is a protected span in normalized coords,
    # mapped through the ledger with its protection kind.
    spans = [list(s) for s in kw["protected_spans"]]
    assert spans == [[0, 5, "literal_escape"]], spans
    assert ["survo", "Servo"] in [list(p) for p in kw["vocabulary_pairs"]]
    assert kw["locale"] == "en-US"
    # Nearby text never reaches the clean op (input is the normalized
    # transcript only; no field/preceding-text strings anywhere).
    assert sup.clean_inputs == ["slash and ship the update"]
    # The happy path really ran: the literal survives with its allowed
    # sentence-initial capital and the job is llm-cleaned.
    assert text == "Slash and ship the update.", text
    assert job["cleanup_path"] == "llm", job["cleanup_path"]
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
    # A genuinely accepted clean result on the job's own source.
    assert text == "Meet me at the coffee shop no wait the library.", text
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    cleanup = env["cleanup"]
    assert cleanup["applied_path"] == "llm", cleanup["applied_path"]
    assert cleanup["decision"]["accepted"] is True
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


def test_worker_v2_engine_exception_keeps_normalized_input():
    """An engine exception mid-job answers with the unchanged normalized
    input and honest labels (never "llm"). The basic regex pass is not
    the V2 failure answer: it strips fillers inside protected literals
    (audit M07-AUDIT-08)."""
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
    assert msg["path"] == "llm_fallback_normalized"    # never "llm"
    assert msg["fallback_reason"] == "cleanup_engine_failed"
    assert msg["text"] == "um keep this text intact"   # unchanged input
    assert msg["v2"]["termination"]["kind"] == "engine_error"
    assert msg["v2"].get("error") == "RuntimeError"
    print("ok  worker v2 engine exception: unchanged normalized input,"
          " honest labels")


def _collected_job(asr_text, engine):
    """Run one job with collection on; returns (text, job, harness,
    envelope). The caller closes the harness."""
    sup = V2Supervisor(asr_text, engine)
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m07 remediation test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    return text, job, h, st.latest_revision(st.latest_example()[0])


def _manifest(st, v2):
    assert v2["decisions_retained"] is True, v2
    art = v2["decisions_artifact_id"]
    rows = st.submit(lambda db: db.execute(
        "SELECT a.retention_class, l.holder FROM artifacts a JOIN "
        "artifact_leases l ON l.artifact_id=a.artifact_id WHERE "
        "a.artifact_id=? AND l.revoked_at_utc IS NULL", (art,)).fetchall())
    assert rows == [("training", "training")], rows
    return json.loads(st.artifact_payload(art))


def test_evidence_round_trip_accept():
    """Accepted job: every pass keeps identity/range/termination/status
    in the envelope; the decision manifest artifact (lease-governed)
    holds the full validation report; the template revision is wired."""
    text, job, h, env = _collected_job(
        "zqx ship the parser fix today", echo_engine("tmpl:test123"))
    try:
        c = env["cleanup"]
        v2 = c["v2"]
        assert v2["template_revision"] == "tmpl:test123"
        assert v2["corrections_prompt_revision"].startswith("m07c:")
        assert v2["decision_schema"] == "m07-decisions-2"
        main = [p for p in c["passes"] if p["kind"] == "cleanup"]
        assert len(main) == 1 and main[0]["status"] == "selected"
        assert main[0]["pass_id"] and main[0]["window_range"] == \
            [0, len("zqx ship the parser fix today")]
        assert main[0]["limit_hit"] is False and main[0]["max_tokens"]
        assert c["decisions"][0]["status"] == "selected"
        assert env["artifact_ids"]["cleanup_proposal"] == \
            main[0]["proposal_artifact_id"]
        m = _manifest(h.d.store, v2)
        assert m["schema"] == "m07-decisions-2"
        dec = [r for r in m["records"] if r["kind"] == "cleanup_decision"]
        assert dec[0]["validation"]["components"], dec
        assert all("prompt" not in r and "output" not in r
                   for r in m["records"])
        # Envelope stays content-free.
        assert "zqx" not in json.dumps(env)
    finally:
        h.close()
    print("ok  evidence round trip (accept): pass identity, status,"
          " decision manifest, template revision")


def test_evidence_round_trip_reject_and_correction_rollback():
    """Guard-accepted correction + rejected main candidate: the
    correction is rolled back (not counted as applied), the candidate
    keeps its rejected role, no proposal is joined as the cleanup
    proposal, and the outcome stays unreviewed with no preference."""
    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "tuesday no wait", "output_tokens": 3,
                    "limit_hit": False, "prompt": prompt}
        return {"text": "We meet Wednesday.", "output_tokens": 3,
                "limit_hit": False, "prompt": prompt}

    src = "meet tuesday no wait wednesday because i travel"
    text, job, h, env = _collected_job(src, CleanupEngine(gen, "fake"))
    try:
        assert text == src, text
        c = env["cleanup"]
        v2 = c["v2"]
        assert v2["corrections"]["applied"] == 0
        assert v2["corrections"]["rolled_back"] == 1
        main = [p for p in c["passes"] if p["kind"] == "cleanup"][0]
        assert main["status"] == "rejected" and main["accepted"] is False
        assert c["decisions"][0]["status"] == "rolled_back"
        assert "coverage" in c["decisions"][0]["failed_components"] \
            or c["decisions"][0]["failed_components"], c["decisions"]
        assert env["artifact_ids"]["cleanup_proposal"] is None
        m = _manifest(h.d.store, v2)
        props = [p for r in m["records"]
                 if r["kind"] == "corrections_applied"
                 for p in r["proposals"]]
        assert [p["status"] for p in props] == ["rolled_back"], props
        assert env["outcome"]["correctness"] == "unreviewed"
        assert env["preferences"] == []
    finally:
        h.close()
    print("ok  evidence round trip (reject): correction rolled back, not"
          " applied; rejected role; unreviewed, no preference")


def test_evidence_round_trip_split_recovery():
    """Limit-hit then successful split recovery: the truncated parent
    pass, both child passes with their parent id, the child decisions
    with validation, and the retry-assembly decision all persist."""
    src = ("First half sentence goes here. " + "Filler words grow it. " * 6
           + "Second half sentence goes here. "
           + "Filler words grow it. " * 6).strip()

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "NONE", "output_tokens": 1, "limit_hit": False,
                    "prompt": prompt}
        t = extract_transcript(prompt)
        if len(t.split()) > 40:
            return {"text": "First half", "output_tokens": max_tokens,
                    "limit_hit": True, "prompt": prompt}
        return {"text": t, "output_tokens": 5, "limit_hit": False,
                "prompt": prompt}

    text, job, h, env = _collected_job(src, CleanupEngine(gen, "fake"))
    try:
        c = env["cleanup"]
        assert c["applied_path"] == "llm", (c["applied_path"],
                                            c["fallback_reason"])
        passes = [p for p in c["passes"] if p["kind"] == "cleanup"]
        parent = [p for p in passes if p["limit_hit"]]
        kids = [p for p in passes if p["parent_pass_id"]]
        assert len(parent) == 1 and parent[0]["status"] == "truncated"
        assert len(kids) == 2 and all(
            k["parent_pass_id"] == parent[0]["pass_id"]
            and k["depth"] == 1 and k["status"] == "selected"
            for k in kids), kids
        stages = [d["stage"] for d in c["decisions"]]
        assert "retry_assembly" in stages, stages
        assert len(c["v2"]["windows"][0]["children"]) == 2
        m = _manifest(h.d.store, c["v2"])
        child_dec = [r for r in m["records"]
                     if r["kind"] == "cleanup_decision"
                     and r.get("depth") == 1]
        assert len(child_dec) == 2 and all(
            r["validation"]["accepted"] for r in child_dec)
    finally:
        h.close()
    print("ok  evidence round trip (split recovery): truncated parent,"
          " child lineage and assembly decision persist")


def test_m11_transform_source_is_final_clean_artifact():
    """M11 compatibility: the transform's source is the engine's final
    Clean artifact — here the preserved source after a rejected
    candidate — never the rejected candidate."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                           / "transforms"))
    import test_transform_pipeline as tfp

    def gen(prompt, max_tokens):
        if "Find the self-corrections" in prompt:
            return {"text": "NONE", "output_tokens": 1, "limit_hit": False,
                    "prompt": prompt}
        return {"text": "Please review the parser fix and deploy it.",
                "output_tokens": 5, "limit_hit": False, "prompt": prompt}

    class Sup(tfp.M11Supervisor):
        def clean(self, *, job_id, attempt, raw_text, protected_spans=None,
                  vocabulary_pairs=None, **kw):
            self.cleaned = CleanupEngine(gen, "fake").clean(
                raw_text, protected_spans=protected_spans,
                vocabulary_pairs=tuple(tuple(p) for p in
                                       vocabulary_pairs or ()))
            meta = {k: v for k, v in self.cleaned.to_json().items()
                    if k not in ("text", "observations")}
            return {"attempt": attempt, "generation": self.generation,
                    "duration_ms": 1.0, "path": self.cleaned.path,
                    "fallback_reason": self.cleaned.fallback_reason,
                    "text": self.cleaned.text,
                    "observations": self.cleaned.observations, "v2": meta}

    sup = Sup("please review the parser fix",
              transform_outputs=[("Please review the parser fix, kindly.",
                                  "applied")])
    h = tfp.Harness([1.0], supervisor=sup,
                    context=tfp.FakeContextCollector("com.apple.mail",
                                                     "mail"))
    try:
        h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                             scope_value="email", mode="polish")
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.press_release()
        h.run_coordinator()
        assert sup.cleaned.path == "llm_fallback_normalized"
        assert sup.transform_calls, "transform did not run"
        source = sup.transform_calls[0]["source"]
        assert source == sup.cleaned.text == "please review the parser fix"
        assert "deploy" not in source
    finally:
        h.close()
    print("ok  M11 compatibility: the transform source is the final Clean"
          " artifact, never a rejected candidate")


def main():
    test_echo_fake_answers_the_job_not_an_example()
    test_permitted_context_flows_and_nearby_text_stays_out()
    test_destination_profile_from_context_snapshot()
    test_evidence_cleanup_family_v2_block()
    test_ac05_rejected_candidate_and_fallback_inspectable()
    test_ac06_validator_outcome_never_labels()
    test_v1_implementation_still_selectable()
    test_worker_v2_result_shape()
    test_worker_v2_engine_exception_keeps_normalized_input()
    test_evidence_round_trip_accept()
    test_evidence_round_trip_reject_and_correction_rollback()
    test_evidence_round_trip_split_recovery()
    test_m11_transform_source_is_final_clean_artifact()
    print("all cleanup pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
