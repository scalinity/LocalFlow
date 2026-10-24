# Contract: Your Voice profile

**Spec:** S22 (Your Voice and personalization), S25/S29.14 (deletion),
S23 (no extra resident model), E13, ADR-0001 (written layer) ·
**Owner:** M14 · **Suites:** EV-15
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
applied output (S22: Qwen's style is not the user's). The raw text is
admitted by the evidence resolver (contracts/learning.md, m14-policy-r1
D11): the example's own job's `raw_transcript`, retained, matching its
digest — another job's raw, another example's, or an applied output
recorded in the raw slot is never read as speech. Excluded from
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
abstained latest revision counts as none), dictionary-hit dictations,
`technical_terms` — approved, enabled dictionary entries that
normalization applied in ELIGIBLE dictations, each with its count of
eligible dictations and up to five supporting example ids (D04) —
`dictionary_terms_with_recorded_use`, the dictionary's own usage
counters labeled with that source (all dictations, not cleared by
Delete Usage; never presented as speech), spoken self-corrections the
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
- `technical-vocabulary` — the speech-derived `technical_terms`;
  evidence = exactly the eligible dictations those terms cite.

## Written layer (ADR-0001)

Beside the measured profile, `localflow.v2.voice_insights`
(`VoiceInsightsService`) keeps one Claude-written voice profile: a
headline, an archetype title and description, a catchphrase with a
description, a persona (one of 22 categories) and a peak-time
description, plus the locally computed peak time label and app, most
used word, most removed word and the number of dictations sent that
contain the catchphrase.

- **Milestones** (cumulative dictated words, `SUM(final_words)` over
  dictation usage facts): 2,000, 12,000, 37,000, 87,000, 162,000,
  262,000, 362,000, 462,000, 562,000, 662,000. States: `locked`,
  `first_time_eligible`, `current`, `refresh_eligible`, `complete`,
  `invalidated`, with Flow's progress fraction and words remaining.
- **Gate and sample:** eligible speech is `profile.eligible_speech()` —
  the same raw transcripts `compute()` counts, minus user exclusions.
  Generating needs 2,000 / 5,000 / 10,000 / 20,000 stored words by
  milestone (`insufficient_local_words` otherwise, with the numbers);
  all retained eligible speech is sent oldest first, with no milestone
  word cutoff. A request exceeding 350,000 characters is refused as
  `history_too_large` before sending anything, preserving any existing
  profile rather than silently omitting old speech.
- **Interpretation:** per-day word and dictation counts accompany the
  history. The portrait describes habits repeated across dates and
  contexts, not a catalogue of recent projects or apps. A weekly peak
  requires the same weekday/hour on two distinct local dates (recorded
  offsets), ranked by dates, then dictations, then earliest slot. Without
  repetition, label/app are null and the peak description is forced empty.
- **Request:** one structured-output Messages API call (`SCHEMA`), the
  newest active Opus supporting effort `xhigh` (Models API; fallback
  `claude-opus-5-5`), effort `xhigh`, server-side refusal fallback. Sent:
  all retained eligible text, local time and app per dictation, and the stats — no
  ids. Key from the Keychain (`LocalFlow` / `INSIGHTS_ANTHROPIC_API_KEY`),
  read only for the real store.
- **When:** the idle pass writes once per newly reached milestone;
  `voice.write` writes on demand. One generation at a time
  (`already_running`); an invalidated profile waits for a press or the
  next milestone.
- **Storage and clearing:** `voice_insights` / `voice_insight_evidence`
  (schema v14), one row. Its text is cleared (`fields_json='{}'`,
  `state='invalidated'`) when a sampled example is deleted everywhere
  (`source_deleted`, same op), leaves the trainable states
  (`evidence_expired`, `evidence_excluded_from_training`,
  `evidence_quarantined`), loses its raw transcript (`source_purged`),
  is excluded from a measured snapshot (`evidence_excluded`), or its
  usage fact is removed (`usage_removed`); a row with no evidence links
  clears too (`evidence_missing`). Scrubbed on every status read and
  after each retention pass. Publication re-checks every sampled example
  in one write op and refuses (`evidence_changed`) if any changed.
- Nothing in the written layer reaches dictation (M14-AC04); only the app
  and the companion import it (pinned by test).

## Snapshots are records, never caches

`profile_snapshots` (schema v10) rows are append-only records with
their algorithm version, measured JSON, cards, coverage and an
`evidence_signature` (eligible example revisions, the exclusions
digest, the latest label per example, the M13 usage revision, the
vocabulary entry revisions, the floor and algorithm version — 2). The
usage revision moves on EVERY usage mutation — a retry
that only changed a mode, an explicit transform, a deletion — so a
usage-dependent snapshot never goes stale behind unchanged totals.
`profile_evidence` links every eligible example (role `measured`) and
every card example (role `card_example`).

- **Generation** runs on demand (Your Voice → Generate) or on the idle
  pass (Generate runs off the main thread and shows a failure in the
  pane rather than swallowing it). Evidence is read in bounded chunks (250 examples per short
  writer op) and counted off the writer, which records the exact raw
  artifact and latest revision of every example it read. One short
  write op re-checks every one — still live, same revision, artifact
  retained — plus the label and exclusion state the computation used
  (D16); any change restarts the computation, so deleted, purged,
  revised, relabeled or excluded speech never lands in a record — and
  inserts the snapshot.
- **The idle pass** (`profileIdlePass_`, every `profile_idle_minutes`,
  default 30; 0 disables) never starts while recording, while a job is
  pending, during the synthetic-paste window or an insertion/undo
  transaction; it runs `compute(only_if_changed=True)`, which adds NO
  snapshot when nothing changed. It decides first from an input
  signature built from counters only (revisions, example states,
  purges, labels, exclusions, usage, vocabulary) — no transcript is
  read; when those moved but the eligible evidence did not, one read
  confirms it, and the new input signature is remembered only when the
  recomputed evidence signature is equal.
- **Deletion (M14-AC03)**: delete-everywhere invalidates every snapshot
  that drew on the example (`source_deleted`) and clears its measured
  JSON and cards — phrases derived from deleted speech never outlive
  it. Any snapshot whose evidence later expired, left training or was
  quarantined is invalidated and cleared the same way on the next read
  or compute, the reason naming what happened (`evidence_expired`,
  `evidence_excluded_from_training`, `evidence_quarantined`,
  `source_deleted`, or `source_purged` when the example is live but its
  supporting raw transcript was purged). Regeneration always recomputes from the current
  store.
- **Usage removal (M13 D11)**: deleting usage (one job or all) or its
  expiry redacts, in the same writer op, the usage-derived fields of
  EVERY snapshot, current and historical (`app_usage`,
  `hour_histogram`, `hours_unknown`, `modes`, `requested_transforms`,
  `dictionary_hit_examples`), and records `usage_redacted` with the
  reason; speech-derived fields, cards and evidence links stay. The
  pane explains the removal; the next generation (or idle pass, since
  the usage revision moved) recomputes from the usage that remains. A
  computation in flight reads usage inside its own final write op, so
  it never publishes a copy of usage deleted before that op.
- **Exclusion**: excluding one supporting example invalidates every
  current snapshot that presents it as support (`evidence_excluded`) —
  excluding through an older rendered snapshot also retires a newer one
  built from the same evidence; the exclusion is durable. Excluding
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
`profile.idle_failed`; written layer: `voice_insights.generated` (model
id, milestone, sample size, token counts), `voice_insights.failed`,
`voice_insights.unavailable`, `voice_insights.idle_failed` — reason codes
and counts only.

## Config

`profile_min_words` (2000), `profile_idle_minutes` (30; 0 disables the
idle pass — Generate still works).

## Limitations (documented, not hidden)

- Three measured card rules exist; the playful archetype is the
  written layer's (ADR-0001), which the AppKit fallback Hub does not
  show.
- Background speech is excluded only where a review label flags it; no
  automatic detector exists.

## Performance (measured, benchmarks/20260928-120630-m14-remediation-final)

10,000 eligible dictations (286,190 words): compute p95 560 ms in
250-example read chunks plus one write op that re-checks every input;
a dictation's store write waits p95 87 ms and at most 205 ms during it
(94 probes); Python peak 47.5 MB. The idle pass over unchanged evidence
costs p95 104 ms — counters only, no transcript read — and writes
nothing.
