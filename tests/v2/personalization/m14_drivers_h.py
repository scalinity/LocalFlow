"""M14 corpus drivers, group h: entries graded from records rather than
driven in-process.

- ``hub_actions`` native cases (LF-M14-C211…C219) are graded from the
  owned-window suite's record (tests/v2/personalization/
  test_native_m14_training.py ``--json``), supplied to the runner as
  ``--native``: the check bound to the entry must have passed in a run
  that never became frontmost and left the frontmost app unchanged.
- ``performance_validity`` cases (LF-M14-C227…C234) are graded from the
  benchmark record supplied as ``--bench``: ``{"run": <m14.json of the
  full-scale run>, "noop": {component: <m14.json of a --noop
  --validate-only run>}}``. Speed is never graded here — only that the
  run did the declared work (the benchmark's own independent recount),
  that each no-op component is rejected before timing, that write waits
  and writer hold were measured apart from wall clock, and that the
  environment was recorded.

Without its record an entry is NOT_RUN, never PASS.
"""

from __future__ import annotations

from m14_drivers_common import BENCH, NATIVE, drives, check, result

_BENCH_COMPONENTS = ("mining", "note_mining", "profile", "sampling",
                     "splits", "export")


def _not_run(why):
    return result("NOT_RUN", note=why)


# ---- native owned-window checks ---------------------------------------------


@drives("LF-M14-C211", "LF-M14-C212", "LF-M14-C213", "LF-M14-C214",
        "LF-M14-C215", "LF-M14-C216", "LF-M14-C217", "LF-M14-C218",
        "LF-M14-C219")
def native_hub_action(entry):
    if not NATIVE:
        return _not_run("no native record supplied (--native)")
    bound = [(name, r) for name, r in (NATIVE.get("checks") or {}).items()
             if entry["id"] in (r.get("cases") or [])]
    if not bound:
        return _not_run("no native check bound to this entry")
    name, r = bound[0]
    observed = {"check": name, "check_status": r.get("status"),
                "never_frontmost": NATIVE.get("never_frontmost"),
                "frontmost_unchanged": NATIVE.get("frontmost_unchanged"),
                "suite_sha256": (NATIVE.get("code") or {}).get(
                    "suite_sha256"),
                "code_root_sha": (NATIVE.get("code") or {}).get(
                    "code_root_sha")}
    out = check({"check_passed": r.get("status") == "PASS",
                 "never_frontmost": NATIVE.get("never_frontmost") is True,
                 "frontmost_unchanged":
                     NATIVE.get("frontmost_unchanged") is True},
                observed, witness=f"native record check {name}")
    out["grading"] = "native"
    if r.get("status") != "PASS" and r.get("note"):
        out["note"] = f"{out.get('note')} | {r['note']}"[:400]
    return out


# ---- performance validity ---------------------------------------------------


def _run():
    run = BENCH.get("run")
    return run if isinstance(run, dict) else None


def _bench(entry, conds_fn):
    run = _run()
    if run is None:
        return _not_run("no benchmark record supplied (--bench)")
    work = (run.get("validity") or {}).get("work") or {}
    conds, observed = conds_fn(run, work, run.get("results") or {})
    out = check({"run_valid": run.get("status") == "valid",
                 "full_scale": run.get("scale") == "full", **conds},
                observed, witness="benchmark record")
    out["grading"] = "benchmark"
    return out


@drives("LF-M14-C227")
def perf_positive_10k(entry):
    def conds(run, work, res):
        st, prof = work.get("store") or {}, work.get("profile") or {}
        return ({"ten_thousand_rows": st.get("example_rows") == 10_000
                 == st.get("expected_examples"),
                 "audio_rows": st.get("audio_artifacts")
                 == st.get("expected_audio"),
                 "eligible_recount": prof.get("eligible_examples")
                 == prof.get("expected_examples")},
                {"store": st, "profile": prof})
    return _bench(entry, conds)


@drives("LF-M14-C228")
def perf_mining_1k(entry):
    def conds(run, work, res):
        m = work.get("mining") or {}
        sizes = run.get("sizes") or {}
        return ({"thousand_observations": sizes.get("observations") == 1000,
                 "changed_mined": m.get("candidates")
                 == m.get("expected_candidates")
                 == 1000 - sizes.get("unchanged_observations", -1),
                 "unchanged_dismissed": m.get("dismissed")
                 == m.get("expected_dismissed"),
                 "timed": "mining_observations" in res},
                {"mining": m, "sizes": sizes})
    return _bench(entry, conds)


@drives("LF-M14-C229")
def perf_note_mining(entry):
    def conds(run, work, res):
        n = work.get("note_mining") or {}
        t = res.get("note_mining") or {}
        return ({"minted_equals_typed_corrections":
                 n.get("candidates") == n.get("expected")
                 and bool(n.get("expected")),
                 "wall_and_writer_separate":
                 bool((t.get("wall") or {}).get("n"))
                 and (t.get("writer_hold") or {}).get("n") is not None},
                {"note_mining": n, "timing": t})
    return _bench(entry, conds)


@drives("LF-M14-C230")
def perf_sampling_splits(entry):
    def conds(run, work, res):
        sm, sp = work.get("sampling") or {}, work.get("splits") or {}
        return ({"decisions_recounted": sm.get("decisions")
                 == sm.get("expected_decisions"),
                 "families_recounted": sp.get("memberships") == sp.get(
                     "expected") and (sp.get("expected") or 0) >= 10,
                 "timed": "sampling_refresh" in res
                 and "split_assign" in res},
                {"sampling": sm, "splits": sp})
    return _bench(entry, conds)


@drives("LF-M14-C231")
def perf_audio_export(entry):
    def conds(run, work, res):
        ex = work.get("export") or {}
        t = res.get("export_asr_cleanup") or {}
        return ({"rows_recounted": ex.get("asr_supervised")
                 == ex.get("expected_asr")
                 and ex.get("cleanup_supervised")
                 == ex.get("expected_cleanup"),
                 "bytes_on_disk_measured": ex.get("audio_bytes_on_disk")
                 == ex.get("expected_audio_bytes")
                 and bool(ex.get("expected_audio_bytes")),
                 "validator_valid": ex.get("validator_valid") is True
                 and (res.get("validate") or {}).get("valid") is True,
                 "dataset_bytes_measured": bool(t.get("dataset_bytes"))},
                {"export": ex, "dataset_bytes": t.get("dataset_bytes")})
    return _bench(entry, conds)


@drives("LF-M14-C232")
def perf_noop_components(entry):
    noop = BENCH.get("noop")
    if not isinstance(noop, dict) or not noop:
        return _not_run("no no-op validity records supplied (--bench)")
    observed, conds = {}, {}
    for comp in _BENCH_COMPONENTS:
        rec = noop.get(comp) or {}
        reasons = (rec.get("validity") or {}).get("reasons") or []
        observed[comp] = {"status": rec.get("status"), "reasons": reasons,
                          "timed": rec.get("results") is not None}
        conds[f"{comp}_rejected_before_timing"] = (
            rec.get("status") == "INVALID" and rec.get("noop") == comp
            and rec.get("results") is None and bool(reasons))
    out = check(conds, observed, witness="benchmark --noop records")
    out["grading"] = "benchmark"
    return out


@drives("LF-M14-C233")
def perf_writer_probe(entry):
    def conds(run, work, res):
        timed = {k: v for k, v in res.items()
                 if isinstance(v, dict) and "probe_wait" in v}
        return ({"components_probed": len(timed) >= 8,
                 "probe_samples_every_component": all(
                     (v["probe_wait"] or {}).get("n", 0) > 0
                     for v in timed.values()),
                 "writer_hold_every_component": all(
                     (v.get("writer_hold") or {}).get("n", 0) > 0
                     for v in timed.values())},
                {k: {"wall_p95": v["wall"].get("p95_ms"),
                     "probe_max": v["probe_wait"].get("max_ms"),
                     "hold_max": v["writer_hold"].get("max_ms")}
                 for k, v in timed.items()})
    return _bench(entry, conds)


@drives("LF-M14-C234")
def perf_environment(entry):
    def conds(run, work, res):
        env = run.get("environment") or {}
        keys = ("code_sha", "mac_model", "cpu", "memory_bytes", "macos",
                "python", "sqlite", "power", "load_average")
        return ({"environment_complete": all(env.get(k) not in (None, "")
                                             for k in keys),
                 "exact_code_sha": isinstance(env.get("code_sha"), str)
                 and len(env["code_sha"]) == 40,
                 "clean_tree": env.get("tree_modified") is False,
                 "warm_state_declared": bool(
                     (run.get("definitions") or {}).get("warm_state")),
                 "counts_declared": bool(run.get("sizes"))},
                {k: env.get(k) for k in keys + ("tree_modified",)})
    return _bench(entry, conds)
