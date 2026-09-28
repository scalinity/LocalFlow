"""Independent M13 oracles (pure Python — no AppKit, no production
analytics code).

``reference_aggregates`` recomputes every ``daily_aggregates`` field
from raw fact rows with its own zone conversion (``zoneinfo`` directly)
— never through the production bucketing helper, recompute or query
code — and ``compare_aggregates`` checks every field of every day in
both directions. Shared by the portable store suite, the isolated M13
world, the corpus runner and the benchmark's validity gate.
"""

from __future__ import annotations

import datetime as dt
import math
import zoneinfo


def parse_utc(s: str) -> dt.datetime:
    """Python's own ISO reader over a Z-suffixed UTC string."""
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def canonical(iso) -> str:
    """The expected stored form of an admitted instant, derived here:
    Python's ISO reader, then microseconds written out."""
    t = parse_utc(iso).astimezone(dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}Z"


def local_day(iso, zone) -> str:
    return parse_utc(iso).astimezone(zoneinfo.ZoneInfo(zone)).strftime(
        "%Y-%m-%d")


_OUTCOME_COLS = {"confirmed": "insertion_confirmed",
                 "posted_unverified": "insertion_unverified",
                 "saved_not_inserted": "saved_not_inserted",
                 "cancelled": "cancelled", "failed": "failed"}

AGG_FIELDS = ("dictations", "dictations_with_text", "insertion_confirmed",
              "insertion_unverified", "saved_not_inserted", "cancelled",
              "failed", "raw_words", "final_words", "capture_seconds",
              "fallback_jobs", "dictionary_hits", "snippet_hits",
              "transforms", "transform_words", "repastes")


def reference_aggregates(facts, zone, version):
    """{day: {field: value}} reduced from raw fact rows (dicts with the
    usage_facts column names). Days come from each fact's instant in
    ``zone``; every aggregate field is computed here."""
    out = {}
    for f in facts:
        day = local_day(f["activity_at_utc"], zone)
        d = out.setdefault(day, dict.fromkeys(AGG_FIELDS, 0))
        if f["kind"] == "dictation":
            d["dictations"] += 1
            if (f["final_words"] or 0) > 0:
                d["dictations_with_text"] += 1
            col = _OUTCOME_COLS.get(f["insertion_outcome"])
            if col:
                d[col] += 1
            d["raw_words"] += f["raw_words"] or 0
            d["final_words"] += f["final_words"] or 0
            d["capture_seconds"] += f["duration_sec"] or 0.0
            if f["fallback_reason"] is not None:
                d["fallback_jobs"] += 1
            d["dictionary_hits"] += f["dictionary_hits"] or 0
            d["snippet_hits"] += f["snippet_hits"] or 0
        elif f["kind"] == "transform":
            d["transforms"] += 1
            d["transform_words"] += f["source_words"] or 0
        elif f["kind"] == "repaste":
            d["repastes"] += 1
    for d in out.values():
        d["reporting_timezone"] = zone
        d["algorithm_version"] = version
    return out


def compare_aggregates(stored_rows, reference):
    """Every field of every day, both directions (a missing day, an
    extra day, a duplicate day, a wrong zone/version or any wrong number
    is a mismatch). Returns human-readable differences (empty = equal)."""
    diffs = []
    stored = {}
    for r in stored_rows:
        if r["day_local"] in stored:
            diffs.append(f"duplicate aggregate rows for {r['day_local']}")
        stored[r["day_local"]] = r
    for day in sorted(set(stored) | set(reference)):
        s, ref = stored.get(day), reference.get(day)
        if s is None:
            diffs.append(f"{day}: aggregate row missing")
            continue
        if ref is None:
            diffs.append(f"{day}: aggregate row without facts")
            continue
        for k in AGG_FIELDS + ("reporting_timezone", "algorithm_version"):
            a, b = s.get(k), ref.get(k)
            if isinstance(a, float) or isinstance(b, float):
                if not math.isclose(float(a or 0.0), float(b or 0.0),
                                    abs_tol=1e-6):
                    diffs.append(f"{day}.{k}: stored {a!r} != {b!r}")
            elif a != b:
                diffs.append(f"{day}.{k}: stored {a!r} != {b!r}")
    return diffs


def read_rows(conn, table, order="rowid"):
    cur = conn.execute(f"SELECT * FROM {table} ORDER BY {order}")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def store_mismatches(store, zone, version):
    """Read facts and aggregates in ONE writer op, then compare."""
    facts, aggs = store.submit(lambda conn: (
        read_rows(conn, "usage_facts"),
        read_rows(conn, "daily_aggregates", "day_local")))
    return compare_aggregates(aggs, reference_aggregates(facts, zone,
                                                         version))
