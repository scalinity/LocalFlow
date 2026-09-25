"""Differential check: inherited vs repaired parser on simulated well-formed
legacy logs that follow localflow/app.py@7cdd904 print causality:
worker thread prints raw/cleaned/timing (or 'transcription failed'),
the main thread prints audio (at capture end) and inserted/empty (after the
job's worker output, via callAfter). Aggregates must be identical.
Usage:
    git show 1ee8e44:scripts/v2/parse_legacy_log.py > /tmp/old_parser.py
    .venv/bin/python docs/v2/acceptance/M01/remediation/diff_parsers.py \
        /tmp/old_parser.py scripts/v2/parse_legacy_log.py 5000
Recorded output: diff_parsers.out. Evidence of neutrality on well-formed
simulated sequences only; the real historical file is checked on the Mac
(VERIFICATION.html M01-V008).
"""
import importlib.util
import json
import random
import sys

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

old = load(sys.argv[1], "old")
new = load(sys.argv[2], "new")
N = int(sys.argv[3]) if len(sys.argv) > 3 else 3000

def payload(rng):
    words = ["alpha", "beta", "gamma", "delta", "x.y", "um", "Dom?"]
    lines = [" ".join(rng.choice(words) for _ in range(rng.randint(1, 8)))
             for _ in range(rng.choice([1, 1, 1, 2, 3]))]
    if rng.random() < 0.2:
        lines.insert(1, "")
    if rng.random() < 0.2:
        lines[-1] = "   " + lines[-1] + "  "
    return "\n".join(lines)

def simulate(rng):
    out = []  # list of (time, seq, text)
    t = 0.0
    seq = 0
    def emit(time, text):
        nonlocal seq
        seq += 1
        out.append((time, seq, text))
    for _launch in range(rng.randint(1, 3)):
        emit(t, "[localflow] ready — hold fn to dictate, release to insert text.")
        t += 0.1
        emit(t, "[localflow] model loaded.")
        t += 0.1
        if rng.random() < 0.7:
            emit(t, "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)")
        else:
            emit(t, "[localflow] cleanup model unavailable, using basic cleanup: boom")
        worker_free = t
        for _job in range(rng.randint(0, 12)):
            t += rng.uniform(0.05, 3.0)  # capture end
            emit(t, "[localflow] audio: 2.0s from 'mic', voiced 40%, "
                    "trailing silence 0.5s, overflows 0")
            if rng.random() < 0.1:
                emit(t + 0.0001, "[localflow] WARNING: recording was nearly silent")
            start = max(t, worker_free) + rng.uniform(0.01, 0.5)
            kind = rng.choices(["ok", "empty", "fail", "cleaned_empty", "paste_fail"],
                               [70, 10, 3, 3, 4])[0]
            wt = start
            if kind == "fail":
                emit(wt, "[localflow] transcription failed: error creating Metal shared event")
                emit(wt + rng.uniform(0.001, 0.05), "[localflow] empty transcription — nothing to insert")
            elif kind == "empty":
                emit(wt, "[localflow] timing: stt 0.1s, cleanup 0.0s")
                emit(wt + rng.uniform(0.001, 0.05), "[localflow] empty transcription — nothing to insert")
            else:
                emit(wt, "[localflow] raw:     " + payload(rng))
                wt += 0.0001
                if rng.random() < 0.1:
                    emit(wt, "[localflow] cleanup output failed sanity check, using basic pass")
                    wt += 0.0001
                cleaned = "" if kind == "cleaned_empty" else payload(rng)
                emit(wt, "[localflow] cleaned: " + cleaned)
                wt += 0.0001
                emit(wt, f"[localflow] timing: stt {rng.randint(0, 30) / 10:.1f}s, "
                         f"cleanup {rng.randint(0, 60) / 10:.1f}s")
                post = wt + rng.uniform(0.001, 1.5)  # paste may be slow
                if kind == "cleaned_empty":
                    emit(post, "[localflow] empty transcription — nothing to insert")
                elif kind == "ok":
                    emit(post, f"[localflow] inserted {rng.randint(1, 99)} chars")
            worker_free = wt
        t = max(t, worker_free) + 5
    out.sort()
    return "\n".join(x[2] for x in out) + ("\n" if rng.random() < 0.9 else "")

STRIP = {"schema_version", "source", "parser", "eof_incomplete_pairs",
         "decode_uncertain_pairs", "heuristic_fields", "method_notes",
         "notable_examples"}
NEW_COUNTS = {"malformed_timing_records", "timing_detached_after_posted_insertion"}

def norm(r):
    r = {k: v for k, v in r.items() if k not in STRIP}
    r["counts"] = {k: v for k, v in r["counts"].items() if k not in NEW_COUNTS}
    return r

rng = random.Random(20260924)
diffs = 0
pairs_total = 0
detached = 0
for i in range(N):
    text = simulate(rng)
    a, b = norm(old.parse(text)), norm(new.parse(text))
    pairs_total += a["pairs"]
    detached += new.parse(text)["counts"]["timing_detached_after_posted_insertion"]
    if a != b:
        diffs += 1
        if diffs <= 3:
            print("DIFF on case", i)
            for k in a:
                if a[k] != b.get(k):
                    print("  ", k, a[k], "->", b.get(k))
print(json.dumps({"simulated_logs": N, "pairs": pairs_total,
                  "aggregate_differences": diffs,
                  "timings_detached": detached}))
