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
on the reference Mac (`benchmarks/20260922-005827-m04/m04.json`; historical —
the M04 remediation added boundary/chain checks, re-measurement is
M04-V003). Overlap arbitration and edit application are O(n log n) in
the edit count (review R22); the benchmark gates workload validity
(authored per-sentence outputs and summed edit counts) before speed.

## Policy and context objects

- `NormalizationPolicy(locale, profile, registered_skills, identifiers)`
  — immutable value object, **deeply** (M04 remediation, AUDIT-12):
  each policy owns a private copy of the parsed policy file frozen
  recursively (read-only mappings, tuples, frozensets) before its
  revision is computed, its `LocaleTables` are sealed, and its
  attributes cannot be reassigned — no caller dictionary, process
  cache or nested table can change what an existing policy (or its
  revision) means; its
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
  minimal fields M06 will feed; `identifiers` is snapshotted (frozen
  copy) at construction. `identifiers` (spoken form → canonical,
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
  reason (`overlap_conflict`, `ambiguous_same_span`,
  `lower_layer_same_span`, `unknown_skill`, `no_command_frame`,
  `invalid_octet`, `invalid_day`, `invalid_date`, `invalid_version`,
  `unanchored_version`, `malformed_scale`, `quantified_scale`,
  `dotted_number_arity`, `leading_decimal`, `invalid_port`,
  `incomplete_path`, `ambiguous_month_word`, `protected_span`,
  `flagged_region`, `crosses_delimiter`). Rejected
  and ambiguous proposals are first-class evidence, not noise.
- `protected` — protected spans (`literal_escape`, `quoted`, `code`).
- `duration_ms` — the COMPLETE stage (tokenize, propose, arbitrate,
  assemble and apply; M04-AUDIT-17).
- `replay(input_text)` — re-applies the ledger to the retained input
  and must reproduce `text` byte-for-byte (AC05). `is_idempotent()`
  evaluates a second pass and reports the honest bool.

## Precedence and conflict resolution (S10)

Layer 1 literal escape → layer 2 protected syntax (quote zones; code
zones — the inside of ``` fences and inline `code`; already written
forms cannot re-match) → layer 3 registered skill intent → layer 4
typed numeric/symbol grammar → layer 5 context vocabulary. Candidates
sort by `(layer, longer span, position, class)` and accept greedily;
losers are retained as rejected. **Exact same-span proposals:** the
highest layer present owns the span first — also when a lower layer's
output text is identical (`lower_layer_same_span`, AUDIT-14); within
that layer, different outputs or the same text with different typed
values are all rejected (`ambiguous_same_span`). Flagged regions
(invalid values) block smaller rewrites inside them ("flagged, never
repaired") but not a larger containing match; **structural** refusals
(`invalid_day`/`invalid_date`, `invalid_octet`, `unanchored_version`,
`invalid_version`, `malformed_scale`, `quantified_scale`,
`dotted_number_arity`, `leading_decimal`, `invalid_port`,
`incomplete_path`) also block proposals that straddle their edge, so
no valid-looking prefix or suffix of a refused candidate converts
(AUDIT-04/-08). Nothing is ever applied by substitution order.

**Structural delimiters (AUDIT-02).** Edge punctuation (`.,;:!?` on a
word) and line breaks — every separator `str.splitlines()` honors,
incl. U+2028/U+2029, VT, FF, NEL and the record separators (review
R14) — separate clauses; spaces, tabs and no-break spaces do not. Every M04 grammar matches within one clause only, and
every edit covers token CORES only, so the punctuation outside a
converted phrase survives ("twelve percent." → `12%.`, "twelve
dollars, please" → `$12, please`) and two delimited quantities are
never merged ("twenty, five percent" → `twenty, 5%`, never `25%`). A
proposal that would still cross a delimiter is rejected
(`crosses_delimiter`); M05 vocabulary and M10 snippets/file tags keep
their own matching rules. A spoken punctuation/structure command owns
its own token's edge punctuation ("hello comma, how" → `hello, how`;
"new line, hello" at a text start → `hello`, review R23).

## Grammar behavior reference

**Integers** — technical profile converts a number phrase followed by a
non-function word ("twelve retries" → "12 retries"). Guards: function
words after ("one of the reasons", "the two of us", "one through
five"), the idiom "number one", a bare multiplier after a quantifier
("a few hundred people", "some hundred dollars", "a few hundred
thousand dollars" stay prose — the whole run is a `quantified_scale`
region), terminal bare quantities ("the answer is twelve" stays),
year-speak ("nineteen eighty four" stays; "twenty six retries" parses
as one phrase and converts), digit runs (phone/code territory) and any
number standing next to other number speech in the same clause ("three
fifteen minute breaks", "chapter five thirty two", "five minus three",
"one oh five" stay words — adjacent digits would change how the run
reads). Number speech includes a hyphenated compound ("three hundred
sixty-five days" stays words rather than `300 sixty-five`), an ordinal
after a tens word ("the twenty fifth anniversary"), "dot" and "and"
only between numbers, "oh" only next to a digit ("oh twelve people" →
`oh 12 people`), and "point"/"dot" not after a determiner ("at this
point twelve percent" → `at this point 12%`) (review R2–R4, R12, R23).
en joins a scale and a smaller group with "and" ("two thousand and
twenty dollars" → `$2020`, "one thousand and one" → 1001); es does not
use "y" after "mil", so "dos mil y veinte euros" stays words. es tables
carry the accented spellings (`dieciséis`, `veintidós`, `veintitrés`,
`veintiséis`, `millón`; review R13). Malformed scale chains are refused whole (`malformed_scale`):
an explicit zero multiplier ("zero hundred"), a scale directly after a
scale ("one thousand million") or a scale not smaller than the previous
one ("one million million") — an explicit zero is tracked separately
from an omitted multiplier. Anchors (`milestone`,
`step`, `sprint`, … in the profile) convert a trailing cardinal
("milestone fourteen" → "milestone 14"; "step negative five" →
`step -5` with typed value −5). Ordinal prose ("first time",
"finished first") never converts. The standard profile keeps all bare
integers as words.

**Decimals/signs** — "minus zero point zero five" → `-0.05`; spoken
fraction digits are preserved exactly ("zero point five zero" →
`0.50`). Sign words: minus/negative (en), menos (es). A second decimal
word in the phrase is version-speak, not a decimal: the whole
unanchored chain is refused (`unanchored_version`) — no suffix
("twenty six point four") converts on its own. A chain opening with a
decimal word ("point five percent") is refused whole
(`leading_decimal`) — a fraction is spoken digit by digit, so this
needs a single digit word after the decimal word and no determiner
before it (review R12). **Scaled decimals are exact** (AUDIT-03): "one
point two three four five thousand dollars" → `$1234.5` (typed value
1234.5); an integral result renders as an integer ("one point five
million" → `1,500,000`); nothing is truncated through `int()`. Every
typed value carries the spoken sign exactly as rendered (AUDIT-05).

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
marzo" → `4 de marzo`). **Narrow calendar check** (design D1,
adjudicated in the M04 remediation): a day past the month's maximum is
flagged `invalid_day` ("March thirty two", "February thirty first",
"April thirty first"); February 29 with an explicit non-leap year is
flagged `invalid_date`; February 29 without a year renders (value
`02-29`, not certified against a year). A tens word + ordinal is ONE
compound day even when out of range ("March thirty second" is flagged
whole, never shortened to `March 30`). Month names that are also
ordinary words (`may`, `march`, `august` — `ambiguous_month_words` in
the locale table) need evidence: written capitalization ("May first")
or a date preposition before them ("on march fourth", "due on may
first") AND date-shaped context after the date phrase (clause end, a
function word other than the modal-only "be", or a time follower: "on
May first at noon"); "this may first require approval", "we build on
may first require updates" and "May first responders" stay prose
(`ambiguous_month_word` review; review R11). The day-first shape "the
Nth of <month>" is date evidence by itself; an out-of-range day there
is flagged too ("the thirty second of May", review R4). Numeric dates (03/04) and relative
days ("tomorrow") are never touched.

**Times** — hour + minute ("five thirty PM" → `5:30 PM`; "at nine oh
five" → `at 9:05`), gated on time EVIDENCE (AUDIT-06): a time
preposition right before the hour (`at`, `by`, `around`, `before`,
`after`, …) or a spoken meridiem. Utterance start alone is not
evidence ("three fifteen minute breaks", "one oh five", "five thirty
people" stay words). Without a meridiem, what follows an anchored
hour + minute must be clause material — the end of the clause, a
function word, a pronoun or a time adverb (`time_followers`: "at five
thirty tomorrow", "at eight fifteen sharp"); a content word means the
numbers count or measure something ("for three fifteen minute
breaks", "sold at three fifty dollars", "about one twenty people"),
never a clock (review R5). No
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
inside it). A dotted number chain of any other arity ("one dot two dot
three", "… dot four dot five") is refused whole
(`dotted_number_arity`); a four-octet prefix of a longer chain never
converts. "port eight thousand" → `port 8000`; the SIGNED value is
validated (1–65535) — "port negative eighty" or "port seventy thousand"
is refused (`invalid_port`), never emitted as a port.

**Dimensions/units** — "ten by twenty centimeters" → `10 × 20 cm` (no
unit conversion, no rounding). Number + unit word converts the number
and keeps the spoken word ("thirty seconds" → `30 seconds`); the edit's
unit carries the canonical symbol, keeping MB vs Mb distinct.

**Identifiers** — only with context identifiers ("user ID" → `userId`);
never invented otherwise. A span that already reads as its canonical
form emits no edit (AUDIT-15) and claims the span.

**Paths/dotfiles/domains/email** — known dotfiles ("dot env" →
`.env`), anchored spoken paths ("path slash users slash danny" →
`/users/danny`); components keep the speaker's written spelling
("path slash Users slash Ada" → `/Users/Ada` — paths are
case-significant, AUDIT-11), a component may carry spoken dots
("path slash etc slash nginx dot conf" → `/etc/nginx.conf`, "… slash
dot env" → `/…/.env`; review R9), and a chain whose next component is
not a plain word ("… slash build2") is refused whole
(`incomplete_path`);
unanchored slash chains stay prose ("slash the budget"). Spoken
addresses with known TLDs convert ("danny at gmail dot com" → email;
"example dot co dot uk" → domain), keeping the written spelling of
every component ("UserName at example dot com" →
`UserName@example.com`); articles block ("the dot com era"). Already-written URLs/paths/emails never re-match.
No filesystem action ever runs.

**Slash skills** — `slash brainstorm` → `/brainstorm` only for a
registered skill/alias, exact spelling, multiword aliases map to exact
hyphenated names; unknown skill words stay literal with a retained
review suggestion. Registry membership is identity, not intent
(AUDIT-01, review R1): the token is inserted only in a COMMAND
POSITION — the start of a clause ("slash code review", "Done. Slash
code review the PR") or right after an explicit command frame
(`slash_command_frames`: "add", "run", "use", "then", "please", "the",
…; "to" only after a motion/change verb in `slash_command_frames_to`:
"switch to slash code review"; a frame right after a subject pronoun
is a verb — "we do slash costs"). Anywhere else ("we should really
slash code review time", "managers slash costs", "we cut hiring and
slash …") "slash" is the ordinary verb: the words stay literal with a
`no_command_frame` review record.
Residual (design D2): utterance-initial "slash <registered alias>"
remains the command even when the alias is also an ordinary noun. A token followed by prose is space-separated. Slash
insertion is text only — no Enter, no autocomplete selection, no skill
invocation.

**Symbols** — spoken punctuation names convert with structural noun
guards (AUDIT-09): a determiner right before ANY name ("a question
mark", "the forward slash character", "my comma key" — articles,
"each"/"every" and the possessives that cannot be objects; "that",
"this", "her", "his", "those" are also object pronouns, so "let's do
that period" → `let's do that.`; review R6), and a trailing-punctuation
or noun-ambiguous name at the start of a clause with any token after
it ("period drama", "colon cancer", "pipe tobacco", "Period 3 starts";
alone, "comma" is still `,`; review R7 keeps the second pass stable). The historical lexical guards
stay ("a dash of salt", "the period of adjustment", "fourth period",
"grace period" / "trial period"). Flags keep the written case of their
letters ("ls dash L" → `ls -L`; `-L` ≠ `-l`, review R10); a
single-letter flag follows a command in the same clause, so a
clause-initial "dash I asked him" stays prose. Residual (design D2): a mid-clause name
followed by a noun ("we discussed period drama") and "time period"
are surface-identical to the command positions "hello comma how" /
"stop period"; the supported escape is "write the word period". Tight
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
`twelve thousand`). "word" protects one word; "words"/"phrase" protect
the whole run of tokens — written tokens such as "version 2" or
"GPT-5" included (review R8) — to the next structural delimiter or the
end of the utterance, with no word cap (AUDIT-10); a marker inside an
escaped object is content, never a second escape. Quoted instructions are content, not escapes
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

**M04 remediation.** A retention failure (normalized-text or ledger
write, or either lease) never fails the stage, but it is visible: a
content-free `training.capture_failed` event names the failed step
(`stage=normalization`, `detail=<step>`, `outcome=
normalization_not_retained`), the envelope carries the distinct
missing reason `retention_write_failed` (the stage ran; its evidence
was not retained); a normalized-text artifact fully published before
a ledger failure stays referenced (it is what cleanup read), and no
half-published artifact is ever referenced (AUDIT-16, review R16). The
block records `policy_source`: `job_snapshot` (the job's own captured
policy), `retry_unscoped_default` (a retry of retained audio: a new
snapshot belonging to no destination — configured profile, global
dictionary and manifest skills, unscoped vocabulary, never the
previous job's workspace skills or context; AUDIT-21, review R15) or
`current_default` (the configured-profile fallback for a job whose
hotkey-down capture failed). A job's inherited ("inherit" style) profile always
resolves against the configuration, never the previous job's
effective profile (AUDIT-13).

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

## M10 live status (layer 3 extended)

Layer 3 "registered snippet/skill intent" is fully populated
(`contracts/profiles.md`): `grammar_snippets` expands frozen snippet
triggers (exact stored content, utterance-filled placeholders) and
`grammar_file_tags` resolves explicit "attach file …" references
against the destination's known files; manifest-sourced skills join
dictionary skills in `registered_skills`. The same-span conflict rule
is precedence-aware as of M10: differing outputs ACROSS layers resolve
by precedence (the loser is retained as `lower_layer_same_span`);
differing outputs at one layer still reject as `ambiguous_same_span`.
Generated output spans (snippet expansions, resolved filenames) carry
separate normalized-coordinate protection into cleanup
(`snippets.protected_output_spans`).
