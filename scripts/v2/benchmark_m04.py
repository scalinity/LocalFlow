"""M04 benchmark: normalization latency without any model call (Spec
S24/E11; milestone target P95 <= 25 ms for a 500-word input on the
reference Mac).

Cohorts:

* ``short`` (~20 words), ``medium`` (~120), ``long_500`` (500 — the
  target size, built by repeating fixture sentences with varied
  numbers) — MATCHED workloads: every call must do real, owned work;
* ``long_500_plain`` — the no-match control: 500 words that must come
  back unchanged with an empty ledger;
* stress cohorts (characterization, no budget gate): ``dense_edits``
  (an edit every few words), ``number_words`` (thousands of number
  words), ``repeated_point`` (runs of "point"/digit speech),
  ``command_words`` (runs of command names) and ``long_identifiers``
  (long already-written technical tokens).

Workload validity is a gate independent of speed (M04-AUDIT-20): a
matched cohort must change the text, reach a minimum edit count and
produce every expected edit class; the no-match cohort must be an exact
passthrough. A fast no-op therefore FAILS. The timer wraps the complete
public ``normalize`` call.

Exit codes: 0 = workload valid and the gated budgets met; 1 = a gated
p95 budget missed; 2 = workload invalid (takes precedence).

Run: .venv/bin/python scripts/v2/benchmark_m04.py [--out DIR]
     [--budget-ms 25] [--iterations-scale 1.0]
"""

import argparse
import json
import pathlib
import platform
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from localflow.v2.normalize import NormalizationPolicy, normalize  # noqa: E402

SENTENCES = [
    "the timeout is thirty seconds and the budget grew twelve percent",
    "deploy on march fourth with version one point two six point four",
    "the host is one ninety two dot one sixty eight dot one dot ten",
    "we need twelve retries and the file is ten by twenty centimeters",
    "set the retry count to twenty six and port eight thousand",
    "the download took twelve megabytes at a cost of twelve thousand dollars",
    "see you at five thirty PM for the two percentage point review",
    "code zero zero seven three unlocks room two one four",
    "edit dot env then grep dash i pattern files",
    "the ratio is one point two six plus five hundred fifty items",
    "write the word slash then hello comma world period",
    "the constant is minus zero point zero five for twelve seconds",
    "revenue reached two hundred fifty thousand dollars last quarter",
    "el doce por ciento de doce mil euros quedó registrado",
    "path slash users slash danny slash documents holds dot gitignore",
    "ninety nine percent of the time twelve dollars is enough",
]

# The authored, hand-checked normalization of every benchmark sentence
# (output text, edit count) under the default policy — an oracle
# independent of the run. Each matched cohort must reproduce exactly the
# summed per-sentence work: a normalizer that silently skips part of its
# work (review R21) or rewrites a sentence differently is INVALID,
# whatever its speed.
EXPECTED_SENTENCES = [
    ("the timeout is 30 seconds and the budget grew 12%", 2),
    ("deploy on March 4 with version 1.26.4", 2),
    ("the host is 192.168.1.10", 1),
    ("we need 12 retries and the file is 10 × 20 cm", 2),
    ("set the retry count to twenty six and port 8000", 1),
    ("the download took 12 megabytes at a cost of $12,000", 2),
    ("see you at 5:30 PM for the 2 percentage point review", 2),
    ("code 0073 unlocks room 214", 2),
    ("edit .env then grep -i pattern files", 2),
    ("the ratio is 1.26 plus 550 items", 2),
    ("slash then hello, world.", 3),
    ("the constant is -0.05 for 12 seconds", 2),
    ("revenue reached $250,000 last quarter", 1),
    ("el doce por ciento de doce mil euros quedó registrado", 0),
    ("/users/danny/documents holds .gitignore", 2),
    ("99% of the time $12 is enough", 2),
]

# Edit classes the matched cohorts must actually produce (long_500
# contains every sentence at least once).
EXPECTED_CLASSES_LONG = {
    "percent", "currency", "ip", "version", "date", "time", "dimension",
    "unit_number", "decimal", "symbol", "flag", "path", "code",
    "literal_escape", "percentage_points", "port", "integer",
}
EXPECTED_CLASSES_SHORT = {"unit_number", "percent"}

PLAIN = " ".join(
    "the quick brown fox jumps over the lazy dog while the committee "
    "reviews the quarterly numbers and decides whether to postpone the "
    "offsite until everyone returns from vacation".split()[:40])

STRESS = {
    "dense_edits": "twelve percent comma ",
    "number_words": "one two three four five six seven eight nine ten ",
    "repeated_point": "one point two point three point four point ",
    "command_words": "comma period colon semicolon hyphen new line ",
    "long_identifiers": "see LocalFlow_V2_normalization_engine_identifier"
                        "_with_many_parts_2026 and https://example.com/a"
                        "/very/long/path?q=12&x=34 now ",
}


def build_text(words: int, plain: bool = False) -> str:
    if plain:
        out = []
        total = 0
        while total < words:
            out.append(PLAIN)
            total += len(PLAIN.split())
        return " ".join(out)
    out = []
    total = 0
    i = 0
    while total < words:
        s = SENTENCES[i % len(SENTENCES)]
        out.append(s)
        total += len(s.split())
        i += 1
    return " ".join(out)


def build_stress(unit: str, words: int) -> str:
    n = max(1, words // len(unit.split()))
    return (unit * n).strip()


def bench(text: str, policy, iterations: int) -> dict:
    times = []
    res = None
    for _ in range(iterations):
        t0 = time.monotonic()
        res = normalize(text, policy)
        times.append((time.monotonic() - t0) * 1000.0)
    times.sort()

    def pct(p):
        idx = min(int(len(times) * p), len(times) - 1)
        return times[idx]

    classes = {}
    for e in res.edits:
        classes[e.cls] = classes.get(e.cls, 0) + 1
    return {
        "words": len(text.split()),
        "chars": len(text),
        "iterations": iterations,
        "p50_ms": round(pct(0.50), 3),
        "p95_ms": round(pct(0.95), 3),
        "p99_ms": round(pct(0.99), 3),
        "max_ms": round(times[-1], 3),
        "edits": len(res.edits),
        "rejected": len(res.rejected),
        "edit_classes": dict(sorted(classes.items())),
        "text_changed": res.text != text,
        "internal_duration_ms_last": round(res.duration_ms or 0.0, 3),
    }


def sentence_work(words: int) -> int:
    """Summed authored edit count of the sentences build_text(words)
    concatenates."""
    total = n = i = 0
    while total < words:
        s = SENTENCES[i % len(SENTENCES)]
        n += EXPECTED_SENTENCES[i % len(SENTENCES)][1]
        total += len(s.split())
        i += 1
    return n


def sentence_problems(policy) -> list:
    """Each sentence alone against its authored normalization."""
    out = []
    for src, (want, count) in zip(SENTENCES, EXPECTED_SENTENCES):
        res = normalize(src, policy)
        if res.text != want or len(res.edits) != count:
            out.append(f"sentence changed: {src!r}")
    return out


def validate(name: str, r: dict) -> list:
    """Workload validity: independent of speed."""
    problems = []
    if name in ("short", "medium", "long_500"):
        want = sentence_work({"short": 20, "medium": 120,
                              "long_500": 500}[name])
        if r["edits"] != want:
            problems.append(f"{r['edits']} edits, authored work is {want}")
    if name == "long_500_plain":
        if r["text_changed"] or r["edits"]:
            problems.append("no-match control was changed")
        return problems
    if name in ("short", "medium", "long_500"):
        if not r["text_changed"]:
            problems.append("matched cohort text unchanged")
        min_edits = {"short": 2, "medium": 10, "long_500": 60}[name]
        if r["edits"] < min_edits:
            problems.append(f"only {r['edits']} edits (< {min_edits})")
        want = EXPECTED_CLASSES_LONG if name == "long_500" \
            else EXPECTED_CLASSES_SHORT
        missing = sorted(want - set(r["edit_classes"]))
        if missing:
            problems.append(f"missing edit classes {missing}")
    if name == "dense_edits" and r["edits"] < r["words"] // 4:
        problems.append("dense cohort did not produce dense edits")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="directory for the JSON report (default: none)")
    ap.add_argument("--budget-ms", type=float, default=25.0,
                    help="p95 budget for the gated 500-word cohorts")
    ap.add_argument("--iterations-scale", type=float, default=1.0)
    args = ap.parse_args(argv)

    policy = NormalizationPolicy()
    scale = args.iterations_scale
    cohorts = [
        ("short", build_text(20), 300, True),
        ("medium", build_text(120), 100, True),
        ("long_500", build_text(500), 40, True),
        ("long_500_plain", build_text(500, plain=True), 40, True),
    ] + [(name, build_stress(unit, 500), 20, False)
         for name, unit in STRESS.items()] + [
        ("number_words_4000", build_stress(STRESS["number_words"], 4000),
         5, False),
    ]
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        sha = None
    report = {
        "benchmark": "m04_normalization",
        "target": f"P95 <= {args.budget_ms} ms for a 500-word input "
                  "(matched and no-match), no model call",
        "policy_revision": policy.policy_revision,
        "source_sha": sha,
        "model_call": False,
        "command": " ".join([pathlib.Path(sys.argv[0]).name] +
                            (argv if argv is not None else sys.argv[1:])),
        "environment": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "system": platform.system(),
            "platform": platform.platform(),
            "macos": platform.mac_ver()[0],
        },
        "sizes": {},
        "workload_problems": {},
    }
    budget_ok = True
    workload_ok = True
    bad = sentence_problems(policy)
    if bad:
        workload_ok = False
        report["workload_problems"]["sentences"] = bad
    for name, text, iters, gated in cohorts:
        r = bench(text, policy, max(1, int(iters * scale)))
        r["gated"] = gated and name in ("long_500", "long_500_plain")
        report["sizes"][name] = r
        problems = validate(name, r)
        if problems:
            workload_ok = False
            report["workload_problems"][name] = problems
        flag = "ok"
        if r["gated"] and r["p95_ms"] > args.budget_ms:
            budget_ok = False
            flag = "FAIL"
        if problems:
            flag = "INVALID"
        print(f"{name:>18}: {r['words']:5d} words  p50 {r['p50_ms']:8.3f}"
              f"  p95 {r['p95_ms']:8.3f}  p99 {r['p99_ms']:8.3f} ms"
              f"  edits {r['edits']:4d}  [{flag}]")
    verdict = 2 if not workload_ok else (0 if budget_ok else 1)
    report["verdict"] = {0: "pass", 1: "budget_fail",
                         2: "workload_invalid"}[verdict]
    report["exit_code"] = verdict
    print(f"verdict: {report['verdict']}")
    if args.out:
        out_dir = pathlib.Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"{stamp}-m04" / "m04.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report: {path}")
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
