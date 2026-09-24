"""M01 remediation: the runbook's evidence summarizer
(scripts/v2/m01_verify_summary.py) flags violated invariants and never
reports a clean bill for bad evidence. Inputs are produced by the real
M01 tools on synthetic fixtures.

Needs numpy (via the manifest producer's model helpers).

Run: .venv/bin/python tests/v2/test_m01_verify_summary.py
"""

import contextlib
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.v2.build_baseline_manifest as bm  # noqa: E402
import scripts.v2.m01_verify_summary as vs  # noqa: E402
import scripts.v2.parse_legacy_log as pl  # noqa: E402
import scripts.v2.snapshot_user_data as su  # noqa: E402


def summarize(kind, path):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = vs.main([kind, str(path)])
    return rc, out.getvalue()


def test_snapshot_summary():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        app = td / "app"
        app.mkdir()
        (app / "dictionary.json").write_text("{}")
        (app / "transforms.json").write_text("[]")
        con = sqlite3.connect(app / "stats.db")
        con.execute("CREATE TABLE t (x)")
        con.commit()
        con.close()
        log = td / "LocalFlow.log"
        log.write_text("[localflow] ready\n")
        saved = (su.APP_SUPPORT, su.LOG_PATH)
        su.APP_SUPPORT, su.LOG_PATH = app, log
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                assert su.main(["--root", str(td / "ev")]) == 0
        finally:
            su.APP_SUPPORT, su.LOG_PATH = saved
        run = next(p for p in (td / "ev").iterdir() if not p.name.startswith("."))
        rc, out = summarize("snapshot", run)
        assert rc == 0 and "0 invariant(s) violated" in out, out
        os.chmod(run / "dictionary.json", 0o644)
        rc, out = summarize("snapshot", run)
        assert rc == 1 and "CHECK every evidence file is 0600" in out, out
    print("ok  snapshot summary: clean run OK, loosened file flagged")


def test_parse_summary_rejects_wrong_source():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "r.json"
        p.write_text(json.dumps(pl.parse_bytes(b"[localflow] ready\n")))
        rc, out = summarize("parse", p)
        assert rc == 1
        assert "CHECK report is bound to the audited artifact hash" in out
        assert "CHECK pairs = 0 (E02: 749)" in out
    print("ok  parse summary never passes a non-audited source")


def test_probe_summary_flags_fallbacks_and_failures():
    base = {"run_id": "x", "errors": [], "stages": [],
            "config": {"matches_runtime_load": True},
            "cleanup_selection": {"selected_by": "config",
                                  "configured_implementation": "v2",
                                  "probed_implementation": "v2"},
            "summary": {"stages_failed": 0, "fallback_runs": 0}}
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "probe.json"
        p.write_text(json.dumps(base))
        assert summarize("probe", p)[0] == 0
        for mutate, text in (
                (lambda r: r["summary"].__setitem__("fallback_runs", 2),
                 "CHECK no cleanup run fell back"),
                (lambda r: r["summary"].__setitem__("stages_failed", 1),
                 "CHECK no requested stage failed"),
                (lambda r: r["cleanup_selection"].__setitem__(
                    "probed_implementation", "v1"),
                 "CHECK probed implementation is the configured one")):
            r = json.loads(json.dumps(base))
            mutate(r)
            p.write_text(json.dumps(r))
            rc, out = summarize("probe", p)
            assert rc == 1 and text in out, (text, out)
    print("ok  probe summary flags fallbacks, failures and wrong selection")


def test_manifest_summary():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        repo = td / "repo"
        repo.mkdir()
        for args in (["init", "-q"], ["config", "user.email", "t@e.invalid"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(repo), *args], check=True)
        (repo / "config.json").write_text('{"cleanup": "llm"}')
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"],
                       check=True)
        hub = td / "hub"
        for mid in ("mlx-community/parakeet-tdt-0.6b-v3",
                    "mlx-community/Qwen3-4B-Instruct-2507-4bit"):
            snap = hub / ("models--" + mid.replace("/", "--")) / "snapshots" / "r1"
            snap.mkdir(parents=True)
            (snap / "config.json").write_text("{}")
            (snap / "model.safetensors").write_bytes(b"w")
        home = td / "home"
        home.mkdir()
        saved = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        try:
            m = bm.build(root=repo, app=td / "absent.app",
                         env={"HF_HUB_CACHE": str(hub)})
            m_nocache = bm.build(root=repo, app=td / "absent.app",
                                 env={"HF_HUB_CACHE": str(td / "empty")},
                                 hash_model_files=False)
        finally:
            os.environ["HOME"] = saved
        p = td / "m.json"
        p.write_text(json.dumps(m))
        rc, out = summarize("manifest", p)
        assert rc == 0, out
        p.write_text(json.dumps(m_nocache))
        rc, out = summarize("manifest", p)
        assert rc == 1 and "usable snapshot in the resolved cache" in out
    print("ok  manifest summary: consistent run OK, missing model cache flagged")


if __name__ == "__main__":
    test_snapshot_summary()
    test_parse_summary_rejects_wrong_source()
    test_probe_summary_flags_fallbacks_and_failures()
    test_manifest_summary()
    print("all m01 verify summary tests passed (4)")
