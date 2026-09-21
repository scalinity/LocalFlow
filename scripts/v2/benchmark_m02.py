"""M02 benchmarks: event-writer overhead, storage ops, paired collection cost.

Measures, on this machine (E11 discipline — reports carry environment and
honest labels, never a claim about another machine):
1. Event emit overhead + synthetic-burst queue drain (Spec S07).
2. The audio callback's execution time — proving no database/logging work
   rides the capture path (Spec S06).
3. SQLite store operations over a 50,000-row artifact fixture.
4. Paired collection enabled/disabled over the real collector hooks around
   stubbed stages (S29.16): writer backlog and incomplete records reported.
   This is NOT the release-to-insert pilot — that needs a human speaker and
   stays pending; no extra model calls are made here.

Usage:
    .venv/bin/python scripts/v2/benchmark_m02.py [--output PATH] [--real]
"""

import argparse
import datetime as dt
import json
import pathlib
import platform
import statistics
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from localflow.v2 import eventlog, ids, store, training  # noqa: E402


def pct(values, q):
    if not values:
        return None
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (pos - lo), 3)


def bench_emit(n=20000):
    with tempfile.TemporaryDirectory() as td:
        w = eventlog.EventWriter(pathlib.Path(td) / "logs", mirror_stderr=False)
        lat = []
        for i in range(n):
            t0 = time.perf_counter()
            w.emit("bench.event", level="INFO",
                   duration_ms=float(i % 97))
            lat.append((time.perf_counter() - t0) * 1000.0)
        drain0 = time.perf_counter()
        w.flush(timeout=60)
        drain = time.perf_counter() - drain0
        stats = w.stats()
        w.close()
    drain_note = ("writer kept pace during emission; residual backlog drained"
                  " inline" if drain < 0.001 else "backlog drained after burst")
    return {
        "n": n,
        "emit_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95),
                    "max": round(max(lat), 3)},
        "residual_drain_sec": round(drain, 4),
        "drain_note": drain_note,
        "dropped": stats["dropped_low"] + stats["dropped_normal"],
        "degraded": stats["degraded"],
    }


def bench_audio_callback(calls=2000):
    from localflow.audio import Recorder

    rec = Recorder(sample_rate=16000)
    indata = (np.random.default_rng(0).random((800, 1)) * 0.2 - 0.1).astype(
        np.float32)
    # Warm the adaptive meter state
    for _ in range(50):
        rec._callback(indata, 800, None, None)
    lat = []
    for _ in range(calls):
        t0 = time.perf_counter()
        rec._callback(indata, 800, None, None)
        lat.append((time.perf_counter() - t0) * 1000.0)
    return {
        "calls": calls,
        "callback_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95),
                        "max": round(max(lat), 4)},
        "note": "pure in-memory capture path; recorder holds no store or "
                "event-writer references, so no db/logging work can ride it",
    }


def bench_storage(n=50000):
    with tempfile.TemporaryDirectory() as td:
        st = store.Store(pathlib.Path(td) / "v2.db")
        ids_list = []
        t0 = time.perf_counter()
        for i in range(n):
            ids_list.append(st.write_text_artifact(
                job_id=None, stage="bench", role="row",
                text=f"synthetic benchmark row {i} " + "x" * (i % 64),
                retention_class="history"))
        st.sync(timeout=120)
        insert_sec = time.perf_counter() - t0
        t0 = time.perf_counter()
        for aid in ids_list[:200]:
            st.artifact(aid)
        read_ms = (time.perf_counter() - t0) * 1000.0 / 200
        count = st.artifact_count()
        st.close()
    return {
        "rows": n,
        "insert_sec": round(insert_sec, 3),
        "insert_rate_per_sec": round(n / insert_sec, 1),
        "point_read_ms_avg": round(read_ms, 3),
        "count_query_rows": count,
    }


def bench_collection_paired(n=50):
    rng = np.random.default_rng(1)
    audio = (rng.random(16000) * 0.1 - 0.05).astype(np.float32)

    def run_round(st, consent, collector):
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(),
            timezone="America/New_York", utc_offset_minutes=-240)
        collector.attach_capture_meta(
            ctx, {"device": "bench", "duration_sec": 1.0,
                  "voiced_pct": 50.0, "trailing_silence_sec": 0.1,
                  "overflow_blocks": 0}, 16000)
        collector.on_audio(ctx, audio, 16000, {})
        collector.on_asr_result(ctx, "synthetic raw text for bench",
                                model_id="bench-asr", model_revision=None,
                                stage_duration_ms=1.0)
        collector.on_cleaner_observation({
            "kind": "cleanup", "model_id": "bench-llm",
            "input": "synthetic raw text for bench",
            "system_prompt": "bench system", "examples_count": 0,
            "prompt": "bench full rendered prompt", "max_tokens": 64,
            "output": "Synthetic raw text for bench."})
        collector.on_cleaner_observation({"kind": "cleanup_decision",
                                          "accepted": True,
                                          "applied": "Synthetic raw text for bench."})
        collector.on_cleanup_result(ctx, "Synthetic raw text for bench.")
        collector.finalize(ctx)
        collector.on_insertion(ctx, True, 27)

    results = {}
    for mode in ("disabled", "enabled"):
        with tempfile.TemporaryDirectory() as td:
            st = store.Store(pathlib.Path(td) / "v2.db")
            emit = (lambda *a, **k: None)
            consent = training.ConsentManager(st, emit)
            if mode == "enabled":
                consent.set("enabled", note="bench")
            collector = training.EvidenceCollector(st, emit, consent,
                                                   lambda: {"bench": True})
            lat = []
            for _ in range(n):
                t0 = time.perf_counter()
                run_round(st, consent, collector)
                lat.append((time.perf_counter() - t0) * 1000.0)
            st.sync()
            ver = st.verify()
            results[mode] = {
                "p50_ms": pct(lat, 0.5), "p95_ms": pct(lat, 0.95),
                "consistency_ok": ver["ok"],
                "incomplete_records": len(ver["issues"]),
            }
            st.close()
    delta_p95 = round(results["enabled"]["p95_ms"] - results["disabled"]["p95_ms"], 3)
    return {
        "n_per_mode": n,
        "disabled": results["disabled"],
        "enabled": results["enabled"],
        "delta_p95_ms": delta_p95,
        "s2916_target_ms": 25,
        "note": "synthetic stub stages around the real collector/store; the "
                "release-to-insert paired pilot with real models and a human "
                "speaker remains pending human verification",
    }


def bench_real_cleanup(n=3):
    """Optional model-backed spot check of the collector around the real
    Qwen cleanup pass (no ASR — synthetic raw text in, real LLM pass)."""
    from localflow.cleanup import TranscriptCleaner

    cleaner = TranscriptCleaner("llm", "mlx-community/Qwen3-4B-Instruct-2507-4bit")
    cleaner.load()
    with tempfile.TemporaryDirectory() as td:
        st = store.Store(pathlib.Path(td) / "v2.db")
        emit = (lambda *a, **k: None)
        consent = training.ConsentManager(st, emit)
        collector = training.EvidenceCollector(st, emit, consent,
                                               lambda: {"bench": "real"})
        out = {}
        for mode in ("disabled", "enabled"):
            consent.set("disabled" if mode == "disabled" else "enabled")
            lat = []
            for i in range(n):
                ctx = collector.job_started(
                    ids.new_id("job"), ids.new_id("fam"),
                    captured_at_utc=ids.now_utc_iso(), timezone=None,
                    utc_offset_minutes=None)
                t0 = time.perf_counter()
                cleaner.observer = collector.on_cleaner_observation
                cleaned = cleaner.clean(
                    "um i think maybe we should um push the demo to next"
                    " week no wait the week after because uh the vendor quote"
                    " is not ready")
                lat.append((time.perf_counter() - t0) * 1000.0)
                collector.on_cleanup_result(ctx, cleaned)
                collector.finalize(ctx)
            st.sync()
            out[mode] = {"p50_ms": pct(lat, 0.5), "n": n}
        st.close()
    return {"real_cleanup": out,
            "note": "real Qwen3-4B cleanup pass, model-backed native Mac"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--real", action="store_true",
                    help="add the model-backed real-cleanup spot check (~1 min)")
    args = ap.parse_args(argv)

    report = {
        "schema_version": 1,
        "benchmark": "m02",
        "run_id": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
                  + "-m02",
        "evaluated_utc": ids.now_utc_iso(),
        "environment": {
            "machine": platform.machine(),
            "macos": platform.mac_ver()[0],
            "python": sys.version.split()[0],
            "runtime": training.runtime_versions(),
            "source_revision": ids.source_revision(),
        },
        "emit_overhead": bench_emit(),
        "audio_callback": bench_audio_callback(),
        "storage_50k": bench_storage(),
        "collection_paired": bench_collection_paired(),
    }
    if args.real:
        report["real_cleanup_spot"] = bench_real_cleanup()

    out = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
