# Contract: Faithful cleanup and document-aware formatting

**Spec:** S13, S14, S15 (clean mode), S24 (budget context), S29.4
(cleanup family) · **Owner:** M07 · **Suites:** EV-09
(tests/v2/fidelity/, tests/v2/structure/), EV-19 (cleanup fields)

`localflow.v2.cleanup` (`prompts`, `document_nodes`, `lexicon`,
`correction_retention`, `validation`, `engine`, `model`) renders the user's intended wording without ever
answering, executing or rewriting the dictation. V1
(`localflow.cleanup.TranscriptCleaner`) stays intact and selectable
(`cleanup_implementation: "v1"`) as the ablation control and fallback;
the default is `v2` on the M07 ablation evidence
(`benchmarks/<run>-m07/m07.json`).

## The faithful contract (S13, frozen verbatim)

`prompts.CONTRACT` is the S13 clean-prompt contract word for word. The
prompt is versioned by content hash: `prompt_revision()` =
`m07:<sha256-12>` over contract + formatting guidance + examples + version — an edited word
can never share a revision id with the old prompt. Curated examples
satisfy the contract themselves (digits stay digits, the exact
`/code-review` token, retained questions, cloud stays cloud, discourse
words like "like"/"you know" are content, Spanish stays Spanish).

Instructions stay separate from payloads: system message = the
contract plus owner-approved formatting guidance; examples = few-shot turns;
the final user message is a JSON
payload with the S13 field names — `transcript`, `mode`, `locale`,
`destination_profile`, `relevant_vocabulary`, `protected_spans`,
`structure_hints`, `permitted_edits` (plus an explicitly labeled
`read_only_context` for window overlap). Vocabulary alias→canonical
pairs are validator data only and never enter the prompt.

The list guidance
formats explicit introductions such as “here is a list of grocery items”
into a retained prose heading and one bullet per item. Ordinary prose,
discussion of lists and quoted uses of “list” stay prose; closing conditions
remain outside the list. Each few-shot example contains its transcript and
response. One shared instruction assigns clean mode, en-US, no supplied
vocabulary or protected spans, and the final job's content-free destination
profile, structure hints and permitted edits. The final job retains its full
structured payload. Markdown support does not become a request to turn every
sentence into bullets.

The validator permits the final list-joining “and” to become a bullet
separator only when an unambiguous matching introduction and every item
match the source words in order, fillers aside. The introduction is the
last sentence before the colon; it names a `list` and holds `here is`/`here
are` or ends with `list` or `list is`. An item never runs past a source
sentence boundary, so a closing sentence glued onto the last bullet fails.
It does not authorize dropping “and” within an item, introduction words,
protected text, or item content.

Consecutive spoken step labels (`step 1`, `step one`, or `step number one`)
introducing actions or questions become numbered items, including without
an introduction. Introductory prose and explicit closing sentences stay
outside the list; multiple sentences within a step stay together. Step
references and quoted labels stay prose. Nonconsecutive, repeated or
reversed labels are preserved in prose instead of silently renumbered.
The validator authorizes a label's deletion only when the complete item's
tokens match the source in order and every rendered number matches the
corresponding source label. Conjunctions within an item remain content.
Word labels one through twenty and positive digit labels are recognized;
other forms retain the existing lossless fallback behavior. This is model
formatting guidance with fidelity guards, not a deterministic transcript
rewriter or permission to execute the steps.

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

**Prefix cache.** `ModelRunner` prefills each prompt in `PREFILL_STEP`
(2048) token blocks and caches whole blocks of an instruction prefix, so
the cached and uncached paths process the prompt in the same groups.
Only prompts the cleanup engine renders through `render_cached` are
cached; that call records where the final user turn starts from the
message list, so dictated text containing a turn marker cannot move the
boundary, and the final dictation is never cached. Transform prompts use
`render` and are never cached, so they cannot evict the cleanup prefix.
`PREFIX_CACHE_SLOTS` (2) holds the cleanup and corrections prompt
families, least recently used dropped first; each request generates from
a private copy of the stored state. Load warms the cache with a real
cleanup prompt. A prompt with no cacheable block is passed on as the
tokens already encoded. The opt-in `test_prompt_cache_parity`
(`LOCALFLOW_PREFIX_CACHE_PARITY=1`) checks cached against uncached tokens
on the real model and reports the mlx-lm version, which is not pinned.

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
present** (never a second call on plain input). Existing direct triggers,
including standalone `actually`, are retained. Standalone `sorry` and `no`
are admitted only when a possible deletion ending at that marker passes
the existing `_evidence_reason` guard: a nearby outdated value and a
parallel replacement, within the same sentence and six-word span budget.
This admission proposes or deletes nothing. The model's exact proposal
still passes offset resolution, all protection/evidence guards, and full
candidate validation; ordinary negative/interjection prose does not gain
an unconditional extra correction-model call.
The proposal format is V1's production-proven line format — the model
lists the exact words to delete (the outdated value together with its
correction marker), one span per line. The engine resolves each span to
exact zero-based half-open offsets (on word boundaries) by **sequential
in-order matching**: a span resolves to its first occurrence at or
after the previous accepted span, so duplicate correction spans delete
in spoken order and an earlier deletion can never redirect a later one
to the wrong occurrence.

Proposals are **provisional**. Each accepted proposal is parsed once into
its neighbourhood (`lexicon.neighbourhood`: the old value's words, the
first words after the marker in the same sentence, a frame word leading
both, and whether the replacement closes its clause) and admitted as one
`AdmittedCorrection` record (span, marker offset, exact restart and
qualifier move). Applying the deletion, the observation record, the
comparison view and validation all read that record; nothing re-derives
admission. Shared word classes and the number and unit grammar live in
`lexicon`. Deterministic guards, each rejecting with a recorded reason:

| Guard | Reason |
|---|---|
| a proposal batch cut off by the output limit applies nothing | `batch_truncated` |
| the span ends with a marker (on a word boundary) | `no_marker_ending` |
| not a bare marker | `bare_marker` |
| ≤ 6 words (`SPAN_MAX_WORDS`); one quantity with its detail (a fraction head is one) may reach 10 words (`BOUND_SPAN_MAX_WORDS`) when retention binds it against a replacement that repeats its unit. A line over 80 characters (`SPAN_MAX_CHARS`) is not read as a proposal | `span_too_long` |
| the text occurs in the window no more often than it was proposed — never resolved to a first match | `ambiguous_occurrence` |
| resolvable at/after the cursor | `offsets_unresolved` |
| no overlap with a protected span | `protected_span` |
| stays inside one sentence | `crosses_sentence` |
| the outdated value X (before the marker) has a content word | `no_outdated_value` |
| a replacement Y with a content word follows the marker in the same sentence | `no_replacement` |
| `i mean it/that/this` is emphasis | `emphasis_not_correction` |
| through a marker that is also ordinary speech (`actually`, `sorry`, `no`, `make that`), X and Y are visibly parallel: both numbers, both weekdays, both months, sharing a content word, closed numeric metric-length values, a repeated `as` frame with one closed complement, or two closed identifiers; the replacement does not open a new predicate | `not_parallel` |
| replacing a weekday/month with another cannot also delete preceding content words (for example, `check Monday no wait Tuesday` may delete `Monday no wait`, but not `check`) | `overbroad_calendar_value` |

**Markers.** The markers are `lexicon.CORRECTION_MARKERS`; a comma may
separate the words of a compound marker (`no, sorry`, `I mean, actually`),
and the whole compound is the marker, so its `no` is not a lost negation.
Validation reads consecutive markers as one marker: markers directly
before a deletion's recorded marker (`0.5 seconds no I mean`) belong to
it when the old value before them is complete, holding its own number or
closed by a comma (`Dr. Okafor, no I mean Dr. Lindqvist`; in `There are
no, sorry, there are two` the `no` is the old value), and markers left right after
a deletion belong to it while a replacement follows (`ten, no, sorry,
eleven` deleting `ten, no`; `6 am no make that 7 am`). A trailing run
never takes a word that can open the replacement: no marker ending in
`no` (`5, no wait, no more than 6`; `sorry, wait, no more licenses`),
`make that` only before a number (`make that change` is a predicate), and
`scratch`, `sorry`, `actually` or a marker starting with `no` only when a
comma closes it (`sorry, scratch disk`, `sorry, no wait at all`).

**Closure.** A replacement closes its clause when, after an optional
repeated frame word and one article, its value is followed by the end of
the text, a comma, semicolon or line break, or sentence punctuation
before a space (`lexicon.CLAUSE_END`). The `as` frame (`as suspect,
actually, as fine.`) and the identifier branch (`sample_index, sorry,
record_cache.`) apply only to closed replacements; `as soon as the bank
confirms` and `worker_b is running` continue into a clause and fall back
to the other parallel checks. A digit inside an identifier (`worker_1`)
is part of a name, not a number. Through a single-word marker, an
auxiliary right after the replacement value, or after a number and its
noun, makes the value a new subject (`Monday, no Tuesday is a holiday`):
not parallel. The replacement may repeat the article that stands before
the old value (`on the 12th, no, the 14th`). A repeated `every` is itself
the evidence for a frequency correction (`every month, no every
quarter`). Through `make that`, the replacement must also end its clause
within one word more than the old value (`50 microliters, um, make that
60 microliters.`); `make that change`, `make that bigger` and `make that
the default` stay prose and do not call the corrections model.

A metric-length pair may change its numeric value and metric prefix when
both values name meters/metres and the replacement closes its clause.
Extra descriptions and open replacement clauses do not qualify. A proposal containing one fused alphabetic word may restore the
space between two unique adjacent source words; the recovered proposal
must then resolve to one exact contiguous source span and pass every
existing bound and guard. Ambiguous nominal phrases, apologies and
preposition attachments do not gain correction permission from their shape.

At most 6 apply per window. Protected spans are rebased **per window**
(window-local coordinates, this window's texts only) before validation
and the corrections guard. Deletions apply right-to-left in Python to
form the model's input; the surviving replacement and reason clause
stay by construction.

**Retained details.** An exact source detail attached to an outdated
quantity (`4 liters of dye, no wait, 6 liters`) moves beside the
replacement quantity when the replacement repeats the quantity's unit and
does not state its own detail of the same relation. A frame word leading
both quantities (`with 4 liters of dye, sorry, with 6 liters`) is set
aside, and the replacement must repeat it. A detail starts with one of
`lexicon.DETAIL_PREPOSITIONS`, and it ends before a clause link
(`lexicon.CLAUSE_LINKS`), `only` or punctuation. A restated recipient
after `to` must be a bounded noun phrase or pronoun on both sides.
Explicit presence→absence (`with dye … without dye`) replaces the
descriptor; other opposing relations reject (`opposing_quantity_qualifier`).
A quantity detail the rule cannot bind (a spelled number, a determiner
before the number, an unrepeated frame, an unresolved replacement)
rejects as `unresolved_quantity_qualifier`. The moved wording remains
required; an obsolete value cannot return through the word-addition
allowance. Original proposal and moved-source coordinates remain in the
observation record.

**Fractions.** A complete fraction head (`7 quarters of a turn`: a
positive count agreeing with `half`/`halves`/`quarter`/`quarters`, `of
a`/`an`, and one measure unit) corrected to `1 half` or `1 quarter` of the
same unit needs no move when the replacement closes its clause, the count
starts its own source token, the marker is not a bare `no`, and no
quotation, code span or fence overlaps or touches the correction.

**Frequency frames.** A value-only proposal inside `every 18 cycles,
sorry, every 27 cycles` includes the first `every` when both complete
quantity heads repeat it with the same unit. A repeated preposition
around a short corrected value is included the same way; the frame must
sit on the value's own line.

**Repeated restarts.** A compound `I mean actually` restart may remove a
repeated `it <modal> be` frame (any of `lexicon.MODALS`) only when the
original subject is `it` or a determiner followed by one to three plain words, the adjacent modal predicate is identical, and
both numeric values use the same explicit unit. Subject postmodifiers,
function words, quantifiers and visible plural forms are excluded.
Changed subjects, modality, negation, units, protected text and sentence
boundaries do not gain deletion permission. The additional restart range is
recorded separately from the marker-terminated proposal.

**Quote-sensitive rules.** The fraction exception, the incomplete-restart
authorization and the list-connective placement abstain only when a
quotation, inline code span or fence (`lexicon.quoted_regions`) overlaps
or touches their own span. An apostrophe after a letter (`don't`,
`patients'`) is not a quote; a quote or code mark without a partner makes
the whole text one region.

Validation uses the source with only these exact qualifier moves and
accepted deletion spans rebased into that comparison view
(`correction_retention.correction_view`). The decision
settles each proposal as `selected`
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

`validation.validate(source, candidate, protected=, vocabulary_pairs=,
continued_list_start=, correction_spans=, protected_positions=)`
returns a report of components, each labeled **deterministic** or
**heuristic**. `source` is the window's comparison view: the original
window text with exact inherited qualifiers moved beside their
replacements. Accepted correction deletions ride as rebased `(start,
end, marker_start)` spans; retained qualifiers stay ordinary required
words; `protected_positions` are the window's protected occurrences.
Original coordinates remain in the correction record. Comparison atoms
are words (hyphenated tokens split, apostrophes ignored) and whole
identifiers (`sample_index`, `name:value`), which never split into words.

| Component | Kind | Fails → |
|---|---|---|
| `coverage` | deterministic | critical — every source word survives in order or is authorized away (flagged deletion ranges, question-flagged); no word inside a protected occurrence is ever authorized away, so the designated occurrence — not an equal text elsewhere — survives |
| `clause_scope` | deterministic | critical — an explicit source boundary (`. ! ? ;` or a line break; the sentence a negation or condition is read from runs past a title's period, `Dr.`, `Mr.`, `Mrs.`, `Ms.` or `Prof.`, while that period still counts as a boundary a merge must keep) next to a negated or conditional sentence survives as an output boundary (`. ! ? ; :`, newline or dash); merging "Do not deploy. Run tests." into one clause fails, whatever conjunction opens the second sentence. Text an admitted correction deletes shapes no sentence: a boundary inside it (`for 15 minutes. Actually no, 10 minutes`) and its words (the marker's `no`) do not count. A new break may not detach a trailing `only` from its clause, or separate `only` from the condition, subordinator or preposition after it (`only if`, `only then`), unless a new subject and finite auxiliary follow `only`; and new terminal punctuation may not strand a conjunction (`water and. I want`) |
| `numeric_values` | deterministic | critical — typed numeric occurrences survive **in order** with sign, unit (`%`, `$ € £`, unit words) and identity (times, leading-zero codes, versions/ranges, letter-digit identifiers like `Qwen3-4B` — case-exact unless the source spelling is all lowercase — and commas that are not thousands grouping); grouping and number words are representation (`thirty percent` ↔ `30%`). Source list markers are structure: each ordered list's start number survives. Rendered list labels, taken from the `document_nodes` parse, never bind a value; a label must open a list (1, a spoken-enumeration value, a source start, the seam-continued start) or follow its predecessor — otherwise it is an invented value. A source quantity therefore cannot become a label (`1 apple` is not `1. Apple`); bare source numbers stand behind labels only as a spoken run 1, 2, 3 … whose members open a clause and are followed by a comma or a determiner or subject pronoun (`One, check …`, `1 the east wing …`). Closing brackets, quotes and sentence punctuation after a number, in any order, are not part of it (`12).` holds `12`), and a number-word phrase's words are separated by spaces only (`the Tuesday one. Four, set …` holds 1 and 4) and never end in `point` (`we lost one point.` keeps the word). A plain number dictated right after a word may fuse with it into one identifier, the word's letters (in the source's case unless the source word is all lowercase), an optional `-` or `.`, then the number's digits as written (`WGS eighty four` → `WGS84`, `PROJ four` → `PROJ.4`; `BA084` or `PROJ.4.0` adds digits), unless the word is a function word or the source already holds that identifier |
| `protected_tokens` | deterministic | critical — each protected occurrence survives with exact bytes, as often as protected, on token boundaries; a dictated literal (`literal_escape`, `quoted`) may take an initial capital, a `generated` span may not |
| `literal_spans` | deterministic | critical — each quoted source literal keeps its own delimited output occurrence of the same kind (double or single quotes; glyph style may change), verbatim apart from an initial capital |
| `negation_coverage` | deterministic | critical — the negation multiset is preserved exactly: none lost, none added (a correction's marker is not content, and a negation in an admitted correction's old value is not lost when the replacement restates it in the same place, the same word at the same position after the deletion: `no acute pneumothorax, sorry, no acute effusion`; a negation elsewhere in the sentence restates nothing; a negation word hyphenated into a name, `--no-cache`, negates no clause and is left to coverage and novelty) |
| `uncertainty_coverage` | deterministic | critical — the hedge multiset is preserved exactly, read through corrections the same way (`about 45 minutes, no sorry, about 50 minutes` keeps one `about`) |
| `technical_tokens` | deterministic | critical — paths, flags, versions, emails, URLs, identifiers, case-significant words (`MB`, `UserID`, `iOS`) with exact case, and operator symbols (`= + < > ≤ ≥ ≠`) by count (a spoken `equals`/`plus`/`minus` may add its symbol); a `?` may be added, never dropped. Pipes keep their count, and each standalone pipe or pipe run stays in its original gap between the same aligned words, with the same numbers, punctuation and line breaks; only horizontal spacing there may change |
| `novelty` | deterministic | critical — no word, including articles, prepositions, pronouns and auxiliaries, appears more often than in the source plus matched vocabulary replacements; `a`/`an` share an existing occurrence allowance. Removed correction words cannot fund additions. This catches invented facts, grammar completion, repeated clauses and copied read-only context |
| `names` | heuristic | finding only |
| `structure` | deterministic on explicit blocks; heuristic on spoken enumerations | fail / finding |

Authorized deletions (never inside a protected occurrence): accepted
corrections (their spans — whose words may not reappear: novelty does
not count them), pure fillers, immediate function-word stutter (a filler
between the copies does not break it: `the uh the`; a repeated
function-word phrase ending in an article is one too: `in the in the`,
`on the, uh, on the`; quoted text keeps its repeats), the restated frame
a correction leaves doubled (up to four words right after
the deletion that repeat the words right before it: `longer than 6 hours,
no wait, longer than 4 hours`; a single word only as a function word or
preposition, or before a number that replaces a number: `target 212, no
wait, target 221`; the frame counts once for negation and hedges), the
earlier copy of an exact restatement that changes only a number, and the
first copy of an immediately repeated incomplete opening such as `that we
that we should`.

An exact restatement (`assign 4 rooms with extra linen to Marta. Sorry, 6
rooms with extra linen to Marta.`) authorizes the earlier copy and its
marker as a correction span when every word around the number repeats
after the marker: up to three repeated words before the number, at least
two after it, each copy within one sentence, the restated copy closing its
clause, and no quotation, protected text or other correction touching it.
It applies only when the output dropped one copy and the marker; the
restated words and the new number stay required, so a dropped qualifier,
a changed recipient or identifier, the same number, an apology that opens
a clause, a negation in the old copy or a kept old value still fail.
That opening is `that`/`which`/`who`/`whom` plus a subject pronoun before a
retained finite auxiliary. Exactly two copies and their preceding word
must share one clause with only horizontal spacing; a proposed deletion
qualifies only when the second copy and auxiliary remain at their matched
position and all other required words survive in order. The removed copy
cannot fund new words, and unchanged text grants no deletion permission.
A quotation, code span or fence touching the opening, an existing
list-item line, and overlap with protected, correction, vocabulary,
list-marker or numeric representation spans exclude this rule. It does
not authorize repeated finite phrases (`who had who had`), temporal words
(`then then`) or other repeats beyond the stutter list: `had had`, `that
that`, `then then` and `we know we know` can be grammatical or emphatic,
so such repeats are kept. Other
authorized deletions are interjectors at a phrase
start (text start or after `. ! ? ; :`/newline, possibly after other
fillers — never mid-phrase), number-word→digit representation changes
whose value survives, spoken-list markers when ≥ 2 items are rendered
and the marker's own content (fillers and words a correction removed
skipped) opens a rendered item (a sentence-final marker only where the
output turns its sentence into a `…:` intro directly before an item;
sequence words such as `then` stay content, because one can open a
condition's consequent), and **matched
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
window (cross-seam order, duplication, multiplicity), with each half's
admitted corrections rebased into the parent window by offset rather
than admitted again against the parent text. With no safe cut,
a half that still fails, or a rejected assembly, the window ships its
normalized source with an explicit incomplete notice — a truncated
model output is never pasted as success (`incomplete: true`,
`termination.kind: "output_limit"`, path `llm_partial`; reasons
`output_limit`, `output_limit_retry_failed`,
`retry_assembly_rejected:…`).

Per-window fallback ladder: validated clean output → the window's
normalized source (corrections rolled back with it — unvalidated
correction deletions never survive a rejected candidate, M07-AC02).
Before fallback, a bounded repair loop runs at most one step per repair:
putting back, byte for byte, a rejected correction the cleanup applied
anyway (a proposal that resolves to one exact source place, clear of the
admitted corrections, when the output lacks its words and the source
words on both sides are adjacent in the output; that correction stays
uncorrected as dictated and the window keeps the rest of its cleanup);
splitting one fused candidate word at the exact space between two unique
adjacent source words (when `coverage` and `novelty` are the only
failures); removing a new break that detached a restriction or
conjunction (when `clause_scope` is the only failure), absorbing only
the spacing beside the break; and restoring a few dropped source words
(when `coverage` is the only failure, at most `SALVAGE_MAX_WORDS` and
`SALVAGE_MAX_SHARE` of the window), reattaching a restriction the
restored words detach. A restored connective opens a list item only when
that item is a sentence. A step is taken only when its result has
strictly fewer failures than its input and no new ones, and every step's
result passes the complete validator. A candidate the loop cannot make
valid is reported and rolled back as the model wrote it.
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
  whose connective (`and`) is dropped without a spoken marker, a
  correction that removes a negation or hedge word from its outdated
  value, bare digit labels followed by a word they could count (`1 open
  the panel. 2 inspect all 2 leads.` rendered as a numbered list), a
  merge of a conditional fragment into the next sentence (`If X. We
  should Y.`), and a correction whose old value plus a compound marker
  exceeds the word cap.
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
