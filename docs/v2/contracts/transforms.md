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

## The Prompt Engineer's additional contract

`atoms.py` extracts requirement atoms deterministically (questions,
negations, edit constraints, counts, ordering, deadlines, uncertainty
cues, quoted spans, URLs/technical paths — each with its source
excerpt and coverage anchors) and `coverage_map` reports, per atom,
which output span carries it: `covered` (an anchor located),
`uncertain` (partial evidence only), `missing`. Missing or uncertain
atoms are review issues: the original wording is surfaced beside the
diff and the result degrades to `needs_review` — **never silently
dropped as "irrelevant"**, and auto-apply declines. Every mode guards
quoted spans, links and technical tokens verbatim (case-sensitive); an
empty output is never a result. The acceptance set: 30 synthetic
cases (15 dev / 5 validation / 10 held-out, E04) with enumerated
anchors — pass = anchors survive or the loss is honestly flagged;
zero silent losses.

## The two execution surfaces

- **Selected-text execution:** the status menu's Transforms submenu
  (rebuilt on open) starts a run from idle only. The focused
  selection, its range and a snapshot-shaped target identity are
  captured off the UI callback; the pill acknowledges immediately
  (MODE_TRANSFORMING, measured ≤50 ms budget); the generation runs on
  a transform thread; the preview panel shows the block/word diff with
  review clauses kept, and the actions: **accept** (replacement
  through the M08 queue — revalidation first: a changed selection is
  never overwritten, M11-AC03; `target_changed` routes to the copy
  offer), **copy**, **retry-original**, **apply-another** (the source
  again under another definition) and **transform-of-result**; undo of
  an accepted replacement is the M08 target-bound undo (Recovery menu)
  — this panel never builds a second undo engine. Save-to-Scratchpad
  is honestly labeled as arriving with M12 (no dead button).
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
(`insert_text_artifact_row`/`grant_lease_row`). The same-task
invariant is enforced at write time — a judgment across task keys
refuses. Judgments: `accept|reject|undo|prefer_a|prefer_b|tie|neither|
uncertain`; the dictation auto-apply path records candidates only
(an automatic application is not a preference, S29.10 — no judgment,
no inferred winner).

## Evidence (S29.4 transform family; S29.14)

`EvidenceCollector.on_transform_result` (dictation path, before
finalize) retains the exact rendered prompt and output as
lease-governed artifacts and fills the envelope's content-free
`transform` block (transform id/revision, prompt revision, task key,
path, reason, coverage counts, tokens, duration, artifact ids). With
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

- The atom extractor is deterministic and conservative: it extracts
  constraint-shaped clauses, not full semantics — an atom miss is a
  review flag, and the anchors are English-word based (the E04 cases
  are English; a multilingual extractor is future work if evidence
  demands it).
- Coverage `uncertain` uses order-free content-word evidence (≥ 3/4)
  — honest hedging, never a guessed pass.
- The selection capture requires Accessibility trust and a readable
  focused field; `app_denied` destinations (context_denied_apps)
  refuse transforms honestly.
- A transform generation queues behind/holds the serialized GPU lock:
  a concurrent dictation's ASR waits (measured 0.65 s behind a
  504-word transform on this machine) — recorded, never starved.
- The preview panel's visual pass (layout, focus, text scale) is the
  pending native trial; the headless suites cover state, wiring, the
  real coordinator and the insertion composition.
