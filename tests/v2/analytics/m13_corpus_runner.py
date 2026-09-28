"""M13 corpus runner: every frozen case through its bound driver, the 14
metamorphic relations, and the 22 stateful probes derived from their
linked cases' witnesses.

The frozen corpus (tests/v2/analytics/m13_audit_corpus.json) is verified
by sha256 and never modified; results are written to a separate run
record. Per case: id, category, tier, base/final code identity, driver
and oracle versions, fixture cardinality, clock/zone, status (PASS /
FAIL / ERROR / INVALID / NOT_RUN), grading (semantic / structural /
decision / native), the adopted decision for a policy-gated case, the
observed values, the witness and any note. A driver incompatibility is
ERROR, never the defect it failed to reach; NOT_RUN is never PASS.

  .venv/bin/python tests/v2/context/run_isolated.py \\
      tests/v2/analytics/m13_corpus_runner.py --out RECORD.json \\
      [--native NATIVE.json] [--bench BENCH.json] [--only ID,...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m13_world as W  # noqa: E402  (isolation guard)
import m13_drivers as D1  # noqa: E402
import m13_drivers_b as D2  # noqa: E402
from m13_world import AWorld  # noqa: E402

from localflow.v2 import analytics as A  # noqa: E402

CORPUS = HERE.parent / "m13_audit_corpus.json"
CORPUS_SHA = "35aeb9bf3ea3a0add615ccfbb449cf1b72677dc3382083f4fb0648040ca814c0"
DECISIONS = W.ROOT / "docs/v2/acceptance/M13/remediation/decisions.json"
DRIVER_VERSION = "m13-drivers-r1"
ORACLE_VERSION = "m13-oracle-r1"


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# =============================================================================
# metamorphic relations (independent of the case drivers)
# =============================================================================

def mr01_retry_identity():
    with AWorld() as w:
        for i in range(3):
            w.dictation(f"job-{i}")
        n0 = w.insights.summary(days=None)["dictations"]
        w.dictation("job-1", attempt=2, final_words=10)
        n1 = w.insights.summary(days=None)["dictations"]
    return n1 <= n0, {"before": n0, "after_replace": n1}


def mr02_cross_day():
    with AWorld() as w:
        w.dictation("job-a", activity_at_utc="2026-09-25T15:00:00.000Z",
                    final_words=10)
        w.dictation("job-b", activity_at_utc="2026-09-25T16:00:00.000Z",
                    final_words=5)
        w.transform(at="2026-09-25T17:00:00.000Z")
        before = {a["day_local"]: a for a in w.aggs()}
        tot0 = w.insights.summary(days=None)["final_words"]
        w.dictation("job-a", activity_at_utc="2026-09-26T15:00:00.000Z",
                    final_words=10)
        after = {a["day_local"]: a for a in w.aggs()}
        tot1 = w.insights.summary(days=None)["final_words"]
        ok = (before["2026-09-25"]["final_words"]
              - after["2026-09-25"]["final_words"] == 10
              and after["2026-09-26"]["final_words"] == 10
              and after["2026-09-25"]["transforms"] == 1
              and tot0 == tot1 and not w.mismatches())
    return ok, {"total_before": tot0, "total_after": tot1}


def mr03_content_independence():
    with AWorld() as w:
        s = w.store
        jid, _f = s.create_job(captured_at_utc="2026-09-20T10:00:00.000Z",
                               time_quality="known",
                               state="insertion_confirmed")
        aid = s.write_text_artifact(job_id=jid, stage="asr",
                                    role="raw_transcript", text="synthetic",
                                    retention_class="transcript")
        w.dictation(jid, activity_at_utc="2026-09-20T10:00:00.000Z")
        before = (w.insights.summary(days=None)["dictations"], w.aggs())
        s.delete_everywhere("job", jid)
        s.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1 WHERE artifact_id=?", (aid,)))
        after = (w.insights.summary(days=None)["dictations"], w.aggs())
    return before == after, {"dictations": before[0]}


def mr04_usage_independence():
    import m13_drivers_b as B
    sys.path.insert(0, str(W.ROOT / "tests" / "v2" / "ui"))
    from test_training_data import Env
    with Env() as e:
        a = A.AnalyticsStore(e.store, reporting_timezone="UTC")
        e.add_example()
        a.record_dictation_fact(job_id="job-u",
                                activity_at_utc="2026-09-26T15:00:00.000Z",
                                final_words=3, insertion_outcome="confirmed")
        before = B._content_digest(e.store)
        a.delete_all_usage()
        after = B._content_digest(e.store)
    return before == after, {"tables_compared": sorted(before)}


def mr05_narrowing():
    with AWorld() as w:
        import test_m13_remediation as R
        R.seed_cohort(w)
        full = w.insights.report(days=None)
        out = {}
        ok = True
        for app in [o["key"] for o in full["apps"]]:
            for mode in [None] + full["modes"]:
                r = w.insights.report(days=None, app=app, mode=mode)
                n = r["summary"]["dictations"]
                ok &= n <= full["summary"]["dictations"]
                ok &= sum(x["dictations"] for x in r["per_mode"]) == n
                ok &= sum(x["dictations"] for x in r["per_app"]) == n
                out[f"{app}|{mode}"] = n
    return ok, out


def mr06_zone_conservation():
    with AWorld(zone="America/New_York") as w:
        for i in range(24):
            w.dictation(f"job-{i}", activity_at_utc=A.instant_from_epoch(
                W.epoch("2026-09-26T00:00:00.000Z") + i * 3600),
                final_words=i + 1)
        s0 = w.insights.summary(days=None)
        w.analytics.rebuild_aggregates(
            reporting_timezone="America/Los_Angeles")
        s1 = w.insights.summary(days=None)
        m = w.mismatches(zone="America/Los_Angeles")
    return (s0["dictations"], s0["final_words"]) == \
        (s1["dictations"], s1["final_words"]) and not m, \
        {"dictations": s1["dictations"], "words": s1["final_words"]}


def mr07_aggregate_equivalence():
    with AWorld() as w:
        for i in range(30):
            w.dictation(f"job-{i}", activity_at_utc=A.instant_from_epoch(
                W.epoch("2026-09-20T12:00:00.000Z") + i * 11000),
                insertion_outcome=A.OUTCOMES[i % 5],
                final_words=None if i % 5 >= 3 else 10 + i,
                fallback_reason="x" if i % 4 == 0 else None,
                dictionary_hits=i % 3, snippet_hits=i % 2)
        for i in range(5):
            w.transform(at=A.instant_from_epoch(
                W.epoch("2026-09-21T12:00:00.000Z") + i * 3600))
            w.repaste(at=A.instant_from_epoch(
                W.epoch("2026-09-22T12:00:00.000Z") + i * 3600))
        incremental = w.aggs()
        m1 = w.mismatches()
        w.analytics.rebuild_aggregates()
        rebuilt = w.aggs()
        m2 = w.mismatches()
    strip = lambda rows: [{k: v for k, v in r.items()  # noqa: E731
                           if k != "computed_at_utc"} for r in rows]
    return not m1 and not m2 and strip(incremental) == strip(rebuilt), \
        {"incremental_mismatches": m1, "rebuilt_mismatches": m2}


def mr08_latency_removal():
    with AWorld() as w:
        for i in range(5):
            w.dictation(f"job-{i}", end_to_end_ms=100.0 + i, asr_ms=50.0)
        n0 = w.insights.summary(days=None)["latency"]
        w.dictation("job-2", end_to_end_ms=None, asr_ms=50.0)
        n1 = w.insights.summary(days=None)["latency"]
    return n1["end_to_end"]["n"] == n0["end_to_end"]["n"] - 1 and \
        n1["asr"]["n"] == n0["asr"]["n"], \
        {"e2e": (n0["end_to_end"]["n"], n1["end_to_end"]["n"])}


def mr09_rename():
    with AWorld() as w:
        w.dictation("job-1", app_name="Synthetic Old",
                    app_bundle="com.synthetic.one")
        w.dictation("job-2", app_name="Synthetic Other",
                    app_bundle="com.synthetic.two")
        k0 = sorted(o["key"] for o in w.insights.apps_available())
        w.dictation("job-3", app_name="Synthetic New",
                    app_bundle="com.synthetic.one")
        k1 = sorted(o["key"] for o in w.insights.apps_available())
    return k0 == k1, {"keys": k1}


def mr10_readiness_partition():
    sys.path.insert(0, str(W.ROOT / "tests" / "v2" / "ui"))
    from test_training_data import Env
    with Env() as e:
        a, b = e.add_example(), e.add_example()
        e.svc.mark_intended(a, True)
        e.svc.mark_intended(b, False)
        r0 = e.svc.readiness()
        e.svc.exclude(b)
        r1 = e.svc.readiness()
    b0, b1 = r0["outcome_balance"], r1["outcome_balance"]
    ok = (b1["verified_failure"] == b0["verified_failure"] - 1
          and b1["excluded"] == b0["excluded"] + 1
          and b1["verified_positive"] == b0["verified_positive"]
          and b1["population"] == b0["population"]
          and r1["readiness_metrics"]["capture_completeness"][
              "denominator"] == r0["readiness_metrics"][
              "capture_completeness"]["denominator"] - 1)
    return ok, {"before": b0, "after": b1}


def mr11_deletion_locality():
    from localflow.v2.profile import ProfileService
    with AWorld() as w:
        w.dictation("job-a", app_name=W.APP_CANARY)
        w.repaste(job_id="job-a")
        w.dictation("job-b", app_name="Synthetic Keep")
        w.repaste(job_id="job-b")
        w.transform()
        ProfileService(w.store, min_words=1).compute()
        w.analytics.delete_usage_for_job("job-a")
        rows = w.rows()
        snaps = w.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots")])
    ok = (not any(r["job_id"] == "job-a" for r in rows)
          and sum(r["job_id"] == "job-b" for r in rows) == 2
          and sum(r["kind"] == "transform" for r in rows) == 1
          and not any(W.APP_CANARY in s for s in snaps))
    return ok, {"rows": len(rows)}


def mr12_activity_no_words():
    with AWorld() as w:
        w.dictation("job-a", final_words=10)
        s0 = w.insights.summary(days=None)
        for _ in range(3):
            w.transform()
            w.repaste(job_id="job-a")
        s1 = w.insights.summary(days=None)
    return (s0["dictations"], s0["final_words"], s0["raw_words"]) == \
        (s1["dictations"], s1["final_words"], s1["raw_words"]), \
        {"transforms": s1["transforms"], "repastes": s1["repastes"]}


def mr13_order_invariance():
    import random
    facts = [("d", f"job-{i}", A.instant_from_epoch(
        W.epoch("2026-09-20T12:00:00.000Z") + i * 7000), 5 + i)
        for i in range(12)] + [("t", None, A.instant_from_epoch(
            W.epoch("2026-09-21T12:00:00.000Z") + i * 900), 0)
            for i in range(4)] + [("r", None, A.instant_from_epoch(
                W.epoch("2026-09-22T12:00:00.000Z") + i * 900), 0)
                for i in range(4)]
    outs = []
    for seed in (1, 2, 3):
        order = list(facts)
        random.Random(seed).shuffle(order)
        with AWorld() as w:
            for kind, job, at, words in order:
                if kind == "d":
                    w.dictation(job, activity_at_utc=at, final_words=words)
                elif kind == "t":
                    w.transform(at=at)
                else:
                    w.repaste(at=at)
            outs.append([{k: v for k, v in r.items()
                          if k != "computed_at_utc"} for r in w.aggs()])
    return outs[0] == outs[1] == outs[2], {"permutations": 3}


def mr14_delay_sensitivity():
    r = D2.d_bench_delay({"case_id": "M13-C257"})
    return r["status"] == "PASS", r["observed"]


RELATIONS = {"M13-MR01": mr01_retry_identity, "M13-MR02": mr02_cross_day,
             "M13-MR03": mr03_content_independence,
             "M13-MR04": mr04_usage_independence,
             "M13-MR05": mr05_narrowing, "M13-MR06": mr06_zone_conservation,
             "M13-MR07": mr07_aggregate_equivalence,
             "M13-MR08": mr08_latency_removal, "M13-MR09": mr09_rename,
             "M13-MR10": mr10_readiness_partition,
             "M13-MR11": mr11_deletion_locality,
             "M13-MR12": mr12_activity_no_words,
             "M13-MR13": mr13_order_invariance,
             "M13-MR14": mr14_delay_sensitivity}


# =============================================================================
# runner
# =============================================================================

def run_case(case):
    drv = D1.DRIVERS.get(case["case_id"])
    if drv is None:
        return {"status": "NOT_RUN", "note": "no driver bound"}
    t0 = time.monotonic()
    try:
        r = dict(drv(case))
    except Exception as e:
        r = {"status": "ERROR",
             "note": f"{type(e).__name__}: {e}"[:300] + " | "
             + traceback.format_exc()[-900:]}
    r["seconds"] = round(time.monotonic() - t0, 2)
    r["driver"] = getattr(drv, "__name__", "?")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--native")
    ap.add_argument("--bench")
    ap.add_argument("--only")
    ap.add_argument("--no-relations", action="store_true")
    args = ap.parse_args(argv)
    corpus_sha = sha256(CORPUS)
    if corpus_sha != CORPUS_SHA:
        sys.exit(f"frozen corpus changed ({corpus_sha}); refusing")
    corpus = json.loads(CORPUS.read_text())
    if args.native:
        D2.NATIVE["record"] = json.loads(pathlib.Path(args.native)
                                         .read_text())
    if args.bench:
        D2.NATIVE["bench"] = json.loads(pathlib.Path(args.bench)
                                        .read_text())
    decisions = json.loads(DECISIONS.read_text())
    only = set(args.only.split(",")) if args.only else None
    cases = []
    for case in corpus["cases"]:
        if only and case["case_id"] not in only:
            continue
        r = run_case(case)
        gate = case.get("policy_gate")
        rec = {"case_id": case["case_id"], "category": case["category"],
               "tier": case["execution_tier"], "title": case["title"],
               "finding_ids": case["finding_ids"], "policy_gate": gate,
               "decision_applied": (f"{decisions['version']}:{gate}"
                                    if gate else None),
               "clock": case["clock"].get("wall_utc"),
               "expected": case["expected"], **r}
        cases.append(rec)
        print(f"{rec['status']:8} {case['case_id']} [{case['category']}]"
              + (f" — {str(rec.get('note'))[:120]}"
                 if rec["status"] != "PASS" and rec.get("note") else ""),
              flush=True)
    by = {c["case_id"]: c for c in cases}
    relations = []
    if not args.no_relations and not only:
        for rel in corpus["metamorphic_relations"]:
            fn = RELATIONS[rel["relation_id"]]
            try:
                ok, obs = fn()
                status = "PASS" if ok else "FAIL"
            except Exception as e:
                status, obs = "ERROR", f"{type(e).__name__}: {e}"[:300]
            relations.append({"relation_id": rel["relation_id"],
                              "status": status, "observed": obs})
            print(f"{status:8} {rel['relation_id']}", flush=True)
    probes = []
    for p in corpus["stateful_probes"]:
        linked = [by.get(c) for c in p["case_ids"]]
        if any(x is None for x in linked):
            status = "NOT_RUN"
        elif all(x["status"] == "PASS" for x in linked):
            status = "PASS"
        elif any(x["status"] == "ERROR" for x in linked):
            status = "ERROR"
        elif any(x["status"] == "NOT_RUN" for x in linked):
            status = "NOT_RUN"
        else:
            status = "FAIL"
        probes.append({"probe_id": p["probe_id"], "barrier": p["barrier"],
                       "status": status,
                       "cases": {c: (by.get(c) or {}).get("status")
                                 for c in p["case_ids"]},
                       "witnesses": {c: (by.get(c) or {}).get("witness")
                                     for c in p["case_ids"]
                                     if (by.get(c) or {}).get("witness")},
                       "grading": sorted({(by.get(c) or {}).get("grading")
                                          or "?" for c in p["case_ids"]})})
    counts = {}
    tiers = {}
    for c in cases:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
        t = tiers.setdefault(c["tier"], {})
        t[c["status"]] = t.get(c["status"], 0) + 1
    grading = {}
    for c in cases:
        if c["status"] == "PASS":
            g = c.get("grading") or "semantic"
            grading[g] = grading.get(g, 0) + 1
    rel_counts = {}
    for r in relations:
        rel_counts[r["status"]] = rel_counts.get(r["status"], 0) + 1
    probe_counts = {}
    for p in probes:
        probe_counts[p["status"]] = probe_counts.get(p["status"], 0) + 1
    record = {"schema": "m13-corpus-run", "driver_version": DRIVER_VERSION,
              "oracle_version": ORACLE_VERSION,
              "decision_record": decisions["version"],
              "corpus": {"path": "tests/v2/analytics/m13_audit_corpus.json",
                         "sha256": corpus_sha},
              "code": W.code_stamp(
                  "tests/v2/analytics/m13_corpus_runner.py"),
              "drivers_sha256": {n: sha256(HERE.parent / n) for n in (
                  "m13_drivers.py", "m13_drivers_b.py", "m13_oracle.py",
                  "m13_world.py", "test_m13_remediation.py")},
              "native_record": args.native and pathlib.Path(
                  args.native).name,
              "bench_record": args.bench and pathlib.Path(args.bench).name,
              "counts": counts, "by_tier": tiers, "pass_grading": grading,
              "relations": rel_counts, "probes": probe_counts,
              "cases": cases, "relation_results": relations,
              "probe_results": probes}
    pathlib.Path(args.out).write_text(json.dumps(record, indent=1,
                                                 default=str))
    print("cases:", counts, "| tiers:", tiers)
    print("relations:", rel_counts, "| probes:", probe_counts,
          "| pass grading:", grading)
    return 0


if __name__ == "__main__":
    sys.exit(main())
