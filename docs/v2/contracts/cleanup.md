# Contract: Faithful cleanup and document-aware formatting

**Spec:** S13, S14, S15 (clean mode), S24 (budget context), S29.4
(cleanup family) · **Owner:** M07 · **Suites:** EV-09
(tests/v2/fidelity/, tests/v2/structure/), EV-19 (cleanup fields)

`localflow.v2.cleanup` (`prompts`, `document_nodes`, `validation`,
`engine`, `model`) renders the user's intended wording without ever
answering, executing or rewriting the dictation. V1
(`localflow.cleanup.TranscriptCleaner`) stays intact and selectable
(`cleanup_implementation: "v1"`) as the ablation control and fallback;
the default is `v2` on the M07 ablation evidence
(`benchmarks/<run>-m07/m07.json`).

## The faithful contract (S13, frozen verbatim)

`prompts.CONTRACT` is the S13 clean-prompt contract word for word. The
prompt is versioned by content hash: `prompt_revision()` =
`m07:<sha256-12>` over contract + examples + version — an edited word
can never share a revision id with the old prompt. Curated examples
satisfy the contract themselves (digits stay digits, the exact
`/code-review` token, retained questions, cloud stays cloud, discourse
words like "like"/"you know" are content, Spanish stays Spanish).

Instructions stay separate from payloads: system message = the
contract; examples = few-shot turns; the final user message is a JSON
payload with the S13 field names — `transcript`, `mode`, `locale`,
`destination_profile`, `relevant_vocabulary`, `protected_spans`,
`structure_hints`, `permitted_edits` (plus an explicitly labeled
`read_only_context` for window overlap). Vocabulary alias→canonical
pairs are validator data only and never enter the prompt.

## Sampling (recorded, explicit)

Greedy decoding: `make_sampler(temp=0.0)` passed explicitly to
`stream_generate` (mlx's default is argmax; V2 states it rather than
inheriting it). `enable_thinking=False` stays from the baseline; a
belt-and-suspenders `<think>` strip remains. `max_tokens` =
`min(words*3+96, 4096)` per window (corrections pass: 160); the
recorded `sampling.max_tokens_rule` matches. The chat
template is hashed (`template_revision`) and recorded per job. No
determinism claim across runtimes is made (S13/R02).

## Windows (long utterances, S13)

The fixed 35/50-word chunking is gone. `plan_windows`:

- A whole dictation within `WINDOW_MAX_WORDS` (200) is ONE generation.
- Longer input splits into **complete blocks** (paragraphs, whole list
  groups, code blocks — the M04 block commands already emit these); an
  oversized block splits at sentence boundaries inside it, never right
  after or right before a correction marker, and a block that OPENS
  with a marker packs with the previous block (up to 1.5× budget) so a
  correction cannot straddle a seam.
- Ownership is exclusive and exhaustive: every window owns a
  zero-based half-open code-point range of the normalized input,
  verbatim; seams contain only whitespace.
- Read-only neighboring context: the previous window's tail rides in
  the labeled `read_only_context` field ("do not repeat").

## Corrections (exact offsets, S13)

Corrections run as a separate proposal pass **only when a marker is
present** (never a second call on plain input). The proposal format is
V1's production-proven line format — the model lists the exact words to
delete (the outdated value together with its correction marker), one
span per line. The engine resolves each span to exact zero-based
half-open offsets by **sequential in-order matching**: a span resolves
to its first occurrence at or after the previous accepted span, so
duplicate correction spans delete in spoken order and an earlier
deletion can never redirect a later one to the wrong occurrence
(V1's post-deletion first-match quirk replaced by an explicit cursor).
An unlocatable span rejects with `offsets_unresolved`. Deterministic
guards (V1 semantics): marker-terminated spans, no bare markers,
≤ 6 words, ≤ 6 applied per window, no overlap with accepted spans.
Protected spans are rebased **per window** (window-local coordinates,
this window's texts only) before validation and the corrections guard.
Deletions apply right-to-left in Python; the surviving replacement and
reason clause stay by construction (only the outdated value + marker is
deleted).

## Document nodes and the renderer (S13)

`document_nodes` parses paragraphs, list groups (ordered with start
number, bullets) and fenced code blocks; the renderer — not the model
— controls numbering and separators. `renumber` enforces contiguous
numbering and continues a list group split across a window seam;
`continue_list_number` carries the next number to the following
window. Structure validation compares source-declared structure
(explicit M04 blocks: deterministic) against spoken-enumeration counts
(heuristic findings only).

## Validation (S14, E09)

`validation.validate(post_corrections_source, candidate)` returns a
report of components, each labeled **deterministic** or **heuristic**:

| Component | Kind | Fails → |
|---|---|---|
| `coverage` | deterministic | critical (flagged deletion ranges, question-flagged) |
| `numeric_values` | deterministic | critical (value-preserving word→digit passes; 30→300 fails) |
| `protected_tokens` | deterministic | critical |
| `literal_spans` | deterministic | critical (quoted text verbatim) |
| `negation_coverage` | deterministic | critical (multiset of negation words) |
| `uncertainty_coverage` | deterministic | critical (hedges: maybe, probably, …) |
| `technical_tokens` | deterministic | critical (paths, flags, versions, emails, URLs) |
| `novelty` | deterministic | critical (no invented content words; vocabulary canonicals excepted) |
| `names` | heuristic | finding only |
| `structure` | deterministic on explicit blocks; heuristic on spoken enumerations | fail / finding |

Authorized deletions: accepted corrections (applied before validation —
the validation source is the corrected text, so pre-correction offsets
are never passed), pure fillers, immediate function-word stutter (plus
the doubled preposition a correction leaves), phrase-initial
interjectors, number-word→digit representation changes whose value
survives, vocabulary alias→canonical pairs, and spoken-list markers
when ≥ 2 items are rendered (their values carried by the rendered
numbering). A deterministic failure rejects the candidate; heuristic
findings are review labels only. A validator rejection is a mining
signal (S29.9 hard trigger), never an automatic human dispreference —
outcome.correctness stays `unreviewed` and no preference is recorded
(M07-AC06).

## Termination, recovery and the fallback ladder (S13/S14)

Output-limit termination is detected from the generation token count
(`output_tokens >= max_tokens`). Recovery: split the owned range in
halves at a sentence boundary (never before a correction marker) and
retry the halves — the halves are fresh windows over the ORIGINAL
source range, so a sub-window fallback rolls back to true source text
(AC02). If a half still fails, the window ships its normalized source
with an explicit incomplete notice — a truncated model output is never
pasted as success (`incomplete: true`,
`termination.kind: "output_limit"`, path `llm_partial`; a failed retry
carries the same incomplete marking).

Per-window fallback ladder: validated clean output → the window's
normalized source (corrections rolled back with it — unvalidated
correction deletions never survive a rejected candidate, M07-AC02) →
job-level basic/raw (engine failure: the degraded basic
TranscriptCleaner answers with M03's exact labels). Recorded paths:
`llm` · `llm_partial` · `llm_fallback_normalized` · `basic` · `raw`;
`fallback_reason` carries the failing components
(`validation_rejected:coverage,…`) or `output_limit`. Fallback
references an immutable earlier artifact — never an already-mutated
base; the original ASR text stays recoverable upstream.

## Permitted context (from the M06 snapshot — the whole surface)

Cleanup receives, and only receives: **protected spans** (the M04
ledger's literal/quoted zones mapped raw→normalized by verbatim search,
`protected_spans_for_cleanup`, rebased per window), **relevant
vocabulary** (the job's frozen hint-set canonicals, ≤ 40), **vocabulary
pairs** (the frozen alias→canonical pairs, validator-only data),
**destination profile** (the M06 snapshot's target category → structure
hints), **locale** and **mode**. Nearby text, identifiers,
origins and workspaces never reach any cleanup prompt; "ignore previous
rules" in surrounding text cannot change cleanup behavior (the M06-AC04
invariant extends unchanged — pinned by test).

## Evidence (S29.4 cleanup family; S29.14)

With collection enabled, the worker's V2 result carries per-pass
observations (exact rendered prompts, inputs, outputs, token counts,
limit flags, window ranges) through the existing M02 prompt-dedupe
artifact mechanism (roles `cleanup_input_corrections` /
`cleanup_input_cleanup`, proposals as `cleanup_proposal` /
`cleanup_rejected_proposal`). `on_cleanup_result(..., v2=,
cleanup_context=)` writes the exact permitted-context payload as a
lease-governed `cleanup_context` artifact (vocabulary terms and
protected texts are content-bearing) and fills the envelope's
`cleanup.v2` block — content-free: prompt version/revision, template
revision, sampling, termination, window source ranges (normalized-text
coordinates; joined to raw coordinates through the normalization
ledger's input/output spans), validation component outcomes, fallback
lineage, corrections counts/reasons. Verbatim (raw) and
intended-writing (applied) references stay separate artifacts; window
source ranges give later supervised cleanup exports their coverage
maps.

## Limitations (documented, not hidden)

- A correction whose outdated value ends one block and whose marker
  opens the next applies only when both pack into one window (the
  marker-open packing rule); the residual case falls back losslessly
  (uncorrected source) — never corrupted.
- Corrections-proposal quality depends on the model; every proposal is
  deterministically guarded, and unresolved/ambiguous proposals reject
  with reasons (retained as evidence).
- The validator's sentence/question flags and name checks are
  heuristics on unpunctuated ASR text — findings, never gates.
- The adjudicated real-text validation subset (E04's 60-case stratum)
  awaits human review; the synthetic EV-09 strata (60 fidelity + 40
  structure + 20 literal) are the automatable acceptance set.
- `WINDOW_MAX_WORDS = 200` is the tested budget on this machine
  (ablation-measured); it is a constant, not a config knob.
