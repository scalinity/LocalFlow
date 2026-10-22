"""Re-run the committed development analyses with exact bootstrap sums and compare them with the committed files.

  research_exact_recheck.py OUT_DIR

Arm values that average three seeds make every per-case difference a multiple of 1/6. Summed as floats, a resample whose
exact mean is zero can come out as a residue such as -3.5e-19, so p_two_sided counts it on one side only and an interval
end lands a residue away from zero. This run takes each sum exactly on that lattice (falling back to floats, and saying so,
for a contrast off the lattice) and otherwise runs research_analysis.py unchanged, on the arms each committed file holds.
It writes OUT_DIR/<analysis>/analysis.json and OUT_DIR/summary.json (every p-value, Holm p-value or support decision that
differs from the committed file). Final-set and H5 development analyses compare single runs, whose per-case differences
are integers and sum exactly, so they are not rechecked.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments/cleanup-model-v2"))
sys.path.insert(0, str(ROOT / "experiments/cleanup-model"))

import research_analysis as ra  # noqa: E402

A = ROOT / "experiments/cleanup-model-v2/artifacts"
P = ROOT / "docs/v2/research/paper"
SCALE = 6
NORMALIZED = ["--cases", str(A / "research/dev-normalized/validation.jsonl")]
# analysis -> (arms file, committed analysis, extra arguments, judges as name=run under A/judge)
RUNS = {
    "main": ("data/arms.json", "results/analysis.json", [],
             ["anthropic=dev-main-anthropic", "openai=openai/dev-main-openai", "openrouter=openrouter/dev-main-openrouter"]),
    "final_checkpoints": ("data/arms_final.json", "results/supplementary/final_checkpoints/analysis.json", [],
                          ["anthropic=dev-final-anthropic", "openai=openai/dev-final-openai"]),
    "normalized_references_selected": ("data/arms.json", "results/supplementary/normalized_references_selected/analysis.json",
                                       NORMALIZED, ["anthropic=dev-norm-sel-anthropic"]),
    "normalized_references_selected_engine": ("data/arms.json",
                                              "results/supplementary/normalized_references_selected_engine/analysis.json",
                                              NORMALIZED, []),
    "normalized_references_final": ("data/arms_final.json", "results/supplementary/normalized_references_final/analysis.json",
                                    NORMALIZED, ["anthropic=dev-norm-final-anthropic"]),
}
off_lattice: dict[str, float] = {}


def exact_bootstrap(diffs_by_contrast, ids, resamples=None, seed=ra.SEED):
    """ra.bootstrap with the same resampled indices, summing integer multiples of 1/SCALE."""
    resamples = resamples or ra.RESAMPLES
    rng = random.Random(seed)
    n = len(ids)
    vecs = {}
    for k, values in diffs_by_contrast.items():
        raw = [values[i] for i in ids]
        ints = [round(v * SCALE) for v in raw]
        worst = max(abs(v * SCALE - q) for v, q in zip(raw, ints))
        if worst > 1e-9:
            off_lattice[k] = worst
            vecs[k] = (None, raw)
        else:
            vecs[k] = (SCALE * n, ints)
    samples = {k: [] for k in vecs}
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        for k, (denominator, v) in vecs.items():
            s = sum(v[i] for i in idx)
            samples[k].append(s / denominator if denominator else s / n)
    return samples


def differences(committed, exact):
    out = []
    for section in ("contrasts", "exploratory_contrasts"):
        for metric, rows in committed.get(section, {}).items():
            by_name = {r["contrast"]: r for r in exact.get(section, {}).get(metric, [])}
            for r in rows:
                e = by_name.get(r["contrast"], {})
                keys = [k for k in ("p", "p_holm", "superiority_supported", "noninferiority_supported")
                        if k in r and r.get(k) != e.get(k)]
                if keys:
                    out.append({"section": section, "metric": metric, "contrast": r["contrast"],
                                **{k: {"committed": r.get(k), "exact": e.get(k)} for k in keys}})
    return out


def main() -> None:
    base = Path(sys.argv[1]).resolve()
    os.chdir(ROOT)
    ra.bootstrap = exact_bootstrap
    summary = {}
    for name, (arms_rel, committed_rel, extra, judges) in RUNS.items():
        out = base / name
        out.mkdir(parents=True, exist_ok=True)
        committed = json.loads((P / committed_rel).read_text())
        arms = json.loads((P / arms_rel).read_text())
        container = arms["arms"] if "arms" in arms else arms
        for arm in [a for a in container if a not in committed["available_arms"]]:
            container.pop(arm)
        arms_path = out / "arms.json"
        arms_path.write_text(json.dumps(arms))
        judge_args = [a for j in judges for a in ("--judge", f"{j.split('=')[0]}={A / 'judge' / j.split('=')[1]}/verdicts.jsonl")]
        sys.argv = ["research_analysis.py", str(arms_path), "--out-dir", str(out), *extra, *judge_args]
        ra.main()
        exact = json.loads((out / "analysis.json").read_text())
        summary[name] = {"arms_match": exact["available_arms"] == committed["available_arms"],
                         "off_lattice": dict(off_lattice), "differences": differences(committed, exact)}
        off_lattice.clear()
        flips = sum(1 for d in summary[name]["differences"] if "superiority_supported" in d or "noninferiority_supported" in d)
        print(name, "differences", len(summary[name]["differences"]), "decision changes", flips, flush=True)
    (base / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
