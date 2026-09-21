# Contract: ASR hint sets (capability-qualified)

**Spec:** S30.1 · **Shape owner:** M01 · **Live owner:** M03 (capability boundary), M05/M06 (wiring) · **Suites:** EV-18

## HintSet (immutable)

One `Relevant Vocabulary Selector` output feeds pre-decode requests,
post-ASR recovery and cleanup. A set carries: ordered terms (canonical
text, scope, source, selector score — a score, not a probability), budget
omissions with reasons, provenance, and a policy revision. It is frozen
before decoding; late context gets a new downstream snapshot and is never
relabeled pre-decode.

## Adapter capability manifest

Booleans — `contextual_biasing`, `key_terms`, `language_hint`,
`word_timestamps`, `word_confidence`, `n_best`, `token_log_probs`,
`independent_itn` — are qualified per **adapter + checkpoint + runtime**
with evidence. `unknown` is not `supported`.

## Baseline status (M01)

The current adapter (`parakeet-mlx`, Parakeet TDT 0.6B v3, MLX 0.31.2)
starts with contextual biasing and key terms **disabled** until a real
supported implementation is separately qualified. Ignoring unsupported
hints is explicit and logged; hints are never concatenated into the audio
transcript and called acoustic context support. Membership in a hint set
is not an observed vocabulary hit; a post-ASR dictionary repair is never
recorded as a decoder hit.
