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
import json
import re
import copy
from collections import OrderedDict

from .lookup import prefill

# Prompt tokens per prefill forward pass, shared by the prefix cache and
# generation. Full static-prefix caching also retains the final short block.
PREFILL_STEP = 2048
# Cached instruction prefixes, least recently used dropped first: one slot
# each for the cleanup and the corrections prompt families.
PREFIX_CACHE_SLOTS = 2
_USER_TURN = "<|im_start|>user\n"


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
        self._prefix_caches = OrderedDict()
        # (prompt, offset of its final user turn) from the last render_cached.
        self._rendered = None
        self._draft = None
        self.use_lookup = True
        self.cache_full_prefix = True
        self.lookup_stats = None
        self.last_prefix_tokens = 0
        self.last_prefix_hit = False
        # mlx entry points the prefix cache uses, bound by load().
        self._mx = None
        self._make_prompt_cache = None

    def load(self, on_phase=None):
        """on_phase("warming") fires once the weights are loaded, before
        the warmup generation (mirrors ``Transcriber.load``)."""
        import mlx.core as mx
        from mlx_lm import load as llm_load
        from mlx_lm.models.cache import make_prompt_cache
        self._mx, self._make_prompt_cache = mx, make_prompt_cache
        self._model, self._tokenizer = llm_load(self.model_id)
        if on_phase is not None:
            on_phase("warming")
        self._prefix_caches.clear()
        self.template_revision = self._probe_revision()
        # Warmup: run the production path once on a real cleanup prompt, so
        # its instruction prefix is already cached for the first dictation.
        # The prefix does not depend on the payload.
        from . import prompts
        self.generate_fn()(self.render_cached(
            prompts.build_messages({"transcript": "warmup"})), 8)

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

    def render_cached(self, messages: list[dict]) -> str:
        """Render a cleanup-engine prompt whose instruction prefix may be cached.

        The final user turn is located from ``messages``, not searched for in
        the text, so a dictation that contains a turn marker cannot move it.
        Only prompts rendered here are cached; ``render`` (transforms) never
        is, so it cannot evict the cleanup prefix.
        """
        prompt = self.render(messages)
        final = prompt.rfind(messages[-1]["content"])
        turn = final - len(_USER_TURN)
        self._rendered = (prompt, turn) if (
            final >= 0 and turn >= 0 and prompt[turn:final] == _USER_TURN) else None
        self._draft = None
        from . import prompts
        if (self._rendered is not None and messages
                and messages[0]["content"].startswith(prompts.CONTRACT)):
            try:
                payload = json.loads(messages[-1]["content"])
                transcript = payload.get("transcript") if isinstance(payload, dict) else None
                if isinstance(transcript, str) and transcript:
                    self._draft = (prompt, transcript)
            except (ValueError, TypeError):
                pass  # Corrections and other prompt families use ordinary decoding.
        return prompt

    def engine(self, notifier=None):
        """A CleanupEngine wired to this runner's generate/render (the
        worker and the model-backed suites use the same construction)."""
        from .engine import CleanupEngine
        return CleanupEngine(self.generate_fn(), model_id=self.model_id,
                             notifier=notifier, render_fn=self.render_cached,
                             template_revision=self.template_revision)

    def _cached_prompt(self, prompt):
        """Reuse instructions before the final user turn of a cached render.

        Prefix tokens must match the actual whole-prompt tokenization. Each
        call branches from a private copy: no dictation or generated suffix
        can become another call's history. The block-only switch retains the
        original prefill grouping for A/B qualification of recurrent models.
        """
        mx = self._mx
        self.last_prefix_tokens = 0
        self.last_prefix_hit = False
        if self._rendered is None or self._rendered[0] != prompt:
            return prompt, None
        boundary = self._rendered[1]
        tok = self._tokenizer
        special = tok.bos_token is None or not prompt.startswith(tok.bos_token)
        # Encoded exactly as stream_generate would, so an uncached prompt
        # is passed on as these tokens rather than encoded again.
        tokens = tok.encode(prompt, add_special_tokens=special)
        if not self.cache_full_prefix and len(tokens) <= PREFILL_STEP:
            return tokens, None
        prefix = tok.encode(prompt[:boundary], add_special_tokens=special)
        count = (len(prefix) if self.cache_full_prefix else
                 (len(prefix) // PREFILL_STEP) * PREFILL_STEP)
        if not count or tokens[:len(prefix)] != prefix or count >= len(tokens):
            return tokens, None
        key = tuple(prefix[:count])
        self.last_prefix_hit = key in self._prefix_caches
        if key not in self._prefix_caches:
            cache = self._make_prompt_cache(self._model)
            prefill(mx, self._model, cache, prefix[:count], PREFILL_STEP)
            self._prefix_caches[key] = cache
            while len(self._prefix_caches) > PREFIX_CACHE_SLOTS:
                self._prefix_caches.popitem(last=False)
        self._prefix_caches.move_to_end(key)
        self.last_prefix_tokens = count
        # Generation writes into the copy's arrays; an mx.array update makes
        # a new array, so the stored prefix state is never changed.
        return tokens[count:], copy.deepcopy(self._prefix_caches[key])

    def stream(self, prompt: str, max_tokens: int):
        """The production generation path, also used by timed evaluation."""
        from mlx_lm.generate import stream_generate
        from mlx_lm.sample_utils import make_sampler
        suffix, cache = self._cached_prompt(prompt)
        self.lookup_stats = None
        if self.use_lookup and max_tokens > 0 and self._draft is not None \
                and self._draft[0] == prompt:
            from .lookup import stream_lookup
            # A lookup prompt matches the cached render, so ``suffix`` is
            # already token ids; a prefix that could not be cached starts
            # from an empty cache.
            if cache is None:
                cache = self._make_prompt_cache(self._model)
            source = self._tokenizer.encode(self._draft[1], add_special_tokens=False)
            self.lookup_stats = {}
            yield from stream_lookup(
                self._model, self._tokenizer, suffix, cache, source, max_tokens,
                prefill_step=PREFILL_STEP, stats=self.lookup_stats)
            return
        yield from stream_generate(
            self._model, self._tokenizer, prompt=suffix,
            max_tokens=max_tokens, sampler=make_sampler(temp=0.0),
            prompt_cache=cache, prefill_step_size=PREFILL_STEP)

    def generate_fn(self):
        def generate(prompt: str, max_tokens: int) -> dict:
            text = ""
            tokens = 0
            for response in self.stream(prompt, max_tokens):
                text += response.text
                tokens += 1
            return {
                "text": text,
                "output_tokens": tokens,
                "limit_hit": tokens >= max_tokens,
                "prompt": prompt,
            }

        return generate

