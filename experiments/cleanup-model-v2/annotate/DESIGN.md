# LocalFlow Annotate

LocalFlow is a local dictation app; its cleanup model rewrites a spoken transcript into clean text.

## Design plan

A quiet reading desk using the copied LocalFlow Live Hub tokens, built for paragraph-length pairs that differ by a little. The window is the page and never scrolls: a compact header with the progress ledger, the source band, two equal candidate panes, and a decision bar pinned at the bottom with A at the left and B at the right. The source band is capped at about a quarter of the height; the type steps down for long pairs until everything fits, and only then does text scroll inside its own area, with a fade at the bottom edge. Serif reading text, restrained sans-serif controls, sentence-case labels, no side emphasized by color or initial focus.

The one memorable element is the disagreement marks: lavender where only one side has words, a thin bar where only the other side has text, a return glyph for a line break only one side has, and punctuation or case marked by the character. Pointing at a mark lights its counterpart. Source changes stay available as a separate view.

The How to decide guide mirrors the pre-registered rule and opens by itself before the first judgment. The ledger counts judgments in sets of 25 and never shows which side was chosen; counts appear only at the end. The one motion answers a choice: the chosen button confirms and the next pair fades in, removed under reduced motion. A note opens in place; pause hides the text and stops the timer. Panes stack at narrow widths, where the stacked area scrolls inside and the bar stays pinned.

## Rust plan

- `load_session`: open only the configured pairs.jsonl and annotations.jsonl, validate typed fields and unique pair IDs, replay complete annotation lines with last-record-wins semantics, and return pairs plus pending order and progress. Never scan the annotation directory. Reject symlink files and filenames other than the two permitted basenames, including configuration overrides.
- `judge`: serialize one typed judgment, write newline, flush and sync_all before acknowledging. Undo writes choice null for the most recent still-active judgment. Hold an exclusive file lock for this app session. Recover only an unterminated tail before the next append; completed lines remain immutable. Reject malformed completed records.
- `skip` / `save_draft`: atomically save pending order and draft notes to app state outside the input directory. On resume reconcile pending order with the authoritative journal, including undo records. Journal writes always precede session updates.
- `progress`: derive completed count, choice counts and median seconds from the last non-null record for each pair. Export summary.json beside annotations without reading it or any neighboring file.
- File paths are configured through environment variables and never cross the Rust/UI boundary. Errors use fixed messages without paths or data. Browser mock mode uses generated toy pairs and memory only.

## Verification plan

Rust tests cover durable append/reopen, last-wins, undo, truncated tails, malformed complete lines, path restrictions, skip/draft resume and summary calculations. Playwright exercises every shortcut, focus, timing, summary, both appearances and narrow layout against toy data. Desktop verification uses a separate toy copy for ten judgments, quit, relaunch and resume. No real research data is opened.
