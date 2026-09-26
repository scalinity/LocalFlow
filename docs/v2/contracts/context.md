# Contract: Local context snapshots and destination awareness

**Spec:** S12, S18 (identity half), S30.1 (snapshot id) · **Owner:** M06 ·
**Suites:** EV-08 (tests/v2/context/), EV-18/EV-19 (pipeline half)

`localflow.v2.context` (snapshot value objects + providers + collector)
gives the pipeline destination awareness without making dictation depend
on a slow screen reader: cheap identity at PTT start, asynchronous
bounded collection during recording, and a finalize at release bounded
by the S12 deadline (`context_deadline_ms`, default 75).

## Capture structure (S12)

- **PTT-start identity** — `TargetSnapshot` reads the frontmost app via
  NSWorkspace only (bundle/pid/name, denied-app decision, category).
  It runs after the overlay shows; **no Accessibility call ever runs on
  the hotkey path**.
- **During recording** — `ContextCollector.begin(target)` returns the
  job's **collection handle** and starts one daemon collection thread.
  Every later call names that handle; there is no global "active"
  collection.
- **At release** — `finalize(handle, deadline)` waits at most the
  deadline for that handle's providers and composes the immutable
  pre-decode `ContextSnapshot`. A provider that misses the deadline is
  omitted with reason `deadline`; the snapshot is marked `partial` and
  dictation proceeds (M06-AC02). A handle publishes **exactly one**
  pre-decode snapshot: a repeated or concurrent call returns the same
  object; a handle whose target is not the caller's yields None.
- **After ASR starts** — `take_downstream(handle)` returns at most one
  **downstream revision** (`stage: "downstream"`, new id): a late
  **delta** carrying only the providers that finished after the cut,
  with `parent_context_snapshot_id` = the pre-decode id and
  `revision_kind: "late_delta"`. Taking it **seals** the handle: a
  provider still running is discarded and a second call returns None.
  Late context is never merged into, and never relabeled as, the
  pre-decode snapshot (M06-AC05, S30.1).
- **Preview** — `preview(handle)` composes what the handle has collected
  so far WITHOUT publishing it (no snapshot, evidence, cache or event;
  None once the handle is revoked or released);
  the app uses it only to precompute scope projections while recording.

### Read ownership

Content is read from **one element**: the focused element **of the
target application's own element** (`focused_element_for(target pid)`),
accepted only when `element_pid(el)` equals the target pid. A focus
change to another app after PTT can therefore never make a job read that
app; an element that cannot be proven to belong to the target is refused
unread (`destination_unverified`). The frontmost identity is re-checked
before collection and again after the field stage: a change — another
pid, or another bundle at the same pid — skips every remaining read
(`destination_changed`). Field, window and origin all
derive from that one element, so a snapshot never mixes destinations.
External Accessibility state is not atomic: the target's own UI can
change between two reads of its element; such a change is still the
target's, and a destroyed element answers with an error, not content.

### Lifecycle, revocation and bounds

A handle is collecting → finalized → sealed, or **revoked** at any
point. `revoke(handle)` only flips a flag — no store call, no wait, no
event — so the store's deletion listener can call it. Every
Accessibility call the collection makes checks the flag first: once
revoked or sealed, no further call reaches the application, and nothing
more is published (finalize and take_downstream return None; the cache
is not refreshed). The app revokes on cancel (recording and processing),
a below-minimum discard, sleep/lock abandonment and job deletion, and
calls `shutdown()` on quit (admission closes, every live handle is
revoked). At most `MAX_ACTIVE` (4) collection threads are admitted; a
collection older than `MAX_AGE_S` (30 s) is revoked at the next begin;
a refused begin leaves the job identity-only
(`context.admission_refused`). Threads are never killed and the UI
never waits for them.

## One snapshot, three consumers (no per-purpose reads)

- `to_scope_context()` → the M05 `ScopeContext` (app_bundle,
  `scope_site_origin`, workspace; profile stays None — the writing
  profile is resolution state, see `contracts/profiles.md`).
- `to_engine_context(vocabulary)` → the M04 normalize
  `ContextSnapshot(destination_app, path_context, identifiers,
  vocabulary)` — attached whether or not a vocabulary exists.
- `context_snapshot_id` → `capabilities.asr_hint_request_fields(...,
  context_snapshot_id=...)` — the S30.1 request field, populated only
  under a qualified adapter manifest (None on this adapter); always the
  pre-decode id.

The live wiring: the M05 trio is captured at hotkey-down scoped by the
identity (app bundle, plus the resolved writing profile). At finalize,
when origin/workspace resolve and widen the scope, the trio is upgraded
by projecting the job's **frozen entry set** onto the widened scope
(never a store re-read, so a mid-flight dictionary edit cannot leak into
an in-flight job — M05 AC03). The upgraded vocabulary, engine context
and policy are built in locals and commit as one tuple; the job records
`scope_disposition`: `widened`, `unchanged`, `no_policy` (normalization
off: nothing to widen), `widening_failed` (a build
failed — the captured narrower scope stays, with an event) or
`widening_deferred` (see the release budget). A successful widening
whose optional hint selection fails leaves the job with no hint set.

### Release budget

The additional post-release context delay target is **P95 ≤ 75 ms**,
measured from the release instant (`released_mono`, taken on entry to
the release handler — before the recorder stops and before finalize,
the scope upgrade and evidence packaging — so M13's end-to-end time
includes that work). The widened projection (~55–75 ms for 10,000
entries on the reference Mac) is **precomputed while recording**: once
the job's collection finishes, a background precompute resolves the
scope the finalize will use (the same helpers; the profile resolved
purely) and builds the projection into a single-slot cache keyed by the
captured entry tuple itself (identity) and the scope. At release a hit
is used as-is; a precompute still running is waited for only within
what remains of the budget; a miss builds synchronously when its
estimated cost fits (or is under 5 ms) — the last measured cost per
entry, 0.01 ms before any build, times this dictionary's size;
otherwise the job keeps its captured narrower scope as
`widening_deferred` and the projection warms in the background for the
next job. A failed or deferred widening also restores the captured
writing profile, number policy and skill registry: the job runs
entirely on its hotkey-down tuple, never a finalized profile over
captured vocabulary. A precompute stops once its handle is released. The provider deadline and the
widening share the one budget clock.

## Sensitive-field rules (absolute)

1. **Classify before any content read**: AXRole/AXSubrole decide
   `secure | text | unclassifiable | none`. A secure field's content
   attributes (value, selection, placeholder, ranges, character count)
   are never read; the snapshot records classification `secure` with
   omission `secure_field` and no retained content anywhere (M06-AC01).
2. **A failed classification read** (an AXError other than "attribute
   unsupported"/"no value") makes the field `unclassifiable` with
   omission `classification_failed` — never text.
3. **Unclassifiable fields** get plain dictation: identity kept, no
   nearby text (omission `unclassifiable_field`).
4. **Secure/unclassifiable elements answer AXRole/AXSubrole only**
   (plus the ownership and window lookup): their AXURL is not asked.
   The containing window's title is allowed destination metadata.
5. **Denied apps** (`context_denied_apps`) are never read at all — no
   Accessibility call of any kind; identity records the denial
   (omission `denied_app` on every provider).
6. **Browser origins** are `scheme://host[:port]` for http/https only,
   rebuilt from validated parts: userinfo, path, query and fragment are
   dropped by construction; the host is kept as written (M05 compares
   case-insensitively); an explicit port is kept; IPv6 literals are
   bracketed. Invalid ports, malformed authorities and non-web schemes
   yield no origin (`not_exposed`).
7. **Title fallback** — when the element exposes no usable AXURL, the
   first plausible host in the window title is a marked fallback
   (`origin_source: window_title`); file names in any case, version
   numbers, e-mail bylines and path segments are never hosts. A
   title-derived origin is **evidence, never site scope**
   (`scope_site_origin` is None for it; M05 scope and M10 rules see only
   an authoritative origin).
8. **Placeholders** are recorded as metadata, never as field text, and
   are never prepended to a transcript.
9. **No arbitrary filesystem reads** — an `AXDocument` locator is a
   recorded string; nothing is opened, stat'd or listed. Only file URLs
   and scheme-less absolute paths are locators; the workspace is the
   containing directory name exactly as written in the locator
   (percent-encoding is not decoded; a file URL's authority is
   ignored), or the IDE title's project segment. Workspace names are
   opaque scope values: equal names at different paths share scope.
10. **Nearby text is data, never instructions**: it never enters a
   model prompt; "ignore previous rules" in surrounding text cannot
   change cleanup behavior (M06-AC04). **M07 permitted context (the
   whole surface, since M07):** cleanup receives the normalized
   transcript, the protected spans from the M04 ledger (mapped into
   normalized-text coordinates), the job's frozen scoped vocabulary
   canonicals (bounded, ≤ 40) plus the frozen alias→canonical pairs as
   validator-only data, and the destination profile derived from the
   snapshot's target category — never nearby text, selected text,
   identifiers, origins or workspaces. See `contracts/cleanup.md`.

## Budgets and offsets

- Flanks: `NEARBY_CHARS` = 600 UTF-16 units on each side of the
  selection/caret, read with `AXStringForRange`; a host that returns
  more is clipped to what was requested, and a surrogate pair cut by the
  boundary is dropped.
- Identifiers are extracted only from those flanks (never from the
  selection), scanned lazily and capped (`IDENTIFIER_LIMIT` = 64).
- Selection: the range is read first; the text is read only when the
  range is valid (non-negative, inside the field's character count) and
  at most `SELECTION_LIMIT` (4,096) units, and kept only when its length
  matches the range. Otherwise there is no selected text and no range
  at all, native or code-point (a `selection_unavailable` note): an
  incomplete selection never carries replacement authority — M08 treats
  the field like a caret.
- Placeholder 200, document locator 2,048 and window title 512
  characters: an over-budget value is omitted, not truncated.
- Offsets: `FieldContext.selected_range` is zero-based half-open
  **Unicode code points** (`contracts/artifacts.md`) and is present only
  when exact — when the whole prefix up to the selection was read;
  `selected_range_utf16` is the same selection in the host's native
  units (UTF-16 code units). The two are never interchanged.

## Freshness, identity and caching

Snapshots carry `captured_at_utc`/`finalized_at_utc`/
`finalize_duration_ms` and per-provider status + duration (coverage and
skip frequency are first-class benchmark outputs). A snapshot's nested
state (identifiers, provider rows, omissions) is frozen at construction
from a private copy; every serialization returns fresh plain
containers, so no caller or consumer can change the bytes behind a
`context_snapshot_id`.

**Destination identity** is one rule, `snapshot.identity_matches`
(`same_destination` on both `ContextSnapshot` and `TargetSnapshot`):
a match needs a usable pid on both sides, else a usable bundle on both
sides; a pid match is refused when both bundles are known and differ;
absent identity never matches. M08's revalidation and the insertion
lease use the same rule (`contracts/insertion.md`). The pre-decode
snapshot also carries `window_element` — the host's own window element,
**in memory only** (never serialized, compared or hashed with the
snapshot) — which M08 compares with the live window: an equal title is
not a unique window.

A single-slot origin cache (TTL 30 s) is keyed by the identity of what
was read — target pid and bundle, the field element, its window element
and the document locator — never by a title; reuse is disabled when any
of those is unavailable, only an origin read from the element's AXURL
is cached (a title-derived origin is re-derived every capture), a
frontmost pid change clears it (`context.cache_invalidated`), and a
reused value is marked `cached: true` in its provider row.

## Degradation, statuses and diagnostics

Every failure mode degrades to less context, never a failed dictation.
Provider omission reasons: `deadline`, `provider_failed` (an exception —
only for providers that produced nothing; a failed window lookup costs
only the title-derived fallbacks), `permission_unavailable`,
`ax_messaging_failed` (no focused element / failed lookup),
`not_exposed` (an honest absence), `secure_field`,
`unclassifiable_field`, `classification_failed`, `denied_app`,
`destination_changed`, `destination_unverified`, `not_in_revision`
(downstream rows only). AXError classes: 0 is a value;
kAXErrorAttributeUnsupported (-25205) and kAXErrorNoValue (-25212) are
absence; kAXErrorAPIDisabled (-25211) is permission; every other error
is a failed read. Events are content-free (counts/reasons/durations;
exception class names, never messages): `context.snapshot_finalized`,
`context.cache_invalidated`, `context.identity_unavailable`,
`context.capture_failed`, `context.finalize_failed`,
`context.collector_unavailable`, `context.provider_failed`,
`context.destination_changed`, `context.admission_refused`,
`context.collection_revoked`, `config.context_invalid`,
`vocabulary.refresh_deferred`, `vocabulary.prewiden_failed`.

## Configuration (read once at startup; no hot reload)

`config.context_policy` validates the privacy controls and fails CLOSED:
a non-boolean `context_enabled` disables context; a non-boolean
`training_retain_context` disables context retention; a
`context_denied_apps` that is not a list of non-empty strings disables
context entirely (the deny intent cannot be honored); a
`context_deadline_ms` outside finite [0, 250] falls back to 75. Each
problem is a content-free `config.context_invalid` event (key +
reason). JSON `false` and proper lists work as written. A change applies
from the next launch.

## Evidence (S29.4 context family; S29.14)

`EvidenceCollector.on_context_snapshot(ctx, snapshot, downstream=False,
scope_disposition=None)`: the pre-decode call happens before recognition;
the downstream revision is stored separately with its stage and
lineage. The full snapshot JSON (identity strings, origin, workspace,
field text) is a **lease-governed store artifact**
(`stage=pre_decode_context`/`downstream_context`, `role=context_snapshot`,
training lease) — never an event or envelope field. The envelope's
`context.destination` sub-block is content-free (ids, flags, counts,
omission reasons, provider statuses, `scope_disposition`);
`context.downstream` mirrors the late revision and names its parent.
`retained: true` is decided at publication: `publish_example` keeps it
only when the referenced artifact committed for the job AND holds a live
training lease; otherwise the block says `retained: false`,
`retention_reason: retention_write_failed`, and
`missing_reasons.context_snapshot_payload` records it. Retention is the
**independent** `training_retain_context` knob: off ⇒ no payload artifact
is written even with collection enabled (pre-decode and downstream), the
envelope marks `retained: false` with the reason plus
`missing_reasons.context_snapshot_payload` (E19 reconstructable-vs-
redacted). Deletion stays governed by the store (M02): a revoked handle
publishes nothing, and the store's deletion barrier refuses any late
write for a deleted job.

## Hosts and testability

`SystemAXHost` is the typed native adapter and the only Accessibility
call site: elements come from the target application's own element with
a per-call messaging timeout (0.2 s); reads return `(value, AXError)`;
selection ranges are decoded from the native `AXValue` CFRange
(`AXValueGetValue`) and parameterized reads box theirs (`AXValueCreate`);
the window is the field's own `AXWindow` (with the same messaging
timeout) — never a substitute such as the application's focused window,
which nothing proves contains the field; unavailable otherwise. `system_frontmost` isolates NSWorkspace. Tests inject
fakes: `FakeAXHost` over the synthetic trees
(`tests/v2/context/fixtures_context_targets.json`: 8 E10 destination
classes × empty/mid-sentence/selected/hostile plus adversarial trees)
and the multi-app `m06_world.WorldHost` (per-app focus, a movable
system focus, every call logged by owner and attribute). The native
half is qualified against a synthetic window of the suite's own
(`tests/v2/context/test_native_ax.py`, never activated, reached by its
pid). App-level suites on a Mac whose terminal holds the Accessibility
grant run under `tests/v2/context/run_isolated.py`, which blocks and
counts every live-desktop Accessibility read and synthetic event.
Real-destination behavior (Mail, Slack, browsers, Xcode, real secure
fields, permission changes) remains the human trial in
`docs/v2/VERIFICATION.html`.

## Caller inventory (local `rg`, remediation)

Constructors and consumers of the M06 types in `localflow/` and
`scripts/`, classified:

- **Producer:** `v2/context/collector.py` (TargetSnapshot,
  ContextSnapshot, handles).
- **App wiring (`app.py`):** `startDictation` (identity, begin,
  precompute), `_finishCapture` (release instant, finalize, evidence),
  `_finalize_job_context` (finalize, M04/M05/M10 upgrade),
  `_m10_re_resolve`/`_m10_destination` and `_m10_finalize_upgrade`
  (profile + workspace), coordinator `take_downstream`,
  `cancelDictation`/`_discard_short`/`_abandon_capture_for_system`/
  `_on_job_deleted` (revoke), `applicationWillTerminate_` (shutdown),
  `_m11_capture_selection` (an M11 constructor of a
  `transform_selection` snapshot for M08 revalidation — M11-owned; it
  still reads the raw `context_denied_apps` rather than the validated
  policy, and the M11 merge owns switching it to
  `_context_policy`, with a malformed list denying every app for
  transforms).
- **Consumers:** `v2/insertion/validation.py` and `target_lease.py`
  (identity rule, window element, host-unit selection),
  `v2/insertion/service.py` (target category/surface label),
  `v2/training.py` (`on_context_snapshot`), `v2/store.py`
  (publication reconciliation), `v2/capabilities.py`
  (`context_snapshot_id`), `v2/vocabulary.py` (`ScopeContext`).
- **Not M06:** `v2/normalize/*` define and consume their own
  `ContextSnapshot` (the M04 engine context, `to_engine_context`'s
  target type).
- **Scripts:** `benchmark_m06.py`, `m06_remediation_repro.py`,
  `m06_native_probe.py`, `m06_mutation_check.py`; `benchmark_m05.py`,
  `benchmark_m08.py`, `benchmark_m10.py`, `m04_/m05_remediation_repro.py`
  construct snapshots or scripted collectors for their own milestones.

## Limitations (documented, not hidden)

- The document locator (`AXDocument`) is read from the focused element
  only; an app that exposes it only on its window yields no workspace
  (the synthetic native probe's NSTextView answers -25205 for it).
  Which real editors expose it on the field is part of the pending
  native trial (M06-V001).
- Browser origins come from the focused element's AXURL; a browser that
  exposes the URL only on an ancestor web area yields the title
  fallback (evidence only) or no origin — real browsers are part of the
  pending native trial.
- Identifier resolution is the bounded nearby window only; a full
  visible-symbol provider would need the optional IDE/browser extension
  channel (S12) — not shipped.
- Within one window, M08 does not distinguish two fields of the same
  role (a moved caret or a field change keeps authority by design);
  element identity is reliable only within one process lifetime, so the
  window element is never persisted.
- The jobs table has no `target_snapshot_id` column; the ids live on the
  job dict and in the evidence context block, and M08's insertion rows
  carry them where persistence needs them.

## Remediation policy (m06-policy-v1)

The decisions behind the rules above, numbered as in
`tests/v2/context/m06_corpus_adjudications.json`: D1 secure/
unclassifiable metadata (rule 4); D2 failed versus absent (rule 2 and
the AXError classes); D3 heuristic authority (rules 7 and 9); D4
downstream revisions (capture structure); D5 destination distinctions
(identity rule and window element); D6 configuration; D7 budgets; D8
native offsets; D11 release clock and budget; D12 origin forms (rule
6); D13 workspace locators (rule 9).
