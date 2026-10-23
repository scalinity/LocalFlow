# Contract: Transforms and prompt collaboration

**Scope:** deliberate text rewriting and prompt authoring. Ordinary dictation,
normalization, faithful cleanup, vocabulary, and insertion retain their contracts.
**Implementation:** `localflow.v2.transforms`, `transforms_store`, scoped memory,
the native preview, the companion bridge, and the existing insertion queue.
Qualification results belong in the acceptance record; this contract does not
certify an installed application or a model's output.

## Editing and engineering

Polish improves expression while preserving meaning, stance, modality, facts,
constraints and voice. Concise removes redundancy without removing substance.
Prompt Engineer improves the effectiveness of the requested task: proportionate
verification standards, comparison dimensions, deliverables and methodological
clarifications are permitted. Research premises remain claims to investigate.
Personal/project additions require eligible supplied evidence. A short clear
prompt may stay short. Original language stays unless translation is requested.

None of these modes answers or executes the downstream request. Advice,
investigation, proposals and implementation remain different scopes. Do not
invent budgets, deadlines, models, environments, personal facts, new prohibitions
or implementation authority. Explicit no-expansion instructions disable enrichment.
Custom instructions define permitted changes; unaltered requirements survive.
Built-in instructions are read-only; duplication creates a custom definition.

## Compiler and identities

`prompts.build_request` is authoritative for execution, inspection, previews and
evaluation. Trusted instructions are separate from JSON-serialized source,
examples, explicit follow-up instructions, constraints and labeled context data.
Closing XML tags or JSON resembling a system message do not escape that framing.
Examples demonstrate the complete current output schema. Keys and provider access
remain native; the WebView receives neither credentials nor provider thinking.

`TransformJob` freezes source, definition/instruction and example versions,
compiler/schema/enrichment policy, locale, follow-up constraints, depth and the
exact context fingerprint. Mutated context refuses before a provider call. A
context/source/instruction change creates a new semantic task. Model and requested
effort describe an attempt, so comparable models can share the same task identity.
Authored task, frozen context, generation attempt, canonical revision and external
apply operation are separate identities.

Retry Original reuses the frozen task; it does not silently refresh context.
Transform Output makes the previous output the source of a new task. Its external
destination remains the original captured region. Neither operation is a
preference judgment. Auto/Compact/Thorough controls prompt depth independently
of provider effort.

## Generation and independent checks

The native Anthropic layer reads the existing Transforms Keychain credential.
Generation, verification and index work run off UI/audio/GPU-lock paths. No key,
network, SDK, supported configuration or usable response yields an explicit
recoverable outcome with the original intact. Invalid saved model choices remain
unavailable until explicitly changed/reset. An uncertain network submission is
not automatically retried. A source over the supported bound refuses; it is
never truncated.

Structured output contains only the finished replacement text in `text` or
`prompt`. Prompt Engineer also returns requirement spans, enrichments,
evidence IDs/revisions, unresolved clauses and separate warnings. Copy/Accept
never includes commentary, warning text, JSON, internal IDs or thinking.

The generator's map is supporting evidence. It cannot certify completeness:

- A source-side clause ledger reaches the independent semantic verifier even
  when a clause is absent from the returned map.
- Deterministic checks preserve quoted/code spans, URLs, paths and identifiers,
  validate cited spans and reject fabricated/changed context references.
- A separate verification call checks omissions, contradictory mappings,
  modality/optional changes, invented restrictions, downstream task execution
  and unsupported personal additions. It is probabilistic, not a proof.
- At most one targeted repair receives concrete issues. A material unresolved
  issue disables Apply and retains a recovery result. No substitute provider
  silently replaces the selected configuration.

`applied` is the compatible engine path for a validated candidate **ready for
application**, not a receipt that an external write happened. Other paths are
`needs_review`, `no_changes` and `fallback_original`. Blocking issues are separate
from advisory warnings. Significant whitespace is preserved; exact equality,
not whitespace folding, establishes no change. Attempts retain requested/served
configuration, token usage, end-to-end time and verification/repair cost; unknown
usage remains unknown.

`atoms.py` retains the historical lexical validator and its adversarial regression
cases. Lexical similarity is not the production semantic gate.

## Capture, review and application

Menu and physical global shortcuts enter the same coordinator. Secure/denied
fields refuse before content reads. AX capture binds the field's owner, window,
UTF-16 range, source and bounded surroundings. Direct selected text is checked
against range text when available. Conflicting APIs or invalid units refuse.
Terminal screen/scrollback ranges confer no composer authority.

A suspended ZLE widget or supported Codex external-editor handoff exports its
logical buffer. The private same-user IPC challenge binds an operation to the
client process/session and immutable buffer revision. ZLE exposes a marked region
or whole buffer; Codex exposes the whole prompt. Only the editor client updates
its own verified buffer, without paste framing, backspaces, Return, command
acceptance or prompt submission. Cancellation leaves the original intact.
Installation and removal preserve unrelated shell/editor settings and active
sessions. Codex's trailing-whitespace limitation is disclosed and refused rather
than silently damaging text.

The preview remains nonactivating, with text-only accessible actions. The scoped
review-key lease consumes plain Return/keypad Enter and their repeats/matching
release, including after hiding the panel. The same candidate-scoped coordinator
arbitrates clicks and keys once, independently of training collection. A held key
cannot queue acceptance during generation. Escape dismisses/cancels. App switches,
expiry, shutdown and tap disablement disarm the lease. Modified keys, input-method
composition and LocalFlow editing surfaces retain their own keyboard behavior.
When interception is unavailable, click remains explicit and Enter is unverified.

The existing insertion queue owns external AX/paste replacements and logical
editor commits. It revalidates immediately before the effect; a changed target
never receives blind deletion. Outcomes distinguish verified application,
unverified posting, changed target, cancellation, failure and copy. A logical
editor's accepted return is not an app-visible verified-delivery receipt. Undo
retains the existing target-bound authority.

Busy, missing-definition, capture and generation failures are visible. Diagnostics
records operation/phase, reason, source length/hash and adapter without source text.

## Context, memory and revisions

Context defaults off. Explicit project selection and personal memory use are
separate controls. A project identity comes from approved roots/verified paths or
explicit selection, never a window title or the last project. Approved excerpts
are bounded and exclude secrets, caches, build outputs, binaries and root/symlink
escape. Local semantic and lexical retrieval filter eligibility/scope/freshness
before ranking. Missing local embedding assets are labeled lexical degradation.

Memories are versioned, source-linked facts/preferences with scope, authorship,
status, freshness and correction/forgetting. Explicit Remember is distinct from
text selected for transformation. Optional learning accepts eligible user activity;
generated output, quoted third-party content and uncertain ASR cannot become
personal truth. Learning, context disclosure and training collection are separate.
Current instructions override remembered defaults. Disputed/stale facts are not
silently merged into a prompt.

Forgetting revokes retrieval, indexes, suggestions and pending publication.
Source suppression prevents unchanged deleted evidence being re-extracted. Jobs
validate frozen evidence again inside the writer operation that publishes their
result. Already transmitted requests and user-managed external documents/backups
cannot be retroactively erased by LocalFlow.

Prompt sessions persist full canonical revisions, explicit instructions, manual
edits, context lineage and a monotonic canonical pointer. Concurrent edits use
expected revisions; a stale result cannot overwrite a newer draft. Reopening a
session does not revive external destination authority. Applying from the Hub
requires deliberate destination reacquisition and the existing insertion checks.

## AI creation, suggestions and persistence

AI creation produces an editable complete definition with synthetic examples,
production-pipeline tests and conversational refinement. The host permits at most
four model turns/eight typed tools, bounded tokens/spend and cancellation. Tools
retrieve only eligible context, inspect definitions, validate/test samples and
propose a draft. No shell, arbitrary writer, credential reader, message sender or
computer-control tool is exposed. Only explicit idempotent Save creates a versioned
transform, with no automatic shortcut, auto-apply or silent overwrite.

General suggestions work without history. Personalized suggestions require
eligible recurring observations, retain provenance, respect dismissal/cooldown and
revoke when evidence is forgotten. No background suggestion activates itself.

All new data uses additive versioned migrations and the existing Store writer.
Transform definitions, examples, hotkeys, model preferences, history, research and
training candidates retain their existing lifetimes. Runtime preview/apply
identity works with collection off. Frontend changes require rebuilt bundled
assets and separate qualification of the actual application bundle.

## Evaluation

The synthetic suite separates development, selection and final scenario families;
private reference examples are development only. Selection never uses the final
holdout. A frozen candidate is evaluated repeatedly on the untouched final set;
a failed final requires a new evaluation version and fresh holdout before claiming
an untouched result. Authoring is measured by created-transform performance on
unseen samples. Execution, prompt refinement, authoring, suggestions, extraction
and verification are distinct roles, including deterministic alternatives.

Cache identity includes fixtures/split manifest, compiler/prompt/schema/context,
model/effort, validator, judge prompt/model/schema and scoring revision. Paid calls
use a resumable total ceiling, including verification, repairs and judging;
unknown billing retains its reservation. Failures, costs, end-to-end p50/p95,
warning errors and quality distributions are reported as observed. A rubric-complete
reference or LLM self-rating is not release evidence.
