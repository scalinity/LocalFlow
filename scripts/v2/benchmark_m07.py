"""M07 ablation benchmark: same-model V1 vs V2 prompt/chunking on the
frozen M07 fixture corpus (Evaluation E07 Run A/B; milestone M07).

V1 = the shipped TranscriptCleaner (contradictory-examples prompt,
35/50-word chunking, verbatim-span corrections, plausibility checks).
V2 = the faithful-contract engine (S13 prompt, complete-block windows,
offset-anchored corrections, validation + fallback ladder).
Both run the SAME model (Qwen3-4B-Instruct-2507 4-bit, greedy) in this
process, sequentially, over the 120 frozen fixtures stratified by
length. Reports stage latency by bucket, generation counts, fallback
rates, failed terminations, and the fixture pass rates each
implementation achieves on the same assertions.

Run: .venv/bin/python scripts/v2/benchmark_m07.py [--limit N]
Output: docs/v2/benchmarks/<ts>-m07/m07.json (counts/latencies only —
the corpus is the committed synthetic fixture set).
"""

import gc
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
FIXTURES = [
    (ROOT / "tests/v2/fidelity/fixtures_fidelity.json", "fidelity"),
    (ROOT / "tests/v2/structure/fixtures_structure.json", "structure"),
    (ROOT / "tests/v2/fidelity/fixtures_literal.json", "literal"),
]


def load_corpus():
    cases = []
    for path, stratum in FIXTURES:
        for case in json.loads(path.read_text())["cases"]:
            case["_stratum"] = stratum
            cases.append(case)
    return cases


def bucket(words):
    if words <= 20:
        return "short"
    if words <= 60:
        return "medium"
    return "long"


def assertions(case, text):
    low = text.lower()
    for group in case.get("expect", []):
        if not any(alt.lower() in low for alt in group):
            return False
    for bad in case.get("forbid", []):
        if bad.lower() in low:
            return False
    return True


def stats(values):
    if not values:
        return {"n": 0}
    s = sorted(values)
    return {
        "n": len(s),
        "p50": round(statistics.median(s), 1),
        "p95": round(s[max(0, int(len(s) * 0.95) - 1)], 1),
        "max": round(s[-1], 1),
    }


def run_v1(cases):
    from localflow.cleanup import TranscriptCleaner
    cleaner = TranscriptCleaner("llm", MODEL)
    t0 = time.monotonic()
    cleaner.load()
    load_s = time.monotonic() - t0
    rows = []
    for case in cases:
        t1 = time.monotonic()
        text = cleaner.clean(case["input"])
        stage_ms = (time.monotonic() - t1) * 1000.0
        rows.append({
            "case_id": case["case_id"],
            "stratum": case["_stratum"],
            "bucket": bucket(len(case["input"].split())),
            "stage_ms": round(stage_ms, 1),
            "path": cleaner.last_path,
            "fallback_reason": cleaner.last_fallback_reason,
            "passes": text is not None,
            "assertions": assertions(case, text or ""),
        })
    del cleaner
    gc.collect()
    return rows, load_s


def run_v2(cases):
    from localflow.v2.cleanup import ModelRunner
    runner = ModelRunner(MODEL)
    t0 = time.monotonic()
    runner.load()
    load_s = time.monotonic() - t0
    engine = runner.engine()
    rows = []
    for case in cases:
        protected = []
        for needle in case.get("protected", []):
            idx = case["input"].find(needle)
            if idx >= 0:
                protected.append((idx, idx + len(needle)))
        t1 = time.monotonic()
        res = engine.clean(case["input"], protected_spans=protected)
        stage_ms = (time.monotonic() - t1) * 1000.0
        rows.append({
            "case_id": case["case_id"],
            "stratum": case["_stratum"],
            "bucket": bucket(len(case["input"].split())),
            "stage_ms": round(stage_ms, 1),
            "path": res.path,
            "fallback_reason": res.fallback_reason,
            "passes": res.termination["kind"] != "output_limit"
            or res.path == "llm",
            "incomplete": res.incomplete,
            "windows": res.termination["windows"],
            "generations": sum(
                1 for o in res.observations
                if o.get("kind") in ("cleanup", "corrections")),
            "assertions": assertions(case, res.text),
        })
    return rows, load_s


def summarize(rows, label):
    by_bucket = {}
    for b in ("short", "medium", "long"):
        sel = [r for r in rows if r["bucket"] == b]
        by_bucket[b] = {
            "stage_ms": stats([r["stage_ms"] for r in sel]),
            "assertion_pass": sum(r["assertions"] for r in sel),
            "n": len(sel),
        }
    fallback = [r for r in rows if r["path"] in (
        "llm_fallback_basic", "llm_fallback_normalized", "basic")]
    return {
        "label": label,
        "cases": len(rows),
        "assertion_pass": sum(r["assertions"] for r in rows),
        "fallback_jobs": len(fallback),
        "fallback_paths": {
            p: sum(1 for r in rows if r["path"] == p)
            for p in sorted({r["path"] for r in rows})},
        "failed_termination": sum(1 for r in rows if not r["passes"]),
        "buckets": by_bucket,
        "rows": rows,
    }


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) \
        if "--limit" in sys.argv else None
    cases = load_corpus()
    if limit:
        cases = cases[:limit]
    import hashlib
    corpus_hash = hashlib.sha256(
        json.dumps([{k: v for k, v in c.items() if not k.startswith("_")}
                    for c in cases], sort_keys=True).encode()).hexdigest()
    print(f"corpus: {len(cases)} frozen fixtures ({corpus_hash[:12]})")
    print("V1 (TranscriptCleaner) …")
    v1_rows, v1_load = run_v1(cases)
    print(f"  done: {sum(r['assertions'] for r in v1_rows)}/{len(cases)}"
          f" assertions, load {v1_load:.1f}s")
    print("V2 (faithful engine) …")
    v2_rows, v2_load = run_v2(cases)
    print(f"  done: {sum(r['assertions'] for r in v2_rows)}/{len(cases)}"
          f" assertions, load {v2_load:.1f}s")
    from localflow.v2.training import runtime_versions
    out = {
        "benchmark": "m07-cleanup-ablation",
        "model": MODEL,
        "corpus": {
            "fixtures": len(cases),
            "strata": {s: sum(1 for c in cases if c["_stratum"] == s)
                       for s in ("fidelity", "structure", "literal")},
            "sha256": corpus_hash,
        },
        "environment": {
            "runtime": runtime_versions(),
            "sampling_v2": {"temperature": 0.0, "greedy": True},
        },
        "load_seconds": {"v1": round(v1_load, 2), "v2": round(v2_load, 2)},
        "v1": summarize(v1_rows, "v1-transcriptcleaner"),
        "v2": summarize(v2_rows, "v2-faithful-engine"),
    }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = ROOT / "docs/v2/benchmarks" / f"{stamp}-m07"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "m07.json").write_text(json.dumps(out, indent=2))
    print(f"written: {dest / 'm07.json'}")
    v1s, v2s = out["v1"], out["v2"]
    print(f"assertion pass: v1 {v1s['assertion_pass']}/{v1s['cases']}"
          f" · v2 {v2s['assertion_pass']}/{v2s['cases']}")
    print(f"fallback jobs:  v1 {v1s['fallback_jobs']}"
          f" · v2 {v2s['fallback_jobs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
