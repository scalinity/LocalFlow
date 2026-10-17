"""Selected versus final checkpoint, programmatic metrics per run (aggregates only).

  research_checkpoints.py OUT.json

A run is included when both its selected-checkpoint and final-checkpoint evaluations are complete.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cleanup-model"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research_analysis import engine_metrics, read_jsonl  # noqa: E402

ART = HERE / "artifacts"
# run -> (selected label, final label)
PAIRS = {
    "M1 seed0": ("M1s0-ck426", "M1s0-final"), "M1 seed1": ("M1s1-ck852", "M1s1-final"), "M1 seed2": ("M1s2-ck213", "M1s2-final"),
    "M2 seed0": ("M2s0-ck426", "M2s0-final"), "M2 seed1": ("M2s1-ck1065", "M2s1-final"), "M2 seed2": ("M2s2-ck852", "M2s2-final"),
    "M3": ("M3-ck426", "M3-final"), "A1": ("A1-ck624", "A1-final"), "A2": ("A2-ck199", "A2-final"),
    "A2prime": ("A2prime-ck199", "A2prime-final"), "A3": ("A3-ck434", "A3-final"),
}
METRICS = ("engine_damage", "engine_noop_preserved", "engine_repair_success", "engine_correction_success")


def rate(per_case, metric):
    vals = [m[metric] for m in per_case.values() if metric in m]
    return sum(vals) / len(vals) if vals else None


def main():
    cases = {c["case_id"]: c for c in read_jsonl(ART / "refinement" / "dataset" / "validation.jsonl")}
    out = {}
    for run, (selected, final) in PAIRS.items():
        scored = {}
        for kind, label in (("selected", selected), ("final", final)):
            if not (ART / "eval" / f"development-{label}.jsonl").exists():
                break
            m = engine_metrics(cases, ART, label)
            if m is None:
                break
            scored[kind] = {"label": label, **{k: rate(m, k) for k in METRICS}}
        if len(scored) == 2:
            out[run] = scored
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps({"runs": sorted(out)}))


if __name__ == "__main__":
    main()
