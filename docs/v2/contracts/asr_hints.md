# Contract: ASR hint sets (capability-qualified)

**Spec:** S30.1 · **Shape owner:** M01 · **Live owner:** M03 (capability boundary), M05 (selector/wiring), M06 (context snapshot) · **Suites:** EV-18

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

## M03 live status

`localflow/v2/capabilities.py` ships the manifest
(`asr_capability_manifest`, revision `m03-conservative-v1`): all eight
booleans are `False` with per-field reasons and evidence
(`disabled_until_qualified` for contextual biasing/key terms;
`unsupported_by_adapter` for language hints, confidence, n-best, token
log-probs and independent ITN; `not_exposed_on_dictation_path` for word
timestamps, which parakeet_mlx produces internally for long-audio merging
but the dictation path does not return). `hint_disposition()` records the
no-selector status: 0 offered, ignored with reason. The evidence envelope
carries the manifest's capability block and this disposition, and its
optional-ASR missing reasons use `unsupported_by_adapter` (not a
fabricated value, never zero).

## M05 live status

The Relevant Vocabulary Selector ships: `localflow.v2.vocabulary`
builds frozen HintSets from the scoped dictionary snapshot
(`contracts/vocabulary.md`), captured per job at hotkey-down (after
the overlay shows, so selector work never delays visible feedback)
and stored pre-decode when collection is enabled.
`hint_disposition(manifest, hint_set)` now reports the real offered
count with `accepted_terms: 0` and `ignored: true`
(`disabled_until_qualified`) — with **zero offered terms nothing is
ignored** (`ignored` false, reason null); the note still states the
boundary. `asr_hint_request_fields(hint_set, manifest)` is the
adapter extension point and returns `None` until an adapter +
checkpoint + runtime is separately qualified — no request ever
pretends to carry hints the decoder ignored. Post-ASR recovery
consumes the same snapshot; its repairs are normalization ledger
edits with rule ids, never decoder hits (AC05). Cleanup consumes
permitted context from M07 and is not a consumer yet. M06 feeds the
`context_snapshot_id` field and live scope context.
