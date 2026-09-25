"""M01: snapshot safety tests (EV-01).

Proves the snapshot routines leave originals byte-identical and produce
parseable/consistent copies, using throwaway fixtures in a temp directory.
The M01 remediation (M01-AUDIT-06/12) adds regressions for exclusive run
allocation, symlink refusal, private permissions, WAL-aware change
detection, explicit missing/error inventory, log-append status and
unpublished partial runs under injected I/O faults.

Run: .venv/bin/python tests/v2/test_snapshot_safety.py
"""

import contextlib
import datetime as dt
import errno
import io
import json
import os
import pathlib
import sqlite3
import stat
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

import scripts.v2.snapshot_user_data as su  # noqa: E402
from scripts.v2.snapshot_user_data import (  # noqa: E402
    snapshot_bytes, snapshot_sqlite, sha256_file,
)

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def make_sources(td, *, wal=False):
    td = pathlib.Path(td)
    app = td / "appsupport"
    app.mkdir()
    (app / "dictionary.json").write_text('{"terms": ["Qwen", "MLX"]}')
    (app / "transforms.json").write_text('[{"key": "1", "prompt": "p"}]')
    db = app / "stats.db"
    con = sqlite3.connect(db)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE dictations (id INTEGER PRIMARY KEY, ts REAL)")
    con.executemany("INSERT INTO dictations (ts) VALUES (?)",
                    [(1751664000.0 + i,) for i in range(7)])
    con.commit()
    con.close()
    logs = td / "logs"
    logs.mkdir()
    log = logs / "LocalFlow.log"
    log.write_bytes(b"[localflow] ready\n" * 10)
    return app, log


@contextlib.contextmanager
def patched(**attrs):
    saved = {k: getattr(su, k) for k in attrs}
    try:
        for k, v in attrs.items():
            setattr(su, k, v)
        yield
    finally:
        for k, v in saved.items():
            setattr(su, k, v)


def run(app, log, root, **extra):
    out, err = io.StringIO(), io.StringIO()
    with patched(APP_SUPPORT=app, LOG_PATH=log, **extra), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = su.main(["--root", str(root)])
    return rc, err.getvalue()


def published(root):
    return sorted(p for p in pathlib.Path(root).iterdir()
                  if not p.name.startswith("."))


def manifest_of(run_dir):
    return json.loads((run_dir / su.MANIFEST_NAME).read_text())


# ---- inherited M01 cases -------------------------------------------------

@case
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


@case
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


@case
def test_snapshot_cli_never_mutates_sources():
    """The full CLI flow (main) must leave live sources byte-identical."""
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        before = {p: sha256_file(p) for p in (
            app / "dictionary.json", app / "transforms.json",
            app / "stats.db", log)}
        rc, _ = run(app, log, pathlib.Path(td) / "evidence")
        assert rc == 0, rc
        for p, sha in before.items():
            assert sha256_file(p) == sha, f"source mutated: {p}"
        runs = published(pathlib.Path(td) / "evidence")
        assert len(runs) == 1, runs
        m = manifest_of(runs[0])
        assert m["all_sources_unchanged"] is True
        assert m["outcome"] == "complete" and m["complete"] is True
        kinds = {e["kind"] for e in m["entries"]}
        assert {"sqlite_backup", "file_copy", "live_log_full"} <= kinds
    print("ok  snapshot CLI leaves live sources byte-identical")


@case
def test_snapshot_refuses_in_repo_root():
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    with contextlib.redirect_stderr(io.StringIO()) as err:
        rc = su.main(["--root", str(repo_root / "docs/v2/private")])
    assert rc == su.EXIT_REFUSED, rc
    assert "must live outside the repository" in err.getvalue()
    assert not (repo_root / "docs/v2/private").exists()
    print("ok  snapshot refuses an in-repository evidence root (exit 3)")


@case
def test_snapshot_refuses_roots_in_other_worktrees_of_the_repo():
    # The runbook runs the tool from a verification worktree; the user's
    # main checkout is ANOTHER worktree of the same repository and must be
    # refused too (review finding on the first remediation pass).
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        main_wt = td / "LocalFlow"
        main_wt.mkdir()
        for args in (["init", "-q"], ["config", "user.email", "t@e.invalid"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(main_wt), *args], check=True)
        (main_wt / "README").write_text("x")
        subprocess.run(["git", "-C", str(main_wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(main_wt), "commit", "-q", "-m", "i"],
                       check=True)
        verify = td / "LocalFlow-m01-verify"
        subprocess.run(["git", "-C", str(main_wt), "worktree", "add", "-q",
                        "--detach", str(verify)], check=True)
        for root in (main_wt / "docs" / "v2" / "private", main_wt,
                     verify / "x", td / "link-into-main" / "x"):
            if root.parent.name == "link-into-main":
                root.parent.symlink_to(main_wt, target_is_directory=True)
            try:
                su.prepare_root(root, repo_root=verify)
            except su.EvidenceRootError:
                pass
            else:
                raise AssertionError(f"accepted {root}")
        assert not (main_wt / "docs").exists()
        ok = su.prepare_root(td / "evidence", repo_root=verify)
        assert ok["created_by_this_run"] is True
    print("ok  roots inside any worktree of the repository are refused")


@case
def test_usage_errors_do_not_collide_with_outcomes():
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            su.main(["--no-such-flag"])
        except SystemExit as e:
            assert e.code == su.EXIT_USAGE, e.code
        else:
            raise AssertionError("usage error not raised")
    print("ok  usage error exits 64, distinct from incomplete (2)")


# ---- M01-AUDIT-06: allocation, confinement, permissions --------------------

@case
def test_same_instant_runs_never_share_or_overwrite():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        root = pathlib.Path(td) / "evidence"
        frozen = dt.datetime(2026, 9, 24, 12, 0, 0, tzinfo=dt.timezone.utc)

        class FrozenDT:
            timezone = dt.timezone

            class datetime:
                @staticmethod
                def now(tz=None):
                    return frozen

        assert run(app, log, root, dt=FrozenDT)[0] == 0
        first = published(root)
        first_copy = (first[0] / "dictionary.json").read_bytes()
        (app / "dictionary.json").write_text('{"terms": ["changed"]}')
        assert run(app, log, root, dt=FrozenDT)[0] == 0
        runs = published(root)
        assert len(runs) == 2, runs
        assert runs[0].name != runs[1].name
        assert (first[0] / "dictionary.json").read_bytes() == first_copy, \
            "first run's evidence was overwritten"
    print("ok  same-instant runs get distinct directories; nothing overwritten")


@case
def test_exclusive_writes_refuse_existing_files_and_leaf_symlinks():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        src = td / "src.json"
        src.write_text("new")
        victim = td / "victim.txt"
        victim.write_text("UNRELATED EVIDENCE")
        snap = td / "snap"
        snap.mkdir()
        (snap / "dictionary.json").symlink_to(victim)
        (snap / "existing.json").write_text("old evidence")
        for name in ("dictionary.json", "existing.json"):
            try:
                snapshot_bytes(src, snap / name)
            except OSError as e:
                assert e.errno in (errno.EEXIST, errno.ELOOP), e
            else:
                raise AssertionError(f"{name}: write went through")
        assert victim.read_text() == "UNRELATED EVIDENCE"
        assert (snap / "existing.json").read_text() == "old evidence"
        try:
            snapshot_sqlite(src, snap / "dictionary.json")
        except OSError:
            pass
        else:
            raise AssertionError("sqlite backup followed a leaf symlink")
        assert victim.read_text() == "UNRELATED EVIDENCE"
    print("ok  exclusive writes refuse existing files and leaf symlinks")


@case
def test_root_and_descendant_confinement():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        app, log = make_sources(td)
        elsewhere = td / "elsewhere"
        elsewhere.mkdir()
        # A symlinked evidence root is refused outright.
        link_root = td / "link-root"
        link_root.symlink_to(elsewhere, target_is_directory=True)
        assert run(app, log, link_root)[0] == su.EXIT_REFUSED, \
            "symlinked root accepted"
        # A group/other-writable root is refused.
        loose = td / "loose"
        loose.mkdir()
        os.chmod(loose, 0o777)
        assert run(app, log, loose)[0] == su.EXIT_REFUSED, \
            "world-writable root accepted"
        # A pre-planted symlink at the staging/run name is never followed:
        # the staging directory is created exclusively.
        root = td / "evidence"
        root.mkdir(mode=0o700)
        planted = "20260924T120000.000000Z-deadbeef"
        (root / f".{planted}{su.PARTIAL_SUFFIX}").symlink_to(
            elsewhere, target_is_directory=True)
        rc, err = run(app, log, root, new_run_id=lambda now=None: planted)
        assert rc == 1 and "not published" in err, (rc, err)
        assert list(elsewhere.iterdir()) == [], "evidence escaped the root"
        # And a pre-existing directory with the final run name is never
        # merged into or replaced.
        other = "20260924T120001.000000Z-cafef00d"
        (root / other).mkdir()
        (root / other / "keep.txt").write_text("unrelated")
        rc, err = run(app, log, root, new_run_id=lambda now=None: other)
        assert rc == 1, rc
        assert sorted(p.name for p in (root / other).iterdir()) == ["keep.txt"]
    print("ok  root/descendant symlinks and existing run names are refused")


@case
def test_private_permissions_under_permissive_umask():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        root = pathlib.Path(td) / "evidence"
        old = os.umask(0)
        try:
            rc, _ = run(app, log, root)
        finally:
            os.umask(old)
        assert rc == 0
        assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
        for p in root.rglob("*"):
            mode = stat.S_IMODE(os.lstat(p).st_mode)
            want = 0o700 if p.is_dir() else 0o600
            assert mode == want, (p, oct(mode))
    print("ok  root 0700, run dirs 0700, files 0600 under umask 000")


# ---- M01-AUDIT-12: WAL, inventory, log status, faults ----------------------

@case
def test_wal_backed_write_during_snapshot_is_detected():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td, wal=True)
        db = app / "stats.db"
        writer = sqlite3.connect(db)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO dictations (ts) VALUES (1.0)")
        writer.commit()  # committed into -wal, not the main file
        real = su.snapshot_sqlite

        def racing(src, dst):
            out = real(src, dst)
            writer.execute("INSERT INTO dictations (ts) VALUES (2.0)")
            writer.commit()
            return out
        main_before = sha256_file(db)
        rc, _ = run(app, log, pathlib.Path(td) / "ev", snapshot_sqlite=racing)
        assert sha256_file(db) == main_before, "precondition: main file static"
        writer.close()
        assert rc == 1, rc
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        e = next(x for x in m["entries"] if x["kind"] == "sqlite_backup")
        assert e["status"] == "changed_during_snapshot", e
        assert e["companions"]["-wal"]["exists"] is True
        assert m["all_sources_unchanged"] is False and m["outcome"] == "failed"
    print("ok  WAL-only write during snapshot is detected (main file unchanged)")


@case
def test_wal_content_is_captured_consistently():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td, wal=True)
        writer = sqlite3.connect(app / "stats.db")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO dictations (ts) VALUES (99.0)")
        writer.commit()
        rc, _ = run(app, log, pathlib.Path(td) / "ev")
        writer.close()
        assert rc == 0
        snap = published(pathlib.Path(td) / "ev")[0] / "stats.db.bak"
        con = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
        (n,) = con.execute("SELECT COUNT(*) FROM dictations").fetchone()
        con.close()
        assert n == 8, n  # 7 checkpointed + 1 only in the WAL
    print("ok  uncheckpointed WAL rows are in the snapshot")


@case
def test_idle_wal_database_is_not_a_false_change():
    # A WAL-mode database with no open connection and no -wal file (the
    # installed pre-M02 app never opens stats.db): SQLite's own read-only
    # open creates an empty -wal/-shm. That is recorded as a side effect,
    # not reported as a content change.
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td, wal=True)
        db = app / "stats.db"
        assert not pathlib.Path(str(db) + "-wal").exists()
        main_before = sha256_file(db)
        rc, _ = run(app, log, pathlib.Path(td) / "ev")
        assert rc == 0, rc
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        e = next(x for x in m["entries"] if x["kind"] == "sqlite_backup")
        assert e["status"] == "unchanged", e
        assert sha256_file(db) == main_before
        created = e["companions_created_by_read"]
        assert "-wal" in created, created
        assert pathlib.Path(str(db) + "-wal").stat().st_size == 0
    print("ok  idle WAL database: read-created empty companions recorded, not a change")


@case
def test_missing_required_source_is_inventoried_and_incomplete():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        (app / "transforms.json").unlink()
        rc, err = run(app, log, pathlib.Path(td) / "ev")
        assert rc == 2, rc
        assert "INCOMPLETE" in err
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        e = next(x for x in m["entries"]
                 if x["source"].endswith("transforms.json"))
        assert e["status"] == "missing" and e["required"] is True
        assert m["outcome"] == "incomplete" and m["complete"] is False
        assert m["missing_required"] == [str(app / "transforms.json")]
    print("ok  missing required source -> explicit entry, incomplete, exit 2")


@case
def test_all_missing_is_incomplete_not_green():
    with tempfile.TemporaryDirectory() as td:
        empty = pathlib.Path(td) / "empty"
        empty.mkdir()
        rc, _ = run(empty, empty / "no.log", pathlib.Path(td) / "ev")
        assert rc == 2, rc
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        assert [e["status"] for e in m["entries"]] == ["missing"] * 4
        assert m["complete"] is False
    print("ok  all-missing run is published as incomplete (exit 2), never green")


@case
def test_corrupt_sqlite_is_an_error_not_a_crash():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        (app / "stats.db").write_bytes(b"not a database" * 100)
        rc, _ = run(app, log, pathlib.Path(td) / "ev")
        assert rc == 1
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        e = next(x for x in m["entries"] if x["kind"] == "sqlite_backup")
        assert e["status"] == "error" and "SQLite" in e["note"], e
        assert m["outcome"] == "failed"
    print("ok  corrupt SQLite recorded as error, exit 1")


@case
def test_permission_failure_is_an_error():
    # The cloud container runs as root, so chmod 000 cannot deny a read;
    # the permission error is injected at the copy boundary instead.
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)

        def denied(src, dst):
            raise PermissionError(errno.EACCES, "Permission denied", str(src))
        rc, _ = run(app, log, pathlib.Path(td) / "ev", snapshot_bytes=denied)
        assert rc == 1
        m = manifest_of(published(pathlib.Path(td) / "ev")[0])
        errs = [e for e in m["entries"] if e["status"] == "error"]
        assert len(errs) == 2 and all("permission" in e["note"] for e in errs)
    print("ok  permission failure recorded as error, exit 1")


@case
def test_log_append_vs_rewrite_status():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        real = su._write_exclusive

        def appending(path, data):
            real(path, data)
            if path.name == "LocalFlow.log.full":
                with open(log, "ab") as f:
                    f.write(b"[localflow] appended\n")
        rc, _ = run(app, log, pathlib.Path(td) / "ev1",
                    _write_exclusive=appending)
        assert rc == 0, rc
        m = manifest_of(published(pathlib.Path(td) / "ev1")[0])
        e = next(x for x in m["entries"] if x["kind"] == "live_log_full")
        assert e["status"] == "appended_during_snapshot", e
        assert e["source_bytes_after"] > e["bytes"]

        def rewriting(path, data):
            real(path, data)
            if path.name == "LocalFlow.log.full":
                log.write_bytes(b"X" + data[1:])
        rc, _ = run(app, log, pathlib.Path(td) / "ev2",
                    _write_exclusive=rewriting)
        assert rc == 1, rc
        m = manifest_of(published(pathlib.Path(td) / "ev2")[0])
        e = next(x for x in m["entries"] if x["kind"] == "live_log_full")
        assert e["status"] == "changed_during_snapshot", e
        hp = next(x for x in m["entries"] if x["kind"] == "historical_prefix")
        assert hp["status"] == "not_present" and hp["snapshot"] is None
    print("ok  log append allowed and recorded; non-append change fails")


@case
def test_disk_full_leaves_only_an_unpublished_partial():
    with tempfile.TemporaryDirectory() as td:
        app, log = make_sources(td)
        real = su._write_exclusive

        def full(path, data):
            if path.name == su.MANIFEST_NAME:
                raise OSError(errno.ENOSPC, "No space left on device", str(path))
            real(path, data)
        root = pathlib.Path(td) / "ev"
        rc, err = run(app, log, root, _write_exclusive=full)
        assert rc == 1 and "not published" in err, (rc, err)
        assert published(root) == [], "partial run published"
        partials = [p for p in root.iterdir() if p.name.endswith(su.PARTIAL_SUFFIX)]
        assert len(partials) == 1 and not (partials[0] / su.MANIFEST_NAME).exists()
    print("ok  injected ENOSPC -> exit 1, no published run, partial kept private")


if __name__ == "__main__":
    for t in TESTS:
        t()
    print(f"all snapshot safety tests passed ({len(TESTS)})")
