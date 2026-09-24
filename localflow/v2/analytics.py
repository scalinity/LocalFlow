"""Usage analytics: dated facts, versioned aggregates, Insights queries
(V2 M13, Spec S08 usage_facts/daily_aggregates, S21, E06/E13/E19.4,
contract analytics.md).

Two layers, both riding the single-writer store (``Store.submit`` — one
op per action, fact write and its day's aggregate recompute atomic):

- ``AnalyticsStore`` — the write side. One usage fact per logical
  dictation (a retry reaching a terminal state again REPLACES the row,
  M13-AC02), separate ``transform``/``repaste`` activity rows (explicit
  transforms and re-pastes never increment dictated words), versioned
  daily aggregates recomputed from the facts, usage retention expiry and
  the explicit delete-content ≠ delete-usage controls (M13-AC03).
- ``InsightsQueryService`` — the read side the Hub's Insights view
  binds: weighted WPM (``60 × sum(words) / sum(capture_seconds)``,
  never an average of row WPM — E06/metrics.md), sample-aware latency
  percentiles that state cohort size, per-app/per-mode breakdowns, the
  Undated and imported-legacy lines, and honest no-data states.

Honesty rules carried here:

- Exactly one accepted logical dictation contributes to dictation
  totals; retries, replays, transforms and re-pastes are separate
  activity kinds (S21/M13-AC02). Note text never feeds these counts
  (contracts/scratchpad.md — usage reads jobs, never note revisions).
- Unknown dates never enter dated views (S21); the undated legacy log
  pairs surface only as an explicit Undated count.
- Legacy analytics (``legacy_dictations``) are read in place, never
  rewritten into new semantics: totals reconcile exactly, and the
  legacy ``fixed_words``/``wpm`` columns stay labeled legacy (the
  row-level wpm formula is unknown and stays so — the M13 stop
  condition).
- No operational WER exists here without reference text; nothing
  infers correctness from absence of edits (M13-AC05).
- App names are private usage metadata: they live in the store's
  fact rows, never in events or committed artifacts.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
import zoneinfo

from . import ids

# Bump when the aggregation formula changes; a bump + rebuild recomputes
# every day under the new version (versioned recomputation, task 5).
ALGORITHM_VERSION = 1

# The word-count definition behind raw_words/final_words (S21: counts
# carry their tokenizer/word-count version).
WORD_COUNT_VERSION = "whitespace-split-v1"

USAGE_KINDS = ("dictation", "transform", "repaste")

# Terminal outcomes a dictation fact can carry. 'dictations_with_text'
# counts everything that produced text (confirmed/unverified/saved);
# cancelled/failed produced none or lost authority.
OUTCOMES = ("confirmed", "posted_unverified", "saved_not_inserted",
            "cancelled", "failed")


def word_count(text: str | None) -> int | None:
    """The documented word-count rule: whitespace-split tokens. None
    stays None (unknown), never coerced to zero."""
    if text is None:
        return None
    return len(text.split())


def local_day_for(iso_utc: str, tz_name: str) -> str | None:
    """Bucket a UTC instant into a local calendar day in the reporting
    zone (S21: the user's selected reporting timezone). Zone-aware
    conversion, so DST boundaries fall where the user actually spent
    them; unparseable instants return None (unknown dates never enter
    dated views). Both the writer's millisecond form and a plain
    seconds form parse — a future writer must not have its facts
    silently dropped over a formatting difference."""
    t = None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            t = dt.datetime.strptime(iso_utc, fmt).replace(
                tzinfo=dt.timezone.utc)
            break
        except (ValueError, TypeError):
            continue
    if t is None:
        return None
    try:
        zone = zoneinfo.ZoneInfo(tz_name)
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        zone = dt.timezone.utc
    return t.astimezone(zone).strftime("%Y-%m-%d")


def resolve_reporting_zone(configured: str | None = None) -> str:
    """The reporting zone: an explicit IANA name from config, else the
    system's local zone name, else UTC (recorded, never guessed)."""
    if configured:
        try:
            zoneinfo.ZoneInfo(configured)
            return configured
        except (ValueError, zoneinfo.ZoneInfoNotFoundError):
            pass
    return ids.local_zone_name() or "UTC"


def percentile(samples: list[float], q: float) -> float | None:
    """Nearest-rank percentile over the observed samples; None when
    there are none (honest null, never a zero)."""
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, min(len(ordered),
                      math.ceil(q / 100.0 * len(ordered))))
    return ordered[rank - 1]


class AnalyticsStore:
    """Write side of M13 analytics, over ``Store.submit`` (one writer op
    per action; the fact write and its day's aggregate recompute commit
    atomically)."""

    def __init__(self, store, emit=None, now_fn=time.time,
                 reporting_timezone=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)
        self.now_fn = now_fn
        self.reporting_timezone = reporting_timezone or \
            resolve_reporting_zone()

    # ---- internal helpers (writer-thread side) ---------------------------

    def _day(self, iso_utc: str) -> str | None:
        return local_day_for(iso_utc, self.reporting_timezone)

    def _write_fact(self, conn, *, fact_id, kind, values: dict):
        """INSERT ... ON CONFLICT replace for dictation rows (a retry
        rewrites its own fact — one row per logical job), plain INSERT
        for activity kinds. Returns the fact id."""
        cols = ["fact_id", "kind", "activity_at_utc", "day_local",
                "reporting_timezone", "algorithm_version",
                "created_at_utc", "meta_json", "word_count_version"]
        vals = [fact_id, kind, values["activity_at_utc"],
                values["day_local"], self.reporting_timezone,
                ALGORITHM_VERSION, ids.now_utc_iso(self.now_fn()),
                json.dumps(values.get("meta") or {}, ensure_ascii=False),
                WORD_COUNT_VERSION]
        for key in ("job_id", "time_quality", "timezone",
                    "utc_offset_minutes", "duration_sec", "raw_words",
                    "final_words", "cleanup_path", "fallback_reason",
                    "mode", "profile_name", "app_name", "app_bundle",
                    "insertion_outcome", "asr_ms", "cleanup_ms",
                    "transform_ms", "end_to_end_ms", "dictionary_hits",
                    "snippet_hits", "transform_id", "task_key",
                    "transform_path", "source_kind", "source_words",
                    "output_words", "attempt"):
            cols.append(key)
            value = values.get(key)
            # Required columns never fall to an explicit NULL the
            # schema's DEFAULT would have covered.
            if key == "time_quality" and value is None:
                value = "known"
            if key in ("dictionary_hits", "snippet_hits") \
                    and value is None:
                value = 0
            vals.append(value)
        # The retry-replace upsert refreshes every observation but keeps
        # first-creation provenance (created_at_utc) and the identity.
        update_cols = [c for c in cols
                       if c not in ("fact_id", "created_at_utc")]
        sql = (f"INSERT INTO usage_facts({','.join(cols)})"
               f" VALUES({','.join('?' * len(cols))})"
               " ON CONFLICT(fact_id) DO UPDATE SET "
               + ",".join(f"{c}=excluded.{c}" for c in update_cols))
        conn.execute(sql, vals)
        return fact_id

    def _recompute_day(self, conn, day_local: str):
        """Rebuild one day's aggregate row from the facts — always
        derived, never incrementally mutated, so a rebuild is always
        correct (versioned recomputation)."""
        row = conn.execute(
            "SELECT COUNT(*),"
            " SUM(CASE WHEN final_words IS NOT NULL AND final_words > 0"
            "  THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN insertion_outcome='confirmed' THEN 1"
            "  ELSE 0 END),"
            " SUM(CASE WHEN insertion_outcome='posted_unverified' THEN 1"
            "  ELSE 0 END),"
            " SUM(CASE WHEN insertion_outcome='saved_not_inserted' THEN 1"
            "  ELSE 0 END),"
            " SUM(CASE WHEN insertion_outcome='cancelled' THEN 1"
            "  ELSE 0 END),"
            " SUM(CASE WHEN insertion_outcome='failed' THEN 1"
            "  ELSE 0 END),"
            " SUM(COALESCE(raw_words,0)), SUM(COALESCE(final_words,0)),"
            " SUM(COALESCE(duration_sec,0.0)),"
            " SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1"
            "  ELSE 0 END),"
            " SUM(COALESCE(dictionary_hits,0)),"
            " SUM(COALESCE(snippet_hits,0))"
            " FROM usage_facts WHERE kind='dictation' AND day_local=?",
            (day_local,)).fetchone()
        (n, with_text, confirmed, unverified, saved, cancelled, failed,
         raw_words, final_words, seconds, fallbacks, dict_hits,
         snip_hits) = row
        tf = conn.execute(
            "SELECT COUNT(*), SUM(COALESCE(source_words,0)) FROM"
            " usage_facts WHERE kind='transform' AND day_local=?",
            (day_local,)).fetchone()
        repastes = conn.execute(
            "SELECT COUNT(*) FROM usage_facts WHERE kind='repaste' AND"
            " day_local=?", (day_local,)).fetchone()[0]
        conn.execute(
            "INSERT OR REPLACE INTO daily_aggregates(day_local,"
            " reporting_timezone, algorithm_version, dictations,"
            " dictations_with_text, insertion_confirmed,"
            " insertion_unverified, saved_not_inserted, cancelled,"
            " failed, raw_words, final_words, capture_seconds,"
            " fallback_jobs, dictionary_hits, snippet_hits, transforms,"
            " transform_words, repastes, computed_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (day_local, self.reporting_timezone, ALGORITHM_VERSION,
             n or 0, with_text or 0, confirmed or 0, unverified or 0,
             saved or 0, cancelled or 0, failed or 0, raw_words or 0,
             final_words or 0, seconds or 0.0, fallbacks or 0,
             dict_hits or 0, snip_hits or 0, tf[0] or 0, tf[1] or 0,
             repastes or 0, ids.now_utc_iso(self.now_fn())))

    # ---- fact writers ------------------------------------------------------

    def record_dictation_fact(self, *, job_id, activity_at_utc,
                              timezone=None, utc_offset_minutes=None,
                              time_quality="known", duration_sec=None,
                              raw_words=None, final_words=None,
                              cleanup_path=None, fallback_reason=None,
                              mode=None, profile_name=None, app_name=None,
                              app_bundle=None, insertion_outcome=None,
                              asr_ms=None, cleanup_ms=None,
                              transform_ms=None, end_to_end_ms=None,
                              dictionary_hits=0, snippet_hits=0,
                              transform_id=None, task_key=None,
                              transform_path=None, attempt=1, meta=None):
        """One logical dictation's metric facts. Upserts on the job's
        fact row — a retry that reaches a terminal outcome again
        replaces the previous row instead of adding a second (M13-AC02:
        retries/replays never increment dictated words twice)."""
        if insertion_outcome is not None and \
                insertion_outcome not in OUTCOMES:
            raise ValueError(f"unknown insertion_outcome"
                             f" {insertion_outcome!r}")
        day = self._day(activity_at_utc)
        if day is None:
            # Unknown instants never enter dated views; the fact is
            # refused rather than parked on a fabricated day (S21).
            self.emit("usage.fact_refused", level="WARNING",
                      reason_code="unknown_activity_time", job_id=job_id)
            return None

        def op(conn):
            prev = conn.execute(
                "SELECT fact_id, day_local FROM usage_facts WHERE"
                " kind='dictation' AND job_id=?", (job_id,)).fetchone()
            fact_id = prev[0] if prev else ids.new_id("uf")
            prev_day = prev[1] if prev else None
            self._write_fact(conn, fact_id=fact_id, kind="dictation",
                             values={
                                 "job_id": job_id,
                                 "activity_at_utc": activity_at_utc,
                                 "time_quality": time_quality,
                                 "timezone": timezone,
                                 "utc_offset_minutes": utc_offset_minutes,
                                 "day_local": day,
                                 "duration_sec": duration_sec,
                                 "raw_words": raw_words,
                                 "final_words": final_words,
                                 "cleanup_path": cleanup_path,
                                 "fallback_reason": fallback_reason,
                                 "mode": mode,
                                 "profile_name": profile_name,
                                 "app_name": app_name,
                                 "app_bundle": app_bundle,
                                 "insertion_outcome": insertion_outcome,
                                 "asr_ms": asr_ms, "cleanup_ms": cleanup_ms,
                                 "transform_ms": transform_ms,
                                 "end_to_end_ms": end_to_end_ms,
                                 "dictionary_hits": dictionary_hits,
                                 "snippet_hits": snippet_hits,
                                 "transform_id": transform_id,
                                 "task_key": task_key,
                                 "transform_path": transform_path,
                                 "attempt": attempt,
                                 "meta": meta,
                             })
            self._recompute_day(conn, day)
            if prev_day is not None and prev_day != day:
                # A retry completing on another day moved the logical
                # dictation — the departed day's aggregate must not keep
                # its counts (delete when it emptied, recompute if other
                # facts remain).
                if conn.execute(
                        "SELECT 1 FROM usage_facts WHERE day_local=?"
                        " LIMIT 1", (prev_day,)).fetchone() is None:
                    conn.execute(
                        "DELETE FROM daily_aggregates WHERE day_local=?",
                        (prev_day,))
                else:
                    self._recompute_day(conn, prev_day)
            return fact_id
        return self.store.submit(op)

    def record_transform_fact(self, *, transform_id, task_key, path,
                              source_kind, source_words=None,
                              output_words=None, duration_ms=None,
                              activity_at_utc=None, meta=None):
        """A transform execution — its own activity kind, counted
        separately from dictations (M13-AC02). Covers selection, note
        and dictation auto-apply runs; each run is one fact."""
        at = activity_at_utc or ids.now_utc_iso(self.now_fn())
        day = self._day(at)
        if day is None:
            self.emit("usage.fact_refused", level="WARNING",
                      reason_code="unknown_activity_time")
            return None

        def op(conn):
            fact_id = ids.new_id("uf")
            self._write_fact(conn, fact_id=fact_id, kind="transform",
                             values={
                                 "activity_at_utc": at, "day_local": day,
                                 "transform_id": transform_id,
                                 "task_key": task_key,
                                 "transform_path": path,
                                 "source_kind": source_kind,
                                 "source_words": source_words,
                                 "output_words": output_words,
                                 "duration_sec": (duration_ms / 1000.0
                                                  if duration_ms
                                                  is not None else None),
                                 "meta": meta,
                             })
            self._recompute_day(conn, day)
            return fact_id
        return self.store.submit(op)

    def record_repaste_fact(self, *, job_id=None, activity_at_utc=None,
                            meta=None):
        """History's Paste Again — an activity row with no word counts:
        a re-paste never re-increments dictated words (M13-AC02)."""
        at = activity_at_utc or ids.now_utc_iso(self.now_fn())
        day = self._day(at)
        if day is None:
            return None

        def op(conn):
            fact_id = ids.new_id("uf")
            self._write_fact(conn, fact_id=fact_id, kind="repaste",
                             values={"activity_at_utc": at,
                                     "day_local": day, "job_id": job_id,
                                     "meta": meta})
            self._recompute_day(conn, day)
            return fact_id
        return self.store.submit(op)

    # ---- deletion and retention (M13-AC03) ---------------------------------

    def delete_usage_for_job(self, job_id):
        """The explicit 'delete associated usage' action for one job —
        independent of content deletion (the content may already be
        gone; transcript expiry never triggers this)."""

        def op(conn):
            days = [r[0] for r in conn.execute(
                "SELECT DISTINCT day_local FROM usage_facts WHERE"
                " job_id=?", (job_id,)).fetchall()]
            conn.execute("DELETE FROM usage_facts WHERE job_id=?",
                         (job_id,))
            for day in days:
                if conn.execute(
                        "SELECT 1 FROM usage_facts WHERE day_local=?"
                        " LIMIT 1", (day,)).fetchone() is None:
                    conn.execute(
                        "DELETE FROM daily_aggregates WHERE day_local=?",
                        (day,))
                else:
                    self._recompute_day(conn, day)
            return len(days)
        n = self.store.submit(op)
        self.emit("usage.deleted", level="INFO",
                  reason_code="job_usage_deleted", job_id=job_id)
        return {"days_touched": n}

    def delete_all_usage(self):
        """The explicit 'delete all usage data' control (Settings).
        Removes facts and aggregates only — transcripts, audio, jobs and
        training evidence are untouched."""

        def op(conn):
            facts = conn.execute(
                "SELECT COUNT(*) FROM usage_facts").fetchone()[0]
            conn.execute("DELETE FROM usage_facts")
            conn.execute("DELETE FROM daily_aggregates")
            return facts
        n = self.store.submit(op)
        self.emit("usage.deleted", level="INFO",
                  reason_code="all_usage_deleted", detail=f"facts={n}")
        return {"facts_deleted": n}

    def expire_usage(self, now=None):
        """Usage retention pass: facts older than the ``usage`` knob are
        removed and their days recomputed. Independent of the
        transcript/audio/metadata knobs (M13-AC03)."""
        now = now if now is not None else self.now_fn()

        def op(conn):
            cutoff = ids.now_utc_iso(now - self.store.retention_days[
                "usage"] * 86400)
            days = [r[0] for r in conn.execute(
                "SELECT DISTINCT day_local FROM usage_facts WHERE"
                " activity_at_utc < ?", (cutoff,)).fetchall()]
            cur = conn.execute(
                "DELETE FROM usage_facts WHERE activity_at_utc < ?",
                (cutoff,))
            removed = cur.rowcount
            for day in days:
                if conn.execute(
                        "SELECT 1 FROM usage_facts WHERE day_local=?"
                        " LIMIT 1", (day,)).fetchone() is None:
                    conn.execute(
                        "DELETE FROM daily_aggregates WHERE day_local=?",
                        (day,))
                else:
                    self._recompute_day(conn, day)
            return {"facts_removed": removed}
        out = self.store.submit(op)
        if out["facts_removed"]:
            self.emit("usage.retention_applied", level="INFO",
                      reason_code="usage_expiry",
                      detail=f"facts={out['facts_removed']}")
        return out

    # ---- versioned recomputation -------------------------------------------

    def rebuild_aggregates(self, *, reporting_timezone=None):
        """Full versioned recompute: re-bucket every fact's day_local
        under the (possibly changed) reporting zone and rebuild every
        aggregate row under the current algorithm version. Old-zone
        aggregate rows for other zones are removed — the table always
        reflects exactly one zone/version's arithmetic. The zone
        assignment happens inside the writer op so no concurrently
        queued op can observe the half-applied change."""
        new_zone = reporting_timezone or self.reporting_timezone
        try:
            zoneinfo.ZoneInfo(new_zone)
        except (ValueError, zoneinfo.ZoneInfoNotFoundError):
            return {"outcome": "unknown_timezone", "zone": new_zone}

        def op(conn):
            self.reporting_timezone = new_zone
            rows = conn.execute(
                "SELECT fact_id, kind, activity_at_utc FROM"
                " usage_facts").fetchall()
            days = set()
            for fact_id, kind, at in rows:
                day = local_day_for(at, new_zone)
                conn.execute(
                    "UPDATE usage_facts SET day_local=?,"
                    " reporting_timezone=? WHERE fact_id=?",
                    (day, new_zone, fact_id))
                days.add(day)
            conn.execute("DELETE FROM daily_aggregates")
            for day in sorted(d for d in days if d):
                self._recompute_day(conn, day)
            return {"facts": len(rows), "days": len(days)}
        out = self.store.submit(op)
        self.emit("usage.aggregates_rebuilt", level="INFO",
                  reason_code="versioned_recompute",
                  detail=f"zone={new_zone} facts={out['facts']}")
        return out


class InsightsQueryService:
    """Read side for the Hub's Insights view (the M09 query discipline:
    one materialized ``Store.submit`` op per query, fully plain data)."""

    def __init__(self, store, analytics: AnalyticsStore):
        self.store = store
        self.analytics = analytics

    # ---- helpers -------------------------------------------------------------

    def _cohort_where(self, app=None, mode=None):
        clauses = ["kind='dictation'"]
        params: list = []
        if app:
            clauses.append("(app_name=? OR app_bundle=?)")
            params += [app, app]
        if mode:
            clauses.append("mode=?")
            params.append(mode)
        return " AND ".join(clauses), params

    def _range_days(self, days):
        """day_local >= the day `days` ago in the reporting zone; None
        when days is None (all time)."""
        if days is None:
            return None
        zone = zoneinfo.ZoneInfo(self.analytics.reporting_timezone)
        cutoff = (dt.datetime.now(zone) - dt.timedelta(
            days=days - 1)).replace(hour=0, minute=0, second=0,
                                    microsecond=0)
        return cutoff.strftime("%Y-%m-%d")

    # ---- the summary the view renders ---------------------------------------

    def summary(self, days=30, app=None, mode=None) -> dict:
        """Cohort summary over the reporting-zone day range: weighted
        WPM with its denominator, totals by outcome, fallback rate,
        dictionary/snippet hits, transform and repaste counts, and
        sample-aware latency percentiles (cohort size stated — E06)."""
        def op(conn):
            where, params = self._cohort_where(app, mode)
            start = self._range_days(days)
            if start is not None:
                where += " AND day_local >= ?"
                params = params + [start]
            row = conn.execute(
                f"SELECT COUNT(*),"
                " SUM(CASE WHEN final_words IS NOT NULL AND final_words > 0"
                "  THEN 1 ELSE 0 END),"
                " SUM(CASE WHEN insertion_outcome='confirmed' THEN 1"
                "  ELSE 0 END),"
                " SUM(CASE WHEN insertion_outcome='posted_unverified'"
                "  THEN 1 ELSE 0 END),"
                " SUM(CASE WHEN insertion_outcome='saved_not_inserted'"
                "  THEN 1 ELSE 0 END),"
                " SUM(CASE WHEN insertion_outcome='cancelled' THEN 1"
                "  ELSE 0 END),"
                " SUM(CASE WHEN insertion_outcome='failed' THEN 1"
                "  ELSE 0 END),"
                " SUM(COALESCE(raw_words,0)),"
                " SUM(COALESCE(final_words,0)),"
                " SUM(COALESCE(duration_sec,0.0)),"
                # WPM's seconds denominator: the SAME text-producing
                # cohort as its words — a cancelled/failed job's capture
                # time must not deflate the rate (AC04's one-cohort
                # denominator).
                " SUM(CASE WHEN final_words IS NOT NULL AND final_words > 0"
                "  THEN COALESCE(duration_sec,0.0) ELSE 0.0 END),"
                " SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1"
                "  ELSE 0 END),"
                " SUM(COALESCE(dictionary_hits,0)),"
                " SUM(COALESCE(snippet_hits,0)),"
                " MIN(day_local), MAX(day_local)"
                f" FROM usage_facts WHERE {where}", params).fetchone()
            (n, with_text, confirmed, unverified, saved, cancelled,
             failed, raw_words, final_words, seconds, text_seconds,
             fallbacks, dict_hits, snip_hits, first_day, last_day) = row
            latency = self._latencies(conn, where, params)
            # Transform/repaste activity rows carry no destination app or
            # writing mode, so a filtered cohort cannot honestly count
            # them — they surface as None, only the unfiltered view
            # counts them (never a number borrowed from another cohort).
            transforms = repastes = transform_words = None
            if app is None and mode is None:
                # Activity kinds have no app/mode cohort of their own;
                # they are counted over the same day range unfiltered.
                tw, tp = ["day_local >= ?"], [start]
                if start is None:
                    tw, tp = ["1=1"], []
                transforms = conn.execute(
                    "SELECT COUNT(*) FROM usage_facts WHERE kind="
                    f"'transform' AND {tw[0]}", tp).fetchone()[0]
                repastes = conn.execute(
                    "SELECT COUNT(*) FROM usage_facts WHERE kind="
                    f"'repaste' AND {tw[0]}", tp).fetchone()[0]
                transform_words = conn.execute(
                    "SELECT COALESCE(SUM(source_words),0) FROM usage_facts"
                    f" WHERE kind='transform' AND {tw[0]}",
                    tp).fetchone()[0]
            return {
                "reporting_timezone": self.analytics.reporting_timezone,
                "algorithm_version": ALGORITHM_VERSION,
                "day_start": start,
                "cohort": {"app": app, "mode": mode, "days": days},
                "dictations": n or 0,
                "dictations_with_text": with_text or 0,
                "outcomes": {"confirmed": confirmed or 0,
                             "posted_unverified": unverified or 0,
                             "saved_not_inserted": saved or 0,
                             "cancelled": cancelled or 0,
                             "failed": failed or 0},
                "raw_words": raw_words or 0,
                "final_words": final_words or 0,
                # Whole-cohort capture seconds (all outcomes) — a
                # separate, honestly-labeled total from the WPM
                # denominator below.
                "capture_seconds": round(seconds or 0.0, 1),
                # Weighted full-capture WPM (E06): 60 × sum(final words)
                # / sum(capture seconds), BOTH over the cohort's
                # text-producing jobs — never an average of row WPM, and
                # null when the denominator is zero.
                "wpm": (round(60.0 * (final_words or 0) / text_seconds, 1)
                        if (text_seconds or 0) > 0 and (final_words or 0) > 0
                        else None),
                "wpm_denominator": {"jobs": with_text or 0,
                                    "words": final_words or 0,
                                    "capture_seconds":
                                        round(text_seconds or 0.0, 1)},
                "fallback_jobs": fallbacks or 0,
                "fallback_rate": (round((fallbacks or 0) / (n or 1), 3)
                                  if n else None),
                "dictionary_hits": dict_hits or 0,
                "snippet_hits": snip_hits or 0,
                "transforms": transforms,
                "transform_words": transform_words or 0,
                "repastes": repastes,
                "latency": latency,
                "range_first_day": first_day,
                "range_last_day": last_day,
            }
        return self.store.submit(op)

    def _latencies(self, conn, where, params):
        """Sample-aware stage/end-to-end percentiles. Stage-only and
        end-to-end stay separate; every number carries its sample size
        and the failed/timed-out jobs stay in the cohort denominator
        (they are why the cohort count can exceed any latency n)."""
        out = {}
        for key, label in (("asr_ms", "asr"), ("cleanup_ms", "cleanup"),
                           ("transform_ms", "transform"),
                           ("end_to_end_ms", "end_to_end")):
            samples = [r[0] for r in conn.execute(
                f"SELECT {key} FROM usage_facts WHERE {where}"
                f" AND {key} IS NOT NULL", params).fetchall()]
            out[label] = {
                "n": len(samples),
                "p50": percentile(samples, 50),
                "p95": percentile(samples, 95),
                "kind": ("stage" if key != "end_to_end_ms"
                         else "end_to_end"),
            }
        return out

    # ---- breakdowns ----------------------------------------------------------

    def daily(self, days=30, app=None, mode=None, limit=400) -> list[dict]:
        """Per-day rows for the dated table/heatmap, newest first.
        Legacy imported rows are NOT folded in: they surface through
        their own legacy lines (their semantics stay legacy-labeled).
        Transform/repaste columns are None under a cohort filter
        (activity rows carry no app/mode)."""
        def op(conn):
            where, params = self._cohort_where(app, mode)
            start = self._range_days(days)
            if start is not None:
                where += " AND day_local >= ?"
                params = params + [start]
            rows = conn.execute(
                f"SELECT day_local, COUNT(*),"
                " SUM(COALESCE(raw_words,0)),"
                " SUM(COALESCE(final_words,0)),"
                " SUM(COALESCE(duration_sec,0.0)),"
                " SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1"
                "  ELSE 0 END)"
                f" FROM usage_facts WHERE {where} GROUP BY day_local"
                " ORDER BY day_local DESC LIMIT ?",
                params + [limit]).fetchall()
            unfiltered = app is None and mode is None
            out = []
            for (day, n, raw_w, final_w, secs, fb) in rows:
                tf = rp = None
                if unfiltered:
                    tf = conn.execute(
                        "SELECT COUNT(*) FROM usage_facts WHERE"
                        " kind='transform' AND day_local=?",
                        (day,)).fetchone()[0]
                    rp = conn.execute(
                        "SELECT COUNT(*) FROM usage_facts WHERE"
                        " kind='repaste' AND day_local=?",
                        (day,)).fetchone()[0]
                out.append({"day": day, "dictations": n,
                            "raw_words": raw_w or 0,
                            "final_words": final_w or 0,
                            "capture_seconds": round(secs or 0.0, 1),
                            "fallbacks": fb or 0, "transforms": tf,
                            "repastes": rp})
            return out
        return self.store.submit(op)

    def per_app(self, days=30) -> list[dict]:
        """App breakdown over dictation facts (private usage metadata —
        store-side only)."""
        def op(conn):
            start = self._range_days(days)
            where = "kind='dictation'" + (
                " AND day_local >= ?" if start is not None else "")
            params = [start] if start is not None else []
            rows = conn.execute(
                f"SELECT COALESCE(app_name, app_bundle, 'Unknown') AS a,"
                " COUNT(*), SUM(COALESCE(final_words,0)),"
                " SUM(COALESCE(duration_sec,0.0))"
                f" FROM usage_facts WHERE {where} GROUP BY a"
                " ORDER BY 2 DESC LIMIT 50", params).fetchall()
            return [{"app": a, "dictations": n, "final_words": w or 0,
                     "capture_seconds": round(s or 0.0, 1)}
                    for a, n, w, s in rows]
        return self.store.submit(op)

    def per_mode(self, days=30) -> list[dict]:
        """Writing-mode breakdown (the effective mode the job ran
        under; the cleanup-path vocabulary backs the fallback graphs)."""
        def op(conn):
            start = self._range_days(days)
            where = "kind='dictation'" + (
                " AND day_local >= ?" if start is not None else "")
            params = [start] if start is not None else []
            rows = conn.execute(
                f"SELECT COALESCE(mode, 'unknown') AS m, COUNT(*),"
                " SUM(COALESCE(final_words,0))"
                f" FROM usage_facts WHERE {where} GROUP BY m"
                " ORDER BY 2 DESC LIMIT 50", params).fetchall()
            return [{"mode": m, "dictations": n, "final_words": w or 0}
                    for m, n, w in rows]
        return self.store.submit(op)

    def apps_available(self) -> list[str]:
        """Distinct destination apps for the cohort filter menu."""
        def op(conn):
            return sorted({r[0] for r in conn.execute(
                "SELECT DISTINCT COALESCE(app_name, app_bundle) FROM"
                " usage_facts WHERE kind='dictation' AND"
                " COALESCE(app_name, app_bundle) IS NOT NULL")})
        return self.store.submit(op)

    def modes_available(self) -> list[str]:
        def op(conn):
            return sorted({r[0] for r in conn.execute(
                "SELECT DISTINCT mode FROM usage_facts WHERE"
                " kind='dictation' AND mode IS NOT NULL")})
        return self.store.submit(op)

    # ---- undated + imported legacy lines (S21/E13) ---------------------------

    def undated_count(self) -> int:
        """Legacy log pairs — unknown dates never enter dated views;
        they surface as this explicit count only."""
        def op(conn):
            return conn.execute(
                "SELECT COUNT(*) FROM artifacts WHERE stage='legacy_log'"
                " AND role='cleaned_transcript'").fetchone()[0]
        return self.store.submit(op)

    def legacy_summary(self) -> dict | None:
        """The imported legacy analytics readout (E13 reconciliation
        figures): row count, raw/cleaned word sums, capture seconds,
        fixed-word sum and the instants — read in place, never
        relabeled. The row-level wpm column's formula is unknown and is
        not reused; the legacy label stays on fixed_words."""
        def op(conn):
            row = conn.execute(
                "SELECT COUNT(*), SUM(raw_words), SUM(cleaned_words),"
                " ROUND(SUM(duration_sec),1), SUM(fixed_words),"
                " MIN(captured_at_utc), MAX(captured_at_utc),"
                " SUM(CASE WHEN captured_at_utc IS NULL THEN 1"
                "  ELSE 0 END) FROM legacy_dictations").fetchone()
            if not row or not row[0]:
                return None
            return {"rows": row[0], "raw_words": row[1],
                    "cleaned_words": row[2], "capture_seconds": row[3],
                    # Legacy label, by contract: an unknown historical
                    # formula, never presented as a V2 metric.
                    "legacy_fixed_words": row[4],
                    "first_instant": row[5], "last_instant": row[6],
                    "rows_without_instant": row[7]}
        return self.store.submit(op)
