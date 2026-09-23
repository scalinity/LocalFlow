"""M12 benchmarks (Spec S24/S20 required benchmarks):

1. Warm note open P95 ≤ 200 ms for a 10,000-word note — ``open_note``
   through the store writer (the Scratchpad's load path), repeated
   warm.
2. Editor responsiveness while saving/searching — the main-thread cost
   of arming an edit (dirty marker + debounce bookkeeping) with saves
   and searches running, budgeted like the M11 acknowledgment (≤ 50 ms).
3. Autosave flush P95 and local search P95 over 200 notes (personal
   scale, recorded).

Run: .venv/bin/python scripts/v2/benchmark_m12.py [--out DIR]
"""

import argparse
import json
import pathlib
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.notes import (NoteStore, NotesEditorModel,  # noqa: E402
                                ORIGIN_TYPED, TRIGGER_AUTOSAVE)

WORD10K = " ".join(
    f"benchmark filler word {i} for the scratchpad fixture line"
    for i in range(1250))  # 10,000 words


def pct(values, q):
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1)))))
    return s[k]


def bench_warm_open(tmp):
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    try:
        ns = NoteStore(s)
        out = ns.create_note(WORD10K)
        ns.open_note(out["note_id"])  # warm the writer + page cache
        times = []
        for _ in range(30):
            t0 = time.monotonic()
            detail = ns.open_note(out["note_id"])
            times.append(time.monotonic() - t0)
            assert detail["revision"]["word_count"] == len(
                WORD10K.split())
        return {"cases": len(times),
                "words": len(WORD10K.split()),
                "p95_ms": round(pct(times, 95) * 1000.0, 3),
                "median_ms": round(statistics.median(times) * 1000.0, 3),
                "budget_ms": 200.0,
                "pass": pct(times, 95) * 1000.0 <= 200.0}
    finally:
        s.close()


def bench_editor_responsive_during_io(tmp):
    """The main-thread cost of one edit while a save and searches run
    on their own threads (the M11 UI-acknowledgment budget)."""
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    try:
        ns = NoteStore(s)
        out = ns.create_note(WORD10K)
        import threading
        stop = threading.Event()

        def io_loop():
            i = 0
            while not stop.is_set():
                ns.search(f"filler word {i % 1250}")
                ns.notes()
                i += 1

        io = threading.Thread(target=io_loop, daemon=True)
        io.start()
        model = NotesEditorModel(out["note_id"], out["revision"],
                                 WORD10K,
                                 on_dirty=lambda _nid: ns.mark_dirty(
                                     out["note_id"]))
        ack = []
        try:
            for i in range(50):
                t0 = time.monotonic()
                model.edit(WORD10K + f" tail {i}")
                model.flush(ns, trigger=TRIGGER_AUTOSAVE)
                ack.append(time.monotonic() - t0)
        finally:
            stop.set()
            io.join(timeout=2.0)
        return {"cases": len(ack),
                "max_ms": round(max(ack) * 1000.0, 3),
                "p95_ms": round(pct(ack, 95) * 1000.0, 3),
                "budget_ms": 50.0,
                "pass": max(ack) * 1000.0 <= 50.0}
    finally:
        s.close()


def bench_flush_and_search(tmp):
    s = store_mod.Store(tmp / "v2.db", backup_dir=None)
    try:
        ns = NoteStore(s)
        model = None
        out = ns.create_note("flush target note")
        model = NotesEditorModel(out["note_id"], out["revision"], "")
        flushes = []
        for i in range(20):
            model.edit(f"typed content revision {i} with a few words")
            t0 = time.monotonic()
            model.flush(ns, trigger=TRIGGER_AUTOSAVE)
            flushes.append(time.monotonic() - t0)
        # 200-note search corpus (synthetic, content-free).
        for i in range(200):
            n = ns.create_note(
                f"synthetic note {i} filler words for search scale")
        searches = []
        for i in range(20):
            t0 = time.monotonic()
            rows = ns.search(f"note {i * 7 % 200} filler")
            searches.append(time.monotonic() - t0)
            assert rows
        return {
            "autosave_flush": {
                "cases": len(flushes),
                "p95_ms": round(pct(flushes, 95) * 1000.0, 3),
                "median_ms": round(
                    statistics.median(flushes) * 1000.0, 3)},
            "search_200_notes": {
                "cases": len(searches),
                "p95_ms": round(pct(searches, 95) * 1000.0, 3),
                "median_ms": round(
                    statistics.median(searches) * 1000.0, 3)},
        }
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    results = {"kind": "m12-benchmarks", "synthetic": True}
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        print("warm note open (10,000 words) …")
        results["warm_note_open"] = bench_warm_open(tmp)
        print(f"  p95 {results['warm_note_open']['p95_ms']} ms"
              f" (budget {results['warm_note_open']['budget_ms']} ms)")
        print("editor responsiveness during save+search …")
        results["editor_ack_during_io"] = \
            bench_editor_responsive_during_io(tmp)
        print(f"  max {results['editor_ack_during_io']['max_ms']} ms"
              f" (budget {results['editor_ack_during_io']['budget_ms']}"
              " ms)")
        print("autosave flush + search scale …")
        results["io_latency"] = bench_flush_and_search(tmp)
        print(f"  flush p95 "
              f"{results['io_latency']['autosave_flush']['p95_ms']} ms;"
              f" search p95 "
              f"{results['io_latency']['search_200_notes']['p95_ms']} ms")
    ok = (results["warm_note_open"]["pass"]
          and results["editor_ack_during_io"]["pass"])
    results["overall_pass"] = bool(ok)
    out_dir = pathlib.Path(args.out) if args.out else \
        pathlib.Path("docs/v2/benchmarks")
    if args.out:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "m12.json").write_text(
            json.dumps(results, indent=1, sort_keys=True) + "\n")
        print(f"wrote {out_dir / 'm12.json'}")
    else:
        print(json.dumps(results, indent=1, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
