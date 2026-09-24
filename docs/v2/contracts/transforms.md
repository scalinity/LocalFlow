# Contract: Transforms and the Prompt Engineer

**Spec:** S15 (transform-backed modes), S16, S13 (the faithful
boundary), S18 (replacement authority), S24, S29.4 (transform family),
S29.10 · **Owner:** M11 · **Suites:** EV-13 (tests/v2/transforms/),
EV-19/EV-20 (producer fixtures in test_transform_pipeline.py)

`localflow.v2.transforms` (`prompts`, `definitions`, `atoms`,
`engine`, `diffview`) + `transforms_store` (schema v7) + the
coordinator's executor/selection paths and the Hub Transforms view
deliver deliberate local rewriting as a product workflow — never a
loosening of faithful cleanup (S16: a transform never expands the S13
permitted edits; requirement preservation is this contract, not a
cleanup relaxation).

## Definitions and revisions

- A `TransformDefinition` carries id, name, mode
  (`polish|concise|prompt_engineer|custom`), origin
  (`builtin|legacy|user`), prompt revision (content hash — an edited
  word never shares a revision id), declared edit types, optional
  writing samples (`(before, after)` pairs), a single-character
  shortcut, target profiles and the auto-apply flag. Store as many as
  useful; nothing is subscription-capped.
- **Old definitions are never erased:** every edit appends a preserved
  revision to `transform_revisions`; deletion disables, never deletes
  (M11-AC01). The two uploaded V1 definitions materialize from the M02
  legacy artifacts as `origin="legacy"` rows — prompt verbatim, legacy
  `key` recorded but **never bound** (existing keys 1/2 are not
  automatically Option shortcuts), frozen against edits.
- Shortcuts are menu key equivalents; collisions are detected at write
  time (case-insensitive) and surfaced in the Hub — never silently
  rebound, and never a global key grab.
- The strengthened built-ins (`builtin:polish`, `builtin:concise`,
  `builtin:prompt_engineer`) carry versioned contracts in `prompts.py`
  (the S16 Prompt Engineer contract verbatim in substance). The
  uploaded V1 prompt's "relevant context"/"format if implied"/"be
  concise" wording appears nowhere and cannot override the constraints.

## Execution and task identity (S16/S29.10)

`TransformJob` freezes the immutable source revision, transform +
prompt revisions, mode, custom instructions and examples; its
`task_key` hashes exactly (mode, source, instructions, examples
revision, locale). **Retry-original is the same task** (a fresh
attempt may join the task key as a preference candidate);
**transform-of-result and any changed source/instructions are
different tasks** — never exported as same-input pairs (M11-AC05).

`run_transform` renders contract system message + few-shot samples +
one labeled draft payload (instructions never mix into the payload;
the label, not a bare JSON object, is what the 4-bit model reads
reliably), runs ONE bounded greedy generation on the cleanup engine's
model in the worker subprocess (`transform` op; no second engine, no
model change; serialized with every other GPU request — a concurrent
dictation's ASR waits its turn, measured and recorded). Output budget
`min(words*4+128, 4096)`; an output-limit hit falls back to the
original with the honest reason — a truncated proposal never applies.

Result paths: `applied` (validated) · `needs_review`
(`requirement_coverage_uncertain` — original clauses kept, never
auto-applied) · `fallback_original` (generation failed/limit/refused).
A source over 12,000 characters refuses honestly, never truncates.

## The requirement-preservation gate (`atoms.py`, revision `m11-gate-2`)

A deterministic gate that **fails closed**: a requirement it cannot
place in the output is a review issue, never silently applied. An
empty requirement map is never proof of fidelity.

**Representation.** Every source clause is a requirement atom (kind
`requirement`). Clauses come from sentence ends, newlines, `;`, `:`,
spaced dashes and commas; list markers and heading marks are blanked
first; a piece opening with a subordinator (if/unless/when/once/
before/after/until/only if/…) joins the piece it governs; content-free
pieces join their neighbour; "X and/but Y" splits only when both sides
carry at least two content words and X holds no negation/hedge/
condition/scope that could govern Y. Quoted (double/curly, single
quotes not touching word characters, backticks, fences), URL (trailing
`.,;:!?` and unbalanced `)` stripped), path (rooted `~/`, `/`, `./`
with spaced middle segments; relative), file (any letter-initial
extension, longer than three characters) and identifier (letters mixed
with digits except ordinals/units, underscores, camelCase, versions)
spans are **exact-carry literals** (kinds `quoted`, `link`,
`identifier`): masked before splitting, deduplicated case-sensitively,
and required verbatim in the output (case-sensitive; a word boundary
is checked only at an alphanumeric edge).

Each clause carries an operator profile: negation, hedge/optional,
condition (including soft conditions such as "if they exist"/"if
possible", which govern the words before them and are not
interchangeable with "maybe"), scope, alternative, interrogative
(`?`, why/whether/how, contextual what/which/who/where, "ask … if"),
sequence (a numbered item satisfies it), directional relation
(before/after/once/until/then, with direction), stop, always,
comparators (le/ge/lt/gt/eq; "no more than" is a comparator, not a
negation) and numbers bound to the noun they count. Each operator
governs the content words up to the next operator. In a draft that
asks for a prompt, the framing ("write/make/draft a prompt", "asks the
copy editor to", "prompt for the retrospective", "makes clear",
"note that") is not a requirement.

**Coverage by mode.**

| Mode | Gate |
|---|---|
| Prompt Engineer | full: the clause's content (⅔ of its stems; all when ≤ 2) in ONE output segment — or, for clauses with ≥ 4 stems and pure ordering clauses, a short run of adjacent segments (headings between bullets are skipped); every operator holds there with its governed words and direction; equally good segments that disagree on negation/hedge are `uncertain`; ordered clauses keep their order; every source content stem survives somewhere |
| Polish, Concise | operators: no content threshold, but every operator, bound number and comparator holds in the segment carrying that clause's content, and no clause gains a governing operator |
| Custom | exact-carry literals only — its instruction defines what may change |

For Prompt Engineer, Polish and Concise the output is also checked for
**invention** (atoms of kind `added`, excerpt = the added output text):
an operator added to a matched segment that governs clause content
(negation/hedge/scope/condition/alternative/stop; an added `exactly`
is allowed); S16 escalation terms absent from the source (implement,
deploy, migrate, benchmark, test, refactor, commit, push, merge,
release, production, backend, frontend, database, schema, security,
compliance, criteria, environment, fix, code, delete, remove, ship,
rollback, deadline) unless a negation earlier in the segment governs
them; novel numbers (not list markers, labels like "Step 1", or "one");
novel identifiers/paths/URLs.

Statuses are `covered`/`uncertain`/`missing`; any review issue makes
the result `needs_review` with the source clause (or the added output
text) kept as a de-duplicated review excerpt beside the diff; auto-apply
declines. The historical atom kinds (`question`, `negation`, `count`,
`ordering`, `edit_constraint`, `deadline`, `uncertainty`) remain
defined so older coverage JSON reads. `TransformResult.to_json()`
records `validator_revision`; coverage entries serialize their atom's
kind and operators and survive the worker protocol
(`engine.result_from_message` rebuilds them parent-side).

**Why Polish and Concise are gated too.** Their own contracts in
`prompts.py` require every condition, negation, quantity and question
to survive, and their auto-apply exposure is the same as Prompt
Engineer's. They skip the content threshold and global-presence rule
because rewording and removing redundancy are their job. Custom stays
exact-carry only (recorded under Limitations).

**The acceptance set** is `tests/v2/transforms/fixtures_prompt_engineer_v2.json`:
15 dev, 5 validation, 10 regression (the v1 held-out cases, exposed
during the remediation) and 10 new blind held-out families. Each case
encodes relations the independent oracle
(`test_prompt_engineer_cases.judge`) checks inside one output segment;
verdicts are reported separately (applied, applied-semantic-failure,
review-addresses-loss, review-misdirected, review-no-loss, fallback,
error) — a fallback is never counted as applied. v1 stays unchanged as
the historical manifest.

## The two execution surfaces

- **Selected-text execution:** the status menu's Transforms submenu
  (rebuilt on open) starts a run from idle only. The capture
  (`insertion/selection.py`, off the UI callback) **classifies the
  focused field first** — a secure field refuses (`secure_field`)
  without reading its selection, range or value — then records the
  selection, its range, the window title and up to 200 characters of
  text on either side. The pill acknowledges immediately
  (MODE_TRANSFORMING, measured ≤50 ms budget); the generation runs on
  a transform thread; the preview panel shows the block/word diff with
  review clauses kept, and the actions (laid out side by side, never
  overlapping): **accept** (replacement through the M08 queue under
  **strict replacement** — positive proof of the same selection in the
  same document, contracts/insertion.md; anything short of that routes
  to the copy offer, M11-AC03), **copy**, **retry-original**,
  **apply-another** (the source again under another definition) and
  **transform-of-result** (a new task over the output whose
  DESTINATION stays the originally captured selection or note region —
  never the current caret); undo of an accepted replacement is the M08
  target-bound undo (Recovery menu) — this panel never builds a second
  undo engine. Since M12, **save-to-Scratchpad** is live (the output
  becomes a new note with its task identity recorded), and a
  NOTE-scope capture (the Scratchpad's picker — selection or whole
  note) accepts into the editor instead of the external queue, bound
  to its captured note and region (contracts/scratchpad.md).
- **Automatic application (the dictation path):** a resolved
  transform-backed mode whose bound definition opted in
  (`auto_apply`, default **off** — M11-AC04) transforms the **Clean
  artifact** before insertion: the cleanup stage's applied output
  stays the Clean text, the transform writes its own stage artifacts,
  and only a validated (`applied`) result changes the inserted text —
  anything else inserts Clean with the honest reason recorded in the
  job, the menu line and the envelope. A transform never runs over an
  unretained base (`transform_requires_cleanup` when cleanup is off).

## Mode resolution (extends contracts/profiles.md)

All six S15 modes are executable. A transform-backed mode resolves
`effective_mode = mode` only when the frozen `TransformSnapshot`
finds its bound definition opted in and targeting the resolved
profile; otherwise Clean with the honest `fallback_reason`
(`transform_auto_apply_disabled:<mode>`,
`transform_profile_not_targeted:<profile>`,
`transform_not_bound:<mode>` — two auto-applicable custom transforms
are ambiguous, never guessed).

## Store (schema v7, additive; the vocabulary pattern)

`transforms` (versioned rows + usage counters) +
`transform_revisions` (append-only) + `transform_meta` (state
counter) + `transform_candidates`/`preference_observations` (S29.10):
rows carry hashes/ids/counts only; source/output texts ride
lease-governed artifacts written inside the same writer op
(`insert_text_artifact_row`/`grant_lease_row`).

**Candidates are training evidence and follow collection consent
(S29.2).** `record_candidate` writes nothing and returns `None` unless
collection is `enabled`: the selected-text and note previews read the
consent state inside the same writer op (a revocation while the
generation ran is honoured); the dictation path passes the consent its
job captured at start (`collecting`). The transform itself works the
same either way (`candidate_id` None). With an output artifact, the
candidate retains two children of it: `transform_prompt` (the exact
rendered prompt) and `transform_decision` (JSON: path, reason,
validator revision, task key, the full coverage map and the review
excerpts shown). A note candidate's source artifact carries `note_id`
and `note_revision_id`.

The same-task invariant is enforced at write time — a judgment across
task keys refuses. Judgments: `accept|reject|undo|prefer_a|prefer_b|
tie|neither|uncertain`. **Retry Original is not a judgment:** it
records no observation; the new candidate's output artifact names the
earlier candidate as `retry_of`. The dictation auto-apply path records
candidates only (an automatic application is not a preference, S29.10
— no judgment, no inferred winner). A `needs_review` candidate is
never a preference by itself; an explicit human accept of it is
legitimate evidence and stays distinguishable because its decision
record keeps the automated status (the M14 transform export carries
`automated_path` and `decision_artifact_id`).

## Evidence (S29.4 transform family; S29.14)

`EvidenceCollector.on_transform_result` (dictation path, before
finalize) retains the exact rendered prompt, the output and the
`transform_decision` record (child of the output) as lease-governed
artifacts and fills the envelope's content-free `transform` block
(transform id/revision, prompt revision, task key, path, reason,
coverage counts, validator revision, tokens, duration, artifact ids). With
no transform requested the slot's reason is `not_applicable`; a
requested-but-not-run transform records its gate reason — never a
silent Clean. History's fourth lineage stage resolves from
`transform_output` artifacts.

## Events

`transforms.not_applied`, `transforms.selection_unavailable`,
`transforms.busy`, `transforms.accepted`, `transforms.copied`,
`transforms.insertion_done`, `transforms.review_required` (via
stage.completed), `transforms.record_failed`,
`transforms.store_unavailable` — content-free (ids, reasons, counts).

## Config

No new knobs. The transform surface is store-configured (Hub
Transforms view); execution budgets are engine constants, not config.

## Limitations (documented, not hidden)

- The gate is lexical and English: it binds operators, governed
  words, numbers, direction and literals, not full semantics. A
  paraphrase that keeps every operator and content word but changes
  meaning is not caught; a synonym that replaces an operator word
  ("leave X untouched" for "do not modify X") is reviewed. Its
  false-review rate on real model output is measured by the
  model-backed suite, not assumed.
- Custom transforms carry only the exact-carry gate: the user's
  instruction may legitimately remove or reword clauses, so a lost
  condition under a Custom instruction is not caught.
- Identifier literals are case-sensitive: a Polish that capitalizes a
  dictated "q3" to "Q3" is reviewed.
- The selection capture requires Accessibility trust and a readable
  focused field; `app_denied` destinations (context_denied_apps)
  refuse transforms honestly; a secure field refuses before any read.
- A transform generation queues behind/holds the serialized GPU lock:
  a concurrent dictation's ASR waits (measured 0.65 s behind a
  504-word transform on this machine) — recorded, never starved.
- The preview panel's visual pass (layout, focus, text scale,
  keyboard reachability) is the pending native trial; the headless
  suites cover state, wiring, geometry, the real coordinator and the
  insertion composition.
- Task identity hashes the contract, custom instruction and user
  examples; the built-in few-shot turns and payload framing are pinned
  by a test (`tg_task_identity_inputs_pinned`) so editing them forces a
  `prompts.VERSION` bump.
