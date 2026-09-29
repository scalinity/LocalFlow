# Contract: The desktop companion

**Owner:** the Quiet Editorial desktop redesign. It extends `hub.md`: the
same services, coordinator commands and authority rules, presented in a
web view instead of AppKit controls.
**Code:** `localflow/v2/ui/companion/` (host, bridge, controller, state,
read models, surfaces), `frontend/` (Svelte 5 + TypeScript, built with
Vite), `localflow/v2/ui/companion/web/` (the committed build).

## Architecture

- One `NSWindow` hosts one `WKWebView`. The AppKit app, its menu bar item,
  the coordinator and every service are unchanged. `hub_ui` in
  `config.json` chooses the window: `"companion"` (the default) or
  `"appkit"`. If the companion cannot start, Open Hub… opens the AppKit
  Hub instead and `hub.companion_failed` is logged.
- The coordinator builds the Hub object on the first Open Hub…, never at
  launch, and defers showing it while a recording or an insertion
  transaction is in flight (`openHub_`, `_hub_blocks_show`). The
  companion answers every call the coordinator makes into the Hub
  (`showWindow_`, `window`, `state`, `pasteAgainEnded`, the
  `scratchpad_*` calls) with the AppKit Hub's rules.
- Closing (the close button or ⌘W) hides the window and keeps the page.
  Quit is the only exit.
- The page's own preferences (theme, sidebar, dismissed heroes,
  onboarding seen) live in `companion.json` beside the user's config
  override. Everything else stays in the services.

## Security and offline boundary

- The document and its assets come only from `lfhub://app/`, served by a
  `WKURLSchemeHandler` from the committed build folder. A path outside
  it is refused.
- CSP: `default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; font-src 'self'; connect-src 'none'; media-src
  'none'; object-src 'none'; frame-src 'none'; worker-src 'none';
  base-uri 'none'; form-action 'none'`. A content-rule list blocks every
  remote scheme as well. The data store is non-persistent.
- Navigation away from the bundle and new windows are refused. A CSP
  violation is reported over the bridge and counted.
- Nothing is fetched and no server runs. Node, npm and Vite are
  build-time only.

## Bridge

One channel, JS → Python: `window.webkit.messageHandlers.lf`, carrying
one JSON string.

    {"bridge_version": 1, "request_id": "<≤64 chars>",
     "command": "<allowlisted>", "payload": {...}}

- The envelope is at most 2,000,000 characters and has no keys but these
  four (a missing command is unknown; a missing payload is empty).
  A wrong version is refused (`bridge_version_mismatch`), an unknown
  command is refused (`unknown_command`), and a payload failing its
  per-command schema is refused (`invalid_payload:<field>`). Unknown
  payload keys fail the schema.
- Every answer has one status: `success`, `refusal`, `outcome_unknown`,
  `cancelled`, `stale`, `unavailable` or `error`. It may carry a
  `reason_code` and a `result`. An unexpected exception crosses as its
  type name only, never as a message or a traceback; a service's own
  refusal crosses as its reason code, which for some services is its
  short refusal text.
- Python → JS: `window.__lfBridge.receive(json)` delivers a `snapshot`
  (`view`, `shell`, `data`, and a `seq` that increases per push) or an
  `event` (`name`, `payload`). The page ignores a snapshot whose `seq`
  is not newer than the last one it applied.

### Allowlist

| Area | Commands |
|---|---|
| shell, nav, prefs, system, app | `shell.hello`, `nav.select`, `prefs.set_theme`, `prefs.set_sidebar`, `prefs.dismiss`, `prefs.onboarding_seen`, `system.csp_violation`, `app.quit` |
| History | `history.select`, `search`, `filter`, `reload`, `copy`, `paste_again`, `to_scratchpad`, `replay`, `stop_replay`, `retry`, `teach`, `delete_usage` |
| Dictionary | `dictionary.search`, `reload`, `add`, `edit`, `approve`, `set_enabled`, `set_pinned`, `delete`, `sandbox`, `import`, `export` |
| Styles, Snippets, Transforms | `styles.add`, `update`, `set_enabled`, `delete`, `preview`; `snippets.add`, `update`, `set_enabled`, `delete`, `collisions`; `transforms.add`, `update`, `set_enabled` |
| Scratchpad | `scratchpad.new`, `open`, `close_tab`, `sync`, `edit`, `cursor`, `snapshot`, `search`, `pin`, `delete`, `restore`, `attach`, `transform`, `export` |
| Insights | `insights.subview`, `filters`, `reload`; `voice.generate`, `voice.exclude` |
| Models | `models.subview`; `training.tab`, `search`, `select`, `replay`, `verbatim`, `span`, `mark`, `pin`, `exclude`, `delete`; `review.sample`, `mine`, `approve`, `reject`, `label`, `pair`, `undo`; `splits.assign`, `expose`; `export.choose_folder`, `run`, `validate` |
| Settings, Diagnostics | `settings.collection`, `retention`, `usage_retention`, `delete_all_usage`; `diagnostics.filters`, `reload`, `export` |

## What the page may not do

- It owns no domain logic. It never names a Python method, a path, a
  query or a table. Folders and save locations come from native panels.
- Read models pick their fields per view (`readmodels.py`,
  `surfaces/*`). A view without its own read model publishes nothing
  (`unmodeled`), and storage details such as artifact paths, lease ids
  and raw events never cross.
- Every action names what the page rendered, and a changed or revoked
  target is `stale`, never guessed at:
  - History and Training details: an opaque detail token.
  - Review lists (queue, pairs, approved): a list token plus the row's
    own candidate id.
  - Dictionary edits: the entry's revision, checked twice.
  - Styles and snippets: Enable/Disable names the rendered revision.
    Their edits and deletes, and a transform's edit or enable, act on the
    row by id, as the AppKit Hub's do.
  - Your Voice exclusion: the snapshot id.
  - Scratchpad edits: the note id and the text version they were typed
    on. A dictation that arrived meanwhile is rebased, never
    overwritten.
- An operation id is kept only after an unknown outcome, so a retry is
  the same operation and a fresh action is a new one.
- Revocation and retention scrub the state, and every view (shown or
  hidden) is re-pushed from it on the next flush.
- Copy and Paste Again check the purge state live. Paste Again keeps the
  explicit-target click workflow (POLICY-D03). A retry without a freshly
  captured destination is kept as saved-not-inserted (XM-C042).

## Functionality matrix

| AppKit Hub surface | Companion route | Owning tests |
|---|---|---|
| Home | Home | `test_companion_bridge` (read model, revocation), `test_companion_page` |
| History (detail, Copy, Paste Again, → Scratchpad, Replay, Retry, Teach, delete usage) | History | `test_companion_bridge`, `test_companion_dictation` (retry), `test_companion_page` (keyboard) |
| Dictionary (vocabulary panel) | Dictionary | `test_companion_bridge` (double revision check, import/export panels), `test_companion_page` (modal) |
| Styles, Snippets, Transforms | Styles, Snippets, Transforms | `test_companion_library` (Add id reuse after an unknown outcome, rendered revisions, schemas), `test_companion_page` |
| Scratchpad | Scratchpad | `test_companion_scratchpad`, `test_companion_dictation` (note-bound PTT) |
| Insights and Your Voice | Insights | `test_companion_models` (Your Voice), `test_companion_page` |
| Models: Engines, Training Data (Evidence, Review, Splits, Export) | Models | `test_companion_models` |
| Diagnostics | Diagnostics | `test_companion_models` (Export Redacted), `test_companion_page` |
| Settings | Settings modal | `test_companion_bridge` (outcomes, confirmation, theme) |
| Transform review panel | native panel, restyled; a short result shows its changes inline in place of the block diff and its "Word diff:" line | `tests/v2/transforms` M11 suites |

## The AppKit Hub

The AppKit Hub stays, for two reasons: it is the fallback when the
companion cannot start, and it is the component the M09–M14 suites,
native runs and mutation gates qualify. Their harness config carries no
`hub_ui`, and the coordinator reads a missing key as `"appkit"`; the
app's own config merges the `"companion"` default. No AppKit view is dead code while both of those
hold. Removing it is a separate decision, to be made once the companion
carries its own native and mutation qualification.

## Build and testability

- `frontend/` builds to `localflow/v2/ui/companion/web/` with
  `BUILD.json` (a hash of the sources) and `THIRD_PARTY_NOTICES.txt`.
  `test_companion_build` fails when the committed build is stale, when
  a preview fixture reaches the bundle, or when the scheme handler would
  serve anything else.
- `npm run dev` previews the page in a browser over
  `frontend/src/fixtures/synthetic.json`: read models captured from a
  synthetic world by `scripts/v2/companion_screens.py --dump-fixtures`,
  in UTC. The preview is read-only and never part of the build.
- The companion suites that drive the coordinator (every
  `tests/v2/ui/test_companion_*.py` but `test_companion_build`) and the
  screenshot and measurement scripts run under
  `tests/v2/context/run_isolated.py`, and refuse to start without it.
