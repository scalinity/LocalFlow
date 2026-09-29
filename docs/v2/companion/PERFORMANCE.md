# Desktop companion — timings and memory

Measured with `scripts/v2/companion_perf.py --rows 2000` under
`tests/v2/context/run_isolated.py`: the lifecycle Harness (temporary
store, fake microphone, no speech or cleanup model loaded), 2,000
synthetic History rows on top of the screenshot seed, and the real
CompanionController and WKWebView in an off-screen window at 1150 × 715.
Timings run from the action until the page shows a usable result, taken
inside the page (`performance.now`, checked every frame). Two consecutive runs agreed within 2 ms and 3 MB;
the table gives the second.

## Timings

| Step | ms |
|---|---|
| Controller and WKWebView created (first Open Hub only) | 92 |
| Show → bundled page loaded | 104 |
| Show → first shell render with Home data | 124 |
| Route switch (Home, Styles, Diagnostics, Snippets, Transforms, Models, Dictionary) | 4 – 27 |
| History, first rows usable (the first page of 200 rows) | 20 |
| Insights, Usage cards shown | 17 |
| Scratchpad, a note open in the editor | 17 |
| Theme switch, chosen in the page (bridge round trip + repaint) | 20 |

Dictation never waits on the companion. The coordinator builds it on the
first Open Hub, not at launch, and opening waits while an insertion
transaction is in flight (`tests/v2/ui/test_companion_dictation.py`);
the same guard covers a recording in progress.

## Memory (resident)

| State | This process | WebKit (3 processes) |
|---|---|---|
| Companion never opened | 112 MB | — |
| Open on Home | 153 MB | 95 MB |
| After History with 200 rows, scrolled to the end | 156 MB | 154 MB |
| Closed (hidden), 5 s later | 156 MB | 153 MB |

The first row is the Harness process with no model loaded, not the full
app. In the real app the speech and cleanup models dominate, so the
companion's cost is the difference: about 41 MB in the app process and
95–155 MB across WebKit's content, networking and GPU processes.

Closing hides the window and keeps the web view, so reopening is
immediate and keeps the route. Nothing runs while it is hidden: pushes
are event-driven, the one timer (a two-second recheck while a model is
still loading) runs only while the window is shown, and WebKit suspends
a hidden page. The memory stays in use. Releasing the web view on close
would return about 150 MB, and the next open would cost the 124 ms first
render again.

## Wake-ups

There is no polling loop. The page has no `setInterval`, and its single
`requestAnimationFrame` is a one-shot debounce of caret reports in the
Scratchpad editor.
