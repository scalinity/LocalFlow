"""Engine capture mode.

``CleanupEngine.clean`` runs with a fake ``generate_fn`` that answers each call
with gold text. The wrapped ``render_fn`` records which messages produced each
rendered prompt, so the fake identifies the call role from the messages
themselves (never from call order):

* corrections role: ``messages[0]["content"] == CORRECTIONS_INSTRUCTION``;
  answered with the gold deletion lines for that window, or ``NONE``;
* main role: answered with the gold target for that transcript.

A gold pair is accepted only when the engine delivers it byte-for-byte on the
``llm`` path with every gold correction selected and no salvage. The rendered
prompts become training examples for both call roles.
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import CONFIG, expand

_TOKENIZERS: dict = {}


def snapshot(repo: str, revision: str | None = None) -> Path:
    from huggingface_hub import snapshot_download
    return Path(snapshot_download(repo, revision=revision, local_files_only=True))


def tokenizer(key: str):
    """'qwen35' renders captures (the base tokenizer that B and C share);
    'qwen3' is A's tokenizer, used only for output-length checks."""
    if key not in _TOKENIZERS:
        from transformers import AutoTokenizer
        m = CONFIG["models"]
        path = snapshot(m["base_bf16"]["repository_id"], m["base_bf16"]["revision"]) if key == "qwen35" \
            else snapshot(m["A"]["repository_id"], m["A"]["revision"])
        _TOKENIZERS[key] = AutoTokenizer.from_pretrained(str(path))
    return _TOKENIZERS[key]


def render_with(tok):
    def render(messages):
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                       enable_thinking=False)
    return render


LIST_JOINERS = {"and", "or"}


def capture(pair: dict, *, tok_key: str = "qwen35", length_keys=("qwen35", "qwen3"),
            main_answer=None, render_override=None) -> dict:
    """Run the engine on ``pair['model_input']`` with gold answers.

    ``main_answer`` (optional) replaces the gold main-pass answer with a
    callable ``(prompt, max_tokens) -> generate dict`` — used for the
    teacher-forced main-pass evaluation, where corrections stay gold."""
    from localflow.v2.cleanup import protected_spans_for_cleanup
    from localflow.v2.cleanup.engine import (CORRECTIONS_INSTRUCTION, CleanupEngine,
                                             _has_correction_marker)
    from .synth import normalize_text

    tok = tokenizer(tok_key)
    render_base = render_override or render_with(tok)
    by_prompt: dict = {}
    calls: list = []
    reasons: list = []
    gold_lines = list(pair.get("gold_lines") or [])

    def render(messages):
        prompt = render_base(messages)
        by_prompt[prompt] = messages
        return prompt

    def generate(prompt, max_tokens):
        messages = by_prompt[prompt]
        if messages[0]["content"] == CORRECTIONS_INSTRUCTION:
            role = "corrections"
            window = messages[-1]["content"]
            lines = [g for g in gold_lines if g.lower() in window.lower()]
            answer = "\n".join(lines) if lines else "NONE"
        else:
            role = "main"
            transcript = json.loads(messages[-1]["content"])["transcript"]
            if main_answer is not None:
                res = main_answer(prompt, max_tokens)
                calls.append({"role": role, "prompt": prompt, "completion": res["text"],
                              "max_tokens": max_tokens, "transcript": transcript, "model": True})
                return res
            answer = pair["target"]
        n = len(tok.encode(answer, add_special_tokens=False)) + 1
        calls.append({"role": role, "prompt": prompt, "completion": answer, "max_tokens": max_tokens})
        return {"text": answer, "output_tokens": n, "limit_hit": n >= max_tokens, "prompt": prompt}

    norm = normalize_text(pair["raw_input"])
    if norm.text != pair["model_input"]:
        reasons.append("normalization_mismatch")
        spans = []
    else:
        try:
            spans = protected_spans_for_cleanup(pair["raw_input"], norm.text, norm.protected, norm.edits)
        except ValueError:
            reasons.append("protected_span_unmapped")
            spans = []
    triggered = _has_correction_marker(pair["model_input"])
    if gold_lines and not triggered:
        reasons.append("marker_not_triggered")
    engine = CleanupEngine(generate, model_id="capture", render_fn=render,
                           template_revision="capture")
    try:
        result = engine.clean(pair["model_input"], locale="en-US",
                              destination_profile=pair.get("destination_profile"),
                              relevant_vocabulary=pair.get("relevant_vocabulary") or [],
                              protected_spans=spans,
                              vocabulary_pairs=tuple(tuple(p) for p in pair.get("vocabulary_pairs") or []))
    except Exception as exc:
        return {"pair_id": pair["pair_id"], "accepted": False,
                "reject": sorted(set(reasons + [f"engine_error:{type(exc).__name__}"])), "calls": []}

    selected, offsets, salvaged = 0, [], 0
    for o in result.observations:
        if o.get("kind") == "corrections_applied":
            for p in o["proposals"]:
                if p.get("status") == "selected" and p.get("span"):
                    selected += 1
                    offsets.append([p["span"][0] + o["window_range"][0], p["span"][1] + o["window_range"][0]])
                elif p.get("status") == "rejected":
                    reasons.append("gold_correction_rejected:" + str(p.get("reason")))
        if o.get("kind") == "cleanup_decision" and o.get("salvaged_words"):
            salvaged += o["salvaged_words"]
    if main_answer is None:
        if gold_lines and selected != len(gold_lines):
            reasons.append("gold_correction_not_selected")
        list_and_salvage = False
        if result.path != "llm":
            reasons.append("gold_rejected_by_validator:" + (result.fallback_reason or "")[:80])
        elif result.text != pair["target"]:
            # The validator does not authorize dropping a comma-joined list's
            # final "and"; salvage puts it back. Keep such pairs (gold stays the
            # contract target) only when the restored words are list joiners.
            from collections import Counter
            from .synth import words
            extra = Counter(words(result.text)) - Counter(words(pair["target"]))
            missing = Counter(words(pair["target"])) - Counter(words(result.text))
            if salvaged and not missing and extra and set(extra) <= LIST_JOINERS:
                list_and_salvage = True
            else:
                reasons.append("salvaged" if salvaged else "delivered_differs_from_gold")
        elif salvaged:
            reasons.append("salvaged")
        if result.termination.get("windows", 1) != 1:
            reasons.append("multi_window")
        roles = [c["role"] for c in calls]
        expected = (["corrections"] if triggered else []) + ["main"]
        if roles != expected:
            reasons.append("unexpected_call_list:" + ",".join(roles))
        for key in length_keys:
            t = tokenizer(key)
            for c in calls:
                if len(t.encode(c["completion"], add_special_tokens=False)) + 2 > c["max_tokens"]:
                    reasons.append(f"too_long_for_tokenizer:{key}")
    return {"pair_id": pair["pair_id"], "accepted": not reasons, "reject": sorted(set(reasons)),
            "calls": calls, "path": result.path, "delivered": result.text,
            "list_and_salvage": main_answer is None and list_and_salvage,
            "fallback_reason": result.fallback_reason, "corrections_triggered": triggered,
            "gold_offsets": offsets, "protected_spans": [list(s) for s in spans],
            "result": result}
