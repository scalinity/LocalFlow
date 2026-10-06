# LocalFlow V2 — M04 Read-Only Deep Audit

**Milestone:** Typed Numeric and Spoken-Syntax Normalization  
**Repository:** `scalinity/LocalFlow`  
**Audit date:** September 25, 2026  
**Audited canonical main:** `1c9d981b1505b6cd975ce6e701e0382c6db96c78`  
**Verdict:** **C. Significant normalization-semantic weaknesses**  
**Evidence class:** committed-source audit; runtime reproductions and native verification not performed in this session.

## Executive Assessment

M04 has a useful architecture—typed proposals, explicit layers, retained raw text, a position-based edit ledger, profile validation and independent edit replay—but its semantic acceptance boundary is not yet reliable enough to treat normalized text as meaning-preserving source for downstream cleanup.

The dominant problem is **ownership**: recognizing words that can form a number, date, punctuation command or registered token is repeatedly treated as sufficient evidence that the whole phrase has that meaning. Several independent arithmetic and provenance problems compound that weakness. A comma can disappear into a quantity span; a scaled Decimal can be converted through `int`; a negative port can be validated using its positive magnitude; a literal tail can lose protection; a mixed-case path can be lower-cased; and a mutable policy can keep its old revision after changing behavior.

The finding register contains **1 Critical, 12 High, 3 Medium, 1 Low and 4 Test Gaps**. These are **source-supported findings and verification obligations, not 21 runtime-confirmed failures**. The Critical classification uses the supplied rubric: ordinary prose can become a materially different command-shaped token without review. **It does not mean remote code execution, shell execution or automatic skill invocation.** No such execution path was found in the inspected normalization code.

The accompanying corpus contains **368 text cases across 171 text families, plus 10 stateful probes**. Every case is marked `NOT_RUN`. Wrappers, profiles and registry variants are not independent speech samples, and no population error rate is claimed.

**Recommended decision:** remediate the root causes and harden the independent oracles before relying on M04’s output as trusted semantic input or treating its historical acceptance as current certification. Preserve the existing useful grammar; do not solve this by turning normalization off.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policy.py`

## Audit Boundary

> This audit covers committed GitHub state at `1c9d981b1505b6cd975ce6e701e0382c6db96c78`. Any uncommitted local state is outside the audit boundary.

GitHub was read only. No source changes, branch, commit, issue, pull request, implementation work, native verification or private-data access was performed. M01–M03, M07 and M11 were not re-audited. Downstream modules were inspected only at interfaces relevant to M04.

The connected repository supplied pinned source and ancestry. Repository code search returned incomplete/empty results even for known matches, so absence of search hits was **not** used as proof that no additional callers exist. Selected live coordinator, evidence and consumer paths were traced directly. An exhaustive caller inventory remains M04-AUDIT-21.

The repository was not made executable in this environment: direct checkout/archive access was unavailable, and the connector returned source text rather than a runnable checkout. Consequently:

| Evidence surface | Status |
| --- | --- |
| Source inspection and ancestry | Performed on pinned GitHub content |
| Core package and policy population | Seven Python modules plus policy JSON inspected; downstream collaborators inspected selectively |
| M04 suites / historical fixtures | Read; not executed |
| Adversarial and mutation outputs | Source-derived predictions and independently specified intended semantics; not observed runtime output |
| Portable benchmark | Harness audited; no new timing run |
| AppKit, microphone, Parakeet, Qwen, installed app | Not exercised; PENDING_LOCAL_VERIFICATION |
| Local tree, installed build, pending native results | Outside boundary; no inference made |

This distinction is important: a deterministic source defect can justify repair investigation without a native run, but its exact reproduction and final disposition must still be established by the cloud session. The report deliberately does not claim the current repository suites passed.

## M01–M03 Remediated Main Baseline

The prerequisite foundation check **passes**. The exact commits are:

| Marker | Resolved full SHA | Relationship |
| --- | --- | --- |
| M01 final production repair | 3db74061f23001b9cce3d4fe029e0b30cbc295d6 | Ancestor of audited main; compare showed main ahead 9, behind 0 |
| M02 final production repair | bfbc63c35efa6273cc13242d54d3e5bbe264b21e | Ancestor of audited main; compare showed main ahead 5, behind 0 |
| M03 final production repair | 3e0d1ab972b866b4acbda622984bce04e8f95093 | Direct parent of audited main |
| M03 evidence/documentation head | 1c9d981b1505b6cd975ce6e701e0382c6db96c78 | Audited main itself |

Recent ancestry and the remediation addenda were inspected. `docs/v2/VERIFICATION.html` contains the accumulated M01, M02 and M03 material; its header identifies all three production-repair revisions, and actual M02/M03 verification items and the M01 section were read. The campaign’s non-blocking pending-verification rule is retained. This establishes the committed foundation—not Daniel’s installed application or completion of human checks.

**Pinned commit:** `https://github.com/scalinity/LocalFlow/commit/1c9d981b1505b6cd975ce6e701e0382c6db96c78`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/VERIFICATION.html`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/handoffs/M01.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/handoffs/M02.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/handoffs/M03.md`

## M04 Responsibilities

M04 converts explicitly owned representations while preserving meaning: cardinal quantities, decimals, percent versus percentage points, locale-qualified currency, limited dates/times, codes/phones, versions, IPv4/ports, selected units/dimensions, spoken syntax and registered tokens. It emits text and a typed edit ledger. It does **not** execute the emitted syntax, invent a model name, repair a filesystem path through lookup, perform semantic reasoning on arbitrary prose or create an acoustic reference.

Its essential invariants are: exact value/sign/unit/component identity; conservative whole-span refusal for unsupported/ambiguous grammar; preservation of original punctuation and literal intent; explicit precedence; immutable per-job policy/context; raw-source retention; independent positional replay; and honest stage/evidence failure reporting. M04-AC03 asks for stable second output and an empty second ledger, with the historical literal exceptions now requiring explicit retrospective treatment.

Partial formatting is not inherently corruption. The current contract deliberately permits `twelve dollars and fifty cents` → `$12 and 50 cents` and forbids silently inventing a combined `$12.50` implementation. Conversely, partial parsing that converts an invalid version’s suffix or collapses two comma-separated numbers is not safe merely because its output is syntactically valid.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_SPEC.md#s10`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_MILESTONES.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/normalization.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md#e06`

## Current Normalization Architecture

The package has seven Python modules: `__init__.py`, `engine.py`, `numbers.py`, `syntax.py`, `policy.py`, `span_types.py` and `scoring.py`, plus `policies/number_profiles.json`. The seven-module historical count still describes the package root, **not the complete dependency boundary**: current syntax also consumes M05 vocabulary, M10 snippets and a file resolver supplied through context.

The engine invokes 16 numeric grammars, nine syntax grammars and the two context-fed identifier/vocabulary grammars, with literal/quote discovery and arbitration around them. Its broad path is:

```text
raw text + policy + context
  → whitespace-run tokens, word matching and literal/quote regions
  → numeric / syntax / registered / contextual proposals
  → protected-region and rejected-candidate handling
  → same-span arbitration and greedy overlap resolution
  → text assembly + code-point edit ledger + rejected proposals
```

The declared layer order is literal escape → protected existing syntax → registered explicit intent → typed grammar → context-supported vocabulary → ordinary prose. Numeric input uses `Decimal`; token/ledger offsets are Python string code-point indices, zero-based and half-open. The output-coordinate protection added for generated snippets/file tags is distinct from raw-coordinate protected spans. Neither is an AppKit UTF-16 range.

Several good properties coexist with the findings: proposals are collected before application; edits are applied by coordinates rather than global replacement; the raw source is not overwritten; different-output same-span ambiguity has a rejection path; and the plain transform interface does not itself run a model or shell. Equal-output ownership, structural boundaries and deep immutability are the weak points discussed below.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/span_types.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/snippets.py`

## Historical Review Findings Considered

The historical M04 handoff and September 22 acceptance are useful evidence, not current proof. The original quantified-`hundred`, period-noun and wrong-path AC04 defects have identifiable repairs and regression coverage. The scanner is no longer vacuous. Explicit unknown-profile failure, canonical-content hashing, raw/normalized separation, rejection records, independent edit replay and typed-value privacy controls are genuine improvements.

This audit does not re-report those exact historical fixes as absent. It challenges their remaining boundary: multi-token quantified scales, previously unlisted noun compounds, count-duration time prose, same-output priority, deep table mutation and current downstream composition. It also carries forward the two documented literal idempotence exceptions rather than pretending the old acceptance claimed universal idempotence.

The historical native dictation-profile check remains pending evidence in the campaign. Its existence is not a native pass, and this audit does not erase or duplicate it.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/handoffs/M04.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/acceptance/M04/results.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_syntax.py`

## Numeric Grammar Assessment

Cardinal recognition has useful conservative stop words and a separate anchored path, but arithmetic validity is weaker than lexical recognition. Explicit zero is conflated with an omitted multiplier, and increasing/repeated scale sequences can acquire a plausible number. The approximate-quantity guard does not amount to a complete quantified-region grammar. See M04-AUDIT-04.

Decimal arithmetic is exact until a scaled quantity is sent through integer formatting. That creates an actual value defect rather than merely a formatting preference (M04-AUDIT-03). Unary negative handling is not uniformly propagated into typed consumers (M04-AUDIT-05). Positive/plus speech is not generally the same parser feature as the explicit `plus sign` syntax command; unsupported arithmetic prose should remain prose instead of being “completed” by an invented expression grammar.

Leading decimals, repeated point tokens, malformed scales, unanchored multi-component versions and year speech must be tested as whole expressions. A guard that protects `five and a half percent` does not prove every other unsupported quantity is safe from suffix parsing. `about twelve percent` → `about 12%` is not itself a loss of approximation: the qualifier survives. The oracle must distinguish that from dropping a qualifier or assigning exact evidence to unsupported quantified prose.

Year speech is deliberately limited and can depend on the following context and the optional-year lookahead. Terminal date-year positives are not evidence for all document-title/model-name/prose contexts. Treat those extensions as literal-stability probes; do not implement more year grammar just to increase conversion coverage.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_numeric.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/normalization.md`

## Currency / Percentage / Unit Assessment

Percent and percentage-point classes are distinct, and locale-specific currency/percent display is explicit. English uses the configured dollar convention; Spanish numeric fixtures cover euro/percent/date rendering. Units mostly retain their spoken word while the ledger carries a canonical unit label; dimensions render the multiplication sign and mapped unit without performing a unit conversion.

The exact current supported unit vocabulary is the `dimension_units` policy map, reused by the dimension and number-before-unit grammars—not a general units library. The map contains singular/plural centimeters, millimeters, meters, kilometers, inches, feet, megabytes/megabits, gigabytes/gigabits, kilobytes/kilobits, pixels, seconds, minutes, hours, days, weeks, bytes/bits, grams and kilograms. The numeric suite explicitly distinguishes megabytes from megabits. A remediation must preserve that case-sensitive distinction, singular/plural limitations, and documented unsupported forms rather than infer more units from nearby numbers.

The weak points are full-token punctuation consumption, scaled-decimal truncation, unsigned metadata in selected grammars and whole-candidate refusal. The signed second dimension is especially instructive: the output can look correct while the ledger is wrong. That is why E06 requires independent typed semantics, not only exact text.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policies/number_profiles.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_numeric.json`

## Date / Time Assessment

Month-name dates avoid inventing a US interpretation of already-written `03/04`, and relative dates/noon/hour-only phrases have explicit limitations. Valid meridiem-bearing time output does not add a timezone. These are appropriate conservative boundaries.

However, lexical month matching still accepts modal “may,” invalid compound ordinals can fall back to shorter days, and the time grammar’s utterance-start/preposition rule still steals count-plus-duration prose. These are M04-AUDIT-06/07, not demands to implement a larger date/time library.

The date parser’s current contract documents day-range validation rather than full calendar validation. February 31 and leap-day/year combinations must therefore be adjudicated as a **contract/safety design concern**, not silently presented as a feature already promised and tested. The safe decision must be explicit: do not let consumers treat a minimally parsed date as a calendar-certified date. The corpus includes such design probes separately from defect oracles.

The time ledger uses a clock string (including a supplied suffix) rather than the normalized 24-hour form used by some fixture `protected_values`. That discrepancy reinforces the typed-oracle gap; it is not evidence that the written time necessarily changed meridiem. Define one documented semantic representation before asserting equality across those fields.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/normalization.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_numeric.json`

## Version / Technical-Identifier Assessment

The anchored version grammar deliberately treats a component such as twenty six as 26 and supports digit-run components; it does not conflate the intended anchored version with one ordinary decimal. Existing structured tokens such as `GPT-5.6`, `Qwen3-4B`, `Python 3.14`, `MLX 0.31.2`, underscores and slash-containing literal paths generally bypass the spoken-word grammar because their token shape is not a word phrase. This is useful protection, not a comprehensive parser for all existing code syntax.

The important weaknesses are malformed structured candidates that can expose valid suffixes/prefixes, and spoken paths built from lower-cased matching tokens. Full-chain invalidity, component count and original case must be independent test dimensions. Backticks, fenced code and quoted multiword identifiers also need explicit protection coverage; quote-zone blocking currently names command/vocabulary classes, not every possible contextual rewrite.

Contextual canonicalization is permitted only from the supplied map/snapshot. M04 should not learn the identity of a model, package or path from an online guess, and none is proposed here. M04-AUDIT-14/15 examine only how the current identifier interface composes and becomes idempotent, not the wider M05/M06 feature.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_SPEC.md#s10`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/asr_hints.md`

## Spoken-Syntax / Punctuation Assessment

The actual symbol table includes comma, period/full stop, question/exclamation marks, colon/semicolon, hyphen, bracket/brace/parenthesis commands, asterisk/underscore/backtick, signs, slash/backslash, vertical bar/pipe, quotes and ellipsis. Bare ordinary “dot” and “slash” are not simply global replacement rules; they participate in specific dotfile/domain/IP/path/skill grammars. That distinction is a strength.

Nevertheless, the punctuation gate is substantially a collection of local blockers, and registry membership is used as evidence of slash intent. This leaves ordinary noun compounds and an ordinary verb followed by a real alias exposed. A larger real registry can make a negative fail even though it passed with the default empty registry. M04-AUDIT-01/09 are therefore related but separate: exact registered identity is not command intent, and a known punctuation name is not command intent either.

Literal escape is the appropriate escape hatch, but its arbitrary protection cap and nested-marker handling weaken that safety mechanism on the first pass (M04-AUDIT-10). This is separate from the known second-pass literal exceptions.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policies/number_profiles.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_syntax.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/short_command_corpus.json`

## Profile / Policy Assessment

`technical` is the default; `standard` inherits most behavior but disables designated bare-integer/flag behavior; `off` is a normalization bypass. Standard is **not** a blanket “no syntax/no addresses” profile. The configured locale is `en-US` or `es-ES`; unsupported locales/profiles raise rather than silently remap. Spanish punctuation-name/version support is explicitly narrower than English, as LF-SYN-059/060 document. This audit does not invent multilingual support.

Canonical JSON content, locale/profile and registered mappings contribute to the revision. Equivalent dictionary ordering is deliberately normalized by sorting. The parsed file is cached per process; live file edits are not evidence of automatic hot reload. These features do not overcome mutable nested tables after construction (M04-AUDIT-12).

The application has a separate scope problem: a cached job-effective override can become the next inherited base (M04-AUDIT-13). This must be reproduced with sequential jobs and finalization, not inferred from an isolated constructor test.

**Refuted/narrowed hypothesis:** a style rule with `number_policy="off"` was considered during review. The actual style contract only permits `inherit | technical | standard`; treating an unsupported style value as a shipped production scenario would be a false finding. Global normalization `off` and Raw mode are legitimate, separately handled paths. The profile finding retained here is the supported standard/technical inheritance sequence.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policy.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/profiles.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_syntax.json`

## Span Arbitration / Idempotence Assessment

The engine has explicit priorities and retains rejected proposals. It does not simply apply grammars in discovery order. Different-output same-span ambiguity is treated separately from ordinary overlap, and M10’s deliberate cross-layer snippet-over-vocabulary behavior must be preserved.

Equal-output same-span proposals are not necessarily interchangeable: they can carry different layers, units or typed values. Retaining the wrong representative affects a later overlap and the evidence even when the two strings happen to agree. That is M04-AUDIT-14.

The ordinary worker applies M04 once to raw ASR. `preview_phrase` and evidence collection intentionally call the idempotence diagnostic, which computes a second normalization without applying that second output to the user’s text. Thus the historical literal exceptions are not, by themselves, proof of a live double-normalization bug. The broader current identifier/snippet exception surface and exhaustive alternate-call-path invariant still need explicit tests (M04-AUDIT-15/21).

Permutation testing should distinguish deliberate priority from accidental ordering. Reordering equivalent policy mappings should not alter outputs or revisions; genuinely priority-bearing lists must remain documented as such. Equal-text/different-metadata and three-way overlaps are stronger tests than simple pairwise string equality.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/span_types.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/__init__.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

## Ledger / Evidence / Replay Assessment

The ledger retains source spans, input/output text, class/op, typed value/unit, policy revision, reasons and rejected proposals. Its independent replay applies recorded edits by position, right-to-left, and verifies that each source slice matches its recorded input. It does not merely call the normalizer again or search for the first occurrence of an input string. Repeated substrings and Unicode are therefore addressable in the correct coordinate system.

Raw ASR and normalized text are distinct artifacts. The collector writes a changed normalized-text artifact and a ledger artifact linked to raw; no-change normalization can refer to raw plus the ledger. This supports the M14 distinction between actual normalized text and ledger JSON. The current envelope allowlist includes only selected numeric/date/time-like classes; paths, emails, skills, identifiers, codes, phone numbers, IP strings and versions do not ride as long-lived transcript-derived values in that metadata. Their payload stays in lease-governed artifacts. That is a source-verified privacy strength.

Replay correctness is **not semantic correctness**. A replay can reproduce a wrong date, wrong sign or dropped comma perfectly. Nor is a revision string a complete retained policy. The ledger is sufficient for edit replay while artifacts exist; regeneration from raw+historical policy/context requires verification of retained policy contents and all contextual dependencies. The latter remains a specific M04-AUDIT-21 obligation, not an asserted absence everywhere in the repository.

The collector’s normalization write failure path returns silently (M04-AUDIT-16), and selected typed fields are wrong even when text is plausible (M04-AUDIT-05). Both undermine downstream use of otherwise good evidence structures. Offsets must remain code points internally; UTF-16 conversion belongs only at native UI boundaries.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/span_types.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/training.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/artifacts.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/training_evidence.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/learning.md`

## Pipeline / Failure-Mode Assessment

The inspected live path is `ASR raw → M04 normalize → cleanup → later transform/insertion`. The worker gives the normalizer raw ASR, records the normalized stage separately, then supplies normalized text to cleanup. Raw mode and global normalization-off have explicit bypass behavior. A parser exception retains raw text and emits a normalization failure instead of dropping dictation. The applied text is assigned from a completed result, not an incrementally mutated buffer.

M07 receives normalized source and generated protected output spans. A protection-construction failure uses a conservative fallback rather than silently trusting malformed protection. Cleanup retry reuses normalized source; the inspected M11 transform seam consumes its explicit source and does not call normalization there. These are verified source paths, not full model/native tests.

The real coordinator test is stronger than a fake standalone function test, but imports app/native-related dependencies; it cannot be advertised as a Linux-native integration pass just because the core normalizer is pure Python. The cloud session should use a genuine portable seam or report the platform boundary, never pretend a stubbed AppKit is a native certification.

History/recovery/Scratchpad/manual retry must be exhaustively inventoried in the cloud checkout. In particular, distinguish a new recognition attempt over retained audio from reprocessing already normalized text, retain the previous attempt’s ledger, and identify whether the old or a new policy snapshot was used. This report does not infer Daniel’s private histories or re-open the accepted M03 lifecycle audit.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalization_pipeline.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/training.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/jobs.md`

## Test-Oracle Assessment

The four required suites and benchmark were read, together with the actual fixture documents: `fixtures_numeric.json`, `fixtures_syntax.json`, and `short_command_corpus.json`. The JSON fixtures carry schema version, owner, family/origin, contexts, expected outputs and reference-status metadata. They are synthetic authored regressions, not audio gold or demonstrated untouched holdout sets.

The numeric and syntax suites enforce their nonzero/exact populations, and the short suite asserts 24 cases with separate 16-command and eight-non-command denominators. Independent positional replay, profile/off controls, selected Decimal/unit checks and current AC04 population checks are real strengths. The numeric runner invokes its current review regressions; this audit did not find those functions orphaned outside `main()`.

Weaknesses are concentrated in the oracles: most `protected_values` do not drive a general independent semantic check; negative registry contexts often cannot offer the competing parse; the time test forbids a substring rather than verifying semantic preservation; exception flags can suppress idempotence checks without a tightly asserted exception inventory; and publication failures/sequential profile state are not covered by the ordinary M04 pipeline tests.

No claim of train/test contamination is made merely because fixtures are visible in Git. The history does show author-and-repair regression use, so label them development evidence. Freeze the new challenge set before remediation, record which families are consulted, and retain a separate final challenge layer where feasible. Variants do not create independent prevalence denominators.

Scoring separates number-word representation edits from other ledger edits, and command success from false commands. That is not itself a complete verbatim WER pipeline. M15 must keep raw lexical WER, intended representation, typed semantics and product output separate under E06/E18.4.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_short_command_scoring.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalization_pipeline.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/scoring.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md#e18`

## Performance / Benchmark Assessment

The benchmark times the real API call, records environment and actual constructed word counts, and returns nonzero when its primary long-input p95 misses the 25 ms budget. It is not the historical vacuous scanner. However, nonempty output is insufficient proof of positive work; an identity normalizer can pass that assertion. The workload needs observed edit-class/count assertions and explicit negative-candidate budget coverage (M04-AUDIT-20).

The source shows bounded parser lookaheads rather than an obvious catastrophic nested regex, but overlap arbitration scans prior accepted spans and repeated immutable-string application can scale poorly with edit count. This is a complexity concern, **not a measured regression**. Benchmark 500-word mixed/no-match/dense-edit populations, then longer stress runs to characterize growth. Preserve complete input and output so a “faster” result cannot hide skipped work or truncated content.

The engine’s internal duration excludes final application work, whereas the external live/benchmark timers include it (M04-AUDIT-17). Distinguish those fields. No current cloud timings or Mac timings were measured; historical September 22 M5 Pro measurements remain historical, and this audit does not overwrite them or claim the current build meets the reference-Mac budget.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/scripts/v2/benchmark_m04.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/acceptance/M04/results.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md#e11`

### Finding register

| ID | Severity | Finding / proof obligation |
| --- | --- | --- |
| M04-AUDIT-01 | CRITICAL | A registered alias can turn ordinary slash prose into a command-shaped token |
| M04-AUDIT-02 | HIGH | Word-token spans consume punctuation and can merge separate quantities |
| M04-AUDIT-03 | HIGH | Scaled decimals are formatted through integer truncation |
| M04-AUDIT-04 | HIGH | Cardinal parsing manufactures scale values from zero and accepts malformed scale chains |
| M04-AUDIT-05 | HIGH | Signed text and typed evidence disagree; a negative port can be accepted |
| M04-AUDIT-06 | HIGH | Time ownership steals count-plus-duration prose |
| M04-AUDIT-07 | HIGH | Date recognition changes modal May and falls back inside invalid compound ordinals |
| M04-AUDIT-08 | HIGH | Malformed structured phrases can be partially normalized as valid suffixes or prefixes |
| M04-AUDIT-09 | HIGH | Punctuation blocker lists still rewrite ordinary nouns and descriptions |
| M04-AUDIT-10 | HIGH | Literal escape scope can expire or be reinterpreted inside its own payload |
| M04-AUDIT-11 | HIGH | Spoken paths lower-case user components and accept unsupported chain prefixes |
| M04-AUDIT-12 | HIGH | A policy revision does not identify immutable runtime policy contents |
| M04-AUDIT-13 | HIGH | A previous job’s style override can become the next job’s inherited normalization default |
| M04-AUDIT-14 | MEDIUM | Same-output same-span arbitration can lose higher-priority ownership |
| M04-AUDIT-15 | MEDIUM | Idempotence exceptions extend beyond the two documented literal fixtures |
| M04-AUDIT-16 | MEDIUM | Normalization evidence-write failures are swallowed without a stage-specific failure record |
| M04-AUDIT-17 | LOW | The result’s internal duration excludes application/assembly work |
| M04-AUDIT-18 | TEST GAP | Fixture success does not independently establish typed semantics or broad negative coverage |
| M04-AUDIT-19 | TEST GAP | AC04 is no longer vacuous but does not certify the whole reachable normalization boundary |
| M04-AUDIT-20 | TEST GAP | The benchmark can report a green budget after normalization is reduced to no-op work |
| M04-AUDIT-21 | TEST GAP | Global retry/caller and historical-policy reconstruction guarantees remain unclosed |

**Reading the findings:** “source predicts” below means a control-flow-derived likely output, not a recorded runtime result. The cloud session must reproduce, refute or narrow each one before changing production. All minimal calls assume `from localflow.v2.normalize import normalize, NormalizationPolicy, ContextSnapshot` and the pinned checkout.

## Critical Findings

### M04-AUDIT-01 — A registered alias can turn ordinary slash prose into a command-shaped token

**Severity:** CRITICAL  
**Confidence:** High for the parser path; end-to-end reproduction still required  
**Category:** Command-intent false positive  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10: registered explicit skill intent; ordinary slash speech remains content. M04-AC06 and EV-06/E06: separate false-command controls.

**Code location.** `localflow/v2/normalize/syntax.py — grammar_skills`; `tests/v2/normalization/short_command_corpus.json — SC-17, SC-24`; `tests/v2/normalization/fixtures_syntax.json — LF-SYN-017, 019, 024`

**Current / likely actual behavior.** With registered_skills={"code review":"code-review"}, the source predicts `we should slash code review time` → `we should /code-review time`. This is command-shaped TEXT, not execution.

**Failure mechanism.** The grammar recognizes slash plus an exact registered alias at arbitrary positions. Registry membership establishes token identity but is being used as sufficient evidence of command intent. The ordinary verb sense can have precisely the same following words as an alias.

**Minimal reproduction.** normalize("we should slash code review time", NormalizationPolicy(registered_skills={"code review":"code-review"}))

**Expected behavior.** Keep the ordinary budget/time-reduction sentence literal, or reject an ambiguous skill proposal. Preserve `slash code review` → `/code-review` and the explicitly intended mid-sentence `add slash code review to the list` positive.

**Existing test coverage.** Current negatives use slash prose whose following words are NOT registered aliases. Existing positives intentionally support mid-sentence tokens.

**Why the existing oracle misses it.** An empty or irrelevant registry makes the crucial negative easy: the competing interpretation is never offered. A sentence-start-only fix would break existing accepted positives.

**Regression recommendation.** Use matched registry-present/absent negatives: `slash code review time`, `slash costs` with costs registered, plus literal/quoted variants. Assert no skill edit as well as preserved meaning. Pair every negative with actual token-insertion positives.

**Narrow repair direction.** Introduce explicit, conservative intent ownership without removing useful mid-sentence command dictation. Resolve ambiguous ordinary verb uses to literal/review; do not rely on a blacklist of alias names.

**Downstream impact.** M05/M10 supply real aliases, so more vocabulary can increase false triggers. M07 sees the wrong token as its source. M14/M15 must not label a deterministic token insertion as an ASR success/error. No evidence of M04 executing a skill was found.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/short_command_corpus.json`

## High Findings

### M04-AUDIT-02 — Word-token spans consume punctuation and can merge separate quantities

**Severity:** HIGH  
**Confidence:** High  
**Category:** Token boundaries and semantic scope  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 source offsets/original spelling and exact values; S13/S14 scope preservation; M04-AC01/AC05.

**Code location.** `localflow/v2/normalize/engine.py — tokenize, _assemble, _apply`; `localflow/v2/normalize/numbers.py — _span and quantity-consuming grammars`

**Current / likely actual behavior.** Source-predicted examples: `twelve percent.` → `12%`; `twelve dollars, please` → `$12 please`; `twenty, five percent` → `25%`. The last changes two punctuation-separated quantities into one.

**Failure mechanism.** Token matching removes edge punctuation to recognize a word, but start/end still cover the entire non-whitespace run. Numeric parsers consume adjacent word tokens without treating that punctuation as a structural barrier. The resulting edit replaces punctuation together with the number words.

**Minimal reproduction.** For s in ["twelve percent.", "twelve dollars, please", "twenty, five percent", "one hundred. five percent"]: inspect normalize(s, NormalizationPolicy()).text and edits.

**Expected behavior.** Retain punctuation outside the owned numeric core. Never parse through a comma or sentence boundary as though it were a space between cardinal components. Accept safe independent edits only when their scopes remain separate.

**Existing test coverage.** Exact fixtures mostly use unpunctuated numeric phrases. Vocabulary/identifier code already has narrower handling for core word boundaries; it does not establish correctness for numeric grammars.

**Why the existing oracle misses it.** Checking a rendered number without testing the original punctuation envelope misses both boundary deletion and changed arithmetic grouping.

**Regression recommendation.** Test commas, periods, colons, semicolons, parentheses, quotes, smart quotes, em dashes, newline, tabs and nonbreaking spaces. Distinguish benign whitespace from a clause/list delimiter. Check source and output spans independently.

**Narrow repair direction.** Separate lexical core spans from delimiter spans and make grammar continuation respect structural barriers. Do not recover punctuation with a global post-formatting pass that guesses where it belonged.

**Downstream impact.** All downstream cleanup, references and insertion receive altered scope. Replay can faithfully reproduce the WRONG edit, so replay alone cannot catch this.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

### M04-AUDIT-03 — Scaled decimals are formatted through integer truncation

**Severity:** HIGH  
**Confidence:** High  
**Category:** Exact numerical value  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 decimal arithmetic and exact representation; E06 numeric fidelity versus display; M04-AC01.

**Code location.** `localflow/v2/normalize/numbers.py — parse_signed_quantity, _quantity_text, grammar_currency, grammar_integer`

**Current / likely actual behavior.** The source predicts an amount of 1234 rather than 1234.5 for `one point two three four five thousand dollars`; the formatter may add a grouping separator. `zero point zero zero zero one thousand dollars` can render an amount of 0 rather than 0.1. The numeric truncation, not grouping punctuation, is the defect.

**Failure mechanism.** After applying a spoken scale, the parsed quantity clears its fractional-format marker. The no-fraction formatter uses int(...), even when the scaled Decimal is non-integral. Some typed values can remain fractional while the displayed amount is truncated.

**Minimal reproduction.** Normalize both phrases above; compare the rendered amount with Decimal("1.2345") * Decimal(1000) and Decimal("0.0001") * Decimal(1000), independently of production parsing.

**Expected behavior.** Render the exact amount, or conservatively keep an unsupported phrase in words. Never truncate or silently round. Display and ledger must denote the same amount.

**Existing test coverage.** LF-NUM-027 checks 1.5 million dollars, whose scaled value is integral. The suite has significant-zero tests but not a fractional residue after scaling.

**Why the existing oracle misses it.** An integral-scale example cannot detect a formatter that coerces every scaled result to int. Most typed assertions are separate hand-picked examples.

**Regression recommendation.** Cover positive/negative, zero/nonzero fractional residues, all supported scales, currency/percent/bare quantity paths, and both positive controls 1.5 million and 1.25 thousand.

**Narrow repair direction.** Keep exact Decimal value and rendering precision separate; choose integer formatting only after proving integrality. Avoid floating-point round trips.

**Downstream impact.** M07 cannot safely infer the lost fraction. M14 evidence may otherwise show a ledger value inconsistent with text. M15 needs independent numerical equality, not just expected-string checks.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

### M04-AUDIT-04 — Cardinal parsing manufactures scale values from zero and accepts malformed scale chains

**Severity:** HIGH  
**Confidence:** High for zero/scale mechanics; quantifier variants require reproduction  
**Category:** Cardinal validity and approximation  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 exact values and ordinary-prose preservation; M04 historical quantified-scale repair; M04-AC01.

**Code location.** `localflow/v2/normalize/numbers.py — parse_cardinal, quantity/prose guards, grammar_currency`; `tests/v2/normalization/test_normalize_numbers.py — quantified-prose regression`

**Current / likely actual behavior.** The arithmetic path treats `zero hundred` as 100 and `zero thousand` as 1000. A malformed sequence such as `one thousand million` is accumulated as 1,001,000 rather than rejected. The narrow quantified-scale guard also needs `a few hundred thousand dollars` and analogous multi-token scales challenged.

**Failure mechanism.** Using `(current or 1)` conflates explicit zero with absence of a multiplier. Scale transitions lack a complete validity check for repeated/increasing scales. The historical prose guard is local rather than a whole-quantity ownership rule.

**Minimal reproduction.** Normalize `zero hundred dollars`, `zero thousand dollars`, `one thousand million dollars`, `one million million dollars`, and `a few hundred thousand dollars`.

**Expected behavior.** Unsupported or malformed constructions stay literal/rejected as a whole. Explicit zero must never become a positive scale. Quantified prose must not acquire an exact amount ledger solely because a numeric suffix is parseable.

**Existing test coverage.** The existing review regressions cover short phrases such as a few hundred and several thousand. Normal scale positives and a hundred people do not challenge explicit zero versus implicit one.

**Why the existing oracle misses it.** Expected outputs for well-formed scales cannot validate the state machine. Local blocker-word examples do not establish closure over compound scales.

**Regression recommendation.** Mutate every supported scale with explicit zero, duplicate scales, reversed scale order, an intervening and, and quantifiers few/several/some. Preserve one hundred and five, twelve thousand dollars, and ordinary around/about quantities with their qualifiers intact.

**Narrow repair direction.** Track multiplier-present separately from its numeric value; enforce a declared scale grammar. Protect the maximal invalid/approximate quantity rather than applying a supported suffix.

**Downstream impact.** Incorrect quantities enter M07 as accepted source text and poison numeric-fidelity evidence for M15. Do not implement new large-number grammar merely to make malformed tests pass.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_numbers.py`

### M04-AUDIT-05 — Signed text and typed evidence disagree; a negative port can be accepted

**Severity:** HIGH  
**Confidence:** High  
**Category:** Sign, typed metadata and domain bounds  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 exact signs/values/units; normalization contract port range 1–65535; S29.4 exact typed evidence.

**Code location.** `localflow/v2/normalize/numbers.py — grammar_anchored_integer, grammar_port, grammar_dimension`

**Current / likely actual behavior.** Source predicts `step negative five` rendered with -5 but an anchored-integer value of +5. `port negative eighty` can emit `port -80` while its typed value is 80. A signed second dimension is rendered with its sign but its composite value omits that sign.

**Failure mechanism.** The parser stores magnitude and sign separately. Several consumers validate/serialize pn.value without composing pn.sign, although their formatter does compose it. Port bounds consequently validate a different value from the one emitted.

**Minimal reproduction.** Inspect text AND all typed edits for `step negative five`, `port negative eighty`, and `ten by minus twenty centimeters`.

**Expected behavior.** Every signed field must agree with displayed semantics. Invalid signed ports stay literal/reviewed, not accepted as a valid positive port. Domain-specific refusal is preferable to silently deleting a sign.

**Existing test coverage.** Port fixtures only cover valid positive 80 and 8000. General negative decimal fixtures do not exercise anchored integers, ports or the second dimension.

**Why the existing oracle misses it.** Exact output alone can pass with wrong typed metadata. A range check on the magnitude looks valid unless the emitted value is checked separately.

**Regression recommendation.** Use independently authored typed tuples: anchored value -5, invalid port -80, dimension components [10,-20] if signed dimensions remain supported. Include 0,1,65535,65536, plus/minus variants and both dimension positions.

**Narrow repair direction.** Centralize signed-value composition before validation and evidence serialization. Keep formatting, domain validity and typed identity consistent without expanding supported units.

**Downstream impact.** M14/M15 can misclassify value changes or score invalid output as correct if they trust the unsigned ledger. A faithful replay does not validate the sign.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

### M04-AUDIT-06 — Time ownership steals count-plus-duration prose

**Severity:** HIGH  
**Confidence:** High  
**Category:** Time versus quantity intent  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 no invented time meaning; M04 historical unanchored-time repair; M04-AC01 and negative controls.

**Code location.** `localflow/v2/normalize/numbers.py — grammar_time`; `tests/v2/normalization/test_normalize_numbers.py — time regression`

**Current / likely actual behavior.** At utterance start, `three fifteen minute breaks` can become `3:15 minute breaks`, and `one twenty minute session` can become `1:20 minute session`. These lose the intended count/duration structure.

**Failure mechanism.** Time recognition accepts utterance start or a broad previous-word anchor. It does not require the following phrase to remain compatible with time-of-day intent. Earlier chapter guards therefore do not close this ordinary-language pattern.

**Minimal reproduction.** Normalize the two phrases above, then compare with `at five thirty`, `five thirty PM`, and `at nine oh five am`.

**Expected behavior.** No time edit for the count-plus-duration readings. Keeping the phrase literal is acceptable; a separately valid quantity representation is acceptable only if it preserves the count and duration.

**Existing test coverage.** The earlier chapter/section regression rejects a particular time-looking substring; canonical anchored and meridiem positives are present.

**Why the existing oracle misses it.** Not containing `5:3` is not an oracle for preservation of all non-time prose. It misses other hours/minutes and can pass after a different destructive rewrite.

**Regression recommendation.** Cross hours/minutes with following units/nouns, utterance-start versus mid-sentence context, chapters/sections, and supplied/absent AM/PM. Assert no time-class edit for negatives.

**Narrow repair direction.** Use bounded, explicit evidence for time ownership and reject incompatible continuations. Preserve supported bare intended times through declared policy/intent rules rather than disabling the family.

**Downstream impact.** M07 receives an already precise time string, and typed evidence may incorrectly certify a time that was never spoken.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_numbers.py`

### M04-AUDIT-07 — Date recognition changes modal May and falls back inside invalid compound ordinals

**Severity:** HIGH  
**Confidence:** High  
**Category:** Date ownership and partial invalid parsing  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 unambiguous dates, ordinary content preservation; M04-AC01; invalid-date negative controls.

**Code location.** `localflow/v2/normalize/numbers.py — grammar_date, _date_parse and year attachment`; `tests/v2/normalization/fixtures_numeric.json — LF-NUM-033, 036`

**Current / likely actual behavior.** Source predicts `this may first require approval` → `this May 1 require approval`. `March thirty second` can produce `March 30 second`: an invalid compound ordinal is reduced to a valid shorter date.

**Failure mechanism.** Month-name matching is case-folded and not separated from modal may. When the tens-plus-ordinal day is invalid, parsing can fall back to a cardinal prefix instead of rejecting the whole day expression.

**Minimal reproduction.** Normalize those phrases plus `March thirty two is invalid`, `May first`, and `September twenty fifth`.

**Expected behavior.** Keep modal may prose literal. Reject an invalid compound day as a whole. Preserve valid month/day positives and never resolve ambiguous numeric dates such as 03/04.

**Existing test coverage.** The existing invalid-day fixture covers cardinal thirty two, not ordinal thirty second. Valid date cases do not contrast modal may with the month name.

**Why the existing oracle misses it.** One spelling of an invalid day is insufficient when cardinal and ordinal parsing take different branches.

**Regression recommendation.** Cross cardinal/ordinal days at 28–32, month case and prose continuations; include may first require, may second-guess, valid May first, and terminal versus nonterminal year speech.

**Narrow repair direction.** Prevent fallback from a recognized invalid compound day to its shorter prefix; require credible date ownership for ambiguous month words. Full calendar validation is a separately adjudicated design concern, not automatic feature expansion.

**Downstream impact.** Dates can change instructions and deadlines before cleanup. Exact source spans and rejection reasons must preserve the original for M14/M15 review.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_numeric.json`

### M04-AUDIT-08 — Malformed structured phrases can be partially normalized as valid suffixes or prefixes

**Severity:** HIGH  
**Confidence:** High for the identified control flow; exact rendered variants require runtime checks  
**Category:** Maximal-span ownership  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 separate decimal/version/IP grammars; invalid octets stay flagged; M04-AC01/AC06; safe unsupported behavior.

**Code location.** `localflow/v2/normalize/numbers.py — grammar_decimal, grammar_version, grammar_ip`; `localflow/v2/normalize/engine.py — review_regions containment and overlap arbitration`

**Current / likely actual behavior.** An unanchored `one point twenty six point four` can yield `one point 26.4`. A five-component `one dot two dot three dot four dot five` admits a valid four-octet prefix proposal instead of rejecting the full candidate; likely output is `1.2.3.4 dot five`. Leading `point five percent` also needs whole-span refusal tested rather than conversion of only five.

**Failure mechanism.** Candidate generators start at multiple positions and some stop after the accepted arity. Rejection regions only block candidates contained within their spans. A failed enclosing parse does not consistently own the whole structured-looking expression.

**Minimal reproduction.** Normalize the three phrases above and print accepted/rejected spans. Repeat IP arity 3/4/5, invalid octets, version separators and component spellings.

**Expected behavior.** Unanchored multi-component versions and malformed IP candidates remain literal/reviewed as a whole. A leading decimal must not become five percent through a supported suffix. Canonical anchored versions and four-octet addresses must continue working.

**Existing test coverage.** LF-NUM-059 covers only digit-spoken multi-component version syntax; LF-NUM-065 covers an out-of-range octet in a four-component candidate. Neither establishes maximal ownership for different arities/spellings.

**Why the existing oracle misses it.** Examples chosen to hit a specific rejection branch cannot show that another grammar cannot steal a suffix. Same-normalizer replay reproduces the mistake faithfully.

**Regression recommendation.** Mutate every component, separator and arity; independently check tuples [1,26,4] and [192,168,1,10]. Reject illegal whole candidates, not just a forbidden final string. Test incomplete endpoints and lookahead-limit boundaries.

**Narrow repair direction.** Identify the maximal structured candidate first and preserve its invalid/ambiguous ownership across component grammars. Keep precedence-aware exceptions for genuinely valid anchored versions; do not blanket-block every overlap.

**Downstream impact.** Technical identifiers and network addresses can be silently changed before M07/M10. M15 needs valid/invalid structured-value oracles independent of formatter output.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

### M04-AUDIT-09 — Punctuation blocker lists still rewrite ordinary nouns and descriptions

**Severity:** HIGH  
**Confidence:** High  
**Category:** Spoken syntax false positives  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 punctuation names are commands only in the selected formatting context; ordinary names remain phrases. M04-AC02/AC06.

**Code location.** `localflow/v2/normalize/policies/number_profiles.json — symbols and prose blockers`; `localflow/v2/normalize/syntax.py — grammar_symbols, grammar_flags`

**Current / likely actual behavior.** Source predicts `period drama` → `. drama`, `time period` → `time.`, `colon cancer` → `: cancer`, and `pipe tobacco` → `| tobacco`. Unguarded compound command names such as `a question mark` or `the forward slash character` are further candidates.

**Failure mechanism.** The historic period fix checks selected preceding/following words. It does not establish positive command intent. Several multiword commands bypass the guarded-name list entirely; single-letter flag parsing can also interpret the pronoun I after dash as a flag.

**Minimal reproduction.** Normalize each phrase above under technical and standard; also probe `dash I asked him` versus `grep dash i pattern files`.

**Expected behavior.** Preserve the noun/verb/descriptive readings. Keep canonical intended punctuation such as `hello comma how are you`, `stop period`, and an explicit flag command working.

**Existing test coverage.** Current tests pin grace/trial/fourth period, period of adjustment, dash cam and dash of salt. The negative corpus is real but structurally narrow.

**Why the existing oracle misses it.** A finite blocker list can pass all known examples while the same structural error persists with a new noun compound. Standard inherits most symbol rules.

**Regression recommendation.** Build ordinary-language negatives for every registered punctuation command, including compound names, singular/plural, quotation and determiners. Pair each with an owned positive and inspect class/operation, not only text.

**Narrow repair direction.** Base interpretation on explicit formatting intent or conservative owned contexts. Do not repair solely by adding these specific nouns to another growing blacklist.

**Downstream impact.** Changes ordinary prose and punctuation scope before cleanup. M14 should attribute a correction to normalization, not teach an acoustic alias.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policies/number_profiles.json`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

### M04-AUDIT-10 — Literal escape scope can expire or be reinterpreted inside its own payload

**Severity:** HIGH  
**Confidence:** High for bounded scope; nested-output reproduction required  
**Category:** Literal and quoted protection  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 explicit literal escape is highest precedence; quoted instructions remain content; M04-AC02/AC03.

**Code location.** `localflow/v2/normalize/syntax.py — find_literal_escapes, quote zones, _ESCAPE_MAX_WORDS`; `localflow/v2/normalize/engine.py — literal_escape handling`

**Current / likely actual behavior.** A `write the phrase` payload longer than twelve word tokens loses protection beyond the cap even though the marker is removed. A trailing command word can then be normalized. An inner `write the word` marker can also be processed inside an already escaped outer phrase.

**Failure mechanism.** The escape scan caps protection at twelve tokens rather than refusing an oversized literal as one unit. Escapes are collected independently, and literal_escape proposals bypass the protection rejection used for other grammars.

**Minimal reproduction.** Normalize `write the phrase ` + "alpha "*12 + `period`. Also probe `write the phrase please write the word comma`; the source predicts removal of the inner marker, leaving `please comma` rather than its literal words.

**Expected behavior.** No unprotected tail or nested reinterpretation of a literal payload. Either preserve the complete requested literal output or reject the whole unsupported escape without dropping its marker. Backtick/code-fence protection needs a separate regression, not an assumption.

**Existing test coverage.** The fixtures exercise short literals, quoted markers, and two explicitly non-idempotent emitted command cases. They do not cover cap+1 or nested markers.

**Why the existing oracle misses it.** A short escape passing says nothing about the exact position where protection stops. Testing only a second pass also misses corruption within the first pass.

**Regression recommendation.** Test 11/12/13+ word payloads, nested markers, punctuation boundaries, smart quotes, code fences and quoted identifiers. Assert highest-precedence ownership and retained output exactly.

**Narrow repair direction.** Make literal regions structurally owned before generating nested proposals. Any processing bound must fail closed for the whole literal, not silently expose a suffix.

**Downstream impact.** M05/M10 aliases and commands inside literal text become especially risky. M07 must receive correct protected regions; its existing safeguards must not be weakened.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

### M04-AUDIT-11 — Spoken paths lower-case user components and accept unsupported chain prefixes

**Severity:** HIGH  
**Confidence:** High  
**Category:** Technical literal integrity  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 paths preserve spaces, case, extensions and dotfiles; no invented or altered technical identifiers. M04-AC01/AC02.

**Code location.** `localflow/v2/normalize/syntax.py — grammar_spoken_path, grammar_domain_email`; `tests/v2/normalization/fixtures_syntax.json — LF-SYN-052`

**Current / likely actual behavior.** Source predicts `path slash Users slash Ada slash MyProject` → `/users/ada/myproject`. A chain ending in an unsupported token such as build2 may be emitted only through an earlier prefix, leaving a mixed path/spoken tail.

**Failure mechanism.** Path components are assembled from Token.word, which is lower-cased for matching, instead of the original token spelling. The parser can stop on an unsupported component yet still accept accumulated segments.

**Minimal reproduction.** Normalize that mixed-case path and `path slash Users slash Ada slash build2`. Include existing `/Users/Ada/MyProject` as an unchanged control.

**Expected behavior.** Preserve exact component case. An unsupported candidate must not be partially reformatted into a misleading hybrid; retain or explicitly reject it. Do not assume a particular destination filesystem is case-insensitive.

**Existing test coverage.** Current spoken path fixtures are all lower-case, while mixed-case fixtures are already-written paths that bypass this grammar.

**Why the existing oracle misses it.** Case sensitivity is never exercised on the branch that constructs paths. Already-written literal preservation does not validate spoken path construction.

**Regression recommendation.** Cross case, spaces, dots, digits, underscores, leading/trailing separators and benign wrappers. For email local parts, separately adjudicate whether case is preserved; do not conflate domain case equivalence with path or local-part spelling.

**Narrow repair direction.** Use original lexical core text for literal components. Require complete ownership of the intended chain or reject it, without inventing new filesystem lookup behavior.

**Downstream impact.** Wrong paths may be preserved as authoritative literals by M07 and later copied into developer tools. No actual filesystem execution occurs in this grammar.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/fixtures_syntax.json`

### M04-AUDIT-12 — A policy revision does not identify immutable runtime policy contents

**Severity:** HIGH  
**Confidence:** High  
**Category:** Determinism and provenance  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** M04 immutable NormalizationPolicy and stable ContextSnapshot; S29.4 actual policy revision; P02 deterministic contracts.

**Code location.** `localflow/v2/normalize/policy.py — load_profiles, NormalizationPolicy, LocaleTables construction, profile_table`; `localflow/v2/normalize/policies/number_profiles.json`

**Current / likely actual behavior.** Nested numeric/symbol tables remain mutable after revision computation. Changing a nested entry can change normalization output without changing an existing policy object's revision. Cached shared tables can expose later policies to the same mutation.

**Failure mechanism.** A read-only outer MappingProxyType is not a deep freeze. Locale table objects and nested profile collections are shared mutable state; policy attributes also are not an enforced immutable snapshot.

**Minimal reproduction.** In an isolated process, create p=NormalizationPolicy(); save p.policy_revision; set p.tables.teens["twelve"]=13; normalize("twelve percent",p); compare revision and output. Restore nothing by guess: isolate the process because tables are cached. Also probe a nested symbol mapping.

**Expected behavior.** The snapshot either rejects mutation or produces a distinct immutable policy with a new revision. Historical and in-flight jobs must not observe changed behavior under the old identity.

**Existing test coverage.** Canonical-content hashing and profile validation are tested, but formatting/order hash tests do not prove the hashed object stays unchanged.

**Why the existing oracle misses it.** A test that hashes immediately after construction cannot detect later nested mutation. Rebuilding a new policy and rehashing it is not the same scenario as using the old job object.

**Regression recommendation.** Deep mutation attempts on every nested table, caller-owned dictionaries, constructor inputs and context identifiers; verify old-object outputs/revisions remain stable and new semantic revisions differ. Reorder equivalent dictionaries to preserve canonical identity.

**Narrow repair direction.** Deep-copy and freeze the entire effective policy graph, including inherited profile values. Avoid a mutable exported cache. Snapshot each behavior-affecting context dependency or record it separately with immutable identity.

**Downstream impact.** M05/M06 per-job snapshots and M15 reproducibility depend on this. A correct edit ledger can replay an output, but cannot prove which mutable policy produced it.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policy.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policies/number_profiles.json`

### M04-AUDIT-13 — A previous job’s style override can become the next job’s inherited normalization default

**Severity:** HIGH  
**Confidence:** High for source path; portable coordinator reproduction required  
**Category:** Profile isolation at the M04 integration boundary  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** profiles.md: winning style number policy overrides configuration FOR THAT JOB; inherit uses configuration default. S10 per-job normalization policy.

**Code location.** `localflow/app.py — _vocab_job_state, _finalized_policy, _m10_finalize_upgrade`; `docs/v2/contracts/profiles.md — modes and style attributes`

**Current / likely actual behavior.** The app caches an effective standard/technical policy in self._norm_policy, then uses that same object as the base for a later inherit job. The later job can inherit the preceding style override rather than the configured default.

**Failure mechanism.** _vocab_job_state starts from self._norm_policy, computes explicit style policy or policy.profile, and writes the rebuilt job-effective policy back to self._norm_policy. Finalization repairs explicit overrides but does not restore the configuration default for inherit.

**Minimal reproduction.** Portable coordinator seam: configured technical → job A explicit standard → job B inherit/no rule. Assert B.profile is technical; reverse the sequence with configured standard and an explicit technical job. Use `twelve retries failed` as a designated bare-integer contrast.

**Expected behavior.** Each job resolves inherit against the stable configured base, independently of the prior job, cache hit/miss or destination context availability.

**Existing test coverage.** Current M04 pipeline tests cover profile off and normalization exceptions, not sequential style overrides followed by inherit. M10 tests need targeted compatibility, not a broad re-audit.

**Why the existing oracle misses it.** A single-job profile test cannot reveal state leakage. A populated destination snapshot can conceal some explicit-profile errors, not inheritance from the wrong base.

**Regression recommendation.** Cross configured technical/standard, explicit A profile, inherited B profile, cache hit/miss and available/missing context; verify actual policy revision and recorded profile match. Keep registries scoped per job.

**Narrow repair direction.** Separate the immutable configured base from cached effective job policies. Preserve M05/M10 registry interfaces and finalization semantics.

**Downstream impact.** M06/M10 choose the context but the defect is the policy delivered to M04. It can enable unexpected rewriting under a standard default. Do not re-open unrelated M10 behavior.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/profiles.md`

## Medium Findings

### M04-AUDIT-14 — Same-output same-span arbitration can lose higher-priority ownership

**Severity:** MEDIUM  
**Confidence:** Medium-high; constructed composition must be executed before repair  
**Category:** Span arbitration and metadata identity  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S10 explicit precedence; same-span conflicts use scope and layer, not incidental class names.

**Code location.** `localflow/v2/normalize/engine.py — same-span grouping and greedy overlap arbitration`; `localflow/v2/normalize/syntax.py — grammar_skills, grammar_identifiers, grammar_symbols`

**Current / likely actual behavior.** When same-span outputs differ, the engine considers precedence. When outputs agree, the tie-breaker can choose a lower-layer class instead. A later overlapping proposal can then beat the selected representative, even though it should lose to the discarded higher-priority owner.

**Failure mechanism.** Equal strings are treated as interchangeable evidence. Sorting by unit presence/class name can replace a layer-3 owner with a layer-5 owner; layer-4 overlap arbitration subsequently sees the wrong priority.

**Minimal reproduction.** Construct registered_skills={"period":"period"} and ContextSnapshot(identifiers={"slash period":"/period"}); normalize `slash period`. Inspect equal-output skill/identifier selection and overlapping period symbol. Also directly test proposal sets with equal text but differing typed value/unit/layer.

**Expected behavior.** Identical output must retain the strongest legitimate ownership and coherent provenance. Different typed semantics are not automatically equivalent just because text matches.

**Existing test coverage.** Existing same-span tests cover different outputs and documented layer precedence, not the interaction of equal-output representatives with a third overlapping proposal.

**Why the existing oracle misses it.** The final string in a two-proposal test can be correct even when the retained class/layer is wrong; only composition exposes the regression.

**Regression recommendation.** Permute proposal ordering; compare equal-text/different-layer, equal-text/different-value, same-layer conflicting output, nested and adjacent proposals. Include the three-proposal composition above.

**Narrow repair direction.** Apply explicit precedence to all same-span groups, including equal-output groups; preserve or reject incompatible typed metadata rather than choosing it by class-name order.

**Downstream impact.** M05 identifiers and M10 skills/snippets compose through this shared M04 arbiter. Repair it without changing legitimate snippet-over-vocabulary precedence.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

### M04-AUDIT-15 — Idempotence exceptions extend beyond the two documented literal fixtures

**Severity:** MEDIUM  
**Confidence:** High for identifier no-op edit path  
**Category:** Idempotence and evidence honesty  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** M04-AC03: identical second output AND empty second ledger; documented exceptions must be bounded.

**Code location.** `localflow/v2/normalize/syntax.py — grammar_identifiers`; `localflow/v2/normalize/span_types.py — NormalizationResult.is_idempotent`; `localflow/v2/training.py — on_normalization_result`

**Current / likely actual behavior.** With identifiers={"user id":"user ID"}, the second normalization can produce an identifier edit whose input and output are already identical. Text is stable, but the second ledger is not empty. Snippet-generated command words also broaden the set of second-pass behaviors needing explicit scope.

**Failure mechanism.** The context identifier grammar does not consistently discard already-canonical no-op matches. The idempotence oracle correctly requires no edits, but fixture exception flags and narrow contexts do not exhaust current composition cases.

**Minimal reproduction.** ctx=ContextSnapshot(identifiers={"user id":"user ID"}); a=normalize("user id",p,ctx); b=normalize(a.text,p,ctx); inspect b.text and b.edits. Run the same context through is_idempotent.

**Expected behavior.** Canonical identifiers generate no new edit on a second pass. Intentional literal/snippet exceptions must be explicitly recorded without calling them safe merely because the old two cases were documented.

**Existing test coverage.** LF-NUM-078 uses userId, whose token shape differs from its alias. LF-SYN-003/005 are marked exceptions; most fixtures have no live context.

**Why the existing oracle misses it.** An alias that becomes a distinct single token stops matching, hiding the no-op path of a canonical form that still matches the alias words.

**Regression recommendation.** Canonical-case variants, same-word-count canonical forms, snippet outputs containing command words, and an exact exception allowlist with asserted expected false/true results. Require an empty second ledger except adjudicated exceptions.

**Narrow repair direction.** Suppress semantically and textually no-op proposals at the owning grammar/arbiter. Keep diagnostic second passes separate from applied output; do not feed normalized text through M04 again to work around the problem.

**Downstream impact.** The inspected coordinator applies M04 once to raw ASR. The collector and preview perform a diagnostic second evaluation, not a second insertion. Global retry/history/Scratchpad no-double-apply coverage remains a test obligation, not a proven runtime corruption claim.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/span_types.py`

### M04-AUDIT-16 — Normalization evidence-write failures are swallowed without a stage-specific failure record

**Severity:** MEDIUM  
**Confidence:** High for the collector path  
**Category:** Failure visibility and evidence completeness  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** S29.4/29.16 actual retained inputs and honest missingness; ordinary dictation continues on evidence failure.

**Code location.** `localflow/v2/training.py — EvidenceCollector.on_normalization_result`; `localflow/app.py — _worker collector call and exception handler`

**Current / likely actual behavior.** A normalized-text, ledger or lease write exception is caught by an unconditional return inside the collector. The caller’s error handler never observes it. Dictation continues, but this hook emits no normalization-specific retention-failure reason/event.

**Failure mechanism.** The try block wraps several separately committed writes; its except branch returns before assigning ctx.normalization. It neither distinguishes not-run from ran-but-not-retained nor reports which publication step failed.

**Minimal reproduction.** Inject one failure at each write_text_artifact/grant_lease call in on_normalization_result. Assert dictation still yields the normalized output and inspect events, artifact references, missing reasons and final envelope. Exact final-envelope fallback reason requires runtime verification.

**Expected behavior.** Continue dictation while recording a content-free failure stage/reason and trustworthy artifact completeness. Never fabricate a successful ledger or expose partial orphan references as complete evidence.

**Existing test coverage.** Current pipeline suite tests normal collection and parser failure, not each normalization-artifact publication failure.

**Why the existing oracle misses it.** An outer catch does not cover an inner catch that returns normally. A not-captured slot alone cannot distinguish a skipped stage from a failed retention attempt.

**Regression recommendation.** Fail first text write, its lease, ledger write and ledger lease separately; verify retained references, counts, privacy, replay eligibility and emitted error. Include collection off and no-edit normalizations.

**Narrow repair direction.** Expose structured retention status from the collector or emit its own content-free event; mark partial publication honestly using existing store/lease conventions. Do not redo M02 consent/transaction architecture.

**Downstream impact.** M14 origin attribution and M15 replay become incomplete without an explanation. Preserve availability and all accepted M01/M02 privacy barriers.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/training.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

## Low Findings

### M04-AUDIT-17 — The result’s internal duration excludes application/assembly work

**Severity:** LOW  
**Confidence:** High  
**Category:** Timing field semantics  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** E06/S24 stage timing must name what is measured; no speed claim from partial work.

**Code location.** `localflow/v2/normalize/engine.py — final result construction and _apply`; `scripts/v2/benchmark_m04.py — external timing`; `localflow/app.py — external normalization-stage timer`

**Current / likely actual behavior.** The engine records duration before _apply assembles the final text/ledger. The live coordinator and benchmark use an external timer and do include that work.

**Failure mechanism.** The duration argument is evaluated before the function that applies edits completes, so the result field is a partial-stage duration.

**Minimal reproduction.** Compare result.duration_ms with an external monotonic measurement on a dense, long edit workload. No timing run was performed in this audit.

**Expected behavior.** Either measure the complete API stage or name/document the field as partial work. Do not relabel historical external benchmark results as affected.

**Existing test coverage.** Benchmark exercises the complete call but does not reconcile its timing with result.duration_ms.

**Why the existing oracle misses it.** A correct external budget test can coexist with misleading per-result telemetry.

**Regression recommendation.** Instrument or inject bounded assembly delay and assert the reported duration includes it; keep external full-call benchmark as the independent budget oracle.

**Narrow repair direction.** Set complete-stage duration after assembly, or explicitly split named timing fields without double-counting.

**Downstream impact.** M13/M15 consumers should not confuse the internal field with end-to-end or full normalization timing.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/scripts/v2/benchmark_m04.py`

## Test Gaps

### M04-AUDIT-18 — Fixture success does not independently establish typed semantics or broad negative coverage

**Severity:** TEST GAP  
**Confidence:** High  
**Category:** False-green semantic oracle  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** EV-06, E06/E09 typed value/sign/unit versus display, M04-AC01/AC03/AC06.

**Code location.** `tests/v2/normalization/test_normalize_numbers.py`; `tests/v2/normalization/test_normalize_syntax.py`; `tests/v2/normalization/test_short_command_scoring.py`; `tests/v2/normalization/fixtures_numeric.json`; `tests/v2/normalization/fixtures_syntax.json`

**Current / likely actual behavior.** The suites assert nonzero/exact populations and many useful exact outputs, but most fixture protected_values are not checked by a general independent typed oracle. The time negative is substring-based and idempotence_expected=false can exempt cases without an enforced fixed exception inventory.

**Failure mechanism.** Formatting, semantic identity, intent and idempotence are sampled separately instead of cross-checked on every applicable case. Negative fixtures often omit the conflicting registry/grammar context.

**Minimal reproduction.** Mutate only an emitted typed sign/value while leaving text unchanged; run the existing numeric suite. Substitute a different destructive time-like output not containing the forbidden substring. Add an unjustified idempotence exception flag. Confirm which checks actually fail.

**Expected behavior.** The suite must fail each semantic/oracle mutation, while preserving positive supported forms. Exact fixture counts remain useful but are not the quality denominator.

**Existing test coverage.** 80 numeric + 60 syntax fixtures, 24 short-command cases (16 command,8 non-command), standalone regression functions and independent edit replay are present.

**Why the existing oracle misses it.** A claimed 140-fixture pass can be true while these unsampled invariants fail. These are authored development regressions, not demonstrated untouched holdout validation.

**Regression recommendation.** Validate typed class/value/sign/unit/component tuples independently; schema-check fixtures, IDs, tags, expected exceptions, negative contexts and their match populations. Keep intended-written and verbatim references distinct.

**Narrow repair direction.** Strengthen oracles alongside each production fix. Freeze a new challenge set before repair; log every case later used for tuning as exposed development evidence.

**Downstream impact.** M15 must score representation, lexical ASR, technical tokens and false commands separately. Do not claim real-world error rates from this hand-authored corpus.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_numbers.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_syntax.py`

### M04-AUDIT-19 — AC04 is no longer vacuous but does not certify the whole reachable normalization boundary

**Severity:** TEST GAP  
**Confidence:** High  
**Category:** No-execution static/runtime oracle  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** M04-AC04: no execution, Enter/send, network or plugin invocation caused by normalization.

**Code location.** `tests/v2/normalization/test_normalize_syntax.py — AC04 scanner`; `localflow/v2/normalize/syntax.py — snippets and file-resolver integration`; `localflow/v2/snippets.py — expand and split_slots`

**Current / likely actual behavior.** The current scanner checks an existing root and at least seven Python modules: the historical wrong-path defect is repaired. However, a top-level glob and token/attribute checks do not cover every newly nested module or every transitive helper/callback.

**Failure mechanism.** Population assertions protect today’s root, not automatically the import/call closure. Substring/token scans also cannot distinguish harmless documentation from an aliased execution path in general.

**Minimal reproduction.** In an isolated test fixture, add a nested normalization helper or transitive alias path to a forbidden API without executing it, and verify the scanner detects the intended source population. Include harmless comment/string references as controls.

**Expected behavior.** Fail a scanner that sees zero or incomplete intended modules; inspect reachable production collaborators and assert that text generation does not trigger execution capabilities.

**Existing test coverage.** Current positive source count, banned-token checks and direct-module checks are genuine improvements. Reviewed normalizer/expansion code shows text processing, not an execution path.

**Why the existing oracle misses it.** No actual command-execution defect was found. A green heuristic scanner is not a proof that arbitrary injected resolver objects are pure.

**Regression recommendation.** Recursive source inventory, AST import/call analysis where useful, concrete collaborator capability tests, and a dependency-boundary test that fails when new files join the normalization boundary without review.

**Narrow repair direction.** Keep a small explicit capability boundary and test it. Do not respond by removing legitimate pure snippet/file-tag composition or by executing dictated commands in tests.

**Downstream impact.** M05/M10 integrations must remain text emission only. This gap does not justify calling the current implementation an RCE vulnerability.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_normalize_syntax.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/syntax.py`

### M04-AUDIT-20 — The benchmark can report a green budget after normalization is reduced to no-op work

**Severity:** TEST GAP  
**Confidence:** High  
**Category:** Benchmark workload and performance oracle  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** M04-AC performance p95 ≤25 ms at 500 words; E06/E11 cohort/build/failure transparency.

**Code location.** `scripts/v2/benchmark_m04.py`

**Current / likely actual behavior.** The benchmark times the actual normalize call and exits nonzero when its main long-input p95 exceeds the budget. Its per-call validity assertion is only nonempty output, so an identity normalizer can satisfy it without applying owned edits.

**Failure mechanism.** The constructed corpus has intended matches but the harness does not assert observed edit classes/counts. A no-match cohort is reported without the same explicit budget gate. Build SHA and distinct case/work counts are not fully carried by the report.

**Minimal reproduction.** Replace normalize only in a controlled harness test with an identity result whose text is nonempty. The workload-validity check should fail independently of runtime speed. Also force slow matched and no-match calls to test exit semantics.

**Expected behavior.** Budget success requires both legitimate work and acceptable time; never report zero-work speed as normalization performance. State actual word counts, edit populations and environment.

**Existing test coverage.** The existing exit gate and external wall-clock timer are real strengths. Historical Mac timings in results.json are not current measurements.

**Why the existing oracle misses it.** Input construction and nonempty output do not establish positive semantic work. Testing only the matched budget does not cover pathological negative candidates.

**Regression recommendation.** Assert multiple owned classes, minimum nonzero edits, unchanged no-match controls, exact constructed word counts and failures. Add dense overlaps, thousands of number words, repeated point, command-word runs and long identifiers.

**Narrow repair direction.** Harden the harness; measure scaling and full-call quantiles. Keep reference-Mac certification separate from portable algorithmic comparisons and preserve historical reports.

**Downstream impact.** M13/M15 performance claims must not trade semantics for a fast no-op. No new cloud or Mac timing was measured here.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/scripts/v2/benchmark_m04.py`

### M04-AUDIT-21 — Global retry/caller and historical-policy reconstruction guarantees remain unclosed

**Severity:** TEST GAP  
**Confidence:** High that coverage is incomplete; no unsupported runtime defect asserted  
**Category:** Audit boundary and provenance verification  
**Execution status:** SOURCE_REVIEWED_RUNTIME_NOT_RUN

**Canonical requirement.** M04 raw-ASR-only application, S29 actual policy/context provenance, attempt-aware immutable evidence, AC03/AC05.

**Code location.** `localflow/app.py — _worker, capture/finalization, transform seam`; `localflow/v2/normalize/__init__.py — preview_phrase`; `localflow/v2/training.py — on_normalization_result`; `docs/v2/contracts/jobs.md`; `docs/v2/contracts/training_evidence.md`

**Current / likely actual behavior.** The inspected live coordinator applies M04 once to raw ASR and passes normalized output to cleanup. Preview and evidence intentionally evaluate a second pass diagnostically. This session did not establish an exhaustive repository-wide caller inventory or execute every recovery/history/Scratchpad retry path.

**Failure mechanism.** Connected code search was incomplete/empty despite known matches, so its results cannot prove absence. The ledger records edits and policy revision; a revision is not itself a serialized policy. Full historical regeneration requires verification of the surrounding snapshot/artifact machinery.

**Minimal reproduction.** In the cloud checkout, inventory every normalize/preview/replay caller, then change policy/registry between capture, ASR, cleanup retry, manual retry and recovery. Inspect actual input source, attempt identity and retained policy/context artifacts.

**Expected behavior.** No applied second pass over normalized output. Retries either reuse the recorded snapshot or declare a new attempt/snapshot honestly. Ledger replay must work from retained raw+edits; policy regeneration must use retained exact policy/context or report unavailable.

**Existing test coverage.** The real coordinator seam test and independent edit replay cover the ordinary path. Accepted M03 attempt repairs are inherited and are not re-audited here.

**Why the existing oracle misses it.** A global negative claim would exceed the evidence obtained in this session. Successful ledger replay does not prove full policy regeneration or safe retry provenance.

**Regression recommendation.** Add a caller inventory and portable seam matrix for live, automatic retry, manual retry, crash recovery, History, transform and Scratchpad paths. Check old ledger/history survives with correct identity when recomputed.

**Narrow repair direction.** Close the tests and provenance inventory first; change production only for reproduced M04-specific violations. Do not redesign M03 lifecycle or M14/M15.

**Downstream impact.** This is a specific remaining proof obligation, not a claim that M03/M07/M11 remediations are absent or broken.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/__init__.py`

## Design Concerns

**D1 — Calendar validity and typed time identity.** The present date contract limits validation to day range; it does not implement a full leap-year/month-length validator. The audit brief also says not to expand calendar scope casually. Reconcile those facts explicitly: either reject known impossible complete candidates narrowly or record the parsed-but-not-calendar-validated boundary so downstream evidence does not certify it as a real date. Do not introduce date expansion, regional guessing or timezone inference. Similarly, define typed time components and supplied/unknown meridiem rather than comparing a clock string and a fixture’s 24-hour string as though their schemas were identical.

**D2 — Intent cannot be inferred solely from a matching surface.** The same words can be an intended `/code-review` insertion or an ordinary instruction to reduce code-review time. A deterministic system needs a declared conservative ownership/escape policy, not a promise that a keyword list can infer every speaker intention. This does not authorize an extra model call on every dictation, a broad disable switch disguised as a repair, or a new user-confirmation workflow for all existing good cases. Preserve useful canonical cases and make ambiguity explicit.

**D3 — Edit replay versus policy regeneration.** These are separate capabilities. Retained raw+ledger can reproduce an output byte-for-byte independently of the parser. Regenerating the same proposals requires the actual policy tables, effective profile and contextual snapshots. A hash is an identity check, not the contents. Verify the latter retention graph before claiming it exists or is absent; when the graph is incomplete, state reconstruction limits rather than silently re-running current policy over historical text.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/normalization.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/LOCALFLOW_V2_SPEC.md#s10`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/docs/v2/contracts/artifacts.md`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/policy.py`

## Areas Verified Strong

These are **source-verified properties**, not newly measured acceptance passes:

The canonical foundation is current and inherits all three accepted remediation commits. Core normalization uses structured proposals with explicit layers and rejects some ambiguity rather than relying on last-write-wins replacements. Decimal arithmetic is used at the parser level, and percent versus percentage points plus MB versus Mb have distinct representations. Unknown profile/locale values fail explicitly; global off is a real bypass. Registered skills use exact aliases and do not themselves invoke skills. Raw ASR, normalized output and the edit ledger are separate governed artifacts. Replay uses positions and source-slice verification, including repeated-substring safety. The envelope’s selected-value allowlist prevents path/email/skill/identifier strings from being copied there as generic values. The real coordinator gives M04 raw ASR before cleanup and falls back to raw on parser error. Current fixtures, short-command denominators and AC04 source counts are nonzero and explicitly checked. The benchmark has a real external timer and a real main budget exit gate.

None of those strengths cancels a value/intent defect. They are interfaces and guarantees the remediation must preserve, not code to discard wholesale.

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/engine.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/normalize/span_types.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/v2/training.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/localflow/app.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/tests/v2/normalization/test_short_command_scoring.py`

**Source at audited SHA:** `https://github.com/scalinity/LocalFlow/blob/1c9d981b1505b6cd975ce6e701e0382c6db96c78/scripts/v2/benchmark_m04.py`

## Adversarial Corpus

The complete machine-readable corpus is `LocalFlow_M04_Adversarial_Corpus.json`. It contains **368 text cases, 171 text families and 10 stateful probes**:

| Role | Text cases |
| --- | --- |
| false_positive_control | 248 |
| positive_control | 50 |
| adversarial_probe | 44 |
| profile_relation | 18 |
| negative_control | 2 |
| design_probe | 6 |

The 248 false-positive controls include 60 ordinary-prose/technical-literal bases with orthographic/context wrappers and matched registry variants. They are **not 248 independent real-world utterances**. Stateful probes cover deep policy mutation, sequential profile inheritance, equal-output overlap, idempotence, retention failure, oracle mutation, scanner coverage, benchmark no-op work and retry provenance.

Each record names an oracle kind. `literal_exact` and supported positive controls have exact intended text. `intent_invariant` describes semantics that must survive and may require adjudication. `structured_or_literal` allows conservative whole-span refusal where support is not guaranteed but never permits a different structured value. `whole_literal_or_review` forbids partial ownership of an invalid expression. No oracle is generated by calling the production grammar. No corpus record contains runtime output or a claimed pass.

Representative pairs to prioritize:

| Family | Challenge | Independent expectation | Positive control |
| --- | --- | --- | --- |
| Slash intent | we should slash code review time | Keep ordinary prose with the same registered alias present | slash code review → /code-review |
| Boundary | twenty, five percent | Never collapse to 25%; preserve delimiter and distinct quantities | twelve percent → 12% |
| Scaled value | one point two three four five thousand dollars | Amount 1234.5, or whole literal; never 1234 | one point five million dollars → $1,500,000 |
| Time | three fifteen minute breaks | Three breaks of fifteen minutes, not 3:15 | at five thirty → at 5:30 |
| Date | this may first require approval | Modal may stays prose | September twenty fifth → September 25 |
| Invalid ordinal | March thirty second | Whole invalid candidate stays literal/reviewed | March thirty first → March 31 |
| IPv4 arity | one dot two dot three dot four dot five | No valid four-octet prefix emitted | ten dot zero dot zero dot one → 10.0.0.1 |
| Literal scope | write the phrase + 12 alpha words + period | No command conversion beyond protection cap | write the word slash → slash |
| Path case | path slash Users slash Ada slash MyProject | Preserve exact case or refuse whole candidate | path slash etc slash hosts → /etc/hosts |
| Typed sign | step negative five | Ledger and display both mean -5 | milestone fourteen → milestone 14 |

Additional corpus expansion during remediation should include every current symbol name, all scale/sign combinations, dates with invalid calendar components, digit/word component mixtures, quote boundaries, benign Unicode and lookahead-limit mutations. Any newly consulted challenge becomes exposed development evidence; keep the label honest.

## Metamorphic / Mutation Test Plan

**M1 — Structural wrappers.** Add punctuation, parentheses and quotes around valid owned quantities without changing their values; never allow a punctuation delimiter between components to be treated as numeric whitespace. Check exact source/output spans with repeated identical text and Unicode.

**M2 — Approximation.** Add about/roughly/approximately without losing the qualifier. Introduce few/several around a scale and require conservative quantified-region behavior. Do not assume every digit rendering makes an approximate statement exact.

**M3 — Profile relation.** Compare technical/standard/off on the same input. Only designated grammar switches should differ; dates/currency must not change unrelated semantics. Run sequential jobs to test inherit against configuration rather than the last effective cache.

**M4 — Immutable snapshots.** Reorder equivalent mappings and vary JSON formatting to preserve identity where canonicalization promises equivalence. A semantic table change must yield a distinct new revision. Attempt nested mutation after capture; the old policy/context must remain stable.

**M5 — Idempotence.** Compare both text and second-ledger emptiness under the same effective context. Explicitly assert the known exception set and its reasons. Test identifier canonical forms, snippets, escaped command words and actual retry call sites separately from diagnostics.

**M6 — Independent replay.** Sort accepted edits by source start, assert non-overlap, bounds and exact original slices, and apply them right-to-left without importing the parser. Compare byte-for-byte normalized output; independently verify output-coordinate spans. Alter one span/value and make the appropriate oracle fail.

**M7 — Invalidity and maximal ownership.** Change one version/IP/date/quantity component or remove/append a separator. The whole candidate must become rejected/literal when its grammar is invalid, rather than exposing a legal suffix. Pair every invalid mutation with a nearby valid control.

**M8 — Priority permutation.** Reorder equivalent candidate discovery while retaining declared priorities. Test equal text with different layers, units, values or joins, plus nested/adjacent/three-way conflicts. A stable string is insufficient when the retained metadata or later overlap changes.

**M9 — Failure injection.** Parser throw, missing/malformed policy, unknown/null profile or locale, every ledger/normalized-artifact write/lease failure, and incomplete evidence must preserve usable dictation and explicit content-free failure status. Never promote a missing ledger to a success.

**M10 — Work-preserving performance.** Mutate the benchmark to identity, empty populations and artificially slow matched/no-match cases in an isolated harness test. Verify both work validity and exit verdict. Measure real implementations at 500 words and larger sizes, recording edit populations, complete outputs and environment.

The structured-value oracle should use independent tuples: percent `(signed amount, percent)`, currency `(signed Decimal amount, currency)`, version ordered components, IPv4 four octets in range, port signed value/domain, date explicit components plus stated validation scope, and time hour/minute/supplied meridiem. Numeric identity and written form are separate assertions.

## Downstream Impact

| Consumer | M04-specific consequence / guardrail |
| --- | --- |
| M05 | Keep exact registry/alias and preview contracts. Correct dictionary recovery stays a normalization edit, never an acoustic decoder hit. Test real alias collisions and canonical no-op behavior. |
| M06 | Pass explicit frozen context; do not read destination text/files from the core normalizer or silently substitute a later context. Preserve unavailable-context degradation. |
| M07 | It receives normalized text as source. Do not ask its already-remediated validator to infer what M04 destroyed. Preserve raw/normalized distinction and generated output-span protection. |
| M10 | Skills/snippets/file tags share arbitration and per-job policy resolution. Preserve exact expansions and no-execution behavior. Limit changes to the demonstrated interface defects. |
| M13 | Distinguish full normalization time from partial result timing and evidence missingness; no metric should count a silent no-op as successful semantic work. |
| M14 | Preserve origin_stage=normalization for later corrections. Wrong typed metadata or absent normalized artifacts must not be laundered into ASR learning labels. |
| M15 | Score raw recognition, representation, typed values and false commands separately. Distinguish edit replay from policy regeneration and portable timing from reference-Mac certification. |

These are compatibility obligations, not new audits of those milestones. The accepted M01–M03/M07/M11 protections remain constraints on the repair.

## Recommended Repair Order

1. **Reproduce and freeze the challenge baseline.** Inventory actual callers and record the inherited SHA, exact source predictions versus runtime outcomes, and initial benchmark/work populations. Refute or narrow findings before production changes.
2. **Fix shared boundary/ownership and arithmetic roots.** Prioritize M04-AUDIT-02/03/04/05/08; preserve exact value, signs, maximal invalid spans and punctuation. Shared changes need paired positives immediately.
3. **Repair intent/literal/technical surfaces.** Address 01/06/07/09/10/11 with actual registry contexts and ordinary prose. Do not merely append blockers or disable useful classes.
4. **Repair determinism and composition.** Address 12/13/14/15, including deep snapshots and sequential jobs. Avoid exposing the whole project to a policy-interface rewrite.
5. **Close evidence and oracle gaps.** Address 16–21, keeping failure visibility, privacy, independent typed/replay checks, scanner closure and honest benchmark populations.
6. **Freeze first-pass production SHA and commission the required isolated adversarial review.** Independently reproduce reviewer findings on that SHA; tests for confirmed review defects must fail there and pass on the final production repair.
7. **Re-run portable and targeted compatibility evidence, then document and push.** Preserve historical acceptance and all prior runbook sections. Leave only genuine native/model/reference-Mac work pending.

## M04 Readiness Verdict

### C. Significant normalization-semantic weaknesses

This is not a verdict that M04 must be replaced. It is a verdict that several shared mechanisms—not just one or two missing examples—can alter correctly recognized meaning or misdescribe the resulting evidence. Boundary consumption, exact-value formatting, semantic ownership, literal scope, path case and policy identity all require focused remediation and independent regression oracles.

The findings are sufficiently concrete to justify a cloud remediation round, but they are **not runtime acceptance evidence**. The cloud agent must reproduce/adjudicate them against the inherited code and may refute or narrow any prediction. A refuted prediction should be recorded, not “fixed” by forcing a new behavior into production.

The baseline is current, so this is not D merely because native testing is pending. Conversely, the historical 140-fixture acceptance is not enough for A or B while these source-supported root causes remain. The next action is the accompanying M04-only Claude Code cloud handoff—not M05, M15, a main-branch merge, or a request for Daniel to run the native checklist now.
