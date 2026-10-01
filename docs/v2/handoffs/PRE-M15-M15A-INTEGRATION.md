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

27 retained WAV files: prior 11 plus five live-log files and 11 live-store
artifacts. Twenty-four sample-distinct families; further related copies require
review. Read-only live-store counts show zero correction labels and preference
observations, ten captured-unreviewed examples and one excluded example. The
existing excluded audio stays excluded; it is not reauthorized by this queue. Four all-zero files
represent one sample-identical family, with no approved negative reference.
Confirmed eligible human: 0; adjudicated: 0; unverified audio: 27; confirmed
synthetic: 0; approved negatives: 0. Those zeros are confirmed eligibility
counts, not claims about actual origin. No microphone was used.

The exact historical legacy-log prefix exists and hashes to its established
baseline identity. Sixty unique provisional real-text candidates are privately
queued from that source. Raw inputs are reviewed independently; historical
cleaned output is labeled a candidate and assessed after authoring reference
truth. Family/origin/exposure checks and substitution of unsuitable cases
precede the 30/10/20 lock. There are zero existing confirmed reusable M07 cases;
60 remain missing. No held-out set is falsely declared frozen.

One private queue has 87 items: 27 audio items and 60 legacy items. Of these,
86 require owner adjudication; one live-store item is already excluded. Additional
recordings are deferred until review. Verified speech deficit is 140 (60 short /
80 diverse), negatives deficit 20; conditional residual estimate is 137–160,
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

## Changes after the integration (2026-10-01)

The integration is published on `origin/main`. Production defaults and the
cleanup model are unchanged. These production changes landed on `main` before
any model comparison ran, so the benchmarks run on them; the benchmark
freeze test pins `engine.py` and `validation.py` to `0441d15` (the last of
the two cleanup repairs) and `config.py`/`model.py` to `3505659`.

- **Cleanup validator** (`3f2f5cc`): the coverage check aligns source words by
  longest in-order match. A greedy cursor counted one dropped repeated word as
  many missing words and sent most windows back to the raw transcript.
- **Cleanup engine** (`0441d15`): a candidate whose only failure is a few
  deleted source words (at most 8 and 10% of the window) is repaired by
  restoring exactly those words and validated again in full. Candidates that
  add words, change numbers or lose negations are still rejected whole.
- **Insertion**: caret delivery to Chromium browsers and any Electron app uses
  the clipboard transaction (their AX writes are acknowledged and ignored; `9ceeb9c`
  and earlier); a paste that landed in a resized field is consumed (`resized`);
  a non-matching readback records content-free `readback_detail`.
- **Hub replay** (`d1bfdfc`): the Play button builds its `NSSound` with
  `initWithData:`; the previous class method did not exist.
- **Capture** (`6d58425`, `428b69d`): `input_device` accepts an ordered list so a
  preferred microphone sits ahead of a headset that is the system default
  (a Bluetooth microphone delivered 0.7-0.8 s of exact silence at the start);
  `capture.start_path` records the key-press timing.

Repository history was rewritten on 2026-10-01 for commit identity. Commit
hashes recorded in these documents before then name pre-rewrite commits; each
has a rewritten twin with the same subject and an identical tree, and a fresh
clone does not contain the originals. `STATUS.json` and the freeze-test pins
name the rewritten commits.

Remaining open work is unchanged: human corpus adjudication and freeze, then
the model comparison. The spoken-correction pass of the 4B cleanup model still
returns bare markers that the deterministic guards reject (measured 6/10), which
is a model-capability limit for the benchmark to address.
