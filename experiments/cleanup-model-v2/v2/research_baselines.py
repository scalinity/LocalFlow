"""Development-only paper baselines. All execution is opt-in through the CLI.

Importing this module never loads weights, reads a corpus, or creates clients.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from .common import (ART, PRICES, c_identity, file_sha256, read_json,
                     read_jsonl, sha256_text, utc_now, write_json, use_model)
from . import baseline_cost as cost
from .evaluate import Runner, postprocess
from lfx.common import sha256_json
from localflow.v2.cleanup import engine as production

LOCAL = {"base-4b-prod-prompt": "Qwen/Qwen3.5-4B", "base-9b-prod-prompt": "Qwen/Qwen3.5-9B"}
SYSTEMS = {**LOCAL, **cost.CLOUD}
RESEARCH = ART / "research/baselines"
SEED = 20261015
SOURCE_NAMES = ("engine.py", "prompts.py", "validation.py", "document_nodes.py", "correction_retention.py")


def source_identity():
    directory = Path(production.__file__).parent
    return {n: file_sha256(directory / n) for n in SOURCE_NAMES if (directory / n).exists()}


def check_path(path, split):
    path = Path(path)
    forbidden = {"final", "test", "audio", "fresh", "locked", "comparison", "real_audio"}
    # Reject forbidden names before opening anything, including symlink targets.
    import re
    for candidate in (path.absolute(), path.resolve()):
        if forbidden & set(re.split(r"[^a-z0-9]+", str(candidate).lower())):
            raise ValueError("Forbidden data path")
    expected = "train.jsonl" if split == "train" else "validation.jsonl"
    if path.name != expected:
        raise ValueError(f"Use a frozen {expected} pool")
    return path


def pool(path, split):
    path = check_path(path, split)
    freeze = read_json(path.parent / "freeze.json")
    if not freeze or freeze.get("files", {}).get(path.name) != file_sha256(path):
        raise ValueError("Pool has no matching frozen file hash")
    rows = read_jsonl(path)
    allowed = {"train"} if split == "train" else {"validation", "development"}
    if not rows or any(r.get("split") not in allowed or r.get("origin", "synthetic") != "synthetic" for r in rows):
        raise ValueError("Only synthetic rows from the declared split are allowed")
    ids = [r["case_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    return rows


def final_user(prompt):
    from lfx.train import USER_TURN
    if USER_TURN not in prompt:
        raise ValueError("Capture lacks final user turn")
    return prompt.rsplit(USER_TURN, 1)[1].split("<|im_end|>", 1)[0]


def select_fewshot(train_path, output=None, seed=SEED):
    """Five shortest-window TRAIN captures, ranked by seeded SHA256.

    Only the explicitly named TRAIN file and its TRAIN captures are opened.
    The frozen consolidated corpus already excludes held-out text overlaps.
    """
    train_path = check_path(train_path, "train")
    rows = pool(train_path, "train")
    captures_path = train_path.with_name("train_captures.jsonl")
    freeze = read_json(train_path.parent / "freeze.json")
    if freeze["files"].get(captures_path.name) != file_sha256(captures_path):
        raise ValueError("TRAIN capture hash mismatch")
    train = {r["case_id"]: r for r in rows}
    captures = read_jsonl(captures_path)
    if any(c["pair_id"] not in train for c in captures):
        raise ValueError("Capture is outside TRAIN membership")
    candidates = {}
    for cap in captures:
        row = train[cap["pair_id"]]
        if cap["pair_id"] in candidates:
            raise ValueError("Duplicate TRAIN capture")
        main = [c for c in cap["calls"] if c["role"] == "main"]
        corr = [c for c in cap["calls"] if c["role"] == "corrections"]
        if len(main) != 1 or len(corr) > 1 or len(row["model_input"].split()) > 80:
            continue
        if main[0]["completion"] != row["target"]:
            raise ValueError("Capture completion differs from TRAIN target")
        example = {"case_id": row["case_id"], "split": "train", "row_sha256": sha256_json(row),
                   "capture_sha256": sha256_json(cap), "input_sha256": sha256_text(row["model_input"]),
                   "target_sha256": sha256_text(row["target"]),
                   "main_user": final_user(main[0]["prompt"]), "main_answer": main[0]["completion"],
                   "correction_user": final_user(corr[0]["prompt"]) if corr else row["model_input"],
                   "correction_answer": corr[0]["completion"] if corr else "NONE"}
        candidates[row["case_id"]] = example
    ordered = sorted(candidates, key=lambda cid: (sha256_text(f"{seed}|{cid}"), cid))
    if len(ordered) < 5:
        raise ValueError("Need five eligible TRAIN captures")
    examples = [candidates[cid] for cid in ordered[:5]]
    manifest = {"version": 1, "seed": seed,
                "rule": "single main window, at most one correction, <=80 source words; SHA256(seed|case_id)",
                "train_sha256": file_sha256(train_path), "captures_sha256": file_sha256(captures_path),
                "freeze_sha256": file_sha256(train_path.parent / "freeze.json"),
                "examples": examples, "examples_sha256": sha256_json(examples)}
    if output is not None:
        immutable_json(Path(output), manifest)
    return manifest


def load_fewshot(path, cases):
    manifest = read_json(Path(path))
    return validate_fewshot(manifest, cases)


def validate_fewshot(manifest, cases):
    examples = manifest["examples"]
    if len(examples) != 5 or manifest["examples_sha256"] != sha256_json(examples) \
            or any(e.get("split") != "train" for e in examples) \
            or len({e["case_id"] for e in examples}) != 5:
        raise ValueError("Invalid five-example TRAIN manifest")
    ids = {c["case_id"] for c in cases}
    texts = {sha256_text(c[k]) for c in cases for k in ("model_input", "target")}
    if any(e["case_id"] in ids or e["input_sha256"] in texts or e["target_sha256"] in texts for e in examples):
        raise ValueError("Few-shot example overlaps development")
    return manifest


def immutable_json(path, value):
    if path.exists() and read_json(path) != value:
        raise RuntimeError(f"Existing artifact has another identity: {path.name}")
    if not path.exists():
        write_json(path, value)


class NeedCall(Exception):
    def __init__(self, request_id, params):
        self.request_id, self.params = request_id, params


class RecordingEngine(production.CleanupEngine):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(owner.generate, model_id=SYSTEMS[owner.key], render_fn=owner.render,
                         template_revision=owner.mr.template_revision)

    def _generate(self, payload, **kwargs):
        self.owner.kind = kwargs["kind"]
        response, record = super()._generate(payload, **kwargs)
        self.owner.calls[-1].update(role=kwargs["kind"], window=list(kwargs["window_range"]),
                                    depth=kwargs.get("depth", 0), input=kwargs["input_text"],
                                    input_sha256=sha256_text(kwargs["input_text"]),
                                    pass_id=record["pass_id"], parent_pass_id=record.get("parent_pass_id"))
        return response, record


class BaselineRunner(Runner):
    def __init__(self, system, model_path=None, *, fewshot=None, responses=None, planning=False):
        # Avoid historical-engine loaders (which write private source caches).
        self.key, self.path = system, Path(model_path or system)
        self.engine_name, self.module = "updated_source", production
        self.calls, self.fewshot = [], fewshot
        self.responses, self.planning = responses if responses is not None else {}, planning
        self.updated_engine, self.recorded_f, self.adapter = True, False, None
        self.mx = SimpleNamespace(get_peak_memory=lambda: 0)
        self.mr = SimpleNamespace(template_revision="anthropic-messages-five-train-v1")

    def engine(self):
        return RecordingEngine(self)

    def render(self, messages):
        # Preserve the production contract and final user payload, changing
        # demonstration count only. The correction role has its own contract.
        if self.key in LOCAL:
            return self.mr.render(messages)
        role = "correction" if self.kind == "corrections" else "main"
        turns = [messages[0]]
        for example in self.fewshot["examples"]:
            turns.extend([{"role": "user", "content": example[role + "_user"]},
                          {"role": "assistant", "content": example[role + "_answer"]}])
        turns.append(messages[-1])
        return json.dumps(turns, ensure_ascii=False)

    def generate(self, prompt, max_tokens):
        if self.key in LOCAL:
            result = super().generate(prompt, max_tokens)
            self.calls[-1].update(prompt=prompt, output=result["text"], limit_hit=result["limit_hit"])
            return result
        messages = json.loads(prompt)
        params = {"model": SYSTEMS[self.key], "system": messages[0]["content"],
                  "messages": messages[1:], "max_tokens": max_tokens,
                  "temperature": 0, "thinking": {"type": "disabled"}}
        rid = "b" + sha256_text(self.case_id + "|" + sha256_json(params))[:40]
        if self.planning:
            self.requests[rid] = params
            output = "NONE" if self.kind == "corrections" else json.loads(messages[-1]["content"])["transcript"]
            raw = {"text": output, "output_tokens": 0, "limit_hit": False, "finish_reason": "planned"}
        elif rid not in self.responses:
            raise NeedCall(rid, params)
        else:
            raw = self.responses[rid]
        self.calls.append({"request_id": rid, "prompt": prompt, "request": params, "output": raw["text"],
                           "raw_response": raw.get("raw_response"), "usage": raw.get("usage"),
                           "batch_id": raw.get("batch_id"), "custom_id": raw.get("custom_id"),
                           "limit_hit": raw["limit_hit"], "yields": raw["output_tokens"],
                           "finish_reason": raw["finish_reason"], "max_tokens": max_tokens,
                           "first_token_ms": None, "generation_ms": 0})
        return {"text": raw["text"], "output_tokens": raw["output_tokens"],
                "limit_hit": raw["limit_hit"], "prompt": prompt}

    def clean(self, case):
        self.case_id, self.requests = case["case_id"], {}
        row = super().clean(case)
        row["calls"] = self.calls
        row["prompt_regime"] = "production prompt with its built-in examples, no added research examples" if self.key in LOCAL else "5shot-TRAIN"
        row["timing_scope"] = "local_inference" if self.key in LOCAL else "replay_cpu_excludes_batch_wait"
        return row


def identity(system, cases_path, *, fewshot=None, model=None):
    from . import evaluate
    from localflow.v2.cleanup import model as inference
    result = {"model": system, "path": str(model or SYSTEMS[system]), "engine": "updated_source",
              "cases_sha256": file_sha256(Path(cases_path)), "limit": None,
              "engine_source_sha256": source_identity(), "harness_sha256": file_sha256(Path(__file__)),
              "evaluation_source_sha256": file_sha256(Path(evaluate.__file__)),
              "cost_source_sha256": file_sha256(Path(cost.__file__)),
              "inference_source_sha256": file_sha256(Path(inference.__file__)),
              "model_only_postprocess_sha256": sha256_text(inspect.getsource(postprocess)),
              "prompt_regime": "production prompt with its built-in examples, no added research examples" if system in LOCAL else "production-contract-5shot-TRAIN"}
    if fewshot:
        result["fewshot_sha256"] = sha256_json(fewshot)
    return result


def plan(system, cases_path, fewshot_path, out):
    cases = pool(cases_path, "development")
    fewshot = load_fewshot(fewshot_path, cases)
    runner = BaselineRunner(system, fewshot=fewshot, planning=True)
    requests = {}
    for case in cases:
        runner.clean(case)
        requests.update(runner.requests)
    result = {"system": system, "identity": identity(system, cases_path, fewshot=fewshot),
              "fewshot": fewshot, "requests": requests,
              "projection": "preserved inputs, NONE corrections, no limit splits; later calls are adaptive"}
    immutable_json(Path(out), result)
    return result


def validate_local(path, system, c_info):
    path = Path(path)
    cfg = read_json(path / "config.json")
    q = cfg.get("quantization", {})
    if (q.get("bits"), q.get("group_size"), q.get("mode", "affine")) != (4, 64, "affine"):
        raise ValueError("Require 4-bit affine, group 64; precision substitution is forbidden")
    if not c_info.get("quantization", "").startswith("4-bit affine, group 64"):
        raise ValueError("C quantization recipe changed")
    validate_architecture(cfg, system)
    receipt = read_json(path / "baseline-identity.json")
    from lfx.export import content_digest
    if not receipt or receipt["base_repository"] != LOCAL[system] or receipt.get("adapter") is not None:
        raise ValueError("Need an unfine-tuned base export receipt")
    # The digest excludes its own receipt, which is written last.
    hashes = {p.name: file_sha256(p) for p in path.iterdir() if p.is_file() and p.name != "baseline-identity.json"}
    if receipt["files"] != hashes or any("adapter" in n.lower() for n in hashes):
        raise ValueError("Base export changed or contains adapter files")
    return content_digest(path)


def validate_architecture(cfg, system):
    text = cfg.get("text_config", cfg)
    expected = (2560, 9216) if system == "base-4b-prod-prompt" else (4096, 12288)
    if text.get("model_type") != "qwen3_5_text" or text.get("num_hidden_layers") != 32 \
            or (text.get("hidden_size"), text.get("intermediate_size")) != expected:
        raise ValueError("Wrong Qwen3.5 base architecture")


def memory_fit(path, available):
    weight_bytes = sum(p.stat().st_size for p in Path(path).glob("*.safetensors"))
    needed = int(weight_bytes * 1.3) + 3 * 1024 ** 3
    if not weight_bytes or needed > available:
        raise RuntimeError(f"4-bit base cannot fit: need about {needed} bytes, available {available}; no precision substitution")
    return needed


def prepare_base(system, source, output, tokenizer_source, revision):
    """Called by the lead only; stock MLX conversion, never fusion or training."""
    source, output, tokenizer_source = map(Path, (source, output, tokenizer_source))
    if output.exists():
        raise ValueError("Choose a new export directory; existing models are never overwritten")
    cfg = read_json(source / "config.json")
    if cfg.get("quantization") or any(source.glob("*adapter*")):
        raise ValueError("Conversion source must be the unadapted bf16 base")
    if cfg.get("_name_or_path") not in (None, LOCAL[system]):
        raise ValueError("Source repository differs from requested base")
    validate_architecture(cfg, system)
    if source.name != revision or source.parent.name != "snapshots" \
            or source.parent.parent.name != "models--" + LOCAL[system].replace("/", "--"):
        raise ValueError("Use a pinned official Qwen bf16 cache snapshot")
    import shutil
    from lfx.export import TOKENIZER_FILES
    reference = Path(c_identity()["tokenizer_files_from"])
    for name in TOKENIZER_FILES:
        if (reference / name).exists() and (not (tokenizer_source / name).exists() or
                file_sha256(tokenizer_source / name) != file_sha256(reference / name)):
            raise ValueError("Tokenizer/template must match C's reference files")
    subprocess.run([sys.executable, "-m", "mlx_lm", "convert", "--hf-path", str(source),
                    "--mlx-path", str(output), "-q", "--q-bits", "4", "--q-group-size", "64"],
                   check=True, env=dict(os.environ, HF_HUB_OFFLINE="1"))
    for name in TOKENIZER_FILES:
        if (tokenizer_source / name).exists():
            shutil.copyfile(tokenizer_source / name, output / name)
    receipt = {"base_repository": LOCAL[system], "base_revision": revision, "adapter": None,
               "quantization": "4-bit affine, group 64", "source_config_sha256": file_sha256(source / "config.json"),
               "files": {p.name: file_sha256(p) for p in output.iterdir() if p.is_file()}}
    write_json(output / "baseline-identity.json", receipt)
    validate_local(output, system, c_identity())


def output_state(system, expected):
    path = ART / "eval" / f"development-{system}.jsonl"
    meta_path = path.with_suffix(".meta.json")
    meta = read_json(meta_path)
    if meta and meta["identity"] != expected:
        raise RuntimeError("Output identity changed; preserve existing outputs")
    if path.exists() and not meta:
        raise RuntimeError("Output has no identity metadata")
    rows = read_jsonl(path)
    if len({r["case_id"] for r in rows}) != len(rows):
        raise RuntimeError("Duplicate output rows")
    meta = meta or {"identity": expected, "runs": []}
    path.parent.mkdir(parents=True, exist_ok=True)
    return path, meta_path, rows, meta


def local_run(system, cases_path, model_path):
    cases = pool(cases_path, "development")
    expected = identity(system, cases_path, model=model_path)
    expected["model_content_digest"] = validate_local(model_path, system, c_identity())
    runner = BaselineRunner(system, model_path)
    import mlx.core as mx
    import psutil
    if sys.platform != "darwin":
        raise RuntimeError("Local base inference requires MLX on the Mac")
    memory_fit(model_path, psutil.virtual_memory().available)
    path, meta_path, rows, meta = output_state(system, expected)
    done = {r["case_id"] for r in rows}
    if done - {c["case_id"] for c in cases}:
        raise RuntimeError("Output contains cases outside this development pool")
    if len(done) == len(cases):
        return
    try:
        info = runner.load()
        meta["runs"].append({"started": utc_now(), "load": info, "pid": os.getpid()})
        write_json(meta_path, meta)
        with path.open("a") as fh:
            for case in cases:
                if source_identity() != expected["engine_source_sha256"]:
                    raise RuntimeError("Engine changed during local run")
                if case["case_id"] not in done:
                    row = runner.clean(case)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
        meta["runs"][-1]["finished"] = utc_now()
        write_json(meta_path, meta)
    except (MemoryError, RuntimeError) as exc:
        raise RuntimeError(f"{system} stopped at required 4-bit precision; no substitution: {exc}") from exc
    finally:
        if getattr(runner.mr, "_model", None) is not None:
            runner.unload()
        mx.clear_cache()


@contextmanager
def cap_lock():
    RESEARCH.mkdir(parents=True, exist_ok=True)
    with (RESEARCH / ".submit.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def capped_wave(name, requests, model):
    from lfx import batches
    from .common import anthropic_client

    class CappedWave(batches.Wave):
        def submit_pending(self, limit=None):
            with cap_lock():
                upper = sum(cost.charge_bound(self.requests[k]) for k in self.pending()[:limit or None])
                # _reserve below independently checks global spend under the
                # shared ledger lock. This lock serializes the two baselines.
                cost.require_budget(batches.ledger(), [], new_upper=upper)
                return super().submit_pending(limit)

    use_model(model)
    wave = CappedWave(name, requests, lambda text: text, cost.input_bound,
                      client=anthropic_client(max_retries=3), client_noretry=anthropic_client(max_retries=0),
                      purpose=cost.PURPOSE, poll_seconds=45)
    immutable_json(wave.dir / "pricing.json", {"model": model, "batch_usd_per_million": PRICES[model]})
    return wave


def responses_from_wave(wave):
    responses = {}
    # Read the raw batch messages, including max_tokens outcomes, so the engine
    # can perform its normal truncation split. Never invent an empty response.
    raw = {}
    for attempt in wave.manifest["attempts"]:
        if attempt["state"] != "collected":
            raise RuntimeError("Batch has uncollected or ambiguous attempts")
        for result in read_jsonl(wave.dir / f"results-{attempt['batch_id']}.jsonl"):
            raw[(attempt["batch_id"], result["custom_id"])] = result
    for rid in wave.requests:
        outcome = wave.outcomes.get(rid, {})
        if outcome.get("status") not in ("succeeded", "truncated"):
            raise RuntimeError(f"Missing/failed baseline response: {rid} {outcome.get('status')}")
        result = raw[(outcome["batch_id"], outcome["custom_id"])]
        message = result["result"]["message"]
        if message["stop_reason"] not in ("end_turn", "stop_sequence", "max_tokens"):
            raise RuntimeError("Unsupported baseline stop reason")
        responses[rid] = {"text": "".join(b["text"] for b in message["content"] if b["type"] == "text"),
                          "output_tokens": message["usage"]["output_tokens"],
                          "limit_hit": message["stop_reason"] == "max_tokens",
                          "finish_reason": message["stop_reason"], "usage": message["usage"],
                          "raw_response": result, "batch_id": outcome["batch_id"], "custom_id": outcome["custom_id"]}
    return responses


def batch_run(system, cases_path, plan_paths, *, wave_factory=capped_wave):
    """Lead-only execution. Two immutable plans are mandatory before any API use."""
    from lfx import batches
    cases = pool(cases_path, "development")
    plans = [read_json(Path(p)) for p in plan_paths]
    if {p["system"] for p in plans} != set(cost.CLOUD):
        raise ValueError("Need both cloud plans")
    for candidate in plans:
        validate_fewshot(candidate["fewshot"], cases)
        if candidate["identity"] != identity(candidate["system"], cases_path, fewshot=candidate["fewshot"]):
            raise ValueError("Plan differs from current cases, few-shot examples, or engine")
    current = next(p for p in plans if p["system"] == system)
    fewshot = current["fewshot"]
    # Revalidate manifest and overlap without opening any training file.
    validate_fewshot(fewshot, cases)
    expected = identity(system, cases_path, fewshot=fewshot)
    if current["identity"] != expected:
        raise ValueError("Plan differs from current cases, few-shot examples, or engine")
    path, meta_path, rows, meta = output_state(system, expected)
    done = {r["case_id"] for r in rows}
    if done - {c["case_id"] for c in cases}:
        raise RuntimeError("Output contains cases outside this development pool")
    runner = BaselineRunner(system, fewshot=fewshot)
    run_dir = RESEARCH / system
    run_dir.mkdir(parents=True, exist_ok=True)
    immutable_json(run_dir / "identity.json", expected)
    responses_path = run_dir / "responses.json"
    runner.responses.update(read_json(responses_path, {}))
    meta["runs"].append({"started": utc_now(), "pid": os.getpid(), "backend": "anthropic-message-batches"})
    write_json(meta_path, meta)
    for round_no in range(64):
        if source_identity() != expected["engine_source_sha256"]:
            raise RuntimeError("Engine changed during batch run")
        requests, completed = {}, []
        for case in cases:
            if case["case_id"] in done:
                continue
            try:
                completed.append(runner.clean(case))
            except NeedCall as missing:
                requests[missing.request_id] = missing.params
        if completed:
            with path.open("a") as fh:
                for row in completed:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    done.add(row["case_id"])
        if not requests:
            meta["runs"][-1].update(finished=utc_now(), complete=len(done))
            write_json(meta_path, meta)
            return
        # Stable request-set hash makes restart independent of frontier number.
        name = f"research-{system}-{sha256_json(requests)[:16]}"
        if not any(k.startswith("research-") for k in batches.ledger()["entries"]):
            cost.require_budget(batches.ledger(), plans)
        wave = wave_factory(name, requests, SYSTEMS[system])
        wave.run(chunk=200)
        runner.responses.update(responses_from_wave(wave))
        write_json(responses_path, runner.responses)
    raise RuntimeError("64 adaptive frontiers exhausted; retained calls are resumable")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("fewshot")
    s.add_argument("--train-pool", type=Path, required=True)
    s.add_argument("--out", type=Path, default=RESEARCH / "fewshot-examples.json")
    s.add_argument("--seed", type=int, default=SEED)
    s = sub.add_parser("prepare-base")
    s.add_argument("--system", choices=LOCAL, required=True)
    for arg in ("source", "output", "tokenizer-source", "revision"):
        s.add_argument("--" + arg, required=True)
    s = sub.add_parser("plan")
    s.add_argument("--system", choices=cost.CLOUD, required=True)
    s.add_argument("--cases", type=Path, required=True)
    s.add_argument("--fewshot", type=Path, default=RESEARCH / "fewshot-examples.json")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("local")
    s.add_argument("--system", choices=LOCAL, required=True)
    s.add_argument("--cases", type=Path, required=True)
    s.add_argument("--model-dir", type=Path, required=True)
    s = sub.add_parser("batch")
    s.add_argument("--system", choices=cost.CLOUD, required=True)
    s.add_argument("--cases", type=Path, required=True)
    s.add_argument("--plans", nargs=2, type=Path, required=True)
    a = p.parse_args()
    if a.command == "fewshot":
        select_fewshot(a.train_pool, a.out, a.seed)
    elif a.command == "prepare-base":
        prepare_base(a.system, a.source, a.output, a.tokenizer_source, a.revision)
    elif a.command == "plan":
        plan(a.system, a.cases, a.fewshot, a.out)
    elif a.command == "local":
        local_run(a.system, a.cases, a.model_dir)
    else:
        batch_run(a.system, a.cases, a.plans)


if __name__ == "__main__":
    main()
