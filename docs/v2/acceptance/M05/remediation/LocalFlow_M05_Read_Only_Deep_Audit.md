# LocalFlow V2 — M05 Read-Only Deep Audit
## Scoped Vocabulary and Dictionary Management

**Repository:** `scalinity/LocalFlow`  
**Audited canonical main:** `267d1c25910328f72afff7096eb2a442e96a5174`  
**Audit date:** September 25, 2026  
**Audit state:** `READ_ONLY_AUDIT_COMPLETE — SOURCE ANALYSIS; RUNTIME REPRODUCTIONS NOT PERFORMED`  
**Readiness verdict:** **C. Significant vocabulary/scope/evidence weaknesses**

## Executive Assessment

M05 has a useful deterministic foundation, but it does not yet substantiate its strongest claim: that every applied rule belongs to the exact occurrence, destination and immutable dictionary state recorded for that job. The most consequential source-confirmed mechanisms are a multiword alias crossing clause boundaries and a refresh-error fallback that can reuse another job’s scoped dictionary. The current matcher also has an order-dependent canonical no-op shield; the snapshot and HintSet are not deeply frozen; and vocabulary updates validate stale caller-side state outside the writer operation.

The report contains **20 findings: 2 Critical, 7 High, 5 Medium, 5 Test Gaps and 1 Low**. These are not 20 runtime-reproduced failures. Material mechanisms are derived from the pinned source; exact end-to-end outputs and interleavings remain to be reproduced. Policy questions are separated into six design concerns rather than silently scored as defects. The remediation session must independently adjudicate every finding before changing code.

This is not a recommendation to disable the dictionary. Successful-path scope keys include all four contextual dimensions; the cache is bounded; approved/enabled filtering and ordinary same-scope collision masking are real; normal scope upgrades rebuild from frozen entries rather than the live store; and the current ASR adapter honestly declines unsupported hints. Preserve those properties while repairing ownership, failure-path isolation and evidence identity. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S08: ASR capability boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py)

### Deliverables

- `LocalFlow_M05_Read_Only_Deep_Audit.md` — this report, including the full finding register and source index.
- `LocalFlow_M05_Adversarial_Corpus.json` — **226 synthetic cases across 66 named families**, all `NOT_RUN`.
- `LocalFlow_M05_Claude_Cloud_Remediation_Handoff.md` — complete execution handoff, including independent review and M05-only verification-runbook constraints.

The corpus is visible development/challenge material, not a blind holdout. Variants do not establish independent real-world samples, an error rate or acoustic improvement.

## Audit Boundary

> This audit covers committed GitHub state at `267d1c25910328f72afff7096eb2a442e96a5174`. Any uncommitted local state is outside the audit boundary.

Only connected GitHub reads were used for repository evidence. No branch, commit, issue, pull request, repository file, live database or installed application was changed. Files accompanying this report are new audit deliverables in the conversation workspace, not repository edits. The native Dictionary panel, Accessibility collection, microphone, Parakeet/Qwen inference and reference-Mac latency were not exercised.

**Execution limitation:** an executable checkout was not available to this audit. No repository test suite, new regression, mutation, concurrency probe, benchmark or adversarial case was run. Source-derived predictions are explicitly labeled; archived pass counts and timings are historical evidence, not current audit results. A source-confirmed unsafe branch is actionable without pretending its integration reproduction has occurred.

The audit is M05-owned. M04, M06, M07, M10 and M14 were inspected only at relevant interfaces. M01–M04, M07 and M11 were not re-audited; M06 and M15 were not begun. Site/provider extraction and broad learning quality are outside this report. The caller map below is the traced M05-facing graph, not certification of every provider implementation in the repository.

## M01–M04 Remediated Main Baseline

The main branch resolved to the expected full SHA above. GitHub ancestry comparisons showed the accepted repair commits as ancestors, and main’s direct parent is the M04 production repair. The shared runbook contains the accumulated M01–M04 sections/check identifiers. Its pending native statuses are not interpreted as results from Daniel’s machine.

| Accepted milestone | Production repair | Ancestry evidence at audited main |
|---|---|---|
| M01 | `3db74061f23001b9cce3d4fe029e0b30cbc295d6` | main ahead 14, behind 0; merge base is this repair |
| M02 | `bfbc63c35efa6273cc13242d54d3e5bbe264b21e` | main ahead 10, behind 0; merge base is this repair |
| M03 | `3e0d1ab972b866b4acbda622984bce04e8f95093` | main ahead 6, behind 0; merge base is this repair |
| M04 | `4ef219c52598e92a9857e9e0dec13ca7143f56dc` | direct parent of audited main |
| M04 evidence/documentation | `267d1c25910328f72afff7096eb2a442e96a5174` | current main |

Foundation constraints carried forward: M01 historical/current evidence separation; M02 schema-11 deletion barriers, acknowledged publication, timeout-not-cancellation and safe repair behavior; M03 job/generation ownership and capture/deletion ordering; M04 clause barriers, protected literals/code, canonical-claim semantics, slash command-position guards, layer arbitration, configured-profile inheritance and `retry_unscoped_default`. In particular, do not “repair” M05 by reverting the accepted M04 History retry fix. [S32: Shared native verification runbook](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/VERIFICATION.html) [S33: M01 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M01.md) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md) [S35: M03 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M03.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md) [S37: Current normalization contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/normalization.md) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

## M05 Responsibilities

M05 owns approved vocabulary/aliases, deterministic scope membership and collision resolution, dictionary skill registration, immutable job vocabulary identity, management/persistence/history/import-export, relevant hint selection, post-ASR hit accounting and dictionary-specific evidence. It does not infer acoustic correctness, decide arbitrary speaker intent, collect destinations or evaluate general cleanup reasoning.

The acceptance invariant is stronger than substring matching: **this approved entry, in this frozen revision, was applicable to this job’s actual scope and owned this source occurrence**. Optional ASR hints must remain distinct from applied post-ASR dictionary edits. Current fields and consumers must be assessed together, not as the historical pre-M06 global-only system. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S18: Specification](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md) [S19: Evaluation plan](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) [S20: Milestone definitions](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_MILESTONES.md) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)

## Current Vocabulary Architecture

```text
VocabularyStore (current Store schema 11; M05-owned tables originated in v3)
    │ entries + aliases + mutation revision counter
    ▼
VocabularySnapshot(entries, ScopeContext)
    ├── enabled/in-scope/approved alias resolutions → M04 vocabulary layer 5
    ├── approved dictionary skills → M10 SkillRegistry → M04 layer 3
    └── enabled in-scope ranking cohort → RelevantVocabularySelector → HintSet

PTT-down target/profile state → application M05 trio (policy, context, hints)
    → M06 finalize → rebuild from captured entries for effective scope
    → pre-decode capability gate / retained HintSet
    → ASR → M04 normalization → actual applied dictionary hit accounting
    → M07 bounded canonical hints + approved alias pairs
    → retained stage ledger/context → M14 review/export boundaries
```

The five scopes are global, app, site, profile and workspace. Match precedence is workspace > profile > site > app > global. Match precedence is not selector rank: the selector deliberately orders pin before scope, then recency, frequency, priority and entry ID. M10 profile resolution feeds an effective profile value before normal vocabulary rescoping. The application holds a single last cache entry, not an unbounded per-site map. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md) [S27: M10 skill registry boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/developer/skills.py)

### Entry-field semantics

| Field family | Current role and audit conclusion |
|---|---|
| canonical / entry ID | Output and attribution; implicit case-preserving alias for valid word-token canonicals. IDs distinguish approving entities; import remints IDs for newly created records. |
| aliases / alias approval | Only approved aliases of an approved, enabled, in-scope entry enter matching. Alias approval must survive mutation/import faithfully. |
| approved / enabled | Active rewrite/skill gates; not currently the same gate as hint inclusion. Strict primitive validation is missing. |
| scope kind/value | Exact equality against the corresponding ScopeContext dimension; affects matching, ranking and snapshot identity. |
| kind / matching mode | Kind separates term and skill integration. Current supported matching-mode validation should not be broadened casually. |
| language | Stored informational metadata, not a locale filter; per-alias persistence is inconsistent on some transitions. |
| origin / verification | Origin labels provenance; verification is a controlled label. The label does not replace explicit approval and scope checks. |
| pin / priority | Selector ranking inputs; do not override matcher scope precedence. Included in dictionary identity. |
| usage / last used | Ranking statistics; intentionally excluded from matching revision/invalidation. Batch IDs are deduplicated. |
| entry revision | Per-entry change sequence. Stale caller-side RMW can reuse the same next revision. |
| snapshot revision | Hash of serialized frozen entry state plus scope, excluding usage/time statistics. It is distinct from the store invalidation counter and per-entry revision. |

The source includes behavior fields in the snapshot serialization; the central identity defect is mutable state after construction, not an alleged omitted scope dimension. Equivalent insertion order with stable entry IDs is a relevant deterministic test; reminted IDs after import need not yield the same provenance hash as the original database. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py)

## Historical Review Findings Considered

The September 22 M05 handoff records the tuple-alias approval/import crash, alias-only revision bug, scope-blind suggestions, language/alias update mismatch, usage-triggered rebuild cost, matching performance, content-bearing duplicate errors, API coverage and a formerly vacuous immutability assertion. Current source contains real repairs for tuple aliases, alias-only versioning, normal duplicate prechecks, first-word indexing, hit-counter invalidation separation and outer-list snapshot independence.

Those repairs do not settle the new questions. Nested immutability remained deferred. The language test covers a combined language-and-alias update, not language-only or explicit alias-language round-trip. The import test misses unsorted aliases and duplicate identities within one file. The original pipeline tests still lack real current M06/M10 job-scope composition. None of this invalidates the dated September 22 evidence; it limits what can be inferred from it today. [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py) [S16: M05 historical handoff](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md) [S17: M05 historical acceptance](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/acceptance/M05/results.json)

## Entry / Alias / Approval Assessment

The ordinary matcher filters enabled, scoped and approved entries before building its alias resolution set, then requires per-alias approval. Unapproved and disabled contenders do not suppress a legitimate approved term in that path. Approving an entry intentionally approves its aliases together. A previously captured normal store snapshot retains its old approval/disable/delete state for the in-flight job; subsequent snapshots see the mutation.

The danger is not that the ordinary matching loop ignores approval. It is that malformed external booleans can mint approval, concurrent management actions can validate stale state, and the panel can address the wrong selected entity. Those are three distinct authorization boundaries. Canonical no-op hits must remain absent from usage accounting; actual ledger applications, not hint membership, are the caller contract for record_hits. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S07: Dictionary panel](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/dictionary_panel.py)

Alias admission accepts Unicode letters, internal hyphens/apostrophes and normalized whitespace. It rejects digits, dots, underscores, slashes and emoji as spoken aliases. Canonicals can contain richer technical output, subject to trimming/nonempty/length checks; not every rich canonical can become an implicit spoken alias. Direct dataclass construction can bypass some public validation and must not be used to make an import-admission test pass. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py)

## Scope / Precedence / Cache Assessment

**Normal-path strengths:** all four contextual dimensions participate in the application’s scope key; narrower scope wins before same-scope conflict masking; pin/usage/priority do not displace that matcher winner; approved/disabled filtering occurs before active conflicts. Scope upgrades use captured entries, not the current store. Cache storage is bounded to the last entry.

**Failure-path weakness:** last-good state is returned without proving scope compatibility after a refresh error, and the finalizer treats missing hints as a reason not to rebuild vocabulary. This is an ownership bug even though normal keys are correct. Missing destination data must not grant the previous job’s destination authority.

Scope identity is deliberately narrow. App uses bundle identity; site compares the normalized origin supplied under M06’s contract; workspace is a directory/project label, not a globally unique canonical filesystem path; profile uses the resolved M10 identity/name/category contract. Same folder display names can therefore be indistinguishable by design. Manual/imported site values are not automatically normalized by M05, so scheme, host case, port, trailing dot, www and query/fragment differences need explicit characterization. Do not invent a new URL or filesystem matching policy while repairing an unrelated cache failure. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md)

## Matching / Collision / Idempotence Assessment

Exact approved alias matching and implicit canonical spelling are useful and generally deterministic. Same-scope aliases resolving to different canonicals are masked rather than chosen by row order; a narrower applicable scope wins over broader contenders. Terms and skills have different integration paths, so their collision cannot be assessed as two ordinary layer-5 aliases.

The material occurrence defect is internal clause-barrier crossing (01), not benign trailing punctuation. The material no-op defect is a canonical claim encountered after an earlier overlapping proposal (03), not a requirement to invent speaker intent. The M04 addendum explicitly leaves parenthesis/quote-attached tokenizer limitations in place; they must be characterized, not silently fixed as part of an unrelated M05 repair.

A longer conflicting alias and a shorter valid alias need a policy-explicit test: masking a resolution is not automatically the same thing as reserving its whole text span. Likewise, a lone explicitly approved wrong rule may intentionally rewrite its alias, including a common word. The audit does not propose an LLM adjudicator or a blanket ban on mid-sentence matching. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S30: Vocabulary fixtures](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## M04 / Skill / Snippet Composition Assessment

Current M04 command-position rules remain authoritative for dictionary-registered skills; test real aliases, not an empty registry. Intended `slash code review` and framed commands need positive controls; `we should really slash code review time` needs a matched negative. Terms do not automatically become skills and unapproved/disabled/out-of-scope skills do not enter the normal dictionary skill map.

The identified defect is loss of dictionary skill provenance, not evidence that all command-intent guards are bypassed. Same-span snippets at layer 3 outrank vocabulary at layer 5, including equal-output cases; competing different outputs within the same owning layer are ambiguous. Overlap behavior must be tested through actual current registries and grammars, not synthetic proposals that bypass the integration under review. No emitted slash token is executed by the normalizer. [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md) [S27: M10 skill registry boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/developer/skills.py) [S37: Current normalization contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/normalization.md)

## Store / History / Import-Export Assessment

The active Store schema is **11**, not historical M05 schema 3. M05-owned rows, aliases, history and revision counter are written inside each queued operation, and operation failure can roll back those writes together. That is a real strength. It does not make an earlier caller-side read/merge atomic: finding 06 concerns the gap before the writer operation.

History survives entry deletion while active entry and alias rows are removed. Empty update requests return the current entry without fabricating history; explicitly supplied same-value fields are not guaranteed to be deduplicated by the current contract. Alias-only updates now version the entry. Hit recording increments existing IDs in a deduplicated batch and intentionally does not invalidate matching snapshots; a deleted entry contributes no row update and must not invalidate an otherwise legitimate frozen rewrite.

Import parses entry representations and upserts by canonical/scope, reminting IDs for newly created entries and preserving existing IDs on updates. Imported usage is not adopted as real hit history. Export and reimport must be assessed semantically, not by demanding identical newly minted IDs. Strict type validation, unsorted aliases, duplicate identities inside one file, language preservation and honest partial completion need repair or adjudication. Full-file atomicity and full Unicode linguistic equivalence are not assumed promises. SQLite NOCASE is the stated uniqueness backstop; importer key behavior must nevertheless be internally coherent with that backstop.

The populated torn-table matrix, concurrent duplicate error canary, full public alias representation matrix and fault-injected rollback remain runtime verification work. Existing empty-table repair tests are not proof of lossless recovery of populated user state. [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S10: Current store and migrations](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

## Snapshot / Revision / Immutability Assessment

Separate four concepts: the store’s invalidation counter, an entry’s revision, the effective vocabulary snapshot hash and the HintSet hash. Usage is deliberately excluded from the matching identity. Scope and the serialized behavior fields are included. The normal M06 scope upgrade changes effective snapshot identity while preserving the job’s captured entry set.

The promised deep freeze is not achieved. A frozen dataclass annotation is not a deep copy; a mapping proxy is not object sealing; a tuple containing mutable dictionaries is not immutable. Snapshot rebinding and caller-owned alias lists threaten the later rescope boundary. HintSet mutation threatens pre-decode request/evidence identity. Test both direct exposed mutations and mutations of original caller-owned containers, then compare behavior and canonical serialized bytes, not just a saved hash string. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md)

## HintSet / Selector Assessment

The selector implements pin > scope > recency > frequency > priority > entry ID. Default budget is 100; the constructor rejects limits below one. Omissions carry term_limit metadata. Enabled/in-scope suggestions can be offered, because the implementation explicitly separates offering context from permission to rewrite. Conflict-masked aliases do not necessarily remove a canonical from hint ranking. The current system does not promise deduplicating equal canonicals across entries/scopes.

Hint identity includes ordered selected terms/scores, omissions, scope, selector revision, vocabulary revision and budget. It deliberately excludes the creation timestamp. No HintSet.conflicts field exists. The main defect is mutable nested content after hashing, not a claim that every requested identity field was omitted.

Recency/frequency can remain stale indefinitely while the same edited snapshot is cached and no dictionary edit occurs. That is an explicit performance approximation, not a newly discovered violation of matcher correctness. Pin-first ordering can starve unpinned scoped entries at the budget; record it honestly instead of changing contractual rank based on preference. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py)

## Pre-Decode Hint Honesty Assessment

The current production manifest declares contextual biasing/key terms unsupported pending qualification. Nonempty offered terms have an explicit ignored disposition; zero offered terms are not labeled ignored. Request hint fields remain None for that unqualified path, accepted terms are not fabricated and membership is not an acoustic hit. This is a genuine source-supported strength.

The synthetic qualified-adapter test pins request shape but flips a boolean rather than proving adapter/checkpoint/runtime qualification. Treat that as future-boundary coverage, not evidence of a current supported decoder or a reason to add one during this audit. No model-backed hint experiment was performed and no acoustic recovery, confidence, WER or decoder improvement is claimed. [S08: ASR capability boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S18: Specification](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)

## Evidence / Privacy Assessment

Term normalization edits preserve an approving rule ID and controlled verification label; the envelope records vocabulary revision and applied IDs. Actual post-ASR dictionary edits remain distinguishable from ASR hint disposition. Dictionary skills lose that M05 identity (09). Whether a deleted/changed rule can be fully reconstructed from retained evidence without the live dictionary is an explicit proof gap (15), distinct from ledger replay.

Hint terms belong in lease-governed content artifacts, not raw operational logs. Successful retention serializes the HintSet at that time; later live-store edits do not rewrite stored bytes. Write/lease failure presently collapses to a generic not-captured envelope reason (14). The audit does not claim a dangling artifact reference is published on that failure path. M02’s committed-reference checks and deletion barriers must stay intact.

Caller-side duplicate validation and the M05 collector’s type/reason diagnostics avoid obvious dictionary text disclosure in the inspected normal paths. That is not a blanket privacy certification: concurrent uniqueness errors, invalid import/type paths, snapshot/selector failures and artifact/lease faults still need synthetic canaries in raw event logs. Dictionary text visibly displayed inside the Dictionary panel is expected and is not itself an operational-log privacy defect. [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S07: Dictionary panel](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/dictionary_panel.py) [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S25: Artifact contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/artifacts.md) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md)

## M06 / M10 Live-Scope Compatibility

On success, the application captures the M05 trio, obtains destination/profile information, rebuilds from frozen entries and selects pre-decode hints. Profile identity is included in the cache key; no missing profile-key bug was found. A normal store mutation after A captures must affect B but not A, including A’s later scope upgrade.

The serious exception is finding 02. Its regression must inspect the dictionary, skill map, HintSet and cleanup pairs together, not only final text. The current-context conversion contracts use exact scope values; this report does not certify Accessibility-derived origins/workspaces or target transition behavior from source alone. Recovery/History retries intentionally use a new unscoped vocabulary snapshot with a source label; same-job automatic retry must retain its declared job input. They are not interchangeable retry semantics. [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## M07 Cleanup Consumer Compatibility

Current app integration supplies at most 40 alias→canonical pairs from the frozen snapshot’s approved matcher, and at most 40 canonical hints from the job’s HintSet (or a bounded fallback derived from pairs). Alias pairs therefore inherit M05 scope and approval resolution on the successful path. The two budgets are capped independently; they do not guarantee identical selected populations.

The HintSet-based canonical list can include suggestions or conflict-masked entries because offering policy differs from rewrite approval. That contradicts an unconditional “no suggestion in cleanup context” interpretation of the audit brief, but it is an explicit implementation policy and the cleanup contract names frozen hint terms as prompt context. Classify and resolve this policy difference rather than silently asserting an approval bypass in M07’s repaired validator. The validator’s alias authorization pairs remain a separate, approved-only input. Alias keys are normalized for matching; exact canonical output case is preserved. Do not demand original alias case where the declared matcher key is case-insensitive. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S23: M07 cleanup contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/cleanup.md)

## M14 / M15 Provenance Boundary

M14’s LearningService explicitly routes approval through VocabularyStore; pending/rejected/stale candidates are not direct active dictionary rules. It records learning linkage and checks adverse counterexamples using scope-aware snapshots. The inspected stage-classification boundary distinguishes raw/normalized/applied texts and can attribute a later regression to normalization instead of ASR. These mechanisms do not replace exact dictionary skill attribution or prove a frozen rule can be reconstructed after deletion.

No source evidence here establishes acoustic decoder-hit laundering as current production behavior. The future test must still prove that a successful post-ASR repair is never promoted to an audio-reviewed reference or contextual decoder recovery. M15 should receive precise offered/ignored hints, actual deterministic edits, complete or explicitly missing frozen input evidence and task-specific eligibility—not a single undifferentiated “vocabulary success” counter. M15 implementation/evaluation is outside this audit. [S08: ASR capability boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py) [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S28: M14 learning boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/learning.py) [S29: M14 stage classification boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/curation/classify.py) [S39: References contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/references.md) [S40: Preferences contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/preferences.md)

## Test-Oracle Assessment

| Existing area | What it actually supports | What it does not independently prove |
|---|---|---|
| 40 inline vocabulary fixtures | Useful spelling, alias, scope, collision, layer and negative examples | Current application error-path scope ownership, left-overlap canonical shielding, delimiter matrix |
| Generated negative corpus | Broad substring safety with known aliases deliberately absent | Real aliases in prohibited intent/protected/currently wrong scope; real-world prevalence |
| Store suite | Sequential APIs, old snapshot after store mutation, tuple fix, outer-list independence | Nested mutation, stale RMW barriers, unsorted import, populated torn tables |
| Hint suite | Basic determinism, limits/omissions, conservative adapter, text-side distractor matrix | Full independent rank contrasts, mutable JSON aliases, qualified runtime identity, current cleanup consumer |
| Pipeline suite | Historical global integration, successful predecode retention, applied term IDs | All current M06/M10 scope transitions and failure combinations; skill provenance |
| Preview tests | All four named preview kinds are reachable | Preview-versus-committed-state parity under active/inactive contenders |
| Benchmark | 10k construction and selected/omitted count checks; timing exit gate | Actual vocabulary edits in normalization timing; dense shared-first-word work; current Mac latency |

The 40 hint-matrix bases are eight targets × five templates, with variants grouped by target family. They are synthetic text-side development cases; they are not 40 unseen acoustic recordings. The new corpus deliberately adds matched positives and negative controls, state transitions and evidence failures. A count of cases is not a count of independent failures. [S11: M05 benchmark](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/scripts/v2/benchmark_m05.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py) [S30: Vocabulary fixtures](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json) [S31: Hint matrix](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_hint_matrix.json)

## Performance / Benchmark Assessment

The source supports a first-word alias index, avoiding a scan of every entry for ordinary no-hit words. That does not eliminate a large shared-first-word bucket; the current synthetic aliases share "tirm" and need an actual matching-text stress cohort. M04’s improved arbitration does not certify M05’s candidate-generation cost.

The historical handoff reports a roughly 126.9 ms cold 10k snapshot, roughly 5.1/5.3 ms selector/scoped-selector figures and roughly 2.4 ms normalization figure on the then-recorded Mac environment. These are dated September 22 measurements on older code/workloads, **not rerun here and not current Mac certification**. The current script uses 25 ms hot-path timing gates and already returns a failing exit for exceeded timing budgets. Its normalization work-validity gap remains finding 16.

A new benchmark must separately report cold snapshot build, cached application snapshot retrieval, selector ranking, scoped selection, finalization scope rebuild, pre-decode packaging, normal dictionary-hit normalization, dense overlaps and large shared-first-word buckets. The single-entry cache prevents unbounded growth but alternating scopes can repeatedly rebuild; a cold scope at hotkey/release boundaries therefore needs direct measurement. Do not call a selector-only timing a release-to-ASR or release-to-insertion measurement.

Required record: exact SHA, interpreter/platform, actual entry and approved-alias populations, scope distribution, expected match population, selected/omitted counts, cache state, exact workload word count, p50/p95/p99, work-validity verdict, timing verdict and exit code. This audit supplies no new timings. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S11: M05 benchmark](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/scripts/v2/benchmark_m05.py) [S16: M05 historical handoff](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md) [S17: M05 historical acceptance](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/acceptance/M05/results.json) [S19: Evaluation plan](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## Critical Findings

### M05-AUDIT-01 — A multiword alias can consume a clause delimiter

**Severity:** CRITICAL  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Occurrence ownership / M04 composition

**Canonical requirement.** S11 / EV-07 whole-phrase ownership; the audit’s explicit requirement that aliases own word cores without swallowing punctuation or crossing clause barriers.

**Code location.** `normalize/syntax.py::grammar_vocabulary; normalize/engine.py::_BARRIER_EXEMPT, normalize, MatchHost.connected`

**Current behavior and failure mechanism.** The vocabulary grammar compares successive word tokens without requiring MatchHost.connected for the full candidate. The engine deliberately exempts vocabulary from its generic crosses_delimiter rejection because M05 is expected to enforce its own rules. Trimming punctuation at the two outer edges does not protect punctuation or line separators inside the replacement span. A correctly approved entry can consequently own two separate clauses and record the rewrite as an ordinary dictionary correction.

**Minimal reproduction.** Create one approved term E-CC, canonical "Claude Code", approved alias "clod code", global. Normalize "clod, code" and separately "clod\ncode". Compare the positive "clod code,". No shorter alias or unrelated rule is needed.

**Expected behavior.** The first two strings remain unchanged by vocabulary, with no applied E-CC edit; the contiguous positive becomes "Claude Code," and retains its comma.

**Likely actual behavior / verification boundary.** Source-derived prediction: the first two become "Claude Code", deleting the internal comma or newline; the edit carries E-CC. This exact output has NOT been executed in this audit.

**Existing coverage and why its oracle misses this.** The punctuation fixture covers a comma after the whole alias, not between its words. The engine’s recent M04 barrier repair expressly leaves M05 to its own matcher; inherited M04 greens do not test this exception.

**Independent regression recommendation.** Use the actual current engine with real entries. Pair each internal comma, period, colon, semicolon and Unicode line separator negative with an outer-punctuation or space/NBSP positive. Assert exact text, exact owned spans and actual nonzero positive edit population.

**Narrow repair direction.** Use the current token connectivity/core-span interface inside M05. Preserve legitimate whitespace, edge punctuation and mid-sentence aliases; do not globally disable vocabulary or alter accepted M04 delimiter semantics.

**Downstream impact.** M04 integration; M07 receives corrupted normalized input; M14/M15 may otherwise treat the legitimate-looking rule ID as sufficient explanation.

**Pinned source evidence.** [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S30: Vocabulary fixtures](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json) [S37: Current normalization contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/normalization.md)

### M05-AUDIT-02 — A failed refresh can reuse another job’s scoped dictionary

**Severity:** CRITICAL  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Cross-job isolation / error-path scope ownership

**Canonical requirement.** S11 frozen per-job scope; M06 finalization rebuilds from this job’s frozen entries, not a different job; failures must not grant unverified scope authority.

**Code location.** `app.py::_vocab_job_state and _finalize_job_context`

**Current behavior and failure mechanism.** _vocab_job_state starts with the application’s previous normalization policy/context. On a refresh exception it returns that last-good state with no HintSet. _finalize_job_context can attach the new destination but returns before rebuilding vocabulary when hint_set is None. Its no-collector/no-snapshot paths also retain the incoming vocabulary. Thus the cache key is complete on successful reads, but the fallback is not constrained by that key. Hint selection failure also incorrectly gates an otherwise possible scope upgrade.

**Minimal reproduction.** Job A: capture an approved app-A-only E-A: clod→Claude. Job B: target app B. Inject a revision/snapshot-read exception in _vocab_job_state after A has populated state. Let M06 successfully finalize B. Process B text "ask clod now". Separately fail only selector.select while a frozen set contains both global and workspace contenders.

**Expected behavior.** B must never apply E-A. Either establish a B-valid frozen snapshot or proceed without the unsafe scoped vocabulary and record the reason. Failure to produce optional hints must not prevent a valid dictionary scope rebuild.

**Likely actual behavior / verification boundary.** Source-derived prediction: the first path returns A’s vocabulary, hint_set=None, skips the rescope, and can rewrite B using E-A. Runtime reproduction is required for the full coordinator seam.

**Existing coverage and why its oracle misses this.** The original pipeline failure test covers startup failure without a prior scoped job. Direct snapshot scope fixtures bypass this application fallback. Normal cache-key tests cannot detect an exception that bypasses key matching.

**Independent regression recommendation.** Latch A capture, inject B refresh failure, then run actual application helper/finalizer and engine through portable shims. Assert B’s destination, vocabulary scope, revision, applied IDs and cleanup pairs together. Add selector-only failure, context failure, consecutive profiles and workspace alternation.

**Narrow repair direction.** Decouple scope ownership from hint availability. Only reuse last-good state when compatibility with this job’s effective context is proven; otherwise use a content-free safe fallback. Preserve frozen-entry rescoping, not a mid-flight live-store reread.

**Downstream impact.** M06/M10 live scopes; M07 cleanup input; M13/M14/M15 provenance. Do not undo M04’s separate, already-correct retry_unscoped_default repair.

**Pinned source evidence.** [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## High Findings

### M05-AUDIT-03 — Canonical no-op shielding is order-dependent and permits second-pass drift

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Idempotence / overlap ownership

**Canonical requirement.** The vocabulary contract protects an already-canonical phrase from a shorter overlapping alias and requires no vocabulary edit for a canonical no-op.

**Code location.** `normalize/syntax.py::grammar_vocabulary; normalize/engine.py::_sort_key and overlap arbitration`

**Current behavior and failure mechanism.** Canonical no-ops add a local claimed span during the left-to-right scan. That blocks later-starting candidates, but does not withdraw a proposal already yielded from an earlier start. The M04 resolver cannot see a no-op claim that M05 never submits. First-pass and second-pass ownership can therefore differ.

**Minimal reproduction.** E-A canonical "Status Page" (implicit canonical alias), E-B canonical "Orange", alias "red status", both approved/global. Normalize "red status page", then normalize the result under exactly the same snapshot. Also test the intended E-B positive "red status" alone.

**Expected behavior.** Pass 1 produces "red Status Page"; pass 2 leaves it unchanged with zero vocabulary edits. The standalone E-B positive still produces "Orange".

**Likely actual behavior / verification boundary.** Source-derived prediction: pass 1’s longer Status Page span wins; pass 2 yields the earlier "red Status" proposal before encountering the no-op Status Page claim, producing "Orange Page". Not runtime-executed.

**Existing coverage and why its oracle misses this.** The existing idempotence fixtures cover canonical phrases and later-starting shorter aliases, not a competing alias that begins to the left of the canonical span.

**Independent regression recommendation.** Author the two-pass text and ledger expectations independently; include both left- and right-overlap cases and verify a positive for each competing rule. Do not compare only normalize(normalize(x)) text for unrelated simple fixtures.

**Narrow repair direction.** Collect complete canonical ownership claims before emitting competing candidates, or carry explicit non-edit claims through a narrowly compatible arbitration mechanism. Preserve M04’s accepted layer and same-span precedence rules.

**Downstream impact.** M04 determinism; repeated normalization in previews/retries; M07 input stability and M15 text scoring.

**Pinned source evidence.** [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S30: Vocabulary fixtures](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json)

### M05-AUDIT-04 — VocabularySnapshot is not deeply immutable after its revision is computed

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Snapshot identity / caller-owned inputs

**Canonical requirement.** VocabularySnapshot is a frozen job input, including entries, aliases, scope, matcher and skills; behavior must not change under an unchanged revision.

**Code location.** `vocabulary.py::VocabularyEntry and VocabularySnapshot`

**Current behavior and failure mechanism.** VocabularySnapshot is a normal assignable class. Its indexes and skill state originate in mutable dictionaries; mapping proxies do not seal the object or all backing structures. Entry aliases are type-annotated tuples but are not defensively converted when a caller constructs an entry with a list. Mutating an alias list after capture can change snapshot.entries used by a later rescope while the original matcher and hash remain unchanged. Public attributes can also be rebound.

**Minimal reproduction.** Capture a snapshot from an entry whose aliases argument is a caller-owned list. Save revision, entries serialization, match output and a rebuilt-scope output. Append an Alias to the original list; rescope from captured entries. Independently attempt snapshot.scope assignment, index replacement and nested conflict mutation.

**Expected behavior.** All behavior-bearing state is defensively owned and immutable, or changes create a new snapshot and identity. Caller mutations cannot change the current job or its later scope upgrade.

**Likely actual behavior / verification boundary.** Source confirms assignable attributes and non-copied nested input. Individual mutation outcomes and actual rescope effects require runtime probes; no such probe was run here.

**Existing coverage and why its oracle misses this.** The replacement immutability test mutates the outer input list and replaces an entry object; that is useful, but does not mutate a nested aliases list, exposed attributes or conflict dictionaries.

**Independent regression recommendation.** Test mutation of each reachable public/nested container, independently of mutations of original caller-owned inputs. Re-run matching, skill registry construction, rescoping and serialization under the saved revision.

**Narrow repair direction.** Defensively freeze entries/aliases and seal the snapshot’s owned structures without adding hot-path deep copies on every use. Do not rely on annotations or MappingProxyType over an externally mutable dictionary.

**Downstream impact.** M06 frozen-entry upgrade; M07 match_items; M10 skills; M14/M15 immutable evidence identities.

**Pinned source evidence.** [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md)

### M05-AUDIT-05 — HintSet content can change without changing hint_set_id

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Hint identity / provenance

**Canonical requirement.** S30.1 immutable pre-decode hints; S29.11 no post-answer context leakage; distinct behavior/provenance must have distinct identity.

**Code location.** `vocabulary.py::HintSet, HintSet.to_json, RelevantVocabularySelector.select`

**Current behavior and failure mechanism.** The dataclass is frozen only at the outer attribute level. scope is a mutable dictionary; omitted is a tuple containing mutable dictionaries; to_json returns shared nested objects. Direct construction can also accept a caller-owned mutable terms container. A dictionary mutation can therefore change serialized content while retaining the original hint_set_id. There is no HintSet.conflicts field to freeze; snapshot.conflicts is a different object.

**Minimal reproduction.** Capture a HintSet with at least one selected and one omitted term. Save ID and serialized bytes. Change hs.scope["workspace"], mutate an omitted reason, and separately mutate the nested objects obtained from hs.to_json(). Repeat using caller-owned containers passed to the constructor.

**Expected behavior.** Each attempt is rejected or leaves the frozen object unchanged. A separately constructed different scope/omission/budget/order gets a new identity.

**Likely actual behavior / verification boundary.** Source confirms mutable nested state and serialization aliases. Hash/content divergence is source-derived, not an executed artifact comparison.

**Existing coverage and why its oracle misses this.** Current tests cover deterministic construction and later store changes, not deep mutation through exposed objects or the JSON return value.

**Independent regression recommendation.** Assert both ID and canonical bytes before/after direct and indirect mutation attempts; distinguish term order, scope, selector revision, vocabulary revision, omissions and budget. Equivalent reconstruction remains deterministic.

**Narrow repair direction.** Deep-freeze internal data and return detached serialization trees. Maintain the current deliberate exclusion of created_at_utc from deterministic identity.

**Downstream impact.** Pre-decode request/evidence consistency; M07 input and future M15 contextual evaluations. Already-written artifact bytes are not retroactively mutable, but an ID can denote inconsistent serializations.

**Pinned source evidence.** [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S18: Specification](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)

### M05-AUDIT-06 — Vocabulary read-modify-write validation occurs outside the writer transaction

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Store concurrency / history and revision integrity

**Canonical requirement.** Each mutation atomically maintains a valid entry, aliases, monotonically meaningful revision, history and state counter; the single writer does not by itself serialize caller-side reads.

**Code location.** `vocabulary_store.py::update_entry, approve_entry, delete_entry; store.py::submit`

**Current behavior and failure mechanism.** update_entry reads current and validates merged fields before queuing its writer operation. new_revision is derived from that stale object inside the closure. Two callers can validate against the same revision, then commit two histories with the same next revision. Compatible individual field edits can form an invalid combined scope. Deletion between the read and write can leave an update with no matching entry row while alias/history writes still run. approve_entry takes another stale alias copy before delegating.

**Minimal reproduction.** Barrier both callers after entry() returns global/None at revision 1. Caller A sets scope_kind="workspace", scope_value="X"; caller B sets only scope_value=None. Commit A then B. A second probe performs two independent edits from revision 1. A third deletes between update’s read and writer execution.

**Expected behavior.** Validate against the authoritative row inside one writer transaction or reject a stale expected revision. No workspace/None row, duplicate next revision, lost alias approval or orphaned update may commit.

**Likely actual behavior / verification boundary.** Source-derived prediction: A and B both validate against the old global row and can persist workspace/None with duplicate revision 2 histories. The full interleaving has NOT been executed.

**Existing coverage and why its oracle misses this.** The suite exercises sequential mutations and per-operation atomicity; it has no barriers across caller read, validation and queued write. Existing M02 fixes demonstrate why a writer queue alone is insufficient but do not repair this M05-specific operation.

**Independent regression recommendation.** Use explicit barriers around current-row reads and writer admission, not sleeps. Assert raw rows, aliases, history revisions, counter, snapshot construction and final matcher independently. Include approve/edit, hit/delete, preview/commit and import/update races.

**Narrow repair direction.** Move authoritative read/merge/validation/versioning and affected alias decisions into one writer operation, or use explicit compare-and-swap. Preserve M02 deletion/publication and shutdown semantics; do not globally replace Store.

**Downstream impact.** M05 persistence and all future snapshots; M14 approval through VocabularyStore. This is not a request to re-audit general M14 learning.

**Pinned source evidence.** [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S10: Current store and migrations](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S28: M14 learning boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/learning.py) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

### M05-AUDIT-07 — Malformed boolean values are coerced into approval

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Admission / import authorization

**Canonical requirement.** Approval and enabled state must be explicit and faithfully imported; malformed types must not silently authorize a rule.

**Code location.** `vocabulary.py::VocabularyEntry.from_json; vocabulary_store.py::_normalize_alias_items, add_entry, update_entry, import_json`

**Current behavior and failure mechanism.** from_json uses bool(value) for approval, enablement and pinning, including per-alias approval. The nonempty string "false" becomes True. Update and alias normalization also use truth-value coercion instead of a strict boolean boundary. Thus a malformed dictionary file can promote something visually represented as false into an active approved rule.

**Minimal reproduction.** Import a single synthetic global entry with canonical Claude, alias clod, entry approved="false", alias approved="false", enabled="false". Compare a valid file using actual JSON false. Exercise the public update API with approved="false" too.

**Expected behavior.** Reject malformed boolean types before any write with a content-free validation error. Correctly typed false remains false; correctly typed true retains the intended positive behavior.

**Likely actual behavior / verification boundary.** Source-derived prediction: all three strings become True, allowing clod→Claude on future snapshots. No import or normalization was run in this audit.

**Existing coverage and why its oracle misses this.** Round-trip tests use valid booleans. Existing alias representation repair tests prove accepted tuple support, not strict trust-boundary types.

**Independent regression recommendation.** Table-drive false/true, strings, null, integers, arrays and objects for each boolean field; separately assert rejection, no partial state change, no history/counter change and no content in error events.

**Narrow repair direction.** Validate primitive types at public/import boundaries. Do not change the intentional default values for omitted fields without a compatibility decision.

**Downstream impact.** M05 approval semantics; M14 approved-rule consumption; incorrect authority can look legitimate downstream.

**Pinned source evidence.** [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py)

### M05-AUDIT-08 — Panel selection can retarget an approval after filtering or refresh

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** UI authorization / stable entry ownership

**Canonical requirement.** The user’s approve/disable/pin/delete action must address the entry they selected, not whichever entry later occupies its display row.

**Code location.** `dictionary_panel.py::refresh, _selected_entry, searchChanged_, runSandbox_, approveEntry_`

**Current behavior and failure mechanism.** The panel stores _selected as an integer into _shown. refresh replaces _shown but does not clear or rebind selection. _selected_entry resolves that old index in the new filtered list. Search changes or a store-driven reorder can silently change the target of approval and other management actions.

**Minimal reproduction.** Create Alpha and Beta, both unapproved. Filter to Beta; select line 1 using the Test phrase selection path. Clear the filter, refresh, then approve without a new selection. Repeat with a concurrent rename or insertion before the selected row.

**Expected behavior.** Approve still targets Beta by stable ID, or the panel explicitly clears selection and requires a new selection. It must not approve Alpha.

**Likely actual behavior / verification boundary.** Source-derived controller prediction: index 0 now resolves to Alpha and approves it. This was not executed under AppKit and is not a claim about observed native usability.

**Existing coverage and why its oracle misses this.** The pipeline panel check is a native construction/smoke path, not a stable-selection state machine. Source/controller logic can be tested portably with UI stubs; real rendering remains local.

**Independent regression recommendation.** Assert selected ID before/after filtering, refresh, deletion and reorder. Invoke each mutating action and verify exact committed ID plus unaffected other rows.

**Narrow repair direction.** Store selection by stable entry ID and revalidate presence/current revision at action time. Clear invalid selection; never infer user authorization from a stale display index.

**Downstream impact.** M05 explicit approval and management; wrong approved entry can later rewrite with an apparently valid rule ID.

**Pinned source evidence.** [S07: Dictionary panel](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/dictionary_panel.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py)

### M05-AUDIT-09 — Dictionary skill edits lose the approving vocabulary entry identity

**Severity:** HIGH  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Rule attribution / M10 composition

**Canonical requirement.** The audit requires every dictionary-owned rewrite, including skills, to identify its approving entry, verification and frozen vocabulary revision.

**Code location.** `vocabulary.py::VocabularySnapshot skills map; normalize/syntax.py::grammar_skills; developer/skills.py::SkillRegistry; training.py normalization and writing-profile evidence`

**Current behavior and failure mechanism.** The M05 skill export reduces an approved entry to alias→canonical name. The M10 registry consumes this mapping without its approving entry ID. grammar_skills emits a skill proposal without M05 rule_id/verification. Term edits retain their MatchTarget identity, but dictionary skill edits do not. The registry’s serialized dictionary alias count cannot recover that identity. This is a provenance omission, not proof that slash-intent guards are bypassed.

**Minimal reproduction.** Create approved dictionary skill E-SK, canonical code-review, alias "code review". Normalize "slash code review" through the real M05→M10 registry and current M04 engine. Inspect the applied edit and retained registry/vocabulary evidence, not only output text.

**Expected behavior.** The edit is /code-review and carries, or has an unambiguous retained reference to, E-SK, its verification and the exact frozen dictionary revision. Non-dictionary manifest skills must not receive fabricated M05 IDs.

**Likely actual behavior / verification boundary.** Source-derived prediction: output is correct but the applied skill edit has no approving vocabulary rule ID. Runtime verification required for final envelope serialization.

**Existing coverage and why its oracle misses this.** The attribution test filters cls=="vocabulary"; skill-output tests assert token text. That excludes the dictionary-owned layer-3 case from the rule-ID oracle.

**Independent regression recommendation.** Use a real dictionary skill, conflicting manifest skill and term contender; assert output, winning source, IDs and artifact reconstruction. Include scope changes, kind changes and no-op skills where applicable.

**Narrow repair direction.** Carry typed provenance alongside compatibility mappings into skill proposals and retained registry evidence. Do not move skills to vocabulary layer 5 or weaken M04 command-position rules.

**Downstream impact.** M04/M10 provenance; M13 usage interpretation; M14/M15 separation of deterministic dictionary effects from decoder effects.

**Pinned source evidence.** [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S27: M10 skill registry boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/developer/skills.py)

## Medium Findings

### M05-AUDIT-10 — An unsorted alias list makes repeated import non-idempotent

**Severity:** MEDIUM  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Import / revision churn

**Canonical requirement.** Vocabulary import is idempotent for the same effective file; repeated import should not fabricate updates/history solely from storage ordering.

**Code location.** `vocabulary_store.py::entries and import_json`

**Current behavior and failure mechanism.** Alias rows are read in NOCASE sort order. Import compares the incoming ordered alias list with that stored order without normalizing the incoming semantic set. An external file containing the same aliases in another order is therefore repeatedly classified as an update.

**Minimal reproduction.** Import an entry with approved aliases ordered ["zulu", "alpha"]. Import the identical bytes again and again. Inspect returned counters, entry revision, history and snapshot revision.

**Expected behavior.** After the first import, repeated identical files are unchanged unless order is explicitly a behavior-bearing contract. Current matching does not use alias insertion order for ownership.

**Likely actual behavior / verification boundary.** Source-derived prediction: each repeated import calls update_entry and bumps revision/history because the stored list reads [alpha,zulu]. Runtime verification required.

**Existing coverage and why its oracle misses this.** Current round-trip and update tests use one alias or already sorted aliases, so they do not challenge this representation mismatch.

**Independent regression recommendation.** Compare import once/twice/reordered with independent expected aliases, approvals, IDs and usage. Assert no revision/counter churn for semantic identity.

**Narrow repair direction.** Canonicalize comparison consistently with persistence while retaining meaningful approval/language distinctions. Do not suppress genuine alias changes.

**Downstream impact.** Unnecessary snapshot rebuilds, misleading history, unstable evidence revisions and management feedback.

**Pinned source evidence.** [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py)

### M05-AUDIT-11 — Repeated identities within one import can leave a partially applied file

**Severity:** MEDIUM  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Import identity / error reporting

**Canonical requirement.** Entry integrity remains authoritative, repeated import is deterministic, and failures must not misleadingly conceal committed mutations. Whole-file atomicity is not assumed without an explicit policy.

**Code location.** `vocabulary_store.py::import_json, add_entry`

**Current behavior and failure mechanism.** import_json builds its existing-entry lookup once, then performs each item as a separate committed public mutation. It does not update that lookup after creating a new identity. Two new rows with the same canonical/scope can cause the first to commit and the second to attempt another add and fail. The method raises instead of returning an accurate partial-result report. Python lower-based import keys and SQLite ASCII NOCASE uniqueness also need a single declared identity rule.

**Minimal reproduction.** Import two same-scope rows for a previously absent synthetic canonical; give the second a different alias. Catch the error and inspect the store, counter and history. Repeat with case variants and with an already-existing identity; characterize É/é separately rather than assuming full Unicode equivalence.

**Expected behavior.** Preflight and reject the ambiguous file without writes, or apply a documented deterministic duplicate policy and report the actual committed result. A per-entry importer must explicitly report partial completion.

**Likely actual behavior / verification boundary.** Source-derived prediction: first row committed, second add rejected, caller receives an exception without the committed counts. No file import executed here.

**Existing coverage and why its oracle misses this.** Existing tests cover importing a valid file twice, not duplicate new identities inside one file or a fault after an earlier row committed.

**Independent regression recommendation.** Use duplicate-new, duplicate-existing, reversed order, malformed later row and writer-fault cohorts; compare exact persisted state and returned status. Test chosen Unicode identity policy without imposing linguistic equivalence.

**Narrow repair direction.** Preflight duplicate identities and/or update the working identity map; choose and document file transaction/reporting semantics. Retain the DB unique index and content-free errors.

**Downstream impact.** Dictionary management reliability; snapshot state and history may change despite an apparent failed import.

**Pinned source evidence.** [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S10: Current store and migrations](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

### M05-AUDIT-12 — Alias language metadata is not preserved by all public transitions

**Severity:** MEDIUM  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Entry/alias consistency / round-trip metadata

**Canonical requirement.** Language is currently informational, but stored entry and per-alias metadata should follow the documented update and round-trip semantics rather than silently change.

**Code location.** `vocabulary_store.py::_normalize_alias_items, update_entry, import_json; vocabulary.py::VocabularyEntry.from_json and Alias.to_json`

**Current behavior and failure mechanism.** A language-only entry update changes the entry row but does not update existing alias rows. The repaired combined language+aliases path does update them. Alias normalization retains text and approval, discarding per-alias language overrides; import reconstructs alias rows using entry language. Thus a supported serialized per-alias language may not survive persistence.

**Minimal reproduction.** Create an en entry and alias, then update only language="es". Inspect both rows. Separately import an entry-language en with one alias-language es; export it again.

**Expected behavior.** Preserve explicit alias overrides or consistently migrate inherited alias languages under an explicit rule. Do not claim an effective language filter: this field currently does not constrain matching.

**Likely actual behavior / verification boundary.** Source-derived prediction: language-only change leaves old alias language; import loses a distinct alias-language override. Not runtime-tested.

**Existing coverage and why its oracle misses this.** The regression named language-and-aliases combined update does not cover either language-only mutation or explicit per-alias language round-trip.

**Independent regression recommendation.** Assert entry metadata, each alias metadata, revision/history and matching separately for language-only, alias-only, combined and import paths.

**Narrow repair direction.** Define inherited versus explicit alias language and preserve that distinction through normalization/storage, or formally narrow the serialized contract. Do not silently add locale filtering.

**Downstream impact.** M05 management/evidence semantics; future language-aware consumers. Current cross-language matching itself is a documented design choice.

**Pinned source evidence.** [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py)

### M05-AUDIT-13 — Sandbox and conflict diagnostics do not fully mirror live scope/ownership

**Severity:** MEDIUM  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Management truth / current M06/M10 integration

**Canonical requirement.** Sandbox output must honestly describe the scope being tested; suggested rewrites/conflict previews must distinguish actual active behavior from hypothetical approval.

**Code location.** `dictionary_panel.py::runSandbox_; vocabulary.py::sandbox_phrase, _scan_aliases, _phrase_spans, preview_entry_conflicts`

**Current behavior and failure mechanism.** The panel always captures snapshot(None), hence tests globals rather than the currently effective five-scope job. Domain suggestion scanning is separate from the protected-span engine and can report a quoted/code/literal occurrence as one that would rewrite after approval. Conflict preview considers entries/aliases that are not active contenders and reports masking without consistently distinguishing hypothetical activation. The live engine itself still filters approved/enabled rules correctly.

**Minimal reproduction.** With workspace X active, add approved workspace E-X and test its alias in the panel versus a snapshot(X) sandbox. Create an unapproved alias inside a spaced quoted region or fenced code; compare its suggestion with actual output after approval. Preview a same-alias disabled or unapproved contender and then inspect committed matcher behavior.

**Expected behavior.** Test an explicit selectable/frozen scope or clearly label a global-only preview. “Would rewrite if approved” must respect protection and alias approval; inactive conflicts are conditional, not actual masking.

**Likely actual behavior / verification boundary.** Source confirms global-only panel capture and separate simplified diagnostic matching. Individual displayed strings versus post-approval engine results require execution.

**Existing coverage and why its oracle misses this.** The historical preview test checks that four kind strings appear, not that committing the described condition produces the predicted mask. Old pipeline tests predate actual M06/M10 scope feeding.

**Independent regression recommendation.** For each preview kind, construct active and inactive cases, commit in a temporary store, and compare exact runtime behavior. Assert sandbox causes no hits, approvals or evidence writes.

**Narrow repair direction.** Share effective contender/protected-span logic or build a hypothetical approved snapshot through the real engine. Add explicit scope identity to the panel preview without scraping new context.

**Downstream impact.** M05 Dictionary UI and approval decisions; M06/M10 scope confidence. No AppKit usability certification is made.

**Pinned source evidence.** [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S07: Dictionary panel](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/dictionary_panel.py) [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md)

### M05-AUDIT-14 — Hint retention failure is recorded as ordinary non-capture

**Severity:** MEDIUM  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Evidence completeness / honest failure reason

**Canonical requirement.** S29.4 and current training_evidence contract distinguish unavailable input from retention_write_failed; failures must not erase the fact that a HintSet existed.

**Code location.** `training.py::EvidenceCollector.on_hint_set and envelope context/hint-set construction`

**Current behavior and failure mechanism.** on_hint_set emits a content-free hint_set_not_retained diagnostic and returns when artifact writing or lease acquisition fails. The context_hints block is assigned only after success. Envelope construction subsequently treats absent context_hints as not_captured_at_stage, losing the distinction between no offered snapshot and a known snapshot whose retention failed. The source does not show a published dangling artifact reference on this path; that broader allegation is not made.

**Minimal reproduction.** Begin a collecting synthetic job, construct a nonempty HintSet, then inject artifact-write failure; separately allow the write and fail its training lease. Finalize and inspect the exact persisted envelope and operational event.

**Expected behavior.** Preserve safe ID/count/disposition metadata when feasible with a precise retention failure reason and no invalid artifact reference; no content leak and no dictation failure. A genuinely absent HintSet remains a separate reason.

**Likely actual behavior / verification boundary.** Source-derived prediction: diagnostic reports retention failure while the envelope has generic not_captured_at_stage. No fault injection executed here.

**Existing coverage and why its oracle misses this.** Pre-decode evidence tests cover successful retention; prior M04 text/ledger retention regressions do not establish HintSet failure semantics.

**Independent regression recommendation.** Fault each publication boundary, test collection off and deletion before publication, and assert reason codes, reference validity, event canaries and unchanged dictation output.

**Narrow repair direction.** Carry a content-free failure state separately from retained payload success. Reuse the controlled reason vocabulary; preserve M02 committed-reference checks and delete-everywhere barriers.

**Downstream impact.** M14 evidence completeness and M15 contextual scoring; inability to reconstruct input must be explicit, not mistaken for zero offered vocabulary.

**Pinned source evidence.** [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S18: Specification](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S25: Artifact contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/artifacts.md) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## Low Findings

### M05-AUDIT-20 — Some active M05-facing descriptions still describe pre-M06/pre-M07 consumers

**Severity:** LOW  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Documentation currency

**Canonical requirement.** Current interfaces and current runbook instructions must describe the connected system while preserving dated historical evidence.

**Code location.** `Vocabulary/hints contract trailing statements and test_hint_selection.py consumer test messages; historical M05 native instructions`

**Current behavior and failure mechanism.** Current source/test descriptions still say cleanup is deferred/not a consumer and some scope resolution is future work, while app.py supplies M06/M10 scopes and M07 vocabulary. The September 22 handoff is properly historical and should not be rewritten as if those later integrations existed then.

**Minimal reproduction.** Compare the current app caller graph with active contract/test statements; compare the pending native trial with current M06/M10 scope behavior.

**Expected behavior.** Update active interface statements and version the native instruction set. Preserve original September 22 results and instruction history.

**Likely actual behavior / verification boundary.** Source discrepancy confirmed; no runtime reproduction is applicable.

**Existing coverage and why its oracle misses this.** Tests print old architectural claims even when their narrow assertions pass.

**Independent regression recommendation.** Check active documentation against actual consumers; keep historical labels and original evidence immutable.

**Narrow repair direction.** Add an M05 remediation addendum and amend only M05 runbook instructions using stable IDs and preserved localStorage/history semantics.

**Downstream impact.** Remediation handoff clarity and future audit correctness.

**Pinned source evidence.** [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S16: M05 historical handoff](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md) [S32: Shared native verification runbook](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/VERIFICATION.html) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py)

## Test Gaps

### M05-AUDIT-15 — Historical approving-rule reconstruction is not independently demonstrated

**Severity:** TEST GAP  
**Confidence:** High that the oracle is absent in inspected M05 suites; evidence sufficiency needs isolated runtime adjudication  
**Category:** Evidence sufficiency after edit/delete

**Canonical requirement.** The audit’s exact-rule/frozen-revision invariant; S29 task inputs and honest unsupported reconstruction.

**Code location.** `vocabulary_store.py history payloads; training.py vocabulary block; HintSet serialization; developer/skills.py registry serialization`

**Current behavior and failure mechanism.** Term ledgers identify the applied rule and snapshot revision, but a hash is not the old rule. History payloads do not uniformly contain all behavior-bearing fields or per-alias approval; HintSets contain budgeted canonical hints rather than the complete approved alias graph. The current suites do not reconstruct a deleted or edited approving rule from retained evidence alone. This audit does not assume that full dictionary export is required for every job; it identifies an unproven ownership-reconstruction boundary.

**Minimal reproduction.** Capture an applied rule that is omitted from a budgeted HintSet, then edit its alias approvals and delete it. In a clean reader without the live dictionary, identify the exact old alias, approval, scope, verification and revision from retained artifacts.

**Expected behavior.** Either reconstruct the exact rule from a permitted frozen manifest, or explicitly report the missing evidence and exclude unsupported regeneration claims. Ledger replay alone is not dictionary-state reconstruction.

**Likely actual behavior / verification boundary.** Runtime verification and contract adjudication required. The source exposes insufficient-looking retention paths, but a complete isolated reconstruction probe was not executed.

**Existing coverage and why its oracle misses this.** Existing tests show IDs in the ledger and history surviving deletion, not full historical authorization recovery.

**Independent regression recommendation.** Add an isolated artifact-graph reconstruction oracle, including budget omission, alias-only approval, skill, disable/delete and retention-off cases.

**Narrow repair direction.** Prefer bounded applied-rule provenance or a deduplicated lease-governed frozen manifest if required; do not store raw dictionary content in operational envelopes or bypass deletion.

**Downstream impact.** M14 export provenance and M15 regeneration versus replay claims.

**Pinned source evidence.** [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S24: Training evidence contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md) [S25: Artifact contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/artifacts.md) [S27: M10 skill registry boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/developer/skills.py)

### M05-AUDIT-16 — The normalization benchmark can pass a matcher that performs no vocabulary work

**Severity:** TEST GAP  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Benchmark validity / performance coverage

**Canonical requirement.** Performance passes require the intended actual work, correct populations, explicit budgets and separate cold/warm/scoped paths.

**Code location.** `scripts/v2/benchmark_m05.py`

**Current behavior and failure mechanism.** The 10,000-entry cohort uses aliases beginning with "tirm", while the normalization workload contains no such alias and only asserts a nonempty result. A disabled/identity vocabulary matcher can pass that timing cohort. The selector is not wholly vacuous: selected and omission counts are checked, and timing budgets already affect the exit code. Missing stress dimensions include real dictionary edits, active shared-first-word scans, actual app scope-upgrade work and complete workload identity.

**Minimal reproduction.** In a scratch test harness, replace only vocabulary matching with an empty proposal generator and run the original benchmark. Keep selector work intact. Separately alter selected scope membership while preserving counts to test its scope oracle.

**Expected behavior.** The normalization work-validity gate fails before a fast timing earns a pass. A valid dense-hit benchmark asserts authored text, exact edit counts and IDs.

**Likely actual behavior / verification boundary.** Source confirms the no-hit workload and weak normalization oracle. Mutation experiment and current timings NOT_RUN.

**Existing coverage and why its oracle misses this.** The inherited benchmark explicitly checks term counts but not actual dictionary normalization work. M04’s repaired benchmark has stronger independent per-sentence work checks; M05 has not inherited them automatically.

**Independent regression recommendation.** Add positive, no-hit, dense-hit, shared-first-word, long-alias, 10k-entry and scope-upgrade cohorts. Invalid work must produce nonzero exit. Report p50/p95/p99 and interpreter/platform/SHA.

**Narrow repair direction.** Harden the benchmark, not the production matcher merely to meet a clock. Preserve historical M5 Pro results and label new cloud timings algorithmic only.

**Downstream impact.** M05 performance claims and M15 readiness evidence.

**Pinned source evidence.** [S11: M05 benchmark](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/scripts/v2/benchmark_m05.py) [S16: M05 historical handoff](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md) [S17: M05 historical acceptance](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/acceptance/M05/results.json) [S19: Evaluation plan](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

### M05-AUDIT-17 — Current live-scope, privacy and race oracles are thinner than the connected system

**Severity:** TEST GAP  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Cross-interface validation

**Canonical requirement.** Current M05 must be tested with M06/M10 scopes, M07 cleanup and M14 evidence, not only its historical global pipeline.

**Code location.** `Four tests/v2/vocabulary suites and their integration helpers`

**Current behavior and failure mechanism.** The inspected suites contain useful direct scope fixtures, but the pipeline suite predates actual live M06/M10 scope/profile composition. Generated negatives deliberately avoid known aliases; many acceptance checks can stay green without a competing scoped contender or matched negative surface. Independent ranking tuples, full mutation coverage and barrier-driven races are missing. Raw error-path privacy canaries are not demonstrated across all M05 producers.

**Minimal reproduction.** Run paired real-alias positives/negatives with every scope populated, then repeat with refresh/selector/store/evidence faults. Run sequential profiles/workspaces, barrier-controlled dictionary edits, complete ranking ties and privacy canaries.

**Expected behavior.** Each acceptance condition proves the expected nonempty population and verifies output, winning ID, snapshot scope and evidence together. Native-only work remains separately pending.

**Likely actual behavior / verification boundary.** New challenge cases are NOT_RUN. This is a test-gap finding, not a claim that every listed scenario currently fails.

**Existing coverage and why its oracle misses this.** The historical 120 generated negatives are useful substring controls, not 120 independent real-world intent examples. Exact fixture counts and archived pass counts do not establish unseen holdout performance.

**Independent regression recommendation.** Use the delivered corpus and independent runner; require each material bug’s regression to fail the inherited implementation. Keep family-level exposure accounting and mutation survival counts.

**Narrow repair direction.** Add focused compatibility tests rather than re-auditing or rewriting other milestones.

**Downstream impact.** M04/M06/M07/M10/M14 interfaces, privacy confidence and honest M15 inputs.

**Pinned source evidence.** [S12: Matching suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S15: Pipeline suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py) [S30: Vocabulary fixtures](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json) [S31: Hint matrix](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_hint_matrix.json)

### M05-AUDIT-18 — Torn-table repair is tested on an empty vocabulary, not surviving user state

**Severity:** TEST GAP  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** Migration / data preservation

**Canonical requirement.** Current schema repair must not silently destroy surviving M05 data; M02 v11 safeguards must remain authoritative.

**Code location.** `tests/v2/vocabulary/test_vocabulary_store.py::test_store_repair_recreates_vocabulary_tables; store.py migration/repair`

**Current behavior and failure mechanism.** The M05 test drops entry/alias tables from an empty database, reopens, checks table names and adds a new row. That proves additive schema recreation but says nothing about a surviving populated entry set when aliases/history/index/meta is missing. It also does not prove counter recovery and cache invalidation.

**Minimal reproduction.** Create a populated scratch vocabulary with approvals, history and conflicts. In separate copies remove only alias table, history table, unique index or revision metadata. Reopen under current schema 11 and inspect backup/refusal/repair behavior and surviving bytes.

**Expected behavior.** Preserve surviving records; refuse with an explicit backup/error when safe reconstruction is impossible. Never report an empty recreated dictionary as successful recovery of lost content.

**Likely actual behavior / verification boundary.** Runtime verification required; no corrupted database was opened in this audit. No assertion is made that the current general store necessarily mishandles every cohort.

**Existing coverage and why its oracle misses this.** Empty-table recreation is a vacuous oracle for data preservation. Accepted M02 core-table protections must be exercised at the M05-owned boundary rather than assumed.

**Independent regression recommendation.** Assert exact before/after entries, alias approvals, history, counter/index state and clear classification of irrecoverable missing rows.

**Narrow repair direction.** Only adjust M05-owned repair tests/handling proven defective; never roll back schema to historical v3 or weaken M02 missing-core-table guards.

**Downstream impact.** M05 durability; all downstream snapshots depend on trustworthy recovered state.

**Pinned source evidence.** [S10: Current store and migrations](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py) [S13: Store suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py) [S34: M02 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

### M05-AUDIT-19 — The future qualified-adapter test proves shape, not qualification identity

**Severity:** TEST GAP  
**Confidence:** High — source-confirmed mechanism; runtime reproduction not performed  
**Category:** ASR extension contract

**Canonical requirement.** S30.1 qualification is per adapter + checkpoint + runtime, with supported capability and evidence, not merely a boolean.

**Code location.** `tests/v2/vocabulary/test_hint_selection.py::test_request_fields_shape_pinned_for_qualified_adapter; capabilities.py`

**Current behavior and failure mechanism.** The synthetic test flips contextual_biasing.supported to True on a generated manifest and checks request keys. It does not challenge missing/mismatched checkpoint/runtime qualification, stale evidence or actual context_snapshot_id propagation. Current production remains explicitly unqualified, so this is not a present decoder-support misrepresentation.

**Minimal reproduction.** Create supported-looking manifests with missing checkpoint, changed runtime, missing evidence or wrong context snapshot; assert refusal or explicit unqualified disposition. Use a complete synthetic identity as the positive.

**Expected behavior.** No advertised model-family capability or generic supported=True bypasses the qualification contract.

**Likely actual behavior / verification boundary.** Future-path runtime contract verification required. Production unqualified behavior is source-supported and conservative.

**Existing coverage and why its oracle misses this.** The existing test is honestly described as request-shape pinning; it should not be cited as full capability qualification.

**Independent regression recommendation.** Add identity-bound positive/negative manifest tests and actual predecode serialization checks; acoustic qualification remains a separately authorized model-backed task.

**Narrow repair direction.** Keep production fields None until a real implementation is qualified. Do not add an unsupported decoder or conduct M15 acoustic experiments during M05 remediation.

**Downstream impact.** Future M15 decoder-versus-post-ASR comparisons.

**Pinned source evidence.** [S08: ASR capability boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py) [S14: Hint suite](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py) [S18: Specification](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)

## Design Concerns

### D1 — Informational language is not locale isolation

Language is stored but not consulted by scope_matches or alias resolution. The same alias in two languages can collide in one scope. Neutral technical terms currently work across locales. Do not retrofit a language filter without defining neutral terms, locale fallback and migration behavior; first characterize and document the consequence. The language metadata persistence defect remains finding 12. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py)

### D2 — Explicit wrong rules and common-word canonicals

An explicitly approved `cloud→Claude` rule can rewrite ordinary weather prose. An approved common-word canonical can impose its capitalization. Historical M05 openly measured the lone-wrong-approved-entry limitation. Same-scope ambiguity and scope ownership are legitimate safety controls; an invented semantic intent adjudicator is not part of deterministic M05. Negative controls must not demand that identical surface text receive two different outputs without a contractual contextual discriminator. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S16: M05 historical handoff](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md) [S31: Hint matrix](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_hint_matrix.json)

### D3 — Suggested and conflict-masked vocabulary as context

The audit brief’s strongest reading excludes suggestions from hints and cleanup context, while the current selector intentionally includes enabled in-scope suggestions and the cleanup contract permits frozen hint terms. This is a real policy mismatch that needs explicit adjudication. Offering is not direct rewrite authorization, but prompt influence is not purely observational either. Require a declared answer, separate hint source/approval visibility and paired intended-use controls before changing selection. Do not silently label this a proven M07 validator bypass. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S23: M07 cleanup contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/cleanup.md) [S26: ASR hints contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)

### D4 — Frozen usage ranking, pin starvation and duplicate canonicals

Usage does not invalidate matching snapshots, so rank freshness may be indefinitely stale. Pin-first ranking can exhaust a budget before a narrow unpinned rule. Duplicate canonical strings from different entries can occupy slots. These are approximations/policies, not proof of a wrong matcher scope. Record them and decide any changed selector contract separately from ownership repairs. [S01: Vocabulary contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md) [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py)

### D5 — Scope representation and workspace homonyms

Workspace identity is a name/project segment, not a path; identical labels can intentionally share a scope. App identity is stable bundle ID, not PID. M05 exact site comparison relies on normalized M06 input; it does not itself canonicalize every imported URL representation. Characterize host/scheme/port/trailing-dot/www variants and profile deletion/rename/inherit behavior under current contracts. Do not require symlink or nested-path semantics the product has not defined. [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S21: M06 context contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md) [S22: M10 profiles contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md)

### D6 — Import/file transaction and identity policy

Per-mutation atomicity does not automatically promise an atomic whole-file import. Choose all-or-nothing preflight/transaction or explicit partial completion, but never conceal committed mutations behind a generic failure. SQLite’s stated NOCASE guarantee is narrower than Unicode casefolding; the importer’s lookup must be coherent with the chosen guarantee, not accidentally broader. Alias order should not produce revision churn when it has no semantic authority. [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S10: Current store and migrations](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py) [S38: Store contract](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)

## Areas Verified Strong

“Verified” here means supported by inspected committed source, not newly executed tests.

1. Normal matching filters approved/enabled/in-scope entries and approved aliases before collision resolution; disabled/suggested entries do not ordinarily mask approved term rules.
2. Matcher scope precedence is deterministic and independent of pin/frequency; successful-path cache identity includes app, site, workspace and profile and uses bounded storage.
3. Successful M06 rescoping uses captured entries rather than a live store reread; current History retry explicitly uses an unscoped fresh snapshot with a source label.
4. The tuple-alias repair and alias-only revision bump exist; sequential writes maintain entry/aliases/history/counter in one operation; usage is intentionally separated from matching invalidation.
5. Current unqualified ASR requests remain honest: no invented contextual biasing, no zero-offer ignored label and no acoustic hit derived from post-ASR dictionary membership.
6. M04 protected code/literal and command-position logic remains in the shared engine; same-span layer precedence is explicit.
7. Ordinary term edits carry approving IDs; successful hints are retained in lease-governed artifacts; the benchmark already has selector population checks and an exit-code timing gate.

These strengths constrain remediation. An all-global fallback, empty matcher, no-alias policy or blanket deletion of useful context is not an acceptable “fix.” [S02: Vocabulary domain and selector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py) [S03: Vocabulary persistence](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py) [S04: Normalization grammars](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py) [S05: Current M04 engine](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py) [S06: Live application integration](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py) [S08: ASR capability boundary](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py) [S09: Evidence collector](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py) [S11: M05 benchmark](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/scripts/v2/benchmark_m05.py) [S36: M04 remediation addendum](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)

## Adversarial Corpus Summary

**File:** `LocalFlow_M05_Adversarial_Corpus.json`  
**Cases:** 226  
**Named families:** 66  
**Execution:** every case is `NOT_RUN`; no observed_result is populated.

The corpus includes exact Unicode string oracles where the contract is determinate, and explicit invariant/state-machine cases where current registry setup or policy adjudication is required. It covers every requested category: positives, matched-surface negatives, collisions, scope precedence, unapproved/disabled/deleted states, language characterization, canonical no-op/overlap, quote/literal/code protection, actual skill intent, snippet composition, scope transitions, independent ranking contrasts, budgets, deep mutation, imports and privacy/evidence.

Thirty stateful definitions include all fourteen specifically requested probes and additional refresh failure, selector failure, stale RMW, approval/edit, panel selection, post-answer identity, historical reconstruction, torn schema, duplicate-error privacy, M02 deletion, retry and M14 approval interfaces. Twelve single-field mutation cases and ten metamorphic relation definitions are separate from ordinary fixtures. They are test specifications, not an executable runner or claimed passed tests. Large budget populations have deterministic generation instructions; snippet same-span cases require concrete valid current registry setup to be frozen by the implementing test, rather than an invented constructor API.

### Corpus category counts

| Category | Cases |
|---|---:|
| M04 command ambiguity | 4 |
| aliases/canonical no-op | 3 |
| budget truncation | 8 |
| cross-scope precedence | 17 |
| disabled/deleted | 1 |
| evidence/privacy | 18 |
| exact positives | 16 |
| hint ranking | 8 |
| import/export | 40 |
| language | 4 |
| matched-surface false positives | 22 |
| mutability/stateful probes | 45 |
| overlapping phrases | 7 |
| quotes/literals/code | 12 |
| same-scope collisions | 5 |
| scope transitions | 7 |
| snippet/skill conflicts | 3 |
| suggested/unapproved | 6 |

## Stateful / Metamorphic / Mutation Test Plan

Run the supplied corpus against the inherited SHA first. Preserve its bytes and checksum, record each case’s effective policy and record exact real runtime output separately. Do not edit an expected value simply because production produces it. A finding may be reproduced, narrowed, refuted, already fixed, test-gap-only or design-only; preserve the reasoning and supporting evidence for each disposition.

Use acknowledged operations for sequential transitions and latches/barriers for overlapping operations. Synchronize snapshot/edit, scope-upgrade/edit, hit/delete, panel/capture, import/snapshot and preview/commit directly. Never use a sleep and a single lucky outcome as race proof. Direct constructor tests and public Store/import tests are distinct admission boundaries.

Metamorphic checks cover scope narrowing/removal, mid-flight freeze, approval transitions, canonical no-op, punctuation wrappers, unrelated global isolation, HintSet identity, import idempotence and stable-ID insertion/hash-order determinism. Mutate each behavior field independently; prove that disabling the matcher, skipping every fourth edit, removing a scoped contender, changing a ranking tie-break or dropping rule IDs cannot earn a green acceptance result.

After the first-pass production SHA is frozen, a separate reviewer should author at least one new matched positive/negative family and execute it without the implementer tuning on it first. That newly authored family may provide a limited independent challenge; the supplied visible corpus is never called blind. No statistical prevalence claim follows from either.

## Downstream Impact

| Interface | Preserve | Repair/verify |
|---|---|---|
| M04 | Literal/code protection, command-position rules, layer precedence, near-linear arbitration, configured default/retry semantics | Vocabulary delimiter ownership, canonical claims, dictionary-skill provenance |
| M06 | Bounded destination collection and frozen-entry upgrades | Scope rescope independent of optional hints; no wrong-job last-good fallback |
| M07 | Repaired semantic validator and bounded approved alias authorization | Exact frozen scope/pairs/canonical inputs and explicit suggestion policy |
| M10 | Resolved profile identity, snippet precedence, manifest-skill semantics | Dictionary approving metadata survives registry and profile transitions |
| M13 | Usage facts remain separate from model/evidence success | Actual dictionary applications, not hint offers/no-ops, count as hits |
| M14 | Explicit approval and reference-quality boundaries, M02 deletion protection | Correct deterministic-stage provenance, failed-retention reasons, reconstructability |
| M15 | No implementation started | Supply honest frozen inputs and separate decoder effects from post-ASR repair |

## Recommended Repair Order

**First: authority and occurrence.** Reproduce and repair 01/02; establish regression oracles before changing their code. Add 03’s left-overlap no-op test, 06’s transactional barriers, 07’s strict admission and 08’s stable-selection authorization early because they can change text or committed approval state.

**Second: identity and provenance.** Repair 04/05/09 and adjudicate 15. Verify that scope upgrades, skill registries, cleanup inputs and retained artifacts consume the same immutable identities, with no live-store reconstruction after the answer.

**Third: management/evidence precision.** Repair 10–14; decide the explicit design policies before changing selection or import semantics. Keep historical evidence intact.

**Fourth: proof and performance.** Close 16–19, update active descriptions under 20, run targeted compatibility and actual-work benchmarks, freeze first-pass SHA and complete independent adversarial review. Reproduce every reviewer finding against that first-pass SHA before fixing; each confirmed review regression must fail first pass and pass final.

## M05 Readiness Verdict

### C. Significant vocabulary/scope/evidence weaknesses

The source reveals independent risks to occurrence ownership, cross-job scope isolation, mutable identity, concurrent dictionary state and approval targeting. These exceed a small documentation-only or isolated UI cleanup. The deterministic foundation is useful and should be repaired narrowly, not replaced.

This verdict is a **source-grounded remediation priority**, not a statement that twenty failures were executed or that Daniel’s installed app has exhibited them. Portable runtime reproduction remains the first remediation action; native/model-backed status is `PENDING_LOCAL_VERIFICATION` where relevant. Pending runbook checks do not block the next read-only milestone audit unless an unverified condition invalidates downstream static analysis.

## Coverage and Explicit Remaining Evidence

The required overview, milestone/specification/evaluation vocabulary boundaries, contracts, M05 implementation, core suites/fixtures, benchmark, accepted remediation constraints and live app/skill/learning interfaces were inspected. Reads were pinned to one SHA, and the complete recursive Git tree was used alongside direct file reads rather than relying only on code search. The report does not claim complete dynamic coverage of every caller or destination provider.

The following requested evidence is **not supplied as a result**: current portable suite outcomes; actual concurrent interleavings; all API malformed-type and crash-fault matrix outcomes; cross-process hash-seed determinism; populated torn-schema recovery results; current scaling/timing distributions; raw-event canary outcomes; native panel usability; live Accessibility transitions; model-backed hint influence. The corpus/handoff specifies these next actions. Historical results remain historical.

## Pinned Source Index

Every link below names the audited commit rather than moving main. Function-level locations in the findings are the navigation anchors; no unverified line numbers are invented.

- **S01 — Vocabulary contract:** [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/vocabulary.md)
- **S02 — Vocabulary domain and selector:** [localflow/v2/vocabulary.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary.py)
- **S03 — Vocabulary persistence:** [localflow/v2/vocabulary_store.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/vocabulary_store.py)
- **S04 — Normalization grammars:** [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/syntax.py)
- **S05 — Current M04 engine:** [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/normalize/engine.py)
- **S06 — Live application integration:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/app.py)
- **S07 — Dictionary panel:** [localflow/v2/dictionary_panel.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/dictionary_panel.py)
- **S08 — ASR capability boundary:** [localflow/v2/capabilities.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/capabilities.py)
- **S09 — Evidence collector:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/training.py)
- **S10 — Current store and migrations:** [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/store.py)
- **S11 — M05 benchmark:** [scripts/v2/benchmark_m05.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/scripts/v2/benchmark_m05.py)
- **S12 — Matching suite:** [tests/v2/vocabulary/test_vocabulary_matching.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_matching.py)
- **S13 — Store suite:** [tests/v2/vocabulary/test_vocabulary_store.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_store.py)
- **S14 — Hint suite:** [tests/v2/vocabulary/test_hint_selection.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_hint_selection.py)
- **S15 — Pipeline suite:** [tests/v2/vocabulary/test_vocabulary_pipeline.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/test_vocabulary_pipeline.py)
- **S16 — M05 historical handoff:** [docs/v2/handoffs/M05.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M05.md)
- **S17 — M05 historical acceptance:** [docs/v2/acceptance/M05/results.json](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/acceptance/M05/results.json)
- **S18 — Specification:** [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_SPEC.md)
- **S19 — Evaluation plan:** [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)
- **S20 — Milestone definitions:** [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/LOCALFLOW_V2_MILESTONES.md)
- **S21 — M06 context contract:** [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/context.md)
- **S22 — M10 profiles contract:** [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/profiles.md)
- **S23 — M07 cleanup contract:** [docs/v2/contracts/cleanup.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/cleanup.md)
- **S24 — Training evidence contract:** [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/training_evidence.md)
- **S25 — Artifact contract:** [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/artifacts.md)
- **S26 — ASR hints contract:** [docs/v2/contracts/asr_hints.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/asr_hints.md)
- **S27 — M10 skill registry boundary:** [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/developer/skills.py)
- **S28 — M14 learning boundary:** [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/learning.py)
- **S29 — M14 stage classification boundary:** [localflow/v2/curation/classify.py](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/localflow/v2/curation/classify.py)
- **S30 — Vocabulary fixtures:** [tests/v2/vocabulary/fixtures_vocabulary.json](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_vocabulary.json)
- **S31 — Hint matrix:** [tests/v2/vocabulary/fixtures_hint_matrix.json](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/tests/v2/vocabulary/fixtures_hint_matrix.json)
- **S32 — Shared native verification runbook:** [docs/v2/VERIFICATION.html](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/VERIFICATION.html)
- **S33 — M01 remediation addendum:** [docs/v2/handoffs/M01.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M01.md)
- **S34 — M02 remediation addendum:** [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M02.md)
- **S35 — M03 remediation addendum:** [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M03.md)
- **S36 — M04 remediation addendum:** [docs/v2/handoffs/M04.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/handoffs/M04.md)
- **S37 — Current normalization contract:** [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/normalization.md)
- **S38 — Store contract:** [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/store.md)
- **S39 — References contract:** [docs/v2/contracts/references.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/references.md)
- **S40 — Preferences contract:** [docs/v2/contracts/preferences.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/preferences.md)
- **S41 — Reader entry point:** [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/START_HERE.md)
- **S42 — Repository overview:** [README.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/README.md)
- **S43 — Project status:** [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/STATUS.json)
- **S44 — Contract index:** [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/267d1c25910328f72afff7096eb2a442e96a5174/docs/v2/contracts/INDEX.md)

## Claude Code Cloud Handoff

The complete copy-paste-ready handoff is supplied separately as `LocalFlow_M05_Claude_Cloud_Remediation_Handoff.md`. It transfers the finding IDs and locations above without duplicating the full audit. Read it with this report and the frozen JSON corpus. No remediation has been performed by this audit.
