# LocalFlow V2 — Start here

Compact orientation index for fresh sessions. Not a specification — the
three canonical Markdown documents are. Package entry point: `README.md`.

## Read order

1. `STATUS.json` — where the build is right now.
2. `LOCALFLOW_V2_MILESTONES.md` — your assigned milestone section only,
   plus its listed Spec/Evaluation sections.
3. `contracts/INDEX.md` and the contracts your milestone touches.
4. `handoffs/` for your milestone's prerequisites.
5. `registry.json` — 33 requirements / 22 suites, derived from the current
   canonical documents by `scripts/v2/build_registry.py` (never hand-edited).

## Where things live

| Path | What |
|---|---|
| `baseline/manifest.json` | **Frozen 2026-09-21 historical** deployed/source/config/data baseline (schema 1; never regenerated or overwritten) |
| `baseline/runs/<run-id>/manifest.json` | Versioned current-run observations (schema 2) from `scripts/v2/build_baseline_manifest.py` (`--repo-root`, `--app`); historical claims appear only as dated pointers |
| `VERIFICATION.html` | The one human runbook for deferred reference-Mac checks (M01–M14 sections; stable IDs `Mxx-Vnnn`; status saved in the browser) |
| `baseline/legacy-log-reconciliation.json` | Audited log aggregates reproduced by `scripts/v2/parse_legacy_log.py` |
| `benchmarks/<run-id>/` | Measured runs (probe output, environment) |
| `acceptance/<Mxx>/results.json` | Per-milestone structured acceptance results |
| `handoffs/<Mxx>.md` | Per-milestone completion reports |
| `decisions/` | ADRs for accepted deviations (none yet) |
| `tests/v2/`, `scripts/v2/` | V2 evaluation scaffolding (runnable with `.venv/bin/python`; pytest is not installed — files are standalone scripts) |
| `~/Library/Application Support/LocalFlow/v2-evidence/` | **Private** evidence root — snapshots, historical prefix, log copies. Never commit. |

## Rules that travel

- Preserve the installed app, live user data (`stats.db`, `dictionary.json`,
  `transforms.json` in Application Support) and the Parakeet v3 + Qwen3-4B
  baseline. The analytics/dictionary/transform producers exist as data +
  compiled remnants only (see `baseline/manifest.json`).
- Run `tests/v2/` plus the existing `tests/test_cleanup.py` (LLM tier) and
  `tests/test_stuck_overlay.py` before changes; record pre-existing
  failures separately.
- Never commit transcripts, audio, database files or the live log.
  `tests/v2/test_baseline_manifest.py` enforces this.
- Unknown facts are null with a reason. Never mark unavailable human checks
  as passed.
- Checks that need the real Mac go into `VERIFICATION.html` as
  `PENDING_LOCAL_VERIFICATION` entries (append to your milestone's section;
  never renumber). Pending entries do not block the next read-only audit
  unless an unverified condition invalidates its static premise.
