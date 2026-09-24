"""Your Voice — the local communication profile (V2 M14, Spec S22,
contract profile.md).

Measured views are computed from ELIGIBLE evidence only: live V2
examples' RAW transcripts (the speech, not Qwen's cleaned output —
S22: never learn the cleanup model's style as the user's), usage
facts for app/time patterns, correction labels and dictionary hits.
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
recomputes from the current store. Any snapshot whose evidence died
(delete-everywhere, expiry, exclusion from training) is invalidated and
loses its text-bearing content — phrases and cards never outlive their
source. User-excluded evidence links carry forward to future snapshots
by example id. Nothing here ever feeds the dictation
pipeline: no cleanup prompt, context or vocabulary path reads a
profile snapshot (M14-AC04 — pinned by test).
"""

from __future__ import annotations

import json
import re
import statistics

from . import ids
from .store import TRAINABLE_STATES, Store

ALGORITHM_VERSION = 1
DEFAULT_MIN_WORDS = 2000
_PHRASE_TOP = 12
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
    None when either is missing (a UTC hour is not a time of day)."""
    if not iso_utc or len(iso_utc) < 16 or offset_minutes is None:
        return None
    try:
        minutes = int(iso_utc[11:13]) * 60 + int(iso_utc[14:16])
    except ValueError:
        return None
    return ((minutes + int(offset_minutes)) // 60) % 24


# Why a snapshot's evidence stopped being usable, by the example's state.
_DEAD_REASONS = {"deleted": "source_deleted", "expired": "evidence_expired",
                 "excluded": "evidence_excluded_from_training",
                 "quarantined_sensitive": "evidence_quarantined"}


def _scrub_dead_evidence(conn) -> int:
    """Invalidate every snapshot — current or historical — that drew on
    an example no longer eligible (deleted, expired, excluded,
    quarantined), clearing its text-bearing content: derived phrases
    and cards never outlive their source (S29.14). The reason names
    what happened to the evidence. Returns the number scrubbed."""
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
    for snapshot_id, reason in reasons.items():
        conn.execute(
            "UPDATE profile_snapshots SET invalidated_reason=CASE WHEN"
            " state='current' THEN ? ELSE invalidated_reason END,"
            " state='invalidated', measured_json='{}', cards_json='[]'"
            " WHERE snapshot_id=?", (reason, snapshot_id))
    return len(reasons)


def _latest_labels(conn) -> dict:
    """example_id → (edit_kind, domains) of its CURRENT reviewed label —
    the latest revision; an abstained latest revision counts as no
    label (the reviewer's current opinion is uncertainty)."""
    out = {}
    for ex, kind, domains, abstained in conn.execute(
            "SELECT l.example_id, l.edit_kind, l.domains_json,"
            " l.abstained FROM correction_labels l WHERE l.revision ="
            " (SELECT MAX(m.revision) FROM correction_labels m WHERE"
            " m.example_id = l.example_id)").fetchall():
        if not abstained:
            out[ex] = (kind, json.loads(domains or "[]"))
    return out


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
        """One bounded read: the live examples among ``example_ids``
        with a retained raw transcript, as (example_id, envelope, raw
        text, snippet_expanded)."""
        marks = ",".join("?" * len(example_ids))
        states = dict(conn.execute(
            "SELECT example_id, state FROM training_examples WHERE"
            f" example_id IN ({marks})", example_ids).fetchall())
        out = []
        for ex_id, payload in conn.execute(
                "SELECT example_id, envelope_json FROM training_revisions"
                " WHERE rowid IN (SELECT MAX(rowid) FROM"
                f" training_revisions WHERE example_id IN ({marks})"
                " GROUP BY example_id)", example_ids).fetchall():
            if states.get(ex_id) not in _LIVE_STATES:
                continue
            env = json.loads(payload)
            if env.get("origin") not in (None, "live_capture"):
                continue  # synthetic/legacy corpus material is not the
                # user's speech
            raw_aid = (env.get("artifact_ids") or {}).get("source_text")
            if not raw_aid:
                continue
            row = conn.execute(
                "SELECT content_text, purged FROM artifacts WHERE"
                " artifact_id=?", (raw_aid,)).fetchone()
            if row is None or row[1] or row[0] is None:
                continue
            snippets = bool(((env.get("normalization") or {})
                             .get("snippets") or {}).get("expansions"))
            out.append((ex_id, env, row[0], snippets))
        return out

    def _eligible(self, labels: dict):
        """Live examples with a retained raw transcript, minus what S22
        says is not the user's own speech: examples whose normalization
        expanded snippets (generated text), examples whose current
        review label flags background speech, and verbatim repeats of
        an earlier utterance (test phrases said over and over count
        once). Reads in bounded chunks — each a short writer op, so a
        dictation's store writes interleave instead of queueing behind
        the whole history (S29.16). Returns (eligible, excluded
        counts)."""
        live = self.store.submit(lambda conn: [r[0] for r in conn.execute(
            "SELECT example_id FROM training_examples WHERE state IN"
            f" ({','.join('?' * len(_LIVE_STATES))}) ORDER BY"
            " example_id", _LIVE_STATES).fetchall()])
        rows = []
        for i in range(0, len(live), _READ_CHUNK):
            chunk = live[i:i + _READ_CHUNK]
            rows += self.store.submit(
                lambda conn, ch=chunk: self._read_candidates(conn, ch))
        excluded = {"snippet_expanded": 0, "background_speech": 0,
                    "repeated_verbatim": 0}
        kept = []
        for ex_id, env, text, snippets in rows:
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
        return out, excluded

    def _excluded_evidence(self, conn) -> set[str]:
        """Durable evidence exclusions carried forward by example id."""
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT example_id FROM profile_evidence WHERE"
            " included=0").fetchall()}

    # ---- compute (a record, never a cache) ------------------------------------

    def compute(self, *, only_if_changed: bool = False) -> dict:
        """Compute a new snapshot. Evidence is read in bounded chunks
        and counted off the writer; one short write op then re-checks
        that every evidence example is still live (a deletion during
        the read restarts the computation — deleted speech never lands
        in a snapshot) and records the snapshot. ``only_if_changed``
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
        labels = self.store.submit(_latest_labels)
        user_excluded = self.store.submit(self._excluded_evidence)
        candidates, excluded = self._eligible(labels)
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
        vocab_examples = sorted(
            ex for ex, env, _t in eligible
            if ((env.get("normalization") or {}).get("vocabulary")
                or {}).get("applied_rule_ids"))
        captured = [env.get("captured_at_utc") for _e, env, _t in eligible
                    if env.get("captured_at_utc")]
        coverage = [min(captured) if captured else None,
                    max(captured) if captured else None]
        length_values = list(lengths.values())
        median = statistics.median(length_values) if length_values \
            else None
        enough = words_total >= self.min_words and len(eligible) >= 10

        def write(conn):
            live_now = {r[0] for r in conn.execute(
                "SELECT example_id FROM training_examples WHERE state IN"
                f" ({','.join('?' * len(_LIVE_STATES))})",
                _LIVE_STATES).fetchall()}
            if not eligible_ids <= live_now:
                return {"stale": True}  # evidence died during the read
            signature = ids.sha256_text(json.dumps({
                "examples": sorted((ex, env.get("revision_id") or "")
                                   for ex, env, _t in eligible),
                "user_excluded": sorted(user_excluded),
                "labels": list(conn.execute(
                    "SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM"
                    " correction_labels").fetchone()),
                "usage": list(conn.execute(
                    "SELECT COUNT(*), TOTAL(raw_words),"
                    " COALESCE(MAX(activity_at_utc), '') FROM"
                    " usage_facts WHERE kind='dictation'").fetchone()),
                "vocabulary": list(conn.execute(
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
                    return {"skipped": True, "snapshot_id": last[0]}
            hits = conn.execute(
                "SELECT COUNT(*) FROM usage_facts WHERE"
                " kind='dictation' AND dictionary_hits > 0").fetchone()[0]
            dict_hit_terms = [
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
                "technical_terms": dict_hit_terms,
                "app_usage": app_counts,
                "hour_histogram": hours,
                "hour_note": "local hour of each dictation (its recorded"
                             " UTC offset); dictations without an offset"
                             " are counted in hours_unknown",
                "hours_unknown": hours_unknown,
                "modes": mode_counts,
                "sources": {
                    "speech": "eligible live examples' raw transcripts",
                    "usage": "usage facts (M13) — every dictation"},
                "min_words_threshold": self.min_words,
                "evidence_signature": signature,
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
                if dict_hit_terms and vocab_examples:
                    cards.append({
                        "card_id": "technical-vocabulary",
                        "kind": "interpretive",
                        "title": "Technical vocabulary in daily use",
                        "statement": f"{len(dict_hit_terms)} approved"
                                     " dictionary terms have recorded"
                                     f" use; {len(vocab_examples)}"
                                     " eligible dictations applied one.",
                        "evidence_example_ids": vocab_examples[:5],
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
        example must still be live; when one expired or was deleted the
        snapshot is marked invalidated AND its text-bearing content
        (phrases, cards) is cleared — derived text never outlives its
        source (S29.14, M14-AC03). The UI shows the reason until the
        next generation."""
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
        (S22 'edit, exclude or delete'). The snapshot invalidates —
        cards must regenerate without it; the exclusion is durable and
        carries into future snapshots (never silently re-included)."""

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
                "UPDATE profile_snapshots SET state='invalidated',"
                " invalidated_reason='evidence_excluded' WHERE"
                " snapshot_id=? AND state='current'",
                (snapshot_id,))
            return "excluded"
        out = self.store.submit(op)
        if out == "not_evidence":
            raise ValueError("not_evidence_of_this_snapshot")
        self.emit("profile.evidence_excluded", level="INFO",
                  reason_code="user_action")
        return out
