# LocalFlow V2 — Implementation & Evaluation Plan

**Document:** `LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`  
**Version:** 1.1 · 21 September 2026  
**Authority:** Evaluation companion to `LOCALFLOW_V2_SPEC.md`; execution is divided by `LOCALFLOW_V2_MILESTONES.md`.  
**Status:** Measured historical baseline plus proposed implementation/acceptance protocol. No V2 code or real-model Mac benchmark was executed for this report.

**Amendment:** v1.1 adds training-data validation, pre-decode hints and optional external comparisons. Historical E02 measurements are unchanged; new suites and dataset counts are future build obligations, not completed tests.

## Navigation

- [E01. What this plan must establish](#e01)
- [E02. Evidence inventory, provenance and measured baseline](#e02)
- [E03. Failure taxonomy and prioritization](#e03)
- [E04. Corpus design and labeling](#e04)
- [E05. Seed acceptance cases](#e05)
- [E06. Metric definitions and honest interpretation](#e06)
- [E07. Model and prompt experiments](#e07)
- [E08. Validation suite catalog and traceability](#e08)
- [E09. Deterministic and semantic test design](#e09)
- [E10. Context and target integration protocol](#e10)
- [E11. Performance harness](#e11)
- [E12. Logging acceptance and regression cases](#e12)
- [E13. Analytics, learning and profile validation](#e13)
- [E14. Human evaluation on the Mac](#e14)
- [E15. Quality gates and fallback promotion](#e15)
- [E16. Migration, rollout, rollback and final release](#e16)
- [E17. Decision record and limitations](#e17)
- [E18. Comparator, hint and acoustic challenge protocol](#e18)
- [E19. Training evidence, curation and export validation](#e19)
- [E20. Post-V2 optimization and amendment scope](#e20)

- [Sources](#sources)

<a id="e01"></a>
## E01. What this plan must establish

The build must show that V2 produces more usable text without silently changing Daniel's intent, retains the speed of short dictation, recovers from local inference faults, preserves existing analytics/settings, and provides the full local desktop experience. A bigger model, prettier Hub or lower benchmark WER alone does not establish those outcomes.

It must also capture trustworthy training evidence early, preserve independent retention/label semantics and export valid task-specific datasets without requiring model training. Optional live comparator access is never a release prerequisite.

Implementation principles: preserve working behavior; distinguish a recorded failure from a inferred cause; keep original artifacts; test deterministic logic separately from models; measure the actual paste destination; label missing evidence; and compare versions on the same inputs. The source snapshot is `7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9`. Unknown installed-source differences are resolved in M01, not erased by migration. [R01]

All named `tests/v2/`, `scripts/v2/`, `localflow/v2/` and `docs/v2/` paths below are **planned delivery contracts**. Their commands become usable only when their owning milestone creates them. Existing tests remain runnable through their current entry points; they must not be represented as already passing in this audit.

<a id="e02"></a>
## E02. Evidence inventory, provenance and measured baseline

### Uploaded inputs

| Source | Size / contents | SHA-256 |
|---|---|---|
| `LocalFlow.log` | 544,221 bytes; 3,496 newline-normalized `splitlines()` lines | `51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0` |
| `stats.db` | 20,480 bytes; 7 dictation rows | `e4005289c7b9468e27db39be28e35df16fd4076c81692e13e0b086896489cb25` |
| `dictionary.json` | 122 bytes; 7 terms | `56f2fcd135e362d4e703975f0e5d9151e624aa7899616a38c4926308940ef547` |
| `transforms.json` | 737 bytes; 2 definitions | `e7eb86b16a9f31d24fa3c46efca5975ff99d76508524e68b400ad8ae18baee89` |

The log was parsed programmatically in the analysis environment. SQLite was opened read-only and its integrity check returned `ok`. All WAV headers and sample arrays were inspected. The original inputs were not edited. This evaluation does not include recorded listening judgments, gold transcripts, true WER, actual user-edit ground truth, GPU benchmarks or UI trials on Daniel's Mac.

### Parsing protocol

Recognize the exact runtime prefix and support a prefix embedded after a download-progress fragment. Treat continuation lines as part of a multiline raw/cleaned payload until the next record. Preserve physical line offsets. Partition launch cohorts at explicit readiness messages; mark cleanup state only after a success/unavailable message in that cohort. Pair raw→cleaned→timing→posted-insertion within the sequential processing stream; reset at terminal events and restarts. Record ambiguous audio associations separately because captures can overlap queued processing.

Do not search transcript text for “failed” and call that a runtime failure. The file contains many dictated bug reports about unrelated applications. Do not date a record from phrases such as “today” or “September eighteenth” inside its transcript. A filename timestamp is a filename claim with unspecified timezone, not a reliable universal join key.

### Aggregate findings and denominators

| Measurement | Result | Interpretation |
|---|---:|---|
| Complete raw/cleaned pairs | 749 | Candidate text corpus, not gold labels |
| Pairs after explicit cleanup-loaded message | 476 | Runtime-log cohort; model revision not recorded |
| Pairs after explicit cleanup-unavailable message | 272 | Historical degraded cohort |
| Pairs with unknown readiness | 1 | Final startup/download overlap |
| Timed nonempty pairs | 477 | Includes one 0.0-second cleanup case |
| Explicit cleanup-load failure messages | 21 | Historical startup failures, not 21 current 4B quality failures |
| Explicit cleanup-load success messages | 27 | Starts/restarts, not unique model versions |
| Sanity fallback messages | 9 | Message count; a multi-piece job can emit more than one |
| Explicit inference failures | 3 | All mention Metal shared-event creation |
| Empty-transcription messages | 29 | Includes those three failures; silence is not established |
| Capture diagnostics | 498 | One unresolved capture association exists |
| Reported positive overflow counts | 0 / 498 | Only the recorded callback diagnostic |
| Loaded-cohort changed outputs | 257 / 476 | Any change, not necessarily an error |
| Loaded-cohort lexical changes | 108 / 476 | Case/punctuation-insensitive comparison |
| Loaded-cohort added sentence boundaries | 133 / 476 | Formatting triage proxy, not a grammar verdict |

Across the timed cohort, summed ASR and cleanup durations are 176.6 and 629.6 seconds, respectively. Cleanup is approximately 78.1% of that total. Latency by length is shown in Spec S03; report P95 about 4.4 seconds overall rather than implying millisecond precision from tenths-of-a-second logs.

Four strong text-only regression examples need no audio ground truth to establish that cleanup removed supplied content: deletion of `DOM` from `React DOM`; removal of a direct request to write a reply; deletion of “user” in “sole user”; and the editor acting on “Remove the adjective small…” instead of preserving that dictated instruction. [D01, lines 1540–1544, 1790–1794, 1330–1332, 1690–1694] A plausible recovery, `bar graft`→`bar graph`, is supported by context but is not an acoustically verified recovery-rate measurement.

### SQLite slice

The schema includes `id`, Unix `ts`, capture duration, raw/cleaned text, raw/cleaned words, `fixed_words`, WPM, app name/bundle and kind. The seven records total 280 raw words, 277 cleaned words, 350.3 seconds and 11 legacy fixed words. All name Terminal. Their timestamps decode to 4 July 2026, 21:15:42–21:38:40 UTC. None exactly matches a raw transcript in the uploaded log. [D02]

The observed WPM formula matches `60 × cleaned_words / duration_sec`; its aggregate for this slice is approximately 47.45 WPM. This measures text per capture minute including pauses, not true articulated speech rate. Preserve the seven rows and the original fixed-word field; do not infer word-error improvement from it. A complete live-database export should use a consistent SQLite snapshot before any later analysis. [T01]

### Audio inspection

| WAV filename | Duration | Peak dBFS | RMS dBFS | Result |
|---|---:|---:|---:|---|
| `dictation-20260920-001203-161.wav` | 66.00 s | -15.61 | -37.62 | Readable mono PCM16 |
| `dictation-20260920-001210-162.wav` | 1.20 s | -18.88 | -38.90 | Readable mono PCM16 |
| `dictation-20260920-044231-163.wav` | 64.60 s | -17.38 | -36.95 | Readable mono PCM16 |
| `dictation-20260920-044418-001.wav` | 1.35 s | -16.32 | -36.63 | Readable mono PCM16 |
| `dictation-20260921-003900-001.wav` | 57.55 s | -17.25 | -45.31 | Readable mono PCM16 |

All five are 16 kHz and contain no samples at or above the chosen full-scale clipping threshold `abs(sample/32768) >= 0.999`. This rules out that particular clipping signal in these files; it says nothing conclusive about intelligibility, channel contamination, earlier truncation or ASR accuracy. The 66.0/1.2/64.6 durations align with the final sequence of failed attempts, but no shared job/audio ID proves that mapping. Treat it as a candidate association requiring confirmation, never as a labeled transcript.

<a id="e03"></a>
## E03. Failure taxonomy and prioritization

| Code | Stage | Evidence / current uncertainty | Test and priority |
|---|---|---|---|
| CAP-01 | Capture | Low amplitude or device-loss warnings; current gate is heuristic | Quiet speech, device-switch and callback-jitter trials; high |
| CAP-02 | Capture/ASR | Unrelated commentary embedded in raw text | Labeled overlap/noise recordings; do not hallucinate missing words; high |
| ASR-01 | ASR | Claude-like forms and technical names already wrong in raw text | Named-entity audio references + scoped vocabulary; high |
| ASR-02 | Runtime | Three Metal shared-event failures | Fault injection, fresh worker, retained audio; critical |
| CLEAN-01 | Cleanup | Direct instruction/question deletion | Exact request and clause coverage; critical |
| CLEAN-02 | Cleanup | Dictated request is acted upon | Instruction-as-data fixtures; critical |
| CLEAN-03 | Cleanup | Synonym substitution, hedges/asides lost | Faithful vs rewrite-mode tests; high |
| STRUCT-01 | Formatting | New fragment boundaries in long prompts | Block-aware chunking and seam tests; high |
| NORM-01 | Representation | Written-out numbers persist; tests allow them | Typed numeric exact-match; high |
| NORM-02 | Representation | Slash words not rendered as syntax | Registry/literal-context counterexamples; high |
| VALID-01 | Validation | Count/novelty heuristics miss meaningful edits | Deliberately corrupted candidate-output tests; critical |
| READY-01 | Lifecycle | Cleanup not ready while ASR is used | Readiness race and explicit fallback UI; high |
| INSERT-01 | Insertion | Source risk: frontmost target may change | Target identity/revision races; critical |
| INSERT-02 | Clipboard | Source risk: delayed restore overwrites new copy | Ownership and multi-format tests; critical |
| DATA-01 | Persistence | Database/JSON evidence exceeds Git snapshot | Non-destructive provenance and migration; critical |
| OBS-01 | Logging | No event dates/IDs; progress text interleaves | Dated JSONL and correlation under concurrency; high |
| PROFILE-01 | Analytics | Legacy fixed words not validated corrections | Formula reconciliation, honest labels; high |

Priority is based on severity, frequency evidence and prerequisites—not a fabricated percentage of daily frustration. The earliest milestones establish the baseline and durable data, then recovery, normalization/vocabulary/context, and faithful cleanup. Hub/insights must not obscure unresolved critical corruption.

<a id="e04"></a>
## E04. Corpus design and labeling

Create `tests/v2/fixtures/` for sanitized synthetic fixtures and keep private real audio/text outside Git under the local evaluation-data root. A manifest contains opaque case IDs, hashes, consent/retention state and relative artifact IDs. Diagnostic exports never include raw private data by default.

### Required initial corpus

| Set | Minimum size | Purpose |
|---|---:|---|
| Curated deterministic/semantic fixtures | 320 | 80 numbers/units/dates; 60 syntax/paths/skills; 40 vocabulary; 60 fidelity; 40 structure; 20 multilingual; 20 literal/quoted commands |
| Adjudicated real text cases | 60 | Stratified from 749 candidates: 30 development, 10 validation, 20 held-out |
| Diverse real audio clips with verbatim references | 80 | Supplied five plus new reviewed recordings; at least 10 quiet, 10 noise/overlap, 10 EN/ES or code-switching, 10 technical-name cases; E18 expands acoustic tags. |
| Additional short speech clips | 60 | Distinct from the original 80; 30 with 1–2 spoken words and 30 with 3–5; exact intended-token and false-substitution metrics. |
| Silence/background-only negative clips | 20 | Separate from 140 speech clips; hallucinated output/false-command measures, no zero-denominator WER. |
| Training-evidence fixture pack | 100 | Synthetic provenance/label/retention/split cases, plus 40 critical attribution/pairing counterexamples; E19. |
| Prompt Engineer cases | 30 | 15 development, 5 validation, 10 held-out; enumerate all requirement atoms |
| Context/target integration scenarios | 32 | Minimum four for each of eight destination classes |
| Fault/concurrency scenarios | 24 | Startup, worker restart, cancellation, clipboard, disk, sleep and import |

These are **required future fixtures**, not a claim this audit generated 320 gold examples. Audio categories may overlap; record exact memberships. If an attached clip is unusable or has no trustworthy reference, retain its status and add a substitute rather than inventing a label. Keep near-duplicate recordings and repeated phrases within the same train/validation/test partition to prevent leakage.

Record distinct **verbatim references**, **intended final-text references**, **span-only/weak references** and **preferences** as appropriate. For fully reviewed audio, retain both a verbatim reference and an intended final-text reference. The first is used for ASR WER; the second captures authorized punctuation, numeral rendering and self-correction. Raw Parakeet output is not gold speech text. Cleaned Qwen output is not the user's intended reference merely because it was pasted.

A human reviewer marks spans for names, numbers/units, negation scope, requests, constraints, conditional clauses, uncertainty, literal text and structure. Disputed cases are labeled ambiguous with permitted outputs. A reference must never be retroactively changed simply to make a model pass. Record reference version and reason for changes.

### Case record contract

```json
{
  "case_id": "LF-NUM-001",
  "origin": "synthetic",
  "split": "train",
  "tags": ["regression"],
  "family_id": "LF-FAMILY-NUM-001",
  "input_text": "set the timeout to thirty seconds",
  "context": {"profile":"coding","locale":"en-US"},
  "expected_text": "Set the timeout to 30 seconds.",
  "protected_values": [{"type":"duration","value":"30","unit":"s"}],
  "forbidden_outputs": ["Set the timeout to 300 seconds."],
  "requirement_ids": ["LF-R06","LF-R11"],
  "reference_status": "reviewed",
  "audio_artifact_id": null
}
```

Do not make all tests exact whole-string equality. Use exact matching for commands/values/identifiers; document-tree equivalence for lists; and reviewed permissible alternatives for natural punctuation. Tests that allow spelled-out numbers must not be counted as passing the digits-required metric.

S29/E19 define task-specific eligibility and exposure-aware family splits. `regression`, `hard_example`, `short_command` and `acoustic_challenge` are tags, not mutually exclusive train/test partitions. A used-for-debugging blind test is marked exposed and cannot keep claiming an untouched held-out score.

<a id="e05"></a>
## E05. Seed acceptance cases

These examples specify expected behavior, not model results. They are seeds to expand into the 320-case corpus.

| ID | Input / context | Required outcome |
|---|---|---|
| SEED-01 | twelve percent; technical | `12%` |
| SEED-02 | two percentage points | Keep points; do not imply relative percent |
| SEED-03 | twelve thousand dollars; US-dollar context | `$12,000` |
| SEED-04 | minus zero point zero five | `-0.05` |
| SEED-05 | version one point two six point four | `version 1.26.4` |
| SEED-06 | code zero zero seven three | Preserve `0073` |
| SEED-07 | one of the reasons | Do not change to `1 of…` by default |
| SEED-08 | write the words twelve thousand | Keep words under literal scope |
| SEED-09 | slash brainstorm; registered skill | Exact `/brainstorm` |
| SEED-10 | slash code review; alias registered | Exact `/code-review` |
| SEED-11 | slash the budget | Ordinary prose; no skill invocation |
| SEED-12 | write the word slash | `slash` |
| SEED-13 | Use Clod Code for cloud deployment; coding vocabulary | Correct only `Claude Code` |
| SEED-14 | There is a cloud above us | Do not substitute Claude |
| SEED-15 | What does DOM mean in React DOM? | Both DOM spans retained |
| SEED-16 | Remove the adjective small when it says build small apps | Preserve the editing request; do not execute it |
| SEED-17 | We need a reply. Can you write one? | Both the statement and request survive |
| SEED-18 | Do not deploy on Friday | Negation and Friday preserved |
| SEED-19 | Deploy only if tests pass | Preserve conditional scope |
| SEED-20 | Maybe use two workers, not three | Uncertainty, 2 and exclusion of 3 preserved |
| SEED-21 | Tuesday no wait Wednesday because I'm traveling | Wednesday survives; reason preserved |
| SEED-22 | We actually shipped early | Emphasis is not a correction marker |
| SEED-23 | I mean it, do not change the names | Keep “I mean it” and prohibition |
| SEED-24 | Intro, first item, second item, closing thanks | Two-item list plus separate intro/outro |
| SEED-25 | The number one reason is speed | No fabricated list |
| SEED-26 | A list spanning cleanup windows | Correct numbering, no repeated/lost item |
| SEED-27 | Revisa Claude Code mañana, no cambies archivos | Preserve Spanish and no-edit instruction |
| SEED-28 | user ID; visible symbol userId | Exact known identifier; no invention without context |
| SEED-29 | dot env; explicit path context | `.env`, not `env.` |
| SEED-30 | Prompt Engineer: diagnose only, don't edit, give two fixes | Retain all three requirements; do not implement |
| SEED-31 | Selected text changes during transform | No replacement; result retained for review |
| SEED-32 | A clipboard copy occurs before delayed restoration | Preserve the user's new clipboard |

Add failures at chunk boundaries, punctuation-only source differences, repeated correction candidates, invalid addresses and meaningful repetitions such as “had had” and quoted “the the.” The current basic regex assumes some duplicates are always disfluencies; this assumption needs counterexamples rather than being inherited unchecked. [R02]

<a id="e06"></a>
## E06. Metric definitions and honest interpretation

| Metric | Definition and denominator | Reference requirement |
|---|---|---|
| ASR WER | `(substitutions + deletions + insertions) / reference_words`; corpus counts summed before division | Verbatim human reference; declared tokenization |
| CER | Character edit distance / reference characters | Declared Unicode/case/spacing rules |
| Named-entity accuracy | Correct canonical entity mentions / labeled entity mentions | Exact names with scope/case policy |
| Numeric fidelity | Correct typed values, signs and units / labeled numeric spans | Parsed-value comparison |
| Numeric representation | Correct requested written forms / digits-required spans | Exact display expectations |
| Technical-token accuracy | Exact versions, paths, flags, identifiers / labeled technical spans | Case-sensitive when appropriate |
| Slash-command accuracy | Correct token on registered command cases / command cases | Separate false-trigger rate on non-command cases |
| Semantic preservation | Human-reviewed outputs retaining all critical meaning / reviewed outputs | Not inferred solely from embedding similarity |
| Cleanup regression | Introduced substantive error / cases where source was correct for that labeled aspect | Adjudicated source/output comparison |
| Cleanup recovery | Corrected source error / labeled source-error opportunities | Gold intended content |
| Formatting accuracy | Valid paragraph/list/document structure / structure cases | Structure reference, not word substring presence |
| Correction resolution | Correct replacement with surrounding content preserved / labeled self-corrections | Correction-span annotation |
| Hallucination / deletion | Unauthorized content additions/deletions per reviewed case and per affected span | Manual/adjudicated labels |
| Observed user edits | Edit distance from inserted text to observed final field text | Reliable target-bound observation; report coverage |
| Model edit rate | Fraction of source→output differences | No implied correctness |
| End-to-end latency | Parent monotonic PTT-release to target-confirmed visible text | Instrumented target; separate unknown outcomes |
| Fallback rate | Jobs using a fallback / jobs requesting the relevant stage | Job outcomes, not warning-message count |
| Insertion success | Confirmed accepted insertion / attempted insertions | Report posted-unverified separately |

WER can exceed 100% with enough insertions and does not weight dangerous words more heavily. Do not compare Parakeet's published benchmark WER with a vendor number from a different corpus and infer a personal-use accuracy ranking. [M01]

Quantiles must show cohort size, censoring/failure count, context/mode and build. Failed or timed-out jobs must not vanish from the report and make a slower model look fast. Report successful-call latency plus timeout/failure rate; retain the observed timeout duration. Bootstrap intervals should resample by utterance/session rather than treating correlated repeated runs as independent people.

Add S29/E19 dataset-readiness metrics and E18 exact short-utterance/distractor metrics. `no_edit_observed`, `posted_unverified`, partial reference and explicit correctness are distinct outcomes. Score a whole product and a raw recognizer separately; document any provider formatting that cannot be disabled.

<a id="e07"></a>
## E07. Model and prompt experiments

### Controlled experiment ladder

Run A: the installed V1 baseline, with its exact environment and configuration captured. Run B: the same models with V2 normalization/context/cleanup contracts. Run C: one ASR challenger with cleanup held constant. Run D: one cleanup challenger with fixed text inputs. Run E: richer transform engine on explicit transform cases only. This isolates whether a gain came from recognition, representation, context, prompting or model selection.

Freeze a development corpus, validation corpus and held-out set before prompt tuning. Evaluate a simple prompt, revised faithful prompt, protected-span prompt, and full contextual prompt. Ablate chunking independently from normalization. The public model card's general reasoning score is not a substitute for this comparison.

The initial ASR control is Parakeet v3. Qwen3-ASR-1.7B via MLX Audio is an eligible challenger, not a replacement decided in advance. The initial cleanup control is confirmed Qwen3-4B-Instruct-2507 4-bit. Qwen3.5-4B and 9B MLX conversions are candidates for cleanup and richer transformations, respectively. Their documented loader path differs from the current one; compatibility must be established first. [M01–M07]

### Runtime qualification before quality scoring

For every candidate, record model and tokenizer commit, file hashes, quantization/group size, declared license, loader package/version, Python version, MLX runtime, macOS build, machine chip/RAM and exact inference parameters. Run a packaged-app load, an offline cold load, an English/Spanish input, a long input and repeated inference.

The Qwen3-ASR developer issue about empty/NaN/very short inputs is a test source, not a confirmed defect in whatever revision the agent installs. Verify behavior on the pinned candidate revision. [M08] Empty and non-finite arrays must be rejected by the adapter before inference. Silence must not become a fake command. A padded 10 ms input must not be logged as one second of actual speech.

Use the existing no-thinking setting for the baseline. For Qwen3.5, explicitly configure and verify its thinking/template behavior; do not merely strip visible `<think>` text and assume no reasoning cost occurred. Record effective sampling values; compare a deterministic control against the vendor-supported decoding option when necessary. [R02, M03–M05]

### Model promotion rule

A candidate must pass all critical deterministic/integration requirements, introduce zero critical semantic errors on the frozen acceptance set, and either materially reduce manual correction effort or meet a predeclared latency/resource improvement without degrading quality. Proposed “material” quality improvement is at least 20% relative reduction in adjudicated noncritical defect rate when the denominator is sufficient; report confidence intervals and raw counts. If the small held-out sample is inconclusive, retain the existing default and collect more evidence. Do not promote on a one-utterance anecdote.

No numeric improvement can compensate for a new dropped prohibition or changed amount. A transform engine can be promoted separately from the fast cleanup engine. Model selection and feature rollout must remain reversible via a manifest revision and preserved V1 path.

E18 extends this experiment ladder with capability-qualified hints and an optional Grok/Wispr comparator. E19 validates training evidence and exports; E20 specifies how future personalized candidates re-enter these gates. No public benchmark number or external output becomes ground truth automatically.

<a id="e08"></a>
## E08. Validation suite catalog and traceability

| Suite | Required coverage | Requirements |
|---|---|---|
| EV-01 Baseline/provenance | Installed vs repository/config/data inventory; no overwrite; corpus hashes | LF-R01, LF-R28 |
| EV-02 Logging/time | UTC/local fields, sequence, clock jumps, DST, rotation, redaction, download interleaving | LF-R02 |
| EV-03 Storage/migration | All legacy rows/terms/transforms preserved; idempotent import; rollback; interrupted migration | LF-R03, LF-R20, LF-R25 |
| EV-04 Capture/lifecycle | Fn/watchdog compatibility, silence, mic switch, crash journal, cancel and wake | LF-R04, LF-R27 |
| EV-05 Worker recovery | Model-ready races, Metal fault injection, restart generation, no duplicate insertion | LF-R05 |
| EV-06 Normalization | Values/forms, literal escapes, syntax, registered skills and negative controls | LF-R06, LF-R07 |
| EV-07 Vocabulary | Scoped/longest-boundary matching, collisions, dictionary import, no cloud→Claude overreach | LF-R08 |
| EV-08 Context | Field/app/site snapshots, timeout, sensitive fields, stale context, hostile surrounding text | LF-R09 |
| EV-09 Cleanup/fidelity | Corrections, complete requests, semantic spans, list/chunk structure and fallback lineage | LF-R10, LF-R11 |
| EV-10 Insertion | Target races, clipboard ownership/formats, partial paste, retry/undo, unknown terminal | LF-R12 |
| EV-11 Hub/history | Search/replay/diff/retry, keyboard/accessibility, window/focus, retained settings | LF-R13 |
| EV-12 Profiles/developer | Mode precedence, snippets, file tags, CLI syntax, per-surface compatibility | LF-R14, LF-R15, LF-R16 |
| EV-13 Transforms | Selected text, prompt atoms, samples, auto-apply, literal references, diff and undo | LF-R17, LF-R18 |
| EV-14 Scratchpad | Autosave, versions, local attachments, search/export, restore | LF-R19 |
| EV-15 Analytics/profile | Formula reconciliation, dedup, dates, deletion, suggestions, evidence-linked profile | LF-R20, LF-R21, LF-R22 |
| EV-16 Models/performance | Loader/offline compatibility, corpus comparison, release-to-insert timing, memory | LF-R23, LF-R24 |
| EV-17 Release/offline | No-network acceptance, permissions/build identity, upgrade/rollback, soak and sign-off | LF-R25, LF-R26, LF-R27, LF-R28 |
| EV-18 ASR hints/discrimination | Capability manifests; offered/applied/ignored hints; pre-decode snapshots; true/distractor contexts | LF-R29, LF-R08, LF-R09 |
| EV-19 Training capture/lineage/retention | Live early hooks, exact audio/task joins, original/proposed/applied artifacts, independent leases and deletion | LF-R30, LF-R02, LF-R03, LF-R25 |
| EV-20 Correction/preferences/sampling | Multi-axis labels, partial grafts, same-input pairs, verified positives, hard mining and weak feedback | LF-R31, LF-R22 |
| EV-21 Dataset splits/export | Family grouping, test exposure, task eligibility, portable round trip, hashes, privacy and revocation | LF-R32, LF-R25 |
| EV-22 Comparator/challenge evaluation | Supported provider modes, consent/no-network boundary, short/audio strata, human adjudication and no false raw-ASR claim | LF-R33, LF-R23, LF-R24 |

Every requirement has an owner milestone in Spec S05 and at least one suite above. A suite is a family of tests with fixture IDs, not a single superficial mock assertion. M01 establishes the registry; each milestone adds its own cases and results.

EV-18 is delivered by M03/M05/M06 with M15 acoustic qualification; EV-19 begins in M02 and every producing stage extends it; EV-20 is completed by M14 over M08/M09/M11 observations; EV-21 is built in M14 and round-tripped in M15/M16; EV-22 is owned by M15. M01 registers all 33 requirements and 22 suites. No coverage is inferred from merely naming a suite.

<a id="e09"></a>
## E09. Deterministic and semantic test design

Normalization tests must distinguish display form from numerical value. Test decimals with significant zeros, leading-zero codes, negative amounts, ordinal prose, ambiguous dates, percentage points, units, invalid IP octets, versions with multiple dots, quoted paths and URLs containing punctuation. Use exact comparison for skill tokens and IDs. Test repeated application to ensure idempotence.

Vocabulary tests cover phrase boundaries, capitalization, multiword aliases, overlapping matches, explicit scope precedence, stale workspace context, dictionary disable/undo and conflict with a snippet. Include at least 200 ordinary non-command/ambiguous phrases across the overall corpus and integration extensions before enabling automatic skill/alias interpretation broadly. Report false triggers with exact denominators; zero failures among 200 trials still does not prove zero real-world risk.

Semantic tests deliberately hand the validator damaged outputs: delete “not,” change 30 to 300, move “only if” to the wrong clause, omit a final question, change a file name, invent a test requirement, drop “maybe,” and swap ordered actions. A valid number-word→digit change must pass. Counterexamples must cover correct self-corrections where a previous number/name is intentionally removed; otherwise the validator will reject the feature it is meant to protect.

Do not equate source-word membership with safety. “Do not deploy”→“Deploy” has no novel words but reverses the instruction. Conversely, `thirty`→`30` adds a new written token without changing the amount. The edit ledger must explain the authorized difference. [R02]

Structure tests validate exact list item count, start number, item order, intro/outro placement, nested list scope, code blocks and no mid-word or artificial clause-boundary splitting. Exercise a correction with its old value before a chunk seam and new value after it. Give context overlap read-only status so adjacent chunks cannot duplicate the same sentence.

<a id="e10"></a>
## E10. Context and target integration protocol

Test the same utterance across eight destination classes: personal messaging; Slack/work messaging; Gmail/email; Notes/TextEdit; Claude/ChatGPT web prompt field; Claude Code/Codex terminal prompt; Cursor/VS Code; Xcode. Record application and surface versions rather than assuming all text fields behave alike.

For each class, test empty field, mid-sentence continuation, selected text replacement and target change during inference. Add secure-field and unavailable-Accessibility variants. Test a placeholder that contains a brand name, a field containing prompt-injection text, an unrelated browser tab and a browser with inaccessible site identity.

Use an instrumented fixture app for exact target readback and reproducible races. For external applications without reliable readback, label results `posted_unverified` and include human verification. Do not fake confirmation by reading LocalFlow's own clipboard. A target switch must leave the output available in History without inserting into the newly focused field.

Clipboard trials include plain text, rich text, images, file promises, a user copy during delay, two consecutive dictations, cancelled transforms and failed paste. Never clear a user's new clipboard while restoring an old value. When complete format preservation is unsupported, state it and use a safe alternative.

Terminal trials include bracketed paste, multiline input, a shell without verified paste protection, a CLI that collapses pasted text and a cursor moved during insertion. Literal preservation takes precedence over avoiding a collapsed visual representation. Do not generate keystrokes or newlines that execute partial commands to mimic a vendor's UX.

<a id="e11"></a>
## E11. Performance harness

Create a local benchmark driver with reproducible input manifests and JSON/CSV reports. Measure startup, model load/warmup, capture dispatch, ASR, normalization, cleanup, validation, optional transform, queue wait, target verification and actual insertion. The parent monotonic timer measures end-to-end elapsed time; wall-clock timestamps are for chronology only.

For warm latency, use at least 30 unique representative cases per length band with five repeated runs each after warmup. Randomize order and report per-case summaries to avoid inflated independence. For cold startup, use at least ten new processes with already downloaded models; distinguish page-cache-warm from reboot-cold conditions. Do not time a network download as model inference.

Measure memory with an appropriate macOS process/GPU memory instrument and record its definition. Report parent, worker, peak/steady state, cache size, swap pressure and competing workloads. File size is not resident memory. A claimed “8 GiB budget passed” requires a measurement, not parameter count multiplied by quantization bits.

Run at least four conditions: AC idle, battery idle, browser/development workload, and competing local inference. The published acceptance target applies to the stated reference condition; contention results reveal degradation behavior and scheduling fairness. Thermal and power settings go in the report.

Performance gates are Spec S24. If a target is missed, identify the stage, preserve the complete input/output, and compare a fast path, prompt-prefix caching, smaller relevant context, better chunk scheduling or a qualified model. Never meet a speed goal by deleting content, weakening validation or quietly skipping a requested transform.

Measure paired training-collection on/off runs under the same workload, including writer backlog, retention boundaries and export/enrichment contention. S29.16 proposes at most 25 ms incremental P95 release-to-insert cost while all original S24 targets still hold. Explicitly identify paused collection and missing diagnostics instead of meeting latency by silently losing evidence.

### Planned commands and outputs

| Planned entry point | Purpose | Output |
|---|---|---|
| `python -m pytest tests/v2/unit` | Deterministic/pure tests | JUnit + fixture failures |
| `python -m pytest tests/v2/integration` | Storage, worker and target harness | Event traces + outcome report |
| `python scripts/v2/evaluate_text.py --manifest …` | Cleanup/transform comparison | Per-case edits, metrics and prompt hashes |
| `python scripts/v2/evaluate_audio.py --manifest …` | ASR with gold references | WER/CER/entities and segment diagnostics |
| `python scripts/v2/benchmark.py --profile reference` | Latency/memory | JSON/CSV cohort report |
| `python scripts/v2/verify_release.py --manifest …` | Cross-suite release check | Requirement-status matrix |
| `python scripts/v2/export_dataset.py --manifest … --output …` | M14 offline task-view export | Portable graph, task JSONL and hashes |
| `python scripts/v2/validate_dataset.py --path …` | M14/M15 reconstruction and eligibility | Coverage, split and integrity report |
| `python scripts/v2/compare_cloud.py --manifest …` | M15 separately approved comparator run | Dated provider settings, results, cost and skip status |

M01 creates the first test/report scaffolding; later milestones implement the corresponding drivers. The scripts are not included as pre-existing project tools in this specification package.

<a id="e12"></a>
## E12. Logging acceptance and regression cases

Every V2 event must include a parseable UTC date/time, job/stage correlation where applicable and versioned reason codes. Test newlines, Unicode, long transcripts and text containing `[localflow]` so the log parser cannot confuse content with operations. A format validator rejects malformed event envelopes in tests.

Test UTC midnight rotation, DST forward/backward, travel to another timezone, a wall-clock adjustment during inference, a restarted worker, two captures queued before a prior paste, an exception before ASR text exists and a third-party progress bar writing concurrently. Assertions include unique event IDs, increasing parent sequence, nonnegative monotonic durations, exactly one logical terminal job outcome, and no secret/raw-text leakage in default operational export.

Legacy import must keep missing event times unknown. The seven timestamped analytics rows retain their original instants; they are not silently reassigned to September because the report date is September. Imported unknown-date records must not count toward streaks or time-of-day patterns. Test reopening, reimporting the same data, importing an appended log and interrupting the import halfway.

Logging overload tests verify that high-volume debug output can coalesce while critical outcomes persist or produce a clear degraded-state warning. Disk-full tests must preserve available captured blocks and an explicit failure outcome rather than claiming the prompt was inserted. Rotation/deletion never removes a live capture or unresolved failed job simply to satisfy the normal success-history limit.

<a id="e13"></a>
## E13. Analytics, learning and profile validation

Start with the attached seven-row database as a migration fixture, using a sanitized clone for committed tests and retaining the exact private snapshot locally. Reconcile row count, timestamps, 280/277 words, 350.3 capture seconds and legacy fixed-word sum 11 before and after migration. Verify weighted WPM rather than average row WPM.

Synthetic event streams cover retry, reprocess, transform, replay, multiple paste attempts, cancellation, partial failure, unknown insertion outcome, unknown date and deleted content. Exactly one logical dictation contributes to core dictation totals; a transform must not inflate dictated words. Historical analytics must remain available when transcript retention expires, unless the user chose to remove associated usage.

Learning tests separate a correction (“Clod”→“Claude”) from intentional rewriting, pasted replacement text, unrelated later typing and a different target field. Verify proposed scope, duplicate suppression, rejection persistence, approval, rule revision and rollback. Include adverse counterexamples before promoting an alias. A confidence label cannot be numeric unless a calibration method and held-out reliability are provided.

Profile tests verify that each factual observation is derived from eligible input and that each interpretive card cites supporting examples or clearly signals uncertainty. No unseen personality diagnosis, fabricated percentage or claim about all of Daniel's speech is allowed. Exclude flagged background speech/test snippets; deletion invalidates evidence. A profile must not automatically become universal cleanup instructions.

Training evidence is validated by EV-19–EV-21, not inferred from existing analytics passing. Outcome observation must report coverage and uncertainty; a correct usage total does not establish an accurate training label. Training retention deletion/expiry tests are separate from aggregate retention tests.

<a id="e14"></a>
## E14. Human evaluation on the Mac

Use a blind side-by-side comparison where feasible. Randomize output order and hide model identity. Daniel marks which result requires less correction, then flags critical defects separately. A fluent but semantically wrong rewrite loses, even when it reads better.

The minimum manual review covers the 20 held-out real text cases, 10 held-out Prompt Engineer cases, 20 diverse audio cases and the 32 target-context scenarios. Several cases may serve both audio and context categories, but record that overlap. Test at least one interrupted recording, one offline restart, one changed insertion target and one rich-text clipboard cycle.

For each trial, record expected wording or requirement atoms, observed output, manual edits, critical/noncritical defect labels, latency impression, stage evidence and verdict. For perceived speed, record instrumented latency too; “felt faster” is useful feedback, not a replacement for timing.

Human checks that cannot run in an automated environment become an explicit checklist with steps, expected result and required evidence. Mark `implemented_pending_human`, not `passed`. A coding session completes its assigned automation work and handoff rather than idling indefinitely for a playtest; dependent work may continue only where those pending checks are not a prerequisite. Final release requires the human sign-off.

Add the E19 live evidence-review/export pilot and blinded comparator disagreement review when that optional lane runs. Listen before assigning verbatim references; preserve intention-only feedback separately. A partial correction is valuable without certifying the full utterance. Include actual reviewed positives, not just failures.

<a id="e15"></a>
## E15. Quality gates and fallback promotion

| Gate | Required result | Failure treatment |
|---|---|---|
| G01 Preservation | All seven analytics rows, seven terms and two transform definitions migrate losslessly; repeated import adds zero duplicates | Stop destructive migration; preserve backup and report mismatch |
| G02 Core semantics | 100% of labeled critical invariants pass on the frozen acceptance set; zero unauthorized executed/answered dictation requests | Do not promote candidate path |
| G03 Normalization | All curated unambiguous numeric/skill/identifier fixtures pass; ambiguity controls do not trigger destructive conversion | Keep literal path or review instead |
| G04 Structure | All declared list item/order and seam fixtures pass; ≥95% acceptable formatting on adjudicated real held-out cases | Fix policy/chunking; do not loosen content preservation |
| G05 Reliability | All 24 fault/concurrency scenarios pass; failed audio recoverable under enabled retention; no duplicate or wrong-target insertion in tests | Block affected feature promotion |
| G06 Performance | Spec S24 targets on reference conditions; failures/timeouts disclosed | Optimize or record explicit approved target revision |
| G07 Local operation | Dictation, cleanup, transforms, history, profile and search succeed with external network denied after installation | Block “fully local” release claim |
| G08 Product completeness | Required Hub/transform/Scratchpad/analytics workflows pass keyboard, visual and functional checks | Finish missing workflow, not just a placeholder tab |
| G09 Final acceptance | All LF-R01–LF-R33 traced; G01–G08 and G10 pass; critical issues closed; human checks complete | Keep V1 available; no false V2-ready announcement |
| G10 Training readiness | Early collection, exact lineage, qualified annotations/splits and portable offline export pass EV-18–EV-22; comparator status honest | Fix infrastructure or keep checks pending; no trained model or paid comparator required |

These gates establish behavior on a defined sample, not zero risk in all future speech. Formatting ≥95% must be reported with its actual denominator; on a 20-case test this means at least 19 acceptable cases and no critical failures. A null measurement remains unknown and cannot be converted to a pass.

Fallbacks are product behavior and must be evaluated as part of end-to-end output. A candidate that fails half its model calls but falls back safely must report both safe-output quality and its 50% fallback rate. Never claim its model itself achieved the fallback's result.

<a id="e16"></a>
## E16. Migration, rollout, rollback and final release

Freeze a recoverable V1 bundle and consistent data backup before installing V2. Stage changes behind explicit versioned pipeline/profile selection. Run offline replay/shadow comparisons on recorded data before switching normal dictation; shadow work must not paste or double-count usage. Do not continuously run two expensive pipelines during daily use merely to collect comparisons.

Promote deterministic normalization, cleanup, context, transforms and model defaults independently when their gates pass. Rollback changes the selected pipeline/model policy without erasing history. Additive storage migrations must remain readable by the compatibility layer until final acceptance; if a schema cannot be downgraded, restore the consistent backup to a separate data root and clearly distinguish V1/V2 stores.

The final release report lists every requirement, owner milestone, automated result, benchmark result, human status, evidence path and remaining limitation. Include packaging identity, actual deployment revision, active config origin, model hashes, supported application/surface versions and verified OS/hardware. No “all tests passed” statement without commands, dates, exit codes and artifact references.

Perform a 500-job scripted soak using fixture audio/text and a mixed workload, followed by at least three days of ordinary use with no known critical semantic/insertion failures. The soak checks bounded memory growth, restart recovery, exactly-once analytics, no retained cancelled insertion authority, private retention and no microphone active while idle. Three days is a release observation window, not a background task this report has already run.

Final offline acceptance also covers evidence collection, manual review, sampling, split validation and export. A local build must not load a cloud SDK or require credentials merely to open Models → Training Data. The final export pilot tests revocation/deletion and can reconstruct the selected tasks without the LocalFlow database. No future training algorithm or checkpoint is included in V2 release criteria.

<a id="e17"></a>
## E17. Decision record and limitations

The recommended initial model strategy remains Parakeet v3 plus the confirmed Qwen4B, improved through explicit normalization, context and faithful cleanup. Candidate loaders and larger transform models are admitted only through the methodology above. This is an evidence-led recommendation, not a claim the current model is the strongest possible.

Unresolved measurements: reference WER, actual manual-edit rate, true release-to-insert latency, real-model critical-defect rate on a frozen corpus, target-specific insertion confirmation, memory contention and the cause of the Metal fault. The source establishes risky behavior and the log establishes incidents; neither alone establishes a GPU root cause. V2 supplies instrumentation and recovery first, then validates causation where it matters.

The attached operational history is sufficient to prioritize the work and create precise regression obligations. It is not sufficient to claim 70% of all errors are cleanup failures, that a new model is faster on the Mac, or that deleting sports words from a transcript recovers Daniel's actual intended speech.

<a id="e18"></a>
## E18. Comparator, contextual-hint and acoustic challenge protocol

### E18.1. Experiment identity and provider qualification

Extend E07's local ladder with an optional external lane. Human-reviewed references remain authoritative. The comparator may disagree, be unavailable or outperform a local engine; none of those outcomes automatically selects a production provider. Run provider code in the isolated evaluator, never in the dictation service. Mock/recorded-response tests establish adapter behavior only; reports must distinguish those from live paid measurements.

Before any live request, validate an explicit model ID and supported endpoint parameters against current vendor documentation, preview the exact selected audio/context and projected cost, obtain per-run consent, and set bounded retries. Preserve actual response metadata, serialized parameters without secrets, input/output hashes, run time, tariff version and billable duration where exposed. Requested model ID is not necessarily an immutable server snapshot. A missing server revision remains unknown. Unknown or changed model IDs fail clearly rather than silently falling back to a provider default.

The initial named comparator is `grok-voice-transcribe-2.0`. The current streaming interface couples explicit language with ITN, permits up to 100 key terms of at most 50 characters, and has filler, VAD and endpointing controls. [A02] Store the observed API contract. A no-ITN mode is a tested request condition, not a guarantee of untouched lexical decoding; do not infer internal raw tokens from formatted output. Batch and streaming have separately verified schemas and are reported separately.

### E18.2. Requested configurations and what they establish

| Condition | Configuration contract | Interpretation |
|---|---|---|
| L0 | Current Parakeet, no unsupported hints, original decode settings | Local recognition control |
| L1 | L0 plus V2 normalization/cleanup, with frozen policies | End-to-end local writing, not raw ASR |
| LX | One qualified local ASR challenger, same audio and controlled downstream path | Attributable local model comparison |
| G0 | Explicit Grok ID, no key terms, language omitted where valid, fillers retained when supported | Hosted minimally formatted request condition; verify actual output behavior |
| G1 | G0 with explicit correct language, enabling documented ITN behavior | Combined language-hint/representation condition unless independent ITN control is verified |
| G2 | G1 plus the same frozen relevant vocabulary selected before recognition | Measures hint-set effect conditional on the same language/ITN setting |
| W0 | Wispr app, frozen app/profile/dictionary/context, documented replay/capture | Whole-product comparator, not isolated Canto logits or ASR output |

Do not claim G1−G0 isolates ITN if language changes too. G2−G1 isolates the supplied hint set only when all other parameters are held constant. If a mode is unsupported or no exact upload/replay path exists, mark it unavailable and run the remaining valid comparisons. Do not reverse-normalize a cloud answer and call it an authentic raw transcript.

For lexical WER, declare punctuation/case/tokenization and filler policy; retain source strings. Number-normalized WER is a separately named auxiliary metric with a versioned scorer, not a replacement for verbatim WER. Score written forms and parsed values independently. For example, `one point two six` cannot be globally assumed to mean a semantic version rather than decimal `1.26`; use labeled intent/context.

Quality runs receive the same waveform bytes after explicitly documented unavoidable provider-format conversion; keep hashes of original and each derivative. Transport latency trials are separate: batch starts at request submission; streaming plays frames at real-time pace and measures end-of-speech to final result. Do not compare faster-than-real-time file streaming, a first interim token or advertised vendor latency with LocalFlow's release-to-confirmed-insertion metric. Include network, endpointing, failures, retries and cost in cloud reports.

### E18.3. Context discrimination, not unconditional adoption

Use matched hint conditions: none; correct terms only; correct terms plus phonetically similar distractors; distractors only; stale/wrong workspace; unrelated large vocabulary. Freeze selector revisions and lists before observing candidate output. Repeat on local adapters only where actual support is qualified; unsupported adapters should produce an explicit no-hints disposition rather than a fabricated score.

Report correct-context recovery, false contextual substitution and **distractor flip rate**: among baseline-correct labeled target spans, the fraction changed to a supplied incorrect distractor. Also report overall false substitutions, cases already wrong without hints, exact critical identifiers and latency. A model that adopts correct terms more frequently but also substitutes “Claude” for ordinary “cloud” has not unambiguously improved. Minimum controlled text/hint matrix: 40 labeled base utterances × four primary hint conditions, with all variants in the same dataset family. Variant count is not unique-utterance count. At least 20 of those bases should have real referenced audio before drawing an acoustic conclusion.

### E18.4. Short utterances and realistic audio

The final audio corpus is **at least 140 distinct referenced speech clips**: the original 80 diverse clips plus 60 additional short clips. A shared category label can overlap, but one recording cannot count toward both the original-80 and additional-60 quota. Add at least 20 separately labeled silence/non-speech/background-only negative clips; these are not counted in speech WER. Do not increase apparent sample size by counting crops, repeated runs or hint variants as new independent examples.

For the 60 short clips, include 30 with 1–2 spoken words and 30 with 3–5 words under a declared spoken-token policy. Cover registered skills, names/acronyms, dotfiles/paths, model/version identifiers and ordinary ambiguous/literal phrases. Proposed allocation across the 60: 20 skill/syntax, 15 names, 10 version/model tokens, 5 acronyms and 10 non-command/literal controls. Include English/Spanish where meaningful; no forced translation.

| Challenge dimension | Required coverage / recording metadata |
|---|---|
| Device | Built-in Mac mic and the user's actual headset/AirPods path; record actual selected device, rate and route rather than assuming the headphones were the input. |
| Quiet / amplitude / distance | Normal desk, low-volume, whisper and far-field; separate low signal level from low signal-to-noise ratio. |
| Background | Fan/AC, music/TV, competing human speech and traffic/environmental noise; use consented or licensed reproducible sources when staging conditions. |
| Language/content | English, Spanish, code switching, technical terms, ordinary prose and exact commands. |
| Speaking pattern | Fast speech, disfluencies, self-corrections, short commands, long multi-constraint prompts and incomplete/cancelled captures. |

Retain the original 80-clip minimum strata in E04. Within the expanded corpus, obtain at least five reviewed clips in each named quiet/low-volume/whisper/far-field/noise/overlap/switching stratum before reporting its rate, and show the denominator and overlap. These are coverage minima, not statistical power guarantees. Missing equipment or an unverified label is recorded explicitly; do not invent an acoustic condition from amplitude alone or assume the log's `voiced_pct` is ground truth. No recording activity should require unsafe traffic exposure.

Primary short-utterance measures are exact intended-token/command success, entity/technical-token correctness, incorrect-command rendering on negative controls and false contextual substitutions. A slash token is text, not an executed skill. For zero-reference-word negative clips, report hallucinated utterances/characters and false-command outputs rather than dividing WER by zero. For difficult audio, compare paired defects, complete-content retention, false deletions and per-stratum intervals—not just an overall pooled score that hides a rare severe failure.

### E18.5. Disagreement and evidence use

Cloud/local disagreement creates a review candidate. Hide engine identities during human comparison where possible and listen to the audio before assigning verbatim truth. Retain ties, both-wrong and ambiguous results. Never overwrite a human reference or learn an alias based on provider confidence alone. Store original responses, adjudicated reference and the decision separately.

Provider outputs remain evaluation-only unless downstream training use has been verified under the applicable service terms. Human-authored references from the user's own audio remain a separate source; do not launder provider text into “human gold” by changing its label. Evaluation can proceed without cloud credentials through local drivers and contract tests; a live cloud ranking or superiority claim requires live evidence and recorded settings.

<a id="e19"></a>
## E19. Training evidence validation, curation and portable export

### E19.1. Fixture pack and milestones

Add a **100-record synthetic training-evidence fixture pack** with at least: 20 fully reviewed successes; 20 recognition/representation corrections; 20 mixed edits or changed-intent cases; 10 cleanup/transform regressions; 10 uncertain/unobserved outcomes; 10 sensitive/excluded/deleted cases; and 10 crop/retry/duplicate-family cases. These categories define the fixture allocation, not population prevalence. Link generated audio only when explicitly marked synthetic. Add 40 negative counterexamples for wrong-target attribution, unrelated pasted text, no-edit acceptance inference and different-input preference pairing; they may be variants of the pack but retain family IDs.

M02 implements storage/retention fixtures and live early hooks; M03 adds sample-accurate audio; M04–M07 add exact stage inputs/edits; M08 adds outcome observations; M09 makes manual annotation usable; M10–M12 contribute provenance; M14 completes classification/splits/export. M15 uses a private live pilot; M16 demonstrates the export without the running app. Tests must not be postponed wholesale to M14 merely because the eventual training consumer is later.

### E19.2. EV-19 capture, lineage and retention

Test exact job/audio joins across simultaneous capture, FIFO queueing, identical text from distinct jobs, failed inference and worker restart. Verify original samples, explicit dtype/rate, crop offset bounds, overlap ownership, padding exclusion from duration, and source/model-input derivative hashes. An uncertain legacy association stays uncertain. Inject missing artifacts and incomplete tails; exports must fail or downgrade task eligibility, not attach a neighboring clip.

Verify manifests retain exact permitted model inputs, prompt/template content, vocabulary/context snapshot and available tokenizer/runtime/decoder metadata. Hash-only references to deleted context are insufficient for full reconstruction. Unsupported confidence, n-best and token probabilities remain null with reasons. Test omitted fields, stale revisions, overwritten pointers, idempotent retries and a crash between payload creation and record commit. Orphan cleanup must respect all valid retention leases.

Exercise collection off, enable, pause, denied app, secure field, never-store, per-record exclusion, independent history expiry, training retention and soft/hard disk pressure. A 7-day history expiry must preserve a visible 30-day training lease; delete-everywhere must remove both. Revoke consent during export; check worker caches and temporary export files cannot restore the payload. Only content-free metadata can persist as the deletion tombstone. Test removal of audio without text and resulting eligibility downgrades.

### E19.3. EV-20 correction and preference quality

The classifier is an assistive curator. Use the multi-axis labels in S29, and freeze a 60/20/20 development/validation/held-out allocation by fixture family for the 100-record pack where compatible with related variants. Synthetic tests establish mechanics; they do not establish real classification accuracy. Before enabling automatic category suggestions on real usage, review at least 60 real edit observations with explicit intent/audio checks where needed, split 30/10/20 by session/family. Record classes and denominators; rare classes remain unqualified.

Report per-class precision, recall, abstention, confusion between recognition error and changed intent, mixed-edit span precision and coverage. Proposed suggestion gate: at least 95% precision on held-out reviewed recognition-correction suggestions with the exact numerator/denominator shown; zero changed-intent/wrong-target negatives promoted as verified ASR examples in the critical fixture set. If evidence is insufficient, keep suggestions visibly unverified and require explicit review. User-reviewed labels remain possible even when automated suggestions are disabled; never silently relabel an uncertain example to satisfy a quota.

Test a mixed edit that corrects “Cloud”→“Claude” while changing Friday→Monday. Only the acoustically supported name correction belongs in a graft; the date change stays changed intent. Verify that a span graft remains partial/weak, not full-gold. Alignment may support review but cannot overrule clear human evidence or magically verify a homophone. Check character offsets across Unicode combining characters and emoji: declare the offset convention, retain exact strings and test conversion to tokenizer/sample coordinates.

Preference tests require identical conditional input/task hashes or an explicit valid canonical comparison input. Verify ties/neither, randomized display order, manual corrections vs preferences, changed source between retries, a different model with the same input, and fallback output versus the original rejected proposal. Any automatically derived preference stays weak until a trustworthy judgment exists. Model confidence and selection order are not a user preference.

### E19.4. Sampling and readiness metrics

| Metric | Denominator / interpretation |
|---|---|
| Capture completeness | Collected eligible jobs with required field families present or explicit missing reasons / eligible jobs; include paused/dropped collection counts separately. |
| Exact audio-join coverage | Records with verified shared job/artifact linkage / retained audio records; never count proximity matches as exact. |
| Verbatim reference coverage | Audio seconds/spans actually reviewed / retained eligible seconds; one corrected word does not verify the whole utterance. |
| Task eligibility | Eligible ASR, cleanup, transform, preference and calibration records reported separately. |
| Positive/failure balance | Explicitly reviewed outcomes by task; unknown/no-edit outputs form a separate class. |
| Ambiguity/abstention | Uncertain labels or suggestions / reviewed candidates, with stage/class coverage. |
| Diversity | Unique recording families, terms, sessions, devices, language/acoustic tags and durations; state single-speaker scope. |
| Split contamination | Shared families, answer-derived context, inspected test cases and future-derived vocabulary affecting an earlier test. |
| Retention health | Bytes/hours retained, records nearing expiry, excluded/quarantined/deleted, unresolved leases and collection pauses. |
| Comparator coverage | Approved evaluated examples / eligible selected examples, with unavailable conditions and consent declines. |
| Export integrity | Hash/lineage/input-reconstruction failures, excluded-row counts, task eligibility and rights state. |

Test deterministic sampling with fixed policy/seed, enriched hard queues, dedup of repeated triggers, long-vs-short duration reporting and selection probability bookkeeping. A biased review queue cannot estimate overall ASR error rate without an appropriate sampling design. Review quality can improve while the hard-queue error rate rises because mining improved; dashboards must not call that a product regression automatically.

### E19.5. EV-21 split and export qualification

Validate all crops, augmentations, repeated candidate transcripts and related scripted recordings share a family split. Negative fixtures deliberately introduce train/test overlap, context assembled from future corrections, an exposed blind-test example and a stale family assignment. All must be detected before export/promotion. Reopening an inspected test as a regression example changes its exposure status in a new manifest; it does not rewrite the old manifest into claiming an untouched test.

Export twice from identical permitted revisions; compare the nonvolatile content fingerprint, task views and every artifact hash. Then move one export into an empty directory, make the app database unavailable, disable network and reconstruct the selected tasks. No absolute user path, database foreign key without its target payload, credentials or provider session may be needed. Dataset code must not execute untrusted content embedded in a transcript.

Minimum round-trip qualification pack: 25 unique safe cases, including at least 10 audio/reference examples, 10 reviewed cleanup examples and 5 explicit preference pairs. Include at least one short-command, numeric, mixed-edit, English/Spanish, rejected-proposal and audio-deleted text-only case. Categories may overlap where valid; reference quality must be real. Synthetic examples prove mechanics but must remain labeled synthetic. M15 additionally exercises at least 10 live retained jobs, with explicit review establishing whichever task views they genuinely support; a lack of real preference choices is reported, not fabricated.

Negative export tests cover a wrong hash, missing original/crop, changed source prompt, different-task preference, partial graft mislabeled gold, split leakage, secret in audio with redacted text, revoked permission mid-export, disk-full/cancel, unsafe archive paths and unsupported schema. Excluded cases receive content-free reason entries, not leaked transcript excerpts. Successful packaging cannot count as a successful training experiment.

### E19.6. Training readiness gate

V2 must demonstrate capture→stage lineage→real user review→task eligibility→family/split validation→portable export, with deletion and offline tests passing. It need not accumulate hundreds of hours or produce a personalized checkpoint. Quality quantities remain whatever was actually reviewed. Empty/insufficient datasets must still show accurate readiness states and support schema/round-trip tests with clearly labeled fixtures.

The new release gate **G10** requires EV-18–EV-22 contracts, provenance/retention/export tests, a nonfabricated live pilot and a documented comparator status. Live paid comparators are optional; model training is excluded. G09 remains final integration and now requires G10 as well as G01–G08. A pending human reference review stays pending rather than becoming an inferred pass.

<a id="e20"></a>
## E20. Post-V2 optimization evidence and amendment scope

### Future experiment package

A training proposal must name target stage, base checkpoint/license, training runtime/hardware, dataset revision/splits, label coverage, objective and reward provenance, resource estimates, independent holdout and rollback. Start with learning curves over increasing amounts of reviewed data rather than asserting a universal minimum dataset size. Compare a training-free vocabulary/prompt/normalization improvement with supervised adaptation before assuming an RL run is needed.

For future GRPO/PPO-style work, record new rollout group, current/behavior/reference policy identities as required by the algorithm, exact conditional inputs, generation sampling, token/log-probability semantics, reward vector and normalization. Ordinary V2 logs are historical evidence; sampling new policy rollouts is a training-time activity. A reward-model or DPO dataset can use qualified offline preferences, but that does not convert it into an on-policy RL replay buffer. [A08, A09]

The future reward report must distinguish human-reference correctness, deterministic invariant checks, heuristic semantic judgments, weak behavioral feedback and latency. Test reward hacking with no-op copying, shortened outputs, dropped negatives, rewritten quantities, correct-but-unrequested style changes, over-adopted dictionary terms and failures hidden by fallback. Critical fidelity remains a promotion constraint. Report task-specific metrics and uncertainty instead of one attractive weighted reward number.

### Scope boundary

The amendment is materially larger than adding a log field: it adds evidence lifecycle, review, sampling, splits and export. Most work fits existing storage, capture, Hub, learning and evaluation seams. Preserve M01–M16 numbering and dependencies. M02, M08/M09, M14 and M15 receive the largest additions; M14 has three bounded checkpoints within the same milestone so fresh sessions can resume rather than carrying an oversized context. No claim of a precise percentage or calendar estimate is made before agents inspect the current implementation.

Historical baseline aggregates in E02, `EVIDENCE_SUMMARY.json` and `LATENCY_BASELINE.csv` remain unchanged. This amendment performs documentation research and artifact QA, not new model benchmarks, listening-based labels or a rerun of the original source audit. All newly specified fixtures, schemas, UI features and scripts are planned deliverables.

<a id="sources"></a>
## Sources

[D01]–[D05] identify the exact uploads listed in E02 and the audio manifest below. Repository/source references are pinned; external sources were checked on 21 September 2026. Spec S03 preserves the short source examples, and the package includes aggregate evidence JSON without redistributing raw private inputs.

- [R01] Repository tree and source snapshot — https://github.com/scalinity/LocalFlow/tree/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9
- [R02] Cleanup implementation — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/cleanup.py
- [R03] App lifecycle, queue, logging and insertion dispatch — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/app.py
- [R04] Capture and amplitude-based meter diagnostics — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/audio.py
- [R05] Parakeet adapter and overlapping long-audio merge — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/stt.py
- [R06] Configuration precedence — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/config.py
- [R07] Clipboard insertion — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/localflow/inject.py
- [R08] Packaging and launcher — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/scripts/build_app.sh
- [R09] Cleanup meaning-preservation test suite — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/tests/test_cleanup.py
- [R10] Lost-release regression suite — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/tests/test_stuck_overlay.py
- [R11] README and existing workflow — https://github.com/scalinity/LocalFlow/blob/7cdd90486b23a1a86b3da00f9fdee39bfa40a8f9/README.md
- [M01] NVIDIA Parakeet TDT 0.6B v3 model card — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- [M02] Qwen3 4B Instruct 2507 model card — https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- [M03] Qwen3.5 4B model card — https://huggingface.co/Qwen/Qwen3.5-4B
- [M04] Qwen3.5 4B MLX conversion — https://huggingface.co/mlx-community/Qwen3.5-4B-4bit
- [M05] Qwen3.5 9B MLX conversion — https://huggingface.co/mlx-community/Qwen3.5-9B-4bit
- [M06] Qwen3-ASR 1.7B model card — https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- [M07] MLX Audio supported models and adapters — https://github.com/Blaizzy/mlx-audio
- [M08] Developer report: Qwen3-ASR invalid/short/no-speech inputs — https://github.com/Blaizzy/mlx-audio/issues/928
- [T01] SQLite consistent backup guidance — https://www.sqlite.org/backup.html

### Audio integrity manifest

- `dictation-20260920-001203-161.wav` — SHA-256 `95113ce4683313253b7e57e25029665eb3c58b4bfcc49e76cc2d0e93fc36c763`. No gold transcript assigned.
- `dictation-20260920-001210-162.wav` — SHA-256 `a46fda2799e7f5999959b4f8229704dfe0aa2f3bfd3165915574ca4a715e0401`. No gold transcript assigned.
- `dictation-20260920-044231-163.wav` — SHA-256 `b9a7f6701be81418eea637dac213ba5f78a0a0c700e5fb2190ef9ad66bf06205`. No gold transcript assigned.
- `dictation-20260920-044418-001.wav` — SHA-256 `5fdf92991bfecade3c43cb2fb05ed41c1711c5e81b315adfffd7fd9d63872844`. No gold transcript assigned.
- `dictation-20260921-003900-001.wav` — SHA-256 `9c5715cd11d08fb8f0dcb052be6cb9169399ed310c35779f673db52f39159c9a`. No gold transcript assigned.

### v1.1 amendment research (checked 21 September 2026)

These sources support the narrowly stated external facts. LocalFlow schemas, defaults, metrics and acceptance thresholds are design decisions, not vendor results. Source availability does not establish performance on the user's Mac.

- [A01] Wispr AI Lab, Canto: a speech model built for the real world — https://wisprflow.ai/canto . Runtime dictionary hints; SFT/GRPO; correction/context experiments explicitly distinguished from released-model training.
- [A02] xAI Voice REST/streaming reference — https://docs.x.ai/developers/rest-api-reference/inference/voice . Verify endpoint-specific flags, model IDs, language/ITN coupling, key terms and response metadata at integration time.
- [A03] Grok Voice Transcribe 2.0 release — https://x.ai/news/grok-voice-transcribe-2 . Vendor announcement, 18 September 2026; not a LocalFlow benchmark.
- [A04] NVIDIA Parakeet TDT 0.6B v3 model card — https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 . CC-BY-4.0; NeMo/Transformers training examples and documented hardware assumptions.
- [A05] MLX-LM LoRA/QLoRA documentation — https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md . Compatible-model fine-tuning, not universal ASR/GRPO support.
- [A06] Qwen3-ASR official fine-tuning instructions — https://github.com/QwenLM/Qwen3-ASR/blob/main/finetuning/README.md . JSONL audio/text SFT; CUDA-oriented examples.
- [A07] Qwen3-4B-Instruct-2507 model card — https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 . Exact current cleanup base; Apache-2.0.
- [A08] Hugging Face TRL GRPO Trainer — https://huggingface.co/docs/trl/main/en/grpo_trainer . Rollout/reward/policy machinery; documented mismatch concerns. Pin an actual future training release.
- [A09] Hugging Face TRL DPO Trainer — https://huggingface.co/docs/trl/main/en/dpo_trainer . Same-input preference format and training objective.
- [A10] Hugging Face Datasets audio dataset creation — https://huggingface.co/docs/datasets/audio_dataset . Local audio/metadata interoperability.
- [A11] xAI Speech-to-Text guide — https://docs.x.ai/developers/model-capabilities/audio/speech-to-text . Integration behavior; independently verify transport/SDK compatibility.
- [A12] Qwen3-ASR-1.7B model card — https://huggingface.co/Qwen/Qwen3-ASR-1.7B . Apache-2.0 and model information.
- [A13] Qwen3-ASR official repository — https://github.com/QwenLM/Qwen3-ASR . Inference/forced-alignment framework and separate training instructions.
