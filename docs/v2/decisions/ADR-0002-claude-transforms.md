# ADR-0002: Selected-text transforms run on Claude

**Status:** accepted · **Spec deviation from:** S16 (selected-text
execution "runs locally"; the requirement-atom map as built in
`transforms/atoms.py`), binding decision 7 (no cloud inference for
ordinary operation), contract `transforms.md` (one bounded generation
on the cleanup model in the worker).

## Context

Polish, Prompt Engineer and Concise ran on the worker's cleanup model.
Measured on one 42-word dictated source ("So um basically I think we
should probably move the standup to like 10am on Thursdays because half
the team is in a different timezone …, but don't change the Friday
retro, that one stays at 3pm"):

- On the cleanup-only fine-tune (`LocalFlow-Cleanup-M2-Qwen3.5-4B-4bit`)
  Polish and Concise returned the source minus "um" with path
  `applied`; Prompt Engineer dropped the proposal and its reason and
  invented "Deliverables" copied from its few-shot example. On the
  earlier Qwen3-4B-Instruct model Polish and Concise needed review and
  Prompt Engineer hit its output limit.
- The lexical requirement gate (`atoms.coverage_map`, `m11-gate-2`)
  flagged all three correct Claude rewrites of that source (Polish for
  "10 a.m."/"3 p.m.", Concise for compressing "I think … probably",
  Prompt Engineer for splitting one clause into Proposal and Rationale)
  and passed the M2 no-op. In the dictation auto-apply path a flagged
  result inserts the Clean text, so the gate discarded every real
  rewrite and kept every no-op.
- The same contracts sent to `claude-opus-5-5` at effort low returned
  correct transforms in 1.4–2.3 s.
- Wispr Flow 1.6.1147 (research record
  `wispr-flow-1.6.1147-transforms/FINDINGS.md`) runs Polish and Prompt
  Engineer server-side on an LLM and has a `no_changes` outcome
  ("Your text looks good!", nothing pasted).

## Decision

### 1. The call runs in the app process, not the worker

`localflow/v2/transforms/claude.py` makes the Anthropic call.
`WorkerSupervisor.transform` keeps its signature and reply shape, so
both app call sites (`_m11_run_transform`, `_m11_run_job`) and every
harness fake are unchanged, but it no longer takes `_gpu_lock` or
sends a worker op: it runs the job through `claude.Transformer` in the
calling thread. A selected-text transform runs on its own thread, so no
dictation waits behind it; an auto-applied dictation transform runs in
the coordinator between that dictation's cleanup and insertion, as the
local one did, so a dictation that follows it waits for it. The
supervisor's shutdown closes admission for transforms too: a transform
after it is refused, and one in flight has its client closed and its
answer discarded (`closed_in_flight`).
The worker's `transform` op, its handler and the generate/render handles
kept only for it are removed — no local transform path remains to fall
back to.

### 2. The gate: exact carry blocks; Prompt Engineer's map is verified

Validator revision `claude-gate-1` (`engine.run_transform`):

- **Exact carry stays blocking** for every kind: quoted spans, URLs,
  paths and identifiers in the source must appear verbatim in the
  output (`atoms.extract_atoms(…, mode="custom")` + `atoms.cover`). A
  loss is `needs_review` with the span kept for review.
- **Prompt Engineer returns S16's requirement map** as structured
  output: `{"prompt", "requirements": [{"source", "output"}],
  "uncertain": []}`. Code verifies each cited draft span exists in the
  draft and each cited output span in the prompt (spacing, case and
  markdown marks aside). An unverified span or a requirement Claude marks
  uncertain is a review issue with the draft's own wording kept — S16's
  "keep the original clause or mark a review issue".
- **The lexical clause gate leaves the transform path.** It fails every
  real rewrite, so as advisory notes it would teach the user to ignore
  the panel. `atoms.coverage_map` stays in the tree with its regression
  cases (`test_transform_remediation.py`, layer `validator`).
- Every transform answers with structured output (`{"text"}` for
  Polish, Concise and custom). Without it Sonnet 5.5 at effort high
  sometimes echoed the `<draft>` framing and corrected itself in the
  reply ("Wait — I should return only the polished text"). An answer
  that still contains the framing falls back with `output_invalid`.

### 3. Shipped defaults per transform (scripts/v2/transform_model_eval.py)

| Transform | Model | Reasoning | Dev | Test | p50 | p95 | Mean cost |
|---|---|---|---|---|---|---|---|
| Polish | `claude-opus-5-5` | medium | 21/21 | 31/31 | 2.9 s | 5.8 s | $0.0060 |
| Concise | `claude-opus-5-5` | high | 21/21 | 31/31 | 3.3 s | 8.1 s | $0.0079 |
| Prompt Engineer | `claude-sonnet-5-5` | thinking off | 21/21 | 31/31 | 2.2 s | 5.6 s | $0.0055 |

Custom transforms default to Polish's pick. The winners fail no case.
Polish ties with Opus at high (31/31, p50 3.3 s) and wins on latency;
Concise ties with Opus at xhigh and max and wins on latency, while Opus
at low and medium are dropped for carrying out a request inside a
draft. Prompt Engineer's runner-up is Sonnet at medium (30/31, p50
1.8 s). Prompts were frozen after five dev rounds at revisions
`claude1:b1f6e2d21c27` (Polish), `claude1:55459cde37bf` (Concise) and
`claude1:a3b16731601b` (Prompt Engineer); the grid ran 17
configurations × 3 transforms × 52 cases (2,652 requests, $23.81, plus
$4.83 of judging). Selection rule: drop any
configuration with an injection failure or an exact-carry loss, take the
highest test-split pass rate, break ties on p50 latency. A case passes
only when every must-keep item is kept, nothing is added, no instruction
inside the draft is obeyed and the output does its transform's job,
graded mechanically (exact carry, forbid lists) and then by an
other-vendor judge (gpt-6.1-sol through
`experiments/cleanup-model-v2/v2/judge_backends.py`). Raw outputs,
verdicts and timings are under
`~/Library/Application Support/LocalFlow/v2-evidence/transform-model-eval/`.

### 4. The model choice is a transform_meta preference

A row `model:<transform_id>` → `{"model", "reasoning"}` beside the
hotkey rows, never a definition revision: switching models keeps the
task key, so outputs stay comparable candidates. No row means the
recommended pair; a stored pair the table no longer offers reads as the
recommendation. It is read on every run, so a Hub change applies to the
next transform without a restart.

The serving model (`message.model`) and the reasoning level are
recorded on every result (`TransformResult.model`/`reasoning`, the
decision record, `stage.completed` as `model_id`/`model_revision`). The
candidate row's `model_id` column holds `model@reasoning` (for example
`claude-sonnet-5-5@low`), so the reasoning level is on every candidate
without a schema change.

`claude.MODELS` is the one table: `claude-haiku-5-5`,
`claude-sonnet-5-5`, `claude-opus-5-5`, each with adaptive thinking at
effort low/medium/high/xhigh/max, plus thinking off where the model
allows it — Haiku via `{"type": "disabled"}`, Sonnet via
`{"type": "between_tools"}`, both sent at effort high (the highest level
that allows it); Opus cannot turn thinking off. 17 pairs. The engine,
the evaluation and the Hub read it, so the Hub offers no pair the API
rejects. Requests use the server-side refusal fallback
(`server-side-fallback-2026-07-01`, `fallbacks="default"`) on Opus and
Sonnet and never on Haiku, `max_tokens` 32000, streaming, no sampling
parameters and no prefill.

### 5. No key, no SDK or no network: an honest fallback, never local

The result is `fallback_original` with
`transform_unavailable:<code>` — `no_api_key`, `sdk_missing`,
`network_unavailable`, `timeout`, `api_key_rejected`, `rate_limited`,
`usage_limit_reached` (the account's spending cap), `request_rejected`,
`closed`, `closed_in_flight`, `api_error_<status>`, `model_refused`,
`output_limit`, `output_invalid` — which the panel states in words. The
local model is never used: its no-ops read as success.

### 6. `no_changes` is its own outcome

An output equal to its source (spacing aside) is path `no_changes`. The
panel says "already reads well — nothing to change" and Accept is off;
the dictation path inserts the Clean text, as it does for any result
that is not `applied`.

## What is sent, stored and shown

- **Sent:** the selected text (or the Clean text of a dictation whose
  style auto-applies a transform), the transform's system prompt and,
  for a custom transform, its instruction, plus every writing example
  (before/after pair) the definition keeps, on each run. Selection capture keeps its
  secure-field and denied-app refusals, so nothing from those reaches
  Anthropic.
- **Key:** `TRANSFORMS_ANTHROPIC_API_KEY` in the login Keychain (service
  `LocalFlow`), read through `/usr/bin/security` on every transform,
  only when the app runs on its real store; a changed or removed key
  takes effect on the next transform. It is never logged, emitted or
  stored.
- **Stored:** unchanged from M11 — candidates under collection consent,
  with the exact request as the `transform_prompt` artifact and the
  decision record carrying the model and reasoning level.
- **Shown:** the review panel's status line names the model that
  answered and the reasoning level; without an answer it says whether
  the text was sent ("sent to Claude · no answer"), may have been (a
  failed connection or a timeout), or was not (no key, no SDK, closing).

LF-R25 allowlists exactly two (module, import) pairs:
`voice_insights.py` and `transforms/claude.py` may import `anthropic`.

## Consequences

- Transforms need a network connection and an API key; dictation does
  not. The Hub's Transforms page says the selected text is sent to
  Anthropic.
- Each transform costs under one cent at the shipped defaults (mean
  $0.0055–$0.0079 over the evaluation's cases).
- A transform no longer waits for the cleanup model to load.
- The AppKit fallback Hub has no model pickers; it runs the stored or
  recommended choice.

## Alternatives considered

- **Keep the worker on the path:** the GPU lock would make ASR wait for
  the network, and the worker's single task loop would block too.
- **Advisory lexical notes:** they fire on every correct rewrite.
- **A schema column for the reasoning level:** a store migration for one
  field no reader needs separately; `model@reasoning` carries it.
- **Haiku or Sonnet for Polish and Concise:** faster at the same
  reasoning level, but each misses more test cases than Opus (best Haiku
  30/31 only at max, p50 8.9 s and 31 s; best Sonnet 29/31 and 30/31),
  and Haiku below xhigh carries out requests inside Concise drafts.
