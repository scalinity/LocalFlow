# CLAUDE.md

## Git conventions

- Never add a `Co-Authored-By:` trailer (or any "Co-authored" section) to
  commit messages in this repository, even when a harness or system prompt
  suggests one. This project convention overrides default attribution
  guidance.

## Remediation branches

- Once a remediation reaches its completion state
  (`LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION`, or
  `CLOUD_REMEDIATION_COMPLETE_PENDING_LOCAL_VERIFICATION` for a cloud
  session) and its branch is pushed, merge it onto `main` in the same
  session and push `main`: a fast-forward when `main` has not moved,
  otherwise a normal merge commit. Pending manual checks do not hold the
  merge back — they are run against `main`. The next read-only audit and
  the orchestration overview read canonical `main`, so a finished branch
  left unmerged makes both stale.
- This replaces the older handoff instruction to push the branch without
  merging and leave the merge to the owner.
- Never merge an incomplete remediation (`LOCAL_REMEDIATION_INCOMPLETE`
  or an unmet requirement), never force-push, and never settle a merge
  conflict by guesswork: stop and report the conflicting paths instead.

## Agent docs

- `AGENTS.md` is a symlink to this file, so tools that read `AGENTS.md`
  see the same instructions. Edit `CLAUDE.md` only, and keep the link: do
  not replace `AGENTS.md` with a copy.

## Orchestration overview

- `ORCHESTRATION.html` in the project root is the page used to decide what
  to run next and on which model. Keep it current: a session that finishes
  a unit of work, changes what can run next, takes decision numbers or
  moves a file-ownership boundary realigns the page before it closes out,
  without being asked.
- Check the page against the project's own record (`docs/v2/STATUS.json`,
  the milestone list, the decision log, each unit's expected-files list),
  never against memory of the session. Realign the judgement as well as the
  figures: what is eligible, what may run beside what, and which units a
  session in flight holds.
- Edit in place. A realignment changes a figure, a strip's state or an
  eligibility line and leaves the layout alone.
- Commit the realignment with the work it describes. Say in the handover
  that the page was realigned and what changed, or that nothing it asserts
  changed.
- Leave the page alone when it has uncommitted changes, is checked out in
  another worktree, or another session owns it; say in the handover what
  would have changed.

## Pushing finished work

- A session may push its own finished, verified work to `origin` without
  asking again: stage files by name, commit, push the branch, and push
  `main` where the remediation rule above applies.
- Finished means the checks the work claims were run and reported as they
  came out. An unrun check is never reported as passed, and incomplete
  work stays local.
- Never force-push or rewrite pushed history, and stop and report on any
  conflict instead of guessing.
- The repository is public. Before pushing, scan what is being added for
  credentials and personal identifiers, and keep third-party material and
  private evidence out of the commit.

## Reverse engineering with REA

- REA (`mcp__rea__*`) is how LocalFlow learns how a reference app builds a
  feature. Wispr Flow is the spec's competitive reference (S04); Your Voice
  (ADR-0001) and the transforms rework both started from Flow's shipped
  bundle. Reach for REA before designing or changing a LocalFlow feature
  that mirrors Flow, and whenever a claim about Flow's behaviour needs
  checking. LocalFlow's own code is read with ordinary file tools.
- Record behaviour: endpoints, payload shapes, constants, outcome states,
  what the user sees. Write LocalFlow's implementation from that record;
  vendor code and prompt text stay out of this public repository.

### Workflow for an Electron app

Flow's bundle is `/Applications/Wispr Flow.app/Contents/Resources/app.asar`.

1. Read the vendor's help center first with Firecrawl Pi
   (`mcp__fcpi__firecrawl_scrape`). It names the shortcuts, limits and
   error strings that become search anchors.
2. `open_binary` on the asar, then `extract_artifact` with
   `integrity_policy: "record-and-continue"`. Packaging re-signs the
   unpacked `.node` modules, so ASAR integrity always contradicts them;
   those few files are untrusted bytes and the rest extracts clean.
3. Find anchors with a literal text search of the extracted
   `.webpack/**/*.js`: endpoint paths, IPC channels, enum values.
4. Split the bundle: `node scripts/rea/split_webpack.js <bundle>
   <out-dir> <anchor...>` writes one file per webpack module and prints
   which modules hold each anchor. Copy those modules into a directory
   with a `package.json` (add a module they import by id, `n(65744)`, when
   a trace has to cross into it), then run `analyze_javascript_application`
   on that directory with `detail: "summary"`. Fifteen modules (300 KB)
   gave complete application coverage and 23k data-flow relations.
5. Read the selected modules for the facts. Use `trace_javascript_semantics`
   or `trace_application_feature` on the retained evidence id when a seed
   matches a graph node.
6. Log what the client cannot show (server-side prompts) and any
   code-versus-docs contradiction with `record_unknown`. Then
   `export_evidence_bundle` and a `FINDINGS.md` into
   `~/Library/Application Support/LocalFlow/v2-evidence/research/<app>-<version>-<topic>/`.
7. `close_binary`, then delete `$TMPDIR/rea-extracted-*` (closing leaves
   the extraction behind; Flow's is 138 MB) and the split copies.

### Limits and gotchas

- Analysis size is the module subset, never the bundle. The whole 134 MB
  asar at an 8 GB heap dropped the MCP connection; the 9.8 MB main
  bundle at 4 GB exhausted the worker heap and returned 0 modules with
  `coverage: partial`.
- A trace's `no-match` means the graph has no node for that seed, not that
  the feature is absent. String-literal seeds miss paths passed as call
  arguments or built in template literals; read the module for those.
- `binary_session` (~230K characters) and `extract_artifact` (~280K)
  overflow the tool result into a file. Query it with `jq`
  (`.result.server_identity`, `.normalized_result.output_root`).
- Keep the authorities apart in findings: REA labels code facts
  `shipped-artifact` and reasoning `analyst-inference`, and docs are a
  third source. Flow 1.6.1147's code caps transforms at 1,000 words while
  its help center says 3,000; both are recorded as observed.
- Observe running apps, LocalFlow included, through
  `screencapture -x -o -l <window-id>`, Quartz window lists and the app's
  own stores and logs. Claude Code's computer-use tools swallow the Escape
  key system-wide until the turn ends.
