"""M05 benchmark: vocabulary retrieval and dictionary normalization with
a 10,000-entry dictionary (Spec S11/S30.1; milestone target P95 <= 25 ms
for the hot paths), with WORK VALIDITY checked before any timing is
believed (M05-AUDIT-16).

Every cohort's expected result is authored by the benchmark's own
generator — never by the code under test:

- cold_snapshot: store rows → VocabularySnapshot (one read + index
  build; the app caches it per revision) — informational;
- cached_retrieval: the per-job cost on a cache hit (the store revision
  read + selection over the cached snapshot) — gated;
- warm_selection / scoped_selection: RelevantVocabularySelector over the
  cached global / workspace-scoped snapshot (the per-job path: repeat
  selections on one snapshot are memoized); the selected and omitted
  entry ids must equal an independent ranking of the generator's data
  (pin, scope, recency, frequency, priority, id) — gated;
- fresh_selection / fresh_scoped_selection: the FIRST selection on each
  of several freshly built snapshots (built outside the timing), so
  every timed call does the real ranking, omission and identity work
  (review R9: a memo hit can never stand in for it) — same oracle —
  gated;
- scope_upgrade: the M06 finalize rebuild from the frozen entry set
  under the widened scope + selection + pre-decode packaging
  (disposition, request fields, retained JSON) — reported against the
  75 ms finalize bound, informational here;
- normalize_no_hit / normalize_positive: 500-word dictation with no
  alias / with authored alias occurrences — exact output text, edit
  count and rule ids must match — gated;
- stress: dense hits, overlapping multiword aliases, long aliases and a
  large shared-first-word bucket — exact oracles, timings informational.

Verdicts: ``work_invalid`` (exit 2) is decided before timing;
``budget_failed`` (exit 1) when a gated p95 exceeds 25 ms; ``pass``
(exit 0). Cloud numbers are algorithmic evidence only — never
reference-Mac latency (VERIFICATION.html M05 keeps that pending).

Run: .venv/bin/python scripts/v2/benchmark_m05.py [--out DIR]
     [--entries N] [--reps N] [--code-root DIR]
"""

import argparse
import json
import pathlib
import platform
import subprocess
import sys
import tempfile
import time

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=None,
                help="directory for the JSON report (default: none)")
ap.add_argument("--entries", type=int, default=10_000)
ap.add_argument("--reps", type=int, default=200)
ap.add_argument("--code-root", default=None,
                help="production tree to measure (default: this one)")
ARGS = ap.parse_args() if __name__ == "__main__" else ap.parse_args([])
ROOT = pathlib.Path(__file__).resolve().parents[2]
CODE = pathlib.Path(ARGS.code_root).resolve() if ARGS.code_root else ROOT
sys.path.insert(0, str(CODE))

from localflow.v2 import capabilities  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)
from localflow.v2.vocabulary import (  # noqa: E402
    RelevantVocabularySelector,
    ScopeContext,
    VocabularySnapshot,
)
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

BUDGET_MS = 25.0
FINALIZE_BOUND_MS = 75.0
LIMIT = 100
SCOPED_EVERY = 20          # every 20th entry is workspace-scoped
PINNED_EVERY = 250         # a few pinned entries (rank contrasts)
NOW = "2026-09-25T00:00:00Z"


def code(i: int) -> str:
    """Deterministic letters-only code (aliases are spoken word tokens)."""
    s, n = "", i
    while True:
        s = chr(ord("a") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


def spec(i: int) -> dict:
    """The generator's own record of entry i — the oracle's source."""
    scoped = i % SCOPED_EVERY == 0
    return {
        "entry_id": f"vocab-bench-{i:05d}",
        "canonical": f"Term{i:05d}",
        # Aliases share the first word "tirm": a 10k-entry shared-first
        # -word bucket the matcher must scan when "tirm" is spoken.
        "alias": "tirm " + code(i),
        "scope": ("workspace", "scope-a") if scoped else ("global", None),
        "pinned": i % PINNED_EVERY == 7,
        "priority": i % 5,
    }


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(int(len(xs) * p), len(xs) - 1)]


def timed(fn, reps):
    out = []
    val = None
    for _ in range(reps):
        t0 = time.monotonic()
        val = fn()
        out.append((time.monotonic() - t0) * 1000.0)
    return val, {"iterations": reps, "p50_ms": round(pct(out, .5), 3),
                 "p95_ms": round(pct(out, .95), 3),
                 "p99_ms": round(pct(out, .99), 3),
                 "max_ms": round(max(out), 3)}


def timed_each(fn, items):
    """timed() over distinct inputs: one call per item."""
    out = []
    val = None
    for it in items:
        t0 = time.monotonic()
        val = fn(it)
        out.append((time.monotonic() - t0) * 1000.0)
    return val, {"iterations": len(out), "p50_ms": round(pct(out, .5), 3),
                 "p95_ms": round(pct(out, .95), 3),
                 "p99_ms": round(pct(out, .99), 3),
                 "max_ms": round(max(out), 3)}


def expected_order(specs, workspace):
    """Independent ranking: pinned, scope precedence (workspace 4 >
    global 0), recency (none recorded), frequency (0), priority, then
    entry id ascending as the final tie-break."""
    rows = [s for s in specs
            if s["scope"][0] == "global"
            or (workspace and s["scope"][1] == workspace)]
    rows.sort(key=lambda s: s["entry_id"])
    rows.sort(key=lambda s: (1 if s["pinned"] else 0,
                             4 if s["scope"][0] == "workspace" else 0,
                             s["priority"]), reverse=True)
    return [s["entry_id"] for s in rows]


def build_store(td, specs):
    st = store_mod.Store(pathlib.Path(td) / "v2.db")
    vs = VocabularyStore(st)
    for s in specs:
        vs.add_entry(s["canonical"], [s["alias"]], scope_kind=s["scope"][0],
                     scope_value=s["scope"][1], pinned=s["pinned"],
                     priority=s["priority"], approved=True,
                     entry_id=s["entry_id"])
    return st, vs


def prose(n_words):
    base = ("the quick brown fox jumps over the lazy dog while the "
            "committee reviews the quarterly numbers and decides "
            "whether to postpone the offsite until everyone returns "
            "from vacation").split()
    return [base[i % len(base)] for i in range(n_words)]


def dictation_with_hits(specs, n_words, every):
    """(input, expected, expected rule ids): an alias of a GLOBAL entry
    every ``every`` words, authored with its canonical as the answer."""
    words = prose(n_words)
    glob = [s for s in specs if s["scope"][0] == "global"]
    inp, exp, rules = [], [], []
    k = 0
    for i, w in enumerate(words):
        if i % every == every - 1:
            s = glob[(k * 37) % len(glob)]
            k += 1
            inp.append(s["alias"])
            exp.append(s["canonical"])
            rules.append(s["entry_id"])
        else:
            inp.append(w)
            exp.append(w)
    return " ".join(inp), " ".join(exp), rules


def check_norm(label, snap, text, expected_text, expected_rules, reps,
               problems):
    ctx = ContextSnapshot(vocabulary=snap)
    pol = NormalizationPolicy()
    res, t = timed(lambda: normalize(text, pol, ctx), reps)
    got_rules = [e.rule_id for e in res.edits if e.cls == "vocabulary"]
    valid = res.text == expected_text and got_rules == expected_rules
    if not valid:
        problems.append(f"{label}: output/edits differ from the authored"
                        f" oracle ({len(got_rules)} vs"
                        f" {len(expected_rules)} edits)")
    return {**t, "words": len(text.split()),
            "expected_edits": len(expected_rules),
            "observed_edits": len(got_rules), "work_valid": valid}


def main():
    specs = [spec(i) for i in range(ARGS.entries)]
    problems = []
    reps = ARGS.reps
    with tempfile.TemporaryDirectory() as td:
        t0 = time.monotonic()
        st, vs = build_store(td, specs)
        build_s = time.monotonic() - t0

        snap, cold = timed(lambda: vs.snapshot(None), max(5, reps // 20))
        snap_ws, _ = timed(lambda: vs.snapshot(
            ScopeContext(workspace="scope-a")), 3)
        # Population checks (the snapshot is what the matcher uses).
        n_glob = sum(1 for s in specs if s["scope"][0] == "global")
        n_ws = len(specs) - n_glob
        if len(snap.match_index) != 2 * n_glob:
            problems.append("global snapshot matchable-alias population"
                            f" {len(snap.match_index)} != {2 * n_glob}")
        if len(snap_ws.match_index) != 2 * len(specs):
            problems.append("scoped snapshot population"
                            f" {len(snap_ws.match_index)} !="
                            f" {2 * len(specs)}")

        sel = RelevantVocabularySelector(LIMIT)
        hs, warm = timed(lambda: sel.select(snap, now_utc=NOW), reps)
        want = expected_order(specs, None)
        got = [t.entry_id for t in hs.terms]
        om = [o["entry_id"] for o in hs.omitted]
        if got != want[:LIMIT] or om != want[LIMIT:]:
            problems.append("warm selection membership/order differs from"
                            " the independent ranking")
        hs_s, scoped = timed(lambda: sel.select(snap_ws, now_utc=NOW), reps)
        want_s = expected_order(specs, "scope-a")
        got_s = [t.entry_id for t in hs_s.terms]
        om_s = [o["entry_id"] for o in hs_s.omitted]
        if got_s != want_s[:LIMIT] or om_s != want_s[LIMIT:]:
            problems.append("scoped selection membership/order differs"
                            " from the independent ranking")

        # Real selection work: the first select() on each fresh snapshot
        # (snapshots built before the clock starts; review R9).
        n_fresh = max(8, reps // 10)
        fresh = [VocabularySnapshot(snap.entries, None)
                 for _ in range(n_fresh)]
        hs_f, fresh_t = timed_each(
            lambda sn: sel.select(sn, now_utc=NOW), fresh)
        del fresh
        if [t.entry_id for t in hs_f.terms] != want[:LIMIT] \
                or [o["entry_id"] for o in hs_f.omitted] != want[LIMIT:]:
            problems.append("fresh selection membership/order differs"
                            " from the independent ranking")
        fresh_s = [VocabularySnapshot(snap.entries,
                                      ScopeContext(workspace="scope-a"))
                   for _ in range(n_fresh)]
        hs_fs, fresh_scoped_t = timed_each(
            lambda sn: sel.select(sn, now_utc=NOW), fresh_s)
        del fresh_s
        if [t.entry_id for t in hs_fs.terms] != want_s[:LIMIT] \
                or [o["entry_id"] for o in hs_fs.omitted] != want_s[LIMIT:]:
            problems.append("fresh scoped selection membership/order"
                            " differs from the independent ranking")

        def cached_job():
            vs.revision()                       # the per-job store read
            return sel.select(snap, now_utc=NOW)
        _, cached = timed(cached_job, reps)

        manifest = capabilities.asr_capability_manifest(
            "bench", model_revision="r1")

        def upgrade():
            up = VocabularySnapshot(snap.entries,
                                    ScopeContext(workspace="scope-a"))
            h = sel.select(up, now_utc=NOW)
            capabilities.hint_disposition(manifest, h)
            capabilities.asr_hint_request_fields(h, manifest,
                                                 context_snapshot_id="c")
            json.dumps(h.to_json(), ensure_ascii=False, sort_keys=True)
            return up, h
        (up, hs_up), upgrade_t = timed(upgrade, max(5, reps // 20))
        if [t.entry_id for t in hs_up.terms] != want_s[:LIMIT] \
                or up.revision != snap_ws.revision:
            problems.append("scope upgrade from frozen entries differs from"
                            " a direct scoped snapshot")

        # Dictation normalization with the loaded dictionary.
        no_hit = " ".join(prose(500))
        norm_no_hit = check_norm("normalize_no_hit", snap, no_hit, no_hit,
                                 [], reps, problems)
        pos_in, pos_exp, pos_rules = dictation_with_hits(specs, 500, 25)
        norm_pos = check_norm("normalize_positive", snap, pos_in, pos_exp,
                              pos_rules, reps, problems)
        # Stress cohorts (exact oracles; timings informational).
        dense_in, dense_exp, dense_rules = dictation_with_hits(specs, 500,
                                                               2)
        stress_dense = check_norm("dense_hits", snap, dense_in, dense_exp,
                                  dense_rules, max(5, reps // 10), problems)
        bucket = " ".join(["tirm"] * 250 + [specs[1]["alias"]])
        stress_bucket = check_norm(
            "shared_first_word_bucket", snap, bucket,
            " ".join(["tirm"] * 250 + [specs[1]["canonical"]]),
            [specs[1]["entry_id"]], max(5, reps // 10), problems)
        # Overlaps + long aliases in a small dedicated snapshot, with the
        # winners authored here (longest valid phrase, then earlier).
        from localflow.v2.vocabulary import Alias, VocabularyEntry
        ov = [VocabularyEntry(entry_id=f"ov-{i}", canonical=c,
                              aliases=(Alias(a),), approved=True,
                              verification="explicit")
              for i, (c, a) in enumerate([
                  ("Alpha", "al fa"), ("AlphaBeta", "al fa be ta"),
                  ("Gamma", "be ta ga ma"),
                  ("LongName", "one two three four five six")])]
        ov_snap = VocabularySnapshot(ov + list(snap.entries[:2000]))
        unit_in = "say al fa be ta ga ma and one two three four five six"
        unit_exp = "say AlphaBeta ga ma and LongName"
        stress_overlap = check_norm(
            "overlap_long", ov_snap, " ".join([unit_in] * 20),
            " ".join([unit_exp] * 20), ["ov-1", "ov-3"] * 20,
            max(5, reps // 10), problems)
        st.close()

    work_valid = not problems
    gated = {"cached_retrieval": cached, "warm_selection": warm,
             "scoped_selection": scoped,
             "fresh_selection": fresh_t,
             "fresh_scoped_selection": fresh_scoped_t,
             "normalize_no_hit": norm_no_hit,
             "normalize_positive": norm_pos}
    over = {k: v["p95_ms"] for k, v in gated.items()
            if v["p95_ms"] > BUDGET_MS}
    verdict = "work_invalid" if not work_valid else (
        "budget_failed" if over else "pass")
    sha = subprocess.run(["git", "-C", str(CODE), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    report = {
        "benchmark": "m05_vocabulary_actual_work",
        "code_sha": sha,
        "code_root_modified": bool(subprocess.run(
            ["git", "-C", str(CODE), "status", "--porcelain",
             "--untracked-files=no"], capture_output=True,
            text=True).stdout.strip()),
        "environment": {"python": platform.python_version(),
                        "machine": platform.machine(),
                        "system": platform.system(),
                        "processor": platform.processor() or None,
                        "macos": platform.mac_ver()[0] or None,
                        "label": "algorithmic evidence only (not"
                                 " reference-Mac latency)"},
        "model_call": False,
        "budget_ms": BUDGET_MS,
        "population": {
            "entries": len(specs), "approved_aliases": len(specs),
            "matchable_keys_global": 2 * n_glob,
            "matchable_keys_scoped": 2 * len(specs),
            "scope_distribution": {"global": n_glob,
                                   "workspace:scope-a": n_ws},
            "pinned": sum(1 for s in specs if s["pinned"]),
            "store_build_seconds": round(build_s, 1)},
        "selection": {"limit": LIMIT, "offered": len(hs.terms),
                      "omitted": len(hs.omitted),
                      "scoped_offered": len(hs_s.terms),
                      "scoped_omitted": len(hs_s.omitted),
                      "membership_checked_against_independent_rank": True},
        "cache_state": {"cold_snapshot": "fresh store read + build each"
                        " iteration", "cached_retrieval": "store revision"
                        " read + selection over the cached snapshot",
                        "warm_selection": "repeat selection on one"
                        " snapshot (memoized per snapshot)",
                        "fresh_selection": "first selection on each of"
                        " several fresh snapshots (no memo)"},
        "timings": {"cold_snapshot": cold, **gated,
                    "scope_upgrade_and_packaging": {
                        **upgrade_t, "bound_ms": FINALIZE_BOUND_MS,
                        "within_bound": upgrade_t["p95_ms"]
                        <= FINALIZE_BOUND_MS,
                        "gated": False},
                    "stress_dense_hits": stress_dense,
                    "stress_shared_first_word_bucket": stress_bucket,
                    "stress_overlap_long_aliases": stress_overlap},
        "work_validity": {"verdict": "valid" if work_valid else "invalid",
                          "problems": problems},
        "timing_verdict": "not_scored" if not work_valid else (
            "over_budget" if over else "within_budget"),
        "over_budget": over,
        "verdict": verdict,
    }
    report["exit_code"] = {"pass": 0, "budget_failed": 1,
                           "work_invalid": 2}[verdict]
    for k, v in report["timings"].items():
        print(f"{k:34s} p50 {v['p50_ms']:9.3f}  p95 {v['p95_ms']:9.3f}"
              f"  p99 {v['p99_ms']:9.3f} ms")
    print(f"work validity: {report['work_validity']['verdict']}"
          + (f" — {problems}" if problems else ""))
    print(f"verdict: {verdict} (exit {report['exit_code']})")
    if ARGS.out:
        out_dir = pathlib.Path(ARGS.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "m05_benchmark.json"
        out.write_text(json.dumps(report, indent=1) + "\n")
        print(f"report: {out}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
