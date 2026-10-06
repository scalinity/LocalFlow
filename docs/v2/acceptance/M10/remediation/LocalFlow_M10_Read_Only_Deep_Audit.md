# LocalFlow V2 — M10 Read-Only Deep Audit

**Repository:** `scalinity/LocalFlow`  
**Audited commit:** `9344fa14e2d013b5c9befef88663fcd03d3c6ef1`  
**Audit date:** 26 September 2026  
**Milestone:** M10 — Styles, Snippets, and Developer Workflows  
**Method:** committed-source and contract inspection through the connected GitHub repository. No LocalFlow code, tests, model inference, benchmarks, native UI interactions or Daniel's manual checks were executed.

> This audit covers committed GitHub state at `9344fa14e2d013b5c9befef88663fcd03d3c6ef1`. Any uncommitted local state is outside the GPT-6 audit boundary.

**Deliverable companions:** `LocalFlow_M10_Adversarial_Corpus.json` and `Claude_Code_LOCAL_Opus_5_5_M10_Remediation_Handoff.md`.

## Executive Assessment

**Verdict C — Significant profile/developer-workflow weaknesses.** M10 has a real implementation, genuine positive tests and several sound inherited protections. Its main weaknesses are not missing features or the two historical Critical findings. They are authority and state-composition failures at the boundaries between configuration, capture, finalization, filesystem discovery, previews and the writer queue.

The register contains **1 Critical, 14 High and 9 Medium source-supported defect findings**, plus **4 Test Gaps and 4 Design Concerns**. These are static findings awaiting local reproduction, not 24 executed failures. Severity reflects the specific supplied rubric and demonstrated source path, not a claim about observed user harm or attack frequency.

The highest-priority issue is configured-root skill discovery following a child symlink to an unconfigured target. The other principal repair clusters are strict Boolean/path admission, correlated-field writer validation, manifest cache/freeze and M06 rollback composition, snippet/file-tag delimiter ownership, duplicate-basename resolution, and admitted-write timeout reconciliation. Benchmark qualification must be repaired before any old or new latency figure is accepted.

There is **no demonstrated unintended shell execution, no demonstrated arbitrary file-content read from the file-tag resolver, and no demonstrated automatic promotion of generated snippet text to a reviewed acoustic reference**. Those distinctions keep this audit from inflating the findings. Sources: [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) — fixture construction, timed callbacks, output manifest.

## Audit Boundary

The review follows M10 production paths and the narrow M04/M05/M06/M08/M09/M11/M14 interfaces they consume. It does not reopen accepted milestones wholesale, implement fixes, change configuration, certify external editor surfaces, redesign the Hub, or start M12–M15. Repository access was read-only. Generated audit files live only in this conversation's working area; they are not repository edits.

The supplied prompt was treated as a set of hypotheses to test against current source, not an assertion that every suspected failure exists. Current contracts outrank historical implementation notes where they differ. Historical tests/benchmarks are evidence of what those earlier runs reported, not proof that this commit currently passes them.

The complete recursive tree was retrieved and core files/identified consumers read. Remote code search did not provide an exhaustive caller inventory. A local `rg` inventory and current test execution are therefore explicit follow-through requirements, not something this report claims to have done. Native geometry is reported as a source lead requiring actual AppKit hit-testing, not an observed failure.

No real snippets, personal filenames, workspace contents, audio, manifest paths or machine settings were collected. All proposed reproductions use synthetic inputs. [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics; [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) — final a304d48; rendered rows, timeouts and MainQueue.

## Canonical Foundation

Remote `main` resolved to the supplied baseline `9344fa14e2d013b5c9befef88663fcd03d3c6ef1`. No intervening main delta needed substitution into this audit. Recent ancestry and current remediation addenda were reconciled before treating M10 as post-M09 code.

| Milestone | Inherited checkpoint | Interpretation |
|---|---|---|
| M01 | `3db74061f23001b9cce3d4fe029e0b30cbc295d6` | Direct remote comparison: ancestor; main ahead 89, behind 0. |
| M02 | `bfbc63c35efa6273cc13242d54d3e5bbe264b21e` | Actual commit/parent records in reachable recent ancestry; retain current store/deletion contracts. |
| M03 | `3e0d1ab972b866b4acbda622984bce04e8f95093` | Direct comparison has this commit as merge base; review-round repair is inherited. |
| M04 | `4ef219c52598e92a9857e9e0dec13ca7143f56dc` | Actual commit/parent records in reachable recent ancestry; current normalization contract inspected. |
| M05 | `01a1f3c07ed3270aa1e7b3da39d89c453c84c1e8` | Direct comparison: ancestor; main ahead 70, behind 0. Final test checkpoint 4adda7d is documented in current handoff. |
| M06 | `4388b521cedfebe5a16dc8c485d25275f0b342f0` | Direct comparison: ancestor; main ahead 63, behind 0. Includes R3 captured-tuple rollback. |
| M07 | `52edc4753df9be17d9119e95d760c4086c5649cd` | Direct comparison: ancestor; main ahead 101, behind 0. The later 39762cc commit is orchestration, not production. |
| M08 | `9483d1be777ac2fa07111d8e0020e6b1652c5e69` | Inherited tested-tree/runbook checkpoint, NOT the production-change SHA. Current evidence identifies production ea83bc1; evidence commit 4ea2389 follows. Direct comparison: ahead 34, behind 0. |
| M09 | `a304d48c3adf0ef7639fe66986d8affe41a2264a` | Final production inherited by 18ff4f5 and the audited 9344fa1 evidence head. |
| M11 | `9a049b341d315201ba7d8019585fd7e71370af31` | Direct comparison: ancestor; main ahead 54, behind 0. Local replay 1545de9 and M06 R4 repair 46ecd5b are the reconciled line; f8bf7e5 is integration evidence. |

Evidence: [M01 ancestry](https://github.com/scalinity/LocalFlow/compare/3db7406...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M03 ancestry](https://github.com/scalinity/LocalFlow/compare/3e0d1ab...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M05 ancestry](https://github.com/scalinity/LocalFlow/compare/01a1f3c...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M06 ancestry](https://github.com/scalinity/LocalFlow/compare/4388b52...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M07 ancestry](https://github.com/scalinity/LocalFlow/compare/52edc47...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M08 tested tree ancestry](https://github.com/scalinity/LocalFlow/compare/9483d1b...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [M11 ancestry](https://github.com/scalinity/LocalFlow/compare/9a049b3...9344fa14e2d013b5c9befef88663fcd03d3c6ef1); [pinned recent ancestry](https://api.github.com/repos/scalinity/LocalFlow/commits?sha=9344fa14e2d013b5c9befef88663fcd03d3c6ef1&per_page=100); [docs/v2/handoffs/M04.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M04.md) — normalization remediation addendum; [docs/v2/handoffs/M05.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M05.md) — scope, concurrency and evidence remediation addendum; [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M06.md) — local remediation; R3 rollback; authority decisions; [docs/v2/handoffs/M07.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M07.md) — cleanup remediation and generated-span preservation; [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M08.md) — local effect-boundary and terminal remediation; [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) — final a304d48; rendered rows, timeouts and MainQueue; [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M11.md) — local replay 1545de9, final production 9a049b3; model-quality residuals.

**Important SHA distinction:** M08's `9483d1b` is the committed test/runbook tree. Its evidence says production `ea83bc1`. M11's original Cloud-era `aa03af7`/`1be42ee` are not asserted to be ancestors; the current handoff documents replay/reconciliation into the local line. Content preservation and original commit ancestry are not interchangeable.

Current `hub.md`, `store.md`, `context.md`, `insertion.md` and `training_evidence.md` reflect post-remediation semantics: writer wait timeouts can have unknown outcomes; rendered rows bind actions to stable IDs; deletion invalidates dependent state; missing transformed output cannot silently substitute Clean; M06 scope authority is explicit. Historical `STATUS.json` implementation readiness is not a fresh M10 audit sign-off. [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics; [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/store.md) — single-writer atomic operations and timeout semantics; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/insertion.md) — current M08 terminal and effect-boundary contract; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/STATUS.json) — historical implementation status, distinct from audit campaign; [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/ORCHESTRATION.html) — campaign and historical evidence overview.

## Current M10 Architecture

```text
validated configuration / stores
    ├─ style rules + pending one-shot mode
    ├─ snippet definitions
    ├─ configured global/workspace manifest records
    └─ enabled transform definitions
                    ↓
PTT admission → _m10_freeze → job-owned configuration
                    ↓
M06 final destination / vocabulary projection
                    ↓
_m10_finalize_upgrade → _finalized_policy → file-name resolver
                    ↓
raw: ASR only            clean: one normalization proposal pass
                                      ↓
                     snippets / explicit skills / file-tag text
                                      ↓
                 cleanup with protected generated/literal spans
                                      ↓
             optional frozen, enabled, opted-in M11 transform
                                      ↓
                   current M08 insertion/effect boundary
                                      ↓
        content-free status + governed stage/registry artifacts
```

`StyleRuleStore` and `SnippetStore` share the single database writer but perform important validation before their queued operations. `WritingProfile` carries mode, number policy, profile identity and source explanation. Snippet and skill registries precompute lookup structures. `HubState` loads service data and the modern shell renders stable row snapshots; preview calls route back through the app coordinator. Training Evidence records the selected profile and governed normalization/registry artifacts.

The architecture is sensible at the component level. The risky edges are replacement of captured state during finalization, pre-writer validation, inconsistent scope comparisons, cached preview context, and assuming a helper's semantics automatically reach production. [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/state.py) — Styles/Snippets service loading and selection state; [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering.

## Historical M10 Findings Revisited

| Historical allegation | Current disposition | Remaining qualification |
|---|---|---|
| Hub never passed styles_service/snippets_service into HubState | **Repair present.** Production constructor passes both; the shared Hub test constructor also uses real services. | This does not prove actual native text entry, pane hit-testing or stale-editor concurrency. |
| M06 final scope upgrade rebuilt policy from dictionary skills only | **Normal successful-path repair present.** `_finalized_policy` is the common builder and merges frozen manifest skills with scoped dictionary skills. | Re-reading manifests and the following M10 finalizer's failed/deferred composition are different defects: AUDIT-11/12. |

Neither historical Critical finding is simply reopened under a new ID. The local regression must still use a real nonempty manifest plus a distinct dictionary skill through the actual coordinator; an empty registry cannot certify the second repair. [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) — make_hub service wiring, MainQueue, shell and M10 CRUD checks; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests; [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M10.md) — historical implementation, review repairs, limitations; not fresh proof.

## Writing Profile / Precedence Assessment

The source implements explicit workspace > site > app rule priority, then category handling, then global behavior, with a per-job override above those choices. Equal-authority candidates are ordered by rule ID. Disabled rules do not acquire authority through the healthy resolver. The existing tests use genuine conflicting rule populations.

There are two important qualifications. First, a known category with no stored category rule receives its built-in Clean default before a global rule; that convention is documented and is not a newly discovered precedence bug. Second, a mode override is not transparently the rest of a destination rule with only its mode replaced. Its number/profile fallback is a separate documented resolution branch. Preserve these controls while fixing canonical equality and atomic tuple publication. Duplicate enabled defaults need a policy/UX decision, not an invented newest-wins implementation. See AUDIT-02, 29 and 32. [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) — precedence/defaults and transform binding controls.

## Profile Scope / M05 Compatibility

M10 matching uses direct strings where M05 has explicit canonical comparison rules. This can make a style and its vocabulary disagree about an otherwise equivalent destination. Bundle case, site host case/trailing slash and scope whitespace require shared tests; workspace/profile identity must not acquire fuzzy case folding or filesystem interpretation merely to make those tests pass.

Profile names are behavior-bearing vocabulary scope, not just UI labels. Empty/whitespace/duplicate/renamed/deleted names require strict identity admission and the frozen name must remain attached to the job. Unicode support is not permission to invent Unicode equivalence policy.

**Refuted hypothesis:** M10 does not simply use the weak title-derived origin to regain site scope. The app's M10 adapter uses M06's `scope_site_origin` for rule/category authority. Exact-string category false negatives remain, but no heuristic-origin privilege regain was found on that path. Unknown browsers/messengers/IDEs should remain generic rather than be guessed from a familiar-looking title. [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) — canonical scope comparisons and writer-authoritative mutation discipline; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator.

## Per-Job Override Assessment

Normal capture admission is serialized on the app/UI path and rejects another active recording. The ordinary linearization point is `_m10_freeze` taking the pending mode for the admitted capture. A cancelled or too-short admitted capture can consume it; a recorder-start failure before this point does not. Explicit History Retry does not represent a new PTT capture and should not consume this slot.

The concrete failure is later fallible work after the pending mode is cleared: the snapshot can fail to publish and the outer path can continue without the requested mode. Raw is the strongest safety witness because accidentally running normal cleanup is observable. AUDIT-13 requires job-owned mode capture before optional discovery, not a naive restore-to-global-slot that could steal a newer user choice. True parallel API calls remain a deterministic ownership probe, not an assumed normal UI race. [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests.

## Style Store Concurrency Assessment

The single-writer queue is valuable, but does not make caller-side read/merge/validation atomic. The concrete style reproduction changes an app rule to category/coding while another caller patches its value to a bundle string valid only for the old app scope. The combined committed category tuple is invalid. Snippets have the analogous kind/content race.

**Narrowed/refuted parts of the prompt's hypothesis:** these methods apply a patch, not a stale full row, so independent mode/name changes do not automatically overwrite each other. Revision is incremented in SQL, so two successful writes do not both persist revision 5. Real issues are writer-current validation, missing row outcomes, and full stale form submissions from the UI. Boolean coercion is a separate admission problem, especially where it grants rewrite/auto-apply authority. See AUDIT-03–07, 20–21. [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) — schema v6, Store.submit/_submit and writer transactions; [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh.

## Snippet Engine Assessment

Captured definition rows normally survive later store edits because matching uses the job's captured snapshot. Enabled duplicate triggers are masked rather than chosen by input order. Existing literal/quote protections and equal-span arbitration are meaningful strengths. URL snippets reject multi-token content and placeholders; rich payloads are stored alongside their plain representation.

The grammar has an integration hole: snippets are exempted from the normalizer's general barrier predicate but do not enforce the missing predicate themselves. Word-token matching can span line/sentence boundaries and use punctuation-inclusive token bounds. The 24-word slot cap does not repair ownership of a newline or trailing sentence. Snapshot containers also need a deep immutability check beyond frozen dataclass fields and tuple wrappers. See AUDIT-14 and 17. [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage.

## Placeholder / Generated-Text Assessment

Current syntax is `{{name}}` or `{{ name }}` with conservative named slots. Values come from spoken continuation, not private context. `split_slots` strips leading spoken `comma` tokens as trigger/value delimiters, splits only until the declared slot count is reached, and keeps later `comma` words in the last slot. Missing values become empty. The corpus preserves these source-derived details instead of treating a leading comma as an empty first slot.

Byte-exact template substitution is implemented by `expand`; exact pipeline preservation additionally depends on protected output-span mapping. The captured `allow_rewrite` flag, not today's store row, governs later cleanup. Missing-definition and cleanup-failure cases must fail safe. The real defect is crossing structural boundaries and the historical-provenance omission: expanded output plus a snapshot hash is not an exact retained template/slot/rewrite record after the current definition is deleted.

A second independent normalization of a generated trigger can chain another snippet. The normal production coordinator performs one pass, so this is an idempotence/API policy concern, not proof of recursive expansion in normal dictation. See AUDIT-14, 23, 31–32. [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering; [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/artifacts.md) — retained exact stage inputs, revision lineage and deletion.

## Collision / Arbitration Assessment

The actual engine distinguishes a bare snippet alias from explicit `slash` skill syntax, resolves cross-layer precedence by spans, and can abstain on same-layer same-span ambiguity. These are stronger than a simple first-match replacement loop.

The collision preview is not equivalent. The owning suite itself contains a runtime bare-alias snippet positive and a preview assertion declaring the same bare alias ambiguous. Broader vocabulary eligibility and the synthetic preview candidate ID create further scope/self-conflict risks. A differential preview/runtime test with an independently specified expected decision is needed; sharing the same wrong label between two test helpers would not be sufficient. See AUDIT-18–19. [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage.

## Skill Manifest Assessment

No shell/eval/subprocess execution or speculative home-directory fallback was found in the inspected discovery path. Valid leading frontmatter identity fields become records; the body is not ordinarily appended to prompts. `SkillRegistry.to_json` omits raw manifest paths. These protections should survive remediation.

The remaining boundaries are substantial: child symlink escape, non-leading/incomplete frontmatter acceptance, wrong-shaped valid JSON exceptions, permissive path-list admission and unbounded whole-file hashing/JSON reads. Reading a full body for a permitted integrity hash is not itself the same as interpreting that body as instructions, but it is a resource/provenance issue when done unbounded or from a different read than parsing. See AUDIT-01, 07–09 and 22. [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/config.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/config.py) — M10 configuration defaults/merge; contrast with context_policy; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests.

## Workspace / Registry Freeze Assessment

Workspace display/project identity is kept separate from the document locator in the app's source derivation; it is not simply concatenated onto home to invent a directory. Stable workspace-switch discovery has explicit handling and should not be replaced with a global scan.

There are two distinct cache/freeze bugs. For a configured directory, ordinary in-place child manifest edits can be invisible to the top-level mtime cache, so B gets stale data. For a top-level manifest whose key does change, the finalizer can reread it after A's capture and give A new data. Fixing one by scanning more often can worsen the other unless one explicit immutable snapshot/refresh model is designed.

M06's guarded rollback is present. M10's following registry/policy finalization must honor its disposition and commit the complete tuple atomically; retaining the successful-path common policy builder does not settle failed/deferred widening. See AUDIT-10–12. [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M06.md) — local remediation; R3 rollback; authority decisions.

## File Tag / Filesystem Boundary Assessment

The file resolver operates on names, not file contents. Stable child directory symlinks are not traversed by the listing's `is_dir(follow_symlinks=False)`. The configured result bound is depth 2 and 500 returned names, hidden names omitted. The review did not find arbitrary `open/read_text/read_bytes` in the file-tag resolution path.

Those strengths do not make the full path qualified. `sorted(os.scandir(...))` materializes a directory before the output cap; root/rename races require independent traversal logs. The parser can infer commands across delimiters. The resolver's open-document early return can bypass a real duplicate basename, even though its normal candidate union otherwise handles duplicates correctly. Spoken path separators can disambiguate; spoken numeric words are not a general digit-normalization feature of this resolver.

File-chip certification remains empty. The standalone attachment helper has honest fallback fields, but the live coordinator path does not consume that helper. The runtime must expose its own `attachment_created=false` limitation instead of assuming a helper test proves the user sees it. See AUDIT-15–16, 22 and 24. [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/developer/surfaces.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/surfaces.py) — live compatibility table and certification sets; [tests/v2/developer/test_developer_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_developer_resolution.py) — file ambiguity, listing and helper-level attachment/surface tests.

## Surface Safety Assessment

The current M08 insertion service treats terminal LF, CR, CRLF, NEL, Unicode line/paragraph separators and unsafe control characters as hazards. With the live certified bracketed-paste set empty, it routes these payloads to a copy-only offer. If the category was initially unknown, it classifies the application bound by validation before effect and checks the hazard again. M10's surface table derives from the live enforcement sets rather than a duplicated optimistic matrix.

No M10 path was found synthesizing Return or invoking a shell. A snippet containing `&&` or `|` is not itself an execution call; safe single-line terminal policy should not be replaced with a blanket operator ban. The needed proof is a populated snippet/file-tag payload traversing the actual current insertion service, including separator mutations and a successful normal-editor positive control. Real external terminal/editor certification and Daniel's manual checks remain pending. [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/insertion/service.py) — CERTIFIED_BRACKETED_SURFACES, _TERMINAL_UNSAFE, _transaction, _terminal_hazard; [localflow/v2/developer/surfaces.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/surfaces.py) — live compatibility table and certification sets; [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/insertion.md) — current M08 terminal and effect-boundary contract; [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M08.md) — local effect-boundary and terminal remediation.

## M11 Auto-Apply Compatibility

For well-typed definitions, the current M11 seam is substantially sound: disabled definitions are excluded, requested mode must bind to the appropriate frozen definition, auto-apply is opt-in, target profile/category restrictions apply, ambiguous Custom resolution abstains, and failure/needs-review keeps Clean with an explicit reason. Real coordinator tests assert actual transform calls, exact delivered transform output and retained Clean—not just a mode label.

The concrete seam defect is malformed Boolean admission: `TransformStore.update_transform(..., auto_apply="false")` coerces the string to true. Fix the shared authorization boundary and retain positive True/False controls. Do not recast model-quality failures, output limits or the known wrong review clause as M10 bugs. Definition freezing and its enabled/disabled between-job behavior belong in the stateful suite. See AUDIT-06. [localflow/v2/transforms/definitions.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms/definitions.py) — TransformDefinition, TransformSnapshot.auto_apply_decision/for_mode; [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms_store.py) — update_transform Boolean admission; no general M11 store re-audit; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/transforms/test_transform_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/transforms/test_transform_pipeline.py) — positive auto-apply, opt-out, review fallback and retained Clean controls; [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/transforms.md) — enabled frozen definitions, opt-in and honest fallback; [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M11.md) — local replay 1545de9, final production 9a049b3; model-quality residuals.

## Hub Styles / Snippets Functional Assessment

Production and shared-test service wiring are present. Rendered row snapshots and stable IDs prevent the old row-index retargeting class. The post-M09 MainQueue test pattern is real; do not regress to running supposed main-thread callbacks inline from worker threads.

The outstanding configuration problems are stale full-form updates without revision checks, incomplete deleted-editor invalidation and generic timeout-as-failure messages. Synchronous M10 CRUD on the main thread was explicitly left as a limitation by M09; the mere fact that it is synchronous is not a new High finding. Its outcome semantics and responsiveness must nevertheless be measured honestly.

The pane constructors' root view geometry is a concrete native hit-testing lead. A field assigned programmatically in a test does not establish that Daniel can click and type into it. Actual AppKit responder/input/action qualification is mandatory locally and is not future visual redesign work. See AUDIT-20–21 and 26. [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/state.py) — Styles/Snippets service loading and selection state; [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) — make_hub service wiring, MainQueue, shell and M10 CRUD checks; [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) — final a304d48; rendered rows, timeouts and MainQueue; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics.

## Evidence / Privacy Assessment

The producer distinguishes raw ASR, normalization output and typed generated edits; skill registry content is retained in governed artifacts with envelope counts/revisions. Registry serialization omits raw manifest paths. Preview does not intentionally create training examples or usage hits. No deterministic false-acoustic-export path was established.

The important omission is exact applied snippet definition/slot/rewrite provenance after the current configuration changes. Governed artifact write failures also need an explicit completeness witness, not a false retained/replayable claim. The corpus includes that fault seam.

Arbitrary user-defined `profile_name` is explicitly allowed in the current envelope profile block. It can be private, so calling the envelope content-free is a contract inconsistency requiring adjudication. It is not correct to pretend the field is undocumented, nor to silently remove it without handling vocabulary identity. Check derived fallback reason strings as well as the primary block. Any exact names, filenames and snippets belong only in the appropriate permitted configuration/content artifacts, never generic operational error logs. See AUDIT-23, 28 and 30. [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/artifacts.md) — retained exact stage inputs, revision lineage and deletion; [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_SPEC.md) — S10, S12, S15, S17, S19, S29.4/S29.11, S30.1.

## Retry / Recovery Assessment

**Explicit History/Recovery Retry is not exact original-configuration replay.** The current contract deliberately builds fresh, unscoped defaults with the current permitted global vocabulary/global manifests and records `retry_unscoped_default`. It does not attach today's destination styles, workspace registry or snippets as if they were original inputs. An old job can therefore legitimately differ under a newly configured global default, provided that provenance remains explicit.

Internal worker/stage retry within one logical job is different: it must keep that job's captured M10 state, attempt lineage and usage identity. Neither retry path should consume a pending mode intended for a newly admitted capture. Do not “fix” explicit Retry by copying the live destination into historical audio, and do not claim unavailable original snippet templates have been recovered. [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment.

## Test-Oracle Assessment

| Owning test surface | Genuine strength | What it does not establish |
|---|---|---|
| Style resolution | Real conflicting rules and default/opt-in branches | Canonical equivalent representations; writer-current correlated validation |
| Snippets | Real positive expansion, literal protection, same-span arbitration | Delimiter ownership, deep snapshot immutability, preview parity |
| Skills | Actual configured synthetic manifest reads | Coordinator cache refresh, child symlink authority, header anchoring, wrong JSON shapes |
| Files | Real distinct candidates and ambiguity controls | Open-document plus duplicate-basename interaction; command parser barriers |
| M10 pipeline | Real coordinator with scripted workers, not a fake policy evaluator | Every stateful finalization/cache/timeout barrier |
| Hub | Actual services and post-M09 MainQueue | Owned-pane native text input and stale editor revision binding |
| M11 seam | Positive transform generation and exact final output; opt-out zero calls | Malformed primitive admission and all between-job state changes |
| Benchmark | Populations and timing loop exist | Any valid work at all without independent output assertions |

Coverage statements are limited to the inspected owning tests; no current suite was executed or declared green. The local session must record complete callers and commands, retain positive populations, fail on unreached barriers/harness errors, and kill mutants with semantic assertions. See AUDIT-25–28. [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) — precedence/defaults and transform binding controls; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests; [tests/v2/developer/test_developer_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_developer_resolution.py) — file ambiguity, listing and helper-level attachment/surface tests; [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests; [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) — make_hub service wiring, MainQueue, shell and M10 CRUD checks; [tests/v2/transforms/test_transform_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/transforms/test_transform_pipeline.py) — positive auto-apply, opt-out, review fallback and retained Clean controls; [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) — fixture construction, timed callbacks, output manifest.

## Native / Manual Verification Assessment

This audit performed **zero** native UI tests and **zero** manual checks. The local handoff separates three kinds of evidence: portable/desktop-isolated automation, owned-window AppKit automation, and Daniel's genuinely human-only real-destination trial.

Native automation must prove actual hit-testing and first-responder acquisition, text entry, Cmd+A/edit/tab navigation, popups, toggles, Add/Update/Delete and stable-ID effects for both M10 panes. It must not send uncontrolled events to Daniel's current foreground application or touch his live clipboard to run a portable test. The existing M08 safe-native infrastructure should be reused where appropriate.

Preserve the pending `native-m10-developer-trial` and earlier backlog. Its remaining real-world checks include destination-class mode behavior, an explicitly authorized real manifest, actual editor filename fallback and terminal multiline behavior. Do not mark those passed because a fixture window or direct setter worked. Update only M10 runbook instructions and retain all other milestone IDs/status storage. [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M10.md) — historical implementation, review repairs, limitations; not fresh proof; [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) — final a304d48; rendered rows, timeouts and MainQueue; [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M08.md) — local effect-boundary and terminal remediation; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05.

## Performance / Benchmark Assessment

**No current M10 latency qualification is available from this audit.** The September 22 figures are historical and the current script lacks work validity. Its intended populated snippets can refuse expansion because a placeholder consumes an oversized continuation; its file probe's digit words are not equivalent to the actual filename under the resolver. Skill command eligibility must also be checked, not inferred from a populated registry.

Require separate cold/warm measurements for style resolution, snippet snapshot construction, normalization/matching, manifest parsing/registry construction, file listing, file resolution and combined M10 overhead. Use actual valid hits plus genuine ambiguity/distractor controls. Report p50/p95/p99, population sizes, byte/entry work, cache state, SHA, Mac model, macOS, Python, power/load and exact command. Run timing alone—not concurrently with full-tree tests or native sweeps.

The owning target remains ≤25 ms P95 policy/snippet contribution for a 500-word reference workload, with adapter overhead separately reported. This does not justify hiding manifest/listing costs outside the combined contribution or cutting work until the target passes. No-op components must invalidate the benchmark before their faster timings can be accepted. See AUDIT-22 and 25. [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) — fixture construction, timed callbacks, output manifest; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05; [docs/v2/acceptance/M10/results.json](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/acceptance/M10/results.json) — historical September 22 execution record; not current measurements.

## Critical Findings

1 registered. Each record below is source analysis or a defined proof/policy gap; target execution remains `NOT_RUN`.

### M10-AUDIT-01 — Configured skill-directory children can escape the authorized root through symlinks

**Severity:** CRITICAL

**Confidence:** High (source-supported; not executed)

**Category:** Filesystem authority

**Canonical requirement:** S12/S17; M10 configured-path-only discovery. Critical classification is specifically for an out-of-root file read, not command execution.

**Code location / source:** [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_SPEC.md) — S10, S12, S15, S17, S19, S29.4/S29.11, S30.1

**Current behavior:** Skill-directory discovery tests child directories and SKILL.md with path operations that follow symlinks, then opens the resulting path. No descendant containment or no-follow read boundary is established.

**Failure mechanism:** Permission to scan one configured directory is treated as permission to follow a child link into a different, unconfigured directory. A root explicitly configured as a symlink is a separate policy question; this finding uses a normal configured root with a malicious/unintended child.

**Minimal reproduction:** Create synthetic allowed/ and outside/ directories. Put a valid SKILL.md with name outside-canary in outside/. Put allowed/linked -> outside/. Configure only allowed/. Trace real discovery file opens. Repeat with allowed/unit/SKILL.md -> outside/SKILL.md. Never use a real private directory.

**Expected behavior:** No bytes from outside/ are opened under authority granted only to allowed/. Report a content-free refusal, or require separate explicit authorization for that target.

**Likely actual behavior / verification boundary:** Outside frontmatter is read and can enter the registry. No local reproduction has been run; no shell execution or network disclosure is alleged.

**Existing coverage:** test_skills.py reads real temporary configured manifests, but does not establish an out-of-root canary read log.

**Why the oracle misses it:** A positive configured manifest and a body-nonexecution test do not exercise descendant path authority.

**Regression recommendation:** Record open/read attempts independently; positive in-root manifest must load, both child-link variants must remain unread. Include a rename/link-swap barrier and state residual TOCTOU honestly.

**Narrow repair direction:** Define the configured-root policy and enforce it at the file-open boundary; reject or explicitly authorize symlink targets. Do not merely check a string prefix, and do not scan home as fallback.

**Downstream impact:** M06 locator authority, M10 registry ownership/privacy, M15 qualification.

**Corpus references:** M10-C118, M10-C119, M10-C120, M10-C135, M10-C214

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

## High Findings

14 registered. Each record below is source analysis or a defined proof/policy gap; target execution remains `NOT_RUN`.

### M10-AUDIT-02 — Style scope comparison diverges from the accepted M05 canonicalization rules

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Profile authority

**Canonical requirement:** S15 destination rules and M05/M06 scope compatibility; profile-scoped vocabulary and writing policy must agree on the destination.

**Code location / source:** [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) — canonical scope comparisons and writer-authoritative mutation discipline; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) — precedence/defaults and transform binding controls

**Current behavior:** _rule_matches compares raw scope strings directly; derive_category also checks exact bundle/origin strings. M05 trims scopes, normalizes bundle comparison and canonicalizes site comparisons.

**Failure mechanism:** Two representations of one destination can activate vocabulary but not its corresponding style rule. Host casing, padding and trailing slash variants are not consistently admitted or compared.

**Minimal reproduction:** Store an app rule for com.example.editor and resolve a destination COM.EXAMPLE.EDITOR. Repeat for a known AI origin with host case/trailing slash differences, and workspace/profile padding according to the existing M05 policy. Include unrelated-origin negative controls.

**Expected behavior:** Equivalent authorized scope representations resolve the same rule and number policy. Non-equivalent origins, ports or workspace identities remain distinct according to the existing contract.

**Likely actual behavior / verification boundary:** Exact strings match; equivalent-but-different representations can fall through to a category/global default. This is principally a false-negative authority mismatch, not evidence of fuzzy site matching.

**Existing coverage:** Style tests have real precedence contenders but mostly exact same-string scopes.

**Why the oracle misses it:** Passing precedence on canonical literals does not test compatibility with the vocabulary/context comparators.

**Regression recommendation:** Reuse a table of equivalent and non-equivalent scope pairs across both M05 and M10; assert complete resolved tuples, not merely an effective mode.

**Narrow repair direction:** Share the already-adjudicated comparison/admission helpers. Do not invent www/port aliasing or case-fold workspace names beyond that policy.

**Downstream impact:** M05 vocabulary, M06 scope, M11 target-profile selection.

**Corpus references:** M10-C001, M10-C002, M10-C003, M10-C004, M10-C005, M10-C006, M10-C009, M10-C014, M10-C015, M10-C016, M10-C017, M10-C018, M10-C019, M10-C020, M10-C021, M10-C022, M10-C023, M10-C024, M10-C025, M10-C038, M10-C039, M10-C040, M10-C201, M10-C209

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-03 — Concurrent style patches can commit a rule that fails its own domain validation

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Store concurrency

**Canonical requirement:** One valid, versioned style rule per committed row; validation must describe the row actually written.

**Code location / source:** [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) — schema v6, Store.submit/_submit and writer transactions; [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) — canonical scope comparisons and writer-authoritative mutation discipline

**Current behavior:** update_rule reads and validates a merged object before submitting the patch. The writer applies only changed columns and increments revision in SQL without revalidating the resulting current row.

**Failure mechanism:** Individually valid patches against the same old row can combine into an invalid correlated scope tuple. This is NOT the hypothesized full-row overwrite for disjoint patches, and SQL revision increments do not both become revision 5.

**Minimal reproduction:** Initial row: scope_kind=app, scope_value=com.example.alpha. Hold two callers after their read. A changes scope_kind=category and scope_value=coding. B changes only scope_value=com.example.beta, valid against its stale app row. Commit A, then B.

**Expected behavior:** B is rejected as stale, or merged and validated against the writer-current row before commit. All subsequent rule reads remain valid.

**Likely actual behavior / verification boundary:** The database can contain category/com.example.beta, which StyleRule rejects when rows are reconstructed. A post-write read failure is too late to undo the committed invalid state.

**Existing coverage:** Sequential store tests cover updates and revisions; no correlated-field two-caller barrier is present in the inspected owning suite.

**Why the oracle misses it:** A single writer serializes SQL statements, not caller-side read/validate/write transactions.

**Regression recommendation:** Use explicit read and commit barriers. Inspect raw row, revision, meta revision and public reads after both orders; include disjoint compatible patches as a preservation control.

**Narrow repair direction:** Move read/merge/domain validation and affected-row checks into one writer op; use expected_revision where an editor intends optimistic concurrency.

**Downstream impact:** M10 policy availability, M09 editing, M05-consistent store discipline.

**Corpus references:** M10-C043, M10-C044, M10-C168, M10-C204

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-04 — Concurrent snippet patches can commit an invalid kind/content combination

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Store concurrency

**Canonical requirement:** S17 safe versioned snippets; committed content must satisfy the kind-specific domain invariant.

**Code location / source:** [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) — schema v6, Store.submit/_submit and writer transactions

**Current behavior:** Snippet updates similarly validate against a caller-side snapshot and later apply only changed fields.

**Failure mechanism:** Kind and content are coupled. A kind-only update and a content-only update can each pass against the old plain snippet but leave invalid URL content after both commits.

**Minimal reproduction:** Start with kind=plain, content=https://example.invalid/path. Barrier two reads. A changes kind=url. B changes content to two ordinary words while it still sees kind=plain. Commit A then B and inspect raw storage/public reconstruction.

**Expected behavior:** Reject the stale/incompatible patch without committing invalid snippet state; compatible independent changes can still merge under an explicit policy.

**Likely actual behavior / verification boundary:** The row may commit as kind=url with non-URL content; reconstruction can then raise. Exact exception wording is a local reproduction detail.

**Existing coverage:** Sequential snippet CRUD and positive expansions exist.

**Why the oracle misses it:** No test validates writer-current correlated fields under two concurrent callers.

**Regression recommendation:** Assert both raw row validity and public snapshot build after barrier-controlled orders, with positive URL and ordinary-plain controls.

**Narrow repair direction:** Writer-authoritative merge and validation, plus version-aware UI writes. Do not address this only by retrying a failed post-write read.

**Downstream impact:** M10 expansion availability and M09 configuration UX.

**Corpus references:** M10-C045, M10-C206

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-06 — Truthiness coercion can enable rules, snippet rewriting and transform auto-apply

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Boolean admission / M11 seam

**Canonical requirement:** Explicit enablement and M11 auto-apply opt-in; Boolean-looking strings are not Boolean authorization.

**Code location / source:** [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/transforms/definitions.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms/definitions.py) — TransformDefinition, TransformSnapshot.auto_apply_decision/for_mode; [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms_store.py) — update_transform Boolean admission; no general M11 store re-audit; [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/transforms.md) — enabled frozen definitions, opt-in and honest fallback

**Current behavior:** M10 mutation paths use bool(value)/int(bool(value)); TransformStore.update_transform does so for auto_apply and enabled. TransformDefinition.from_json also coerces these fields.

**Failure mechanism:** The string "false" is truthy, so a public update intended to disable auto-apply can persist 1. Domain constructors do not consistently reject malformed Boolean primitives first.

**Minimal reproduction:** Call update_transform("builtin:polish", auto_apply="false"), then resolve a Polish style and exercise the real coordinator with a recording fake supervisor. Separately update style enabled and snippet allow_rewrite using "false", "0", [], {}. Positive controls use real True and False.

**Expected behavior:** Reject malformed types before mutation; only an actual Boolean True grants opt-in. DB integer-to-bool decoding is not the public admission boundary and need not be removed.

**Likely actual behavior / verification boundary:** The transform update can store enabled auto-apply and run under the selected M10 mode. Empty containers and nonempty strings differ by truthiness rather than a strict schema.

**Existing coverage:** M11 positive True/negative default-off coordinator tests are strong, but malformed primitive opt-in is absent.

**Why the oracle misses it:** A checkbox always passes a Boolean; that does not qualify public store/deserialization boundaries.

**Regression recommendation:** Assert stored type/value and actual transform call count for each malformed input. Reject before any revision or event content changes.

**Narrow repair direction:** Strict primitive validation at shared public boundaries. Limit M11 edits to the auto-apply/enabled admission seam; do not reopen model quality or general transform design.

**Downstream impact:** M10 authority and exact snippets; M11 no-silent-auto-apply; M15 safety.

**Corpus references:** M10-C036, M10-C048, M10-C049, M10-C050, M10-C051, M10-C052, M10-C053, M10-C054, M10-C055, M10-C056, M10-C057, M10-C058, M10-C059, M10-C060, M10-C061, M10-C062, M10-C063, M10-C064, M10-C065, M10-C066, M10-C067, M10-C106, M10-C107, M10-C159, M10-C160, M10-C161, M10-C163, M10-C182, M10-C211

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-07 — M10 configuration has no strict path-list and scanning-Boolean admission

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Configuration / filesystem authority

**Canonical requirement:** Only explicitly configured developer paths may be scanned; malformed configuration cannot broaden reads.

**Code location / source:** [localflow/config.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/config.py) — M10 configuration defaults/merge; contrast with context_policy; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator

**Current behavior:** Configuration is merged without M10-specific strict validation; configure converts path collections with tuple(value or ()) and the listing switch with bool(value).

**Failure mechanism:** A string supplied instead of a list becomes a sequence of characters, potentially including a root or relative path; "false" enables the listing switch. This differs from the validated M06 context policy.

**Minimal reproduction:** Load synthetic config with skill_manifest_paths as a string, workspace_skill_dirs as a string, and developer listing set to "false". Instrument discovery/listing invocations rather than scanning the real machine.

**Expected behavior:** Reject or disable the invalid feature with a typed content-free reason, retaining ordinary dictation. No scan is derived from malformed input.

**Likely actual behavior / verification boundary:** Malformed values can be accepted and interpreted as different filesystem authority. The exact file-read population depends on the host and must be measured only in a synthetic filesystem.

**Existing coverage:** Happy-path list configuration and default settings are covered.

**Why the oracle misses it:** No negative schema matrix checks both admission and zero filesystem effects.

**Regression recommendation:** Test strings, mappings, nested lists, non-string elements, empty values and Boolean subclasses/types as applicable; every invalid case must have a no-read witness.

**Narrow repair direction:** Introduce one immutable validated M10 config object with explicit path collection types and Boolean admission. Preserve the separately defined workspace identity/locator distinction.

**Downstream impact:** M06 read policy, M10 privacy, startup reliability and capture feedback.

**Corpus references:** M10-C120, M10-C121, M10-C122, M10-C123, M10-C124, M10-C125, M10-C131, M10-C132, M10-C138

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-08 — SKILL.md frontmatter need not be at the start, so body metadata can become authority

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Manifest interpretation

**Canonical requirement:** S17 configured manifests/frontmatter only; skill body text is not registry or prompt authority.

**Code location / source:** [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests

**Current behavior:** The frontmatter parser searches for a delimiter rather than requiring the opening delimiter at the document start, and does not robustly require a complete closed frontmatter block.

**Failure mechanism:** Ordinary body text followed by a Markdown horizontal-rule block containing name/aliases can be interpreted as skill identity. A well-formed initial frontmatter canary test does not cover this shape.

**Minimal reproduction:** Create SKILL.md beginning with ordinary prose, then --- / name: body-canary / aliases: [body alias] / ---. No valid leading frontmatter exists. Repeat with an unclosed leading block and a later body delimiter.

**Expected behavior:** No skill identity is accepted from the body; malformed/incomplete frontmatter is refused or ignored with an explicit non-content reason.

**Likely actual behavior / verification boundary:** The later block can populate registry identity. This does not mean the body executes or is appended to the LLM prompt; the defect is promotion of body metadata into registry authority.

**Existing coverage:** test_skills.py has a canary body under ordinary valid frontmatter and checks non-execution/serialization.

**Why the oracle misses it:** It does not move the identity-shaped text into a non-frontmatter body region.

**Regression recommendation:** Anchor-independent oracle: only a syntactically valid, bounded, leading closed header may yield the canary identity. Include a valid header with hostile body as a positive preservation test.

**Narrow repair direction:** Use a bounded leading-frontmatter parser with an explicit supported field schema and closing-delimiter requirement.

**Downstream impact:** M10 exact skill emission, manifest provenance and M15 developer safety.

**Corpus references:** M10-C110, M10-C111, M10-C112

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-10 — Skill cache ignores in-place changes to child manifests

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Cache invalidation

**Canonical requirement:** New jobs must see changed configured manifest content while old jobs keep their frozen state.

**Code location / source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests

**Current behavior:** _m10_skill_records keys discovery by configured top-level path modification times and workspace identity. For a skill directory, the child SKILL.md content is not part of that cache key.

**Failure mechanism:** Editing an existing child file normally leaves the parent directory modification time unchanged. The coordinator can therefore reuse the old registry for subsequent jobs.

**Minimal reproduction:** Discover allowed/unit/SKILL.md with alias alpha; edit that existing file in place to alias beta without changing the directory entry; start a second job. Repeat an atomic child replacement and deliberate timestamp preservation.

**Expected behavior:** A keeps alpha; a later fresh B gets beta under a documented current manifest fingerprint. Cache hits cannot claim a fresh discovery when child inputs were not checked.

**Likely actual behavior / verification boundary:** B can keep alpha even though direct discover() would see beta. This is distinct from same-job rereading in AUDIT-11.

**Existing coverage:** The skill refresh test invokes discovery directly instead of the coordinator cache.

**Why the oracle misses it:** Bypassing _m10_skill_records proves the parser refreshes, not the product cache.

**Regression recommendation:** Drive the real coordinator with synthetic directories; record actual discovery calls, cache keys and resulting registry revisions.

**Narrow repair direction:** Fingerprint the actual configured manifest set/content or use a reliable invalidation protocol. Include deletions and child replacements; bound the work separately.

**Downstream impact:** M10 correctness across jobs, M06 workspace changes and M15 latency.

**Corpus references:** M10-C126, M10-C127, M10-C128, M10-C130, M10-C208

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-11 — Release-time discovery can replace manifest state already captured for the job

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Per-job freeze

**Canonical requirement:** The central M10 invariant and pre-decode registry provenance: edits after the chosen freeze boundary affect future jobs, not this job.

**Code location / source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05

**Current behavior:** _m10_freeze captures records, but _m10_finalize_upgrade can call discovery again and replace skill_records/registry state during finalization.

**Failure mechanism:** A global manifest edited after hotkey-down can be reread and change the current job. It is not merely late destination classification over the original immutable configuration.

**Minimal reproduction:** Configure one global JSON manifest. Start A and pause after _m10_freeze; replace its alias/token while preserving destination identity; finish A, then start B. Record the two captured registry revisions and emitted skills.

**Expected behavior:** Under the prompt/current freeze claim, A retains the initial configured manifest; B sees the edit. If scope projection requires a later boundary, that must be explicitly adjudicated and represented as a separate snapshot, not silently advertised as hotkey-frozen.

**Likely actual behavior / verification boundary:** A can use the edited records when the top-level manifest fingerprint changes. Source establishes the reread; execution remains NOT_RUN.

**Existing coverage:** Style/snippet in-flight tests and direct registry tests exist; they do not hold a manifest edit at this coordinator boundary.

**Why the oracle misses it:** A frozen object can be replaced in a mutable job dictionary even if that object itself is immutable.

**Regression recommendation:** Barrier at _m10_freeze completion and before finalization; assert token, record fingerprint, policy revision, hints and evidence all refer to A's original state.

**Narrow repair direction:** Freeze configured content once and project scope from it. Keep workspace discovery authority explicit and atomically publish the complete final tuple.

**Downstream impact:** M04 skill policy, M06 pre-decode provenance, M14 exact inputs, M15.

**Corpus references:** M10-C126, M10-C128, M10-C130, M10-C187, M10-C203, M10-C208

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-12 — The later M10 finalizer can bypass M06 rollback and publish mixed registry/policy state

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Atomic composition

**Canonical requirement:** Post-M06 contract: deferred/failed widening retains the captured coherent profile, number policy, vocabulary and skills tuple.

**Code location / source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M06.md) — local remediation; R3 rollback; authority decisions

**Current behavior:** _finalize_job_context restores captured profile state on a failed/deferred widening. The subsequent _m10_finalize_upgrade has independent registry mutation and does not consistently honor that disposition; it assigns registry records before all downstream policy work succeeds.

**Failure mechanism:** A protected M06 downgrade can be followed by M10 adding destination/workspace records anyway. An exception after assignment can also leave evidence-facing records newer than the policy actually used.

**Minimal reproduction:** Force M06 widening_deferred or widening_failed with an otherwise available synthetic workspace locator. Then run the real following M10 finalizer. Separately inject failure after record selection but before _finalized_policy completes. Compare every tuple component and envelope reference.

**Expected behavior:** Either one fully committed authorized upgrade or the entire captured fallback tuple; no newly claimed registry whose rules were not used, and no widened rules after a disposition that refused widening.

**Likely actual behavior / verification boundary:** A hybrid is possible. The original M06 rollback repair itself is present and should not be removed or falsely reported absent.

**Existing coverage:** M06 review R3 covers its guarded stage; historical M10 manifest-retention coverage tests the successful path.

**Why the oracle misses it:** Testing each finalizer alone misses the sequential composition and exception between field assignments.

**Regression recommendation:** Exercise the actual M06→M10 order with barriers/faults at category, profile, vocabulary, registry and hints. Explicitly distinguish accepted hint-failure degradation from unauthorized scope widening.

**Narrow repair direction:** Build the candidate tuple off to the side, honor scope_disposition, then replace it once. Keep _finalized_policy as the single successful policy builder.

**Downstream impact:** M05/M06 authority, M04 policy, M11 targeting and M14 provenance.

**Corpus references:** M10-C038, M10-C039, M10-C040, M10-C041, M10-C130, M10-C131, M10-C133, M10-C201, M10-C208, M10-C209, M10-C210, M10-C217

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-13 — A freeze failure can consume Next Dictation Mode without applying it

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Override ownership

**Canonical requirement:** A next-job override belongs to exactly one admitted capture/job under an explicit consumption point; failure must not silently change requested Raw behavior.

**Code location / source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests

**Current behavior:** _m10_freeze clears the pending mode before later snapshot/discovery operations complete. The surrounding start path can continue after an M10 exception.

**Failure mechanism:** A later transform snapshot or manifest failure prevents the override from being installed in the job, while the pending slot has already been cleared.

**Minimal reproduction:** Set next mode Raw. Inject a failure after the pending mode has been taken but before _m10_freeze returns. Complete A using synthetic ASR, then begin B. Observe cleanup/transform calls and both jobs' requested/effective mode.

**Expected behavior:** A either retains its captured Raw override with coherent degraded registries or stops with an honest explicit failure; an unconsumed override is restored only under a race-safe documented ownership policy.

**Likely actual behavior / verification boundary:** The override can affect neither A nor B. This is not a claim that normal cancelled/too-short captures must restore an already consumed override.

**Existing coverage:** Healthy one-shot override and Raw path tests exist.

**Why the oracle misses it:** They do not inject failure after consume and before snapshot publication.

**Regression recommendation:** Record a mode ownership token at the linearization point; test freeze faults, cancellation, short capture, identity failure, worker retry and a second queued request.

**Narrow repair direction:** Capture the override into job-owned state before fallible optional work; never let an error turn requested Raw into normal cleanup without disclosure.

**Downstream impact:** M10 user intent; M03 lifecycle compatibility; M11 no hidden transform.

**Corpus references:** M10-C026, M10-C027, M10-C028, M10-C029, M10-C030, M10-C031, M10-C032, M10-C033, M10-C035, M10-C036, M10-C113, M10-C114, M10-C115, M10-C116, M10-C186, M10-C207, M10-C218

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-14 — Snippet matching bypasses hard delimiters and can consume punctuation it does not own

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Snippet grammar

**Canonical requirement:** S10 literal/source-span discipline and S17 exact snippets; a multiword trigger cannot bridge separate clauses/lines silently.

**Code location / source:** [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/normalization.md) — literal/barrier protection, arbitration and M10-owned grammars; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage

**Current behavior:** Snippet proposals are exempted from the engine barrier check, but their own trigger/slot scan lacks the corresponding connected-token barrier test. Whole-token boundaries also include surrounding punctuation.

**Failure mechanism:** Matching token words can join a trigger split by a period or newline; slot collection can cross a structural boundary. Replacing whole token spans can remove a sentence delimiter rather than preserving it around the inserted payload.

**Minimal reproduction:** Snippet trigger quick reply → ACK. Normalize quick
reply and quick. reply, with punctuation commands otherwise off. Then use a one-slot snippet followed by value
Do not deploy. Include quick reply. as an edge-punctuation case and quoted/escaped controls.

**Expected behavior:** No cross-line/clause trigger, no structural trailing-prose consumption, and punctuation outside the trigger span preserved. Exact payload bytes survive once legitimately expanded.

**Likely actual behavior / verification boundary:** A snippet can expand across a delimiter or consume boundary punctuation/prose. Test the ledger spans and exact output bytes locally.

**Existing coverage:** Positive expansions, protected quotes, collisions and a long-slot cap are covered.

**Why the oracle misses it:** The owning suite does not combine a valid trigger with hard separators or check ownership of edge punctuation.

**Regression recommendation:** Table every M04 hard separator, Unicode whitespace distinction and quote/literal transition; independent expected spans and exact outputs.

**Narrow repair direction:** Use connected core spans for the trigger and explicit bounded slot delimiters consistent with existing policy. Do not change the documented unpunctuated 24-word convention without adjudication.

**Downstream impact:** M04 literal safety, M07 generated protection, M10 exact output, M14 provenance.

**Corpus references:** M10-C069, M10-C070, M10-C071, M10-C072, M10-C073, M10-C074, M10-C075, M10-C076, M10-C077, M10-C078, M10-C079, M10-C080, M10-C081, M10-C085, M10-C086, M10-C087, M10-C088, M10-C091, M10-C092, M10-C093, M10-C094, M10-C095, M10-C096, M10-C097

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-15 — File-tag grammar can infer attachment intent across clause boundaries

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Developer intent parsing

**Canonical requirement:** S17 explicit attach file syntax only; ordinary prose and literal/quoted boundaries do not authorize a file reference.

**Code location / source:** [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/normalization.md) — literal/barrier protection, arbitration and M10-owned grammars

**Current behavior:** The file-tag grammar is also barrier-exempt and scans word tokens without enforcing connected command/name spans.

**Failure mechanism:** attach at the end of one sentence and file at the start of the next can be treated as one action. Name tokens can similarly be taken across a newline.

**Minimal reproduction:** Known synthetic file alpha.py. Normalize attach. file alpha dot py and attach file
alpha dot py; compare attach file alpha dot py plus untouched trailing prose. Add quoted and literal-escape variants.

**Expected behavior:** Only a connected explicit command yields a resolution; disconnected prose stays literal/review without a fabricated attachment action.

**Likely actual behavior / verification boundary:** Disconnected words can resolve to a filename. This is a text/intent defect; the audited path does not create real file attachments.

**Existing coverage:** File-resolution positives and ambiguity tests exist, mostly with contiguous plain input.

**Why the oracle misses it:** Utility resolver tests start after parsing and cannot detect unauthorized command formation.

**Regression recommendation:** Drive normalize and the coordinator, asserting both output and absence/presence of file_tag ledger entries.

**Narrow repair direction:** Apply the shared hard-boundary predicate to the command and owned reference span, retaining progressive-prefix trailing prose preservation.

**Downstream impact:** M04 syntax, M10 explicit intent and evidence, M08 safe final payload.

**Corpus references:** M10-C145, M10-C146, M10-C147, M10-C148

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-16 — Open-document preference defeats duplicate-basename ambiguity

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** File resolution authority

**Canonical requirement:** Speaking only a basename shared by multiple candidates cannot silently choose a file; a disambiguating path is required when supported.

**Code location / source:** [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/developer/test_developer_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_developer_resolution.py) — file ambiguity, listing and helper-level attachment/surface tests

**Current behavior:** FileTagResolver.resolve checks the open document's basename/prefix before considering the candidate-set ambiguity.

**Failure mechanism:** The open file becomes an implicit tie-breaker even when src/config.json and tests/config.json are both eligible matches for config json.

**Minimal reproduction:** Known files: src/config.json and tests/config.json; document_name=config.json. Resolve config json, then explicit src slash config dot json. Reverse input candidate order and vary the active document.

**Expected behavior:** Bare basename remains ambiguous; an exact spoken path may resolve uniquely. The open document may be shown as a suggestion, not used to bypass the ambiguity rule.

**Likely actual behavior / verification boundary:** The early document branch can return resolved before the duplicate union is inspected.

**Existing coverage:** Duplicate basenames and open-document matching are tested separately.

**Why the oracle misses it:** No test supplies both a matching open document and a genuine competing basename population.

**Regression recommendation:** One integrated positive-path/negative-basename matrix, including foo/foobar/foo-bar and candidate-order permutation.

**Narrow repair direction:** Resolve against the complete authoritative candidate set before selecting; document preference must never manufacture uniqueness.

**Downstream impact:** M10 file intent/provenance; later attachment consumers must not inherit a false resolution.

**Corpus references:** M10-C139, M10-C140, M10-C141, M10-C142, M10-C143

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-21 — Timed-out configuration writes are reported as failed without reconciling possible commits

**Severity:** HIGH

**Confidence:** High (source-supported; not executed)

**Category:** Unknown outcome / idempotency

**Canonical requirement:** The current Store timeout bounds the wait, not the queued mutation; M09 outcome honesty must extend to M10 configuration.

**Code location / source:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) — schema v6, Store.submit/_submit and writer transactions; [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/store.md) — single-writer atomic operations and timeout semantics; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics

**Current behavior:** Styles/Snippets catch TimeoutError as a generic exception and display not saved/not deleted. Adds allocate fresh identities inside each attempt; no operation-level reconciliation is exposed in these handlers.

**Failure mechanism:** The writer can commit after the UI reports failure. Retrying Add Style creates a second rule with a fresh ID; its equal-authority resolution may silently differ. Exact duplicate snippet triggers are blocked by the existing unique index, but that does not provide an honest reconciled success.

**Minimal reproduction:** Allow an Add Style to enqueue, hold its writer completion beyond the caller wait, release it to commit, then press Add again. Repeat Add Snippet and an update. Distinguish a read timeout before enqueue from a mutation timeout after admission.

**Expected behavior:** Report outcome unknown only after actual mutation admission, retain stable operation identity, reconcile with the writer/store, and prevent blind duplicate creation on retry.

**Likely actual behavior / verification boundary:** The UI can say not saved although the row exists; a style retry can create two enabled same-authority rules. No claim that a timeout guarantees a late commit.

**Existing coverage:** M09 has unknown-outcome regressions for other actions; inspected M10 handlers retain generic exception branches.

**Why the oracle misses it:** Synchronous happy-path CRUD never holds an admitted writer op past the caller deadline.

**Regression recommendation:** Barrier-based admitted/not-admitted timeout controls; count rows, stable IDs and committed revisions after reconciliation.

**Narrow repair direction:** Return typed admission/outcome state; preallocate/reuse an operation or row ID and reconcile. Do not globally cancel writer operations or mistake pre-read timeout for an unknown write.

**Downstream impact:** M09 outcome semantics, M10 authority, duplicate-rule UX and caches.

**Corpus references:** M10-C010, M10-C011, M10-C012, M10-C013, M10-C068, M10-C170, M10-C171, M10-C172, M10-C213

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

## Medium Findings

9 registered. Each record below is source analysis or a defined proof/policy gap; target execution remains `NOT_RUN`.

### M10-AUDIT-05 — Update/delete races lack authoritative affected-row outcomes

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Mutation outcomes

**Canonical requirement:** M09/store outcome honesty; an earlier existence read is not proof that a later mutation affected a row.

**Code location / source:** [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) — schema v6, Store.submit/_submit and writer transactions; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics

**Current behavior:** M10 update/delete paths do not consistently assert that their target row still exists at mutation time before reporting completion or bumping configuration state.

**Failure mechanism:** Deletion can happen between caller validation and writer execution. A zero-row UPDATE can still advance a state counter or lead to an unhelpful return/post-read instead of an explicit stale/deleted outcome.

**Minimal reproduction:** Hold a style update after its read, delete that rule, release the update. Repeat with a snippet and with repeated deletion. Capture affected rows, meta revisions and public results.

**Expected behavior:** An explicit not-found/stale outcome; no fabricated changed revision and no recreation of the deleted row.

**Likely actual behavior / verification boundary:** A ghost mutation notification or misleading result is possible, but the inspected patch SQL does not itself recreate the row. Do not label this resurrection without a separate path.

**Existing coverage:** Normal update and deletion are exercised sequentially.

**Why the oracle misses it:** Prior-existence assertions and final snapshots do not prove the intended row existed during mutation.

**Regression recommendation:** Barrier deletion between read and write; assert exact rowcounts and result classifications.

**Narrow repair direction:** Check affected rows in the writer transaction and return a structured, content-free mutation result.

**Downstream impact:** M09 stale editors, M10 cache invalidation and reconciliation.

**Corpus references:** M10-C046, M10-C047, M10-C068, M10-C169, M10-C205

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-09 — Syntactically valid but wrong-shaped manifests can escape the discovery error boundary

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Manifest robustness

**Canonical requirement:** Malformed optional developer configuration must not abort unrelated capture configuration or consume an override silently.

**Code location / source:** [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests

**Current behavior:** Discovery handles selected parse/read exceptions, but nested JSON shapes are used without complete type validation. TypeError, AttributeError or KeyError can escape for valid JSON of an unexpected shape.

**Failure mechanism:** A parseable list, scalar, null or malformed nested skill entry is not a JSON decoding failure. The outer capture boundary may catch the exception only after M10 freeze has partly progressed.

**Minimal reproduction:** Pass configured files containing null, a scalar, a skills collection of scalars, or a malformed aliases value. Trace discovery return, the next-mode slot and job M10 configuration.

**Expected behavior:** A scoped manifest-invalid outcome and a still-coherent job configuration; unrelated valid configured manifests can be handled according to a documented fail-closed policy.

**Likely actual behavior / verification boundary:** An uncaught shape error can abort the M10 snapshot path. Exact failing shapes and exception classes must be recorded by local reproduction rather than assumed identical.

**Existing coverage:** Malformed JSON syntax is covered; full shape/type admission is not.

**Why the oracle misses it:** Decode-error tests exercise a different failure class from a valid JSON document with the wrong schema.

**Regression recommendation:** Independent schema-negative matrix with valid peer manifests and a pending Raw override.

**Narrow repair direction:** Validate outer and nested primitives before use; convert parse failures to a typed result rather than a blanket success/empty registry.

**Downstream impact:** M10 robustness; interacts with AUDIT-13 override loss.

**Corpus references:** M10-C027, M10-C113, M10-C114, M10-C115, M10-C116, M10-C117, M10-C182, M10-C218

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-17 — Snapshot containers and exported conflicts are not deeply immutable

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Snapshot identity

**Canonical requirement:** Per-job snapshot revision must identify immutable captured behavior/diagnostics, including nested containers and exported JSON.

**Code location / source:** [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests

**Current behavior:** SnippetSnapshot/SkillRegistry use frozen records or read-only indexes in places, but the snapshot classes are not uniformly sealed and nested conflict maps/lists can be shared through serialization.

**Failure mechanism:** A caller can mutate a returned conflict structure or assign snapshot state while the recorded revision remains unchanged. Standard stored string payloads themselves are immutable; no arbitrary nested rich-text payload is alleged.

**Minimal reproduction:** Build a snapshot with a real duplicate-trigger/skill conflict. Mutate a nested list in to_json()["conflicts"], then serialize again and compare revision. Separately attempt public snapshot attribute replacement and caller-list mutation.

**Expected behavior:** Mutating an export cannot change the snapshot; unsupported attribute writes fail or are detached copies. Revision remains a reliable fingerprint.

**Likely actual behavior / verification boundary:** At least diagnostic nested state can change without revision change. Establish any behavioral effect separately instead of assuming every mutable field changes matching.

**Existing coverage:** Existing freeze tests generally edit the store, not the captured object/export itself.

**Why the oracle misses it:** Tuple conversion and frozen dataclass tests are not sufficient for a container of mutable nested records.

**Regression recommendation:** Deep mutation matrix with behavior, conflicts, serialized bytes and revision invariants; caller-list positive preservation control.

**Narrow repair direction:** Seal snapshot state and deeply freeze/copy nested collections at admission/serialization, keeping lookups efficient.

**Downstream impact:** M10 explainability and cache/provenance; M14 retained snapshot fidelity.

**Corpus references:** M10-C082, M10-C083, M10-C102, M10-C105, M10-C106, M10-C107, M10-C202, M10-C219

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-18 — Collision preview disagrees with actual explicit-skill arbitration

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Preview parity / oracle

**Canonical requirement:** Hub collision preview must describe the same candidate eligibility and span conflict as runtime.

**Code location / source:** [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) — expansion, collision runtime/preview, store and freeze coverage; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits

**Current behavior:** Preview treats a bare skill alias as a collision even though runtime requires explicit slash intent; it also receives a broader vocabulary population and a synthetic candidate ID without a selected-item exclusion.

**Failure mechanism:** The inspected tests positively require bare code review to expand as a snippet, yet separately require preview to call that bare alias ambiguous. A test encodes the discrepancy instead of detecting it.

**Minimal reproduction:** Snippet code review → REVIEW; registered skill /code-review alias code review. Compare runtime and preview for code review and slash code review. Add disabled/out-of-scope vocabulary and preview an unchanged selected snippet.

**Expected behavior:** Preview matches eligible runtime proposals and distinguishes same-span ambiguity from a different explicit command; editing a snippet does not conflict with itself.

**Likely actual behavior / verification boundary:** False ambiguity warnings and self/scope false positives are expected; additional false negatives need independent reproduction, not assumption.

**Existing coverage:** Runtime positive and preview checks both exist in test_snippets.py, but use inconsistent expected outcomes.

**Why the oracle misses it:** Each test checks its own expected label rather than preview versus engine under identical frozen inputs.

**Regression recommendation:** Differential eligibility/decision assertions with independently specified expected actions; mutate preview only and require a failure.

**Narrow repair direction:** Share candidate construction/eligibility with runtime or derive preview from a dry-run proposal graph; retain a separate oracle and selected-item identity.

**Downstream impact:** M09 configuration confidence, M05 scope, M10 usability and no-op-proof tests.

**Corpus references:** M10-C082, M10-C083, M10-C098, M10-C099, M10-C100, M10-C101, M10-C102, M10-C103, M10-C173, M10-C174, M10-C216

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-19 — Phrase preview mixes stale snippets and last-workspace files under an unscoped label

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Preview authority

**Canonical requirement:** A sandbox must accurately identify the scope and configuration revision it previews, and must not impersonate the selected style or a live destination.

**Code location / source:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) — canonical scope comparisons and writer-authoritative mutation discipline

**Current behavior:** hubPreviewPhrase combines current unscoped vocabulary/skills with the cached snippet snapshot, _last_file_resolver and an active/last normalization preview policy. The selected style editor is not passed as explicit scope.

**Failure mechanism:** A snippet edit may not be reflected until another job refreshes the cache, while a file from a prior workspace can resolve in a supposedly global-only sandbox.

**Minimal reproduction:** Run a job in synthetic workspace A to install alpha.py, edit a snippet without starting a new dictation, then preview its trigger and attach file alpha dot py from the Styles pane. Repeat while Raw/standard is selected in the editor.

**Expected behavior:** Preview names its exact frozen sandbox inputs; no prior-workspace file authority under a global-only claim; a requested selected-style preview actually uses that style.

**Likely actual behavior / verification boundary:** Stale expansion and last-workspace filename resolution can disagree with displayed/global scope. Preview itself does not increment usage or train.

**Existing coverage:** Preview output is exercised, but not compared with a just-edited snippet or an unrelated preceding workspace.

**Why the oracle misses it:** Using the same cached objects in both setup and assertion masks stale revisions and scope contamination.

**Regression recommendation:** Assert revision IDs and file-candidate provenance alongside outputs, with a fresh store edit and workspace removal.

**Narrow repair direction:** Use an explicit preview request containing declared destination/profile and freshly snapshotted registries. Default to truly global/no-files, or label any explicit workspace sandbox.

**Downstream impact:** M05 sandbox authority, M09 UX, M10 explainability.

**Corpus references:** M10-C173, M10-C216

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-20 — Stable table IDs do not protect stale Styles/Snippets editor contents

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Hub editor concurrency

**Canonical requirement:** Post-M09 rendered selection/editor binding; stale updates must not overwrite newer configuration or retain an actionable deleted editor.

**Code location / source:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/state.py) — Styles/Snippets service loading and selection state; [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics

**Current behavior:** M09 rendered-row stable IDs are in place. M10 update actions nevertheless submit every visible field without an expected revision, and pane refresh does not clear all editor controls merely because a rendered row vanished.

**Failure mechanism:** A legitimate edit by another caller can be overwritten by a full stale form update. Deselecting a missing table row under suppressed callbacks is not equivalent to invalidating the editor's identity and text.

**Minimal reproduction:** Load rule A into the form; externally change A's number policy; change only its name in the old form and press Update. Repeat for snippet kind/content. Delete the selected row externally, refresh, and inspect field contents, selected identity and enabled mutation controls.

**Expected behavior:** Reject stale revision or merge only explicitly changed fields under a documented policy; clear/disable deleted editors. Row reorder alone must still update A, never the row now at A's old index.

**Likely actual behavior / verification boundary:** The full stale form can overwrite the newer field. Exact native visual/focus behavior remains unexecuted; table ID binding itself is a verified strength.

**Existing coverage:** Shared Hub tests wire real services and cover CRUD; M09 stable-row architecture exists.

**Why the oracle misses it:** Programmatic same-session field writes do not model an external concurrent edit or a deleted editor's lifetime.

**Regression recommendation:** Real HubController + MainQueue, rendered row reorder, independent store update/delete and a native editor check.

**Narrow repair direction:** Bind editor buffer to stable ID and revision, use CAS/field-diff writes, and invalidate it explicitly on disappearance. Do not redesign the Hub.

**Downstream impact:** M09 state contract and M10 configuration integrity.

**Corpus references:** M10-C046, M10-C047, M10-C167, M10-C168, M10-C169, M10-C175, M10-C176, M10-C212

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-22 — Advertised discovery/listing limits bound results, not all filesystem work

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Resource bounds

**Canonical requirement:** Bounded developer discovery/listing must not stall capture or do unbounded optional work; report real costs separately.

**Code location / source:** [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) — fixture construction, timed callbacks, output manifest

**Current behavior:** Frontmatter extraction reads a bounded prefix, but _hash_file reads the entire file; JSON manifests are read whole. Directory listing materializes/sorts scandir results before applying the output cap.

**Failure mechanism:** A huge SKILL.md body or wide directory can consume substantial I/O/memory even when only a small header or 500 filenames are returned. Parser bytes and separately read hash bytes can also refer to different file revisions during a concurrent edit.

**Minimal reproduction:** Synthetic manifest with a tiny header and a large generated body; synthetic directory with far more than 500 entries. Instrument bytes read/entries visited. Barrier a content replacement between parse and hash and inspect record identity.

**Expected behavior:** Explicit byte/entry budgets and honest truncation/refusal; metadata identity corresponds to the parsed bytes. A result cap alone is not described as a traversal/work cap.

**Likely actual behavior / verification boundary:** Total reads/enumeration can exceed the advertised small result bounds; mixed parse/hash revisions are a source-supported race to reproduce.

**Existing coverage:** Current tests check returned count/depth and successful manifests, not all bytes/visits or parse/hash coherence.

**Why the oracle misses it:** An assertion len(files)<=500 passes after enumerating a million entries.

**Regression recommendation:** Instrumented I/O counters independent of returned arrays, positive near-limit populations and a parse/hash barrier.

**Narrow repair direction:** Bound file admission and enumeration; derive parsing and fingerprint from the same admitted bytes/handle. Preserve deterministic selection and disclose any bounded sampling policy.

**Downstream impact:** M06 release budget, M10 responsiveness/privacy minimization and M15 measurement.

**Corpus references:** M10-C129, M10-C134, M10-C135, M10-C136, M10-C137, M10-C138, M10-C214

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-23 — Applied snippet evidence does not retain the exact frozen template revision and rewrite policy

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Generated-text provenance

**Canonical requirement:** M10 task 6; S29.4 exact mode/style/snippet revision and expansion provenance; immutable stage-input lineage.

**Code location / source:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) — SnippetStore mutation methods and row reconstruction; [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/artifacts.md) — retained exact stage inputs, revision lineage and deletion; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05

**Current behavior:** The envelope records snippet snapshot revision/count and the governed normalization ledger records expansion output and snippet rule ID. The inspected producer does not retain the applied snippet's exact template, individual revision and allow_rewrite decision as a recoverable job manifest.

**Failure mechanism:** After the configuration row changes or is deleted, the hash/ID and filled output are insufficient to reconstruct which characters came from a template versus slot values, or why the span was protected/rewriteable.

**Minimal reproduction:** Capture a two-slot snippet at revision 1 with allow_rewrite=false and collection enabled; finish the job; edit/delete the snippet; reconstruct only from retained job artifacts, without querying current configuration.

**Expected behavior:** An exact governed applied-definition/provenance manifest or an explicit not-captured limitation prevents claims of replayable template provenance. Do not copy raw template content into operational events.

**Likely actual behavior / verification boundary:** The original expanded text remains available, but complete original snippet-definition provenance is not independently reconstructible from the inspected artifacts.

**Existing coverage:** Pipeline producer tests check generated edits and high-level profile metadata, not offline reconstruction after definition deletion.

**Why the oracle misses it:** Reading today's snippet store makes a missing historical definition look available.

**Regression recommendation:** Offline reconstruction test with the current configuration inaccessible; independently assert template revision, slot source spans and rewrite authorization.

**Narrow repair direction:** Retain only the required applied frozen definitions/slot provenance under governed leases, with deletion/consent semantics; otherwise accurately downgrade completeness.

**Downstream impact:** M14 task eligibility and acoustic-versus-generated distinction; M15 auditability. No Critical false-ASR export has been demonstrated.

**Corpus references:** M10-C088, M10-C097, M10-C104, M10-C106, M10-C107, M10-C108, M10-C109, M10-C177, M10-C178, M10-C188, M10-C202, M10-C219, M10-C220

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-24 — Runtime filename fallback lacks the promised explicit attachment-not-created result

**Severity:** MEDIUM

**Confidence:** High (source-supported; not executed)

**Category:** Attachment status integration

**Canonical requirement:** M10-AC04: uncertified surfaces retain resolved text and explain that attachment creation was not verified.

**Code location / source:** [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/developer/surfaces.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/surfaces.py) — live compatibility table and certification sets; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05

**Current behavior:** attachment_plan has an honest uncertified helper result, and the live certification set is empty. The inspected coordinator never calls that helper; the runtime grammar emits a filename with attach_file/exact_match metadata, without an explicit attachment_created=false result or its reason.

**Failure mechanism:** Helper-level tests certify a status object the production normalization/insertion path does not use. Plain filename insertion is not the promised limitation explanation.

**Minimal reproduction:** Through the real coordinator, resolve attach file alpha dot py on an uncertified synthetic editor. Capture final payload, Hub/menu notices, events and retained decision metadata. Require a real positive filename match.

**Expected behavior:** Filename preserved and attachment_created=false with an explicit uncertified/not-supported reason in the actual action outcome shown/retained. No surface is called certified without native readback qualification.

**Likely actual behavior / verification boundary:** The filename can be emitted without the helper's explicit limitation notice. No live true attachment_created claim or actual attachment effect was found.

**Existing coverage:** test_developer_resolution.py tests attachment_plan directly, including a supplied test certification set.

**Why the oracle misses it:** A passing helper is not evidence that any production caller consumes its result.

**Regression recommendation:** Coordinator-level producer/UI assertion; a helper-no-op or unwired helper must fail the contract test.

**Narrow repair direction:** Wire a typed file-reference outcome into the production action/evidence path without implementing speculative file-chip insertion or arbitrary file reads.

**Downstream impact:** M10 user intent and truthful action reporting; M14 evidence consumers.

**Corpus references:** M10-C104, M10-C148, M10-C149, M10-C183

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

## Low Findings

No separate Low production finding is asserted. Minor documentation and policy-clarity details are covered under their owning findings rather than inflated into additional defects.

## Test Gaps

4 registered. Each record below is source analysis or a defined proof/policy gap; target execution remains `NOT_RUN`.

### M10-AUDIT-25 — The M10 benchmark can accept no-op work and its hit fixtures are not qualified

**Severity:** TEST GAP

**Confidence:** High (source-supported; not executed)

**Category:** Benchmark validity

**Canonical requirement:** Current reference-Mac timing is valid only after positive matching/expansion/skill/file work and ambiguity controls are proven.

**Code location / source:** [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) — fixture construction, timed callbacks, output manifest; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M10.md) — historical implementation, review repairs, limitations; not fresh proof; [docs/v2/acceptance/M10/results.json](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/acceptance/M10/results.json) — historical September 22 execution record; not current measurements

**Current behavior:** The benchmark discards callback results and has no work-validity gate. Its snippets are placeholder snippets followed by long filler, and spoken digit words in file probes do not match the resolver's filename representation. The recorded environment is not a fresh audited-tree measurement.

**Failure mechanism:** A fast callback that returns unchanged input or unresolved files can look successful. The 24-word slot cap and explicit skill-command framing make nominal hit populations unreliable without assertions.

**Minimal reproduction:** First run each benchmark callback once through independent assertions: exact winning rule, actual snippet edit/output, exact skill emission, correct file and ambiguous file control. Then replace each unit with a no-op and require nonzero invalid-work exit before timing is accepted.

**Expected behavior:** Invalid work cannot produce a qualified latency result. Every timed sample/cohort declares work validity, population and the exact committed code/environment.

**Likely actual behavior / verification boundary:** Current source permits apparently good timings with no useful matched work. No current latency figure is claimed by this audit.

**Existing coverage:** Historical September 22 timing exists; no independent benchmark mutation gate appears in the inspected script.

**Why the oracle misses it:** Population construction is counted as evidence that work occurred, while outputs are ignored.

**Regression recommendation:** Positive and distractor populations, per-sample validity, at least style/snippet/skill/file no-op mutants, injected-delay timing witness and adversarial prefix cohorts.

**Narrow repair direction:** Repair benchmark fixtures/oracles first; then run isolated reference-Mac measurements for each component and combined contribution. Do not copy historical timings.

**Downstream impact:** M15 readiness and all M10 performance claims.

**Corpus references:** M10-C136, M10-C144, M10-C189, M10-C190, M10-C191, M10-C192, M10-C193, M10-C194, M10-C195, M10-C196, M10-C197, M10-C198, M10-C199, M10-C200

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-26 — Native Styles/Snippets input and hit-testing remain unqualified

**Severity:** TEST GAP

**Confidence:** High (source-supported; not executed)

**Category:** Native functional UI

**Canonical requirement:** M10 controls must actually accept typing and actions; this is functional qualification, not Quiet Editorial redesign.

**Code location / source:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) — make_hub service wiring, MainQueue, shell and M10 CRUD checks; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics

**Current behavior:** Both pane constructors create a root NSView with init() while giving its children frames based on the content bounds. The inspected selection path adds the pane without an explicit pane frame update. Programmatic construction/CRUD is not a mouse/keyboard hit-test.

**Failure mechanism:** Root/child geometry and responder traversal may prevent clicks or typed edits even when setStringValue_ and direct action calls work in tests. This is a concrete source lead, not a claimed observed native failure.

**Minimal reproduction:** Use actual AppKit/PyObjC and synthetic stores. Inspect root frame/bounds, hitTest at the center of each input, makeFirstResponder, then native text entry/Cmd+A/edit/tab and action clicks. Resize the real helper window and repeat.

**Expected behavior:** Every M10 input is reachable and receives text; popups/toggles/actions work. Record owned-window proof and distinguish automation from Daniel's manual destination trial.

**Likely actual behavior / verification boundary:** Runtime/native verification required. Do not label controls broken merely from this static geometry lead.

**Existing coverage:** test_hub_shell.py checks real service wiring, outer window geometry and programmatic actions, not complete owned-pane input qualification.

**Why the oracle misses it:** An outer window in bounds does not prove a child pane participates in hit-testing.

**Regression recommendation:** Dedicated native functional suite, positive text-entry witness and mutation removing pane sizing/responder repair.

**Narrow repair direction:** Repair pane sizing/responder/CRUD behavior only when reproduced. Preserve the existing shell and future redesign boundary.

**Downstream impact:** M09 Hub compatibility and M10 practical usability.

**Corpus references:** M10-C175, M10-C176

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-27 — Owning tests do not independently cover the required stateful seams and all live consumers

**Severity:** TEST GAP

**Confidence:** High (source-supported; not executed)

**Category:** Coverage / caller inventory

**Canonical requirement:** M10 requires real coordinator, current Hub services, stateful barriers and independent oracles; incomplete code search is not an exhaustive caller inventory.

**Code location / source:** [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests; [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) — synthetic manifests, refresh and workspace tests; [tests/v2/developer/test_developer_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_developer_resolution.py) — file ambiguity, listing and helper-level attachment/surface tests; [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) — make_hub service wiring, MainQueue, shell and M10 CRUD checks; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths

**Current behavior:** The core consumers and complete repository tree were inspected remotely. GitHub code search was not exhaustive, and the historical suites do not collectively prove all cache, mutation, finalization, preview and retry seams required by this audit.

**Failure mechanism:** Direct utility tests can bypass coordinator caches/finalization; standalone terminal text tests can bypass the current insertion guard; programmatic UI tests bypass input delivery.

**Minimal reproduction:** On the local pinned worktree, inventory every requested symbol with rg, map each production caller to a positive test, and run the supplied barrier/metamorphic/mutation plan.

**Expected behavior:** An explicit complete local caller map and per-case owner/oracle; positive populations for every no-action negative control.

**Likely actual behavior / verification boundary:** Coverage remains partial until local inventory and new tests run; this audit does not infer absence of additional consumers from a zero-result search.

**Existing coverage:** Real coordinator and current M09 MainQueue tests are genuine existing strengths; their reach is narrower than the full adversarial campaign.

**Why the oracle misses it:** Counting passing test files cannot prove a particular branch or boundary was reached.

**Regression recommendation:** Log barrier reached counts, actual service calls and independent effects; harness errors and unfired barriers are ERROR, never PASS or mutation kills.

**Narrow repair direction:** Extend owning tests and seam cases rather than broadly re-auditing previously accepted milestones.

**Downstream impact:** M05/M06/M08/M09/M11 compatibility and M15 evidence integrity.

**Corpus references:** M10-C023, M10-C032, M10-C033, M10-C035, M10-C037, M10-C080, M10-C081, M10-C101, M10-C108, M10-C109, M10-C110, M10-C132, M10-C137, M10-C139, M10-C143, M10-C150, M10-C151, M10-C152, M10-C153, M10-C154, M10-C155, M10-C156, M10-C157, M10-C158, M10-C159, M10-C160, M10-C161, M10-C162, M10-C164, M10-C165, M10-C166, M10-C185, M10-C186, M10-C187, M10-C188, M10-C210, M10-C211, M10-C215

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-28 — Generated output is distinguished at the producer, but AC05 needs a narrow end-to-end eligibility witness

**Severity:** TEST GAP

**Confidence:** High (source-supported; not executed)

**Category:** Evidence consumer seam

**Canonical requirement:** M10-AC05: snippet-expanded/profile-transformed words cannot be a verbatim speech reference without independent audio review.

**Code location / source:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering; [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) — real-coordinator M10 integration tests; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05

**Current behavior:** Raw and normalized artifacts are separate and snippet edits are typed. This source review did not demonstrate a deterministic path that exports generated text as reviewed acoustic truth, nor did it execute the complete eligibility witness.

**Failure mechanism:** Producer tags alone cannot prove that every later consumer preserves the distinction. Conversely, an unexecuted consumer probe is not grounds for a fabricated Critical finding.

**Minimal reproduction:** Create a synthetic audio job whose ASR words do not include a long snippet payload; inspect eligibility with no review, intended-writing-only review, and independent verbatim audio review. Include a transform-backed mode control.

**Expected behavior:** No ASR-supervised eligibility from automatic expansion, insertion, a clean-text correction or a preference alone; independently reviewed verbatim spans may qualify under existing contracts.

**Likely actual behavior / verification boundary:** Not executed. The producer boundary is substantially correct; the narrow export/eligibility seam remains a proof requirement, not a broad M14 audit.

**Existing coverage:** M10 EV-19 producer tests and inherited training contracts exist.

**Why the oracle misses it:** Exact expanded output and typed edits do not independently test task-specific eligibility after review.

**Regression recommendation:** One synthetic end-to-end seam test with current M14 APIs, no new learning/export design.

**Narrow repair direction:** Preserve producer lineage; fix only a demonstrated M10-owned omission or seam contract. Escalate unrelated M14 defects as leads.

**Downstream impact:** M14 training eligibility and M15 qualification.

**Corpus references:** M10-C165, M10-C177, M10-C179, M10-C184, M10-C220

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

## Design Concerns

4 registered. Each record below is source analysis or a defined proof/policy gap; target execution remains `NOT_RUN`.

### M10-AUDIT-29 — Equal-authority duplicate style rules resolve by ID without an explicit conflict UX

**Severity:** DESIGN CONCERN

**Confidence:** High on current behavior; policy decision open

**Category:** Duplicate authority policy

**Canonical requirement:** Resolution must be deterministic and explainable; the audit must not invent a uniqueness policy absent from current contracts.

**Code location / source:** [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) — StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) — precedence/defaults and transform binding controls

**Current behavior:** Enabled equal-scope matches are sorted by rule_id. Style storage admits duplicates. That is deterministic, not random or last-write-wins.

**Failure mechanism:** An older or lexically lower ID may beat a newly added rule of the same authority, including a duplicate created after an unknown-outcome retry.

**Minimal reproduction:** Two enabled global/category/app/workspace rules with opposite modes; reverse insertion order and IDs; inspect selected rule and any visible conflict explanation.

**Expected behavior:** Adjudicate whether to preserve documented ID tie-break with explicit conflict visibility, reject duplicates, or require a user-selected winner. Existing jobs remain frozen.

**Likely actual behavior / verification boundary:** ID tie-break applies. Absence of an intuitive newest-wins behavior is not by itself a code defect.

**Existing coverage:** Precedence tests establish deterministic winners but do not settle user-facing duplicate authority.

**Why the oracle misses it:** Testing determinism is necessary but insufficient for a policy decision about conflicting defaults.

**Regression recommendation:** Policy-versioned corpus labels; permutation metamorphic test under the chosen policy.

**Narrow repair direction:** Record one explicit decision before changing admission/resolution. Reconcile existing duplicates non-destructively.

**Downstream impact:** M10 UX and AUDIT-21 reconciliation.

**Corpus references:** M10-C010, M10-C011, M10-C012, M10-C013

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-30 — Arbitrary profile names are explicitly permitted metadata inside a nominally content-free envelope

**Severity:** DESIGN CONCERN

**Confidence:** High on explicit contract contradiction; policy open

**Category:** Privacy contract inconsistency

**Canonical requirement:** S29 privacy/content-free operational evidence versus the profiles contract's explicit profile_name field.

**Code location / source:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) — on_writing_profile, on_normalization_result, governed artifacts and envelope filtering; [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_SPEC.md) — S10, S12, S15, S17, S19, S29.4/S29.11, S30.1

**Current behavior:** on_writing_profile retains profile_name. It can be a user-configured phrase such as Synthetic NDA Proposal. The current M10 contract explicitly permits that identity field.

**Failure mechanism:** Calling an arbitrary user string content-free is misleading, but silently deleting the field as an undocumented leak would contradict the accepted local contract and downstream profile identity needs.

**Minimal reproduction:** Use a synthetic sensitive-looking profile name and a not-targeted transform fallback; inspect envelope, events, governed artifacts and export/redaction boundaries.

**Expected behavior:** Explicitly classify profile names as governed private metadata or replace them with opaque stable IDs plus a governed mapping. Define display/export/retention separately.

**Likely actual behavior / verification boundary:** The profile block can retain the arbitrary name by design. No raw skill path leak is alleged: SkillRegistry.to_json omits manifest_path.

**Existing coverage:** Current evidence tests permit profile_name; general content-free checks do not settle whether it is allowed private metadata.

**Why the oracle misses it:** A key allowlist does not make every value under an allowed key non-sensitive.

**Regression recommendation:** Policy-versioned redaction/retention tests with synthetic canaries, including derived reason strings.

**Narrow repair direction:** Adjudicate the classification and contract first; prefer opaque identifiers where identity suffices. Do not hash a secret and call it automatically safe.

**Downstream impact:** M10 explainability, M14 evidence/export and privacy.

**Corpus references:** M10-C025, M10-C163, M10-C180, M10-C181, M10-C182, M10-C183

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-31 — Text-only second normalization can chain snippets after provenance has been discarded

**Severity:** DESIGN CONCERN

**Confidence:** High on text-only ambiguity; product policy open

**Category:** Idempotence / generated intent

**Canonical requirement:** M04 repeated-normalization guarantee and M10 generated-text authority need one explicit composition policy.

**Code location / source:** [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/normalization.md) — literal/barrier protection, arbitration and M10-owned grammars

**Current behavior:** The engine applies one proposal pass. If snippet A expands to the trigger of B, an independent second normalize call on the output string can expand B because it has lost the original generated-span provenance.

**Failure mechanism:** A text-only API cannot distinguish identical spoken and generated trigger bytes without additional state. This is not evidence of recursive expansion inside the normal one-pass coordinator.

**Minimal reproduction:** A trigger alpha phrase → beta phrase; B trigger beta phrase → FINAL. Normalize alpha phrase once, then normalize the output under the same snapshot. Inspect the runtime call graph and retained provenance.

**Expected behavior:** Adjudicate provenance-aware repeat processing, a non-chaining configuration constraint, or an explicitly narrowed text-only idempotence claim. Do not prohibit legitimate speech of beta phrase by accident.

**Likely actual behavior / verification boundary:** Second-pass chaining is possible; the normal coordinator does not repeatedly normalize its result in the inspected path.

**Existing coverage:** M04 idempotence checks and positive snippet tests exist, but generated-trigger chaining is not independently pinned as a product policy.

**Why the oracle misses it:** Testing only literal payloads that are not other triggers misses the ambiguity.

**Regression recommendation:** Metamorphic second-pass tests plus a mutation that re-normalizes generated payloads in the real pipeline.

**Narrow repair direction:** Resolve the API/contract boundary before altering expansion semantics; carry generated-span provenance when repeat processing is supported.

**Downstream impact:** M04 idempotence, M10 snippet intent, retry/transform boundaries.

**Corpus references:** M10-C084

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

### M10-AUDIT-32 — Defaults, one-shot consumption and placeholder extent need preserved explicit policy labels

**Severity:** DESIGN CONCERN

**Confidence:** High on documented behavior; changes require decision

**Category:** Policy clarity

**Canonical requirement:** Follow current defaults/slot rules instead of substituting intuitive but incompatible expectations.

**Code location / source:** [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) — StyleRule, derive_category, _rule_matches, resolve, _finish; [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) — grammar_snippets, grammar_file_tags, slot/reference limits; [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) — M10 behavior, defaults, slots, freeze, evidence and M06 amendment; [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) — precedence/defaults and transform binding controls

**Current behavior:** A categorized destination without a category rule receives built-in Clean before a global rule. An override selects a mode with default policy rather than transparently inheriting every destination-rule field. Cancelled/short captures normally consume the capture-bound override. Slots use a maximal bounded word run, missing values become empty and surplus values are folded according to the documented convention.

**Failure mechanism:** Tests can incorrectly accuse these intentional behaviors of defects, or a repair can silently change them. Hard delimiter crossing is separately a real defect in AUDIT-14/15.

**Minimal reproduction:** Use a global Raw rule with a known category but no category rule; set a one-shot mode over a destination technical-number rule; cancel the admitted first capture; exercise missing/surplus/24/25-word slots.

**Expected behavior:** Preserve current explicit decisions unless a versioned product adjudication changes them. Any changed mode-only, global-default or slot-end policy must be described in UI and corpus.

**Likely actual behavior / verification boundary:** The current documented conventions apply; not all are what a user might infer from the abbreviated precedence chain.

**Existing coverage:** Style default and slot tests already encode several of these behaviors.

**Why the oracle misses it:** Replacing the oracle with an intuitive expectation would manufacture a regression rather than expose one.

**Regression recommendation:** Positive preservation cases and separate policy-dependent cases, never a fabricated universal expected output.

**Narrow repair direction:** Document the distinctions and adjudicate only genuine ambiguity. Keep cancellation ownership separate from AUDIT-13 failure loss.

**Downstream impact:** M03 lifecycle, M04/M10 formatting, M11 mode selection.

**Corpus references:** M10-C001, M10-C002, M10-C003, M10-C004, M10-C005, M10-C007, M10-C008, M10-C029, M10-C030, M10-C034, M10-C042, M10-C085, M10-C086, M10-C087, M10-C089, M10-C090, M10-C091, M10-C092, M10-C093, M10-C094, M10-C185, M10-C188, M10-C207, M10-C215

**Execution status:** NOT_RUN — no local reproduction or native execution in this audit.

## Areas Verified Strong

“Verified” here means directly supported by current committed source and inspected assertions, not rerun tests.

The two historical M10 Critical repairs are present. Healthy per-job style/snippet/transform snapshots use captured records rather than constantly reading the store. Successful final policy construction preserves manifest plus dictionary skills. Scope authority uses M06's permitted origin instead of granting a title heuristic site authority. Raw normally bypasses normalization, snippets, file tags, cleanup and transform application. Literal/quote protection and same-span ambiguity handling are real. Skill discovery does not execute bodies or scan home by fallback. File tags read names rather than file contents; stable directory symlinks are not descended during listing. Surface certification sets remain empty and the current M08 guard safely downgrades unsafe terminal payloads. M11 has genuine positive and opt-out coordinator tests. Hub actions are rendered-ID bound. Preview is not intentionally usage or training. Explicit Retry has a documented fresh-unscoped provenance contract.

These controls are regression constraints on remediation, not reasons to waive the identified composition failures. [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) — _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths; [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) — _BARRIER_EXEMPT, arbitration, normalization execution; [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) — Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans; [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) — manifest/frontmatter parsing, discovery, SkillRegistry; [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) — list_workspace_files, FileTagResolver.resolve, attachment_plan; [localflow/v2/developer/surfaces.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/surfaces.py) — live compatibility table and certification sets; [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/insertion/service.py) — CERTIFIED_BRACKETED_SURFACES, _TERMINAL_UNSAFE, _transaction, _terminal_hazard; [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) — initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh; [tests/v2/transforms/test_transform_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/transforms/test_transform_pipeline.py) — positive auto-apply, opt-out, review fallback and retained Clean controls; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults.

## Adversarial Corpus Summary

`LocalFlow_M10_Adversarial_Corpus.json` contains **220 proposed cases**, including **20 stateful integration cases**, plus **12 metamorphic relations** and **26 mutation definitions**. All status fields remain **`NOT_RUN`** and all observed-result fields are null. The stateful cases are included in the 220 case count, not an extra 20 executed tests.

The corpus uses structured fixture setup, actions, independent assertions, related finding IDs, execution class, policy-adjudication fields and positive-control requirements. It is deliberately a declarative test specification, not an unverified harness pretending to execute the app. A local adapter must bind cases to current APIs and record any binding/policy change separately. The corpus itself remains immutable.

| Category | Cases |
|---|---:|
| `allow_rewrite` | 4 |
| `benchmark_validity` | 12 |
| `duplicate_rules` | 4 |
| `evidence_privacy` | 8 |
| `file_listing` | 5 |
| `file_tag_resolution` | 11 |
| `hub_crud` | 11 |
| `m11_auto_apply` | 7 |
| `manifest_cache` | 4 |
| `manifest_parsing` | 16 |
| `number_policy` | 5 |
| `per_job_override` | 9 |
| `placeholders` | 13 |
| `profile_precedence` | 9 |
| `raw_mode` | 3 |
| `retry` | 4 |
| `rich_snippets` | 2 |
| `scope_canonicalization` | 12 |
| `snippet_skill_collisions` | 6 |
| `snippet_triggers` | 16 |
| `stateful_integration` | 20 |
| `store_concurrency` | 26 |
| `surface_safety` | 9 |
| `workspace_switch` | 4 |

All 23 requested categories are represented; `stateful_integration` is an additional cross-cutting category. Synthetic paths are placeholders beneath a fresh temporary root, never permission to read Daniel's real home/workspaces. Native/benchmark cases have explicit execution classes. Test errors, refused permissions and unfired barriers cannot be counted as passes or mutation kills.

## Stateful / Metamorphic / Mutation Plan

Use barrier-controlled schedules and independent observations of the actual coordinator/writer/native target. Do not simulate races with sleep and then conclude they were exercised. Every schedule records the base SHA, mutation/fixture identity, reached barriers, raw rows or policy tuple, effect counts and typed result.

| Stateful ID / corpus case | Required schedule |
|---|---|
| `M10-S001` / `M10-C201` | style edit while A in flight |
| `M10-S002` / `M10-C202` | snippet edit while A in flight |
| `M10-S003` / `M10-C203` | global manifest edit while A in flight |
| `M10-S004` / `M10-C204` | two concurrent style patches |
| `M10-S005` / `M10-C205` | style update versus deletion |
| `M10-S006` / `M10-C206` | two concurrent snippet patches |
| `M10-S007` / `M10-C207` | cancelled first capture consumes only its assigned override |
| `M10-S008` / `M10-C208` | workspace A to B |
| `M10-S009` / `M10-C209` | profile A to B vocabulary scope |
| `M10-S010` / `M10-C210` | M06 successful scope upgrade retains manifest skills |
| `M10-S011` / `M10-C211` | M11 enable/disable between jobs |
| `M10-S012` / `M10-C212` | Hub rendered row reorders before Update |
| `M10-S013` / `M10-C213` | admitted Add times out then commits then retries |
| `M10-S014` / `M10-C214` | file rename/list race |
| `M10-S015` / `M10-C215` | retry old audio in different current workspace |
| `M10-S016` / `M10-C216` | collision preview versus runtime under same snapshot |
| `M10-S017` / `M10-C217` | failure after registry selection before policy commit |
| `M10-S018` / `M10-C218` | override error after consume and before publication |
| `M10-S019` / `M10-C219` | snippet current-row deletion after capture |
| `M10-S020` / `M10-C220` | profile/registry evidence write failure |

The 12 metamorphic relations cover narrower-scope replacement, disabled authority, freezing, literal protection, ambiguity, filesystem authority reduction, preview parity, candidate permutation, strict Boolean admission, retained evidence after config deletion, benchmark no-op rejection and terminal separator downgrades.

The 26 mutations include every mutation requested in the audit prompt, plus cache-only-parent-mtime, symlink following, half-tuple publication, override-loss faults, timeout mislabeling, stale form writes, no-work timing, export aliasing and the native pane sizing lead. A mutant counts as killed only when an independent semantic assertion fails after the intended altered branch was reached. Compile/import errors, unrelated failures or unavailable native permissions are not kills. Equivalent/surviving mutants need an explicit adjudication and proof, not a silent denominator reduction.

Keep fail-first and final evidence separately. Reviewer-confirmed defects must fail the frozen first-pass production tree and pass final production. Cases used to tune repairs are development/regression evidence, not blind holdouts, consistent with S29.11. [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_SPEC.md) — S10, S12, S15, S17, S19, S29.4/S29.11, S30.1; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05; [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) — final a304d48; rendered rows, timeouts and MainQueue.

## Downstream Impact

| Boundary | Preserve / qualify |
|---|---|
| M04 | Core literal/barrier/arbitration and replay lineage; fix only M10-owned grammars/composition. |
| M05 | Shared canonical comparisons, writer-current validation, actual-only hit accounting and frozen profile vocabulary. |
| M06 | Authoritative origin, workspace identity versus locator, bounded context and complete rollback disposition. |
| M08 | Current effect-boundary ownership, full terminal separator guard, empty certification sets and no synthetic Return. |
| M09 | Actual MainQueue, rendered stable IDs, deleted-editor invalidation and honest unknown writer outcomes. |
| M11 | Frozen enabled definition, explicit typed opt-in, target-profile match, Clean preservation and truthful fallback. No model-quality redesign. |
| M14 | Exact generated/template provenance, governed retention/deletion and narrow ASR-eligibility witness. No broader learning implementation. |
| M15 | No qualification on invalid/no-op benchmarks or inherited test counts; current reference-Mac evidence required later. |

These are compatibility obligations, not permission to start or re-audit those milestones. [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/normalization.md) — literal/barrier protection, arbitration and M10-owned grammars; [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) — canonical scope comparisons and writer-authoritative mutation discipline; [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) — scope_site_origin, widening disposition, identity versus locator; [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/insertion.md) — current M08 terminal and effect-boundary contract; [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) — post-M09 rendered identity, editor binding and unknown-outcome semantics; [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/transforms.md) — enabled frozen definitions, opt-in and honest fallback; [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) — content-free versus governed artifacts, profile block, retry defaults; [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) — P01–P04; M10 tasks and AC01–AC05.

## Recommended Repair Order

1. **Reproduce and freeze the base.** Inventory callers/environment; retain original corpus and historical controls. Establish native pane functionality early so a broken form does not hide later tests. Do not change policy while building the reproductions.
2. **Close authority/admission failures.** AUDIT-01, 06–09: configured-root reads, strict configuration/Boolean types, anchored manifest schema and safe error boundaries.
3. **Stabilize mutation and capture ownership.** AUDIT-03–05, 10–13, 17: writer-current valid rows, registry cache/freeze, coherent finalization and one-shot ownership.
4. **Repair parsing/resolution and truthful action results.** AUDIT-02, 14–16, 18–19, 24: canonical scopes, delimiter-owned snippets/tags, real ambiguity and preview/runtime agreement.
5. **Finish UI/evidence correctness.** AUDIT-20–23, 26, 28: revision-bound editors, unknown outcome reconciliation, bounded work and applied-definition provenance. Adjudicate AUDIT-29–32 explicitly rather than silently changing policy.
6. **Qualify the result.** Independent fail-first regressions, complete corpus/stateful/metamorphic/mutation evidence, current compatibility, safe owned-native checks, valid isolated benchmark, fresh read-only reviewer, final rerun, contracts/runbook/orchestration and dedicated branch push.

Do not bundle a Quiet Editorial redesign with these changes. Daniel, not the agent, merges the accepted branch and performs the genuinely manual trial.

## M10 Readiness Verdict

### C. Significant profile/developer-workflow weaknesses

M10 is not ready to be waved through as an already-qualified prerequisite on the strength of September 22 acceptance. The source establishes material configuration/authority, freeze/composition, parser/resolver and outcome defects, plus a benchmark that does not validate its work. Those defects are narrow enough to repair within M10 and its owned seams; they do not justify replacing the architecture or reopening all preceding milestones.

This is not verdict D: enough current source and contract evidence was available to identify actionable failures and define deterministic reproductions. It is not verdict A or B merely because the happy path and historical fixes exist: too many independent high-priority authority and state paths require local repair and proof.

**Audit state:** `READ_ONLY_AUDIT_COMPLETE — LOCAL_REPRODUCTION_AND_REMEDIATION_REQUIRED`.

**Runtime evidence state:** `NOT_RUN`. **Native/manual verification:** `NOT_RUN`. **Current benchmark qualification:** `NOT_RUN / WORK_VALIDITY_REPAIR_REQUIRED`.

The companion local handoff defines the authorized remediation procedure and the exact conditions for eventually reporting `LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION`. This audit does not grant that state, mark Daniel's checks complete or authorize a merge to main.

## Appendix — Immutable Source Register

All production, test and contract anchors below are pinned to `9344fa14e2d013b5c9befef88663fcd03d3c6ef1`. Function/section names are the code locations; no connector wrapper line number is presented as a repository source line. Entry-point documents and prerequisite addenda provide context; historical run claims remain attributed to their recorded runs. The tiny `localflow/v2/developer/__init__.py` was also inspected and is an import surface, not an additional execution authority.

| Key | Pinned source | Inspected relevance |
|---|---|---|
| `profiles` | [localflow/v2/profiles.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles.py) | StyleRule, derive_category, _rule_matches, resolve, _finish |
| `style_store` | [localflow/v2/profiles_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/profiles_store.py) | StyleRuleStore.add_rule/update_rule/delete_rule/set_enabled |
| `snippets` | [localflow/v2/snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets.py) | Snippet, SnippetSnapshot, preview_conflicts, protected_output_spans |
| `snippet_store` | [localflow/v2/snippets_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/snippets_store.py) | SnippetStore mutation methods and row reconstruction |
| `skills` | [localflow/v2/developer/skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/skills.py) | manifest/frontmatter parsing, discovery, SkillRegistry |
| `files` | [localflow/v2/developer/file_tags.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/file_tags.py) | list_workspace_files, FileTagResolver.resolve, attachment_plan |
| `surfaces` | [localflow/v2/developer/surfaces.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/developer/surfaces.py) | live compatibility table and certification sets |
| `app` | [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/app.py) | _m10_skill_records, _m10_freeze, _m10_finalize_upgrade, _finalized_policy, _finalize_job_context, worker, hub* and retry paths |
| `config` | [localflow/config.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/config.py) | M10 configuration defaults/merge; contrast with context_policy |
| `store` | [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/store.py) | schema v6, Store.submit/_submit and writer transactions |
| `engine` | [localflow/v2/normalize/engine.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/engine.py) | _BARRIER_EXEMPT, arbitration, normalization execution |
| `syntax` | [localflow/v2/normalize/syntax.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/normalize/syntax.py) | grammar_snippets, grammar_file_tags, slot/reference limits |
| `hub` | [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/hub.py) | initWithSpec_, _render_rows, Styles/Snippets pane constructors, actions and refresh |
| `state` | [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/ui/state.py) | Styles/Snippets service loading and selection state |
| `training` | [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/training.py) | on_writing_profile, on_normalization_result, governed artifacts and envelope filtering |
| `tf_defs` | [localflow/v2/transforms/definitions.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms/definitions.py) | TransformDefinition, TransformSnapshot.auto_apply_decision/for_mode |
| `tf_store` | [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/transforms_store.py) | update_transform Boolean admission; no general M11 store re-audit |
| `insertion` | [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/localflow/v2/insertion/service.py) | CERTIFIED_BRACKETED_SURFACES, _TERMINAL_UNSAFE, _transaction, _terminal_hazard |
| `bench` | [scripts/v2/benchmark_m10.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/scripts/v2/benchmark_m10.py) | fixture construction, timed callbacks, output manifest |
| `t_profiles` | [tests/v2/profiles/test_style_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_style_resolution.py) | precedence/defaults and transform binding controls |
| `t_snippets` | [tests/v2/profiles/test_snippets.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_snippets.py) | expansion, collision runtime/preview, store and freeze coverage |
| `t_pipeline` | [tests/v2/profiles/test_profiles_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/profiles/test_profiles_pipeline.py) | real-coordinator M10 integration tests |
| `t_skills` | [tests/v2/developer/test_skills.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_skills.py) | synthetic manifests, refresh and workspace tests |
| `t_files` | [tests/v2/developer/test_developer_resolution.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/developer/test_developer_resolution.py) | file ambiguity, listing and helper-level attachment/surface tests |
| `t_hub` | [tests/v2/ui/test_hub_shell.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/ui/test_hub_shell.py) | make_hub service wiring, MainQueue, shell and M10 CRUD checks |
| `t_tf` | [tests/v2/transforms/test_transform_pipeline.py](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/tests/v2/transforms/test_transform_pipeline.py) | positive auto-apply, opt-out, review fallback and retained Clean controls |
| `c_profiles` | [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/profiles.md) | M10 behavior, defaults, slots, freeze, evidence and M06 amendment |
| `c_vocab` | [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/vocabulary.md) | canonical scope comparisons and writer-authoritative mutation discipline |
| `c_context` | [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/context.md) | scope_site_origin, widening disposition, identity versus locator |
| `c_hub` | [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/hub.md) | post-M09 rendered identity, editor binding and unknown-outcome semantics |
| `c_store` | [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/store.md) | single-writer atomic operations and timeout semantics |
| `c_norm` | [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/normalization.md) | literal/barrier protection, arbitration and M10-owned grammars |
| `c_training` | [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/training_evidence.md) | content-free versus governed artifacts, profile block, retry defaults |
| `c_tf` | [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/transforms.md) | enabled frozen definitions, opt-in and honest fallback |
| `c_insertion` | [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/insertion.md) | current M08 terminal and effect-boundary contract |
| `c_artifacts` | [docs/v2/contracts/artifacts.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/artifacts.md) | retained exact stage inputs, revision lineage and deletion |
| `spec` | [docs/v2/LOCALFLOW_V2_SPEC.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_SPEC.md) | S10, S12, S15, S17, S19, S29.4/S29.11, S30.1 |
| `milestones` | [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_MILESTONES.md) | P01–P04; M10 tasks and AC01–AC05 |
| `evaluation` | [docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md) | EV-12/EV-19 and developer-surface evaluation requirements |
| `h10` | [docs/v2/handoffs/M10.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M10.md) | historical implementation, review repairs, limitations; not fresh proof |
| `r10` | [docs/v2/acceptance/M10/results.json](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/acceptance/M10/results.json) | historical September 22 execution record; not current measurements |
| `h04` | [docs/v2/handoffs/M04.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M04.md) | normalization remediation addendum |
| `h05` | [docs/v2/handoffs/M05.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M05.md) | scope, concurrency and evidence remediation addendum |
| `h06` | [docs/v2/handoffs/M06.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M06.md) | local remediation; R3 rollback; authority decisions |
| `h07` | [docs/v2/handoffs/M07.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M07.md) | cleanup remediation and generated-span preservation |
| `h08` | [docs/v2/handoffs/M08.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M08.md) | local effect-boundary and terminal remediation |
| `h09` | [docs/v2/handoffs/M09.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M09.md) | final a304d48; rendered rows, timeouts and MainQueue |
| `h11` | [docs/v2/handoffs/M11.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/handoffs/M11.md) | local replay 1545de9, final production 9a049b3; model-quality residuals |
| `readme` | [README.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/README.md) | repository entry point |
| `start` | [docs/v2/START_HERE.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/START_HERE.md) | standalone test runners and current orientation |
| `status` | [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/STATUS.json) | historical implementation status, distinct from audit campaign |
| `orchestration` | [ORCHESTRATION.html](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/ORCHESTRATION.html) | campaign and historical evidence overview |
| `index` | [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/9344fa14e2d013b5c9befef88663fcd03d3c6ef1/docs/v2/contracts/INDEX.md) | contract ownership and cross-milestone seams |

**Coverage limitation:** remote read/search is not a substitute for a complete local `rg` consumer inventory. The full M14 exporter and every historical test file were not broadly audited; only the M10 producer/consumer seams described above are claimed. All target-code execution remains delegated to the authorized local remediation session.
