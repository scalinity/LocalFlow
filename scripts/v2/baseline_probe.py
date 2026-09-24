"""M01: current-machine baseline probe (stage timings only).

Loads the actual deployed code paths with the effective configuration's
models and measures per-stage latency on SYNTHETIC, non-private input:

- Parakeet ASR (localflow.stt.Transcriber) on 3 s of generated audio
  (two runs: cold/warm within load)
- Cleanup on a fixed synthetic sentence (two runs), through the
  implementation the configuration SELECTS (M01 remediation,
  M01-AUDIT-09): ``cleanup_implementation`` "v2" runs the M07 engine the
  worker loads (localflow.v2.cleanup.ModelRunner -> CleanupEngine);
  "v1" runs localflow.cleanup.TranscriptCleaner, the retained V1 control.
  ``--cleanup-implementation`` overrides the selection and the report says
  so. Every run records the path that actually produced its output, so a
  fallback is never reported as a model-cleaned timing.

This is NOT a release-to-insert measurement: it excludes capture, queue,
target validation and paste confirmation, and the input is not speech from
a real dictation. Release-to-insert stays a pending human check.

The report binds the run to its source (Git HEAD + dirty-content digest),
effective configuration (source + hash + model-selection values) and the
model cache observation at run time, and records success/failure/skip/
fallback counts. It is written even when a stage fails.

Usage:
    .venv/bin/python scripts/v2/baseline_probe.py [--skip-models]
        [--cleanup-implementation {config,v1,v2}] [--output-dir DIR]

Exit codes: 0 every requested stage succeeded (fallbacks are recorded, see
summary.fallback_runs); 1 a requested stage failed; 2 the report could not
be written (it is printed to stdout instead).
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.v2.build_baseline_manifest as bm  # noqa: E402

SENTENCE = ("um so i think we should push the demo to next week no wait the "
            "week after because the vendor quote isn't back yet")


def new_run_id():
    return (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
            + "-m01-baseline")


def env_facts():
    facts = bm.hardware()
    facts["timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return facts


def bindings(cfg_record, cfg, hash_models=False):
    g = bm.git_state(ROOT)
    return {
        "source": {"head_commit": g["head_commit"], "clean_tree": g["clean_tree"],
                   "dirty_digest": g["dirty_digest"],
                   "reason": g["head_reason"] or g.get("dirty_digest_reason")},
        "config": {k: cfg_record[k] for k in (
            "effective_source", "effective_values", "effective_config_sha256",
            "overridden_keys", "winner")},
        "model_cache_at_run": bm.models_record(cfg, dict(os.environ),
                                               hash_files=hash_models)
        if cfg else None,
    }


# ---- stages -------------------------------------------------------------------

def run_asr(model_id, factory=None):
    """ASR stage. ``factory(model_id)`` returns an object with load() and
    transcribe(audio) — localflow.stt.Transcriber by default."""
    rec = {"stage": "asr", "implementation": "localflow.stt.Transcriber",
           "model_id": model_id, "status": None, "runs": []}
    try:
        import numpy as np
        if factory is None:
            from localflow.stt import Transcriber as factory
        t0 = time.monotonic()
        tr = factory(model_id)
        tr.load()
        if getattr(tr, "load_error", None):
            raise RuntimeError(f"load_error: {tr.load_error}")
        rec["load_seconds"] = round(time.monotonic() - t0, 3)
        rec["loaded_model_id"] = model_id
        rng = np.random.default_rng(7)
        audio = (0.02 * rng.standard_normal(int(3 * 16000))).astype(np.float32)
        rec["input"] = "3.0 s synthetic gaussian noise (seed 7), float32 16 kHz"
        for _ in range(2):
            t0 = time.monotonic()
            tr.transcribe(audio)
            rec["runs"].append({"seconds": round(time.monotonic() - t0, 3),
                                "status": "ok"})
        rec["status"] = "ok"
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}",
                   traceback_tail=traceback.format_exc().splitlines()[-3:])
    return rec


def run_cleanup_v1(cfg, factory=None):
    rec = {"stage": "cleanup", "implementation":
           "localflow.cleanup.TranscriptCleaner (V1 control)",
           "model_id": cfg["cleanup_model"], "status": None, "runs": []}
    try:
        if factory is None:
            from localflow.cleanup import TranscriptCleaner as factory
        t0 = time.monotonic()
        cl = factory(cfg["cleanup"], cfg["cleanup_model"])
        cl.load()
        if not cl.llm_ready.is_set():
            reason = "cleanup_engine_failed" if getattr(cl, "load_failed", False) \
                else "cleanup_not_ready"
            rec.update(status="failed", error=f"V1 LLM not ready ({reason}); "
                       "clean() would return the basic pass")
            return rec
        rec["load_seconds"] = round(time.monotonic() - t0, 3)
        rec["loaded_model_id"] = cfg["cleanup_model"]
        rec["input"] = "fixed synthetic dictation sentence (28 words)"
        for _ in range(2):
            t0 = time.monotonic()
            cl.clean(SENTENCE)
            path = getattr(cl, "last_path", None)
            rec["runs"].append({
                "seconds": round(time.monotonic() - t0, 3), "status": "ok",
                "path": path,
                "fallback": path != "llm",
                "fallback_reason": getattr(cl, "last_fallback_reason", None)})
        rec["status"] = "ok"
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}",
                   traceback_tail=traceback.format_exc().splitlines()[-3:])
    return rec


def run_cleanup_v2(cfg, factory=None):
    rec = {"stage": "cleanup", "implementation":
           "localflow.v2.cleanup.ModelRunner -> CleanupEngine (M07)",
           "model_id": cfg["cleanup_model"], "status": None, "runs": []}
    try:
        if factory is None:
            from localflow.v2.cleanup import ModelRunner as factory
        t0 = time.monotonic()
        runner = factory(cfg["cleanup_model"])
        runner.load()
        engine = runner.engine()
        rec["load_seconds"] = round(time.monotonic() - t0, 3)
        rec["loaded_model_id"] = cfg["cleanup_model"]
        rec["template_revision"] = getattr(runner, "template_revision", None)
        rec["input"] = "fixed synthetic dictation sentence (28 words)"
        for _ in range(2):
            t0 = time.monotonic()
            result = engine.clean(SENTENCE, locale=cfg.get(
                "normalization_locale", "en-US"))
            rec["runs"].append({
                "seconds": round(time.monotonic() - t0, 3), "status": "ok",
                "path": result.path,
                "fallback": result.path != "llm",
                "fallback_reason": result.fallback_reason,
                "prompt_revision": getattr(result, "prompt_revision", None)})
        rec["status"] = "ok"
    except Exception as e:
        rec.update(status="failed", error=f"{type(e).__name__}: {e}",
                   traceback_tail=traceback.format_exc().splitlines()[-3:])
    return rec


def select_cleanup(cfg, override):
    configured = cfg.get("cleanup_implementation", "v2")
    if cfg.get("cleanup") != "llm":
        return None, configured, (f"cleanup mode is {cfg.get('cleanup')!r}; "
                                  "no cleanup model is loaded by design")
    impl = configured if override in (None, "config") else override
    return impl, configured, None


def summarize(stages):
    requested = [s for s in stages if s["status"] != "skipped"]
    runs = [r for s in requested for r in s.get("runs", [])]
    return {
        "stages_requested": len(requested),
        "stages_ok": sum(1 for s in requested if s["status"] == "ok"),
        "stages_failed": sum(1 for s in requested if s["status"] == "failed"),
        "stages_skipped": sum(1 for s in stages if s["status"] == "skipped"),
        "runs_ok": sum(1 for r in runs if r["status"] == "ok"),
        "fallback_runs": sum(1 for r in runs if r.get("fallback")),
    }


def main(argv=None, *, asr_factory=None, v1_factory=None, v2_factory=None,
         out_root=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true",
                    help="record environment and bindings only, no model loads")
    ap.add_argument("--cleanup-implementation", choices=("config", "v1", "v2"),
                    default="config")
    ap.add_argument("--hash-models", action="store_true",
                    help="hash every cached model file into the binding")
    ap.add_argument("--output-dir", type=pathlib.Path)
    args = ap.parse_args(argv)

    run_id = new_run_id()
    report = {
        "schema_version": 2,
        "run_id": run_id,
        "milestone": "M01",
        "kind": "stage_timing_probe_synthetic_input",
        "scope_disclaimer": "Stage timings on synthetic input. Not "
            "release-to-insert; excludes capture, queue, target validation "
            "and paste confirmation.",
        "environment": None, "bindings": None, "config": None,
        "cleanup_selection": None, "stages": [], "summary": None,
        "errors": [],
    }
    code = 0
    try:
        report["environment"] = env_facts()
        from localflow import config as lf_config
        cfg_record, cfg = bm.effective_config_record(
            "probe process", env_value=os.environ.get("LOCALFLOW_CONFIG"),
            env_observation={"observed": True, "method": "probe environment"},
            user_override=lf_config.user_override_path(),
            bundled=ROOT / "config.json")
        if cfg is None:
            raise RuntimeError("effective configuration would make the "
                               "runtime raise; nothing to probe")
        # Cross-check against the runtime's own loader in this process.
        runtime_cfg = lf_config.load()
        report["config"] = {k: cfg.get(k) for k in bm.SAFE_CONFIG_KEYS}
        report["config"]["matches_runtime_load"] = runtime_cfg == cfg
        report["bindings"] = bindings(cfg_record, cfg, args.hash_models)

        impl, configured, why = select_cleanup(cfg, args.cleanup_implementation)
        report["cleanup_selection"] = {
            "configured_implementation": configured,
            "probed_implementation": impl,
            "selected_by": "config" if args.cleanup_implementation == "config"
                           else "command-line override",
            "role": {"v1": "V1 control (not the configured V2 path)"
                     if configured == "v2" else "configured implementation",
                     "v2": "configured implementation" if configured == "v2"
                     else "V2 engine (override; config selects v1)",
                     None: None}[impl],
            "reason": why,
        }
        if args.skip_models:
            report["stages"] = [
                {"stage": "asr", "status": "skipped", "reason": "--skip-models"},
                {"stage": "cleanup", "status": "skipped", "reason": "--skip-models"}]
        else:
            report["stages"].append(run_asr(cfg["model"], asr_factory))
            if impl == "v1":
                report["stages"].append(run_cleanup_v1(cfg, v1_factory))
            elif impl == "v2":
                report["stages"].append(run_cleanup_v2(cfg, v2_factory))
            else:
                report["stages"].append({"stage": "cleanup", "status": "skipped",
                                         "reason": why})
    except Exception as e:  # early failure: still publish what we have
        report["errors"].append(f"{type(e).__name__}: {e}")
        code = 1
    report["summary"] = summarize(report["stages"])
    if report["summary"]["stages_failed"]:
        code = 1

    blob = json.dumps(report, indent=2) + "\n"
    out_dir = args.output_dir or (pathlib.Path(out_root or ROOT)
                                  / "docs/v2/benchmarks" / run_id)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "probe.json", "x") as f:
            f.write(blob)
    except OSError as e:
        print(blob)
        print(f"ERROR: probe report not written ({type(e).__name__}: {e})",
              file=sys.stderr)
        return 2
    print(blob)
    print(f"wrote {out_dir / 'probe.json'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
