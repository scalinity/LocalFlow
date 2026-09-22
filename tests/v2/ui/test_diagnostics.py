"""EV-11 (diagnostics halves) / M09: event reading, job timelines, the
engine/build block and the redacted export. Synthetic events only.

Run: .venv/bin/python tests/v2/ui/test_diagnostics.py
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import diagnostics as diag  # noqa: E402


def _write_events(dirpath, records):
    dirpath.mkdir(parents=True, exist_ok=True)
    with open(dirpath / "events-2026-09-22.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _rec(seq, event, **kw):
    return {"schema_version": 2, "event_id": f"evt-{seq}",
            "timestamp_utc": f"2026-09-22T0{seq % 10}:00:0{seq % 10}.000Z",
            "sequence": seq, "event": event, "level": "INFO",
            **kw}


def test_load_filter_and_timeline():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        _write_events(d, [
            _rec(1, "capture.started", job_id="job-a"),
            _rec(2, "stage.completed", job_id="job-a", stage="asr"),
            _rec(3, "capture.started", job_id="job-b"),
        ])
        with open(d / "events-2026-09-22.jsonl", "a") as f:
            f.write("{not json at all\n")  # unparsable → skipped
        recs = diag.load_events(d)
        assert len(recs) == 3
        assert diag.load_events(d, job_id="job-a") == [
            r for r in recs if r.get("job_id") == "job-a"]
        assert len(diag.load_events(d, last=1)) == 1
        timeline = diag.job_timeline(recs, "job-a")
        assert len(timeline) == 2
        assert "capture.started" in timeline[0]
        assert "stage.completed" in timeline[1]
        assert diag.render(recs[0], utc=True).startswith("2026-09-22")
        print("ok  load/filters/timeline; unparsable lines skipped")


def test_redacted_export_drops_detail():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        _write_events(d, [_rec(1, "app.ready", level="INFO",
                               detail="secret-ish free text")])
        recs = diag.load_events(d)
        out = pathlib.Path(td) / "out.jsonl"
        n = diag.redacted_export(recs, out)
        assert n == 1
        blob = out.read_text()
        assert "secret-ish" not in blob
        assert json.loads(blob)["event"] == "app.ready"
        print("ok  redacted export drops the detail field")


def test_engine_block():
    block = diag.engine_block(
        {"models": {"asr": "parakeet", "asr_revision": "r1",
                    "cleanup": "qwen", "cleanup_revision": "r2"},
         "source_revision": "beef9c0", "pipeline_revision": "m09",
         "config_hash": "h", "runtime": {"mlx": "0.31.2"}},
        {"asr": "ready", "cleanup": "loading"})
    assert block["asr_state"] == "ready"
    assert block["cleanup_state"] == "loading"
    assert block["asr_model"] == "parakeet"
    assert block["source_revision"] == "beef9c0"
    assert block["runtime"] == {"mlx": "0.31.2"}
    blob = json.dumps(block)
    assert "transcript" not in blob.lower()
    print("ok  engine/build block content-free")


if __name__ == "__main__":
    test_load_filter_and_timeline()
    test_redacted_export_drops_detail()
    test_engine_block()
    print("all diagnostics tests passed")
