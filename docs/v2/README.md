# LocalFlow V2 — Start here

**Package version:** 1.1 · 21 September 2026  
**Purpose:** Complete pre-build specification and execution package, amended for training-grade data collection, ASR context hints and optional cloud reference evaluation.  
**Implementation status:** Planning documents only. This package contains no V2 implementation, trained weights, real-model benchmark results or new human-reviewed speech dataset.

## 1. Which file does what?

| File | Use it for | Do not use it for |
|---|---|---|
| `LOCALFLOW_V2_SPEC.md` | Canonical product/architecture, 33 requirements, exact behavior/data/privacy contracts. S29–S31 contain the new training/comparator/adaptation design. | Evidence that planned capabilities already ship. |
| `LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md` | Canonical metrics, fixtures, 22 test suites, promotion gates, comparator protocol and portable dataset validation. New details are E18–E20. | Claiming proposed tests or performance targets have passed. |
| `LOCALFLOW_V2_MILESTONES.md` | Canonical sequence: M01–M16, required reading, dependencies, tasks, acceptance items and fresh-session handoffs. | One giant implementation prompt that runs all milestones in one context. |
| `LOCALFLOW_V2_SPEC.docx` | Human reading edition of the specification with rendered architecture diagrams. | Independent architecture or an alternative version to edit separately. |
| `LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.docx` | Human reading edition of the evaluation plan. | A different test plan from its Markdown source. |
| `LOCALFLOW_V2_MILESTONES.docx` | Human reading edition of milestone contracts and kickoff instructions. | An additional milestone schedule. |
| `EVIDENCE_SUMMARY.json` | Preserved original historical aggregates; source/denominator context for the baseline. | Gold transcripts, labels, an RL dataset, current runtime statistics or V2 benchmark results. |
| `LATENCY_BASELINE.csv` | Preserved original historical ASR-plus-cleanup timings. | Release-to-visible-text latency, a current Mac benchmark or a model leaderboard. |
| `SHA256SUMS.txt` | Integrity checks for the other nine package files. | Verification that the product is implemented or tests pass. |
| `README.md` | Package entry point, file roles, installation in the repo and first-session instructions. | A fourth competing specification. |

**Markdown is canonical.** Word files are regenerated reading editions; their diagrams render the relationships expressed in the Markdown Mermaid blocks. Read one representation, not both. The original historical JSON and CSV are preserved byte-for-byte. The corresponding full private log, recordings and database were not included in the original specification ZIP and remain excluded from this ZIP.

## 2. Put the package in the working repository

Use the existing `scalinity/LocalFlow` checkout. Place this folder's files under `docs/v2/`. Do not replace source code, the installed app, user configuration or the data directory with anything in this package. The historical audited commit is a reference, not an instruction to reset the current branch.

Before replacing any pre-existing `docs/v2/` files, inspect local changes and preserve genuinely newer work. These v1.1 documents are the coordinated replacement for the supplied v1.0 set. Avoid mixing an old milestone document with a new specification.

Inside the extracted package directory, verify integrity:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

All nine checks should pass. The manifest does not hash itself. After future intentional edits, regenerate the reading editions and checksums together; an old manifest should not falsely certify new content.

## 3. Start M01 in a fresh coding-agent session

The first session reads this README, Spec S01–S06 and the exact M01 required sections. M01 creates `START_HERE.md`, `STATUS.json`, the contract index, baseline manifest and handoff directories. Their absence before M01 is expected, not an external blocker. The examples inside the documents are templates, not existing status files or completed milestones.

Copyable kickoff:

```text
Implement LocalFlow V2 M01 only, using docs/v2/README.md and the three
canonical v1.1 Markdown documents.

Read the M01 section and its specifically required spec/evaluation sections.
Inspect the current checkout, uncommitted work, installed app and effective
configuration. Preserve the confirmed Parakeet v3 + Qwen3 4B baseline and
existing analytics/dictionary/transforms. Do not reset to the historical
snapshot or replace locally newer work.

Create the planned startup/status/contract/handoff scaffolding; these files
are not prerequisites before M01. Register LF-R01–LF-R33 and EV-01–EV-22.
Record actual source/config/data provenance and baseline tests. Preserve
private recordings/logs/datasets outside Git. Reserve evaluation families
before tuning; training labels are not inferred from old model outputs.

Complete automatable M01 work, record unavailable native/human verification
as pending, write the M01 handoff and acceptance results, and provide the
next eligible milestone kickoff. Stop at M01. Do not implement the remaining
milestones, run model training, rent compute or upload audio to a provider.
```

For later sessions, follow Milestones P03/P06: read the compact startup/status index, selected milestone, required contracts/sections, prerequisite handoffs and accepted decisions. Run baseline tests before changes. Stop at the assigned milestone boundary or a coherent checkpoint with a precise handoff. Never mark unavailable human checks as passed.

## 4. What changed in v1.1?

The native Python/MLX/AppKit direction, initial Parakeet/Qwen controls, existing feature scope and all 16 milestone numbers remain. New requirements are:

- **LF-R29:** capability-qualified pre-decode hints, sharing a Relevant Vocabulary Selector with post-ASR recovery.
- **LF-R30:** live Training Evidence capture, exact inputs/lineage, independent consent/retention and deletion.
- **LF-R31:** classified corrections, hard/representative sampling and valid same-task preferences.
- **LF-R32:** family-safe splits, task-specific datasets and portable verified exports.
- **LF-R33:** optional cloud comparator plus explicit short/acoustic/context challenge evaluation.

All five map to tests EV-18–EV-22 and owning milestones. Existing requirement IDs and acceptance obligations remain. The Spec integrates the new contracts into existing pipeline/context/storage/Hub/privacy sections and adds S29–S31. The Evaluation Plan adds E18–E20 and gate G10. The Milestones document adds concrete tasks, tests and acceptance items, not just a trailing wish list.

All M01–M16 sections receive either implementation or traceability/producer changes. The largest expansions are M02, M08/M09, M14 and M15. M14-A/B/C are resumable checkpoints within M14, not extra milestones. A new agent may resume the same milestone at a checkpoint to avoid context rot.

## 5. Collect evidence early, not at the end

**M02:** one-time local collection choice, real live hooks, stable record/audio/task identities, exact permitted model inputs, output lineage and retention leases. Enable collection on the actual app at this point to accumulate evidence while the rest of V2 is built. No repeated per-utterance confirmation is required after the choice.

**M03–M07:** original-sample fidelity, capability manifests, typed edits, actual hint/context use and cleanup proposals/validation/fallbacks become richer.

**M08/M09/M11:** reliable bounded edits and explicit correctness/span/preference review begin before M14. Unsupported editors report unknown outcomes instead of recording arbitrary keystrokes.

**M14:** curation, classification, hard/positive review, family splits, task-specific export and dataset UI are completed.

**M15/M16:** short/noisy/context comparisons, a live reviewed evidence pilot and a portable export reconstruction prove readiness.

Collection opt-in, an annotation being correct, a dataset being exportable and consent to a cloud upload are different decisions. An unedited paste is not a verified positive. A name correction does not validate every other word in an utterance. Audio-reviewed verbatim text is separate from intended final writing.

## 6. Important architectural boundaries

The Training Evidence namespace shares local artifacts with history but has distinct leases, eligibility and deletion. Default original-audio history expiry cannot silently destroy a pinned training example; delete-everywhere cannot leave a hidden training copy. Private original speech/context remains local. Sanitize audio and all derived content together or exclude the example from a sanitized export.

Grok is a **Cloud Reference Comparator**, never the oracle or default production backend. Human-reviewed references govern comparisons. Missing credentials, provider outages or declined uploads are valid skips. Language/ITN coupling is explicitly treated as a possible confound; unsupported API modes are not invented. Wispr is a product comparator, not an assumed public raw-Canto endpoint.

Historical outputs may support supervised or preference datasets when properly reviewed. They are not automatically on-policy GRPO/PPO rollouts. Future online optimization will generate new candidates from the trainable policy and use qualified rewards. No weight training, automatic model promotion, cloud compute rental or guaranteed improvement is part of V2 acceptance.

## 7. Evidence and source boundaries

The original measured baseline and pinned source audit are preserved, not rerun or recast as new findings. New vendor/framework facts were checked against primary sources and are indexed [A01]–[A13] in the Spec and Evaluation files. Actual runtime compatibility, human references and performance must be measured in the build.

Input identity for this amendment:

| Canonical source | SHA-256 of supplied v1.0 Markdown |
|---|---|
| `LOCALFLOW_V2_SPEC.md` | `f9046e9cae166be2545f9bde7f598e39e5e8a57318f871a6cc82911207a017f4` |
| `LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md` | `99cfa2f8c686da1cac5bc2049bcff0a14734f1f61db9d1da0d720100e56fb830` |
| `LOCALFLOW_V2_MILESTONES.md` | `bd26157459d82b8750679e8e35f52bfd10721216eea2b07497291ee1009bdbe4` |

The screenshot's ten-file structure is retained. Supporting JSON/CSV are byte-identical to the previous ZIP; all three Markdown files, all three Word editions, README and the checksum manifest are refreshed. Rendering/integrity QA of this package does not constitute product tests.

## 8. Scope and completion

This is a material but bounded scope increase: collection/provenance, review and export require real engineering. Keeping 16 milestone numbers does not mean the work is unchanged. Do not invent a percentage/time estimate before inspecting the current implementation. Use M14 checkpoints and the existing fresh-session protocol to contain session size.

V2 completion requires working local training-data infrastructure, trustworthy actual label coverage and a reconstructable export—not a dataset of arbitrary size, a trained personalized model or a favorable cloud comparison. Preserve the full local dictation experience throughout the build.
