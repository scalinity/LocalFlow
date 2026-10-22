"""Rerun the Stage 2 analysis to record each component's bootstrap distribution for a figure (aggregates only).

  research_bootstrap_densities.py OUT.json

Runs research_analysis.py --stage2 as REPRODUCE.md does, into a scratch directory, with ra.bootstrap wrapped to
keep each component's resampled means (the first, complete-case test of each component). The rerun must reproduce
the stage2 section of the committed results/stage2/analysis.json exactly. It then writes, per component, the
stored estimate, interval, threshold and outcome, the share of resamples at or below the threshold, and a Gaussian
kernel density of the resampled means on a fixed grid in percentage points. No case text, per-case score or model
output is written.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments/cleanup-model-v2"))
sys.path.insert(0, str(ROOT / "experiments/cleanup-model"))

import research_analysis as ra  # noqa: E402

A = ROOT / "experiments/cleanup-model-v2/artifacts"
P = ROOT / "docs/v2/research/paper"
GRID = [round(-8 + 0.1 * i, 1) for i in range(301)]  # percentage points, -8 to +22
samples_by_component: dict[str, list[float]] = {}


def recording_bootstrap(diffs_by_contrast, ids, resamples=None, seed=ra.SEED):
    out = original_bootstrap(diffs_by_contrast, ids, resamples, seed)
    for name, values in out.items():
        samples_by_component.setdefault(name, values)
    return out


def density(samples):
    """Gaussian kernel density in points, Silverman's bandwidth with a 0.15-point floor."""
    pts = [100 * s for s in samples]
    q = statistics.quantiles(pts, n=4)
    spread = min(statistics.stdev(pts), (q[2] - q[0]) / 1.34)
    h = max(0.9 * spread * len(pts) ** -0.2, 0.15)
    counts: dict[float, int] = {}
    for v in pts:
        key = round(v, 2)
        counts[key] = counts.get(key, 0) + 1
    norm = len(pts) * h * math.sqrt(2 * math.pi)
    return h, [sum(c * math.exp(-0.5 * ((x - v) / h) ** 2) for v, c in counts.items()) / norm for x in GRID]


def main() -> None:
    out_path = Path(sys.argv[1]).resolve()
    os.chdir(ROOT)
    committed = json.loads((P / "results/stage2/analysis.json").read_text())
    ra.bootstrap = recording_bootstrap
    with tempfile.TemporaryDirectory() as scratch:
        sys.argv = ["research_analysis.py", str(P / "data/arms_stage2.json"), "--out-dir", scratch, "--stage2",
                    "--prefix", "final", "--cases", str(A / "refinement/dataset/test.jsonl"),
                    "--judge", f"anthropic={A}/judge/final-main-anthropic/verdicts.jsonl",
                    "--judge", f"openai={A}/judge/openai/final-main-openai/verdicts.jsonl",
                    "--rewritten-judge", f"anthropic={A}/judge/final-c3-anthropic/verdicts.jsonl",
                    "--rewritten-judge", f"openai={A}/judge/openai/final-c3-openai/verdicts.jsonl"]
        ra.main()
        rerun = json.loads((Path(scratch) / "analysis.json").read_text())
    assert rerun["stage2"] == committed["stage2"], "the rerun does not reproduce the committed Stage 2 results"
    components = {}
    for claim, block in committed["stage2"].items():
        for c in block["components"]:
            s = samples_by_component[c["component"]]
            assert ra.interval(s, ra.STAGE2_LEVEL) == c["ci99"], c["component"]
            h, dens = density(s)
            components[c["component"]] = {
                "claim": claim, "estimate": c["estimate"], "ci99": c["ci99"], "threshold": c["threshold"],
                "outcome": c["outcome"], "resamples": len(s), "share_at_or_below_threshold": sum(v <= c["threshold"] for v in s) / len(s),
                "bandwidth_points": h, "density_per_point": dens}
    out_path.write_text(json.dumps({"grid_points": GRID, "components": components}, indent=1) + "\n")
    print(f"wrote {len(components)} component densities; the rerun reproduces every stored Stage 2 interval")


original_bootstrap = ra.bootstrap

if __name__ == "__main__":
    main()
