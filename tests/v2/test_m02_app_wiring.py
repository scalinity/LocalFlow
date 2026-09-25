"""M02 remediation: STATIC wiring checks of localflow/app.py (AppKit).

The app delegate imports AppKit/PyObjC and cannot be imported in a
portable (non-macOS) run. These checks parse the source with ``ast`` and
assert that the call sites the M02 repairs depend on exist in the right
functions and order. They are NOT native verification: behavior of the
running app stays PENDING_LOCAL_VERIFICATION (VERIFICATION.html M02-V*).

Run: .venv/bin/python tests/v2/test_m02_app_wiring.py
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "localflow" / "app.py"
TREE = ast.parse(APP.read_text())


def fn(name):
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def src(node):
    """Unparsed source with quotes normalized (ast.unparse emits ')."""
    return ast.unparse(node).replace("'", '"')


def calls(node):
    """Dotted call names in source order."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            out.append((n.lineno, n.col_offset, ast.unparse(n.func)))
    return [name for _, _, name in sorted(out)]


def test_consent_snapshot_at_ptt_down():
    ptt = None
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and any(
                "self.consent.capture_snapshot" == c for c in calls(node)):
            ptt = node
    assert ptt is not None, "no PTT-down consent snapshot"
    names = calls(ptt)
    # Taken after the job is minted and before capture starts.
    assert names.index("self.store.create_job") \
        < names.index("self.consent.capture_snapshot") \
        < names.index("self.recorder.start")
    body = src(ptt)
    assert '"consent": consent_snapshot' in body
    fin = src(fn("_finishCapture"))
    assert 'consent_snapshot=job.get("consent")' in fin
    retry = src(fn("_retry_job"))
    assert "consent_snapshot=self.collector.retry_snapshot(job_id)" in retry
    print("ok  06 wiring: snapshot at PTT down (after create_job, before"
          " recorder.start); finishCapture and retry pass snapshots")


def test_attempt_propagation():
    worker = src(fn("_worker"))
    assert worker.count("self.collector.note_attempt(") == 2
    assert 'stage="asr"' in worker and 'stage="cleanup"' in worker
    print("ok  09 wiring: both automatic-retry sites propagate the attempt")


def test_debug_copy_and_job_dirs():
    cfg = src(fn("configure"))
    assert "register_job_payload_dir(AUDIO_DEBUG_DIR" in cfg
    assert "register_job_payload_dir(V2_JOURNAL" in cfg
    assert "config_mod.retention_policy(cfg)" in cfg
    assert "config_mod.event_retention_policy(cfg)" in cfg
    assert "int(cfg.get(\"retention_" not in cfg
    assert "self._dump_audio(audio, job_id)" in src(fn("_worker"))
    dump = src(fn("_dump_audio"))
    assert "v2_debug_audio.write_debug_copy" in dump
    assert dump.index("self.store.job_deleted(job_id)") \
        < dump.index("write_debug_copy")
    hub = src(fn("hubApplyRetention"))
    assert "validate_retention_value" in hub
    print("ok  02/19 wiring: job-named debug copy + registered job dirs;"
          " validated retention at startup and in the Hub")


def test_shutdown_drains_writers():
    term = calls(fn("applicationWillTerminate_"))
    assert term.index("self.supervisor.shutdown") \
        < term.index("self._shutdown_persistence")
    sd = calls(fn("_shutdown_persistence"))
    assert sd.index("self.store.close") < sd.index("self.v2log.close")
    print("ok  15 wiring: quit stops producers, drains the store, then the"
          " event writer")


def main():
    tests = [test_consent_snapshot_at_ptt_down, test_attempt_propagation,
             test_debug_copy_and_job_dirs, test_shutdown_drains_writers]
    for t in tests:
        t()
    print(f"all m02 app wiring (static) checks passed ({len(tests)})")


if __name__ == "__main__":
    main()
