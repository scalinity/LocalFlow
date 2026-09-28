# LocalFlow Cross-Milestone Interface Matrix

**Repository:** `scalinity/LocalFlow`  
**Audited commit:** `340c566686c7123bfcf721e16160aacabbe0b97d`  
**Prepared:** 2026-09-28

**Coverage boundary:** This is a 50-interface authority map, not an exhaustive production call-site inventory. `DIRECT_SOURCE_PAIR` means the owner and consumer were traced for the stated allegation, not that every caller was inspected. Contract/handoff rows remain explicitly unclosed. No target code was executed.

## Summary

- Interfaces: **50**. Directly traced allegation pairs: **9**.
- All target tests, native probes, models, races and mutations: **NOT_RUN**.
- Exact source versions are attached to every row; current main was rechecked at the audited commit.

| ID | Authority / interface | Owner → known consumers | Milestones | Coverage | Finding / closure |
|---|---|---|---|---|---|
| XF-IF-001 | Event taxonomy and content-free envelope | M01 events contract / EventLog → coordinator, services, Diagnostics | M01/M02/M03/M09 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-002 | Public Store submission | Store.submit/_submit → all synchronous service mutations and queries | M02/M03/M09/M11/M12/M14 | DIRECT_SOURCE_PAIR | XF-AUDIT-05/06/07 |
| XF-IF-003 | Job/attempt lifecycle identity | session coordinator → workers, collector, History, insertion, analytics | M02/M03/M07/M08/M09/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-004 | Audio provenance across retry | audio/session owner → worker ASR, Recovery, replay, ASR export | M02/M03/M09/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-005 | Deletion tombstones | Store deletion API → collector, workers, HubState, notes, review/export/profile | M02/M03/M09/M12/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-006 | Lease/purge ownership | Store retention policy → History, training buffer, notes annotations, dataset sources | M02/M09/M12/M14 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-007 | Capture-boundary consent | coordinator + EvidenceCollector → stage capture, retry, example creation | M02/M03/M06/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-008 | Frozen personal vocabulary | VocabularyStore/configured normalizer → normalization, ASR hints, cleanup hints, learning approval sandbox | M04/M05/M06/M10/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-009 | Normalization result and retained input | EvidenceCollector.on_normalization → cleanup qualifier, exporter | M04/M07/M14 | DIRECT_SOURCE_PAIR | XF-AUDIT-04 |
| XF-IF-010 | Normalization edit/lease envelope | normalizer + collector → History stages, training qualification | M04/M05/M06/M07/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-011 | Context handle and late delta | ContextEngine → coordinator, profile resolution, insertion capture, collector | M03/M05/M06/M08/M10/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-012 | Cleanup faithful gate | cleanup validator/engine → coordinator, collector, replay/evaluation | M04/M05/M06/M07/M10/M14 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-013 | Cleanup provenance completeness | cleanup_qualification_in → teach readiness, dataset records, qualification data | M07/M14/M15 | DIRECT_SOURCE_PAIR | XF-AUDIT-04 |
| XF-IF-014 | Writing profile frozen for one job | profile resolver → normalization, cleanup, transform-backed mode | M06/M10/M11 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-015 | Snippet literal provenance | snippet expansion → normalizer, cleanup, notes/profile eligibility | M04/M07/M10 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-016 | Current transform definition and preserved revision | TransformStore.update_transform → engine definition lookup, transform qualification, dataset exporter | M02/M11/M14 | DIRECT_SOURCE_PAIR | XF-AUDIT-02 |
| XF-IF-017 | Transform editor update binding | Hub transform editor → TransformStore | M09/M10/M11 | DIRECT_SOURCE_PAIR | XF-AUDIT-03 |
| XF-IF-018 | Transform Add outcome identity | Hub _transform_write / transformsAdd_ → TransformStore.add_transform | M02/M09/M11 | DIRECT_SOURCE_PAIR | XF-AUDIT-05 |
| XF-IF-019 | Transform frozen task/candidate identity | transform request/task producer → result panel, candidate store, preference and export | M01/M11/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-020 | Prompt Engineer preservation | Prompt Engineer requirement/literal gates → transform acceptance, saved result, dataset candidates | M07/M11/M14 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-021 | Insertion admission handshake | InsertionService → live coordinator, retry, paste-again, transform paste | M03/M08/M09/M11/M12 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-022 | Clipboard payload ownership | InsertionService.copy_text / _guarded_copy → History Copy, transform Copy, Recovery Copy Last Raw | M08/M09/M11/M12 | DIRECT_SOURCE_PAIR | XF-AUDIT-01 |
| XF-IF-023 | Insertion final readback and cancellation | insertion transaction → coordinator state, History attempt, analytics | M03/M08/M13 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-024 | History current final-stage resolution | HistoryQueryService.final_text → Copy, Teach, Scratchpad transfer, detail | M02/M03/M09/M11/M12 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-025 | History search versus display lineage | HistoryQueryService → Hub list/detail | M03/M09 | PARTIAL_SOURCE_AND_CONTRACT | BOUNDED_INSPECTION_NO_NEW_DEFECT_ESTABLISHED |
| XF-IF-026 | Hub query publication epoch | QueryExecutor / HubState → all pane queries and errors | M02/M09/M12/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-027 | Rendered detail action identity | Hub controllers → Copy, Teach, labels, candidate actions, notes transfer | M09/M10/M11/M12/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-028 | Replay source availability | replay service → History Replay, training listening gate | M02/M09 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-029 | Note create and typed outcomes | NoteStore.create_note/_mutation_submit → Scratchpad New, transform Save, History transfer | M02/M11/M12 | DIRECT_SOURCE_PAIR | XF-AUDIT-06 |
| XF-IF-030 | Note arrival durability | note arrival receipt owner → dictation destination, autosave, coordinator completion | M03/M12 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-031 | Note rebase/attribution boundary | rebase_spans / occurrence ownership → editor save, learning miner, profile eligibility | M12/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-032 | Note transform whole/selection acceptance | note_destination_check → transform Accept into Scratchpad | M11/M12 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-033 | History Copy/Move two-phase receipt | hubSaveHistoryRow → History transfer controls, NoteStore, source deletion | M02/M09/M12 | DIRECT_SOURCE_PAIR | XF-AUDIT-07 |
| XF-IF-034 | Explicit Teach source authority | Hub Teach / LearningService → candidate queue, VocabularyStore approval | M09/M11/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-035 | Vocabulary approval/undo atomicity | LearningService + vocabulary composer → Review controls, effective dictionary | M05/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-036 | Candidate counterexample scope | approval sandbox → approve action | M05/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-037 | Training label/span source checks | curation repository → inspector, readiness, sampling, exports | M02/M09/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-038 | Audio-reviewed verbatim gate | training inspector → reference creation, ASR export | M09/M14 | CONTRACT_ONLY | UNRESOLVED_FULL_CLOSURE |
| XF-IF-039 | Preference comparability/order | pair/judgment owner → Review pair surface, preference exporter | M01/M11/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-040 | Family split membership/exposure | split/exposure service → Review readiness, export publication, M15 qualification | M01/M14 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-041 | Dataset snapshot and exact-input publication fence | DatasetExporter → filesystem staging/final output, export receipts, exposure bookkeeping | M02/M14 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-042 | Offline validator and bundle manifest | validate_dataset_folder → qualification harness, user exported folder | M01/M14/M15 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-043 | Profile eligible population | ProfileService → Your Voice cards, Insights links | M12/M13/M14 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-044 | Profile input-signature/commit fence | profile snapshot store → cached cards, phrase evidence, generation state | M02/M13/M14 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-045 | Analytics logical fact population | AnalyticsStore → Insights report, profile usage projection | M03/M08/M13 | CONTRACT_AND_SOURCE_WINDOWS | UNRESOLVED_FULL_CLOSURE |
| XF-IF-046 | Content/usage deletion distinction | Store + analytics/profile deletion owners → usage reports, profile snapshot copies, UI invalidation | M02/M13/M14 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-047 | Read-only/focus-safe Hub publication | Hub and transform controllers → menu/status/timer/background callbacks | M08/M09/M11/M12 | PARTIAL_SOURCE_AND_CONTRACT | UNRESOLVED_FULL_CLOSURE |
| XF-IF-048 | Status/runbook/browser state projection | STATUS + ORCHESTRATION + VERIFICATION owners → fresh agent, human acceptance tracking | M01/M09/M14/M15 | DIRECT_DOCUMENT_PAIR | XF-AUDIT-08 |
| XF-IF-049 | Performance validity versus speed | benchmark harness and independent validity oracle → milestone acceptance, model/performance qualification | M01/M13/M14/M15 | CONTRACT_AND_HANDOFF | UNRESOLVED_FULL_CLOSURE |
| XF-IF-050 | M15 qualification gate | canonical milestone/spec/evaluation owners → future model candidates, performance and acceptance reports | M01/M04/M07/M11/M14/M15 | CANONICAL_EXCERPT_AND_CONTRACT_INDEX | UNRESOLVED_FULL_CLOSURE |

## Detailed contracts and remaining work

### XF-IF-001 — Event taxonomy and content-free envelope

**Owner:** M01 events contract / EventLog. **Consumers:** coordinator, services, Diagnostics.

**Authority:** schema_version, timestamp/time-quality, job/attempt, decision/path, content-free detail.

**Thread/writer rule:** Queue-backed event writing; do not block callback or write private content in envelope.

**Required outcome behavior:** Unknown facts retain null/reason; queue loss is explicit.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/events.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/events.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-002 — Public Store submission

**Owner:** Store.submit/_submit. **Consumers:** all synchronous service mutations and queries.

**Authority:** admission occurred versus not_started; eventual commit independent of reply timeout.

**Thread/writer rule:** One writer op; transaction BEGIN/COMMIT or rollback.

**Required outcome behavior:** Admitted timeout remains unknown; no unconditional retry with a fresh identity.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-003 — Job/attempt lifecycle identity

**Owner:** session coordinator. **Consumers:** workers, collector, History, insertion, analytics.

**Authority:** job_id, attempt, worker/stage generation, capture identity.

**Thread/writer rule:** Coordinator validates before publication; writer validates liveness.

**Required outcome behavior:** Old attempt/generation must not mutate current state.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/jobs.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/jobs.md); [docs/v2/contracts/worker.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/worker.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-004 — Audio provenance across retry

**Owner:** audio/session owner. **Consumers:** worker ASR, Recovery, replay, ASR export.

**Authority:** original sample rate/count/digest, capture time/quality, artifact owner.

**Thread/writer rule:** Managed payloads and bounded worker transport.

**Required outcome behavior:** Unavailable audio refuses replay/export; original unknown time is not retry time.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/capture.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/capture.md); [docs/v2/contracts/jobs.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/jobs.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-005 — Deletion tombstones

**Owner:** Store deletion API. **Consumers:** collector, workers, HubState, notes, review/export/profile.

**Authority:** job/note/example identity, tombstone/revocation epoch.

**Thread/writer rule:** Check inside each write op; notify UI without recursive blocking Store call.

**Required outcome behavior:** Delete wins over late finalize/publication; no resurrection.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/store.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-006 — Lease/purge ownership

**Owner:** Store retention policy. **Consumers:** History, training buffer, notes annotations, dataset sources.

**Authority:** owner-specific purpose/expiry; managed path; pending purge record.

**Thread/writer rule:** Serial decisions, tracked unlink/reconciliation.

**Required outcome behavior:** pending_purge is not complete deletion; retention failure is not permission.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/store.md); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-007 — Capture-boundary consent

**Owner:** coordinator + EvidenceCollector. **Consumers:** stage capture, retry, example creation.

**Authority:** consent_revision_id at capture, privacy mode and original capture lineage.

**Thread/writer rule:** Freeze before processing; producer checks applicable authority.

**Required outcome behavior:** Late enable does not retroactively authorize captured payloads.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py#L660-L830); [docs/v2/contracts/store.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/store.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-008 — Frozen personal vocabulary

**Owner:** VocabularyStore/configured normalizer. **Consumers:** normalization, ASR hints, cleanup hints, learning approval sandbox.

**Authority:** dictionary revision, scope, approved state, active normalizer mode.

**Thread/writer rule:** One job snapshot; dictionary writes through writer.

**Required outcome behavior:** Unavailable scope cannot expand vocabulary; rejected/pending never become rules.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/vocabulary.md); [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/normalization.md); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py#L1-L300).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-009 — Normalization result and retained input

**Owner:** EvidenceCollector.on_normalization. **Consumers:** cleanup qualifier, exporter.

**Authority:** actual normalized text, changed/not-run/failure, artifact role/hash, missing reasons.

**Thread/writer rule:** Collector writes/leases evidence; consumer must preserve producer outcome.

**Required outcome behavior:** Failed retention is not absent normalization; complete tier requires exact input.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py#L660-L830); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-010 — Normalization edit/lease envelope

**Owner:** normalizer + collector. **Consumers:** History stages, training qualification.

**Authority:** input/output digest, edits, policy snapshot, hint-context provenance.

**Thread/writer rule:** Managed artifact writes; release retired attempt leases.

**Required outcome behavior:** Missing stage artifacts retain specific reasons, not guessed content.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/training.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/training.py#L660-L830); [docs/v2/contracts/normalization.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/normalization.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-011 — Context handle and late delta

**Owner:** ContextEngine. **Consumers:** coordinator, profile resolution, insertion capture, collector.

**Authority:** opaque per-job handle, origin, trust, fingerprint, parent revision.

**Thread/writer rule:** Capture/finalize deadlines and ownership; native AX access at adapter.

**Required outcome behavior:** Deny/secure/unavailable is explicit; late result cannot reparent.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/context.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/context.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-012 — Cleanup faithful gate

**Owner:** cleanup validator/engine. **Consumers:** coordinator, collector, replay/evaluation.

**Authority:** exact input, applicable hints, required preservation, path/model/prompt provenance.

**Thread/writer rule:** Worker model path; deterministic validation boundary.

**Required outcome behavior:** Fail-closed fallback with a real reason; no relaxed fidelity for score gain.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/cleanup.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/cleanup.md); [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/training_evidence.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-013 — Cleanup provenance completeness

**Owner:** cleanup_qualification_in. **Consumers:** teach readiness, dataset records, qualification data.

**Authority:** explicit intended correctness, stage input/output, model revision, rendered prompt.

**Thread/writer rule:** Same eligibility owner used by readiness/export.

**Required outcome behavior:** Text-pair-only remains distinct from model-task-complete.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md#L45-L145).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-014 — Writing profile frozen for one job

**Owner:** profile resolver. **Consumers:** normalization, cleanup, transform-backed mode.

**Authority:** mode override, app rule, skills, dictionary/context/settings revisions.

**Thread/writer rule:** Resolve/freeze once at documented boundary.

**Required outcome behavior:** No workspace context means no stale workspace skills; one-shot consumed once.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profiles.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-015 — Snippet literal provenance

**Owner:** snippet expansion. **Consumers:** normalizer, cleanup, notes/profile eligibility.

**Authority:** trigger, expansion range, protected literals, origin.

**Thread/writer rule:** Use frozen profile/registry.

**Required outcome behavior:** Missing placeholder does not become fabricated successful expansion.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profiles.md); [docs/v2/contracts/training_evidence.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/training_evidence.md); [docs/v2/contracts/profiles.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profiles.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-016 — Current transform definition and preserved revision

**Owner:** TransformStore.update_transform. **Consumers:** engine definition lookup, transform qualification, dataset exporter.

**Authority:** transform_id/revision and all definition fields.

**Thread/writer rule:** Authoritative merge/update/preserve must be atomic in one writer op.

**Required outcome behavior:** No revision may name divergent live and preserved definitions.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-017 — Transform editor update binding

**Owner:** Hub transform editor. **Consumers:** TransformStore.

**Authority:** rendered id/revision, edited delta, auto_apply opt-out.

**Thread/writer rule:** Main-thread form, guarded store mutation.

**Required outcome behavior:** Stale form refuses/conflicts; unchanged stale fields do not overwrite newer state.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-018 — Transform Add outcome identity

**Owner:** Hub _transform_write / transformsAdd_. **Consumers:** TransformStore.add_transform.

**Authority:** logical create id and outcome state.

**Thread/writer rule:** Store admission is separate from UI reply.

**Required outcome behavior:** Preserve outcome_unknown and reconcile same id before repeat.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/v2/transforms_store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/transforms_store.py#L200-L335); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-019 — Transform frozen task/candidate identity

**Owner:** transform request/task producer. **Consumers:** result panel, candidate store, preference and export.

**Authority:** source digest, cleaned input, transform id/revision, settings/prompt, candidate id.

**Thread/writer rule:** Freeze task before worker execution.

**Required outcome behavior:** Equal outputs alone do not establish comparable task identity.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/transforms.md); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-020 — Prompt Engineer preservation

**Owner:** Prompt Engineer requirement/literal gates. **Consumers:** transform acceptance, saved result, dataset candidates.

**Authority:** actions, polarity, actors, explicit literals, protected requirements.

**Thread/writer rule:** Independent deterministic acceptance gate around model output.

**Required outcome behavior:** Drop/negate explicit requirements means refuse/fallback, not accepted improvement.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/transforms.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/transforms.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-021 — Insertion admission handshake

**Owner:** InsertionService. **Consumers:** live coordinator, retry, paste-again, transform paste.

**Authority:** submission accepted versus settled outcome; job/generation/source authority.

**Thread/writer rule:** Serial insertion service; native transport isolated.

**Required outcome behavior:** No backend call when not admitted; truthful queued/unverified/confirmed distinction.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/insertion/service.py#L1-L250); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py); [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/insertion.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-022 — Clipboard payload ownership

**Owner:** InsertionService.copy_text / _guarded_copy. **Consumers:** History Copy, transform Copy, Recovery Copy Last Raw.

**Authority:** ownership ticket, clipboard generation and pending payload.

**Thread/writer rule:** One guarded broker; every in-app caller must use it.

**Required outcome behavior:** clipboard_payload_pending refusal survives caller/UI.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/insertion/service.py#L1-L250); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L5830-L6005); [localflow/inject.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/inject.py#L1-L150).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-023 — Insertion final readback and cancellation

**Owner:** insertion transaction. **Consumers:** coordinator state, History attempt, analytics.

**Authority:** irreversible-post phase, observable host state, cancellation timing.

**Thread/writer rule:** Serialized transaction; bounded wait/retention.

**Required outcome behavior:** Unobservable is not confirmed; cancellation after post is not no effect.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/insertion/service.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/insertion/service.py#L1-L250); [docs/v2/contracts/insertion.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/insertion.md); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-024 — History current final-stage resolution

**Owner:** HistoryQueryService.final_text. **Consumers:** Copy, Teach, Scratchpad transfer, detail.

**Authority:** applied final stage, exact artifact id/hash, lineage attempt.

**Thread/writer rule:** Read authoritative live state; action revalidates.

**Required outcome behavior:** Missing applied transformed final must not fall back to cleaned/raw.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/history_queries.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py#L1-L600); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-025 — History search versus display lineage

**Owner:** HistoryQueryService. **Consumers:** Hub list/detail.

**Authority:** retained attempt match, current displayed manifest, explicit search policy.

**Thread/writer rule:** Bounded read/query publication.

**Required outcome behavior:** Search policy broader than current final is not itself a wrong-target defect.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** BOUNDED_INSPECTION_NO_NEW_DEFECT_ESTABLISHED.

**Source pointers:** [localflow/v2/history_queries.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py#L1-L600); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-026 — Hub query publication epoch

**Owner:** QueryExecutor / HubState. **Consumers:** all pane queries and errors.

**Authority:** per-key newest generation, active pane, deletion epoch.

**Thread/writer rule:** Background read; actual main-thread publication.

**Required outcome behavior:** Older success or error cannot repaint newer state.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/ui/state.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/state.py#L1-L300); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-027 — Rendered detail action identity

**Owner:** Hub controllers. **Consumers:** Copy, Teach, labels, candidate actions, notes transfer.

**Authority:** what was drawn: id/revision/hash/slot order, not only current selected_id.

**Thread/writer rule:** Bind before background action; revalidate on writer admission.

**Required outcome behavior:** selection_loading/stale_source before mutation; preserve user input.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md); [localflow/v2/ui/hub.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/ui/hub.py#L1820-L2050); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-028 — Replay source availability

**Owner:** replay service. **Consumers:** History Replay, training listening gate.

**Authority:** exact audio artifact/job/example, real payload availability.

**Thread/writer rule:** Serialize playback ownership; cancel old source on new failure.

**Required outcome behavior:** Missing audio stops old playback and cannot authorize another example.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md); [docs/v2/contracts/capture.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/capture.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-029 — Note create and typed outcomes

**Owner:** NoteStore.create_note/_mutation_submit. **Consumers:** Scratchpad New, transform Save, History transfer.

**Authority:** preallocated note_id, admitted/refused/unknown, origin.

**Thread/writer rule:** Caller-supplied note id in Store writer; reconcile an existing note before any replay.

**Required outcome behavior:** NoteOutcomeUnknown identity must reach caller reconciliation.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L285-L640); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-030 — Note arrival durability

**Owner:** note arrival receipt owner. **Consumers:** dictation destination, autosave, coordinator completion.

**Authority:** arrival id, note id, base revision, content/generation, origin span.

**Thread/writer rule:** Actual writer receipt; no enqueue-as-durability.

**Required outcome behavior:** Keep admitted arrivals until settled; do not overwrite typed buffer.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/scratchpad.md); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L285-L640).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-031 — Note rebase/attribution boundary

**Owner:** rebase_spans / occurrence ownership. **Consumers:** editor save, learning miner, profile eligibility.

**Authority:** codepoint/UTF16 mapping, occurrence identity, typed/dictated origin.

**Thread/writer rule:** Pure attribution analysis plus writer-bound revision update.

**Required outcome behavior:** Ambiguous repeated occurrence abstains; typed edits do not become speech.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L1-L285); [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py#L1-L300); [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/scratchpad.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-032 — Note transform whole/selection acceptance

**Owner:** note_destination_check. **Consumers:** transform Accept into Scratchpad.

**Authority:** scope, captured full text or selected range, source revision/digest.

**Thread/writer rule:** Verify current destination at actual apply boundary.

**Required outcome behavior:** Whole-note changes refuse; unrelated outside edit may remain valid for exact selection.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L1-L285); [docs/v2/contracts/scratchpad.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/scratchpad.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-033 — History Copy/Move two-phase receipt

**Owner:** hubSaveHistoryRow. **Consumers:** History transfer controls, NoteStore, source deletion.

**Authority:** strict final/hash, destination id, source-delete phase/outcome.

**Thread/writer rule:** Destination create then optional delete; reconcile phases separately.

**Required outcome behavior:** create_unknown is handled; source_delete_unknown must not become confirmed failure.

**Evidence class:** DIRECT_SOURCE_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py#L2000-L2235); [localflow/v2/notes.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/notes.py#L285-L640); [localflow/v2/store.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/store.py#L1240-L1415).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-034 — Explicit Teach source authority

**Owner:** Hub Teach / LearningService. **Consumers:** candidate queue, VocabularyStore approval.

**Authority:** cleaned source artifact id/hash, explicit user correction, op id.

**Thread/writer rule:** Preallocated action id, writer current-source checks.

**Required outcome behavior:** Transformed final refuses; job-only explicit intent does not require enabling collection.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/learning.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/learning.py#L1-L300); [localflow/v2/history_queries.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/history_queries.py#L1-L600); [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-035 — Vocabulary approval/undo atomicity

**Owner:** LearningService + vocabulary composer. **Consumers:** Review controls, effective dictionary.

**Authority:** candidate/decision id, exact alias/canonical/scope, recorded delta.

**Thread/writer rule:** One composed writer op, no nested submit.

**Required outcome behavior:** Unknown receipt target-bound; undo cannot erase independent later edit.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/learning.md); [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/vocabulary.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-036 — Candidate counterexample scope

**Owner:** approval sandbox. **Consumers:** approve action.

**Authority:** effective rule scope and independently supplied adverse phrase.

**Thread/writer rule:** Same normalization semantics/scope as resulting rule.

**Required outcome behavior:** A global sandbox cannot validate an app-scoped rule; would-flip refuses.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/learning.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/learning.md); [docs/v2/contracts/vocabulary.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/vocabulary.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-037 — Training label/span source checks

**Owner:** curation repository. **Consumers:** inspector, readiness, sampling, exports.

**Authority:** rendered example revision, stage id/hash, exact span coverage.

**Thread/writer rule:** Writer checks liveness/state/current source.

**Required outcome behavior:** Partial remains partial; expired/quarantined does not become live by labeling.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md); [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-038 — Audio-reviewed verbatim gate

**Owner:** training inspector. **Consumers:** reference creation, ASR export.

**Authority:** same example/audio listened-for identity and explicit coverage.

**Thread/writer rule:** Rendered binding plus writer reference validation.

**Required outcome behavior:** Model suggestion is not verbatim; playback of A does not authorize B.

**Evidence class:** CONTRACT_ONLY. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-039 — Preference comparability/order

**Owner:** pair/judgment owner. **Consumers:** Review pair surface, preference exporter.

**Authority:** same frozen task identity, displayed candidate ids/slot order, latest judgment.

**Thread/writer rule:** Append-only judgment; query current eligible state.

**Required outcome behavior:** Mismatched tasks/dead candidates refuse; row order is not displayed choice.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/curation/evidence.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/evidence.py#L105-L285); [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-040 — Family split membership/exposure

**Owner:** split/exposure service. **Consumers:** Review readiness, export publication, M15 qualification.

**Authority:** frozen family membership, partition version, forward-only exposure.

**Thread/writer rule:** Writer-bound assignment and exposure history.

**Required outcome behavior:** Below floor/unassigned are reasons, not invented complete partitions.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-041 — Dataset snapshot and exact-input publication fence

**Owner:** DatasetExporter. **Consumers:** filesystem staging/final output, export receipts, exposure bookkeeping.

**Authority:** actual input ids/revisions/digests and build operation target.

**Thread/writer rule:** Consistent snapshot; expensive I/O outside writer; scoped final fence.

**Required outcome behavior:** Relevant deletion/exposure refuses; unrelated changes do not arbitrary-abort.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [localflow/v2/curation/export.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/v2/curation/export.py#L335-L475); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md#L45-L145); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-042 — Offline validator and bundle manifest

**Owner:** validate_dataset_folder. **Consumers:** qualification harness, user exported folder.

**Authority:** record schema, semantic task/lineage, digests, local audio links.

**Thread/writer rule:** Offline read-only validation without live DB authority.

**Required outcome behavior:** Hash-consistent semantic tampering still fails; actual UTF8/missing files diagnosed.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md#L45-L145); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-043 — Profile eligible population

**Owner:** ProfileService. **Consumers:** Your Voice cards, Insights links.

**Authority:** eligible raw/spoken content, origin exclusions, measured word denominator.

**Thread/writer rule:** Bounded background compute with independent population validity.

**Required outcome behavior:** Typed/snippet/model boilerplate are excluded, not represented as user speech.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-044 — Profile input-signature/commit fence

**Owner:** profile snapshot store. **Consumers:** cached cards, phrase evidence, generation state.

**Authority:** exact eligible revisions, restrictions, source liveness, usage-derived metadata.

**Thread/writer rule:** Recheck inputs at commit; invalidate derived copies.

**Required outcome behavior:** No-change avoids new snapshot; changed/deleted source cannot publish stale snapshot.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-045 — Analytics logical fact population

**Owner:** AnalyticsStore. **Consumers:** Insights report, profile usage projection.

**Authority:** logical job id, current attempt, kind, valid capture time/zone.

**Thread/writer rule:** Writer upsert then cohort-consistent query.

**Required outcome behavior:** Retry replaces fact; transform/repaste not counted as another dictation.

**Evidence class:** CONTRACT_AND_SOURCE_WINDOWS. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/analytics.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-046 — Content/usage deletion distinction

**Owner:** Store + analytics/profile deletion owners. **Consumers:** usage reports, profile snapshot copies, UI invalidation.

**Authority:** explicit content versus usage deletion and derived dependencies.

**Thread/writer rule:** Cascade invalidation under named owners.

**Required outcome behavior:** Content deletion not silently usage deletion; usage deletion clears copied derived metadata.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/analytics.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/analytics.md); [docs/v2/contracts/profile.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/profile.md); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-047 — Read-only/focus-safe Hub publication

**Owner:** Hub and transform controllers. **Consumers:** menu/status/timer/background callbacks.

**Authority:** pipeline busy, insertion hold, rendered action token.

**Thread/writer rule:** Main-thread UI with passive refresh guards.

**Required outcome behavior:** Passive work never steals focus or performs external insertion.

**Evidence class:** PARTIAL_SOURCE_AND_CONTRACT. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/contracts/hub.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/hub.md); [localflow/app.py](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/localflow/app.py).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-048 — Status/runbook/browser state projection

**Owner:** STATUS + ORCHESTRATION + VERIFICATION owners. **Consumers:** fresh agent, human acceptance tracking.

**Authority:** current code/evidence refs, stable V-id instruction revision, browser namespace.

**Thread/writer rule:** Docs generated/reconciled from real id set; historical records immutable.

**Required outcome behavior:** Old green localStorage not a current pass; counts cannot be assumed from old addendum.

**Evidence class:** DIRECT_DOCUMENT_PAIR. **Closure:** OPEN_FINDING.

**Source pointers:** [docs/v2/STATUS.json](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/STATUS.json); [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280); [docs/v2/contracts/INDEX.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/INDEX.md).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-049 — Performance validity versus speed

**Owner:** benchmark harness and independent validity oracle. **Consumers:** milestone acceptance, model/performance qualification.

**Authority:** actual work cardinalities, semantic outputs, fixture/env/source identity, timing samples.

**Thread/writer rule:** Validate work before timing interpretation; separate queue wait from throughput.

**Required outcome behavior:** No-op/empty work INVALID; historical timing is not current end-to-end pass.

**Evidence class:** CONTRACT_AND_HANDOFF. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/handoffs/M14.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/handoffs/M14.md#L180-L280); [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md#L1380-L1515).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

### XF-IF-050 — M15 qualification gate

**Owner:** canonical milestone/spec/evaluation owners. **Consumers:** future model candidates, performance and acceptance reports.

**Authority:** current code, complete eligible data tiers, family exposure, faithful/PE policies.

**Thread/writer rule:** No execution authorized by this report; prepare source-bound local campaign.

**Required outcome behavior:** Do not use defective evidence as qualification truth or relax fidelity to obtain green results.

**Evidence class:** CANONICAL_EXCERPT_AND_CONTRACT_INDEX. **Closure:** UNRESOLVED_FULL_CLOSURE.

**Source pointers:** [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md#L1380-L1515); [docs/v2/LOCALFLOW_V2_MILESTONES.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/LOCALFLOW_V2_MILESTONES.md); [docs/v2/contracts/dataset_exports.md](https://github.com/scalinity/LocalFlow/blob/340c566686c7123bfcf721e16160aacabbe0b97d/docs/v2/contracts/dataset_exports.md#L45-L145).

**Unclosed:** Run the specified real local probe and complete a tracked-file consumer inventory. No absence claim follows from this row.

## Inventory self-check

All 50 ids are unique. Every row declares owner, known consumers, authority, writer/thread rule, required refusal/missing/unknown behavior, coverage and closure. No row claims an exhaustive consumer census. The JSON companion preserves machine-readable fields.
