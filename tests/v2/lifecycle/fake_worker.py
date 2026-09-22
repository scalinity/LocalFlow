"""Test-owned scriptable model worker (tests/v2/lifecycle, EV-05).

Speaks the exact protocol of localflow.v2.worker but does no model work:
behaviors come from a JSON plan file (path in $LOCALFLOW_FAKE_WORKER_PLAN)
so tests can inject Metal-style faults, crashes, delays, stale frames and
scripted results deterministically. Production code knows nothing about it.

Plan shape:
{
  "asr": "ready" | "failed",
  "cleanup": "ready" | "failed" | "loading_forever",
  "transcribe": [behavior, ...],   # consumed per request
  "clean": [behavior, ...]
}

behavior:
  "ok:<text>"                     result with text
  "ok:<text>|path=P|reason=R|obs=N"  clean result extras
  "fault:<ErrorType>"             structured fault for this request
  "crash"                         os._exit(1) — a dead process
  "delay:<ms>|<behavior>"         sleep first, then run the behavior
  "stale:<text>"                  unsolicited result for a fabricated old
                                  request id / generation (never resolves a
                                  live request; exercises the discard guard)
  "staleecho:<text>"              answers the LIVE request id but echoes
                                  generation-1 — the supervisor must treat
                                  it as a stale-generation fault (M03-AC02)
"""

import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from localflow.v2.worker import PROTOCOL_VERSION, _read_msg, _write_msg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-root", required=True)
    args = ap.parse_args()
    plan_path = pathlib.Path(os.environ["LOCALFLOW_FAKE_WORKER_PLAN"])
    with open(plan_path) as f:
        plan = json.load(f)
    # Cursor state survives worker restarts (the supervisor respawns this
    # script as a fresh process): consumed behaviors are counted in a
    # sidecar file so a retried request gets the NEXT behavior, not a
    # replay of the fault.
    cursor_path = plan_path.with_suffix(".cursor")

    def take(op):
        cursors = {}
        try:
            cursors = json.loads(cursor_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
        i = int(cursors.get(op, 0))
        cursors[op] = i + 1
        cursor_path.write_text(json.dumps(cursors))
        behaviors = plan.get(op, [])
        return behaviors[i] if i < len(behaviors) else "ok:plan-exhausted"

    _write_msg({"v": PROTOCOL_VERSION, "op": "hello", "pid": os.getpid(),
                "protocol": PROTOCOL_VERSION,
                "python": sys.version.split()[0]})

    def send_engine(engine, state, reason=None):
        _write_msg({"v": PROTOCOL_VERSION, "op": "engine", "engine": engine,
                    "state": state, "reason_code": reason})

    while True:
        try:
            msg = _read_msg(0)
        except (EOFError, Exception):
            return 0
        op = msg.get("op")
        if op == "shutdown":
            return 0
        if op == "load":
            send_engine("asr", plan.get("asr", "ready"),
                        "not_in_cache" if plan.get("asr") == "failed"
                        else None)
            cleanup = plan.get("cleanup", "ready")
            if cleanup == "loading_forever":
                send_engine("cleanup", "loading")
            else:
                send_engine("cleanup", cleanup,
                            "cleanup_load_error" if cleanup == "failed"
                            else None)
            continue
        if op not in ("transcribe", "clean"):
            _write_msg({"v": PROTOCOL_VERSION, "op": "fault",
                        "req_id": msg.get("req_id"),
                        "stage": op, "error_type": "ProtocolError",
                        "reason_code": "unknown_op"})
            continue

        behavior = take(op)

        if behavior.startswith("delay:"):
            head, behavior = behavior.split("|", 1)
            time.sleep(int(head[len("delay:"):]) / 1000.0)

        if behavior == "crash":
            os._exit(1)

        if behavior.startswith("stale:"):
            # Unsolicited stale frame: an old request id AND generation 0.
            _write_msg({"v": PROTOCOL_VERSION, "op": "result", "kind": op,
                        "req_id": "req-fabricated-old",
                        "job_id": msg.get("job_id"), "attempt": 99,
                        "generation": 0, "text": behavior[len("stale:"):],
                        "duration_ms": 0.0})
            # And still answer the real request afterwards.
            behavior = "ok:after-stale"

        if behavior.startswith("staleecho:"):
            # A live req_id echoing an OLD generation: the supervisor must
            # discard it as stale and resolve the request as a fault rather
            # than let a generation-mismatched result satisfy anything.
            _write_msg({"v": PROTOCOL_VERSION, "op": "result", "kind": op,
                        "req_id": msg.get("req_id"),
                        "job_id": msg.get("job_id"),
                        "attempt": msg.get("attempt"),
                        "generation": int(msg.get("generation") or 1) - 1,
                        "text": behavior[len("staleecho:"):],
                        "duration_ms": 0.0})
            behavior = "ok:after-staleecho"

        if behavior.startswith("fault:"):
            _write_msg({"v": PROTOCOL_VERSION, "op": "fault",
                        "req_id": msg.get("req_id"),
                        "job_id": msg.get("job_id"), "stage": op,
                        "error_type": behavior[len("fault:"):],
                        "reason_code": "injected_fault"})
            continue

        text = behavior[len("ok:"):] if behavior.startswith("ok:") else behavior
        extras = {}
        if "|" in text:
            text, *rest = text.split("|")
            for part in rest:
                k, _, v = part.partition("=")
                extras[k] = v
        out = {"v": PROTOCOL_VERSION, "op": "result", "kind": op,
               "req_id": msg.get("req_id"), "job_id": msg.get("job_id"),
               "attempt": msg.get("attempt"),
               "generation": msg.get("generation"),
               "text": text, "duration_ms": 0.5,
               "decode_ranges": [[0, 16000]]}
        if op == "clean":
            out["path"] = extras.get("path", "llm")
            out["fallback_reason"] = extras.get("reason")
            out["observations"] = [
                {"kind": "cleanup", "model_id": "fake", "input": text,
                 "system_prompt": "SYS", "examples_count": 0,
                 "prompt": f"<fake prompt {text}>", "max_tokens": 8,
                 "output": text.upper()} for _ in range(int(extras.get(
                     "obs", "1")))]
        _write_msg(out)


if __name__ == "__main__":
    raise SystemExit(main())
