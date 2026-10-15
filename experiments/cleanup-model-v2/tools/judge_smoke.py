"""Lead-only live smoke test: one OpenAI Batch containing three built-in toys.

Do not run during implementation. Reusing --name resumes the same purchase.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.judge import SCHEMA, SYSTEM, parse_verdicts
from v2.judge_backends import MODELS, OtherWave, estimate, request_params


def smoke(name="toy-smoke-v1", *, root=None, client=None):
    toys = [("um bring the red cup", "Bring the red cup."),
            ("Keep five bolts.", "Keep five bolts."),
            ("meet Tuesday no Wednesday", "Meet Wednesday.")]
    requests = {}
    for i, (source, text) in enumerate(toys):
        view = {"source": source, "outputs": [{"output_id": f"toy-{i}", "text": text}],
                "vocabulary": [], "reference": text, "is_noop": source == text}
        requests[f"toy-{i}"] = {"model": MODELS["openai"], "max_tokens": 2800,
            "system": [{"type": "text", "text": SYSTEM}],
            "messages": [{"role": "user", "content": json.dumps(view)}],
            "output_config": {"format": {"schema": SCHEMA}}}
    maximum = sum(estimate("openai", request_params(p, "openai")) for p in requests.values())
    if maximum >= 0.25:
        raise RuntimeError("Toy smoke estimate must remain below $0.25")
    wave = OtherWave(name, requests, parse_verdicts, "openai", root=root, client=client)
    wave.run(chunk=3)
    usage = {k: sum(a.get("usage", {}).get(k, 0) for a in wave.manifest["attempts"])
             for k in ("input_tokens", "output_tokens")}
    result = {"backend": "openai", "model": MODELS["openai"], "usage": usage,
              "actual_usd": sum(a.get("actual_usd", 0) for a in wave.manifest["attempts"]),
              "estimate_max_usd": maximum,
              "statuses": {rid: out["status"] for rid, out in wave.outcomes.items()}}
    print(json.dumps(result))
    if len(wave.outcomes) != 3 or any(o["status"] != "succeeded" for o in wave.outcomes.values()):
        raise RuntimeError("Toy smoke did not return three valid responses; see recorded usage and outcomes")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="toy-smoke-v1")
    smoke(parser.parse_args().name)
