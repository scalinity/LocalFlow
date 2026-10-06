# Session log — 2026-10-05

Implementation notes for one working session: the installed-app replacement,
the menu fixes that followed, and the consolidation of loose project files.
Paths are repo-relative unless marked `~`.

## 1. Installed app replaced

- `/Applications/LocalFlow.app` was replaced with the `owner-qualified` review
  build (source revision `b096d563`, clean). Its embedded `localflow/` matched
  `main` at the time of install.
- The previous installed build was copied first to
  `build/companion-review/final/LocalFlow-previous-installed-20260811.app`
  (rollback: quit, delete the installed app, `ditto` the backup back).
- Paste had stopped working because the Accessibility grant no longer matched
  the installed executable. Bundles are ad-hoc signed, so macOS ties the grant
  to the executable's CDHash (`466e0c1a…` installed, `09bdb1cd…` review build,
  same bundle id). After a whole-bundle install the entry must be removed and
  re-added in System Settings → Privacy & Security → Accessibility, then the
  app restarted. Copying only Python files into a bundle keeps the CDHash and
  needs no re-grant.
- Later fixes in this session were deployed by copying only the changed
  `localflow/` files into the bundle; the CDHash stayed `09bdb1cd…`.

## 2. Training menu

- Cause of the missing check mark: the Training submenu was never rendered from
  the saved consent state when the menu was built (only after a toggle or a Hub
  change). A click on "Collect Training Evidence" therefore flipped a saved
  *on* to *off* with no visible state before or after.
- Cause of the always-live "Pause Collection": the submenu auto-enabled its
  items, so AppKit re-validated them on open and discarded `setEnabled_`.
- Changes in `localflow/app.py`: the submenu moved into
  `_build_training_menu()`; it disables auto-enabling and renders the saved
  state when built (`_refresh_training_menu()`, guarded for a consent timeout
  the same way as the toggle handlers).

## 3. Collection defaults to on

- `_seed_default_collection()` runs once from `applicationDidFinishLaunching_`,
  before the menu is built. A store with no consent revision records
  `enabled` (note `default on`). A saved choice, including off or paused, is
  never overridden.
- The real profile's saved *off* was replaced with *on* through
  `ConsentManager.set` with the app closed (note
  `owner request: collection on`), after a copy of `v2.db` was taken.
- `docs/v2/LOCALFLOW_V2_SPEC.md` S29.2 and the `localflow/v2/training.py`
  docstring state the new default.
- `docs/v2/VERIFICATION.html` still tells a manual tester that a fresh sandbox
  shows "Collect Training Evidence" without a check mark. Under the new default
  it is checked. That script records past manual runs and was not rewritten.

## 4. Transforms listings

- The two V1 rows (`origin="legacy"`, "Polish" and "Prompt Engineer" with their
  own prompts) are no longer listed in the menu-bar Transforms submenu
  (`localflow/app.py`) or in the Hub and companion Transforms list
  (`HubState._load_transforms` in `localflow/v2/ui/state.py`). The rows stay in
  the store: an old definition is never erased (S16/M11-AC01) and
  `TransformStore.definitions()` is unchanged.
- Menu titles show the transform name only; the repeated `(mode)` suffix was
  removed.

## 5. Tests

- Added `tests/v2/lifecycle/test_training_menu.py` (saved on/off/paused states,
  Pause greyed while off, click flow, default seeding, saved choice never
  overridden) and `tests/v2/lifecycle/test_transform_listings.py` (menu and
  Hub/companion lists hide legacy rows; menu titles are names only). Each was
  run red before its fix.
- Passing after the changes: both new files, the lifecycle, training, storage
  and consent-adjacent suites (22), the transforms and UI suites (35 through
  the isolated runner), the cross-milestone suite (86 of 86) and the baseline
  manifest privacy scan.
- Not passing, unrelated to these changes: `transforms/test_prompt_engineer_cases.py`
  (model-backed, fails by design) and `transforms/test_owner_hotkeys_native.py`
  (native harness that requires `--out`). `ui/test_native_m10_panes.py` failed
  once with 2 of 3 cases and passed 3 of 3 on two re-runs and on the committed
  code (native window timing).
- The real `applicationDidFinishLaunching_` path is not covered by any test;
  the default seeding was checked by a real launch (no new errors in the event
  log). The Training and Transforms menus were inspected on screen afterwards
  and displayed correctly.

## 6. Files consolidated into the repository

- Two merged, clean worktree folders (`m15-cleanup-model-benchmark-setup-20261001`,
  `pre-m15-m15a-integration-20261001`) were removed after confirming each was
  contained in `main` and on `origin`; ten stale worktree records were pruned.
  The two local branches remain.
- Review builds moved from the Desktop into `build/companion-review/` (ignored
  by git). Eight superseded `.app` bundles and the app copies under `package/`
  and `qualified/` were deleted; `LocalFlow-owner-qualified.app` and the
  previous-installed backup were kept. The review launcher and the two
  companion docs now point at the new location.
- Milestone audits M02–M10 and M12 were filed under
  `docs/v2/acceptance/<milestone>/remediation/`, the cross-milestone audit zip
  under `docs/v2/acceptance/cross-milestone/audits/` (hash matches
  `artifact_map.json`), and the branch SHA record under `docs/v2/handoffs/`.
  Eleven files identical to tracked ones were deleted from Downloads.
- UI reference screenshots (third-party product captures) were filed under
  `docs/v2/companion/references/` and are git-ignored, not committed.

## 7. Outside this repository

- `LocalFlowResearch` stays a separate repository holding only its current
  (v1.2) material. A full clone, `LocalFlowResearch-legacy`, holds the legacy
  v1 and v1.1 specifications, registry v1.1 and the kickoff package.

## Open items

- `docs/v2/VERIFICATION.html` manual steps for the collection default (above).
