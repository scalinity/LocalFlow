# Contract: Preference observations

**Spec:** S29.10 · **Shape owner:** M01 · **Live owners:** M11 (transform preferences), M14 (review) · **Suites:** EV-20

A valid preference record: task kind; immutable source/audio/input/context
manifest; **both** exact candidate outputs; generating model/runtime/decode
metadata where available; displayed order; reviewer; judgment ∈
{`A`, `B`, `tie`, `neither`, `uncertain`}; reason/domain; review time;
source event IDs.

## Invariants

1. Both candidates must address the same supplied task/input — identical
   conditional input hashes, or an explicit valid canonical comparison
   input. A retry with changed source/instructions is a different task.
2. The last-pasted candidate is not thereby the winner; a manual correction
   is an edit observation until a supported judgment exists.
3. Display order is randomized and recorded; model confidence and selection
   order are not preferences.
4. Fallback output vs the rejected proposal is a valid pair only when both
   were shown as candidates for the same input.

## Baseline status (M01)

None exist. Historical retries in the legacy log are NOT preference pairs
(new audio each time).
