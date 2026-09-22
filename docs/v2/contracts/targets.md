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
destination, never instructions for the cleaner.

## Insertion transaction (live since M08)

`same_destination()` answers the stale check insertion revalidation
calls before granting replacement authority — consumed since M08 by
`localflow.v2.insertion.validation.validate_target` (the identity row
of the full matrix in `contracts/insertion.md`: identity, window,
field, and exact-selection for the replacement case). The coordinator
hands every finished artifact to the serialized insertion queue;
revalidation failure routes the output to saved history with a
clipboard copy as the one-action paste offer. Clipboard ownership
generations, the method matrix, readback confirmation, target-bound
undo and the S29.8 observation window are specified and tested in
`contracts/insertion.md`.

## Insertion outcomes

`confirmed` · `posted_unverified` · `saved_not_inserted` · `target_changed`
· `failed`. A posted event is not a confirmed insertion: `confirmed`
requires a target readback of the owned range equal to the inserted
text — never LocalFlow's own pasteboard. The V1 baseline recorded
every paste as `posted_unverified` ("inserted N chars" meant "event
posted"); the legacy collector entry preserves that semantic.

## Invariants

1. Revalidate the target immediately before writing; on change or
   uncertainty save the output and offer a one-action paste instead.
2. Clipboard restore only if the pasteboard still holds LocalFlow's owned
   generation; a user copy always wins.
3. One parent-owned insertion queue; completed jobs never interleave
   clipboard transactions.
4. Undo is target-bound; stale ranges show the previous text rather than
   sending destructive backspaces.
