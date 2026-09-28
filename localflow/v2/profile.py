"""Your Voice — the local communication profile (V2 M14, Spec S22,
contract profile.md).

Measured views are computed from ELIGIBLE evidence only: live V2
examples' RAW transcripts (the speech, not Qwen's cleaned output —
S22: never learn the cleanup model's style as the user's), each the
example's OWN retained raw-transcript artifact (job, role and digest
checked — m14-policy-r1 D11), usage facts for app/time patterns,
correction labels and the dictionary rules applied in that speech.
Snippet-generated spans and excluded/quarantined examples never feed
speech statistics. Every measured number is a store fact with its
denominator.

Interpretive cards are DETERMINISTIC functions of the measured views
(rule-based synthesis, no model call — the S23 table requires no
extra always-resident model, and a deterministic card keeps committed
fixtures stable): each card carries its supporting example ids,
coverage period and the ``interpretive`` label. Below the eligible-
words threshold (default 2,000, S22's initial default — a floor for
interpretation, not a validity claim) only measured totals render and
the honest explanation shows; a fabricated profile to fill an empty
screen is the M14 stop condition.

Deletion: a snapshot is a RECORD, never a cache — regeneration always
recomputes from the current store. Publication re-validates the exact
inputs it read (each example's revision and raw artifact, the labels
and exclusions — D16): a change during the read restarts the
computation. Any snapshot whose evidence died (delete-everywhere,
expiry, exclusion from training, a purged raw transcript) is
invalidated and loses its text-bearing content — phrases and cards
never outlive their source. User-excluded evidence links carry forward
to future snapshots by example id. Nothing here ever feeds the
dictation pipeline: no cleanup prompt, context or vocabulary path reads
a profile snapshot (M14-AC04 — pinned by test).
"""

from __future__ import annotations

import json
import re
import statistics

from . import ids
from .analytics import conn_usage_revision
from .curation import evidence as ev
from .store import TRAINABLE_STATES, Store

ALGORITHM_VERSION = 2
DEFAULT_MIN_WORDS = 2000
_PHRASE_TOP = 12
_TERM_TOP = 10
# Examples per bounded eligibility read (one short writer op each).
_READ_CHUNK = 250
_STOPWORDS = frozenset(
    "the a an and or but to of in on for with is are was were be it"
    " this that i you we they he she do does did so at as by from not"
    " my your our".split())

_LIVE_STATES = TRAINABLE_STATES  # quarantined content never feeds speech stats


_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _local_hour(iso_utc: str, offset_minutes) -> int | None:
    """The local hour of a UTC instant under its recorded UTC offset;
    None when either is missing or unusable — a corrupt or impossible
    offset (outside UTC−12…UTC+14) is unknown, never a guessed hour
    (a UTC hour is not a time of day)."""
    if not iso_utc or len(iso_utc) < 16 or offset_minutes is None \
            or isinstance(offset_minutes, bool):
        return None
    try:
        minutes = int(iso_utc[11:13]) * 60 + int(iso_utc[14:16])
        offset = int(offset_minutes)
    except (ValueError, TypeError):
        return None
    if not -720 <= offset <= 840:
        return None
    return ((minutes + offset) // 60) % 24


# Why a snapshot's evidence stopped being usable, by the example's state.
_DEAD_REASONS = {"deleted": "source_deleted", "expired": "evidence_expired",
                 "excluded": "evidence_excluded_from_training",
                 "quarantined_sensitive": "evidence_quarantined"}


def _invalidate(conn, reasons: dict) -> int:
    for snapshot_id, reason in reasons.items():
        conn.execute(
            "UPDATE profile_snapshots SET invalidated_reason=CASE WHEN"
            " state='current' THEN ? ELSE invalidated_reason END,"
            " state='invalidated', measured_json='{}', cards_json='[]'"
            " WHERE snapshot_id=?", (reason, snapshot_id))
    return len(reasons)


def _scrub_dead_evidence(conn) -> int:
    """Invalidate every snapshot — current or historical — that drew on
    an example no longer eligible (deleted, expired, excluded,
    quarantined) or whose raw transcript is no longer retained (a purge
    while the example stayed live — M14-AUDIT-03), clearing its
    text-bearing content: derived phrases and cards never outlive their
    source (S29.14). The reason names what happened to the evidence.
    Returns the number scrubbed."""
    reasons: dict[str, str] = {}
    for snapshot_id, state in conn.execute(
            "SELECT pe.snapshot_id, e.state FROM profile_evidence pe"
            " JOIN profile_snapshots s ON s.snapshot_id=pe.snapshot_id"
            " LEFT JOIN training_examples e ON e.example_id=pe.example_id"
            " WHERE (s.measured_json!='{}' OR s.state='current') AND"
            " (e.example_id IS NULL OR e.state NOT IN"
            f" ({','.join('?' * len(_LIVE_STATES))}))"
            " ORDER BY pe.snapshot_id, e.state", _LIVE_STATES).fetchall():
        reasons.setdefault(snapshot_id,
                           _DEAD_REASONS.get(state, "source_deleted"))
    for (snapshot_id,) in conn.execute(
            "SELECT DISTINCT pe.snapshot_id FROM profile_evidence pe"
            " JOIN profile_snapshots s ON s.snapshot_id=pe.snapshot_id"
            " JOIN training_examples e ON e.example_id=pe.example_id"
            " JOIN training_revisions r ON r.revision_id="
            "e.latest_revision_id"
            " LEFT JOIN artifacts a ON a.artifact_id="
            "json_extract(r.envelope_json, '$.artifact_ids.source_text')"
            " WHERE (s.measured_json!='{}' OR s.state='current') AND"
            " (a.artifact_id IS NULL OR a.purged=1)").fetchall():
        reasons.setdefault(snapshot_id, "source_purged")
    return _invalidate(conn, reasons)


def _latest_labels(conn) -> dict:
    """example_id → (edit_kind, domains) of its CURRENT reviewed label —
    the latest revision; an abstained latest revision counts as no
    label (the reviewer's current opinion is uncertainty; the shared
    effective-judgment rule, m14-policy-r1 D01)."""
    out = {}
    for ex, kind, domains, abstained in conn.execute(
            "SELECT l.example_id, l.edit_kind, l.domains_json,"
            " l.abstained FROM correction_labels l WHERE l.revision ="
            " (SELECT MAX(m.revision) FROM correction_labels m WHERE"
            " m.example_id = l.example_id)").fetchall():
        if not abstained:
            out[ex] = (kind, json.loads(domains or "[]"))
    return out


def _labels_digest(conn) -> str:
    """Every label row's content-free axes (never transcript text): a
    label change moves it even when the row count stays the same."""
    rows = conn.execute(
        "SELECT example_id, revision, edit_kind, abstained, domains_json"
        " FROM correction_labels ORDER BY example_id, revision"
    ).fetchall()
    return ids.sha256_text(json.dumps(rows))


def _exclusions_digest(conn) -> str:
    return ids.sha256_text(json.dumps([r[0] for r in conn.execute(
        "SELECT DISTINCT example_id FROM profile_evidence WHERE"
        " included=0 ORDER BY example_id").fetchall()]))


def _applied_canonicals(conn, example_id, env) -> dict:
    """entry id -> the canonical frozen in the example's OWN applied-rules
    artifact (qualified: this job's artifact, its producer role, its
    digest) — {} when that record is absent or does not qualify."""
    vocab = ((env.get("normalization") or {}).get("vocabulary") or {})
    q = ev.qualify(conn, vocab.get("applied_rules_artifact"),
                   "vocabulary_applied_rules",
                   job_id=ev.conn_example_job(conn, example_id))
    if not q["ok"]:
        return {}
    try:
        payload = json.loads(q["artifact"]["text"])
    except ValueError:
        return {}
    return {r["entry_id"]: r["canonical"]
            for r in (payload.get("rules") or [])
            if isinstance(r, dict) and r.get("entry_id")
            and r.get("canonical")}


def _vocabulary_revision(conn) -> int:
    row = conn.execute("SELECT value FROM vocabulary_meta WHERE"
                       " key='revision'").fetchone()
    return int(row[0]) if row else 0


class ProfileService:
    """Profile computation and snapshot reads over the single-writer
    store: bounded chunked reads, counting off the writer, one short
    write op per snapshot."""

    def __init__(self, store: Store, emit=None,
                 *, min_words: int = DEFAULT_MIN_WORDS):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)
        self.min_words = min_words

    # ---- eligibility --------------------------------------------------------

    def _read_candidates(self, conn, example_ids) -> list:
        """One bounded read of the live-capture examples among
        ``example_ids``, as (example_id, envelope, raw text,
        snippet_expanded, raw artifact id, revision id, job, state, attempt
        order). An example that is not live or lacks its OWN retained raw
        transcript is returned with text None: it still names its job's
        latest attempt, so an older attempt never stands in for it."""
        marks = ",".join("?" * len(example_ids))
        rows = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
            "SELECT example_id, state, job_id, rowid FROM training_examples"
            f" WHERE example_id IN ({marks})", example_ids).fetchall()}
        out = []
        for ex_id, payload in conn.execute(
                "SELECT example_id, envelope_json FROM training_revisions"
                " WHERE rowid IN (SELECT MAX(rowid) FROM"
                f" training_revisions WHERE example_id IN ({marks})"
                " GROUP BY example_id)", example_ids).fetchall():
            state, job_id, published = rows.get(ex_id, (None, None, 0))
            env = json.loads(payload)
            if env.get("origin") not in (None, "live_capture"):
                continue  # synthetic/legacy corpus material is not the
                # user's speech
            raw = ev.qualify(conn, (env.get("artifact_ids") or {}).get(
                "source_text"), "source_text", job_id=job_id) \
                if state in _LIVE_STATES else {"ok": False}
            # Not live, or absent, purged, foreign or wrong-stage text:
            # kept as a blocker for its job, never counted.
            ok = raw["ok"]
            snippets = bool(((env.get("normalization") or {})
                             .get("snippets") or {}).get("expansions"))
            attempt = env.get("attempt")
            out.append((ex_id, env, raw["artifact"]["text"] if ok else None,
                        snippets, raw["artifact"]["id"] if ok else None,
                        env.get("revision_id"),
                        job_id or ex_id,
                        state,
                        (attempt if isinstance(attempt, int)
                         and not isinstance(attempt, bool) else 0,
                         published or 0)))
        return out

    def _eligible(self, labels: dict):
        """Live examples with their own retained raw transcript — ONE
        per logical job: a retry is the same capture spoken once, so of
        a job's attempts only the latest (ties: the latest published),
        whatever its state, speaks for it — when that one is excluded,
        quarantined, expired or has lost its transcript the job
        contributes nothing — and the others count as
        ``superseded_attempt`` (xm-policy-r1 D07; they stay inspectable
        as training evidence).
        Then minus what S22 says is not the user's own speech: examples
        whose normalization expanded snippets (generated text), examples
        whose current review label flags background speech, and
        verbatim repeats of an earlier utterance (test phrases said over
        and over count once). An excluded contribution never falls back
        to an older attempt. Reads in bounded chunks — each a short
        writer op, so a dictation's store writes interleave instead of
        queueing behind the whole history (S29.16). Returns (eligible,
        excluded counts, the exact inputs read)."""
        # Every example of a job that has a live one: the job's latest
        # attempt is chosen among ALL its attempts, whatever their state.
        live = self.store.submit(lambda conn: [r[0] for r in conn.execute(
            "SELECT example_id FROM training_examples WHERE state IN"
            f" ({','.join('?' * len(_LIVE_STATES))}) OR job_id IN"
            " (SELECT job_id FROM training_examples WHERE state IN"
            f" ({','.join('?' * len(_LIVE_STATES))})) ORDER BY"
            " example_id", (*_LIVE_STATES, *_LIVE_STATES)).fetchall()])
        rows = []
        for i in range(0, len(live), _READ_CHUNK):
            chunk = live[i:i + _READ_CHUNK]
            rows += self.store.submit(
                lambda conn, ch=chunk: self._read_candidates(conn, ch))
        excluded = {"superseded_attempt": 0, "snippet_expanded": 0,
                    "background_speech": 0, "repeated_verbatim": 0}
        inputs = {}
        per_job = {}
        for (ex_id, env, text, snippets, raw_aid, rev, job, state,
             order) in rows:
            if text is not None:
                inputs[ex_id] = (raw_aid, rev)
            best = per_job.get(job)
            if best is None or order > best[-1]:
                per_job[job] = (ex_id, env, text, snippets, state, order)
        # Counted attempts that are not their job's contribution.
        excluded["superseded_attempt"] = len(inputs) - sum(
            1 for c in per_job.values() if c[2] is not None)
        for ex_id, _env, text, _sn, state, _order in per_job.values():
            if text is None:
                # A blocking latest attempt is an input too: the fence
                # restarts when its state changes (review R2-09).
                inputs[ex_id] = (None, state)
        kept = []
        for ex_id, env, text, snippets, _state, _order in per_job.values():
            if text is None:
                continue  # the latest attempt is not countable: the job
                # contributes nothing
            if snippets:
                excluded["snippet_expanded"] += 1
            elif "background_speech" in (labels.get(ex_id)
                                         or (None, []))[1]:
                excluded["background_speech"] += 1
            else:
                kept.append((ex_id, env, text))
        kept.sort(key=lambda r: (r[1].get("captured_at_utc") or "", r[0]))
        seen = set()
        out = []
        for ex_id, env, text in kept:
            key = " ".join(_WORD_RE.findall(text.lower()))
            if key in seen:
                excluded["repeated_verbatim"] += 1
                continue
            seen.add(key)
            out.append((ex_id, env, text))
        return out, excluded, inputs

    def _input_signature(self, conn) -> str:
        """A cheap fingerprint of everything that can change a profile
        — revisions, example states, purges, labels, exclusions, usage,
        vocabulary, the floor and algorithm — read from counters, maxima
        and content-free rows only, never from transcript text."""
        parts = [
            list(conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM"
                " training_revisions").fetchone()),
            [list(r) for r in conn.execute(
                "SELECT state, COUNT(*), COALESCE(MAX(updated_at_utc), '')"
                " FROM training_examples GROUP BY state ORDER BY state"
            ).fetchall()],
            conn.execute("SELECT COUNT(*) FROM artifacts WHERE purged=1"
                         ).fetchone()[0],
            _labels_digest(conn),
            _exclusions_digest(conn),
            # M13's usage revision moves on EVERY usage mutation (a
            # retry that only changed a mode, an explicit transform, a
            # deletion) — never only on dictation totals (M13 C228/C229).
            conn_usage_revision(conn),
            _vocabulary_revision(conn),
            list(conn.execute(
                "SELECT COUNT(*), TOTAL(usage_count), TOTAL(revision)"
                " FROM vocabulary_entries WHERE approved=1 AND"
                " enabled=1").fetchone()),
            self.min_words, ALGORITHM_VERSION]
        return ids.sha256_text(json.dumps(parts, sort_keys=True))

    def _excluded_evidence(self, conn) -> set[str]:
        """Durable evidence exclusions carried forward by example id."""
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT example_id FROM profile_evidence WHERE"
            " included=0").fetchall()}

    # ---- compute (a record, never a cache) ------------------------------------

    def compute(self, *, only_if_changed: bool = False) -> dict:
        """Compute a new snapshot. Evidence is read in bounded chunks
        and counted off the writer; one short write op then re-checks
        every input it read — each example still live at the same
        revision with its raw transcript retained, the labels and the
        exclusions unchanged (a change during the read restarts the
        computation — deleted or purged speech never lands in a
        snapshot, D16) — and records the snapshot. ``only_if_changed``
        (the idle pass) returns ``{"skipped": True, ...}`` when the
        current snapshot was computed from exactly the same evidence —
        snapshots are records, so an unchanged idle tick adds none."""
        for _attempt in range(3):
            out = self._compute_once(only_if_changed)
            if not out.get("stale"):
                break
        else:
            raise RuntimeError("profile evidence kept changing")
        if out.get("skipped"):
            return out
        self.emit("profile.snapshot_computed", level="INFO",
                  reason_code=f"v{ALGORITHM_VERSION}",
                  detail=f"words={out['measured']['eligible_words']}"
                         f" cards={len(out['cards'])}")
        return out

    def _compute_once(self, only_if_changed: bool) -> dict:
        self.store.submit(_scrub_dead_evidence)
        quick = self.store.submit(self._input_signature)
        if only_if_changed:
            last = self.store.submit(lambda conn: conn.execute(
                "SELECT snapshot_id, state, measured_json FROM"
                " profile_snapshots ORDER BY rowid DESC LIMIT 1"
            ).fetchone())
            if last and last[1] == "current" and json.loads(
                    last[2]).get("input_signature") == quick:
                # Nothing that feeds the profile has changed since the
                # current snapshot: decided without reading any text.
                return {"skipped": True, "snapshot_id": last[0]}
        labels_seen = self.store.submit(_labels_digest)
        labels = self.store.submit(_latest_labels)
        user_excluded = self.store.submit(self._excluded_evidence)
        candidates, excluded, inputs = self._eligible(labels)
        eligible = [(ex, env, text) for ex, env, text in candidates
                    if ex not in user_excluded]
        excluded["user_excluded"] = len(candidates) - len(eligible)
        eligible_ids = {ex for ex, _env, _t in eligible}
        words_total = sum(len(t.split()) for _e, _env, t in eligible)
        lengths = {ex: len(t.split()) for ex, _env, t in eligible}
        # Frequent phrases: 2- and 3-word n-grams over non-stopword
        # anchors, counted per example (an example never pads a phrase
        # it already contributed).
        phrase_counts: dict[str, list[str]] = {}
        for ex, _env, text in eligible:
            tokens = [w.lower().strip(".,!?;:\"'()") for w in text.split()]
            tokens = [w for w in tokens if w]
            seen = set()
            for n in (2, 3):
                for i in range(len(tokens) - n + 1):
                    gram = tokens[i:i + n]
                    if all(w in _STOPWORDS for w in gram):
                        continue
                    key = " ".join(gram)
                    if key in seen:
                        continue
                    seen.add(key)
                    phrase_counts.setdefault(key, []).append(ex)
        phrases = sorted(
            ((k, v) for k, v in phrase_counts.items() if len(v) >= 2),
            key=lambda kv: (-len(kv[1]), kv[0]))[:_PHRASE_TOP]
        # Corrections by kind: each eligible example's CURRENT reviewed
        # label (label revisions append; only the latest opinion
        # counts, and an abstained one counts as none).
        label_examples: dict[str, list[str]] = {}
        for ex in sorted(eligible_ids):
            kind, _domains = labels.get(ex) or (None, [])
            if kind:
                label_examples.setdefault(kind, []).append(ex)
        label_kinds = {k: len(v) for k, v in label_examples.items()}
        # Spoken self-corrections ("no wait, I mean …") the cleanup stage
        # detected — counted only over dictations whose cleanup recorded
        # the count (older or V1-path jobs are not zero, just unknown).
        with_count = [((env.get("cleanup") or {}).get("v2") or {})
                      .get("corrections") for _e, env, _t in eligible]
        with_count = [c for c in with_count if isinstance(c, dict)]
        self_corrections = {
            "dictations_with": sum(1 for c in with_count
                                   if c.get("applied")),
            "applied": sum(int(c.get("applied") or 0)
                           for c in with_count),
            "denominator": len(with_count),
            "definition": "eligible dictations whose cleanup detected at"
                          " least one spoken self-correction, over those"
                          " whose cleanup recorded the count"}
        # Technical terms (D04): approved rules APPLIED in eligible
        # speech, each citing the dictations that applied it.
        rule_examples: dict[str, list[str]] = {}
        for ex, env, _t in sorted(eligible, key=lambda r: r[0]):
            for rid in sorted(set(((env.get("normalization") or {})
                                   .get("vocabulary") or {})
                                  .get("applied_rule_ids") or [])):
                rule_examples.setdefault(rid, []).append(ex)
        captured = [env.get("captured_at_utc") for _e, env, _t in eligible
                    if env.get("captured_at_utc")]
        coverage = [min(captured) if captured else None,
                    max(captured) if captured else None]
        length_values = list(lengths.values())
        median = statistics.median(length_values) if length_values \
            else None
        enough = words_total >= self.min_words and len(eligible) >= 10

        def write(conn):
            # The exact-input fence (D16): everything the computation
            # read must still hold, or it restarts.
            for ex in eligible_ids | set(inputs):
                raw_aid, rev = inputs[ex]
                row = conn.execute(
                    "SELECT state, latest_revision_id, job_id FROM"
                    " training_examples WHERE example_id=?",
                    (ex,)).fetchone()
                if raw_aid is None:
                    # A job's blocking latest attempt, read in state
                    # ``rev``: any change may change what the job counts.
                    if row is None or row[0] != rev:
                        return {"stale": True}
                    continue
                if row is None or row[0] not in _LIVE_STATES:
                    return {"stale": True}  # evidence died during the read
                if rev and row[1] and row[1] != rev:
                    return {"stale": True}
                if not ev.qualify(conn, raw_aid, "source_text",
                                  job_id=row[2])["ok"]:
                    return {"stale": True}
            if _labels_digest(conn) != labels_seen or \
                    self._excluded_evidence(conn) != user_excluded:
                return {"stale": True}
            signature = ids.sha256_text(json.dumps({
                "examples": sorted((ex, env.get("revision_id") or "")
                                   for ex, env, _t in eligible),
                "user_excluded": sorted(user_excluded),
                "labels": labels_seen,
                "usage": conn_usage_revision(conn),
                "vocabulary": [_vocabulary_revision(conn)] + list(
                    conn.execute(
                        "SELECT COUNT(*), TOTAL(usage_count) FROM"
                        " vocabulary_entries WHERE approved=1 AND"
                        " enabled=1").fetchone()),
                "min_words": self.min_words,
                "algorithm": ALGORITHM_VERSION}, sort_keys=True))
            if only_if_changed:
                last = conn.execute(
                    "SELECT snapshot_id, state, measured_json FROM"
                    " profile_snapshots ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                if last and last[1] == "current" and json.loads(
                        last[2]).get("evidence_signature") == signature:
                    # Store metadata moved but the evidence did not:
                    # remember the new metadata so the next idle tick
                    # decides without reading (bookkeeping, not content).
                    conn.execute(
                        "UPDATE profile_snapshots SET measured_json="
                        "json_set(measured_json, '$.input_signature', ?)"
                        " WHERE snapshot_id=?", (quick, last[0]))
                    return {"skipped": True, "snapshot_id": last[0]}
            hits = conn.execute(
                "SELECT COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' AND dictionary_hits > 0").fetchone()[0]
            # The current dictionary decides which rules count (approved
            # and enabled now); the NAME is the canonical frozen in each
            # dictation's own applied-rules record — what that speech
            # actually applied, never today's spelling (xm-policy-r1
            # D11, MERGED-X11). A rule without a qualifiable record is
            # omitted rather than relabeled.
            active = {r[0] for r in conn.execute(
                "SELECT entry_id FROM vocabulary_entries WHERE"
                " approved=1 AND enabled=1").fetchall()}
            envs = {ex: env for ex, env, _t in eligible}
            applied_names: dict = {}
            terms: dict[tuple, list[str]] = {}
            unrecorded = set()
            for rid, exs in rule_examples.items():
                if rid not in active:
                    continue
                for ex in exs:
                    if ex not in applied_names:
                        applied_names[ex] = _applied_canonicals(
                            conn, ex, envs[ex])
                    name = applied_names[ex].get(rid)
                    if name:
                        terms.setdefault((rid, name), []).append(ex)
                    else:
                        unrecorded.add(ex)
            used = sorted(terms.items(),
                          key=lambda p: (-len(p[1]), p[0][1]))[:_TERM_TOP]
            technical = [{"term": name, "dictations": len(exs),
                          "example_ids": exs[:5]}
                         for (_rid, name), exs in used]
            recorded_use = [
                r[0] for r in conn.execute(
                    "SELECT canonical FROM vocabulary_entries WHERE"
                    " approved=1 AND enabled=1 AND usage_count > 0"
                    " ORDER BY usage_count DESC LIMIT 10").fetchall()]
            # App usage and local hour-of-day from usage facts (private
            # usage metadata — stays store-side and in the local UI).
            app_counts = dict(conn.execute(
                "SELECT app_name, COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' AND app_name IS NOT NULL GROUP BY"
                " app_name ORDER BY COUNT(*) DESC LIMIT 8").fetchall())
            hours = [0] * 24
            hours_unknown = 0
            for inst, offset in conn.execute(
                    "SELECT activity_at_utc, utc_offset_minutes FROM"
                    " usage_facts WHERE kind='dictation'").fetchall():
                h = _local_hour(inst, offset)
                if h is None:
                    hours_unknown += 1
                else:
                    hours[h] += 1
            mode_counts = dict(conn.execute(
                "SELECT mode, COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' AND mode IS NOT NULL GROUP BY"
                " mode").fetchall())
            # Requested output structures: which transforms the user
            # asks for — explicit runs and auto-applied dictation
            # transforms counted separately (usage facts, M13).
            requested = {"explicit": dict(conn.execute(
                "SELECT transform_id, COUNT(*) FROM usage_facts WHERE"
                " kind='transform' AND transform_id IS NOT NULL GROUP BY"
                " transform_id ORDER BY COUNT(*) DESC LIMIT 10"
            ).fetchall()), "auto_applied": dict(conn.execute(
                "SELECT transform_id, COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' AND transform_id IS NOT NULL GROUP BY"
                " transform_id ORDER BY COUNT(*) DESC LIMIT 10"
            ).fetchall())}
            note = None if enough else (
                f"measured totals only — {words_total} eligible words"
                f" over {len(eligible)} dictations is below the"
                f" {self.min_words}-word / 10-dictation interpretation"
                " floor (S22: more examples needed, not a fabricated"
                " profile)")
            measured = {
                "eligible_examples": len(eligible),
                "eligible_words": words_total,
                "excluded": excluded,
                "utterance_words": {
                    "mean": round(statistics.fmean(length_values), 1)
                    if length_values else None,
                    "median": median,
                },
                "frequent_phrases": [
                    {"phrase": p, "count": len(exs),
                     "example_ids": exs[:5]} for p, exs in phrases],
                "corrections_by_kind": label_kinds,
                "dictionary_hit_examples": hits,
                "technical_terms": technical,
                "technical_terms_source": "approved dictionary rules"
                                          " applied in eligible"
                                          " dictations (each cites"
                                          " them), named as spelled"
                                          " when applied",
                "technical_terms_unrecorded": {
                    "dictations": len(unrecorded),
                    "reason": "applied spelling not recorded for these"
                              " dictations"},
                "dictionary_terms_with_recorded_use": recorded_use,
                "dictionary_terms_source": "independent dictionary usage"
                                           " counters over all"
                                           " dictations — not evidence"
                                           " of this speech; not cleared"
                                           " by Delete Usage"
                                           " (analytics.md)",
                "app_usage": app_counts,
                "hour_histogram": hours,
                "hour_note": "local hour of each dictation (its recorded"
                             " UTC offset); dictations without an offset"
                             " are counted in hours_unknown",
                "hours_unknown": hours_unknown,
                "modes": mode_counts,
                "self_corrections": self_corrections,
                "requested_transforms": requested,
                "sources": {
                    "speech": "eligible live examples' own raw"
                              " transcripts",
                    "usage": "usage facts (M13) — every dictation"},
                "min_words_threshold": self.min_words,
                "evidence_signature": signature,
                "input_signature": quick,
                "interpretive_note": note,
            }
            cards = []
            if enough:
                if median is not None:
                    style = ("concise" if median <= 12
                             else "long-form" if median >= 40
                             else "mid-length")
                    # The utterances nearest the median support it.
                    nearest = sorted(
                        lengths, key=lambda e: (abs(lengths[e] - median),
                                                e))[:5]
                    cards.append({
                        "card_id": "style-length",
                        "kind": "interpretive",
                        "title": f"{style} utterances",
                        "statement": f"Median dictation runs {median:g}"
                                     " words — interpreted from"
                                     f" {len(eligible)} eligible"
                                     " utterances.",
                        "evidence_example_ids": nearest,
                        "coverage": coverage,
                    })
                if label_kinds:
                    top = max(sorted(label_kinds), key=label_kinds.get)
                    reviewed = sum(label_kinds.values())
                    cards.append({
                        "card_id": "correction-focus",
                        "kind": "interpretive",
                        "title": "Reviewed corrections are mostly"
                                 f" {top.replace('_', ' ')}",
                        "statement": f"{label_kinds[top]} of {reviewed}"
                                     " reviewed eligible dictations carry"
                                     " this label — an observation of"
                                     " reviewed labels, not a population"
                                     " rate.",
                        "evidence_example_ids": label_examples[top][:5],
                        "coverage": coverage,
                    })
                if technical:
                    applied = sorted({ex for _rid, exs in used
                                      for ex in exs})
                    cards.append({
                        "card_id": "technical-vocabulary",
                        "kind": "interpretive",
                        "title": "Technical vocabulary in daily use",
                        "statement": f"{len(technical)} approved"
                                     " dictionary terms were applied in"
                                     f" {len(applied)} eligible"
                                     " dictations.",
                        "evidence_example_ids": applied[:5],
                        "coverage": coverage,
                    })
            now = ids.now_utc_iso()
            snapshot_id = ids.new_id("prof")
            conn.execute(
                "INSERT INTO profile_snapshots(snapshot_id,"
                " algorithm_version, computed_at_utc, eligible_words,"
                " measured_json, cards_json, state, source_example_count,"
                " coverage_from_utc, coverage_to_utc)"
                " VALUES(?,?,?,?,?,?, 'current', ?, ?, ?)",
                (snapshot_id, ALGORITHM_VERSION, now, words_total,
                 json.dumps(measured, ensure_ascii=False, sort_keys=True),
                 json.dumps(cards, ensure_ascii=False, sort_keys=True),
                 len(eligible), coverage[0], coverage[1]))
            conn.executemany(
                "INSERT OR IGNORE INTO profile_evidence(snapshot_id,"
                " example_id, card_id, role, included) VALUES(?,?,?,?,1)",
                [(snapshot_id, ex, "measured", "measured")
                 for ex in sorted(eligible_ids)]
                + [(snapshot_id, ex, card["card_id"], "card_example")
                   for card in cards
                   for ex in card["evidence_example_ids"]])
            return {
                "snapshot_id": snapshot_id,
                "algorithm_version": ALGORITHM_VERSION,
                "measured": measured,
                "cards": cards,
                "interpretive_available": enough,
                "interpretive_note": note,
                "coverage": coverage,
            }
        return self.store.submit(write)

    # ---- reads ---------------------------------------------------------------

    def current(self) -> dict | None:
        """The latest snapshot with its honest state. Every evidence
        example must still be live with its raw transcript retained;
        when one expired, was deleted or purged the snapshot is marked
        invalidated AND its text-bearing content (phrases, cards) is
        cleared — derived text never outlives its source (S29.14,
        M14-AC03). The UI shows the reason until the next generation."""
        def op(conn):
            row = conn.execute(
                "SELECT snapshot_id, algorithm_version, computed_at_utc,"
                " measured_json, cards_json, state, invalidated_reason,"
                " source_example_count, coverage_from_utc,"
                " coverage_to_utc FROM profile_snapshots ORDER BY rowid"
                " DESC LIMIT 1").fetchone()
            if row is None:
                return None
            if _scrub_dead_evidence(conn):
                row = conn.execute(
                    "SELECT snapshot_id, algorithm_version,"
                    " computed_at_utc, measured_json, cards_json, state,"
                    " invalidated_reason, source_example_count,"
                    " coverage_from_utc, coverage_to_utc FROM"
                    " profile_snapshots ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
            (snapshot_id, version, computed, measured_raw, cards_raw,
             state, reason, n_examples, cov_from, cov_to) = row
            return {
                "snapshot_id": snapshot_id, "algorithm_version": version,
                "computed_at_utc": computed,
                "measured": json.loads(measured_raw),
                "cards": json.loads(cards_raw), "state": state,
                "invalidated_reason": reason,
                "source_example_count": n_examples,
                "coverage": [cov_from, cov_to],
            }
        return self.store.submit(op)

    def exclude_evidence(self, snapshot_id: str, example_id: str) -> str:
        """Remove one supporting example from a snapshot's evidence
        (S22 'edit, exclude or delete'). The exclusion is durable and
        carries into future snapshots (never silently re-included), and
        EVERY snapshot that still presents that example as support
        invalidates — excluding through an older rendered snapshot also
        retires a newer current one built from the same evidence
        (corpus S034)."""

        def op(conn):
            now = ids.now_utc_iso()
            changed = conn.execute(
                "UPDATE profile_evidence SET included=0, excluded_at_utc=?"
                " WHERE snapshot_id=? AND example_id=? AND included=1",
                (now, snapshot_id, example_id)).rowcount
            if not changed:
                # Not this snapshot's evidence (or already excluded):
                # nothing durable would be recorded, so say so.
                return "not_evidence"
            conn.execute(
                "UPDATE profile_evidence SET included=0, excluded_at_utc=?"
                " WHERE example_id=? AND included=1", (now, example_id))
            conn.execute(
                "UPDATE profile_snapshots SET state='invalidated',"
                " invalidated_reason='evidence_excluded' WHERE"
                " state='current' AND snapshot_id IN (SELECT snapshot_id"
                " FROM profile_evidence WHERE example_id=?)",
                (example_id,))
            return "excluded"
        out = self.store.submit(op)
        if out == "not_evidence":
            raise ValueError("not_evidence_of_this_snapshot")
        self.emit("profile.evidence_excluded", level="INFO",
                  reason_code="user_action")
        return out
