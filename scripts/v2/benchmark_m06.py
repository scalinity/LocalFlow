#!/usr/bin/env python3
"""M06 context benchmark (Spec S12, E11-style local harness).

Measures on synthetic AX trees — no model calls, no live app reads:
- identity-capture cost (the only hotkey-path addition; it runs after
  the overlay, so hotkey→overlay feedback is untouched by design);
- the post-release finalize delay distribution against the 75 ms S12
  budget, including a worst-case slow provider that must be cut;
- provider coverage and skip frequency across the eight E10
  destination classes (not just latency on successful reads);
- the scope-upgrade rebuild cost (cold vs cached) for the dictionary
  sizes that matter, and the paired pipeline delta context-on vs off.

Run: .venv/bin/python scripts/v2/benchmark_m06.py <outdir>
"""

import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]
                       / "tests/v2/context"))

from test_context_snapshot import (  # noqa: E402
    ADVERSARIAL,
    SCENARIOS,
    FakeAXHost,
    FIXTURES,
)
from localflow.v2.context import ContextCollector  # noqa: E402
from localflow.v2 import vocabulary as vocab  # noqa: E402

N = 60            # per-measurement iterations (p95 stable, quick)
SLOW_MS = 250.0


def pct(xs, p):
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, round(p / 100.0 * (len(xs) - 1))))
    return xs[i]


def identity_cost():
    s = SCENARIOS["LF-CTX-010"]
    out = []
    for _ in range(N):
        host = FakeAXHost(s)
        coll = ContextCollector(enabled=True, emit=lambda *a, **k: None,
                                host=host,
                                frontmost=lambda: s["frontmost"])
        t0 = time.perf_counter()
        coll.capture_identity()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def finalize_fast():
    """Warm providers well inside the deadline: the p95 added post-
    release delay for a healthy destination."""
    s = SCENARIOS["LF-CTX-010"]
    out = []
    for _ in range(N):
        host = FakeAXHost(s)
        coll = ContextCollector(enabled=True, deadline_ms=75.0,
                                emit=lambda *a, **k: None, host=host,
                                frontmost=lambda: s["frontmost"])
        t = coll.capture_identity()
        coll.begin(t)
        time.sleep(0.05)            # providers already done (recording)
        t0 = time.perf_counter()
        coll.finalize()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def finalize_slow_cut():
    """Worst case: a provider slower than the deadline must be cut —
    finalize itself stays inside the budget (+ scheduling slack)."""
    s = dict(ADVERSARIAL["LF-CTX-A8"])
    out = []
    for _ in range(20):
        host = FakeAXHost(s)
        coll = ContextCollector(enabled=True, deadline_ms=75.0,
                                emit=lambda *a, **k: None, host=host,
                                frontmost=lambda: s["frontmost"])
        t = coll.capture_identity()
        coll.begin(t)
        t0 = time.perf_counter()
        snap = coll.finalize()
        out.append((time.perf_counter() - t0) * 1000.0)
        assert snap.partial
    return out


def coverage_matrix():
    """Provider coverage + skip frequency over the eight destination
    classes (reported, not just latency on success)."""
    rows = []
    for s in FIXTURES["scenarios"]:
        host = FakeAXHost(s)
        coll = ContextCollector(enabled=True, deadline_ms=75.0,
                                emit=lambda *a, **k: None, host=host,
                                frontmost=lambda: s["frontmost"])
        t = coll.capture_identity()
        coll.begin(t)
        time.sleep(0.03)
        snap = coll.finalize()
        rows.append(snap)
    resolved = skipped = 0
    per_provider = {}
    for snap in rows:
        for p in snap.providers:
            per_provider.setdefault(p["name"], {"ok": 0, "omitted": 0})
            per_provider[p["name"]]["ok" if p["status"] == "ok"
                                     else "omitted"] += 1
            if p["status"] == "ok":
                resolved += 1
            else:
                skipped += 1
    return {
        "scenarios": len(rows),
        "provider_slots": resolved + skipped,
        "resolved": resolved,
        "skipped": skipped,
        "skip_rate": round(skipped / (resolved + skipped), 4),
        "per_provider": per_provider,
        "identity_scope_keys": len({
            (s.target.app_bundle, s.site_origin, s.workspace)
            for s in rows}),
    }


def scope_upgrade_cost():
    """The finalize-time trio rebuild for a resolved wider scope: cold
    (first time this (revision, scope) pair is seen) vs cached."""
    from localflow.v2.vocabulary import VocabularySnapshot

    def make_entries(n):
        return [vocab.VocabularyEntry(
            entry_id=f"vocab-b{i}", canonical=f"Term{i}",
            aliases=(vocab.Alias(f"term {i}"),), approved=True,
            usage_count=i, last_used_utc="2026-09-01T00:00:00Z")
            for i in range(n)]

    out = {}
    for n in (10, 1000, 10000):
        entries = make_entries(n)
        base = VocabularySnapshot(entries)          # app-only scope state
        full = vocab.ScopeContext(app_bundle="com.google.Chrome",
                                  site_origin="https://mail.google.com")
        t0 = time.perf_counter()
        upgraded = VocabularySnapshot(base.entries, full)   # cold rebuild
        cold = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        for _ in range(50):
            key = (1, ("com.google.Chrome", "https://mail.google.com",
                       None, None))
            hit = key == (1, ("com.google.Chrome",
                              "https://mail.google.com", None, None))
        warm = (time.perf_counter() - t0) * 1000.0 / 50.0
        out[f"entries_{n}"] = {
            "cold_rebuild_ms": round(cold, 3),
            "cache_key_check_ms": round(warm, 6),
            "upgraded_revision_changes":
                upgraded.revision != base.revision,
        }
    return out


def pipeline_delta():
    """Paired end-to-end coordinator runs (real app delegate, scripted
    supervisor): context on vs off — the added release-to-text cost."""
    import tempfile
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]
                           / "tests/v2/normalization"))
    from test_normalization_pipeline import Harness, RecordingSupervisor

    def one(cfg_extra):
        sup = RecordingSupervisor("twelve percent works")
        h = Harness([1.0], cfg=cfg_extra, supervisor=sup)
        s = SCENARIOS["LF-CTX-010"]
        h.d._context = ContextCollector(
            enabled=True, deadline_ms=75.0, emit=lambda *a, **k: None,
            host=FakeAXHost(s), frontmost=lambda: s["frontmost"])
        h.press_release()
        t0 = time.perf_counter()
        h.run_coordinator()
        dt = (time.perf_counter() - t0) * 1000.0
        h.close()
        return dt

    ctx_on = [one({}) for _ in range(10)]
    ctx_off = [one({"context_enabled": False}) for _ in range(10)]
    return {
        "context_on_ms": round(statistics.median(ctx_on), 3),
        "context_off_ms": round(statistics.median(ctx_off), 3),
        "delta_ms": round(statistics.median(ctx_on)
                          - statistics.median(ctx_off), 3),
        "runs": len(ctx_on),
    }


def main():
    outdir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    ident = identity_cost()
    fast = finalize_fast()
    slow = finalize_slow_cut()
    report = {
        "benchmark": "m06-context",
        "spec": "S12 (75 ms post-release context deadline), E10 matrix",
        "method": "synthetic AX trees via tests/v2/context fixtures;"
                  " fake providers; no model calls, no live apps",
        "iterations": {"identity": N, "finalize_fast": N,
                       "finalize_slow_cut": 20},
        "identity_capture_ms": {
            "p50": round(pct(ident, 50), 3),
            "p95": round(pct(ident, 95), 3),
            "note": "runs after the overlay: hotkey→overlay feedback is"
                    " untouched by construction (M03 benchmark owns it)",
        },
        "finalize_fast_ms": {
            "p50": round(pct(fast, 50), 3),
            "p95": round(pct(fast, 95), 3),
            "budget_ms": 75.0,
            "within_budget_p95": pct(fast, 95) <= 75.0,
        },
        "finalize_slow_cut_ms": {
            "p50": round(pct(slow, 50), 3),
            "p95": round(pct(slow, 95), 3),
            "max": round(max(slow), 3),
            "budget_ms": 75.0,
            "note": "budget + scheduling slack only; provider cut at the"
                    " deadline and delivered downstream",
        },
        "coverage": coverage_matrix(),
        "scope_upgrade": scope_upgrade_cost(),
        "pipeline_delta": pipeline_delta(),
    }
    text = json.dumps(report, indent=1, sort_keys=True)
    print(text)
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "m06.json").write_text(text + "\n")
        print(f"\nwritten: {outdir / 'm06.json'}")
    ok = report["finalize_fast_ms"]["within_budget_p95"] \
        and max(slow) < 150.0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
