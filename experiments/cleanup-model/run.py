"""LocalFlow cleanup-model experiment: one resumable orchestrator.

    HF_HOME=~/Documents/LocalAI/models ~/Documents/LocalAI/.venv/bin/python \
        experiments/cleanup-model/run.py all          # run or resume everything
    ... run.py status                                  # what is done, spend so far
    ... run.py all --dry-run                           # show what would run

Every stage checks its own outputs and skips finished work. Claude batches
resume from their manifests (results matched by custom_id; nothing already
returned is bought again). Model jobs run one at a time in child processes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
os.environ.setdefault("HF_HOME", str(Path("~/Documents/LocalAI/models").expanduser()))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from lfx.common import ART, CONFIG, expand, read_json, read_jsonl, utc_now, write_json  # noqa: E402

LOCALAI_PY = str(expand(CONFIG["paths"]["localai_python"]))
LOCALFLOW_PY = str(expand(CONFIG["paths"]["localflow_python"]))
STATE = ART / "state.json"
GEN_WAVES = [("gen-pilot", "train", 72, "p", None), ("gen-test", "test", 470, "", None),
             ("gen-validation", "validation", 380, "", None), ("gen-train", "train", 4200, "", 120)]


def state() -> dict:
    return read_json(STATE, {})


def mark(stage: str, **info):
    s = state()
    s[stage] = {"done": True, "time": utc_now(), **info}
    write_json(STATE, s)


def sh(args: list[str], log: str, python: str = LOCALAI_PY, env: dict | None = None) -> None:
    e = dict(os.environ)
    e["PYTHONPATH"] = str(EXP)
    e.update(env or {})
    (ART / "logs").mkdir(parents=True, exist_ok=True)
    with open(ART / "logs" / log, "a") as fh:
        subprocess.run([python, *args], cwd=EXP, env=e, check=True, stdout=fh, stderr=subprocess.STDOUT)


# ---------------------------------------------------------------- stages

def st_incumbent():
    from lfx import incumbent
    r = incumbent.verify()
    mark("incumbent", verified=r["verified"])


def st_audio():
    from lfx import audio
    audio.prepare()
    if not (ART / "real" / "asr.jsonl").exists() or len(read_jsonl(ART / "real" / "asr.jsonl")) < len(read_jsonl(audio.CASES)):
        sh(["-m", "lfx.audio", "asr"], "asr.log", python=LOCALFLOW_PY)
    if not (ART / "real" / "style_exemplars.json").exists():
        audio.style_decode()
        sh(["-m", "lfx.audio", "style"], "asr.log", python=LOCALFLOW_PY)
    mark("audio", cases=len(read_jsonl(audio.CASES)))


def st_generate():
    from lfx import batches, datagen, synth
    from lfx.common import write_json as wj
    batches.set_reservation("verify", CONFIG["claude"]["reserve_usd"]["verify"])
    batches.set_reservation("judge", CONFIG["claude"]["reserve_usd"]["judge"])
    for name, split, n, tag, chunk in GEN_WAVES:
        if wave_finished(name) and (ART / "pairs" / f"{name}.stats.json").exists():
            continue                      # never rebuild a finished wave's requests
        specs = synth.seed_plan(split, n, seed_tag=tag)
        requests, spec_map = datagen.plan_requests(name, specs)
        if not (ART / "claude" / name / "specs.json").exists():
            wj(ART / "claude" / name / "specs.json", spec_map)
        c, nr = datagen.clients()
        w = batches.Wave(name, requests, parse=synth.parse_generation,
                         est_input_tokens=lambda p: datagen.GEN_INPUT_TOKENS, client=c, client_noretry=nr,
                         purpose="generation")
        w.run(chunk=chunk)
        if not (ART / "pairs" / f"{name}.stats.json").exists():
            datagen.process_generation(name)
    mark("generate")


VERIFY_PLAN = [("gen-pilot", 1.0), ("gen-test", 1.0), ("gen-validation", 1.0), ("gen-train", 0.15)]


def wave_finished(name: str) -> bool:
    """A wave whose manifest exists and has nothing pending or in flight."""
    m = read_json(ART / "claude" / name / "manifest.json")
    if not m:
        return False
    outcomes = read_json(ART / "claude" / name / "outcomes.json", {})
    inflight = any(a["state"] in ("creating", "ambiguous", "submitted") for a in m["attempts"])
    return not inflight and len(outcomes) == m["request_count"]


def st_verify():
    from lfx import batches, datagen
    out = {}
    for wave, frac in VERIFY_PLAN:
        if not wave_finished("ver-" + wave.replace("gen-", "")):
            out[wave] = datagen.verify_wave(wave, frac)
    if not wave_finished("ver-train-rest"):
        out["gen-train-rest"] = datagen.verify_remaining("gen-train", ["ver-train"], "ver-train-rest")
    batches.set_reservation("verify", 0.0)
    mark("verify", **out)


def st_assemble():
    from lfx import assemble, datagen
    if (assemble.FROZEN / "freeze.json").exists() and (assemble.DATA / "train.jsonl").exists():
        mark("assemble", note="already frozen and assembled")
        return
    assemble.freeze_eval()
    assemble.finalize_train()
    mark("assemble")


def st_train():
    if (ART / "train" / "main" / "final" / "adapters.safetensors").exists():
        mark("train", note="already trained")
        return
    sh(["-m", "lfx.trainrun", "train"], "train_main.log")
    mark("train")


def st_select():
    if (ART / "train" / "selection.json").exists():
        return mark("select", note="already selected")
    sh(["-m", "lfx.trainrun", "select"], "select.log")
    mark("select")


def st_export():
    if (ART / "export" / "C_identity.json").exists():
        return mark("export", note="already exported")
    sh(["-m", "lfx.trainrun", "export"], "export.log")
    mark("export")


def st_evaluate():
    sh(["-m", "lfx.evalrun", "all"], "evaluate.log")
    mark("evaluate")


def st_judge():
    sh(["-m", "lfx.judge", "run"], "judge.log")
    mark("judge")


def st_analyze():
    sh(["-m", "lfx.analyze"], "analyze.log")
    mark("analyze")


def st_report():
    sh(["-m", "lfx.report"], "report.log")
    mark("report")


STAGES = [("incumbent", st_incumbent), ("audio", st_audio), ("generate", st_generate), ("verify", st_verify),
          ("assemble", st_assemble), ("train", st_train), ("select", st_select), ("export", st_export),
          ("evaluate", st_evaluate), ("judge", st_judge), ("analyze", st_analyze), ("report", st_report)]


def status():
    from lfx import batches
    s = state()
    for name, _ in STAGES:
        print(f"{name:10s} {'done ' + s[name]['time'] if s.get(name, {}).get('done') else 'pending'}")
    t = batches.ledger_totals()
    print(f"claude spend: actual ${t['actual_usd']:.2f}, outstanding max ${t['outstanding_max_usd']:.2f}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    dry = "--dry-run" in argv
    if cmd == "status":
        return status()
    todo = STAGES if cmd == "all" else [st for st in STAGES if st[0] == cmd]
    if not todo:
        raise SystemExit(f"unknown stage {cmd}; stages: {[n for n, _ in STAGES]}")
    s = state()
    for name, fn in todo:
        if cmd == "all" and s.get(name, {}).get("done"):
            print(f"[skip] {name} (done {s[name]['time']})")
            continue
        if dry:
            print(f"[would run] {name}")
            continue
        print(f"[run] {name}", flush=True)
        fn()


if __name__ == "__main__":
    main(sys.argv)
