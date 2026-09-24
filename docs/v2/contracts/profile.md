# Contract: Your Voice profile

**Spec:** S22 (Your Voice and personalization), S25/S29.14 (deletion),
S23 (no extra resident model), E13 · **Owner:** M14 · **Suites:** EV-15
profile portion (tests/v2/personalization/test_profile.py), the Hub half
(tests/v2/ui/test_training_review_hub.py)

`localflow.v2.profile` (`ProfileService`) computes local, evidence-
linked profile snapshots; `localflow.v2.ui.your_voice` renders them as
the Insights view's **Your Voice** subview (S19 puts the communication
profile under Insights). Useful observations, never a personality
diagnosis.

## Eligible evidence (M14-AC02)

Speech statistics come only from **eligible** evidence: live,
trainable examples (`captured_unreviewed`, `review_candidate`,
`annotated`, `ambiguous` — never `quarantined_sensitive`: suspected
secrets feed no statistic, S29.14) of origin `live_capture`, read from their
retained **raw** transcript — the speech, never the cleanup model's
applied output (S22: Qwen's style is not the user's). Excluded from
speech statistics, each counted in `measured.excluded`:

- `snippet_expanded` — the example's normalization expanded a snippet
  (generated text);
- `background_speech` — its current review label carries the
  `background_speech` domain;
- `repeated_verbatim` — the same words as an earlier eligible
  utterance (a test phrase said over and over counts once);
- `user_excluded` — evidence the user excluded from a snapshot
  (durable; carried into every later snapshot by example id).

Excluded/expired/deleted/synthetic examples never enter at all.

## Measured views

Every measured value is a store fact with its source
(`measured.sources`): eligible examples and words, mean/median words
per utterance, frequent 2–3-word phrases (counted once per example,
with up to five supporting example ids each), corrections by kind (each
eligible example's CURRENT reviewed label — the latest revision; an
abstained latest revision counts as none), dictionary-hit dictations
and the approved terms with recorded use, spoken self-corrections the
cleanup stage detected (over the dictations whose cleanup recorded the
count — unknown is not zero), requested transforms (explicit runs and
auto-applied dictation transforms separately), app and mode usage, and
the **local** hour of each dictation from usage facts (the fact's recorded
UTC offset; dictations with no offset are counted in `hours_unknown`,
never bucketed by UTC). App names are private usage metadata: store and
local UI only.

## Interpretive cards

Rendered only at or above the interpretation floor — `profile_min_words`
eligible words (default 2,000, S22's initial default — a floor for
interpretation, not a validity claim) AND at least 10 eligible
dictations. Below it the snapshot carries measured totals and
`interpretive_note` explaining that more examples are needed; nothing
is fabricated to fill the screen (the M14 stop condition).

Cards are deterministic rule-based synthesis (no model call — S23 adds
no resident model for profile synthesis, and determinism keeps fixtures
stable). Each carries `kind: "interpretive"`, a title, a statement with
its own numbers, `coverage` (first/last capture) and the examples that
actually support it:

- `style-length` — concise / mid-length / long-form by median words;
  evidence = the utterances nearest the median;
- `correction-focus` — the most common current reviewed label kind;
  evidence = eligible dictations carrying that label ("an observation
  of reviewed labels, not a population rate");
- `technical-vocabulary` — approved terms with recorded use; evidence =
  eligible dictations whose normalization applied an approved rule.

## Snapshots are records, never caches

`profile_snapshots` (schema v10) rows are append-only records with
their algorithm version, measured JSON, cards, coverage and an
`evidence_signature` (eligible example revisions, exclusions, labels,
usage and vocabulary counts, the floor and algorithm version).
`profile_evidence` links every eligible example (role `measured`) and
every card example (role `card_example`).

- **Generation** runs on demand (Your Voice → Generate) or on the idle
  pass (Generate runs off the main thread and shows a failure in the
  pane rather than swallowing it). Evidence is read in bounded chunks (250 examples per short
  writer op) and counted off the writer; one short write op re-checks
  that every evidence example is still live — a deletion landing
  mid-read restarts the computation, so deleted speech never lands in
  a record — and inserts the snapshot.
- **The idle pass** (`profileIdlePass_`, every `profile_idle_minutes`,
  default 30; 0 disables) never starts while recording, while a job is
  pending, during the synthetic-paste window or an insertion/undo
  transaction; it runs `compute(only_if_changed=True)`, which adds NO
  snapshot when nothing changed. It decides first from an input
  signature built from counters only (revisions, example states,
  purges, labels, exclusions, usage, vocabulary) — no transcript is
  read; when those moved but the eligible evidence did not, one read
  confirms it and the new input signature is remembered.
- **Deletion (M14-AC03)**: delete-everywhere invalidates every snapshot
  that drew on the example (`source_deleted`) and clears its measured
  JSON and cards — phrases derived from deleted speech never outlive
  it. Any snapshot whose evidence later expired, left training or was
  quarantined is invalidated and cleared the same way on the next read
  or compute, the reason naming what happened (`evidence_expired`,
  `evidence_excluded_from_training`, `evidence_quarantined`,
  `source_deleted`). Regeneration always recomputes from the current
  store.
- **Exclusion**: excluding one supporting example invalidates the
  snapshot (`evidence_excluded`); the exclusion is durable. Excluding
  an id that is not evidence of the snapshot refuses
  (`not_evidence_of_this_snapshot`) rather than silently recording
  nothing.
- The pane never renders an invalidated snapshot's numbers or cards —
  it shows the reason and asks for a regeneration.

## No injection (M14-AC04)

No cleanup prompt, context snapshot, vocabulary selector or
normalization path reads a profile snapshot; the service exposes no
pipeline hook. Normal dictation never receives the profile or
conversation history (pinned by the engine-identity test).

## Events

`profile.snapshot_computed`, `profile.evidence_excluded`,
`profile.idle_failed` — reason codes and counts only.

## Config

`profile_min_words` (2000), `profile_idle_minutes` (30; 0 disables the
idle pass — Generate still works).

## Limitations (documented, not hidden)

- Three card rules exist; playful archetypes (S22's optional cards)
  are not synthesized — no rule without evidence to cite.
- Background speech is excluded only where a review label flags it; no
  automatic detector exists.

## Performance (measured, benchmarks/20260924-010937-m14)

10,000 eligible dictations (284,990 words): compute p95 313 ms in
250-example read chunks plus one write op; a dictation's store write
waits at most 54 ms during it (16 probes); Python peak 41.4 MB. The
idle pass over unchanged evidence costs p95 38 ms — counters only, no
transcript read — and writes nothing.
