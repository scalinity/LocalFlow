#!/usr/bin/env python3
"""M14 benchmark: curation, profile and export cost at personal scale,
kept apart from dictation latency.

Builds a synthetic store in a temp dir — 10,000 live examples (raw +
applied text, ~200 days of heavy dictation), 10,000 usage facts, 1,000
edit observations and 400 retained 10-second float32 WAVs (~256 MB) with
audio-reviewed verbatim references — then measures:

1. Profile generation (on demand / idle): compute p50/p95, the idle
   pass's unchanged-evidence skip, Python peak memory.
2. Maximum dictation delay: every curation operation is one writer op
   on the single store writer, so a dictation's store write that
   arrives mid-operation waits for it. A probe submits a dictation-
   shaped write (one artifact row + lease) while each operation runs;
   the probe's latency is the delay a dictation would see. (The idle
   scheduler additionally never STARTS profile work while recording,
   an insertion or a worker job is in flight — the guard is covered by
   tests/v2/ui/test_training_review_hub.py.)
3. Review/sampling/split cost: sampling refresh, review queue load,
   mining, family assignment, contamination check.
4. Export: build throughput and the dataset's on-disk size, with
   Python peak memory compared against the total audio bytes (audio is
   streamed, never loaded into RAM), then offline validation time.

Committed output carries timings/sizes/counts only (synthetic content in
a temp dir, never committed). Run:
.venv/bin/python scripts/v2/benchmark_m14.py [outdir]
"""

import hashlib
import json
import pathlib
import platform
import resource
import statistics
import sys
import tempfile
import threading
import time
import tracemalloc

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2 import ids, learning, profile, store as store_mod  # noqa: E402
from localflow.v2.curation import (  # noqa: E402
    export as export_mod, review, sampling, splits)
from localflow.v2.store import (  # noqa: E402
    grant_lease_row, insert_text_artifact_row)

N_EXAMPLES = 10_000
N_AUDIO = 400
N_OBSERVATIONS = 1_000
AUDIO_SECONDS = 10.0
RATE = 16_000
WORDS = ("ship", "the", "module", "review", "notes", "weekly", "summary",
         "deploy", "branch", "draft", "team", "plan", "check", "update",
         "docs", "build", "later", "today", "message", "client")


def p95(samples):
    ordered = sorted(samples)
    return ordered[max(0, int(round(0.95 * len(ordered))) - 1)]


def stats(samples):
    return {"p50_ms": round(statistics.median(samples), 2),
            "p95_ms": round(p95(samples), 2),
            "max_ms": round(max(samples), 2), "n": len(samples)}


def utterance(i):
    """A distinct synthetic utterance (real dictation rarely repeats
    verbatim — and verbatim repeats are excluded from the profile)."""
    n = 12 + (i * 7) % 30
    return " ".join(WORDS[(i * 3 + k * 5) % len(WORDS)]
                    for k in range(n)) + f" item {i}"


def build(s, tmp):
    now = "2026-09-20T10:00:00.000Z"
    s.append_consent("enabled", note="m14-benchmark")
    audio_dir = s.artifacts_dir
    silence = (np.sin(np.arange(int(AUDIO_SECONDS * RATE)) / 40.0)
               * 0.01).astype("<f4")
    audio_bytes = 0
    audio_rows = []
    for i in range(N_AUDIO):
        path = audio_dir / f"art-baud-{i:05d}.wav"
        store_mod.write_wav_f32(path, silence, RATE)
        with open(path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        size = path.stat().st_size
        audio_bytes += size
        audio_rows.append((f"art-baud-{i:05d}", path.name, digest, size))

    def op(conn):
        for i in range(N_EXAMPLES):
            ex, job, fam = f"ex-b{i:05d}", f"job-b{i:05d}", f"fam-b{i:05d}"
            text = utterance(i)
            raw = insert_text_artifact_row(
                conn, artifact_id=f"art-braw-{i:05d}", job_id=job,
                stage="asr", role="raw_transcript", text=text,
                retention_class="training", created_at_utc=now)
            app = insert_text_artifact_row(
                conn, artifact_id=f"art-bapp-{i:05d}", job_id=job,
                stage="cleanup", role="applied_output",
                text=text.capitalize() + ".",
                retention_class="training", created_at_utc=now)
            env = {"example_id": ex, "job_id": job, "family_id": fam,
                   "origin": "live_capture", "time_quality": "known",
                   "captured_at_utc":
                       f"2026-0{3 + i % 6}-1{i % 10}T1{i % 10}:00:00.000Z",
                   "attempt": 2 if i % 50 == 0 else 1,
                   "artifact_ids": {"source_text": raw,
                                    "applied_output": app},
                   "capture": {"duration_sec": 2.0 if i % 40 == 0
                               else 9.0},
                   "recognition": {"language": "es" if i % 97 == 0
                                   else "en"},
                   "outcome": {"correctness": "unreviewed"},
                   "annotations": [], "missing_reasons": {}}
            if i < N_AUDIO:
                aid, name, digest, size = audio_rows[i]
                conn.execute(
                    "INSERT INTO artifacts(artifact_id, job_id, stage,"
                    " parent_artifact_id, kind, role, content_path,"
                    " content_text, sha256, bytes, meta_json,"
                    " retention_class, purged, created_at_utc)"
                    " VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,0,?)",
                    (aid, job, "capture", None, "audio_wav_f32",
                     "original_audio", name, digest, size,
                     json.dumps({"synthetic": True}), "training", now))
                grant_lease_row(conn, aid, "training", days=None,
                                granted_at_epoch=0.0)
                vref = insert_text_artifact_row(
                    conn, artifact_id=f"art-bvref-{i:05d}", job_id=job,
                    stage="review", role="verbatim_reference", text=text,
                    retention_class="training", created_at_utc=now)
                env["artifact_ids"]["original_audio"] = aid
                env["annotations"].append({
                    "annotation_id": f"ann-b{i:05d}",
                    "kind": "verbatim_reference", "coverage": "full",
                    "listened_audio": True, "artifact_id": vref})
                env["outcome"] = {
                    "correctness": "correct",
                    "correctness_provenance":
                        "user_explicit_intended_writing"}
            rev = f"rev-b{i:05d}"
            env["revision_id"] = rev
            payload = json.dumps(env, sort_keys=True)
            conn.execute(
                "INSERT INTO training_examples(example_id, job_id,"
                " family_id, consent_revision_id, collection_policy,"
                " state, created_at_utc, updated_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (ex, job, fam, "consent-bench", "m14_benchmark",
                 "annotated" if i < N_AUDIO else "captured_unreviewed",
                 now, now))
            conn.execute(
                "INSERT INTO training_revisions(revision_id, example_id,"
                " parent_revision_id, created_at_utc, envelope_json,"
                " content_sha256) VALUES(?,?,?,?,?,?)",
                (rev, ex, None, now, payload, ids.sha256_text(payload)))
            conn.execute(
                "INSERT INTO usage_facts(fact_id, kind, job_id,"
                " activity_at_utc, utc_offset_minutes, day_local,"
                " reporting_timezone, algorithm_version, raw_words,"
                " final_words, app_name, mode, created_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"fact-b{i:05d}", "dictation", job,
                 f"2026-0{3 + i % 6}-1{i % 10}T1{i % 10}:00:00.000Z",
                 -420, f"2026-0{3 + i % 6}-1{i % 10}", "UTC", 1,
                 len(text.split()), len(text.split()),
                 f"Synth App {i % 4}", "clean", now))
            if i >= N_AUDIO and i < N_AUDIO + N_OBSERVATIONS:
                wrong = text.replace("module", "modul", 1)
                for suffix, body in (("b", wrong.capitalize()),
                                     ("a", text.capitalize())):
                    insert_text_artifact_row(
                        conn, artifact_id=f"art-bobs{suffix}-{i:05d}",
                        job_id=job, stage="insertion",
                        role=f"observed_{suffix}", text=body,
                        retention_class="training", created_at_utc=now)
                conn.execute(
                    "INSERT INTO insertion_observations(observation_id,"
                    " insertion_id, job_id, started_at_utc,"
                    " stopped_at_utc, stop_reason, edited, reanchors,"
                    " ticks, before_artifact_id, after_artifact_id,"
                    " meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"obs-b{i:05d}", f"ins-b{i:05d}", job, now, now,
                     "owned_range_edited", 1, 0, 3,
                     f"art-bobsb-{i:05d}", f"art-bobsa-{i:05d}", "{}"))
    s.submit(op, timeout=600)
    return audio_bytes


def _probe_write(s):
    """One dictation-shaped store write (artifact row + lease), timed
    from submit to commit."""
    now = ids.now_utc_iso()
    aid = ids.new_id("art")
    t = time.monotonic()
    s.submit(lambda conn: (insert_text_artifact_row(
        conn, artifact_id=aid, job_id="job-probe", stage="asr",
        role="raw_transcript", text="probe dictation text",
        retention_class="history", created_at_utc=now),
        grant_lease_row(conn, aid, "history", days=30,
                        granted_at_epoch=time.time())), timeout=600)
    return (time.monotonic() - t) * 1000.0


def probe_delay(s, fn, *, every_s=0.005):
    """Run ``fn`` on a thread and keep submitting dictation-shaped
    writes (one every ``every_s`` after the previous completes) until
    it finishes. The worst probe latency is the longest a dictation's
    store write would wait on the single writer during the operation."""
    done = {}

    def run():
        t = time.monotonic()
        done["out"] = fn()
        done["op_ms"] = (time.monotonic() - t) * 1000.0
    th = threading.Thread(target=run)
    th.start()
    probes = []
    while th.is_alive():
        time.sleep(every_s)
        probes.append(_probe_write(s))
    th.join()
    return done, (max(probes) if probes else 0.0), len(probes)


def timed(fn, reps):
    samples = []
    out = None
    for _ in range(reps):
        t = time.monotonic()
        out = fn()
        samples.append((time.monotonic() - t) * 1000.0)
    return out, samples


def traced(fn):
    """Python peak allocation of one run (tracemalloc slows the run
    several-fold, so timings always come from untraced runs)."""
    tracemalloc.start()
    tracemalloc.reset_peak()
    t = time.monotonic()
    out = fn()
    ms = (time.monotonic() - t) * 1000.0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return out, ms, peak


def main():
    outdir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    res = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = store_mod.Store(tmp / "v2.db", artifacts_dir=tmp / "art",
                            backup_dir=tmp / "backups")
        t0 = time.monotonic()
        audio_bytes = build(s, tmp)
        print(f"built {N_EXAMPLES} examples, {N_AUDIO} WAVs"
              f" ({audio_bytes / 1e6:.0f} MB) in"
              f" {time.monotonic() - t0:.1f}s")
        emit = lambda *a, **k: None  # noqa: E731
        ps = profile.ProfileService(s, emit=emit)
        sm = sampling.SamplingService(s, emit=emit)
        rs = review.ReviewService(s, emit=emit)
        ls = learning.LearningService(s, emit=emit)
        sp = splits.SplitService(s, emit=emit)
        ex = export_mod.DatasetExporter(s, emit=emit)

        # 1. Profile generation.
        _out, samples = timed(ps.compute, 7)
        _out, _ms, peak = traced(ps.compute)
        out, skip_samples = timed(
            lambda: ps.compute(only_if_changed=True), 7)
        assert out.get("skipped")
        words = ps.current()["measured"]["eligible_words"]
        res["profile_compute"] = {
            **stats(samples), "eligible_examples": N_EXAMPLES,
            "eligible_words": words,
            "python_peak_mb": round(peak / 1e6, 1),
            "note": "on demand (Generate) or the idle pass; chunked reads"
                    " + one short write op"}
        res["profile_idle_skip"] = {
            **stats(skip_samples),
            "note": "idle pass over unchanged evidence: eligibility scan"
                    " + signature, no snapshot written"}
        print(f"profile compute: {res['profile_compute']}")
        print(f"profile idle skip: {res['profile_idle_skip']}")

        # 2 + 3. Curation operations with the dictation-delay probe.
        ops = (
            ("profile_compute", ps.compute),
            ("sampling_refresh", sm.refresh),
            ("review_queue", rs.queue),
            ("mining", lambda: ls.mine_observation_candidates(
                limit=N_OBSERVATIONS)),
            ("split_assign", sp.assign),
            ("contamination_check", sp.contamination),
        )
        delays = {}
        for name, fn in ops:
            done, probe_ms, n_probes = probe_delay(s, fn)
            delays[name] = {"operation_ms": round(done["op_ms"], 1),
                            "max_dictation_write_delay_ms":
                                round(probe_ms, 1),
                            "probes": n_probes}
            print(f"{name}: op {done['op_ms']:.0f} ms · worst dictation"
                  f" write wait {probe_ms:.0f} ms over {n_probes}"
                  " probes")
        res["writer_occupancy"] = delays

        # 4. Export throughput / storage / memory, then validation.
        views = ("asr_supervised", "cleanup_supervised")
        dest = tmp / "dataset"
        done, probe_ms, n_probes = probe_delay(
            s, lambda: ex.build(dest, task_views=views))
        out, build_ms = done["out"], done["op_ms"]
        dataset_bytes = sum(p.stat().st_size for p in dest.rglob("*")
                            if p.is_file())
        # Memory: the same export traced, against a text-only control
        # export — the difference is what the 256 MB of audio costs in
        # RAM (streamed copy + hash ⇒ ~nothing).
        _o, _ms, export_peak = traced(
            lambda: ex.build(tmp / "dataset-mem", task_views=views))
        _o, _ms, text_peak = traced(
            lambda: ex.build(tmp / "dataset-text",
                             task_views=("cleanup_supervised",)))
        res["export"] = {
            "views": list(views),
            "examples": out["counts"]["examples"],
            "asr_rows": out["counts"]["asr_supervised"],
            "cleanup_rows": out["counts"]["cleanup_supervised"],
            "build_ms": round(build_ms, 1),
            "throughput_mb_per_s": round(
                dataset_bytes / 1e6 / (build_ms / 1000.0), 1),
            "examples_per_s": round(
                out["counts"]["examples"] / (build_ms / 1000.0), 1),
            "dataset_bytes": dataset_bytes,
            "audio_bytes_exported": audio_bytes,
            "python_peak_mb": round(export_peak / 1e6, 1),
            "text_only_control_peak_mb": round(text_peak / 1e6, 1),
            "audio_added_peak_mb": round(
                (export_peak - text_peak) / 1e6, 1),
            "max_dictation_write_delay_ms": round(probe_ms, 1),
            "probes": n_probes,
            "note": "the export holds the writer only for its snapshot"
                    " and finalize-recheck ops; audio copy, hashing and"
                    " writing run outside the writer"}
        print(f"export: {res['export']}")
        report, val_samples = timed(
            lambda: export_mod.validate_dataset(dest), 3)
        val_ms = statistics.median(val_samples)
        _r, _ms, val_peak = traced(
            lambda: export_mod.validate_dataset(dest))
        assert report["valid"], report["issues"]
        res["validate"] = {"ms": round(val_ms, 1),
                           "python_peak_mb": round(val_peak / 1e6, 1),
                           "valid": report["valid"]}
        print(f"validate: {res['validate']}")
        res["process_max_rss_mb"] = round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)
        s.close()

    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        payload = {
            "milestone": "M14",
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime()),
            "environment": {
                "python": platform.python_version(),
                "machine": platform.machine(),
                "macos": platform.mac_ver()[0],
                "processor": platform.processor()},
            "store": f"synthetic {N_EXAMPLES} examples, {N_AUDIO}"
                     f" x {AUDIO_SECONDS:g}s float32 WAVs (temp dir;"
                     " never committed)",
            "results": res,
        }
        (outdir / "m14.json").write_text(
            json.dumps(payload, indent=1, sort_keys=True) + "\n")
        print(f"wrote {outdir / 'm14.json'}")


if __name__ == "__main__":
    main()
