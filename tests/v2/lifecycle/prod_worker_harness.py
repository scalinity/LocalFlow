"""Production worker entry with declared model shims (EV-05 portable).

Runs the REAL ``localflow.v2.worker`` (``Worker.serve`` scheduling, the
protocol framing, fault/reason handling, input-path checks) in a fresh
subprocess, replacing only the model loaders — ``localflow.stt
.Transcriber``, ``localflow.v2.cleanup.ModelRunner`` and the v1
``TranscriptCleaner.load`` (latched like the V2 load, then reported
failed: the shim has no v1 model) — with scriptable stand-ins. Unlike
``fake_worker.py`` (which re-implements the protocol),
nothing here decides WHEN a request is read or answered: that is the
production loop's behaviour under test.

Plan (JSON file named by $LOCALFLOW_PROD_WORKER_PLAN):
{
  "asr_load": "ok" | "fail",
  "cleanup_load": "ok" | "fail",
  "cleanup_reload": "fail",         # every cleanup load after the first fails
  "cleanup_reload_delay_ms": <int>, # every cleanup load after the first
                                    # takes this long (footprint rig tests)
  "cleanup_load_latch": "<path>",   # cleanup load blocks until it exists
  "asr_load_delay_ms": <int>,       # the ASR load takes this long (footprint
                                    # rig tests)
  "transcribe": ["ok:<text>" | "raise:<message>"
                 | "delay:<ms>|<one of those>"],     # per call
  "clean": ["ok:<text>" | "raise:<message>"
            | "degraded:<text>"      # a degraded answer and a reason code
            | "delay:<ms>|<one of those>"],          # per call
  "record": "<path>",               # JSONL: what the shims were given
  "hold_gpu_mib": <int>,            # ASR load keeps a plain MLX array of
                                    # this size alive (footprint rig tests)
  "trace_clears": true,             # with "record": also log every
                                    # mx.clear_cache call and every frame
                                    # the worker writes, in order, each with
                                    # the calling thread's name
  "clear_cache_fails": true         # with "trace_clears": the traced
                                    # mx.clear_cache raises
}
With "record", the shim runner's weights object logs a "weights_freed" event
when it is released, so a test can read WHEN the worker let the model go.
A pass with these shims is protocol/scheduling evidence, never a
model-backed result (no Parakeet, no Qwen; MLX only for the optional
plain array above and the memory counters).
"""

import json
import os
import sys
import threading
import time
import types

sys.path.insert(0, os.environ.get("LOCALFLOW_CODE_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))))))

PLAN = {}
_cursor = {}
_GPU_HOLD = None
_cleanup_loads = 0


def _take(op):
    i = _cursor.get(op, 0)
    _cursor[op] = i + 1
    seq = PLAN.get(op) or []
    return seq[i] if i < len(seq) else "ok:plan-exhausted"


def _record(**kw):
    path = PLAN.get("record")
    if not path:
        return
    with open(path, "a") as f:
        f.write(json.dumps(kw) + "\n")


class ShimTranscriber:
    def __init__(self, model_id):
        self.model_id = model_id
        self.last_decode_ranges = None

    def load(self, on_phase=None):
        if on_phase is not None:
            on_phase("loading")
            on_phase("warming")
        if PLAN.get("asr_load_delay_ms"):
            time.sleep(PLAN["asr_load_delay_ms"] / 1000.0)
        if PLAN.get("hold_gpu_mib"):
            # Optional: keep a real GPU allocation alive so the process
            # shows a GPU line to the footprint tool (rig tests only).
            import mlx.core as mx
            global _GPU_HOLD
            _GPU_HOLD = mx.random.uniform(
                shape=(int(PLAN["hold_gpu_mib"]) * 1024 * 1024 // 4,))
            mx.eval(_GPU_HOLD)
        if PLAN.get("asr_load") == "fail":
            raise RuntimeError("shim asr load failure")
        _record(event="asr_loaded", t=time.monotonic())

    def transcribe(self, samples):
        b = _take("transcribe")
        if b.startswith("delay:"):
            head, b = b.split("|", 1)
            time.sleep(int(head[len("delay:"):]) / 1000.0)
        _record(event="transcribe", samples=int(samples.size),
                t=time.monotonic())
        if b.startswith("raise:"):
            raise RuntimeError(b[len("raise:"):])
        self.last_decode_ranges = [[0, int(samples.size)]]
        return b[len("ok:"):] if b.startswith("ok:") else b


class _Weights:
    """Stands in for the loaded model: reachable only through the runner
    that loaded it, so its release shows when the worker dropped the engine."""

    def __del__(self):
        try:
            _record(event="weights_freed", t=time.monotonic())
        except Exception:
            pass


class ShimEngine:
    def __init__(self, runner=None):
        # Like the real engine, which reaches the model through its runner.
        self.runner = runner

    def clean(self, raw_text, **kw):
        b = _take("clean")
        if b.startswith("delay:"):
            head, b = b.split("|", 1)
            time.sleep(int(head[len("delay:"):]) / 1000.0)
        _record(event="engine_clean", t=time.monotonic())
        if b.startswith("raise:"):
            raise RuntimeError(b[len("raise:"):])
        from localflow.v2.cleanup.engine import CleanupResult
        degraded = b.startswith("degraded:")
        if degraded:
            b = b[len("degraded:"):]
        return CleanupResult(
            text=b[len("ok:"):] if b.startswith("ok:") else b,
            path="llm_fallback_normalized" if degraded else "llm",
            stage="clean",
            fallback_reason="shim_degraded" if degraded else None,
            incomplete=False,
            termination={"kind": "complete", "windows": 1, "limit_hits": 0},
            validation={"components": [], "windows_validated": 1,
                        "windows_fallback": 0},
            windows=[{"source_range": [0, len(raw_text)], "stage": "clean",
                      "reason": None}],
            corrections={"applied": 0, "rejected": 0, "rejected_reasons": [],
                         "applied_span_count": 0},
            observations=[])


class ShimRunner:
    def __init__(self, model_id):
        self.model_id = model_id

    def load(self, on_phase=None):
        global _cleanup_loads
        _cleanup_loads += 1
        latch = PLAN.get("cleanup_load_latch")
        _record(event="cleanup_load_started", t=time.monotonic())
        if latch:
            while not os.path.exists(latch):
                time.sleep(0.01)
        if PLAN.get("cleanup_reload_delay_ms") and _cleanup_loads > 1:
            time.sleep(PLAN["cleanup_reload_delay_ms"] / 1000.0)
        if on_phase is not None:
            on_phase("warming")
        if PLAN.get("cleanup_load") == "fail" or (
                PLAN.get("cleanup_reload") == "fail" and _cleanup_loads > 1):
            raise RuntimeError("shim cleanup load failure")
        self._weights = _Weights()
        _record(event="cleanup_loaded", t=time.monotonic())

    def engine(self, notifier=None):
        return ShimEngine(self)

    def generate_fn(self):
        return lambda prompt, max_tokens: {"text": "", "tokens": 0}

    def render(self, messages):
        return ""


def _shim_v1_load(self):
    """v1 cleaner load: same latch as the V2 load, then an honest failure
    (the cleaner keeps its basic path — no v1 model exists here)."""
    latch = PLAN.get("cleanup_load_latch")
    _record(event="cleanup_load_started", impl="v1", t=time.monotonic())
    if latch:
        while not os.path.exists(latch):
            time.sleep(0.01)
    self.load_failed = True


def _trace_clears():
    """Log each ``mx.clear_cache`` call and each frame the worker writes into
    the record file, so a test reads their order and calling threads."""
    import mlx.core as mx
    from localflow.v2 import worker
    real_clear, real_write = mx.clear_cache, worker._write_msg

    def clear_cache():
        _record(event="clear_cache",
                thread=threading.current_thread().name)
        if PLAN.get("clear_cache_fails"):
            raise RuntimeError("shim clear_cache failure")
        return real_clear()

    def write_msg(msg):
        _record(event="frame", op=msg.get("op"), engine=msg.get("engine"),
                state=msg.get("state"), label=msg.get("label"),
                thread=threading.current_thread().name)
        return real_write(msg)

    mx.clear_cache, worker._write_msg = clear_cache, write_msg


def main():
    global PLAN
    with open(os.environ["LOCALFLOW_PROD_WORKER_PLAN"]) as f:
        PLAN = json.load(f)
    stt = types.ModuleType("localflow.stt")
    stt.Transcriber = ShimTranscriber
    sys.modules["localflow.stt"] = stt
    import localflow.v2.cleanup as v2c
    v2c.ModelRunner = ShimRunner
    import localflow.cleanup as v1c
    v1c.TranscriptCleaner.load = _shim_v1_load
    if PLAN.get("trace_clears"):
        _trace_clears()
    from localflow.v2 import worker
    return worker.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
