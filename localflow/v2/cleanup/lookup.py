"""Greedy cleanup generation with transcript-token proposals.

The transcript supplies guesses only. The target model verifies every token.
On rejection, replay from a private checkpoint instead of trimming the cache:
Qwen3.5's recurrent layers cannot roll their state back by token count.
Batch arithmetic can differ from singleton decoding near numerical ties;
full-token parity on the exact model/runtime is a deployment check.
"""
from __future__ import annotations

import copy
import time

MAX_MATCH = 4      # longest output suffix looked up in the transcript
DRAFT_WIDTH = 8    # proposed tokens per verification batch
MISS_LIMIT = 3     # consecutive rounds accepting nothing before ordinary decoding
CLEAR_EVERY = 256  # mx.clear_cache cadence, as in mlx_lm.generate_step


def propose(history, source, width=DRAFT_WIDTH):
    """Propose up to ``width`` transcript tokens to verify next.

    Find the longest suffix of the output so far (up to MAX_MATCH tokens)
    inside ``source`` and return the tokens after its first occurrence.
    An occurrence that ends the transcript has nothing after it and is
    skipped.
    """
    for size in range(min(MAX_MATCH, len(history)), 0, -1):
        tail = history[-size:]
        for pos in range(len(source) - size):
            if source[pos:pos + size] == tail:
                return source[pos + size:pos + size + width]
    return []


def verified_tokens(model, cache, pending, source, *, max_tokens, eos_ids,
                    step, evaluate, stats=None, fallback=None):
    """Yield verified tokens; ``cache`` excludes the pending token.

    The model callables keep this state machine independent of MLX, which
    permits adverse-cache tests:

    - ``step(model, cache, tokens)`` advances the cache by ``tokens`` and
      returns the target's greedy prediction after each of them.
    - ``evaluate(model, cache, tokens)`` advances the cache by ``tokens``
      and returns nothing; it replays the accepted part of a rejected
      proposal after the checkpoint is restored.
    - ``fallback(model, cache, pending, remaining)``, when given, yields up
      to ``remaining`` tokens after ``pending`` with ordinary decoding. It
      takes over after MISS_LIMIT consecutive rounds that accept nothing.

    The caller supplies a private disposable cache; model calls consume it,
    including on failure. Never pass the stored reusable prefix itself.
    ``stats``, when given, receives the per-call counters.
    """
    history = []
    misses = 0
    stats = stats if stats is not None else {}
    for name in ("drafted_tokens", "accepted_tokens", "replay_rounds",
                 "full_rounds", "fallbacks", "decode_calls"):
        stats[name] = 0
    while len(history) < max_tokens:
        history.append(pending)
        yield pending
        if pending in eos_ids or len(history) == max_tokens:
            return
        drafting = misses < MISS_LIMIT
        if not drafting and fallback is not None:
            stats["fallbacks"] += 1
            for token in fallback(model, cache, pending, max_tokens - len(history)):
                yield token
                if token in eos_ids:
                    return
            return
        draft = (propose(history, source,
                         min(DRAFT_WIDTH, max_tokens - len(history) - 1))
                 if drafting else [])
        checkpoint = copy.deepcopy(cache) if draft else None
        predicted = step(model, cache, [pending] + draft)
        stats["decode_calls"] += 1
        stats["drafted_tokens"] += len(draft)
        accepted = 0
        while accepted < len(draft) and draft[accepted] == predicted[accepted]:
            token = draft[accepted]
            history.append(token)
            accepted += 1
            stats["accepted_tokens"] += 1
            yield token
            if token in eos_ids:
                return
        if draft:
            if accepted < len(draft):
                cache[:] = checkpoint
                stats["replay_rounds"] += 1
                # Advancing by accepted tokens alone restores recurrent state;
                # the rejected suffix must never influence subsequent tokens.
                evaluate(model, cache, [pending] + draft[:accepted])
            else:
                stats["full_rounds"] += 1
        # A round without a proposal also accepts nothing.
        misses = 0 if accepted else misses + 1
        pending = predicted[accepted]


def stream_lookup(model, tokenizer, tokens, cache, source, max_tokens, *,
                  prefill_step, stats):
    """Stream verified generation as mlx_lm ``GenerationResponse`` objects.

    ``tokens`` is the encoded prompt after any cached prefix and ``cache`` a
    private cache that already holds everything before it. ``source`` is the
    encoded transcript; ``stats`` receives the per-call counters.
    """
    import mlx.core as mx
    from mlx_lm.generate import (GenerationResponse, generate_step,
                                 generation_stream, wired_limit)

    eos = tokenizer.eos_token_ids
    prompt_size = len(tokens)

    def evaluate(model, cache, tokens):
        model(mx.array([tokens]), cache=cache)
        mx.eval([c.state for c in cache])

    def step(model, cache, tokens):
        logits = model(mx.array([tokens]), cache=cache)[0]
        # Use the same arithmetic as the ordinary greedy sampler, including
        # normalization: near ties can round differently without it.
        scores = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        return mx.argmax(scores, axis=-1).tolist()

    def fallback(model, cache, pending, remaining):
        # Resume ordinary asynchronous decoding from the accepted state.
        for token, _ in generate_step(mx.array([pending]), model,
                prompt_cache=cache, max_tokens=remaining,
                prefill_step_size=prefill_step):
            yield token

    with wired_limit(model, [generation_stream]), mx.stream(generation_stream):
        started = time.perf_counter()
        while len(tokens) > 1:
            chunk = min(prefill_step, len(tokens) - 1)
            evaluate(model, cache, tokens[:chunk])
            tokens = tokens[chunk:]
            mx.clear_cache()
        pending = step(model, cache, tokens)[-1]
        prompt_time = time.perf_counter() - started
        started = time.perf_counter()
        detokenizer = tokenizer.detokenizer
        detokenizer.reset()
        for generated, token in enumerate(verified_tokens(
                model, cache, pending, source, max_tokens=max_tokens,
                eos_ids=eos, step=step, evaluate=evaluate,
                stats=stats, fallback=fallback), 1):
            is_eos = token in eos
            finished = is_eos or generated == max_tokens
            if not is_eos:
                detokenizer.add_token(token)
            if finished:
                detokenizer.finalize()
            if generated == 1 or generated % CLEAR_EVERY == 0:
                mx.clear_cache()
            yield GenerationResponse(
                text=detokenizer.last_segment, token=token, logprobs=None,
                from_draft=False, prompt_tokens=prompt_size,
                prompt_tps=prompt_size / max(prompt_time, 1e-9),
                generation_tokens=generated,
                generation_tps=generated / max(time.perf_counter() - started, 1e-9),
                peak_memory=mx.get_peak_memory() / 1e9,
                finish_reason=("stop" if is_eos else "length") if finished else None)
