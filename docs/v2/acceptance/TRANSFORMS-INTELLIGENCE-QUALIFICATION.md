# Transforms intelligence qualification

Date: 2026-10-23 (US Eastern). Verdict: **IMPLEMENTED_WITH_BLOCKED_VERIFICATION**. Product implementation and the scoped primary workflow checks are complete. The separate cleanup request remains blocked: NativePeers refuses eight retained worktrees because resumed ownership or owned-process/output closure is unproved. Those refusals are not passes and no forced removal was performed.

Qualification build 25 is installed in `/Applications/LocalFlow.app`. The completion audit added the visible, cancellable semantic-search setup path, inherited-context revocation checks for saved prompt refinement/copy/apply, and local Git identity in frozen project context. Existing limitations and earlier blocked attempts remain recorded below. This verdict does not claim universal application compatibility or empirically perfect model output.

## Revisions and deployment

- Repository: `scalinity/LocalFlow`; integrated branch `main`.
- Implementation commit: `16c50dc846b94c8a6d21e2f7afb3623fdc72b939`, pushed to origin/main.
- Completion-audit implementation: `8513e2397c02d15fd2e476954b0c9f81a958890b`, merged/pushed to main.
  Installed production/frontend files match this committed source; the build
  retains its honest pre-commit identity. The finished follow-up branch was removed locally and remotely after ancestry and open-PR checks.
- Qualification build-time HEAD: `4a6d7624cdd24e28d38efa18d09f44f82c4121a7`
  plus the implementation snapshot. The containing source commit records that
  snapshot; BUILD.json retains the honest pre-commit dirty build identity.
  Runtime and frontend content hashes above identify the deployed bytes.
- Installed bundle: `/Applications/LocalFlow.app`, qualification build 25.
- Production SHA-256: `8e10636d55a130da59324c09f43a370ab4993f1763d137539ec373d6225a81a9`.
- Frontend source SHA-256: `1ad0bb2776f422362777dd015976872b71e0cc0c142286acfb711c417f4508b5`.
- Frontend build SHA-256: `571abba5e96a96af5dcada3add91b7d62cbcf557d2bbfe07e2689b328871a871`.
- Native executable SHA-256: `ca60bbbadb12e32838956c83b992753b35fa2f86e57773f9bb67b593ae68f6d9`.
- Store schema 16. Installed bundle passes all 16 packaging/provenance checks. The build-time dirty identity is retained; content hashes identify the deployed source.

The specification and kickoff files were moved from Downloads into descriptively
named files under ignored `docs/v2/private/transforms-intelligence/`. Original
Downloads paths no longer exist. Private fixtures, captures, transcripts, outputs,
credentials and recovery data remain outside public source.

## Established causes and corrections

1. The original launcher ran the coordinator as Python. Terminal attribution could
   make microphone or Accessibility requests appear under the launching terminal.
   The native LocalFlow executable now embeds CPython and owns the AppKit identity.
   Worker subprocesses retain the bundled interpreter. Its own macOS permission
   grant is required; unavailable suppressing taps are visible and shortcut
   monitors wait for permission instead of leaking Option+2 into the destination.
2. An offscreen hidden overlay anchored error instructions outside the visible
   display. Placement now uses a visible anchor or pointer display and clamps to
   its visible frame. Status messages replace old attributed diff text and reset
   the title, preventing stale strikethrough on an error message.
3. Electron editors can omit AX text until native accessibility is enabled.
   Supported, settable `AXManualAccessibility` is requested after policy checks,
   off the UI path; original target identity is checked again.
4. ChatGPT can report success for an AX value setter without changing its editor.
   Selected replacement uses guarded paste, exact source/range/flank checks and
   readback. An uncertain write is never retried through another method. Clipboard
   restoration includes Chromium, legacy/public text and materialized remote
   metadata representations.
5. Terminal screen text is not the shell or agent composer. Zsh captures and
   replaces native ZLE BUFFER/CURSOR/MARK; Codex uses its supported external editor.
   The local handoff carries exact buffer revisions and one-use acceptance and
   never invokes accept-line or submits a prompt. OSC window titles can render
   after the client sends IPC. Admission now waits at most 0.5 seconds for that
   marker, bound to the original app/field/window, then rechecks policy and ancestry.
6. Home and Your Voice refreshed different snapshots. A restored row also made
   MAX(rowid) disagree with latest_revision_id, repeatedly failing profile refresh.
   Reads now follow the saved current revision, refresh changed evidence in the
   background and retain valid measurements on transient failure. Installed Home
   verified 1,749/1,749 spoken words again in installed build 25, including visible
   Your Voice progress and zero provider requests. Your Voice counts eligible speech
   before cleanup; excluded evidence can legitimately differ from total speech.
7. Tap interruption could miss a key release. Startup/recovery reconcile physical
   state while retaining still-held consumed keys. Enter routing uses the active
   input source, disarms on focus changes and stays out of the Hub refinement input.
8. Source deletion previously prevented disclosure but left derived text/index
   rows. The same writer transaction now purges linked current memories, history,
   evidence, FTS/vectors and queued learning, and rejects late source ingestion.
   Independent explicit corrections survive on their own evidence. Mixed-source
   inferences lose authority if any required source is deleted.
9. Suggestions limited the mixed candidate set before category filtering, hiding
   General cards behind personalized candidates. Category filtering now precedes
   the limit and native WKWebView category switching is verified.
10. Inspection ignored selected context/model settings. It now uses preview's
    authoritative compiler, frozen context, model/effort and depth asynchronously.
    Copy refers to the displayed inspection and refuses changed/forgotten evidence.
11. A timed event could reach a cold Hub before the workspace mounted. Pending
    session IDs now remain native until consumed by the mounted route. Recent
    sessions are loaded independently from the initial session, so Clear/reopen
    does not permanently filter the list to the cleared ID. Lists include bounded
    source excerpts; full canonical revisions are loaded only when opened.
12. Scratchpad Enter lacked a review PID and was excluded by the external-app
    key guard. Host-created note captures now receive an explicit internal-editor
    lease. The menu closes and the editor regains focus before generation. Missing
    WKWebView AXWindow values require an opt-in, bounded same-process parent chain
    to the exact Hub window; a contradictory real window is rejected. Note ID,
    revision and range are still revalidated before its single committed write.
13. Native menus can keep AX focus on the original text field while tracking keys.
    AXMenuOpened now permanently invalidates that candidate's focus lease. An
    actual menu received Return and ran a harmless counter action, with no preview
    acceptance. Native input-method composition also received Return normally.
14. A cached semantic model had no user-facing setup path when absent. Memories
    now exposes a native background setup job with progress and cancellation.
    It checks existing data locally, stages missing/corrupt assets, verifies the
    pinned artifact hashes, validates CPU inference and publishes a complete cache
    generation under the cancellation lock. Failed publication restores the prior
    cache. Cancel/failure refreshes actual status; it does not claim to undo a
    cache generation whose publication already completed.
15. Later prompt refinements could retain facts from an ancestor even when their
    own retrieval pack was empty. Copy/refine/select/apply and cached job reads now
    validate that entire selected branch. Provider admission, writer publication
    and queued insertion recheck it. Revoked context previews are removed from
    outbound session views. Saved prompt text stays as a document; using that
    assistant branch again requires Original or a deliberate manual revision.
16. Approved project paths omitted available Git identity. Frozen context now
    records separate resolved workspaces, sanitized remote identity, HEAD and
    observation time using bounded local Git reads. It contacts no remote and
    imports no files. Missing roots retain notes/source-only operation.
17. Definition authoring sometimes changed task nesting, audience/actor roles or
    quantity scope. Its generic contract, independent definition review and custom
    verifier now cover those relations. Completed repairs compact repeated history
    while retaining the frozen intention, reviewed candidate, user constraints and
    actual host observations. Every later provider admission revalidates context.

These are observed code paths and test findings. They do not assert that every
historical screenshot was independently reproduced.

## Implementation map

| Responsibility | Principal paths |
|---|---|
| Compiler, bounded enrichment, verification, metering | `localflow/v2/transforms/{prompts,engine,quality,claude,evaluation}.py` |
| Canonical revisions, jobs, authoring, suggestions | `localflow/v2/transforms/{conversations,intelligence,authoring,jobs,learning,runtime,destinations}.py` |
| Scoped projects, evidence, local retrieval, correction/forgetting | `localflow/v2/memory/`, `localflow/v2/store.py` |
| Capture and single insertion authority | `localflow/v2/insertion/{selection,hosts,service,validation}.py` |
| Review keys, focus, permissions, native UI | `localflow/{app,permissions,transform_hotkey}.py`, `localflow/v2/transforms/{review_keys,focus_scope}.py`, `localflow/v2/ui/transforms_panel.py` |
| Shell/Codex integration and native launcher | `localflow/v2/integrations/`, `scripts/integrations/`, `scripts/build_app.sh` |
| Hub workspace/inspector/creation/memory/selectors | `frontend/src/routes/transforms/`, `frontend/src/lib/`, `frontend/src/components/Select.svelte`, companion surfaces |
| Fresh Home counts and eligible activity | Home route, companion state/readmodels, profile, STT, worker |
| Evaluation and qualification | `scripts/v2/transform_*eval.py`, `scripts/v2/qualify_transform_*.py`, focused tests |

## Measured quality, model selection and cost

Prompt Engineer/refinement use Sonnet 5.5 extra high. Polish remains Opus 5.5
medium; Concise remains Opus high. Definition authoring uses Sonnet medium;
created custom transforms execute with the production custom default, Opus medium.
Definition/semantic verification use Opus low; memory extraction uses Haiku with
thinking off. Host-backed suggestions make no model call. Roles are measured
separately; authoring model selection does not silently change execution.

| Evaluation | Actual result | Limit |
|---|---|---|
| Frozen PE final: 20 fresh sources twice | Mean 99.6, minimum 95; zero judged hard failures; 2 repairs; $1.605818 | Fallible independent judgments |
| Seven matched enrichment pairs | Candidate preferred 6/7, median score gain 8 | Small comparison; losing pair retained |
| Private subscription/model comparison fixtures | 88→97 / 91→100 | Transformed only; not answered or researched |
| PE end-to-end latency | p50 19.825 s, p95 24.938 s | Misses initial 5 s / 15 s UX targets; fidelity tradeoff disclosed |
| PE verifier, 20 clean + 20 adversarial | 1 false positive, 0 false negatives | Exact request equivalence checked; historical cohort summaries retained |
| Custom verifier final, 20 clean + 20 adversarial | 40/40, 0 false positives/negatives; $0.378020; p50 2.142 s, p95 2.980 s | Fixed synthetic labels, custom verifier revision 4 |
| Scoped local retrieval | 33/36 top-five relevant hits, zero cross-scope disclosures | Actual MiniLM CPU retrieval; lexical fallback labeled degraded |
| Retrieval at 10,000 records | Earlier fixture: p50 181.47 ms, p95 205.6 ms. Fresh Git-identity fixture: p50 291.86 ms, p95 339.62 ms | Latest end-to-end Git variant misses the initial 250 ms p95 target. Separate host runs; no isolated overhead estimate |
| Contextual generation | 12/12 across two projects/off; 8 scope contrasts, zero leaks | Four synthetic tasks |
| Downstream outcomes | Baseline 8/8, current 8/8, delta 0 | No improvement claim |
| Refinement | Sonnet extra high 6/6, low 5/6 | Small role set |
| Authoring selection comparison | Sonnet medium 3/3, $0.408434, p50 45.758 s; Opus medium 1/3, $0.768736, p50 71.028 s | Development calibration before final samples |
| Authoring final v3 | 12/12 intention families; 24 fresh nonempty samples + 12 empty controls; mean 99.75, minimum 98; $1.697936; p50 43.249 s, p95 70.632 s | Families were previously exposed; sample inputs are fresh. 129 calls, 340,897 input and 44,709 output tokens, no unknown costs or unseen execution repairs |
| Memory extraction | Haiku off 15/15; 4 useful positives, precision 1.0; $0.0075767 | Small labeled scope/authorship set |
| Suggestions | Actual host pipeline 5/5, model cost $0 | Evidence required for personalization |

Earlier authoring failures remain recorded. Fresh v2 passed 11/12: the remaining
case hit the conservative repair budget, not a passing output. Compaction and
bounded request/token capacity addressed that failure; the v3 sample set was
frozen afterward. No intention-family holdout or empirically perfect output is
claimed. A 100 score is a rubric result, not proof of completeness.

Authoring permits four drafting turns, eight host tools and twelve total native
requests including sample verification/repair, with a 64k-token and $1 job bound.
No silent shortcut binding, auto-apply or overwriting is introduced. Evaluation
uses immutable request/fixture/context/compiler/validator/model/judge identities,
explicit attempt IDs, preflight reservations and SDK retries disabled.

Known token-priced usage is **$32.0991873**; unknown or
unfinished calls retain **$29.91948** in conservative reservations
(**20** calls). Reservations are not charges. Additional frugal API
spending is authorized; the $80 working tranche is an internal resumable bound.
The initial $25 budget no longer blocks work. This is token-price accounting,
not a provider billing statement. Several focused high/extra-high source-review
attempts exhausted output caps and supplied no verdict; measured usage remains
in the ledger. A narrow Sonnet thinking-off review completed, and its findings
have explicit dispositions. Earlier review records remain. No NativePeers
compatibility rejection was bypassed.

## Native compatibility and keyboard evidence

All content was synthetic. No test chat or coding task was submitted and no
transformed command was executed. Tail barriers consume only issued test events
if production suppression fails; barrier counts are separate from target counters.

| Target/path | Actual evidence | Result and limit |
|---|---|---|
| Instrumented native target | Actual event tap, held/repeated Return, keypad, disabled preview, Escape | PASS: 2 writes, 0 target Return events |
| Installed ChatGPT flow | Actual shortcut, exact source, native provider/preview, Return, unchanged flanks and independent readback | Build 21 PASS, 0 tail interceptions, owned window cleared/closed; earlier keypad PASS on build 14. Earlier build-21 focus/blank-view refusals remain BLOCKED, not counted as passes |
| Installed Ghostty/zsh | Actual installed buffer client/server, ZLE, provider, Escape, Return+repeat, independent BUFFER readback | PASS on build 15; exact test-prompt capture excluded unrelated screen strings; Unicode/multiline/flanks preserved, accept-line attempts 0. Owned window closure independently confirmed |
| Installed Ghostty/Codex | Actual managed CLI Ctrl-G, installed editor/client/server/provider, Enter+repeat, second editor composer readback, cancel 130 | PASS on build 16; 0 unframed Return bytes, 0 tail interceptions; owned child/window closed |
| Installed Claude | Native coordinator, provider, held/repeated Return during generation and after readiness, fresh Return/readback | Build 18 PASS; held key did not accept, fresh press applied once, 0 tail interceptions, owned window closed |
| Installed Chrome localhost app window | Native coordinator, provider, contenteditable, Return, exact readback/flanks | Build 18 core flow PASS, 0 tail interceptions. Overall run BLOCKED only on empty-paragraph cleanup assertion; independent process/profile cleanup confirms owned window/process closed and disposable profile removed |
| TextEdit helper | Native Return/keypad replacement | Keys pass; cleanup blocked by unsaved-document risk, recorded separately |
| Hub workspace → original ChatGPT | Installed native Refine, canonical identity, physical typing/Returns, manual save, original-target revalidation/readback | Core flow PASS on build 16; run 7 overall BLOCKED on subsequent test-session cleanup. All four owned sessions later cleared through actual UI; recent-session route-remount regression fixed and verified in four browser variants |
| Installed inspector/suggestions | Real WKWebView/native bridge and disposable Store checks | PASS within recorded scope; browser fixtures are not live-provider claims |
| Physical Fn speech → ChatGPT | Actual microphone sample, installed recognizer/cleanup, independent AX readback | Spoken phrase captured/pasted exactly after word correction; no chat submitted. Native outcome remains insertion_unverified:readback_resized rather than insertion_confirmed; independent readback established the text. Owned usage/training content was removed |
| Installed Scratchpad | Native menu → provider → preview → Return/repeat → committed note revision | Build 20 PASS, exact canonical prompt, one committed revision, 0 tail interceptions, owned note deleted. Build 21 additionally freezes the note ID before async editor focus |
| Native focus/menu/IME | Real production listener/FocusScope against disposable AppKit target | Other-field Return delivered normally; native menu action received Return with no transform accept; Japanese composition committed 日本 with no transform accept. U.S. source and original input settings restored; target closed |
| Identity/lifecycle | Native name/menu/icon, single instance, close/reopen/quit, live suppressing tap | PASS; bundle packaging 16/16 on installed build 21 |

Only one disposable application window was used at a time. Every owned ChatGPT
window returned to its before-window count after closure; historical CG window IDs
are not treated as permanent identity. Final inventory sees two ChatGPT AX windows
and one LocalFlow instance, with the original coding terminal process still alive.
No unrelated window is closed. The original native target run after the latest
change stopped on a foreground guard after its first successful suppressed apply;
its owned target was independently closed. Its earlier complete Return/keypad/
disabled/Escape record remains separate. Native menu and IME tests cover the
recorded AppKit menu/input method, not every third-party menu or IME implementation.

## AC01–AC22 disposition

PASS refers to stated scope. A blocked or unrun check is not counted as a pass.

| Gate | Status | Evidence / remaining condition |
|---|---|---|
| AC01 Baseline | PASS | Remote/HEAD/worktrees/ownership/build manifests recorded; unrelated research preserved |
| AC02 Prompt quality | PASS | Frozen final and matched comparisons; timing target miss disclosed |
| AC03 Independence | PASS | All-source independent verification, literal/grounding and omission fixtures |
| AC04 Native flow | PASS | Installed ChatGPT build 24 ordinary/full-screen and separate native status-menu path; earlier Claude/Chrome/TextEdit scopes retained; cleanup limits recorded |
| AC05 Source accuracy | PASS | Exact native selections and ZLE/Codex composer readbacks; wrong-source strings excluded |
| AC06 Terminal | PASS | Actual installed Ghostty ZLE and Codex editor round trips; PTY stale/region/Unicode cases, no execution |
| AC07 Enter apply | PASS | Installed ChatGPT Return/keypad, terminal repeats, instrumented zero-Return counters; scope limits above |
| AC08 Key lifecycle | PASS | Actual focus switch, menu, Japanese IME and restored input source; native Escape/repeats, real Hub text Returns, tap-gap/paired-release tests |
| AC09 Replacement | PASS | Single authority, target/region/flank checks, uncertain-write refusal, collection-independent idempotence |
| AC10 Inspector | PASS | Exact compiler/context/settings parity, stale-copy refusal, installed UI and real Store tests |
| AC11 Selectors | PASS | Custom accessible controls, long labels/keyboard/minimum widths/light/dark browser checks |
| AC12 Tutorial | PASS | Text actions and Enter semantics match native controls; retention/capability limits described |
| AC13 AI authoring | PASS | Real tool loop, production sample tests, refine/save/reload/idempotence; final 12/12 families on fresh samples |
| AC14 Suggestions | PASS | General/personalized pipeline, eligibility, dismissals, category filtering and source deletion |
| AC15 Conversation | PASS | Live canonical refinement/manual edit/apply-back; actual UI clearing of four sessions, persistent CAS/version tests, cleared-session route-remount regression |
| AC16 Context | PASS | Installed build 25 real CPU setup/reuse; cancellable staged downloads/repair verified through real Store jobs with HTTP fixtures and four UI variants; two-project/off generation, measured retrieval, Git identity/isolation/freshness/conflict checks |
| AC17 Memory | PASS | Capture/confirm/correct/scope/pause/forget/restart tests; eligible extraction measured |
| AC18 Forgetting | PASS | Extraction/index/retrieval/publication races, inherited assistant context checked before provider/copy/select/apply and on publication; atomic source-derived purging. Deliberate user documents remain independent |
| AC19 Agent boundary | PASS | Bounded native tools, cancellation, source revocation before subsequent admission, explicit saves |
| AC20 Model choice | PASS | Separate role pipelines, measured model/effort selection, cost/latency, final sample exposure disclosed |
| AC21 Dock | PASS | Native app name/icon/menu/lifecycle and own permissions; no duplicate native instance |
| AC22 Upgrade/regression | PASS | Migration/restart/frontend/store/deletion/notes/history, physical Fn speech/readback and Scratchpad Enter; native resize outcome retains its unverified label |

## Verification and private records

Records are in ignored `build/transforms-intelligence/`, including the following
completion-audit checks (suites overlap and are not summed):

- `final25-git-workspace-scale.json`: 10,000 actual stored synthetic records,
  36 queries with fresh local Git identity, p50 291.86 ms / p95 339.62 ms.
  The initial 250 ms p95 target is missed and retained as such.
- `final25-transforms-unittest.log`: 168 passing cases;
  `final25-integrations-unittest.log`: 109 passing cases;
  `final25-memory-unittest.log`: 42 passing cases, actual MiniLM recall 33/36
  and zero cross-scope disclosures.
- `installed-home-counts25.json`: visible Home 1,749 words and Your Voice
  1,749 of 2,000; both match the current retained counts, with zero paid calls.
- `installed-semantic-setup25-3.json`: actual installed Hub setup action, real CPU
  validation, existing assets reused, successful job and ready state. Earlier
  startup/layout observation refusals remain separately recorded.
- `installed-memory25-tests.log`: 18 passing real Store/bridge/job cases importing
  the installed modules; no live desktop calls, clipboard changes or paid calls.
  `completion-audit-native-remediation.log`: 17/17 actual coordinator cases,
  including refusal before any write for a forgotten ancestor.
- `packaging25.log` / `packaging-installed25.log`: 16/16 each; frontend Node
  41/41, Svelte 0 errors/warnings and four light/dark responsive browser variants.
  The UI fixtures cover setup progress/cancel/timeout/retry and repository identity;
  native setup in build 25 checks and reuses the real cached CPU encoder without a
  model call or download. A native cold-download/cancel was not run against the
  installed cache; its real Store job/HTTP boundary and UI cancellation are tested
  separately rather than mislabeled as a live-network UI run.
- `installed-chatgpt-24.json`: exact source, displayed result, flanks and Return,
  zero tail interceptions, owned window cleared/closed. `installed-chatgpt-24-fullscreen-4.json`
  additionally verifies full-screen Space entry, an onscreen preview, apply and
  restoration. Earlier window-set/layout/readiness refusals are retained.
- `installed-native-menu24.json`: actual installed status-menu capture/provider/
  preview/apply with exact readback and zero target Return events. Overall report
  remains BLOCKED on its final AX window-count read after closing the window;
  `installed-native-menu24-independent-cleanup.json` independently confirms empty
  target, zero Returns, process exit and removed owned bundle. It is a native
  AppKit control, not a new claim that every third-party menu was qualified.
- `native24-to-build25-content-delta.json`: all UI/key/insertion/provider/frontend
  modules are byte-identical between the native build-24 checks and build 25.
  The sole runtime delta handles a missing project root in local Git metadata;
  filesystem tests and the installed backend suite cover it. The ChatGPT runs
  are retained as build-24 records, not relabeled as new build-25 tests.
- `completion-audit-context-lineage-review-off.json` and the explicit finding
  dispositions. The extra-high attempt hit its output cap and gave no verdict;
  its measured usage remains accounted. Static review is not test certification.

Earlier qualification records remain unchanged, including:

- `final21-transforms-unittest-2.log`: 155 passing unittest cases;
  `final-selection-m06-seam.log`: 8 isolated seam checks;
  `final-custom-quality-tests.log`: 7 plain-function checks.
- `final21-integrations-unittest-2.log`: 109 passing cases;
  `final21-memory-unittest.log`: 35 passing cases;
  `backend-final17-tests.log`: 49 backend/role cases including recent-session data.
  Suites overlap; these are not summed into a unique-test claim.
- Frontend: 41 Node checks; Svelte zero errors/warnings; four light/dark responsive
  browser fixtures; committed web assets rebuilt. Browser fixtures use synthetic
  bridge replies, not a paid provider or native apply operation.
- `qualification-bundle-21-tests.log` and `installed-bundle-21-tests.log`: each
  16/16; source and frontend provenance included.
- Quality/role/context reports, frozen manifests, immutable calls and budget ledger;
  earlier failures, invalid fixture labels and blocked runs are retained unchanged.
- `installed-chatgpt-11.json`, `installed-chatgpt-12.json`,
  `installed-ghostty-zle-12.log`, its independent cleanup record,
  `installed-codex-gui-4.log`, `installed-hub-apply-7.json`,
  `installed-fn-chatgpt-1.json`, `installed-asr-audio-diagnosis.json`,
  `installed-physical-fn-chatgpt-18.json`, `installed-chatgpt-21-4.json`,
  `installed-claude-held-18-2.json`, `installed-browser-18.json`,
  `installed-scratchpad20.json`, `native-key-edges-4.log`,
  `input-method-final-restoration.json`.
- Memory-deletion/inspector/suggestion installed-code/UI records, clipboard
  round-trip checks, profile/Home and all 81 M14 cases from the recorded earlier
  qualification batches. Their dates/scopes are retained rather than relabeled.

## Defaults, integration and recovery

Memory retrieval and learning default off. Approved project roots/manual evidence
are required; window titles, model-written text and quoted third-party claims do
not establish truth. Retrieval/learning/training consent remain separate. Context
is inspectable, optional, scoped, correctable, excludable and forgettable. Missing
MiniLM assets preserve source-only transforms and explicitly degraded lexical
retrieval. Memories → Local semantic search provides visible/cancellable setup.
Downloads use pinned public Hugging Face assets and local CPU inference. No cloud embedding key or subscription is required.

The user-scoped terminal integration lives in the application support directory.
Its marked `.zshrc` block preserves unrelated configuration and existing bindings.
New shells expose Ctrl-X Ctrl-L for the ZLE transform and `codex-localflow` for an
explicit Codex editor handoff. Only the wrapper child gets EDITOR/VISUAL changes.
Ctrl-G opens the external editor; no active coding session is restarted.

Uninstall from outside the repository so the bundled modules are selected:

```sh
PYTHONPATH=/Applications/LocalFlow.app/Contents/Resources \
  /Applications/LocalFlow.app/Contents/Resources/venv/bin/python \
  -m localflow.v2.integrations.cli uninstall \
  --directory "$HOME/Library/Application Support/LocalFlow/terminal-integration" \
  --zshrc "$HOME/.zshrc"
```

`localflow-terminal-unload` removes owned bindings in an existing shell without
closing it. Recovery archives preserve verified bytes, links and modes; matching
pre-upgrade and pre-build database backups remain private. Schema-14-only code
must not be paired with the migrated schema-16 database. A rollback requires a
matching database and preservation of later records before replacement.

Superseded qualification bundles 14–21 were compared with verified archives or
the installed app and removed, freeing about 7.45 GB of logical duplicate data.
Earlier remnant installations were also archived and removed; reproducible native
test bundles and the owned browser profile were removed after process closure.
The installed app is preserved. Earlier remnant recovery bundles are ZIP archives,
not launchable app copies. The merged remote spacing branch was deleted after
ancestry/PR checks. After main was pushed, the completed Claude-transforms and
transforms-intelligence remote heads and the local intelligence branch were
removed after ancestry checks and zero open pull requests. Eight NativePeers-owned worktrees remain because the tool's
planner refuses four resumed histories (OWNERSHIP_CONFLICT) and four histories
with unproved owned-process/output closure (CLEANUP_UNCERTAIN). They occupy about
324 MB. Tool-owned worktrees are not removed behind its controller; no unique or
dirty work is forced away. The separate paper branch and all eight tool-owned
worktree branches remain.

The orchestration page has uncommitted changes and is left alone under its
ownership rule. Its next realignment should show terminal, authoring and core Hub
apply-back, microphone, Scratchpad and keyboard qualification complete, with the
scoped limits in this report, plus build25 semantic setup, inherited context
revocation and Git workspace identity; controller teardown remains blocked.
Other M07/M14/M15/paper work is outside this slice.


## Completion-audit close-out

Follow-up launchable builds 22–25 were also removed after verifying their source
snapshots, prior recovery archive or identical installed bytes. The installed
build 25 and verified recovery ZIP/database pairs remain.

The follow-up source remediation is complete and deployed; remaining teardown
verification belongs to the NativePeers controller. Its fresh read-only plan
still refuses four resumed generations (OWNERSHIP_CONFLICT) and four unproved
owned-process/output closures (CLEANUP_UNCERTAIN). No additional API credential or
subscription is needed for the implemented product. Removing those eight worktrees
requires controller-owned release/closure proof; their branches and local data are
retained until that exists. Earlier failed Claude authentication/quota attempts are
worker-admission failures, not proof that their tasks were implemented. Their
replacement implementations and actual qualification results are the records above.

The original generic handoff files remain privately relocated under descriptive
titles. The orchestration page, unrelated caller inventory and paper outputs remain
under their existing ownership. This slice does not edit those dirty files.
