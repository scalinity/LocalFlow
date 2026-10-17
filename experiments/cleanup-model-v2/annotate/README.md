# LocalFlow Annotate

A small, local desktop workspace for judging blinded pairs of cleaned dictation. Tauri 2, Vite, and plain TypeScript. The interface uses a copied set of LocalFlow Hub tokens, follows the system appearance, and loads no remote assets.

## Built macOS app

The ready-to-open application is `LocalFlow Annotate.app` in this folder (`experiments/cleanup-model-v2/annotate/` in the LocalFlow repository). It is an Apple Silicon release bundle with a native icon and local ad-hoc signature. It contains the interface and does not need Node.js, Rust, or a development server to run. Opening it normally uses the default annotation paths below. It is not notarized for distribution.

If the input file has not been prepared, the app shows **Waiting for review pairs**. Choose **Check again** after the producer creates it, or **Try toy pairs** to practice with the bundled examples. Toy choices stay in memory and never enter the research annotations. **Leave toy session** returns to the configured input; leaving or reloading discards toy choices. Other file errors remain errors and do not silently switch to toy data.

To launch that bundle with a different dataset, set the same environment variables and run its executable directly:

```sh
cd experiments/cleanup-model-v2/annotate
LOCALFLOW_ANNOTATE_PAIRS="/absolute/folder/pairs.jsonl" \
LOCALFLOW_ANNOTATE_ANNOTATIONS="/absolute/folder/annotations.jsonl" \
"./LocalFlow Annotate.app/Contents/MacOS/localflow-annotate"
```

To rebuild from source:

```sh
npm install
npm run tauri -- build --bundles app
```

The build writes `src-tauri/target/release/bundle/macos/LocalFlow Annotate.app`. The project-root copy is the verified build delivered with this change; later rebuilds appear at the build output path. Both bundle locations are ignored by Git. The icon artwork and [design brief](assets/icon-design.md) are retained under `assets/`; the `.icns` and raster sizes are under `src-tauri/icons/`.

## Development launch

Requires Node.js/npm, Rust, and the macOS command-line developer tools.

```sh
cd experiments/cleanup-model-v2/annotate
npm install
npm run tauri dev
```

This starts Vite on **localhost:1431** and opens the titleless desktop window. Drag its header to move it. Use the app menu to quit. The default input must exist before the session can open; the output is created if absent. Stop a separately running Vite server on this port before using the normal desktop launch command.

For the browser-only toy session:

```sh
npm run dev
```

Open [the toy session](http://localhost:1431/?mock=1). It contains 44 generated pairs: four paragraph-length pairs first (a dash list against prose, a one-comma difference, a one-word change, and a long passage with a self-correction), then short pairs, including four repeats with distinct pair IDs. All toy judgments are in memory; refreshing starts over. Export downloads a toy `summary.json`.

## Point the desktop app at files

Defaults:

- Pairs: `experiments/cleanup-model-v2/artifacts/research/annotation/pairs.jsonl`
- Judgments: `experiments/cleanup-model-v2/artifacts/research/annotation/annotations.jsonl`

Both sit in the study's git-ignored artifacts folder. The build resolves them from the app's own location in the repository, so a bundle built in one checkout reads that checkout's artifacts.

Override them before launch. Keep the basenames `pairs.jsonl` and `annotations.jsonl`; both parent directories must already exist. Configuration is deliberately outside the window so private paths never appear during annotation.

```sh
LOCALFLOW_ANNOTATE_PAIRS="/absolute/folder/pairs.jsonl" \
LOCALFLOW_ANNOTATE_ANNOTATIONS="/absolute/folder/annotations.jsonl" \
npm run tauri dev
```

Leave these variables unset to use the real defaults. There is no directory picker or directory scan. The app reads only these two data files, and never opens a key file. Candidate text is rendered as text, never HTML. Pair and case identifiers are not displayed. Input schemas reject extra fields, including candidate metadata. This assumes the producer supplies genuinely blinded text; names already embedded in the dictated text cannot be inferred or removed safely.

Resume order and unfinished notes are stored in the app-data directory (`~/Library/Application Support/ai.localflow.annotate/session.json` on macOS), separate from the annotation directory. This file is private session data and also contains an input identity snapshot. `LOCALFLOW_ANNOTATE_STATE_DIR` can override its directory for isolated toy sessions; it must be outside the annotation folder. Use a separate state directory when alternating between datasets to retain each dataset’s skipped order. Judgments always reload from the configured annotation file.

## Keys

| Key | Action |
| --- | --- |
| A or Left | A is better |
| B or Right | B is better |
| T or Down | Tie; both are fine |
| W | Both are wrong |
| U | Undo the most recent active judgment |
| N | Open the optional note |
| S | Move this pair to the end of the pending queue |
| M | Toggle the marks where A and B differ; initially on |
| D | Toggle word differences against the source instead of the marks; initially off |
| ? | Show or hide the How to decide guide |
| Esc | Pause or continue; in a note, finish editing first; with the guide open, hide it first |
| Tab / Shift-Tab | Move between controls |
| Enter / Space | Activate the focused button |

Shortcuts do not judge while typing a note, holding a key, or using command/control/option combinations. Notes stay attached to their pair, including after a skip or undo. Pausing hides the pair and stops its timer. Time per judgment counts the current review visit, excluding explicit pauses; an unfinished visit starts a fresh timer after relaunch. Skipped visits are not added to the final judgment time.

A choice advances as soon as Rust confirms the durable write. A storage failure stops review rather than accepting more choices. Retry reloads the journal, including a judgment that reached disk before a later state-save failure. Only one app instance can write a given annotation file at a time; do not edit or replace that file externally while the app is open.

The whole review fits the window: the page never scrolls. The source band is capped at about a quarter of the height, the type steps down for long pairs until the source and both panes fit, and only past the smallest step does text scroll inside its own area, with a fade at the bottom edge while more remains. When both panes overflow they scroll together proportionally. The decision bar stays pinned at the bottom, with A at the left and B at the right like the panes; at narrow widths the panes stack and scroll inside one area.

Marks are on by default. Words that only one side has are marked in lavender in that pane; a thin bar shows where only the other side has text; a line break that only one side has shows a return glyph drawn by CSS, so the text itself is unchanged. A difference of punctuation or case within one word marks only those characters. Pointing at a mark lights up its counterpart in the other pane.

The How to decide guide opens by itself before the first judgment and follows the order of the pre-registered rule: damage first, then cleanup, punctuation and self-corrections; still equal is a tie.

Progress counts current non-null judgments. The ledger under the header has one tick per pair in sets of 25; ticks count judgments and never show which side was chosen, and running counts appear only on the completion screen. The estimate uses the median seconds per item. A short break suggestion appears each time a set of 25 is finished. Skipped items return after the remaining queue; skip does not emit a judgment. The completion screen shows counts and median time, and notes that some pairs appeared twice. **Export summary** writes `summary.json` next to the desktop annotation file.

## Fixed data contract

Input: one object per line. Pair IDs must be unique, including repeated comparison items; repeated case IDs are allowed. Text fields and identifiers are strings.

```json
{"pair_id":"toy-001","case_id":"case-1","source":"um send the notes please","a":{"text":"Send the notes, please."},"b":{"text":"Please send the notes."},"vocabulary":[["quick note","QuickNote"]]}
```

Output: one newline-terminated record per judgment.

```json
{"pair_id":"toy-001","choice":"a","note":"Preserves the meaning.","seconds":7.4,"annotated_at":"2026-10-15T20:00:00+00:00"}
```

`choice` is `a`, `b`, `tie`, `both_wrong`, or `null`. Undo appends a null record and returns the pair to the front. The last complete record per `pair_id` wins. `annotated_at` is an RFC 3339 timestamp. Notes are limited to 2,000 characters.

Every judgment writes a complete JSON line, flushes, and calls `sync_all` before acknowledgment. Completed lines are never rewritten. A trailing fragment without a newline is ignored during reload and removed before the next append so it cannot contaminate a new judgment. A malformed **completed** line stops loading instead of silently losing history. State and summary exports use a synced temporary file plus rename. These checks do not simulate a physical power failure.

Differences and marks use one word-level longest-common-subsequence alignment in which line breaks are tokens of their own. Linear-space comparison rows keep memory bounded for long dictated passages.

## Toy data and checks

The generator refuses to overwrite an existing output file:

```sh
npm run mock -- /absolute/new-folder/pairs.jsonl
```

With no argument it writes `verification/mock/pairs.jsonl`. It also refreshes `src/mock-pairs.json`, the bundled browser fixture. All examples are synthetic.

For a durable desktop toy session, point the two environment variables at that toy folder and set `LOCALFLOW_ANNOTATE_STATE_DIR` to a different directory.

```sh
npm run check
cargo test --manifest-path src-tauri/Cargo.toml
# In another terminal, keep npm run dev running:
npm run test:browser
```

The Playwright suite uses installed Google Chrome in headless mode. It exercises every shortcut, held-key suppression, notes, skipped return, undo, pause, the guide, the marks and their accuracy, the ledger, the break reminder, summary export, light/dark appearances, visible focus, and that the page never scrolls with every paragraph-length pair at 1100 by 800 and 390 by 700 while the decision bar stays inside the window. Screenshots, logs, toy output and desktop verification bundles stay under ignored `verification/` in this project. See [VERIFICATION.md](VERIFICATION.md) for the executed checks and their limits.

No analytics, telemetry, network client, shell plugin, or general filesystem plugin is included. The production CSP permits local assets and Tauri IPC only. Development adds only localhost:1431 for Vite and its update socket. The app lives in the LocalFlow repository; the packet, its key and the judgments stay in the ignored artifacts folder and are never committed.
