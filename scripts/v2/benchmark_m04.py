"""M04 benchmark: normalization latency without any model call (Spec
S24/E11; milestone target P95 <= 25 ms for a 500-word input on the
reference Mac).

Sizes: short (~20 words), medium (~120), long (500 — the target size,
built by repeating fixture sentences with varied numbers). Reports
p50/p95/max per size plus environment, and writes a JSON report.

Run: .venv/bin/python scripts/v2/benchmark_m04.py [--out DIR]
"""

import argparse
import json
import pathlib
import platform
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

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


PLAIN = " ".join(
    "the quick brown fox jumps over the lazy dog while the committee "
    "reviews the quarterly numbers and decides whether to postpone the "
    "offsite until everyone returns from vacation".split()[:40])


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


def bench(text: str, policy, iterations: int) -> dict:
    times = []
    for _ in range(iterations):
        t0 = time.monotonic()
        res = normalize(text, policy)
        times.append((time.monotonic() - t0) * 1000.0)
        assert res.text  # keep the result live
    times.sort()

    def pct(p):
        idx = min(int(len(times) * p), len(times) - 1)
        return times[idx]

    return {
        "words": len(text.split()),
        "chars": len(text),
        "iterations": iterations,
        "p50_ms": round(pct(0.50), 3),
        "p95_ms": round(pct(0.95), 3),
        "max_ms": round(times[-1], 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="directory for the JSON report (default: none)")
    args = ap.parse_args()

    policy = NormalizationPolicy()
    sizes = [
        ("short", build_text(20), 300),
        ("medium", build_text(120), 100),
        ("long_500", build_text(500), 40),
        ("long_500_plain", build_text(500, plain=True), 40),
    ]
    report = {
        "benchmark": "m04_normalization",
        "target": "P95 <= 25 ms for a 500-word input, no model call",
        "policy_revision": policy.policy_revision,
        "model_call": False,
        "environment": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "system": platform.system(),
            "macos": platform.mac_ver()[0],
        },
        "sizes": {},
    }
    all_pass = True
    for name, text, iters in sizes:
        r = bench(text, policy, iters)
        report["sizes"][name] = r
        flag = "ok" if (name != "long_500" or r["p95_ms"] <= 25.0) else "FAIL"
        if flag == "FAIL":
            all_pass = False
        print(f"{name:>9}: {r['words']:4d} words  p50 {r['p50_ms']:7.3f} ms"
              f"  p95 {r['p95_ms']:7.3f} ms  max {r['max_ms']:7.3f} ms"
              f"  [{flag}]")
    if args.out:
        out_dir = pathlib.Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"{stamp}-m04" / "m04.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report: {path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
