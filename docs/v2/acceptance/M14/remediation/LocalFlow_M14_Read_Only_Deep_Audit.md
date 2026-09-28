# LocalFlow V2 — M14 Read-Only Deep Audit

**Repository:** `scalinity/LocalFlow`  
**Audited commit:** `1e351d723d11a7bb5cb333c93a5daaca416f93d0`  
**Mode:** read-only static audit; all target execution `NOT_RUN`  
**Date:** 28 September 2026  
**Verdict:** **C — Significant learning/eligibility/curation weaknesses**

## Executive Assessment

M14 is **not ready to advance on the strength of its historical acceptance record**. The current tree contains concrete source-level paths that can accept foreign evidence, destroy an unrelated staging directory, publish a profile after its source artifact is purged, and issue a new frozen-test export from a pre-exposure assignment. These are qualification-boundary defects, not requests for a broad rewrite.

The register contains **36 entries: 4 Critical, 14 High, 8 Medium, 0 Low, 3 Test Gaps and 7 Design Concerns**. “Finding” does not mean “runtime reproduced”: production consequences are source-derived predictions to reproduce locally. Policy disagreements are explicitly separated from implementation defects. No target test, native action, benchmark, model inference, migration or Git mutation was performed.

Important inherited protections remain: pending suggestions do not directly update vocabulary; ordinary label writes recheck restricted states; normal split reassignment preserves exposure; existing destination files have safeguards; audio hashes and export fingerprints are recomputed; selected-input purge before the final export fence aborts while unrelated deletion does not; deletion reaches job-keyed candidates and linked profile snapshots; M13 redacts usage-derived profile copies in the same operation. Those strengths must be preserved rather than “fixed” away.

The repair order is authority and filesystem safety first, then reversible operations and review UX, then shared eligibility/portable lineage, then profiling/retention and independent qualification. M15 and Quiet Editorial remain outside scope.

Evidence: [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py) [splits.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py) [M13.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M13.md).

## Audit Boundary

> This audit covers committed GitHub state at 1e351d723d11a7bb5cb333c93a5daaca416f93d0. Historical M14 acceptance is evidence about an earlier tree, not current qualification. Any uncommitted local state is outside the GPT-6 audit boundary.

The user’s attached 139-section audit brief is the controlling task specification. The connected GitHub repository was used for committed source and documentation. This is an inspection of M14 and its consumption of already-remediated interfaces, not a re-audit of M01–M13.

All corpus entries, stateful probes, metamorphic relations, mutation experiments and finding reproductions remain **NOT_RUN**. Generated-file schema/cross-reference checks are deliverable validation, not execution of LocalFlow. A deterministic interleaving written here is a proposed local witness, not an observed race.

Large connector responses and code-search results were incomplete. Core M14 modules were read in source windows; selected integration paths and tests were read, but a full tracked-file caller inventory and complete native qualification were not established. The ledger below makes the distinction explicit. “Source-supported protection” means inspected code, not a newly passing test. Every local allegation must be independently adjudicated as reproduced, refuted, narrowed, already fixed, test-gap only, design-only or native/manual unresolved.

## Canonical Foundation

Remote `main` resolved to **`1e351d723d11a7bb5cb333c93a5daaca416f93d0`**, identical to the brief’s accepted M13 evidence head. The branch response identified tree `0e1cdd585fbda87f9ff582c553772d2986325945`. Recent ancestry read through the connector included:

```text
1e351d7  M13 evidence/docs head (audited main)
8c5b74b  prior M13 evidence
de7246c  intermediate M13 record
36e03a2  final M13 production
```

The parent chain establishes final M13 production `36e03a2a30e380729ceb56d3f1f41bea751bbb4f` below main. GitHub compare established final M12 production `b17aa2bee82c46ef9f01d680e1b1031629744835` as merge base/ancestor (main ahead 23, behind 0), and M05 campaign head `4adda7ddff8acd2510bb6057c1df4d466d3cbf81` as ancestor (ahead 122, behind 0). An additional M01 comparison returned `3db74061f23001b9cce3d4fe029e0b30cbc295d6` as the merge base. No intervening main commit was identified at baseline resolution.

The accepted campaign lineage is recorded in current orchestration and milestone addenda. Additional bounded GitHub comparisons establish an inherited accepted anchor for **every milestone M01–M13**, directly or transitively. Each comparison below returned `status=ahead`, `behind_by=0`, and a merge base equal to its base commit. This proves graph inheritance, not current qualification of the earlier milestones.

| Milestone | Recorded production/integration anchor | Evidence handling |
|---|---|---|
| M01 | `3db7406` | Current remediation addendum; direct comparison corroborates inheritance. |
| M02 | `bfbc63c` | Graph-confirmed through M03 → M04 → M05 campaign → audited main. |
| M03 | `3e0d1ab` | Graph-confirmed through M04 → M05 campaign → audited main. |
| M04 | `4ef219c` | Graph-confirmed through M05 campaign → audited main. |
| M05 | `01a1f3c`, later campaign/test head `4adda7d` | Direct compare confirms later campaign head inherited. |
| M06 | `4388b52`, integrated review lineage | Graph-confirmed through M11 integration → M08 → M09 → M10 → M12 → audited main. |
| M07 | `52edc47` | Graph-confirmed through M01 remediation → audited main; milestone number is not commit chronology. |
| M08 | `4ea2389` | Graph-confirmed through M09 → M10 → M12 → audited main. |
| M09 | `a304d48` | Graph-confirmed through M10 → M12 → audited main. |
| M10 | `ed5e206` | Graph-confirmed through M12 → audited main. |
| M11 | replay/integration `1545de9`, final `9a049b3` | Final integration anchor graph-confirmed through M08 → M09 → M10 → M12 → audited main. Cloud-only hashes are not required ancestors. |
| M12 | `b17aa2b` | Direct ancestor proof as above. |
| M13 | `36e03a2`, evidence `1e351d7` | Recent parent chain and current main. |

The additional graph-proof edges were:

| Base → descendant | Descendant ahead / behind | Pinned comparison |
|---|---|---|
| `bfbc63c` → `3e0d1ab` | 4 / 0 | [M02 → M03](https://github.com/scalinity/LocalFlow/compare/bfbc63c35efa6273cc13242d54d3e5bbe264b21e...3e0d1ab972b866b4acbda622984bce04e8f95093) |
| `3e0d1ab` → `4ef219c` | 5 / 0 | [M03 → M04](https://github.com/scalinity/LocalFlow/compare/3e0d1ab972b866b4acbda622984bce04e8f95093...4ef219c52598e92a9857e9e0dec13ca7143f56dc) |
| `4ef219c` → `4adda7d` | 7 / 0 | [M04 → M05 campaign](https://github.com/scalinity/LocalFlow/compare/4ef219c52598e92a9857e9e0dec13ca7143f56dc...4adda7ddff8acd2510bb6057c1df4d466d3cbf81) |
| `52edc47` → `3db7406` | 12 / 0 | [M07 → M01 remediation](https://github.com/scalinity/LocalFlow/compare/52edc4753df9be17d9119e95d760c4086c5649cd...3db74061f23001b9cce3d4fe029e0b30cbc295d6) |
| `4388b52` → `9a049b3` | 9 / 0 | [M06 → M11 integration](https://github.com/scalinity/LocalFlow/compare/4388b521cedfebe5a16dc8c485d25275f0b342f0...9a049b341d315201ba7d8019585fd7e71370af31) |
| `9a049b3` → `4ea2389` | 22 / 0 | [M11 integration → M08](https://github.com/scalinity/LocalFlow/compare/9a049b341d315201ba7d8019585fd7e71370af31...4ea2389d4396d2f767a4de9cec16d7d99c38be56) |
| `4ea2389` → `a304d48` | 30 / 0 | [M08 → M09](https://github.com/scalinity/LocalFlow/compare/4ea2389d4396d2f767a4de9cec16d7d99c38be56...a304d48c3adf0ef7639fe66986d8affe41a2264a) |
| `a304d48` → `ed5e206` | 16 / 0 | [M09 → M10](https://github.com/scalinity/LocalFlow/compare/a304d48c3adf0ef7639fe66986d8affe41a2264a...ed5e20631529e063564b151555215485ec316a53) |
| `ed5e206` → `b17aa2b` | 16 / 0 | [M10 → M12](https://github.com/scalinity/LocalFlow/compare/ed5e20631529e063564b151555215485ec316a53...b17aa2bee82c46ef9f01d680e1b1031629744835) |

The local handoff still requires `git merge-base --is-ancestor` against the newly fetched remote to detect drift and records exact full SHAs. M11 cloud hashes `aa03af7`/`1be42ee` must not be falsely called missing accepted history: the addendum says their content was replayed. The comparison proves inheritance of `9a049b3`, not that every historical cloud commit was merged.

Historical M14 production `15984ba3…`, review record `1b1b7d3…`, follow-up `e8c4e73…` and close-out `6593bf3…` were orientation only; none was substituted for the current audit tree. `STATUS.json` and M14 `results.json` retain historical acceptance state rather than proving current qualification.

Sources: [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/ORCHESTRATION.html) [STATUS.json](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/STATUS.json) [M01.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M01.md) [M02.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M02.md) [M03.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M03.md) [M04.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M04.md) [M05.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M05.md) [M09.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M09.md) [M10.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M10.md) [M11.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M11.md) [M12.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M12.md) [M13.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M13.md) [results.json](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/acceptance/M14/results.json).

## Current M14 Architecture

`LearningService` mines certified insertion observations and note revisions, accepts explicit teaches, stores governed candidate payloads and controls approval/rejection/undo through M05 vocabulary. `curation.classify` suggests multi-axis classifications and constructs partial grafts. `ReviewService` combines candidates with sampled examples, appends human labels and delegates preference observations. `SamplingService` selects representative/enriched review items; `SplitService` manages family versions/exposure. The exporter’s actual class is **`DatasetExporter`**, not a presumed `ExportService`. `ProfileService` computes eligible speech summaries and usage-derived fields; the Hub exposes review/profile/export actions. `training_data.py` contains the inherited annotation/retention/readiness consumer interface.

```text
retained job/stage artifacts + certified observations + M12 note spans
                         ↓
     learning candidates / sampled review / explicit human labels
             ↓ approved vocabulary       ↓ qualified tasks
       M05 runtime snapshot         families + exposure + export
                                            ↓
                               offline reconstruction/validation

retained eligible speech + current M13 usage facts
                         ↓
              Your Voice measured snapshot + evidence/cards
                  (no implicit cleanup-prompt authority)
```

The central architecture risk is **duplicated eligibility and authority checks**, not the presence of a single-writer store. A series of individually serialized operations is not one atomic approval; a check before filesystem publication is not a publication fence; a matching artifact ID or task key is not a proof of ownership or retained input.

### Inspection and caller ledger

| Surface | What was inspected | Boundary still requiring local inventory |
|---|---|---|
| Canonical docs | README, START_HERE, STATUS, orchestration lineage, M14/P01–P04 milestones, selected S11/S22/S29 and E13/E14/E19/EV19–21 sections | Not a claim of every prose line being reconciled. |
| Contracts | INDEX; learning, profile, preferences, dataset_exports, training_evidence, references, analytics, scratchpad, vocabulary, store, hub, artifacts, transforms | Resolve explicitly identified canonical/contract conflicts in a decision record. |
| Remediation records | M05/M09/M10/M11/M12/M13 current addenda; M14 handoff/results; selected earlier lineage addenda | Historical execution remains historical. |
| Core M14 source | learning.py, profile.py, curation package/module files, your_voice.py | Core paths reviewed statically; no runtime result. |
| Shared integrations | store deletion/prune/helpers, training_data annotations/pins/readiness, notes provenance, transform preference writer, config defaults, app service wiring and selected coordinator paths, Hub review/export handlers, state model portions | Run full local tracked-file rg; resolve all aliases/dynamic callers, idle tick integration and uninspected portions. |
| Tools | export_dataset.py, validate_dataset.py, benchmark_m14.py | Local CLI subprocess, offline distribution and benchmark qualification. |
| Tests | Selected learning/profile/export and training-review Hub tests, historical suite inventory | Remaining training/personalization suites and complete native matrix must be inventoried/run locally. |

The handoff enumerates all requested service/predicate/table search keys. A zero GitHub search result was never treated as proof that a caller does not exist. Code roots/symbols above are the observed architecture, not a complete call graph. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [splits.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [training_data.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py) [__init__.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/__init__.py) [transforms_store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/transforms_store.py) [config.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/config.py).

## Historical M14 Findings Revisited

| Historical class | Current source assessment |
|---|---|
| H1: deletion missed job/note candidates | Store deletion explicitly reaches job-keyed candidates; M12 propagates note evidence deletion. Preserve this. New approval-phase and derived-artifact races are narrower than “delete is broken.” |
| H2: full observation words in rows; unreviewed permanent pin | Main observation/classification payloads moved into governed artifacts and machine leases are finite. **Residual:** counterexample_json retains full phrases; Unpin does not distinguish all M14 reviewed leases. |
| H3: label restored expired/quarantined state | Current label/annotation writers check restricted states inside the operation. Preserve this; add stale-source and retry identity tests instead of blindly reopening resurrection. |
| Export rmtree existing destination | Destination safeguards exist, but the separate predictable staging directory remains unowned and destructively removed (02). |
| prefer_b serialized A | Current mapping chooses B and tests use distinct outputs. Preserve it; the native comparison’s visibility/identity remains a separate defect (16). |
| Dead action wrapper | Wrapper now handles the real keyword calls. A positive real-wrapper test exists. Not reopened. |
| Exposed family hashes back to frozen | Normal subsequent assignment protects exposure. A NEW export requesting a historical version remains vulnerable (04). |
| Existing dictionary entry approval | Ordinary composition exists. Raw scope equivalence, interleavings and exact undo still need repair (09/10/22). |
| Vacuous scoped counterexample test | Current own-scope positive-control test actually applies the rule. Empty population qualification remains a decision (35). |
| Wrong stage attribution | Envelope-backed ownership/role remains insufficient; no-example job+role fallback is stronger (01). |
| Endless idle profile churn | Fast unchanged gate exists; keep zero-read/zero-write behavior. Secondary signature incompleteness needs targeted test (23). |
| Arbitrary profile citations | Correction-card support is materially improved. Technical-term source/citation semantics still require scrutiny (33). |
| UTC called local | Recorded offset is used and missing remains unknown; preserve M13 behavior. |
| Invalidated snapshot retained words | Deletion clears linked snapshots. Artifact-only purge during/after compute can bypass the example-state fence (03). |
| CLI migration without backup | Backup directory now supplied; explicit --db type remains a separate CLI defect (25). |

These are source assessments, not fresh retest passes. [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py) [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [M14.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M14.md) [test_learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/personalization/test_learning.py) [test_dataset_export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/training/test_dataset_export.py).

## Correction Mining Assessment

M08 mining consumes certified `owned_range_edited` observations and serializes each examined observation, providing a real idempotence foundation. Machine candidates use finite training-buffer leases; explicit Teach receives reviewed retention. Main candidate rows retain offsets/axes rather than whole observations. The source and artifact ownership boundary remains weak (01); multi-operation Teach/approval can use stale authority (09/11); counterexample content escapes the governed payload model (15). Mineability is not ASR truth, and a suggestion is not approval. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py).

## Note / Observation Attribution Assessment

M12’s current `rebase_spans` checks repeated occurrence count and rank and carries producing job identity. M14 instead reruns a word diff over whitespace-normalized revision text. Finding 13’s strongest witness is one dictated correction plus a disconnected typed-only edit: hit_jobs contains A, but all changed regions are minted as A’s candidate. A+B, legacy unattributed, repeated-word, NBSP/newline/emoji and transform-only controls are separate corpus cases. Do not weaken M12’s accepted editor logic to fit the miner. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [notes.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/notes.py) [scratchpad.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/scratchpad.md).

## Classification Assessment

The classifier is a conservative assistive curator, not a human-intent oracle. It has useful number/date, negation, low-overlap and large-rewrite guards. Teach’s earlier unchanged gate drops punctuation-only changes (20). Near-spelling directional antonyms need an independent semantic-negative oracle (21). No synthetic precision/accuracy or production confidence is claimed; the E19.3 real reviewed-observation gate remains unqualified. A classifier “recognition” result must never replace a full audio-reviewed reference. [classify.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/classify.py) [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md).

## Review Label Assessment

Labels are append-only with revision allocation in the writer; restricted-state admission prevents ordinary resurrection. The effective judgment is nevertheless fragmented: queue resolution uses any non-abstained history (19), ASR applies historical blockers, and profile uses its own current label interpretation. Label retries lack stable operation identity (17). The ambiguous/user_rewrite resolution question is explicitly **design concern 30**, not an instruction to erase changed_intent history. [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [learning.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/learning.md).

## ASR Eligibility Assessment

The M14 promotion gate requires a trainable example, listened verbatim annotation, retained audio and no applicable historical blocker. It does not prove that referenced audio belongs to the example’s job or is original_audio; exported reference identity is also insufficiently checked (01). M13 ASR readiness already checks its audio owner/role, but that does not protect the exporter’s distinct gate. Grafts remain insufficient for full ASR. Full-reference review must not be inferred from a text correction or model output. [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [training_data.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py).

## Cleanup / Transform Eligibility Assessment

Cleanup export requires an explicit correct intended-writing outcome and retained source/applied output, not mere lack of editing. Its owner/role and exact-input checks remain weaker than qualification requires. Missing exact model prompts are deliberately allowed with a missing reason in the current lower contract (32); distinguish an incomplete text-pair research view from full model-task reconstruction.

Transform-supervised selection requires an explicit accept, source/output and frozen definition information; automatic application alone is not sufficient. Single-candidate accept→undo/reject meaning needs decision 36, rather than importing pairwise latest-wins by assumption. Task-family partition omission is explicit policy concern 31. [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/dataset_exports.md) [transforms.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/transforms.md).

## Artifact Ownership / Role Assessment

Use a conjunction, never ID existence: **authoritative example/job + latest valid revision + artifact existence + retained payload + expected role/stage + exact task binding + correct digest + current permission**. Store producer checks and `verify()` are useful defense layers but not evidence that an export independently qualifies a corrupted graph. Probe each stage with a distinct foreign canary; a shared string can hide a cross-job read. Finding 01 groups the root cause, while the corpus separates each consumer so one fixed gate cannot mask another. [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [training_data.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py).

## Graft Assessment

The existing graft implementation validates spans and keeps weak/partial quality distinct from full ASR. Preserve code-point offsets and coverage semantics. Missing expected source artifact/hash at Save remains an authority defect (12); latest-nonnull graft selection and its exported source closure also need explicit current decision/source proof. One corrected span, multiple/overlapping/adjacent spans, malformed primitives, changed source and Unicode boundaries all have independent cases. [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [classify.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/classify.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py).

## Approval / Undo Assessment

Actual M05 snapshot effects occur only after explicit approval in the inspected path. That is a meaningful strength. Plan-first ordering handles some retry cases but does not make plan→vocabulary→candidate status one authorized transaction (09/17). Undo disables a created entry wholesale and can overwrite aliases read before a user edit (10). M05 already supplies canonical scope and expected-revision mechanisms; M14 should consume those rather than invent a parallel dictionary writer. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [vocabulary.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/vocabulary.md).

## Counterexample Assessment

The scoped sandbox has a genuine positive adverse-phrase test: it is not the old empty-scope false green. Empty populations still return no flips, so testing status must not be presented as safety qualification (35). Full effective-dictionary composition and canonical scopes require proof. Store content-bearing phrases in governed artifacts, not counterexample_json (15). A useful oracle proves the candidate actually applies to at least one in-scope adverse example and does not falsely block an out-of-scope control. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [test_learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/personalization/test_learning.py).

## Rejection / Suppression Assessment

Exact rejected alias/canonical pairs are persistently suppressed and this is intentional user preference metadata. The current comparison is global and exact-string; case-equivalent and different-scope behavior must be explicitly adjudicated (34), not silently converted to a new policy. Pair metadata is distinct from whole-observation or counterexample retention. Reject state checks are useful; current liveness, retry outcome and every retained content field still require local probes. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py).

## Sampling Assessment

A seeded per-example/policy decision stream and serialized refresh support determinism and deduplication. Explicit/hard/supplemental/late enrichment must use null probability rather than claiming the base Bernoulli inclusion probability. Test genuinely populated strata and independent expected membership, including late triggers and insertion-order permutation. `LIVE_EXAMPLE_STATES` can include metadata-review states beyond trainable states; do not assume every sampling membership is training eligibility or invent a floor policy from that constant. Sampling/exclusion serialization and unknown-outcome retries remain local proof requirements. [sampling.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/sampling.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py) [splits.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py).

## Preference Assessment

The same-task writer checks candidates’ task keys, and the exporter correctly maps prefer_b and latest comparable pair judgments. Those protections should be retained. They do not prove exact retained input comparability: the writer lacks artifact-liveness checks, the exporter omits task-source dependencies (08), and native A/B rendering does not establish visible candidate identities (16). Tie/neither/uncertain must not fabricate a preferred output. A randomized display-order test must pass through the real displayed view model, not merely set display_order in a DB fixture. [transforms_store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/transforms_store.py) [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [hub.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py).

## Family Split Assessment

The current floor is ten live families, not ten examples. Family-based hashing is deterministic under a fixed seed/policy; a family must never occupy multiple partitions in one version. Normal subsequent assignments preserve all-history exposure. The old-version NEW export path does not consult later exposure (04). Task-keyed transforms/preferences lack equivalent partition lineage by explicit current exception (31). Exposure and family mapping require authoritative links—not proximity, repeated text or a fabricated task-to-family identity. [splits.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/dataset_exports.md).

## Dataset View Assessment

These are **current implemented predicates**, not inferred desired predicates. The common `_select` layer uses the selected assignment, requested partitions, latest training envelope, `TRAINABLE_STATES`, family consistency and the exposure flag in that assignment. It does not apply that example layer to every task-keyed record.

| View | Current selection conditions | Qualification gaps |
|---|---|---|
| `asr_supervised` | Selected trainable example; listened verbatim annotation; original_audio ID; M14 ASR gate; retained reference and audio with a file path. | Owner/role/source-reference checks; effective-label policy; complete serialized lineage. |
| `cleanup_supervised` | Selected trainable example; correctness=`correct`; provenance=`user_explicit_intended_writing`; retained source and applied text. Normalized/model-input availability is handled separately, with missing-input allowance. | Owner/role/stage; prompt/conditional-input qualification; readiness parity. |
| `transform_supervised` | Accepted transform candidate with retained source/output and stored definition/revision information; task-keyed rather than example-partition selected. | Exact task lineage, effective single-candidate acceptance semantics, explicit unsplit status/family mapping. |
| `preference_pairs` | Latest comparable judgment for a pair; matching stored task/input metadata; both output texts retained; chosen mapping follows judgment, neutral judgments do not fabricate a winner. | Source payload liveness/reconstruction, role/job authority, visible-pair binding, family partitions. |
| `asr_span_graft_weak` | Selected example with latest nonnull graft artifact and partial/weak representation; audio is not equivalent to a full reviewed reference. | Exact immutable graft source/coverage lineage, current effective label, retention ownership and offline reconstruction. |

No view is qualified by another view’s positive test. Positive witnesses must be independently present for all five; an empty export is not a successful round trip. The source contains useful missing-reason metadata, but a reason for missing data is not the missing data. [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/dataset_exports.md).

## Export Safety / Integrity Assessment

Four distinct boundaries must be tested: source selection, source file opening, operation-owned staging, and publication. Existing-destination protection and copied-audio digest checks are real. The unowned `.destination.building` deletion is Critical (02); unconstrained source audio paths are High (05); the final publication gap remains High pending a precise barrier witness (06); source-dependency omissions are covered by 07/08.

The source snapshot is selected in one writer operation, reducing mixed-database reads. Bulk audio copy occurs outside that operation. The final recheck correctly distinguishes consumed inputs from unrelated tombstones in existing tests. It does not by itself establish publication safety after the check returns, nor does it protect a dependency never placed in the input set. Consent revocation, vanished artifact rows, label/preference changes and filesystem errors need independently ordered probes. Concurrent builds sharing the staging name belong to operation identity finding 17.

Crash cases must prove no half-valid directory appears complete, and cleanup must never touch pre-existing or another operation’s staging. An output name or an exporter_version marker is not sufficient ownership proof. [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [test_dataset_export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/training/test_dataset_export.py).

## Offline Validator Assessment

The current validator **does recompute checksums and a content fingerprint**; it is not merely trusting the manifest. Its reduced exported graph prevents it from validating absent job/role/source/revision/rights objects (07). A foreign payload with internally consistent hashes remains foreign.

The inspected round-trip test closes the store and changes cwd; this is useful but narrower than removing live DB access, blocking network and reconstructing every conditional task from the package. The validator may require its declared installed Python/package runtime; “offline” does not mean “no executable runtime.” It must not require the original private DB, transcript store, repository path or unresolved database ID. Move the export and provide only the declared validation distribution, then independently reconstruct five-view witnesses. [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [validate_dataset.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/scripts/v2/validate_dataset.py) [test_dataset_export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/training/test_dataset_export.py) [LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md).

## Readiness Assessment

Finding 14 is a semantic parity defect, not a reopening of M13’s reconciled usage population. M13 already corrected audio owner/role for its own ASR readiness and identified cleanup ownership as an M14 residual. Further disagreements include incorrect intended-writing as cleanup “eligible,” M14 blocking labels and current preference judgments. Preserve the explicit **last export integrity** label: it is not a claim that the current dataset is qualified. Per-span reviewed seconds cannot be fabricated from span count; known full-clip listened coverage and unknown partial coverage must remain distinct. [training_data.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py) [M13.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M13.md).

## Your Voice Eligibility Assessment

The inspected population excludes nontrainable examples, profile exclusions, snippet-expanded evidence and currently flagged background speech, and deduplicates repeated utterances under its declared normalization. This is not a complete measure of all lifetime speech. Its default interpretation floor is **2,000 eligible words AND ten dictations**; each threshold needs its own below-boundary negative and an exactly-at-both positive.

Retention and immutable-source identity must be checked independently of example state. A count can be numerically correct for the data read and still be unauthorized at publication (03). Repeated-case/punctuation/whitespace normalization and exclusion ordering should be characterized against the current contract rather than “fixed” to a guessed dedup policy. [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [config.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/config.py) [profile.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/profile.md).

## Your Voice Profile / Card Assessment

Measured speech fields, usage facts and interpretive cards have different evidence populations. Every card needs specific live support and an independently derivable claim; a nonempty evidence-ID list is not enough. Correction-card support was improved historically and should be preserved. Technical terms derive from independent vocabulary counters, not exclusively the speech cohort (33). Do not label a dictionary-use fact as “you say this” unless cited retained utterances support it.

The final source-artifact fence and current-snapshot validity are incomplete (03); the two-stage signature can swallow certain vocabulary changes (23). A durable exclusion applied through an older rendered snapshot must affect the current supported result, not merely mark that old snapshot invalid. This latter race is in the corpus and is not counted as a separately reproduced defect. [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [your_voice.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/your_voice.py).

## Usage Redaction Assessment

Current M13 policy redacts app/hour/mode/request and applicable other usage-derived profile copies in the same deletion/expiry operation, and handles no-usage launch state. This is a source-supported strength. Speech-derived fields may remain when their own retained evidence remains. Missing local-hour offsets and self-correction metrics remain unknown; self-correction rates use only cases whose signal is known.

Current analytics policy **deliberately does not erase independent vocabulary occurrence counters with Delete Usage**. Therefore this audit does not allege that a surviving vocabulary-use count alone is an M13 deletion violation. Finding 33 concerns accurate provenance, wording and term/card support. Preserve the distinction when testing dictionary-hit-derived fields versus independent dictionary counters. [analytics.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/analytics.md) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [your_voice.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/your_voice.py) [M13.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M13.md).

## Idle Profile Assessment

The fast unchanged check is counters/signatures based, and an unchanged idle pass should read no transcript content and write no snapshot. Preserve that improvement. Finding 23 targets the later equivalence decision, not a claim that every tick churns snapshots. Instrument reads and writes with independent counters and test output-bearing changes held constant in cardinality: labels, canonical terms, exclusions, source purges, usage revisions, algorithm and threshold.

`profile_idle_minutes=0` disables idle generation, not all on-demand personalization. The configuration read includes the 30-minute default and 2,000-word floor. Do not invent a separate generic “learning disabled” flag; inventory actual coordinator/config controls and test the documented baseline, profile-off and approval states. Actual busy-yield scheduling and all coordinator callers remain local qualification tasks. [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [config.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/config.py) [app.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/app.py).

## Hub Functional Assessment

Current M09 discipline binds ordinary candidate actions to stable rendered items, and the formerly dead action wrapper has a real positive test. Preserve its refusal on deletion/reordering. Three M14 gaps stand out: job-only candidates cannot follow the example-dependent selection path (18); A/B comparison text/identity is not established before judgment (16); retry-sensitive domain operations do not inherit stable identity simply because a background completion token exists (17).

Local owned-window qualification must exercise populated Review, Label, Approve, Reject, listened/verbatim gates, A/B/tie/neither/uncertain, splits, a real successful export, Generate, evidence exclusion and keyboard navigation. A consent-refused export does not prove a successful Export action; a below-floor profile pane does not prove evidence-linked cards. No native checks were run here, and no visual redesign is authorized. [hub.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py) [state.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/state.py) [test_training_review_hub.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/ui/test_training_review_hub.py).

## Privacy Assessment

Main learning event emissions inspected are metadata/reason based; no new M14 network or microphone operation was observed in the core modules. This is not a repository-wide runtime no-network/no-microphone certification: local capability traps and caller inventory remain required.

The material privacy defects are derived speech republished after artifact purge (03), unconstrained audio reads (05), full counterexample strings outside governed artifacts (15), and absolute private paths in current historical M14 results (26). The audit does not reproduce those personal paths. Explicit local dataset export may legitimately contain opted-in synthetic/real training content when chosen by the user; it is different from generic logs or automatic sharing. Benchmarks and Git evidence must use synthetic text/audio only and must scan all fields, not only two candidate JSON columns. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [results.json](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/acceptance/M14/results.json).

## Test-Oracle Assessment

Meaningful existing positives include actual M05 pre/post approval output, in-scope adverse counterexample application, copied WAV digests, prefer_b with distinct outputs, selected-source purge refusal and unrelated deletion completion. Do not discard those tests or describe the entire suite as vacuous.

Important missing or narrower oracles are in 27/29: a real coordinator personalization-disabled comparison; exact visible A/B identity; every card’s support; five-view reconstruction of source inputs; corruption-based readiness/export parity; late deletion after the final fence; user-edit CAS during undo; M14 reviewed retention through Unpin; and independent component work counts. Mutation witnesses must distinguish NOT_REACHED, INVALID and SURVIVED from KILLED. A crashed mutant never establishes semantic protection.

The supplied corpus is a **declarative specification**, with fixture recipes and local binding points, not a secretly executed test harness. Every refusal population has a positive fixture/control requirement. Policies 30–36 must be resolved before grading policy-dependent expectations. [test_learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/personalization/test_learning.py) [test_profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/personalization/test_profile.py) [test_dataset_export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/training/test_dataset_export.py) [test_training_review_hub.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/ui/test_training_review_hub.py).

## Performance / Benchmark Assessment

The historical benchmark runs real store work, streams audio and probes concurrent writes. It must not be dismissed as a pure no-op. Its independent validity is insufficient (28): nominal observation rows need not equal actual changed/mineable observations; some report fields are constants; copied bytes and component outcomes need independent recounts. A fast no-op must fail validity, not win a timing comparison.

No current timing is reported. Re-measure profile compute, 1k observation mining, note mining, 10k-example sampling/splits and large-audio export on the actual reference Mac. Separate wall-clock duration, throughput, peak memory, actual writer hold and dictation write wait. Profile chunking helps, but the note-mining pass and export snapshot can still hold the writer; sampled wall-time figures do not establish acceptable disruption. Run continuous overlapping probes and record exact SHA, Mac/macOS/Python/SQLite/PyObjC, power/load, warm/cold state and actual counts/bytes. Do not run timing alongside the test sweep. [benchmark_m14.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/scripts/v2/benchmark_m14.py) [results.json](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/acceptance/M14/results.json).

## Critical Findings

### M14-AUDIT-01 — Artifact existence is accepted as evidence authority

**Severity:** CRITICAL  
**Confidence:** High: direct source-to-export path; corruption probe not executed  
**Category:** artifact ownership  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.5/S29.12/S29.13; artifacts.md; audit §§8–10,57–63: retained evidence must belong to the same job and the expected semantic role.

**Code location.** [`localflow/v2/curation/review.py` — verified_asr_eligible_in; stage_texts_for](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L1-L320); [`localflow/v2/curation/export.py` — _conn_artifact; _asr_rows; _cleanup_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L90-L335); [`localflow/v2/training_data.py` — readiness](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py#L680-L965); [`localflow/v2/profile.py` — eligible speech input reads](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py#L1-L310). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The M14 ASR gate checks retained audio existence without proving job/role; export reads audio and references through an ID-only helper. Cleanup and envelope-backed stage reads likewise do not consistently enforce owner/role. M13 ASR readiness already has an owner/role check, which is not the M14 export gate.

**Failure mechanism.** A synthetic corrupted latest envelope can substitute B’s retained audio or text for A’s. The helper does not even select job_id. Valid hashes authenticate B’s bytes, not A’s lineage. Store.verify can report a foreign reference, but export does not make that report a prerequisite.

**Minimal reproduction (local; NOT_RUN).**

1. Create independently eligible A and B, distinct original-audio canaries, own reviewed references, and a valid family assignment.
2. Change only A’s latest original_audio reference to B’s retained audio; preserve A’s job identity. Repeat with wrong-role same-job audio and foreign/wrong-stage cleanup source.
3. Run the gate, readiness and an actual selected-view export; inspect copied bytes and ownership independently.

**Expected behavior.** Every foreign/wrong-role row is refused or excluded with a content-free reason; B’s uncorrupted positive control remains eligible. No foreign canary enters A’s exported record.

**Likely actual behavior / verification boundary.** The M14 ASR gate checks retained audio existence without proving job/role; export reads audio and references through an ID-only helper. Cleanup and envelope-backed stage reads likewise do not consistently enforce owner/role. M13 ASR readiness already has an owner/role check, which is not the M14 export gate. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Existing export fixtures cover missing/purged audio, copied-audio hashes and ordinary live examples; M13 coverage checks its own readiness population.

**Why the oracle misses it.** Ordinary fixtures use internally coherent references. Byte-integrity and existence assertions do not challenge ownership. The two ASR gates are different implementations.

**Regression recommendation.** Every foreign/wrong-role row is refused or excluded with a content-free reason; B’s uncorrupted positive control remains eligible. No foreign canary enters A’s exported record. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Introduce an M14-owned evidence resolver that checks authoritative example/job identity, latest revision, expected role/stage, retained payload and digest; reuse its qualified result across M14 gates, export and readiness. Preserve M02 producer barriers.

**Downstream impact.** M02/M05/M11/M12 inputs; M13 readiness; blocks M15 dataset qualification.

### M14-AUDIT-02 — Exporter recursively removes an unowned staging directory

**Severity:** CRITICAL  
**Confidence:** High: unconditional destructive branch in source  
**Category:** export filesystem safety  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.13/E19.5 and audit §§64–65: no unrelated existing file may be deleted or overwritten.

**Code location.** [`localflow/v2/curation/export.py` — DatasetExporter.build staging preparation](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L450-L505). The links pin source windows; function names identify the relevant branch.

**Current behavior.** For destination D, the predictable sibling .D.building is recursively deleted whenever it already exists as a directory. No operation marker or ownership proof is required.

**Failure mechanism.** The code equates a directory name with an interrupted build. The deletion occurs before snapshot/consent admission, so even a subsequently refused export can destroy an unrelated sentinel.

**Minimal reproduction (local; NOT_RUN).**

1. In a synthetic temporary parent create .dataset.building/UNRELATED_KEEP with unique bytes; leave dataset absent.
2. Invoke build for dataset with a valid store; also repeat with consent disabled.
3. Record filesystem operations and compare the sentinel byte-for-byte.

**Expected behavior.** Refuse the collision without changing any existing file. Remove only an exclusively created, operation-owned staging tree.

**Likely actual behavior / verification boundary.** For destination D, the predictable sibling .D.building is recursively deleted whenever it already exists as a directory. No operation marker or ownership proof is required. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Tests protect nonempty destinations, earlier exports with added files, staging files and symlinks.

**Why the oracle misses it.** A pre-existing staging directory containing unrelated data is not the same case as a staging file. Existing-destination checks never protect this sibling.

**Regression recommendation.** Refuse the collision without changing any existing file. Remove only an exclusively created, operation-owned staging tree. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use unique exclusive per-operation staging with durable ownership identity; never rmtree a predictable pre-existing directory. Confine cleanup to the exact staging identity created by this operation.

**Downstream impact.** Independent of other milestones; blocks safe export and M15.

### M14-AUDIT-03 — Your Voice can publish speech after its source artifact was purged

**Severity:** CRITICAL  
**Confidence:** High: read/commit gap and insufficient current-snapshot scrub  
**Category:** profile evidence liveness  
**Target execution:** NOT_RUN

**Canonical requirement.** S22/S29.14; profile.md; audit §§79–80: every output-bearing input must remain live through publication; deleted speech cannot survive as a current derived phrase.

**Code location.** [`localflow/v2/profile.py` — compute commit fence; current; input/evidence signatures](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py#L1-L610); [`localflow/v2/store.py` — _purge_artifact](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py#L2680-L2780). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Profile computation reads text in chunks, but its final commit primarily rechecks that contributing example rows are live. A purge can remove the source payload while leaving the example live; the current-snapshot scrub checks example liveness rather than every artifact used.

**Failure mechanism.** After the text is copied into the computation, purge sets content_text/path to null and purged=1 without invalidating all corresponding derived snapshots. The computed frequent phrase can then be committed and returned as current.

**Minimal reproduction (local; NOT_RUN).**

1. Seed ten unique eligible dictations totaling at least 2,000 words and a repeated synthetic phrase supported by designated raw artifacts.
2. Latch computation after reading one supporting artifact but before final commit. Purge that artifact through the store while leaving its example trainable.
3. Release computation; inspect current() and all published snapshot data for the phrase and its support.

**Expected behavior.** Abort/recompute against current qualified inputs; do not publish the purged phrase. A no-purge companion publishes a valid snapshot. Test label/exclusion/revision changes at the same fence separately.

**Likely actual behavior / verification boundary.** Profile computation reads text in chunks, but its final commit primarily rechecks that contributing example rows are live. A purge can remove the source payload while leaving the example live; the current-snapshot scrub checks example liveness rather than every artifact used. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Profile tests cover deletion of an example during reads and clearing snapshots linked to deleted examples. Store deletion clears linked snapshots.

**Why the oracle misses it.** Example deletion trips the existing state fence. Artifact-only purge deliberately does not, so the historical deletion test is not a witness for this race.

**Regression recommendation.** Abort/recompute against current qualified inputs; do not publish the purged phrase. A no-purge companion publishes a valid snapshot. Test label/exclusion/revision changes at the same fence separately. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Track and revalidate the exact artifact/revision/label/exclusion dependency set in the commit operation. Current snapshot access must reject/redact snapshots whose retained support no longer exists.

**Downstream impact.** M02 retention and M12 evidence consumption; preserve M13 same-operation usage redaction; M15 privacy gate.

### M14-AUDIT-04 — A new export can reclaim frozen-test status from an older assignment

**Severity:** CRITICAL  
**Confidence:** High: explicit assignment-version selection omits later exposure history  
**Category:** exposed families  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.11/E19.5; dataset_exports.md; audit §§54,67,101: exposure is forward-only across future exports, even while historical manifests remain immutable.

**Code location.** [`localflow/v2/curation/export.py` — DatasetExporter._select](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L135-L214); [`localflow/v2/curation/splits.py` — mark_exposed; assign](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py#L1-L330). The links pin source windows; function names identify the relevant branch.

**Current behavior.** _select reads exposed flags only from the requested assignment version. An old version can still contain frozen_test/exposed=false after a later version records exposure.

**Failure mechanism.** Immutable history is appropriate, but exporting a new dataset from that old assignment is a new qualification decision. The export checks the historical row rather than current knowledge that the family has been exposed.

**Minimal reproduction (local; NOT_RUN).**

1. Create a valid v1 assignment containing a frozen family F and eligible source records.
2. Expose F so the current assignment carries its regression/development status. Keep v1 unchanged.
3. Build a NEW frozen_test export explicitly using assignment_version=v1.

**Expected behavior.** Refuse or explicitly mark the exposed family non-blind in the new export; never emit a fresh frozen_test/exposed=false claim. Reproducing historical bytes must be a separately labeled non-qualification operation.

**Likely actual behavior / verification boundary.** _select reads exposed flags only from the requested assignment version. An old version can still contain frozen_test/exposed=false after a later version records exposure. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Split tests verify subsequent assignments preserve exposure, including a family absent for one version. Export tests challenge exposed=true in the selected version.

**Why the oracle misses it.** Those paths do not request a version predating exposure. No ordinary reassignment regression is reopened here.

**Regression recommendation.** Refuse or explicitly mark the exposed family non-blind in the new export; never emit a fresh frozen_test/exposed=false claim. Reproducing historical bytes must be a separately labeled non-qualification operation. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Join selected families to the all-history exposure ledger at export qualification and retain that evidence in the manifest; keep old assignment rows immutable.

**Downstream impact.** M14 split/export boundary; critical for M15 holdout integrity.

## High Findings

### M14-AUDIT-05 — Audio export trusts an unconstrained stored source path

**Severity:** HIGH  
**Confidence:** High: path join and copy lack a managed-file boundary  
**Category:** export path confinement  
**Target execution:** NOT_RUN

**Canonical requirement.** Artifacts/store managed-file contracts; audit §66: a corrupted DB path must not cause arbitrary file read/copy.

**Code location.** [`localflow/v2/curation/export.py` — build.copy_audio](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L530-L563). The links pin source windows; function names identify the relevant branch.

**Current behavior.** copy_audio joins artifacts_dir with artifact["path"] and passes it to shutil.copyfile. Absolute paths, parent traversal and symlink targets are not admitted through a no-follow managed-file reader.

**Failure mechanism.** A synthetically corrupted audio row with a matching digest can cause export to copy an outside sentinel. Post-copy hashing does not confine the source path.

**Minimal reproduction (local; NOT_RUN).**

1. Place an outside synthetic WAV sentinel next to, not inside, the managed artifact root.
2. Point an eligible audio row at its absolute path, ../ path, then an in-root symlink; use the sentinel digest.
3. Export and record file opens/copies. Include a legitimate managed WAV positive control.

**Expected behavior.** Refuse before opening outside bytes; only managed regular files of the expected identity are copied.

**Likely actual behavior / verification boundary.** copy_audio joins artifacts_dir with artifact["path"] and passes it to shutil.copyfile. Absolute paths, parent traversal and symlink targets are not admitted through a no-follow managed-file reader. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Audio damage/hash mismatch and exported symlink tests exist.

**Why the oracle misses it.** They challenge payload integrity or exported paths, not the source path authority.

**Regression recommendation.** Refuse before opening outside bytes; only managed regular files of the expected identity are copied. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Reuse the current managed-file confinement/no-follow discipline at the M14 copy boundary; handle FIFO/device/ancestor-symlink cases with bounded refusal.

**Downstream impact.** M02 managed artifact boundary, M14 privacy and filesystem safety.

### M14-AUDIT-06 — Export publication is outside the final source-liveness fence

**Severity:** HIGH  
**Confidence:** High for gap; exact interleaving requires local barrier witness  
**Category:** export concurrency  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.13/S29.14; audit §§68–70: deletion of a source actually consumed before final publication must not leave a completed export.

**Code location.** [`localflow/v2/curation/export.py` — build final recheck and rename](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L713-L850). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The final recheck is a store operation, followed by filesystem replacement/rename outside that operation. The dependency check also focuses on selected artifacts and example state rather than all behavior-bearing revisions.

**Failure mechanism.** A selected-source purge or consent revocation can commit after the recheck returns but before publication. Earlier after_sums tests place deletion before the fence, not in this remaining interval.

**Minimal reproduction (local; NOT_RUN).**

1. Prepare a valid nonempty export.
2. Latch immediately after successful final store recheck and before staging publication; purge a selected input or revoke export consent.
3. Release publication and inspect destination and export-manifest status. Repeat with unrelated source deletion.

**Expected behavior.** No completed export contains the deleted selected source. Unrelated deletion must not abort the companion. A documented publication linearization point and dependency semantics must be explicit.

**Likely actual behavior / verification boundary.** The final recheck is a store operation, followed by filesystem replacement/rename outside that operation. The dependency check also focuses on selected artifacts and example state rather than all behavior-bearing revisions. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Historical selected-input purge abort and unrelated-deletion completion tests are real positive/negative controls.

**Why the oracle misses it.** Their hook is before the final recheck; they cannot close the post-recheck race.

**Regression recommendation.** No completed export contains the deleted selected source. Unrelated deletion must not abort the companion. A documented publication linearization point and dependency semantics must be explicit. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Arbitrate publication with current deletion/consent authority, using a small writer-fenced publish decision or an equivalent proven protocol. Preserve streaming bulk I/O outside the writer.

**Downstream impact.** M02 deletion fences and M14 export; do not broadly redesign the store.

### M14-AUDIT-07 — Portable export cannot independently reconstruct or qualify its full evidence graph

**Severity:** HIGH  
**Confidence:** High: serialized schema omits required source objects  
**Category:** dataset lineage and offline validation  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.13 and E19.5: no database foreign key without target payload; retained task inputs, revisions, family/sampling/rights lineage independently reconstructable offline.

**Code location.** [`localflow/v2/curation/export.py` — record serialization; dataset manifest; validate_export](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L565-L1035); [`scripts/v2/validate_dataset.py` — main](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/scripts/v2/validate_dataset.py#L1-L120). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Exports serialize task rows and output/reference text, but omit substantial revision/parent/consent/sampling and exact source-task objects. Preference inputs are hashes rather than retained conditional text. Validator recomputes checksums and content fingerprint, but cannot verify absent lineage.

**Failure mechanism.** A self-consistent package can pass byte-integrity checks without demonstrating that a reference belongs to its job, a preferred output belongs to the retained task input, or a decision was the qualified current human judgment.

**Minimal reproduction (local; NOT_RUN).**

1. Export a populated five-view fixture, remove access to the live DB and network, and reconstruct each task from exported bytes only.
2. For each view demand the exact source, reviewed authority and family lineage; inventory missing targets.
3. Create a semantic ownership/task mismatch in a synthetic package and consistently recompute hashes/fingerprint; require the validator to reject it independently.

**Expected behavior.** Task reconstruction and semantic lineage validation succeed without live DB/source payloads; corrupt-but-self-consistent lineage is rejected. Honest incomplete research records must not be labeled fully qualified.

**Likely actual behavior / verification boundary.** Exports serialize task rows and output/reference text, but omit substantial revision/parent/consent/sampling and exact source-task objects. Preference inputs are hashes rather than retained conditional text. Validator recomputes checksums and content fingerprint, but cannot verify absent lineage. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Round-trip tests actually hash copied WAVs and JSONL; validator works from a different cwd with store closed.

**Why the oracle misses it.** Same-code schema checks establish packaging integrity, not information absent from the schema. Tests do not reconstruct every conditional input and authority chain.

**Regression recommendation.** Task reconstruction and semantic lineage validation succeed without live DB/source payloads; corrupt-but-self-consistent lineage is rejected. Honest incomplete research records must not be labeled fully qualified. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Export a bounded, versioned evidence closure with explicit ownership/role and current decision proofs; independently validate references, task identity, splits and rights. Keep legacy/incomplete views explicitly separate.

**Downstream impact.** M11 transform inputs, M13 readiness, M15 G10. No training algorithm is requested.

### M14-AUDIT-08 — Preference selection ignores the liveness of its source task

**Severity:** HIGH  
**Confidence:** High: source dependencies absent from export selection  
**Category:** preference eligibility  
**Target execution:** NOT_RUN

**Canonical requirement.** preferences.md/S29.10/S29.12; audit §§48–50,62: outputs must share a retained, live conditional task, not merely matching stored hashes.

**Code location.** [`localflow/v2/curation/export.py` — _preference_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L355-L450); [`localflow/v2/transforms_store.py` — record_observation](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/transforms_store.py#L490-L554). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Preference export fetches the candidates’ output artifacts and stored task/hash metadata but not their source artifacts. Its final dependency set therefore cannot notice deletion of an input it never selected.

**Failure mechanism.** Purge the task source while retaining both candidate outputs and the current explicit judgment. A same-task-key comparison remains exportable even though the training input no longer exists. The writer itself compares task keys, not source payload identity/liveness.

**Minimal reproduction (local; NOT_RUN).**

1. Create two outputs of one valid task, explicit prefer_b, and retained source text.
2. Purge only the shared task source; keep outputs and judgment.
3. Query preference readiness/selection and build preference_pairs; compare with a source-live positive pair.

**Expected behavior.** The purged-input pair becomes incomplete/ineligible and is refused or excluded; the live pair exports B with the retained exact task input.

**Likely actual behavior / verification boundary.** Preference export fetches the candidates’ output artifacts and stored task/hash metadata but not their source artifacts. Its final dependency set therefore cannot notice deletion of an input it never selected. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Cross-task rejection and prefer_b/latest-judgment output mapping are covered.

**Why the oracle misses it.** The fixture’s output-only shape can satisfy those assertions without a source-liveness witness.

**Regression recommendation.** The purged-input pair becomes incomplete/ineligible and is refused or excluded; the live pair exports B with the retained exact task input. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Qualify both candidate bindings against the canonical retained input/revision and expected roles; include every source dependency in export and its final fence.

**Downstream impact.** M11 task identity consumed by M14; readiness parity and M15 preference qualification.

### M14-AUDIT-09 — Approval can install a rule after its candidate was revoked

**Severity:** HIGH  
**Confidence:** High: plan/effect/status are separate writer operations  
**Category:** approval transaction authority  
**Target execution:** NOT_RUN

**Canonical requirement.** S11/learning.md; audit §§25–35: approval must be live, narrow, idempotent and recoverable; no orphan learned rule.

**Code location.** [`localflow/v2/learning.py` — approve; _plan_rule; _apply_plan](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L445-L624). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Approval persists a plan, invokes vocabulary mutation, then marks the candidate. It does not hold one authoritative candidate/evidence decision across those phases.

**Failure mechanism.** Delete/stale/reject a pending candidate after the plan commits but before vocabulary mutation. The rule can be installed although the later status write refuses; undo_approval requires approved status, so ordinary undo cannot reconcile the orphan.

**Minimal reproduction (local; NOT_RUN).**

1. Seed one approvable, live candidate and no existing vocabulary entry.
2. Latch after plan persistence; delete its example/job or reject it, then release vocabulary application.
3. Inspect real M05 normalization, candidate status, plan and dictionary history; retry once with the same logical action.

**Expected behavior.** No rule is installed after prior revocation; or a proven atomic operation linearizes approval first and deletion follows its documented policy. Every effect has one recoverable approved operation identity.

**Likely actual behavior / verification boundary.** Approval persists a plan, invokes vocabulary mutation, then marks the candidate. It does not hold one authoritative candidate/evidence decision across those phases. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Plan-before-effect and a simulated failure before the vocabulary write are tested.

**Why the oracle misses it.** Pre-write failure is not post-commit unknown outcome; the tests do not revoke the candidate between the three operations.

**Regression recommendation.** No rule is installed after prior revocation; or a proven atomic operation linearizes approval first and deletion follows its documented policy. Every effect has one recoverable approved operation identity. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Make the plan an operation with expected candidate/evidence/vocabulary revisions and writer-authoritative transition checks; reconcile uncertain effects instead of retrying a new logical approval.

**Downstream impact.** M05 authoritative dictionary mutation; M09/M10 outcome discipline; M12 deletion.

### M14-AUDIT-10 — Undo is not confined to the original vocabulary delta

**Severity:** HIGH  
**Confidence:** High: unconditional disable and non-CAS alias replacement  
**Category:** undo and manual edits  
**Target execution:** NOT_RUN

**Canonical requirement.** S11/learning.md; audit §§35–36: undo reverses only what learning added and preserves subsequent user-owned configuration.

**Code location.** [`localflow/v2/learning.py` — undo_approval; _with_alias; _apply_plan](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L610-L784). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Undo of a created entry disables the entire entry even if the user has since changed it. Alias undo reads aliases outside the writer and submits a replacement without expected_revision.

**Failure mechanism.** A user-added alias or changed canonical can be disabled with the learned entry. A concurrent alias edit between read and update can be overwritten. Re-approval of a prior created plan also needs a deliberate policy for a later user disable.

**Minimal reproduction (local; NOT_RUN).**

1. Approve to create an entry; manually add a distinct alias and edit its canonical; undo.
2. For alias_added, latch after undo reads aliases; add a second user alias through M05; release undo.
3. Exercise approve→undo→reapprove and a manually disabled entry separately.

**Expected behavior.** Only the learning-owned delta is reversed, or a stale-revision conflict is honestly refused. User changes remain byte-for-byte and behaviorally intact.

**Likely actual behavior / verification boundary.** Undo of a created entry disables the entire entry even if the user has since changed it. Alias undo reads aliases outside the writer and submits a replacement without expected_revision. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Existing tests preserve an already user-owned entry and ordinary alias additions without a concurrent edit.

**Why the oracle misses it.** The created-entry/manual-edit and read-update races are absent; ordinary alias undo passing does not prove scoped reversal.

**Regression recommendation.** Only the learning-owned delta is reversed, or a stale-revision conflict is honestly refused. User changes remain byte-for-byte and behaviorally intact. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Record the exact delta and revision; perform writer-time CAS/merge through M05. Preserve new user ownership and refuse ambiguous reversals.

**Downstream impact.** M05 history/revision semantics and M14 reversible learning.

### M14-AUDIT-11 — Teach does not bind to the immutable final text the reviewer saw

**Severity:** HIGH  
**Confidence:** High: acknowledged M09 lead; transformed UI path already guarded  
**Category:** explicit teaching authority  
**Target execution:** NOT_RUN

**Canonical requirement.** Current hub.md and M09 addendum; audit §§17–20: rendered final text and immutable source identity govern Teach.

**Code location.** [`localflow/v2/learning.py` — teach_correction](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L40-L150); [`docs/v2/contracts/hub.md` — History Teach authority](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/hub.md#L230-L340); [`docs/v2/handoffs/M09.md` — Limits and leads](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/handoffs/M09.md#L80-L190). The links pin source windows; function names identify the relevant branch.

**Current behavior.** teach_correction accepts no expected artifact/revision/hash. It derives applied text with a raw fallback. The current Hub correctly refuses Teach when its displayed final is an applied transform, which narrows the reachable defect.

**Failure mechanism.** A retry or revision change after rendering can make the service compare the correction against a newer/different source; a missing applied stage can fall back to raw. Shared M02 job-deletion guards prevent the broad claim that a deleted job can simply be recreated.

**Minimal reproduction (local; NOT_RUN).**

1. Render a synthetic History item with final artifact F1; type a correction without submitting it.
2. Change its current final/attempt to F2 or purge F1 while retaining raw; then submit Teach.
3. Repeat collection on/off and verify the existing transformed-final UI refusal as a preservation control.

**Expected behavior.** Persist a teach only against the exact visible F1 identity/hash and still-live authorized state, or refuse stale/missing authority without substituting raw.

**Likely actual behavior / verification boundary.** teach_correction accepts no expected artifact/revision/hash. It derives applied text with a raw fallback. The current Hub correctly refuses Teach when its displayed final is an applied transform, which narrows the reachable defect. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M09 item binding and transformed-final refusal exist; learning tests cover ordinary teaching and already-deleted/quarantined examples.

**Why the oracle misses it.** Stable job/example identity is not stable artifact/attempt identity. The service cannot validate an expected source it never receives.

**Regression recommendation.** Persist a teach only against the exact visible F1 identity/hash and still-live authorized state, or refuse stale/missing authority without substituting raw. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Pass expected final artifact, revision/attempt and hash to Teach and revalidate inside the mint operation; explicitly support or continue to refuse transformed-final teaching.

**Downstream impact.** M09 History contract; M11 final-stage decisions; M02 deletion barriers remain intact.

### M14-AUDIT-12 — Confirmed graft offsets are not bound to the displayed source identity

**Severity:** HIGH  
**Confidence:** High: current-text validation without expected artifact/hash  
**Category:** partial graft authority  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.7; audit §§16–17: a partial graft indexes the exact immutable source reviewed; it never becomes full gold.

**Code location.** [`localflow/v2/curation/review.py` — label; graft construction](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L200-L390); [`localflow/v2/curation/classify.py` — graft application](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/classify.py#L400-L550). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Graft span mechanics validate ranges and current source words, but the M14 label API does not carry the displayed source artifact/hash as a compare-and-swap precondition.

**Failure mechanism.** A new source with the same word at the same offset can satisfy text checks despite being a different recording/revision. Full/partial quality remains correctly separate; the defect is authority, not an existing full-gold conversion.

**Minimal reproduction (local; NOT_RUN).**

1. Render source S1 and a confirmed span; prepare S2 with the same local substring but different surrounding text/identity.
2. Switch the current source before label Save, then submit the old offsets.
3. Test purged source, overlapping/out-of-range spans and Unicode boundaries with a valid positive companion.

**Expected behavior.** Save refuses stale source identity even when a substring happens to match; valid S1 graft is weak_partial with the exact coverage mask.

**Likely actual behavior / verification boundary.** Graft span mechanics validate ranges and current source words, but the M14 label API does not carry the displayed source artifact/hash as a compare-and-swap precondition. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Overlap, range, Unicode and partial-quality tests exist; M09’s separate span annotation API already has stronger expected-source arguments.

**Why the oracle misses it.** Good offset mechanics against writer-current text do not prove that the reviewer saw that text.

**Regression recommendation.** Save refuses stale source identity even when a substring happens to match; valid S1 graft is weak_partial with the exact coverage mask. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Carry immutable source artifact/revision/hash into the M14 label writer; store and export that source link with the graft, and retain weak/partial permanently.

**Downstream impact.** M09 annotation pattern; M14 ASR weak view; no full-ASR promotion.

### M14-AUDIT-13 — Note mining combines dictated and typed regions under one job

**Severity:** HIGH  
**Confidence:** High for mixed-region path; repeated-token variants require local characterization  
**Category:** M12 note attribution  
**Target execution:** NOT_RUN

**Canonical requirement.** S20/S22/S29.8; current scratchpad.md D04; audit §§21–22: no typed-only or cross-dictation region becomes evidence for another dictation.

**Code location.** [`localflow/v2/learning.py` — _mine_notes](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L195-L319); [`localflow/v2/notes.py` — rebase_spans; arrival_span](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/notes.py#L170-L256). The links pin source windows; function names identify the relevant branch.

**Current behavior.** M14 computes its own changed regions over whitespace-normalized text, collects the jobs touched by any region, and then classifies/mints all changed regions under the one surviving job. It does not reuse M12’s occurrence-count/rank ambiguity checks.

**Failure mechanism.** A revision with one edit in dictated A and another in typed-only text has hit_jobs={A}; both regions enter A’s governed candidate payload. Repeated tokens can additionally make SequenceMatcher’s convenient alignment disagree with actual occurrence authority.

**Minimal reproduction (local; NOT_RUN).**

1. Create a note containing a dictated A span plus a typed-only sentence and a live A evidence link.
2. In one typed revision correct a word in A and a different word in the typed sentence. Mine once.
3. Inspect each retained candidate region’s exact provenance. Add A+B crossing and repeated-word/count-change variants.

**Expected behavior.** Only exactly attributable regions from A are retained as A evidence; typed-only/ambiguous/cross-job regions are excluded or explicitly unqualified. No region gains reliable_target_observation by association.

**Likely actual behavior / verification boundary.** M14 computes its own changed regions over whitespace-normalized text, collects the jobs touched by any region, and then classifies/mints all changed regions under the one surviving job. It does not reuse M12’s occurrence-count/rank ambiguity checks. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Historical tests cover edits in one of two dictations and an edit touching both. M12 has stronger occurrence-safe rebase tests.

**Why the oracle misses it.** Those controls do not add a disconnected typed-only region to an otherwise attributable correction, and M14 reruns a weaker diff.

**Regression recommendation.** Only exactly attributable regions from A are retained as A evidence; typed-only/ambiguous/cross-job regions are excluded or explicitly unqualified. No region gains reliable_target_observation by association. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Consume one shared occurrence-safe attribution result with per-region source identity; do not classify the entire revision as A because one region touched A.

**Downstream impact.** Narrow M12→M14 evidence seam; M12 editor and deletion repairs are not reopened.

### M14-AUDIT-14 — Readiness and export disagree on task eligibility

**Severity:** HIGH  
**Confidence:** High: independent predicates visibly diverge  
**Category:** readiness/export parity  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.9/S29.12/E19.4; audit §§99–103: readiness must describe the same eligibility or explicitly named narrower export qualification.

**Code location.** [`localflow/v2/training_data.py` — readiness](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py#L680-L965); [`localflow/v2/curation/review.py` — verified_asr_eligible_in](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L85-L165); [`localflow/v2/curation/export.py` — _asr_rows; _cleanup_rows; _preference_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L210-L450). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Cleanup readiness accepts an intended-writing mark of correct OR incorrect with a retained source, while cleanup export requires correct plus explicit intended-writing provenance and additional output inputs. ASR readiness does not apply all M14 blocking-label policy; preference predicates also differ.

**Failure mechanism.** A readiness-positive population can yield no corresponding supervised records. Owner/role checks alone will not fix these semantic differences. The existing minimally described transform/readiness and last_export metrics should not be misrepresented as current full qualification.

**Minimal reproduction (local; NOT_RUN).**

1. Build a table of independently authored examples: correct/incorrect intended writing, blocked ASR labels, missing output, purged reference, and latest preference changes.
2. Count readiness by task; independently enumerate actual export membership using the same assignment population.
3. Change one gate only and require the parity oracle to fail; report legitimate documented narrower filters separately.

**Expected behavior.** Every displayed count names its exact tier; qualified counts match export membership and reason-coded exclusions on the corruption/negative population.

**Likely actual behavior / verification boundary.** Cleanup readiness accepts an intended-writing mark of correct OR incorrect with a retained source, while cleanup export requires correct plus explicit intended-writing provenance and additional output inputs. ASR readiness does not apply all M14 blocking-label policy; preference predicates also differ. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M13 tests reconcile the trainable population, exclusion priority, owner-aware ASR joins and available metric shapes.

**Why the oracle misses it.** A cohort/shape oracle does not compare M14 export predicates over intentionally inconsistent task evidence.

**Regression recommendation.** Every displayed count names its exact tier; qualified counts match export membership and reason-coded exclusions on the corruption/negative population. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Share a typed eligibility result with reasons across readiness and export; separate review-ready, minimally captured, and qualified-export tiers rather than silently broadening training.

**Downstream impact.** M13 readiness consumer seam only; M15 G10 cannot trust current counts as full qualification.

### M14-AUDIT-15 — Counterexample transcripts are stored in long-lived candidate metadata

**Severity:** HIGH  
**Confidence:** High: row write plus deletion path omission  
**Category:** learning privacy/retention  
**Target execution:** NOT_RUN

**Canonical requirement.** learning.md/store.md and S22/S29.14; audit §§24,38,95: full phrases live in governed artifacts, not content-free candidate rows.

**Code location.** [`localflow/v2/learning.py` — approve; _counterexample_flips](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L445-L665); [`localflow/v2/store.py` — _stale_candidates](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py#L2660-L2710). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Counterexample results include phrase and applied text and are serialized into counterexample_json on learning_candidates. Candidate staling clears selected terms/spans but does not clear this field.

**Failure mechanism.** A refused approval can leave complete user-entered counterexample phrases outside the payload lease/deletion mechanism. A rejection preference may intentionally keep an alias/canonical pair; that is not authority to keep whole examples.

**Minimal reproduction (local; NOT_RUN).**

1. Attempt approval with a synthetic sentence containing a unique private-text canary and an actual adverse alias hit.
2. Delete the source job/example/note and run retention; inspect candidate row JSON and artifact payloads independently.
3. Use a pair-only suppression control to distinguish permitted terms from whole-sentence retention.

**Expected behavior.** No full counterexample phrase remains in content-free metadata after its governing evidence is removed; any deliberate separate retention has explicit policy, ownership and delete controls.

**Likely actual behavior / verification boundary.** Counterexample results include phrase and applied text and are serialized into counterexample_json on learning_candidates. Candidate staling clears selected terms/spans but does not clear this field. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Row privacy tests inspect changed_spans_json and classification_json; normal observation payloads are governed artifacts.

**Why the oracle misses it.** The privacy assertion does not inspect counterexample_json, and historical clearing predates or omits that field.

**Regression recommendation.** No full counterexample phrase remains in content-free metadata after its governing evidence is removed; any deliberate separate retention has explicit policy, ownership and delete controls. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Move content-bearing counterexample evidence into governed artifacts, keep only IDs/result codes on rows, and propagate deletion/expiry through its lineage.

**Downstream impact.** M14 local privacy; preserve intentional pair-only rejection preference metadata.

### M14-AUDIT-16 — The A/B pane does not establish what the user is judging

**Severity:** HIGH  
**Confidence:** High: pane rendering and click handler inspected; native execution NOT_RUN  
**Category:** Hub preference review authority  
**Target execution:** NOT_RUN

**Canonical requirement.** preferences.md/E14/E19.3; M09 stable-rendered-ID contract; audit §§46–48,104–106.

**Code location.** [`localflow/v2/ui/hub.py` — preference view rendering and preference action](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py#L3340-L3650); [`localflow/v2/curation/review.py` — preference queue](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L390-L550). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The pane displays task metadata/counts rather than the source and both candidate texts. At judgment time it reloads candidates and chooses the first two, instead of binding the action to a rendered comparison pair/order.

**Failure mechanism.** A user can record an explicit preference without having seen the compared outputs; refreshed membership/order may change which pair the action targets. Correct prefer_b serialization cannot repair missing human comparison authority.

**Minimal reproduction (local; NOT_RUN).**

1. Create one task with visually distinct A and B outputs; render the native pane.
2. Assert both exact output texts and the shared input are visible and map to stable candidate IDs.
3. Change candidate order/add C after render; click B. Inspect the recorded and exported candidate identity.

**Expected behavior.** The action judges exactly the visible pair and order, or refuses staleness. All five choices retain unambiguous source/pair authority.

**Likely actual behavior / verification boundary.** The pane displays task metadata/counts rather than the source and both candidate texts. At judgment time it reloads candidates and chooses the first two, instead of binding the action to a rendered comparison pair/order. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Headless tests call real services and cover judgment vocabulary and cross-task rejection.

**Why the oracle misses it.** They do not verify that candidate text was displayed or exercise swapped display order through native handlers.

**Regression recommendation.** The action judges exactly the visible pair and order, or refuses staleness. All five choices retain unambiguous source/pair authority. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Add a stable comparison view model containing source identity, A/B IDs, texts, render generation and display order; bind every judgment to it.

**Downstream impact.** M09 action binding and M11 task identity consumed by M14; native functional qualification required.

### M14-AUDIT-17 — M14 retry-sensitive actions lack end-to-end operation identity

**Severity:** HIGH  
**Confidence:** High for absent identities; individual race effects require local probes  
**Category:** concurrency and unknown outcomes  
**Target execution:** NOT_RUN

**Canonical requirement.** Current M09/M10/M13 store-outcome contracts; audit §§33–34,106–108: timeout is not cancellation and repeat-sensitive writes must reconcile.

**Code location.** [`localflow/v2/curation/review.py` — label; preference writes](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L160-L440); [`localflow/v2/curation/splits.py` — assign](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py#L40-L250); [`localflow/v2/ui/hub.py` — _training_action; background export dispatch](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py#L3040-L3650); [`localflow/v2/learning.py` — approve; undo_approval](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L445-L735). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Label saves and split assignments create new revisions/versions on retry without a supplied stable logical operation ID. Background action tokens suppress stale UI completion, not duplicate mutations. Concurrent exports share a predictable staging path.

**Failure mechanism.** An admitted writer can commit after the caller stops waiting; a second click then creates another revision/assignment or starts another build. Generic UI wording is partly honest, but it cannot reconcile an identity the service never retained.

**Minimal reproduction (local; NOT_RUN).**

1. Hold a writer operation after admission, force the caller’s timeout, let the operation commit, then retry the same visible action.
2. Repeat label, split, approval/undo and export with two barrier-synchronized clicks.
3. Count logical effects, operation receipts and destination ownership; distinguish not_started from outcome_unknown.

**Expected behavior.** One logical action produces one effect and a reconciled receipt. Unknown results are never reported as definite failure; unrelated actions can still proceed.

**Likely actual behavior / verification boundary.** Label saves and split assignments create new revisions/versions on retry without a supplied stable logical operation ID. Background action tokens suppress stale UI completion, not duplicate mutations. Concurrent exports share a predictable staging path. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M09 annotation and M13 usage commands have identity/reconciliation controls. M14’s generic wrapper now accepts kwargs and reports some unknown outcomes correctly.

**Why the oracle misses it.** Wrapper tests do not prove domain-level idempotency; a new version after a retry is not caught by simple append-only checks.

**Regression recommendation.** One logical action produces one effect and a reconciled receipt. Unknown results are never reported as definite failure; unrelated actions can still proceed. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Adopt stable per-action IDs and expected rendered revisions, with writer receipts/read-back reconciliation and per-export destination ownership. Do not copy the UI completion token as a substitute.

**Downstream impact.** M09/M10/M13 consistency patterns; M14 labels/splits/export only.

### M14-AUDIT-24 — Unpin can revoke M14 review-retention leases

**Severity:** HIGH  
**Confidence:** High: explicit role exclusion list omits M14 artifacts  
**Category:** reviewed evidence retention  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.14/training_evidence.md; audit §§25,38: reviewed evidence retention is not a user pin and must not be revoked by Unpin.

**Code location.** [`localflow/v2/training_data.py` — _ANNOTATION_ROLES; _is_pinned; pin](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py#L40-L70); [`localflow/v2/training_data.py` — pin](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/training_data.py#L550-L591); [`localflow/v2/learning.py` — explicit teach lease](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L390-L435); [`localflow/v2/curation/review.py` — graft lease](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L245-L390). The links pin source windows; function names identify the relevant branch.

**Current behavior.** _ANNOTATION_ROLES contains only verbatim_reference and span_correction. M14 span_graft and explicit-teach candidate_observation artifacts can carry forever training leases but fall outside that exemption.

**Failure mechanism.** The UI can mistake reviewed evidence for a user pin; pin(False) revokes any non-exempt forever training lease for the job. Eventual payload loss depends on other live leases/state, but loss of the independent reviewed lease is direct.

**Minimal reproduction (local; NOT_RUN).**

1. Create a reviewed M14 graft and an explicit teach on otherwise finite-retention synthetic jobs.
2. Record every lease and UI pinned state, then invoke Unpin.
3. Advance the synthetic clock and run retention with no unrelated protective lease; compare M09 annotation controls.

**Expected behavior.** Unpin removes only user-pin leases. M14 review-derived leases remain independently identifiable and effective until explicit review/evidence deletion.

**Likely actual behavior / verification boundary.** _ANNOTATION_ROLES contains only verbatim_reference and span_correction. M14 span_graft and explicit-teach candidate_observation artifacts can carry forever training leases but fall outside that exemption. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M09 tests protect the two listed annotation roles; M14 tests cover pending suggestion finite retention.

**Why the oracle misses it.** Neither cross-product challenges M14 reviewed artifacts through M09 Unpin.

**Regression recommendation.** Unpin removes only user-pin leases. M14 review-derived leases remain independently identifiable and effective until explicit review/evidence deletion. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use explicit lease purpose/owner rather than an incomplete role blacklist; extend compatibility and migration carefully without making pending suggestions permanent.

**Downstream impact.** M09 retention controls × M14 artifacts; narrow shared-service repair.

## Medium Findings

### M14-AUDIT-18 — Job-only teaches appear in Review but cannot be selected for action

**Severity:** MEDIUM  
**Confidence:** High: selection precondition conflicts with supported row shape  
**Category:** Hub collection-off workflow  
**Target execution:** NOT_RUN

**Canonical requirement.** learning.md and audit §§19,43–44: a job-keyed teach without a training example must be reviewable without fabricated example identity.

**Code location.** [`localflow/v2/ui/hub.py` — _selected_queue_row; candidate actions](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py#L3140-L3450); [`localflow/v2/curation/review.py` — queue](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L1-L220). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The queue can return a candidate whose example_id is None, but the Hub action-selection path requires a matching selected example identity. The supported collection-off row therefore cannot reach ordinary Approve/Reject through that path.

**Failure mechanism.** Displaying a candidate is not a functioning review workflow. The action authority model is keyed to the Evidence example rather than the rendered candidate/job.

**Minimal reproduction (local; NOT_RUN).**

1. Disable collection, create a retained synthetic job and an explicit teach without an example.
2. Render Review, select that candidate and activate Approve/Reject using native handlers.
3. Confirm no example row is synthesized just to make the action work.

**Expected behavior.** Candidate actions bind to a rendered stable candidate ID and its job/evidence authority even without an example; example-only labels remain clearly unavailable.

**Likely actual behavior / verification boundary.** The queue can return a candidate whose example_id is None, but the Hub action-selection path requires a matching selected example identity. The supported collection-off row therefore cannot reach ordinary Approve/Reject through that path. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** The service tests prove job-only teaches exist and can be listed.

**Why the oracle misses it.** Listing does not exercise the Hub selection precondition.

**Regression recommendation.** Candidate actions bind to a rendered stable candidate ID and its job/evidence authority even without an example; example-only labels remain clearly unavailable. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use candidate-centric rendered selection for learning actions, separate from example-centric annotation selection.

**Downstream impact.** M09 Hub binding; collection-off teaching promised by M14.

### M14-AUDIT-19 — A historical non-abstained label can hide a currently unresolved item

**Severity:** MEDIUM  
**Confidence:** High for queue predicate; final policy must be explicit  
**Category:** effective review judgment  
**Target execution:** NOT_RUN

**Canonical requirement.** Append-only labels plus audit §§14–15: queue state must match the documented effective judgment, not any convenient historical label.

**Code location.** [`localflow/v2/curation/review.py` — _labeled; review queue](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L1-L230). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The reviewed predicate accepts any historical non-abstained label. Saving a later abstained/unresolved judgment does not necessarily return the item to the unresolved queue.

**Failure mechanism.** The implementation has append-only rows but no single effective-label model shared by queue, ASR eligibility and profile interpretation.

**Minimal reproduction (local; NOT_RUN).**

1. On a sampled eligible example save an explicit non-abstained label, then a later abstained one.
2. Refresh the queue and independently inspect revision ordering and the displayed reviewed state.
3. Reverse the order as a positive resolution control; preserve changed_intent policy independently.

**Expected behavior.** Queue status follows a documented effective judgment. A deliberate policy that abstention is non-superseding must be visible, not silently assumed.

**Likely actual behavior / verification boundary.** The reviewed predicate accepts any historical non-abstained label. Saving a later abstained/unresolved judgment does not necessarily return the item to the unresolved queue. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Revision numbering and ordinary label classification are tested.

**Why the oracle misses it.** Append-only storage tests do not assert latest unresolved state against historical resolved rows.

**Regression recommendation.** Queue status follows a documented effective judgment. A deliberate policy that abstention is non-superseding must be visible, not silently assumed. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Define one effective-judgment reducer, with explicit treatment of abstention and blocking labels, and use it in all consumers.

**Downstream impact.** M14 review/ASR/profile consistency; policy finding 30 remains separate.

### M14-AUDIT-20 — Teach rejects punctuation-only corrections before classification

**Severity:** MEDIUM  
**Confidence:** High: pre-classification unchanged test  
**Category:** explicit teaching UX  
**Target execution:** NOT_RUN

**Canonical requirement.** S22/S29.7; audit §§11,18: formatting and punctuation changes are valid review categories even when not vocabulary suggestions.

**Code location.** [`localflow/v2/learning.py` — teach_correction changed-region admission](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L40-L145); [`localflow/v2/curation/classify.py` — classify_observation punctuation handling](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/classify.py#L345-L440). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Word-oriented changed_regions can return no changed words for a punctuation-only edit, causing Teach to report unchanged before the classifier can label punctuation/formatting.

**Failure mechanism.** The classifier supports the category, but the caller’s earlier admission discards it. This need not create an alias or ASR gold to be a useful explicit correction.

**Minimal reproduction (local; NOT_RUN).**

1. Use final text "Wait here." and teach "Wait here!"; also test a comma and a line-break-only edit.
2. Assert exact source/target inequality and call the real Teach path.
3. Use identical text as the true unchanged negative and one word correction as a positive.

**Expected behavior.** An actual punctuation/formatting correction is recorded under the appropriate non-ASR/non-alias category; identical text is refused as unchanged.

**Likely actual behavior / verification boundary.** Word-oriented changed_regions can return no changed words for a punctuation-only edit, causing Teach to report unchanged before the classifier can label punctuation/formatting. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Classifier punctuation tests exercise the classifier directly.

**Why the oracle misses it.** They bypass the Teach admission that discards the input.

**Regression recommendation.** An actual punctuation/formatting correction is recorded under the appropriate non-ASR/non-alias category; identical text is refused as unchanged. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Determine unchanged by exact authorized text equality; let the classifier retain punctuation/formatting observations with suitable offsets and quality.

**Downstream impact.** M14 teaching/review only; no normalization policy redesign.

### M14-AUDIT-21 — Near-spelling semantic opposites can be suggested as recognition corrections

**Severity:** MEDIUM  
**Confidence:** Medium-high: rule-based shape path; exact label must be characterized locally  
**Category:** classifier abstention  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.7/E19.3; audit §§11–12: semantic reversal must not become a recognition suggestion merely from edit distance.

**Code location.** [`localflow/v2/curation/classify.py` — recognition/confusable and negation gates](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/classify.py#L1-L530); [`localflow/v2/learning.py` — _mint_in_op suggestion gate](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L355-L435). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Explicit negation and number/date guards exist, but near-spelling antonyms such as increase→decrease are not equivalent to those guarded markers and can satisfy recognition-shaped edit criteria.

**Failure mechanism.** With retained raw/applied text and reliable-observation status, a small spelling distance can be interpreted as ASR origin despite reversed direction. This is an unverified suggestion risk, not evidence that full ASR training happens automatically.

**Minimal reproduction (local; NOT_RUN).**

1. Set raw and applied text to "Please increase the output level today" and observe "Please decrease the output level today" in a certified synthetic target.
2. Inspect axes, abstention, candidate proposal and downstream ASR gate separately.
3. Use do deploy→do not deploy and is safe→isn't safe as existing-guard controls; use a real spelling correction positive.

**Expected behavior.** No one-click recognition alias is certified from the directional reversal alone; unresolved semantics remain visibly unverified and require explicit human classification.

**Likely actual behavior / verification boundary.** Explicit negation and number/date guards exist, but near-spelling antonyms such as increase→decrease are not equivalent to those guarded markers and can satisfy recognition-shaped edit criteria. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Negation/contraction, number/date and held-out synthetic negative fixtures exist.

**Why the oracle misses it.** Those dictionaries do not establish general semantic equivalence; classifier self-consistency is not an independent intent oracle.

**Regression recommendation.** No one-click recognition alias is certified from the directional reversal alone; unresolved semantics remain visibly unverified and require explicit human classification. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Add independently authored semantic-direction controls and conservative abstention for the demonstrated class; do not advertise general semantic understanding or calibrated accuracy.

**Downstream impact.** M14 suggestion safety; real classification accuracy stays unqualified.

### M14-AUDIT-22 — Approval composition compares raw rather than canonical scopes

**Severity:** MEDIUM  
**Confidence:** High: raw planning comparisons differ from current scope contract  
**Category:** M05/M10 scope integration  
**Target execution:** NOT_RUN

**Canonical requirement.** Current vocabulary.md M05/M10 canonical scope comparisons; audit §§29–32.

**Code location.** [`localflow/v2/learning.py` — _plan_rule; _scope_from_context](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L545-L620); [`docs/v2/contracts/vocabulary.md` — canonical scope comparisons](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/vocabulary.md#L80-L280). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Approval planning searches an existing entry using raw scope values. The vocabulary store applies canonical scope admission, so equivalent bundle/site forms can be missed by the planner and then collide at mutation.

**Failure mechanism.** A valid existing user entry under canonical app scope is not composed with when the candidate carries padded/differently cased equivalent identity. The later M05 refusal can prevent unsafe duplication, but the promised approval workflow fails.

**Minimal reproduction (local; NOT_RUN).**

1. Create an approved entry scoped to com.synthetic.editor.
2. Approve the same canonical with an equivalent padded/cased app scope captured in the candidate; repeat equivalent site spelling.
3. Check entry count, retained user aliases and actual in/out-of-scope normalization.

**Expected behavior.** Equivalent scopes compose into the existing entry under M05 rules; workspace/profile exactness is preserved, and unrelated scopes stay distinct.

**Likely actual behavior / verification boundary.** Approval planning searches an existing entry using raw scope values. The vocabulary store applies canonical scope admission, so equivalent bundle/site forms can be missed by the planner and then collide at mutation. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** App-scoped counterexample and existing-entry approval tests use matching raw strings.

**Why the oracle misses it.** They do not exercise current canonical equivalence at the planning boundary.

**Regression recommendation.** Equivalent scopes compose into the existing entry under M05 rules; workspace/profile exactness is preserved, and unrelated scopes stay distinct. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use the shared M05 canonical scope key for lookup, sandbox context, operation identity and comparison; never normalize workspace/profile beyond the contract.

**Downstream impact.** M05/M10 seam only; preserve their accepted admission implementation.

### M14-AUDIT-23 — A second profile signature can suppress a needed vocabulary refresh

**Severity:** MEDIUM  
**Confidence:** Medium-high: two-stage signature mismatch; local reproduction required  
**Category:** idle profile invalidation  
**Target execution:** NOT_RUN

**Canonical requirement.** profile.md; audit §§87–89: every output-bearing change must recompute once, unchanged ticks must read no transcripts/write no snapshot.

**Code location.** [`localflow/v2/profile.py` — _input_signature; evidence-signature unchanged decision](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py#L1-L610). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The fast input signature includes vocabulary revision information, but the later evidence-signature/unchanged decision does not cover every vocabulary field that changes measured technical terms. It can remember a new fast signature without publishing newly derived terms.

**Failure mechanism.** Change a vocabulary canonical while retaining row count and usage totals. The fast gate notices a change; the later skip can declare evidence unchanged and permanently retain the old term until another input changes.

**Minimal reproduction (local; NOT_RUN).**

1. Generate a profile with one eligible, used vocabulary term.
2. Edit only its canonical/approved output-bearing metadata through M05, keeping counts and usage totals fixed.
3. Run only_if_changed twice and compare technical terms, input signatures and snapshot count.

**Expected behavior.** The first changed tick publishes exactly one correctly updated snapshot or explicitly invalidates the affected field; the next unchanged tick performs zero transcript reads and zero writes.

**Likely actual behavior / verification boundary.** The fast input signature includes vocabulary revision information, but the later evidence-signature/unchanged decision does not cover every vocabulary field that changes measured technical terms. It can remember a new fast signature without publishing newly derived terms. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Tests cover unchanged ticks, metadata-only changes and snapshot churn on selected inputs.

**Why the oracle misses it.** Count/usage changes do not isolate a canonical edit held constant across the secondary signature.

**Regression recommendation.** The first changed tick publishes exactly one correctly updated snapshot or explicitly invalidates the affected field; the next unchanged tick performs zero transcript reads and zero writes. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use one complete versioned dependency signature or ensure every secondary equivalence test covers the same output-bearing inputs; never mark an unprocessed change consumed.

**Downstream impact.** M05 metadata consumed by M14; retain the strong counters-only idle fast path.

### M14-AUDIT-25 — A supplied --db argument breaks the export CLI

**Severity:** MEDIUM  
**Confidence:** High: argparse type mismatch visible in source  
**Category:** CLI robustness  
**Target execution:** NOT_RUN

**Canonical requirement.** A functioning safe local export tool; audit §73 and M14 command surface.

**Code location.** [`scripts/v2/export_dataset.py` — main argument parsing and Store construction](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/scripts/v2/export_dataset.py#L1-L180). The links pin source windows; function names identify the relevant branch.

**Current behavior.** --db has a Path default but no Path conversion for a supplied argument. The CLI later accesses args.db.parent, so a user-supplied string path raises before export.

**Failure mechanism.** Argparse does not convert a provided string merely because the default is a pathlib.Path. Default-path invocation and API-level export tests miss this branch.

**Minimal reproduction (local; NOT_RUN).**

1. Run the CLI against a synthetic store with an explicit --db path and supported output argument.
2. Run the equivalent default/parsed-Path positive control without touching the live DB.

**Expected behavior.** An explicit synthetic database path parses correctly, uses protected migration/backup discipline, and reaches export or a domain refusal rather than AttributeError.

**Likely actual behavior / verification boundary.** --db has a Path default but no Path conversion for a supplied argument. The CLI later accesses args.db.parent, so a user-supplied string path raises before export. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** The CLI now supplies a migration backup directory; historical no-backup concern is repaired.

**Why the oracle misses it.** Backup construction is not exercised with the supplied-argument type.

**Regression recommendation.** An explicit synthetic database path parses correctly, uses protected migration/backup discipline, and reaches export or a domain refusal rather than AttributeError. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Use type=pathlib.Path or explicit conversion at admission; add CLI subprocess coverage and backup/no-live-store guards.

**Downstream impact.** M14 tooling only.

### M14-AUDIT-26 — Historical M14 evidence still contains absolute private paths

**Severity:** MEDIUM  
**Confidence:** High: visible current acceptance file  
**Category:** committed evidence privacy  
**Target execution:** NOT_RUN

**Canonical requirement.** INDEX.md privacy rules; audit §§74,96,134: no home/repository/session paths in committed evidence.

**Code location.** [`docs/v2/acceptance/M14/results.json` — environment and human_verification](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/acceptance/M14/results.json). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The current historical M14 results record contains absolute user home/repository paths in environment and manual instructions.

**Failure mechanism.** Historical evidence is still distributed from current main. Keeping measured results intact does not require retaining private path strings.

**Minimal reproduction (local; NOT_RUN).**

1. Scan only M14-owned evidence/docs and their current benchmark outputs for full home paths and path fragments.
2. Verify matches manually and distinguish synthetic placeholders from personal locations.

**Expected behavior.** Forward-redact private paths to documented placeholders while preserving historical outcomes, source attribution and a redaction note. Do not rewrite Git history.

**Likely actual behavior / verification boundary.** The current historical M14 results record contains absolute user home/repository paths in environment and manual instructions. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M12/M13 addenda already demonstrate forward redaction of their own historical results.

**Why the oracle misses it.** The older M14 acceptance artifact has not received that owner-specific cleanup.

**Regression recommendation.** Forward-redact private paths to documented placeholders while preserving historical outcomes, source attribution and a redaction note. Do not rewrite Git history. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Redact the M14-owned occurrences, add an explicit privacy_redactions record and strengthen the evidence pre-commit scan to catch truncated prefixes.

**Downstream impact.** M14 documentation/evidence only; do not sweep unrelated historical owners in this remediation.

## Low Findings

No Low-severity item is separately assigned. Narrow robustness issues with material workflow effects are classified Medium; unproven properties remain Test Gaps rather than padded defects.

## Test Gaps

### M14-AUDIT-27 — Important negative suites lack independent end-to-end semantic oracles

**Severity:** TEST GAP  
**Confidence:** High: inspected tests establish narrower properties  
**Category:** test-oracle validity  
**Target execution:** NOT_RUN

**Canonical requirement.** E09/E13/E19; audit §§114–115,119: every refusal cohort needs a true positive; mutation kills need reached branches and semantic failure.

**Code location.** [`tests/v2/personalization/test_profile.py` — no-profile-injection and card tests](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/personalization/test_profile.py#L1-L330); [`tests/v2/ui/test_training_review_hub.py` — preference/export functional tests](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/ui/test_training_review_hub.py#L1-L500); [`tests/v2/training/test_dataset_export.py` — round trip and negatives](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/tests/v2/training/test_dataset_export.py#L1-L610). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The profile no-injection test compares two otherwise identical normalizer calls, not a personalization-disabled coordinator run. UI preferences are not graded by rendered texts/order. Export validation uses the same reduced schema without independent reconstruction of missing inputs.

**Failure mechanism.** Identity/no-op or self-consistent wrong implementations can pass selected assertions. This is not a claim that every existing test is vacuous: learning pipeline effects, audio hashes, prefer_b and selected-source purge controls are substantive.

**Minimal reproduction (local; NOT_RUN).**

1. Inject a profile-to-cleanup prompt read, a swapped A/B binding and a same-checksum semantic lineage corruption independently.
2. Require the actual affected branch to be reached and an independent expected-output assertion to fail.
3. Pair each refusal case with an eligible same-shape control and record population counts.

**Expected behavior.** The mutation suite rejects intended semantic deviations without counting import/crash failures. Real coordinator, task reconstruction and card-support oracles are used.

**Likely actual behavior / verification boundary.** The profile no-injection test compares two otherwise identical normalizer calls, not a personalization-disabled coordinator run. UI preferences are not graded by rendered texts/order. Export validation uses the same reduced schema without independent reconstruction of missing inputs. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Existing historical suite inventory and source were inspected; no suite executed here.

**Why the oracle misses it.** Service calls and equal calls do not prove native perception or causal absence of profile influence.

**Regression recommendation.** The mutation suite rejects intended semantic deviations without counting import/crash failures. Real coordinator, task reconstruction and card-support oracles are used. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Write fail-first owning regressions with independent source/intent/family/choice oracles; keep structural, portable, native and manual results separate.

**Downstream impact.** M14 qualification across all surfaces, not a reason to reopen unrelated milestones.

### M14-AUDIT-28 — M14 benchmark reports lack independent work-validity and current-tree measurements

**Severity:** TEST GAP  
**Confidence:** High: benchmark source and historical record inspected  
**Category:** performance validity  
**Target execution:** NOT_RUN

**Canonical requirement.** E11/M14 benchmark requirements; audit §§109–113,135: work before speed, correct populations, current SHA and continuous writer probes.

**Code location.** [`scripts/v2/benchmark_m14.py` — fixture generation, timing and report](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/scripts/v2/benchmark_m14.py#L1-L510); [`docs/v2/acceptance/M14/results.json` — historical benchmark](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/acceptance/M14/results.json). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The harness performs real work and copies audio, but some reported populations/bytes are constants, timed mining/sampling results are not independently reconciled, and metadata is insufficient for current qualification. Historical September 24 timings predate M12/M13 changes.

**Failure mechanism.** An observation-row count can exceed actually changed/mineable observations; a no-op component may look fast without violating a separate validity gate. Current performance, memory and worst dictation wait were not measured in this audit.

**Minimal reproduction (local; NOT_RUN).**

1. Generate the nominal 10k/1k/large-audio workload and independently count actual unique eligible examples, changed observations, emitted candidates, sample membership, split membership and copied bytes.
2. Disable one component without crashing; the benchmark must return invalid before reporting success.
3. Run isolated reference-Mac timing only after validity passes, recording full environment and writer overlap.

**Expected behavior.** No skipped/no-op component qualifies. Report measured populations, wall time, p50/p95/p99 where justified, peak memory, writer hold/wait and copied audio throughput separately.

**Likely actual behavior / verification boundary.** The harness performs real work and copies audio, but some reported populations/bytes are constants, timed mining/sampling results are not independently reconciled, and metadata is insufficient for current qualification. Historical September 24 timings predate M12/M13 changes. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** The existing benchmark includes continuous write probes and real audio/validator work, which should be preserved.

**Why the oracle misses it.** Constants and same-code shape checks can survive omitted component work; historical timings are not current-tree evidence.

**Regression recommendation.** No skipped/no-op component qualifies. Report measured populations, wall time, p50/p95/p99 where justified, peak memory, writer hold/wait and copied audio throughput separately. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Add per-component independent validity gates/no-op negatives; freeze exact production SHA and run alone on Daniel’s actual Mac.

**Downstream impact.** M14 background contention with dictation; M15 performance evidence remains pending.

### M14-AUDIT-29 — Repository-wide caller and native qualification remain unproven

**Severity:** TEST GAP  
**Confidence:** Certain limitation, not a production defect  
**Category:** audit coverage boundary  
**Target execution:** NOT_RUN

**Canonical requirement.** Audit §§6,104,128,131: GitHub search is not exhaustive; local rg and native qualification required.

**Code location.** [`localflow/app.py` — M14 service wiring and coordinator integrations](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/app.py); [`localflow/v2/ui/hub.py` — M14 panes and actions](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/ui/hub.py#L3000-L3650). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The current core M14 files, relevant contracts, addenda and selected callers/tests were read through the connector. Large responses/search were incomplete; a full tracked-file local rg inventory, native execution and the target corpus were not performed.

**Failure mechanism.** No claim that all production callers are enumerated, all source lines are covered, or any native workflow passed can follow from connector search or historical green records.

**Minimal reproduction (local; NOT_RUN).**

1. On the audited local checkout run tracked-file rg for every service, predicate, table and manifest producer/consumer listed in the handoff.
2. Resolve dynamic aliases and every actual caller; record a reviewed inventory before editing.
3. Run portable/native scenarios under isolation with owned windows, never Daniel’s personal data.

**Expected behavior.** A complete local caller ledger and fresh native results exist before completion. A retrieval gap is reported rather than treated as absence.

**Likely actual behavior / verification boundary.** The current core M14 files, relevant contracts, addenda and selected callers/tests were read through the connector. Large responses/search were incomplete; a full tracked-file local rg inventory, native execution and the target corpus were not performed. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Source-level M14 paths and several actual coordinator/UI integrations were inspected; no target code executed.

**Why the oracle misses it.** GitHub index misses and clipped large-file responses cannot establish exhaustiveness.

**Regression recommendation.** A complete local caller ledger and fresh native results exist before completion. A retrieval gap is reported rather than treated as absence. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Close the inventory and native proof gaps locally, preserving static findings as hypotheses to reproduce rather than presumed verdicts.

**Downstream impact.** Every narrow integration seam; no M15 or manual-check claims.

## Design Concerns

### M14-AUDIT-30 — Historical blocking labels conflict with “while unresolved” semantics

**Severity:** DESIGN CONCERN  
**Confidence:** High: explicit contract versus docstring tension  
**Category:** label policy adjudication  
**Target execution:** NOT_RUN

**Canonical requirement.** Current learning.md; review.py docstring; audit §§14–15: do not invent latest-wins, especially for changed_intent.

**Code location.** [`docs/v2/contracts/learning.md` — ASR promotion policy](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/learning.md); [`localflow/v2/curation/review.py` — verified_asr_eligible_in](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py#L85-L165). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The current contract/SQL treat any historical changed_intent, ambiguous or user_rewrite label as blocking; nearby prose describes ambiguity/rewrite as blocking while unresolved.

**Failure mechanism.** There is no explicit resolution model that can clear an old ambiguous label. Conversely, blindly switching to latest-only would violate intentionally permanent changed_intent policy.

**Minimal reproduction (local; NOT_RUN).**

1. Construct ambiguous→explicit recognition and user_rewrite→explicit resolved judgment histories; separately changed_intent→recognition.
2. Record current SQL results and all governing prose before selecting a resolution policy.

**Expected behavior.** A versioned decision defines permanent versus resolvable blockers, abstention supersession and what explicit resolution proves. Tests are decision-bound; no policy-dependent scenario is graded against an invented rule.

**Likely actual behavior / verification boundary.** The current contract/SQL treat any historical changed_intent, ambiguous or user_rewrite label as blocking; nearby prose describes ambiguity/rewrite as blocking while unresolved. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Historical-blocking SQL and append-only labels exist.

**Why the oracle misses it.** A test that merely repeats SQL cannot resolve a contradictory product policy.

**Regression recommendation.** A versioned decision defines permanent versus resolvable blockers, abstention supersession and what explicit resolution proves. Tests are decision-bound; no policy-dependent scenario is graded against an invented rule. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Adjudicate and document a minimal effective-judgment model, then implement shared semantics with irreversible changed_intent protection if retained by policy.

**Downstream impact.** M14 queue/ASR/profile/export; requires explicit local decision record.

### M14-AUDIT-31 — Task-keyed transform and preference rows are outside family partitions

**Severity:** DESIGN CONCERN  
**Confidence:** High: documented current behavior conflicts with broader canonical guarantee  
**Category:** split qualification policy  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.11/S29.13/E19.5 versus dataset_exports.md task-keyed exception; audit §§51,55,57.

**Code location.** [`docs/v2/contracts/dataset_exports.md` — task-keyed rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/dataset_exports.md); [`localflow/v2/curation/export.py` — _transform_rows; _preference_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L310-L450). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Transform and preference records are intentionally task-keyed and unsplit in the current contract. They are not filtered like example-based ASR/cleanup/graft rows.

**Failure mechanism.** A manifest listing selected partitions cannot by itself establish family isolation for all included tasks. Calling this an accidental missing SQL condition would ignore the explicit contract exception.

**Minimal reproduction (local; NOT_RUN).**

1. Create a transform/preference pair derived from a known recording family; export one requested partition.
2. Trace whether family identity and exposure follow into the task rows, without fabricating a family from a task hash.

**Expected behavior.** Either extend a trustworthy family/split model to these task rows or expose them as explicitly unpartitioned and not holdout-qualified. The exception must be reconciled with canonical M14 acceptance.

**Likely actual behavior / verification boundary.** Transform and preference records are intentionally task-keyed and unsplit in the current contract. They are not filtered like example-based ASR/cleanup/graft rows. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Tests affirm current task-keyed output and ordinary example-family splits.

**Why the oracle misses it.** Passing each separate contract does not prove the cross-task family guarantee.

**Regression recommendation.** Either extend a trustworthy family/split model to these task rows or expose them as explicitly unpartitioned and not holdout-qualified. The exception must be reconciled with canonical M14 acceptance. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Write an explicit decision and migration/compatibility plan for task-family lineage; do not invent linkages by proximity or text equality.

**Downstream impact.** M11 task origins, M12 note lineage, M15 split qualification.

### M14-AUDIT-32 — Cleanup records with missing exact model inputs are still named supervised

**Severity:** DESIGN CONCERN  
**Confidence:** High: explicit lower-level allowance versus canonical reconstruction requirement  
**Category:** dataset qualification tiers  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.12/S29.13 and E19.5 versus dataset_exports.md missing-prompt allowance.

**Code location.** [`localflow/v2/curation/export.py` — _cleanup_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L280-L338); [`docs/v2/contracts/dataset_exports.md` — cleanup reconstruction note](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/dataset_exports.md). The links pin source windows; function names identify the relevant branch.

**Current behavior.** The current exporter deliberately permits cleanup records with a missing exact prompt/model-input artifact and reports a missing reason. That is honest missingness, but it is not full conditional-task reconstruction.

**Failure mechanism.** A text-pair research view can be useful while failing the stronger qualified-supervised contract. A missing-reason field alone must not count as proof that the absent task input was retained.

**Minimal reproduction (local; NOT_RUN).**

1. Create explicit correct intended-writing evidence with raw/normalized/applied text but no exact cleanup prompt.
2. Export and run the independent reconstruction check; distinguish text-pair availability from model-task qualification.

**Expected behavior.** An explicit decision names the tier and permitted use, or the qualified view refuses missing required inputs. Readiness and README use the same distinction.

**Likely actual behavior / verification boundary.** The current exporter deliberately permits cleanup records with a missing exact prompt/model-input artifact and reports a missing reason. That is honest missingness, but it is not full conditional-task reconstruction. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Existing tests deliberately assert the honest prompt gap.

**Why the oracle misses it.** Those tests validate the exception rather than demonstrate the canonical reconstruction property.

**Regression recommendation.** An explicit decision names the tier and permitted use, or the qualified view refuses missing required inputs. Readiness and README use the same distinction. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Preserve useful incomplete research data under a clearly separate tier; require exact retained inputs for any fully qualified view unless the canonical requirement is explicitly revised.

**Downstream impact.** M07 input capture consumed by M14; M15 G10 not waived silently.

### M14-AUDIT-33 — Technical-term statistics are not exclusively retained-speech evidence

**Severity:** DESIGN CONCERN  
**Confidence:** High: source population distinction is explicit in code/contracts  
**Category:** Your Voice source interpretation  
**Target execution:** NOT_RUN

**Canonical requirement.** S22/profile.md and current analytics.md; audit §§81–83: distinguish retained-speech measures from independent vocabulary usage counters.

**Code location.** [`localflow/v2/profile.py` — technical terms and cards](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py#L180-L430); [`docs/v2/contracts/analytics.md` — Delete Usage and independent occurrence counters](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/docs/v2/contracts/analytics.md). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Technical terms derive from global vocabulary usage counters rather than exclusively the profile-eligible speech cohort. Current M13 policy deliberately leaves independent vocabulary occurrence counters intact when Usage is deleted.

**Failure mechanism.** It would be incorrect to claim these counters necessarily violate Delete Usage. It is also incorrect to imply that every displayed term is supported by the cited retained utterances or that the field measures only this speech population.

**Minimal reproduction (local; NOT_RUN).**

1. Give a vocabulary term usage only outside the eligible speech cohort; compute profile and inspect card wording/citations.
2. Delete Usage while retaining dictionary occurrence metadata; verify app/hour/mode redaction and classify the independent term field accurately.

**Expected behavior.** UI/data explicitly state the source population and deletion semantics. Term-specific claims cite actual supporting examples or are presented only as independent dictionary usage, not “you say” evidence.

**Likely actual behavior / verification boundary.** Technical terms derive from global vocabulary usage counters rather than exclusively the profile-eligible speech cohort. Current M13 policy deliberately leaves independent vocabulary occurrence counters intact when Usage is deleted. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** M13 same-op usage-derived field redaction and unknown metric treatment are present.

**Why the oracle misses it.** An aggregate vocabulary counter and any vocabulary-hit example do not necessarily support a particular term claim.

**Regression recommendation.** UI/data explicitly state the source population and deletion semantics. Term-specific claims cite actual supporting examples or are presented only as independent dictionary usage, not “you say” evidence. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Choose speech-derived computation or clearly labeled independent dictionary-usage presentation; document how each source is cleared and invalidate cards accordingly.

**Downstream impact.** Preserve accepted M13 semantics; repair M14 interpretation without silently resetting personal vocabulary.

### M14-AUDIT-34 — Rejection identity needs an explicit canonical/scope policy

**Severity:** DESIGN CONCERN  
**Confidence:** High: exact-string global pair comparison observed  
**Category:** suppression policy  
**Target execution:** NOT_RUN

**Canonical requirement.** S11/learning.md and audit §§37–38: rejected pairs should not reappear under the adopted policy; do not invent scope-specific behavior.

**Code location.** [`localflow/v2/learning.py` — _mint_in_op suppression query; reject](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L355-L435); [`localflow/v2/learning.py` — reject](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L644-L680). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Suppression is global for an exact stored alias/canonical pair and uses exact strings, while dictionary matching uses canonical/case-aware comparison.

**Failure mechanism.** Equivalent case forms may escape rejection, whereas identical terms in an unrelated scope remain suppressed. Whether that is intended global preference or a scoped preference is not fully resolved by the implementation alone.

**Minimal reproduction (local; NOT_RUN).**

1. Reject a synthetic alias/canonical pair in app A.
2. Mine same pair/same scope, case-equivalent pair/same scope, and same pair/app B.
3. Record exact intended policy before grading scope-dependent outcomes.

**Expected behavior.** A versioned suppression key and disclosed scope policy govern all three cases; permitted preference metadata contains only necessary terms/IDs.

**Likely actual behavior / verification boundary.** Suppression is global for an exact stored alias/canonical pair and uses exact strings, while dictionary matching uses canonical/case-aware comparison. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Exact pair reappearance is tested.

**Why the oracle misses it.** Exact-string fixtures do not challenge equivalence or establish a scope policy.

**Regression recommendation.** A versioned suppression key and disclosed scope policy govern all three cases; permitted preference metadata contains only necessary terms/IDs. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Adjudicate canonical identity and scope; share comparison semantics with M05 where appropriate without silently broadening suppression.

**Downstream impact.** M14 rejected suggestions; M05 comparison semantics only.

### M14-AUDIT-35 — An empty counterexample set must not imply safety qualification

**Severity:** DESIGN CONCERN  
**Confidence:** High: empty-set early return; qualification interpretation needs a decision  
**Category:** counterexample qualification  
**Target execution:** NOT_RUN

**Canonical requirement.** S11/E13; audit §§31–32: a vacuous scoped check cannot certify safety.

**Code location.** [`localflow/v2/learning.py` — approve; _counterexample_flips](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py#L445-L660). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Counterexample checking returns no flips when no counterexamples are supplied. Its sandbox contains the proposed entry and matching scope, not necessarily the full current effective dictionary.

**Failure mechanism.** “No observed adverse hit” is different from “tested safe.” The existing app-scoped positive-control test is not vacuous, but an empty user action still requires honest population/coverage semantics.

**Minimal reproduction (local; NOT_RUN).**

1. Approve with no counterexamples, then with an in-scope known adverse phrase, and with a phrase outside scope under an explicit scoped fixture.
2. Inspect recorded tested count, effective snapshot identity, result and user wording.

**Expected behavior.** Empty evidence is labeled untested, not safe; any required counterexample gate has a nonzero independently checked population and a real candidate-applying positive control.

**Likely actual behavior / verification boundary.** Counterexample checking returns no flips when no counterexamples are supplied. Its sandbox contains the proposed entry and matching scope, not necessarily the full current effective dictionary. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** The app-scoped counterexample test genuinely exercises the candidate and refuses a flip.

**Why the oracle misses it.** One populated test does not validate empty-set qualification or interaction with the effective dictionary.

**Regression recommendation.** Empty evidence is labeled untested, not safe; any required counterexample gate has a nonzero independently checked population and a real candidate-applying positive control. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Record tested population/snapshot and qualification tier; decide whether approval may remain an explicitly untested user choice, rather than silently certifying safety.

**Downstream impact.** M05 snapshot composition and M14 approval evidence.

### M14-AUDIT-36 — Single-candidate acceptance history needs an effective-target policy

**Severity:** DESIGN CONCERN  
**Confidence:** High for any-accept query; whether undo revokes target requires adjudication  
**Category:** transform supervised judgment  
**Target execution:** NOT_RUN

**Canonical requirement.** S29.10/S29.12 and transforms.md; audit §61: explicit qualified target required; do not infer preference policy from another judgment type.

**Code location.** [`localflow/v2/curation/export.py` — _transform_rows](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py#L310-L355); [`localflow/v2/transforms_store.py` — record_observation](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/transforms_store.py#L490-L554). The links pin source windows; function names identify the relevant branch.

**Current behavior.** Transform-supervised selection can find a historical accept for a candidate. Preference pairs explicitly use latest judgment; the single-candidate accept/reject/undo target semantics are not equally explicit.

**Failure mechanism.** An accept followed by undo or reject may still provide a supervised target. Undo of insertion is not necessarily a correction of writing quality, so imposing latest-wins without policy would be an unsupported change.

**Minimal reproduction (local; NOT_RUN).**

1. Record accept→undo, accept→reject and auto-applied-without-accept histories on the same candidate.
2. Inspect export and document whether each action changes target approval or only insertion state.

**Expected behavior.** One versioned decision distinguishes target acceptance from insertion undo and governs export accordingly; automatic application alone never fabricates human approval.

**Likely actual behavior / verification boundary.** Transform-supervised selection can find a historical accept for a candidate. Preference pairs explicitly use latest judgment; the single-candidate accept/reject/undo target semantics are not equally explicit. This is a static prediction; target execution is NOT_RUN.

**Existing coverage.** Explicit-accept and auto-applied path metadata tests exist.

**Why the oracle misses it.** Pairwise latest-wins tests do not establish single-candidate target semantics.

**Regression recommendation.** One versioned decision distinguishes target acceptance from insertion undo and governs export accordingly; automatic application alone never fabricates human approval. Require a populated positive companion and an independent semantic assertion.

**Narrow repair direction.** Separate target approval from insertion actions where needed; export the effective qualified target decision and its lineage.

**Downstream impact.** M11 candidate observations consumed by M14; no transform engine redesign.

## Areas Verified Strong

“Verified” here means supported by inspected current source, **not newly executed**. Preserve these properties in every repair:

1. Pending/sampled/profile-only observations do not directly mutate M05 vocabulary; actual approval is the pipeline-affecting step in the inspected learning path.
2. Main observation payloads are governed artifacts; machine-mined candidate retention is finite. Proposed pair preference metadata is not confused with a transcript copy.
3. Store delete-everywhere reaches job-keyed candidates, including collection-off cases, and clears linked profile snapshots; M12 provides note deletion fences.
4. Label/annotation writers reject expired, excluded, quarantined and deleted examples rather than using labels as Restore.
5. Ordinary grafts remain weak/partial. An intended-writing judgment is not an audio-verbatim judgment.
6. Same-task preference keys are checked, latest pair judgments are used, and prefer_b maps to B in current export serialization.
7. Normal new family assignments preserve exposure across earlier versions; partitions remain separate from review tags.
8. Export checks ordinary destination safety, streams audio, checks copied digests, computes fingerprints, and distinguishes selected-source purge from unrelated deletion before its final fence.
9. Profile computation is chunked and has an unchanged fast gate; below-floor interpretation is withheld. Usage-derived fields and unknown self-correction/hour semantics follow the accepted M13 contract in the inspected paths.
10. Export CLI supplies migration backup discipline; historical no-backup allegations are not blindly reopened. Current CLAUDE.md requires completed remediation branches to merge into canonical main and forbids incomplete merges/force pushes.

The associated residual findings are deliberately narrower than these protections. [learning.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/learning.py) [review.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/review.py) [splits.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/splits.py) [export.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/curation/export.py) [profile.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/profile.py) [store.py](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/localflow/v2/store.py) [CLAUDE.md](https://github.com/scalinity/LocalFlow/blob/1e351d723d11a7bb5cb333c93a5daaca416f93d0/CLAUDE.md).

## Adversarial Corpus Summary

The separate **LocalFlow_M14_Adversarial_Corpus.json** contains:

| Inventory | Count | Status |
|---|---:|---|
| Required categories | 30 | All represented |
| Parameterized semantic case specifications | 234 | NOT_RUN |
| Deterministic stateful probes | 34 | NOT_RUN |
| Metamorphic relations | 14 | NOT_RUN |
| Mutation specifications | 32 | NOT_RUN |
| Finding reproduction/decision records | 36 | NOT_RUN |
| Executed/passed/failed target cases | 0 / 0 / 0 | No target execution |

The categories are: explicit_teaching, m08_observation_mining, m12_note_mining, candidate_liveness, classifier_axes, human_labels, asr_gate, artifact_ownership, partial_grafts, approval, undo, counterexamples, suppression, sampling, preferences, family_splits, exposed_test_families, dataset_eligibility, export_safety, export_concurrency, offline_validation, readiness, profile_eligibility, profile_cards, profile_invalidation, m13_usage_redaction, idle_profile_pass, hub_actions, privacy, performance_validity. Fixture recipes use synthetic temporary stores, generated tone WAVs, explicit origin maps and distinct canaries. They intentionally require binding to actual current producer roles/APIs rather than inventing artifact-role names or a nonexistent ExportService. Schema/ID/reference validation of this JSON is not a target-test pass.

All 28 required stateful probes from the user brief appear as S001–S028; S029–S034 add revocation-between-approval-phases, post-fence purge, concurrent alias edits, duplicate exports, review Unpin and stale-snapshot exclusion. The corpus remains immutable specification; the local run writes separate execution results at base and repaired SHAs.

## Stateful / Metamorphic / Mutation Plan

The local adapter must expose deterministic authority boundaries without deadlocking the single writer. When a second writer must commit, pause the first actor **between** writer operations; never hold that writer while waiting for another queued writer. Record branch reachability, commit order and semantic assertions, not timing guesses.

First establish a nonempty eligible positive fixture. Then execute the named invalidating action and compare exact identities, payloads, leases and output membership. For deletion tests, include an unrelated-deletion positive to prevent “always abort” implementations from passing. For ASR/cleanup corruption tests, include intact A and B controls to prevent “nothing is eligible” false greens. For profile tests, exercise exactly the floor and above it; no below-floor-only suite qualifies cards.

Metamorphic relations cover approval locality, reversible learning, rejection stability, evidence deletion, reviewed-resolution policy, family permutation, exposure, profile floor, usage redaction, export dependency locality, display permutation, idle idempotence, canonical scope equivalence and pack relocation. Do not impose false invariants such as every percentage decreasing after deletion; the invariant is retained support and honest recomputation.

For each mutant record: mutation applied, intended branch reached, independent semantic assertion evaluated, and outcome. **KILLED = reached AND semantic assertion failed.** Import errors, setup failures, deadlocks and crashes are INVALID, not kills. Policy-dependent mutants require a decision ID; an inapplicable mutant is not silently counted as a pass. Every base/final result references the exact production SHA and adapter hash.

## Downstream Impact

**M05:** use its admitted vocabulary entries, canonical scope keys, immutable revisions and expected-revision updates; test actual snapshot output before/after approval. **M09/M10:** retain stable rendered IDs, strict admission and honest unknown outcomes; add M14 operation/source identities rather than bypassing them. **M11:** consume frozen transform task/input/output and actual applied-final decisions; preserve the current transformed-final Teach guard unless explicit exact-stage support is approved. **M12:** consume occurrence-safe per-dictation region authority and deletion fences; do not reimplement weaker provenance. **M13:** preserve its reconciled populations and same-operation usage redaction; align M14 task eligibility and source labeling. **M15:** remains blocked on current M14 qualified evidence, portable reconstruction, exposure integrity, native functionality and valid current benchmark evidence—not on a fabricated model-training result.

Previously recorded M11/manual/model-backed limits remain inherited. This audit neither clears those gates nor expands remediation into them. Cross-milestone compatibility tests target only M14’s consumption of accepted contracts.

## Recommended Repair Order

1. **Freeze and adjudicate.** Safely sync, record local/remote SHAs, verify replay-aware ancestry and exhaustive caller inventory, bind corpus, and reproduce the base before any fix.
2. **Close destructive/unauthorized boundaries.** 02 staging ownership, 05 managed audio paths, 01 shared evidence qualification, 03 profile artifact fence, 04 all-history exposure on new exports, 06 publication fence.
3. **Make human actions authoritative and reversible.** 09/10/17 operation receipts and exact deltas; 11/12 immutable visible sources; 13 per-region note authority; 16/18 rendered candidate/pair UX; 24 review-purpose retention; 15 governed counterexamples.
4. **Reconcile decisions before eligibility changes.** 30 historical label resolution, 31 task-family partitions, 32 exact-input qualification tiers, 33 term provenance, 34 suppression identity, 35 counterexample qualification, 36 target acceptance versus insertion undo.
5. **Unify qualified datasets.** 07/08 complete retained task closure and independent validator; 14 shared readiness tiers; 19 effective queue judgment; 20/21 classification admission/semantic negatives; 22 canonical scope composition; 23 complete profile signatures; 25 CLI path parsing.
6. **Qualify and publish evidence.** 26 forward privacy redaction; 27–29 independent oracles, full local caller/native coverage and current valid benchmark; compatibility sweep; frozen-SHA fresh-context independent review; reconcile its findings; update M14 contracts/handoff/results/runbook/orchestration; commit/push/merge only under current CLAUDE.md completion rules.

Do not combine unrelated fixes merely to reduce commit count. Do not change the test oracle to agree with production unless a documented policy adjudication requires it. Freeze the failing base evidence before the branch is repaired.

## M14 Readiness Verdict

### C. Significant learning/eligibility/curation weaknesses

This is a current-tree static verdict supported by concrete authority, filesystem, derived-content and holdout-exposure paths. The number of cross-cutting boundaries makes **B — Ready after targeted repairs** too optimistic before reproduction and convergence. **A — Strong/no remediation needed** is contradicted by the inspected source. **D — Audit inconclusive** would incorrectly hide the substantial confirmed source-level mechanisms, although exhaustive local caller and runtime qualification remain unproven.

The path forward is bounded remediation of M14 and its narrow consumers, not a wholesale redesign. Every material allegation must first be reproduced, refuted or narrowed locally. A truthful final state can become `LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION` only after all confirmed automatable defects, corpus and independent-review gates, native functional checks that can safely run, current valid benchmark, compatibility, documentation and authorized Git integration are complete. Daniel’s genuine manual checks remain pending.

**No M15, no Quiet Editorial, no GitHub modification, and no manual verification was performed by this audit.** The three deliverables terminate the GPT audit.
