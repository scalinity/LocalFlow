"""M15-A local frozen-input runner. Setup runs only --smoke, never full corpus.

Run with the existing LocalFlow .venv runtime. All outputs stay in the private
v2-evidence root. Downloading is an explicit separate setup action.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from cleanup_benchmark import (ID, STATES, aggregate, atomic_json, digest, failure_state,
        file_hash, frozen_case, load_corpus, blind_queue, require, score, source_identity,
        utc_now, validate_manifest, write_report, freeze_requirements, validate_freeze_lock)


def private_output(path):
    path = pathlib.Path(path).expanduser().resolve()
    private = pathlib.Path.home() / "Library/Application Support/LocalFlow/v2-evidence"
    require(path.is_relative_to(private.resolve()), "output must be in private v2-evidence storage")
    require(not path.is_relative_to(ROOT), "private output cannot be in repo")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def checkpoint_path(output, candidate, case, repetition, track):
    require(ID.fullmatch(candidate) and ID.fullmatch(case), "checkpoint ids")
    return pathlib.Path(output) / "checkpoints" / candidate / track / f"{case}-{repetition}.json"


def worker(connection, candidate, corpus, track):
    # Suppress arbitrary library output: it can include a prompt or source path.
    with open(os.devnull, "w") as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from cleanup_candidate_adapter import CandidateAdapter, memory_snapshot
    adapter = CandidateAdapter(candidate)
    try:
        metadata = adapter.load()
        if track == "end-to-end-audio":
            adapter.load_asr(corpus)
        connection.send({"status": "READY", **metadata})
        while True:
            unit = connection.recv()
            if unit is None:
                break
            try:
                case, source, reference, audio = unit
                if track == "end-to-end-audio":
                    source, result, timing, identity = adapter.audio_replay(audio, case)
                else:
                    result, timing, identity = adapter.clean(source, case)
                metrics = score(source, reference, result, adapter.last_protected)
                if track == "end-to-end-audio" and digest(source.encode()) != case["normalized"]["sha256"]:
                    # Frozen text correction offsets cannot be applied to a different ASR replay.
                    for key in ("correction_opportunities", "correct_resolutions", "missed_corrections",
                                "wrong_corrections", "over_deletions", "correction_exact_match",
                                "correction_precision_denominator"):
                        metrics[key] = None
                    metrics["correction_missing_reason"] = "replay_normalized_text_differs_from_frozen_gold_offsets"
                # Raw model inputs/proposals/findings are retained privately, never exported to Git.
                connection.send({"status": "COMPLETE", "metrics": metrics, "timing_ms": timing,
                                 "identity": identity, "memory": memory_snapshot(adapter.mx),
                                 "private": {"source": source, "output": result.text,
                                             "result": result.to_json(), "observations": result.observations,
                                             "validation_reports": adapter.validation_reports}})
            except Exception as exc:
                connection.send({"status": failure_state(exc), "failure_kind": type(exc).__name__})
                break
    except Exception as exc:
        connection.send({"status": failure_state(exc), "failure_kind": type(exc).__name__})
    finally:
        try:
            connection.send({"status": "UNLOADED", "settled": adapter.unload()})
        except Exception:
            pass
        connection.close()


def receive(connection, process, timeout):
    """Bounded process wait: a crash/timeout only loses this candidate's unit."""
    started = time.monotonic()
    from cleanup_candidate_adapter import system_memory
    initial = system_memory()
    while time.monotonic() - started < timeout:
        if connection.poll(.25):
            try:
                return connection.recv()
            except EOFError:
                return {"status": "LOAD_FAILED", "failure_kind": "WorkerExited"}
        if not process.is_alive():
            return {"status": "LOAD_FAILED", "failure_kind": "WorkerExited"}
        current = system_memory()
        # Stop this subprocess if pressure is producing a swap storm. Never kill other apps.
        if (current["swapouts"] is not None and initial["swapouts"] is not None and
                current["swapouts"] - initial["swapouts"] > 16384 and
                current["system_available_bytes"] is not None and
                current["system_available_bytes"] < 4 * 1024**3):
            process.terminate()
            process.join(10)
            return {"status": "SKIPPED_BY_CONTRACT", "failure_kind": "MeasuredMemoryPressureGuard"}
    process.terminate()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join(10)
    return {"status": "TIMEOUT", "failure_kind": "DeadlineExceeded"}


def stop_worker(connection, process):
    settled = None
    if process.is_alive():
        try:
            connection.send(None)
            if connection.poll(30):
                reply = connection.recv()
                if reply.get("status") == "UNLOADED":
                    settled = reply.get("settled")
        except (OSError, EOFError):
            pass
    process.join(10)
    if process.is_alive():
        process.terminate()
        process.join(10)
    if process.is_alive():
        process.kill()
        process.join(10)
    connection.close()
    return settled


def select(candidates, selector):
    if selector == "all":
        return candidates
    if selector == "core":
        return [c for c in candidates if c["role"] in {"control", "challenger"}]
    ids = selector.split(",")
    require(set(ids) <= {c["candidate_id"] for c in candidates}, "unknown candidate")
    return [c for c in candidates if c["candidate_id"] in ids]


def run_candidate(candidate, cases, corpus, base, output, identity, track,
                  repetitions, timeout, rerun=False, warmup=True):
    cid = candidate["candidate_id"]
    pending, rows = [], []
    for case in cases:
        for repetition in range(repetitions):
            path = checkpoint_path(output, cid, case["case_id"], repetition, track)
            if path.exists() and not rerun:
                row = json.loads(path.read_text())
                require(row["run_identity"] == identity, "checkpoint identity drift")
                frozen_case(base, case)
                if row["status"] == "COMPLETE":
                    rows.append(row)
                    continue
            pending.append((case, repetition, path))
    if not pending:
        return rows, None
    parent, child = mp.get_context("spawn").Pipe()
    process = mp.get_context("spawn").Process(target=worker, args=(child, candidate, corpus, track))
    process.start()
    child.close()
    loaded = receive(parent, process, timeout)
    load = {"candidate_id": cid, **loaded}
    pinned = pathlib.Path(output) / (cid + "-adapter-identity.json")
    fatal = loaded if loaded["status"] != "READY" else None
    try:
        if loaded["status"] == "READY":
            if pinned.exists() and not rerun:
                require(json.loads(pinned.read_text()) == loaded["identity"], "template/runtime identity drift")
            else:
                atomic_json(pinned, loaded["identity"])
        for index, (case, repetition, path) in enumerate(pending):
            source, reference, audio = frozen_case(base, case)
            if fatal is None and track == "end-to-end-audio" and audio is None:
                reply = {"status": "SKIPPED_BY_CONTRACT", "failure_kind": "AudioUnavailable"}
            elif fatal is not None:
                reply = fatal
            else:
                if warmup and index == 0:
                    parent.send((case, source, reference, str(audio) if audio else None))
                    warm = receive(parent, process, timeout)
                    if warm["status"] != "COMPLETE":
                        fatal = warm
                if fatal:
                    reply = fatal
                else:
                    parent.send((case, source, reference, str(audio) if audio else None))
                    reply = receive(parent, process, timeout)
                    if reply["status"] != "COMPLETE":
                        fatal = reply
            row = {"candidate_id": cid, "case_id": case["case_id"], "family_id": case["family_id"], "repetition": repetition,
                   "track": track, "origin": case["origin"], "stratum": case["stratum"],
                   "split": case["split"], "reference_type": case["reference_type"],
                   "length_band": "short" if len(source.split()) <= 20 else "medium" if len(source.split()) <= 60 else "long",
                   "input_sha256": case["normalized"]["sha256"],
                   "audio_sha256": case.get("audio", {}).get("sha256"),
                   "timestamp": utc_now(), "run_identity": identity,
                   **reply}
            require(row["status"] in STATES, "unexpected worker status")
            atomic_json(path, row)
            rows.append(row)
    finally:
        load["post_run_settled"] = stop_worker(parent, process)
        load["process_released"] = not process.is_alive()
    atomic_json(pathlib.Path(output) / (cid + "-load.json"), load)
    return rows, load


def smoke_case(output):
    assets = output / "smoke-input"
    assets.mkdir(exist_ok=True)
    source = "please keep café and the number 30"
    reference = {"text": "Please keep café and the number 30.",
                 "checks": {"required": [["café"]], "literals": ["30"]}}
    (assets / "normalized.txt").write_text(source)
    atomic_json(assets / "reference.json", reference)
    case = {"case_id": "smoke_unicode", "family_id": "smoke_family", "origin": "synthetic",
            "stratum": "compatibility", "split": "dev", "exposed": True,
            "reviewed": True, "reference_type": "intended_writing",
            "normalization_revision": "smoke-frozen-no-asr", "protected_spans": [],
            "normalized": {"path": "normalized.txt", "sha256": file_hash(assets / "normalized.txt")},
            "reference": {"path": "reference.json", "sha256": file_hash(assets / "reference.json")}}
    corpus = {"schema": "m15-frozen-corpus/1", "reference_state": "frozen", "cases": [case]}
    atomic_json(assets / "corpus.json", corpus)
    return assets / "corpus.json"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=pathlib.Path, default=ROOT / "docs/v2/benchmarks/m15-cleanup-candidates.json")
    p.add_argument("--corpus", type=pathlib.Path)
    p.add_argument("--track", choices=["cleanup-only", "end-to-end-audio"], default="cleanup-only")
    p.add_argument("--candidates", default="core")
    p.add_argument("--output", type=pathlib.Path)
    gate = p.add_mutually_exclusive_group()
    gate.add_argument("--freeze-corpus", action="store_true", help="validate owner references and write immutable manifest lock; no models")
    gate.add_argument("--validate-corpus", action="store_true", help="verify freeze lock and coverage; no models")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--rerun", action="store_true")
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--cold-processes", type=int, default=10)
    p.add_argument("--timeout", type=float, default=600)
    p.add_argument("--blind-finalists", help="two candidate ids; prepare private queue from completed units only")
    args = p.parse_args()
    if args.freeze_corpus or args.validate_corpus:
        require(args.corpus is not None and not args.smoke, "private corpus required")
        private_output(args.corpus.resolve().parent)
        corpus = load_corpus(args.corpus)
        if args.freeze_corpus:
            freeze_requirements(args.corpus, corpus)
            lock_path = pathlib.Path(str(args.corpus) + ".freeze-lock.json")
            require(not lock_path.exists(), "existing freeze lock: create a new corpus version")
            atomic_json(lock_path, {"state": "M15A_CORPUS_FROZEN_READY_TO_BENCHMARK",
                                    "corpus_sha256": file_hash(args.corpus)})
        validate_freeze_lock(args.corpus, corpus)
        print("M15A_CORPUS_FROZEN_READY_TO_BENCHMARK")
        return 0
    require(args.repetitions > 0 and args.cold_processes > 0 and args.timeout > 0, "positive run bounds")
    require(not args.smoke or args.corpus is None, "smoke does not accept acceptance corpus")
    require(not args.smoke or args.track == "cleanup-only", "smoke is cleanup-only")
    require(args.output is not None, "private output required")
    output = private_output(args.output)
    candidates = select(validate_manifest(json.loads(args.manifest.read_text())), args.candidates)
    corpus_path = smoke_case(output) if args.smoke else args.corpus
    require(corpus_path is not None, "private frozen corpus required")
    corpus = load_corpus(corpus_path)
    if not args.smoke:
        validate_freeze_lock(corpus_path, corpus)
    if args.blind_finalists:
        finalists = args.blind_finalists.split(",")
        require(len(finalists) == 2 and finalists[0] != finalists[1], "two distinct finalists")
        select(validate_manifest(json.loads(args.manifest.read_text())), args.blind_finalists)
        shown, keys = [], []
        for case in corpus["cases"]:
            source, reference, _ = frozen_case(corpus_path.parent, case)
            rows = [json.loads(checkpoint_path(output, c, case["case_id"], 0, args.track).read_text())
                    for c in finalists]
            require(all(r["status"] == "COMPLETE" for r in rows), "finalist unit incomplete")
            require(rows[0]["input_sha256"] == rows[1]["input_sha256"], "finalist inputs differ")
            item, key = blind_queue(case["case_id"], source, reference["text"],
                                   {c: r["private"]["output"] for c, r in zip(finalists, rows)})
            shown.append(item)
            keys.append(key)
        atomic_json(output / "blind-finalists.json", shown)
        atomic_json(output / "blind-finalists-key.json", keys)
        return 0
    identity = {**source_identity(), "candidate_manifest_sha256": file_hash(args.manifest),
                "corpus_manifest_sha256": file_hash(corpus_path), "track": args.track,
                "repetitions": 1 if args.smoke else args.repetitions,
                "cold_processes": 1 if args.smoke else args.cold_processes,
                "machine_class": subprocess_machine(), "mode": "compatibility_smoke" if args.smoke else "qualification"}
    run_file = output / "run-identity.json"
    if run_file.exists() and not args.rerun:
        require(json.loads(run_file.read_text()) == identity, "run identity drift; choose a new run directory")
    else:
        atomic_json(run_file, identity)
    all_rows, loads = [], []
    for c in candidates:
        rows, load = run_candidate(c, corpus["cases"], corpus, corpus_path.parent, output, identity,
                    args.track, identity["repetitions"], args.timeout, args.rerun, warmup=not args.smoke)
        all_rows.extend(rows)
        if load:
            loads.append(load)
        else:
            previous_load = output / (c["candidate_id"] + "-load.json")
            if previous_load.exists():
                loads.append(json.loads(previous_load.read_text()))
        # Ten cached cold processes are load experiments, separate from warm latency units.
        for cold in range(1, identity["cold_processes"]):
            dest = output / "cold" / c["candidate_id"] / str(cold)
            receipt = dest / "load.json"
            if receipt.exists() and not args.rerun:
                loads.append(json.loads(receipt.read_text()))
                continue
            parent, child = mp.get_context("spawn").Pipe()
            process = mp.get_context("spawn").Process(target=worker, args=(child, c, corpus, args.track))
            process.start()
            child.close()
            reply = receive(parent, process, args.timeout)
            reply.update(candidate_id=c["candidate_id"], cold_process=cold,
                         post_run_settled=stop_worker(parent, process))
            atomic_json(receipt, reply)
            loads.append(reply)
            if reply["status"] != "READY":
                break
        print(c["candidate_id"], dict((s, sum(r["status"] == s for r in rows)) for s in sorted({r["status"] for r in rows})), flush=True)
        write_report(output, all_rows, identity, loads)
    return 0


def subprocess_machine():
    import platform
    import subprocess
    return {"system": platform.platform(), "architecture": platform.machine(),
            "model": subprocess.check_output(["sysctl", "-n", "hw.model"], text=True).strip(),
            "physical_memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))}


if __name__ == "__main__":
    raise SystemExit(main())
