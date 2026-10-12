"""Real train -> save -> reload -> generate check on Qwen3.5-4B (bf16).

``python -m lfx.smoke train``   (LoRA targets, finite loss/grad, adapter
weights change, overfit check, throughput, peak memory, adapter saved)
``python -m lfx.smoke reload``  (fresh process: load(base, adapter_path),
logits match the trained in-process model, greedy generation is non-empty
and thinking-free)
"""

from __future__ import annotations

import json
import sys
import time

from .common import ART, CONFIG, read_jsonl, write_json
from . import train

SMOKE = ART / "train" / "smoke"


def _examples(n: int) -> list[dict]:
    caps = read_jsonl(ART / "captures" / "gen-pilot.jsonl")
    ex = train.load_examples(caps)
    mains = [e for e in ex if e["role"] == "main"][: n - n // 4]
    corr = [e for e in ex if e["role"] == "corrections"][: n // 4]
    return mains + corr


def run_train() -> dict:
    import mlx.core as mx
    import numpy as np
    from mlx.utils import tree_flatten
    from .gdn_chunked import CALLS
    lora = CONFIG["training"]["lora"]
    model, tok = train.load_for_training()
    targets = train.lora_targets(model)
    before = {k: np.array(v.astype(mx.float32)) for k, v in tree_flatten(model.trainable_parameters())}
    examples = _examples(16)
    # Response-only loss equals the full-logit masked loss (shortest example).
    import mlx.nn as nn
    short = min(examples, key=lambda e: len(e["prompt"]))
    toks, off = train.encode_example(tok, short)
    b, ln = train.make_batch(toks, off)
    model.eval()
    full = model(b[:, :-1])
    m = train.loss_mask(ln, b.shape[1] - 1)
    ce_full = ((nn.losses.cross_entropy(full.astype(mx.float32), b[:, 1:]) * m).sum() / m.sum()).item()
    ce_resp = train.response_loss(model, b, ln)[0].item()
    # Prefix-cached loss equals the full-sequence loss (eval mode, both roles).
    cached_vs_full = []
    for ex in (next(e for e in examples if e["role"] == "main"), next(e for e in examples if e["role"] == "corrections")):
        t_, o_ = train.encode_example(tok, ex)
        b_, l_ = train.make_batch(t_, o_)
        full_l = train.response_loss(model, b_, l_)[0].item()
        it = train.split_example(tok, ex)
        c_l = train.cached_response_loss(model, mx.array([it["suffix"]]), train.clone_cache(
            train.prefix_cache(model, it["prefix"])), it["off_s"])[0].item()
        cached_vs_full.append([ex["role"], full_l, c_l])
    model.train()
    # 1) 24 micro-steps, accumulation 4 -> 6 updates, real-length prompts: finiteness, change, throughput.
    t0 = time.perf_counter()
    out = train.train_loop(model, tok, (examples * 2)[:24], examples[:4], SMOKE / "run", lr=1e-4, warmup=1,
                           grad_accum=4, checkpoints=1, max_seq_length=8192, lora_cfg=lora, log_every=1,
                           eval_every=6)
    elapsed = time.perf_counter() - t0
    after = {k: np.array(v.astype(mx.float32)) for k, v in tree_flatten(model.trainable_parameters())}
    changed = sum(not np.array_equal(before[k], after[k]) for k in before)
    lora_b = [k for k in after if k.endswith("lora_b")]
    b_nonzero = sum(bool(np.any(after[k] != 0)) for k in lora_b)
    metrics = read_jsonl(SMOKE / "run" / "metrics.jsonl")
    tr = [m for m in metrics if m["event"] == "train"]
    # 2) overfit 4 short examples: loss must fall.
    tiny = sorted(examples, key=lambda e: len(e["prompt"]))[:4]
    model2, _ = train.load_for_training(seed=1)
    out2 = train.train_loop(model2, tok, tiny * 12, [], SMOKE / "overfit", lr=3e-4, warmup=1, grad_accum=1,
                            checkpoints=1, max_seq_length=8192, lora_cfg=lora, log_every=4)
    of = [m for m in read_jsonl(SMOKE / "overfit" / "metrics.jsonl") if m["event"] == "train"]
    tokens = [len(train.encode_example(tok, e)[0]) for e in examples]
    report = {
        "loss_full_vs_response": [ce_full, ce_resp], "loss_paths_agree": abs(ce_full - ce_resp) < 2e-3,
        "cached_vs_full": cached_vs_full,
        "cached_agrees": all(abs(a - b) < 2e-3 + 1e-2 * abs(a) for _, a, b in cached_vs_full),
        "lora_targets": targets, "trainable_tensors": len(before), "tensors_changed": changed,
        "lora_b_nonzero": f"{b_nonzero}/{len(lora_b)}",
        "train_losses": [m["loss"] for m in tr], "grad_norms": [m["grad_norm"] for m in tr],
        "all_finite": all(np.isfinite(m["loss"]) and np.isfinite(m["grad_norm"]) for m in tr),
        "tokens_per_s": [round(m["tokens_per_s"], 1) for m in tr],
        "peak_mem_gb": max(m["peak_mem_gb"] for m in tr), "chunked_gdn_calls": CALLS["chunked"],
        "example_tokens": {"min": min(tokens), "max": max(tokens), "mean": sum(tokens) / len(tokens)},
        "elapsed_s_24_microsteps": elapsed,
        "overfit_first_last": [of[0]["loss"], of[-1]["loss"]] if of else None,
        "adapter_dir": str(SMOKE / "run" / "final"),
    }
    # Reference logits from the trained in-process model for the reload check.
    ex = examples[0]
    tokens0, _ = train.encode_example(tok, ex)
    model.eval()
    logits = model(mx.array([tokens0]))[0, -8:].astype(mx.float32)
    np.save(SMOKE / "ref_logits.npy", np.array(logits))
    write_json(SMOKE / "ref_example.json", ex)
    write_json(SMOKE / "train_report.json", report)
    return report


def run_reload() -> dict:
    import mlx.core as mx
    import numpy as np
    from mlx_lm import load
    from mlx_lm.generate import stream_generate
    from mlx_lm.sample_utils import make_sampler
    ex = json.loads((SMOKE / "ref_example.json").read_text())
    model, tok = load(str(train.base_path()), adapter_path=str(SMOKE / "run" / "final"))
    tokens0, off = train.encode_example(tok, ex)
    logits = np.array(model(mx.array([tokens0]))[0, -8:].astype(mx.float32))
    ref = np.load(SMOKE / "ref_logits.npy")
    max_diff = float(np.max(np.abs(logits - ref)))
    text = "".join(r.text for r in stream_generate(model, tok, prompt=ex["prompt"], max_tokens=200,
                                                   sampler=make_sampler(temp=0.0)))
    report = {"reload_logit_max_abs_diff": max_diff, "logits_match": max_diff < 1e-2,
              "generation": text[:400], "nonempty": bool(text.strip()), "think_free": "<think>" not in text,
              "expected": ex["completion"][:400],
              "eos_ids": sorted(int(i) for i in getattr(tok, "eos_token_ids", []) or [])}
    write_json(SMOKE / "reload_report.json", report)
    return report


if __name__ == "__main__":
    fn = {"train": run_train, "reload": run_reload}[sys.argv[1]]
    print(json.dumps(fn(), indent=1, default=str))
