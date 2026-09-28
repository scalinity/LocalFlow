# Cross-milestone interface union (A ∪ C ∪ B)

- Sources: Audit A 50 rows (XF-IF-001..050), Audit C 29 rows (IF-01..29), Audit B 40 rows (IF-001..040) — 119 source rows.
- Verified at branch `xm-local-remediation-20260928`, commit `63f9ef25148b4d10381693527e4679e351dcd60a`. The branch advanced twice during the build (another session committing); every site was re-resolved at the final pin and the closure check re-run with identical results.
- Caller baseline: the tracked census at `340c566` (`caller_inventory.json`, `census.json`); where the census has no symbol, the same `git grep` method at the pinned commit.
- Merge key: authoritative object, producer, consumer(s), identity/revision, deletion authority, timeout/unknown-outcome behaviour. Rows merged only when all of these matched; row count was never used as authority.

## Totals

| Measure | Count |
|---|---|
| Union rows | 78 |
| Shared rows (≥2 source rows, all span ≥2 audits) | 36 |
| Distinct source rows merged into shared rows | 78 of 119 |
| A-only rows kept | 27 |
| C-only rows kept | 3 |
| B-only rows kept | 12 |
| Shared by A+C / A+B / C+B / A+C+B | 8 / 7 / 12 / 9 |
| Source rows split across two union rows | 5 (A XF-IF-035, B IF-018, C IF-07, C IF-12, C IF-22) |
| Source rows covered | 119 (A 50, C 29, B 40) |

Split rows: XF-IF-035 and C IF-22 cover both approval (XM-IF-052) and Undo Approval (XM-IF-053); B IF-018 covers History Copy (XM-IF-034, clipboard ownership) and Paste Again (XM-IF-035); C IF-07 covers the frozen mode tuple (XM-IF-022) and file/skill confinement (XM-IF-023); C IF-12 covers the note receipt to the coordinator (XM-IF-045) and to usage (XM-IF-069). C's Paste Again destination policy is a History-surface and DESIGN-05 item, not a C matrix row; it is kept as XM-IF-035 with B IF-018.

## Closure

| State | Rows |
|---|---|
| bound | 70 |
| partial | 5 (XM-IF-001, 002, 009, 011, 063) |
| unbound | 3 (XM-IF-074, 076, 077) |

Rule: `bound` means every production caller of the producer that the census (or the pinned-commit grep) finds is listed as a consumer; every other pattern hit is classified per row in `closure_residue` (producer internals, name collisions, comment mentions, callers listed on a sibling row, scripts/ harnesses). 396 consumer sites and 29 missing-consumer sites were resolved to `file:line` at the pinned commit; none is unresolved.

## Partial and unbound rows

### XM-IF-001 — Content-free event envelope (event taxonomy) (`partial`)

Aliases: A ["XF-IF-001"], C [], B []. Findings: none.

Consumers found by the census that do not honour the interface:

- `Store._run` — `localflow/v2/store.py:1290` — exception text passed as free-text detail; EventWriter.emit stores detail verbatim (no sanitizer), so content-freedom rests on each caller
- `CaptureJournal._degrade` — `localflow/v2/capture_journal.py:348` — reason string concatenated into free-text detail; same verbatim-storage dependency

### XM-IF-002 — Public Store submission admission (writer op, reply timeout) (`partial`)

Aliases: A ["XF-IF-002"], C [], B []. Findings: MERGED-X08, MERGED-X09, MERGED-X10.

Consumers found by the census that do not honour the interface:

- `DictionaryPanelController.addEntry_` — `localflow/v2/dictionary_panel.py:239` — caller inventory class b: admitted timeout shown as 'not added'; residual, not repaired (M05 identity refuses a duplicate)
- `DictionaryPanelController.approveEntry_` — `localflow/v2/dictionary_panel.py:287` — class b residual label
- `DictionaryPanelController.toggleEntry_` — `localflow/v2/dictionary_panel.py:303` — class b residual label
- `DictionaryPanelController.pinEntry_` — `localflow/v2/dictionary_panel.py:316` — class b residual label
- `DictionaryPanelController.deleteEntry_` — `localflow/v2/dictionary_panel.py:329` — class b residual label
- `HubController.reviewMine_` — `localflow/v2/ui/hub.py:3514` — class b residual label ('action failed')
- `HubController.voiceGenerate_` — `localflow/v2/ui/hub.py:4329` — class b residual label ('generation failed')
- `HubController._set_collection` — `localflow/v2/ui/hub.py:4718` — class b: consent write may commit while shown as failed
- `AppDelegate.importDictionaryJSON_` — `localflow/app.py:5751` — class b residual label
- `AppDelegate.toggleTrainingCollection_` — `localflow/app.py:5305` — class c: store timeout raises into AppKit
- `AppDelegate.toggleTrainingPause_` — `localflow/app.py:5310` — class c
- `AppDelegate.excludeLastDictation_` — `localflow/app.py:5318` — class c
- `AppDelegate.markLastCorrect_` — `localflow/app.py:5321` — class c
- `ScratchpadEditor._mark_dirty` — `localflow/v2/ui/scratchpad.py:178` — class c: wait=False, exception swallowed
- `AppDelegate._retry_job` — `localflow/app.py:5960` — direct store.submit read; TimeoutError collapses into usage.retry_provenance_unavailable

### XM-IF-009 — Capture-boundary consent snapshot (`partial`)

Aliases: A ["XF-IF-007"], C [], B []. Findings: none.

Consumers found by the census that do not honour the interface:

- `AppDelegate.toggleTrainingCollection_` — `localflow/app.py:5305` — census class c: consent.state()/consent.set read the store with a wait and have no timeout handling
- `AppDelegate.toggleTrainingPause_` — `localflow/app.py:5310` — census class c
- `HubController._set_collection` — `localflow/v2/ui/hub.py:4718` — census class b: TimeoutError shown as failed while the append_consent write may commit

### XM-IF-011 — Canonical scoped vocabulary entry identity (writer-authoritative) (`partial`)

Aliases: A [], C ["IF-05"], B []. Findings: none.

Consumers found by the census that do not honour the interface:

- `DictionaryPanelController.addEntry_` — `localflow/v2/dictionary_panel.py:239` — caller inventory class b residual: admitted timeout reported as 'not added'
- `DictionaryPanelController.approveEntry_` — `localflow/v2/dictionary_panel.py:287` — class b residual
- `DictionaryPanelController.toggleEntry_` — `localflow/v2/dictionary_panel.py:303` — class b residual
- `DictionaryPanelController.pinEntry_` — `localflow/v2/dictionary_panel.py:316` — class b residual
- `DictionaryPanelController.deleteEntry_` — `localflow/v2/dictionary_panel.py:329` — class b residual
- `AppDelegate.importDictionaryJSON_` — `localflow/app.py:5751` — class b residual

### XM-IF-063 — Managed artifact file capability for export reads (`partial`)

Aliases: A [], C ["IF-25"], B ["IF-040"]. Findings: none.

Consumers found by the census that do not honour the interface:

- `Store.artifact_payload` — `localflow/v2/store.py:1759` — managed audio read by path (census file_io store.py read_wav/read_bytes) outside the confined no-follow helper; reached by ReplayService.play_artifact
- `AppDelegate._retry_job` — `localflow/app.py:5883` — retry reads managed audio by path outside the confined helper
- `ReplayService.play_artifact` — `localflow/v2/ui/replay.py:84` — History/training replay reaches Store.artifact_payload (plain-path read of managed audio)

### XM-IF-074 — Status/runbook/registry current-state projection (`unbound`)

Aliases: A ["XF-IF-048"], C ["IF-29"], B []. Findings: MERGED-X16, MERGED-X17.

Reason: document projection with no production callable: census STATUS.json has 0 production hits; VERIFICATION.html production hits are comments in scripts. At the pinned commit STATUS.json has no current_state projection (D15 not landed) and VERIFICATION.html M07 is still the placeholder at line 2514 (D16 not landed; GATE-G03 records M07 has none).

### XM-IF-076 — Performance validity versus speed (`unbound`)

Aliases: A ["XF-IF-049"], C [], B []. Findings: none.

Reason: the producer exists only as benchmark scripts; its consumers are acceptance documents and humans, not a production callable.

### XM-IF-077 — M15 qualification gate (`unbound`)

Aliases: A ["XF-IF-050"], C [], B []. Findings: none.

Reason: M15 is not implemented; the gate is a document requirement with no producer or consumer callable.

## Preserved interfaces (required by the brief)

| Required | Union row |
|---|---|
| A XF-IF-002 Store submission | XM-IF-002 |
| A XF-IF-009 normalization retained input | XM-IF-012 |
| A XF-IF-013 cleanup provenance completeness | XM-IF-021 |
| A XF-IF-016 transform live/preserved revision | XM-IF-025 (with C IF-08) |
| A XF-IF-017 transform editor binding | XM-IF-026 |
| A XF-IF-018 Transform Add identity | XM-IF-027 |
| A XF-IF-022 clipboard payload ownership | XM-IF-034 (with B IF-019) |
| A XF-IF-029 note create typed outcomes | XM-IF-044 |
| A XF-IF-033 History Move two-phase receipt | XM-IF-049 (with C IF-15, B IF-020) |
| A XF-IF-048 status/runbook projection | XM-IF-074 (with C IF-29) |
| C later relational repair/exposure | XM-IF-078 (IF-28), XM-IF-059 (IF-24) |
| C transform definition history | XM-IF-025 (IF-08) |
| C eligible speech profile identity | XM-IF-064 (IF-19) |
| C historical applied vocabulary | XM-IF-067 (IF-20) |
| C Store family integrity | XM-IF-078 (IF-28) |
| C Paste Again destination policy | XM-IF-035 (History surface, DESIGN-05) |
| B current History attempt | XM-IF-038 (IF-016) |
| B profile cohort | XM-IF-064 (IF-029) |
| B Export Validate | XM-IF-062 (IF-037) |
| B Undo Approval | XM-IF-053 (IF-032) |
| B offline package | XM-IF-061 (IF-036) |
| B schema-family graph | XM-IF-078 (IF-038) |
| B managed export reads | XM-IF-063 (IF-040) |

## Shared rows

| Union | Object | Aliases | Findings | Closure |
|---|---|---|---|---|
| XM-IF-003 | Job/attempt lifecycle identity and ASR audio request | A[XF-IF-003] C[] B[IF-003] |  | bound |
| XM-IF-005 | Managed audio and original capture provenance across retry/replay/export | A[XF-IF-004] C[IF-02] B[] |  | bound |
| XM-IF-008 | Artifact leases, retention purge and revocation | A[XF-IF-006] C[] B[IF-039] |  | bound |
| XM-IF-010 | Frozen per-job vocabulary snapshot | A[XF-IF-008] C[] B[IF-004] | MERGED-X11 | bound |
| XM-IF-013 | Runtime normalization result into cleanup (ledger, protected spans) | A[] C[IF-04] B[IF-010] |  | bound |
| XM-IF-015 | Job-scoped context handle and late downstream delta | A[XF-IF-011] C[IF-06] B[] |  | bound |
| XM-IF-020 | Clean applied output into transform input and insertion | A[] C[IF-09] B[IF-011] |  | bound |
| XM-IF-022 | Writing profile frozen for one job (mode, rules, skills, revisions) | A[XF-IF-014] C[IF-07] B[] |  | bound |
| XM-IF-023 | Skill/file reference records (confined root, manifest/listing revision) | A[] C[IF-07] B[IF-009] |  | bound |
| XM-IF-024 | Snippet expansion literal provenance | A[XF-IF-015] C[] B[IF-008] |  | bound |
| XM-IF-025 | Transform definition revision (live row and preserved history) | A[XF-IF-016] C[IF-08] B[] | MERGED-X03, MERGED-X08 | bound |
| XM-IF-029 | Transform task/candidate identity into candidates, preference and export | A[XF-IF-019] C[] B[IF-033] |  | bound |
| XM-IF-034 | Clipboard payload ownership (guarded copy) | A[XF-IF-022] C[] B[IF-019,IF-018] | MERGED-X02 | bound |
| XM-IF-036 | External insertion outcome (InsertionResult) | A[XF-IF-023] C[IF-11] B[IF-014] |  | bound |
| XM-IF-037 | History current final-stage resolution (display final) | A[XF-IF-024] C[IF-13] B[] | MERGED-X06 | bound |
| XM-IF-045 | Internal note arrival/delivery receipt to the coordinator | A[XF-IF-030] C[IF-12] B[] |  | bound |
| XM-IF-048 | Note revision provenance and dictated-edit attribution | A[XF-IF-031] C[IF-17] B[IF-023] |  | bound |
| XM-IF-049 | History Copy/Move into Scratchpad (two-phase receipt) | A[XF-IF-033] C[IF-15] B[IF-020] | MERGED-X10 | bound |
| XM-IF-050 | Explicit Teach source authority | A[XF-IF-034] C[IF-14] B[IF-021] |  | bound |
| XM-IF-051 | Certified edit observation into learning candidates | A[] C[IF-16] B[IF-015] |  | bound |
| XM-IF-052 | Approved learning delta into vocabulary | A[XF-IF-035] C[IF-22] B[IF-031] | MERGED-X01, MERGED-X15 | bound |
| XM-IF-053 | Undo Approval (Hub control over the recorded delta) | A[XF-IF-035] C[IF-22] B[IF-032] | MERGED-X15, MERGED-X01 | bound |
| XM-IF-058 | Shared task qualification / eligibility decision | A[] C[IF-23] B[IF-035] |  | bound |
| XM-IF-059 | Family split membership and forward-only exposure | A[XF-IF-040] C[IF-24] B[IF-034] | MERGED-X01 | bound |
| XM-IF-060 | Dataset snapshot, exact-input fence and publication | A[XF-IF-041] C[IF-26] B[] | MERGED-X14 | bound |
| XM-IF-061 | Self-contained offline package and validator | A[XF-IF-042] C[] B[IF-036] | MERGED-X14 | bound |
| XM-IF-062 | Export Validate result into Hub export-pane state | A[] C[IF-27] B[IF-037] | MERGED-X12, MERGED-X13 | bound |
| XM-IF-063 | Managed artifact file capability for export reads | A[] C[IF-25] B[IF-040] |  | partial |
| XM-IF-064 | Eligible speech cohort (training examples into Your Voice) | A[] C[IF-19] B[IF-029] | MERGED-X07 | bound |
| XM-IF-067 | Historical applied vocabulary into technical terms | A[] C[IF-20] B[IF-030] | MERGED-X11 | bound |
| XM-IF-068 | Terminal usage fact (one logical dictation per job) | A[XF-IF-045] C[IF-18] B[IF-025] |  | bound |
| XM-IF-069 | Note dictation terminal receipt into usage | A[] C[IF-12] B[IF-024] |  | bound |
| XM-IF-072 | Content versus usage deletion and usage-derived profile copies | A[XF-IF-046] C[IF-21] B[IF-028] | MERGED-X01 | bound |
| XM-IF-074 | Status/runbook/registry current-state projection | A[XF-IF-048] C[IF-29] B[] | MERGED-X16, MERGED-X17 | unbound |
| XM-IF-075 | Baseline/config/model/fixture provenance | A[] C[IF-01] B[IF-001] |  | bound |
| XM-IF-078 | Schema version and relational-family integrity (repair authority) | A[] C[IF-28] B[IF-038] | MERGED-X01 | bound |

## A-only rows

| Union | Object | A | Findings | Closure |
|---|---|---|---|---|
| XM-IF-001 | Content-free event envelope (event taxonomy) | XF-IF-001 |  | partial |
| XM-IF-002 | Public Store submission admission (writer op, reply timeout) | XF-IF-002 | MERGED-X08, MERGED-X09, MERGED-X10 | partial |
| XM-IF-007 | Deletion tombstones and in-memory revocation | XF-IF-005 |  | bound |
| XM-IF-009 | Capture-boundary consent snapshot | XF-IF-007 |  | partial |
| XM-IF-012 | Normalization result evidence and retained exact input | XF-IF-009 | MERGED-X05 | bound |
| XM-IF-014 | Normalization edit/lease envelope for History stages and qualification | XF-IF-010 |  | bound |
| XM-IF-019 | Cleanup faithful gate (validation report) | XF-IF-012 |  | bound |
| XM-IF-021 | Cleanup provenance completeness (qualification tier) | XF-IF-013 | MERGED-X05 | bound |
| XM-IF-026 | Transform editor update binding | XF-IF-017 | MERGED-X04 | bound |
| XM-IF-027 | Transform Add outcome identity | XF-IF-018 | MERGED-X08 | bound |
| XM-IF-030 | Prompt Engineer requirement/literal preservation gate | XF-IF-020 |  | bound |
| XM-IF-033 | Insertion admission handshake | XF-IF-021 |  | bound |
| XM-IF-040 | History search versus display lineage | XF-IF-025 |  | bound |
| XM-IF-041 | Hub query publication epoch | XF-IF-026 | MERGED-X12 | bound |
| XM-IF-042 | Rendered detail action identity | XF-IF-027 |  | bound |
| XM-IF-043 | Replay source availability | XF-IF-028 |  | bound |
| XM-IF-044 | Note create with typed outcomes | XF-IF-029 | MERGED-X09, MERGED-X10 | bound |
| XM-IF-047 | Note transform whole/selection acceptance | XF-IF-032 |  | bound |
| XM-IF-054 | Candidate counterexample scope (approval sandbox) | XF-IF-036 |  | bound |
| XM-IF-055 | Training label/span source checks | XF-IF-037 |  | bound |
| XM-IF-056 | Audio-reviewed verbatim gate | XF-IF-038 |  | bound |
| XM-IF-057 | Preference comparability and displayed order | XF-IF-039 |  | bound |
| XM-IF-065 | Profile eligible population on Your Voice cards | XF-IF-043 | MERGED-X07 | bound |
| XM-IF-066 | Profile input-signature and commit fence | XF-IF-044 | MERGED-X01 | bound |
| XM-IF-073 | Read-only/focus-safe Hub publication | XF-IF-047 |  | bound |
| XM-IF-076 | Performance validity versus speed | XF-IF-049 |  | unbound |
| XM-IF-077 | M15 qualification gate | XF-IF-050 |  | unbound |

## C-only rows

| Union | Object | C | Closure |
|---|---|---|---|
| XM-IF-004 | Worker reply bound to its requested attempt (ASR/cleanup result) | IF-03 | bound |
| XM-IF-011 | Canonical scoped vocabulary entry identity (writer-authoritative) | IF-05 | partial |
| XM-IF-031 | Gated transform candidate and explicit Accept into external insertion | IF-10 | bound |

## B-only rows

| Union | Object | B | Findings | Closure |
|---|---|---|---|---|
| XM-IF-006 | Capture job and journal registered into the Store | IF-002  |  | bound |
| XM-IF-016 | Context scope projection into vocabulary/profile scope | IF-005  |  | bound |
| XM-IF-017 | Cleanup context (protected spans, bounded frozen vocabulary, category) | IF-006  |  | bound |
| XM-IF-018 | Insertion target lease | IF-013  |  | bound |
| XM-IF-028 | Transform mode/definition frozen into the transform job | IF-007  |  | bound |
| XM-IF-032 | Validated auto-transform final into insertion | IF-012  |  | bound |
| XM-IF-035 | History Paste Again destination policy | IF-018 (C: SURFACE:History (Paste Again), DESIGN-05) |  | bound |
| XM-IF-038 | Current History attempt (retry stage artifacts vs older training manifest) | IF-016  | MERGED-X06 | bound |
| XM-IF-039 | History Retry command | IF-017  |  | bound |
| XM-IF-046 | Note-bound delivery (dictation/transform into a captured note) | IF-022  |  | bound |
| XM-IF-070 | Explicit activity fact (transform generation, executed repaste) | IF-026  |  | bound |
| XM-IF-071 | Insights report into the Hub pane | IF-027  |  | bound |

## Method notes

- Sites were resolved by symbol within the named enclosing function (census awk indentation map rebuilt from `git archive` of the pinned commit), preferring code lines over comments and docstrings; each resolved line was re-read.
- Two rows (XM-IF-001, XM-IF-002) are too broad to enumerate: they carry a grouped consumer entry with the pinned-commit count (313 emit sites in 148 functions; 142 Store `.submit(` sites in 127 functions) and list the census-classified non-conforming callers individually.
- MERGED-X16 and MERGED-X17 (STATUS `current_state`, M07 runbook checks; decisions D15/D16) have not landed at the pinned commit, which is why XM-IF-074 is unbound. Every other merged finding (X01–X15) touches at least one bound row whose consumers were found at the pinned commit.
