# Contract: Insertion targets and outcomes

**Spec:** S12, S18 · **Shape owner:** M01 · **Live owner:** M06 (snapshot), M08 (transaction) · **Suites:** EV-08, EV-10

## Target snapshot (live since M06)

`target_snapshot_id` (UUID) records app process identity (bundle/pid
via NSWorkspace, read cheaply at PTT start after the overlay — no AX on
the hotkey path), the denied-app decision and app category; window
identity, focused accessible element, selected range and the
surrounding-text fingerprint are completed by the bounded context
finalize at release into `context.ContextSnapshot`
(`contracts/context.md`). Sensitive fields are never read; browser
origins drop query/fragment. Snapshots are evidence about a
destination, never instructions for the cleaner. `same_destination()`
answers the stale check insertion revalidation (M08) will call before
granting replacement authority; the metadata cache invalidates on any
app/focus change. The transaction half (revalidation before writing,
clipboard ownership, one insertion queue, target-bound undo) is M08 —
today's paste remains the V1 `posted_unverified` post.

## Insertion outcomes

`confirmed` · `posted_unverified` · `saved_not_inserted` · `target_changed`
· `failed`. A posted event is not a confirmed insertion. The current V1
behavior posts Cmd+V and reports success without observing the target; M01
records that as the baseline (`posted_unverified` semantics do not exist in
V1 — its "inserted N chars" log line means "event posted").

## Invariants

1. Revalidate the target immediately before writing; on change or
   uncertainty save the output and offer a one-action paste instead.
2. Clipboard restore only if the pasteboard still holds LocalFlow's owned
   generation; a user copy always wins.
3. One parent-owned insertion queue; completed jobs never interleave
   clipboard transactions.
4. Undo is target-bound; stale ranges show the previous text rather than
   sending destructive backspaces.
