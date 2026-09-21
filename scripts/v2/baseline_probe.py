"""M01: current-machine baseline probe (stage timings only).

Loads the actual deployed code paths (localflow.stt.Transcriber,
localflow.cleanup.TranscriptCleaner) with the effective configuration's
models and measures per-stage latency on SYNTHETIC, non-private input:

- Parakeet ASR on 3 s of generated audio (two runs: cold/warm within load)
- Qwen3-4B cleanup on a fixed synthetic sentence (two runs)

This is NOT a release-to-insert measurement: it excludes capture, queue,
target validation and paste confirmation, and the input is not speech from
a real dictation. The release-to-insert pilot requires a human speaker and
is recorded as pending human verification in acceptance/M01/results.json.

Usage:
    .venv/bin/python scripts/v2/baseline_probe.py [--skip-models]
"""

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

RUN_ID = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ") + "-m01-baseline"


def env_facts():
    batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                          text=True).stdout
    power = next((l.strip() for l in batt.splitlines()
                  if "drawing from" in l), None)
    return {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "chip": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                               capture_output=True, text=True).stdout.strip(),
        "memory_gb": round(int(subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True).stdout) / 1024**3, 1),
        "macos": subprocess.run(["sw_vers", "-productVersion"],
                                capture_output=True, text=True).stdout.strip(),
        "power": power,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true",
                    help="record environment only, no model loads")
    args = ap.parse_args()

    from localflow.config import load
    cfg = load()

    report = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "milestone": "M01",
        "kind": "stage_timing_probe_synthetic_input",
        "scope_disclaimer": "Stage timings on synthetic input. Not "
            "release-to-insert; excludes capture, queue, target validation "
            "and paste confirmation. Release-to-insert pilot is a pending "
            "human check (see acceptance/M01/results.json).",
        "environment": env_facts(),
        "config": {"model": cfg["model"], "cleanup": cfg["cleanup"],
                   "cleanup_model": cfg["cleanup_model"]},
        "asr": None,
        "cleanup": None,
    }

    if not args.skip_models:
        # --- ASR: Parakeet on 3 s of generated low-level noise ----------
        from localflow.stt import Transcriber
        try:
            t0 = time.monotonic()
            tr = Transcriber(cfg["model"])
            tr.load()
            load_s = time.monotonic() - t0
            rng = np.random.default_rng(7)
            audio = (0.02 * rng.standard_normal(int(3 * 16000))).astype(np.float32)
            runs = []
            for _ in range(2):
                t0 = time.monotonic()
                tr.transcribe(audio)
                runs.append(round(time.monotonic() - t0, 3))
            report["asr"] = {
                "model": cfg["model"],
                "load_seconds": round(load_s, 3),
                "input": "3.0 s synthetic gaussian noise (seed 7), float32 16 kHz",
                "transcribe_seconds_per_run": runs,
            }
        except Exception as e:
            report["asr"] = {"model": cfg["model"], "error": repr(e)}

        # --- Cleanup: Qwen 4B on a fixed synthetic sentence --------------
        from localflow.cleanup import TranscriptCleaner
        t0 = time.monotonic()
        cl = TranscriptCleaner(cfg["cleanup"], cfg["cleanup_model"])
        cl.load()
        if cfg["cleanup"] != "llm":
            report["cleanup"] = {
                "mode": cfg["cleanup"],
                "note": f"cleanup mode is {cfg['cleanup']!r}; LLM not loaded "
                        "by design — no model timing applies.",
            }
        elif not cl.llm_ready.is_set():
            report["cleanup"] = {"model": cfg["cleanup_model"],
                                 "error": "cleanup LLM failed to load"}
        else:
            load_s = time.monotonic() - t0
            sentence = ("um so i think we should push the demo to next week "
                        "no wait the week after because the vendor quote "
                        "isn't back yet")
            runs = []
            for _ in range(2):
                t0 = time.monotonic()
                cl.clean(sentence)
                runs.append(round(time.monotonic() - t0, 3))
            report["cleanup"] = {
                "model": cfg["cleanup_model"],
                "load_seconds": round(load_s, 3),
                "input": "fixed synthetic dictation sentence (28 words)",
                "clean_seconds_per_run": runs,
            }

    out_dir = ROOT / "docs/v2/benchmarks" / RUN_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {out_dir / 'probe.json'}")


if __name__ == "__main__":
    main()
