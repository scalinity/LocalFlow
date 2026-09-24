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

## M11 live status (transform preferences)

Transform candidates record the exact task manifest (task key over
mode + source + instructions + examples revision, source/instruction
hashes, transform/prompt revisions, display order) with source/output
texts in lease-governed artifacts inside the same writer op; explicit
`accept|reject|undo|prefer_a|prefer_b|tie|neither|uncertain`
observations join candidates **only under one task key** — the store
refuses cross-task pairs at write time (M11-AC05). Retry-original
joins the task; transform-of-result and changed-source retries are
different tasks by construction. The dictation auto-apply path
records candidates only — an automatic application is not a judgment.
No preference-training algorithm exists (S16 deliverable boundary).

## Baseline status (M01)

None exist. Historical retries in the legacy log are NOT preference pairs
(new audio each time).

## M14 live status (pair review and export)

The Review tab lists every task key with at least two retained
candidates (`ReviewService.preference_pairs`) and records explicit
`prefer_a`/`prefer_b`/`tie`/`neither`/`uncertain` judgments through
`TransformStore.record_observation` — the M11 write-time same-task
invariant is the enforcement, and a cross-task judgment refuses. The
pair is stored in the order shown: `candidate_id` is A,
`candidate_b_id` is B, and `prefer_a`/`prefer_b` name the winner by
slot. Judgments append; the latest comparable judgment on a pair is its
current one. accept/reject/undo stay single-candidate observations,
never pair judgments. The exporter re-verifies the shared task key AND
the conditional input hashes (source, instructions, examples revision)
before any pair leaves the machine, and exports both outputs with their
display order (contracts/dataset_exports.md). No preference-training
algorithm exists.
