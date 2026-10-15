# ADR-0001: Your Voice gets a written profile from Claude

**Status:** accepted · **Spec deviation from:** S22 ("Profile generation
runs locally"), binding decision 7 (no network for ordinary operation),
S23 (profile synthesis on the qualified local engine), contract
`profile.md` ("no model call").

## Context

Wispr Flow's Insights → **Your voice** tab shows a written portrait of
how its user dictates: an archetype title with a short description, a
catchphrase, the most used and most removed word, and the peak time and
place. It was reverse-engineered from Wispr Flow 1.6.957's shipped
bundle and its on-disk state:

- The portrait is written by a server-side LLM. The client posts the
  most recent dictations (text, timestamp, app, language) plus locally
  computed stats to `POST /llm/voice_profile` and polls for the result.
  The prompt itself is server-side and was not recovered.
- It is regenerated at cumulative-word milestones — 2,000, 12,000,
  37,000, 87,000, 162,000, 262,000, then every 100,000 to 662,000 — with
  a progress bar ("Next update in N more words").
- The sample is the most recent speech up to a word budget per milestone
  (2,000, 12,000, 20,000, 30,000, 40,000, 50,000, then 60,000 words; at
  most 350,000 characters). Generating needs a minimum of stored text
  (2,000 / 5,000 / 10,000 / 20,000 words).
- Stats sent along: the (weekday, hour) with the most dictations and the
  top app in it ("Friday at 12 p.m."), the most used word (stopwords
  skipped) and the word most often removed between raw speech and the
  cleaned text.
- The model returns a headline, an archetype title and description, a
  peak-time description, a catchphrase with a description, and one of 22
  persona categories.

LocalFlow's Your Voice was deterministic by contract. The owner asked
for Flow's feature and approved the Claude API for it once it turned
out Flow uses an LLM.

## Decision

Your Voice gains a **written layer** beside the deterministic measured
profile, which is unchanged:

- `localflow/v2/voice_insights.py` builds the sample from the measured
  profile's eligible speech — live examples' own **raw** transcripts
  (S22: the user's speech, never the cleanup model's style) — newest
  first within Flow's budgets, computes the stats locally, and asks
  Claude for the fields through one structured-output Messages API call.
- **Model:** the newest active Opus that supports effort `xhigh` and
  structured outputs, found through the Models API at generation time
  (fallback `claude-opus-5-5`), effort `xhigh`, adaptive thinking, the
  server-side refusal fallback. A newer Opus is used as soon as it ships.
- **When:** automatically on the idle pass once per newly reached
  milestone, and whenever the user presses Write / Rewrite. A profile
  cleared by deletion waits for a press or the next milestone, so
  deletions never trigger paid re-runs. One generation runs at a time.
- **Key:** `INSIGHTS_ANTHROPIC_API_KEY` in the login Keychain (service
  `LocalFlow`), read through `/usr/bin/security`. It is never logged,
  emitted or put in a read model. Without a key the page explains how to
  add one and nothing is sent. The key is read only when the app runs on
  its real store, so no test harness can reach the API.

## What is sent, stored and cleared

- **Sent:** the sampled raw dictation text, each one's local time and
  app name, and the stats above. No ids, audio, context snapshots,
  dictionary or history beyond the sample.
- **Stored:** one row in `voice_insights` (schema v14) with the fields,
  milestone, model id, sample size and coverage, and the sampled example
  ids in `voice_insight_evidence`.
- **Cleared:** the row's text whenever any sampled example is deleted
  everywhere (same op), expires, leaves training, is quarantined, loses
  its raw transcript, is excluded from a measured snapshot, or its usage
  fact is removed — the M14-AC03 rule that derived text never outlives
  its source. Publication re-checks every sampled example in one write op
  (the profile.py D16 fence).
- **Never:** fed to dictation, cleanup, normalization or transforms
  (M14-AC04); the companion page itself makes no network calls (its CSP
  stays `connect-src 'none'`).

LF-R25 keeps banning network clients everywhere in `localflow/`, with a
single allowlisted (module, import) pair: `voice_insights.py` may import
`anthropic`.

## Consequences

- Ordinary dictation still needs no network; only writing a voice
  profile does, and the page says so before and after.
- Each generation costs a few cents at the first milestone and up to
  roughly a dollar at the 60,000-word budget.
- The AppKit fallback Hub shows only the measured profile.
- With short transcript retention, the written profile clears itself as
  sampled dictations expire; the owner's retention keeps them.

## Alternatives considered

- **Local Qwen3-4B (S23's engine):** fits the spec, but the archetype
  and catchphrase need judgment across thousands of words that a 4B
  cleanup model does not reliably give, and a long generation would hold
  the single GPU lock dictation uses.
- **Widening ProfileService:** its public surface is pinned by test
  (M14-AC04 discipline); a separate service keeps the deterministic
  profile exactly as qualified.
- **A key file in Application Support:** simpler, but a plain-text key
  beside the database; the Keychain was chosen.
