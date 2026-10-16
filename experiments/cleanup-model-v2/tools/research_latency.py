"""Latency summary of the sequential clean pass (aggregates only).

Reads the evaluation rows of systems that ran one at a time on an otherwise idle Mac and writes
latency.json: median and p95 of total cleanup, generation and first-token time, peak memory,
fallback rate, and for re-runs the share of cases whose delivered text equals the earlier
(concurrent) run of the same checkpoint.

  PYTHONPATH=experiments/cleanup-model-v2:experiments/cleanup-model .venv/bin/python \
    experiments/cleanup-model-v2/tools/research_latency.py OUT_DIR
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ART = HERE / "artifacts"

# arm -> (clean-pass label, earlier concurrent label or None)
CLEAN = {
    "C": ("latency-C", "C-merged"),
    "base-4b-prod-prompt": ("base-4b-prod-prompt", None),
    "base-9b-prod-prompt": ("base-9b-prod-prompt", None),
    "M2": ("latency-M2s0", "M2s0-ck426"),
    "M1": ("latency-M1s0", "M1s0-ck426"),
    "M3": ("latency-M3", "M3-ck426"),
    "A1": ("latency-A1", "A1-ck624"),
    "A3": ("latency-A3", "A3-ck434"),
    "A2prime": ("latency-A2prime", "A2prime-ck199"),
    "A2": ("latency-A2", "A2-ck199"),
}


def rows(label):
    path = ART / "eval" / f"development-{label}.jsonl"
    if not path.exists():
        return None
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pct(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p))]


def summarize(label, earlier):
    data = rows(label)
    if not data:
        return None
    meta = json.loads((ART / "eval" / f"development-{label}.meta.json").read_text())
    total = [r["total_cleanup_ms"] for r in data]
    out = {"label": label, "n": len(data),
           "total_cleanup_ms": {"median": statistics.median(total), "p95": pct(total, 0.95), "mean": statistics.mean(total)},
           "generation_ms_median": statistics.median(r["generation_ms"] for r in data),
           "first_token_ms_median": statistics.median(r["first_token_ms"] for r in data if r.get("first_token_ms") is not None),
           "peak_mlx_gb": max(r.get("peak_mem_bytes", 0) for r in data) / 1e9,
           "peak_rss_gb": max(r.get("rss_peak_bytes", 0) for r in data) / 1e9,
           "fallback_rate": sum(r["path"] != "llm" for r in data) / len(data),
           "runs": [{"started": run.get("started"), "finished": run.get("finished")} for run in meta["runs"]]}
    if earlier:
        old = rows(earlier)
        if old:
            by_id = {r["case_id"]: r for r in old}
            same = sum(by_id.get(r["case_id"], {}).get("delivered") == r["delivered"] for r in data)
            out["delivered_equals_earlier_run"] = {"earlier": earlier, "equal": same, "of": len(data)}
    return out


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {arm: summarize(*pair) for arm, pair in CLEAN.items()}
    result = {k: v for k, v in result.items() if v}
    (out_dir / "latency.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    print(json.dumps({"systems": sorted(result)}))


if __name__ == "__main__":
    main()
