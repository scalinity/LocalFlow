"""Greedy cleanup generation with transcript-token proposals.

The transcript supplies guesses only. The target model verifies every token.
On rejection, restore a checkpoint and replay the accepted tokens instead of
trimming the whole cache: Qwen3.5's recurrent layers cannot roll their state
back by token count. Its attention layers can, so their checkpoint is just
an offset. Batch arithmetic can differ from singleton decoding near numerical ties;
full-token parity on the exact model/runtime is a deployment check.
"""
from __future__ import annotations

import copy
import functools
import time

MAX_MATCH = 4      # longest output suffix looked up in the transcript
DRAFT_WIDTH = 8    # proposed tokens per verification batch
MISS_LIMIT = 3     # consecutive rounds accepting nothing before ordinary decoding
CLEAR_EVERY = 256  # mx.clear_cache cadence, as in mlx_lm.generate_step


def propose(history, source, width=DRAFT_WIDTH, cursor=0):
    """Return ``(end, tokens)``: up to ``width`` transcript tokens to verify.

    Find the longest suffix of the output so far (up to MAX_MATCH tokens)
    in ``source``. Of its occurrences, take the first that ends at or after
    ``cursor``, where the last verified proposal stopped, so a repeated
    phrase continues from the current place rather than an earlier one;
    with none there, take the first. ``end`` is where that occurrence ends
    and the proposal follows it. An occurrence that ends the transcript
    means the output has caught up with it: nothing is proposed, rather
    than a shorter suffix matched earlier in the transcript.
    """
    for size in range(min(MAX_MATCH, len(history)), 0, -1):
        tail = history[-size:]
        ends = [pos + size for pos in range(len(source) - size + 1)
                if source[pos:pos + size] == tail]
        if ends:
            end = next((e for e in ends if e >= cursor), ends[0])
            return end, source[end:end + width]
    return cursor, []


def _restore_all(cache, saved):
    cache[:] = saved


def verified_tokens(model, cache, pending, source, *, max_tokens, eos_ids,
                    step, evaluate, stats=None, fallback=None,
                    snapshot=copy.deepcopy, restore=_restore_all):
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
    - ``snapshot(cache)`` saves what ``restore(cache, saved)`` needs to put
      the cache back as it was before a proposal; the defaults copy and
      replace the whole cache.

    The caller supplies a private disposable cache; model calls consume it,
    including on failure. Never pass the stored reusable prefix itself.
    ``stats``, when given, receives the per-call counters.
    """
    history = []
    misses = 0
    cursor = 0  # transcript position just after the verified proposal
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
        start, draft = (propose(history, source,
                                min(DRAFT_WIDTH, max_tokens - len(history) - 1),
                                cursor)
                        if drafting else (cursor, []))
        saved = snapshot(cache) if draft else None
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
                restore(cache, saved)
                stats["replay_rounds"] += 1
                # Advancing by accepted tokens alone restores recurrent state;
                # the rejected suffix must never influence subsequent tokens.
                evaluate(model, cache, [pending] + draft[:accepted])
            else:
                stats["full_rounds"] += 1
            cursor = start + accepted
        # A round without a proposal also accepts nothing.
        misses = 0 if accepted else misses + 1
        pending = predicted[accepted]


def prefill(mx, model, cache, tokens, step):
    """Advance ``cache`` by ``tokens`` in forward passes of ``step`` tokens.

    mlx_lm.generate_step groups a prompt the same way. The prefix cache and
    lookup decoding both use this function, so their grouping cannot drift
    apart. ``mx`` is passed in so that the prefix-cache tests can run
    without MLX.
    """
    for start in range(0, len(tokens), step):
        model(mx.array([tokens[start:start + step]]), cache=cache)
        mx.eval([c.state for c in cache])
        mx.clear_cache()


# The MLX model callables. They live at module level so that tests drive
# the same functions production uses against real caches. Each runs its
# model call on mlx_lm's generation stream, as generate_step does; the
# stream is not held across the adapter's yields.

def greedy_step(model, cache, tokens):
    """Advance ``cache`` by ``tokens``; return the greedy token after each."""
    import mlx.core as mx
    from mlx_lm.generate import generation_stream
    with mx.stream(generation_stream):
        logits = model(mx.array([tokens]), cache=cache)[0]
        # Use the same arithmetic as the ordinary greedy sampler, including
        # normalization: near ties can round differently without it.
        scores = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
        return mx.argmax(scores, axis=-1).tolist()


def evaluate(model, cache, tokens):
    """Advance ``cache`` by ``tokens`` without computing predictions.

    Lookup uses this only to replay accepted tokens. The evaluation is
    asynchronous, as in generate_step: the GPU replays while the next
    verification graph is built, and that step's result waits for it.
    """
    import mlx.core as mx
    from mlx_lm.generate import generation_stream
    with mx.stream(generation_stream):
        model(mx.array([tokens]), cache=cache)
        mx.async_eval([c.state for c in cache])


def snapshot_cache(cache):
    """Checkpoint a model cache without holding its attention buffers.

    A KVCache writes keys and values into its buffers in place and reads
    only the first ``offset`` positions, so its offset is a complete
    checkpoint: the replay overwrites anything past it. A deep copy would
    keep a second reference to those buffers and make the next write copy
    every layer's keys and values (about 80 MiB for the cleanup prompt).
    Other caches, such as Qwen3.5's recurrent state, replace their arrays on
    update, so a deep copy shares them at no cost.
    """
    from mlx_lm.models.cache import KVCache
    return [c.offset if type(c) is KVCache else copy.deepcopy(c) for c in cache]


def restore_cache(cache, saved):
    """Undo a verification step from a ``snapshot_cache`` checkpoint."""
    for i, entry in enumerate(saved):
        if isinstance(entry, int):
            cache[i].trim(cache[i].offset - entry)
        else:
            cache[i] = entry


def resume_ordinary(model, cache, pending, remaining, *, prefill_step):
    """Continue with mlx_lm's asynchronous decoder from the accepted state."""
    import mlx.core as mx
    from mlx_lm.generate import generate_step
    for token, _ in generate_step(mx.array([pending]), model,
                                  prompt_cache=cache, max_tokens=remaining,
                                  prefill_step_size=prefill_step):
        yield token


def stream_lookup(model, tokenizer, tokens, cache, source, max_tokens, *,
                  prefill_step, stats):
    """Stream verified generation as mlx_lm ``GenerationResponse`` objects.

    ``tokens`` is the encoded prompt after any cached prefix and ``cache`` a
    private cache that already holds everything before it. ``source`` is the
    encoded transcript; ``stats`` receives the per-call counters.

    Responses match ``mlx_lm.stream_generate`` field for field except two
    that nothing in LocalFlow reads: ``logprobs`` is None, and
    ``from_draft`` is False even for accepted proposals, because every
    emitted token is the target model's own greedy choice.
    """
    import mlx.core as mx
    from mlx_lm.generate import (GenerationResponse, generation_stream,
                                 wired_limit)

    eos = tokenizer.eos_token_ids
    prompt_size = len(tokens)
    fallback = functools.partial(resume_ordinary, prefill_step=prefill_step)

    # Like stream_generate, only the wired limit spans the yields.
    with wired_limit(model, [generation_stream]):
        started = time.perf_counter()
        with mx.stream(generation_stream):
            prefill(mx, model, cache, tokens[:-1], prefill_step)
        pending = greedy_step(model, cache, tokens[-1:])[-1]
        prompt_time = time.perf_counter() - started
        started = time.perf_counter()
        detokenizer = tokenizer.detokenizer
        detokenizer.reset()
        for generated, token in enumerate(verified_tokens(
                model, cache, pending, source, max_tokens=max_tokens,
                eos_ids=eos, step=greedy_step, evaluate=evaluate,
                stats=stats, fallback=fallback, snapshot=snapshot_cache,
                restore=restore_cache), 1):
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
