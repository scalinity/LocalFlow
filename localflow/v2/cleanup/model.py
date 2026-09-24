"""Model runner for cleanup V2 (M07, Spec S13 sampling rules).

Loads the cleanup model once in the worker subprocess and exposes an
explicit, recorded sampling configuration: temperature 0 (greedy —
``enable_thinking=False`` remains from the baseline), max_tokens by
rule, and output-limit detection via the generation token count. The
chat-template revision is hashed so evidence records the exact
rendering (S29.4 cleanup family). mlx imports stay inside ``load`` so
the engine and its tests import cleanly without MLX present.
"""

from __future__ import annotations

import hashlib
import re


def render_messages(messages: list[dict],
                    tokenizer=None,
                    enable_thinking: bool = False) -> str:
    """Render chat messages with the tokenizer's template. Without a
    tokenizer (tests) a stable plain rendering is used."""
    if tokenizer is not None:
        return tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False,
            enable_thinking=enable_thinking)
    out = []
    for m in messages:
        out.append(f"<|{m['role']}|>\n{m['content']}")
    out.append("<|assistant|>")
    return "\n".join(out)


class ModelRunner:
    """Owns the loaded model + tokenizer and produces the generate_fn
    the engine consumes. One generation is in flight at a time (the
    worker's supervisor already serializes GPU access)."""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self._model = None
        self._tokenizer = None
        self.template_revision = None

    def load(self):
        from mlx_lm import load as llm_load
        self._model, self._tokenizer = llm_load(self.model_id)
        self.template_revision = self._probe_revision()
        # Warmup: exercise the full generation path once (V1 parity).
        self.generate_fn()("<|probe|> warmup", 8)

    def _probe_revision(self) -> str:
        probe = render_messages(
            [{"role": "system", "content": "probe"},
             {"role": "user", "content": "probe"}],
            tokenizer=self._tokenizer)
        return "tmpl:" + hashlib.sha256(probe.encode()).hexdigest()[:12]

    def ready(self) -> bool:
        return self._model is not None

    def render(self, messages: list[dict]) -> str:
        """Tokenizer-bound chat rendering (enable_thinking stays off)."""
        return render_messages(messages, tokenizer=self._tokenizer)

    def engine(self, notifier=None):
        """A CleanupEngine wired to this runner's generate/render (the
        worker and the model-backed suites use the same construction)."""
        from .engine import CleanupEngine
        return CleanupEngine(self.generate_fn(), model_id=self.model_id,
                             notifier=notifier, render_fn=self.render,
                             template_revision=self.template_revision)

    def generate_fn(self):
        from mlx_lm.generate import stream_generate
        from mlx_lm.sample_utils import make_sampler
        model, tokenizer = self._model, self._tokenizer
        sampler = make_sampler(temp=0.0)   # greedy, explicit (S13)

        def generate(prompt: str, max_tokens: int) -> dict:
            text = ""
            tokens = 0
            for response in stream_generate(
                    model, tokenizer, prompt=prompt,
                    max_tokens=max_tokens, sampler=sampler):
                text += response.text
                tokens += 1
            return {
                "text": text,
                "output_tokens": tokens,
                "limit_hit": tokens >= max_tokens,
                "prompt": prompt,
            }

        return generate

