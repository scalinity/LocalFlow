"""LoRA fine-tuning of the post-trained Qwen/Qwen3.5-4B checkpoint (bf16) on
exact LocalFlow engine prompts captured for both call roles.

* Inputs: ``encode(prompt)`` exactly as ``mlx_lm.stream_generate`` tokenizes a
  string prompt, then ``encode(completion) + <|im_end|>``.
* Loss: response tokens only. mlx-lm 0.31.3's ``default_loss`` mask uses
  ``steps <= length`` and so also scores one padding position after the
  sequence; ``response_loss`` uses ``steps < length`` (covered by a test).
* GatedDeltaNet layers train through ``gdn_chunked`` (patched training path).
* One example per micro-batch (no packing, no truncation), gradient
  accumulation, global-norm clipping, fixed seeds, checkpoints at fractions of
  the run, validation loss on a fixed subset.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

from .common import ART, CONFIG, read_jsonl, utc_now, write_json

TRAIN_DIR = ART / "train"
BUCKET = 256


# ---------------------------------------------------------------- data

def load_examples(captures: list[dict], cfg: dict | None = None, rng_seed: int | None = None,
                  max_examples: int | None = None) -> list[dict]:
    """Flatten captures into (role, prompt, completion) examples with the
    corrections-role share and NONE share capped as configured."""
    cfg = cfg or CONFIG["training"]
    rng = random.Random(rng_seed if rng_seed is not None else cfg["seed"])
    main, corr_pos, corr_none = [], [], []
    for cap in captures:
        for call in cap["calls"]:
            ex = {"pair_id": cap["pair_id"], "family_id": cap["family_id"], "role": call["role"],
                  "prompt": call["prompt"], "completion": call["completion"]}
            if call["role"] == "main":
                main.append(ex)
            elif call["completion"].strip().upper() == "NONE":
                corr_none.append(ex)
            else:
                corr_pos.append(ex)
    rng.shuffle(main)
    rng.shuffle(corr_pos)
    rng.shuffle(corr_none)
    share = cfg["corrections_role_max_share"]
    none_share = cfg["none_share_of_corrections"]
    n_main = len(main) if max_examples is None else min(len(main), int(round(max_examples * (1 - share))))
    main = main[:n_main]
    max_corr = int(n_main * share / (1 - share))
    n_none = min(len(corr_none), int(max_corr * none_share))
    n_pos = min(len(corr_pos), max_corr - n_none)
    n_none = min(len(corr_none), max(n_none, int(n_pos * none_share / (1 - none_share))))
    out = main + corr_pos[:n_pos] + corr_none[:n_none]
    rng.shuffle(out)
    return out


def encode_prompt(tokenizer, prompt: str) -> list[int]:
    """Same rule as mlx_lm.generate for a string prompt."""
    bos = tokenizer.bos_token
    add_special = bos is None or not prompt.startswith(bos)
    return list(tokenizer.encode(prompt, add_special_tokens=add_special))


def im_end_id(tokenizer) -> int:
    tid = tokenizer.convert_tokens_to_ids("<|im_end|>")
    assert isinstance(tid, int) and tid >= 0, "missing <|im_end|>"
    return tid


def encode_example(tokenizer, ex: dict) -> tuple[list[int], int]:
    p = encode_prompt(tokenizer, ex["prompt"])
    c = list(tokenizer.encode(ex["completion"], add_special_tokens=False)) + [im_end_id(tokenizer)]
    return p + c, len(p)


def make_batch(tokens: list[int], offset: int):
    """One example padded to a 256-token bucket (+1 for the shifted target)."""
    import mlx.core as mx
    import numpy as np
    L = len(tokens)
    padded = BUCKET * math.ceil(L / BUCKET) + 1
    arr = np.zeros((1, padded), np.int32)
    arr[0, :L] = tokens
    return mx.array(arr), mx.array([[offset, L]])


def loss_mask(lengths, width: int):
    """Positions t of ``targets`` (predicting token t+1) that are scored:
    exactly the completion tokens and the closing <|im_end|>."""
    import mlx.core as mx
    steps = mx.arange(1, width + 1)
    return mx.logical_and(steps >= lengths[:, 0:1], steps < lengths[:, 1:])


def response_loss(model, batch, lengths):
    """Cross-entropy on the response positions only. The LM head runs on
    those positions alone (logits over a 248k vocabulary for a 3.8k-token
    prompt would cost several GB); the scored positions are exactly the
    ones ``loss_mask`` selects."""
    import mlx.core as mx
    import mlx.nn as nn
    off, L = int(lengths[0, 0].item()), int(lengths[0, 1].item())
    lm = model.language_model
    hidden = lm.model(batch[:, : L - 1])
    sel = hidden[:, off - 1: L - 1]
    logits = lm.model.embed_tokens.as_linear(sel) if lm.args.tie_word_embeddings else lm.lm_head(sel)
    targets = batch[:, off:L]
    ce = nn.losses.cross_entropy(logits.astype(mx.float32), targets)
    ntoks = mx.array(L - off)
    return ce.sum() / ntoks, ntoks


# ---------------------------------------------------------------- model

def base_path() -> Path:
    from .capture import snapshot
    b = CONFIG["models"]["base_bf16"]
    return snapshot(b["repository_id"], b["revision"])


def load_for_training(lora_cfg: dict | None = None, seed: int | None = None):
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.tuner.utils import linear_to_lora_layers
    from .gdn_chunked import patch_qwen3_5
    cfg = CONFIG["training"]
    lora_cfg = lora_cfg or cfg["lora"]
    mx.random.seed(seed if seed is not None else cfg["seed"])
    patch_qwen3_5()
    model, tokenizer = load(str(base_path()))
    model.freeze()
    linear_to_lora_layers(model, lora_cfg["num_layers"],
                          {k: lora_cfg[k] for k in ("rank", "scale", "dropout", "keys")})
    return model, tokenizer


def lora_targets(model) -> dict:
    from mlx_lm.tuner.lora import LoRALinear
    found = {}
    for name, m in model.named_modules():
        if isinstance(m, LoRALinear):
            key = ".".join(name.split(".")[-2:])
            found[key] = found.get(key, 0) + 1
    return found


def adapter_config(lora_cfg: dict) -> dict:
    b = CONFIG["models"]["base_bf16"]
    return {"fine_tune_type": "lora", "num_layers": lora_cfg["num_layers"],
            "lora_parameters": {k: lora_cfg[k] for k in ("rank", "scale", "dropout", "keys")},
            "base_model": {"repository_id": b["repository_id"], "revision": b["revision"]},
            "training": "experiments/cleanup-model (LocalFlow cleanup LoRA, PRODUCT_AUTOGENERATED data)"}


def save_adapter(model, out_dir: Path, lora_cfg: dict, extra: dict | None = None) -> None:
    import mlx.core as mx
    from mlx.utils import tree_flatten
    out_dir.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(out_dir / "adapters.safetensors"), dict(tree_flatten(model.trainable_parameters())))
    write_json(out_dir / "adapter_config.json", {**adapter_config(lora_cfg), **(extra or {})})


def global_norm(tree) -> float:
    import mlx.core as mx
    from mlx.utils import tree_flatten
    return math.sqrt(sum(mx.sum(g.astype(mx.float32) ** 2).item() for _, g in tree_flatten(tree)))


# ---------------------------------------------------------------- prefix-cached training

USER_TURN = "<|im_start|>user\n"


def split_example(tokenizer, ex: dict) -> dict:
    """Split at the final user turn: the shared prefix (system prompt and
    few-shot turns, identical for every example of a role and destination
    profile) and the per-example suffix (payload + response)."""
    i = ex["prompt"].rfind(USER_TURN)
    prefix = ex["prompt"][:i]
    tokens, off = encode_example(tokenizer, ex)
    p_ids = encode_prompt(tokenizer, prefix)
    if tokens[: len(p_ids)] != p_ids:
        raise ValueError("prefix tokenization does not align with the full prompt")
    from .common import sha256_text
    return {"key": sha256_text(prefix), "prefix": p_ids, "suffix": tokens[len(p_ids):],
            "off_s": off - len(p_ids), "n_tokens": len(tokens), "n_response": len(tokens) - off}


def prefix_cache(model, prefix_ids: list[int]):
    """Prefix states under the current adapter weights, outside autodiff
    (forward-exact; gradients do not flow back into the shared prefix)."""
    import mlx.core as mx
    was_training = model.training
    model.eval()
    cache = model.make_cache()
    model.language_model.model(mx.array([prefix_ids]), cache)
    mx.eval([c.state for c in cache])
    if was_training:
        model.train()
    return cache


def clone_cache(cache):
    from mlx_lm.models.cache import ArraysCache, KVCache
    out = []
    for c in cache:
        if isinstance(c, KVCache):
            n = KVCache()
            n.keys, n.values, n.offset = c.keys[..., : c.offset, :], c.values[..., : c.offset, :], c.offset
        else:
            n = ArraysCache(len(c.cache))
            n.cache = list(c.cache)
        out.append(n)
    return out


def cached_response_loss(model, suffix, cache, off_s: int):
    """Loss on the response tokens of the suffix, attending to a cached prefix."""
    import mlx.core as mx
    import mlx.nn as nn
    lm = model.language_model
    S = suffix.shape[1]
    hidden = lm.model(suffix[:, : S - 1], cache)
    sel = hidden[:, off_s - 1: S - 1]
    logits = lm.model.embed_tokens.as_linear(sel) if lm.args.tie_word_embeddings else lm.lm_head(sel)
    ce = nn.losses.cross_entropy(logits.astype(mx.float32), suffix[:, off_s:S])
    return ce.sum() / (S - off_s), mx.array(S - off_s)


def make_blocks(items: list[dict], size: int, seed: int) -> list[list[dict]]:
    """Accumulation blocks that share one prefix, in shuffled order."""
    rng = random.Random(seed)
    groups: dict = {}
    for it in items:
        groups.setdefault(it["key"], []).append(it)
    blocks = []
    for key in sorted(groups):
        g = groups[key]
        rng.shuffle(g)
        blocks += [g[i:i + size] for i in range(0, len(g), size)]
    rng.shuffle(blocks)
    return blocks


def train_loop(model, tokenizer, train_examples: list[dict], val_examples: list[dict], run_dir: Path, *,
               lr: float, warmup: int, grad_accum: int, checkpoints: int, max_seq_length: int,
               lora_cfg: dict, log_every: int = 10, eval_every: int | None = None,
               max_updates: int | None = None, time_budget_s: float | None = None, seed: int | None = None) -> dict:
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_map
    from mlx_lm.tuner.utils import build_schedule
    from .gdn_chunked import CALLS

    items = [split_example(tokenizer, ex) for ex in train_examples]
    longest = max(it["n_tokens"] for it in items)
    if longest > max_seq_length:
        raise ValueError(f"example of {longest} tokens exceeds max_seq_length {max_seq_length}; refusing to truncate")
    run_dir.mkdir(parents=True, exist_ok=True)
    val_items = [split_example(tokenizer, ex) for ex in val_examples]
    seed = CONFIG["training"]["seed"] if seed is None else seed
    blocks = make_blocks(items, grad_accum, seed)
    n_updates = len(blocks) if max_updates is None else min(max_updates, len(blocks))
    schedule = build_schedule({"name": "cosine_decay", "arguments": [lr, max(1, n_updates - warmup), lr * 0.05],
                               "warmup": warmup})
    optimizer = optim.AdamW(learning_rate=schedule, weight_decay=0.0)
    mx.set_cache_limit(2 * 1024 ** 3)
    model.train()
    loss_and_grad = nn.value_and_grad(model, cached_response_loss)
    save_at = sorted({max(1, round(n_updates * (i + 1) / checkpoints)) for i in range(checkpoints)})
    eval_every = eval_every or max(1, n_updates // 10)
    metrics = open(run_dir / "metrics.jsonl", "a")

    def log(rec):
        rec["time"] = utc_now()
        metrics.write(json.dumps(rec) + "\n")
        metrics.flush()

    def val_loss():
        tot, ntok = 0.0, 0
        caches: dict = {}
        model.eval()
        for it in val_items:
            if it["key"] not in caches:
                caches[it["key"]] = prefix_cache(model, it["prefix"])
            l, n = cached_response_loss(model, mx.array([it["suffix"]]), clone_cache(caches[it["key"]]), it["off_s"])
            mx.eval(l)
            tot += l.item() * int(n.item())
            ntok += int(n.item())
        model.train()
        mx.clear_cache()
        return tot / max(ntok, 1)

    log({"event": "start", "examples": len(items), "updates": n_updates, "blocks": len(blocks),
         "grad_accum": grad_accum, "lr": lr, "warmup": warmup, "save_at": save_at, "longest_tokens": longest,
         "prefix_groups": len({it["key"] for it in items}), "val_examples": len(val_items),
         "method": "prefix-cached: shared prefix forward under current weights, gradient through suffix"})
    if val_items:
        log({"event": "val", "update": 0, "val_loss": val_loss()})
    mx.reset_peak_memory()
    started = t0 = time.perf_counter()
    tok_count, window_loss, window_n, update = 0, 0.0, 0, 0
    for block in blocks[:n_updates]:
        cache = prefix_cache(model, block[0]["prefix"])
        accum = None
        for it in block:
            (loss, n), grads = loss_and_grad(model, mx.array([it["suffix"]]), clone_cache(cache), it["off_s"])
            accum = grads if accum is None else tree_map(lambda x, y: x + y, accum, grads)
            mx.eval(loss, accum)
            lv = loss.item()
            if not math.isfinite(lv):
                raise FloatingPointError(f"non-finite loss at update {update + 1}")
            window_loss += lv
            window_n += 1
            tok_count += it["n_tokens"]
        accum = tree_map(lambda g: g / len(block), accum)
        gnorm = global_norm(accum)
        if not math.isfinite(gnorm):
            raise FloatingPointError(f"non-finite gradient norm at update {update + 1}")
        accum, _ = optim.clip_grad_norm(accum, 1.0)
        optimizer.update(model, accum)
        mx.eval(model.parameters(), optimizer.state)
        del accum, cache
        mx.clear_cache()
        update += 1
        if update % log_every == 0 or update == n_updates:
            dt = time.perf_counter() - t0
            log({"event": "train", "update": update, "loss": window_loss / window_n, "grad_norm": gnorm,
                 "lr": float(schedule(update)), "tokens_per_s": tok_count / dt,
                 "examples_per_s": window_n / dt, "peak_mem_gb": mx.get_peak_memory() / 1e9,
                 "chunked_gdn_calls": CALLS["chunked"]})
            t0, tok_count, window_loss, window_n = time.perf_counter(), 0, 0.0, 0
        if val_items and (update % eval_every == 0 or update == n_updates):
            log({"event": "val", "update": update, "val_loss": val_loss()})
        if update in save_at:
            save_adapter(model, run_dir / f"ckpt-{update:05d}", lora_cfg, {"update": update})
            log({"event": "checkpoint", "update": update, "path": str(run_dir / f"ckpt-{update:05d}")})
        if time_budget_s and time.perf_counter() - started > time_budget_s:
            save_adapter(model, run_dir / f"ckpt-{update:05d}", lora_cfg, {"update": update, "stopped": "time_budget"})
            log({"event": "stopped_time_budget", "update": update})
            break
    save_adapter(model, run_dir / "final", lora_cfg, {"update": update})
    log({"event": "done", "update": update, "elapsed_s": time.perf_counter() - started})
    metrics.close()
    return {"updates": update}
