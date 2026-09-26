"""The accepted event-view policy (M02-AUDIT-12/20), shared by the CLI
viewer (``scripts/v2/view_events.py``) and the Hub's Diagnostics view —
one ordering and one redaction policy, never two.

Ordering (M02-AUDIT-20): records from every file (active, numbered
rolls, other-process files) are merged by an explicit policy, never by
filename order. A stream is one writer instance (boot_id, session_id,
process_id); WITHIN a stream the writer's sequence is authoritative;
ACROSS streams records merge by their UTC instant. A stream whose
instants go backwards (a wall-clock rollback) is kept in sequence order
and reported on stderr: cross-stream placement near that point is
ambiguous and is not presented as certain.

Redacted export (M02-AUDIT-12): a versioned, TYPED ALLOWLIST. Only the
envelope fields in ``REDACTION_ALLOWLIST`` survive, each only when its
value passes that field's type/shape check (ids must look like minted
ids, codes like code tokens, numbers like numbers); anything else —
``detail``, any unknown or future field, any nested value, any value of
the wrong type or shape, and any string the local secret scanner flags —
is omitted. Each exported record carries ``redaction_version`` and a
content-free ``omitted_fields`` count.
"""

from __future__ import annotations

import datetime as dt
import heapq
import re
import sys


def _instant(rec):
    ts = rec.get("timestamp_utc")
    try:
        return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return float("-inf")  # unparsable instants sort first, honestly


def _seq(rec):
    s = rec.get("sequence")
    return s if isinstance(s, int) and not isinstance(s, bool) else -1


def order_records(recs, warn=True):
    """The declared view order (see module doc): per-stream sequence,
    cross-stream UTC instant merge."""
    streams = {}
    for r in recs:
        key = (str(r.get("boot_id")), str(r.get("session_id")),
               str(r.get("process_id")))
        streams.setdefault(key, []).append(r)
    ordered_streams = []
    for key, items in streams.items():
        items.sort(key=lambda r: (_seq(r), _instant(r)))
        back = sum(1 for a, b in zip(items, items[1:])
                   if _instant(b) < _instant(a))
        if back and warn:
            print(f"warning: wall clock went backwards {back} time(s) within"
                  " one writer stream; that stream is shown in sequence"
                  " order and its placement relative to other streams near"
                  " those points is ambiguous", file=sys.stderr)
        ordered_streams.append(items)
    # k-way merge by instant; ties keep stream-internal order.
    return list(heapq.merge(*ordered_streams, key=_instant))


# ---- redacted export: versioned typed allowlist (M02-AUDIT-12) ----------

REDACTION_VERSION = 2
_ID = r"[a-z]+-[0-9a-f]{32}"
_CODE = re.compile(r"^[A-Za-z0-9_.:\-]{1,96}$")
_HEX = re.compile(r"^[0-9a-f]{6,128}$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return (_is_int(v) or isinstance(v, float)) and v == v


def _match(pattern):
    rx = re.compile(pattern)
    return lambda v: isinstance(v, str) and bool(rx.match(v))


def _id_of(*kinds):
    return _match(r"^(?:" + "|".join(kinds) + r")-[0-9a-f]{32}$")


def _code(v):
    return isinstance(v, str) and bool(_CODE.match(v))


def _opt(check):
    return lambda v: v is None or check(v)


REDACTION_ALLOWLIST = {
    "schema_version": _is_int,
    "event_id": _id_of("evt"),
    "timestamp_utc": _match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$"),
    "timezone": _opt(_match(r"^[A-Za-z_+\-/0-9]{1,64}$")),
    "utc_offset_minutes": _opt(_is_int),
    "boot_id": _opt(_id_of("boot")),
    "session_id": _opt(_id_of("session")),
    "process_id": _opt(_is_int),
    "worker_generation": _opt(_is_int),
    "source_revision": _opt(_match(r"^[0-9a-zA-Z_.\-+]{1,64}$")),
    "pipeline_revision": _opt(_code),
    "sequence": _opt(_is_int),
    "job_id": _opt(_id_of("job")),
    "attempt": _opt(_is_int),
    "stage": _opt(_code),
    "event": _code,
    "level": lambda v: v in ("DEBUG", "INFO", "WARNING", "ERROR"),
    "outcome": _opt(_code),
    "reason_code": _opt(_code),
    "duration_ms": _opt(_is_num),
    "queue_wait_ms": _opt(_is_num),
    # A hub id ("name" or "org/name"), never a filesystem path: a
    # locally configured model directory would carry a home path.
    "model_id": _opt(_match(r"^[A-Za-z0-9_.\-]{1,64}"
                            r"(?:/[A-Za-z0-9_.\-]{1,64})?$")),
    "model_revision": _opt(_code),
    "config_hash": _opt(lambda v: isinstance(v, str) and bool(_HEX.match(v))),
    "prompt_hash": _opt(lambda v: isinstance(v, str) and bool(_HEX.match(v))),
    "artifact_ids": _opt(lambda v: isinstance(v, list) and len(v) <= 64
                         and all(_id_of("art")(a) for a in v)),
}


def _secret_like(v) -> bool:
    try:
        from .training import scan_secrets
    except Exception:  # scanner unavailable: be conservative
        return isinstance(v, str)
    vals = v if isinstance(v, list) else [v]
    return any(isinstance(x, str) and scan_secrets(x) for x in vals)


def redact(rec: dict) -> dict:
    """One content-free record: allowlisted, type-checked fields only."""
    out = {}
    omitted = 0
    for key, value in rec.items():
        check = REDACTION_ALLOWLIST.get(key)
        if check is None or not check(value) or _secret_like(value):
            omitted += 1
            continue
        out[key] = value
    out["redaction_version"] = REDACTION_VERSION
    out["omitted_fields"] = omitted
    return out
