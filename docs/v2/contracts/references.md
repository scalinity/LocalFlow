# Contract: References (four distinct objects)

**Spec:** S29.6 · **Owner:** M01 · **Suites:** EV-19, EV-20, EV-21

1. **Verbatim speech reference** — audio-reviewed words under a declared
   transcription policy (including meaningful repetitions). Supports ASR
   scoring. `origin: "audio_reviewed"`.
2. **Intended written reference** — authorized final representation and
   structure, resolved self-corrections included. Supports cleanup
   scoring. Not acoustic truth.
3. **Span annotation** — a reviewed local change with explicit coverage; a
   corrected name verifies that span only.
4. **Preference judgment** — see `preferences.md`. Never a transcript.

## Invariants

- A confirmed paste is not a confirmed transcript; an undo or quiet period
  is an observation, not approval.
- Partial correction grafts remain weak/partial references; they never
  upgrade to full gold and never grant whole-utterance SFT eligibility.
- Audio-reviewed and intention-only annotations are stored separately.
- A reference is never retroactively changed to make a model pass; changes
  create a new version with a reason.
- Provider (comparator) output is evaluation-only and never relabeled as
  human gold.

## Baseline status (M01)

No human-reviewed references exist yet. The 749 legacy pairs are candidate
corpus material only. The five supplied WAVs have no gold transcript.
Nothing in the repository is labeled as a reference.
