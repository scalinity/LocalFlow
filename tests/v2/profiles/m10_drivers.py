"""Drivers binding the frozen M10 adversarial corpus
(``m10_audit_corpus.json``, sha256 3cc5a928…755, unchanged) to the
current APIs. One driver per case (families share parameterised
drivers); each returns an ``Outcome`` with the result taxonomy of the
corpus runner contract — PASS / FAIL / ERROR / NARROWED /
MANUAL_PENDING / NOT_RUN — the observed values, and for stateful cases
the barriers actually reached.

Oracles are written here from each case's declared setup and expected
assertions (and the policy adjudications recorded in
``docs/v2/acceptance/M10/remediation/adjudications.json``); nothing asks
the code under test to compute its own expected answer. A driver whose
setup cannot be expressed through a current entry point returns ERROR
with the reason — never PASS.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

import m10_world as w  # noqa: E402
import test_m10_remediation as rem  # noqa: E402
from m10_world import FixtureRoot, harness, hooked_harness, run_job  # noqa
from m10_world import json_manifest, skill_md, write  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2 import ids  # noqa: E402
from localflow.v2 import profiles as prof  # noqa: E402
from localflow.v2 import snippets as snip_mod  # noqa: E402
from localflow.v2 import vocabulary as vocab  # noqa: E402
from localflow.v2.developer import file_tags  # noqa: E402
from localflow.v2.developer import skills as skills_mod  # noqa: E402
from localflow.v2.developer import surfaces  # noqa: E402
from localflow.v2.normalize import (ContextSnapshot,  # noqa: E402
                                    NormalizationPolicy, normalize)


@dataclasses.dataclass
class Outcome:
    status: str
    observed: dict
    barriers: list = dataclasses.field(default_factory=list)
    note: str = ""


DRIVERS: dict = {}


def driver(*case_ids):
    def deco(fn):
        for cid in case_ids:
            DRIVERS[cid] = fn
        return fn
    return deco


def verdict(checks: dict, observed=None, barriers=None, note=""):
    """PASS when every named check holds; FAIL names the ones that do
    not (the observed values ride along)."""
    failed = [k for k, v in checks.items() if not v]
    obs = dict(observed or {})
    obs["checks"] = {k: bool(v) for k, v in checks.items()}
    return Outcome("FAIL" if failed else "PASS", obs, list(barriers or []),
                   note or (f"failed: {failed}" if failed else ""))


# ---- profile precedence / duplicates / canonical scopes ----------------------

def _rule(d, **kw):
    return prof.StyleRule(
        rule_id=d["rule_id"], name=d.get("name", d["rule_id"]),
        scope_kind=d.get("scope_kind", "global"),
        scope_value=d.get("scope_value"), mode=d.get("mode", "clean"),
        number_policy=d.get("number_policy", "inherit"),
        profile_name=d.get("profile_name"), **kw)


def _dest(d):
    return prof.Destination(app_bundle=d.get("app_bundle"),
                            site_origin=d.get("site_origin"),
                            workspace=d.get("workspace"),
                            category=d.get("category"))


@driver("M10-C001", "M10-C002", "M10-C003", "M10-C004", "M10-C005")
def precedence(c):
    s = c["setup"]
    rules = [_rule(r) for r in s["rules"]]
    wp = prof.resolve(s.get("job_override"), rules, _dest(s["destination"]))
    want_id = {"M10-C001": "r:workspace", "M10-C002": "r:site",
               "M10-C003": "r:app", "M10-C004": "r:category",
               "M10-C005": None}[c["id"]]
    want_src = {"M10-C001": "rule:workspace", "M10-C002": "rule:site",
                "M10-C003": "rule:app", "M10-C004": "rule:category",
                "M10-C005": "job_override"}[c["id"]]
    chosen = next((r for r in rules if r.rule_id == want_id), None)
    return verdict({
        "winner": wp.rule_id == want_id,
        "source": wp.source == want_src,
        # no hybrid: number policy and profile come from the same choice
        "number_policy_same_choice": wp.number_policy == (
            chosen.number_policy if chosen else "inherit"),
        "profile_same_choice": wp.profile_name == (
            (chosen.profile_name if chosen else None)
            or s["destination"].get("category")),
    }, {"profile": wp.to_json()})


@driver("M10-C006")
def disabled_narrower(c):
    s = c["setup"]
    rules = [_rule(r, enabled=r["rule_id"] != s["disable"])
             for r in s["rules"]]
    wp = prof.resolve(None, rules, _dest(s["destination"]))
    return verdict({"winner_site": wp.rule_id == "r:site",
                    "disabled_not_applied": wp.rule_id != s["disable"]},
                   {"profile": wp.to_json()})


@driver("M10-C007")
def category_default(c):
    rules = [_rule(r) for r in c["setup"]["rules"]]
    wp = prof.resolve(None, rules, _dest(c["setup"]["destination"]))
    return verdict({"clean": wp.effective_mode == "clean",
                    "category_default": wp.source == "category_default"},
                   {"profile": wp.to_json()})


@driver("M10-C008")
def unknown_destination(c):
    rules = [_rule(r) for r in c["setup"]["rules"]]
    wp = prof.resolve(None, rules, _dest(c["setup"]["destination"]))
    return verdict({"raw": wp.effective_mode == "raw",
                    "global_rule": wp.rule_id == "r:global"},
                   {"profile": wp.to_json()})


@driver("M10-C009")
def missing_site(c):
    rules = [_rule(r) for r in c["setup"]["rules"]]
    wp = prof.resolve(None, rules, _dest(c["setup"]["destination"]))
    return verdict({"site_not_winning": wp.rule_id is None,
                    "global_clean": wp.effective_mode == "clean"
                    and wp.source == "global_default"},
                   {"profile": wp.to_json()})


@driver("M10-C010", "M10-C011", "M10-C012", "M10-C013")
def duplicates(c):
    s = c["setup"]
    kind, value = s["scope_kind"], s["scope_value"]
    rs = [_rule({"rule_id": r["rule_id"], "mode": r["mode"],
                 "scope_kind": kind, "scope_value": value})
          for r in s["rules"]]
    dest = {"global": prof.Destination(),
            "category": prof.Destination(category=value),
            "app": prof.Destination(app_bundle=value),
            "workspace": prof.Destination(workspace=value)}[kind]
    a = prof.resolve(None, rs, dest)
    b = prof.resolve(None, list(reversed(rs)), dest)
    # m10-policy-r1 (AUDIT-29): the lexically smaller rule id wins,
    # deterministically, and the tie is visible (ids of the others).
    return verdict({
        "same_winner_both_orders": a.rule_id == b.rule_id == "r:100",
        "tie_visible": a.equal_authority_rule_ids == ("r:200",)
        and b.equal_authority_rule_ids == ("r:200",)},
        {"a": a.to_json(), "b": b.to_json()})


@driver("M10-C014", "M10-C015", "M10-C016", "M10-C017", "M10-C018")
def canonical_equivalents(c):
    s = c["setup"]
    kind, left, right = s["scope_kind"], s["left"], s["right"]
    m05 = vocab.canonical_scope_value(kind, left) \
        == vocab.canonical_scope_value(kind, right)
    rule = _rule({"rule_id": "r:x", "scope_kind": kind,
                  "scope_value": left, "mode": "raw"})
    dest = prof.Destination(**{{"app": "app_bundle", "site": "site_origin",
                                "workspace": "workspace"}[kind]: right})
    hit = prof.resolve(None, [rule], dest).rule_id == "r:x"
    other = {"app": "com.example.other", "site": "https://other.invalid",
             "workspace": "OtherWorkspace"}[kind]
    miss = prof.resolve(None, [rule], prof.Destination(**{
        {"app": "app_bundle", "site": "site_origin",
         "workspace": "workspace"}[kind]: other})).rule_id is None
    # The vocabulary side of the same destination (M05).
    entry = vocab.VocabularyEntry(entry_id="v1", canonical="Term",
                                  scope_kind=kind, scope_value=left,
                                  approved=True, enabled=True,
                                  aliases=(vocab.Alias(alias="term"),))
    ctx = vocab.ScopeContext(**{{"app": "app_bundle",
                                 "site": "site_origin",
                                 "workspace": "workspace"}[kind]: right})
    return verdict({"m05_equivalent": m05, "m10_rule_matches": hit,
                    "m05_entry_matches": entry.scope_matches(ctx),
                    "different_identity_misses": miss})


@driver("M10-C019")
def canonical_profile(c):
    left, right = c["setup"]["left"], c["setup"]["right"]
    rule = _rule({"rule_id": "r:p", "scope_kind": "global",
                  "profile_name": right})
    wp = prof.resolve(None, [rule], prof.Destination())
    entry = vocab.VocabularyEntry(entry_id="v1", canonical="Term",
                                  scope_kind="profile", scope_value=left,
                                  approved=True, enabled=True,
                                  aliases=(vocab.Alias(alias="term"),))
    return verdict({
        "profile_identity_trimmed": wp.profile_name == left,
        "vocabulary_scope_matches": entry.scope_matches(
            vocab.ScopeContext(profile=wp.profile_name)),
        "other_profile_misses": not entry.scope_matches(
            vocab.ScopeContext(profile="WritingB"))},
        {"profile": wp.to_json()})


@driver("M10-C020", "M10-C021", "M10-C022")
def non_equivalent(c):
    left, right = c["setup"]["left"], c["setup"]["right"]
    kind = "site" if left.startswith("http") else "workspace"
    if c["id"] == "M10-C022":
        kind = "profile"
    if kind == "profile":
        entry = vocab.VocabularyEntry(entry_id="v1", canonical="Term",
                                      scope_kind="profile",
                                      scope_value=left, approved=True,
                                      enabled=True,
                                      aliases=(vocab.Alias(alias="term"),))
        return verdict({"distinct": not entry.scope_matches(
            vocab.ScopeContext(profile=right))})
    rule = _rule({"rule_id": "r:x", "scope_kind": kind, "scope_value": left,
                  "mode": "raw"})
    dest = prof.Destination(**{("site_origin" if kind == "site"
                                else "workspace"): right})
    return verdict({"no_rule_activated":
                    prof.resolve(None, [rule], dest).rule_id is None,
                    "m05_distinct": vocab.canonical_scope_value(kind, left)
                    != vocab.canonical_scope_value(kind, right)})


def _ctx_snap(bundle, category, *, site_origin=None, origin_source=None,
              workspace=None, document_url=None):
    from localflow.v2.context.snapshot import (ContextSnapshot as CtxSnap,
                                               FieldContext, TargetSnapshot)
    return CtxSnap(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=TargetSnapshot(target_snapshot_id=ids.new_id("tgt"),
                              app_bundle=bundle, app_name=bundle,
                              app_pid=42, category=category),
        field=FieldContext(role="AXTextArea", classification="text",
                           document_url=document_url),
        site_origin=site_origin, origin_source=origin_source,
        workspace=workspace)


@driver("M10-C023")
def heuristic_title_origin(c):
    s = c["setup"]
    h, *_ = harness()
    try:
        weak = h.d._m10_destination(_ctx_snap(
            s["app_bundle"], s["target_category"],
            site_origin=s["title_derived_origin"],
            origin_source="window_title"))
        strong = h.d._m10_destination(_ctx_snap(
            s["app_bundle"], s["target_category"],
            site_origin=s["title_derived_origin"], origin_source="ax_url"))
    finally:
        h.close()
    rule = _rule({"rule_id": "r:site", "scope_kind": "site",
                  "scope_value": s["title_derived_origin"], "mode": "raw"})
    return verdict({
        "no_site_rule_from_title": prof.resolve(None, [rule], weak).rule_id
        is None,
        "no_ai_prompt_from_title": weak.category != "ai_prompt",
        "positive_authoritative_ai_prompt": strong.category == "ai_prompt"},
        {"weak": dataclasses.asdict(weak),
         "strong": dataclasses.asdict(strong)})


@driver("M10-C024")
def ai_origin_case(c):
    cats = [prof.derive_category("browser", "com.example.browser", o)
            for o in c["setup"]["origins"]]
    unknown = prof.derive_category("browser", "com.example.browser",
                                   "https://unknown.example")
    return verdict({"both_ai_prompt": cats == ["ai_prompt", "ai_prompt"],
                    "unknown_uncategorized": unknown is None},
                   {"categories": cats})


@driver("M10-C025")
def profile_name_admission(c):
    refused = []
    for name in ("", "   "):
        try:
            prof.StyleRule(rule_id="r", name="n", profile_name=name)
        except ValueError:
            refused.append(name)
    uni = prof.StyleRule(rule_id="r", name="n", profile_name="Synthetic Ω")
    h, *_ = harness()
    try:
        a = h.d._styles.add_rule(name="A", profile_name="WritingA")
        b = h.d._styles.add_rule(name="B", scope_kind="app",
                                 scope_value="com.example.b",
                                 profile_name="WritingA")
        h.d._styles.update_rule(a, name="Renamed display only")
        rules = {r.rule_id: r for r in h.d._styles.rules()}
        h.d._styles.delete_rule(b)
        after = [r.rule_id for r in h.d._styles.rules()]
    finally:
        h.close()
    return verdict({
        "empty_and_blank_refused": refused == ["", "   "],
        "unicode_exact": uni.profile_name == "Synthetic Ω",
        "duplicate_name_is_one_identity":
            rules[a].profile_name == rules[b].profile_name == "WritingA",
        "rename_keeps_profile_identity":
            rules[a].profile_name == "WritingA",
        "delete_leaves_other": after == [a]})


# ---- per-job override / raw / number policy (the real coordinator) ------------

NUM = "we retried three times today"
NUM_TECH = "we retried 3 times today"


@driver("M10-C026")
def override_once(c):
    h, sup, _ = harness()
    try:
        h.d.hubSetNextJobMode("raw")
        clean_calls = []
        real = sup.clean
        sup.clean = lambda **k: (clean_calls.append(1), real(**k))[1]
        ta, ja = run_job(h, NUM)
        a_clean = len(clean_calls)
        tb, jb = run_job(h, NUM)
    finally:
        h.close()
    return verdict({"a_raw": ta == NUM and ja["m10"]["wp"].effective_mode
                    == "raw",
                    "a_no_cleanup": a_clean == 0,
                    "b_ordinary_clean": tb == NUM_TECH and len(clean_calls)
                    == 1})


@driver("M10-C027", "M10-C218")
def override_fault(c):
    h, *_ = harness()
    barriers = []
    try:
        h.d.hubSetNextJobMode("raw")
        real_take = h.d._take_next_job_mode

        def take(job_id=None):
            mode = real_take(job_id)
            barriers.append("next-mode taken")
            return mode
        h.d._take_next_job_mode = take
        real_rev = h.d._tf_store.revision

        def boom():
            barriers.append("before M10 snapshot return")
            raise RuntimeError("synthetic transform snapshot fault")
        h.d._tf_store.revision = boom
        ta, ja = run_job(h, NUM)
        h.d._tf_store.revision = real_rev
        h.d._take_next_job_mode = real_take
        tb, jb = run_job(h, NUM)
        owners = [ln for ln in w.app_events(h) if "override_taken" in ln]
    finally:
        h.close()
    return verdict({"raw_kept": ta == NUM,
                    "job_owned": ja.get("m10_override") == "raw",
                    "ownership_recorded_once": len(owners) == 1,
                    "b_ordinary": tb == NUM_TECH},
                   {"owner_events": len(owners)}, barriers)


@driver("M10-C028")
def recorder_start_failure(c):
    h, *_ = harness()
    try:
        h.d.hubSetNextJobMode("raw")
        real = h.d.recorder.start
        fails = {"n": 0}

        def start():
            if fails["n"] == 0:
                fails["n"] += 1
                raise OSError("synthetic recorder start failure")
            return real()
        h.d.recorder.start = start
        h.hk.held = True
        h.hk.on_press()                 # refused before admission
        h.hk.held = False
        h.hk.on_release()
        pending_after_fail = h.d._next_job_mode
        ta, _ = run_job(h, NUM)
    finally:
        h.close()
    return verdict({"not_consumed_by_failed_start":
                    pending_after_fail == "raw",
                    "healthy_capture_raw": ta == NUM})


@driver("M10-C029", "M10-C207")
def cancelled_capture(c):
    h, *_ = harness()
    barriers = []
    try:
        h.d.hubSetNextJobMode("raw")
        h.hk.held = True
        h.hk.on_press()
        barriers.append("A override ownership recorded"
                        if h.d._job and h.d._job.get("m10_override") == "raw"
                        else "A ownership missing")
        h.d.cancelDictation()
        pending = h.d._next_job_mode
        h.hk.held = False
        inserted_a = list(h.d._insertion.pastes)
        # FakeRecorder pops a duration per stop(); A's stop consumed one.
        tb, _ = run_job(h, NUM)
    finally:
        h.close()
    return verdict({"a_no_insertion": inserted_a == [],
                    "a_consumed_at_capture_boundary": pending is None,
                    "b_ordinary": tb == NUM_TECH},
                   barriers=barriers)


@driver("M10-C030")
def short_capture(c):
    sup = w.M10Supervisor(NUM)
    ctx = w.FakeContextCollector("com.example.editor", "editor")
    h = w.Harness([0.05, 1.0], supervisor=sup, context=ctx)
    try:
        h.d.hubSetNextJobMode("raw")
        h.press_release()               # below min_duration_sec: discarded
        pending = h.d._next_job_mode
        a_pastes = list(h.d._insertion.pastes)
        tb, _ = run_job(h, NUM, deliver=True)
        pastes = list(h.d._insertion.pastes)
    finally:
        h.close()
    return verdict({"no_a_insertion": a_pastes == [],
                    "only_b_inserted": pastes == [NUM_TECH],
                    "consumed_by_a": pending is None,
                    "b_not_raw_again": tb == NUM_TECH})


@driver("M10-C031")
def identity_failure(c):
    h, sup, ctx = harness()
    try:
        def boom():
            raise RuntimeError("synthetic identity failure")
        ctx.capture_identity = boom
        h.d.hubSetNextJobMode("raw")
        ta, ja = run_job(h, NUM)
    finally:
        h.close()
    return verdict({"raw_kept": ta == NUM,
                    "no_other_destination": ja["m10"]["wp"].rule_id is None})


@driver("M10-C032")
def second_start_refused(c):
    h, *_ = harness()
    barriers = []
    try:
        h.d.hubSetNextJobMode("raw")
        h.hk.held = True
        h.hk.on_press()
        barriers.append("A admission")
        job_a = h.d._job
        h.d.startDictation()            # the exposed API path while A owns
        barriers.append("B start attempt")
        same_owner = h.d._job is job_a
        h.d.supervisor.asr_text = NUM
        h.hk.held = False
        h.hk.on_release()
        _fn, (ta, ja) = h.run_coordinator()
        owners = [ln for ln in w.app_events(h) if "override_taken" in ln]
    finally:
        h.close()
    return verdict({"one_owner": len(owners) == 1,
                    "no_second_admission": same_owner,
                    "a_raw": ta == NUM}, barriers=barriers)


@driver("M10-C033", "M10-C187")
def worker_retry_keeps_tuple(c):
    """The supervisor's internal retry (a crashed attempt 1, attempt 2
    answering): between the two the store changes (registry B) and a new
    next-mode is set; the job answers from its frozen tuple and the
    pending mode waits for the next admitted capture."""
    h, sup, _ = harness()
    barriers = []
    try:
        sid = h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                          content="OLD")
        real = sup.transcribe

        def crashed_then_retried(**k):
            barriers.append("attempt 1 crashed")
            if c["id"] == "M10-C033":
                h.d.hubSetNextJobMode("raw")
            h.d._snip_store.update_snippet(sid, content="NEW")
            out = real(**k)
            out["attempt"] = 2
            barriers.append("attempt 2 answered")
            return out
        sup.transcribe = crashed_then_retried
        ta, ja = run_job(h, "quick reply")
        pending = h.d._next_job_mode
        used = h.d.store.submit(lambda db: db.execute(
            "SELECT usage_count FROM snippets").fetchone()[0])
        sup.transcribe = real
        tb, jb = run_job(h, "quick reply")
    finally:
        h.close()
    return verdict({"a_keeps_captured_tuple": ta == "OLD"
                    and ja["m10"]["wp"].mode == "clean",
                    "retry_attempt_recorded": ja.get("attempt") == 2,
                    "pending_left_for_next": (pending == "raw")
                    if c["id"] == "M10-C033" else pending is None,
                    "single_usage": used == 1,
                    "next_job_sees_b": tb == ("quick reply"
                                              if c["id"] == "M10-C033"
                                              else "NEW")},
                   {"attempt": ja.get("attempt")}, barriers)


@driver("M10-C034")
def restart_no_persistence(c):
    h, *_ = harness()
    try:
        h.d.hubSetNextJobMode("raw")
        d2 = app_mod.AppDelegate.alloc().init()
        d2.configure(dict(w.CFG))
        fresh = d2._next_job_mode
        d2.store.sync()
        d2.store.close()
        d2.v2log.close()
    finally:
        h.close()
    return verdict({"no_persisted_one_shot": fresh is None})


@driver("M10-C035")
def raw_skips(c):
    rem.c27_raw_skips_every_m10_stage()
    return Outcome("PASS", {"delegated": "c27_raw_skips_every_m10_stage"})


@driver("M10-C036")
def raw_beats_transform(c):
    import test_transform_pipeline as tp
    sup = tp.M11Supervisor("hello there")
    ctx = w.FakeContextCollector("com.example.editor", "editor")
    h = w.Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
        h.d.hubSetNextJobMode("raw")
        text, job = run_job(h, "hello there")
    finally:
        h.close()
    return verdict({"no_transform_call": sup.transform_calls == [],
                    "raw_text": text == "hello there",
                    "no_transform_evidence": job.get("transform_result")
                    is None})


@driver("M10-C037")
def clean_positive(c):
    rem.c27_clean_positive_expands_once()
    return Outcome("PASS", {"delegated": "c27_clean_positive_expands_once"})


@driver("M10-C038", "M10-C039", "M10-C040")
def number_policy(c):
    s = c["setup"]
    h, *_ = harness(bundle="com.microsoft.VSCode", category="ide",
                    workspace="ProjectA")
    try:
        h.d._styles.add_rule(name="ws", scope_kind="workspace",
                             scope_value="ProjectA",
                             number_policy=s["rule"]["number_policy"])
        text, job = run_job(h, "twelve retries")
    finally:
        h.close()
    np = s["rule"]["number_policy"]
    want = {"inherit": "12 retries", "technical": "12 retries",
            "standard": "twelve retries"}[np]
    return verdict({
        "profile_and_policy_same_rule": job["m10"]["wp"].number_policy
        == np and job["norm_policy"].profile == (
            "technical" if np == "inherit" else np),
        "output": text == want}, {"text": text})


@driver("M10-C041")
def failed_widening_tuple(c):
    h, *_ = harness(bundle="com.microsoft.VSCode", category="ide",
                    workspace="ProjectB")
    try:
        h.d._styles.add_rule(name="A", scope_kind="app",
                             scope_value="com.microsoft.VSCode",
                             profile_name="WritingA",
                             number_policy="standard")
        h.d._styles.add_rule(name="B", scope_kind="workspace",
                             scope_value="ProjectB",
                             profile_name="WritingB",
                             number_policy="technical")
        h.d._vocab.add_entry("BTerm", ["bee term"], scope_kind="profile",
                             scope_value="WritingB", approved=True)

        def boom(job, entries, scope):
            raise RuntimeError("synthetic vocabulary rebuild failure")
        h.d._widened_for_release = boom
        h.d.consent.set("enabled", note="test")
        text, job = run_job(h, "bee term twelve retries")
        _ex, env = w.latest_envelope(h.d.store)
    finally:
        h.close()
    wp = job["m10"]["wp"]
    return verdict({
        "disposition_failed": job.get("scope_disposition")
        == "widening_failed",
        "profile_a_and_standard": wp.profile_name == "WritingA"
        and wp.number_policy == "standard"
        and job["norm_policy"].profile == "standard",
        "b_vocabulary_absent": "BTerm" not in text,
        "evidence_names_used_tuple": env["profile"]["number_policy"]
        == "standard"}, {"text": text})


@driver("M10-C042")
def override_composition(c):
    rule = _rule({"rule_id": "r:app", "scope_kind": "app",
                  "scope_value": "com.example.editor", "mode": "raw",
                  "number_policy": "standard"})
    wp = prof.resolve("clean", [rule],
                      prof.Destination(app_bundle="com.example.editor"),
                      default_number_policy="inherit")
    # Current documented policy (kept): the override selects the mode
    # with the default number policy, not the destination rule's.
    return verdict({"override_mode": wp.effective_mode == "clean",
                    "default_policy_not_rule": wp.number_policy == "inherit"
                    and wp.rule_id is None}, {"profile": wp.to_json()})
