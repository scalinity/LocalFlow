# LocalFlow caller census (read-only)

- Repo: <repo>, branch xm-local-remediation-20260928, HEAD 340c566686c7123bfcf721e16160aacabbe0b97d (working tree clean at start; nothing in the repo was edited).
- File set: `git ls-files` — 91 tracked files under localflow/, 53 under scripts/, 173 under tests/ (291 tracked .py across the three). Production = localflow/ + scripts/; tests/ counted separately. docs/ is not searched except where noted.
- Method: `git grep -n` per symbol over tracked files; enclosing function from an awk indentation map (`Class.method`, nested defs dotted, e.g. `TransformStore.update_transform.op`). Identifier symbols searched as whole words (`-w`), others as substrings. Full rows (file, line, function, kind, line text) are in census.json.

## Counts per symbol (production / test)

| symbol | production | test |
|---|---|---|
| `*_missing_reason` | 51 | 67 |
| `*_not_retained` | 6 | 3 |
| `HistoryQueryService` | 6 | 40 |
| `NoteOutcomeUnknown` | 8 | 1 |
| `ProfileService` | 3 | 49 |
| `STATUS.json` | 0 | 4 |
| `TransformStore` | 3 | 14 |
| `VERIFICATION.html` | 4 | 5 |
| `_CORE_DEPENDENTS` | 3 | 0 |
| `_append_revision` | 3 | 0 |
| `_eligible` | 2 | 7 |
| `_guarded_copy` | 3 | 0 |
| `_job_artifacts` | 3 | 0 |
| `_manifests` | 3 | 0 |
| `_migrate` | 2 | 0 |
| `_refresh_export_pane` | 2 | 0 |
| `_transform_write` | 3 | 0 |
| `add_transform` | 2 | 3 |
| `applied_rule_ids` | 2 | 8 |
| `applied_rules` | 6 | 6 |
| `auto_apply` | 32 | 87 |
| `cleanup_qualification_in` | 4 | 0 |
| `copyLastRaw_` | 1 | 2 |
| `copy_text` | 6 | 1 |
| `create_note` | 15 | 177 |
| `delete_everywhere` | 15 | 249 |
| `expected_revision` | 56 | 7 |
| `exportValidate_` | 1 | 0 |
| `final_text` | 19 | 21 |
| `generation` | 263 | 462 |
| `hubSaveHistoryRow` | 2 | 15 |
| `job_detail` | 4 | 31 |
| `learning_vocabulary_deltas` | 7 | 5 |
| `missing_reason_fields` | 106 | 102 |
| `missing_reasons` | 26 | 53 |
| `model_task_complete` | 5 | 12 |
| `move_failed_note_copied` | 2 | 2 |
| `normalization_ledger` | 6 | 7 |
| `normalized_text` | 17 | 18 |
| `on_normalization` | 5 | 8 |
| `operation_id` | 48 | 164 |
| `outcome_unknown` | 8 | 3 |
| `pasteboard` | 26 | 40 |
| `profile_evidence` | 12 | 11 |
| `publish_op` | 2 | 1 |
| `retention_failed` | 2 | 0 |
| `submit` | 237 | 484 |
| `tfSaveToScratchpad` | 2 | 1 |
| `training_memberships` | 22 | 39 |
| `transform_revisions` | 6 | 3 |
| `transformsAdd_` | 1 | 0 |
| `transformsToggle_` | 1 | 0 |
| `transformsUpdate_` | 1 | 0 |
| `undo_approval` | 1 | 39 |
| `update_transform` | 4 | 29 |
| `usage_facts` | 70 | 63 |
| `validate_dataset` | 10 | 28 |
| `transformsDelete_` | 0 | 0 |
| `M07-V` | 0 | 0 |

Notes on the counts:
- `transformsDelete_` has no tracked occurrence anywhere. `TransformStore.delete_transform` (transforms_store.py:313) exists but has no production caller.
- `M07-V` appears only in docs/v2/VERIFICATION.html:2514 (placeholder "IDs from M07-V001"). `STATUS.json` has 0 production hits (4 in tests).
- `undo_approval`: 1 production hit — the definition `LearningService.undo_approval` (learning.py:852). No UI or script caller; 39 test hits.
- `copy_text`: there is no `InsertionService.copy_text`. Every occurrence is `localflow/inject.py:copy_text` or its import/uses in app.py.
- Broad symbols carry false positives: `generation` (worker generations, pasteboard generations, UI request generations), `final_text` (local variables in learning.py `teach_correction.op`), `normalized_text` (a parameter name in cleanup/engine.py:371), and `missing_reason_fields` (its regex also matches any `"missing"` string literal). `submit` includes `InsertionService.submit` (app.py:1698, 4753) and `QueryExecutor.submit` (ui/state.py:120, 944), which are not Store calls.
- The "missing reason" fields the evidence collector writes (localflow/v2/training.py): `missing_reasons` envelope dict (1244-1246, 1291-1313, 1328-1332, 1782), `normalization_missing_reason` (228, 705, 1705-1709), `hint_set_missing_reason` (475, 1729-1736), `applied_rules_missing_reason` (776), `destination_missing_reason` (1747), `asr_*` via `caps.missing_reason_for` (1605-1610), plus emit outcomes `*_not_retained` (471, 531, 585, 629, 709, 783). The only reader in curation is `model_inputs_missing_reason` at curation/evidence.py:182; training_data.py reads them at 214, 296, 344-366, 756. `retention_failed`: app.py `_retention_pass` (event `store.retention_failed`) and training.py `retention_failed_step`.

## Clipboard writers that do NOT go through the guarded path

The guard is `AppDelegate._guarded_copy` (localflow/app.py:1732-1744). It refuses while `self._insertion.pending` or `.clipboard_payload_pending`, and otherwise calls `inject.copy_text`.

1. **localflow/app.py:5991 `AppDelegate.copyLastRaw_`** calls `copy_text(self._last_failed["raw"])` directly. It is reached from the menu item "Copy Raw Transcript of Last Failure" (app.py:5182). It checks `_job_is_deleted` first, but it skips the insertion-ownership guard.
2. **localflow/app.py:4726 `AppDelegate._finishWithText_`** calls `copy_text(text)` directly when `self._insertion is None`. In that state the guard would pass anyway, but the call still bypasses the helper.
3. **localflow/inject.py:26 `paste_text`** writes the general pasteboard at lines 34, 46 and 63-64 (the last from a restore daemon thread), with no guard. No tracked production code imports it; app.py:51 imports only `copy_text`. It is dead code that still writes.
4. The **InsertionService** paths do not use `_guarded_copy` because they own the clipboard: `ClipboardTransaction.publish` (insertion/clipboard.py:95, from service.py:877), `restore_if_owned` (clipboard.py:125), and `_copy_offer` (service.py:1075) and `_offer_recovery` (service.py:1125). The last two are gated on the service's own `_resolve_pending()` late-consumer check. The primitives are `SystemPasteboard.clear_and_write_text`/`clear_and_write_items` (insertion/hosts.py:239, 245).

These go through `_guarded_copy`: `tfCopyTransform` (app.py:1725) and `hubCopyText` (app.py:5418). `hubCopyText` is reached from hub.py:899 `historyCopy_` and from app.py:5439/5445 `hubPasteText` fallbacks. The script sites are stubs or a private pasteboard: benchmark_m08.py:1270 uses `pasteboardWithUniqueName`, and benchmark_m03.py:128 and m03_remediation_repro.py:212 replace the helpers with stubs.

## UI / controller callers that collapse TimeoutError into failure (or do not handle it)

`Store._submit` raises `TimeoutError("store writer did not respond")` without cancelling the op (store.py:1259-1277). Only one UI/controller site calls `store.submit` directly: app.py:5905 `_retry_job` (a read). It hits `except Exception` at 5909 and emits `usage.retry_provenance_unavailable`. Every other site reaches the store through a service. Handling is typed (a), collapsed into a failure (b), or absent (c).

**(b) TimeoutError reported as a failure:**
- dictionary_panel.py `addEntry_` 249/276, `approveEntry_` 295/300, `toggleEntry_` 309/313, `pinEntry_` 322/326, `deleteEntry_` 335/340. Each is `except Exception as e:` → "not added/approved/toggled/pinned/deleted: {e}". VocabularyStore does not convert TimeoutError.
- hub.py `_transform_write` 1863/1874 → `except Exception as e:` at 1881 → "not saved: {type(e).__name__}". `transformsToggle_` 1897 → 1898 "not toggled". TransformStore has no TimeoutError conversion and no expected_revision.
- hub.py `reviewMine_` (3369, `_in_background`): done() shows "action failed: …" (3358), with no TimeoutError branch.
- hub.py `voiceGenerate_` (4101, `_in_background` → ProfileService.compute): "generation failed: …" (4092).
- hub.py `_settings_call("Changing collection", hubSetCollection)` (4488): `except Exception as e:` at 4455 → "{what} failed (TimeoutError) — nothing changed on screen". `ConsentManager.set` queues `append_consent` with wait=False, then `snapshot_now` reads with a wait. A timeout there is shown as failed even though the consent write may commit.
- app.py `tfSaveToScratchpad` 2045 → `except Exception as e:` at 2053 → `notes.note_create_failed`. This collapses NoteOutcomeUnknown.
- app.py `hubSaveHistoryRow` Move: `store.delete_everywhere` at 2172 → `except Exception as e:` at 2175 → `move_failed_note_copied`. The deletion may still commit.
- app.py `importDictionaryJSON_` 5707 → 5713 `vocabulary.import_failed`.
- Background (log only): app.py `_profile_idle_compute` 2743/2744 and `_retention_pass` 2752-2764/2766 (`store.retention_failed`). Also `hubApplyUsageRetention` `pending_expiry` read at 6082.
- Inside the service: training.py:1565 `mark_last_correct` → `capture_failed`, `annotation_not_recorded`.

**(c) No handling at the UI site:**
- app.py `toggleTrainingCollection_` 5252 and `toggleTrainingPause_` 5260. `consent.state()` and `consent.set` read the store with a wait.
- app.py `excludeLastDictation_` 5264 (`store.latest_example` with a wait) and `markLastCorrect_` 5267.
- ui/scratchpad.py:185 `_mark_dirty` (wait=False, `except Exception: pass`).

**(a) Typed unknown outcome:**
- hub.py `historyTeach_` (1007).
- `_usage_mutation` (app.py:6108).
- `_m10_add/_update/_delete/_toggle`, which branch on profiles_store.OutcomeUnknownError at hub.py:1380.
- The Scratchpad note actions via `_scratchpad_outcome`/`failure_kind`.
- `_training_action` (hub.py:3117/3128), covering mark_intended, pin, exclude, delete_everywhere, sampling refresh, approve, reject, record_label, record_pair_judgment, assign, mark_exposed, validate_dataset and exclude_evidence.
- `trainingVerbatim_` (3275) and `trainingSpan_` (3324).
- `exportRun_` (3580).
- `hubSaveHistoryRow` create (2158).
- `NotesEditorModel._persist` (notes.py:1358).

## NoteOutcomeUnknown

- Raised by NoteStore in four places: `create_note` (notes.py:497), `restore` (555), `set_pinned` (570) and `add_attachment` (675).
- Handlers: no production code has `except NoteOutcomeUnknown`. Every handler classifies through `failure_kind` (notes.py:285):
  - app.py:2158 `hubSaveHistoryRow` → `create_unknown` (returns note_id).
  - hub.py:2090 `_scratchpad_outcome`, used by scratchpadNew_ 2114, Pin 2130, Attach 2184, Restore 2260 and Delete 2325.
  - notes.py:1359 `NotesEditorModel._persist`.
- Collapsing handler: app.py:2053 `tfSaveToScratchpad` (generic except → failed).
- Stable ids across retries:
  - Stable: `_commit_typed` (rid per edit generation, notes.py:1395) and `_commit_arrival` (arrival.revision_id).
  - Not stable: `tfSaveToScratchpad` (no note_id; a retry can duplicate). `hubSaveHistoryRow` allocates a new id per call (app.py:2152), and hub.py:1096 does not keep it. `scratchpadAttach_` passes no attachment_id. `scratchpadRestore_` allocates a new_revision_id per press.
  - `scratchpadNew_` preallocates per press (by intent).

## Store openers with no backup_dir

- Production app: localflow/app.py:241 `AppDelegate.configure` passes `backup_dir=V2_BACKUPS`. This is the only Store opener in localflow/.
- Real-store scripts all pass backup_dir: export_dataset.py:42 and import_legacy.py:41 (both default to ~/Library/Application Support/LocalFlow/v2.db), and m09_trial_seed.py:177 (a sandbox home; it refuses the real home).
- No backup_dir, all on temp dirs:
  - benchmark_m02.py:174, 238, 292
  - benchmark_m05.py:161
  - benchmark_m12.py:219, 258, 291
  - m02_remediation_repro.py:289 (inside a child-process f-string), 299, 817, 825, 830, 836
  - m04_remediation_repro.py:403
  - m05_remediation_repro.py:114, 984, 1047, 1238
- Without backup_dir, a pending upgrade migrates and only emits `store.migration_backup_skipped` (store.py:1356-1365).
- Indirect openers: benchmark_m03.py:76 and m03_remediation_repro.py:199 construct AppDelegate after patching V2_DB/V2_BACKUPS to a temp dir. Scripts that add tests/v2/* to sys.path open stores inside test harnesses (backup_dir UNKNOWN; not enumerated).

## Direct SQL outside store.py

- There are 469 `.execute/.executemany/.executescript` call sites in production: 394 in localflow/ and 75 in scripts/. Receivers in localflow/ are `conn` (271), `db` (106), `cur` (12), `c` (4) and `con` (1). Almost all are inside store-writer ops.
- Raw `sqlite3.connect` outside store.py:
  - importer.py:55, 57, 81 (legacy import)
  - snapshot_user_data.py:161, 163, 322
  - several repro/benchmark scripts on temp copies; m03_remediation_repro.py:848 connects to app_mod.V2_DB after patching it to a temp path
- Cross-module writes worth noting:
  - analytics.py `conn_redact_usage_copies` UPDATEs `profile_snapshots` (282/299)
  - notes.py writes `learning_candidates`
  - curation/review.py and curation/sampling.py write `training_examples`
  - transforms_store.py `record_candidate` reads `notes` and `consent_revisions` (456, 466)
  - curation/evidence.py:215 reads `transform_revisions` directly
  - export.py and training_data.py read `training_memberships` directly rather than through SplitService
- Table names come from a heuristic parse of the SQL literal. Dynamic-SQL sites were resolved by hand; generic query helpers in scripts are marked DYNAMIC.

## Emitters

- There are 321 `*emit*(` call sites: app.py 206, supervisor.py 24, training.py 20, store.py 11, context/collector.py 11, insertion/service.py 9, training_data.py 7, learning.py 6, analytics.py 6, others ≤2, and scripts 12.
- 83 sites pass free text: 79 through `detail=` and 4 through `**kwargs`. None use `message=` or `text=`.
- `detail` is stored verbatim (eventlog.py:126-148, with no sanitizer). Notable free-text details:
  - store.py:1241 `detail=err[:200]` (exception text)
  - capture_journal.py:346 `detail=reason + …`
  - supervisor.py:355 `safe_type(...)`
  - context/collector.py:324 `_coverage_detail(snap)`
  - app.py:6109 `detail=name`
  - app.py:247/260/453 `detail=key` (config keys)
  - analytics.py:848 joined reasons
  - store.py:1440 joined table names
  Most other detail values are counts or ids.

## File read/unlink helpers (production localflow/)

- By kind: unlink 25, os.open 23, read_text 15, read_bytes 9, open-read 4, open-write 4, open_managed_file 2, read_managed_file 1, unlink_managed_file 2, and shutil.rmtree 2 (both in curation/export.py:773 and 794).
- Managed-file helpers are defined at store.py:771/805/834. They are used by curation/evidence.py:111, curation/export.py:818, notes.py:469/681 and store.py:2674.
- User-path reads outside the managed helpers:
  - hub.py:2179 `scratchpadAttach_` `read_bytes` of a user-chosen file
  - snippets_store.py:304 and vocabulary_store.py:789 `import_json`
  - config.py:163
  - app.py:2975, 5679 and 6059 (override JSON)
  - importer.py:79, 128, 153, 183
  - curation/export.py `validate_dataset` reads a user-chosen dataset directory (1172-1173, 1512)

## Other surprises

- `HistoryQueryService` is built ad hoc inside app.py:2127 `hubSaveHistoryRow` (a fresh instance per call) in addition to the Hub's `history_service` (app.py:5312).
- `TransformStore.update_transform` takes no `expected_revision`, unlike the rule, snippet and vocabulary stores. The UI transform writes (hub.py:1863/1874/1897) have no typed unknown outcome.
- `validate_dataset` is named in a user-facing string in training_data.py:862 (`TrainingDataService.readiness.op`).
- `on_normalization_result` has one production caller, app.py:4130 `_worker`. It writes the `normalized_text` and `normalization_ledger` roles (training.py:669/680) and `vocabulary_applied_rules` (760).

## Could not determine (UNKNOWN)

- Whether each background or service call can actually hit the wait timeout for a given op. The classification is by exception-handling shape, not by measured timing.
- Store openers inside tests/ harnesses that scripts import via sys.path (benchmark_m06/m08/m09/m13, m05/m06 repro, measure_m07_cases). They were not traced.
- The enclosing-function map is indentation-based. Lines inside multi-line strings that dedent below their block could be attributed to an outer scope (`<module>`). No such case was observed in the rows cited here.
