"""Usage analytics: dated facts, versioned aggregates, Insights queries
(V2 M13, Spec S08 usage_facts/daily_aggregates, S21, E06/E13/E19.4,
contract analytics.md, decision record m13-policy-r1).

Two layers, both riding the single-writer store (``Store.submit`` — one
op per action, fact write and its day's aggregate recompute atomic):

- ``AnalyticsStore`` — the write side. One usage fact per logical
  dictation (a retry reaching a terminal state again REPLACES the row,
  M13-AC02), separate ``transform``/``repaste`` activity rows (explicit
  transforms and re-pastes never increment dictated words), versioned
  daily aggregates recomputed from the facts, usage retention expiry and
  the explicit delete-content ≠ delete-usage controls (M13-AC03).
- ``InsightsQueryService`` — the read side the Hub's Insights view
  binds: weighted WPM over one defined rate cohort, sample-aware latency
  percentiles that state cohort size and missing reasons, complete
  per-app/per-mode breakdowns keyed by typed identity, the Undated and
  imported-legacy lines, and honest no-data states. ``report`` reads a
  whole Insights report in ONE writer op — one fact generation.

Authority: the reporting zone and the usage revision are durable state
(``usage_meta``) read inside every writer and query op. A fact's day,
its row zone, a query's range and the published label therefore always
come from one committed policy; a failed rebuild rolls back rows and the
zone together, and the in-memory copy (display only) changes only after
a rebuild's commit returns.

Honesty rules carried here:

- Exactly one accepted logical dictation contributes to dictation
  totals; retries, replays, transforms and re-pastes are separate
  activity kinds (S21/M13-AC02). Note text never feeds these counts
  (contracts/scratchpad.md — usage reads jobs, never note revisions).
- Unknown or malformed instants never enter dated views (S21); new ones
  are refused, never dated at now, and never join the legacy Undated
  count. Admitted instants are stored at one canonical precision so
  their text order is their time order.
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
import re
import time
import zoneinfo

from . import ids

# Bump when the aggregation formula changes; a bump + rebuild recomputes
# every day under the new version (versioned recomputation, task 5).
ALGORITHM_VERSION = 1

# The word-count definition behind raw_words/final_words (S21: counts
# carry their tokenizer/word-count version). Whitespace tokens, not a
# language-aware word count ("... !!" is two tokens, unspaced CJK one).
WORD_COUNT_VERSION = "whitespace-split-v1"

USAGE_KINDS = ("dictation", "transform", "repaste")

# Terminal outcomes a dictation fact can carry. 'dictations_with_text'
# counts everything that produced text (confirmed/unverified/saved);
# cancelled/failed produced none or lost authority.
OUTCOMES = ("confirmed", "posted_unverified", "saved_not_inserted",
            "cancelled", "failed")

# The one admitted instant grammar (D02): UTC with an uppercase Z,
# zero-padded fields, optional 1-6 fractional digits.
_INSTANT_RE = re.compile(
    r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z\Z",
    re.ASCII)  # ASCII digits only: \d alone matches every Unicode digit
# The stored canonical form, as an SQLite GLOB (a row that does not match
# was written before canonical storage and is re-bucketed at launch).
_CANONICAL_GLOB = ("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T"
                   "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]."
                   "[0-9][0-9][0-9][0-9][0-9][0-9]Z")

# Your Voice snapshot fields copied from usage facts (M14 consumer
# seam): redacted whenever the facts they were computed from are
# deleted or expire (D11).
USAGE_DERIVED_PROFILE_FIELDS = ("app_usage", "hour_histogram",
                                "hours_unknown", "modes",
                                "requested_transforms",
                                "dictionary_hit_examples")

_COUNT_FIELDS = ("raw_words", "final_words", "dictionary_hits",
                 "snippet_hits")
_TIMING_FIELDS = ("duration_sec", "asr_ms", "cleanup_ms", "transform_ms",
                  "end_to_end_ms")


def word_count(text: str | None) -> int | None:
    """The documented word-count rule: whitespace-split tokens. None
    stays None (unknown), never coerced to zero."""
    if text is None:
        return None
    return len(text.split())


# ---- instants ------------------------------------------------------------------

def canonical_instant(value) -> str | None:
    """A validated UTC instant in canonical microsecond form
    (``YYYY-MM-DDTHH:MM:SS.ffffffZ``), or None when ``value`` is not an
    admitted instant. Only zero pads are added — the true instant is
    unchanged — so canonical strings sort chronologically."""
    if not isinstance(value, str):
        return None
    m = _INSTANT_RE.match(value)
    if m is None:
        return None
    y, mo, d, h, mi, s, frac = m.groups()
    try:
        dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except ValueError:
        return None
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}.{(frac or '').ljust(6, '0')}Z"


def instant_from_epoch(ts: float) -> str:
    """The canonical form of a clock reading."""
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}Z"


def _legacy_admitted(value) -> str | None:
    """The canonical form of an instant the pre-remediation parser
    admitted (case-insensitive Z, unpadded fields): used only to
    re-bucket rows already stored, never to admit new ones."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            t = dt.datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}Z"
    return None


def _parse_canonical(iso: str) -> dt.datetime:
    return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=dt.timezone.utc)


def local_day_for(iso_utc, tz_name: str) -> str | None:
    """Bucket a UTC instant into a local calendar day in the reporting
    zone (S21: the user's selected reporting timezone). Zone-aware
    conversion, so DST boundaries fall where the user actually spent
    them. A non-admitted instant returns None (unknown dates never enter
    dated views); an invalid zone raises ValueError — never a silent
    UTC bucket under another zone's label."""
    at = canonical_instant(iso_utc)
    if at is None:
        return None
    return _parse_canonical(at).astimezone(_zone(tz_name)).strftime(
        "%Y-%m-%d")


# ---- the reporting zone policy (D02b) -----------------------------------------------

def _zone(name):
    try:
        return zoneinfo.ZoneInfo(name)
    except (ValueError, TypeError, OSError,
            zoneinfo.ZoneInfoNotFoundError) as e:
        raise ValueError("invalid reporting timezone") from e


def system_zone() -> str:
    """The documented empty-value policy: the observed system IANA zone
    when it resolves, else UTC (recorded, never guessed)."""
    name = ids.local_zone_name()
    if name:
        try:
            _zone(name)
            return name
        except ValueError:
            pass
    return "UTC"


def validate_reporting_zone(value) -> tuple[str | None, str | None]:
    """(zone, None) for an accepted value, (None, reason) otherwise.
    Empty or None means the system policy; a non-string or an unknown
    name is invalid (reason codes only — the raw value is never echoed
    into metadata)."""
    if value is None or value == "":
        return system_zone(), None
    if not isinstance(value, str):
        return None, "not_a_string"
    try:
        _zone(value)
    except ValueError:
        return None, "unknown_zone"
    return value, None


def resolve_reporting_zone(configured=None) -> str:
    """The zone a configuration value selects: the validated value, else
    the system policy (callers that must disclose an invalid value use
    ``validate_reporting_zone``)."""
    zone, _reason = validate_reporting_zone(configured)
    return zone or system_zone()


def percentile(samples: list[float], q: float) -> float | None:
    """Nearest-rank percentile over the observed samples; None when
    there are none (honest null, never a zero)."""
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, min(len(ordered),
                      math.ceil(q / 100.0 * len(ordered))))
    return ordered[rank - 1]


# ---- admission of numbers (D14) --------------------------------------------------------

def _count(name, value, *, allow_none=True, minimum=0):
    """A usage count: an integer >= minimum (bool is not a count), or
    None where unknown is allowed. Anything else refuses the fact."""
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) \
            or value < minimum:
        raise ValueError(f"invalid usage count {name}")
    return value


def _timing(name, value, invalid: list):
    """An observed duration/latency: finite and >= 0, else None with the
    metric recorded in ``invalid`` (one bad timing never loses the
    fact)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        invalid.append(f"{name}:not_a_number")
        return None
    if not math.isfinite(value):
        invalid.append(f"{name}:not_finite")
        return None
    if value < 0:
        invalid.append(f"{name}:negative")
        return None
    return float(value)


# ---- durable usage state (schema v12 usage_meta) -------------------------------------------

def conn_committed_zone(conn, default=None):
    row = conn.execute("SELECT value FROM usage_meta WHERE"
                       " key='reporting_timezone'").fetchone()
    return row[0] if row else default


def conn_usage_revision(conn) -> int:
    row = conn.execute("SELECT value FROM usage_meta WHERE"
                       " key='revision'").fetchone()
    return int(row[0]) if row else 0


def _bump_revision(conn):
    conn.execute(
        "INSERT INTO usage_meta(key, value) VALUES('revision', '1')"
        " ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")


def conn_redact_usage_copies(conn, reason, at_utc) -> int:
    """Redact every usage-derived field of every Your Voice snapshot
    that still carries one (D11). Speech-derived fields, cards and
    evidence links are untouched. Returns the snapshots redacted."""
    redacted = 0
    for snapshot_id, raw in conn.execute(
            "SELECT snapshot_id, measured_json FROM profile_snapshots"
            ).fetchall():
        try:
            measured = json.loads(raw or "{}")
        except ValueError:
            continue
        present = [k for k in USAGE_DERIVED_PROFILE_FIELDS
                   if measured.get(k) not in (None, {}, [])]
        if not present and "usage_redacted" in measured:
            continue
        if not present:
            continue
        for k in USAGE_DERIVED_PROFILE_FIELDS:
            if k in measured:
                measured[k] = None
        measured["usage_redacted"] = {"reason": reason, "at": at_utc}
        conn.execute("UPDATE profile_snapshots SET measured_json=? WHERE"
                     " snapshot_id=?",
                     (json.dumps(measured, ensure_ascii=False,
                                 sort_keys=True), snapshot_id))
        redacted += 1
    return redacted


class AnalyticsStore:
    """Write side of M13 analytics, over ``Store.submit`` (one writer op
    per action; the fact write and its day's aggregate recompute commit
    atomically)."""

    def __init__(self, store, emit=None, now_fn=time.time,
                 reporting_timezone=None):
        zone, reason = validate_reporting_zone(reporting_timezone)
        if reason is not None:
            raise ValueError(f"invalid reporting timezone ({reason})")
        self.store = store
        self.emit = emit or (lambda *a, **k: None)
        self.now_fn = now_fn
        # The zone this process was configured with (what a launch
        # drift check converges to) and the committed zone's display
        # copy — every op reads the durable zone itself.
        self.configured_timezone = zone
        self._committed_zone = self.store.submit(
            lambda conn: conn_committed_zone(conn, zone))

    @property
    def reporting_timezone(self) -> str:
        """The committed reporting zone (display copy, refreshed after
        each successful rebuild commit)."""
        return self._committed_zone

    # ---- internal helpers (writer-thread side) ---------------------------

    def _zone_in(self, conn) -> str:
        """The committed zone inside a writer op, seeding the configured
        zone when the store has none recorded yet."""
        zone = conn_committed_zone(conn)
        if zone is None:
            zone = self.configured_timezone
            conn.execute("INSERT OR IGNORE INTO usage_meta(key, value)"
                         " VALUES('reporting_timezone', ?)", (zone,))
        return zone

    def _write_fact(self, conn, *, fact_id, kind, zone, values: dict):
        """INSERT ... ON CONFLICT replace for dictation rows (a retry
        rewrites its own fact — one row per logical job), plain INSERT
        for activity kinds. Returns the fact id."""
        cols = ["fact_id", "kind", "activity_at_utc", "day_local",
                "reporting_timezone", "algorithm_version",
                "created_at_utc", "meta_json", "word_count_version"]
        vals = [fact_id, kind, values["activity_at_utc"],
                values["day_local"], zone, ALGORITHM_VERSION,
                ids.now_utc_iso(self.now_fn()),
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

    def _recompute_day(self, conn, day_local: str, zone: str):
        """Rebuild one day's aggregate row from the facts — always
        derived, never incrementally mutated; a day with no facts left
        has no aggregate row."""
        if conn.execute("SELECT 1 FROM usage_facts WHERE day_local=?"
                        " LIMIT 1", (day_local,)).fetchone() is None:
            conn.execute("DELETE FROM daily_aggregates WHERE day_local=?",
                         (day_local,))
            return
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
        # One row per day: any row of another zone/version for this day
        # is replaced, never left beside the current one.
        conn.execute("DELETE FROM daily_aggregates WHERE day_local=?",
                     (day_local,))
        conn.execute(
            "INSERT INTO daily_aggregates(day_local,"
            " reporting_timezone, algorithm_version, dictations,"
            " dictations_with_text, insertion_confirmed,"
            " insertion_unverified, saved_not_inserted, cancelled,"
            " failed, raw_words, final_words, capture_seconds,"
            " fallback_jobs, dictionary_hits, snippet_hits, transforms,"
            " transform_words, repastes, computed_at_utc)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (day_local, zone, ALGORITHM_VERSION,
             n or 0, with_text or 0, confirmed or 0, unverified or 0,
             saved or 0, cancelled or 0, failed or 0, raw_words or 0,
             final_words or 0, seconds or 0.0, fallbacks or 0,
             dict_hits or 0, snip_hits or 0, tf[0] or 0, tf[1] or 0,
             repastes or 0, ids.now_utc_iso(self.now_fn())))

    def _day_in(self, at: str, zone: str) -> str:
        return _parse_canonical(at).astimezone(_zone(zone)).strftime(
            "%Y-%m-%d")

    def _refuse(self, **kw):
        # Unknown instants never enter dated views; the fact is refused
        # rather than parked on a fabricated day (S21).
        self.emit("usage.fact_refused", level="WARNING",
                  reason_code="unknown_activity_time", **kw)
        return None

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
        retries/replays never increment dictated words twice). The
        day and row zone are derived inside the writer op from the
        committed zone."""
        if insertion_outcome is not None and \
                insertion_outcome not in OUTCOMES:
            raise ValueError(f"unknown insertion_outcome"
                             f" {insertion_outcome!r}")
        raw_words = _count("raw_words", raw_words)
        final_words = _count("final_words", final_words)
        dictionary_hits = _count("dictionary_hits", dictionary_hits)
        snippet_hits = _count("snippet_hits", snippet_hits)
        attempt = _count("attempt", attempt, minimum=1)
        invalid: list = []
        duration_sec = _timing("duration_sec", duration_sec, invalid)
        asr_ms = _timing("asr_ms", asr_ms, invalid)
        cleanup_ms = _timing("cleanup_ms", cleanup_ms, invalid)
        transform_ms = _timing("transform_ms", transform_ms, invalid)
        end_to_end_ms = _timing("end_to_end_ms", end_to_end_ms, invalid)
        if invalid:
            meta = dict(meta or {})
            meta["invalid_metrics"] = invalid
        at = canonical_instant(activity_at_utc)
        if at is None:
            return self._refuse(job_id=job_id)

        def op(conn):
            zone = self._zone_in(conn)
            day = self._day_in(at, zone)
            prev = conn.execute(
                "SELECT fact_id, day_local FROM usage_facts WHERE"
                " kind='dictation' AND job_id=?", (job_id,)).fetchone()
            fact_id = prev[0] if prev else ids.new_id("uf")
            prev_day = prev[1] if prev else None
            self._write_fact(conn, fact_id=fact_id, kind="dictation",
                             zone=zone, values={
                                 "job_id": job_id,
                                 "activity_at_utc": at,
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
            self._recompute_day(conn, day, zone)
            if prev_day is not None and prev_day != day:
                # A correction moved the logical dictation to another
                # day — the departed day keeps exactly its other facts
                # (recomputed) or loses its row when it emptied.
                self._recompute_day(conn, prev_day, zone)
            _bump_revision(conn)
            return fact_id
        return self.store.submit(op)

    def record_transform_fact(self, *, transform_id, task_key, path,
                              source_kind, source_words=None,
                              output_words=None, duration_ms=None,
                              activity_at_utc=None, meta=None):
        """One explicit transform execution — its own activity kind,
        counted separately from dictations (M13-AC02, D04). An
        auto-applied dictation transform rides its dictation's fact
        instead and never comes here."""
        source_words = _count("source_words", source_words)
        output_words = _count("output_words", output_words)
        invalid: list = []
        duration_ms = _timing("duration_ms", duration_ms, invalid)
        if invalid:
            meta = dict(meta or {})
            meta["invalid_metrics"] = invalid
        at = (canonical_instant(activity_at_utc)
              if activity_at_utc is not None
              else instant_from_epoch(self.now_fn()))
        if at is None:
            return self._refuse()

        def op(conn):
            zone = self._zone_in(conn)
            day = self._day_in(at, zone)
            fact_id = ids.new_id("uf")
            self._write_fact(conn, fact_id=fact_id, kind="transform",
                             zone=zone, values={
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
            self._recompute_day(conn, day, zone)
            _bump_revision(conn)
            return fact_id
        return self.store.submit(op)

    def record_repaste_fact(self, *, job_id=None, activity_at_utc=None,
                            meta=None):
        """A Paste Again that ran an insertion transaction (History or
        the Recovery menu) — an activity row with no word counts: a
        re-paste never re-increments dictated words (M13-AC02, D04)."""
        at = (canonical_instant(activity_at_utc)
              if activity_at_utc is not None
              else instant_from_epoch(self.now_fn()))
        if at is None:
            return self._refuse(job_id=job_id)

        def op(conn):
            zone = self._zone_in(conn)
            day = self._day_in(at, zone)
            fact_id = ids.new_id("uf")
            self._write_fact(conn, fact_id=fact_id, kind="repaste",
                             zone=zone, values={
                                 "activity_at_utc": at, "day_local": day,
                                 "job_id": job_id, "meta": meta})
            self._recompute_day(conn, day, zone)
            _bump_revision(conn)
            return fact_id
        return self.store.submit(op)

    # ---- deletion and retention (M13-AC03, D03, D11, D13) ----------------------

    def _removed(self, conn, days, reason, op_id):
        zone = self._zone_in(conn)
        for day in days:
            self._recompute_day(conn, day, zone)
        conn_redact_usage_copies(conn, reason,
                                 ids.now_utc_iso(self.now_fn()))
        _bump_revision(conn)
        self._mark(conn, op_id)

    @staticmethod
    def _mark(conn, op_id):
        """The durable completion marker an outcome-unknown caller
        reconciles against (written in the op's own transaction)."""
        if op_id:
            conn.execute("INSERT OR REPLACE INTO usage_meta(key, value)"
                         " VALUES(?, 'committed')", (f"op:{op_id}",))

    def delete_usage_for_job(self, job_id, *, op_id=None, timeout=15.0):
        """The explicit 'delete associated usage' action for one job:
        its dictation fact (with any auto-applied transform metadata)
        and every repaste carrying its job id. Explicit transforms carry
        no job and stay (D04). Independent of content deletion."""

        def op(conn):
            days = [r[0] for r in conn.execute(
                "SELECT DISTINCT day_local FROM usage_facts WHERE"
                " job_id=?", (job_id,)).fetchall()]
            removed = conn.execute("DELETE FROM usage_facts WHERE job_id=?",
                                   (job_id,)).rowcount
            if removed:
                self._removed(conn, days, "usage_deleted", op_id)
            else:
                self._mark(conn, op_id)
            return {"days_touched": len(days), "facts_deleted": removed}
        out = self.store.submit(op, timeout=timeout)
        self.emit("usage.deleted", level="INFO",
                  reason_code="job_usage_deleted", job_id=job_id)
        return out

    def delete_all_usage(self, *, op_id=None, timeout=15.0):
        """The explicit 'delete all usage data' control (Settings).
        Removes facts, aggregates and their Your Voice copies —
        transcripts, audio, jobs, notes and training evidence are
        untouched."""

        def op(conn):
            facts = conn.execute(
                "SELECT COUNT(*) FROM usage_facts").fetchone()[0]
            conn.execute("DELETE FROM usage_facts")
            conn.execute("DELETE FROM daily_aggregates")
            # Redacted whether or not facts remained: a snapshot may
            # still carry copies of usage deleted before copies were
            # redacted (REVIEW-R02).
            self._removed(conn, [], "usage_deleted", op_id)
            return {"facts_deleted": facts}
        n = self.store.submit(op, timeout=timeout)
        self.emit("usage.deleted", level="INFO",
                  reason_code="all_usage_deleted",
                  detail=f"facts={n['facts_deleted']}")
        return n

    def retire_op(self, op_id):
        """A committed deletion's marker is no longer needed (the caller
        saw the commit): removed off the caller's path (REVIEW-R06)."""
        self.store.submit(lambda conn: conn.execute(
            "DELETE FROM usage_meta WHERE key=?", (f"op:{op_id}",)),
            wait=False)

    def committed_zone(self) -> str:
        """The committed reporting zone read from the store (the display
        copy is refreshed with it — a rebuild whose caller timed out may
        still have committed; REVIEW-R07)."""
        self._committed_zone = self.store.submit(
            lambda conn: conn_committed_zone(conn,
                                             self.configured_timezone))
        return self._committed_zone

    def reconcile_op(self, op_id, timeout=60.0) -> str:
        """After an outcome-unknown admission: a FIFO read that runs only
        once the earlier op has executed. 'committed' when its marker
        exists (the marker is then retired), else 'rolled_back'."""

        def op(conn):
            key = f"op:{op_id}"
            found = conn.execute("SELECT 1 FROM usage_meta WHERE key=?",
                                 (key,)).fetchone() is not None
            conn.execute("DELETE FROM usage_meta WHERE key=?", (key,))
            return "committed" if found else "rolled_back"
        return self.store.submit(op, timeout=timeout)

    def _cutoff(self, days, now):
        return instant_from_epoch(now - days * 86400)

    def pending_expiry(self, days, now=None) -> int:
        """How many facts a retention of ``days`` would remove at the
        next pass (Apply's preview; nothing is deleted)."""
        if days is None:
            return 0
        now = now if now is not None else self.now_fn()
        cutoff = self._cutoff(days, now)
        return self.store.submit(lambda conn: conn.execute(
            "SELECT COUNT(*) FROM usage_facts WHERE activity_at_utc < ?",
            (cutoff,)).fetchone()[0])

    def expire_usage(self, now=None):
        """Usage retention pass: with a day count set, facts strictly
        older than now minus that many days of elapsed UTC time are
        removed and their days recomputed; 'keep until cleared' (None)
        removes nothing. Independent of the transcript/audio/metadata
        knobs (M13-AC03, D03)."""
        days = self.store.retention_days.get("usage")
        if days is None:
            return {"facts_removed": 0, "policy": "keep"}
        now = now if now is not None else self.now_fn()
        cutoff = self._cutoff(days, now)

        def op(conn):
            day_rows = [r[0] for r in conn.execute(
                "SELECT DISTINCT day_local FROM usage_facts WHERE"
                " activity_at_utc < ?", (cutoff,)).fetchall()]
            removed = conn.execute(
                "DELETE FROM usage_facts WHERE activity_at_utc < ?",
                (cutoff,)).rowcount
            if removed:
                self._removed(conn, day_rows, "usage_expired", None)
            return {"facts_removed": removed}
        out = self.store.submit(op)
        if out["facts_removed"]:
            self.emit("usage.retention_applied", level="INFO",
                      reason_code="usage_expiry",
                      detail=f"facts={out['facts_removed']}")
        return out

    # ---- versioned recomputation ------------------------------------------

    def _rebuild(self, conn, zone):
        """Re-bucket every fact under ``zone`` and rebuild every
        aggregate row under the current algorithm version, then record
        the zone — all in the caller's writer op (one transaction)."""
        rows = conn.execute("SELECT fact_id, activity_at_utc FROM"
                            " usage_facts").fetchall()
        days = set()
        for fact_id, at in rows:
            canon = canonical_instant(at) or _legacy_admitted(at)
            if canon is None:
                continue  # never admitted; left untouched
            day = self._day_in(canon, zone)
            conn.execute(
                "UPDATE usage_facts SET activity_at_utc=?, day_local=?,"
                " reporting_timezone=? WHERE fact_id=?",
                (canon, day, zone, fact_id))
            days.add(day)
        conn.execute("DELETE FROM daily_aggregates")
        conn.execute("INSERT OR REPLACE INTO usage_meta(key, value)"
                     " VALUES('reporting_timezone', ?)", (zone,))
        for day in sorted(days):
            self._recompute_day(conn, day, zone)
        _bump_revision(conn)
        return {"facts": len(rows), "days": len(days)}

    def rebuild_aggregates(self, *, reporting_timezone=None):
        """Full versioned recompute under ``reporting_timezone`` (default:
        the committed zone). The table always reflects exactly one
        zone/version's arithmetic. The zone becomes visible to later ops
        only when this op commits; the display copy follows after."""
        if reporting_timezone is None:
            zone = None
        else:
            zone, reason = validate_reporting_zone(reporting_timezone)
            if reason is not None:
                return {"outcome": "unknown_timezone", "reason": reason}

        def op(conn):
            target = zone or self._zone_in(conn)
            out = self._rebuild(conn, target)
            out["zone"] = target
            return out
        out = self.store.submit(op)
        self._committed_zone = out["zone"]
        self.emit("usage.aggregates_rebuilt", level="INFO",
                  reason_code="versioned_recompute",
                  detail=f"facts={out['facts']}")
        return out

    def ensure_current(self):
        """The launch drift check (one writer op): when the committed
        zone differs from the configured one, any fact row or aggregate
        row carries another zone, or any aggregate row another algorithm
        version, rebuild everything under the configured zone. Returns
        {"rebuilt": bool, "reasons": [...]}."""
        target = self.configured_timezone

        def op(conn):
            reasons = []
            committed = conn_committed_zone(conn)
            if committed != target:
                reasons.append("zone_changed" if committed
                               else "zone_unrecorded")
            if conn.execute(
                    "SELECT 1 FROM usage_facts WHERE reporting_timezone!=?"
                    " LIMIT 1", (target,)).fetchone():
                reasons.append("fact_zone_drift")
            if conn.execute(
                    "SELECT 1 FROM daily_aggregates WHERE"
                    " reporting_timezone!=? OR algorithm_version!=?"
                    " LIMIT 1", (target, ALGORITHM_VERSION)).fetchone():
                reasons.append("aggregate_drift")
            if conn.execute(
                    "SELECT 1 FROM usage_facts f WHERE NOT EXISTS (SELECT"
                    " 1 FROM daily_aggregates a WHERE a.day_local ="
                    " f.day_local) LIMIT 1").fetchone():
                # A recorded day with no aggregate row: the table was
                # lost and recreated by the store's repair (review RV-07).
                reasons.append("aggregates_missing")
            if conn.execute(
                    "SELECT 1 FROM usage_facts WHERE activity_at_utc NOT"
                    " GLOB ? LIMIT 1", (_CANONICAL_GLOB,)).fetchone():
                # Rows admitted before canonical storage (the old
                # parser's lax forms) are re-bucketed and canonicalized.
                reasons.append("noncanonical_instants")
            # Completion markers only matter to a process still waiting;
            # at launch none is (REVIEW-R06).
            conn.execute("DELETE FROM usage_meta WHERE key LIKE 'op:%'")
            if conn.execute("SELECT 1 FROM usage_facts LIMIT 1"
                            ).fetchone() is None:
                # No usage exists: no snapshot may keep a copy of any
                # (copies left by a deletion before redaction existed —
                # REVIEW-R02).
                conn_redact_usage_copies(conn, "usage_deleted",
                                         ids.now_utc_iso(self.now_fn()))
            if not reasons:
                return {"rebuilt": False, "reasons": []}
            self._rebuild(conn, target)
            return {"rebuilt": True, "reasons": reasons}
        out = self.store.submit(op)
        self._committed_zone = target
        if out["rebuilt"]:
            self.emit("usage.aggregates_rebuilt", level="INFO",
                      reason_code="launch_drift",
                      detail=",".join(out["reasons"]))
        return out


# ---- the read side ----------------------------------------------------------------------

def app_key(name, bundle) -> str:
    """Typed app identity (D09): the bundle id when known, else the
    display name, else unknown."""
    if bundle:
        return f"bundle:{bundle}"
    if name:
        return f"name:{name}"
    return "unknown"


_APP_KEY_SQL = ("CASE WHEN app_bundle IS NOT NULL AND app_bundle != ''"
                " THEN 'bundle:' || app_bundle"
                " WHEN app_name IS NOT NULL AND app_name != ''"
                " THEN 'name:' || app_name ELSE 'unknown' END")


class InsightsQueryService:
    """Read side for the Hub's Insights view (the M09 query discipline:
    one materialized ``Store.submit`` op per query, fully plain data;
    ``report`` materializes a whole report in one op)."""

    def __init__(self, store, analytics: AnalyticsStore, now_fn=None):
        self.store = store
        self.analytics = analytics
        self.now_fn = now_fn or analytics.now_fn

    # ---- helpers (run inside a writer op) ------------------------------------------

    @staticmethod
    def _cohort(app=None, mode=None):
        """The dictation cohort predicate for a typed app key and a mode
        (None = All; 'unknown' = the facts without that field)."""
        clauses = ["kind='dictation'"]
        params: list = []
        if app:
            if app == "unknown":
                clauses.append("(app_bundle IS NULL OR app_bundle='')"
                               " AND (app_name IS NULL OR app_name='')")
            elif app.startswith("bundle:"):
                clauses.append("app_bundle=?")
                params.append(app[len("bundle:"):])
            elif app.startswith("name:"):
                clauses.append("(app_bundle IS NULL OR app_bundle='')"
                               " AND app_name=?")
                params.append(app[len("name:"):])
            else:
                raise ValueError("unknown app key")
        if mode:
            if mode == "unknown":
                clauses.append("mode IS NULL")
            else:
                clauses.append("mode=?")
                params.append(mode)
        return " AND ".join(clauses), params

    def _range(self, zone, days):
        """Inclusive local calendar days [today-(days-1), today] in the
        committed zone at the service clock; (None, None) for All."""
        if days is None:
            return None, None
        if isinstance(days, bool) or not isinstance(days, int) or days < 1:
            raise ValueError("range must be a positive number of days")
        today = dt.datetime.fromtimestamp(self.now_fn(),
                                          tz=_zone(zone)).date()
        start = today - dt.timedelta(days=days - 1)
        return start.isoformat(), today.isoformat()

    @staticmethod
    def _bounded(where, params, start, end):
        if start is not None:
            where += " AND day_local >= ? AND day_local <= ?"
            params = params + [start, end]
        return where, params

    def _ctx(self, conn, days, app, mode):
        zone = conn_committed_zone(conn, self.analytics.configured_timezone)
        start, end = self._range(zone, days)
        where, params = self._cohort(app, mode)
        return zone, start, end, where, params

    # ---- sections ----------------------------------------------------------------------

    def _summary(self, conn, days, app, mode) -> dict:
        zone, start, end, cohort, cparams = self._ctx(conn, days, app, mode)
        where, params = self._bounded(cohort, cparams, start, end)
        row = conn.execute(
            "SELECT COUNT(*),"
            " SUM(CASE WHEN final_words > 0 THEN 1 ELSE 0 END),"
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
            # The WPM rate cohort (D01): text-producing jobs with an
            # observed positive capture duration — its words and its
            # seconds, nothing else.
            " SUM(CASE WHEN final_words > 0 AND duration_sec > 0"
            "  THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN final_words > 0 AND duration_sec > 0"
            "  THEN final_words ELSE 0 END),"
            " SUM(CASE WHEN final_words > 0 AND duration_sec > 0"
            "  THEN duration_sec ELSE 0.0 END),"
            " SUM(CASE WHEN final_words > 0 AND duration_sec IS NULL"
            "  THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN final_words > 0 AND duration_sec <= 0"
            "  THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1"
            "  ELSE 0 END),"
            " SUM(CASE WHEN cleanup_path IS NOT NULL AND"
            "  cleanup_path != 'raw' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN cleanup_path IS NOT NULL AND"
            "  cleanup_path != 'raw' AND fallback_reason IS NOT NULL"
            "  THEN 1 ELSE 0 END),"
            " SUM(COALESCE(dictionary_hits,0)),"
            " SUM(COALESCE(snippet_hits,0)),"
            " MIN(day_local), MAX(day_local)"
            f" FROM usage_facts WHERE {where}", params).fetchone()
        (n, with_text, confirmed, unverified, saved, cancelled, failed,
         raw_words, final_words, seconds, rate_jobs, rate_words,
         rate_seconds, missing_dur, nonpos_dur, fallbacks,
         cleanup_requested, cleanup_fallbacks, dict_hits, snip_hits,
         first_day, last_day) = row
        future = None
        if end is not None:
            future = conn.execute(
                f"SELECT COUNT(*) FROM usage_facts WHERE {cohort}"
                " AND day_local > ?", cparams + [end]).fetchone()[0]
        versions = sorted(r[0] for r in conn.execute(
            f"SELECT DISTINCT word_count_version FROM usage_facts WHERE"
            f" {where} AND word_count_version IS NOT NULL", params))
        latency = self._latencies(conn, where, params)
        # Transform/repaste activity rows carry no destination app or
        # writing mode, so a filtered cohort cannot honestly count
        # them — they surface as None, only the unfiltered view
        # counts them (never a number borrowed from another cohort).
        transforms = repastes = transform_words = None
        if app is None and mode is None:
            aw, ap = self._bounded("1=1", [], start, end)
            transforms, transform_words = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(source_words),0) FROM"
                f" usage_facts WHERE kind='transform' AND {aw}",
                ap).fetchone()
            repastes = conn.execute(
                "SELECT COUNT(*) FROM usage_facts WHERE kind='repaste'"
                f" AND {aw}", ap).fetchone()[0]
        return {
            "reporting_timezone": zone,
            "algorithm_version": ALGORITHM_VERSION,
            "day_start": start,
            "day_end": end,
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
            "word_count_versions": versions,
            "mixed_word_count_versions": len(versions) > 1,
            # Whole-cohort capture seconds (all outcomes) — a separate,
            # honestly-labeled total from the WPM denominator below.
            "capture_seconds": round(seconds or 0.0, 1),
            # Weighted WPM (E06, D01): 60 × sum(words) / sum(seconds)
            # over the rate cohort only — never an average of row WPM,
            # never unknown-duration words; null when the cohort is
            # empty. Excluded text-producing jobs are disclosed.
            "wpm": (round(60.0 * rate_words / rate_seconds, 1)
                    if rate_jobs else None),
            "wpm_denominator": {"jobs": rate_jobs or 0,
                                "words": rate_words or 0,
                                "capture_seconds":
                                    round(rate_seconds or 0.0, 1)},
            "wpm_excluded": {"missing_duration": missing_dur or 0,
                             "nonpositive_duration": nonpos_dur or 0},
            "fallback_jobs": fallbacks or 0,
            # Fallback incidence over ALL dictations (kept under its
            # original key; D05) …
            "fallback_rate": (round((fallbacks or 0) / n, 3)
                              if n else None),
            # … and E06's stage rate over jobs that requested cleanup.
            "cleanup_fallback": {
                "requested": cleanup_requested or 0,
                "fallbacks": cleanup_fallbacks or 0,
                "rate": (round((cleanup_fallbacks or 0)
                               / cleanup_requested, 3)
                         if cleanup_requested else None)},
            "dictionary_hits": dict_hits or 0,
            "snippet_hits": snip_hits or 0,
            "transforms": transforms,
            "transform_words": transform_words,
            "repastes": repastes,
            "latency": latency,
            "future_dated": future,
            "range_first_day": first_day,
            "range_last_day": last_day,
        }

    def _latencies(self, conn, where, params):
        """Sample-aware stage/end-to-end percentiles (D06). Each block
        carries its own n; failures stay in the cohort denominator. The
        end-to-end block counts its missing observations by reason;
        confirmed-visible (E06) is its confirmed subset; a retry's own
        clock is reported apart, never mixed with release clocks."""
        out = {}
        for key, label in (("asr_ms", "asr"), ("cleanup_ms", "cleanup"),
                           ("transform_ms", "transform"),
                           ("end_to_end_ms", "end_to_end")):
            samples = [r[0] for r in conn.execute(
                f"SELECT {key} FROM usage_facts WHERE {where}"
                f" AND {key} IS NOT NULL", params).fetchall()]
            out[label] = self._block(samples, "stage"
                                     if key != "end_to_end_ms"
                                     else "end_to_end")
        out["end_to_end"]["clock"] = "ptt_release_to_terminal_outcome"
        out["end_to_end"]["missing"] = dict(conn.execute(
            "SELECT COALESCE(json_extract(meta_json, '$.e2e_missing'),"
            " 'not_recorded'), COUNT(*) FROM usage_facts WHERE"
            f" {where} AND end_to_end_ms IS NULL GROUP BY 1",
            params).fetchall())
        out["confirmed_visible"] = self._block([r[0] for r in conn.execute(
            f"SELECT end_to_end_ms FROM usage_facts WHERE {where} AND"
            " insertion_outcome='confirmed' AND end_to_end_ms IS NOT NULL",
            params).fetchall()], "end_to_end")
        out["confirmed_visible"]["clock"] = \
            "ptt_release_to_confirmed_visible_text"
        out["retry_to_terminal"] = self._block([r[0] for r in conn.execute(
            "SELECT json_extract(meta_json, '$.retry_to_terminal_ms')"
            f" FROM usage_facts WHERE {where} AND"
            " json_extract(meta_json, '$.retry_to_terminal_ms') IS NOT"
            " NULL", params).fetchall()], "retry")
        out["retry_to_terminal"]["clock"] = "retry_start_to_terminal_outcome"
        return out

    @staticmethod
    def _block(samples, kind):
        return {"n": len(samples), "p50": percentile(samples, 50),
                "p95": percentile(samples, 95),
                "p99": percentile(samples, 99), "kind": kind}

    def _daily(self, conn, days, app, mode, limit=None) -> list[dict]:
        zone, start, end, cohort, cparams = self._ctx(conn, days, app, mode)
        where, params = self._bounded(cohort, cparams, start, end)
        unfiltered = app is None and mode is None
        rows = {r[0]: r for r in conn.execute(
            f"SELECT day_local, COUNT(*),"
            " SUM(COALESCE(raw_words,0)),"
            " SUM(COALESCE(final_words,0)),"
            " SUM(COALESCE(duration_sec,0.0)),"
            " SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1"
            "  ELSE 0 END)"
            f" FROM usage_facts WHERE {where} GROUP BY day_local",
            params).fetchall()}
        activity = {}
        if unfiltered:
            # The unfiltered table's date domain is every activity kind
            # (a transform-only or repaste-only day is a real row).
            aw, ap = self._bounded("kind IN ('transform','repaste')", [],
                                   start, end)
            for day, tf, rp in conn.execute(
                    "SELECT day_local, SUM(kind='transform'),"
                    f" SUM(kind='repaste') FROM usage_facts WHERE {aw}"
                    " GROUP BY day_local", ap).fetchall():
                activity[day] = (tf or 0, rp or 0)
        out = []
        for day in sorted(set(rows) | set(activity), reverse=True):
            r = rows.get(day) or (day, 0, 0, 0, 0.0, 0)
            tf, rp = activity.get(day, (0, 0)) if unfiltered else \
                (None, None)
            out.append({"day": day, "dictations": r[1],
                        "raw_words": r[2] or 0,
                        "final_words": r[3] or 0,
                        "capture_seconds": round(r[4] or 0.0, 1),
                        "fallbacks": r[5] or 0, "transforms": tf,
                        "repastes": rp})
        return out if limit is None else out[:limit]

    def _labels(self, conn):
        """key → display label for every app identity with facts: the
        most recent non-empty name (by activity time) for a bundle; a
        label shared by different keys carries its bundle id, and a
        named app never borrows the distinct Unknown population's label
        (REVIEW-R09)."""
        latest = {}
        for key, name, bundle in conn.execute(
                f"SELECT {_APP_KEY_SQL}, app_name, app_bundle FROM"
                " usage_facts WHERE kind='dictation'"
                " ORDER BY activity_at_utc, rowid"):
            prev = latest.get(key, (None, bundle))
            latest[key] = (name or prev[0], bundle or prev[1])
        base = {}
        for key, (name, bundle) in latest.items():
            if key == "unknown":
                base[key] = "Unknown"
            elif (name or bundle) == "Unknown":
                base[key] = f"“Unknown” ({bundle or 'app name'})"
            else:
                base[key] = name or bundle
        seen = {}
        for key, label in base.items():
            seen.setdefault(label, []).append(key)
        out = {}
        for key, label in base.items():
            bundle = latest[key][1]
            out[key] = (f"{label} ({bundle})"
                        if len(seen[label]) > 1 and bundle else label)
        return out

    def _per_app(self, conn, days, app, mode) -> list[dict]:
        zone, start, end, cohort, cparams = self._ctx(conn, days, app, mode)
        where, params = self._bounded(cohort, cparams, start, end)
        labels = self._labels(conn)
        rows = conn.execute(
            f"SELECT {_APP_KEY_SQL} AS k, COUNT(*),"
            " SUM(COALESCE(final_words,0)),"
            " SUM(COALESCE(duration_sec,0.0))"
            f" FROM usage_facts WHERE {where} GROUP BY k"
            " ORDER BY 2 DESC, k", params).fetchall()
        return [{"key": k, "app": labels.get(k, k), "dictations": n,
                 "final_words": w or 0,
                 "capture_seconds": round(s or 0.0, 1)}
                for k, n, w, s in rows]

    def _per_mode(self, conn, days, app, mode) -> list[dict]:
        zone, start, end, cohort, cparams = self._ctx(conn, days, app, mode)
        where, params = self._bounded(cohort, cparams, start, end)
        rows = conn.execute(
            f"SELECT COALESCE(mode, 'unknown') AS m, COUNT(*),"
            " SUM(COALESCE(final_words,0))"
            f" FROM usage_facts WHERE {where} GROUP BY m"
            " ORDER BY 2 DESC, m", params).fetchall()
        return [{"mode": m, "dictations": n, "final_words": w or 0}
                for m, n, w in rows]

    def _apps_available(self, conn) -> list[dict]:
        labels = self._labels(conn)
        return sorted(({"key": k, "label": v} for k, v in labels.items()),
                      key=lambda o: (o["key"] == "unknown",
                                     o["label"].lower(), o["key"]))

    @staticmethod
    def _modes_available(conn) -> list[str]:
        modes = {r[0] for r in conn.execute(
            "SELECT DISTINCT mode FROM usage_facts WHERE kind='dictation'")}
        out = sorted(m for m in modes if m is not None)
        if None in modes:
            out.append("unknown")
        return out

    @staticmethod
    def _undated(conn) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE stage='legacy_log'"
            " AND role='cleaned_transcript'").fetchone()[0]

    @staticmethod
    def _legacy(conn) -> dict | None:
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

    # ---- public queries (one writer op each) -------------------------------------------

    def summary(self, days=30, app=None, mode=None) -> dict:
        """Cohort summary over the reporting-zone day range: weighted
        WPM with its denominator and exclusions, totals by outcome, both
        fallback metrics, dictionary/snippet hits, transform and repaste
        counts, and sample-aware latency blocks (cohort size stated —
        E06)."""
        return self.store.submit(
            lambda conn: self._summary(conn, days, app, mode))

    def daily(self, days=30, app=None, mode=None,
              limit=None) -> list[dict]:
        """Per-day rows for the dated table, newest first — complete
        unless ``limit`` is given. Unfiltered, every activity date is a
        row; under a cohort filter transform/repaste columns are None
        (activity rows carry no app/mode). Legacy imported rows surface
        only through their own legacy line."""
        return self.store.submit(
            lambda conn: self._daily(conn, days, app, mode, limit))

    def per_app(self, days=30, app=None, mode=None) -> list[dict]:
        """Complete app breakdown of the cohort, keyed by typed identity
        (private usage metadata — store-side only)."""
        return self.store.submit(
            lambda conn: self._per_app(conn, days, app, mode))

    def per_mode(self, days=30, app=None, mode=None) -> list[dict]:
        """Complete writing-mode breakdown of the cohort (the effective
        mode the job ran under; 'unknown' for facts without one)."""
        return self.store.submit(
            lambda conn: self._per_mode(conn, days, app, mode))

    def apps_available(self) -> list[dict]:
        """Every app identity with dictation facts, as typed keys with
        separate display labels (Unknown last)."""
        return self.store.submit(self._apps_available)

    def modes_available(self) -> list[str]:
        return self.store.submit(self._modes_available)

    def undated_count(self) -> int:
        """Legacy log pairs — unknown dates never enter dated views;
        they surface as this explicit count only."""
        return self.store.submit(self._undated)

    def legacy_summary(self) -> dict | None:
        """The imported legacy analytics readout (E13 reconciliation
        figures): row count, raw/cleaned word sums, capture seconds,
        fixed-word sum and the instants — read in place, never
        relabeled. The row-level wpm column's formula is unknown and is
        not reused; the legacy label stays on fixed_words."""
        return self.store.submit(self._legacy)

    def report(self, days=30, app=None, mode=None) -> dict:
        """The whole Insights Usage report in ONE writer op (D10): every
        section reads the same fact generation, stamped with its usage
        revision."""
        def op(conn):
            daily = self._daily(conn, days, app, mode)
            return {
                "usage_revision": conn_usage_revision(conn),
                "summary": self._summary(conn, days, app, mode),
                "daily": daily,
                "daily_total_days": len(daily),
                "per_app": self._per_app(conn, days, app, mode),
                "per_mode": self._per_mode(conn, days, app, mode),
                "undated": self._undated(conn),
                "legacy": self._legacy(conn),
                "apps": self._apps_available(conn),
                "modes": self._modes_available(conn),
            }
        return self.store.submit(op)
