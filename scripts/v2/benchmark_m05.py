"""M05 benchmark: relevant-term retrieval with 10,000 stored entries
(Spec S11/S30.1; milestone target P95 <= 25 ms), with the prompt subset
size and omission policy recorded.

Measures, over a store holding 10,000 synthetic entries:
- cold_snapshot: store → VocabularySnapshot (one SQLite read + index
  build; the app caches this per revision),
- warm_retrieval: RelevantVocabularySelector.select over the cached
  snapshot — the retrieval the 25 ms gate covers,
- in_scope_500: selection with a scope context matching 500 of the
  10,000 entries.

No model call anywhere. Writes a JSON report.

Run: .venv/bin/python scripts/v2/benchmark_m05.py [--out DIR]
"""

import argparse
import json
import pathlib
import platform
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.vocabulary import (  # noqa: E402
    RelevantVocabularySelector,
    ScopeContext,
)
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

N_ENTRIES = 10_000
TERMS_ABOVE_LIMIT = 120  # exceeds the default 100-term budget so the
#                         omission policy actually fires in the report


def _word_code(i: int) -> str:
    """Deterministic letters-only code (aliases are spoken word tokens)."""
    letters = ""
    n = i
    while True:
        letters += chr(ord("a") + n % 26)
        n = n // 26 - 1
        if n < 0:
            return "tirm " + letters[::-1]


def build_store(td: pathlib.Path) -> VocabularyStore:
    st = store_mod.Store(td / "v2.db")
    vs = VocabularyStore(st)
    for i in range(N_ENTRIES):
        vs.add_entry(
            f"Term{i:05d}", [_word_code(i)],
            scope_kind="workspace" if i % 20 == 0 else "global",
            scope_value="scope-a" if i % 20 == 0 else None,
            approved=True)
    return vs


def pct(sorted_times, p):
    idx = min(int(len(sorted_times) * p), len(sorted_times) - 1)
    return sorted_times[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="directory for the JSON report (default: none)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        t0 = time.monotonic()
        vs = build_store(pathlib.Path(td))
        build_s = time.monotonic() - t0
        selector = RelevantVocabularySelector(100)

        # Cold snapshot (one read of all rows + index construction).
        reps = 30
        cold = []
        for _ in range(reps):
            t0 = time.monotonic()
            snap = vs.snapshot(None)
            cold.append((time.monotonic() - t0) * 1000.0)
        cold.sort()

        # Warm retrieval: select over the cached snapshot.
        reps_warm = 200
        warm = []
        for _ in range(reps_warm):
            t0 = time.monotonic()
            hs = selector.select(snap, now_utc="2026-09-22T00:00:00Z")
            warm.append((time.monotonic() - t0) * 1000.0)
        warm.sort()
        in_scope_n = sum(1 for e in snap.entries if e.scope_matches(None))
        assert len(hs.terms) == 100 and len(hs.omitted) == \
            in_scope_n - 100, (len(hs.terms), len(hs.omitted))
        assert all(o["reason"] == "budget_limit"
                   for o in hs.omitted)

        # Scoped selection: one prebuilt snapshot under a workspace
        # context (global + 500 scoped entries participate in ranking).
        scoped_ctx = ScopeContext(workspace="scope-a")
        snap_s = vs.snapshot(scoped_ctx)
        assert sum(1 for e in snap_s.entries
                   if e.scope_kind == "workspace") == 500
        reps_scope = 200
        scoped = []
        for _ in range(reps_scope):
            t0 = time.monotonic()
            hs_s = selector.select(snap_s, scoped_ctx,
                                   now_utc="2026-09-22T00:00:00Z")
            scoped.append((time.monotonic() - t0) * 1000.0)
        scoped.sort()

        # Dictation hot path: normalize() WITH the loaded dictionary in
        # context (the stage between ASR and cleanup) over a 500-word
        # prose text — the S24 gate the selector numbers alone don't
        # cover. The text deliberately contains no alias first-words
        # (prose never mentions the synthetic terms), which is the
        # common case; the first-word index makes non-matching text
        # cheap no matter the dictionary size.
        from localflow.v2.normalize import (ContextSnapshot,
                                            NormalizationPolicy, normalize)
        words = ("the quick brown fox jumps over the lazy dog while the "
                 "committee reviews the quarterly numbers and decides "
                 "whether to postpone the offsite until everyone returns"
                 " from vacation ").split()
        prose = " ".join(words * 13)[:3500]
        pol = NormalizationPolicy()
        reps_norm = 40
        norm_times = []
        for _ in range(reps_norm):
            t0 = time.monotonic()
            res_n = normalize(prose, pol,
                              ContextSnapshot(vocabulary=snap))
            norm_times.append((time.monotonic() - t0) * 1000.0)
        norm_times.sort()
        assert res_n.text, "normalize produced no text"

        report = {
            "benchmark": "m05_vocabulary_retrieval",
            "target": "relevant-term retrieval with 10,000 stored"
                      " entries: P95 <= 25 ms (selector retrieval);"
                      " prompt subset size and omission policy recorded",
            "model_call": False,
            "entries": N_ENTRIES,
            "store_build_seconds": round(build_s, 1),
            "prompt_subset": {
                "term_limit": selector.max_terms,
                "offered": len(hs.terms),
                "omitted": len(hs.omitted),
                "omission_policy": "budget_limit"
                                   " (S30.1: budget omissions carry"
                                   " reasons, never silent drops)",
                "scoped_variant": {
                    "scope": "workspace=scope-a (500 entries)",
                    "offered": 100 if len(hs_s.terms) >= 100
                    else len(hs_s.terms),
                },
            },
            "environment": {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "system": platform.system(),
                "macos": platform.mac_ver()[0],
            },
            "cold_snapshot_ms": {
                "iterations": reps,
                "p50_ms": round(pct(cold, 0.50), 3),
                "p95_ms": round(pct(cold, 0.95), 3),
                "max_ms": round(cold[-1], 3),
                "note": "one full-table read + index build; the app"
                        " caches the snapshot per vocabulary revision"
                        " and rebuilds only on edit",
            },
            "warm_retrieval_ms": {
                "iterations": reps_warm,
                "p50_ms": round(pct(warm, 0.50), 3),
                "p95_ms": round(pct(warm, 0.95), 3),
                "max_ms": round(warm[-1], 3),
            },
            "scoped_retrieval_ms": {
                "iterations": reps_scope,
                "p50_ms": round(pct(scoped, 0.50), 3),
                "p95_ms": round(pct(scoped, 0.95), 3),
                "max_ms": round(scoped[-1], 3),
            },
            "normalize_hot_path_ms": {
                "iterations": reps_norm,
                "words": len(prose.split()),
                "dictionary_entries": len(snap.entries),
                "p50_ms": round(pct(norm_times, 0.50), 3),
                "p95_ms": round(pct(norm_times, 0.95), 3),
                "max_ms": round(norm_times[-1], 3),
                "note": "normalize() with the loaded dictionary in"
                        " context, prose without alias first-words"
                        " (common case; the first-word index keeps"
                        " non-matching text cheap)",
            },
        }
        gate = report["warm_retrieval_ms"]["p95_ms"] <= 25.0 \
            and report["scoped_retrieval_ms"]["p95_ms"] <= 25.0 \
            and report["normalize_hot_path_ms"]["p95_ms"] <= 25.0
        report["gate_pass"] = bool(gate)

        print(f"entries            : {N_ENTRIES}"
              f" (built in {build_s:.1f}s)")
        print(f"cold_snapshot      : p50 {report['cold_snapshot_ms']['p50_ms']:8.3f} ms"
              f"  p95 {report['cold_snapshot_ms']['p95_ms']:8.3f} ms"
              f"  (informational; cached per revision)")
        print(f"warm_retrieval     : p50 {report['warm_retrieval_ms']['p50_ms']:8.3f} ms"
              f"  p95 {report['warm_retrieval_ms']['p95_ms']:8.3f} ms"
              f"  [{'ok' if gate else 'FAIL'} vs 25 ms]")
        print(f"scoped_retrieval   : p50 {report['scoped_retrieval_ms']['p50_ms']:8.3f} ms"
              f"  p95 {report['scoped_retrieval_ms']['p95_ms']:8.3f} ms")
        print(f"normalize_hot_path : p50 {report['normalize_hot_path_ms']['p50_ms']:8.3f} ms"
              f"  p95 {report['normalize_hot_path_ms']['p95_ms']:8.3f} ms"
              f"  (500-word prose, 10k-entry dictionary)")
        print(f"prompt subset      : {len(hs.terms)} offered,"
              f" {len(hs.omitted)} omitted (budget_limit; limit"
              f" {selector.max_terms})")

        if args.out:
            out_dir = pathlib.Path(args.out)
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            out = out_dir / f"{stamp}-m05" / "m05.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=1) + "\n")
            print(f"report             : {out}")
        vs.store.close()
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
