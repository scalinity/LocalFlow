# LocalFlow V2 — M03 Read-Only Deep Audit
## Resilient Capture and Restartable Inference

**Repository:** `scalinity/LocalFlow`  
**Audited branch:** canonical `main`  
**Audited commit:** `2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e`  
**Assessment type:** source-grounded retrospective audit; deterministic reproduction designs, not executed test results  
**Verdict:** **C — Significant capture/worker lifecycle weaknesses**

## Executive Assessment

M03 has a sound architectural direction—parent-owned insertion, a spawned model process, explicit request IDs, a bounded journal queue, float32 audio, and conservative capability claims—but several boundaries do not enforce the guarantees that the current contracts describe. The highest-risk paths are **recovery taking live work**, **deleted work being recreated or delivered by outside-store producers**, and **worker lifecycle state being changed by the wrong generation or after shutdown**.

This report identifies **17 material source findings: 2 Critical, 10 High, and 5 Medium**, followed by **6 test gaps** and **4 design concerns requiring adjudication rather than automatic code changes**. There are no separate Low-severity production findings. Severity describes the demonstrated failure mechanism under its stated preconditions, not an observed incidence rate on Daniel’s machine.

The findings are not a claim that ordinary dictation always fails, that an installed app lost data, or that M01/M02 remediation was unsuccessful. M02’s durable store protections are present. The problem is that M03 owns additional live state and temporary files that do not all participate in those protections. Passing happy-path or synthetic-worker suites cannot establish the missing ownership invariants.

**No repository tests, native tests, or model benchmarks were executed during this audit.** Every reproduction below is an actionable design for the remediation session. Source-established defects and conditional risk assessments are distinguished throughout. Historical acceptance results are evidence of their recorded runs, not newly reproduced results.

## Audit Boundary

> This audit covers committed GitHub state at `2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e`. Any uncommitted local state is outside the audit boundary.

The attached audit brief defines this as the third read-only pre-M15 milestone audit. M03 alone is evaluated; M01/M02 addenda are inherited contracts, and later milestones are inspected only at interfaces that consume M03 state. No GitHub file, branch, commit, issue, pull request, test, or documentation was changed. The report and handoff are separate deliverables, not repository edits.

The repository was inspected through the connected GitHub reader with commit-pinned file reads. No reliable executable repository checkout was available in the analysis runtime, so no fabricated pass/fail counts or reproduced crash traces are supplied. Native AppKit/PyObjC, microphone, TCC, Fn/mouse, sleep/lock, MLX/Metal, model-cache contents, APFS behavior, and performance remain outside this execution boundary.

## M01/M02-Remediated Main Baseline

The branch lookup returned the exact orientation SHA in the brief, and a second lookup at the end of the audit confirmed that main remained at that SHA. Commit comparisons established accepted M01 and M02 ancestry; `main` directly follows the accepted final M02 production repair. The M02 remediation evidence file and current shared verification page were read at the audited commit.

| Role | Full commit |
|---|---|
| M01 accepted production repair | `3db74061f23001b9cce3d4fe029e0b30cbc295d6` |
| M01 documentation/evidence head | `3ae0070d84730f8d750440f51097c4a53ff8bf02` |
| M02 first production repair | `dc3b17e60fe017494acdaddf701fd437e2527678` |
| M02 final production repair | `bfbc63c35efa6273cc13242d54d3e5bbe264b21e` |
| Audited main / M02 documentation-evidence head | `2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e` |

The M01 production repair is five commits behind the audited main with no divergent commits; the M02 first repair is three commits behind it with no divergence. The current M02 evidence is `docs/v2/acceptance/M02/remediation/portable_tests_bfbc63c.json`; it records cloud results on its named repair SHA, not on an inferred local build. `docs/v2/VERIFICATION.html` is present and carries the existing revision/history/localStorage scheme.

Inherited contracts preserved in this assessment: schema v11; committed deletion barriers and post-commit purge intents; acknowledged atomic evidence publication; immutable revision extension; capture-time consent snapshot; recovery collection only with original permission and collection enabled now; independent retention interests; and store/event admission-close/drain semantics. **The store is durable truth; events are diagnostic.**

The optional store `expected_attempt` fence is not treated as a missing feature everywhere. Finding 03 proves a stale **reader finalizer** at the supervisor ownership boundary. Finding 05 proves incomplete transport of a **failed retry’s execution identity**. Neither proves that every FIFO app transition needs speculative store fencing. A repair must coordinate acknowledged attempt admission before expanding those fences.

## M03 Responsibilities

M03 owns capture acquisition and teardown, incremental crash-recovery audio, worker-input lifetime, spawned model-process lifecycle, request/generation/attempt transport, one automatic retry policy, circuit-breaking, cancellation’s output authority, readiness/fallback honesty, trigger/watchdog integration, and the audio/capability metadata that later consumers rely on.

It does not own re-auditing cleanup semantic quality, target certification, analytics formulas, learning-policy quality, or model ranking. Those consumers matter here only when a faulty M03 identity, audio source, lifecycle state, or authority decision crosses their interface.

## Current Worker/Capture Architecture

```text
PTT DOWN (parent/UI)
  ├─ mint job/family; create store row; snapshot consent
  ├─ show capture state; start Recorder
  └─ float32 callback blocks
       ├─ in-memory captured frames → normal inference source
       └─ bounded journal queue → .blk records → crash recovery source

Release / forced capture end
  ├─ stop stream; bounded journal finalization
  ├─ enqueue parent job/context/audio
  └─ single parent coordinator
       ├─ publish permitted original-audio evidence
       ├─ write parent-owned worker WAV
       ├─ supervisor: req_id + job + attempt + generation
       │    └─ spawned worker: load → ASR / cleanup / transform → data/fault
       ├─ preserve stage artifacts and terminal evidence
       └─ parent final callback → serialized insertion service / saved output

Restart recovery
  .blk / WAV + store row → recovery item → explicit retry
```

| Concern | Parent owns | Worker owns | Present limitation |
|---|---|---|---|
| Identity | Logical job/family; request minting; requested attempt/generation | Echoed execution fields | Pending entry lacks immutable expected job/attempt/generation/type |
| Audio | Capture memory, journal/WAV names, retention/deletion | Opens submitted WAV | File confinement/completeness and recovery provenance incomplete |
| Models | Configuration and restart policy | Model instances and execution | Loader blocks dispatch; fatal failures can be downgraded into reusable state |
| Output authority | Cancellation, delivery, target/insertion service | No insertion operation | Deletion does not revoke all cached parent delivery paths |
| Durability | Store, event writer, journal producer | No durable-store writes in inspected protocol | Outside-store payloads and late producers can escape orderly closure |

Normal processing correctly uses the **full in-memory capture**, not the potentially degraded journal. This is an important strength. Crash recovery, however, can use only the retained prefix/segments; its status and original positions must remain distinct from a complete live capture.

## Historical Review Findings Considered

The M03 handoff reports earlier repairs for the hands-free/watchdog interaction, recovery scope, spawn races, stale generations, cancellation/WAV ownership, loading fallback, trigger cross-talk, privacy, and unrecoverable-state naming. Those claims were treated as historical evidence, not current proof.

Several repairs are visible: ordinary hands-free ignores release watchdog semantics; the watchdog selects the capture trigger; cancellation keeps input alive until the coordinator finishes; stale result generations are checked; cleanup reports explicit paths; and unsupported ASR capabilities remain reasoned False/null.

The new counterexamples are narrower or cross-boundary: the **block** scan is not protected by the **WAV** scan’s boot filter; old-reader **finally** is not protected by result-message checks; automatic retry/shutdown do not share the normal spawn lock; and M02’s debug-copy guard does not guard every M03 temporary WAV. The first short cancelled job in a double tap is not filed as a defect by itself.

The original native checks—mic unplug/replug, Fn during processing, quit/reopen recovery, and native hands-free/mouse firing—remain historically pending in the inspected M03 records. No later native success is inferred from static code or cloud evidence.

## Worker Protocol Assessment

The protocol uses an unsigned four-byte big-endian length and JSON. A negative wire length is not representable; zero and lengths over 64 MiB are rejected. The worker reads exact byte counts. The parent consumes framed payloads, discards unparseable JSON for that frame, and terminates its reader on invalid lengths/EOF. A malformed body with a trustworthy length need not desynchronize later frames; a corrupted length or partial outbound write is a different failure class.

Useful protections exist: no insertion opcode, minted request IDs, unknown/duplicate result discard, and current-reader plus echoed-result generation checks. Missing defenses include full request/response shape and version validation, immutable expected response identity, generation-owned fault/finalizer resolution, outbound write-all, and explicit per-generation framing failure disposition. See 03, 13, 14, and 16.

## Request / Attempt / Generation Identity Assessment

The intended identity is `job_id + req_id + attempt + worker_generation`. Successful ASR/cleanup results and M02 collector stage-generation fields carry much of it. Faults and pending ownership do not carry enough of it. Successful automatic retries advance app/context metadata; failed automatic retries can leave the app at the earlier attempt.

Ordinary duplicate responses cannot create a second accepted result because the first resolution removes its req_id. A late timed-out result cannot satisfy a new UUID request. This does not protect against an old finalizer clearing all requests or a response with a live req_id but wrong expected metadata.

No confirmed old-attempt parent callback was found that independently justifies wiring `expected_attempt` into every store transition. The concrete stale-parent path is the old **generation reader**. Fix the ownership and acknowledged execution identity first.

## Supervisor / Retry / Circuit-Breaker Assessment

The ordinary GPU request mutex serializes ASR, cleanup, and shared transforms. Normal ensure-running is protected against two simultaneous initial callers. Automatic retry makes a fresh request identity and increments its payload attempt; successful recovery uses a new generation.

Lifecycle operations bypass that otherwise useful serialization. The breaker counts request-level failures and resets on results, not every idle process death. Engine-load failure is represented without an endless automatic loading loop, which is desirable. However, an old reader can cause a false death, a fatal cleanup exception can be represented as success, and the second failing generation can remain alive. Therefore the three-death rule is not verified correct under adversarial interleavings merely because the sequential breaker test passes.

Timeout is not user cancellation. The supervisor removes a timed-out request and its eventual response becomes unknown; first-failure policy can kill and retry. The second-failure path needs explicit retirement. Request timeout also does not bound every prior loader wait or blocking pipe write. Manual close must revoke retry authority rather than look like another recoverable inference fault.

The code budgets a retry per supervisor request/stage. Whether the canonical user-facing contract intends one per whole dictation is recorded as Design Concern 24, not silently decided by this audit.

## Capture Journal / Crash-Recovery Assessment

The journal queue is bounded and the disk writer is separate from the callback. Block payload writes loop for complete progress; disk errors visibly degrade crash recovery while the normal in-memory path can continue. These are useful mechanisms.

The remaining hazards are ownership before scanning, footer/sequence/gap validation, incomplete worker-WAV publication, metadata loss between reconstruction and retry, and cleanup racing a still-live journal writer. `finalize(timeout)` deliberately allows the caller to proceed while a writer finishes; consumers must not interpret that as a completed journal. `close_discard()` can time out and unlink before a delayed writer opens the path, allowing a cancelled journal to reappear. Include that boundary in the ownership repair for 01/04/08 rather than creating a second independent cleanup policy.

Process-crash persistence here means bytes handed through direct file writes to the operating system; it is not a demonstrated per-block power-loss guarantee. No per-callback fsync is demanded. Footer completion, captured-speech completeness, file-integrity verification, and physical-storage durability are separate claims.

## Cancellation / Insertion-Authority Assessment

The worker cannot directly insert or mutate the durable store through its protocol. Ordinary user cancellation marks the parent job, keeps its input alive during execution, and is checked after stages and again at final delivery. The failure path checks cancellation before creating ordinary recoverable-failure behavior. These source paths address both cancel→fault and fault→cancel reasonably, subject to deterministic execution coverage.

Cancellation while an insertion transaction already physically runs is not equivalent to cancellation before transaction admission; the downstream code explicitly recognizes that distinction. This audit does not promise that an already-posted OS write can be recalled.

Deletion is a different authority signal and is not wired through these cancellation checks. See 02. No normal duplicate-frame double-insertion path was proven. For usage, the inspected producer routes one logical job to an upsert keyed by job_id; this is stronger than counting worker result messages. It cannot correct wrong attempt metadata supplied by 05.

## Sleep / Lock / Trigger Assessment

Sleep/lock handling aims to stop capture and retain a prefix; wake does not intentionally reopen the microphone. Ordinary hands-free and trigger-aware watchdog behavior is present. Device-health checks detect callback/stream problems and trigger completion.

The weak cases are stream teardown exceptions, forced-stop latch cleanup, idle mouse-held reconciliation, and recovery metadata lost on forced capture end. Lock/unlock observation also deserves a native check: the inspected app registers a resign-active notification and uses wake to re-arm observation, but this is not proof of correct real lock/unlock notification coverage. No physical macOS notification behavior was executed or inferred.

## Audio Fidelity / Capability Assessment

Original managed audio is encoded as little-endian IEEE float32 with sample count, rate, mono channel metadata, and hashes. PCM16 requires a parent artifact, has a distinct artifact kind, and is labeled lossy/quantized. Existing complete-file fidelity tests make meaningful positive comparisons.

Those strengths do not establish a complete original capture after journal gaps or WAV truncation. ASR segment ranges are half-open and originate in the adapter’s actual slices, but the bounds test never sends its invalid range into production. Recovery may change the interpretation of rate/time/continuity before those ranges are joined to an “original” artifact. See 08–10 and Test Gap 20.

The current manifest remains conservative: contextual biasing, key terms, language hints, word timestamps, confidence, n-best, token log probabilities, and independent ITN are not qualified as exposed support. Offered unsupported hints are explicitly ignored; zero offered hints are not counted as ignored. No new capability is inferred from model-family marketing or internal token timing availability.

## Engine Readiness / Fallback Assessment

Readiness messages have a generation guard. A suspected deferred UI callback bug was narrowed: `_setEngineStatus_` reads the supervisor’s current state rather than blindly trusting the old callback’s state argument. That is a strength, not a finding.

The serious issue is serviceability: ASR-ready during a synchronous cleanup loader does not mean the process can read an ASR request. A basic-now result cannot be dispatched while the serial load loop is blocked. The fake test’s loader behaves differently. Once an actual cleanup result exists, path/fallback fields are generally explicit; the defect is timing and fatal-runtime classification, not a blanket assertion that basic text is routinely labeled LLM output.

The parent forces `HF_HUB_OFFLINE=1` in the worker environment before model imports, overriding an inherited zero. The inspected worker loaders use that subprocess path. No cloud fallback was identified in this M03 path. This establishes configured offline intent, not a packet-capture test or certification of every dependency version; missing-cache and actual model loading remain reference-Mac checks.

## M02 Deletion / Shutdown Compatibility

M02’s row/artifact/revision guards, acknowledged publication, and purge-after-commit ordering are present. Its store rejects new work once closing, and its event writer has an admission boundary. M03 must stop being a producer before those layers are closed; it currently does not fully do so.

A safe target order is: **close app/trigger/request/retry admission → stop capture and preserve/finalize its audio under an explicit deadline → revoke or settle queued inference/delivery → retire/reap the worker and its readers, and stop remaining producers → close store admission and drain accepted writes → emit final bounded shutdown status → close/drain event admission.** Any deadline-exhausted component must report unresolved work honestly and lose permission to start new work. Do not block a main-thread shutdown waiting on a callback that itself requires that main thread.

Deletion requires a similarly explicit ownership protocol for worker/recovery files. Merely registering the journal directory catches existing files, not files produced afterward. A pre-write `job_deleted` check alone is insufficient if deletion can win between the check and publication. See 02 and 04.

## Test-Oracle Assessment

| Suite | What its inspected oracle establishes | What it does not establish |
|---|---|---|
| `test_worker_protocol.py` | Actual supervisor plus synthetic subprocess framing, ordinary results, selected sequential retry/breaker/stale-result cases | Old-reader finalizer races, close/restart admission, production loader serviceability, full identity/schema/short-write matrix |
| `test_capture_journal.py` | Complete writer/reader round trip, a torn tail, queue bounds, explicit degraded flag | Independent format integrity, persisted gaps, live-owner exclusion, real Recorder survival on disk failure, late writer recreation after discard |
| `test_audio_fidelity.py` | Complete f32/PCM16 artifacts, parent/kind/lossiness, selected manually supplied metadata and capabilities | Production rejection of its invalid range, truncated WAVs, worker-input/evidence byte identity through recovery |
| `test_lifecycle.py` | Production delegate methods with synthetic collaborators for selected state paths | Real audio API failures or hardware; deterministic multi-thread shutdown; production IPC in its fake-supervisor cases |
| `test_worker_live.py` | When actually run with models: real worker startup/ASR/cleanup and a new worker after an idle kill | Active-request worker death/automatic retry; startup basic-now interval; current native certification |
| M02 remediation collector/store tests | Real store/collector deletion, consent and atomicity boundaries in their fixtures | M03 outside-store WAV publication and physical output revocation |
| `test_m02_app_wiring.py` | AST call presence/order | Successful execution of failure branches or proof that producers are stopped |
| `benchmark_m03.py` | Separately labeled fake/harness timings and optional real worker startup/idle-kill RSS observations | Active-fault retry certification; enforced failure of every missed budget; a real native event-to-visible-frame measurement |

The benchmark’s main returns zero after emitting a report even when a Boolean budget field is false; its real-worker path uses an idle kill. The hotkey harness measures the synchronous method return after an overlay-visible assertion, not native compositor presentation. These are measurement/acceptance-oracle limits, not proof that the measured values themselves are fabricated.

## Finding Register

| ID | Severity | Finding |
|---|---|---|
| M03-AUDIT-01 | CRITICAL | The block-journal recovery pass can claim live or already-resolved work |
| M03-AUDIT-02 | CRITICAL | M03 can recreate job audio or deliver output after delete-everywhere |
| M03-AUDIT-03 | HIGH | An old reader finalizer can fail a new generation’s request |
| M03-AUDIT-04 | HIGH | Restart, automatic retry, and shutdown do not share a closed, serialized lifecycle |
| M03-AUDIT-05 | HIGH | A failed automatic retry loses the attempt identity that actually executed |
| M03-AUDIT-06 | HIGH | Fatal model failure can leave the damaged generation reusable |
| M03-AUDIT-07 | HIGH | “Basic now” and bounded cleanup hold are not implemented by the production load loop |
| M03-AUDIT-08 | HIGH | Journal reconstruction lacks integrity, gap, and finalization validation |
| M03-AUDIT-09 | HIGH | Recovery retry reconstructs new capture metadata rather than preserving the original capture |
| M03-AUDIT-10 | HIGH | A partially written worker WAV can be accepted as complete audio |
| M03-AUDIT-11 | HIGH | Audio stream start/stop exceptions bypass capture cleanup and prefix preservation |
| M03-AUDIT-12 | HIGH | Worker exception text is mislabeled as a content-free reason code |
| M03-AUDIT-13 | MEDIUM | Protocol identity and framing defenses are incomplete |
| M03-AUDIT-14 | MEDIUM | The audio-root check accepts symlinks and nonregular inputs |
| M03-AUDIT-15 | MEDIUM | Forced capture ends and lost mouse releases leave trigger state behind |
| M03-AUDIT-16 | MEDIUM | Fault diagnostics can raise TypeError, and the parent stderr bound is only a line count |
| M03-AUDIT-17 | MEDIUM | The insertion-service-unavailable fallback never retires its active job |

## Critical Findings

### M03-AUDIT-01 — The block-journal recovery pass can claim live or already-resolved work

**Severity:** CRITICAL  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Capture ownership / recovery / data loss

**Canonical requirement.** S06 and S25 single-instance/ownership reliability; S09 crash recovery; M03-AC03. Recovery must not take an active capture or treat an already-resolved job as unfinished.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/app.py` — 1810–1960, _recover_journals; startup scheduling around applicationDidFinishLaunching_. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `localflow/v2/capture_journal.py` — reconstruct and unfinished_journals, 224–287. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/capture_journal.py)
- `localflow/v2/store.py` — _write_wav, 789–795. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/store.py)

**Current behavior.** The .blk pass scans job-*.blk without a current-boot, live-owner, deletion, or resolved-state exclusion. The later WAV-only pass has a current-boot check; that check does not protect the earlier block pass. The block pass reconstructs to the job-named WAV and unlinks the block file. It can overwrite an existing WAV.

**Failure mechanism.** A startup scan delayed until the first capture has opened its journal can mistake that live file for crash residue. A second process presents the same risk because a different boot_id is not proof that the first owner has exited. Removing an open journal pathname allows the writer to continue on an unlinked file; a subsequent crash loses those later samples. Separately, a stale, degraded journal can overwrite a fuller existing worker WAV, and a leftover journal for a completed job can be offered as recovery despite a rejected terminal-state transition.

**Minimal reproduction — NOT RUN.** Use barriers around the production recovery scan. Start a journal for a current live job and persist uniquely numbered blocks; release the scan while the writer remains active. Assert whether the file is unlinked and the row/recovery list changes. Repeat with two owners, a completed job, and a full N-sample WAV beside an N/2-sample journal. Do not use timing sleeps to create the ownership window.

**Expected behavior.** Only positively abandoned work is claimed. Live ownership and durable terminal/deleted state take precedence. Recovery never replaces a better committed audio source merely because a .blk file exists.

**Likely actual behavior / verification status.** Expected from source: the first pass can consume the live .blk, write/overwrite its WAV, and add a recovery item. Runtime verification required for each controlled interleaving; no physical capture-loss experiment was run.

**Existing test coverage.** The lifecycle recovery test uses an abandoned synthetic journal. It proves a valid-prefix recovery, not exclusion of a live owner, current capture, resolved row, or fuller WAV.

**Regression recommendation.** Assert zero mutations for live owners and resolved/deleted jobs; assert positive recovery for an abandoned owner; independently compare the selected audio length and exact sample bytes.

**Narrow repair direction.** Introduce one explicit local ownership/claim rule for all scan passes and a deterministic source-selection/publication rule. A process/file lock or equivalent single-instance ownership is sufficient; distributed coordination is not needed. Do not rely only on boot_id or mtime.

**Downstream impact.** M09 may show spurious recovery or lose the best audio; M14 may receive truncated or repeated evidence; M15 recovery qualification is invalid until repaired.

### M03-AUDIT-02 — M03 can recreate job audio or deliver output after delete-everywhere

**Severity:** CRITICAL  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Deletion barrier / temporary payload ownership / insertion authority

**Canonical requirement.** S25 and S29.14 prohibit cached jobs from recreating deleted content. M02 v11 establishes job_deleted() for producers outside the store; deletion is immediate and distinct from pausing collection.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/app.py` — _worker (2390–2950), _recover_journals (1810–1960), _retry_job (3960–4185), _finishWithText_ (2940–3165). [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `localflow/v2/store.py` — delete_everywhere, job_deleted, register_job_payload_dir, 2030–2180. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/store.py)
- `localflow/v2/insertion/service.py` — _run/_transaction and physical write paths, 284–525. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/insertion/service.py)

**Current behavior.** The store protects its artifact/revision writes and registers job-named journal payloads for deletion. M03 nevertheless writes worker WAVs outside that barrier and does not revoke its in-memory delivery authority on deletion. The insertion transaction checks job.cancelled, not the durable deletion barrier. The repaired debug-copy path does check job_deleted(); that protection is not general to worker/recovery WAV production.

**Failure mechanism.** Deletion commits and drains intents for files that exist at enumeration. A paused M03 producer can then create job-<id>.wav under the same root after deletion reported complete. Store publication refusal does not necessarily stop the inference/result path. A job deleted after its result is ready or queued for insertion still has cancelled=False and may copy or insert its cached text.

**Minimal reproduction — NOT RUN.** Gate a production coordinator immediately before worker-WAV creation; delete the job and assert complete; release the producer and inspect the registered root. Separately gate result delivery/transaction admission, delete the now-published example/job, then release delivery using a recording insertion host. Repeat deletion before automatic retry, recovery retry, and recovery reconstruction.

**Expected behavior.** No new managed payload, model retry, clipboard delivery, or insertion is authorized after deletion wins. An input already held by a running worker is relinquished safely, with pending deletion represented honestly rather than unlinking/recreating it opportunistically.

**Likely actual behavior / verification status.** Expected from source: a later outside-store WAV write is not fenced, and cached output is not revoked by the existing cancellation-only gate. Exact physical-delivery reproduction remains unexecuted; the source path is present.

**Existing test coverage.** M02 tests positively prove store-level late artifact/revision refusal and deletion of already-registered files. The app wiring test checks only the debug-copy guard and registration calls. Neither proves M03 publication/delivery cannot occur after deletion.

**Regression recommendation.** Use the real Store plus production M03 methods and a synthetic host; read SQLite and filesystem independently. Assert zero post-deletion file reappearances and zero host/clipboard writes, including both race orderings.

**Narrow repair direction.** Carry deletion/revocation into the coordinator and recovery owner. Serialize authority acquisition and payload publication with deletion, or use an equivalent acknowledged ownership protocol. A lone check-before-write is still a TOCTOU window; rechecking without an ownership rule is not sufficient. Preserve M02 barriers and durable purge semantics.

**Downstream impact.** M08 physical-output authority, M09 recovery, M14 privacy/lineage, and M15 acceptance. This is an M03 integration defect, not a re-audit of repaired M02 SQL.

## High Findings

### M03-AUDIT-03 — An old reader finalizer can fail a new generation’s request

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Generation ownership / stale parent callback

**Canonical requirement.** S06, worker.md, M03-AC01/AC02: a reader may resolve only requests owned by its process/generation.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/supervisor.py` — _read_loop finally, 171–220; _Pending and _pending; _resolve, 310–318. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)

**Current behavior.** The reader finalizer conditionally logs current-generation exit, but unconditionally copies and clears the shared pending table and resolves every entry as WorkerProcessExited. Pending entries contain no owner-generation metadata.

**Failure mechanism.** This is a concrete stale parent-side callback, not merely a stale worker frame. Let an idle G1 exit and pause its reader before finally. A later request observes the dead process, spawns G2, and registers a G2 pending request. G1 finally then removes that G2 request and makes a healthy generation appear dead. Unique req_ids do not protect a bulk clear of the whole table.

**Minimal reproduction — NOT RUN.** Barrier G1 immediately before finalizer cleanup. Start G2 and wait until its pending request is registered and its worker is still alive. Release G1 cleanup. Assert the G2 future remains pending until its own response, and that no retry/death is charged to G2.

**Expected behavior.** Only G1-owned entries fail. G2 result, readiness, pending map, and breaker accounting remain untouched.

**Likely actual behavior / verification status.** Expected from source: the G2 pending entry is faulted by G1. A deterministic executable reproduction has not been run here.

**Existing test coverage.** Existing tests inject old-generation result messages sequentially; they do not hold an old reader’s finally block across a replacement.

**Regression recommendation.** Test old-reader exit before and after G2 registration, and while manual/automatic restart races. Require a positive G2 result and exact one-request completion.

**Narrow repair direction.** Bind pending entries to immutable process/generation ownership and filter finalization/resolution by that owner; join or otherwise retire old readers safely. Do not fix this by indiscriminately adding expected_attempt to every app state write.

**Downstream impact.** M13 failure/attempt statistics and M14 evidence can be attributed to unnecessary retries; M15 reliability. This proves a supervisor ownership fence is needed, not a blanket app-wide stale-attempt writer.

### M03-AUDIT-04 — Restart, automatic retry, and shutdown do not share a closed, serialized lifecycle

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Process lifecycle / GPU isolation / app termination

**Canonical requirement.** S06 one authoritative GPU worker; S09 restart recovery; M02 admission-close/drain contract; M03 normal and forced shutdown requirements.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/supervisor.py` — _spawn/ensure_running, 104–170; _request_locked, 380–450; restart/shutdown/_kill, 480–end. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- `localflow/app.py` — applicationWillTerminate_ and _shutdown_persistence, 1600–1840; infinite _worker loop. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `tests/v2/test_m02_app_wiring.py` — test_shutdown_drains_writers. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/test_m02_app_wiring.py)

**Current behavior.** ensure_running and manual restart use _spawn_lock, but the automatic-retry path calls _kill/_spawn without that lock. Shutdown has no permanent closed-admission state and is not serialized with those transitions. App termination shuts down the supervisor and closes durable writers without first stopping/joining all capture, coordinator, recovery, and insertion producers.

**Failure mechanism.** A manual restart can overlap retry spawning, replacing shared process/readiness state while another spawn or request is still using it. Shutdown can cause an in-flight request to fault, which the still-running coordinator treats as authority to spawn a replacement; shutdown cleanup can also clear a newly replaced _proc. Concurrent workers can load GPU models outside the ordinary request mutex. Late app callbacks then encounter closed store/event admission.

**Minimal reproduction — NOT RUN.** Use latched Popen/hello/request boundaries for restart↔automatic retry, close↔spawn, and close↔submit. Gate a coordinator request, start application termination, then release its fault. Count created/reaped PIDs, open pipes, reader completion, accepted/rejected requests, and callbacks after durable close. Separately quit during active capture with queued journal blocks.

**Expected behavior.** A single lifecycle authority closes admission once, prevents all later spawn/retry, relinquishes capture safely, settles/cancels accepted producer work, reaps workers/readers, and only then drains durable writers.

**Likely actual behavior / verification status.** Expected from source: there is no closed-state rejection, and uncoordinated lifecycle operations can race. Exact interleavings and native termination behavior require verification; no process-race run was executed.

**Existing test coverage.** Protocol tests exercise ordinary serialized requests and sequential restarts. M02’s static app test asserts supervisor.shutdown precedes persistence close and store.close precedes log.close; its “stops producers” printout is stronger than that oracle.

**Regression recommendation.** Behavioral shutdown tests must prove no new worker after closure, no leaked child, bounded request disposition, no microphone reopen, and no producer write after store admission closes. Test rejected submission positively, not merely absence of a hang.

**Narrow repair direction.** Use one lifecycle state machine/lock or equivalent ownership protocol for spawn, retry, restart, and close. Do not hold locks across callbacks that re-enter the supervisor. Add orderly app producer shutdown; retain bounded rejection when a drain deadline is exhausted.

**Downstream impact.** M07/M11 share the worker; M08 delivery can outlive shutdown; M02 drain guarantees otherwise remain correct only for work already admitted. M15 RSS/restart measurements must be refreshed.

### M03-AUDIT-05 — A failed automatic retry loses the attempt identity that actually executed

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Attempt lineage / failure evidence / usage attribution

**Canonical requirement.** jobs.md same logical job with incremented attempt; training_evidence.md attempt denotes the execution whose evidence is recorded; M03-AC01/AC02/AC06.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/supervisor.py` — _request_locked/_request_once, 380–480. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- `localflow/v2/worker.py` — _fault, 433–439. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/app.py` — _worker retry propagation and WorkerFailure handler, 2480–2950. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `localflow/v2/training.py` — note_attempt and failure publication. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/training.py)

**Current behavior.** The supervisor increments the retry request payload. The app advances its job/store/context counter only after a successful returned result with retried=True. When the second request fails, WorkerFailure does not carry the final executed attempt/generation; worker fault frames omit those fields too.

**Failure mechanism.** Attempt 1 faults; attempt 2 genuinely starts and faults; the caller receives a generic failure while its logical job/context still say attempt 1. Recovery eligibility, failure publication, and later retry numbering are based on that stale counter. Successful retries are better wired after M02, but the failure branch bypasses that wiring.

**Minimal reproduction — NOT RUN.** Feed two failing ASR executions and record both request frames. Run the real coordinator/Store/collector failure path. Compare frame attempts [1,2] with the durable job, failure envelope, recovery item, and usage fact. Repeat on cleanup after successful ASR, then perform an explicit recovery retry.

**Expected behavior.** Attempt 2 is acknowledged as executed even when it produces no result. The next legitimate retry has a new monotonic identity; failure records name the executed attempt and relevant generation/stage.

**Likely actual behavior / verification status.** Expected from source: the terminal failure path retains the app’s earlier attempt. No runtime failure trace is claimed.

**Existing test coverage.** M02 app AST coverage checks that two note_attempt calls exist, not that failure reaches them. Protocol double-fault tests stop at exception/breaker behavior. Collector tests verify supplied attempt metadata, not this end-to-end failure transport.

**Regression recommendation.** Assert attempts on success and failure, exact stage generations, unchanged family/job ID, one usage fact, no duplicated successful insertion, and a valid monotonic recovery retry.

**Narrow repair direction.** Carry immutable execution identity in request outcomes/faults or acknowledge attempt admission to the coordinator before executing it. Coordinate any durable attempt bump rather than relying on an unacknowledged increment plus speculative expected_attempt checks.

**Downstream impact.** M13 retry/failure attribution, M14 revision lineage, M15 failure benchmarking. Does not establish that every app transition needs an attempt fence.

### M03-AUDIT-06 — Fatal model failure can leave the damaged generation reusable

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Fault classification / breaker correctness / cleanup lifecycle

**Canonical requirement.** worker.md: fatal GPU failure/timeout must retire the damaged process; second failure is recoverable failure, not permission to reuse poisoned Metal state. S09, M03-AC01/AC04.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/supervisor.py` — _request_locked/_request_once/_record_death, 380–505. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- `localflow/v2/worker.py` — _clean_v2 and result/fault paths, 240–439. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/cleanup.py` — load/clean/_clean_piece exception handling, 270–end. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/cleanup.py)

**Current behavior.** The first WorkerFailure kills/replaces the process. A failure of the second _request_once can escape without killing that generation unless the three-death breaker happens to fire. Cleanup also has catch-all exception-to-preserved-output paths that can return a successful basic/fallback result after a fatal model exception, leaving engine readiness unchanged and resetting the supervisor’s success-based death streak.

**Failure mechanism.** A structured fatal failure need not exit the child. After the retry allowance is exhausted, that child can remain authoritative for the next job. In cleanup, semantic fallback is appropriate for a rejected proposal, but it is not proof that the GPU runtime remains safe after a fatal execution error.

**Minimal reproduction — NOT RUN.** Use a worker that emits a structured fatal fault and stays alive for two executions. After the second failure, submit a healthy job and check its PID/generation. Separately inject a recognized fatal runtime error from the production cleanup-generation seam and inspect the returned op, readiness, next request, and death accounting.

**Expected behavior.** Preserve available text/audio, but retire a fatally damaged generation. A validation rejection may use a healthy-model fallback; a fatal runtime error must remain a lifecycle fault even when text can be saved.

**Likely actual behavior / verification status.** Expected from source: the second structured-fault generation can survive, and catch-all cleanup fallback can hide the lifecycle fault from the supervisor. Whether a specific real MLX exception poisons Metal remains native/model verification, not a claim from this audit.

**Existing test coverage.** Double-fault tests check that an exception occurs, not that the second child is reaped before reuse. Existing successful/fallback tests do not distinguish semantic rejection from fatal GPU failure.

**Regression recommendation.** Positive PID/generation assertions; distinguish recoverable engine-load failure, nonfatal cleanup rejection, timeout, fatal GPU error, and process exit. Require no unbounded respawn loop for a missing model.

**Narrow repair direction.** Introduce narrow, content-free fatal/nonfatal classification and a retire-on-fatal rule in every exit path. Preserve honest fallback text, but do not label damaged-runtime reuse as healthy success or erase its breaker history.

**Downstream impact.** M07 fallback lifecycle (not its previously audited fidelity policy), shared M11 worker behavior, M13 fault counters, M15 model qualification.

### M03-AUDIT-07 — “Basic now” and bounded cleanup hold are not implemented by the production load loop

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Readiness / bounded latency / fake-worker oracle mismatch

**Canonical requirement.** S09 and worker.md basic-now versus bounded-hold policy; M03-AC04; readiness must describe service actually available in the current generation.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/worker.py` — _load and serial serve loop, 117–220 and 378–431. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/v2/supervisor.py` — clean(engine_wait=0), 338–359. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- `localflow/app.py` — cleanup policy branch, 2680–2850. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `tests/v2/lifecycle/fake_worker.py` — load handling. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/fake_worker.py)

**Current behavior.** Production serve executes _load synchronously: ASR load/warmup, ASR ready notification, then cleanup load/warmup, and only afterward reads another request. The fake worker announces loading and returns to its request loop. The parent’s wait_engine timeout bounds its readiness wait, not the time until a request queued behind the production loader is serviced.

**Failure mechanism.** With cleanup loading slowly or indefinitely, the parent can observe ASR ready yet no ASR/cleanup request can be read. A basic-now request is not served now, and a bounded hold can end only to submit into the same blocked loop, waiting until the much longer request timeout.

**Minimal reproduction — NOT RUN.** Exercise Worker.serve with a controlled loader: ASR becomes ready, cleanup load waits on a latch. Submit ASR and a basic-cleanup request and measure the configured policy deadline without releasing the latch. Run both basic-now and bounded-hold, plus ready immediately before/after timeout. Keep GPU work serialized.

**Expected behavior.** Readiness and policy deadlines match actual dispatch. A slow cleanup loader does not turn a configured CPU/basic fallback into an unbounded hidden wait.

**Likely actual behavior / verification status.** Expected from source: production cannot dispatch either queued request until _load returns. The existing fake-worker test can pass while this behavior remains.

**Existing test coverage.** The fake loading_forever mode services requests during loading; the real worker test waits for both engines before sending work. Neither tests the production startup interval in question.

**Regression recommendation.** Use production-shaped load scheduling, positive fallback-result assertions, measured deadline bounds, and actual path/model attribution. Do not repair the test by lengthening its timeout.

**Narrow repair direction.** Decouple control/fallback service from blocking model loading, or adopt an explicitly bounded parent-side fallback/load-cancellation strategy. Preserve one GPU operation at a time; merely putting loaders on concurrent GPU threads is not a safe repair.

**Downstream impact.** M07 fallback labels, M09 model status, M15 startup/latency qualification.

### M03-AUDIT-08 — Journal reconstruction lacks integrity, gap, and finalization validation

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Journal framing / missing speech / audio provenance

**Canonical requirement.** M03-AC03/AC05; capture.md complete-block recovery; S29.5 original-sample offsets and honest discontinuities.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/capture_journal.py` — handoff_block/_writer, 50–172; reconstruct, 224–279. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/capture_journal.py)
- `localflow/v2/training.py` — attach_capture_meta and audio_preparation. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/training.py)

**Current behavior.** Reconstruction ignores block sequence numbers and does not parse or verify the final block count, sample count, or SHA-256. A leading { at a record boundary is treated as clean finalization without validating the JSON. Queue drops are counted only in memory; accepted blocks are renumbered continuously, so the persisted stream has no original positions or durable gap record.

**Failure mechanism.** Reorder/duplicate a complete block, mutate payload bytes, or provide a false final hash: the reader can accept the resulting audio. A dropped journal block followed by later persisted blocks becomes compressed, apparently continuous audio after restart. Structural corruption before later valid records is classified with the same torn-tail flag as a genuine incomplete last write. Exact record-boundary EOF says nothing about whether capture was finalized; that needs separate status, not a fabricated claim of a torn sample.

**Minimal reproduction — NOT RUN.** Build fixtures independently of the production writer. Include reordered/duplicate sequences, one payload bit flip, a bad final count/hash, a lone {, truncated JSON footer, interior corruption with a valid later block, and a queue-overflow timeline with numbered samples before and after the missing range. Reconstruct and inspect downstream recovered evidence.

**Expected behavior.** Known finalization is verified; unknown finalization remains unknown. Recoverable tails and structural corruption are distinct. Retained samples preserve their original timeline mapping, or explicitly declare that mapping unavailable; a gap is never asserted continuous.

**Likely actual behavior / verification status.** Expected from source: several corruptions are accepted; the footer is not verified; queue-drop location/count does not survive solely in the journal. Reproduction execution remains pending.

**Existing test coverage.** Current tests cover correct writer/reader round trips, one torn tail, queue count bounds, and manually supplied discontinuity metadata. They do not independently challenge sequence/footer integrity or recover an actually gapped journal.

**Regression recommendation.** Positive valid-prefix controls plus independent negative byte fixtures. Assert exact samples, classified damage, original offsets, eligibility downgrade, and no “complete” recovered evidence across an unrecorded gap.

**Narrow repair direction.** Validate version/header/types, bounded block lengths/sequences, footer counts/hash, and explicit corruption/finalization status. Persist gap positions/counts at the producer boundary; choose a versioned compatible format. Do not silently resynchronize through corruption and splice unrelated samples.

**Downstream impact.** M14 ASR evidence and sample ranges; M09 recovery presentation; M15 crash-fidelity qualification.

### M03-AUDIT-09 — Recovery retry reconstructs new capture metadata rather than preserving the original capture

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Recovery provenance / timestamps / sample rate / discontinuities

**Canonical requirement.** jobs.md capture time is not retry/import time; training_evidence.md identity/time and capture diagnostics; S29.4/S29.5; M03-AC05/AC06.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/app.py` — _recover_journals, 1810–1960; _retry_job, 3960–4185; sleep/lock recovery. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `localflow/v2/training.py` — job_started, attach_capture_meta, _envelope, audio_preparation. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/training.py)
- `localflow/stt.py` — transcribe assumes adapter model rate. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/stt.py)

**Current behavior.** Recovery items retain IDs, WAV path, raw text, and attempt, but not the complete recovered capture diagnostics. _retry_job reads the WAV’s rate then does not carry that rate into its reconstructed job/evidence path. It starts the collector with the current time; only afterward the analytics-facing job dict restores the original row’s timestamp. The envelope uses live_capture/known time. For missing rows, scan-time timestamp lookup also differs from the nested journal meta written by the app.

**Failure mechanism.** An old capture retried today can receive today’s evidence capture time while usage correctly uses the older date. Torn-tail/gap/device-loss information is lost at the recovery-item seam. A changed configured rate or legacy WAV can be processed/reported with a different rate from the retained bytes. These are producer-lineage errors even when the job/family IDs are correct.

**Minimal reproduction — NOT RUN.** Create an originally consented failed capture at T0 with distinctive rate and discontinuity metadata. Advance the clock/configuration, recover and retry at T1. Compare the WAV header, recorded frames/duration, store row, collector envelope, ASR preparation, and usage fact. Repeat with missing original metadata: assert unknown rather than T1-as-capture.

**Expected behavior.** Original capture time/rate/sample identity and known discontinuities survive; retry time is a separate event. Unknown fields stay reasoned unknown. Consent remains original permission AND enabled now.

**Likely actual behavior / verification status.** Expected from source: collector time and origin are rebuilt as a new known live capture; recovered diagnostics/rate are not faithfully threaded. The consent conjunction itself is correct and must not be “fixed” into current-consent-only collection.

**Existing test coverage.** M02 tests verify original consent revision; lifecycle tests verify retry attempt success; fidelity tests inject metadata directly. No end-to-end recovery test compares original and retried capture envelopes.

**Regression recommendation.** Independent T0/T1 clock and non-default-rate fixtures; compare the exact worker input and evidence parent; assert preserved same job/family and truthful unknowns. Include torn-tail and dropped-block recovery.

**Narrow repair direction.** Carry a versioned capture-provenance record through journal/recovery/retry, taking authoritative original fields from the retained source/store when available. Separate retry execution metadata from capture metadata. Validate/resample only explicitly; never merely relabel a rate.

**Downstream impact.** M13/M14 date disagreement, M14 acoustic eligibility and family provenance, M15 reference-input qualification.

### M03-AUDIT-10 — A partially written worker WAV can be accepted as complete audio

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** WAV crash consistency / inference input validation

**Canonical requirement.** M03-AC03/AC05; S29.5 original samples; S09 recoverable audio must be honest. This concerns M03 temporary/recovery input, not reopening M02 managed-artifact hash repairs.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/store.py` — _write_wav/read_wav_f32/read_wav, 789–835. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/store.py)
- `localflow/v2/worker.py` — _transcribe input decode. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/app.py` — worker-WAV creation and WAV-only recovery/retry. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)

**Current behavior.** _write_wav opens the final path with wb and writes header then payload; there is no staged atomic publication. read_wav_f32 validates selected header fields but slices whatever bytes are present up to the declared data_size. A missing suffix aligned to four bytes therefore produces a shorter valid float32 array instead of a truncation error.

**Failure mechanism.** A process interruption after a WAV header and an aligned payload prefix leaves a named file that can be discovered/retried. With no usable block journal, the prefix can be transcribed as the job’s audio without a specific incomplete-payload indication. The format header advertises more samples than the decoder actually receives.

**Minimal reproduction — NOT RUN.** Write a valid header declaring N float32 samples but only N/2 aligned samples, with no .blk source. Call the actual reader and worker input path, then the recovery retry. Include 1–3 trailing bytes, invalid data marker/size, and a complete-file positive control.

**Expected behavior.** Reject or explicitly classify incomplete input; never silently advertise the truncated prefix as complete. Publish finished worker input atomically before marking it ready for dispatch.

**Likely actual behavior / verification status.** Expected from source: the aligned prefix is returned successfully by the reader. No executed demonstration is claimed.

**Existing test coverage.** Fidelity tests round-trip complete generated WAVs; managed-artifact deep verification checks registered hashes, which is not the same as validating an unregistered recovery/worker WAV.

**Regression recommendation.** Assert declared-versus-actual sample count, truncation status, recovery eligibility, no silent shortened model input, and crash behavior before/after atomic publication.

**Narrow repair direction.** Add strict format/length checks at the M03 input boundary and stage/atomically publish finished worker WAVs. Preserve a damaged original for honest recovery where appropriate rather than overwriting it as “fixed.” Avoid changing unrelated M02 artifact semantics without regression coverage.

**Downstream impact.** M09 recovered duration, M14 original-audio claims, M15 fault-recovery accuracy.

### M03-AUDIT-11 — Audio stream start/stop exceptions bypass capture cleanup and prefix preservation

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Capture lifecycle / device failure

**Canonical requirement.** S09 device-loss prefix preservation and clear recoverable failure; M03-AC04; EV-04 lifecycle.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/audio.py` — Recorder.start and Recorder.stop. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/audio.py)
- `localflow/app.py` — startDictation, _finishCapture, _abandon_capture_for_system, cancelDictation. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)

**Current behavior.** Recorder.start assigns _stream before calling its start method; a start exception does not clear/close that assigned object. Recorder.stop clears its reference then calls stream.stop and close before extracting buffered frames and finalizing the journal, without exception-safe completion.

**Failure mechanism.** An injected start failure leaves a stale non-None stream, so a later start can take an already-started/no-op path despite no working capture. A stop/close failure can skip the entire buffered-prefix extraction and journal-finalization path; callers expecting normal return can remain in inconsistent capture state. This does not assert that every real unplug raises such an exception.

**Minimal reproduction — NOT RUN.** Use a native-interface shim around the real Recorder with a fake stream that raises at start, stop, and close separately. Preload uniquely identifiable captured frames. Assert the next start actually constructs/starts a fresh stream and every stop failure still yields or preserves the captured prefix with a classified error.

**Expected behavior.** Stream teardown is exception-safe; buffered speech is not discarded because the device close operation failed. Subsequent capture starts from clean ownership and reports the actual failure.

**Likely actual behavior / verification status.** Expected from source: those exceptions bypass cleanup/extraction. Physical device behavior remains PENDING_LOCAL_VERIFICATION.

**Existing test coverage.** The lifecycle FakeRecorder.stop always succeeds; its device-loss test cannot expose production Recorder exceptions. Journal disk-failure tests do not exercise stream teardown.

**Regression recommendation.** Test each failing API seam with positive nonempty sample populations; verify stream.close is attempted, references reset, journal disposition honest, app state settles, and next capture succeeds.

**Narrow repair direction.** Use exception-safe acquisition/teardown with a defined capture-result/error object or equivalent finally path. Preserve audio first; classify device failure separately from inference failure and never reopen the mic automatically.

**Downstream impact.** M09 recovery availability, M14 capture diagnostics, M15 native device qualification.

### M03-AUDIT-12 — Worker exception text is mislabeled as a content-free reason code

**Severity:** HIGH  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Operational-event privacy / fault transport

**Canonical requirement.** events.md invariant 2; S07 and S29.14: operational errors contain codes, not transcript/prompt/path/secret content.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/worker.py` — _reason/_fault and serve exception handling, 421–449. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/v2/supervisor.py` — worker.fault emission, around 260–274. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- `localflow/v2/eventlog.py` — emit/write, operational log persistence. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/eventlog.py)

**Current behavior.** _reason claims to sanitize but concatenates exception type and str(e). _fault truncates that string to 120 characters and places it in reason_code. The supervisor forwards it into operational events; truncation is not redaction.

**Failure mechanism.** An ASR/model/path/decoder exception containing a user path, transcript fragment, prompt, or secret sends that content through the supposedly content-free fault channel. M02’s redacted-export allowlist is a separate, typed export boundary and may omit the malformed code; it does not make the original on-disk operational event content-free.

**Minimal reproduction — NOT RUN.** Raise a synthetic exception whose message contains unique transcript, path, prompt, and credential-shaped canaries. Pass it through the production fault frame and event writer. Search raw operational JSONL and failure envelopes, then test the redacted export separately without assuming it leaks.

**Expected behavior.** Only stable allowed reason tokens, exception type, stage/identity, and safe numeric diagnostics enter operational logs. Content remains in explicitly governed artifacts when permitted.

**Likely actual behavior / verification status.** Expected from source: raw operational reason_code contains the exception-message prefix. No user secret or real transcript was used, and no executed canary test is claimed.

**Existing test coverage.** Fake workers use constant safe reason strings, so they do not challenge _reason. Existing redaction tests are not an oracle for the original fault producer.

**Regression recommendation.** Canaries must be absent from raw events, diagnostics, recoverable labels, and redacted exports; include harmless exception types and ordinary error messages as positive controls.

**Narrow repair direction.** Map failures to controlled codes and record safe exception types/counts separately. Do not simply redact common paths while allowing arbitrary exception strings through another approved field.

**Downstream impact.** M02 event contract, M09 failure display, M14 privacy/exports, M15 diagnostic capture.

## Medium Findings

### M03-AUDIT-13 — Protocol identity and framing defenses are incomplete

**Severity:** MEDIUM  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** IPC validation / response attribution / short writes

**Canonical requirement.** worker.md versioned length-framed protocol; parent-owned job + req_id + attempt + generation; M03-AC02.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/worker.py` — _write_msg/_read_msg, 42–63; serve. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- `localflow/v2/supervisor.py` — _Pending, _handle_message and _resolve, 224–318. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)

**Current behavior.** The parent validates result generation and req_id existence but does not compare echoed job_id/attempt/result kind against immutable expected request metadata. _resolve ignores its generation argument for fault resolution. Worker request schema/version checks are incomplete. _write_msg uses one os.write for the entire outbound frame without ensuring all bytes were written or enforcing an outbound size cap.

**Failure mechanism.** A synthetic current-generation response with a live req_id but wrong job/attempt can be accepted as that pending result. This is a protocol-boundary weakness, not evidence that the current well-behaved worker naturally invents another job’s result. A short frame write can leave the next frame interpreted as the remainder of the prior payload.

**Minimal reproduction — NOT RUN.** Inject wrong job, old attempt, wrong result kind, valid req_id from an old reader, duplicate responses, malformed/non-object JSON, future versions, and missing/wrong-type fields. Force os.write to make partial progress and independently parse the emitted bytes. Include split headers, split payloads, coalesced frames, oversized and zero lengths, EOF mid-frame.

**Expected behavior.** Responses satisfy only their immutable expected identity/type. Framing failures have explicit generation-scoped disposition. A write completes its entire frame or fails the generation without emitting a misleading partial success.

**Likely actual behavior / verification status.** Expected from source: job/attempt/kind mismatch is not rejected by the pending entry; a simulated short write is not retried. Ordinary duplicate unknown req_ids and old-generation results are already rejected.

**Existing test coverage.** The existing suite has useful positive request tests and synthetic stale-generation messages, but lacks complete malformed-schema, short-write, and expected-identity matrices.

**Regression recommendation.** Independent byte-level framing oracle; exactly one terminal resolution per request; no cross-job host delivery; malformed generation cannot disturb another live generation.

**Narrow repair direction.** Store immutable expected identity in pending entries; validate every applicable result/fault against it; add symmetric bounded framing and write-all handling. Keep the worker protocol non-executable and insertion-free.

**Downstream impact.** M13/M14 attribution under malformed protocol; M15 fault qualification. No blanket stale-attempt claim is made.

### M03-AUDIT-14 — The audio-root check accepts symlinks and nonregular inputs

**Severity:** MEDIUM  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Worker input ownership / path confinement

**Canonical requirement.** worker.md parent-provided file name under a fixed root; internal-protocol traversal must not select arbitrary files.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/worker.py` — _audio_path and _transcribe, within 200–255. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)

**Current behavior.** The worker restricts the basename with a regular expression and checks lexical abspath/dirname. It does not verify a regular file or resolve/reject a symlink at the input boundary.

**Failure mechanism.** A legal name such as job-x.wav can be a symlink to a file outside the root; a FIFO can block the decoder. The basename guard correctly rejects ../, absolute paths, slashes, and backslashes, but it is not file-identity confinement.

**Minimal reproduction — NOT RUN.** Under a temporary root, test valid regular WAV, traversal names, an outside-root symlink, an inside-root symlink, directory, FIFO, and a controlled replacement between validation and open. Do not read any actual user file.

**Expected behavior.** Only the intended parent-owned regular input is opened, or unsupported file types/ownership changes are explicitly refused.

**Likely actual behavior / verification status.** Expected from source: a lexically valid symlink passes _audio_path. OS-specific open semantics and swap behavior need runtime verification.

**Existing test coverage.** Current protocol tests focus on request/results and unsupported insertion op; no independent file-type/identity matrix was identified in the inspected M03 suites.

**Regression recommendation.** Positive regular-file test plus symlink/FIFO negatives; no external read and bounded failure. APFS identity nuances remain native pending.

**Narrow repair direction.** Use an appropriate no-follow/regular-file/opened-descriptor validation at the local boundary, or an equivalent parent-owned descriptor strategy. Do not add a multi-user sandbox or distributed threat model.

**Downstream impact.** M03 isolation and input honesty; M15 path/fault qualification.

### M03-AUDIT-15 — Forced capture ends and lost mouse releases leave trigger state behind

**Severity:** MEDIUM  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Trigger state machine / watchdog

**Canonical requirement.** S09 hands-free/mouse handling; EV-04; a trigger’s stale state must not affect a later capture.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/app.py` — maxDurationHit_ (2095–2100), _finishCapture, watchdogTick_ (2390–2490). [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- `localflow/hotkey.py` — MouseTriggerListener._down/_up and held state. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/hotkey.py)

**Current behavior.** The ordinary hands-free stop path clears the latch, but maxDurationHit_ and device-loss completion call _finishCapture without the same explicit hands-free reset. The non-recording watchdog resets stale hotkey.held, not mouse_trigger.held; MouseTriggerListener ignores a new down while held remains true.

**Failure mechanism.** After a forced end, the next tap may be consumed as stopping a no-longer-active hands-free capture rather than starting a new one. After sleep/lock/forced completion with a missed mouse-up, the mouse listener can retain held=True while physically released and reject the next press.

**Minimal reproduction — NOT RUN.** Exercise real coordinator methods with controlled physical-state providers. End hands-free through max duration and device loss, then press once. Separately set mouse held, end capture, drop the up event, report physical up while idle, tick the watchdog, and press again. Include normal keyboard and mouse captures as controls.

**Expected behavior.** Capture termination consistently clears the correct trigger/capture latch. Idle reconciliation repairs lost releases for the configured input without one trigger releasing another trigger’s capture.

**Likely actual behavior / verification status.** Expected from source: forced-end latch cleanup and idle mouse-held reconciliation are absent. Real NSEvent/Fn/mouse behavior remains native pending.

**Existing test coverage.** Ordinary double-tap/watchdog behavior is exercised. Mouse coverage constructs button mappings; it does not drive this lost-release sequence. Existing first-tap cancelled jobs are permitted and are not this defect.

**Regression recommendation.** Deterministic source-tagged event sequences across key↔mouse, max duration, device loss, sleep/lock, delayed release, and new capture; assert positive next-capture start and no premature end.

**Narrow repair direction.** Centralize capture termination state cleanup and reconcile held state for the active/configured input. Preserve the existing trigger-aware/hands-free watchdog protection.

**Downstream impact.** M09 visible stuck/no-op capture controls; M15 native trigger checks.

### M03-AUDIT-16 — Fault diagnostics can raise TypeError, and the parent stderr bound is only a line count

**Severity:** MEDIUM  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Diagnostic robustness / generation attribution / memory bound

**Canonical requirement.** M03 error-path reliability and content-free bounded fault diagnostics.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/v2/supervisor.py` — Popen/_drain_stderr, 126–228; _fault_detail, 320–330. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)

**Current behavior.** Popen stderr is binary; _drain_stderr stores bytes. _fault_detail searches for the str "Traceback" inside each nonempty bytes line, which raises TypeError. The tail is capped by line count, not byte count, and old stderr drain threads can append to the shared tail after a replacement clears it.

**Failure mechanism.** An otherwise handled worker fault with a nonempty stderr tail can crash the reader’s diagnostic path, invoke its broad pending cleanup, and pollute fault/retry behavior. A very long unterminated stderr line is not bounded by a 20-line deque; late old-generation stderr can be described as current-generation diagnostics.

**Minimal reproduction — NOT RUN.** Feed one nonempty bytes stderr line, then a fault frame, through the actual supervisor path. Repeat with no stderr, a traceback-shaped line, a large newline-free stream, and a latched old stderr reader that resumes after G2 starts.

**Expected behavior.** Diagnostic formatting never changes request disposition, enforces an explicit byte cap, and reports only its owning generation’s safe metadata.

**Likely actual behavior / verification status.** Expected from source: bytes/str membership raises TypeError. No real worker was run to trigger it in this audit.

**Existing test coverage.** The fake fault cases do not establish a nonempty binary stderr population or old-drainer overlap.

**Regression recommendation.** Assert fault resolution occurs exactly once without reader failure; retained bytes stay within cap; old stderr cannot enter a new generation’s digest.

**Narrow repair direction.** Normalize safely or use bytes consistently, make diagnostics non-throwing, and maintain per-generation byte-bounded tails. Keep raw content out of events.

**Downstream impact.** M13 fault counts and M15 restart diagnostics; interacts with the old-reader cleanup defect.

### M03-AUDIT-17 — The insertion-service-unavailable fallback never retires its active job

**Severity:** MEDIUM  
**Confidence:** High — source-established; reproduction not executed in this audit  
**Category:** Terminal lifecycle / degraded-mode recovery

**Canonical requirement.** jobs.md exactly one terminal disposition; S25 no spinning pill; M03 coordinator must relinquish active work on every terminal path.

**Code location.** Inspection spans/functions at the audited SHA:
- `localflow/app.py` — _finishWithText_ insertion_service_unavailable branch, 3100–3140; _retire_active_job, 3235–3245. [Pinned source](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)

**Current behavior.** When the insertion service is None, the app copies the text, records saved_not_inserted, updates usage/evidence, settles state, and returns. It does not call _retire_active_job, although the ordinary insertion path defers that retirement to _insertionDone_. No insertion callback will arrive in this fallback.

**Failure mechanism.** The job remains in _active_jobs and _pending remains elevated after its durable terminal outcome. The app can display ongoing processing and retain a phantom cancellation target. Audio retention itself should follow the intentional saved-not-inserted recovery policy, not be blindly deleted as part of this repair.

**Minimal reproduction — NOT RUN.** Create one active, nonempty completed job with _pending=1 and _insertion=None. Invoke the production final callback with a recording clipboard stub. Assert exactly one saved outcome/copy, no active job, pending zero, and the intended retained recovery audio policy.

**Expected behavior.** A fallback that terminates synchronously retires its active ownership once, just as an asynchronous insertion completion does.

**Likely actual behavior / verification status.** Expected from source: active/pending bookkeeping survives the return. Execution has not been performed here.

**Existing test coverage.** The lifecycle harness normally supplies an insertion stub; it does not establish the unavailable-service branch’s terminal bookkeeping.

**Regression recommendation.** Exercise both available and unavailable insertion service, empty output, cancelled result, failed result, and exception while recording fallback evidence. Require exactly one retirement, not a negative pending count.

**Narrow repair direction.** Retire the job in the synchronous fallback’s terminal/finally path and preserve the documented recovery-audio disposition. Do not broaden this into an M08 insertion redesign.

**Downstream impact.** M09 pending/History controls; M13 terminal presentation; M15 degraded-mode lifecycle.

## Low Findings

No separate Low-severity production defect is asserted. Durability wording and policy ambiguities are kept below as design concerns rather than padding the defect count.

## Test Gaps

All six entries have **Severity: TEST GAP** and **High confidence in the inspected oracle limitation**. These are not claims that the corresponding production invariant necessarily fails beyond the specific material findings above. No test execution is reported.

### M03-AUDIT-18 — Production-shaped worker concurrency is not independently exercised

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** EV-05; worker generation, retry, readiness and close invariants.

**Code location.** `tests/v2/lifecycle/test_worker_protocol.py`, `fake_worker.py`, and `localflow/v2/supervisor.py`.

**Current behavior / failure mechanism.** The fake is useful for protocol mechanics but its loading behavior differs materially from production. Existing stale-message tests do not hold an old reader finalizer, fault callback, or close operation across a generation change. Concurrent request tests do not supply a complete identity/ownership oracle.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Construct latched production-shaped subprocesses and use real supervisor paths. Require successful G2 completion after G1 cleanup, closed-admission refusal, exactly one worker owner, exact job/attempt matching, and bounded basic-now/hold behavior. Assert the relevant callback/frame actually arrived.

**Downstream impact.** Findings 03–07 and 13; M07/M11 shared-worker boundaries and M13/M14 attribution.

### M03-AUDIT-19 — Journal tests do not independently verify corruption, gaps, or ownership

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** EV-04 and M03-AC03/AC05.

**Code location.** `tests/v2/lifecycle/test_capture_journal.py`, recovery tests in `test_lifecycle.py`, and `capture_journal.py`.

**Current behavior / failure mechanism.** Round trips share writer/reader assumptions. Flood tests observe RAM counters, not reconstruction of the missing interval. Disk-error tests establish journal degradation, not survival of the actual Recorder memory buffer. The callback-I/O test does not make a strong positive assertion that the challenged writer/forbidden call path was exercised.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Build bytes with struct independently; provide all corruption/overflow/ownership cases from 01/08. Use a real Recorder callback seam for disk failure and assert a positive full-memory sample population beside a shorter/degraded journal. Use latches for delayed open/finalize/discard and require no cancelled-file reappearance.

**Downstream impact.** Findings 01, 04, 08; M09 recovery and M14 acoustic evidence.

### M03-AUDIT-20 — The out-of-bounds audio test is a mathematical assertion, not a production rejection test

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** S29.5; EV-19 exact model input, original-sample bounds and derivative hashes.

**Code location.** `tests/v2/lifecycle/test_audio_fidelity.py`, worker input, collector audio_preparation, and recovery retry.

**Current behavior / failure mechanism.** The invalid example [[0, n+1]] is checked as invalid locally but is not submitted to the production API whose rejection the test describes. Discontinuities are manually supplied. Complete-file round trips do not verify unregistered worker-WAV truncation or recovery metadata.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Pass invalid ranges through the actual validated producer/publication path; assert refusal or explicit incomplete eligibility. Hash/compare the exact worker-decoded samples against the evidence parent and every declared derivative. Exercise normal capture, retry, recovered gaps, changed rate, and truncated WAV with nonempty positive controls.

**Downstream impact.** Findings 08–10; M14 export/replay and M15 input qualification.

### M03-AUDIT-21 — Lifecycle and shutdown tests overstate what native fakes and AST wiring prove

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** EV-04/EV-05; orderly M02 shutdown integration; deferred native verification.

**Code location.** `tests/v2/lifecycle/test_lifecycle.py`, `tests/v2/test_m02_app_wiring.py`, and real Recorder/app termination.

**Current behavior / failure mechanism.** The lifecycle file imports AppKit/PyObjC and uses synthetic Recorder/Supervisor/host collaborators. Some cancellation checks invoke the final callback directly rather than execute the concurrent worker path. The static shutdown test checks two call-order relations; it does not prove producer shutdown despite its printed wording.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Use production methods with declared native-interface shims, or a narrowly extracted production coordinator, for deterministic portable orchestration tests. Exercise real Recorder acquisition/teardown seams, active jobs at quit, late callbacks and new submissions after close. Native tests remain separately pending. Do not call a reimplemented toy state machine the app.

**Downstream impact.** Findings 02, 04, 11, 15, 17; reference-Mac certification remains distinct.

### M03-AUDIT-22 — Live and benchmark labels do not prove active-request fault recovery or enforce all budgets

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** E11 measurement discipline; EV-05, EV-16; M03 benchmark requirements.

**Code location.** `tests/v2/lifecycle/test_worker_live.py`, `scripts/v2/benchmark_m03.py`, historical M03 results.

**Current behavior / failure mechanism.** The live test and benchmark kill a worker between completed requests. That proves replacement/load behavior, not an in-flight automatic retry. The live test waits for both engines first. A skipped model suite returns cleanly and must remain a skip. The benchmark emits passes_p95 but main returns zero after reporting; exit zero alone is not a quality gate.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Distinguish harness/fake, real-model, and native end-to-end metrics. Add active-request death with positive successful retry population and no duplicate insertion. Validate expected populations/ready engines/results, and have acceptance explicitly evaluate budget fields and failure/skip status. Use real reference-Mac measurements only where available.

**Downstream impact.** Findings 04–07; M15 model/startup/RSS qualification and honest historical benchmark supersession.

### M03-AUDIT-23 — M02 compatibility coverage stops before the M03 producer boundary

**Severity:** TEST GAP  
**Confidence:** High — source inspection of the test oracle  
**Category:** Test-oracle / false-green risk

**Canonical requirement.** M02 deletion, acknowledgement, consent and drain contracts; EV-19.

**Code location.** `tests/v2/storage/test_m02_remediation_store.py`, `tests/v2/training/test_m02_remediation_collector.py`, `test_m02_app_wiring.py`, and M03 coordinator/recovery.

**Current behavior / failure mechanism.** Existing store/collector tests meaningfully protect admitted durable writes and original-consent reuse. They do not establish no late worker WAV, no physical delivery after deletion, failed-retry attempt attribution, or preserved T0 capture provenance through recovery at T1.

**Minimal reproduction — NOT RUN.** Deliberately retain or inject the corresponding production defect, execute the existing test, and establish whether its oracle stays green; then run the independent challenge below. A historical pass is not substituted for this experiment.

**Expected versus likely actual.** A violated invariant should fail its claimed acceptance test. The inspected test lacks the stated observation/assertion, so it does not establish that invariant; mutation/runtime verification is required to measure its actual false-green behavior.

**Existing coverage, regression recommendation, and narrow repair.** Add a compatibility fixture using the real Store/collector, temporary journal root, production coordinator methods, synthetic worker and recording delivery host. Independently query SQLite/filesystem. Exercise delete at each M03 publication/delivery seam, close at each producer seam, failure after retry admission, and consent/time/rate through recovery. Preserve all existing M02 regressions.

**Downstream impact.** Findings 02, 04, 05, 09; protects accepted M01/M02 while repairing M03.

## Design Concerns

These are **not automatic change requests**. They require a small contract/adversarial adjudication before expanding remediation scope.

### M03-AUDIT-24 — Is the retry allowance per stage or per logical dictation?

**Severity:** DESIGN CONCERN. **Confidence:** High in code behavior; policy interpretation unresolved. **Category:** Retry policy. The supervisor allows one retry per request. A dictation can therefore have ASR fail/retry successfully and cleanup fail/retry successfully. The brief asks for “one retry” of the logical job, while implementation and some worker descriptions are request-oriented. The minimum challenge is that four-execution sequence with job/attempt/generation and usage tracing. Establish the intended scope from current canonical requirements before changing budgets. Preserve same job/family and one usage fact either way. This is not a reason to reopen M07’s internal semantic candidate-retry policy, which is a different concept. Relevant source: supervisor._request_locked and app._worker. Downstream: M13/M15 interpretation of retries.

### M03-AUDIT-25 — The “memory-only” journal setting still needs an explicit temporary-WAV policy

**Severity:** DESIGN CONCERN. **Confidence:** High in the two code paths; setting semantics need adjudication. **Category:** Privacy / retention policy. Disabling incremental capture journaling avoids .blk production, but ordinary subprocess inference still writes a worker WAV and the startup WAV recovery path can see retained files. Temporary file IPC is not inherently wrong, but a documented “memory-only/no recovery” interpretation is not the same as “no incremental journal.” Reproduce with journaling disabled, a failed inference/process interruption, and restart. Decide whether temporary input must be unlinked/no-recovery by policy or the setting must accurately disclose its narrower scope. Do not conflate disabled training collection, disabled debugging, disabled journal, and never-store. Relevant source: capture.md, app._worker/_recover_journals/configure. Downstream: M09 privacy labels and M14 consent boundaries.

### M03-AUDIT-26 — Model cache revisions are not proven to be the worker’s executed checkpoint across restart

**Severity:** DESIGN CONCERN. **Confidence:** Moderate. **Category:** Runtime provenance. The parent resolves model/cache revision information while the worker receives model IDs and loads its own instances. ASR revision data is cached in app configuration, while other pipeline information can be resolved later. A controlled cache-ref change between configuration, load, and restart should establish whether evidence can cite the wrong resolved checkpoint. Do not assume the cache ever changed on Daniel’s machine. Prefer an immutable load selection and/or observed per-generation worker manifest if the experiment proves a mismatch; otherwise document the actual guarantee and unknown fields. This does not invalidate the accepted M01 provenance tooling globally. Relevant source: app.configure/_pipeline_info, worker._load, stt.load, collector.on_asr_result. Downstream: M14 reproducibility and M15 qualification.

### M03-AUDIT-27 — Bounded callback work, capture completeness, and power-loss durability are distinct claims

**Severity:** DESIGN CONCERN. **Confidence:** High in inspected mechanisms; native timing unmeasured. **Category:** Performance / durability semantics. The callback performs bounded array copy/meter work and short lock acquisition, and the journal handoff uses a mutex/condition. This is not literal wait-free execution. Full in-memory capture size grows with duration even though the journal queue is bounded. Direct os.write improves process-crash recovery but no per-block fsync guarantee is established. Define and measure the intended latency/lock bound, separate queue persistence from complete speech, and distinguish process crash from power loss. Do not demand enterprise fsync on every callback or redesign the app on theoretical grounds alone. Relevant source: audio.Recorder callback, capture_journal handoff/writer/finalize, E11/S24. Downstream: M15 performance and honest recovery documentation.

## Areas Verified Strong

“Verified” in this section means **inspected current source and, where noted, a meaningful existing test oracle**, not newly executed native certification.

The worker protocol contains no insertion command and no store-write interface; final physical-output authority remains in the parent. Unknown/duplicate result request IDs are dropped, and ordinary result/engine readiness generation checks exist. The deferred engine-status UI callback reads current supervisor state, avoiding the initially suspected stale-argument display defect.

Ordinary GPU requests are serialized. Initial ensure-running calls share a spawn lock. The parent forces worker offline mode before model loading, rather than trusting a possibly inherited HF_HUB_OFFLINE=0. Missing-engine state does not intentionally create an endless download/restart loop.

Normal ASR input comes from the full in-memory capture, not the degraded crash journal. The journal queue is bounded, regular block writes retry partial progress, and disk failure has an explicit degradation event. Complete float32 artifact round trips and PCM16 derivative parent/lossiness tests are meaningful.

Ordinary cancellation preserves the input while the worker may still read it and rechecks authority after stages and before delivery. The source handles cancelled jobs separately from ordinary recoverable worker failure. Hub retry has active-job/state checks; the suspected unrestricted double-Hub-retry path was not substantiated. A short cancelled first tap is permitted and is not itself an attribution defect.

M02 consent is captured coherently at PTT down; retry collection requires the original captured example’s permission plus current enabled state. Store-level deleted artifact/revision refusal and committed publication are present. These should be preserved rather than replaced with looser “current consent” or event-derived state.

The capability manifest makes all optional unsupported ASR outputs reasoned absent; it does not invent scores, confidence, n-best, timestamps, or acoustic hint acceptance. Usage production uses the logical job identity, not a count of worker result frames.

## Adversarial Reproduction Plan

Every item below is **NOT RUN in this audit**. Use synthetic text/audio, temporary roots, real production seams, and barriers/latches. A test must assert that the adverse event actually happened and that the positive control produced a nonempty relevant population.

| Probe | Ordered challenge | Independent oracle / expected safety | Findings |
|---|---|---|---|
| R01 | Hold old idle reader finally; register a G2 request; release G1 | G2 completes once; no spurious death/retry | 03, 18 |
| R02 | Automatic retry ↔ manual restart in both orders | One authoritative PID/generation; all old children reaped | 04, 18 |
| R03 | Close ↔ submit; close during hello/load/retry | Closed admission refuses; no respawn after close; bounded futures | 04, 21 |
| R04 | Result ↔ cancel before transaction admission | No host/clipboard write after cancellation wins; one terminal disposition | 18, 21 |
| R05 | Cancel ↔ worker fault, both orders | Cancelled state remains authoritative; input not unlinked under reader | 04, 06, 21 |
| R06 | Attempt 1 fault → attempt 2 fault → explicit recovery retry | Request/store/context/evidence counters agree; monotonic new execution | 05, 23 |
| R07 | Current req_id with old generation, old attempt, wrong job/kind; duplicate response | No wrong resolution or double delivery | 03, 13, 18 |
| R08 | Partial header/body, invalid length, non-object JSON, future version, short outbound writes | Bounded generation-scoped failure; no parser drift into another frame | 13 |
| R09 | ASR-ready with cleanup loader latched; policy deadline crosses ready | Actual basic/held response meets declared bound and path identity | 07, 18 |
| R10 | Second structured fatal fault while child stays alive | Child retired; next logical job does not reuse it | 06 |
| R11 | Current/foreign live journal ↔ recovery scan | No mutation of live file/row; abandoned control recovers | 01, 19 |
| R12 | Fuller WAV beside degraded .blk; terminal/deleted row beside residual files | Never replace best source or reoffer resolved/deleted work | 01, 02, 08 |
| R13 | Independent corrupt/reordered/duplicate journal, torn footer, bad hash/count | Correct classified damage; no false complete artifact | 08, 19 |
| R14 | Overflow journal while actual memory capture remains intact | Full live input; recovered gap positions/counts honest | 08, 19, 20 |
| R15 | Pause before journal open; cancel/discard; release writer | No late recreation of cancelled journal | 01, 04, 08 |
| R16 | Aligned/misaligned truncated worker WAV | Rejected or explicit incomplete classification, never silent shorter original | 10, 20 |
| R17 | T0 capture → T1 recovery with different cfg rate and known discontinuity | Original timestamp/rate/positions preserved; unknown stays unknown | 09, 20, 23 |
| R18 | Delete ↔ worker-WAV publication / retry / final output admission | No recreated file, revision, inference retry, or host write | 02, 23 |
| R19 | Stream start/stop/close exception with known buffered samples | Prefix preserved; stale stream cleared; next capture really starts | 11, 21 |
| R20 | Lost Fn/key-up, delayed release, hands-free forced stop, lost idle mouse-up, key↔mouse | Trigger-specific cleanup; positive next capture; no cross-release | 15, 21 |
| R21 | Synthetic exception canaries plus binary stderr / long line / old drainer | No content in events; no diagnostic exception; bounded generation-owned bytes | 12, 16 |
| R22 | _insertion=None with one active completed job | Saved/copy outcome once; active set empty; pending zero | 17, 21 |
| R23 | Ordinary complete f32 capture + healthy worker + successful cancelled/noncancelled controls | Exact bytes, positive stage results, correct one-job usage, no vacuous pass | All |

### Crash-Point Matrix

| Boundary interrupted | What exists at that moment | Current recovery assessment / required classification |
|---|---|---|
| Captured block before memory/queue handoff | Device callback state only | Lost samples cannot be reconstructed; never fabricate them |
| After memory append, before journal persistence | Full process memory; possibly queued block | Process death can lose unpersisted suffix; normal live ASR should still use memory |
| During block header/payload write | Complete prefix plus torn record | Recover verified prefix; distinguish tail from interior corruption |
| After complete blocks, before footer | Complete retained blocks; capture finalization unknown | Preserve samples; distinguish known block integrity from unknown capture completion |
| During/after false or partial footer | Footer may be incomplete or inconsistent | Current parser does not verify; repair must validate or classify unknown/corrupt |
| During final WAV publication | Final pathname with header/prefix may exist | Current reader can accept aligned prefix; stage/validate before dispatch |
| WAV complete, journal still present | Two possible audio sources | Recovery must compare provenance/completeness, not blindly overwrite WAV |
| Request accepted / during model load | Parent job plus temporary audio; worker may not dispatch | Restart must preserve audio and bound readiness; no new authority after close |
| During ASR/cleanup | In-flight generation/attempt | Fatal retirement and explicit executed identity; cancellation/deletion remain authoritative |
| Before/mid/after response frame | Pending request plus zero/partial/full bytes | One resolution; malformed frame affects only owning generation; late unknown result ignored |
| After parent parse, before durable state/evidence | Result in parent memory | Audio/recovery remains; no insertion assumed solely from worker success |
| After atomic evidence publication, before insertion | Replayable result but no physical output yet | Do not count as inserted; deletion can still revoke delivery |
| Physical insertion before durable outcome | External side effect may have happened | Do not auto-reinsert on uncertainty; preserve posted/unknown versus confirmed distinction |
| Terminal outcome before journal cleanup | Stale audio file may remain | Durable terminal state must prevent automatic recovery/duplicate offering |
| Deletion committed before delayed publication | Durable tombstone, no pending intent for nonexistent new file | M03 must not recreate the file or cached output; current outside-store path is unfenced |
| Store/event close while producers remain alive | Writers reject new work | Bounded rejection is honest, but producer shutdown must prevent lost terminal work/respawn |

The matrix describes information availability and expected recovery disposition. It does not claim kill-point tests were executed or that every possible crash has an exactly-once external insertion solution.

## Downstream Impact

| Consumer | Narrow affected contract | Not part of this audit |
|---|---|---|
| M07 | Actual cleanup path, readiness deadline, fatal worker retirement | Semantic fidelity/normalization/validator re-audit |
| M08 | Parent cancellation/deletion authority before physical delivery; terminal callbacks | Target adapter certification or broad insertion redesign |
| M09 | Correct recovery population, original audio, failed/pending state, explicit retry | General Hub UX/accessibility review |
| M13 | Executed attempt/generation, one logical job, true capture time | Analytics formulas or dashboard audit |
| M14 | Capture completeness, original offsets/rate/time, same family, original consent, no resurrection | Learning quality, labels, export algorithm re-audit |
| M15 | Repaired lifecycle baseline, real-model failure/restart and performance evidence | Starting model qualification or the M15 milestone |

## Recommended Repair Order

1. **Close ownership and authority holes first:** 01–04 plus 23. Agree on abandoned-capture ownership, deletion/publication arbitration, per-generation pending ownership, and closed admission. Include delayed journal discard/recreation in that ownership work.
2. **Repair execution/fault truth:** 05–07, 12, 16. Carry failure identity, retire fatal generations, make readiness/serviceability honest, and make diagnostics safe/nonthrowing. Preserve the fixed M07/M11 output semantics.
3. **Repair audio/recovery truth:** 08–11 plus 19–20. Validate/version framing and finalization, preserve gap/time/rate provenance, atomically publish and strictly read worker input, and make Recorder failure handling exception-safe.
4. **Complete smaller lifecycle/protocol boundaries:** 13–15, 17. Add response identity checks/write-all/path validation and correct trigger/terminal bookkeeping without a broad app rewrite.
5. **Independently review the first production repair:** freeze that SHA; challenge the repair’s new lock ordering, callback dependencies, deletion TOCTOU windows, version migration, retry accounting, and test population assumptions. Regressions for confirmed review findings must fail on first-pass code and pass on final repair.
6. **Refresh evidence and M03 verification entries only.** Preserve historical acceptance and M01/M02 runbook data; do not mark native checks passed in cloud.

The order is a dependency recommendation, not permission to implement in this read-only session. Design Concerns 24–27 require adjudication; do not silently expand them into mandatory rewrites.

## M03 Readiness Verdict

**C — Significant capture/worker lifecycle weaknesses.** The recommendation is a bounded M03 remediation campaign on current main, not an architectural restart. Current source has concrete paths that violate ownership, deletion, lifecycle, attempt, and audio-provenance guarantees. The existing tests do not independently challenge several of those paths and, in the loading case, model a different execution schedule.

The audit is not “inconclusive” merely because native/model tests were not run: the source findings and deterministic repro designs are concrete. Their observed runtime behavior, repairs, and regression results still require the cloud session; physical Mac verification remains deferred honestly.

Pending native verification does **not** block the next read-only milestone audit during this campaign unless an unverified condition makes downstream static analysis invalid. The repaired branch should only be described as CLOUD_REMEDIATION_COMPLETE_PENDING_LOCAL_VERIFICATION after all cloud-repairable findings, independent review, portable/compatibility tests, evidence, runbook entries, and push requirements are complete. No such remediation-complete claim is made by this report.

## Evidence Navigation and Coverage Limits

All repository source references in this report are pinned to the audited commit. Ranges given above are inspected source spans, not claims that every line in a span is defective. Function names are the precise navigation anchors. GitHub connector response-wrapper line numbers were not substituted for actual source line numbers.

Primary requirements read: README; START_HERE; STATUS; M03/P01–P04 milestone material; Spec S06/S09/S25/S29 producer fields/S30.1; Evaluation EV-04/EV-05/EV-18 and E19.2 producer requirements; contracts INDEX/jobs/events/store/worker/capture/artifacts/targets/training_evidence/asr_hints; M01/M02 remediation handoffs and current M03 historical handoff/acceptance.

Production inspected: supervisor and worker protocol/lifecycle; capture journal; Recorder; Transcriber; legacy cleanup loader/fallback seams; capabilities; hotkey; relevant AppDelegate capture/coordinator/recovery/retry/termination/delivery/usage paths; collector consent/provenance/evidence; store lifecycle/jobs/deletion/purge/audio helpers; the minimal insertion transaction interface. Overlay state definitions and their app integration were inspected directly; the overlay was not natively rendered or visually certified. No new dependency/network behavior was inferred from brand/model names.

Tests and records inspected: all five named M03 lifecycle/fidelity/protocol/live suites, the fake worker, benchmark_m03, current M02 app wiring and relevant consent/deletion collector regressions, M02 recorded portable result metadata, and the shared verification page’s preservation rules. This is not a claim to have rerun or exhaustively audited every later milestone’s tests.

### Pinned source index

- [`docs/v2/LOCALFLOW_V2_MILESTONES.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/LOCALFLOW_V2_MILESTONES.md)
- [`docs/v2/LOCALFLOW_V2_SPEC.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/LOCALFLOW_V2_SPEC.md)
- [`docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md)
- [`docs/v2/contracts/worker.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/worker.md)
- [`docs/v2/contracts/capture.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/capture.md)
- [`docs/v2/contracts/jobs.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/jobs.md)
- [`docs/v2/contracts/store.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/store.md)
- [`docs/v2/contracts/events.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/events.md)
- [`docs/v2/contracts/artifacts.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/artifacts.md)
- [`docs/v2/contracts/targets.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/targets.md)
- [`docs/v2/contracts/training_evidence.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/training_evidence.md)
- [`docs/v2/contracts/asr_hints.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/contracts/asr_hints.md)
- [`docs/v2/handoffs/M01.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/handoffs/M01.md)
- [`docs/v2/handoffs/M02.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/handoffs/M02.md)
- [`docs/v2/handoffs/M03.md`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/handoffs/M03.md)
- [`docs/v2/acceptance/M03/results.json`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/acceptance/M03/results.json)
- [`docs/v2/acceptance/M02/remediation/portable_tests_bfbc63c.json`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/acceptance/M02/remediation/portable_tests_bfbc63c.json)
- [`docs/v2/VERIFICATION.html`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/docs/v2/VERIFICATION.html)
- [`localflow/v2/supervisor.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/supervisor.py)
- [`localflow/v2/worker.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/worker.py)
- [`localflow/v2/capture_journal.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/capture_journal.py)
- [`localflow/v2/capabilities.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/capabilities.py)
- [`localflow/app.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/app.py)
- [`localflow/audio.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/audio.py)
- [`localflow/stt.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/stt.py)
- [`localflow/cleanup.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/cleanup.py)
- [`localflow/hotkey.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/hotkey.py)
- [`localflow/overlay.py`, state definitions and main-thread ownership](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/overlay.py#L1-L150)
- [`localflow/v2/training.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/training.py)
- [`localflow/v2/store.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/store.py)
- [`localflow/v2/eventlog.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/eventlog.py)
- [`localflow/v2/insertion/service.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/localflow/v2/insertion/service.py)
- [`tests/v2/lifecycle/test_worker_protocol.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/test_worker_protocol.py)
- [`tests/v2/lifecycle/fake_worker.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/fake_worker.py)
- [`tests/v2/lifecycle/test_capture_journal.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/test_capture_journal.py)
- [`tests/v2/lifecycle/test_audio_fidelity.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/test_audio_fidelity.py)
- [`tests/v2/lifecycle/test_lifecycle.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/test_lifecycle.py)
- [`tests/v2/lifecycle/test_worker_live.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/lifecycle/test_worker_live.py)
- [`tests/v2/test_m02_app_wiring.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/test_m02_app_wiring.py)
- [`tests/v2/training/test_m02_remediation_collector.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/tests/v2/training/test_m02_remediation_collector.py)
- [`scripts/v2/benchmark_m03.py`](https://github.com/scalinity/LocalFlow/blob/2b9b7a1832ebf737c2a6c346a28e9b96ac4ba44e/scripts/v2/benchmark_m03.py)

---
End of read-only M03 audit. The separate cloud-remediation handoff is the next deliverable; no implementation or next-milestone work is authorized by this audit.
