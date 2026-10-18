# LocalFlow research journey

An interactive publication of the cleanup-model research: from the first version of LocalFlow's cleanup model to the final test, told at four depths (Story, Mechanism, Research, Evidence) with the source behind every claim. It is a static site; nothing calls a model or an API.

## Run it

```sh
cd experiments/research-journey
npm install
npm run private-examples   # optional: real practice cases, local only (see below)
npm run dev                # http://127.0.0.1:5181
```

## Build the static site

```sh
npm run build     # type check, then a static build in dist/
npm run preview   # serves dist/ at http://127.0.0.1:5182
```

The build uses relative paths and hash routes, so `dist/` works from any folder or static host. Browsers block module scripts from `file://`, so open it through `npm run preview` or any static server.

## Update the data

- `npm run snapshot` rebuilds `src/data/generated/snapshot.json` and `meta.json` from the committed result files in `docs/v2/research/paper/results/` and records each source's SHA-256 and the commit. It copies aggregates only.
- `npm run private-examples` writes `src/data/private/examples.json` from the development artifacts on this machine: a few real practice cases with their recorded answers and verdicts. The case text was written by Claude and is not released, so this folder is git-ignored. A build made while it exists contains that text: do not publish such a `dist/`. Without it, every instrument shows an illustration and says so.
- The final run's timeline (`src/data/stage2.ts`) comes from run logs that live outside the repository; update its statuses and `RUN_SNAPSHOT_AT` when the run moves on.

## How it is built

- `src/content/chapters/`: one file per chapter, each a list of ideas written at four depths in a small markup (`[[term]]`, `{ev:source}`, `*em*`, `` `code` ``). A new chapter is one file and one line in `index.ts`.
- `src/data/`: the research as data. Sources (`evidence.ts`), models and lineage (`models.ts`), claims (`claims.ts`), decision records (`timeline.ts`), the final run (`stage2.ts`), the glossary, and the generated snapshot.
- `src/components/`: the shell (masthead, timeline spine, chapter view, evidence drawer) and conceptual zoom (`zoom/`: the page-wide depth dial and each idea's own lens).
- `src/instruments/`: the interactive figures, each loaded on first use.
- `src/app/`: a small hash router on `useSyncExternalStore` (deep links and history without effects), depth state and evidence navigation.
- `tests/`: integrity checks (every citation and glossary term resolves, lineage has no cycles, no final-set outcome is stated before the analysis runs, the public snapshot holds no case text) and unit tests for the markup, diff and formatting.

`npm test` runs the tests.
