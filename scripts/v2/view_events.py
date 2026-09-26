"""M02: human-readable view and redacted export of the V2 event log.

The viewer renders the same JSONL events the writer persists (Spec S07
human view); changing the display timezone never changes stored instants.

Redacted export (M02-AUDIT-12): a versioned, TYPED ALLOWLIST. Only the
envelope fields in ``REDACTION_ALLOWLIST`` survive, each only when its
value passes that field's type/shape check (ids must look like minted
ids, codes like code tokens, numbers like numbers); anything else —
``detail``, any unknown or future field, any nested value, any value of
the wrong type or shape, and any string the local secret scanner flags —
is omitted. Each exported record carries ``redaction_version`` and a
content-free ``omitted_fields`` count. Nothing is exported because it is
merely "not called detail".

Ordering (M02-AUDIT-20): records from every file (active, numbered
rolls, other-process files) are merged by an explicit policy, never by
filename order. A stream is one writer instance (boot_id, session_id,
process_id); WITHIN a stream the writer's sequence is authoritative;
ACROSS streams records merge by their UTC instant. A stream whose
instants go backwards (a wall-clock rollback) is kept in sequence order
and reported on stderr: cross-stream placement near that point is
ambiguous and is not presented as certain. ``--last N`` takes the last
N records of that merged order after filtering.

Usage:
    .venv/bin/python scripts/v2/view_events.py [--date YYYY-MM-DD] [--utc]
        [--job ID] [--level LEVEL] [--last N]
        [--export-redacted PATH]
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from localflow.v2.eventlog import EventWriter  # noqa: E402
# The accepted ordering and typed redaction live in the package so the
# Hub's Diagnostics view uses the same policy (M09-AUDIT-08/18).
from localflow.v2.event_view import (  # noqa: E402,F401
    REDACTION_ALLOWLIST, REDACTION_VERSION, order_records, redact)

DEFAULT_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow"


def load_records(log_dir: pathlib.Path, date: str | None):
    files = sorted(log_dir.glob("events-*.jsonl*"))
    if date:
        files = [f for f in files if date in f.name]
    recs = []
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"warning: unparsable line in {f.name}", file=sys.stderr)
                continue
            if isinstance(rec, dict):
                recs.append(rec)
    return order_records(recs)


def human(rec, utc: bool) -> str:
    # Same S07 layout the writer mirrors to a TTY; one implementation,
    # with the viewer's UTC/local display choice layered on top.
    return EventWriter.human_line(rec, utc=utc)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=pathlib.Path, default=DEFAULT_DIR)
    ap.add_argument("--date", help="UTC date filter, e.g. 2026-09-21")
    ap.add_argument("--utc", action="store_true",
                    help="display instants in UTC instead of local time")
    ap.add_argument("--job", help="filter by job_id")
    ap.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ap.add_argument("--last", type=int, help="show only the last N events")
    ap.add_argument("--export-redacted", type=pathlib.Path,
                    help="write a content-free JSONL export to this path")
    args = ap.parse_args(argv)

    recs = load_records(args.dir, args.date)
    if args.job:
        recs = [r for r in recs if r.get("job_id") == args.job]
    if args.level:
        recs = [r for r in recs if r.get("level") == args.level]
    if args.last:  # applied after filtering: "last N of the matching set"
        recs = recs[-args.last:]

    if args.export_redacted:
        out_path = args.export_redacted
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for r in recs:
                red = redact(r)
                f.write(json.dumps(red, ensure_ascii=True,
                                   separators=(",", ":")) + "\n")
        print(f"wrote {len(recs)} redacted events to {out_path}")
        return 0

    for r in recs:
        print(human(r, args.utc))
    if not recs:
        print("no events matched", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
