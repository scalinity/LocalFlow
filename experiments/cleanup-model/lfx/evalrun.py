"""Final evaluation on the frozen cases: A, B, C one at a time.

    python -m lfx.evalrun all
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from .common import ART, CONFIG, EXP_DIR, expand, file_sha256, read_json, read_jsonl, utc_now, write_json, write_jsonl

FROZEN = ART / "frozen"
EVAL = ART / "eval"
MODELS = ("A", "B", "C")


def frozen_cases() -> list[dict]:
    rec = read_json(FROZEN / "freeze.json")
    for name, digest in rec["files"].items():
        if file_sha256(FROZEN / name) != digest:
            raise RuntimeError(f"frozen file {name} changed since the freeze")
    cases = read_jsonl(FROZEN / "test_synthetic.jsonl")
    for name in ("real_audio.jsonl", "fixtures.jsonl", "longform.jsonl"):
        cases += read_jsonl(FROZEN / name)
    return cases


def _env(path: str | None = None, tf: bool = True) -> dict:
    env = dict(os.environ, PYTHONPATH=str(EXP_DIR), HF_HOME=str(expand(CONFIG["paths"]["hf_home"])),
               HF_HUB_OFFLINE="1", LFX_TEACHER_FORCED="1" if tf else "0")
    if path:
        env["LFX_MODEL_PATH"] = path
    return env


def model_dir(key: str) -> str:
    from .evaluate import model_path
    return str(model_path(key))


def run_quality() -> None:
    cases = frozen_cases()
    cases_file = EVAL / "final_cases.jsonl"
    EVAL.mkdir(parents=True, exist_ok=True)
    write_jsonl(cases_file, cases)
    for key in MODELS:
        done = len(read_jsonl(EVAL / f"final-{key}.jsonl"))
        if done >= len(cases):
            continue
        subprocess.run([str(expand(CONFIG["paths"]["localai_python"])), "-m", "lfx.evaluate", "run", key,
                        str(cases_file), f"final-{key}"], check=True, env=_env(model_dir(key)), cwd=EXP_DIR)


def run_cold() -> None:
    out_path = EVAL / "cold_loads.json"
    out = read_json(out_path, {})
    for key in MODELS:
        while len(out.get(key, [])) < CONFIG["evaluation"]["cold_load_repeats"]:
            r = subprocess.run([str(expand(CONFIG["paths"]["localai_python"])), "-m", "lfx.evaluate", "cold", key],
                               check=True, env=_env(model_dir(key)), cwd=EXP_DIR, capture_output=True, text=True)
            line = next(l for l in r.stdout.splitlines() if l.startswith("COLD "))
            out.setdefault(key, []).append(json.loads(line[5:]))
            write_json(out_path, out)


def pipeline_ids() -> list[str]:
    real = read_jsonl(FROZEN / "real_audio.jsonl")
    n = CONFIG["evaluation"]["pipeline_clips"] // 2
    pick = []
    for src in ("disfluencyspeech", "fleurs"):
        ids = sorted((c["case_id"] for c in real if c["source"] == src),
                     key=lambda i: hashlib.sha256(i.encode()).hexdigest())
        pick += ids[:n]
    return pick


def run_pipeline() -> None:
    ids_file = EVAL / "pipeline_ids.json"
    ids_file.write_text(json.dumps(pipeline_ids()))
    for key in MODELS:
        if (EVAL / f"pipeline-{key}.jsonl").exists():
            continue
        subprocess.run([str(expand(CONFIG["paths"]["localai_python"])), "-m", "lfx.evaluate", "pipeline", key,
                        str(ids_file)], check=True, env=_env(model_dir(key)), cwd=EXP_DIR)


FIDELITY_SCRIPT = r'''
import json, sys
sys.path.insert(0, sys.argv[3])
from localflow.v2.cleanup import ModelRunner
cases = [json.loads(l) for l in open(sys.argv[2])]
r = ModelRunner(sys.argv[1]); r.load()
eng = r.engine()
out = []
for c in cases:
    res = eng.clean(c["model_input"], locale="en-US", destination_profile=c.get("destination_profile"),
                    relevant_vocabulary=c.get("relevant_vocabulary") or [],
                    protected_spans=[tuple(s) for s in c.get("protected_spans") or []],
                    vocabulary_pairs=tuple(tuple(p) for p in c.get("vocabulary_pairs") or []))
    out.append({"case_id": c["case_id"], "delivered": res.text, "path": res.path})
print("FIDELITY " + json.dumps(out))
'''


def run_fidelity() -> None:
    """Production .venv + production ModelRunner on 50 cases per model; outputs
    must be byte-identical to the LocalAI-venv evaluation."""
    out_path = EVAL / "fidelity.json"
    out = read_json(out_path, {})
    cases = frozen_cases()
    pick = sorted(cases, key=lambda c: hashlib.sha256(c["case_id"].encode()).hexdigest())[
        : CONFIG["evaluation"]["fidelity_cases"]]
    cf = EVAL / "fidelity_cases.jsonl"
    write_jsonl(cf, pick)
    script = EVAL / "fidelity_script.py"
    script.write_text(FIDELITY_SCRIPT)
    for key in MODELS:
        if key in out:
            continue
        r = subprocess.run([str(expand(CONFIG["paths"]["localflow_python"])), str(script), model_dir(key), str(cf),
                            str(EXP_DIR.parents[1])], check=True, capture_output=True, text=True,
                           env=dict(os.environ, HF_HOME=str(expand(CONFIG["paths"]["hf_home"])), HF_HUB_OFFLINE="1"))
        prod = json.loads(next(l for l in r.stdout.splitlines() if l.startswith("FIDELITY "))[9:])
        exp = {x["case_id"]: x for x in read_jsonl(EVAL / f"final-{key}.jsonl")}
        same = [p["delivered"] == exp[p["case_id"]]["delivered"] and p["path"] == exp[p["case_id"]]["path"]
                for p in prod]
        out[key] = {"cases": len(prod), "identical": sum(same),
                    "mismatches": [p["case_id"] for p, s in zip(prod, same) if not s],
                    "runtime": "LocalFlow .venv (production interpreter) + localflow.v2.cleanup.ModelRunner"}
        write_json(out_path, out)


def sizes() -> dict:
    out = {}
    for key in MODELS:
        d = Path(model_dir(key))
        out[key] = sum(f.stat().st_size for f in d.iterdir() if f.is_file() and f.suffix == ".safetensors")
    write_json(EVAL / "artifact_sizes.json", out)
    return out


def main():
    run_quality()
    run_cold()
    run_pipeline()
    run_fidelity()
    sizes()
    write_json(EVAL / "done.json", {"finished": utc_now()})


if __name__ == "__main__":
    {"all": main, "quality": run_quality, "cold": run_cold, "pipeline": run_pipeline,
     "fidelity": run_fidelity, "sizes": sizes}[sys.argv[1]]()
