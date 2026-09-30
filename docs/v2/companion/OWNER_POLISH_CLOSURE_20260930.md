# LocalFlow Quiet Editorial — Final Owner Polish Closure

Readiness: **NOT_READY_FOR_DANIEL_FINAL_VISUAL_APPROVAL**.

The source implementation is complete, but the bundled frontend is stale
and native global-shortcut qualification is incomplete. No build, app
installation, push, merge or milestone progression was performed.

Starting SHA: `7d94d37ae789de0e0fe61801ff48744477b47d2a` (clean tree).
Final source implementation SHA:
`23013db53020bc4fed68fa14d7f3e719b59ba587`.
The documentation SHA is the commit containing this closure; the owner's
external 71-item report records that exact hash after this commit.

## Implemented behavior

- Fresh built-ins: Polish ⌥1, Prompt Engineer ⌥2, Concise ⌥3. All can be
  reassigned, explicitly cleared and reset. Custom transforms have the same
  physical-key recorder. Fn-modified recordings are refused when reported
  by WebKit, and fn is always excluded from the native registry.
- Mutable `transform_meta` preferences distinguish default, user override
  and user null. Old semantic definitions/revisions remain intact. Enabled
  effective chords collide transactionally; disabling/deleting frees a
  chord, re-enabling checks ownership, and resetting never steals a chord.
- One suppressing session CGEvent tap consumes registered down/repeat/up
  events, dispatches once and never reposts keys. Menu and hotkey share the
  existing coordinator, selection capture, M11 gate and review/M08 path.
- Review now uses a borderless nonactivating rounded warm-ink speech bubble
  over the pill anchor, compact short text and bounded long-text scrolling.
  All existing review actions, original clauses and candidate identity stay
  routed through the existing coordinator. Normal dictation overlay is
  unchanged; its transforming shimmer remains the progress state.
- Paste Again only changes visible copy to “Click where you want to paste”.
  Its geometry, Escape, timeout and editable-click authority are unchanged.
- History removes common verification badges from the list. Detail says
  Sent/Sent text with the independent-verification caveat; confirmed text
  remains Inserted. No database state or confirmation logic changed.
- Models says Optional speech features, keeps engine readiness prominent,
  and maps disabled, adapter-unavailable, unexposed and missing evidence
  separately. The capability manifest and models are unchanged.

## Actual evidence and limits

Evidence directory:
`~/Desktop/LocalFlow Companion Review/final/owner-polish/`.
Frontend screenshots are **source development previews**, using synthetic
fixtures; they do not qualify the committed WKWebView bundle. Native bubble,
progress and Paste Again images are actual off-screen AppKit source objects.
They include light/dark appearances and needs-review content. Warm ink is
intentional in both appearances. No old 64-screen campaign was regenerated.

| Check | Result |
| --- | --- |
| Physical preferences/router/native tap object tests | 10/10 |
| Frontend History/capability/physical-recorder checks | 16/16 |
| Svelte source check | 0 errors, 0 warnings |
| Native AppKit bubble geometry/states/action routing | 2/2 |
| Transform definitions / pipeline / engine | 8 / 10 / 8 passed |
| Transform remediation / selection seam | 37/37 / 8/8 |
| Native transform remediation with isolated desktop | 16/16 |
| Companion transform library / bridge / dictation | 3 / 16 / 5 passed |
| Lifecycle fn/hands-free/cancel compatibility | 13 passed |
| M08 remediation / pipeline / races / attribution | 57 / 5 / 13 / 10 passed |
| Real owned-target native M08 | 12/12; one existing residual, five diagnostics separate |
| Paste Again / PA-EDIT / editable-hit methods | 15/15 / 10/10 / 9/9 |
| History query / Models companion | 11 / 4 passed |
| Committed frontend source/hash consistency | **Fails: bundle stale** |
| Real global shortcut → selected capture → review → Accept | **Incomplete** |

The first native attempts stopped at the foreground ownership guard before
posting any keys. A fresh system AX focus check then established ownership.
The source app's active event tap consumed ⌥1 and reached the existing
coordinator once; capture refused `no_focused_element`. Its NSWorkspace
frontmost identity was PID −1 for the shell-launched synthetic helper while
AX identified the helper as focused. This is recorded in
`evidence/native-attempt-8/source-native-hotkeys.json`. No new real ⌥2,
⌥3, rebound/custom, review-focus or Accept/stale-target pass is claimed.
The guard/refusal was not bypassed and production selection rules were not
changed to accommodate the helper. Earlier native closure evidence remains
historical, not a pass for this new global entry path.

The committed build consistency suite fails at the unchanged
bundle's source hash. The user-provided AGENTS rule says “Do not run
build/compile commands unless explicitly instructed”. Frontend build
authorization was requested but had not arrived at closure. Refreshing the
bundle and exercising the current UI through WKWebView remain required.

## Bounded real History audit

The read-only real database contains **eight** retained unverified jobs,
all from 2026-09-22 UTC with `v1_target_unobservable`. Both `insertions` and
`insertion_observations` are empty. Corresponding metadata-only log outcomes
match the legacy V1 path. No dictated text, session identifiers or private
target contents were exported.

Each of the eight is classified in `evidence/history-audit.json`: the
clipboard method is inferred from the legacy result constructor, which
marks readback unavailable. App/category, AX-readable/writable flags and
independent readback evidence were not retained. This sample cannot
establish whether an AX-readable/writable current destination unexpectedly
stays unverified. No current confirmation regression was established and
no insertion repair was justified. The requested minimum of ten records
is unavailable; no fake cases or extra owner dictations fill the gap.

The native M08 suite's existing private-pasteboard residual is disclosed
separately by that suite; it was not introduced or repaired by this UI task.

## Protected scope and remaining checks

M07, M11 prompts/requirement-preservation gate, model selection, the M08
insertion contract and POLICY-D03 stay unchanged. M15/M16 are not started;
STATUS/orchestration and main are unchanged. The owner typing anomaly's
manual-override disposition remains unchanged.

Required before final readiness: authorized frontend build and current
WKWebView recorder/persistence/presentation checks; genuine owned-target
native tests for defaults, rebound/custom, repeat/leakage, focus continuity
and Accept/stale refusal; Daniel's visual review. The ten-record audit
coverage gap must remain explicit. Publication is a separate owner decision.
