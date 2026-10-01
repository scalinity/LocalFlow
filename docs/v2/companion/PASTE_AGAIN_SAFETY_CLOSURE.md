# Quiet Editorial — Paste Again safety closure

Branch-local qualification, September 29, 2026 (native logs cross midnight UTC).
This is not a merge or an update to main-facing milestone qualification.

Starting commit: `e8eee9555a96d5286794c0eda654d3a72d08cc35`.
Final production commit: `cb3f998cdd25a40a7af0c416917fbc7ff0b5c591`.
The final documentation commit follows that production commit. Main remains
`78ebde872f1d08452de56bd008dcf75be545c3f8`.

## Owner decision and repair

The previous POLICY-D03 contract permitted a deliberate application/window
click. Real native qualification demonstrated a titlebar click reusing an old
focused field and inserting History text. The owner explicitly narrowed this
policy: only a click resolving to a currently editable text destination grants
History Paste Again authority. The dated original failure remains evidence;
the additive refinement is `POLICY-D03-EDITABLE-TARGET` in the decision ledger.

Fail-first cases PA-EDIT-01 through PA-EDIT-06 produced five unsafe failures and
one editable success against the old implementation. The repair resolves the
actual event coordinate to an application-owned AX hit, proves text/write
capability and containment, and binds the opaque element/window identity to
the operation. Independent controls cannot inherit a previously focused field.
Non-editable or unsupported hits keep the picker armed under the original
timeout without acquiring authority. Settled focus and M08 must still name the
same writable element and window. Denied applications are rejected before hit
metadata is read; opaque AX references are never serialized.

A native TextEdit text view omitted AXEnabled while exposing writable text.
The follow-up regression and repair retain positive capability proof, reject
explicit disabled state, and avoid an app-specific exception.

## Isolated regression results

Commands use `.venv/bin/python tests/v2/context/run_isolated.py <suite>`.
That runner blocks live AX and event posting and redirects the general
pasteboard to a private test pasteboard. These are compatibility results, not
additional real microphone or native AX evidence.

| Suite | Result |
| --- | --- |
| `tests/v2/crossmilestone/test_xm_paste_again.py` | 15/15 |
| `tests/v2/crossmilestone/test_paste_editable_target.py` | 10/10, PA-EDIT-01–10 |
| `tests/v2/insertion/test_editable_hit.py` | 9/9 unittest methods, with capability/geometry subcases |
| `tests/v2/insertion/test_m08_remediation.py` | 57/57 |
| `tests/v2/insertion/test_insertion_pipeline.py` | 5/5 |
| `tests/v2/insertion/test_insertion_races.py` | 13/13 |
| `tests/v2/insertion/test_insertion_attribution.py` | 10/10 |
| `tests/v2/ui/test_companion_bridge.py` | 16 named checks |

All final invocations passed against production commit `cb3f998`. New cases
also cover same-app field substitution, invalidation during click settling,
non-editable click followed by editable success, and timeout during settling.

## Packaged native evidence

The real recipe `scripts/build_app.sh --output <isolated .app>` produced
`LocalFlow-editable-authority-v2.app`. Its BUILD.json records `cb3f998` and
`dirty=false`. The launcher, UI and worker ran with the synthetic data override
and cached local models. AXIsProcessTrusted returned true inside the actual
running UI process; the debugger was detached before interaction.

| Gate | Evidence and scope |
| --- | --- |
| Original titlebar failure | Actual History control, native titlebar click: empty owned document unchanged; picker still available. |
| Editable success | Subsequent native click inside the owned text view: one confirmed 58-character AX replacement. M08 identity, owner, editable_hit, window and selection passed. Destination stayed active. |
| Newer request | Older A cancelled by real Hub reopen; newer B armed through History and inserted once. A absent. This native UI path includes reopening; direct `superseded` state is covered by the existing regression. |
| Invalid target | Owned target closed after the native editable click, before the settling callback. `editable_destination_changed`, zero insertion attempts. |
| Focus only | Native activation without a field click caused no insertion; rechecked on the new artifact. |
| Timeout | Real timer on the new artifact: 30.004 seconds, timed_out, no insertion. |
| Escape | Prior native pass retained; current isolated cancellation cases pass. Additional injected-key attempts on the new artifact did not establish native cancellation and are inconclusive, not additional passes. |
| Configure → Accept | Genuine selected-text transform; actual Configure control, safe display-name edit, Save, return and actual Accept. One intended replacement confirmed. |
| Configure → stale Accept | Second genuine result; Configure restored the display name, then the owned source selection was changed. Actual Accept returned target_changed / revalidation_failed; source unchanged, no replacement. |

Transform collection was off, so jobless Accept intentionally persisted no
insertion observation row. Visible synthetic witnesses and content-free
completion events provide the native evidence. The canonical Accept path
submits M08 strict_replacement=True. The owner expressly permitted the existing
synthetic clipboard copy offer for the one stale-source test; clipboard
contents were not read/logged. Clipboard policy was not changed.

An automation lookup during the first build attempt inadvertently launched a
second review bundle without the synthetic environment. Both copies were
stopped and that run was excluded. No installed app was launched or modified,
and no real-data test was performed; possible ordinary startup metadata effects
from that excluded copy were not independently verified. All qualifying v2
interactions used the verified isolated process chain.

## Retained evidence and boundaries

The earlier launcher lifecycle, real microphone/PTT/automatic insertion,
protected-insertion focus deferral, retry-without-target refusal, packaged
AX/keyboard smoke and theme persistence passes retain their documented scope.
The History-only target subtype does not change normal PTT, strict replacement,
retry provenance, model behavior, History source semantics or clipboard policy.

The owner-authorized centered 360 × 38 Paste Again pill at `e8eee955` is intact.
No frontend rendering changed; the 17-reference, 64-capture visual package is
retained with its original SHA provenance. No broad visual campaign was rerun.

Typing anomaly remains OWNER_MANUAL_OVERRIDE after non-reproduction; it was not
proven unrelated to LocalFlow and did not visibly recur. The owner accepted the
absence of a visible Tab outline. VoiceOver listening, active Reduce Motion
visual inspection and a global OS appearance transition remain honest
owner-only polish checks; structural AX, theme overrides and relaunch
persistence already passed. No new waiver is inferred for those items.

M07 and M11 qualification are unchanged. M15/M16 were not started.
No merge, push, TCC reset/rebinding or installed-app update is part of this pass.
Private screenshots and detailed local evidence remain outside the repository.

The new review artifact exited through its actual Quit LocalFlow menu; the
launcher, UI and worker were independently verified gone. Accessibility
permissions were left unchanged for the owner to restore afterward.

Closure state: **READY_FOR_DANIEL_VISUAL_APPROVAL**, using the expressly
retained prior native gates and the new repair evidence above. In particular,
Escape handling was not changed; the prior native Escape pass is retained
under the owner's preserve-existing-evidence instruction. The additional
injected-key probe is not converted into a pass or an owner waiver. Remaining
human polish observations are named above. Publication and merge remain the
owner's separate decisions.
