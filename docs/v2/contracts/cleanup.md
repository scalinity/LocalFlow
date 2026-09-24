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
template is hashed (`template_revision`, from `ModelRunner` through
`CleanupEngine` into the result) and the corrections proposal prompt is
hashed (`corrections_prompt_revision` = `m07c:<sha256-12>`); both are
recorded per job. No determinism claim across runtimes is made
(S13/R02).

## Windows (long utterances, S13)

The fixed 35/50-word chunking is gone. `plan_windows`:

- A whole dictation within `WINDOW_MAX_WORDS` (200) is ONE generation.
- Longer input splits into **complete blocks** (paragraphs, whole list
  groups, code blocks — the M04 block commands already emit these), and
  a block that OPENS with a marker packs with the previous block (up to
  1.5× budget) so a correction cannot straddle a seam.
- An oversized block splits only at **safe cuts** (`_safe_cuts`, the one
  policy shared with output-limit recovery): a sentence start (after
  `. ! ?`, next word capitalized) or a line start — never inside a
  protected span or a code fence, never within six words after a
  marker phrase (`i mean`, `no wait`, …) or single-word marker (`no`,
  `sorry`, `actually`, …) nor right before a marker phrase. There is no
  conjunction, word-index or midpoint fallback: a block with no safe cut
  stays one (oversized) window.
- Ownership is exclusive and exhaustive: every window owns a
  zero-based half-open code-point range of the normalized input,
  verbatim; seams contain only whitespace. Every protected span lies
  wholly inside one window (windows a span would cross merge); a span no
  window owns is an engine error, never a silent drop.
- Read-only neighboring context: the previous window's tail rides in
  the labeled `read_only_context` field ("do not repeat").

## Corrections (exact offsets, S13)

Corrections run as a separate proposal pass **only when a marker is
present** (never a second call on plain input); the trigger covers every
marker the proposal format supports, standalone `actually` included.
The proposal format is V1's production-proven line format — the model
lists the exact words to delete (the outdated value together with its
correction marker), one span per line. The engine resolves each span to
exact zero-based half-open offsets (on word boundaries) by **sequential
in-order matching**: a span resolves to its first occurrence at or
after the previous accepted span, so duplicate correction spans delete
in spoken order and an earlier deletion can never redirect a later one
to the wrong occurrence.

Proposals are **provisional**. Deterministic guards, each rejecting with
a recorded reason:

| Guard | Reason |
|---|---|
| a proposal batch cut off by the output limit applies nothing | `batch_truncated` |
| the span ends with a marker (on a word boundary) | `no_marker_ending` |
| not a bare marker | `bare_marker` |
| ≤ 6 words | `span_too_long` |
| the text occurs in the window no more often than it was proposed — never resolved to a first match | `ambiguous_occurrence` |
| resolvable at/after the cursor | `offsets_unresolved` |
| no overlap with a protected span | `protected_span` |
| stays inside one sentence | `crosses_sentence` |
| the outdated value X (before the marker) has a content word | `no_outdated_value` |
| a replacement Y with a content word follows the marker in the same sentence | `no_replacement` |
| `i mean it/that/this` is emphasis | `emphasis_not_correction` |
| through a single-word marker (`actually`, `sorry`, `no` — also ordinary words), X and Y are visibly parallel: both numbers, both weekdays, both months, or sharing a content word | `not_parallel` |

At most 6 apply per window. Protected spans are rebased **per window**
(window-local coordinates, this window's texts only) before validation
and the corrections guard. Deletions apply right-to-left in Python to
form the model's input; the surviving replacement and reason clause
stay by construction. The window's validation runs against the
**original** window text with the accepted deletions as authorized
spans (below), and that decision settles each proposal as `selected`
(kept in the returned text) or `rolled_back`; a truncated pass's
proposals are `superseded` by the split retry that re-proposes them.

## Document nodes and the renderer (S13)

`document_nodes` parses paragraphs, list groups (ordered with start
number, bullets) and fenced code blocks as the validation view. The
renderer — not the model — controls numbering: `renumber_text` changes
only the digits of ordered-list markers, numbering each indentation
level contiguously from its run's first declared number (nested runs
restart under each parent item; a list split at a window seam numbers
as one run). Indentation, nesting, bullets, blank lines, fence info
strings and code bytes pass through unchanged; `next_list_number`
carries the next top-level number to the following window. Structure
validation compares source-declared structure (explicit M04 blocks:
deterministic) against spoken-enumeration counts (heuristic findings
only).

**The final artifact.** Each window's candidate is renumbered (with the
seam-continued start) BEFORE validation, so the validator judges the
digits that will ship. Fallback windows ship their source bytes and are
never rendered. A run of consecutive validated windows is rendered and
then checked (`_render_final`): the rendered text may differ from the
validated text only in ordered-marker digits, and every protected text
survives at least as often — otherwise the validated text ships
unrendered. Every seam joins on the source's own separator (blank line,
line break, or space at a sentence cut). One pair of quotes wrapping
the model's whole reply is removed unless the source is itself so
quoted; quotes inside the text are never stripped.

## Validation (S14, E09)

`validation.validate(original_window_text, candidate, protected=,
vocabulary_pairs=, continued_list_start=, correction_spans=)` returns a
report of components, each labeled **deterministic** or **heuristic**.
The reference is always the ORIGINAL window text; accepted correction
deletions ride as `(start, end, marker_start)` spans, so a false
correction is judged against what it removed, never against the
fragment it left.

| Component | Kind | Fails → |
|---|---|---|
| `coverage` | deterministic | critical — every source word survives in order or is authorized away (flagged deletion ranges, question-flagged); no word inside a protected occurrence is ever authorized away, so the designated occurrence — not an equal text elsewhere — survives |
| `clause_scope` | deterministic | critical — an explicit source boundary (`. ! ? ;` or a line break) next to a negated or conditional sentence survives as an output boundary (`. ! ? ; :`, newline or dash); merging "Do not deploy. Run tests." into one clause fails; unpunctuated source is unconstrained |
| `numeric_values` | deterministic | critical — typed numeric occurrences survive **in order** with sign, unit (`%`, `$ € £`, unit words) and identity (times, leading-zero codes, versions/ranges, letter-digit identifiers like `Qwen3-4B` — case-exact unless the source spelling is all lowercase — and commas that are not thousands grouping); grouping and number words are representation (`thirty percent` ↔ `30%`). Source list markers are structure: each ordered list's start number survives. An output list marker is structure only when it opens a list (1, a spoken-enumeration value, a source start, the seam-continued start) or follows its predecessor — otherwise it is an invented value |
| `protected_tokens` | deterministic | critical — each protected occurrence survives with exact bytes, as often as protected, on token boundaries; a dictated literal (`literal_escape`, `quoted`) may take an initial capital, a `generated` span may not |
| `literal_spans` | deterministic | critical (quoted text verbatim) |
| `negation_coverage` | deterministic | critical — the negation multiset is preserved exactly: none lost, none added (a correction's marker is not content) |
| `uncertainty_coverage` | deterministic | critical — the hedge multiset is preserved exactly |
| `technical_tokens` | deterministic | critical — paths, flags, versions, emails, URLs, case-significant words (`MB`, `UserID`, `iOS`) with exact case, and operator symbols (`= + < > ≤ ≥ ≠`) by count (a spoken `equals`/`plus`/`minus` may add its symbol); a `?` may be added, never dropped |
| `novelty` | deterministic | critical — no content word, and no operator word (`not`, `or`, `if`, `nor`), appears more often than in the source (plus the canonical words of matched vocabulary replacements): catches invented facts, repeated clauses and copied read-only context |
| `names` | heuristic | finding only |
| `structure` | deterministic on explicit blocks; heuristic on spoken enumerations | fail / finding |

Authorized deletions (never inside a protected occurrence): accepted
corrections (their spans — whose words may not reappear: novelty does
not count them), pure fillers, immediate function-word stutter (plus
the doubled preposition a correction leaves), interjectors at a phrase
start (text start or after `. ! ? ; :`/newline, possibly after other
fillers — never mid-phrase), number-word→digit representation changes
whose value survives, spoken-list markers when ≥ 2 items are rendered
and the marker's own content (words a correction removed skipped) opens
a rendered item — a sentence-final marker only where the output turns
its sentence into a `…:` intro directly before an item — and **matched
vocabulary replacements**: an alias occurrence
in the source is authorized only while the output holds a corresponding
extra canonical occurrence — a word outside every matched alias is
never authorized, and a canonical may only appear where an alias was
replaced. A deterministic failure rejects the candidate; heuristic
findings are review labels only. A validator rejection is a mining
signal (S29.9 hard trigger), never an automatic human dispreference —
outcome.correctness stays `unreviewed` and no preference is recorded
(M07-AC06). Lexical components bound what a candidate may change; they
do not prove unrestricted semantic equivalence.

## Termination, recovery and the fallback ladder (S13/S14)

Output-limit termination is detected from the generation token count
(`output_tokens >= max_tokens`). Recovery: split the owned range at the
safe cut nearest its word midpoint (`_safe_cuts`) and retry the halves
— fresh windows over the ORIGINAL source range, each with child-local
protected spans sliced from the child's own text, so a sub-window
fallback rolls back to true source text (AC02). When both halves
validate, their assembly is revalidated as a candidate for the whole
window (cross-seam order, duplication, multiplicity). With no safe cut,
a half that still fails, or a rejected assembly, the window ships its
normalized source with an explicit incomplete notice — a truncated
model output is never pasted as success (`incomplete: true`,
`termination.kind: "output_limit"`, path `llm_partial`; reasons
`output_limit`, `output_limit_retry_failed`,
`retry_assembly_rejected:…`).

Per-window fallback ladder: validated clean output → the window's
normalized source (corrections rolled back with it — unvalidated
correction deletions never survive a rejected candidate, M07-AC02).
A V2 engine failure — load failure or an in-flight exception — answers
with the unchanged normalized input (path `llm_fallback_normalized`,
reason `cleanup_engine_failed`, `termination.kind: "engine_error"`):
protected literals, quotes and code bytes survive because nothing
edits them. Protection the coordinator cannot map abstains from model
cleanup the same way (reason `protection_unmapped`). The selectable V1
path keeps its own basic fallback. Recorded paths: `llm` ·
`llm_partial` · `llm_fallback_normalized` · `basic` (V1) · `raw`;
`fallback_reason` carries the failing components
(`validation_rejected:coverage,…`) or the termination reason. Fallback
references an immutable earlier artifact — never an already-mutated
base; the original ASR text stays recoverable upstream.

## Permitted context (from the M06 snapshot — the whole surface)

Cleanup receives, and only receives: **protected spans** as
`(start, end, kind)` — the M04 ledger's literal/quoted zones mapped
raw→normalized **through the ledger's edit coordinates**
(`protected_spans_for_cleanup(raw, normalized, protected, edits)`: each
boundary shifts by every edit wholly before it, so the designated
occurrence maps, never an earlier repetition; a boundary inside an edit
widens to that edit's output edge; a span the ledger cannot describe
raises), plus M10's generated snippet/file-tag spans (kind
`generated`, exact) — rebased per window, **relevant
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

**Decision evidence (`decision_schema: "m07-decisions-2"`).** Every
generation pass carries `pass_id`, `parent_pass_id` (a split-retry half
points at the truncated pass), `depth`, `window_range`, `max_tokens`,
`output_tokens`, `limit_hit` and `status` (`selected` · `rejected` ·
`truncated` · `rolled_back`); these ride the envelope's content-free
`cleanup.passes`, and `cleanup.decisions` lists every window and
retry-assembly decision (status, failing component names, applied-text
hash). The complete manifest — every pass, correction proposal (span,
marker, status `provisional`→`selected`/`rolled_back`/`superseded`, or
`rejected` with its reason) and full validation report with findings —
is the
lease-governed `cleanup_decisions` artifact
(`cleanup.v2.decisions_artifact_id`); prompts and outputs are
referenced by their own artifact ids, not copied. `corrections.applied`
counts only deletions kept in the returned text (`proposed`,
`rolled_back`, `rejected` beside it). Only a `selected` whole-window
(depth 0) candidate is joined as `artifact_ids.cleanup_proposal`. Records captured before this
schema lack these keys — absent means not captured, never inferred.
None of this is a label: correctness stays `unreviewed`.

## Limitations (documented, not hidden)

- A correction whose outdated value ends one block and whose marker
  opens the next applies only when both pack into one window (the
  marker-open packing rule); the residual case falls back losslessly
  (uncorrected source) — never corrupted.
- Corrections-proposal quality depends on the model; every proposal is
  deterministically guarded, and unresolved/ambiguous proposals reject
  with reasons (retained as evidence). The evidence guards are lexical
  (content words on both sides of the marker); a proposal that passes
  them and removes a requirement is still caught only by the window's
  validation against the original text.
- The lexical validator bounds changes to words, operators, numbers,
  identifiers and sentence boundaries; it does not prove semantic
  equivalence (e.g. a scope change that keeps every boundary and word
  count). Stricter checks trade toward fallback: a false rejection
  ships the normalized source, never a corrupted text.
- A block with no safe cut (no sentence or line start outside protected
  spans and code) stays one window above the budget; if its output hits
  the limit it ships the normalized source with the incomplete notice.
- Known false rejections (fail safe to the normalized source):
  contraction changes (`do not` ↔ `don't`), number-word phrases the
  compact parser reads as sums (`nineteen ninety nine`, `five thirty`,
  `a hundred`), dictated emails (`dot`/`at` → `.`/`@`), a spoken list
  whose connective (`and`) is dropped without a spoken marker, and a
  correction that removes a negation or hedge word from its outdated
  value.
- A split-retry half gets no read-only context from its parent window
  and both halves get the parent's list continuation; the assembly is
  revalidated and renumbered as one run.
- Vocabulary authorization binds the first N alias occurrences (N = the
  canonical's surplus in the output), not where the canonical lands.
- A new ordered list the model renders from prose may start at 1 or a
  spoken-enumeration value; its presence is checked (`structure`), not
  its placement.
- The validator's sentence/question flags and name checks are
  heuristics on unpunctuated ASR text — findings, never gates.
- The adjudicated real-text validation subset (E04's 60-case stratum)
  awaits human review; the synthetic EV-09 strata (60 fidelity + 40
  structure + 20 literal) are the automatable acceptance set.
- `WINDOW_MAX_WORDS = 200` is the tested budget on this machine
  (ablation-measured); it is a constant, not a config knob.
