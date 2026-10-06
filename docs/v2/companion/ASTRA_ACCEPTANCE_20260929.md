# Quiet Editorial final acceptance pass — 2026-09-29

Branch-only review state: **NATIVE_QUALIFICATION_PENDING**. This is not merge
approval. Main remains `78ebde872f1d08452de56bd008dcf75be545c3f8`.
M07, M11, M15 and M16 qualification state is unchanged.

Starting branch: `fc8661758b1a05ab67ef03136728bf3c258ae0eb`.
Final production: `8c64746cc8a83ccc64a5d6322f3eb22f043bc5cd`.

## Targeted changes

- Dictionary hero copy now occupies two lines: 223.6 pt versus 245.3 pt
  before this pass (reference approximately 219 pt at equal window width).
- Input, select and textarea boundaries have at least 3:1 contrast on their
  ordinary adjacent surfaces. Selected segments have a contrasting inset ring.
- Removed text in the native review panel and its onboarding illustration uses
  the approved dark tertiary value, `#908B83` (5.09:1 on the ink background).
- Protocol versions must be integers: booleans and floats no longer pass as `1`.
- Owner-authorized `LOCALFLOW_DATA_HOME` redirects app data, logs and preferences;
  absent the override, paths are unchanged. Model caches remain independent.
- The existing packaging script accepts `--output /absolute/path/name.app`,
  refuses existing outputs, and stamps source revision/dirty state. Qualification
  does not replace the installed app. Packaged provenance reads that stamp.
- Screenshot tooling can load packaged modules and capture the native review
  panel. Memory tooling now really hides the window, repeats ten cycles, and
  reports repeated route/theme timing distributions.

## Package and evidence

Exact final build command:

```sh
zsh scripts/build_app.sh --output "$HOME/Documents/Tools/LocalFlow/build/companion-review/final/LocalFlow-final.app"
```

The bundle is `com.danny.localflow`, version `0.1.0`. Its source stamp is the
production SHA above with `dirty: false`; frontend source hash is
`9b30484cb5ca6b0264a58331bacc5450dc87f54cdb9724ef78f382d0c2865796`.
Bundled assets, fonts, icon and notices resolve without Node/Vite. The existing
venv packaging still uses this Mac's Homebrew Python interpreter; portability
to another machine was not qualified.

LaunchServices launched the actual final bundle using an isolated synthetic
data home, offline model settings and no permission prompts. It emitted
`app.ready / shell_interactive`, and open database/log/journal paths were under
the isolated home. The intentionally unavailable synthetic speech model failed
to load as expected. The new launcher also reported `accessibility_not_trusted`.
No permissions were granted and the installed application was not replaced.

Computer-use selection by exact package path returned `-10005 timeoutReached`.
The launcher forks the UI under the shared Python application identity, also
used by the installed app. No ambiguous Python instance was driven. Consequently
the menu-bar UI, close-button behavior, packaged PTT and launcher-driven route
walkthrough remain unqualified.

Private evidence lives at `<repo>/build/companion-review/final/`:

- `index.html`: self-contained offline comparison page, 24 surface comparisons.
- `light/`, `dark/`: 32 captures each, including the native review panel.
- `comparison/`: reference/light/dark comparisons and complete contact sheets.
- `SCREENSHOT_MANIFEST.json`: SHA-256 hashes and production provenance.
- `evidence/`: exact test logs, initial failures, rechecks, security probes,
  performance JSON, geometry, launcher evidence and palette-update verification.

All 17 references and all 57 previous implementation images were inspected.
All 64 final captures were inspected. `current-home.png` is a design reference.
Final screenshots are real AppKit/WKWebView windows using modules loaded from
the final bundle, over an isolated test harness. They are **not** captures driven
through the packaged launcher's menu. This distinction is visible in the page.

## Visual decisions

Both themes are coherent and convincingly follow the reference shell, spacing,
hierarchy and selective serif typography. No hardcoded white dark-mode panels
were observed. Forms, native review and disabled states remain legible.

| Finding | Classification | Disposition |
| --- | --- | --- |
| Dictionary hero height | POLISH | Fixed, now within about 5 pt of normalized reference |
| Form/control boundaries | MATERIAL | Fixed and contrast measured |
| Native/onboarding removed text | MATERIAL | Fixed to approved accessible dark value |
| Permissive bridge version type | MATERIAL | Fixed; fail-first regression and native-channel probes |
| Synthetic package isolation/provenance | MATERIAL | Fixed; default behavior preserved |
| Transforms hero 216.2 pt versus approximately 200 pt | ACCEPTED_DIFFERENCE | Real instructions remain readable; no behavior changes |
| Add Dictionary modal 275.5 pt versus approximately 256 pt | ACCEPTED_DIFFERENCE | Scope selector and form spacing remain balanced; no clipping |
| Calendar selected range only | ACCEPTED_DIFFERENCE | Preserved; no fabricated months |
| Decorative transform glyph crop | ACCEPTED_DIFFERENCE | Intentional crop; no content/control clipped |
| LocalFlow-only routes and settings | ACCEPTED_DIFFERENCE | Real local functions; no subscriptions or Vibe-coding toggle invented |
| Required active/package qualification absent | BLOCKER | Remains pending; prevents readiness certification |

The global Quiet Editorial section was updated to light `#736E67`, dark
`#908B83`; bytes outside its explicit markers were verified unchanged. That
private configuration is not part of this repository.

## Automated evidence and its limits

All seven companion suites pass (46 checks). Data-home/provenance adds two
checks. Svelte check reports zero errors/warnings; the production build passes.
Across 122 test files, 117 were exercised and their latest invocations succeeded;
eight contain native tiers, some incomplete. Five model-backed files were not
run. The previous “110/111” campaign and accepted M11 model residual are not
re-certified by this pass.

The broad sweep initially passed 106/107 files. Passive M13 Insights had two
layout/selection failures, one persisted on a focused retry. The corresponding
main-baseline checks passed, and a subsequent entire current-branch passive run
passed 8/8. These transient failures are retained in evidence, not erased.

| Native suite | Automated result | Remaining |
| --- | --- | --- |
| M06 native AX | 7 checks, PASSED_NATIVE_AUTOMATED | None in this suite |
| M08 native insertion | 12/12 cases; one residual characterized; five diagnostics | Existing residual unchanged |
| M10 panes | 3/3 passive, PASSED_NATIVE_AUTOMATED | 7 MANUAL_REQUIRED active cases |
| M11 remediation native | 16/16, including panel geometry | Real Accept-after-Configure MANUAL_REQUIRED |
| M12 Scratchpad | 1/1 passive, PASSED_NATIVE_AUTOMATED | 11 MANUAL_REQUIRED active cases |
| M13 Insights | 8/8 passive on final recheck | 3 MANUAL_REQUIRED active cases |
| M14 Training | 10/10 passive, PASSED_NATIVE_AUTOMATED | Broader milestone qualification unchanged |
| Cross-milestone Hub | 6/6 passive, PASSED_NATIVE_AUTOMATED | Real-click picker MANUAL_REQUIRED |

M06/M08 used owned synthetic native targets. The other passive suites used real
AppKit under `tests/v2/context/run_isolated.py`, which blocks general desktop AX
and global event posting and redirects the general pasteboard to a private one.
M11's selection cases include modeled targets; its 16 passes do not establish
the pending real-window Configure/Accept sequence.

PTT/insertion compatibility passes at the coordinator/synthetic-target boundary:
ordinary captured-destination insertion, hidden/background/frontmost companion,
note-bound Scratchpad, protected-insertion deferral, retry without authority,
and modeled Paste Again cancellation/fresh-click authority. No live microphone
or real foreground application was used. Actual packaged PTT remains blocked by
the launcher's absent Accessibility trust.

The real packaged-module WKWebView refused malformed JSON, array envelopes,
boolean protocol version, unknown command, unexpected payload fields and
invalid request IDs. Existing tests cover stale tokens/results, revocation,
outcome_unknown, cancellation and content-free failure logs. The frontend has
no SQLite/model access or target-authority decisions.

Remote image, script, fetch, WebSocket and inline script probes were blocked by
CSP; navigation stayed `lfhub://app/index.html` and `window.open` returned null.
Ordinary final captures emitted zero CSP violations; attack probes emitted five
expected violations. No frontend web access was required.

Keyboard handlers, History arrows, modal focus trap/restoration, Escape, resize
and stale publications pass in WKWebView. Contrast measurements include light
tertiary/card 4.52:1, dark tertiary/raised 4.51:1, form boundaries at least 3.58:1,
and selected-segment rings at least 3.87:1. These are selected role measurements,
not an exhaustive WCAG certification. Actual packaged accessibility-tree,
native key equivalents, OS Reduce Motion and screen-reader behavior remain
MANUAL_REQUIRED.

Theme tests exercise live effective NSAppearance light/dark, explicit overrides
and preference persistence/reconstructed controller. They do not prove a global
macOS appearance toggle or a full packaged process relaunch with saved theme.

## Performance and retained memory

Final production modules, 2,000 added synthetic History rows, no broad tests
running during the final benchmark:

| Operation | n | p50 | p95 | max |
| --- | ---: | ---: | ---: | ---: |
| Alternating Dictionary/History, usable rows | 20 | 12 ms | 16 ms | 32 ms |
| Alternating Light/Dark, computed canvas changed | 20 | 7 ms | 16 ms | 16 ms |

One cold measurement: first usable render 122.9 ms; first History page 19 ms,
200 rendered rows. Cold values are single samples, not percentile estimates.

| Stage | App process KiB | WebKit aggregate KiB |
| --- | ---: | ---: |
| Before companion creation | 113152 | 0 newly attributable |
| First open | 154608 | 94208 |
| Hidden after route work | 158176 | 149728 |
| Cycle 5 hidden | 158496 | 153248 |
| Cycle 10 hidden | 158528 | 160176 |
| Final settled | 158368 | 160112 |

Ten true hide/reopen cycles retained the same view. Hidden-to-final combined
growth was 10.33 MiB, below the owner's 25 MB criterion. Retained WebKit is
accepted for instant reopening; no lifecycle redesign was made. Measurements
are RSS of the harness app plus the three newly appearing WebKit processes,
not full packaged-launcher RSS or a long-duration leak certification.

## Outstanding acceptance gates

1. Grant/verify the final package's Accessibility permission through the owner,
   then exercise its menu and routes, close/reopen, PTT and protected insertion
   in owned synthetic windows. Do not target the installed app's real data.
2. Real-click Paste Again: focus alone must do nothing; a deliberate owned-target
   click must yield exactly one validated paste. Exercise all cancellation paths.
3. Real-window Configure Polish, safe configuration edit, return and Accept:
   prove source binding and current strict replacement revalidation.
4. The 21 active M10/M12/M13 cases explicitly requiring hands-off input.
5. Native keyboard/AX, global OS light/dark and Reduce Motion, and full packaged
   relaunch persistence. Model qualification remains in its existing workstream.

No merge is authorized by this document.
