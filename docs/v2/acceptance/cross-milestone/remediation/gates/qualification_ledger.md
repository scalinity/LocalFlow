# Cross-milestone remediation — native, manual, model and human qualification ledger

The source-remediation campaign closes with these obligations still open. None is passed or implied passed: each keeps its exact case ids and the later gate or runbook check that owns it. Automated evidence in `remediation/final/` counts only for what it actually exercised.

## GATE-G07 — closed for the source remediation, with remaining native qualification

State: `CLOSED_FOR_CROSS_MILESTONE_SOURCE_REMEDIATION_WITH_REMAINING_NATIVE_QUALIFICATION`.

Automated evidence and what it covers: `final/native_xm_hub.json` — the owned synthetic Hub suite, passive tier, 6/6, never frontmost (transform row fills its instruction and Update keeps it; stale transform editor admission; Export Validate result lifetime; the minimum-width Settings controls; pane switch; window close as exercised there).

Remaining native qualification:

| Obligation | Case ids | Owner |
|---|---|---|
| The Hub's active tier: real keyboard and focus, Insights, Review / A-B, Your Voice, active deletion and revocation in a key window | XM-C196, XM-C121 | GATE-G07 active tier; VERIFICATION.html M09-V001 (larger text, light and dark), M09-V002 (keyboard only); M12 native checks LF-M12-N002/N004/N006 |
| Clipboard survival on the real pasteboard | XM-C197 | `tests/v2/insertion/test_native_insertion.py` native tier; VERIFICATION.html M08-V002 |
| History → Paste Again with a real click: the Hub steps aside, the click lands in a real app's field, the text is pasted there, Esc and the 30-second timeout cancel, and a secure field refuses | POLICY-D03 | native qualification of the picker's NSEvent global monitors and hint panel (the policy is proven on the production path in `test_xm_paste_again.py` with the monitors replaced by the test acting as the user) |
| Retry from the Hub or Recovery menu in the real app keeps its result without inserting | XM-C042 | native qualification (proven on the production path in `test_xm_g06_c2.py`) |

## GATE-G08 — closed for the source remediation, with remaining human / M15 performance qualification

State: `CLOSED_FOR_CROSS_MILESTONE_SOURCE_REMEDIATION_WITH_REMAINING_HUMAN_M15_PERFORMANCE_QUALIFICATION`.

Measured after correctness, on this Mac, and kept as exactly that evidence: the dictation-shaped Store writer wait beside each background job, the Hub's construction, first usable result and full pass, and History search — each with its benchmark's own validity controls (the final benchmark directory named in `adjudications.json` records).

Remaining: the true human-speaker release-to-terminal dictation measurement (p50/p95/p99/max) on the reference Mac. No synthetic-audio figure stands in for it. Cases XM-C191 (DEFERRED_HUMAN), XM-C192, XM-C194, XM-C195, XM-MH32 (DEFERRED_M15); owner M15-AC03/AC04.

## Model qualification

| Obligation | Case / requirement | Owner |
|---|---|---|
| M07 long-prompt cleanup trial | M07-V001; XM-C065 | VERIFICATION.html M07-V001; `tests/v2/fidelity/test_fidelity.py` (model-backed EV-09); M15-AC02 |
| M07 adjudicated real-text stratum | M07-V002 | PENDING owner adjudication/corpus freeze; private 60-case provisional legacy review queue prepared, zero human judgments; preserve 30 dev / 10 validation / 20 held-out boundaries |
| M11 integrated record (one misdirected review, fourteen output-limit fallbacks) | GATE-G10 | M11 local verification |
| ASR language coverage | LF-R27 | M15; EV-17 (M16) |
| A qualified decoder adapter and acoustic strata | LF-R29 | M15 |

## Human and whole-app acceptance

| Obligation | Case / requirement | Owner |
|---|---|---|
| Real microphones and device switching | LF-R04 | VERIFICATION.html M03-V006 |
| Whole-app offline operation observed at runtime | LF-R25 | EV-17 (M16) |
| The runbook's manual checks, all Not run as committed | — | docs/v2/VERIFICATION.html |
| M15 preconditions and acceptance | XM-C187, XM-C188, XM-C189, XM-C190 | M15 |

## Owner-polish closure — September 30, 2026 (additive)

The twelve owner-polish gates are closed. Native evidence uses the clean
`ff14f38edd8d47b35645c66db46e7171477b9974` review bundle, an isolated
LocalFlow data home, and an owned external AppKit target with valid
LaunchServices/NSWorkspace and AX process, window, field and selection identity.
The later owner-requested Home greeting change (`899f6ba`) affects no shortcut,
transform, insertion or PTT behavior. Its bundle refresh is recorded separately
in the final owner report. Historical obligations above retain their scope.

| Relevant item | Disposition | Evidence / boundary |
|---|---|---|
| Real default global Polish, Prompt Engineer and Concise; leakage; repeat | CLOSED_BY_CURRENT_EVIDENCE | Each default dispatches one production transform. Unchanged synthetic selection survives review; each Accept makes one confirmed strict replacement. Polish down/two repeats/up produces one generation. Ordinary keys pass. |
| Built-in reassignment and custom hotkey | CLOSED_BY_CURRENT_EVIDENCE | Real companion recorder saves Concise to Control–Option–C; old Option–3 dispatches nothing; new chord works before/after restart; reset restores Option–3. One custom Control–Option–R invokes its actual id and confirms one replacement; disabling unregisters it. |
| Expanded review authority and stale Accept | CLOSED_BY_CURRENT_EVIDENCE | External NSWorkspace and AX window/field pids remain the owned target during review. Changed synthetic text refuses with target_changed/revalidation_failed and zero edits. |
| Existing PTT trigger | CLOSED_BY_CURRENT_EVIDENCE | Native fn flags-changed press admits one capture; release yields the expected below_min_duration discard. No transform dispatch. Separate speech/device qualification is unchanged. |
| Bounded real History audit | CLOSED_BY_CURRENT_EVIDENCE | 12 qualifying jobs available; exactly 10 classified: 3 clipboard/readback_mismatch, 1 AX/readback_pending, 6 legacy/v1_target_unobservable. EXPECTED_STRICT_VERIFICATION_LIMIT; no new confirmation bug established; no confirmation/state relabeling changes. |
| Prior action routing, clear/collision/delete/reconstruction, Models, Paste Again, formatting and S13 evidence | RETAIN_PRIOR_EVIDENCE | Prior targeted suites and owner-approved visual state retained; Models also shows Speech recognition — Ready and Optional speech features in the current native companion. |
| Typing-anomaly uncertainty | OWNER_OVERRIDE | OWNER_MANUAL_OVERRIDE retained; no attribution to another app is claimed. Test-helper event plumbing is not a new production diagnosis. |
| M07-V001/V002, cleanup model/semantic residuals | STILL_OPEN_SEPARATE_QUALIFICATION | No M07 advancement or new model campaign. |
| M11-V001–V006, GATE-G10 and model/semantic measurements | STILL_OPEN_SEPARATE_QUALIFICATION | Interaction evidence does not complete the milestone's extended human/model trial. |
| GATE-G07/G08, older runbook/manual/device/accessibility obligations | STILL_OPEN_SEPARATE_QUALIFICATION | Only overlapping owner-polish facts above are closed; broader clipboard, picker, speech, VoiceOver, Reduce Motion, whole-app and performance trials are not newly passed. |
| M15/M16, installation, publication and merge | OUT_OF_SCOPE | Not started; main and installed app untouched; no push or merge. |

Detailed content-free metadata, synthetic target witnesses and the 89-item final
report remain in the owner's local review directory under
`final/owner-polish/final-qualification/`. This supplement does not modify the
runbook's saved statuses or certify any complete milestone.

## Pre-M15 qualification attempt — September 30, 2026 (additive)

State: `PRE_M15_BLOCKED_M07_V001`. Source `5da6836`; dedicated branch
`pre-m15-qualification-closure-20260930`. M14 / Quiet Editorial remains closed.

Daniel performed both M07-V001 dictations in an isolated private data home.
He supplied Hub and TextEdit screenshots and delegated their assessment to the
agent; this is not a separately supplied human PASS judgment. Source, Normalized
and Cleaned stages are retained for both cases. The long prompt's two model
candidates failed fidelity validation (coverage, numeric values, negation and
novelty); the applied output equals the Normalized source exactly. Constraints,
four list items and sign-off survive, but both corrections remain unresolved.
No output limit was hit, and no correction proposal pass ran. Inspection found
the single-word marker supported by the correction guards absent from the
proposal-pass trigger. The literal attempt used an existing normalization escape
and did not establish paired quoted-literal preservation; initial capitalization
alone is permitted by the cleanup contract. Neither attempt closes M07-V001.

Content-free stage hashes, paths/reasons, model/runtime/prompt identities and
dispositions: `acceptance/M07/results.json` → `pre_m15_qualification_20260930`.
Actual transcripts, audio, rejected proposals and owner images stay private.
No production fix or model/prompt change was made. Stop at this blocker:
M07-V002's reviewer and human adjudication, current M11 suite/benchmark and
Polish/Concise measurements remain unperformed. GATE-G10 is open; M15 and M16
are not started. Historical records and owner-polish closure remain unchanged.

## Authorized M07-V001 narrow remediation (additive)

Starting record `d43a326` remains intact. Trigger repair `aafedbe` admits
standalone ambiguous markers only through the existing nearby parallel-value
evidence guard; it changes no deletion, validation, prompt, model or sampling
semantics. Fail-first positives fail at `00eabba` for the missing proposal pass;
after repair the remediation suite is 40/40, engine suite passes, and isolated
pipeline is 13/13. Six ordinary-prose admission controls gain zero model calls.

Current Qwen correction measurement: 6/10 successful, including all three
negative controls. Four correction cases remain unsuccessful. The new standalone
markers reach the proposal pass, but both produce no deletion proposal; the
standalone negative marker's cleanup candidate rejects and falls back intact.
Owning fidelity is 58/60 (49 model-path passes, 9 fallback-rescued); LF-FID-012
and LF-FID-016 reproduce on the pre-repair source with identical output and path.
Literal fixtures are 20/20 (19 model-path, 1 fallback-rescued).

M07-r2 clarifies the supported spoken literal escape and retains the prior
inconclusive quote attempt; it does not change production quote handling.
No new real-speech retry occurred because automated prerequisites are not green.
State: `PRE_M15_BLOCKED_M07_V001_MODEL_BEHAVIOR`. Content-free per-case evidence:
`acceptance/M07/results.json` → `pre_m15_v001_narrow_remediation`. No further
prompt/model tuning, V002/M11 qualification, M15/M16, build, push or merge.
