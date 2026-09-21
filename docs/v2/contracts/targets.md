# Contract: Insertion targets and outcomes

**Spec:** S12, S18 · **Shape owner:** M01 · **Live owner:** M06 (snapshot), M08 (transaction) · **Suites:** EV-08, EV-10

## Target snapshot

`target_snapshot_id` (UUID) records app process identity, window identity,
focused accessible element, selected range, a surrounding-text fingerprint
and target capabilities. Sensitive fields are never read; browser origins
drop query/fragment. Snapshots are evidence about a destination, never
instructions for the cleaner.

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
