"""Diagnostics data assembly (V2 M09, Spec S19 Diagnostics, S07 viewer).

Reads the same JSONL event files the writer persists (one
implementation of the human view, layered with the viewer's UTC/local
display choice — changing display timezone never changes stored
instants), assembles dated job timelines, and writes the content-free
redacted export (every record verbatim except ``detail``, the one
free-text field, which is dropped — the M02 belt-and-suspenders rule).
"""

from __future__ import annotations

import json
import pathlib

from .eventlog import EventWriter


def load_events(events_dir, date=None, job_id=None, level=None,
                last=None) -> list[dict]:
    """Filtered event records, oldest first. Unparsable lines warn to
    stderr and are skipped (a transcript can never break the reader)."""
    import sys
    files = sorted(pathlib.Path(events_dir).glob("events-*.jsonl*"))
    if date:
        files = [f for f in files if date in f.name]
    recs = []
    for f in files:
        for line in f.read_text(encoding="utf-8",
                                errors="replace").splitlines():
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"warning: unparsable line in {f.name}",
                      file=sys.stderr)
                continue
    if job_id:
        recs = [r for r in recs if r.get("job_id") == job_id]
    if level:
        recs = [r for r in recs if r.get("level") == level]
    if last:
        recs = recs[-last:]
    return recs


def render(rec, utc: bool) -> str:
    return EventWriter.human_line(rec, utc=utc)


def job_timeline(events, job_id) -> list[str]:
    """One job's dated timeline: stage transitions, failures and the
    insertion outcome, rendered in sequence order."""
    rows = [r for r in events if r.get("job_id") == job_id]
    rows.sort(key=lambda r: (r.get("sequence") or 0,))
    return [render(r, utc=False) for r in rows]


def redacted_export(records, path) -> int:
    """Write the content-free JSONL export (drops ``detail``)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            red = dict(r)
            red.pop("detail", None)
            f.write(json.dumps(red, ensure_ascii=True,
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
