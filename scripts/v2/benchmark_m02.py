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

M02 remediation (M02-AUDIT-17): the collection benchmark binds each job's
context exactly as the app's worker does (bind_current before the cleanup
observations, clear_current after) and REFUSES to report an overhead
figure unless every expected stage population exists — per enabled
round: one original_audio, raw_transcript, cleanup model_input (the
rendered prompt), cleanup_proposal and applied_output artifact, one
example and two revisions (publication + outcome); per disabled round:
none of them. A missing or empty population raises
BenchmarkPopulationError and the CLI exits 2 with ``certified: false``.
Timing scope is explicit in the report: the timed region runs from the
first collector hook through the ACKNOWLEDGED publication and outcome
commits (finalize and on_insertion wait for the writer), i.e. committed
end-to-end collector cost around stubbed stages — not enqueue latency and
not release-to-insert.

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


class BenchmarkPopulationError(RuntimeError):
    """The measured path did not produce the evidence it claims to cost."""


COLLECTION_TIMING_SCOPE = (
    "first collector hook through acknowledged publication and outcome"
    " commits (committed end-to-end collector cost around stubbed stages;"
    " not enqueue latency; not release-to-insert)")

EXPECTED_ROLES = ("original_audio", "raw_transcript", "cleanup_input_cleanup",
                  "cleanup_proposal", "applied_output")


def collection_populations(st) -> dict:
    """Independent SQL counts of what the benchmark actually persisted."""
    import sqlite3
    con = sqlite3.connect(st.db_path)
    try:
        roles = dict(con.execute(
            "SELECT role, COUNT(*) FROM artifacts WHERE purged=0 GROUP BY"
            " role").fetchall())
        return {
            "artifacts_by_role": {r: roles.get(r, 0) for r in EXPECTED_ROLES},
            "model_input_artifacts": con.execute(
                "SELECT COUNT(*) FROM artifacts WHERE kind='model_input'"
                ).fetchone()[0],
            "examples": con.execute(
                "SELECT COUNT(*) FROM training_examples").fetchone()[0],
            "revisions": con.execute(
                "SELECT COUNT(*) FROM training_revisions").fetchone()[0],
            "incomplete_publications": con.execute(
                "SELECT COUNT(*) FROM training_revisions WHERE"
                " json_extract(envelope_json, '$.completeness.complete')=0"
                ).fetchone()[0],
        }
    finally:
        con.close()


def check_populations(mode, n, pops):
    """Refuse to certify: every expected population, exactly."""
    problems = []
    if mode == "enabled":
        for role in EXPECTED_ROLES:
            if pops["artifacts_by_role"][role] != n:
                problems.append(f"{role}={pops['artifacts_by_role'][role]}"
                                f" expected {n}")
        if pops["examples"] != n:
            problems.append(f"examples={pops['examples']} expected {n}")
        if pops["revisions"] != 2 * n:
            problems.append(f"revisions={pops['revisions']} expected {2 * n}")
        if pops["incomplete_publications"]:
            problems.append("incomplete publications present")
    else:
        if any(pops["artifacts_by_role"].values()) or pops["examples"] \
                or pops["revisions"]:
            problems.append("disabled mode persisted evidence")
    if n <= 0:
        problems.append("empty measured population")
    if problems:
        raise BenchmarkPopulationError(f"{mode}: " + "; ".join(problems))


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


def bench_collection_paired(n=50, bind=True):
    """``bind=False`` is a fault-injection switch for the benchmark's own
    regression test: it reproduces the pre-remediation unbound observer
    and must make the benchmark refuse (BenchmarkPopulationError)."""
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
        if bind:
            collector.bind_current(ctx)  # as the app's worker does
        collector.on_cleaner_observation({
            "kind": "cleanup", "model_id": "bench-llm",
            "input": "synthetic raw text for bench",
            "system_prompt": "bench system", "examples_count": 0,
            "prompt": "bench full rendered prompt", "max_tokens": 64,
            "output": "Synthetic raw text for bench."})
        collector.on_cleaner_observation({"kind": "cleanup_decision",
                                          "accepted": True,
                                          "applied": "Synthetic raw text for bench."})
        collector.clear_current()
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
            ver = st.verify(deep=True)
            pops = collection_populations(st)
            st.close()
            check_populations(mode, n, pops)
            if not ver["ok"]:
                raise BenchmarkPopulationError(
                    f"{mode}: store verification failed"
                    f" ({len(ver['issues'])} issues)")
            results[mode] = {
                "p50_ms": pct(lat, 0.5), "p95_ms": pct(lat, 0.95),
                "consistency_ok": ver["ok"],
                "incomplete_records": len(ver["issues"]),
                "populations": pops,
                "timed_rounds": len(lat),
            }
    delta_p95 = round(results["enabled"]["p95_ms"] - results["disabled"]["p95_ms"], 3)
    return {
        "certified": True,
        "timing_scope": COLLECTION_TIMING_SCOPE,
        # Certification is about WHAT was measured; whether the cost
        # meets S29.16 is reported separately and never hidden.
        "meets_s2916_target": delta_p95 <= 25,
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
                collector.bind_current(ctx)  # as the app's worker does
                cleaned = cleaner.clean(
                    "um i think maybe we should um push the demo to next"
                    " week no wait the week after because uh the vendor quote"
                    " is not ready")
                lat.append((time.perf_counter() - t0) * 1000.0)
                collector.clear_current()
                collector.on_cleanup_result(ctx, cleaned)
                collector.finalize(ctx)
            st.sync()
            prompts = collection_populations(st)["model_input_artifacts"]
            if mode == "enabled" and prompts < n:
                raise BenchmarkPopulationError(
                    f"real cleanup: {prompts} rendered prompts retained for"
                    f" {n} enabled jobs")
            out[mode] = {"p50_ms": pct(lat, 0.5), "n": n,
                         "model_input_artifacts": prompts}
        st.close()
    return {"real_cleanup": out,
            "timing_scope": "the real cleanup model pass only; collector"
                            " persistence is outside the timed region",
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
    }
    status = 0
    try:
        report["collection_paired"] = bench_collection_paired()
        if args.real:
            report["real_cleanup_spot"] = bench_real_cleanup()
    except BenchmarkPopulationError as e:
        report["collection_paired"] = {"certified": False,
                                       "refusal": str(e)}
        status = 2

    out = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
    print(out)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
