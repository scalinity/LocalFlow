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
- **During recording** — `ContextCollector.begin` spawns a daemon
  collection thread running three providers: `focused_field`,
  `site_origin`, `workspace` (window title read once, shared).
- **At release** — `finalize(deadline)` joins the thread with the
  bounded deadline and composes the immutable `ContextSnapshot`.
  A provider that misses the deadline is omitted with reason
  `deadline`; the snapshot is marked `partial` and dictation proceeds
  (M06-AC02). `finalize` is idempotent per job. Whatever a late
  provider produces afterwards is returned by `take_downstream()` as a
  **separately identified downstream revision** (`stage:
  "downstream"`, new snapshot id) — never merged into the pre-decode
  snapshot and never relabeled pre-decode (M06-AC05, S30.1).

## One snapshot, three consumers (no per-purpose reads)

- `to_scope_context()` → the M05 `ScopeContext`
  (app_bundle/site_origin/workspace; profile stays None until a
  writing-profile subsystem exists) — vocabulary filtering and hint-set
  selection.
- `to_engine_context(vocabulary)` → the M04 normalize
  `ContextSnapshot(destination_app, path_context, identifiers,
  vocabulary)` — the job's already-frozen vocabulary snapshot rides
  through unchanged.
- `context_snapshot_id` → `capabilities.asr_hint_request_fields(...,
  context_snapshot_id=...)` — the S30.1 request field, populated only
  under a qualified adapter manifest (None on this adapter).

The live wiring: the M05 trio is captured at hotkey-down scoped by the
**identity** (app bundle); at finalize, if origin/workspace resolved
and widen the scope, the trio is **upgraded by rebuilding the
vocabulary snapshot from the job's frozen entry set** (never a store
re-read, so a mid-flight dictionary edit cannot leak into an in-flight
job — M05 AC03 preserved), and the upgraded hint set is what
`on_hint_set` stores before recognition.

## Sensitive-field rules (absolute)

1. **Classify before any content read**: role/subrole decide
   `secure | text | unclassifiable | none`. A secure field's content
   attributes (value, selection, placeholder, ranges) are never read;
   the snapshot records classification `secure` with omission
   `secure_field` and no retained content anywhere (M06-AC01).
2. **Unclassifiable fields** get plain dictation: identity kept, no
   nearby text (omission `unclassifiable_field`).
3. **Denied apps** (`context_denied_apps`) are never read at all — not
   even role/subrole; identity records the denial (omission
   `denied_app`).
4. **Browser origins** strip query/fragment by construction
   (`scheme://netloc` only). `AXURL` is the source; a domain-shaped
   window-title token is a marked fallback (`origin_source`), and no
   origin is invented when neither resolves (`not_exposed`).
5. **Placeholders** are recorded as metadata, never as field text, and
   are never prepended to a transcript.
6. **No arbitrary filesystem reads** — an `AXDocument` locator is a
   recorded string; nothing is opened. Workspace is the containing
   directory name (document) or the IDE title's project segment.
7. **Nearby text is data, never instructions**: it never enters a
   model prompt; "ignore previous rules" in surrounding text cannot
   change cleanup behavior (M06-AC04). The cleanup input is exactly
   the normalized transcript. **M07 permitted context (the whole
   surface, since M07):** cleanup additionally receives the protected
   spans from the M04 ledger (mapped into normalized-text
   coordinates), the job's frozen scoped vocabulary canonicals
   (bounded, ≤ 40) plus the frozen alias→canonical pairs as
   validator-only data, and the destination profile derived from the
   snapshot's target category — never nearby text, identifiers,
   origins or workspaces. See `contracts/cleanup.md`; the hostile-text
   and input-invariance tests extend unchanged.
8. Nearby reads are bounded (`NEARBY_CHARS` = 600 around the
   selection/insertion point); identifiers are extracted only from that
   bounded window, capped (`IDENTIFIER_LIMIT` = 64).

## Freshness, staleness, caching

Snapshots carry `captured_at_utc`/`finalized_at_utc`/
`finalize_duration_ms` and per-provider status + duration (coverage and
skip frequency are first-class benchmark outputs, not just latency).
`same_destination(frontmost)` answers the S12/S18 stale check
insertion revalidation calls before granting replacement authority —
**consumed since M08** by `localflow.v2.insertion.validation` (the
identity row of the revalidation matrix, `contracts/insertion.md`); a
pid/bundle mismatch means stale and routes the artifact to saved
history. A short-lived cache holds resolved origin/workspace keyed by
frontmost pid plus a window/field signature that is re-read every
capture; any change invalidates it (event
`context.cache_invalidated`).

## Degradation and diagnostics

Every failure mode degrades to less context, never a failed dictation:
context disabled (`context_enabled: false` — no identity read at all),
identity unavailable, AX permission unavailable
(`permission_unavailable`), AX messaging failure
(`ax_messaging_failed`), provider timeouts (`deadline`). Events are
content-free (counts/reasons/durations; `context.snapshot_finalized`,
`context.cache_invalidated`, `context.identity_unavailable`,
`context.capture_failed`, `context.finalize_failed`,
`context.collector_unavailable`).

## Evidence (S29.4 context family; S29.14)

`EvidenceCollector.on_context_snapshot(ctx, snapshot,
downstream=False)`: the pre-decode call happens before recognition;
the downstream revision is stored separately with its stage. The full
snapshot JSON (identity strings, origin, workspace, field text) is a
**lease-governed store artifact** (`stage=pre_decode_context`/
`downstream_context`, `role=context_snapshot`, training lease) — never
an event or envelope field. The envelope's `context.destination`
sub-block is content-free (ids, flags, counts, omission reasons,
provider statuses); `context.downstream` mirrors the late revision.
Retention is the **independent** `training_retain_context` knob: off ⇒
no payload artifact is written even with collection enabled, and the
envelope marks `retained: false` with the reason plus
`missing_reasons.context_snapshot_payload` so replay inputs are
honestly incomplete (E19 reconstructable-vs-redacted).

## Hosts and testability

`SystemAXHost` isolates every Accessibility call behind a per-call
messaging timeout (`AXUIElementSetMessagingTimeout`, 0.2 s default);
`system_frontmost` isolates NSWorkspace. Tests inject a fake host over
synthetic AX trees (`tests/v2/context/fixtures_context_targets.json`:
8 E10 destination classes × empty/mid-sentence/selected/hostile plus 8
adversarial trees — secure, unclassifiable, permission-off, denied,
no-focused, no-URL, title-fallback, slow). Real-destination behavior
(Mac native AX) is the pending human trial per E10; the dev-run
terminal needs its own Accessibility grant (same TCC pattern as the
mic).

## Limitations (documented, not hidden)

- `profile` scope is fed since M10: the app's per-job freeze widens
  the ScopeContext with the resolved writing-profile name (see
  `contracts/profiles.md`); the snapshot's own `to_scope_context()`
  still leaves it None (the profile is resolution state, not context
  observation).
- Identifier resolution is the bounded nearby-window only; a full
  visible-symbol provider would need the optional IDE/browser
  extension channel (S12) — not shipped, nothing speculates it.
- The window-title origin fallback is heuristic and provenance-marked;
  browsers that expose no AXURL report no origin rather than a guess.
- The jobs table has no `target_snapshot_id` column; the ids live on
  the job dict and in the evidence context block, and M08's insertion
  rows (`insertions`/`insertion_observations`, store schema v4) carry
  them where persistence needs them.
- Insertion revalidation is live since M08 (see above and
  `contracts/insertion.md`).
