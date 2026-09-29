"""GATE-G06 mandatory drivers, batch D (cross-milestone cases XM-C137,
XM-C144, XM-C145, XM-MH01/XM-C146, XM-MH05, XM-C154, XM-MH10, XM-MH12).

Each driver crosses the real producer and consumer its case names — the
real coordinator ``_worker``/``hubRetryJob`` (``test_lifecycle.Harness``,
scripted worker replies only), the real Hub controller headless, the
real Scratchpad editor (``m12_world.HubWorld``), the real M14 services
over the synthetic ``MWorld`` store — and grades it with an independent
oracle: literal values the witness chose, raw rows, file bytes, what the
Hub rendered. Ordering is decided by latches and events, never sleeps.

A defect-shaped driver asserts the CORRECT invariant; when production
violates it the driver FAILS (a reproduced defect) — nothing here works
around it. Every such driver carries a positive control (in the same def
or a paired ``kind="control"`` case).

Run (AppKit headless, desktop isolated — a private pasteboard):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_g06_d.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
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
          ROOT / "tests" / "v2" / "insertion", ROOT / "tests" / "v2" / "notes"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import FakeSupervisor, Harness  # noqa: E402
from m09_world import MainQueue  # noqa: E402

from localflow.v2.curation import classify  # noqa: E402
from localflow.v2.curation import evidence as ev  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402
from localflow.v2.history_queries import (HistoryQueryService,  # noqa: E402
                                          final_text)
from localflow.v2.profile import ProfileService  # noqa: E402
from localflow.v2.supervisor import WorkerFailure  # noqa: E402

M = X.M
CASES = []

VIEWS = ("asr_supervised", "asr_span_graft_weak", "cleanup_supervised",
         "transform_supervised", "preference_pairs")
# Export exclusion reason prefix -> the task view it belongs to
# (curation/export.py _asr_rows/_cleanup_rows/_transform_rows/
# _preference_rows); reasons without one are selection-level.
REASON_VIEW = (("asr_gate_", "asr_supervised"),
               ("graft_", "asr_span_graft_weak"),
               ("cleanup_", "cleanup_supervised"),
               ("transform_", "transform_supervised"),
               ("preference_", "preference_pairs"))


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# =============================================================================
# the real coordinator, scripted worker replies (copied from
# test_xm_remediation.py so the runner shape and seams are identical)
# =============================================================================

class Scripted(FakeSupervisor):
    """A worker whose ASR text is chosen per (job, attempt) and whose
    cleanup can fail after ASR for chosen attempts. Records the exact
    text cleanup RECEIVED (the independent input oracle)."""

    def __init__(self, asr=None, fail_clean=()):
        super().__init__()
        self.asr = asr or (lambda job_id, attempt: f"raw {attempt}")
        self.fail_clean = set(fail_clean)
        self.clean_inputs = []

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        out = super().transcribe(job_id=job_id, attempt=attempt,
                                 audio_name=audio_name,
                                 sample_rate=sample_rate)
        out["text"] = self.asr(job_id, attempt)
        return out

    def clean(self, *, job_id, attempt, raw_text, **ctx):
        self.calls.append("clean")
        self.clean_inputs.append((job_id, attempt, raw_text))
        if attempt in self.fail_clean:
            raise WorkerFailure("scripted_cleanup_fault", stage="clean",
                                fatal=False, attempt=attempt, generation=1)
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
                "text": raw_text.upper(),
                "observations": [{"kind": "cleanup", "input": raw_text,
                                  "system_prompt": "SYS",
                                  "examples_count": 0,
                                  "prompt": f"<prompt {job_id}>\n{raw_text}",
                                  "max_tokens": 64,
                                  "output": raw_text.upper()}]}


def dictate(h):
    """One capture through the REAL hotkey -> _worker -> main-thread
    finish path. Returns the job id."""
    h.press()
    h.release()
    job = h.d._active_jobs[-1] if h.d._active_jobs else None
    fn, a = h.run_coordinator()
    fn(*a)
    return (job or a[1])["job_id"]


def examples_of(store, job_id):
    return rows(store, "SELECT example_id FROM training_examples WHERE"
                " job_id=? ORDER BY rowid", (job_id,))


def envelope(store, example_id):
    return json.loads(one(store, "SELECT r.envelope_json FROM"
                          " training_examples e JOIN training_revisions r"
                          " ON r.revision_id=e.latest_revision_id WHERE"
                          " e.example_id=?", (example_id,))[0])


def rewrite_envelope(store, example_id, mutate):
    """Append a revision whose envelope is ``mutate(env)`` — the
    corruption changes exactly one field (m14_world.rewrite_envelope)."""
    env = envelope(store, example_id)
    parent = env.get("revision_id")
    mutate(env)
    env["revision_id"] = None
    return store.append_revision(example_id, env, parent)


def attempt_final(sup, job, attempt):
    """The final the scripted cleanup produced for (job, attempt): the
    upper-cased text it RECEIVED (normalization ran before it)."""
    got = [t for j, a, t in sup.clean_inputs if j == job and a == attempt]
    assert len(got) == 1, sup.clean_inputs
    return got[0].upper()


def make_hub(h):
    from localflow.v2.training_data import TrainingDataService as TDS
    from localflow.v2.ui import HubController, ReplayService
    d = h.d
    return HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TDS(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d, "replay": ReplayService(
            sound_factory=lambda b: None),
        "capabilities": d._capability_manifest,
        "styles_service": d._styles, "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
        "insights_service": d._insights,
        "learning_service": d._learning, "review_service": d._review,
        "sampling_service": d._sampling, "splits_service": d._splits,
        "profile_service": d._profile, "export_service": d._exporter,
        "transforms_store": d._tf_store})


def open_view(hub, mq, view):
    from localflow.v2.ui.state import VIEWS as HUB_VIEWS
    hub._select_view_index(HUB_VIEWS.index(view))
    hub.state.select_view(view)
    assert mq.drain(hub.state, 60)


def latest_snapshot(store):
    return one(store, "SELECT snapshot_id, state, measured_json,"
               " cards_json FROM profile_snapshots ORDER BY rowid DESC"
               " LIMIT 1")


def evidence_of(store, snapshot_id, role="measured"):
    return {x for (x,) in rows(
        store, "SELECT example_id FROM profile_evidence WHERE"
        " snapshot_id=? AND role=? AND included=1", (snapshot_id, role))}


# =============================================================================
# XM-C137 — a same-job wrong-role artifact is never History's final text
# =============================================================================

C137_A = "swap alpha holds twenty five apples"
C137_B = "twin bravo holds thirty six pears"


@case("G06 XM-C137 (a same-job wrong-role artifact never qualifies and is"
      " never served as History's final text)")
def g06_xm_c137_wrong_role_never_history_final():
    h = Harness(durations=[1.0] * 2)
    try:
        h.d.consent.set("enabled")
        queue = [C137_A, C137_B]
        sup = Scripted(asr=lambda j, a: queue.pop(0))
        h.d.supervisor = sup
        job_a = dictate(h)
        job_b = dictate(h)
        store = h.d.store
        hist = HistoryQueryService(store)
        (ex_a,), = examples_of(store, job_a)
        env_a = envelope(store, ex_a)
        norm_id = ((env_a.get("normalization") or {}).get("artifact_ids")
                   or {}).get("normalized_text")
        assert norm_id, f"fixture: no normalized_text artifact {env_a}"
        row = one(store, "SELECT job_id, role, purged, content_text FROM"
                  " artifacts WHERE artifact_id=?", (norm_id,))
        assert row and row[0] == job_a and row[1] == "normalized_text" \
            and not row[2] and row[3], f"fixture: normalized row {row}"
        norm_text = row[3]
        final_a = attempt_final(sup, job_a, 1)
        assert norm_text != final_a, "fixture: stages not distinguishable"
        before = hist.job_detail(job_a)
        assert before.get("lineage_source") == "manifest" and \
            final_text(before) == final_a, (
                "fixture: unswapped History final",
                before.get("lineage_source"), final_text(before))
        # The LF-M14-C060 swap: the manifest's applied_output names the
        # job's OWN normalized_text artifact (right job, wrong role).
        rewrite_envelope(store, ex_a, lambda env: env["artifact_ids"]
                         .__setitem__("applied_output", norm_id))
        assert envelope(store, ex_a)["artifact_ids"]["applied_output"] \
            == norm_id, "fixture: the swap did not land"
        # Raw SQL: the artifact is live and keeps its own role.
        row2 = one(store, "SELECT role, purged, job_id FROM artifacts"
                   " WHERE artifact_id=?", (norm_id,))
        assert row2 == ("normalized_text", 0, job_a), row2
        # Qualification leg: the role refusal names the role.
        q = store.submit(lambda c: ev.qualify(c, norm_id, "applied_output",
                                              job_id=job_a))
        assert not q["ok"] and "role" in q["reason"], (
            f"qualify admitted a wrong-role applied_output: {q}")
        # Control: the unswapped twin serves its own applied output.
        detail_b = hist.job_detail(job_b)
        assert final_text(detail_b) == attempt_final(sup, job_b, 1), (
            "control: twin final", final_text(detail_b))
        # History leg.
        detail = hist.job_detail(job_a)
        assert detail.get("lineage_source") == "manifest", \
            f"fixture: lineage {detail.get('lineage_source')}"
        shown = final_text(detail)
        cleaned = next(s for s in detail["lineage"]
                       if s["stage"] == "cleaned")
        served = (cleaned.get("artifact") or {}).get("artifact_id")
        assert shown != norm_text and served != norm_id and shown is None, (
            "History served the job's own normalized_text artifact as the"
            f" final text: final_text={shown!r} (normalized stage text"
            f" {norm_text!r}); cleaned stage artifact={served} is the"
            " normalized_text id; HistoryQueryService._job_artifacts'"
            " manifest branch never checks the named artifact's role")
    finally:
        h.close()


# =============================================================================
# XM-C144 — readiness vs export exclusion-reason parity, five views
# =============================================================================

GRAFT_RAW = "send the cloud report on friday"
GRAFT_FIX = "send the Claude report on friday"


def _graft(w, raw, fix):
    """A job whose reviewed recognition span is grafted (weak view) —
    the M14 corpus fixture (m14_drivers_e._graft)."""
    j = w.job(raw)
    spans = classify.changed_regions(raw, fix)
    kw = {}
    if M.accepts(w.review.record_label, "expected_source_artifact_id"):
        kw = {"expected_source_artifact_id": j["raw_aid"],
              "expected_source_sha256": M.ids.sha256_text(raw)}
    w.review.record_label(j["example_id"], edit_kind="recognition_error",
                          origin_stages=("asr",),
                          confirmed_spans=[spans[0]], **kw)
    row = w.one("SELECT graft_artifact_id FROM correction_labels WHERE"
                " example_id=? AND graft_artifact_id IS NOT NULL ORDER BY"
                " revision DESC LIMIT 1", (j["example_id"],))
    assert row and row[0], "fixture: no graft artifact"
    j["graft_aid"] = row[0]
    return j


def _c144_world(w, restricted):
    """One witness per view (and, when ``restricted``, one restricted
    variant per view) under ONE assignment. Returns the INDEPENDENT
    expected table: per view, eligible keys and excluded keys."""
    exp = {v: {"eligible": set(), "excluded": set()} for v in VIEWS}
    exp["selection_excluded"] = set()
    exp["tiers"] = {"model_task_complete": 0, "text_pair_only": 0}
    asr = [w.ready_asr() for _ in range(10)]
    exp["asr_supervised"]["eligible"] |= {j["example_id"] for j in asr}
    g = _graft(w, GRAFT_RAW, GRAFT_FIX)
    exp["asr_span_graft_weak"]["eligible"].add(g["example_id"])
    full = w.ready_cleanup(f"cleanup full words {M.A_CANARY}")
    bare = w.ready_cleanup("cleanup bare words", prompts=0)
    exp["cleanup_supervised"]["eligible"] |= {full["example_id"],
                                              bare["example_id"]}
    exp["tiers"] = {"model_task_complete": 1, "text_pair_only": 1}
    t = w.transform_task(f"transform source {M.A_CANARY}",
                         [f"Transform A {M.A_CANARY}.",
                          f"Transform B {M.B_CANARY}."])
    w.accept(t, t["candidates"][0]["candidate_id"])
    exp["transform_supervised"]["eligible"].add(
        t["candidates"][0]["candidate_id"])
    p = w.transform_task(f"pref source {M.B_CANARY}",
                         ["Pref output one.", "Pref output two."])
    w.judge(p, p["candidates"][0]["candidate_id"],
            p["candidates"][1]["candidate_id"], "prefer_b")
    exp["preference_pairs"]["eligible"].add(p["task_key"])
    act = []
    if restricted:
        # ASR: purged original audio.
        a_bad = w.ready_asr("asr purged audio witness")
        exp["asr_supervised"]["excluded"].add(a_bad["example_id"])
        act.append(lambda: w.purge(a_bad["audio_aid"]))
        # Graft: the label's graft names the job's own raw transcript
        # (right job, wrong role).
        g_bad = _graft(w, "send the cloud memo on monday",
                       "send the Claude memo on monday")
        exp["asr_span_graft_weak"]["excluded"].add(g_bad["example_id"])
        act.append(lambda: w.store.submit(lambda c: c.execute(
            "UPDATE correction_labels SET graft_artifact_id=? WHERE"
            " graft_artifact_id=?", (g_bad["raw_aid"], g_bad["graft_aid"]))))
        # Cleanup: an excluded example (state) and a wrong-role applied
        # output (the C060 swap onto the job's own normalized_text).
        c_ex = w.ready_cleanup("cleanup excluded state words")
        exp["selection_excluded"].add(c_ex["example_id"])
        act.append(lambda: w.training.exclude(c_ex["example_id"], True))
        c_sw = w.ready_cleanup("cleanup swapped role words",
                               normalized="cleanup swapped-role words")
        exp["cleanup_supervised"]["excluded"].add(c_sw["example_id"])
        act.append(lambda: w.rewrite_envelope(
            c_sw["example_id"], lambda env: env["artifact_ids"]
            .__setitem__("applied_output", c_sw["norm_aid"])))
        # Transform: an accepted candidate whose output was purged.
        t2 = w.transform_task("transform purged source",
                              ["Transform purged output."])
        w.accept(t2, t2["candidates"][0]["candidate_id"])
        exp["transform_supervised"]["excluded"].add(
            t2["candidates"][0]["candidate_id"])
        act.append(lambda: w.purge(t2["candidates"][0]["output_aid"]))
        # Preference: a tie is a comparable judgment (evidence.COMPARABLE)
        # and exports with no winner; a pair whose output was purged is
        # excluded.
        tie = w.transform_task("tie pair source",
                               ["Tie left.", "Tie right."])
        w.judge(tie, tie["candidates"][0]["candidate_id"],
                tie["candidates"][1]["candidate_id"], "tie")
        exp["preference_pairs"]["eligible"].add(tie["task_key"])
        p_bad = w.transform_task("purged pair source",
                                 ["Purged left.", "Purged right."])
        w.judge(p_bad, p_bad["candidates"][0]["candidate_id"],
                p_bad["candidates"][1]["candidate_id"], "prefer_a")
        exp["preference_pairs"]["excluded"].add(p_bad["task_key"])
        act.append(lambda: w.purge(p_bad["candidates"][1]["output_aid"]))
    w.splits.assign()  # every example is a member: ONE selection
    for fn in act:
        fn()
    return exp


def _key(rec, view):
    if view in ("transform_supervised",):
        return rec.get("candidate_id")
    if view == "preference_pairs":
        return rec.get("task_key")
    return rec.get("example_id")


def _c144_compare(w, exp):
    """Returns (mismatches, observed). Readiness and the export are read
    over the same store state and the same (latest, only) assignment."""
    out = w.exporter.build(w.tmp / "ds", task_views=VIEWS)
    assert out.get("state") == "complete", f"fixture: export {out}"
    root = w.tmp / "ds"
    exs = M.read_jsonl(root / "examples.jsonl")
    prefs = M.read_jsonl(root / "preferences.jsonl")
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    r = w.training.readiness()
    te = r["readiness_metrics"]["task_eligibility"]
    exported = {v: [] for v in VIEWS}
    for e in exs:
        if e.get("task_kind") in exported:
            exported[e["task_kind"]].append(_key(e, e["task_kind"]))
    exported["preference_pairs"] = [pp.get("task_key") for pp in prefs]
    ex_reasons = {v: collections.Counter() for v in VIEWS}
    ex_keys = {v: set() for v in VIEWS}
    selection = collections.Counter()
    selection_keys = set()
    for row in manifest.get("excluded") or []:
        reason = row.get("reason") or ""
        key = row.get("example_id") or row.get("candidate_id") \
            or row.get("task_key")
        view = next((v for pre, v in REASON_VIEW
                     if reason.startswith(pre)), None)
        if view is None:
            selection[reason] += 1
            selection_keys.add(key)
            continue
        ex_reasons[view][reason[len(next(
            pre for pre, v in REASON_VIEW if v == view)):]] += 1
        ex_keys[view].add(key)
    bad = []
    for v in VIEWS:
        got = exported[v]
        if len(got) != len(set(got)):
            bad.append(f"{v}: duplicate exported rows {len(got)}")
        if set(got) != exp[v]["eligible"]:
            bad.append(f"{v}: exported {len(set(got))} != expected"
                       f" eligible {len(exp[v]['eligible'])}")
        if ex_keys[v] != exp[v]["excluded"]:
            bad.append(f"{v}: export excluded {sorted(ex_reasons[v])}"
                       f" for {len(ex_keys[v])} keys, expected"
                       f" {len(exp[v]['excluded'])}")
        rv = te.get(v)
        if rv is None and v == "asr_span_graft_weak":
            # contracts/analytics.md "Readiness aggregates": task
            # eligibility covers ASR, cleanup, transform and preference
            # pairs; the weak span-graft view is export-only, so its
            # readiness leg is not applicable (its export membership and
            # exclusions are checked above).
            continue
        if rv is None:
            bad.append(f"{v}: readiness reports no such view (export"
                       f" excluded {dict(ex_reasons[v])}, exported"
                       f" {len(set(got))})")
            continue
        if rv.get("count") != len(set(got)):
            bad.append(f"{v}: readiness count {rv.get('count')} !="
                       f" exported {len(set(got))}")
        ready_reasons = collections.Counter(rv.get("excluded") or {})
        if ready_reasons != ex_reasons[v]:
            bad.append(f"{v}: readiness reasons {dict(ready_reasons)} !="
                       f" export reasons {dict(ex_reasons[v])}")
    # Selection-level exclusions: the same selection admits only a state
    # exclusion, matched by readiness's own 'excluded' outcome class.
    if selection_keys != exp["selection_excluded"]:
        bad.append(f"selection: export {dict(selection)} for"
                   f" {len(selection_keys)} keys, expected"
                   f" {len(exp['selection_excluded'])}")
    if selection.get("state_excluded", 0) != \
            r["outcome_balance"]["excluded"]:
        bad.append(f"selection: export state_excluded"
                   f" {selection.get('state_excluded', 0)} != readiness"
                   f" outcome_balance.excluded"
                   f" {r['outcome_balance']['excluded']}")
    extra = set(selection) - {"state_excluded"}
    if extra:
        bad.append(f"selection: unexpected reasons {sorted(extra)} under"
                   " one assignment")
    tiers_export = {t: sum(1 for e in exs
                           if e.get("task_kind") == "cleanup_supervised"
                           and e.get("qualification_tier") == t)
                    for t in exp["tiers"]}
    tiers_ready = {t: ((te.get("cleanup_supervised") or {}).get("tiers")
                       or {}).get(t, 0) for t in exp["tiers"]}
    if not (tiers_export == tiers_ready == exp["tiers"]):
        bad.append(f"cleanup tiers export {tiers_export} readiness"
                   f" {tiers_ready} expected {exp['tiers']}")
    return bad, {"export": {v: dict(ex_reasons[v]) for v in VIEWS},
                 "selection": dict(selection)}


@case("G06 XM-C144 (every export exclusion matches a named readiness reason"
      " and tier on the four contracted readiness views; the weak graft"
      " view is export-only by contract)")
def g06_xm_c144_exclusion_reason_parity():
    with M.MWorld() as w:
        exp = _c144_world(w, restricted=True)
        bad, obs = _c144_compare(w, exp)
        assert not bad, ("readiness/export exclusion parity broken: "
                         + " | ".join(bad) + f" || export={obs}")


@case("G06 XM-C144 control (an all-eligible world: exact membership, no"
      " exclusion on either side)", kind="control")
def c_g06_xm_c144_all_eligible_world():
    with M.MWorld() as w:
        exp = _c144_world(w, restricted=False)
        bad, obs = _c144_compare(w, exp)
        # The control grades what both sides report; a view readiness
        # does not report at all is the defect case's finding.
        bad = [b for b in bad if "readiness reports no such view" not in b]
        assert not bad, " | ".join(bad) + f" || {obs}"


# =============================================================================
# XM-C145 — a family newer than the selected assignment is reason-coded
# =============================================================================

@case("G06 XM-C145 (a family created after the selected assignment is"
      " not_in_assignment_version, never guessed into a partition)")
def g06_xm_c145_late_family_is_reason_coded():
    with M.MWorld() as w:
        base = w.families(10, asr=True)
        v1 = w.splits.assign()["assignment_version"]
        late = w.ready_asr(f"late family witness {M.B_CANARY}")
        late_ex = late["example_id"]
        members_v1 = {x for (x,) in w.rows(
            "SELECT example_id FROM training_memberships WHERE"
            " assignment_version=?", (v1,))}
        assert members_v1 == {j["example_id"] for j in base}, \
            "fixture: v1 membership"
        # Raw SQL: no membership row for the late example in v1.
        assert w.one("SELECT COUNT(*) FROM training_memberships WHERE"
                     " example_id=? AND assignment_version=?",
                     (late_ex, v1))[0] == 0
        try:
            w.exporter.build(w.tmp / "v1", task_views=("asr_supervised",),
                             assignment_version=v1)
            refusal = None
        except export_mod.ExportError as e:
            refusal = str(e)
        assert refusal is None, (
            "the late family was treated as a predicate disagreement /"
            f" refusal: {refusal}")
        root = w.tmp / "v1"
        exs = M.read_jsonl(root / "examples.jsonl")
        refs = M.read_jsonl(root / "references.jsonl")
        manifest = json.loads((root / "dataset_manifest.json").read_text())
        exported = {e["example_id"] for e in exs}
        assert late_ex not in exported and all(
            r.get("example_id") != late_ex for r in refs), (
            "the late example was guessed into a v1 partition:"
            f" {[e.get('split') for e in exs if e['example_id'] == late_ex]}")
        assert exported == members_v1, (
            f"v1 export is not the frozen membership set:"
            f" {len(exported)} vs {len(members_v1)}")
        reasons = [r.get("reason") for r in manifest.get("excluded") or []
                   if r.get("example_id") == late_ex]
        assert reasons == ["not_in_assignment_version"], (
            f"the late example's exclusion is not reason-coded exactly:"
            f" {reasons}")
        # The difference with global readiness is exactly the disclosed
        # row (LF-CROSS-C065: unlike cohorts, disclosed, not a mismatch).
        te = w.training.readiness()["readiness_metrics"]["task_eligibility"]
        assert te["asr_supervised"]["count"] == len(exported) + len(
            reasons), (te["asr_supervised"], len(exported))
        # Control: a new assignment admits the family into its hash
        # partition (computed here from the contract's family hash).
        v2 = w.splits.assign()["assignment_version"]
        w.exporter.build(w.tmp / "v2", task_views=("asr_supervised",),
                         assignment_version=v2)
        exs2 = M.read_jsonl(w.tmp / "v2" / "examples.jsonl")
        got = [e.get("split") for e in exs2 if e["example_id"] == late_ex]
        assert got == [M.family_bucket(late["family_id"])], (
            f"control: v2 partition {got} vs"
            f" {M.family_bucket(late['family_id'])}")


# =============================================================================
# XM-MH01 / XM-C146 — exposure is forward-only; old packages stay historical
# =============================================================================

def _tree(root):
    """{relpath: sha256 | 'dir'} of a package, links not followed."""
    root = pathlib.Path(root)
    out = {}
    for d, dirs, files in os.walk(root, followlinks=False):
        for n in dirs:
            out[(pathlib.Path(d) / n).relative_to(root).as_posix()] = "dir"
        for n in files:
            p = pathlib.Path(d) / n
            out[p.relative_to(root).as_posix()] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


def _rec(root, ex_id):
    return [(e.get("split"), e.get("exposed"))
            for e in M.read_jsonl(pathlib.Path(root) / "examples.jsonl")
            if e.get("example_id") == ex_id
            and e.get("task_kind") == "asr_supervised"]


@case("G06 XM-MH01 + XM-C146 (an exposed family never regains a blind"
      " claim, even under an older assignment; the pre-exposure package"
      " stays byte-identical and valid)")
def g06_xm_mh01_c146_exposure_forward_old_package_historical():
    with M.MWorld() as w:
        fams = w.families(10, asr=True, frozen=2)
        f_ex, g_ex = fams[0]["example_id"], fams[1]["example_id"]
        fam_f, fam_g = fams[0]["family_id"], fams[1]["family_id"]
        assert M.family_bucket(fam_f) == M.family_bucket(fam_g) == \
            "frozen_test", "fixture: frozen families"
        v1 = w.splits.assign()["assignment_version"]
        p1 = w.tmp / "p1"
        w.exporter.build(p1, task_views=("asr_supervised",))
        assert _rec(p1, f_ex) == [("frozen_test", False)], \
            f"fixture: P1 row for F {_rec(p1, f_ex)}"
        base_tree = _tree(p1)
        assert export_mod.validate_dataset(p1)["valid"], "fixture: P1"

        def historical(stage):
            assert _tree(p1) == base_tree, (
                f"P1 bytes changed after {stage}")
            rep = export_mod.validate_dataset(p1)
            assert rep["valid"], f"P1 invalid after {stage}: {rep}"
            assert _rec(p1, f_ex) == [("frozen_test", False)], (
                f"P1 no longer records F as it was after {stage}")
        w.splits.mark_exposed([fam_f], "tuned_on_holdout")
        historical("exposure")
        # A new build selecting the PRE-exposure assignment.
        try:
            w.exporter.build(w.tmp / "n1", task_views=("asr_supervised",),
                             assignment_version=v1)
            n1 = w.tmp / "n1"
        except export_mod.ExportError:
            n1 = None
        historical("a v1 build after exposure")
        if n1 is not None:
            assert ("frozen_test", False) not in _rec(n1, f_ex), (
                "a new v1 export made a fresh blind claim for the exposed"
                f" family: {_rec(n1, f_ex)}")
        # A new build on the current assignment.
        w.exporter.build(w.tmp / "n2", task_views=("asr_supervised",))
        historical("a current build")
        n2 = _rec(w.tmp / "n2", f_ex)
        assert n2 and all(s != "frozen_test" and e is True for s, e in n2), (
            f"the new export's partition for the exposed family: {n2}")
        # Control: the unexposed frozen family keeps its blind claim.
        assert _rec(w.tmp / "n2", g_ex) == [("frozen_test", False)], (
            f"control: unexposed G {_rec(w.tmp / 'n2', g_ex)}")
        # Raw SQL: the exposure history is permanent and the old
        # version's rows are untouched.
        hist = w.rows("SELECT assignment_version, partition, exposed FROM"
                      " training_memberships WHERE example_id=? ORDER BY"
                      " assignment_version", (f_ex,))
        assert hist[0] == (v1, "frozen_test", 0) and hist[-1][1:] == (
            "train", 1), f"exposure history {hist}"


# =============================================================================
# XM-MH05 — an older held profile result released last never republishes
# excluded support
# =============================================================================

PHRASE_X = "marmalade zeppelin"
MH05_TEXTS = ["marmalade zeppelin alpha harbour verse",
              "marmalade zeppelin bravo meadow verse",
              "quiet lantern charlie river verse",
              "quiet lantern delta canyon verse"]


def _settle_without_work(hub, mq):
    """Flush main-queue callbacks and admitted queries while a held
    background generation is still parked (MainQueue.drain would join
    it)."""
    for _ in range(200):
        hub.state.wait_for_queries(10)
        n = mq.flush()
        if n == 0 and hub.state.queries_idle() and mq.pending() == 0:
            return True
    return False


def _mh05(exclude):
    h = Harness(durations=[1.0] * 4)
    try:
        h.d.consent.set("enabled")
        queue = list(MH05_TEXTS)
        h.d.supervisor = Scripted(asr=lambda j, a: queue.pop(0))
        jobs = [dictate(h) for _ in MH05_TEXTS]
        store = h.d.store
        ex_e = examples_of(store, jobs[0])[0][0]
        svc = h.d._profile
        with MainQueue() as mq:
            hub = make_hub(h)
            open_view(hub, mq, "insights")
            hub.state.select_insights_subview("voice")
            assert mq.drain(hub.state, 60)
            s0 = svc.compute()
            assert PHRASE_X in [p["phrase"] for p in
                                s0["measured"]["frequent_phrases"]], \
                f"fixture: X not a phrase {s0['measured']}"
            assert ex_e in evidence_of(store, s0["snapshot_id"]), \
                "fixture: E is not S0's support"
            real_eligible = svc._eligible
            reads = {"n": 0}
            reached, go = threading.Event(), threading.Event()

            def eligible(labels):
                out = real_eligible(labels)
                reads["n"] += 1
                if reads["n"] == 1:  # generation A: held after its read
                    reached.set()
                    assert go.wait(60), "A never released"
                return out
            svc._eligible = eligible
            real_compute = svc.compute
            results = []

            def compute(**kw):
                out = real_compute(**kw)
                results.append(out)
                return out
            svc.compute = compute
            posted = []
            work_post = threading.Event()

            def on_post(fn, a):
                if threading.current_thread().name == "localflow-hub-work":
                    posted.append(fn)
                    work_post.set()
            mq.on_post = on_post
            try:
                hub.voiceGenerate_(None)                  # A
                assert reached.wait(10), "fixture: A never read evidence"
                if exclude:
                    svc.exclude_evidence(s0["snapshot_id"], ex_e)
                hub.voiceGenerate_(None)                  # B (completes)
                assert work_post.wait(20), "fixture: B never completed"
                assert _settle_without_work(hub, mq)
                assert len(results) == 1, "fixture: B's result"
                b = results[0]
                b_ev = evidence_of(store, b["snapshot_id"])
                shown_b = hub.voice_pane.text.string()
                assert b["snapshot_id"][:16] in \
                    hub.voice_pane.status.stringValue(), \
                    "fixture: B not rendered"
                if exclude:
                    assert ex_e not in b_ev and PHRASE_X not in shown_b, \
                        "fixture: B still carries the excluded support"
                else:
                    assert PHRASE_X in shown_b, "fixture: control phrase"
                work_post.clear()
                go.set()                                  # A released last
                assert work_post.wait(20), "fixture: A never completed"
                assert mq.drain(hub.state, 60)
                assert len(results) == 2, "fixture: A's result"
                late_render = hub.voice_pane.text.string()
                late_status = hub.voice_pane.status.stringValue()
                # A routine refresh after A settled (what the next visit
                # to the pane shows).
                hub.state.reload_insights()
                assert mq.drain(hub.state, 60)
                shown = hub.voice_pane.text.string()
                data = (hub.state.views["insights"].get("data") or {}) \
                    .get("profile") or {}
            finally:
                mq.on_post = None
                go.set()
                svc.compute = real_compute
                svc._eligible = real_eligible
            cur = latest_snapshot(store)
            cur_ev = evidence_of(store, cur[0])
            return {"b": b, "b_ev": b_ev, "shown_b": shown_b,
                    "late_render": late_render, "late_status": late_status,
                    "shown": shown, "data": data, "cur": cur,
                    "cur_ev": cur_ev, "ex_e": ex_e, "reads": reads["n"],
                    "a": results[1]}
    finally:
        h.close()


@case("G06 XM-MH05 (an older held Your Voice generation released last"
      " never republishes excluded support)")
def g06_xm_mh05_older_generation_never_republishes_excluded():
    o = _mh05(exclude=True)
    assert o["late_render"] == o["shown_b"] and o["b"]["snapshot_id"][:16] \
        in o["late_status"], (
        "A's late completion repainted over B's generation")
    phrases = [p["phrase"] for p in (o["data"].get("measured") or {})
               .get("frequent_phrases") or []]
    assert PHRASE_X not in o["shown"] and PHRASE_X not in phrases, (
        "the excluded support was republished after the older generation"
        f" was released: rendered phrase present={PHRASE_X in o['shown']},"
        f" view data phrases={phrases}")
    assert o["ex_e"] not in o["cur_ev"], (
        f"the current snapshot {o['cur'][0]} cites the excluded example")
    assert o["cur"][1] == "current" and o["cur_ev"] == o["b_ev"], (
        "the current snapshot's support is not the new generation's:"
        f" {len(o['cur_ev'])} vs B {len(o['b_ev'])} (current"
        f" {o['cur'][0]}, B {o['b']['snapshot_id']})")
    assert (o["data"].get("measured") or {}).get("eligible_examples") == \
        o["b"]["measured"]["eligible_examples"], (
        "rendered support count differs from the new generation's")


@case("G06 XM-MH05 control (no exclusion: releasing A last leaves B's"
      " generation rendered)", kind="control")
def c_g06_xm_mh05_release_last_without_exclusion():
    o = _mh05(exclude=False)
    assert o["late_render"] == o["shown_b"] and o["b"]["snapshot_id"][:16] \
        in o["late_status"], "A's late completion repainted over B"
    assert PHRASE_X in o["shown"], "control: X is legitimate support here"


# =============================================================================
# XM-MH10 / XM-C154 — only eligible user speech feeds the profile
# =============================================================================

CTRL_TEXT = "plain field capture about harbour lanterns"
NOTE_TEXT = "note capture about meadow violins"
SNIP_TRIGGER = "sign off"
SNIP_CONTENT = "Warm regards snippetcanaryqz signature"
TYPED = f"{M.TYPED_CANARY} zebrafinch {M.TYPED_CANARY} zebrafinch"


def _origin_world(hw, snippet):
    """A plain text-field capture, optionally a snippet-expanded
    capture, then a note-bound capture followed by two typed autosaves
    carrying the typed canary. Returns ids and what was pasted."""
    import test_scratchpad_hub as tsh

    class ScriptedTF(tsh.TFSupervisor):
        def __init__(self, texts):
            super().__init__()
            self.texts = list(texts)

        def transcribe(self, **kw):
            out = super().transcribe(**kw)
            out["text"] = self.texts.pop(0)
            return out
    texts = [CTRL_TEXT] + ([SNIP_TRIGGER] if snippet else []) + [NOTE_TEXT]
    hw.d.supervisor = ScriptedTF(texts)
    if snippet:
        hw.d._snip_store.add_snippet(trigger=SNIP_TRIGGER, name="g06",
                                     content=SNIP_CONTENT)
    out = {"pastes": []}

    def field_capture():
        hw.h.press()
        hw.h.release()
        fn, args = hw.h.run_coordinator()
        fn(*args)
        hw.drain()
        return args[1]["job_id"]
    out["ctrl"] = field_capture()
    if snippet:
        out["snip"] = field_capture()
    pastes_before = len(hw.h.pastes)
    n = hw.notes.create_note("")["note_id"]
    hw.open_note(n)
    assert hw.focus(), "fixture: editor focus seam unavailable"
    hw.h.press()
    hw.h.release()
    fn, args = hw.h.run_coordinator()
    fn(*args)
    hw.settle_notes()
    hw.drain()
    out["note_job"] = args[1]["job_id"]
    out["note_id"] = n
    out["pastes_during_note"] = hw.h.pastes[pastes_before:]
    for i in range(2):
        content = hw.store.submit(lambda db: db.execute(
            "SELECT r.content_text FROM notes n JOIN note_revisions r ON"
            " r.revision_id=n.current_revision_id WHERE n.note_id=?",
            (n,)).fetchone())[0]
        hw.type(f"{content} {TYPED} {i}")
        hw.hub.editor.flush_now()
        hw.settle_notes()
        hw.drain()
    last = hw.store.submit(lambda db: db.execute(
        "SELECT r.content_text, r.origin FROM notes n JOIN note_revisions r"
        " ON r.revision_id=n.current_revision_id WHERE n.note_id=?",
        (n,)).fetchone())
    assert last and M.TYPED_CANARY in last[0], \
        f"fixture: typed autosave never landed {last}"
    return out


def _example(store, job_id):
    got = examples_of(store, job_id)
    assert len(got) == 1, f"fixture: examples of {job_id}: {got}"
    return got[0][0]


@case("G06 XM-MH10 (a note-bound capture with typed autosaves counts one"
      " dictation, no typed words, no external AX delivery)")
def g06_xm_mh10_note_capture_counts_dictated_words_only():
    import m12_world as m12w
    with m12w.HubWorld(consent=True) as hw:
        o = _origin_world(hw, snippet=False)
        store = hw.store
        job = o["note_job"]
        facts = rows(store, "SELECT insertion_outcome, final_words,"
                     " meta_json FROM usage_facts WHERE job_id=? AND"
                     " kind='dictation'", (job,))
        assert len(facts) == 1 and facts[0][0] == "confirmed" and \
            facts[0][1] == len(NOTE_TEXT.split()), (
                f"note capture usage facts {facts[:2]} (dictated words"
                f" {len(NOTE_TEXT.split())})")
        ctrl = rows(store, "SELECT final_words FROM usage_facts WHERE"
                    " job_id=? AND kind='dictation'", (o["ctrl"],))
        assert ctrl == [(len(CTRL_TEXT.split()),)], f"control fact {ctrl}"
        # Not an external AX delivery: the insertion service was never
        # handed the arrival and no insertion row/observation names it.
        assert o["pastes_during_note"] == [], (
            f"the note arrival went through the insertion service:"
            f" {o['pastes_during_note']}")
        ins = one(store, "SELECT COUNT(*) FROM insertions WHERE job_id=?",
                  (job,))[0]
        obs = one(store, "SELECT COUNT(*) FROM insertion_observations"
                  " WHERE job_id=?", (job,))[0]
        assert ins == 0 and obs == 0, (
            f"the note arrival is attributed as an external insertion:"
            f" insertions={ins} observations={obs}")
        assert one(store, "SELECT state_reason FROM jobs WHERE job_id=?",
                   (job,))[0] == "scratchpad_note"
        snap = ProfileService(store, min_words=1).compute()
        m = snap["measured"]
        want = len(CTRL_TEXT.split()) + len(NOTE_TEXT.split())
        assert m["eligible_examples"] == 2 and m["eligible_words"] == want, (
            f"profile counted {m['eligible_examples']} dictations /"
            f" {m['eligible_words']} words; dictated speech is 2 / {want}")
        blob = json.dumps({"m": m, "c": snap["cards"]}).lower()
        assert M.TYPED_CANARY not in blob and "zebrafinch" not in blob, (
            "typed note words reached the profile")
        cited = evidence_of(store, snap["snapshot_id"])
        assert cited == {_example(store, job), _example(store, o["ctrl"])},\
            f"profile support {cited}"


@case("G06 XM-C154 (only eligible user speech — never typed or"
      " snippet-expanded words — feeds speech-derived measures)")
def g06_xm_c154_speech_measures_exclude_typed_and_snippet_words():
    import m12_world as m12w
    with m12w.HubWorld(consent=True) as hw:
        o = _origin_world(hw, snippet=True)
        store = hw.store
        snip_ex = _example(store, o["snip"])
        norm = envelope(store, snip_ex).get("normalization") or {}
        assert ((norm.get("snippets") or {}).get("expansions") or 0) >= 1, \
            f"fixture: the snippet never expanded {norm.get('snippets')}"
        snap = ProfileService(store, min_words=1).compute()
        m = snap["measured"]
        # Independent word counts by origin.
        dictated = len(CTRL_TEXT.split()) + len(NOTE_TEXT.split())
        assert m["eligible_words"] == dictated and \
            m["eligible_examples"] == 2, (
                f"measured {m['eligible_examples']} dictations /"
                f" {m['eligible_words']} words; eligible speech is 2 /"
                f" {dictated} (typed {len(TYPED.split()) * 2}, snippet"
                f" {len(SNIP_CONTENT.split())})")
        assert (m.get("excluded") or {}).get("snippet_expanded") == 1, \
            f"snippet exclusion not disclosed: {m.get('excluded')}"
        blob = json.dumps({"m": m, "c": snap["cards"]}).lower()
        for canary in (M.TYPED_CANARY, "zebrafinch", "snippetcanaryqz"):
            assert canary not in blob, f"{canary} reached the profile"
        # Control: the plain dictated capture is counted and cited.
        cited = evidence_of(store, snap["snapshot_id"])
        assert _example(store, o["ctrl"]) in cited and snip_ex not in cited,\
            f"control: support {cited}"


# =============================================================================
# XM-MH12 — a History retry keeps final, usage, profile and evidence agreed
# =============================================================================

A1_TEXT = "alphamark first attempt spoken words"
A2_TEXT = "bravomark second attempt spoken words"
CTRL12 = "controlmark single attempt spoken words"
_TEXT_ROLES = ("raw_transcript", "normalized_text", "applied_output",
               "cleanup_input_cleanup", "cleanup_proposal")


def _named_artifacts(env):
    arts = dict(env.get("artifact_ids") or {})
    for k, v in (((env.get("normalization") or {}).get("artifact_ids")
                  or {}).items()):
        arts[f"normalization.{k}"] = v
    arts.pop("original_audio", None)  # one capture's audio, per job
    return {k: v for k, v in arts.items() if isinstance(v, str) and v}


def _attribution(store, job, env, marks):
    """Mismatches between an envelope's attempt and the artifacts it
    names: owner job, any recorded attempt tag, and the per-attempt
    text markers (the scripted ASR text of each attempt)."""
    k = env.get("attempt")
    bad = []
    for slot, aid in _named_artifacts(env).items():
        row = one(store, "SELECT job_id, role, content_text, meta_json FROM"
                  " artifacts WHERE artifact_id=?", (aid,))
        if row is None:
            bad.append(f"a{k}:{slot} absent")
            continue
        owner, role, text, meta = row
        tag = json.loads(meta or "{}").get("attempt")
        if owner != job:
            bad.append(f"a{k}:{slot} foreign job")
        if isinstance(tag, int) and tag != k:
            bad.append(f"a{k}:{slot} tagged attempt {tag}")
        low = (text or "").lower()
        for other, mark in marks.items():
            if other != k and mark in low:
                bad.append(f"a{k}:{slot} ({role}) carries attempt {other}")
        if role in _TEXT_ROLES and marks[k] not in low:
            bad.append(f"a{k}:{slot} ({role}) lacks its own attempt text")
    return bad


@case("G06 XM-MH12 (a History retry with changed transcription: final,"
      " one usage job, one profile contribution, per-attempt evidence"
      " attributed)")
def g06_xm_mh12_retry_agrees_across_consumers():
    h = Harness(durations=[1.0] * 3)
    try:
        h.d.consent.set("enabled")
        phase = {"ctrl": True}
        sup = Scripted(asr=lambda j, a: CTRL12 if phase["ctrl"] else (
            A1_TEXT if a == 1 else A2_TEXT))
        h.d.supervisor = sup
        ctrl = dictate(h)                       # control: no retry
        phase["ctrl"] = False
        sup.fail_clean = {1}
        job = dictate(h)
        assert h.job_state(job) == "failed_recoverable", h.job_state(job)
        out = h.d.hubRetryJob(job)              # History's Retry
        assert out is None or out.get("outcome") in (
            None, "requeued", "queued"), f"fixture: retry {out}"
        fn, a = h.run_coordinator()
        fn(*a)
        store = h.d.store
        assert one(store, "SELECT attempt FROM jobs WHERE job_id=?",
                   (job,))[0] == 2, "fixture: job attempt"
        final2 = attempt_final(sup, job, 2)
        detail = HistoryQueryService(store).job_detail(job)
        assert detail.get("lineage_attempt") == 2 and \
            final_text(detail) == final2, (
                f"History final {final_text(detail)!r} vs attempt 2"
                f" {final2!r} (lineage attempt"
                f" {detail.get('lineage_attempt')})")
        facts = rows(store, "SELECT attempt, final_words FROM usage_facts"
                     " WHERE job_id=? AND kind='dictation'", (job,))
        assert facts == [(2, len(final2.split()))], (
            f"usage facts for the retried job {facts}")
        exs = [e for (e,) in examples_of(store, job)]
        by_attempt = {envelope(store, e).get("attempt"): e for e in exs}
        assert sorted(by_attempt) == [1, 2] and len(exs) == 2, (
            f"fixture: per-attempt examples {sorted(by_attempt)}")
        snap = ProfileService(store, min_words=1).compute()
        cited = evidence_of(store, snap["snapshot_id"])
        ctrl_ex = _example(store, ctrl)
        assert snap["measured"]["eligible_examples"] == 2, (
            f"2 captures counted as {snap['measured']['eligible_examples']}")
        assert cited & set(exs) == {by_attempt[2]} and ctrl_ex in cited, (
            "profile support for the retried capture is not exactly the"
            f" attempt-2 example: attempt1 cited={by_attempt[1] in cited}"
            f" attempt2 cited={by_attempt[2] in cited}")
        marks = {1: "alphamark", 2: "bravomark"}
        bad = []
        for k, ex in by_attempt.items():
            bad += _attribution(store, job, envelope(store, ex), marks)
        assert not bad, f"per-attempt evidence misattributed: {bad}"
        # Control: a capture without retry — attempt 1 throughout.
        cenv = envelope(store, ctrl_ex)
        assert cenv.get("attempt") == 1 and rows(
            store, "SELECT attempt FROM usage_facts WHERE job_id=? AND"
            " kind='dictation'", (ctrl,)) == [(1,)], "control attempt"
        cbad = _attribution(store, ctrl, cenv, {1: "controlmark"})
        assert not cbad, f"control attribution {cbad}"
    finally:
        h.close()


# =============================================================================
# runner (copied from test_xm_remediation.py; same record shape)
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
    print("xm g06 D:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_g06_d.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_g06_d.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
