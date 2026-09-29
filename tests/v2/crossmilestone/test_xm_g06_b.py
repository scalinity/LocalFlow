"""GATE-G06 mandatory drivers, batch B (cross-milestone remediation).

One driver per DRIVER_REQUIRED case of batch B: XM-C043 XM-C066
XM-C067 XM-C070 XM-C076 XM-R07 XM-MH18 XM-MH20 XM-R21 XM-MR19 XM-MU12.

Every driver crosses the real interface its case names — the real
coordinator ``_worker`` and EvidenceCollector (``test_lifecycle.Harness``
with the scripted-worker pattern of ``test_xm_remediation.py``), the
real Hub controller headless, the real TransformStore, LearningService,
SplitService and DatasetExporter over a temporary Store — and grades it
with an independent oracle: raw rows, exported JSONL, what the scripted
worker actually received, what the Hub shows. Orderings are decided by
latches and the writer hold of ``xm_world``, never by sleeps. Fakes:
the model worker (scripted) and the OS (run_isolated: AX, events and a
private pasteboard). Everything is synthetic.

Run (AppKit headless, desktop isolated):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_g06_b.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import one, rows  # noqa: E402

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle",
          ROOT / "tests" / "v2" / "insertion",
          ROOT / "tests" / "v2" / "transforms"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import Harness  # noqa: E402
from m09_world import Latch as ServiceLatch  # noqa: E402
from m09_world import MainQueue  # noqa: E402

import test_xm_remediation as R  # noqa: E402  (shared XM helpers)
from localflow.v2 import ids  # noqa: E402
from localflow.v2.curation import evidence as ev  # noqa: E402
from localflow.v2.history_queries import (HistoryQueryService,  # noqa: E402
                                          final_text)
from localflow.v2.supervisor import WorkerFailure  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.context import providers as _providers  # noqa: E402

# A pinned synthetic destination: the harness otherwise reads whatever real
# app is in front of the desktop, whose destination profile outranks a
# global style rule under S15 and changes the resolved mode run to run.
_providers.system_frontmost = lambda: {
    "bundle": "com.synthetic.g06", "name": "Synthetic G06", "pid": 1}

CASES = []


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# =============================================================================
# the real coordinator, scripted worker replies (the test_xm_remediation
# Scripted pattern plus the transform op)
# =============================================================================

class TScripted(R.Scripted):
    """``Scripted`` (ASR per job/attempt, cleanup that can fail, the
    exact cleanup input recorded) plus a transform op that records the
    exact payload it RECEIVED — instructions, revision, prompt revision
    — the executed-definition oracle. ``clean_reply`` replaces the
    cleanup answer; ``fail_transform`` makes chosen transform calls
    (0-based) raise a WorkerFailure."""

    def __init__(self, asr=None, fail_clean=(), clean_reply=None,
                 fail_transform=()):
        super().__init__(asr=asr, fail_clean=fail_clean)
        self.clean_reply = clean_reply
        self.fail_transform = set(fail_transform)
        self.transform_calls = []

    def clean(self, *, job_id, attempt, raw_text, **ctx):
        if self.clean_reply is None:
            return super().clean(job_id=job_id, attempt=attempt,
                                 raw_text=raw_text, **ctx)
        self.calls.append("clean")
        self.clean_inputs.append((job_id, attempt, raw_text))
        return self.clean_reply(job_id, attempt, raw_text)

    def transform(self, **payload):
        self.calls.append("transform")
        n = len(self.transform_calls)
        self.transform_calls.append(dict(payload))
        if n in self.fail_transform:
            raise WorkerFailure("scripted_transform_fault", stage="transform",
                                fatal=False, attempt=payload.get("attempt",
                                                                 1),
                                generation=1)
        src = payload.get("source") or ""
        output = f"TF<{payload.get('instructions') or payload['mode']}> {src}"
        return {
            "attempt": payload.get("attempt", 1),
            "generation": self.generation,
            "output": output, "coverage": [], "review_excerpts": [],
            "task_manifest": {"task_key": "ttask:fixture"},
            "result": {"path": "applied", "reason": None,
                       "output_tokens": 20, "limit_hit": False,
                       "duration_ms": 1.0,
                       "coverage": {"atoms": 0, "covered": 0,
                                    "uncertain": 0, "missing": 0},
                       "diff": None},
            "prompt": f"<executed prompt>\n{payload.get('instructions')}"
                      f"\n{src}",
        }


def dictate(h):
    """One capture through the REAL hotkey -> _worker -> main-thread
    finish path. Returns (job id, the text handed to insertion)."""
    h.press()
    h.release()
    job = h.d._active_jobs[-1] if h.d._active_jobs else None
    fn, a = h.run_coordinator()
    fn(*a)
    return (job or a[1])["job_id"], a[0]


def stages(detail):
    return {s["stage"]: s for s in detail["lineage"]}


def art(detail, stage):
    return stages(detail)[stage].get("artifact")


def usage_fact(store, job_id):
    return rows(store, "SELECT mode, cleanup_path, transform_id FROM"
                " usage_facts WHERE job_id=? AND kind='dictation'",
                (job_id,))


def qualification(store, ex):
    env = R.envelope(store, ex)
    return store.submit(lambda c: ev.cleanup_qualification_in(c, ex, env))


def filler_families(store, n=10):
    """``n`` producer-shaped unmarked families (the M14 world's filler
    shape: a retained raw transcript, no mark, no verbatim — never in
    any task view), so a split assignment reaches MIN_FAMILIES."""
    for i in range(n):
        job, fam = store.create_job()
        raw = store.write_text_artifact(
            job_id=job, stage="asr", role="raw_transcript",
            text=f"filler family {i} utterance", retention_class="training")
        store.grant_lease(raw, "training", days=30)
        ex = store.upsert_example(
            job_id=job, family_id=fam,
            consent_revision_id=store.current_consent_id())
        store.append_revision(ex, {
            "example_id": ex, "job_id": job, "family_id": fam,
            "origin": "live_capture", "attempt": 1,
            "artifact_ids": {"source_text": raw}, "outcome": {},
            "annotations": [], "missing_reasons": {}})


def export(h, views, dest_name):
    """Filler families, a split assignment over the live families and
    one real export through the app's DatasetExporter. Returns
    (examples.jsonl rows, manifest)."""
    filler_families(h.d.store)
    out = h.d._splits.assign()
    assert (out.get("assigned") or {}).get("unassigned", 0) == 0, (
        f"fixture: families left unassigned {out}")
    dest = h.tmp / dest_name
    h.d._exporter.build(dest, task_views=views)
    ex = [json.loads(line) for line in (dest / "examples.jsonl")
          .read_text().splitlines() if line.strip()]
    return ex, json.loads((dest / "dataset_manifest.json").read_text())


def artifact_owners(store, env):
    """{artifact id: owning job id} for every artifact id the envelope
    references anywhere (walked, not trusted by key), read from the raw
    artifacts table."""
    found = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            found.add(v)
    walk(env)
    known = {}
    for aid in found:
        row = one(store, "SELECT job_id FROM artifacts WHERE artifact_id=?",
                  (aid,))
        if row is not None:
            known[aid] = row[0]
    return known


# =============================================================================
# XM-C043 — Raw mode: exact ASR bytes, no claim that cleanup ran
# =============================================================================

RAW_ASR = "twelve percent of the orders shipped"


def _raw_route_verdict(h, sup, job, text, how):
    store = h.d.store
    assert not [1 for j, _a, _t in sup.clean_inputs if j == job], (
        f"{how}: a cleanup model ran on a Raw job: {sup.clean_inputs}")
    assert text == RAW_ASR, (
        f"{how}: Raw delivered {text!r}, not the ASR bytes {RAW_ASR!r}")
    detail = HistoryQueryService(store).job_detail(job)
    src, norm, cleaned = (art(detail, "source"), art(detail, "normalized"),
                          art(detail, "cleaned"))
    assert src and src.get("text") == RAW_ASR, f"{how}: source {src}"
    assert norm is None, f"{how}: a Raw job shows a normalized stage {norm}"
    assert cleaned is None or cleaned.get("mode") == "raw", (
        f"{how}: History presents the Raw final as a cleanup stage with"
        f" path {cleaned.get('mode')!r}")
    assert final_text(detail) == RAW_ASR, final_text(detail)
    facts = usage_fact(store, job)
    assert [(m, p) for m, p, _t in facts] == [("raw", "raw")], (
        f"{how}: usage fact {facts}")
    (ex,), = R.examples_of(store, job)
    TrainingDataService(store).mark_intended(ex, True)
    q = qualification(store, ex)
    assert not (q.get("eligible") and q.get("tier") ==
                "model_task_complete"), (
        f"{how}: a Raw job qualifies as a complete cleanup-model task {q}")
    if q.get("eligible"):
        assert q["model_inputs_missing_reason"] == \
            "no_model_pass_recorded" and q["input_text"] == RAW_ASR, q


@case("G06 XM-C043 (Raw delivers the ASR bytes; no consumer claims"
      " cleanup ran)")
def g06_xm_c043_raw_route_never_claims_cleanup():
    h = Harness(durations=[1.0] * 2)
    try:
        h.d.consent.set("enabled")
        sup = TScripted(asr=lambda j, a: RAW_ASR)
        h.d.supervisor = sup
        # (1) the one-job override (Hub "next dictation")
        assert h.d.hubSetNextJobMode("raw") == {"outcome": "set"}
        job, text = dictate(h)
        _raw_route_verdict(h, sup, job, text, "next-job Raw")
        # (2) a Raw style rule
        h.d._styles.add_rule(name="xm raw everywhere", scope_kind="global",
                             mode="raw")
        job2, text2 = dictate(h)
        _raw_route_verdict(h, sup, job2, text2, "Raw style rule")
    finally:
        h.close()


@case("G06 XM-C043 control (the same ASR in Clean runs one cleanup pass)",
      kind="control")
def g06_xm_c043_control_clean_route():
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        sup = TScripted(asr=lambda j, a: RAW_ASR)
        h.d.supervisor = sup
        job, text = dictate(h)
        store = h.d.store
        got = [t for j, _a, t in sup.clean_inputs if j == job]
        assert len(got) == 1, sup.clean_inputs
        assert text == got[0].upper(), (text, got)
        cleaned = art(HistoryQueryService(store).job_detail(job), "cleaned")
        assert cleaned and cleaned.get("mode") == "llm", cleaned
        assert [(m, p) for m, p, _t in usage_fact(store, job)] == [
            ("clean", "llm")], usage_fact(store, job)
        (ex,), = R.examples_of(store, job)
        TrainingDataService(store).mark_intended(ex, True)
        q = qualification(store, ex)
        assert q.get("eligible") and q["tier"] == "model_task_complete", q
    finally:
        h.close()


# =============================================================================
# XM-C066 — interleaved evidence of two jobs with byte-identical text
# =============================================================================

def _interleaved_pair(h, text_a, text_b):
    """Two real evidence contexts on the app's collector, callbacks
    interleaved A,B,A,B through ASR, normalization and cleanup (the
    worker binds the observation sink per job), then finalized. Returns
    ((job, example), (job, example))."""
    from localflow.v2 import normalize as v2_normalize
    store = h.d.store
    col = h.d.collector
    h.d.consent.set("enabled")
    policy = h.d._default_job_policy()
    jobs = [store.create_job() for _ in range(2)]
    ctxs = [col.job_started(j, f, captured_at_utc=ids.now_utc_iso(),
                            timezone=None, utc_offset_minutes=None)
            for j, f in jobs]
    texts = (text_a, text_b)
    for c, t in zip(ctxs, texts):
        col.on_asr_result(c, t, model_id="asr-synth", model_revision=None,
                          stage_duration_ms=1.0)
    norms = [v2_normalize.normalize(t, policy, None) for t in texts]
    for c, t, n in zip(ctxs, texts, norms):
        col.on_normalization_result(c, n, source_text=t, policy=policy)
    for c, n in zip(ctxs, norms):
        col.bind_current(c)
        col.on_cleaner_observation({
            "kind": "cleanup", "input": n.text, "system_prompt": "SYS",
            "examples_count": 0, "prompt": f"<prompt>\n{n.text}",
            "max_tokens": 64, "output": n.text.upper()})
    for c, n in zip(ctxs, norms):
        col.on_cleanup_result(c, n.text.upper(), path="llm")
    exs = [col.finalize(c) for c in ctxs]
    col.clear_current()
    store.sync()
    assert all(exs) and exs[0] != exs[1], f"fixture: examples {exs}"
    assert all(n.text != t for n, t in zip(norms, texts)), (
        "fixture: normalization changed nothing (no normalized artifact)")
    return list(zip([j for j, _f in jobs], exs))


def _ownership_verdict(h, pair):
    store = h.d.store
    seen = {}
    for job, ex in pair:
        owner = one(store, "SELECT job_id FROM training_examples WHERE"
                    " example_id=?", (ex,))[0]
        assert owner == job, (ex, owner, job)
        env = R.envelope(store, ex)
        assert env["job_id"] == job, (env["job_id"], job)
        owners = artifact_owners(store, env)
        roles = {r for (r,) in rows(store, "SELECT role FROM artifacts"
                                    " WHERE artifact_id IN (%s)" % ",".join(
                                        "?" * len(owners)), tuple(owners))}
        assert {"raw_transcript", "normalized_text", "applied_output",
                "cleanup_input_cleanup"} <= roles, f"fixture: roles {roles}"
        foreign = {a: o for a, o in owners.items() if o != job}
        assert not foreign, (
            f"job {job}'s evidence references artifacts owned by another"
            f" job: {foreign}")
        seen[job] = set(owners)
    (a, sa), (b, sb) = seen.items()
    assert not (sa & sb), f"equal-text jobs share artifacts: {sa & sb}"


@case("G06 XM-C066 (identical-text interleaved jobs keep their own"
      " artifacts)")
def g06_xm_c066_identical_text_keeps_ownership():
    h = Harness(durations=[1.0])
    try:
        same = "twelve percent of the orders shipped"
        _ownership_verdict(h, _interleaved_pair(h, same, same))
    finally:
        h.close()


@case("G06 XM-C066 control (different texts, same interleaving)",
      kind="control")
def g06_xm_c066_control_different_texts():
    h = Harness(durations=[1.0])
    try:
        _ownership_verdict(h, _interleaved_pair(
            h, "twelve percent of the orders shipped",
            "five percent of the orders returned"))
    finally:
        h.close()


# =============================================================================
# XM-C067 — a cleanup-only fault: raw traceable, reason-coded fallback
# =============================================================================

FAULT_ASR = "keep the raw source traceable here"


def _worker_engine_exception_reply(job_id, attempt, raw_text):
    """The REAL worker's answer to a cleanup engine that raises (the
    worker module's _clean with an exploding engine; only its message
    pipe is captured)."""
    import tempfile
    import localflow.v2.worker as wm

    class ExplodingEngine:
        def clean(self, raw_text, **kw):
            raise RuntimeError("synthetic engine fault")
    sent = []
    real = wm._write_msg
    wm._write_msg = sent.append
    try:
        with tempfile.TemporaryDirectory() as td:
            w = wm.Worker(td)
            w.cleanup_mode = "llm"
            w.cleanup_implementation = "v2"
            w.cleanup_engine = ExplodingEngine()
            w._clean({"req_id": "r1", "job_id": job_id, "attempt": attempt,
                      "generation": 1, "raw_text": raw_text})
    finally:
        wm._write_msg = real
    (msg,) = [m for m in sent if m.get("kind") == "clean"]
    return msg


@case("G06 XM-C067 (cleanup fault: raw traceable, reason-coded fallback,"
      " never a model output)")
def g06_xm_c067_cleanup_fault_is_reason_coded():
    h = Harness(durations=[1.0] * 2)
    try:
        h.d.consent.set("enabled")
        h.d.cfg["log_transcripts"] = True
        store = h.d.store
        # (a) the worker's engine exception -> llm_fallback_normalized
        sup = TScripted(asr=lambda j, a: FAULT_ASR,
                        clean_reply=_worker_engine_exception_reply)
        h.d.supervisor = sup
        job, text = dictate(h)
        (received,) = [t for j, _a, t in sup.clean_inputs if j == job]
        detail = HistoryQueryService(store).job_detail(job)
        src, cleaned = art(detail, "source"), art(detail, "cleaned")
        assert src and src.get("text") == FAULT_ASR, (
            f"raw source not traceable after a cleanup fault: {src}")
        assert detail.get("lineage_attempt") == 1, detail.get(
            "lineage_attempt")
        assert cleaned is None or cleaned.get("mode") != "llm", (
            "History presents the fallback as a successful model output:"
            f" path {cleaned.get('mode')!r}")
        (ex,), = R.examples_of(store, job)
        env = R.envelope(store, ex)
        cl = env.get("cleanup") or {}
        assert cl.get("applied_path") == "llm_fallback_normalized" \
            or cl.get("path") == "llm_fallback_normalized", (
            f"envelope cleanup path {cl.get('applied_path')!r}"
            f"/{cl.get('path')!r}")
        blob = json.dumps(cl)
        assert "cleanup_engine_failed" in blob, (
            f"the injected fault's reason is not recorded: {blob[:300]}")
        assert text == received, (
            f"inserted {text!r}, not the unchanged cleanup input")
        TrainingDataService(store).mark_intended(ex, True)
        q = qualification(store, ex)
        assert q.get("tier") != "model_task_complete", (
            f"a fallback answer qualifies as a complete model task: {q}")
        # (b) the supervisor's WorkerFailure in cleanup -> recoverable job
        h.d.supervisor = TScripted(asr=lambda j, a: FAULT_ASR,
                                   fail_clean={1})
        job2, _text2 = dictate(h)
        assert h.job_state(job2) == "failed_recoverable", h.job_state(job2)
        d2 = HistoryQueryService(store).job_detail(job2)
        c2 = art(d2, "cleaned")
        assert c2 is None or c2.get("mode") != "llm", (
            f"a failed cleanup shows a model output stage {c2}")
        s2 = art(d2, "source")
        assert s2 and s2.get("text") == FAULT_ASR, (
            f"raw source not traceable after a cleanup WorkerFailure: {s2}")
        exs2 = R.examples_of(store, job2)
        assert exs2, "fixture: the failed attempt left no evidence record"
        for (e2,) in exs2:
            env2 = R.envelope(store, e2)
            assert not (env2.get("artifact_ids") or {}).get(
                "applied_output"), (
                f"a failed cleanup recorded an applied output {env2}")
            src2 = (env2.get("artifact_ids") or {}).get("source_text")
            assert src2 and one(store, "SELECT content_text FROM artifacts"
                                " WHERE artifact_id=?", (src2,))[0] \
                == FAULT_ASR, "the failed attempt's raw source is lost"
            assert "scripted_cleanup_fault" in json.dumps(env2) or \
                (env2.get("outcome") or {}).get("pipeline_error"), (
                f"no failure reason recorded: {env2.get('outcome')}")
    finally:
        h.close()


@case("G06 XM-C067 control (a healthy cleanup is a cleaned stage, path"
      " llm)", kind="control")
def g06_xm_c067_control_healthy_cleanup():
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        h.d.supervisor = TScripted(asr=lambda j, a: FAULT_ASR)
        job, _text = dictate(h)
        cleaned = art(HistoryQueryService(h.d.store).job_detail(job),
                      "cleaned")
        assert cleaned and cleaned.get("mode") == "llm", cleaned
    finally:
        h.close()


# =============================================================================
# XM-C070 — collection disabled: the product works, no evidence invented
# =============================================================================

@case("G06 XM-C070 (collection off: raw/clean/transform, History and"
      " usage work; no evidence or export eligibility)")
def g06_xm_c070_collection_off_invents_nothing():
    h = Harness(durations=[1.0] * 4)
    try:
        store = h.d.store
        h.d.consent.set("disabled")
        h.d.cfg["log_transcripts"] = True
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        texts = iter(["offraw canary alpha words", "offclean canary bravo"
                      " words", "offtf canary charlie words",
                      "consented control delta words"])
        asr = {}

        def pick(j, a):
            if j not in asr:
                asr[j] = next(texts)
            return asr[j]
        sup = TScripted(asr=pick)
        h.d.supervisor = sup
        off = {}
        h.d.hubSetNextJobMode("raw")
        off["raw"] = dictate(h)
        off["clean"] = dictate(h)
        h.d.hubSetNextJobMode("polish")
        off["transform"] = dictate(h)
        assert len(sup.transform_calls) == 1, (
            f"fixture: the transform did not run {sup.transform_calls}")
        hq = HistoryQueryService(store)
        for mode, (job, text) in off.items():
            assert not R.examples_of(store, job), (
                f"collection off, yet {mode} job {job} has a training"
                " example")
            assert len(usage_fact(store, job)) == 1, (
                f"{mode}: usage facts {usage_fact(store, job)}")
            detail = hq.job_detail(job)
            assert art(detail, "source") and \
                art(detail, "source")["text"] == asr[job], (
                f"{mode}: History lost the source stage")
            assert final_text(detail) == text, (
                f"{mode}: History final {final_text(detail)!r} != inserted"
                f" {text!r}")
        tdetail = hq.job_detail(off["transform"][0])
        assert tdetail["final_stage"] == "transformed" and \
            art(tdetail, "transformed") and art(tdetail, "cleaned"), (
            "fixture: the transform job's History stages are not distinct")
        n_cand = one(store, "SELECT COUNT(*) FROM transform_candidates")[0]
        assert n_cand == 0, f"collection off recorded {n_cand} candidates"
        # Control and export: a consented job beside them exports; the
        # collection-off jobs never appear.
        h.d.consent.set("enabled")
        ok_job, _t = dictate(h)
        (ok_ex,), = R.examples_of(store, ok_job)
        TrainingDataService(store).mark_intended(ok_ex, True)
        exported, manifest = export(h, ("cleanup_supervised",), "c070")
        got = {e.get("example_id") for e in exported}
        assert ok_ex in got, (
            f"control: the consented job was not exported {got}"
            f" excluded={manifest.get('excluded')}")
        blob = json.dumps(exported) + json.dumps(manifest)
        for mode, (job, _text) in off.items():
            assert job not in blob and asr[job] not in blob, (
                f"collection-off {mode} job reached the export")
    finally:
        h.close()


# =============================================================================
# XM-C076 — the disjoint-update race, then a transform_supervised export
# =============================================================================

def _race_updates(h, t):
    """The x03 interleaving: A (rename) is held right before its
    mutation while B (new instruction) commits; then A commits."""
    store, tfs = h.d.store, h.d._tf_store
    gate = X.Latch("A_before_mutation")
    real = store.submit

    def submit(fn, wait=True, timeout=15.0):
        if threading.current_thread().name == "updater-A" \
                and "update_transform" in getattr(fn, "__qualname__", "") \
                and gate.hits == 0:
            gate.hit()
        return real(fn, wait=wait, timeout=timeout)
    store.submit = submit
    errs = []

    def updater_a():
        try:
            tfs.update_transform(t.transform_id, name="N1")
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    a = threading.Thread(target=updater_a, name="updater-A")
    try:
        a.start()
        assert gate.reached.wait(10), "fixture: A never reached its mutation"
        tfs.update_transform(t.transform_id, prompt="P1")
        gate.release()
        a.join(10)
    finally:
        gate.release()
        del store.submit
    assert not errs, errs


def _accepted_selection_export(h, t, dest):
    """Run a selection transform at the LIVE revision through the app
    (the frozen snapshot, the scripted worker, _tfShowResult_ records
    the candidate with its exact texts), accept it explicitly, export
    transform_supervised. Returns (the payload the worker received, the
    exported row, the transform_revisions row at the candidate's
    revision)."""
    store = h.d.store
    sup = TScripted(asr=lambda j, a: "family seed words for the split")
    h.d.supervisor = sup
    dictate(h)  # one consented family so a split assignment exists
    defn = h.d._transforms_snapshot().by_id(t.transform_id)
    source = "SELECTIONCANARY please restate this sentence"
    result = h.d._m11_run_transform(defn, source, source_kind="selection")
    assert result.job is not None and len(sup.transform_calls) == 1, (
        f"fixture: the transform did not run ({result.path},"
        f" {result.reason})")
    h.d._tfShowResult_(result, {"source": source}, defn)
    cands = rows(store, "SELECT candidate_id, transform_revision FROM"
                 " transform_candidates WHERE task_key=?",
                 (result.job.task_key(),))
    assert len(cands) == 1, f"fixture: candidates {cands}"
    cid, crev = cands[0]
    h.d._tf_store.record_observation(
        task_key=result.job.task_key(), candidate_id=cid,
        judgment="accept", provenance="user_action",
        source_event_id="transforms.accept")
    exported, manifest = export(h, ("transform_supervised",), dest)
    got = [e for e in exported if e.get("candidate_id") == cid]
    assert len(got) == 1, (
        f"the accepted candidate was not exported: {exported}"
        f" excluded={manifest.get('excluded')}")
    preserved = json.loads(one(store, "SELECT definition_json FROM"
                               " transform_revisions WHERE transform_id=?"
                               " AND revision=?",
                               (t.transform_id, crev))[0])
    return sup.transform_calls[0], got[0], preserved, crev


def _executed_definition_verdict(h, t, executed, row, preserved, crev):
    live = R.transform_row(h.d.store, t.transform_id)
    assert crev == live[4], f"fixture: candidate at {crev}, live {live[4]}"
    assert executed["transform_revision"] == crev, (executed, crev)
    tdef = row["transform_definition"]
    assert (tdef.get("name"), tdef.get("prompt")) == live[:2], (
        f"exported definition {(tdef.get('name'), tdef.get('prompt'))}"
        f" is not the live one {live[:2]}")
    assert tdef.get("prompt") == executed["instructions"], (
        f"exported instructions {tdef.get('prompt')!r} != executed"
        f" {executed['instructions']!r}")
    assert X.strict(tdef) == X.strict(preserved), (
        "exported definition differs from the preserved revision:"
        f" {X.strict(tdef)[:200]} vs {X.strict(preserved)[:200]}")
    assert row["transform_revision"] == crev and \
        row["prompt_revision"] == executed["prompt_revision"], (
        row["transform_revision"], row["prompt_revision"], executed)


@case("G06 XM-C076 (after the disjoint-update race the export carries the"
      " executed definition)")
def g06_xm_c076_race_then_export_carries_executed_definition():
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        t = h.d._tf_store.add_transform(name="N0", mode="custom",
                                        prompt="P0")
        _race_updates(h, t)
        assert R.transform_row(h.d.store, t.transform_id)[:2] == \
            ("N1", "P1"), "fixture: the race lost a field"
        executed, row, preserved, crev = _accepted_selection_export(
            h, t, "c076")
        _executed_definition_verdict(h, t, executed, row, preserved, crev)
    finally:
        h.close()


@case("G06 XM-C076 control (sequential updates export the same fields)",
      kind="control")
def g06_xm_c076_control_sequential_updates():
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        tfs = h.d._tf_store
        t = tfs.add_transform(name="N0", mode="custom", prompt="P0")
        tfs.update_transform(t.transform_id, name="N1")
        tfs.update_transform(t.transform_id, prompt="P1")
        executed, row, preserved, crev = _accepted_selection_export(
            h, t, "c076c")
        _executed_definition_verdict(h, t, executed, row, preserved, crev)
    finally:
        h.close()


# =============================================================================
# XM-R07 — History actions while the selected row's detail is loading
# =============================================================================

HIST_A = "ALPHAROWCANARY first history words"
HIST_B = "BRAVOROWCANARY second history words"


def _record(d, name):
    """Record every call of one coordinator entry point, then run the
    real one (the effect oracle counts calls AND reads the store and
    the private pasteboard)."""
    calls = []
    real = getattr(d, name)

    def rec(*a, **kw):
        calls.append((a, kw))
        return real(*a, **kw)
    setattr(d, name, rec)
    return calls


@case("G06 XM-R07 (an action during a row's detail load refuses visibly;"
      " never acts on A or B)")
def g06_xm_r07_history_action_during_load_refuses():
    h = Harness(durations=[1.0] * 2)
    try:
        store = h.d.store
        h.d.cfg["log_transcripts"] = True
        order = iter([HIST_A, HIST_B])
        seen = {}
        h.d.supervisor = TScripted(
            asr=lambda j, a: seen.setdefault(j, next(order)))
        ja, _ = dictate(h)
        jb, _ = dictate(h)
        with MainQueue() as mq:
            hub = R.make_hub(h)
            R.open_view(hub, mq, "history")
            hub.state.select_history_row("job", ja)
            assert mq.drain(hub.state, 60)
            shown_a = str(hub.history_detail.string())
            assert HIST_A in shown_a, "fixture: A's detail not rendered"
            effects = {n: _record(h.d, n) for n in (
                "hubCopyText", "hubPasteText", "hubRetryJob",
                "hubSaveHistoryRow")}
            board0 = R._board()
            lat = ServiceLatch(hub.state.history_service)
            hub.state.history_service = lat
            gate = lat.hold("job_detail", when=lambda jid: jid == jb,
                            after=False)
            hub.state.select_history_row("job", jb)
            assert gate.arrived.wait(10), "fixture: B's load never started"
            mq.flush()  # render whatever the interval state is
            notes = {}
            try:
                for action in ("historyCopy_", "historyPasteAgain_",
                               "historyRetry_", "historyToScratchpad_",
                               "historyMoveToScratchpad_"):
                    getattr(hub, action)(None)
                    notes[action] = str(hub.history_detail.string())
                interval = {n: list(c) for n, c in effects.items() if c}
                board1 = R._board()
                notes_rows = rows(store, "SELECT note_id FROM notes")
            finally:
                gate.release.set()
            assert mq.drain(hub.state, 60)
            assert not interval, (
                f"an action reached the coordinator while B's detail was"
                f" loading: {sorted(interval)}")
            assert board1 == board0 and not notes_rows, (
                f"an action had an effect during the load: pasteboard"
                f" {board0} -> {board1}, notes {notes_rows}")
            silent = [a for a, text in notes.items()
                      if "wait for its detail to load" not in text]
            assert not silent, (
                "no visible loading/stale refusal for: " + ", ".join(silent))
            # After release: B rendered; the same actions act on B once.
            assert HIST_B in str(hub.history_detail.string()), \
                "fixture: B never rendered"
            hub.historyCopy_(None)
            b_final = final_text(HistoryQueryService(store).job_detail(jb))
            assert [c[0][0] for c in effects["hubCopyText"]] == [b_final], \
                effects["hubCopyText"]
            assert R._board()[1] == b_final, R._board()
            hub.historyMoveToScratchpad_(None)
            store.sync()
            assert [c[0][:2] for c in effects["hubSaveHistoryRow"]] == [
                ("job", jb)], effects["hubSaveHistoryRow"]
            assert len(R.notes_with(store, b_final)) == 1
            assert HistoryQueryService(store).job_detail(ja) is not None, \
                "A was deleted"
    finally:
        h.close()


# =============================================================================
# XM-MH18 — opt-in transform: permitted final, distinct stages, export
# =============================================================================

MH18_ASR = "please summarize the quarterly numbers"


def _mh18(update_between):
    h = Harness(durations=[1.0] * 3)
    try:
        store, tfs = h.d.store, h.d._tf_store
        h.d.consent.set("enabled")
        t = tfs.add_transform(name="XM summary", mode="custom",
                              prompt="Summarize as one line (r1).",
                              auto_apply=True)
        sup = TScripted(asr=lambda j, a: MH18_ASR, fail_transform={1})
        h.d.supervisor = sup
        h.d.hubSetNextJobMode("custom")
        job, text = dictate(h)
        executed = sup.transform_calls[0]
        assert executed["instructions"] == "Summarize as one line (r1)." \
            and executed["transform_revision"] == 1, executed
        clean = MH18_ASR.upper()
        assert text.startswith("TF<") and text != clean, (
            f"the permitted transform final was not inserted: {text!r}")
        detail = HistoryQueryService(store).job_detail(job)
        c, tfa = art(detail, "cleaned"), art(detail, "transformed")
        assert c and tfa and c["artifact_id"] != tfa["artifact_id"], (
            f"cleaned and transformed stages not distinct: {c} / {tfa}")
        assert c["text"] == clean and tfa["text"] == text, (c, tfa)
        assert detail["final_stage"] == "transformed" and \
            final_text(detail) == text, detail["final_stage"]
        # A job whose transform produces no output: Clean inserts, the
        # reason is recorded, never a silent fallback.
        h.d.hubSetNextJobMode("custom")
        job2, text2 = dictate(h)
        assert len(sup.transform_calls) == 2, "fixture: no second call"
        assert text2 == clean, f"missing final inserted {text2!r}"
        (ex2,), = R.examples_of(store, job2)
        reason = (R.envelope(store, ex2).get("missing_reasons") or {}).get(
            "transform") or ""
        assert reason.startswith("transform_request_failed"), (
            f"no fallback reason for the missing transform final: {reason!r}")
        d2 = HistoryQueryService(store).job_detail(job2)
        assert d2["final_stage"] == "cleaned" and final_text(d2) == clean, \
            d2["final_stage"]
        if update_between:
            tfs.update_transform(t.transform_id,
                                 prompt="Summarize as two lines (r2).")
        # The explicit accept of job 1's candidate, then the export.
        (ex,), = R.examples_of(store, job)
        task_key = R.envelope(store, ex)["transform"]["task_key"]
        (cid,), = rows(store, "SELECT candidate_id FROM"
                       " transform_candidates WHERE task_key=?", (task_key,))
        tfs.record_observation(task_key=task_key, candidate_id=cid,
                               judgment="accept", provenance="user_action",
                               source_event_id="transforms.accept")
        exported, manifest = export(h, ("transform_supervised",), "mh18")
        got = [e for e in exported if e.get("candidate_id") == cid]
        excluded = [x for x in manifest.get("excluded") or []
                    if x.get("candidate_id") == cid]
        refs = one(store, "SELECT source_artifact_id, output_artifact_id,"
                   " task_kind FROM transform_candidates WHERE"
                   " candidate_id=?", (cid,))
        # contracts/transforms.md: the dictation path records its
        # candidate by id and hash only (no source or output artifact),
        # and no UI accepts it; the export cannot build a sourced row, so
        # the export hop holds fail-closed — never exported without its
        # source, never silently dropped: excluded with its reason.
        # (Whether dictation candidates should become exportable is an
        # open contract question, recorded with the G06 disposition.)
        assert not got and [x.get("reason") for x in excluded] == [
            "transform_transform_source_missing"], (
            f"accepted unsourced dictation candidate: exported={got},"
            f" excluded={excluded}, candidate refs={refs}")
    finally:
        h.close()


@case("G06 XM-MH18 (opt-in transform: permitted final, distinct stages; an"
      " accepted unsourced dictation candidate is disclosed, never exported"
      " without its source)")
def g06_xm_mh18_transform_mode_end_to_end():
    _mh18(update_between=True)


@case("G06 XM-MH18 control (no later update)", kind="control")
def g06_xm_mh18_control_without_update():
    _mh18(update_between=False)


# =============================================================================
# XM-MH20 / XM-MR19 — normalization retention and the cleanup task
# =============================================================================

def _cleanup_export(h, fail_role=None, raw=R.NORM_RAW, dest="mh20"):
    received, q, env = R._cleanup_record(h, fail_role=fail_role, raw=raw)
    (job,), = rows(h.d.store, "SELECT job_id FROM training_examples")
    (ex,), = R.examples_of(h.d.store, job)
    exported, manifest = export(h, ("cleanup_supervised",), dest)
    recs = [e for e in exported if e.get("example_id") == ex
            and e.get("task_kind") == "cleanup_supervised"]
    excluded = [x for x in manifest.get("excluded") or []
                if x.get("example_id") == ex]
    assert recs or excluded, (
        "fixture: the marked example never reached the cleanup view"
        f" (neither exported nor excluded): {manifest.get('counts')}")
    return received, recs, excluded, ex


@case("G06 XM-MH20 (a failed changed-normalization retention is never"
      " exported as a complete task with raw input)")
def g06_xm_mh20_failed_retention_never_exports_raw_as_input():
    h = Harness(durations=[1.0])
    try:
        received, recs, excluded, ex = _cleanup_export(
            h, fail_role="normalized_text")
        assert received != R.NORM_RAW, "fixture: nothing normalized"
        bad = [r for r in recs if r.get("input_text") == R.NORM_RAW
               and r.get("qualification_tier") == "model_task_complete"]
        assert not bad, (
            "exported a model_task_complete cleanup row whose input is the"
            f" raw text the model never received: {bad}")
        for r in recs:
            assert r.get("input_text") == received, (
                f"exported input {r.get('input_text')!r}, the model"
                f" received {received!r}")
    finally:
        h.close()


@case("G06 XM-MH20 control (retained changed normalization exports the"
      " exact input)", kind="control")
def g06_xm_mh20_control_retained_exports_exact_input():
    h = Harness(durations=[1.0])
    try:
        received, recs, excluded, ex = _cleanup_export(h, dest="mh20c")
        assert received != R.NORM_RAW, "fixture: nothing normalized"
        assert len(recs) == 1 and recs[0]["input_text"] == received and \
            recs[0]["qualification_tier"] == "model_task_complete", (
            recs, excluded)
    finally:
        h.close()


PLAIN = "plain words only here"


@case("G06 XM-MR19 (not-run and valid-unchanged normalization are the"
      " same complete task; failed changed retention is not)")
def g06_xm_mr19_normalization_provenance_relation():
    got = {}
    for arm, cfg, fail, raw in (
            ("not_run", {"normalization_profile": "off"}, None, PLAIN),
            ("valid_unchanged", None, None, PLAIN),
            ("failed_changed", None, "normalized_text", R.NORM_RAW),
            ("retained_changed", None, None, R.NORM_RAW)):
        h = Harness(durations=[1.0], cfg=cfg)
        try:
            received, q, env = R._cleanup_record(h, fail_role=fail, raw=raw)
            got[arm] = (received, q, env)
        finally:
            h.close()
    nr, vu = got["not_run"], got["valid_unchanged"]
    assert nr[0] == PLAIN and vu[0] == PLAIN, (nr[0], vu[0])
    assert not (nr[2].get("artifact_ids") or {}).get("normalization") and \
        (vu[2].get("normalization") or {}) != (nr[2].get("normalization")
                                              or {}), (
        "fixture: the two provenance arms are not distinct:"
        f" {nr[2].get('normalization')} / {vu[2].get('normalization')}")
    for arm in ("not_run", "valid_unchanged"):
        q = got[arm][1]
        assert q.get("eligible") and q["tier"] == "model_task_complete" \
            and q["input_text"] == PLAIN, f"{arm}: {q}"
    assert nr[1]["input_text"] == vu[1]["input_text"] and \
        nr[1]["tier"] == vu[1]["tier"], (nr[1], vu[1])
    fc = got["failed_changed"]
    assert fc[0] != R.NORM_RAW, "fixture: the failed arm changed nothing"
    assert not fc[1].get("eligible") and fc[1].get("reason") == \
        "normalization_input_not_retained", (
        f"failed changed retention treated as equivalent: {fc[1]}")
    rc = got["retained_changed"]
    assert rc[1].get("eligible") and rc[1]["input_text"] == rc[0] and \
        rc[0] != R.NORM_RAW, f"control: {rc[1]}"


# =============================================================================
# XM-R21 — a definition edit after the task snapshot
# =============================================================================

class HookedContext:
    """The scripted context collector (test_transform_pipeline's) with a
    hook inside finalize — the release-time seam, after the job's
    transform snapshot froze at hotkey-down."""

    def __init__(self):
        from test_transform_pipeline import FakeContextCollector
        self._inner = FakeContextCollector("com.synthetic.editor", "editor")
        self.on_finalize = None
        self.fired = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def finalize(self, **kw):
        if self.on_finalize is not None:
            hook, self.on_finalize = self.on_finalize, None
            self.fired += 1
            hook()
        return self._inner.finalize(**kw)


def _r21(edit):
    h = Harness(durations=[1.0] * 4)
    try:
        store, tfs = h.d.store, h.d._tf_store
        h.d.consent.set("enabled")
        ctx = HookedContext()
        h.d._context = ctx
        pre = "Rewrite formally (pre-edit)."
        post = "Rewrite casually (post-edit)."
        t = tfs.add_transform(name="XM rewrite", mode="custom", prompt=pre,
                              auto_apply=True)
        drafts = {}
        # A distinct draft per job: one task key per job (an identical
        # source would make every job the same transform task).
        sup = TScripted(asr=lambda j, a: drafts.setdefault(
            j, f"the draft number {len(drafts) + 1} reads fine to me"))
        h.d.supervisor = sup

        def run(hook=None):
            if hook is not None:
                ctx.on_finalize = hook
            h.d.hubSetNextJobMode("custom")
            n = len(sup.transform_calls)
            job, text = dictate(h)
            if hook is not None:
                assert ctx.fired and ctx.on_finalize is None, \
                    "fixture: the finalize seam never ran"
            return job, text, sup.transform_calls[n:]

        def cand_revision(job):
            (ex,), = R.examples_of(store, job)
            tk = R.envelope(store, ex)["transform"]["task_key"]
            return [r for (r,) in rows(store, "SELECT transform_revision"
                                       " FROM transform_candidates WHERE"
                                       " task_key=?", (tk,))]
        if not edit:
            a = run()
            b = run()
            revs = [c["transform_revision"] for c in a[2] + b[2]]
            assert revs == [1, 1], f"control: executed revisions {revs}"
            assert cand_revision(a[0]) == cand_revision(b[0]) == [1], (
                cand_revision(a[0]), cand_revision(b[0]))
            return
        # (1) prompt edited after A's snapshot
        a = run(lambda: tfs.update_transform(t.transform_id, prompt=post))
        assert len(a[2]) == 1, f"fixture: A ran {len(a[2])} transforms"
        assert a[2][0]["instructions"] == pre and \
            a[2][0]["transform_revision"] == 1, (
            f"the edit reached A's frozen task: {a[2][0]['instructions']!r}"
            f" rev {a[2][0]['transform_revision']}")
        assert cand_revision(a[0]) == [1], cand_revision(a[0])
        b = run()
        assert len(b[2]) == 1 and b[2][0]["instructions"] == post and \
            b[2][0]["transform_revision"] == 2, b[2]
        # (2) opt-out after C's snapshot: C keeps its frozen opt-in, D
        # runs no transform.
        c = run(lambda: tfs.update_transform(t.transform_id,
                                             auto_apply=False))
        assert len(c[2]) == 1 and c[2][0]["instructions"] == post and \
            c[2][0]["transform_revision"] == 2, (
            f"C lost its frozen opt-in: {c[2]}")
        d = run()
        assert d[2] == [] and d[1] == drafts[d[0]].upper(), (
            f"D (opted out) ran a transform or inserted {d[1]!r}")
        live = R.transform_row(store, t.transform_id)
        preserved = json.loads(one(store, "SELECT definition_json FROM"
                                   " transform_revisions WHERE"
                                   " transform_id=? AND revision=?",
                                   (t.transform_id, live[4]))[0])
        assert live[4] == 3 and (preserved["name"], preserved["prompt"],
                                 bool(preserved["auto_apply"]),
                                 bool(preserved["enabled"])) == (
            live[0], live[1], bool(live[2]), bool(live[3])), (
            f"new revision inconsistent: live {live} preserved {preserved}")
    finally:
        h.close()


@case("G06 XM-R21 (an edit after the task snapshot never changes the"
      " frozen prompt, definition or opt-in)")
def g06_xm_r21_edit_after_snapshot_keeps_frozen_task():
    _r21(edit=True)


@case("G06 XM-R21 control (no edit: both jobs use one revision)",
      kind="control")
def g06_xm_r21_control_no_edit():
    _r21(edit=False)


# =============================================================================
# XM-MU12 — Hub Approve: a timed-out press is unknown; the retry is one
# =============================================================================

def _teach_candidate(h):
    store = h.d.store
    h.d.consent.set("enabled")
    job, fam = store.create_job()
    raw = store.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript", text=R.TEACH_RAW,
        retention_class="training")
    applied = store.write_text_artifact(
        job_id=job, stage="cleanup", role="applied_output",
        text=R.TEACH_RAW, retention_class="training",
        parent_artifact_id=raw, meta={"cleanup_path": "model"})
    for aid in (raw, applied):
        store.grant_lease(aid, "training", days=30)
    ex = store.upsert_example(job_id=job, family_id=fam,
                              consent_revision_id=store.current_consent_id())
    store.append_revision(ex, {
        "example_id": ex, "job_id": job, "family_id": fam,
        "origin": "live_capture", "attempt": 1,
        "artifact_ids": {"source_text": raw, "applied_output": applied},
        "outcome": {}, "annotations": [], "missing_reasons": {}})
    return h.d._learning.teach_correction(job, R.TEACH_FIX)["candidate_id"]


def _mu12_run(mutant=None):
    """Press Approve in the real Hub with the approval op admitted but
    the caller timed out, let it commit, press again. ``mutant``
    installs one named mutation on the Hub instance. Returns what the
    oracle needs."""
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        cid = _teach_candidate(h)
        with MainQueue() as mq:
            hub = R.make_hub(h)
            learning = ServiceLatch(hub.spec["learning_service"])
            hub.spec["learning_service"] = learning
            if mutant == "timeout_labeled_failed":
                def training_action(fn, *a, **kw):
                    hub._last_action_unknown = False
                    try:
                        return fn(*a, **kw)
                    except Exception as e:  # noqa: BLE001
                        hub.review_text.setString_(
                            f"action failed: {type(e).__name__}: {e}")
                        return None
                hub._training_action = training_action
            elif mutant == "new_op_id_per_press":
                hub._op_id = lambda kind, key: ids.new_id("op")
            from localflow.v2.ui.state import VIEWS
            hub._select_view_index(VIEWS.index("models"))
            hub.state.select_models_subview("training")
            assert mq.drain(hub.state, 60)
            hub.state.select_training_tab("review")
            assert mq.drain(hub.state, 60)
            popup = hub.review_candidate_popup
            idx = next(i for i in range(popup.numberOfItems())
                       if popup.itemAtIndex_(i).representedObject() == cid)
            popup.selectItemAtIndex_(idx)
            with X.hold_at(store, "approve") as held:
                hub.reviewApprove_(None)
                reached = held.reached
                first = str(hub.review_text.string())
            store.sync()
            committed = one(store, "SELECT status FROM learning_candidates"
                            " WHERE candidate_id=?", (cid,))[0]
            mq.drain(hub.state, 60)
            # The unknown outcome leaves the choice in place; the user
            # presses Approve again.
            if popup.selectedItem() is None or \
                    popup.selectedItem().representedObject() != cid:
                idx = next(i for i in range(popup.numberOfItems())
                           if popup.itemAtIndex_(i).representedObject()
                           == cid)
                popup.selectItemAtIndex_(idx)
            hub.reviewApprove_(None)
            second = str(hub.review_text.string())
            mq.drain(hub.state, 60)
        ops = [c[2].get("operation_id") for c in learning.calls
               if c[0] == "approve"]
        return {
            "reached": reached, "committed": committed, "first": first,
            "second": second, "ops": ops,
            "receipts": one(store, "SELECT COUNT(*) FROM"
                            " m14_operation_receipts WHERE kind='approve'"
                            " AND target_id=?", (cid,))[0],
            "deltas": one(store, "SELECT COUNT(*) FROM"
                          " learning_vocabulary_deltas WHERE"
                          " candidate_id=?", (cid,))[0],
            "entries": one(store, "SELECT COUNT(*) FROM vocabulary_entries"
                           " WHERE canonical='module'")[0],
        }
    finally:
        h.close()


def _mu12_verdict(o):
    assert o["reached"] and o["committed"] == "approved", (
        f"fixture: approval admitted={o['reached']} status={o['committed']}")
    assert len(o["ops"]) == 2, f"fixture: approve calls {o['ops']}"
    assert "unknown" in o["first"] and "failed" not in o["first"], (
        f"a timed-out approval was not shown as unknown: {o['first'][:160]!r}")
    assert o["ops"][0] == o["ops"][1], (
        f"the retry minted a new operation id: {o['ops']}")
    low = o["second"].lower()
    assert "failed" not in low and "refused" not in low, (
        f"the reconciling retry reported a failure: {o['second'][:160]!r}")
    assert (o["receipts"], o["deltas"], o["entries"]) == (1, 1, 1), (
        f"one logical approval made receipts={o['receipts']}"
        f" deltas={o['deltas']} entries={o['entries']}")


@case("G06 XM-MU12 (a timed-out Hub Approve is unknown; the retry reuses"
      " its operation id: one effect)")
def g06_xm_mu12_approve_unknown_then_retry_is_one():
    _mu12_verdict(_mu12_run())


@case("G06 XM-MU12 control (the driver kills both named mutants)",
      kind="control")
def g06_xm_mu12_control_mutants_are_killed():
    for mutant in ("timeout_labeled_failed", "new_op_id_per_press"):
        o = _mu12_run(mutant)
        assert o["reached"] and o["committed"] == "approved", (
            f"{mutant}: fixture did not reach the seam {o}")
        try:
            _mu12_verdict(o)
        except AssertionError:
            continue
        raise AssertionError(f"mutant {mutant} survived the driver: {o}")


@case("G06 XM-MU12 control (an unheld Approve succeeds once)",
      kind="control")
def g06_xm_mu12_control_unheld_approve():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        cid = _teach_candidate(h)
        with MainQueue() as mq:
            hub = R.make_hub(h)
            from localflow.v2.ui.state import VIEWS
            hub._select_view_index(VIEWS.index("models"))
            hub.state.select_models_subview("training")
            assert mq.drain(hub.state, 60)
            hub.state.select_training_tab("review")
            assert mq.drain(hub.state, 60)
            popup = hub.review_candidate_popup
            idx = next(i for i in range(popup.numberOfItems())
                       if popup.itemAtIndex_(i).representedObject() == cid)
            popup.selectItemAtIndex_(idx)
            hub.reviewApprove_(None)
            mq.drain(hub.state, 60)
        assert one(store, "SELECT status FROM learning_candidates WHERE"
                   " candidate_id=?", (cid,))[0] == "approved"
        assert one(store, "SELECT COUNT(*) FROM m14_operation_receipts"
                   " WHERE target_id=?", (cid,))[0] == 1
    finally:
        h.close()


# =============================================================================
# runner (the test_xm_remediation runner, same record shape)
# =============================================================================

redact = R.redact


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
    print("xm g06 batch B:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_g06_b.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_g06_b.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
