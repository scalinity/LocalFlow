# Contract: Typed numeric and spoken-syntax normalization

**Spec:** S10, S14 (ledger), S24 (budget), S29.4 (evidence family) ·
**Owner:** M04 · **Suites:** EV-06, EV-19 (normalization fields)

`localflow.v2.normalize` turns spoken numbers, technical tokens and
command phrases into their written forms without corrupting literal
prose. It is deterministic, model-free, idempotent-by-construction
pure code: identical `(text, policy, context)` triples produce
identical results.

## Process placement (M04 decision)

Normalization runs in the **parent process, on the coordinator thread**,
between ASR and cleanup (S06 pipeline order
`transcribing → normalizing → cleaning`). The worker subprocess exists
to isolate Metal/MLX faults (S06); normalization holds no MLX state, so
it gains no protocol op and never queues behind the supervisor's GPU
lock. The M03 worker protocol (`worker.md`) is unchanged. The stage is
budgeted at P95 ≤ 25 ms for a 500-word input (S24) — measured 4.77 ms
on the reference Mac (`benchmarks/20260922-005827-m04/m04.json`).

## Policy and context objects

- `NormalizationPolicy(locale, profile, registered_skills, identifiers)`
  — immutable value object (read-only table/map views; mutation after
  construction is impossible through the public surface); its
  `policy_revision` (`m04:<sha256-12>` over the canonical policy-file
  content + locale + profile + registrations) is recorded on every
  result and in the evidence envelope. Hashing the file *content*
  (not its revision string) means an edited word table can never share
  a revision id with the old tables.
- Profiles: `technical` (default; integers in technical contexts,
  flags, everything below), `standard` (bare integers stay words; typed
  forms still convert), `off` (exact passthrough, stage skipped).
  Config: `normalization_profile`, `normalization_locale` (default
  `technical` / `en-US`; unknown values disable the stage with an event
  rather than silently re-directing). Locale drives rendering
  (grouping/decimal separators, currency symbols and placement, percent
  spacing, date shape); the locale belongs to the job, not the
  machine's location.
- `ContextSnapshot(destination_app, path_context, identifiers)` — the
  minimal fields M06 will feed. `identifiers` (spoken form → canonical,
  e.g. "user id" → "userId") is the only field read today; absent
  context never invents a casing convention (S10 identifiers row).
- Word tables and profile flags live in
  `localflow/v2/normalize/policies/number_profiles.json` (en-US, es-ES).

## Typed spans and the edit ledger

All text offsets are zero-based half-open Unicode code points
(`artifacts.md`); they never mix with UTF-16 or token offsets. A
`NormalizationResult` carries:

- `edits` — the ledger: per accepted edit, `cls`, `op`, input/output
  spans into the exact source/output strings, the input/output text of
  the effective span, the parsed `value` (int/`Decimal`/str — decimal
  arithmetic, exact), canonical `unit` (%, USD, cm, MB vs Mb, …),
  precedence `layer` and a reason when relevant.
- `rejected` — every considered-but-not-applied proposal with its
  reason (`overlap_conflict`, `ambiguous_same_span`, `unknown_skill`,
  `invalid_octet`, `invalid_day`, `invalid_version`,
  `unanchored_version`, `protected_span`, `flagged_region`). Rejected
  and ambiguous proposals are first-class evidence, not noise.
- `protected` — protected spans (`literal_escape`, `quoted`).
- `replay(input_text)` — re-applies the ledger to the retained input
  and must reproduce `text` byte-for-byte (AC05). `is_idempotent()`
  evaluates a second pass and reports the honest bool.

## Precedence and conflict resolution (S10)

Layer 1 literal escape → layer 2 protected syntax (quote zones; already
written forms cannot re-match) → layer 3 registered skill intent →
layer 4 typed numeric/symbol grammar → layer 5 context vocabulary.
Candidates sort by `(layer, longer span, position, class)` and accept
greedily; losers are retained as rejected. Exact same-span proposals
with different outputs are all rejected (`ambiguous_same_span`).
Flagged regions (invalid values) block smaller rewrites inside them
("flagged, never repaired") but not a larger containing match. Nothing
is ever applied by substitution order.

## Grammar behavior reference

**Integers** — technical profile converts a number phrase followed by a
non-function word ("twelve retries" → "12 retries"). Guards: function
words after ("one of the reasons", "the two of us", "one through
five"), the idiom "number one", a bare multiplier after a quantifier
("a few hundred people", "some hundred dollars" stay prose), terminal
bare quantities ("the answer is twelve" stays), year-speak ("nineteen
eighty four" stays; "twenty six retries" parses as one phrase and
converts), and digit runs (phone/code territory). Anchors (`milestone`,
`step`, `sprint`, … in the profile) convert a trailing cardinal
("milestone fourteen" → "milestone 14"). Ordinal prose ("first time",
"finished first") never converts. The standard profile keeps all bare
integers as words.

**Decimals/signs** — "minus zero point zero five" → `-0.05`; spoken
fraction digits are preserved exactly ("zero point five zero" →
`0.50`). Sign words: minus/negative (en), menos (es). A second decimal
word in the phrase is version-speak, not a decimal.

**Percent** — number + percent word(s) → `12%` (en) / `12 %` (es
spacing). "N percentage points" converts the number only and keeps the
phrase (never a relative percent). Fractional quantities ("five and a
half percent") stay words (documented limitation).

**Currency** — number + currency word renders with the locale symbol
when the locale has one (en-US: `$12,000`; es-ES: `12.000€`), otherwise
digits keep the spoken word ("30 euros" under en-US). No invented
cents handling ("twelve dollars and fifty cents" → `$12 and 50 cents`).

**Dates** — month-name only ("March fourth" → `March 4`, optional
spoken year "twenty twenty six" → `March 4, 2026`; es "el cuatro de
marzo" → `4 de marzo`). Days validate 1–31 ("March thirty two" is
flagged, never repaired). Numeric dates (03/04) and relative days
("tomorrow") are never touched.

**Times** — hour + minute ("five thirty PM" → `5:30 PM`; "nine oh
five" → `9:05`), gated on time context: the phrase must start an
utterance or follow a time preposition (`at`, `by`, `around`,
`before`, `after`, …), so "chapter five thirty two" stays prose. No
meridiem, timezone or 24h form is invented; bare hour + meridiem
("eight AM") and "noon" stay words (limitations). Bare single-unit
minutes do not parse ("five five" is not 5:05).

**Codes/phones** — anchored digit runs preserve order and leading zeros
("code zero zero seven three" → `code 0073`; one linking "is" allowed:
"the zip code is one zero zero zero one" → `10001`). Ten bare digit
words group per locale (`555-123-4555`); explicit "dash" groups join
(`555-1234`). Unanchored runs stay words; no country code is invented.

**Versions** — anchored dotted components ("version one point two six
point four" → `version 1.26.4`); each component validates ≤ 999
("version one point two thousand" is flagged). Unanchored multi-point
phrases stay words with a review suggestion; a single "point" without
anchor is a decimal.

**IPs/ports** — four spoken octets ("one ninety two dot one sixty
eight dot one dot ten" → `192.168.1.10`); octets validate 0–255
("two sixty …" flagged, never repaired, and blocks partial rewrites
inside it). "port eight thousand" → `port 8000` (1–65535).

**Dimensions/units** — "ten by twenty centimeters" → `10 × 20 cm` (no
unit conversion, no rounding). Number + unit word converts the number
and keeps the spoken word ("thirty seconds" → `30 seconds`); the edit's
unit carries the canonical symbol, keeping MB vs Mb distinct.

**Identifiers** — only with context identifiers ("user ID" → `userId`);
never invented otherwise.

**Paths/dotfiles/domains/email** — known dotfiles ("dot env" →
`.env`), anchored spoken paths ("path slash users slash danny" →
`/users/danny`); unanchored slash chains stay prose ("slash the
budget"). Spoken addresses with known TLDs convert ("danny at gmail
dot com" → email; "example dot co dot uk" → domain); articles block
("the dot com era"). Already-written URLs/paths/emails never re-match.
No filesystem action ever runs.

**Slash skills** — `slash brainstorm` → `/brainstorm` only for a
registered skill/alias, exact spelling, multiword aliases map to exact
hyphenated names; unknown skill words stay literal with a retained
review suggestion. A token followed by prose is space-separated. Slash
insertion is text only — no Enter, no autocomplete selection, no skill
invocation.

**Symbols** — spoken punctuation names convert with idiom guards
("hello comma" → `hello,`; "a dash of salt", "the period of
adjustment", "fourth period" and noun compounds like "grace period" /
"trial period" stay prose via the article/blocker lists). Tight
symbols: underscore/hyphen join without spaces ("snake_case");
asterisk is pair-aware ("asterisk bold asterisk" → `*bold*`). Bare
"slash" never becomes "/" ("forward slash" does). Shell pipes/flags
are text ("dash dash verbose" → `--verbose`, "pipe" → `|`); nothing
executes.

**Markdown** — explicit commands produce structure ("new paragraph" →
blank line, "new line", "new bullet", "new heading two", "start/end
code block"); article-guarded prose ("a new bullet point here") and
enumeration ("first item, second item" — cleanup's job, M03/M07) stay
prose. Block output trims leading/trailing breaks at text edges; a
block command that IS the utterance keeps its break.

**Literal escape** — "write the word(s)/phrase X" drops the marker and
emits the object verbatim, protected from every grammar ("write the
word slash" → `slash`; "write the words twelve thousand" →
`twelve thousand`). Quoted instructions are content, not escapes
(escape markers inside quotes do not fire). **Idempotence corner
(documented):** an escape whose object is or contains a command
word/phrase ("write the word comma" → `comma`) is not stable under a
second full pass — the emitted words re-match their command grammar.
The pipeline never re-normalizes normalized text (each attempt starts
from raw ASR output), all 140 owning fixtures are idempotent except
the two that document this corner (LF-SYN-003/005), and
`is_idempotent()` reports False honestly per record (S29.4
"idempotence result when evaluated").

## Test-phrase and scoring APIs

- `preview_phrase(text, policy, context)` — what normalization would do
  to a phrase, edit by edit, for the future Dictionary/Developer UI.
- `scoring.score_command_corpus(cases)` — ITN-independent exact-token
  accuracy on command cases and false-command rate on non-command
  controls (E06/E18.4 text counterparts; M15 owns audio and the
  optional cloud comparator — nothing here touches a network).
- `scoring.separate_scores(result)` — number-word→digit representation
  edits counted apart from everything else (AC05).

## Evidence (S29.4 normalization family)

With collection enabled the collector writes two artifacts — the
normalized text and the full ledger JSON (accepted + rejected +
protected, parent = the raw transcript artifact) — and the envelope's
`normalization` block carries policy revision, per-edit ops/values/
units/spans, counts, the idempotence bool (evaluated with the same
context as the first pass; null-with-reason if evaluation fails) and
artifact ids. Envelope values are typed numbers and date/time forms
only; string-valued command classes (emails, paths, skill tokens,
codes, phones, IPs, versions) keep their strings in the lease-governed
ledger artifact — nothing transcript-derived outlives the artifact
leases inside the envelope (S29.14). Replay pulls text from the
artifacts. Without the stage (profile `off`, policy-load failure, or
the pre-M04 collector path), the envelope keeps the honest
`not_captured_at_stage` reason.

## M05/M06 dependencies

M05 feeds `registered_skills` (dictionary-scoped) and vocabulary terms;
M06 feeds `ContextSnapshot` fields (destination app, path context,
workspace identifiers) — **live since M06**: the app's per-job context
is built by `context.ContextSnapshot.to_engine_context` with the
job's frozen vocabulary snapshot, so `destination_app` (bundle id),
`path_context` (IDE/terminal/document destinations) and `identifiers`
(spoken→canonical from the bounded nearby window, cap 64) carry real
values; absent fields still degrade exactly as before.

## M05 live status (layer 5 fed)

Dictionary vocabulary now feeds layer 5: `ContextSnapshot.vocabulary`
carries the immutable `VocabularySnapshot`, `grammar_vocabulary`
proposes scoped-alias edits with `rule_id` attribution, and
dictionary-scoped skills populate `registered_skills` at policy
construction (the previously inert unknown-skill suggestions now
resolve through the dictionary). Edit/Proposal/Rejected records carry
an optional `rule_id` (additive; JSON round-trips). Layer-5 token
matching now anchors on token cores so edge punctuation survives —
`grammar_identifiers` received the same fix. See
`contracts/vocabulary.md` for the full matching contract.
