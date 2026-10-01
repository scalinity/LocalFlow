"""Focused, synthetic M07 correction measurement on the unchanged Qwen control.

Run: .venv/bin/python tests/v2/fidelity/test_correction_trigger_model.py --json OUT
Reports trigger/proposal/guard/validation separately; fallback is not success.
No private speech or legacy transcript input is accepted.
"""

import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import ModelRunner  # noqa: E402
from localflow.v2.cleanup.engine import (  # noqa: E402
    CORRECTION_MARKER_RE, _has_correction_marker,
)
from localflow.v2.training import runtime_versions  # noqa: E402

CASES = [
    ("NO-WAIT", "Meet Tuesday no wait Wednesday.", "wednesday", "tuesday"),
    ("NO-SORRY", "Timeout 30 no sorry 45 seconds.", "45", "30"),
    ("ACTUALLY", "Meet Tuesday actually Wednesday.", "wednesday", "tuesday"),
    ("I-MEAN", "Timeout 30 i mean 45 seconds.", "45", "30"),
    ("SINGLE-ACTUALLY", "Timeout 30 actually 45 seconds.", "45", "30"),
    ("SINGLE-SORRY", "Timeout 30 sorry 45 seconds.", "45", "30"),
    ("SINGLE-NO", "Meet Thursday no Friday.", "friday", "thursday"),
    ("NEGATIVE-NO", "No we cannot ship today.", "no", None),
    ("NEGATIVE-SORRY", "Sorry to ask again but send the report.", "sorry", None),
    ("NEGATIVE-ACTUALLY", "We actually shipped yesterday.", "actually", None),
]


def main():
    runner = ModelRunner("mlx-community/Qwen3-4B-Instruct-2507-4bit")
    runner.load()
    engine = runner.engine()
    rows = []
    for cid, source, expected, outdated in CASES:
        start = time.perf_counter()
        result = engine.clean(source)
        duration_ms = (time.perf_counter() - start) * 1000
        passes = [o for o in result.observations if o["kind"] == "corrections"]
        guards = [o for o in result.observations
                  if o["kind"] == "corrections_applied"]
        decisions = [o for o in result.observations
                     if o["kind"] == "cleanup_decision"]
        produced = sum(len([s for s in o["output"].splitlines()
                            if s.strip() and s.strip().upper() != "NONE"])
                       for o in passes)
        success = (result.path == "llm" and expected in result.text.lower()
                   and (outdated is None or outdated not in result.text.lower()))
        if outdated is None:
            success = success and result.corrections["applied"] == 0
        row = {
            "case_id": cid, "origin": "synthetic", "successful": success,
            "trigger_before": bool(CORRECTION_MARKER_RE.search(source)),
            "trigger_after": _has_correction_marker(source),
            "correction_passes": len(passes), "proposal_lines": produced,
            "proposals": [{"status": p["status"], "reason": p.get("reason")}
                          for g in guards for p in g["proposals"]],
            "corrections": result.corrections,
            "cleanup_path": result.path, "fallback_reason": result.fallback_reason,
            "failed_components": sorted({c["name"] for d in decisions
                for c in d["validation"]["components"]
                if c["kind"] == "deterministic" and c["status"] == "fail"}),
            "duration_ms": round(duration_ms, 2),
        }
        rows.append(row)
        print(json.dumps(row))
    timings = []
    for _ in range(100):
        start = time.perf_counter()
        for _, source, _, _ in CASES:
            _has_correction_marker(source)
        timings.append((time.perf_counter() - start) * 1000)
    report = {
        "model_id": runner.model_id, "template_revision": runner.template_revision,
        "prompt_revision": result.prompt_revision,
        "corrections_prompt_revision": result.corrections_prompt_revision,
        "runtime": runtime_versions(), "cases": rows,
        "successful": sum(r["successful"] for r in rows), "total": len(rows),
        "admissions_before": sum(r["trigger_before"] for r in rows),
        "admissions_after": sum(r["trigger_after"] for r in rows),
        "new_false_admissions": sum(r["trigger_after"] and not r["trigger_before"]
                                    for r in rows if r["case_id"].startswith("NEGATIVE")),
        "admission_corpus_median_ms": statistics.median(timings),
    }
    if "--json" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(report, indent=2) + "\n")
    print(f"{report['successful']}/{report['total']} successful; "
          f"admissions {report['admissions_before']} -> {report['admissions_after']}; "
          f"new false admissions {report['new_false_admissions']}")
    return 0 if report["successful"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
