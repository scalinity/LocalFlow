# LocalFlow M01–M14 Interface Matrix

**Audited commit:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Date:** 2026-09-28  
**Target execution:** `NOT_RUN`  
**Scope:** Source-backed interface map plus explicit local proof obligations; not an executed integration certificate.

There are **40 important producer→consumer edges** below. Owning suites are discovery/binding anchors, not a claim that every current executable test reaches the exact interface. The local remediation must inventory callers and bind test nodes before changing production. A contract assertion is not the same evidence class as a static code observation or a target test result.

## Central interface contract

A downstream action should carry the source's logical job/capture identity, attempt, artifact role/digest, revision, effective mode, destination proof where needed, deletion/retention authority and operation identity. It must not replace those with a row index, current dictionary spelling, text equality or a generic timeout==failure interpretation.

An explicit independent note or released export is a distinct authority object, not permission to revive a deleted source job. Historical attempts and split versions remain historical; they do not become current output or newly blind evidence by selection.

## Milestone roles

| Milestone | Role | Authority |
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


## IF-001 — M01 → M02–M14: baseline/fixture manifest

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | baseline/fixture manifest |
| Frozen fields | source/config/model/fixture hashes |
| Mutable fields | new evidence records |
| Expected revision / identity | exact SHA and fixture digest |
| Deletion / expiry behavior | private snapshots stay outside commits |
| Timeout / unknown behavior | no target execution inferred |
| Owning tests / binding anchors | EV-01; M01 registry validation (bind current tracked nodes locally) |
| Cross-milestone risk | registry mapping is not production branch proof (12) |
| Evidence | [G09] [G06] |


## IF-002 — M03 → M02: capture job + journal

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | capture job + journal |
| Frozen fields | job/family/capture instant/sample layout |
| Mutable fields | attempt/state |
| Expected revision / identity | job_id + original capture provenance |
| Deletion / expiry behavior | job barrier revokes queued work and managed copies |
| Timeout / unknown behavior | late worker result cannot reopen terminal state |
| Owning tests / binding anchors | tests/v2/lifecycle/; contracts/jobs.md |
| Cross-milestone risk | full current race execution pending |
| Evidence | [H03] [S01] [C01] |


## IF-003 — M02/M03 → M03 ASR worker: audio request

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | audio request |
| Frozen fields | owned journal/audio identity and capture gaps |
| Mutable fields | worker generation/request state |
| Expected revision / identity | job + attempt + request/generation |
| Deletion / expiry behavior | deleted job loses request/publication authority |
| Timeout / unknown behavior | timeout retires/reconciles worker per supervisor contract |
| Owning tests / binding anchors | tests/v2/lifecycle/ |
| Cross-milestone risk | no native/model run in audit |
| Evidence | [H03] |


## IF-004 — M05 → M04/M07: vocabulary snapshot

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | vocabulary snapshot |
| Frozen fields | entry set, approval, scope, revisions |
| Mutable fields | registry changes only for later jobs |
| Expected revision / identity | snapshot + applied rule revision |
| Deletion / expiry behavior | revocation affects future snapshot; source evidence governed |
| Timeout / unknown behavior | optional snapshot failure narrows scope |
| Owning tests / binding anchors | tests/v2/vocabulary/ |
| Cross-milestone risk | historical profile canonical mapping weak (03) |
| Evidence | [C04] [H05] |


## IF-005 — M06 → M05/M10: scope projection

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | scope projection |
| Frozen fields | target + captured entry/rule tuple |
| Mutable fields | one allowed finalized projection |
| Expected revision / identity | handle + pre-decode snapshot + authoritative origin |
| Deletion / expiry behavior | handle revocation stops further publication |
| Timeout / unknown behavior | 75 ms shared release budget; narrow fallback |
| Owning tests / binding anchors | tests/v2/context/; tests/v2/profiles/ |
| Cross-milestone risk | workspace-name equality is intentional, not filesystem authority |
| Evidence | [C03] [C04] |


## IF-006 — M06 → M07: cleanup context

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | cleanup context |
| Frozen fields | normalized protected spans, bounded frozen vocabulary, category |
| Mutable fields | none during job |
| Expected revision / identity | snapshot/tuple identity |
| Deletion / expiry behavior | no unrelated live context reread |
| Timeout / unknown behavior | missing context degrades to allowed narrow fields |
| Owning tests / binding anchors | tests/v2/context/; tests/v2/fidelity/ |
| Cross-milestone risk | no arbitrary nearby-text model feed established |
| Evidence | [C03] [H07] |


## IF-007 — M06/M10 → M11: transform mode/definition

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | transform mode/definition |
| Frozen fields | definition/task/profile/locale and job tuple |
| Mutable fields | later registry revisions |
| Expected revision / identity | transform revision + task key |
| Deletion / expiry behavior | source deletion revokes job-owned effects |
| Timeout / unknown behavior | failed generation keeps source/Clean |
| Owning tests / binding anchors | tests/v2/transforms/ |
| Cross-milestone risk | mode-specific gates; real-model gate open |
| Evidence | [C04] [C05] [H11] |


## IF-008 — M10 → M04/M07: snippet expansion

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | snippet expansion |
| Frozen fields | stored body, slots, generated span coordinates |
| Mutable fields | future snippet revision/hit counter |
| Expected revision / identity | snippet ID/revision + output-coordinate ledger |
| Deletion / expiry behavior | retained generated content follows job authority |
| Timeout / unknown behavior | optional failure cannot silently partly freeze tuple |
| Owning tests / binding anchors | tests/v2/profiles/ (bind actual snippet test nodes locally) |
| Cross-milestone risk | normalization is once per job, not text-only repeat API |
| Evidence | [C04] |


## IF-009 — M10 → M04/M11: skill/file records

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | skill/file records |
| Frozen fields | configured root authority, manifest/listing revision |
| Mutable fields | future filesystem state |
| Expected revision / identity | frozen manifest/listing + exact resolved name |
| Deletion / expiry behavior | no downstream unconfined re-resolution |
| Timeout / unknown behavior | partial listing cannot prove bare-name uniqueness |
| Owning tests / binding anchors | tests/v2/developer/ |
| Cross-milestone risk | exhaustive downstream caller scan pending (15) |
| Evidence | [C04] [H10] |


## IF-010 — M04 → M07: normalization result

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | normalization result |
| Frozen fields | raw→normalized ledger and protected spans |
| Mutable fields | none |
| Expected revision / identity | source/destination coordinate units + ledger revision |
| Deletion / expiry behavior | source artifacts governed |
| Timeout / unknown behavior | unsafe normalization stays source/explicit fallback |
| Owning tests / binding anchors | tests/v2/normalization/; tests/v2/fidelity/ |
| Cross-milestone risk | protect quotes, numeric signs, paths, snippets |
| Evidence | [H04] [C03] [C04] |


## IF-011 — M07 → M11/M08: Clean applied output

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Clean applied output |
| Frozen fields | actual model input/proposal/fallback choice |
| Mutable fields | optional later transform |
| Expected revision / identity | applied artifact + attempt + cleanup path |
| Deletion / expiry behavior | deleted source cannot publish job-owned content |
| Timeout / unknown behavior | fallback is explicit, not successful proposal |
| Owning tests / binding anchors | tests/v2/fidelity/; tests/v2/transforms/ |
| Cross-milestone risk | model quality not proven statically |
| Evidence | [H07] [C05] |


## IF-012 — M11 → M08: validated auto-transform final

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | validated auto-transform final |
| Frozen fields | task, source, output and gate result |
| Mutable fields | insertion transaction outcome |
| Expected revision / identity | same frozen job/target + applied path |
| Deletion / expiry behavior | job deletion revokes insertion |
| Timeout / unknown behavior | needs_review/fallback inserts Clean, not proposal |
| Owning tests / binding anchors | tests/v2/transforms/test_transform_pipeline.py |
| Cross-milestone risk | no human acceptance from auto-apply |
| Evidence | [C05] |


## IF-013 — M06 → M08: target lease

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | target lease |
| Frozen fields | PID/bundle/window/field/selection/region proof |
| Mutable fields | host state at dispatch/readback |
| Expected revision / identity | revalidation against captured destination |
| Deletion / expiry behavior | revocation prevents late insertion/undo |
| Timeout / unknown behavior | uncertainty is saved/unverified, not confirmation |
| Owning tests / binding anchors | tests/v2/insertion/ |
| Cross-milestone risk | native host compatibility pending |
| Evidence | [C06] [C03] |


## IF-014 — M08 → M09/M13: InsertionResult

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | InsertionResult |
| Frozen fields | transaction/job/target identity |
| Mutable fields | settled disposition |
| Expected revision / identity | confirmed vs posted_unverified vs saved/failed |
| Deletion / expiry behavior | deleted jobs invalidate actions; usage independent |
| Timeout / unknown behavior | posted event is not confirmed visible text |
| Owning tests / binding anchors | tests/v2/insertion/; tests/v2/analytics/ |
| Cross-milestone risk | terminal translation must remain explicit |
| Evidence | [C02] [C06] |


## IF-015 — M08 → M14: certified edit observation

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | certified edit observation |
| Frozen fields | owned inserted region, original job/attempt |
| Mutable fields | observation stop reason/edit result |
| Expected revision / identity | exact attributable region and observation ID |
| Deletion / expiry behavior | job/source deletion closes and purges governed evidence |
| Timeout / unknown behavior | lost ownership ends observation, never broad diff |
| Owning tests / binding anchors | tests/v2/insertion/ (bind actual attribution test nodes locally); tests/v2/personalization/ |
| Cross-milestone risk | no-edit/confirmed paste is not gold |
| Evidence | [C06] [H14] |


## IF-016 — M03 → M09: retry result and stage artifacts

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | retry result and stage artifacts |
| Frozen fields | same capture/job; new attempt |
| Mutable fields | terminal row and manifest publication |
| Expected revision / identity | current job attempt + artifact stage |
| Deletion / expiry behavior | old result cannot revive deleted job |
| Timeout / unknown behavior | admitted retry must reconcile before repeat |
| Owning tests / binding anchors | tests/v2/ui/ (bind actual History test nodes locally); lifecycle suites |
| Cross-milestone risk | old training manifest can shadow collection-off retry (01) |
| Evidence | [S02] [S03] |


## IF-017 — M09 → M03: History Retry command

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | History Retry command |
| Frozen fields | rendered job/recoverable identity |
| Mutable fields | admission/current recovery claim |
| Expected revision / identity | selected stable job and revision/state |
| Deletion / expiry behavior | deleted/unavailable audio refuses |
| Timeout / unknown behavior | unknown admission cannot trigger blind duplicate retry |
| Owning tests / binding anchors | tests/v2/ui/; lifecycle suites |
| Cross-milestone risk | full caller inventory pending (13) |
| Evidence | [C07] [S01] |


## IF-018 — M09 → M08: History Copy/Paste Again

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | History Copy/Paste Again |
| Frozen fields | rendered current final artifact |
| Mutable fields | new explicit paste target/transaction |
| Expected revision / identity | job + attempt + artifact/hash + action |
| Deletion / expiry behavior | revoked source cannot repaste |
| Timeout / unknown behavior | no transaction means no repaste fact |
| Owning tests / binding anchors | tests/v2/ui/; tests/v2/insertion/ |
| Cross-milestone risk | depends on final resolver (01) |
| Evidence | [C07] [C02] |


## IF-019 — M03 Recovery → M08: Copy Last Raw

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Copy Last Raw |
| Frozen fields | failed-job cached raw |
| Mutable fields | pasteboard generation |
| Expected revision / identity | internal guarded copy admission |
| Deletion / expiry behavior | deleted cache must refuse |
| Timeout / unknown behavior | pending clipboard ownership must defer/refuse |
| Owning tests / binding anchors | tests/v2/insertion/ |
| Cross-milestone risk | direct legacy copy bypass (04) |
| Evidence | [S01] [S13] [C06] |


## IF-020 — M09 → M12: Save/Move to Scratchpad

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Save/Move to Scratchpad |
| Frozen fields | rendered final text identity |
| Mutable fields | new independent note revision |
| Expected revision / identity | source job/attempt/artifact to note operation |
| Deletion / expiry behavior | Move may delete original only after durable note copy; independent note retained |
| Timeout / unknown behavior | unknown receipt must not duplicate note effect |
| Owning tests / binding anchors | tests/v2/notes/; tests/v2/ui/ |
| Cross-milestone risk | current-final selection dependency (01) |
| Evidence | [C07] [H12] |


## IF-021 — M09 → M14: Teach correction

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Teach correction |
| Frozen fields | rendered source artifact/attempt/span |
| Mutable fields | candidate status |
| Expected revision / identity | expected artifact/hash; transformed final refuses |
| Deletion / expiry behavior | source deletion stales candidate |
| Timeout / unknown behavior | repeat-sensitive operation ID must survive timeout |
| Owning tests / binding anchors | tests/v2/personalization/test_learning.py |
| Cross-milestone risk | transformed Teach guard is intentional and preserved |
| Evidence | [S06] [C07] [H14] |


## IF-022 — M03/M11 → M12: note-bound delivery

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | note-bound delivery |
| Frozen fields | note ID/revision/region captured at start |
| Mutable fields | receipt/committed revision |
| Expected revision / identity | captured note + codepoint/UTF-16 mapping |
| Deletion / expiry behavior | deleted note refuses delivery |
| Timeout / unknown behavior | confirmed only after committed revision receipt |
| Owning tests / binding anchors | tests/v2/notes/ |
| Cross-milestone risk | separate internal delivery, not AX confirmation |
| Evidence | [H12] [C02] [C05] |


## IF-023 — M12 → M14: dictated-edit attribution

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | dictated-edit attribution |
| Frozen fields | per-dictation origin spans and source job |
| Mutable fields | later note revisions |
| Expected revision / identity | canonical M12 attribution result, not coarse note diff |
| Deletion / expiry behavior | note deletion closes linked evidence and transform copies |
| Timeout / unknown behavior | miner rechecks liveness after wait |
| Owning tests / binding anchors | tests/v2/notes/; tests/v2/personalization/ |
| Cross-milestone risk | mixed typed/dictated/transform regions require multihop test |
| Evidence | [S06] [H12] [H14] |


## IF-024 — M12 → M13: note dictation terminal receipt

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | note dictation terminal receipt |
| Frozen fields | original capture/time/job |
| Mutable fields | one settled usage fact |
| Expected revision / identity | job uniqueness + note commit receipt |
| Deletion / expiry behavior | usage deletion independent from note deletion |
| Timeout / unknown behavior | unknown note write is not yet confirmed |
| Owning tests / binding anchors | tests/v2/analytics/; tests/v2/notes/ |
| Cross-milestone risk | autosave never adds dictation words |
| Evidence | [C02] [H12] |


## IF-025 — M03 → M13: terminal usage fact

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | terminal usage fact |
| Frozen fields | original capture instant/zone/app |
| Mutable fields | replacement attempt/outcome/stage metrics |
| Expected revision / identity | one dictation row per job |
| Deletion / expiry behavior | content deletion leaves allowed usage |
| Timeout / unknown behavior | retry completion replaces, never accumulates |
| Owning tests / binding anchors | tests/v2/analytics/ |
| Cross-milestone risk | profile does not inherit this unique index (02) |
| Evidence | [C02] |


## IF-026 — M11/M08 → M13: explicit activity fact

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | explicit activity fact |
| Frozen fields | completed generation or executed repaste ID |
| Mutable fields | fact publication |
| Expected revision / identity | one activity per actual operation |
| Deletion / expiry behavior | job-linked repastes deleted with job usage action |
| Timeout / unknown behavior | refusal/no transaction records nothing |
| Owning tests / binding anchors | tests/v2/analytics/ |
| Cross-milestone risk | auto-transform rides dictation; no word duplication |
| Evidence | [C02] |


## IF-027 — M13 → M09: Insights report

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Insights report |
| Frozen fields | single report revision/cohort/zone |
| Mutable fields | new query generation |
| Expected revision / identity | generation + usage revision + pane identity |
| Deletion / expiry behavior | usage deletion invalidates cached/visible reports |
| Timeout / unknown behavior | unknown deletion revokes then reconciles via receipt |
| Owning tests / binding anchors | tests/v2/analytics/ (bind actual Insights UI test nodes locally) |
| Cross-milestone risk | native stale-publication execution pending (14) |
| Evidence | [C02] [S10] |


## IF-028 — M13 → M14: usage-derived profile fields

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | usage-derived profile fields |
| Frozen fields | source-class label and observed counts |
| Mutable fields | usage revision/redaction |
| Expected revision / identity | same committed usage signature at publication |
| Deletion / expiry behavior | same-op redaction of all usage copies; speech remains |
| Timeout / unknown behavior | unknown deletion not falsely failed |
| Owning tests / binding anchors | tests/v2/analytics/; personalization suites |
| Cross-milestone risk | no dictionary counters presented as speech |
| Evidence | [C02] [S05] |


## IF-029 — M02 training → M14: eligible speech cohort

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | eligible speech cohort |
| Frozen fields | owned raw transcript + capture provenance |
| Mutable fields | example state/revision/retention |
| Expected revision / identity | artifact owner+role+digest and logical capture identity |
| Deletion / expiry behavior | purge/exclusion/deletion invalidates support |
| Timeout / unknown behavior | profile publication rechecks exact inputs |
| Owning tests / binding anchors | tests/v2/personalization/test_profile.py |
| Cross-milestone risk | retry example dedup weaker than job identity (02) |
| Evidence | [S05] [S07] [C08] |


## IF-030 — M05 → M14: applied technical vocabulary

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | applied technical vocabulary |
| Frozen fields | frozen canonical + entry revision |
| Mutable fields | current dictionary edit |
| Expected revision / identity | historical applied revision, not ID alone |
| Deletion / expiry behavior | loss of support suppresses speech claim |
| Timeout / unknown behavior | read failure cannot invent current term evidence |
| Owning tests / binding anchors | tests/v2/vocabulary/; personalization suites |
| Cross-milestone risk | current canonical joined to old speech (03) |
| Evidence | [S05] [S12] |


## IF-031 — M14 → M05: approved learning delta

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | approved learning delta |
| Frozen fields | candidate evidence + proposed scope |
| Mutable fields | vocabulary revision/action result |
| Expected revision / identity | canonical scope + expected revision + operation receipt |
| Deletion / expiry behavior | user edits protected; stale evidence cannot silently approve |
| Timeout / unknown behavior | same operation ID returns one receipt |
| Owning tests / binding anchors | tests/v2/personalization/test_learning.py; vocabulary suites |
| Cross-milestone risk | approval service stronger than absent UI undo (09) |
| Evidence | [H14] [S06] |


## IF-032 — M14 → M05/M09: Undo Approval

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | Undo Approval |
| Frozen fields | exact recorded vocabulary delta |
| Mutable fields | undo result and current entry revision |
| Expected revision / identity | candidate/delta/entry revision |
| Deletion / expiry behavior | does not erase later user changes |
| Timeout / unknown behavior | unknown outcome reconciles rather than applying twice |
| Owning tests / binding anchors | personalization and vocabulary suites |
| Cross-milestone risk | Hub control missing (09) |
| Evidence | [H14] |


## IF-033 — M11 → M14: transform candidate/observation

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | transform candidate/observation |
| Frozen fields | task key, source/output, prompt/definition revisions |
| Mutable fields | latest explicit accept/reject/abstain |
| Expected revision / identity | same task, candidate IDs and current judgment |
| Deletion / expiry behavior | governed payloads purge with authority; independent notes separate |
| Timeout / unknown behavior | no automatic application becomes human label |
| Owning tests / binding anchors | tests/v2/transforms/; training/curation suites |
| Cross-milestone risk | direct SQL forgery only defense-in-depth residual |
| Evidence | [C05] [S14] [H14] |


## IF-034 — M14 split service → M14 exporter/M13 readiness: family membership/exposure

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | family membership/exposure |
| Frozen fields | assignment version and family identity |
| Mutable fields | monotonic exposure knowledge |
| Expected revision / identity | current all-version exposed-ever predicate |
| Deletion / expiry behavior | deletion cannot make previously exposed family blind |
| Timeout / unknown behavior | recheck exposure before publication |
| Owning tests / binding anchors | training/curation suites; M14 remediation corpus |
| Cross-milestone risk | old assignment selection cannot reset exposure |
| Evidence | [S08] [H14] |


## IF-035 — M14 qualification → M13 readiness/M14 export: task eligibility decision

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | task eligibility decision |
| Frozen fields | view/tier/record dependency identity |
| Mutable fields | current evidence/labels/consent |
| Expected revision / identity | same predicate and definition revision |
| Deletion / expiry behavior | removing evidence only removes dependent records |
| Timeout / unknown behavior | refusals return reasons, not fabricated eligibility |
| Owning tests / binding anchors | tests/v2/ui/ and training/curation suites (bind actual readiness test nodes locally); curation suites |
| Cross-milestone risk | shared helper supported; all-view differential run NOT_RUN |
| Evidence | [S07] [S08] [C02] |


## IF-036 — M14 exporter → offline validator: self-contained package

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | self-contained package |
| Frozen fields | manifest/tasks/artifacts/prompts/hashes/exposure |
| Mutable fields | publication/completion state |
| Expected revision / identity | offline closure with no private-DB dependency |
| Deletion / expiry behavior | export already released is independent disclosure; future exports requalify |
| Timeout / unknown behavior | post-rename missing receipt needs reconciliation |
| Owning tests / binding anchors | curation export/validator suites |
| Cross-milestone risk | filesystem/SQLite crash seam (08) |
| Evidence | [S08] [H14] |


## IF-037 — M14 validator → M09 Export pane: validation result

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | validation result |
| Frozen fields | destination/fingerprint/result |
| Mutable fields | action generation |
| Expected revision / identity | newer result beats older background refresh |
| Deletion / expiry behavior | closed/revoked pane cannot publish |
| Timeout / unknown behavior | worker cancellation is not dataset failure |
| Owning tests / binding anchors | tests/v2/personalization/test_native_m14_training.py |
| Cross-milestone risk | late refresh and blocking callback (06/07) |
| Evidence | [S09] |


## IF-038 — M02 repair → M14 profile/deletion: schema family graph

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | schema family graph |
| Frozen fields | recorded schema + backed-up pre-repair state |
| Mutable fields | validated migration state |
| Expected revision / identity | relationship integrity, not table existence alone |
| Deletion / expiry behavior | missing links must invalidate/refuse dependent content |
| Timeout / unknown behavior | failed open cannot expose repaired-empty authority |
| Owning tests / binding anchors | tests/v2/storage/; personalization suites |
| Cross-milestone risk | profile_evidence empty repair gap (05) |
| Evidence | [S04] [S05] |


## IF-039 — M02 retention → M09/M12/M14: artifact leases and revocation

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | artifact leases and revocation |
| Frozen fields | artifact owner/stage; lease purpose/holder |
| Mutable fields | expiry/pin/review interests |
| Expected revision / identity | all current valid leases, explicit purpose |
| Deletion / expiry behavior | expiry/purge propagates to derived views |
| Timeout / unknown behavior | timeout does not prove purge completed |
| Owning tests / binding anchors | storage/training/personalization suites |
| Cross-milestone risk | review retention is not a user pin; UI races pending |
| Evidence | [C01] [H14] |


## IF-040 — M02/M10/M12 → M14 managed export reads: managed file capability

| Dimension | Contract / observed seam |
| --- | --- |
| Authoritative object | managed file capability |
| Frozen fields | configured authority and accepted managed basename |
| Mutable fields | retained/open descriptor |
| Expected revision / identity | root confinement + no-follow + regular-file + digest |
| Deletion / expiry behavior | purge/revocation rechecked before new publication |
| Timeout / unknown behavior | read failure refuses relevant record only |
| Owning tests / binding anchors | storage/developer/notes/curation suites |
| Cross-milestone risk | full caller and CLI backup matrix pending (15) |
| Evidence | [C01] [C04] [S07] [S08] |


## End-to-end outcome variants

| Variant | Identity | Route | Downstream semantics |
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


## Functional surfaces to preserve for the later redesign

| Surface | Data source | Key actions | Stable identity | Async ownership | Qualification status |
| --- | --- | --- | --- | --- | --- |
| Home | Coordinator/engine summaries and recent store state | open views, engine/recovery status | current job/engine generation, not stale process | Hub pane/query generation | Inherited shell evidence; current human functional check pending |
| History | HistoryQueryService + coordinator | search/replay/retry/copy/repaste/save/move/Teach/delete usage | rendered job+attempt+artifact/revision | query generation + action identity | 01 and 04 affect composition; native action requalification pending |
| Styles | StyleRuleStore + frozen effective profile | add/edit/enable/delete, preview, next mode | rule ID/revision; declared preview scope | rendered editor item and mutation generation | M10 native pane evidence inherited; real destination trials pending |
| Snippets | SnippetStore + normalization preview | CRUD/collision preview/phrase preview | snippet ID/revision, trigger ownership | editor identity and refresh invalidation | M10 native evidence inherited; real dictation pending |
| Transforms | TransformStore + worker + preview | CRUD/run/accept/copy/retry-original/apply-another/transform-result/save note | definition revision + task key + original selection/note | worker task ownership + preview lifetime | M11 human/model gates remain; no visual redesign |
| Scratchpad | NoteStore and editor revision queue | type/autosave/dictate/restore/image/export/transform | note/revision/region, UTF-16 mapping, operation receipt | note selection/editor generation, queued saves | M12 owned-native evidence inherited; five human checks pending |
| Insights | one-revision Insights report | range/app/mode filters, subview, reload | typed cohort and usage revision | shared usage epoch/query token | M13 inherited evidence; five human checks and cross-pane races pending |
| Training/Review | TrainingDataService + learning/review/sampling/splits | replay/labels/span refs/approve/reject/exclude/pairs/splits/export | rendered example/candidate/revision/task/assignment | rendered action identity + operation receipt | M14 evidence inherited; Undo Approval gap and native trials pending |
| Your Voice | deterministic ProfileService | regenerate, inspect sources, exclude evidence | snapshot ID + live cited examples and usage signature | profile result and exclusion invalidation | 02/03/05 affect authority; deletion/visibility probes pending |
| Diagnostics | typed event/diagnostic query | filter, inspect, redacted support export | event IDs/time/filter revision | bounded query owner/generation | No global privacy-canary sweep executed here |
| Models / Export | engine state, TrainingDataService, exporter/validator | status, dataset readiness, export/validate | engine/run identity; view/tier/package/destination | Models refresh plus action result generation | 06/07/08 require bounded functional handling |
| Settings | validated config + consent + usage policy | apply policy, collection controls, delete usage | committed policy revision and operation receipt | explicit action outcome + usage invalidation | Historical automation distinct from current user/installed-app state |


## Local linearization ledger to complete before editing

For each repeat-sensitive operation, mark admission, source/revision check, writer transaction, filesystem/external side effect, commit, receipt publication and UI refresh. Mark which boundaries are truly atomic and which are recoverable sequences. Record a concrete same-operation retry strategy for unknown outcomes. Never mark a check→writer→filesystem→writer sequence atomic merely because all individual submits are serialized.

Particularly inspect M10 config persistence, M12 staged attachments/export and note receipts, M14 export rename/completion, source deletion listeners and profile publication. The map names known important interfaces, not a substitute for exhaustive tracked-file caller discovery.

## Pinned sources

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