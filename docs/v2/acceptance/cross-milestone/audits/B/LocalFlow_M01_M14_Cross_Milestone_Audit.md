# LocalFlow V2 — Final M01–M14 Cross-Milestone Read-Only Audit

**Date:** 2026-09-28  
**Repository:** scalinity/LocalFlow  
**Audited commit:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**All target execution:** `NOT_RUN`


## Executive Assessment

**Verdict B — Proceed after targeted cross-milestone repairs.** The accepted remediation lineage is present. The strongest source-supported concerns are narrow producer/consumer failures, not missing milestones: current-attempt History selection, retry identity in Your Voice, a legacy clipboard caller, and missing relational-governance repair. Current source also supports bounded Export UI defects and an unresolved publication/completion crash seam. [S01] [S02] [S04] [S05] [S09]

The report records **4 High, 5 Medium and 2 Low findings**, plus **5 Test Gaps and 2 Design Concerns**. No Critical defect was established in the inspected paths. This is not a zero-Critical guarantee for uninspected code or an execution verdict. Every proposed reproduction remains `NOT_RUN`; the local handoff requires independent reproduction/refutation before repair.

M15 is **not authorized**. Dependency eligibility is not equivalent to current model, native, human or performance qualification. In particular, M11’s integrated model record remains unsuccessful, M07 retains a long-prompt/real-text obligation, and current end-to-end latency has not been measured in this audit. [H07] [H11] [G07]

Deliverables: this report; the 176-case declarative JSON corpus; the 40-interface matrix with functional surfaces; and a local-only remediation handoff. These are audit specifications, not newly executed evidence.


## Audit Boundary

> This audit covers committed GitHub state at 340c566686c7123bfcf721e16160aacabbe0b97d. Any uncommitted local state is outside the GPT-6 audit boundary.

All repository reads were pinned to that commit after resolving remote main. No repository files, branches, commits, settings or worktrees were modified. No LocalFlow target test, app, model, benchmark, database migration, native window or human check was executed. Only audit documents and their declarative consistency checks were authored in the working sandbox.

Evidence labels used here: **static observation** is a source-derived behavior; **inherited automated evidence** is a committed historical report at its recorded SHA; **predicted runtime result** requires the specified local witness; **Test Gap** is missing independent closure, not an asserted production failure. Native, real-model and human results remain separate.

Reading covered the core campaign documents, all fourteen handoffs and targeted remediation addenda, the shared contracts and the concrete coordinator/Store/History/profile/learning/export/Hub seams named in the source catalog. It was not a byte-for-byte audit of every tracked file or a complete executable-branch reconstruction for every registry entry. Exhaustive caller, migration-opener, privacy-canary and production-test binding closure is explicitly retained in 12–16, not represented as passed. Connector code search returned misses for known symbols, so no miss was used as evidence of absence.

Pinned source references at the end make the report portable. Function names are the primary location anchors; any numerical source ranges refer to the pinned repository source, not JSON-wrapper citation line numbers.


## Canonical Main / Lineage

Remote `main` resolved to `340c566686c7123bfcf721e16160aacabbe0b97d`, matching the prompt’s baseline. Root tree: `596a7cc0d812cffb0a0c319a3cccc910cc6c4eb2`; immediate parent: `0e5cdcc8287c51ee5218eaef25a119d1fdb6d494`. No intervening commit existed at the observed resolution. The local Mac’s `origin/main`, installed bundle and worktree were not read.

Each direct comparison or transitive link below returned an ahead relationship with no behind commits and the base as merge base. This proves ancestry, not suite compatibility:

| Milestone | Accepted/integrated anchor | Verified ancestry witness |
| --- | --- | --- |
| M01 | 3db74061f23001b9cce3d4fe029e0b30cbc295d6 | direct → main; ahead 158, behind 0 |
| M02 | bfbc63c35efa6273cc13242d54d3e5bbe264b21e | direct REST compare → main; merge base equals base |
| M03 | 3e0d1ab972b866b4acbda622984bce04e8f95093 | direct → main; ahead 150, behind 0 |
| M04 | 4ef219c52598e92a9857e9e0dec13ca7143f56dc | → M05; ahead 6, behind 0 |
| M05 | 01a1f3c07ed3270aa1e7b3da39d89c453c84c1e8 | → M06; ahead 7, behind 0 |
| M06 | 4388b521cedfebe5a16dc8c485d25275f0b342f0 | → integrated M11; ahead 9, behind 0 |
| M07 | 52edc4753df9be17d9119e95d760c4086c5649cd | → M01; ahead 12, behind 0 |
| M08 | ea83bc198567d001e3d770ae5103ca369701825d | → M09; ahead 35, behind 0 |
| M09 | a304d48c3adf0ef7639fe66986d8affe41a2264a | → M10; ahead 16, behind 0 |
| M10 | ed5e20631529e063564b151555215485ec316a53 | → M12; ahead 16, behind 0 |
| M11 | 9a049b341d315201ba7d8019585fd7e71370af31 | → M08; ahead 17, behind 0 |
| M12 | b17aa2bee82c46ef9f01d680e1b1031629744835 | direct → main; ahead 39, behind 0 |
| M13 | 36e03a2a30e380729ceb56d3f1f41bea751bbb4f | direct → main; ahead 19, behind 0 |
| M14 | 9d0cfdf85f459149b5382f432f7663cda5b16446 | direct → main; ahead 6, behind 0 |

M11’s integrated anchor intentionally differs from the earlier cloud/remediation anchors; cherry-picked/reconciled production is not missing history merely because an earlier parallel SHA is not the direct ancestor. M14 production `9d0cfdf…`, later evidence/benchmark-validity work and the merged docs head are distinct provenance objects. Preserve all three classes rather than replacing every historical SHA with main. [H11] [H14]


## Current System Architecture

| Milestone | Role | Authority produced |
| --- | --- | --- |
| M01 | Baseline / evaluation / source identity | Pinned fixture and environment identities; coverage registry |
| M02 | Jobs, artifacts, Store, import, events, retention | One writer and authoritative persistence/deletion primitives |
| M03 | Capture / worker / retry / restart | Capture provenance and job/attempt/lifecycle ownership |
| M04 | Numeric and spoken-syntax normalization | Typed edits, barriers and raw→normalized ledger |
| M05 | Scoped vocabulary | Approved revisioned rules and frozen matching scope |
| M06 | Destination/context collection | Owned handle and immutable pre-decode snapshot; explicit late delta |
| M07 | Faithful cleanup | Applied Clean output, validated fallback, exact model evidence |
| M08 | External insertion / clipboard / undo | Target lease, actual transaction, confirmation and bounded edit attribution |
| M09 | Hub / History / diagnostics | Rendered identity, async publication and user action routing |
| M10 | Styles / snippets / developer workflows | Per-job tuple; one-shot mode; file/skill confinement |
| M11 | Transforms / Prompt Engineer | Task identity, definition revisions, mode-specific gate and explicit judgments |
| M12 | Scratchpad | Durable note revisions, origin spans, internal delivery receipts and note liveness |
| M13 | Usage / Insights / readiness | One logical dictation fact, independent usage retention, qualified reports |
| M14 | Learning / review / splits / export / Your Voice | Explicit approval and delta undo; shared evidence qualification; deterministic profile |

```text
M03 capture/job/capture provenance
  ├─ M02 artifacts + leases + deletion barrier
  ├─ M06 owned context handle/pre-decode freeze
  │     └─ M05/M10 frozen vocabulary/style/snippet/file-skill tuple
  └─ M03 worker ASR → M04 normalization → M07 Clean applied result
                                      → optional M11 validated transform
                                      → M08 external transaction
                                      OR M12 note-bound durable delivery
                                        ├─ M09 History / actions
                                        ├─ M13 one-job usage / Insights
                                        └─ M02 governed evidence
                                              → M12/M08 attributable corrections
                                              → M14 review/candidate/approval → M05
                                              → M14 deterministic Your Voice
                                              → M14 splits / qualified offline export
```

The pipeline is not a sequence in which context begins after ASR. Context collection and tuple freezing overlap capture; only explicitly permitted bounded finalization/late-delta work follows. Likewise, learning/profile/export are downstream consumers, not implicit runtime policy updates. [C03] [C04] [C05] [C02] [C08]


## Producer → Consumer Interface Map

The separate `LocalFlow_M01_M14_Interface_Matrix.md` enumerates **40 important interfaces**, including the frozen/mutable fields, identity/revision, deletion and timeout behavior, owning coverage and risk. It also inventories twelve product-surface groups and ten end-to-end outcome variants.

The highest-risk edges are not generic “cross-system” failures: M09 owns current History selection (01); M14 owns profile cohort and historical term interpretation (02/03); the M08 coordinator integration owns the legacy copy caller (04); M02 owns relational repair admission (05). The rest are primarily bounded M14 UI/export repairs. [S01] [S02] [S04] [S05] [S09]

| Path | Identity | Authoritative route | Downstream effect |
| --- | --- | --- | --- |
| A external confirmed | J/A/F | Captured target → qualified actual final → external result | History final + one usage fact; training still needs appropriate explicit review |
| B saved-not-inserted | J/A/F | Target mismatch/refusal retains final | No external success; History actions need fresh authority |
| C posted-unverified | J/A/F + transaction | Pending payload ownership until settlement policy ends | No confirmed-visible latency or automatic truth label; guard all internal copies |
| D failed | J/A + partial artifacts | Failure reason and recoverability; no invented expected final | Partial example can support later retry but must not shadow current attempt |
| E cancelled | J/A + revocation | Cancel/close prevents downstream publication | Terminal truthful state; no late insertion or duplicate usage |
| F retry | Same J/capture; A increments | New attempt output, original time/sample provenance retained | Usage replaces; History current-attempt resolver and profile logical dedup need repairs |
| G Scratchpad | J/A + note/revision/region | Internal delivery only after note commit receipt | No AX/clipboard fabrication; autosave not counted as speech |
| H transformed | J/A + Clean artifact + transform task/output | Applied transform final; review/fallback keeps Clean | Auto-apply is not human preference; Teach transformed final intentionally refuses |
| I Raw | J/A + raw path | Original ASR, bypass normalization/cleanup per mode contract | Recorded effective Raw; no snippet rewrite; final selection still attempt-qualified |
| J collection off | J/A; no new training example required | Operational History may retain text under its own logging policy | Usage independent; reduced evidence cannot silently reconstruct a training manifest |


## Job / Attempt Identity

`job_id` represents a logical dictation; `attempt` represents a retry execution; capture provenance is not replaced by retry time. Training examples and transform candidates are evidence/task objects and cannot automatically be treated as distinct captures. Note `source_job_id` is provenance, not a new capture or a retention pin. [C01] [C02] [C05]

M13’s partial uniqueness and replacement discipline is stronger than M14’s text-based profile deduplication. History also mixes a current job row with potentially older manifest-selected artifacts. Findings 01 and 02 therefore identify distinct repairs: current output authority versus cohort identity. Fixing one does not fix the other. Historical retry examples may remain legitimate for review; they must not masquerade as current final text or independent speech volume. [S02] [S03] [S05]


## Terminal Outcome Semantics

| Term | What is proved | Translation | What is NOT proved |
| --- | --- | --- | --- |
| confirmed | M08 positive confirmation, or explicitly typed M12 durable internal receipt | Job external insertion_confirmed; usage confirmed with delivery kind preserved | Not an acoustic/cleanup gold label by itself |
| posted_unverified | Paste/event posted without required readback | Job insertion_unverified; usage posted_unverified | Not failed posting, not confirmed visible text, not human acceptance |
| saved_not_inserted | Final retained, no authorized delivered write | Job saved_not_inserted; usage saved_not_inserted | No fabricated insertion; final may be copied via a new authorized action |
| failed | Capture/inference/delivery failure under explicit reason | Job failed_recoverable or failed_unrecoverable; usage failed | No final_words invented from an unfinished candidate; partial evidence remains partial |
| cancelled | Explicit lifecycle cancellation | Job cancelled; usage cancelled if fact is recorded | Late output cannot revive insertion authority |
| outcome_unknown | Caller stopped waiting after admission; effect may commit | Operation state, not an additional dictation terminal outcome | Preserve ID and reconcile receipt; never blindly retry as a new effect |
| refused / deferred | Action not admitted or authority unavailable | Specific typed action result; not necessarily a job failure | A no-transaction action creates no executed-repaste fact |

M08 external confirmation and M12 internal durable delivery can share an analytics-level successful disposition only when the destination/method distinguishes them. Unknown outcome belongs to an operation’s acknowledgement state; it cannot be casually substituted for a terminal failed dictation. No-edit or posted-unverified observations are not human acoustic references. [C02] [C05] [C06]


## Unknown Outcome / Idempotency

The key linearization point is the committed domain operation, not the caller returning. A writer admitted before a timeout may commit afterwards. M10 preallocated IDs and M14 operation receipts provide concrete mechanisms for returning the original effect; M13 also has committed operation/revision state and UI reconciliation. These mechanisms must survive through the actual Hub callback. [C01] [C02] [C04] [H14]

No exhaustive all-caller pass is claimed. The local inventory must include vocabulary CRUD/import/approval, transform definitions/candidates/observations, note changes, labels/splits/export/profile actions, usage deletion and all Hub writers. In particular, a new operation ID allocated after an unknown outcome is not idempotent merely because each operation is serialized. Receipts must reject identity reuse for another kind/target. 13 is the explicit closure gate; race R015 separately concerns filesystem publication, not just a caller timeout.


## Final Text / Mode Authority

The canonical **semantic** selector should yield an object containing job, attempt, stage, artifact ID/digest, selected text, requested/effective mode and refusal reason—not just a string. Select an actually applied transform over Clean; otherwise select the applied Clean result; Raw is the original ASR path under its explicit mode contract. When an expected final stage is unavailable, report unavailable rather than choosing an earlier stage or another attempt. [S02] [C04] [C05] [C07]

This is a recommended consolidation of current semantics, not a claim that every consumer already calls one shared implementation. History has a stage selector, but 01 shows a weaker upstream attempt selection. Teach’s transformed-final restriction is intentional: the UI refuses instead of teaching against unseen Clean text. No repair should “solve” that refusal by silently falling back. Requested transform mode also remains distinct from effective Clean after opt-out, unbound definition or failed gate. [C07] [S06] [C04]


## Scope / Context Composition

M10’s scope comparison explicitly reuses M05’s canonical representation: trimmed values; app bundle ASCII case normalization; site scheme/host case and trailing-slash normalization; workspace/profile names otherwise exact. No www/port aliasing or inferred filesystem equivalence is authorized. The M06 title-derived origin is evidence, never site-scope permission. [C03] [C04]

A job freezes an owned context handle and rule tuple. Final scope projection uses the frozen entry set, not a dictionary re-read. A late downstream snapshot is a separate revision with a parent pointer; it is not a mutation of pre-decode context. Deferred/failed widening restores the captured tuple as a whole. The cross-interface corpus challenges dictionary edits, transform edits, focus changes and stale publication without incorrectly forbidding these documented revisions. The separate historical-term bug03 occurs in Your Voice, not in the runtime scope comparator.


## Normalization / Protection Composition

The actual normalizer uses precedence and span ownership, not independent blind replacements applied in the milestone-number order. Protected/literal/quoted syntax outranks ambiguous command interpretations; M10 snippet/skill matching composes with the typed grammar and vocabulary under its documented collision rules. Generated snippet/file spans carry output-coordinate protection into M07, while raw-coordinate ledger spans retain their own meaning. [H04] [C04]

M07 consumes normalized text, mapped protection, bounded frozen vocabulary and an allowed destination category—not arbitrary nearby text or instructions from the screen. Raw bypasses both normalization and cleanup. A second text-only normalization call is not the supported way to reprocess generated spans; one pass per job is the contract. The corpus crosses signs, dates, versions, quote escapes, snippets, Unicode offsets and exact literals into M11. Static checks cannot estimate how often the real ASR/model triggers a lexical fallback. [C03] [C04] [H07]


## Transform Composition

Transform identity freezes mode/source/instructions/examples/locale; definition and prompt revisions remain separately recorded. Retry Original is the same task; changing the source or transforming a result is a new task. Original selection/note destination remains bound across chaining rather than following the current caret. [C05]

The gate is deliberately mode-specific: Prompt Engineer requires clause/content/operator coverage; Polish and Concise check operator preservation without the same full content threshold; Custom promises exact-carry literal checks, not universal semantic preservation. `needs_review` and `fallback_original` do not auto-apply. Dictation auto-application records candidates, not human judgments. No supported gate-bypass was established in the inspected call paths; full dynamic caller proof remains pending. [C05] [S14]

The inspected auto-transform recorder does not independently copy source/output payloads at that call site; the governed collector owns those payloads. A live note that survives moving text from a deleted job can have independent transform authority, with note liveness checked in the writer and deleted-job linkage detached. This is not evidence that automatic late output may resurrect deleted job text. [S01] [S14]


## External Insertion vs Scratchpad

External insertion requires M08 target lease/revalidation and truthful readback semantics. Scratchpad delivery requires M12’s captured note/revision/region and a committed revision receipt. An internal receipt does not prove an AX write, and an external result must not accidentally generate a note write. The mode, final stage and logical job should survive both delivery routes. [C06] [H12] [C02]

Typed autosave, restore and note edits are not extra dictations. A note deleted while processing cannot be replaced by the currently selected unrelated note. The corpus requires UTF-16/codepoint and changed-revision checks on the actual note/transform integration. These are compatibility tests, not a new note storage design.


## History / Hub Action Identity

Action authority is rendered stable ID plus the exact content/revision the user saw. Retry requires live recoverability and an owned claim; Teach requires expected final artifact/attempt; Save/Move requires durable destination creation before source deletion; Copy/Paste Again requires live final content and a new authorized insertion decision. A reordered row index is never the source authority. [C07] [S01] [S06]

The inherited rendered-item discipline is strong, but its final-text producer has the collection-off retry seam01. Recovery Copy Last Raw is another entry point entirely and bypasses pending clipboard admission04. A safe History button does not prove its legacy Recovery counterpart is safe. Both require actual coordinator callbacks in regressions, not helper-only assertions.


## Hub Query Generation / Stale Publication

M09 supplies bounded asynchronous work and rendered/generation state; later panes also have domain-specific revision or receipt semantics. Tokens do not have to share one integer implementation to be sound, but each needs a clearly defined invalidation boundary: new query, mutation, deletion, note/pane switch and close. [S09] [S10] [C07]

Export Validate is a concrete exception: it publishes an action result outside the late-refresh ownership model, and a later-arriving old refresh can replace it (06). Validation also runs synchronously in the callback (07). Treat result lifetime and event-loop responsiveness as separate assertions, even if one bounded worker/generation repair addresses both. General multi-pane dynamic revocation is test gap14; no global generation failure is inferred from this one pane.


## Note Provenance → Learning

The M14 note miner uses M12’s stronger attribution surface rather than relying solely on an independent whole-note diff. This preserves the distinction between dictated region A, dictated region B, typed-only text and transform-origin text. Repeated-word alignment and Unicode ambiguity must fail conservatively instead of inventing an acoustic correction. [S06] [H12] [H14]

The existence of canonical attribution is a source-supported strength, not a proof that all async note revision races are closed. The corpus holds the miner across autosave and deletion, then checks source revision, exact spans and evidence liveness before candidate/export publication. A label about intended writing is not automatically a verbatim ASR reference.


## Analytics Exactly-Once Composition

M13 owns the one-dictation-per-logical-job fact. A retry reaching terminal replaces the prior fact, while an explicit selection transform or actually executed repaste is a separate activity. An auto-transform does not duplicate dictated words; note autosave is not an activity counted as dictation. Original capture instant and reporting provenance remain separate from retry-to-terminal timing. [C02]

Reports use a coherent cohort/revision and explicit denominators for durations and outcomes. Confirmed and posted-unverified remain distinguishable; failed/cancelled jobs do not acquire a fabricated final word count. These are real architectural strengths, but the audit has not run a current ten-path end-to-end exactly-once sweep. In particular, M13 uniqueness cannot repair M14’s separate example-based cohort02.


## Privacy / Event Envelope

| Data | Classification | Required boundary |
| --- | --- | --- |
| IDs, counts, stage codes, validator versions | Content-free operational metadata | Typed event allowlist; no freeform private values in reason strings |
| App names/bundles, file/workspace locators, profile names | Private metadata | Permitted private usage/context/config stores; not arbitrary generic events |
| Audio, transcript, normalized/Clean/transformed output | Governed private content | Owned artifacts with lease/deletion/role/digest authority |
| Note text, images, corrected spans, candidate terms | Governed private content (candidate rule terms also private) | Note/candidate stores and linked artifacts; sanitize failures and diagnostics |
| Vocabulary terms, rule names, profile phrases/cards | Private configuration or derived governed content | Historical applied-rule provenance; source liveness and exclusion/redaction rules |
| Explicit dataset payloads and lineage | Explicit export content | Consent/view/task qualification, safe publication, offline hashes and closure; avoid live content in committed audit evidence |

The generic event contract is a typed envelope, not a safe place for arbitrary exception strings, paths or profile terms. Application metadata may be useful private usage data without being permitted generic telemetry. A synthetic canary sweep must exercise success, refusal, timeout and corrupt-data errors across every emitter; this audit did not execute that exhaustive sweep and does not declare event privacy globally passed. [C01] [C02] [C03]

Generated audit fixtures contain only synthetic conceptual data. The local handoff additionally requires pre-commit scanning for real-user paths, truncated path fragments, session IDs, live transcripts/notes, and private model/profile terms.


## Deletion / Expiry / Retention Propagation

| Authority change | Must revoke/remove | Intentionally independent | Composition condition |
| --- | --- | --- | --- |
| Job/content deletion | Raw/normalized/Clean/transformed job artifacts; recovery/debug copies; linked candidates/labels and dependent profile claims | Allowed usage facts independent; independently saved live note follows note authority | M02 deletion barrier plus domain invalidation; current UI must reconcile; missing links defect05 |
| Note deletion | Note revisions/attachments and governed note-transform/mining copies; note evidence links close | Unrelated independent source speech is not automatically erased merely because a note referenced it | M12 note liveness + M14 canonical attribution; late miner must refuse |
| Usage deletion/expiry | Usage facts/aggregates and every usage-derived profile copy | Retained transcript/audio/note text and independently eligible speech claims | M13 writer redaction and query epoch; no false unknown→failed transition |
| Artifact expiry/purge | Task eligibility and derived claims that require that artifact | Unrelated records and artifacts with independent live interests | All consumers must qualify current liveness, owner, role, path and digest |
| Profile evidence exclusion | Current snapshot invalidation and exclusion from future profile generation | Source remains retained for other authorized purposes unless separately deleted | Durable exclusion identity, not a temporary UI filter |
| Export consent revocation | Future export admission/publication under current policy | An already disclosed self-contained package cannot be claimed remotely recalled by a local DB deletion | Explicit publication linearization and historical manifest; new qualification uses current authority |

Leases need explicit owner/purpose: user pin, review-derived evidence, training buffer, note-derived interest and any export hold are not interchangeable. Removing one interest cannot override a different live interest, while a user pin must not be inferred merely from an incomplete role blacklist. M14’s repaired review/unpin seam is retained. The major remaining static concern is05: deletion logic cannot revoke a derived copy through relationship rows that startup silently discarded. [C01] [H14] [S04] [S05]


## Artifact / Filesystem Authority

M14’s shared qualification requires more than artifact existence: retained payload, correct owning job/example, expected role/stage and valid content authority. That predicate is reused by readiness/export paths; History and other action surfaces still need their own correct attempt-qualified source before invoking a consumer. [S07] [S08] [S02]

Managed artifact/note reads use constrained names, no-follow/regular-file admission, and export audio can stream through the canonical managed opener. M10’s explicit configured roots and descriptor-relative discovered descendants are a different authority source but should preserve the same confinement principle. No downstream consumer may turn a frozen filename/skill into an arbitrary fresh path read. Exhaustive caller and all-CLI proof remains15. Corrupt DB locators are tested in disposable fixtures, not treated as permission to access Daniel’s files. [C01] [C04]


## Schema / Migration / Repair Composition

| Schema | Recorded ownership/addition | Invariant to preserve |
| --- | --- | --- |
| 1–2 | M02 core jobs/artifacts/training/import + indexes | Original rows/identities and import idempotence |
| 3 | M05 vocabulary family | Entries/aliases/history/meta remain coherent; no empty torn dictionary |
| 4 | Earlier additive lineage between vocabulary and target schema | Preserve exact migration DDL; full version-specific fixture binding remains local, not guessed here |
| 5 | M09 job_targets | Original destination metadata and capture ordering |
| 6 | M10 style/snippet/meta family | Rule revisions and trigger ownership survive upgrade |
| 7 | M11 transforms/revisions/candidates/observations | Old definitions and same-task source/target identity survive |
| 8 | M12 notes/revisions/attachments/evidence links | Durability/provenance relations not repaired into silently empty state |
| 9 | M13 usage facts/aggregates | One-job uniqueness and independent usage retention |
| 10 | M14 candidates/labels/sampling/splits/membership/profile/export family | Cross-family support and exposure links stay intact |
| 11 | M02 deletion barriers and repair hardening | Late producers cannot recreate deleted job-owned content |
| 12 | M13 usage_meta/revision/zone/operation state | Timestamp precision and reporting semantics preserved, not reinterpreted |
| 13 | M14 operation receipts and vocabulary deltas | Retry/undo effects retain exact operation and delta authority |

**Current source schema version is 13.** The full version-4 DDL and every released-version fixture were not re-derived here; that specific historical detail remains a local binding obligation rather than a guessed table description. Current backup and single-writer discipline are not enough to establish relationship integrity by themselves. [S04] [C01]

Finding05 gives a deterministic missing-profile-link witness. Inventory the complete `_CORE_DEPENDENTS`, expected-table set, domain-level torn-family guards and every Store opener. A fresh empty database, a legitimate old schema and a corrupted current schema require different decisions. A blanket `CREATE TABLE IF NOT EXISTS` repair must not erase the evidence that a current populated family is corrupt. Backups precede any repair, and no test uses the live store.


## Learning / Vocabulary Composition

A candidate, sample, profile, abstention or rejection does not authorize a runtime rewrite. Explicit approval delegates to M05’s canonical scope, revisioned writer history and exact vocabulary delta; Undo reverses only that delta and preserves newer user edits. M14’s repaired service transaction should not be replaced by a looser app-level sequence. [S06] [S12] [H14]

The remaining product seam09 is distinct: the service exists, but the Hub does not expose Undo Approval. A new control must carry the rendered candidate/delta/revision and operation ID through unknown outcomes. Do not reopen the whole learning milestone or redesign its visual shell to fix this action.


## Readiness / Dataset Export Composition

Readiness and export use shared current qualification predicates for task/view membership, including named cleanup tiers and exact evidence requirements. Compare sets of record IDs and reasons, not just totals: “ready ten” can accidentally agree with ten different exported records. The corpus removes audio, expected final input, current labels and source liveness to assert refusal monotonicity. [S07] [S08] [C02]

An offline package must contain the source/target/task/prompt/definition/evidence lineage and hashes needed for its own declared task. A live private DB foreign key is not offline closure. Direct SQL pair forgery remains a corruption-defense residual when supported producers enforce task identity and export requalifies; no supported producer bypass was established here. [C05] [H14]

The publish writer recheck is strong, but SQLite and rename are not jointly atomic.08 requires crash reconciliation, while06/07 concern the UI representation/execution of standalone validation. These three issues must not be merged into a vague “export broken” claim.


## Your Voice / Usage / Evidence Composition

Your Voice is a **local deterministic ProfileService**, with measured fields separated from interpretive cards and usage-derived metadata. No API provider or key is needed for the inspected generation architecture. The current interpretation policy requires the minimum word volume and ten eligible dictations; below that floor, measured-only output is honest while interpretation is unavailable. [S05] [C08]

Three weaker consumer reconstructions remain: text equality in place of logical-capture identity02; current dictionary canonical in place of frozen applied revision03; surviving-link-only liveness after a missing-table repair05. Normal source deletion/exclusion and M13 same-op usage redaction are valuable protections, but they assume the right cohort/provenance and intact dependency graph. [S05] [S04] [C02]

No whole-profile injection into runtime behavior was established. The inspected unit test alone is not a complete noninterference proof because its two normalization calls both occur after profile creation; use a genuine before/after controlled pipeline test as part of12. This is a coverage observation, not evidence of an actual injection path. [T01]


## Family / Exposure Integrity

A selected split version is historical assignment data; current “exposed ever” knowledge is authority for a new qualification decision. Once a family is exposed, choosing an older split or deleting the exposed example cannot make another member newly blind. Historical manifests remain immutable descriptions of what was exported then, while new exports must consult current exposure. [S08] [H14]

The M11 fixtures labeled blind at creation were subsequently observed during integrated evaluation. Keep that history; do not claim the same exposed cases as new independent held-out proof in remediation. Mutation and stateful corpus cases explicitly challenge older assignment selection, publication races and post-delete family continuity. [C05] [H11]


## Performance Composition

| Path | Current requirement/target | Audit result |
| --- | --- | --- |
| 1–20 words, release→insert | P50 ≤0.75 s; P95 ≤1.25 s | Fresh current pipeline NOT_RUN |
| 21–50 words | P50 ≤1.25 s; P95 ≤2 s | Fresh current pipeline NOT_RUN |
| 51–200 words | P50 ≤3 s; P95 ≤6 s | Fresh current pipeline NOT_RUN |
| 201–500 words | P50 ≤8 s; P95 ≤12 s | Fresh current pipeline NOT_RUN |
| 500-word explicit transform | P50 ≤8 s; P95 ≤15 s | Current M11 benchmark gate remains pending |
| UI acknowledgement | P95 ≤50 ms | Validate call path needs repair/measurement (07) |
| Additional post-release context | P95 ≤75 ms | Shared budget/precompute architecture exists; no fresh measurement |
| History search at 50k rows | P95 ≤200 ms | No current composed contention measurement |
| Startup UI / cached model readiness | ≤1 s / ≤15 s | Installed bundle/environment not inspected here |

**Inherited M14 observations, not new measurements:** the corrected final benchmark reports profile compute around 560 ms P95 with worst observed dictation-writer wait about 205 ms; export around 509 ms with worst writer wait about 174 ms. Stronger authority checks changed the workload/cost, so older faster implementation numbers do not establish a regression-free current budget. [H14]

Measure three separate things: event-loop blockage, queued dictation writer wait, and background operation wall time. Then measure actual current release→terminal/verified-visible end-to-end latency. Do not add unrelated benchmark medians or equate “posted unverified” with the moment text became visibly confirmed. Use cached current models, fixed synthetic fixtures and workload hashes. Baseline first; then one background workload at a time—Insights, profile, miner, export, autosave, search—with repeated idle baseline controls. Only after attribution should an explicitly labeled multi-load stress run be considered.

The local handoff requires p50/p95/p99, maxima, denominators, failures/timeouts, work-validity controls and environment/source identities. A no-op or different-work benchmark is INVALID, not fast. Whether the observed writer waits are acceptable is design concern17, bounded by the actual S24 E2E requirements. No correctness check may be removed merely to recover an old number.


## Documentation / Registry / Verification State

`STATUS.json` contains a legitimate historical implementation provenance layer and some stale current-looking descriptions. `ORCHESTRATION.html` points to the cross-milestone phase and distinguishes dependency eligibility from manual completion. Reconcile these semantic roles rather than forcing every file to share one timestamp/SHA.10 identifies the current-summary drift. [G03] [G04] [H14]

The registry maps **33 requirements to 22 suites**. That is a coverage claim, not proof each current test node exists and reaches its production interface.12 requires an executable binding ledger; connector search misses were not used as dead-test proof. [G09]

Actual verification article IDs were enumerated by milestone, excluding the maintainer example. There are **80 declared checks**:

| Milestone | Declared IDs | Count | Instruction/code anchor |
| --- | --- | --- | --- |
| M01 | M01-V001…V011 | 11 | M01-r1/r2; 3db7406 |
| M02 | M02-V001…V009 | 9 | M02-r1; bfbc63c |
| M03 | M03-V001…V008 | 8 | M03-r1; 3e0d1ab |
| M04 | M04-V001…V003 | 3 | M04-r1; 4ef219c |
| M05 | M05-V001…V003 | 3 | M05-r1; 01a1f3c |
| M06 | M06-V001…V004 | 4 | M06-r1; 4388b52 |
| M07 | — (placeholder) | 0 | No check revision |
| M08 | M08-V001…V008 | 8 | M08-r1; ea83bc1 |
| M09 | M09-V001…V007 | 7 | M09-r1; a304d48 |
| M10 | M10-V001…V004 | 4 | M10-r1; ed5e206 |
| M11 | M11-V001…V006 | 6 | M11-r1; 9a049b3 |
| M12 | M12-V001…V005 | 5 | M12-r1; b17aa2b |
| M13 | M13-V001…V005 | 5 | M13-r1; 36e03a2 |
| M14 | M14-V001…V007 | 7 | M14-r1; 9d0cfdf |

No duplicate actual check IDs were observed in this enumerated set. The empty M07 placeholder is a real ownership gap11, not evidence its milestone passed with no checks. The runbook stores personal results in browser-local `localflow.v2.verification/state@1`; committed HTML does not reveal Daniel’s present checkbox statuses. Changed instruction revisions are intended to make old results stale rather than silently reuse them. Browser migration/import behavior and full prior-section byte-preservation were not executed/independently closed in this audit. [G10]

M01-V011 explicitly defers its release-to-insert pilot to M15. Keep it superseded, not passed. Old native checks can be superseded only by an explicit same-scope current automation record under runbook policy; an inherited green suite alone does not authorize changing a human checkbox.


## Historical Residual-Risk Ledger

| Owner | Residual | Current disposition | Required follow-through | M15 impact |
| --- | --- | --- | --- | --- |
| M01 | Installed source/model/config identity; private snapshot parity; E2E pilot | Still relevant to deployed-source qualification; V011 explicitly superseded by M15, not passed | Do not erase original capture/environment provenance | Before current installed/model claims |
| M02 | Native shutdown/retention/import/backup parity; repair-family integrity | Historical hardening retained; defect05 exposes a remaining relationship-family seam | Synthetic migration matrix plus caller inventory; user-store check remains human-owned | Privacy/upgrade blockers relevant |
| M03 | Real microphone loss/sleep/quit; worker lifecycle and retry original provenance | Portable repairs inherited; real hardware cases remain separate | V001–V008 and retry multihop cases; no hardware performed here | Before live acceptance claims |
| M04 | Real spoken numeric/syntax incidence and reference-Mac work validity | Lexical/static regressions do not measure ASR incidence | V001–V003, preserve exact values/operators/coordinates | Quality/performance qualification |
| M05 | Real app/profile scope, dictionary UI, optional ASR biasing qualification | M10 closes prior profile-scope wiring limit; no assumed biasing support | V001–V003; profile historical-term consumer repair03 | Scope service preserved, derived claim pending |
| M06 | Real browser AX origin exposure, permissions and same-app window changes | Owned-native tests not universal host certification; title-derived origin intentionally nonauthoritative | V001–V004; frozen-tuple/target multihop tests | Real host/privacy qualification |
| M07 | Lexical validator limitations, false-safe rejection rates, long-prompt trial and real-text stratum | Explicitly still open in current handoff; deterministic gates are not full semantic proof | Add/transfer actionable runbook ownership; do not tune on frozen blind results | Real-model/product gate |
| M08 | Real app clipboard/undo/terminal and correction observation | Core ownership strong; missed Recovery caller04 remains | V001–V008; owned delayed-host copy regression | External insertion blocker04 |
| M09 | Human keyboard/size/window/replay behavior; synchronous CRUD paths | Generic generations remain useful; later Export action has bounded exception | V001–V007; pane-specific native race checks | Functional pending, visual redesign separate |
| M10 | Real skills/file references/terminal snippet trial; partial-listing limitations | Exact relative path admission versus ambiguous bare-name rejection intentional | V001–V004; preserve no-follow and snapshot behavior | Native/user workflow qualification |
| M11 | Integrated real-model review misdirection, output-limit fallbacks, missing complete current benchmark; six human checks | Still open, not superseded by portable 37/37 or inherited cleanup green | Current model-backed compatibility and explicit benchmark gap; never reblind exposed families | Explicit M15 gate |
| M12 | Five human checks; bounded capture/edit acknowledgement versus durable commit; non-editor synchronous operations | Durability/provenance repairs retained; standalone timings not end-to-end proof | V001–V005; receipt/Unicode/typed-origin multihop tests | Native/human functional pending |
| M13 | Five human counts/filter/retry/delete/keyboard checks; contention | One-job usage and same-op redaction remain strengths | V001–V005; profile redaction and retry composition | Native/human and pairwise performance pending |
| M14 | Export refresh, publish/commit crash, no Hub Undo Approval, direct-SQL pair forgery defense, stronger-check writer waits | 06/08/09 need repair/adjudication; direct-SQL forgery alone not new supported-path defect;17 is performance policy | V001–V007; four high cross-seam findings plus targeted residual handling | Not an M15 authorization |

This ledger captures the material residual families surfaced in the inspected handoffs/addenda. It does not claim every historical sentence is a separate unresolved defect. Explicit accepted limitations—title-origin evidence, opaque workspace names, Custom gate scope, independent saved notes, legacy evidence and externally released packages—are preserved rather than rediscovered as defects.


## Manual / Native / Model Verification Ledger

**No human result was performed, inferred or changed.** The HTML’s eighty declarations include automatable parity/performance work, true hardware/product trials and a superseded item. They are not eighty newly confirmed “pending” personal results. Current committed M12/M13/M14 handoffs explicitly retain five/five/seven human checks, and M11 retains six. [G10] [H11] [H12] [H13] [H14]

| Group | Carried qualification | Disposition |
| --- | --- | --- |
| M01–M05 | Source/config/model parity, safety of copies, hardware capture, real syntax/dictionary trial | May run alongside narrow repairs where code unaffected; no human action here |
| M06/M08 | Real browser/window/field privacy, delayed clipboard, undo, terminal behavior | Native owned regressions for04 first; real host checks remain human-owned |
| M07 | native-m07-long-prompt-cleanup-trial and adjudicated real-text stratum | Explicitly pending; central runbook mapping missing11 |
| M09/M10 | Keyboard/focus/scale and real scoped styles/skills/file/snippet workflows | Functional tests after touched callers; visual design phase remains separate |
| M11 | 37 portable/16 native/8 seam inherited integration; 40-case real-model run exit1 | 10 applied;0 applied semantic failure;1 review-addresses-loss;1 review-misdirected;14 review-no-loss;14 output_limit fallback;0 errors. Not all green. |
| M11 performance/human | Current reference-Mac benchmark scope and V001–V006 | Model gate and timing scope must be explicitly resolved before M15 authorization |
| M12 | V001–V005: writing/delivery, interruption, images/export, transforms, restore/History transfer | Pending human; inherited owned-native automation does not replace every trial |
| M13 | V001–V005: counts, filters, retry, usage deletion, keyboard | Pending human; same-op usage/profile redaction has inherited automated evidence |
| M14 | V001–V007: copied-store upgrade, Teach/approve, labels, A/B, export, profile, keyboard | Pending human; V001 is Daniel’s copy-of-real-store check, not authorized to this audit/remediation agent |
| Current cross-seam native/model | All new corpus adapters, current isolated E2E, pairwise contention | NOT_RUN; local remediation may execute synthetic native compatibility, but not Daniel’s checks or M15 |

The M11 integrated 40-case record includes **PE-BLIND-008’s misdirected review**. Zero applied semantic failures is useful but does not erase that failed review gate or the fourteen truncation fallbacks. No new model conclusion is inferred from static code. [H11]


## M15 Readiness Matrix

| Prerequisite | Classification | Current evidence | Required next action |
| --- | --- | --- | --- |
| Accepted M01–M14 lineage present | satisfied by current static evidence | Fourteen anchors verified as ancestors of audited main | No source omission found; does not certify behavior |
| Canonical job/attempt/final authority | blocked by cross-milestone finding | 01 and 02; separate M13 usage identity stronger | Reproduce/repair; fail-first interface tests |
| Insertion/clipboard ownership | blocked by cross-milestone finding | 04; native delayed-host outcome NOT_RUN | Canonical guarded-copy caller + owned native verification |
| Deletion/privacy/upgrade integrity | blocked by cross-milestone finding | 05; broad migration matrix15 still open | Repair governance-family opening and test downstream invalidation |
| Your Voice historical evidence meaning | blocked by cross-milestone finding | 02/03/05; deterministic service itself present | Logical cohort + frozen term revision + missing-link integrity |
| Review/Export functional action surface | blocked by cross-milestone finding | 06/07/09; 08 needs explicit crash-recovery adjudication | Bounded UI action repairs, not a visual redesign |
| M07 faithful cleanup real-text/long-prompt quality | pending real-model verification | Current M07 handoff explicitly leaves trial/stratum open | Map runbook ownership and perform authorized later qualification |
| M11 Prompt Engineer model gate | pending real-model verification | Integrated 40-case run exit 1; one misdirected review and 14 output-limit fallbacks | Resolve/adjudicate quality gate without relabeling fallback as applied |
| M11 benchmark completeness | pending native verification | Current reference-Mac benchmark remains open; Polish/Concise scope not closed | Current valid-work measurements under approved policy |
| Human destination/keyboard/audio/product checks | pending human verification | Runbook has 80 declared checks, not 80 known pending results; browser-local statuses unavailable | Daniel retains human execution; preserve supersession/revisions |
| Owning-suite compatibility at accepted anchors | satisfied by current automated evidence (inherited records only) | Committed handoff/acceptance reports; not freshly rerun on main here | Use exact historical SHA; broad post-repair sweep still required |
| Current composed performance under S24 | pending native verification | No fresh E2E or pairwise contention; 205/174 ms historical writer waits are not UI timing | Isolated reference Mac p50/p95/p99 and failure-inclusive cohorts |
| M15 AC01/08: packaged offline operation | pending native verification | Local architecture supported statically; installed bundle/assets/permissions outside boundary | Later packaged current-adapter offline qualification |
| M15 AC02/06: frozen quality/corpus conditions | pending real-model verification | No M15 acceptance run; current unresolved M07/M11 obligations | 140 speech +20 negative baseline scope and independent references per current milestone |
| M15 AC03/04: budgets and full failure accounting | pending native verification | No current result distribution measured here | ≥30 unique per latency band ×5 warm;10 cached cold processes; report failures |
| M15 AC05: external comparator | not applicable when skipped with explicit reason | No external upload/credential use authorized or performed | Real comparator evidence only when explicitly authorized; otherwise honest unsupported/skipped |
| M15 AC07: portable/live dataset closure | pending human verification / blocked by cross-milestone finding | 25-case portable and ≥10 live retained/reviewed job qualification not performed;08/05 relevant | Offline validation, correct exposure and reference labels; no DB-dependent truth |
| Quiet Editorial and independent UI review | pending human verification; intentionally not started | Separate product phase after correctness remediation | Preserve functional matrix; no domain-contract changes without authorization |
| M16 final integration / acceptance | not applicable to this audit | Separate downstream milestone | Do not start |

Where multiple classifications apply, the blocking one wins for authorization. “Satisfied by current automated evidence” above means the repository contains accepted historical automation records; it does not claim this audit reran them at the final head. M15 itself remains a later, separately authorized qualification stage. [G07]


## Critical Findings

**None established by this static review.** This is not a complete-source or runtime zero-Critical certification. High findings04/05 concern important insertion and privacy boundaries and must be treated as blockers until independently reproduced/refuted and repaired, not dismissed because target execution was intentionally prohibited.


## High Findings

### CROSS-AUDIT-01 — History can prefer an old training manifest over a newer collection-off retry

**Severity:** HIGH · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M09 · **Compatibility:** M02/M03/M12/M13/M14  
**Producer → consumer:** Retry coordinator and EvidenceCollector → HistoryQueryService, then History actions

**Canonical requirement.** One logical job; current-attempt final-stage authority; no hidden fallback to an older attempt.

**Source locations.** app.py: retry coordinator and collection-off History persistence (4200–4450; 5840–6040); history_queries.py: _manifests, _job_artifacts, job_detail (355–465); training.py: _publish and on_failure. [S01] [S02] [S03] [C02] [C07]

**Current behavior.** History takes a non-null training manifest as authoritative for stage selection. It chooses the greatest artifact attempt only when no manifest exists. A retry can stop collecting training evidence while still writing newer History artifacts.

**Composition failure.** An attempt-1 failure leaves a legitimate partial manifest. Disabling collection before retry prevents its replacement, but does not prevent attempt-2 History output. The job row advances while the stage resolver still follows attempt 1. Stable job identity conceals stale content authority.

**Minimal deterministic reproduction (not executed):**

1. Create a synthetic job with transcript logging on and evidence collection enabled. Let ASR return ALPHA and force a recoverable cleanup failure after source evidence exists.
2. Pause collection. Retry the same job through the production retry coordinator with original capture provenance; let a controlled adapter return BETA and cleanup succeed.
3. Read History through job_detail and the list/detail final selector. Record jobs.attempt, manifest.attempt, chosen artifact IDs and artifact attempt metadata.
4. Invoke Copy, Save to Scratchpad and Teach admission against the rendered row; do not insert into a real application.

**Expected.** The current-success row resolves attempt-2 final BETA, or explicitly reports current final unavailable. Attempt-1 evidence stays accessible only as older evidence, never the current final.

**Likely actual / required runtime verification.** The manifest branch chooses attempt-1 raw/clean references (or no final) despite attempt-2 artifacts and a success state. The retry itself need not insert wrong text; the defect is downstream History/action authority.

**Existing coverage and why it is not composition proof.** History lineage and collection/retry suites exist, but separate tests do not establish the mixed consent transition. Inspect tests/v2/ui/ (bind actual History test nodes locally) and the M03/M02 producer suites; bind one regression across the real coordinator and query service.

**Regression and narrow repair.** Use a canonical job+attempt+stage resolver. Compare manifest attempt to current authority before selecting it; fall back only to qualified artifacts of that SAME current attempt. Add collection-on→off, off→on, unchanged consent, missing-current-final, and transformed-final controls.

**M15 impact.** Repair before treating History, notes saved from History, or reviewed evidence as current in M15.

### CROSS-AUDIT-02 — Your Voice can count multiple transcriptions of one capture as multiple dictations

**Severity:** HIGH · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M02/M03/M13  
**Producer → consumer:** EvidenceCollector retry publications → ProfileService._eligible and interpretation floor

**Canonical requirement.** One logical dictation and original capture provenance must not multiply through derived profile evidence.

**Source locations.** training.py: _publish; store.py: publish_example; profile.py: _read_candidates/_eligible (roughly 180–264), _compute_once; tests/v2/personalization/test_profile.py: add_example. [S03] [S04] [S05] [C02] [C08] [T01]

**Current behavior.** The collector can publish distinct examples for retry contexts. Profile eligibility scans examples and removes repeated normalized transcript strings; it does not first collapse examples by logical job/capture.

**Composition failure.** Text equality is weaker than logical identity. Two eligible attempts of one recording with different ASR text survive the verbatim-repeat filter, add words twice, and increase the example count used by the interpretation floor. This allegation requires distinct attempt transcripts; it does not assert a measured nondeterministic ASR rate.

**Minimal deterministic reproduction (not executed):**

1. Keep collection enabled. Publish two recoverable attempts of the same synthetic capture, with a controlled adapter returning two different transcripts and cleanup failing after ASR on each.
2. Compute a profile through the real collector→store→ProfileService interface. Compare distinct job IDs, distinct examples and eligible_examples/eligible_words.
3. Extend to ten eligible attempt publications of one capture, with sufficient distinct words to cross the configured floor. Keep the default 2,000-word and ten-example policy unchanged.
4. Positive control: ten independent captures; negative control: identical-text retry attempts and a failed-before-ASR attempt.

**Expected.** A profile has one defined contribution per logical capture, selected by an explicit eligible-attempt policy. Retries remain inspectable but cannot manufacture the ten-dictation floor.

**Likely actual / required runtime verification.** Different transcript keys survive deduplication, increasing the cohort and potentially enabling interpretation with fewer than ten actual dictations. Target reproduction must confirm exact retry publication/admission conditions.

**Existing coverage and why it is not composition proof.** test_profile.py creates a fresh job for every example. Its repeat test verifies equal text across separate jobs, not unequal text across attempts of one job. Analytics has a separate one-job uniqueness rule that cannot enforce this profile cohort.

**Regression and narrow repair.** Choose a documented canonical contribution per job/capture before text-repeat exclusion; retain full retry evidence elsewhere. Add a fail-first collector→retry→profile test and a metamorphic test: adding a retry cannot increase logical dictation count.

**M15 impact.** Blocks profile sample-size and interpretation claims used during M15 qualification.

### CROSS-AUDIT-04 — Recovery Copy Last Raw bypasses pending clipboard-paste ownership

**Severity:** HIGH · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M08 · **Compatibility:** M03/M09 coordinator callers  
**Producer → consumer:** Recovery menu copyLastRaw_ → Shared macOS pasteboard and an admitted delayed insertion

**Canonical requirement.** Internal LocalFlow copies must not replace an admitted/pending insertion payload.

**Source locations.** app.py: copyLastRaw_ (near 5983–5997), _guarded_copy; inject.py: copy_text; contracts/insertion.md: protected posted-unverified payload and internal recovery-copy policy. [S01] [S13] [C06]

**Current behavior.** copyLastRaw_ checks deleted-job state but calls the legacy copy_text function directly. That function clears/sets the pasteboard without the M08 guarded-copy admission used by newer callers.

**Composition failure.** A pending paste has already posted its event but the destination has not consumed its payload. A second LocalFlow action replaces that payload through an ungoverned caller. This is not the intentionally permitted case of the user independently copying something in another app.

**Minimal deterministic reproduction (not executed):**

1. Retain a synthetic failed dictation with raw text OLD_RAW.
2. Start a subsequent clipboard-based insertion of NEW_FINAL into an owned target. Hold the target’s clipboard read behind a deterministic barrier after posting, while M08 still protects the payload.
3. Invoke the production Recovery Copy Last Raw action, then release the target read.
4. Record guard admission, pasteboard generation, text consumed and truthful insertion outcome. Repeat after the pending lease has ended as a positive control.

**Expected.** During pending ownership the internal copy is refused/deferred, and the target receives NEW_FINAL. After protection ends the explicit copy can succeed.

**Likely actual / required runtime verification.** The legacy direct write can replace NEW_FINAL with OLD_RAW before consumption. Portable host reproduction and native owned-window confirmation are required; no actual wrong paste was executed in this audit.

**Existing coverage and why it is not composition proof.** M08 exercises paste restoration, pending ownership and guarded callers. Those tests do not establish that every legacy app callback uses the guard. Search all pasteboard write aliases, not just service methods.

**Regression and narrow repair.** Route this action through the canonical guarded-copy path and preserve its typed refusal/status. Add a production-callback→M08 delayed-target regression and inventory every direct copy_text/pasteboard caller.

**M15 impact.** Must close before external insertion compatibility or product-surface readiness is accepted.

### CROSS-AUDIT-05 — Torn-schema repair can erase governance links while leaving a current private profile

**Severity:** HIGH · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M02 · **Compatibility:** M14; compatibility with M05/M10/M12/M13 table families  
**Producer → consumer:** Store._migrate repair of a missing relational table → ProfileService liveness and delete-everywhere propagation

**Canonical requirement.** A partially missing relational family cannot be accepted as clean empty state; derived private content cannot outlive its source.

**Source locations.** store.py: _CORE_DEPENDENTS and _migrate (590–930; 1190–1510), delete_everywhere (2400–2635); profile.py: _scrub_dead_evidence (105–137), current (640 onward). [S04] [S05] [C01] [T01]

**Current behavior.** The repair inventory includes M14 tables, but profile_evidence is not treated as a core-dependent relationship whose unexpected loss blocks opening. Idempotent DDL can recreate it empty while populated profile_snapshots remain.

**Composition failure.** Profile liveness queries and deletion propagation join through surviving profile_evidence rows. After that table is recreated empty, those joins cannot discover a dead source. current() does not recover the missing dependency graph and can return the still-current text-bearing snapshot.

**Minimal deterministic reproduction (not executed):**

1. Build a synthetic schema-13 store using supported profile generation. Confirm a current snapshot with private canary phrases and nonempty profile_evidence.
2. Close the store. In this synthetic corruption fixture only, remove profile_evidence while leaving profile_snapshots and upstream evidence intact.
3. Reopen through Store with a backup directory. Record whether startup refuses or recreates the missing relation empty.
4. Delete the supporting job/example through the supported service and call ProfileService.current(). Inspect both DB payload and returned fields.
5. Controls: clean migration from a genuinely older schema, intact-link deletion, missing snapshot table, and a completely fresh empty database.

**Expected.** An unexpectedly missing populated governance family is refused/quarantined, or a documented conservative repair invalidates dependent derived content before exposing it. A pre-repair backup is preserved.

**Likely actual / required runtime verification.** Empty recreation can allow old measured_json/cards_json to remain current after source deletion because no evidence links survive to trigger invalidation.

**Existing coverage and why it is not composition proof.** Schema repair coverage and ordinary profile deletion coverage exist, but the latter assumes the relationship table survives. The inspected profile deletion test exercises intact links. This is a requested corruption-recovery threat model, not a demand to stop arbitrary malicious SQL.

**Regression and narrow repair.** Extend family-integrity checks or conservative invalidation to M14 relationships and receipts/deltas as appropriate. Do not silently reconstruct empty governance state from no evidence. Test each populated family’s missing root/link table and old-schema upgrades separately.

**M15 impact.** Blocks privacy/deletion and upgrade-integrity qualification until reproduced and repaired or narrowly refuted.


## Medium Findings

### CROSS-AUDIT-03 — Historical dictionary use is rendered using the entry’s current spelling

**Severity:** MEDIUM · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M05/M10  
**Producer → consumer:** Frozen applied vocabulary-rule evidence → Your Voice technical vocabulary views

**Canonical requirement.** Speech-derived claims must cite the rule revision actually applied, not writer-current configuration.

**Source locations.** profile.py: _compute_once, applied-rule ID mapping and current vocabulary_entries canonical lookup (325–575); ui/your_voice.py: technical terms label; vocabulary_store.py: revisioned editable fields. [S05] [S11] [S12] [C04] [C08]

**Current behavior.** Profile computation collects applied rule IDs from retained speech, then resolves those IDs to current enabled/approved vocabulary entries and their current canonical spellings.

**Composition failure.** An entry ID survives a legitimate user edit. Mapping an old application of revision 1 to the current canonical at revision 2 attributes newly configured words to speech in which that spelling was never applied.

**Minimal deterministic reproduction (not executed):**

1. Create approved entry E revision 1, canonical ALPHA_TERM, and a synthetic dictation whose frozen evidence records E revision 1 as applied.
2. Edit the same entry through VocabularyStore to revision 2, canonical BETA_TERM. Do not dictate BETA_TERM.
3. Regenerate Your Voice and inspect technical_vocabulary and its supporting example IDs; compare them with the retained frozen applied-rule record.

**Expected.** Historical-use labels show ALPHA_TERM with its captured rule revision, or omit an unresolvable historical term. A current-config mapping must be separately and honestly labeled.

**Likely actual / required runtime verification.** BETA_TERM can appear as a term applied in the older dictation because the consumer joins by stable entry ID alone.

**Existing coverage and why it is not composition proof.** M05 freezes applied rule records and M14 tests applied-ID provenance. Neither fact alone proves that a later canonical edit is interpreted historically. Bind a vocabulary edit→profile regeneration test.

**Regression and narrow repair.** Consume the frozen canonical/revision already provided by M05. Do not reconstruct historical truth from the current dictionary. Test rename, disable, delete, re-enable, scope edit and missing frozen record.

**M15 impact.** Repair before presenting technical-term profile claims as evidence-backed; no change to runtime vocabulary matching is required.

### CROSS-AUDIT-06 — A late Export refresh can overwrite a completed Validate result

**Severity:** MEDIUM · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M09  
**Producer → consumer:** Older Training/Models refresh completion → Export pane validation status

**Canonical requirement.** An older asynchronous result must not replace newer user-visible action truth.

**Source locations.** ui/hub.py: exportValidate_ (around 3600), _refresh_export_pane (3853 onward). [S09] [S10] [H14] [C07]

**Current behavior.** Validate renders its result directly into export text. The pane refresh separately renders last_export or “No export run yet” and does not retain a newer validation result as a first-class rendered action.

**Composition failure.** The specific Export action does not establish a generation ordering that prevents an earlier refresh callback from replacing the new validation report. This is a bounded M14 pane integration gap, not evidence that every M09 generation is broken.

**Minimal deterministic reproduction (not executed):**

1. Prepare an invalid synthetic dataset whose standalone validator deterministically reports a specific error.
2. Start a Training/Models refresh and hold its main-thread publication callback after the data has been read.
3. Run Validate and observe the error report. Release the older refresh callback.
4. Check that the displayed result remains bound to the validated destination and fingerprint; repeat across pane switch, close and reopen.

**Expected.** The completed validation result remains visible until an explicit newer relevant action supersedes it, or is clearly retained in a separate action result.

**Likely actual / required runtime verification.** The old refresh can replace validation errors with the last-export summary. Dataset contents and validator predicates are not changed by this visual-state defect.

**Existing coverage and why it is not composition proof.** M14 already records the residual. M09 generic generation tests do not prove this pane-specific result lifetime.

**Regression and narrow repair.** Give validation a destination/fingerprint/action-generation identity and fence older refresh publication. Preserve action state across the supported navigation lifecycle; add deterministic publication-order tests.

**M15 impact.** Close before using the Export pane as the operator’s qualification evidence, or explicitly isolate a reliable CLI workflow pending the functional repair.

### CROSS-AUDIT-07 — Export Validate runs potentially large filesystem work on the Hub callback

**Severity:** MEDIUM · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M09  
**Producer → consumer:** Export Validate button callback → Standalone dataset validator and main event loop

**Canonical requirement.** Main-thread responsiveness is separate from background wall time and writer contention.

**Source locations.** ui/hub.py: exportValidate_ and synchronous _training_action invocation; curation/export.py: standalone validator’s file inspection/hash work. [S09] [S08] [G05]

**Current behavior.** The callback invokes validation synchronously rather than scheduling the file traversal and hashing off the main thread.

**Composition failure.** A valid large export or slow filesystem can keep the UI callback occupied. This conclusion follows from the call path, not by treating the 205 ms profile writer-wait observation as a measured UI stall.

**Minimal deterministic reproduction (not executed):**

1. Bind the real Validate callback to a synthetic dataset and a validator file-read barrier.
2. Invoke the action on the owned native event loop. Attempt an independent UI acknowledgement while the read is held.
3. Release the barrier and verify completion publishes only for the still-current destination/generation.
4. Separately measure real validation workload sizes on the reference Mac; report main-thread stall and validator wall time independently.

**Expected.** The UI acknowledges promptly, work runs off the event loop, and completion remains generation-bound. Closing a pane cannot publish stale results.

**Likely actual / required runtime verification.** The current synchronous callback cannot finish until validation finishes. Exact p50/p95/p99 and user-visible stall require native measurement.

**Existing coverage and why it is not composition proof.** A standalone validator benchmark measures throughput, not responsiveness of its UI caller. Generic background query tests do not cover this callback.

**Regression and narrow repair.** Move validation to a bounded owned worker and publish by explicit generation. Retain all content/digest checks; combine the callback repair with CROSS-AUDIT-06 without conflating their assertions.

**M15 impact.** Functional responsiveness must be repaired/qualified before the product-surface phase; no timing gate is declared passed here.

### CROSS-AUDIT-08 — Export rename and database completion commit need crash reconciliation

**Severity:** MEDIUM · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M02  
**Producer → consumer:** Exporter publish_op and Store transaction commit → Export completion records, retry and recovery

**Canonical requirement.** Filesystem publication and SQLite completion must have truthful recoverable semantics, not asserted joint atomicity.

**Source locations.** curation/export.py: publish_op/final qualification/rename (660–930); store.py: writer executes callback before committing its transaction. [S08] [S04] [H14]

**Current behavior.** The final authority check, completion-row work and rename are inside one writer callback. However, the filesystem rename happens before Store commits the SQLite transaction.

**Composition failure.** A process death or commit failure after rename can leave a complete package with no committed completion record. Writer serialization closes concurrent writer races; it does not make SQLite rollback undo a filesystem rename.

**Minimal deterministic reproduction (not executed):**

1. Build a synthetic export in a child process with a barrier immediately after successful staging→destination rename and before Store’s SQLite commit.
2. Capture the package identity/hash manifest, terminate that child at the barrier, and reopen the synthetic store.
3. Validate the package in a separate process that has no live-store access. Compare its valid contents with the missing/failed completion record.
4. Retry/reconcile with the same operation identity. Assert no second logical export, no overwrite of an unrelated directory, no fabricated new consent/exposure qualification.

**Expected.** Restart reports published-but-unrecorded/unknown until a deterministic reconciler confirms the package and restores a truthful receipt, or a documented safe recovery workflow handles it exactly once.

**Likely actual / required runtime verification.** A valid package may exist without a completion record. The allegation does not mean the package is invalid or that pre-publication deletion fences are absent.

**Existing coverage and why it is not composition proof.** This is an explicitly recorded M14 residual. Successful-path export tests and timeout receipts do not establish post-rename crash recovery.

**Regression and narrow repair.** Adjudicate the publication state machine and add a durable recoverable identity/intent or an equally bounded reconciler. Requalify according to current policy when required; never silently relabel an old exposed package as a new blind export.

**M15 impact.** May be accepted as a bounded residual only with explicit recovery policy and demonstrated witness. Until then, block reliance on completion records as complete export inventory.

### CROSS-AUDIT-09 — Approved learning rules have service Undo but no Hub Undo Approval control

**Severity:** MEDIUM · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 · **Compatibility:** M05/M09  
**Producer → consumer:** LearningService approval and recorded vocabulary delta → User-facing Training/Review workflow

**Canonical requirement.** S22’s approved-rule undo/easy-disable promise must be accessible or explicitly deferred.

**Source locations.** Spec S22; M14 remediation residual ledger; Hub learning-candidate controls; M14 reversible approval/undo service. [G05] [H14] [S09]

**Current behavior.** M14 records working reversible approval at the service boundary, while its residual ledger explicitly states that the Hub has no Undo approval control.

**Composition failure.** Correct service capability is not a usable product action. A user approving a learned correction cannot invoke its exact delta undo from the same promised review surface. A generic dictionary edit is not necessarily that reversal.

**Minimal deterministic reproduction (not executed):**

1. Approve a synthetic candidate through the supported review workflow.
2. Inventory visible controls and keyboard actions for that rendered candidate and its approval delta.
3. Demonstrate service undo separately as a positive control; do not call that proof of UI reachability.
4. Inspect any explicit accepted deferral. No such waiver was established in the inspected current documents.

**Expected.** The user can invoke the existing safe undo against the rendered candidate/delta, or an explicit approved product deferral names the alternative and affected gate.

**Likely actual / required runtime verification.** No Hub control exposes the service operation. Native usability of a future control is NOT_RUN.

**Existing coverage and why it is not composition proof.** Service undo tests establish revision and delta safety, not the existence/reachability of a product control. The handoff itself identifies the residual.

**Regression and narrow repair.** Add only the bounded functional action using candidate/delta identity, expected revision, typed unknown outcomes and refresh invalidation. Do not redesign the visual shell. Alternatively obtain a recorded product-policy deferral.

**M15 impact.** Blocks the promised functional surface unless explicitly deferred; does not invalidate the already repaired M05 service authority.


## Low Findings

### CROSS-AUDIT-10 — Current STATUS fields still describe implementation-era M14 behavior and timings

**Severity:** LOW · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M14 documentation · **Compatibility:** M02/M13; orchestration consumers  
**Producer → consumer:** Implementation-era STATUS fields → Current campaign/readiness readers

**Canonical requirement.** Separate historical provenance from current campaign state without deleting history.

**Source locations.** docs/v2/STATUS.json: M14 current detail/benchmark fields versus source_commit_note; ORCHESTRATION.html; M14 remediation addendum; store schema version 13. [G03] [G04] [H14] [C01]

**Current behavior.** Historical implementation source provenance remains useful, but some unqualified status details still describe older approval sequencing and earlier performance rather than the accepted remediation.

**Composition failure.** Readers can interpret an implementation-era summary as the current product guarantee. The fix is not to make every historical timestamp or SHA equal to main.

**Minimal deterministic reproduction (not executed):**

1. Compare each M14 STATUS field with the remediation addendum and current source.
2. Classify each field as historical provenance, current campaign state, stale current detail or ambiguous ownership.
3. Check that the campaign’s next phase remains cross-milestone review/remediation, not implicit M15 launch.

**Expected.** Historical implementation fields remain explicitly historical; current state identifies the remediation anchors, schema and superseding evidence.

**Likely actual / required runtime verification.** Some current-looking summaries conflict with later accepted behavior/measurements. A historical source_commit by itself is not a defect.

**Existing coverage and why it is not composition proof.** Registry/schema syntax validation cannot resolve narrative provenance semantics. Use field-by-field semantic assertions rather than blanket text replacement.

**Regression and narrow repair.** Add explicit current-campaign/remediation references; qualify or update stale summaries only after the local code/evidence converges. Preserve old result records and source_commit_note.

**M15 impact.** Documentation closure before final readiness sign-off, not a runtime correctness blocker by itself.

### CROSS-AUDIT-11 — The central verification runbook has no M07 checks despite carried qualification work

**Severity:** LOW · **Confidence:** High (static source); target reproduction NOT_RUN · **Execution:** NOT_RUN  
**Primary owner:** M07 documentation · **Compatibility:** M11/M15 orchestration  
**Producer → consumer:** M07 handoff and model/human qualification obligations → VERIFICATION.html campaign ledger

**Canonical requirement.** Pending checks must have stable actionable ownership; an empty placeholder is not completion.

**Source locations.** VERIFICATION.html: section id M07, “No deferred checks recorded yet (IDs from M07-V001)”; M07 handoff residual/human verification and M11 integration model evidence. [G10] [H07] [H11] [G07]

**Current behavior.** The M07 section is an empty placeholder while current handoffs still distinguish cleanup model/product-quality qualification from static tests.

**Composition failure.** Counting the eighty populated checks makes the runbook look comprehensive although one milestone’s carried work has no stable check IDs or explicit in-page transfer of ownership.

**Minimal deterministic reproduction (not executed):**

1. Enumerate actual check article IDs by milestone, excluding the maintainer template.
2. Compare the empty M07 section with each still-open M07 human/model obligation and its later evidence.
3. For every obligation require either a stable current instruction ID, a documented superseding check, or an explicit M15-owned qualification reference.

**Expected.** No obligation disappears merely because another milestone has related tests. Historical checks can be superseded explicitly without being falsely marked passed.

**Likely actual / required runtime verification.** M07 has zero actual check articles; an actionable ownership reconciliation is needed. This does not imply M07 was never implemented or audited.

**Existing coverage and why it is not composition proof.** HTML ID uniqueness only checks existing articles. It cannot establish that every pending obligation has an article or owned deferral.

**Regression and narrow repair.** Reconcile residuals, then add stable M07 IDs or explicit cross-references where required. Preserve old IDs, statuses and historical results; do not invent human completion.

**M15 impact.** Must be reconciled before interpreting the runbook as a complete prerequisite ledger.


## Test Gaps

### CROSS-AUDIT-12 — Requirement-to-production-path coverage is not independently closed

**Severity:** TEST GAP · **Owner:** M01 registry; all suite owners · **Target execution:** NOT_RUN

The registry maps 33 requirements to 22 evaluation suites. This review did not reconstruct every current executable node and prove branch reachability through a repository-wide tracked-file inventory. A mapping is not a test execution witness. The inspected no-profile-injection test normalizes twice after compute, so that test alone is not a before/after noninterference proof.

**Required closure.** Bind each LF-R to its current suite, file, executable case and production interface; identify dead/renamed nodes, harness-only assertions and missing adapters. Do not turn search misses into absence. [G09] [T01] [G08]

### CROSS-AUDIT-13 — Exhaustive unknown-outcome/caller inventory remains a local closure gate

**Severity:** TEST GAP · **Owner:** M02 writer contract; M05/M09–M14 callers · **Target execution:** NOT_RUN

M09/M10/M13/M14 carry typed unknown outcomes or receipts in inspected paths. That does not prove every vocabulary, note, transform, annotation, profile and Hub write preserves one operation identity after an admitted timeout.

**Required closure.** Run tracked-file rg before edits; inventory every submit and caller timeout handler. Hold a writer op after admission, let the caller time out, commit, then retry the SAME logical operation. Assert exactly one domain effect and truthful UI reconciliation. [C01] [C02] [C04] [S09] [S14]

### CROSS-AUDIT-14 — Cross-pane deletion, expiry and stale-result revocation need current integrated proof

**Severity:** TEST GAP · **Owner:** M09; M12/M13/M14 pane owners · **Target execution:** NOT_RUN

Inspected generation and deletion mechanisms provide real protection, but this read-only audit did not execute the native publication interleavings across all later panes. A service-level deletion cannot alone prove an already visible widget is cleared.

**Required closure.** Bind the fifteen barrier races in the corpus to the actual UI query/action lifecycle, including pane switch, window close, note switch and in-flight profile/export. Record rejected publications and rendered identity. [S09] [S10] [S11] [C07]

### CROSS-AUDIT-15 — Full historical migration/openers/managed-path matrix remains unexecuted

**Severity:** TEST GAP · **Owner:** M02 plus every tool opening Store · **Target execution:** NOT_RUN

A concrete missing-link repair defect is identified, but the complete old-schema upgrade fixture matrix and every CLI/dev Store-opening path were not independently audited to closure. No safe-live-opener or universal no-follow pass is claimed.

**Required closure.** Inventory every Store constructor and effective default path; assert backup before migration/repair; run synthetic schema 1–13 fixtures and all populated relationship families. Exercise symlink ancestors, traversal, FIFOs, digest mismatches and corrupt DB locators using only disposable roots. [S04] [C01] [S07] [S08]

### CROSS-AUDIT-16 — Current end-to-end, contention and model-backed qualification is still open

**Severity:** TEST GAP · **Owner:** M15 qualification; M03/M07/M08/M11/M13/M14 producers · **Target execution:** NOT_RUN

No fresh target performance or real-model evaluation was run. Historical milestone medians cannot certify the current combined pipeline. M11 explicitly carries an unsuccessful integrated Prompt Engineer qualification result and missing current benchmark scope.

**Required closure.** After narrow correctness repairs, measure isolated current reference-Mac E2E and controlled pairwise contention. Preserve all failed/timed-out calls. Requalify touched M07/M11 seams with the current model without relabeling exposed fixtures blind. Do not begin M15 in this remediation. [H11] [H14] [G05] [G07]


## Design Concerns

### CROSS-AUDIT-17 — Adjudicate writer-contention tolerance without weakening authority

**Severity:** DESIGN CONCERN · **Owner:** M14 with M03/M15

The stronger M14 checks come with historical observed worst dictation-writer waits around 205 ms for profile compute and 174 ms for export. These are not UI stalls and are not, by themselves, a violation of a separately specified per-operation writer budget. They can consume a material fraction of the short-dictation budget.

**Adjudication direction.** Measure pairwise contribution and explicit worst-case cohorts. Prefer bounded snapshots/rechecks and short writer phases where semantics permit; retain final deletion/exposure qualification. Record an approved contention budget before claiming acceptability. [H14] [G05]

### CROSS-AUDIT-18 — Optional future Your Voice interpretation is a separate product decision

**Severity:** DESIGN CONCERN · **Owner:** M14 product design, after cross-milestone remediation

Current Your Voice is deterministic local ProfileService logic, not an external LLM or provider feature. API keys and network are not required by that architecture. A richer optional interpretation layer is neither needed to fix these findings nor authorized here.

**Adjudication direction.** Keep this as a future post-audit/Quiet-Editorial product note only. Any future layer must cite eligible evidence, respect deletion and thresholds, remain explicitly optional, and never inject the whole profile into runtime output. [C08] [S05]


## Areas Verified Strong

The following are source-supported architecture/implementation strengths, not newly executed qualification claims:

| Strength | Evidence boundary |
| --- | --- |
| One-job usage identity and explicit terminal taxonomy | M13 partial uniqueness/replacement and separate transform/repaste activities [C02] |
| Immutable context authority with explicit allowed revisions | Owned handles, target-owned reads, frozen projections and separately parented late delta [C03] |
| Canonical scope across runtime vocabulary/style | M10 explicitly reuses M05 comparator; exact workspace/profile policy retained [C04] |
| Conservative faithful cleanup and mode-specific transforms | Protected spans, applied-versus-proposal separation, source fallback, explicit gate revision [C03] [C05] [H07] |
| Strong external target and internal-note separation | Target-bound M08 actions and M12 durable receipt semantics; not an all-caller pass [C06] [H12] |
| Canonical note attribution into mining | M14 consumes M12’s stronger per-dictation provenance rather than only a note-wide diff [S06] |
| Usage/content retention separation and same-op redaction | Deleted usage does not erase retained speech; derived usage copies scrub in M13 writer [C02] |
| Shared artifact qualification and future exposure checks | Expected owner/role/liveness and all-version exposed-ever predicates in export path [S07] [S08] |
| Approval/undo services use M05 authority | Single operation and exact delta history; UI reachability remains09 [H14] |
| Transform Teach refusal and independent note authority | Guard preserved; note-after-Move is not deleted-job resurrection [C07] [S14] |


## Cross-Milestone Adversarial Corpus Summary

`LocalFlow_M01_M14_Cross_Milestone_Adversarial_Corpus.json` contains **176 declarations**: 116 category scenarios, 15 required multi-hop cases, 15 barrier races, 12 metamorphic relations and 18 proposed mutations. All 29 requested categories are represented. **Every target case is NOT_RUN and every adapter binding starts NOT_BOUND.**

Each declaration includes synthetic setup, production owners, pinned sources, actions, an independent semantic assertion and required observations. The binding policy prohibits passing a case with guessed APIs, setup failures or a toy helper that bypasses the relevant production services. The corpus is a specification for later local execution, not a claim that these cases already exist in the repository.

The findings’ minimal reproductions are additional explicit audit instructions, not extra executed cases counted in the totals.


## Stateful / Metamorphic / Mutation Plan

Stateful cases use named admission/read/commit/publication barriers, never timing sleeps. The race harness must record whether an interleaving is actually possible under the single writer. In particular, a deletion queued after an export’s final writer recheck cannot magically commit inside that callback; test both real orders and do not assert an impossible interleaving as a defect. [C01] [S08]

Metamorphic cases compare semantic projections—logical identities, text/authority, support, eligibility and outcomes—while excluding irrelevant UUID/time differences. Removing evidence or narrowing scope may reduce capability; it cannot manufacture training truth, blind status or current profile support.

A mutation is **KILLED only when the intended production branch was reached and an independent semantic assertion failed**. Import errors, crashes unrelated to the intended assertion, setup errors and unreachable branches are INVALID. No mutation is killed in this audit: all eighteen are proposed and NOT_RUN. Freeze passing-base witnesses before introducing them in a disposable local worktree.


## Recommended Repair Order

1. Reproduce **05** and protect the Store’s relational governance before relying on deletion/profile qualification. Reproduce **04** and close the missed internal clipboard caller.
2. Repair **01** current-attempt final selection, then **02** logical-capture profile deduplication and **03** frozen historical term provenance. Keep old attempt evidence; do not solve identity by deleting history.
3. Repair **06/07** as one bounded Export worker/action-generation change with two independent regressions; expose **09** through existing safe service authority or record an explicit approved product deferral.
4. Reproduce **08** at the actual rename/commit boundary and adjudicate a recoverable exactly-once publication policy. Do not weaken final requalification for speed.
5. Close caller/registry/migration/privacy/native gaps **12–15**, run affected and broad compatibility, perform isolated current performance and current touched-model compatibility, then obtain fresh-context independent review.
6. Reconcile **10/11**, the evidence ledger, runbook ownership and current campaign state after production/evidence converges. Leave Daniel’s human results and M15 qualification untouched.

The separate local handoff expands this into the required safe-start, fail-first, review, evidence, benchmark and same-session completed-remediation merge procedure. [G11]


## Cross-Milestone Readiness Verdict

**B. Proceed after targeted cross-milestone repairs.** There is enough concrete source evidence to justify a bounded remediation session; an inconclusive global verdict would hide actionable defects. There is not enough authority to call the composed product ready for the product-surface phase or M15 today.

This is a prioritized source-backed review with explicit unclosed inventories, not a certificate that every repository path was exhaustively inspected. Local reproduction must adjudicate every allegation as reproduced, refuted, narrowed, already fixed, test-gap only, design-only or unresolved native/model/manual. Fix confirmed owning seams and preserve accepted milestone behavior.

After correctness, compatibility, independent review and required performance evidence converge, the intended sequence remains: **cross-milestone completion → separate Quiet Editorial redesign → independent UI/product-quality review → M15 qualification → M16 final acceptance**. No part of that later sequence was started here.


## Pinned source catalog

| Key | Source | Use |
| --- | --- | --- |
| G01 | [README.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/README.md) | current product boundary; not a substitute for acceptance evidence |
| G02 | [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/START_HERE.md) | campaign entry point |
| G03 | [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json) | current status fields versus historical source_commit provenance |
| G04 | [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/ORCHESTRATION.html) | campaign ordering and M15 dependency eligibility |
| G05 | [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_SPEC.md) | S06–S08, S10–S19, S21–S25, S29–S31 requirements |
| G06 | [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) | evaluation/qualification ownership; not a fresh run |
| G07 | [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md) | M15 section begins after line 1490; AC01–AC08; M16 separately |
| G08 | [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/INDEX.md) | canonical domain-contract index |
| G09 | [docs/v2/registry.json](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/registry.json) | 33 requirements and 22 evaluation suites; mapping, not branch execution proof |
| G10 | [docs/v2/VERIFICATION.html](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/VERIFICATION.html) | check article IDs/revisions/code anchors; M07 placeholder; browser-local state |
| G11 | [CLAUDE.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/CLAUDE.md) | same-session merge of completed remediation; no attribution trailers; no incomplete merge |
| S01 | [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py) | _retry_job; copyLastRaw_; _guarded_copy; _process stages and coordinator callbacks |
| S02 | [localflow/v2/history_queries.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py) | final_text; _manifests; _job_artifacts; job_detail (especially 355–465) |
| S03 | [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py) | retry_snapshot; _publish (1157–1218); on_failure; note observations |
| S04 | [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py) | schema 13; _CORE_DEPENDENTS; _migrate (1190–1510); publish_example; delete_everywhere (2400–2635) |
| S05 | [localflow/v2/profile.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py) | _scrub_dead_evidence (105–137); _eligible (211–264); _compute_once; current (640 onward) |
| S06 | [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py) | teach_correction; mine_note_edits; M12 attribution helper consumption |
| S07 | [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py) | qualify; cleanup_qualification; transform_target shared predicates |
| S08 | [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py) | membership selection; exposed_ever; publication writer operation (660–790); validator |
| S09 | [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py) | rendered action identity; exportValidate_ (3600 region); _refresh_export_pane (3853 onward) |
| S10 | [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py) | query generation/epoch/identity; bounded query executor |
| S11 | [localflow/v2/ui/your_voice.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/your_voice.py) | source labels, invalidated-state rendering, evidence exclusion |
| S12 | [localflow/v2/vocabulary_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py) | writer-authoritative revisioned edits; canonical is an editable field |
| S13 | [localflow/inject.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/inject.py) | copy_text → direct pasteboard write; no M08 ownership admission here |
| S14 | [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py) | record_candidate (400–518); note liveness; dictation candidate versus independent note ownership |
| C01 | [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/store.md) | single writer, domain tables, deletion, repairs, schema additions |
| C02 | [docs/v2/contracts/analytics.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md) | one-job fact; retries; typed outcomes; usage redaction and readiness |
| C03 | [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/context.md) | collection-handle snapshots, late deltas, scope projection, AX ownership |
| C04 | [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profiles.md) | M05 comparator; one-shot mode; frozen tuple; snippets/files/skills |
| C05 | [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/transforms.md) | mode-specific gate; task identity; explicit versus automatic judgments |
| C06 | [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/insertion.md) | pending clipboard payload; confirmation; target-bound undo |
| C07 | [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md) | rendered actions; final-stage authority; transformed Teach refusal; async generations |
| C08 | [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md) | deterministic Your Voice; 10 dictations/2,000-word floor; evidence sources |
| H01 | [docs/v2/handoffs/M01.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M01.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H02 | [docs/v2/handoffs/M02.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M02.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H03 | [docs/v2/handoffs/M03.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M03.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H04 | [docs/v2/handoffs/M04.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M04.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H05 | [docs/v2/handoffs/M05.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M05.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H06 | [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M06.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H07 | [docs/v2/handoffs/M07.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M07.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H08 | [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M08.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H09 | [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H10 | [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M10.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H11 | [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H12 | [docs/v2/handoffs/M12.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H13 | [docs/v2/handoffs/M13.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M13.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| H14 | [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md) | current handoff, remediation/integration addenda, historical evidence and residuals |
| T01 | [tests/v2/personalization/test_profile.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/tests/v2/personalization/test_profile.py) | profile fixture creates a fresh job for every example; intact-evidence deletion and verbatim-repeat tests |

[G01]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/README.md "current product boundary; not a substitute for acceptance evidence"
[G02]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/START_HERE.md "campaign entry point"
[G03]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json "current status fields versus historical source_commit provenance"
[G04]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/ORCHESTRATION.html "campaign ordering and M15 dependency eligibility"
[G05]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_SPEC.md "S06–S08, S10–S19, S21–S25, S29–S31 requirements"
[G06]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md "evaluation/qualification ownership; not a fresh run"
[G07]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md "M15 section begins after line 1490; AC01–AC08; M16 separately"
[G08]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/INDEX.md "canonical domain-contract index"
[G09]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/registry.json "33 requirements and 22 evaluation suites; mapping, not branch execution proof"
[G10]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/VERIFICATION.html "check article IDs/revisions/code anchors; M07 placeholder; browser-local state"
[G11]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/CLAUDE.md "same-session merge of completed remediation; no attribution trailers; no incomplete merge"
[S01]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py "_retry_job; copyLastRaw_; _guarded_copy; _process stages and coordinator callbacks"
[S02]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py "final_text; _manifests; _job_artifacts; job_detail (especially 355–465)"
[S03]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py "retry_snapshot; _publish (1157–1218); on_failure; note observations"
[S04]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py "schema 13; _CORE_DEPENDENTS; _migrate (1190–1510); publish_example; delete_everywhere (2400–2635)"
[S05]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/profile.py "_scrub_dead_evidence (105–137); _eligible (211–264); _compute_once; current (640 onward)"
[S06]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py "teach_correction; mine_note_edits; M12 attribution helper consumption"
[S07]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py "qualify; cleanup_qualification; transform_target shared predicates"
[S08]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py "membership selection; exposed_ever; publication writer operation (660–790); validator"
[S09]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py "rendered action identity; exportValidate_ (3600 region); _refresh_export_pane (3853 onward)"
[S10]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py "query generation/epoch/identity; bounded query executor"
[S11]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/your_voice.py "source labels, invalidated-state rendering, evidence exclusion"
[S12]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/vocabulary_store.py "writer-authoritative revisioned edits; canonical is an editable field"
[S13]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/inject.py "copy_text → direct pasteboard write; no M08 ownership admission here"
[S14]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py "record_candidate (400–518); note liveness; dictation candidate versus independent note ownership"
[C01]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/store.md "single writer, domain tables, deletion, repairs, schema additions"
[C02]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md "one-job fact; retries; typed outcomes; usage redaction and readiness"
[C03]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/context.md "collection-handle snapshots, late deltas, scope projection, AX ownership"
[C04]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profiles.md "M05 comparator; one-shot mode; frozen tuple; snippets/files/skills"
[C05]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/transforms.md "mode-specific gate; task identity; explicit versus automatic judgments"
[C06]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/insertion.md "pending clipboard payload; confirmation; target-bound undo"
[C07]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md "rendered actions; final-stage authority; transformed Teach refusal; async generations"
[C08]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md "deterministic Your Voice; 10 dictations/2,000-word floor; evidence sources"
[H01]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M01.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H02]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M02.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H03]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M03.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H04]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M04.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H05]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M05.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H06]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M06.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H07]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M07.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H08]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M08.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H09]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M09.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H10]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M10.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H11]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M11.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H12]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M12.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H13]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M13.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[H14]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md "current handoff, remediation/integration addenda, historical evidence and residuals"
[T01]: https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/tests/v2/personalization/test_profile.py "profile fixture creates a fresh job for every example; intact-evidence deletion and verbatim-repeat tests"