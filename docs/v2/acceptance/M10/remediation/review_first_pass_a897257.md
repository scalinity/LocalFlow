# M10 independent review — frozen first pass a897257

Reviewer: a fresh-context agent that authored none of the remediation,
in its own detached read-only worktree at
a89725701b05aff62e13fe394d31539242f28dc5 (`localflow/` byte-identical to
first-pass production 409c436). Inputs: the audit, the frozen corpus,
the author's adjudications (as claims to verify), the contracts and the
changed-file list; no author rationale and no instruction to approve.
Reproductions ran under `tests/v2/context/run_isolated.py` from the
worktree root and printed their `localflow` import origin; artifacts
stayed outside the reviewed source (`<scratchpad>/review-artifacts`).
Sanitized for the repository: artifact paths are shown as
`<scratchpad>`, and the synthetic slot value in R-02's trigger is shown
as "Ada".

## 1. Findings (9: 3 Medium, 6 Low; 8 confirmed by reproduction)

**R-01 Medium (override) CONFIRMED** — Next Dictation Mode never
reaches a double-tap hands-free dictation. app.py:3114-3121 (the second
tap discards the pending job and sets hands_free), 3268 (mode taken at
admission), 3422 (_defer_short_discard). With hands_free="double_tap"
the first tap is an admitted job and takes the pending mode; the second
tap discards it and starts the hands-free job, whose take returns None.
Trigger: hubSetNextJobMode("raw"); tap, tap, say "we retried three times
today", tap. Observed: the pending job's override raw; hands-free job
m10_override None, wp.mode clean (category_default); inserted
'we retried 3 times today'. The reviewer notes D3's letter covers a
too-short capture, but not the first half of the hands-free gesture.

**R-02 Medium (grammar boundaries) CONFIRMED** — the slot continuation
swallows LocalFlow's own spoken structure commands into the protected
generated span. engine.py:153-166 (hard_break_before inspects written
characters only), syntax.py:302-304. Snippet "sign off" → "Best,\n{{name}}";
"sign off comma Ada new line do not deploy tonight" →
'Best,\nAda new line do not deploy tonight' (whole string protected);
spoken period and open/close quote the same; controls: no snippet →
'Ada\ndo not deploy tonight'; written newline → stops correctly.

**R-03 Medium (file tags) CONFIRMED** — a partial workspace listing is
treated as the complete candidate set. app.py:1306 (list_workspace_files
drops truncated/reason), file_tags.py:132-135 (a child directory whose
open fails is skipped without marking the listing partial),
file_tags.py:224-243 (no completeness input). (a) unreadable subdir:
truncated=False, listed ['src/config.json'] → resolved; (b) name-cap
truncation: truncated=True reason=name_cap, listed ['a/config.json'] →
coordinator inserted 'a/config.json now'; file_references carries no
partiality label.

**R-04 Low (provenance) CONFIRMED** — a transform-snapshot fault is
recorded and displayed as the user's "auto-apply off". app.py:1042-1050,
profiles.py:364, app.py:2071-2075. builtin:polish auto_apply=True,
override polish, snapshot fault → fallback_reason
transform_auto_apply_disabled:polish; quick menu "asked polish,
auto-apply off"; _m10_degraded the same.

**R-05 Low (writer) CONFIRMED** — the store's one-trigger rule is
ASCII-only while runtime folds case with Unicode rules (SQLite NOCASE vs
str.lower()). "Éclair time" and "éclair time" both admitted; the
snapshot masks both as duplicate_trigger; dictating 'éclair time' stays
literal.

**R-06 Low (Hub preview) CONFIRMED** — the collision preview says "no
collisions" when the trigger's holder is a disabled snippet, but the
store then refuses the save, and its message ("the engine would keep
both literal") is false for a disabled holder.

**R-07 Low (discovery cache) CONFIRMED** — the warm fingerprint
disagrees with discovery for any source that is read and then refused
(('refused', code) vs ('read', …)), and for an unreadable SKILL.md (open
fails in discovery, stat succeeds in the pre-pass): the cache never
hits; three freezes with an unchanged bad manifest → three discoveries
and three manifest_refused events. Errs toward freshness.

**R-08 Low (discovery isolation) CONFIRMED** — one configured path with a
NUL byte aborts discovery of every source: developer_policy admits it,
os.open raises ValueError, _discover_source does not catch it; the valid
source's skill is lost; fingerprint raises too.

**R-09 Low (benchmark) STATIC ONLY** — the "adversarial same-prefix"
cohort does not stress the matcher: 300 triggers share the first word
"trigger", but the 500-word input contains it once, and the snapshot
build has no prefix-dependent cost.

## 2. Refuted hypotheses (18)

History/manual Retry consuming the override; a failed recorder start
losing it; optional freeze faults losing Raw (inner and outer paths);
deferred/failed widening adding workspace skills; correlated patches
committing an invalid row; pre-admission TimeoutError reported unknown;
AdmissionError escaping `except ValueError`; snippet/skill/file text
adding terminal execution (M08 _TERMINAL_UNSAFE); truthy strings opting
a transform in; a user-declared profile name in the envelope or events;
generated snippet text becoming a verified ASR reference; the
snippet_definitions artifact written without consent; deep JSON nesting
escaping per-source isolation; symlinked skill children followed or a
home/cwd fallback; the open document breaking basename ties; the
benchmark accepting no-op components; previews recording usage or
evidence; a stale Hub toggle re-enabling a row; a snippet chaining within
one job.

## 3. Weaker than claimed

- C137/C214 never assert "partial/missing result is labeled honestly"
  (C137 passes with truncated=false although two directories dropped).
- C216/S016 grade the module-level preview_collisions with a hand-built
  policy instead of app.hubSnippetCollisionPreview; the explicit-slash
  and wrong-scope contenders are missing; the barrier label is constant.
- C198 grades population sizes and percentile keys, not adversarial work.
- r13_malformed_manifest_keeps_requested_raw now passes because the
  fault is contained in discovery, not because the override survives it
  (the outer path is exercised by C027).
- C090 has no line or clause in its input; no case covers spoken
  delimiters.
- C030 and c13 run with hands_free off: no double-tap coverage.
- Constant barrier labels in delegated drivers (C170/C213, C203, C217)
  are acceptable only because the delegated tests build the seams.

## 4. Not done / unrated observations

Not run: benchmark, mutation check, native suites, sweep, full corpus.
Unrated: (i) after an unknown-outcome Update the binding keeps the old
revision, so the next reload reports the user's own committed save as
"changed since you opened it"; (ii) _m10_outcome says "press Save
again" on the Update path. Not probed: a worker-thread
_unscoped_norm_state racing the freeze on the discovery cache;
stale_workspace after a deferred job; a "---" at the 4096-byte limit;
hard-linked SKILL.md; control characters in skill names at non-terminal
destinations; IDE-embedded terminals classified "ide".
