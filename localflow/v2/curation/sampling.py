"""Review sampling: the seeded representative stream and the hard-
example queue (V2 M14, Spec S29.9, E19.4).

Two connected queues, one decision ledger:

- **Representative stream** — a deterministic seeded Bernoulli draw
  over eligible live jobs. Same seed + same policy ⇒ same inclusions;
  the known probability (percent/100) is recorded per decision. A job
  is drawn at most once under a policy — reruns only draw for new
  jobs.
- **Hard-example queue** — deterministic triggers derived from what
  the envelope actually records (explicit incorrect marks, retries,
  validator rejections, fallbacks, short utterances, capture
  discontinuities, transform needs_review) plus a linked correction
  candidate. Triggers propose review priority; they never establish
  truth. Explicit user signals (an incorrect mark, a taught
  correction) form the ``explicit`` stratum; the rest ``hard_trigger``.
  Multiple triggers on one job collapse into ONE decision row with
  every reason listed — duplicate job records never mint duplicate
  examples (M14-AC06).
- **Late triggers** — triggers usually arrive after the first draw (a
  mark in the Hub, a retry, a correction). A not-included example that
  later gains one gets exactly one more decision (reason
  ``late_trigger:…``); the Bernoulli draw itself is never repeated,
  and an example is included at most once per policy.
- **Supplemental stratum** — short/noisy and multilingual examples
  beyond the Bernoulli (the documented underrepresented quota, S29.9).

Verified positives, unreviewed cases and hard-mined failures stay
separate: each decision row carries its stratum and reason set, and
the coverage report counts them independently. An unedited job in the
random sample is UNLABELED — inclusion never implies a positive.
"""

from __future__ import annotations

import hashlib
import json

from .. import ids
from ..store import LIVE_EXAMPLE_STATES, Store

DEFAULT_POLICY = "m14_review_sampling_v1"
DEFAULT_SEED = "localflow-m14-review-v1"
DEFAULT_PERCENT = 10.0
SHORT_UTTERANCE_SEC = 3.0

STRATA = ("representative", "hard_trigger", "explicit", "supplemental",
          "not_included")

_LIVE_STATES = LIVE_EXAMPLE_STATES


def _draw(seed: str, key: str) -> float:
    """Deterministic uniform [0,1) from (seed, key) — the recorded
    policy/seed make every inclusion reproducible."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(2 ** 64)


def hard_trigger_reasons(env: dict) -> list[str]:
    """The deterministic hard triggers derivable from one envelope.
    Contextual disagreement and low calibrated confidence have no
    producer yet (no comparator until M15, no calibrated scores at
    all) — absent facts are absent, never faked triggers."""
    reasons = []
    outcome = env.get("outcome") or {}
    if outcome.get("correctness") == "incorrect":
        reasons.append("explicit_incorrect")
    if (env.get("attempt") or 1) > 1:
        reasons.append("retry")
    cleanup = env.get("cleanup") or {}
    fallback = cleanup.get("fallback_reason")
    if fallback:
        reasons.append("cleanup_fallback")
    validation = ((cleanup.get("v2") or {}).get("validation")) or {}
    if any(v is False for v in validation.values()
           if isinstance(v, (bool,))):
        reasons.append("validator_rejection")
    capture = env.get("capture") or {}
    try:
        if capture.get("duration_sec") is not None \
                and float(capture["duration_sec"]) <= SHORT_UTTERANCE_SEC:
            reasons.append("short_utterance")
    except (TypeError, ValueError):
        pass
    if capture.get("journal_dropped_blocks") or capture.get("incomplete_tail"):
        reasons.append("capture_discontinuity")
    transform = env.get("transform") or {}
    if isinstance(transform, dict) and transform.get("path") == "needs_review":
        reasons.append("transform_needs_review")
    return reasons


def _triggered(env: dict, candidate_sources) -> tuple[str, list[str]] | None:
    """(stratum, reasons) when the example must be reviewed, else None.
    Explicit user signals — an incorrect mark or a taught correction —
    are the ``explicit`` stratum; everything else that triggers is
    ``hard_trigger``."""
    reasons = hard_trigger_reasons(env)
    sources = candidate_sources or set()
    if sources:
        reasons.append("correction_candidate")
    if not reasons:
        return None
    explicit = "explicit_incorrect" in reasons \
        or "explicit_teach" in sources
    return ("explicit" if explicit else "hard_trigger"), reasons


def _is_multilingual(env: dict) -> bool:
    """Derived from the envelope's own recorded language fields only —
    honest and cheap; no transcript text is read for the quota."""
    recognition = env.get("recognition") or {}
    lang = recognition.get("language") or recognition.get(
        "language_hint") or recognition.get("detected_language")
    return bool(lang and lang not in ("en", "eng", "en-US", "en_US"))


class SamplingService:
    """Decision mining over live examples (one writer op per refresh).
    ``percent`` is the representative stream's configured default (the
    ``review_sample_percent`` knob)."""

    def __init__(self, store: Store, emit=None, *,
                 percent: float = DEFAULT_PERCENT):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)
        self.percent = float(percent)

    def refresh(self, *, policy: str = DEFAULT_POLICY,
                seed: str = DEFAULT_SEED,
                percent: float | None = None) -> dict:
        """Draw the stream for undecided eligible examples and record
        every decision. Explicit/hard triggers always include; the
        Bernoulli covers the rest; supplemental adds underrepresented
        strata; a not-included example that has since gained a trigger
        gets one late decision. Included unreviewed examples move to
        ``review_candidate`` — the state review owes attention to."""
        percent = self.percent if percent is None else float(percent)

        def op(conn):
            decided: dict[str, set] = {}
            for ex_id, stratum in conn.execute(
                    "SELECT example_id, stratum FROM sampling_decisions"
                    " WHERE policy=?", (policy,)).fetchall():
                decided.setdefault(ex_id, set()).add(stratum)
            links: dict[str, set] = {}
            for ex_id, source in conn.execute(
                    "SELECT example_id, source FROM learning_candidates"
                    " WHERE example_id IS NOT NULL AND status IN"
                    " ('pending','approved')").fetchall():
                links.setdefault(ex_id, set()).add(source)
            latest = conn.execute(
                "SELECT example_id, envelope_json FROM"
                " training_revisions WHERE rowid IN (SELECT MAX(rowid)"
                " FROM training_revisions GROUP BY example_id)"
            ).fetchall()
            states = dict(conn.execute(
                "SELECT example_id, state FROM training_examples"
            ).fetchall())
            population = []
            late = []
            for ex_id, payload in latest:
                if states.get(ex_id) not in _LIVE_STATES:
                    continue
                if ex_id in decided and \
                        decided[ex_id] != {"not_included"}:
                    continue  # already included once under this policy
                env = json.loads(payload)
                if env.get("state") in ("excluded", "deleted", "expired"):
                    continue
                if ex_id in decided:
                    if _triggered(env, links.get(ex_id)):
                        late.append((ex_id, env))
                    continue
                population.append((ex_id, env))
            population.sort(key=lambda pair: pair[0])
            late.sort(key=lambda pair: pair[0])
            population_hash = ids.sha256_text(
                json.dumps([p[0] for p in population]))
            now = ids.now_utc_iso()
            included = {"representative": 0, "hard_trigger": 0,
                        "supplemental": 0, "explicit": 0, "not_included": 0}

            def record(ex_id, env, stratum, reason, probability):
                conn.execute(
                    "INSERT INTO sampling_decisions(decision_id, policy,"
                    " seed, example_id, job_id, stratum, inclusion_reason,"
                    " inclusion_probability, population_hash, event_seq,"
                    " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (ids.new_id("smp"), policy, seed, ex_id,
                     env.get("job_id"), stratum, reason, probability,
                     population_hash, None, now))
                included[stratum] += 1
                if stratum != "not_included" \
                        and states.get(ex_id) == "captured_unreviewed":
                    conn.execute(
                        "UPDATE training_examples SET"
                        " state='review_candidate', updated_at_utc=?"
                        " WHERE example_id=?", (now, ex_id))

            for ex_id, env in population:
                triggered = _triggered(env, links.get(ex_id))
                draw = _draw(seed, ex_id)
                if triggered:
                    # Enriched selection: no fabricated probability.
                    record(ex_id, env, triggered[0],
                           ";".join(triggered[1]), None)
                elif draw < percent / 100.0:
                    record(ex_id, env, "representative",
                           "seeded_bernoulli", percent / 100.0)
                elif _is_multilingual(env):
                    record(ex_id, env, "supplemental",
                           "multilingual_quota", None)
                else:
                    # The draw is RECORDED, not just skipped: a decided
                    # exclusion is never redrawn, so repeated refreshes
                    # never inflate the inclusion rate beyond the
                    # configured percent.
                    record(ex_id, env, "not_included",
                           "bernoulli_excluded", percent / 100.0)
            for ex_id, env in late:
                stratum, reasons = _triggered(env, links.get(ex_id))
                record(ex_id, env, stratum,
                       "late_trigger:" + ";".join(reasons), None)
            return {"policy": policy, "seed": seed,
                    "percent": percent, "population": len(population),
                    "population_hash": population_hash,
                    "late_inclusions": len(late),
                    "included": included}
        out = self.store.submit(op)
        self.emit("sampling.refreshed", level="INFO",
                  reason_code=out["policy"],
                  detail=f"population={out['population']}"
                         f" late={out['late_inclusions']}")
        return out

    def decisions_for(self, example_id: str) -> list[dict]:
        def op(conn):
            rows = conn.execute(
                "SELECT decision_id, policy, seed, stratum,"
                " inclusion_reason, inclusion_probability,"
                " population_hash, created_at_utc FROM"
                " sampling_decisions WHERE example_id=? ORDER BY rowid",
                (example_id,)).fetchall()
            return [dict(zip(
                ("decision_id", "policy", "seed", "stratum",
                 "inclusion_reason", "inclusion_probability",
                 "population_hash", "created_at_utc"), r))
                for r in rows]
        return self.store.submit(op)

    def coverage(self, policy: str = DEFAULT_POLICY) -> dict:
        """E19.4 sampling metrics: stratum counts with denominators,
        dedup guarantees and probability bookkeeping — counts, never
        rates over a population."""
        def op(conn):
            by_stratum = {}
            for stratum, n in conn.execute(
                    "SELECT stratum, COUNT(*) FROM sampling_decisions"
                    " WHERE policy=? GROUP BY stratum",
                    (policy,)).fetchall():
                by_stratum[stratum] = n
            with_prob = conn.execute(
                "SELECT COUNT(*) FROM sampling_decisions WHERE policy=?"
                " AND inclusion_probability IS NOT NULL",
                (policy,)).fetchone()[0]
            # One inclusion per example per policy is structural
            # (refresh skips included examples; a late trigger follows
            # only a not_included draw); the count proves it.
            distinct = conn.execute(
                "SELECT COUNT(DISTINCT example_id) FROM"
                " sampling_decisions WHERE policy=?",
                (policy,)).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM sampling_decisions WHERE policy=?",
                (policy,)).fetchone()[0]
            multi_included = conn.execute(
                "SELECT COUNT(*) FROM (SELECT example_id FROM"
                " sampling_decisions WHERE policy=? AND"
                " stratum!='not_included' GROUP BY example_id HAVING"
                " COUNT(*) > 1)", (policy,)).fetchone()[0]
            late = conn.execute(
                "SELECT COUNT(*) FROM sampling_decisions WHERE policy=?"
                " AND inclusion_reason LIKE 'late_trigger:%'",
                (policy,)).fetchone()[0]
            live = conn.execute(
                "SELECT COUNT(*) FROM training_examples WHERE state IN"
                " (?,?,?,?,?)", _LIVE_STATES).fetchone()[0]
            return {
                "policy": policy,
                "decisions_total": total,
                "decisions_distinct_examples": distinct,
                "one_inclusion_per_example": multi_included == 0,
                "late_inclusions": late,
                "by_stratum": by_stratum,
                "with_known_probability": with_prob,
                "probability_note": "enriched selections carry null —"
                                    " no fabricated probability (S29.9)",
                "live_examples": live,
            }
        return self.store.submit(op)
