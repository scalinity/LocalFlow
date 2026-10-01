# LocalFlow — Pre-M15 + M15-A Canonical Integration

October 1, 2026. Local integration state:
`PRE_M15_AND_M15A_SETUP_INTEGRATED_READY_FOR_CORPUS_FREEZE`.
Corpus state: `CORPUS_FREEZE_REQUIRED`. This is no M07/M11/M15 acceptance
or model promotion. Main publication here means a local Git merge only.

## Identity and provenance

| Item | Identity |
|---|---|
| Original main | `5da68360a0e5b1ea9303f799ea5c550db4f210fe` |
| M07 exact input | `8c08b82f15e75e83fb06bcd5aa2e102c50761903` |
| M15-A exact input | `9b47e2f72012752b8146f57b3cce0194adfac221` |
| Dedicated branch | `pre-m15-m15a-integration-20261001` |
| M07 provenance merge | `60d7641c655f05cc1725ea00b60c26ba0e0ad6af` |
| M15-A provenance merge | `23acfe5f92d97c1e12b599d2d3d3567e89f9bdc4` |

The final integration/main SHAs are reported after their commits in the owner
handoff; this file does not invent its own future SHA. Both exact inputs and main
were verified before creating the dedicated sibling integration worktree.
Only STATUS.json overlapped; Git merged it without conflict. It was then
reconciled semantically so newer M07 evidence and M15 setup both survive.
No production-code overlap exists between the input branches.

## Preserved M07 behavior and blocker

Engine bytes match the exact M07 input. Standalone `no` / `sorry` admit a
proposal pass only through existing nearby parallel-value evidence. Admission
removes nothing. Parser/protection/offset guards, candidate validation and whole
rollback remain unchanged. Ordinary-prose controls gain no correction calls.
Config, cleanup model, prompts and validation bytes match original main.
Production Qwen control remains pinned to
`50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b` in the configured cache.

Fresh deterministic remediation: 40/40; engine owning suite: 19 tests;
cleanup pipeline: 13/13 with desktop isolation. Normalization pipeline passes
with desktop isolation. Literal owning fixtures were separately checked offline:
20/20, 19 model-path passes and one safety fallback. No live speech occurred.
Deterministic fidelity/protection/correction/rollback checks pass in the engine,
remediation, list and spoken-step owning suites. The full 60-case model fidelity
campaign was not rerun: the input branch's 58/60 and focused correction 6/10
are preserved as historical evidence, not fresh measurements. Both inherited
fidelity failures remain recorded. State stays
`PRE_M15_BLOCKED_M07_V001_MODEL_BEHAVIOR`; **M07 is not passed**.

## Integrated M15-A and validation

Spec, seven-candidate manifest, setup results, runner, adapter, AC09/AC10 and
original handoff are integrated. All seven exact snapshots match manifest file
sizes with required assets/shards present and no incomplete files. No cleanup
weights were redownloaded; their previous compatibility smoke is reused.
The manifest bytes/identities remain those of the exact M15-A input.

The old setup's byte-preservation harness expected the pre-repair engine and
failed after integration. Its assertion now compares the engine to the exact M07
input; config/model/validator still compare to original main. This preserves the
authorized production repair without weakening the default/model invariant.

Harness: 49/49 (the original 41 plus eight corpus-freeze gate regressions).
Introduced-list checks: 12/12; spoken-step checks: 31/31.
Registry and baseline/fixture privacy checks pass. The private corpus gate is
required before every non-smoke runner path. Its model-free freeze/validate
commands lock/recheck manifest identities and all asset bytes; human declarations
are never manufactured by these checks. The blind-queue unit isolates that
mechanic; a separate CLI regression proves unreviewed corpora cannot reach model
work. No finalist review was actually performed.

## Parakeet

Exact repository `mlx-community/parakeet-tdt-0.6b-v3`, revision
`ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15`.
The snapshot existed with weights/config but lacked five support files.
The authorized pinned download reused weights and restored those support files.
Strict HF verification checks all seven Git/LFS file hashes, with no missing,
extra or incomplete files. Logical allocation: 2,509,044,141 bytes;
unique-file allocated storage: 2,509,062,144 bytes. This is snapshot size, not
network-transfer or RAM measurement. The exact global snapshot is recorded only
in private evidence and the owner handoff.

A LocalFlow worker loaded that explicit snapshot with cleanup off and processed
one second of synthetic 16 kHz mono float32 silence. Result is a consumable
string (empty), 16,000 decoded samples and `[[0,16000]]` decode range;
inference 45.8 ms, worker exited 0. This is bounded readiness, not speech quality
or Track B corpus measurement. Initial smoke IPC used the wrong audio field
shape, was corrected, and the successful bounded run is recorded separately;
no production worker code changed. Track B's ASR prerequisite is ready.

## Corpus, private owner work and freeze

See [M15-CORPUS-FREEZE.md](../benchmarks/M15-CORPUS-FREEZE.md) and
[m15-corpus-freeze-preparation.json](../benchmarks/m15-corpus-freeze-preparation.json).
Private evidence is under the established v2-evidence integration folder.

16 retained WAV files: prior 11 plus five live-log files. Thirteen identical-
sample families; further related copies require review. Four all-zero files
represent one sample-identical family, with no approved negative reference.
Confirmed eligible human: 0; adjudicated: 0; unverified audio: 16; confirmed
synthetic: 0; approved negatives: 0. Those zeros are confirmed eligibility
counts, not claims about actual origin. No microphone was used.

The exact historical legacy-log prefix exists and hashes to its established
baseline identity. Sixty unique provisional real-text candidates are privately
queued from that source. Raw inputs are reviewed independently; historical
cleaned output is labeled a candidate and assessed after authoring reference
truth. Family/origin/exposure checks and substitution of unsuitable cases
precede the 30/10/20 lock. There are zero existing confirmed reusable M07 cases;
60 remain missing. No held-out set is falsely declared frozen.

One private queue has 76 items: 16 audio items and 60 legacy items. Additional
recordings are deferred until review. Verified speech deficit is 140 (60 short /
80 diverse), negatives deficit 20; conditional residual estimate is 147–160,
subject to actual distinct-case/family/stratum eligibility. No recording is
commissioned. Text-only legacy cases can satisfy M07 plus M15 Track A once
adjudicated; they cannot fill M15 speech or Track B coverage. References are
reviewed once and reused across all candidates; model outputs never become gold.

Draft/private schema supports opaque ids, families, strata, splits, origin,
audio/normalized/reference/protected-context hashes, adjudication/reference
statuses, all three eligibility flags and privacy class. Missing reference and
normalized hashes are null. Freeze machinery locks the whole private manifest
(including protected/context metadata), input/runtime identity and assets;
family/split/exposure guards stay intact. No freeze lock is written for the
pending review manifest. Current state remains `CORPUS_FREEZE_REQUIRED`.

## Boundaries and next action

No seven-model Track A or B corpus, full M07-V002 evaluation, M07-V001 live retry,
final M11 qualification, finalist selection, model promotion or M16 work occurred.
No build, install, shell/HF configuration change or push. Source branches and
worktrees remain; the canonical checkout is returned to main for its real merge.
No private transcripts/audio/references/candidate outputs or runtime state
entered Git. The existing .gitignore already excludes .claude/.codex and private
artifact types. Existing Gemma community-card/upstream license discrepancy stays
explicit in the original manifest/setup handoff; model notices remain a later
packaging obligation. No third-party code is copied.

**Next owner action:** open the private `OWNER-REVIEW.md` and
`owner-review-queue.json`, adjudicate suitable existing items once, and approve
only the residual missing recordings. Then authorize corpus assembly with one
pinned ASR/normalization pass and the model-free freeze gate. Do not begin
candidate comparison before the gate passes.
