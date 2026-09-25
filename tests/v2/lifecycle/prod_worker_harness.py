"""Production worker entry with declared model shims (EV-05 portable).

Runs the REAL ``localflow.v2.worker`` (``Worker.serve`` scheduling, the
protocol framing, fault/reason handling, input-path checks) in a fresh
subprocess, replacing only the two model loaders — ``localflow.stt
.Transcriber`` and ``localflow.v2.cleanup.ModelRunner`` — with scriptable
stand-ins. Unlike ``fake_worker.py`` (which re-implements the protocol),
nothing here decides WHEN a request is read or answered: that is the
production loop's behaviour under test.

Plan (JSON file named by $LOCALFLOW_PROD_WORKER_PLAN):
{
  "asr_load": "ok" | "fail",
  "cleanup_load": "ok" | "fail",
  "cleanup_load_latch": "<path>",   # cleanup load blocks until it exists
  "transcribe": ["ok:<text>" | "raise:<message>"],   # per call
  "clean": ["ok:<text>" | "raise:<message>"],        # per call
  "record": "<path>"                # JSONL: what the shims were given
}
A pass with these shims is protocol/scheduling evidence, never a
model-backed result (no MLX, no Parakeet, no Qwen).
"""

import json
import os
import sys
import time
import types

sys.path.insert(0, os.environ.get("LOCALFLOW_CODE_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
        __file__))))))

PLAN = {}
_cursor = {}


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
        if PLAN.get("asr_load") == "fail":
            raise RuntimeError("shim asr load failure")
        _record(event="asr_loaded", t=time.monotonic())

    def transcribe(self, samples):
        b = _take("transcribe")
        _record(event="transcribe", samples=int(samples.size),
                t=time.monotonic())
        if b.startswith("raise:"):
            raise RuntimeError(b[len("raise:"):])
        self.last_decode_ranges = [[0, int(samples.size)]]
        return b[len("ok:"):] if b.startswith("ok:") else b


class ShimEngine:
    def clean(self, raw_text, **kw):
        b = _take("clean")
        _record(event="engine_clean", t=time.monotonic())
        if b.startswith("raise:"):
            raise RuntimeError(b[len("raise:"):])
        from localflow.v2.cleanup.engine import CleanupResult
        return CleanupResult(
            text=b[len("ok:"):] if b.startswith("ok:") else b, path="llm",
            stage="clean", fallback_reason=None, incomplete=False,
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

    def load(self):
        latch = PLAN.get("cleanup_load_latch")
        _record(event="cleanup_load_started", t=time.monotonic())
        if latch:
            while not os.path.exists(latch):
                time.sleep(0.01)
        if PLAN.get("cleanup_load") == "fail":
            raise RuntimeError("shim cleanup load failure")
        _record(event="cleanup_loaded", t=time.monotonic())

    def engine(self, notifier=None):
        return ShimEngine()

    def generate_fn(self):
        return lambda prompt, max_tokens: {"text": "", "tokens": 0}

    def render(self, messages):
        return ""


def main():
    global PLAN
    with open(os.environ["LOCALFLOW_PROD_WORKER_PLAN"]) as f:
        PLAN = json.load(f)
    stt = types.ModuleType("localflow.stt")
    stt.Transcriber = ShimTranscriber
    sys.modules["localflow.stt"] = stt
    import localflow.v2.cleanup as v2c
    v2c.ModelRunner = ShimRunner
    from localflow.v2 import worker
    return worker.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
