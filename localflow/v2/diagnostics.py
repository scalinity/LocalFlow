"""Diagnostics data assembly (V2 M09, Spec S19 Diagnostics, S07 viewer).

Reads the same JSONL event files the writer persists (one
implementation of the human view, layered with the viewer's UTC/local
display choice — changing display timezone never changes stored
instants), assembles dated job timelines, and writes the content-free
redacted export.

Ordering and redaction are the accepted M02 policy shared with the CLI
viewer (``localflow/v2/event_view.py``): records merge per writer
stream by sequence and across streams by UTC instant — never by
filename order — and the export keeps only typed, allowlisted fields
with a redaction version and an omitted-field count.
"""

from __future__ import annotations

import json
import pathlib

from .event_view import order_records, redact
from .eventlog import EventWriter


def load_events(events_dir, date=None, job_id=None, level=None,
                last=None, stats=None) -> list[dict]:
    """Filtered event records in the accepted view order. Unparsable
    lines and valid JSON that is not an event object are skipped with a
    content-free warning (a transcript can never break the reader, and
    the warning never echoes the line); ``stats['skipped']`` counts
    them. ``last`` is the last N of the ordered, filtered set."""
    import sys
    files = sorted(pathlib.Path(events_dir).glob("events-*.jsonl*"))
    if date:
        files = [f for f in files if date in f.name]
    recs = []
    skipped = 0
    for f in files:
        for line in f.read_text(encoding="utf-8",
                                errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                rec = None
            if not isinstance(rec, dict):
                skipped += 1
                continue
            recs.append(rec)
    if skipped:
        print(f"warning: {skipped} unparsable or non-event line(s)"
              " skipped", file=sys.stderr)
    if stats is not None:
        stats["skipped"] = stats.get("skipped", 0) + skipped
    return select_events(order_records(recs, warn=False), job_id=job_id,
                         level=level, last=last)


def select_events(records, job_id=None, level=None, last=None):
    """Filter then window an already ordered record list."""
    if job_id:
        records = [r for r in records if r.get("job_id") == job_id]
    if level:
        records = [r for r in records if r.get("level") == level]
    if last:
        records = records[-last:]
    return list(records)


def render(rec, utc: bool) -> str:
    return EventWriter.human_line(rec, utc=utc)


def job_timeline(events, job_id, utc: bool = False) -> list[str]:
    """One job's dated timeline: stage transitions, failures and the
    insertion outcome, in the accepted view order, shown in the same
    UTC/local policy as the event list."""
    rows = [r for r in order_records(list(events), warn=False)
            if r.get("job_id") == job_id]
    return [render(r, utc=utc) for r in rows]


def redacted_export(records, path) -> int:
    """Write the content-free JSONL export: every record through the
    accepted typed allowlist (``event_view.redact``)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(redact(r), ensure_ascii=True,
                               separators=(",", ":")) + "\n")
    return len(records)


def engine_block(pipeline_info: dict, engine_states: dict) -> dict:
    """The Models/Diagnostics 'both engine states + effective build'
    block: model ids/revisions, runtime versions, config hash and the
    per-engine lifecycle state — all content-free."""
    models = (pipeline_info or {}).get("models") or {}
    return {
        "asr_state": engine_states.get("asr", "not_started"),
        "cleanup_state": engine_states.get("cleanup", "not_started"),
        "asr_model": models.get("asr"),
        "asr_revision": models.get("asr_revision"),
        "cleanup_model": models.get("cleanup"),
        "cleanup_revision": models.get("cleanup_revision"),
        "source_revision": (pipeline_info or {}).get("source_revision"),
        "pipeline_revision": (pipeline_info or {}).get("pipeline_revision"),
        "config_hash": (pipeline_info or {}).get("config_hash"),
        "runtime": (pipeline_info or {}).get("runtime"),
    }
