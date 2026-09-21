"""M01: snapshot safety tests (EV-01).

Proves the snapshot routines leave originals byte-identical and produce
parseable/consistent copies, using throwaway fixtures in a temp directory.

Run: .venv/bin/python tests/v2/test_snapshot_safety.py
"""

import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

import scripts.v2.snapshot_user_data as su  # noqa: E402
from scripts.v2.snapshot_user_data import (  # noqa: E402
    snapshot_bytes, snapshot_sqlite, sha256_file,
)


def test_file_snapshot_preserves_original():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "dictionary.json"
        src.write_text('["Qwen", "MLX"]')
        before = sha256_file(src)
        dst = pathlib.Path(td) / "snap" / "dictionary.json"
        got = snapshot_bytes(src, dst)
        assert got == before == sha256_file(src)
        assert dst.read_text() == '["Qwen", "MLX"]'
    print("ok  file snapshot preserves original")


def test_sqlite_backup_is_consistent_and_preserves_original():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "stats.db"
        con = sqlite3.connect(src)
        con.execute("CREATE TABLE dictations (id INTEGER PRIMARY KEY, ts REAL)")
        con.executemany("INSERT INTO dictations (ts) VALUES (?)",
                        [(1751664000.0 + i,) for i in range(7)])
        con.commit()
        con.close()
        before = sha256_file(src)
        dst = pathlib.Path(td) / "snap" / "stats.db.bak"
        got = snapshot_sqlite(src, dst)
        assert sha256_file(src) == before, "original mutated by backup"
        check = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        (n,) = check.execute("SELECT COUNT(*) FROM dictations").fetchone()
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        check.close()
        assert n == 7 and integrity == "ok"
        assert got == sha256_file(dst)
    print("ok  sqlite backup consistent, original unchanged")


def test_snapshot_cli_never_mutates_sources():
    """The full CLI flow (main) must leave live sources byte-identical."""
    with tempfile.TemporaryDirectory() as td:
        app = pathlib.Path(td) / "appsupport"
        app.mkdir()
        (app / "dictionary.json").write_text('["Qwen", "MLX"]')
        (app / "transforms.json").write_text('{"1": {"prompt": "p"}}')
        db = app / "stats.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE dictations (id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()
        logs = pathlib.Path(td) / "logs"
        logs.mkdir()
        log = logs / "LocalFlow.log"
        log.write_bytes(b"[localflow] ready\n" * 10)

        before = {p: sha256_file(p) for p in (
            app / "dictionary.json", app / "transforms.json", db, log)}

        saved_app, saved_log = su.APP_SUPPORT, su.LOG_PATH
        try:
            su.APP_SUPPORT, su.LOG_PATH = app, log
            rc = su.main(["--root", str(pathlib.Path(td) / "evidence")])
        finally:
            su.APP_SUPPORT, su.LOG_PATH = saved_app, saved_log

        assert rc == 0, rc
        for p, sha in before.items():
            assert sha256_file(p) == sha, f"source mutated: {p}"
        manifests = sorted((pathlib.Path(td) / "evidence").glob("*/snapshot-manifest.json"))
        assert manifests, "no snapshot manifest written"
        m = json.loads(manifests[-1].read_text())
        assert m["all_sources_unchanged"] is True
        kinds = {e["kind"] for e in m["entries"]}
        assert {"sqlite_backup", "file_copy", "live_log_full"} <= kinds
    print("ok  snapshot CLI leaves live sources byte-identical")


def test_snapshot_refuses_in_repo_root():
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    import argparse, contextlib, io
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            su.main(["--root", str(repo_root / "docs/v2/private")])
        except SystemExit as e:
            assert e.code != 0
        else:
            raise AssertionError("in-repo root accepted")
    print("ok  snapshot refuses an in-repository evidence root")


if __name__ == "__main__":
    test_file_snapshot_preserves_original()
    test_sqlite_backup_is_consistent_and_preserves_original()
    test_snapshot_cli_never_mutates_sources()
    test_snapshot_refuses_in_repo_root()
    print("all snapshot safety tests passed")
