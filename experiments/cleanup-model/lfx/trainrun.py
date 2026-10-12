"""Train C, choose the checkpoint on validation (preservation first), export it.

    python -m lfx.trainrun train | select | export
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from .common import ART, CONFIG, EXP_DIR, expand, read_json, read_jsonl, utc_now, write_json, write_jsonl
from . import train

RUN = ART / "train" / "main"
SECONDS_PER_EXAMPLE = 2.3       # measured in the smoke run (~2.1 s), with margin


def _examples():
    caps = read_jsonl(ART / "dataset" / "train_captures.jsonl")
    ex = train.load_examples(caps)
    vcaps = read_jsonl(ART / "dataset" / "validation_captures.jsonl")
    vex = train.load_examples(vcaps, rng_seed=99)
    rng = random.Random(5)
    rng.shuffle(vex)
    return ex, vex[: CONFIG["training"]["val_loss_examples"]]


def run_train(lr: float | None = None, run_dir: Path = RUN, epochs: float | None = None) -> dict:
    cfg = CONFIG["training"]
    ex, vex = _examples()
    epochs = epochs or cfg["epochs"]
    if epochs != 1:
        rng = random.Random(cfg["seed"] + 1)
        extra = ex[:]
        rng.shuffle(extra)
        ex = ex + extra[: int(len(ex) * (epochs - 1))]
    budget_s = cfg["time_budget_hours"] * 3600
    max_updates = int(budget_s / (SECONDS_PER_EXAMPLE * cfg["grad_accumulation"]))
    model, tok = train.load_for_training()
    write_json(run_dir / "plan.json", {"examples": len(ex), "val_examples": len(vex), "lr": lr or cfg["learning_rate"],
                                       "epochs": epochs, "max_updates_by_budget": max_updates,
                                       "roles": {r: sum(e["role"] == r for e in ex) for r in ("main", "corrections")},
                                       "lora": cfg["lora"], "started": utc_now()})
    out = train.train_loop(model, tok, ex, vex, run_dir, lr=lr or cfg["learning_rate"], warmup=cfg["warmup_updates"],
                           grad_accum=cfg["grad_accumulation"], checkpoints=cfg["checkpoints"], max_seq_length=4608,
                           lora_cfg=cfg["lora"], log_every=5, max_updates=max_updates,
                           time_budget_s=budget_s * 1.15)
    return out


# ---------------------------------------------------------------- selection

def _eval(key: str, path: str | None, cases_file: Path, out_name: str, teacher_forced: bool = False) -> None:
    env = dict(os.environ, PYTHONPATH=str(EXP_DIR), HF_HOME=str(expand(CONFIG["paths"]["hf_home"])),
               HF_HUB_OFFLINE="1", LFX_TEACHER_FORCED="1" if teacher_forced else "0")
    if path:
        env["LFX_MODEL_PATH"] = path
    subprocess.run([str(expand(CONFIG["paths"]["localai_python"])), "-m", "lfx.evaluate", "run", key,
                    str(cases_file), out_name], check=True, env=env, cwd=EXP_DIR)


def val_summary(out_name: str, cases: dict) -> dict:
    from .score import rate, score_synthetic
    rows = read_jsonl(ART / "eval" / f"{out_name}.jsonl")
    mo = [score_synthetic(cases[r["case_id"]], r.get("model_only"), delivered=False) for r in rows]
    de = [score_synthetic(cases[r["case_id"]], r.get("delivered"), delivered=True) for r in rows]
    pct = lambda ms, k: 100 * (rate([m.get(k) for m in ms]) or 0)
    return {"n": len(rows), "model_only_damage": pct(mo, "damage"), "delivered_damage": pct(de, "damage"),
            "noop_preserved": pct(mo, "noop_preserved"), "model_only_repair": pct(mo, "repair_success"),
            "delivered_repair": pct(de, "repair_success"),
            "fallback": 100 * sum(r["path"] != "llm" for r in rows) / max(len(rows), 1)}


def run_select() -> dict:
    from . import export
    val = read_jsonl(ART / "dataset" / "validation.jsonl")
    cases_file = ART / "dataset" / "validation_eval_cases.jsonl"
    write_jsonl(cases_file, val)
    cases = {p["case_id"]: p for p in val}
    results = {}
    for key in ("A", "B"):
        _eval(key, None, cases_file, f"val-{key}")
        results[key] = val_summary(f"val-{key}", cases)
    ckpts = sorted(p for p in RUN.glob("ckpt-*") if (p / "adapters.safetensors").exists())
    for ck in ckpts:
        q = export.candidate(ck, f"main-{ck.name}")
        _eval("C", str(q), cases_file, f"val-C-{ck.name}")
        results[ck.name] = val_summary(f"val-C-{ck.name}", cases)
        results[ck.name]["candidate_dir"] = str(q)
    cands = {k: v for k, v in results.items() if k.startswith("ckpt-")}
    best_damage = min(v["model_only_damage"] for v in cands.values())
    best_noop = max(v["noop_preserved"] for v in cands.values())
    eligible = {k: v for k, v in cands.items() if v["model_only_damage"] <= best_damage + 1.0
                and v["noop_preserved"] >= best_noop - 2.0}
    chosen = max(eligible, key=lambda k: (eligible[k]["delivered_repair"], -eligible[k]["fallback"],
                                          -eligible[k]["model_only_damage"]))
    sel = {"selected": chosen, "rule": "eligible = model-only damage within 1pp of best and no-op preservation "
           "within 2pp of best; choose highest delivered repair success, then lower fallback",
           "results": results, "selected_at": utc_now()}
    write_json(ART / "train" / "selection.json", sel)
    for k, v in cands.items():               # free disk: keep only the chosen candidate
        if k != chosen and Path(v["candidate_dir"]).exists():
            shutil.rmtree(v["candidate_dir"])
    return sel


# ---------------------------------------------------------------- export

def run_export() -> dict:
    from . import export
    sel = read_json(ART / "train" / "selection.json")
    ck = RUN / sel["selected"]
    q = Path(sel["results"][sel["selected"]]["candidate_dir"])
    fused = export.fuse(ck, export.EXPORT / "fused-selected")
    ex = read_jsonl(ART / "dataset" / "validation_captures.jsonl")[0]["calls"][-1]
    check = export.fused_logit_check(ck, fused, ex["prompt"])
    shutil.rmtree(fused)
    info = export.install_c(q, ck, {"checkpoint": sel["selected"], "validation": sel["results"][sel["selected"]],
                                    "fused_logit_check": check})
    # The production loader (LocalFlow's own .venv and ModelRunner) accepts C.
    out = subprocess.run([str(expand(CONFIG["paths"]["localflow_python"])), str(EXP_DIR / "lfx" / "loader_check.py"),
                          info["snapshot_path"], str(EXP_DIR.parents[1])], capture_output=True, text=True,
                         env=dict(os.environ, HF_HUB_OFFLINE="1"), check=True)
    info["production_loader_check"] = json.loads(out.stdout.strip().splitlines()[-1])
    write_json(export.EXPORT / "C_identity.json", info)
    return info


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "train":
        print(json.dumps(run_train()))
    elif cmd == "select":
        print(json.dumps(run_select()["selected"]))
    elif cmd == "export":
        print(json.dumps(run_export(), default=str)[:2000])
