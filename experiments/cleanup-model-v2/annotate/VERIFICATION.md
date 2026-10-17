# Verification record

Executed on macOS on October 15, 2026. All annotation inputs were synthetic. The main LocalFlow checkout was not edited and no Git commands were run there. Its orchestration page was not edited. The default real pairs file was absent at the time checked; no real-data integration result is claimed.

| Check | Result | Method |
| --- | --- | --- |
| TypeScript | PASS | `npm run check` (`tsc --noEmit`) |
| Rust | PASS, 9 tests | `cargo test --manifest-path src-tauri/Cargo.toml` |
| Browser | PASS, 4 tests | Playwright in headless installed Google Chrome, localhost:1431 only |
| Appearance | PASS | Light and dark, 1100×800; separate 390×844 pages; screenshots visually inspected; no horizontal overflow; visible keyboard focus |
| Native persistence | PASS | Ten keyboard judgments, native menu Quit, relaunch via `npm run tauri dev`, then UI and file verification |
| Toy fixture | PASS | 40 unique pair IDs; 36 distinct sources; four exact repeated comparisons with separate IDs |
| Whitespace | PASS | `git diff --check` |

Rust coverage: durable append and reopen, last-record-wins including null undo, truncated UTF-8 tail recovery without changing completed records, malformed complete-line refusal, skip/draft order on resume, exclusive writer lock, bounded filenames and symlink refusal, undo interrupted before state save, actual read-only-handle write failure without advancing, and summary counts.

The keyboard-only Playwright walkthrough exercised A/Left, B/Right, T/Down, W, U, N, S, D, Esc, Tab, and Enter. It checked note typing does not trigger judgments, held keys do not repeat judgments, undo restores notes, skipped pairs return at the end, pause hides the pair and blocks judgments, differences toggle off and on, the break reminder appears at 25, counts match the choices, and summary export downloads. It captured no page errors or non-local requests. Additional word-difference checks cover repeated words, literal markup, and a 1,100-word comparison.

The final native run used `verification/native-final/pairs.jsonl`, a preserved copy of the initially generated toy fixture. Its SHA-256 is `5f8d32b78dc4a97f8ed6d7abd259291b883d91359da309c7481e65d0fd432b9d`. The later fixture refinement made the first 36 examples distinct and was separately checked in the browser; the native input was preserved unchanged with its receipts. After ten judgments, the next pair was `toy-011` (the blue notebook source). After quitting and relaunching, the window showed **10 of 40** and that exact source. All ten JSON records, the entire remaining queue, and draft state matched the pre-quit snapshot.

Computer-use tooling required a temporary, ignored `.app` identity wrapper around the executable produced and launched by `npm run tauri dev`. The app reused the already-running localhost:1431 development server, so this invocation overrode `beforeDevCommand` with an empty string. This changed only the verification launch setup. An early helper-based quit/reopen was unsuitable as an acceptance check; the final run used a fresh toy copy and the native Quit menu, with the pending pair checked before and after. The verification app was closed at the end.

Local receipts are under ignored `verification/`: `rust-tests.log`, `browser-tests.log`, `typecheck.log`, `native-final-before.json`, `native-final-result.json`, `native-final-keys.json`, and `screenshots/`. No screenshots or judgment output are committed.

Not run: annotation of real research pairs, physical power-loss fault injection, or testing on other operating systems. File flush/sync calls, recovery tests, and a real quit/relaunch establish the tested persistence behavior; they do not establish survival of every possible hardware failure.


## Native icon and packaged release

October 15, 2026:

- PASS: source icon inspected at full size and 128×128. Transparent artwork converted into the native `.icns` family and 32/128/256-pixel raster assets with Tauri's icon command.
- PASS: `npm run tauri -- build --bundles app` completed the production frontend build, Rust release compilation, and macOS bundling. The output is an arm64 app, approximately 10.83 MiB.
- PASS: the project-root `LocalFlow Annotate.app` copy passes `codesign --verify --deep --strict`. Its `CFBundleIconFile` is `icon.icns`, and the bundled icon bytes exactly match the repository asset.
- PASS: the actual release bundle opened from its own embedded `tauri://localhost` assets while nothing was listening on localhost:1431. Computer-use verification confirmed its UI and one durable toy judgment; the resulting JSONL record was checked on disk. The app was then quit through its native menu.
- The packaged check used only `verification/bundle-session/pairs.jsonl` and its separate toy output/state. No real-data session was opened.

Build and signature logs plus the executable hash are in ignored `verification/bundle-build.log`, `verification/bundle-signature.log`, and `verification/bundle-result.json`. This is a local ad-hoc-signed app; Developer ID signing, notarization, Intel builds, and distribution were not performed.

## Missing-input startup repair

October 15, 2026:

- Confirmed that the default input was absent. The earlier packaged check used a synthetic input override and did not exercise normal launch with missing input.
- PASS: TypeScript check, all 11 Rust tests, and all 6 browser tests. New tests distinguish missing input from other read errors, confirm missing input creates neither output nor session state, and exercise retry, explicit toy practice, leaving practice, and suppression of private paths in errors.
- PASS: rebuilt the release bundle, replaced the project-root app, and verified its ad-hoc signature with `codesign --verify --deep --strict`.
- PASS: normal native launch without dataset overrides shows **Waiting for review pairs**, **Check again**, and **Try toy pairs**, without stale progress or pause controls. Native computer-use verification entered toy mode, recorded one choice in memory (**1 of 40**), and used **Leave toy session** to return to the waiting screen.
- PASS: metadata checks after native verification confirmed that neither default `pairs.jsonl` nor `annotations.jsonl` existed. No research output was created. The rebuilt app was left open on the waiting screen.

Local receipts: ignored `verification/startup-typecheck.log`, `startup-rust.log`, `startup-browser.log`, `startup-build.log`, `startup-native-result.json`, and `screenshots/waiting.png`. Real-data annotation remains NOT RUN because the producer's input file is absent.

## Window-fitting review, native Escape and the move into LocalFlow

- PASS: Playwright, 12 of 12, against `npm run dev` from `experiments/cleanup-model-v2/annotate/`: every shortcut, the marks, the guide, the ledger, the page never scrolling at 1100 by 800 and 390 by 700 with the decision bar inside the window, a keyup-only Escape, and the time estimate waiting for ten judgments.
- PASS: `npm run tauri -- build --bundles app` from the new location, including `tsc --noEmit`.
- PASS: the release bundle opened a scratch copy of the real 165-pair packet through LaunchServices (`open -n --env`): the pair fits the window, choices write durable lines, undo writes `choice: null`, a relaunch resumes at the same count, and `v2.research_agreement` accepts the file with the pre-registered rule.
- FOUND AND FIXED: in the native window the web view consumes Escape's keydown and delivers only its keyup, so Escape did nothing while every browser test passed. Escape is handled on keyup; the browser suite now includes a keyup-only Escape, and in the release bundle each single Escape toggled pause exactly once over four presses.
- Limit: a bundle executable started directly from a shell is not activated by macOS, so synthetic keystrokes go to the previously active app; launch through `open` when testing keys.
