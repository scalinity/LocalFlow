"""GATE-G06 batch A mandatory drivers (cross-milestone remediation).

One driver per DRIVER_REQUIRED case of batch A: XM-C001..C005 (Store
migration on older, damaged and interrupted stores), XM-C016/C018 and
XM-MU15 (managed-locator confinement across read, export and purge),
XM-C032/C033/C034/C040/MH17 (the real coordinator, insertion service,
History, usage, review, export and profile), XM-C193 (the M14 benchmark
validity gate).

Every driver crosses the real producer and consumer the case names and
grades it with an independent oracle: raw SQL on closed files and
backups, file digests and mtimes, an audit-hook recorder of opens and
unlinks, the M08 world's own read/effect log, what a scripted worker
actually produced. Fakes stand in only for the model worker and the OS
desktop (run_isolated.py). Orderings are decided by barriers — a writer
op, an exporter staging hook, a SQLite trace callback in a disposable
child — never by sleeps. Everything is synthetic.

A driver whose invariant the code violates FAILS; it is a reproduced
defect, reported, not worked around.

Run (AppKit headless, desktop isolated):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_g06_a.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import M, one, raw_rows, rows  # noqa: E402

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle",
          ROOT / "tests" / "v2" / "insertion",
          ROOT / "tests" / "v2" / "normalization",
          ROOT / "scripts" / "v2"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

import numpy as np  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from test_lifecycle import CFG, FakeSupervisor, Harness  # noqa: E402,F401
from m09_world import MainQueue  # noqa: E402,F401

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.analytics import AnalyticsStore  # noqa: E402
from localflow.v2.curation import evidence as ev  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402
from localflow.v2.history_queries import HistoryQueryService  # noqa: E402
from localflow.v2.profile import ProfileService  # noqa: E402
from localflow.v2.supervisor import WorkerFailure, WorkerSupervisor  # noqa: E402

CASES = []
TARGET = max(store_mod._MIGRATIONS)
REFUSED = (store_mod.PATH_REFUSED, store_mod.NONREGULAR_REFUSED)


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# =============================================================================
# shared oracles
# =============================================================================

def sha_file(path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dump(db, *, ro=True):
    """Every table's rows of a CLOSED store file (sorted), by plain SQL."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True) if ro \
        else sqlite3.connect(db)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " ORDER BY name")]
        return {t: sorted(con.execute(f"SELECT * FROM {t}").fetchall(),
                          key=repr) for t in names}
    finally:
        con.close()


def columns(db, table):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    finally:
        con.close()


def version_of(db):
    got = raw_rows(db, "SELECT value FROM schema_meta WHERE"
                   " key='schema_version'")
    return got[0][0] if got else None


def old_schema_store(path, version, **kw):
    """A genuinely older store: the real migrations up to ``version``
    (the approach of test_xm_store_families._old_schema_store)."""
    saved = store_mod._MIGRATIONS
    store_mod._MIGRATIONS = {k: v for k, v in saved.items() if k <= version}
    try:
        s = store_mod.Store(path, artifacts_dir=path.parent / "arts", **kw)
    finally:
        store_mod._MIGRATIONS = saved
    return s


def _seed_row(c, table, v, overrides=None):
    vals = {}
    for _cid, name, typ, _nn, _dflt, _pk in c.execute(
            f"PRAGMA table_info({table})"):
        t = (typ or "").upper()
        vals[name] = 7 if "INT" in t else 1.25 if "REAL" in t \
            else f"{table}.{name}.v{v}"
    vals.update(overrides or {})
    names = list(vals)
    c.execute(f"INSERT INTO {table}({','.join(names)}) VALUES"
              f"({','.join('?' * len(names))})", [vals[n] for n in names])


USAGE_SEEDS = (("fact-a", "job-usage-a", "2026-09-20T10:00:00Z", "UTC"),
               ("fact-b", "job-usage-b", "2026-09-21T11:30:00.5Z",
                "Europe/Paris"))
DELETED_EXAMPLE_JOB = ("job-del-example", "2026-09-01T00:00:00.000Z")
TOMBSTONED_ARTIFACT_JOB = ("job-del-artifact", "2026-09-03T00:00:00.000Z")


def seed_every_table(store, v):
    """One domain row in every table present at schema ``v`` plus the
    inputs of the v11/v12 data statements (deleted examples, an artifact
    tombstone, usage instants in the two short forms)."""
    def op(c):
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for t in names:
            if t == "schema_meta":
                continue
            if t == "usage_facts":
                for fid, job, at, tz in USAGE_SEEDS:
                    _seed_row(c, t, v, {"fact_id": fid, "kind": "dictation",
                                        "job_id": job,
                                        "activity_at_utc": at,
                                        "reporting_timezone": tz})
                continue
            _seed_row(c, t, v)
        job, first = DELETED_EXAMPLE_JOB
        _seed_row(c, "training_examples", v, {
            "example_id": "ex-del-1", "job_id": job, "state": "deleted",
            "updated_at_utc": first})
        _seed_row(c, "training_examples", v, {
            "example_id": "ex-del-2", "job_id": job, "state": "deleted",
            "updated_at_utc": "2026-09-02T00:00:00.000Z"})
        ajob, at = TOMBSTONED_ARTIFACT_JOB
        _seed_row(c, "artifacts", v, {"artifact_id": "art-tombstoned",
                                      "job_id": ajob, "content_path": None})
        _seed_row(c, "deletion_tombstones", v, {
            "tombstone_id": "tomb-art", "target_kind": "artifact",
            "target_id": "art-tombstoned", "created_at_utc": at})
    store.submit(op)


def canonical(instant):
    """The witness's own reading of a UTC instant, re-printed in the
    microsecond form; None when it is not an instant."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            t = dt.datetime.strptime(instant, fmt)
        except (TypeError, ValueError):
            continue
        return t, t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return None, instant


# =============================================================================
# audit-hook recorder (opens and unlinks reaching outside a managed root)
# =============================================================================

class Reach:
    """Records every open/remove/rename audit event while active and
    reports those whose target resolves inside ``outside`` (a no-follow
    open of a symlink resolves to the link itself, as the kernel
    does)."""

    _active = None
    _installed = False

    def __init__(self, outside, bases):
        self.outside = os.path.realpath(outside)
        self.bases = [os.path.realpath(b) for b in bases]
        self.events = []
        self.label = None

    @staticmethod
    def _hook(event, args):
        r = Reach._active
        if r is None or event not in ("open", "os.remove", "os.rename",
                                      "os.truncate", "os.utime",
                                      "os.chmod"):
            return
        path = args[0] if args else None
        flags = args[2] if event == "open" and len(args) > 2 else None
        r.events.append((r.label, event, path, flags))

    def __enter__(self):
        if not Reach._installed:
            sys.addaudithook(Reach._hook)
            Reach._installed = True
        Reach._active = self
        return self

    def __exit__(self, *exc):
        Reach._active = None

    def _inside(self, real):
        return real == self.outside or real.startswith(self.outside + os.sep)

    def hits(self):
        out = []
        for label, event, path, flags in list(self.events):
            if not isinstance(path, (str, bytes, os.PathLike)):
                continue
            p = os.fsdecode(path)
            fulls = [p] if os.path.isabs(p) else \
                [os.path.join(b, p) for b in self.bases]
            nofollow = event != "open" or (
                isinstance(flags, int) and flags & os.O_NOFOLLOW)
            for full in fulls:
                real = os.path.join(os.path.realpath(os.path.dirname(full)),
                                    os.path.basename(full)) if nofollow \
                    else os.path.realpath(full)
                if self._inside(real):
                    out.append((label, event, real))
                    break
        return out


def sentinel_state(path):
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    return (sha_file(path), st.st_mtime_ns, st.st_size)


# =============================================================================
# XM-C001 — genuinely older stores keep every seeded row and its meaning
# =============================================================================

@case("G06 XM-C001 (older store at each schema upgrades after an exact"
      " backup, rows and meanings kept)")
def g06_xm_c001_older_stores_keep_domain_rows():
    problems = []
    for v in range(1, TARGET):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "v2.db"
            s = old_schema_store(db, v)
            seed_every_table(s, v)
            s.close()
            before = dump(db)
            assert version_of(db) == str(v), f"fixture: v{v} stamp"
            assert len(before) > 1 and all(
                before[t] for t in before if t != "schema_meta"), \
                f"fixture: v{v} has an unseeded table"
            events = []
            s2 = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                                 backup_dir=db.parent / "bk",
                                 emit=lambda n, **k: events.append(n))
            s2.close()
            after = dump(db)
            backups = sorted((db.parent / "bk").glob("v2-pre-migrate*.db"))
            bad = []
            if version_of(db) != str(TARGET):
                bad.append(f"stamp {version_of(db)}")
            if {"store.schema_repaired", "store.schema_corrupt"} & \
                    set(events):
                bad.append(f"events {events}")
            if len(backups) != 1:
                bad.append(f"backups {backups}")
            elif dump(backups[0]) != before:
                bad.append("backup rows differ from the pre-upgrade rows")
            # The witness's own expectation of every table after upgrade.
            expect = {t: r for t, r in before.items() if t != "schema_meta"}
            if 9 <= v < 12:
                cols = columns(db, "usage_facts")
                i = cols.index("activity_at_utc")
                expect["usage_facts"] = sorted(
                    (r[:i] + (canonical(r[i])[1],) + r[i + 1:]
                     for r in before["usage_facts"]), key=repr)
            if v < 11:
                expect["job_deletions"] = sorted([
                    (DELETED_EXAMPLE_JOB[0], "pre_v11_deletion",
                     DELETED_EXAMPLE_JOB[1]),
                    (TOMBSTONED_ARTIFACT_JOB[0], "pre_v11_deletion",
                     TOMBSTONED_ARTIFACT_JOB[1])], key=repr)
            if v < 12:
                expect["usage_meta"] = [("reporting_timezone",
                                         USAGE_SEEDS[-1][3])] if v >= 9 \
                    else []
            for t in after:
                if t == "schema_meta":
                    continue
                want = expect.get(t, [])
                if after[t] != want:
                    bad.append(f"{t}: {after[t][:2]} != {want[:2]}")
            if v >= 9:
                cols = columns(db, "usage_facts")
                i, k = cols.index("activity_at_utc"), cols.index("fact_id")
                was = {r[k]: canonical(r[i])[0]
                       for r in before["usage_facts"]}
                now = {r[k]: canonical(r[i])[0]
                       for r in after["usage_facts"]}
                if was != now:
                    bad.append(f"usage instants moved: {was} -> {now}")
            if bad:
                problems.append((v, bad[:4]))
    assert not problems, f"older stores lost rows or meaning: {problems}"
    # Controls: a fresh store opens empty at the current schema; a
    # current store reopens with no backup taken.
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        s = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                            backup_dir=db.parent / "bk")
        assert one(s, "SELECT COUNT(*) FROM jobs")[0] == 0
        s.close()
        assert version_of(db) == str(TARGET)
        s = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                            backup_dir=db.parent / "bk")
        s.close()
        assert not list((db.parent / "bk").glob("*.db")), \
            "a current store reopened with a backup"


# =============================================================================
# XM-C002 — a failed pre-migration backup leaves the store untouched
# =============================================================================

def _file_hashes(db):
    return {suffix: sha_file(str(db) + suffix)
            for suffix in ("", "-wal", "-journal", "-shm")
            if os.path.exists(str(db) + suffix)}


@case("G06 XM-C002 (failed pre-migration backup: open refused, store"
      " byte-unchanged)")
def g06_xm_c002_failed_backup_refuses_untouched():
    for variant in ("backup_dir_is_a_file", "backup_dir_unwritable"):
        with tempfile.TemporaryDirectory() as td:
            db = pathlib.Path(td) / "v2.db"
            s = old_schema_store(db, 9)
            s.create_job()
            s.close()
            if variant == "backup_dir_is_a_file":
                bad = db.parent / "bk"
                bad.write_text("not a directory")
            else:
                bad = db.parent / "bk-ro"
                bad.mkdir()
                os.chmod(bad, 0o500)
            try:
                hashes = _file_hashes(db)
                raised = None
                try:
                    store_mod.Store(db, artifacts_dir=db.parent / "arts",
                                    backup_dir=bad).close()
                except Exception as e:  # noqa: BLE001
                    raised = type(e).__name__
                assert raised, f"{variant}: the open did not refuse"
                assert _file_hashes(db) == hashes, (
                    f"{variant}: the store changed under a refused open")
                assert version_of(db) == "9", (variant, version_of(db))
                later = {r[0] for r in raw_rows(
                    db, "SELECT name FROM sqlite_master WHERE"
                    " type='table'")} & {"learning_candidates",
                                         "job_deletions", "usage_meta",
                                         "m14_operation_receipts"}
                assert not later, f"{variant}: migrated tables {later}"
            finally:
                if bad.is_dir():
                    os.chmod(bad, 0o700)
    # Control: a writable backup dir upgrades with one pre-migrate copy.
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "v2.db"
        s = old_schema_store(db, 9)
        s.create_job()
        s.close()
        store_mod.Store(db, artifacts_dir=db.parent / "arts",
                        backup_dir=db.parent / "bk").close()
        assert version_of(db) == str(TARGET)
        assert len(list((db.parent / "bk").glob("v2-pre-migrate*.db"))) \
            == 1


# =============================================================================
# XM-C003 — every tracked entrypoint backs up before migrating
# =============================================================================

VALIDATOR_WRAPPER = r"""
import json, os, runpy, sys
events = []
def hook(ev, args):
    if ev == "sqlite3.connect":
        events.append(["sqlite3.connect", str(args[0]) if args else ""])
    elif ev == "open" and args and isinstance(args[0], (str, bytes)):
        p = os.fsdecode(args[0])
        if ".db" in os.path.basename(p):
            events.append(["open", p])
sys.addaudithook(hook)
out, script = sys.argv[1], sys.argv[2]
sys.argv = [script] + sys.argv[3:]
code = 0
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as e:
    code = e.code
with open(out, "w") as f:
    json.dump({"events": events, "code": code}, f)
"""


def _run(args, home):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, *map(str, args)], cwd=home,
                          env=env, capture_output=True, text=True,
                          timeout=300)


def _app_open(td, cfg_extra=None):
    """AppDelegate.configure over a store already at the app's V2_DB
    path (every live path redirected under ``td``)."""
    td = pathlib.Path(td)
    app_mod.V2_DB = td / "app" / "v2.db"
    app_mod.V2_ARTIFACTS = td / "app" / "artifacts"
    app_mod.V2_BACKUPS = td / "app" / "backups"
    app_mod.V2_EVENTS_DIR = td / "app" / "events"
    app_mod.V2_JOURNAL = td / "app" / "journal"
    app_mod.AUDIO_DEBUG_DIR = td / "app" / "dbg"
    d = app_mod.AppDelegate.alloc().init()
    d.configure(dict(CFG, **(cfg_extra or {})))
    d.store.sync()
    d.store.close()
    d.v2log.close()
    return app_mod.V2_DB, app_mod.V2_BACKUPS


def _pre_migrate(bk):
    return sorted(pathlib.Path(bk).glob("v2-pre-migrate*.db")) \
        if pathlib.Path(bk).exists() else []


@case("G06 XM-C003 (every store-opening entrypoint backs up before"
      " migrating; the validator opens no database)")
def g06_xm_c003_entrypoints_back_up_and_validator_opens_no_db():
    bad = []
    for version in (9, TARGET):
        older = version < TARGET
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            home = td / "home"
            home.mkdir()
            # export_dataset.py --db
            db = td / "exp" / "v2.db"
            db.parent.mkdir()
            old_schema_store(db, version).close()
            p = _run([ROOT / "scripts/v2/export_dataset.py", td / "exp-out",
                      "--db", db], home)
            bk = _pre_migrate(db.parent / "v2-evidence" / "backups")
            got = (version_of(db), [version_of(b) for b in bk])
            want = (str(TARGET), [str(version)] if older else [])
            if got != want:
                bad.append(("export_dataset.py", version, got, want,
                            p.stdout[-200:], p.stderr[-300:]))
            # import_legacy.py --store/--backup-dir (synthetic HOME)
            db = td / "imp" / "v2.db"
            db.parent.mkdir()
            old_schema_store(db, version).close()
            ibk = td / "imp" / "bk"
            p = _run([ROOT / "scripts/v2/import_legacy.py", "--store", db,
                      "--backup-dir", ibk, "--skip-log", "--output",
                      td / "imp" / "report.json"], home)
            bk = _pre_migrate(ibk)
            got = (version_of(db), [version_of(b) for b in bk])
            if got != want:
                bad.append(("import_legacy.py", version, got, want,
                            p.returncode, p.stderr[-300:]))
            # AppDelegate.configure
            app_db = td / "app" / "v2.db"
            app_db.parent.mkdir()
            old_schema_store(app_db, version).close()
            _db, abk = _app_open(td)
            bk = _pre_migrate(abk)
            got = (version_of(app_db), [version_of(b) for b in bk])
            if got != want:
                bad.append(("AppDelegate.configure", version, got, want))
    assert not bad, f"an entrypoint migrated without its backup: {bad}"
    # validate_dataset.py on a real export: no sqlite3.connect, no *.db.
    with M.MWorld() as w:
        w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        dest = w.tmp / "ds"
        w.export(dest, ("asr_supervised",))
        out = w.tmp / "audit.json"
        wrapper = w.tmp / "wrap.py"
        wrapper.write_text(VALIDATOR_WRAPPER)
        p = _run([wrapper, out, ROOT / "scripts/v2/validate_dataset.py",
                  dest], w.tmp)
        rec = json.loads(out.read_text())
        assert rec["code"] == 0, (
            f"fixture: the validator did not validate the export"
            f" ({p.stdout[-300:]})")
        assert not rec["events"], (
            f"the offline validator touched a database: {rec['events'][:4]}")


# =============================================================================
# XM-C004 — a migration killed between its DDL and its commit
# =============================================================================

KILL_CHILD = r"""
import os, pathlib, re, sqlite3, sys
sys.path.insert(0, sys.argv[1])
db, bk, arts, mode, marker = sys.argv[2:7]
real = sqlite3.connect
state = {}
def connect(*a, **k):
    con = real(*a, **k)
    if mode == "kill" and str(a[0]) == db:
        def trace(stmt):
            if state.get("first") and "schema_meta" not in stmt:
                pathlib.Path(marker).write_text(" ".join(stmt.split())[:120])
                os._exit(9)
            if state["first_ddl"] in stmt:
                state["first"] = True
        con.set_trace_callback(trace)
    return con
sqlite3.connect = connect
from localflow.v2 import store
last = max(store._MIGRATIONS)
state["first_ddl"] = store._MIGRATIONS[last][0].strip()[:60]
s = store.Store(db, artifacts_dir=arts, backup_dir=bk)
s.close()
"""


@case("G06 XM-C004 (a migration killed after DDL, before commit, reopens"
      " at the old version with no rows lost and upgrades cleanly)")
def g06_xm_c004_killed_migration_reopens_and_upgrades():
    base = TARGET - 1
    for mode in ("control", "kill"):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            db = td / "v2.db"
            s = old_schema_store(db, base)
            seed_every_table(s, base)
            s.close()
            d0 = dump(db)
            bk, marker = td / "bk", td / "marker.txt"
            p = subprocess.run(
                [sys.executable, "-c", KILL_CHILD, str(ROOT), str(db),
                 str(bk), str(td / "arts"), mode, str(marker)],
                capture_output=True, text=True, timeout=120)
            new_tables = set(dump(db, ro=False)) - set(d0) \
                if mode == "control" else None
            if mode == "control":
                assert p.returncode == 0, p.stderr[-400:]
                assert version_of(db) == str(TARGET)
                assert new_tables, "control: no table added"
                continue
            assert p.returncode == 9 and marker.exists(), (
                f"fixture: the child was not killed at the DDL barrier"
                f" (rc={p.returncode}, {p.stderr[-300:]})")
            killed_at = marker.read_text()
            second = store_mod._MIGRATIONS[TARGET][1].split("(")[0].split()[-1]
            assert second in killed_at, (
                f"fixture: killed at {killed_at!r}, not after the first"
                f" DDL of v{TARGET}")
            # What any reader sees: a copy with its hot journal, opened
            # read-write so SQLite rolls the torn transaction back.
            peek = td / "peek"
            peek.mkdir()
            for suffix in ("", "-journal", "-wal"):
                if os.path.exists(str(db) + suffix):
                    shutil.copy2(str(db) + suffix, str(peek / "v2.db") + suffix)
            seen = dump(peek / "v2.db", ro=False)
            assert seen == d0, (
                f"after the kill (at {killed_at!r}) the store no longer"
                f" equals its pre-kill rows: tables"
                f" +{sorted(set(seen) - set(d0))}"
                f" -{sorted(set(d0) - set(seen))}")
            assert version_of(peek / "v2.db") == str(base)
            pre = _pre_migrate(bk)
            assert pre and any(dump(b) == d0 for b in pre), \
                "no pre-migrate backup equal to the pre-kill rows"
            events = []
            s2 = store_mod.Store(db, artifacts_dir=td / "arts",
                                 backup_dir=bk,
                                 emit=lambda n, **k: events.append(n))
            s2.close()
            after = dump(db)
            assert version_of(db) == str(TARGET), version_of(db)
            assert "store.schema_repaired" not in events and \
                "store.schema_corrupt" not in events, events
            lost = {t: (len(d0[t]), len(after.get(t, [])))
                    for t in d0 if t != "schema_meta"
                    and after.get(t) != d0[t]}
            assert not lost, f"rows lost across the killed migration: {lost}"
            added = set(after) - set(d0)
            assert added and all(after[t] == [] for t in added), added


# =============================================================================
# XM-C005 — a lost core table is refused, never recreated empty
# =============================================================================

def _reopen_copy(src_dir, table, workdir):
    """Copy a closed store dir, drop ``table`` in the copy, reopen it."""
    cp = pathlib.Path(workdir) / f"copy-{table}"
    shutil.copytree(src_dir, cp)
    db = cp / "v2.db"
    X.drop_table(db, table)
    counts = {t: len(r) for t, r in dump(db).items()}
    events, refusal, store = [], None, None
    try:
        store = store_mod.Store(db, artifacts_dir=cp / "arts",
                                backup_dir=cp / "bk",
                                emit=lambda n, **k: events.append(n))
    except RuntimeError as e:
        refusal = str(e)
    return db, counts, store, refusal, events


def _built_store(td, *, artifacts):
    """A current store written through the real producers: a job, its
    History text/audio (collection off: no lease, no revision, no
    import), a usage fact, an insertion row and a target."""
    from localflow.v2.insertion import InsertionResult
    from localflow.v2.insertion.record import record_insertion
    src = pathlib.Path(td) / "src"
    s = store_mod.Store(src / "v2.db", artifacts_dir=src / "arts",
                        backup_dir=src / "bk")
    job, _fam = s.create_job()
    s.set_job_target(job, "Synthetic Editor", "com.synthetic.editor")
    if artifacts:
        s.write_text_artifact(job_id=job, stage="asr", role="raw_transcript",
                              text="history words kept", kind="text",
                              retention_class="history")
        aid = s.write_audio_artifact(job_id=job, stage="capture",
                                     samples=M.tone(330.0),
                                     sample_rate=M.RATE,
                                     retention_class="history")
        s.set_job_audio(job, aid)
    AnalyticsStore(s, reporting_timezone="UTC").record_dictation_fact(
        job_id=job, activity_at_utc="2026-09-27T10:00:00.000000Z",
        timezone="UTC", utc_offset_minutes=0, raw_words=3, final_words=3,
        insertion_outcome="confirmed", app_name="Synthetic Editor",
        app_bundle="com.synthetic.editor")
    record_insertion(s, InsertionResult(
        insertion_id="ins-g06-c005", job_id=job, state="confirmed",
        method="ax_replacement"))
    s.sync()
    s.close()
    return src, job


@case("G06 XM-C005 (a lost jobs/artifacts table with surviving referrers"
      " is refused with a backup, never recreated empty)")
def g06_xm_c005_lost_core_table_is_refused():
    outcomes = {}
    variants = (("artifacts", True, "History artifacts of a live job"),
                ("jobs", True, "artifacts of the lost jobs"),
                ("jobs", False, "only usage_facts/insertions/job_targets"))
    for table, artifacts, what in variants:
        with tempfile.TemporaryDirectory() as td:
            src, job = _built_store(td, artifacts=artifacts)
            src_rows = dump(src / "v2.db")
            referrers = {t: n for t, n in (
                ("jobs", len(src_rows["jobs"])),
                ("artifacts", len(src_rows["artifacts"])),
                ("usage_facts", len(src_rows["usage_facts"])),
                ("insertions", len(src_rows["insertions"])),
                ("job_targets", len(src_rows["job_targets"])))
                if t != table and n}
            assert src_rows[table] and referrers, f"fixture: {what}"
            db, counts, store, refusal, events = _reopen_copy(src, table, td)
            key = f"lost {table} ({what})"
            if store is not None:
                left = one(store, f"SELECT COUNT(*) FROM {table}")[0]
                store.close()
                outcomes[key] = (f"opened: {table} recreated with {left}"
                                 f" rows while {referrers} survive;"
                                 f" events={events}")
                continue
            bk = sorted((db.parent / "bk").glob("v2-pre-repair*.db"))
            if "corrupt" not in refusal or not bk:
                outcomes[key] = f"refused without backup: {refusal[:80]}"
            elif {t: len(r) for t, r in dump(bk[0]).items()} != counts:
                outcomes[key] = "pre-repair backup rows differ"
    assert not outcomes, f"core-table loss not refused: {outcomes}"


@case("G06 XM-C005 control", kind="control")
def g06_xm_c005_control_fresh_and_intact_stores_open():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "fresh" / "v2.db"
        s = store_mod.Store(db, artifacts_dir=db.parent / "arts",
                            backup_dir=db.parent / "bk")
        assert one(s, "SELECT COUNT(*) FROM jobs")[0] == 0
        s.close()
        src, _job = _built_store(td, artifacts=True)
        events = []
        s = store_mod.Store(src / "v2.db", artifacts_dir=src / "arts",
                            backup_dir=src / "bk",
                            emit=lambda n, **k: events.append(n))
        s.close()
        assert "store.schema_repaired" not in events and \
            "store.schema_corrupt" not in events, events


# =============================================================================
# XM-C016 — a corrupt artifact locator never reaches outside the root
# =============================================================================

class _Sound:
    def play(self):
        return True

    def stop(self):
        pass


def _outside_world(w, name="sentinel.wav"):
    outside = w.tmp / "outside"
    outside.mkdir(exist_ok=True)
    sentinel = outside / name
    store_mod.write_wav_f32(sentinel, M.tone(911.0), M.RATE)
    return outside, sentinel


def _variant_path(w, variant, sentinel, root):
    if variant == "absolute":
        return str(sentinel)
    if variant == "traversal":
        return os.path.relpath(sentinel, root)
    link = pathlib.Path(root) / "link-to-outside.wav"
    if not link.is_symlink():
        os.symlink(sentinel, link)
    return link.name


def _export_or_refusal(w, dest, views):
    try:
        return w.exporter.build(w.tmp / dest, task_views=views), None
    except export_mod.ExportError as e:
        return None, str(e)


@case("G06 XM-C016 (a corrupt locator is refused by every read, export and"
      " purge; nothing outside the managed root is touched)")
def g06_xm_c016_corrupt_locator_never_touches_outside():
    from localflow.v2.notes import NoteStore
    from localflow.v2.ui import ReplayService
    report = {}
    for variant in ("absolute", "traversal", "symlink"):
        with M.MWorld() as w:
            a = w.ready_asr()
            w.families(10, asr=True)
            w.splits.assign()
            arts = w.store.artifacts_dir
            outside, sentinel = _outside_world(w)
            locator = _variant_path(w, variant, sentinel, arts)
            digest = sha_file(sentinel)
            w.store.submit(lambda c: c.execute(
                "UPDATE artifacts SET content_path=?, sha256=? WHERE"
                " artifact_id=?", (locator, digest, a["audio_aid"])))
            notes = NoteStore(w.store)
            note = notes.create_note("g06 note")
            note_id = note if isinstance(note, str) else note["note_id"]
            att = notes.add_attachment(note_id, b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                                       "image/png", "g06.png")
            att_id = att if isinstance(att, str) else att["attachment_id"]
            nloc = _variant_path(w, variant, sentinel, notes.attachments_dir)
            w.store.submit(lambda c: c.execute(
                "UPDATE note_attachments SET content_path=? WHERE"
                " attachment_id=?", (nloc, att_id)))
            before = sentinel_state(sentinel)
            issues = []
            with Reach(outside, [arts, notes.attachments_dir]) as r:
                r.label = "read_managed_file"
                if store_mod.read_managed_file(arts, locator) is not None:
                    issues.append("read_managed_file returned bytes")
                r.label = "history_replay"
                ReplayService(sound_factory=lambda b: _Sound()) \
                    .play_artifact(w.store, a["audio_aid"])
                r.label = "note_attachment_payload"
                if notes.attachment_payload(att_id) is not None:
                    issues.append("attachment_payload returned bytes")
                r.label = "export"
                out, _err = _export_or_refusal(w, f"ds-{variant}",
                                               ("asr_supervised",))
                if out is not None:
                    for f in (w.tmp / f"ds-{variant}" / "artifacts").glob("*"):
                        if sha_file(f) == digest:
                            issues.append("export copied the outside file")
                r.label = "unlink_managed_file"
                code = store_mod.unlink_managed_file(arts, locator)
                if code not in REFUSED:
                    issues.append(f"unlink_managed_file -> {code}")
                r.label = "note_delete_attachment"
                notes.delete_attachment(att_id)
                w.store.sync()
                r.label = "delete_everywhere_artifact_purge"
                w.store.delete_everywhere("job", a["job_id"])
                w.store.sync()
            hits = r.hits()
            after = sentinel_state(sentinel)
            intent = one(w.store, "SELECT completed_at_utc, last_error FROM"
                         " purge_intents WHERE artifact_id=?",
                         (a["audio_aid"],))
            if after != before:
                issues.append("outside sentinel "
                              + ("deleted" if after is None else "modified"))
            if hits:
                issues.append(f"reached outside: {sorted(set(h[:2] for h in hits))}")
            if intent is None or intent[0] is None or intent[1] not in REFUSED:
                issues.append(f"artifact purge intent {intent}")
            if issues:
                report[variant] = issues
    assert not report, f"corrupt locators reached outside the root: {report}"


@case("G06 XM-C016 control", kind="control")
def g06_xm_c016_control_in_root_locator_reads_exports_purges():
    from localflow.v2.ui import ReplayService
    with M.MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        arts = w.store.artifacts_dir
        path = one(w.store, "SELECT content_path FROM artifacts WHERE"
                   " artifact_id=?", (a["audio_aid"],))[0]
        assert store_mod.read_managed_file(arts, path)
        got = ReplayService(sound_factory=lambda b: _Sound()).play_artifact(
            w.store, a["audio_aid"])
        assert got.get("available") is not False, got
        out, err = _export_or_refusal(w, "ds", ("asr_supervised",))
        assert out is not None and out["state"] == "complete", err
        w.store.delete_everywhere("job", a["job_id"])
        w.store.sync()
        assert not (arts / path).exists(), "in-root payload not purged"
        intent = one(w.store, "SELECT completed_at_utc, last_error FROM"
                     " purge_intents WHERE artifact_id=?", (a["audio_aid"],))
        assert intent and intent[0] and intent[1] is None, intent


# =============================================================================
# XM-C018 — FIFO / directory / socket locators refused without blocking
# =============================================================================

def _bounded(fn, seconds=3.0):
    box = {}

    def run():
        try:
            box["out"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["exc"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    return (not t.is_alive()), box


@case("G06 XM-C018 (a FIFO/directory/socket locator is refused by"
      " open_managed_file, qualify and export without blocking)")
def g06_xm_c018_nonregular_nodes_refused_without_blocking():
    problems = {}
    for kind in ("fifo", "directory", "socket"):
        with M.MWorld() as w:
            a = w.ready_asr()
            w.families(10, asr=True)
            w.splits.assign()
            arts = w.store.artifacts_dir
            name = f"{kind}-node.wav"
            node = arts / name
            sock = None
            if kind == "fifo":
                os.mkfifo(node)
            elif kind == "directory":
                node.mkdir()
            else:
                sock = socket.socket(socket.AF_UNIX)
                sock.bind(str(node))
            try:
                w.store.submit(lambda c: c.execute(
                    "UPDATE artifacts SET content_path=? WHERE"
                    " artifact_id=?", (name, a["audio_aid"])))
                issues = []
                done, box = _bounded(
                    lambda: store_mod.open_managed_file(arts, name))
                if not done:
                    issues.append("open_managed_file blocked")
                elif box.get("out") is not None:
                    box["out"].close()
                    issues.append("open_managed_file admitted it")
                if kind == "fifo":
                    try:
                        fd = os.open(node, os.O_WRONLY | os.O_NONBLOCK)
                        os.close(fd)
                        issues.append("a reader still holds the FIFO")
                    except OSError as e:
                        if e.errno != 6:  # ENXIO: no reader
                            issues.append(f"writer probe {e.errno}")
                done, box = _bounded(lambda: w.store.submit(
                    lambda c: ev.qualify(c, a["audio_aid"], "original_audio",
                                         job_id=a["job_id"],
                                         artifacts_dir=arts)))
                q = box.get("out") or {}
                if not done or q.get("ok") or not str(
                        q.get("reason")).endswith("_payload_absent"):
                    issues.append(f"qualify -> {q or box}")
                done, box = _bounded(lambda: _export_or_refusal(
                    w, f"ds-{kind}", ("asr_supervised",)), 30.0)
                if not done:
                    issues.append("export blocked")
                else:
                    out, _err = box.get("out") or (None, None)
                    if out is not None:
                        rows_ = M.read_jsonl(w.tmp / f"ds-{kind}"
                                             / "examples.jsonl")
                        if any(r["example_id"] == a["example_id"]
                               for r in rows_):
                            issues.append("export kept the example")
                if issues:
                    problems[kind] = issues
            finally:
                if sock is not None:
                    sock.close()
    assert not problems, f"non-regular nodes admitted: {problems}"
    # Control: the regular in-root WAV opens and exports.
    with M.MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        path = one(w.store, "SELECT content_path FROM artifacts WHERE"
                   " artifact_id=?", (a["audio_aid"],))[0]
        f = store_mod.open_managed_file(w.store.artifacts_dir, path)
        assert f is not None
        f.close()
        out, err = _export_or_refusal(w, "ds", ("asr_supervised",))
        assert out is not None, err
        assert any(r["example_id"] == a["example_id"] for r in
                   M.read_jsonl(w.tmp / "ds" / "examples.jsonl"))


# =============================================================================
# XM-MU15 — the export confines its own payload open
# =============================================================================

def _mu15_body(*, swap=True, mutant=False):
    """A qualified audio artifact; between qualification and the copy
    (the exporter's staging write) the in-root file becomes a symlink to
    an outside canary with the same bytes. ``mutant`` replaces ONLY the
    export consumer's admission with a plain open (qualify keeps its
    own guard)."""
    with M.MWorld() as w:
        a = w.ready_asr()
        w.families(10, asr=True)
        w.splits.assign()
        arts = w.store.artifacts_dir
        path = arts / one(w.store, "SELECT content_path FROM artifacts"
                          " WHERE artifact_id=?", (a["audio_aid"],))[0]
        outside = w.tmp / "outside"
        outside.mkdir()
        canary = outside / "canary.wav"
        shutil.copyfile(path, canary)
        digest = sha_file(canary)
        reached = []
        real_graph = w.exporter._write_graph

        def write_graph(*args, **kw):
            if swap:
                os.unlink(path)
                os.symlink(canary, path)
            reached.append(True)
            return real_graph(*args, **kw)
        w.exporter._write_graph = write_graph
        real_open = export_mod.open_managed_file
        if mutant:
            export_mod.open_managed_file = \
                lambda d, n: open(os.path.join(d, n), "rb")
        try:
            with Reach(outside, [arts]) as r:
                r.label = "export"
                out, err = _export_or_refusal(w, "ds", ("asr_supervised",))
        finally:
            export_mod.open_managed_file = real_open
            del w.exporter._write_graph
        assert reached, "fixture: the staging seam was never reached"
        if not swap:
            assert out is not None and out["state"] == "complete", err
            ok, text = _validate_offline(w.tmp / "ds")
            assert ok, text
            return
        copies = [f.name for f in (w.tmp / "ds" / "artifacts").glob("*")
                  if sha_file(f) == digest] if out is not None else []
        hits = r.hits()
        assert not hits, f"the export opened the outside canary: {hits[:3]}"
        assert not copies, f"the canary was exported as {copies}"
        assert out is None and err, "the export did not refuse the payload"


def _validate_offline(dest):
    p = subprocess.run([sys.executable,
                        str(ROOT / "scripts/v2/validate_dataset.py"),
                        str(dest)], capture_output=True, text=True,
                       timeout=120)
    return p.returncode == 0, p.stdout[-400:]


@case("G06 XM-MU15 (the export never reads an in-root file swapped for a"
      " symlink after qualification)")
def g06_xm_mu15_export_confines_its_own_open():
    _mu15_body()


@case("G06 XM-MU15 control (no swap: export completes and validates)",
      kind="control")
def g06_xm_mu15_control_no_swap_exports():
    _mu15_body(swap=False)


@case("G06 XM-MU15 mutant (copy_audio plain open) is killed",
      kind="control")
def g06_xm_mu15_mutant_is_killed():
    try:
        _mu15_body(mutant=True)
    except AssertionError as e:
        assert "canary" in str(e), f"killed for another reason: {e}"
        return
    raise AssertionError("the plain-open mutant of copy_audio survived")


# =============================================================================
# XM-C193 — the benchmark is INVALID for any no-op or wrong cohort
# =============================================================================

OWN_REASON = {"mining": "mining:", "note_mining": "note mining:",
              "profile": "profile:", "sampling": "sampling:",
              "splits": "splits:", "export": "export:"}


def _bench_validity(bench, mutate):
    sz = bench.sizes("small")
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = store_mod.Store(tmp / "v2.db", artifacts_dir=tmp / "art",
                            backup_dir=tmp / "backups")
        try:
            expect = bench.build(s, tmp, sz)
            comp, services = bench.components(s, tmp)
            mutate(comp, services, tmp)
            return bench.validate(s, tmp, expect, comp, services), expect
        finally:
            s.close()


@case("G06 XM-C193 (a no-op or wrong-cohort component makes the benchmark"
      " INVALID with its own reason)")
def g06_xm_c193_noop_and_wrong_cohort_are_invalid():
    import benchmark_m14 as bench
    good = bench.run_validity(scale="small")
    assert good["valid"], f"control: the real run is invalid {good['reasons']}"
    missed = {}
    for comp_name in bench.COMPONENTS:
        out = bench.run_validity(scale="small", noop=comp_name)
        if out["valid"] or not any(r.startswith(OWN_REASON[comp_name])
                                   for r in out["reasons"]):
            missed[f"noop:{comp_name}"] = out["reasons"]

    def export_asr_only(comp, services, tmp):
        comp["export"] = lambda: services["ex"].build(
            tmp / "dataset", task_views=("asr_supervised",))

    def profile_minus_one(comp, services, tmp):
        ps = services["ps"]
        real = ps._eligible

        def eligible(*a, **k):
            got = real(*a, **k)
            return (got[0][1:],) + tuple(got[1:])
        ps._eligible = eligible
    for label, mutate, reason in (
            ("wrong_cohort:export_asr_only", export_asr_only, "export:"),
            ("wrong_cohort:profile_minus_one", profile_minus_one,
             "profile:")):
        out, expect = _bench_validity(bench, mutate)
        assert expect["export_cleanup_rows"] > 0 and \
            expect["eligible_examples"] > 0, "fixture: empty cohort"
        if out["valid"] or not any(r.startswith(reason)
                                   for r in out["reasons"]):
            missed[label] = out["reasons"]
    assert not missed, f"benchmark accepted a substituted component: {missed}"


# =============================================================================
# the real coordinator with the real insertion service (M08 world)
# =============================================================================

def _app_env(**kw):
    from test_m08_remediation import AppEnv
    a = AppEnv(**kw)
    app_mod.AUDIO_DEBUG_DIR = a.h.tmp / "dbg"
    a.d.recorder.durations.extend([1.0] * 12)
    return a


class inline_after:
    def __enter__(self):
        self._real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda f, *a: f(*a)

    def __exit__(self, *exc):
        app_mod.AppHelper.callAfter = self._real


def _dictate(a, *, before_finish=None, snapshot=True):
    """press -> real coordinator -> _finishWithText_ (callbacks inline);
    ``before_finish(job)`` runs after the coordinator finished and
    before the text is handed to insertion. Returns (text, job)."""
    from test_m08_remediation import snap
    from m08_world import wait_for
    a.h.press_release()
    _fn, args = a.h.run_coordinator()
    text, job = args
    if snapshot:
        s = snap(a.w)
        job["context_snapshot"] = s
        job["target"] = s.target
    if before_finish is not None:
        before_finish(job)
    with inline_after():
        a.d._finishWithText_(text, job)
        assert wait_for(lambda: job not in a.d._active_jobs, 10), \
            "insertion never settled the job"
    a.d.store.sync()
    return text, job


def _svc_idle(a, timeout=10.0):
    from m08_world import wait_for
    assert wait_for(lambda: not a.svc.pending, timeout), "service busy"
    a.d.store.sync()


def _fact(store, job_id):
    got = rows(store, "SELECT insertion_outcome, final_words, raw_words,"
               " app_name, app_bundle, attempt FROM usage_facts WHERE"
               " kind='dictation' AND job_id=?", (job_id,))
    return got[0] if got else None


def _example(store, job_id):
    got = rows(store, "SELECT example_id, family_id FROM training_examples"
               " WHERE job_id=? ORDER BY rowid", (job_id,))
    return got


def _latest_env(store, example_id):
    row = one(store, "SELECT r.envelope_json FROM training_examples e JOIN"
              " training_revisions r ON r.revision_id=e.latest_revision_id"
              " WHERE e.example_id=?", (example_id,))
    return json.loads(row[0]) if row else None


# =============================================================================
# XM-C032 — worker death at ASR: recoverable, original audio, no transcript
# =============================================================================

FAKE_WORKER = ROOT / "tests" / "v2" / "lifecycle" / "fake_worker.py"


def _real_supervisor(td, plan):
    plan_path = pathlib.Path(td) / f"plan-{time.monotonic_ns()}.json"
    plan_path.write_text(json.dumps(plan))
    return WorkerSupervisor(
        audio_root=app_mod.V2_JOURNAL, asr_model="fake-asr",
        cleanup_mode="llm", cleanup_model="fake-llm",
        worker_cmd=[sys.executable, str(FAKE_WORKER)],
        spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan_path),
                   "PYTHONPATH": str(ROOT)},
        hello_timeout=15.0, ready_timeout=15.0, request_timeout=15.0)


def _witness_capture(h):
    samples = (0.1 * np.sin(np.arange(16000, dtype=np.float64) / 7.3)
               ).astype("<f4")
    orig = h.d.recorder.stop

    def stop():
        orig()
        return samples.copy()
    h.d.recorder.stop = stop
    return samples


def _capture_through(plan):
    h = Harness(durations=[1.0])
    app_mod.AUDIO_DEBUG_DIR = h.tmp / "dbg"
    h.d.consent.set("enabled")
    sup = _real_supervisor(h.tmp, plan)
    h.d.supervisor = sup
    samples = _witness_capture(h)
    h.press()
    h.release()
    fn, args = h.run_coordinator(timeout=60.0)
    text, job = args
    fn(*args)
    h.d.store.sync()
    return h, sup, samples, text, job


@case("G06 XM-C032 (worker death at ASR keeps a recoverable job with the"
      " original audio and no fabricated transcript)")
def g06_xm_c032_worker_death_keeps_audio_never_a_transcript():
    h, sup, samples, text, job = _capture_through(
        {"asr": "ready", "cleanup": "ready",
         "transcribe": ["crash", "crash", "crash"]})
    try:
        jid = job["job_id"]
        assert sup.generation >= 1, "fixture: the real worker never spawned"
        store = h.d.store
        state, reason = one(store, "SELECT state, state_reason FROM jobs"
                            " WHERE job_id=?", (jid,))
        assert state == "failed_recoverable" and reason, (state, reason)
        assert text == "" and h.pastes == [], (text, h.pastes)
        wav = pathlib.Path((h.d._last_failed or {}).get("wav") or "")
        assert wav.is_file(), "no recovery audio kept"
        got, _rate = store_mod.read_wav_f32(wav)
        assert got.size == samples.size and hashlib.sha256(
            np.asarray(got, "<f4").tobytes()).hexdigest() == \
            hashlib.sha256(samples.tobytes()).hexdigest(), (
            f"recovery audio differs from the capture ({got.size} vs"
            f" {samples.size} samples)")
        n = one(store, "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                " role LIKE 'raw_transcript%'", (jid,))[0]
        assert n == 0, f"{n} transcript artifacts for a failed ASR"
        detail = HistoryQueryService(store).job_detail(jid)
        src = next(s for s in detail["lineage"] if s["stage"] == "source")
        assert src["artifact"] is None, "History shows a source text"
        assert detail["insertion"] is None, detail["insertion"]
    finally:
        sup.shutdown()
        h.close()
    # Control: the same audio through a worker that answers.
    h, sup, samples, text, job = _capture_through(
        {"asr": "ready", "cleanup": "ready",
         "transcribe": ["ok:control words here"],
         "clean": ["ok:Control words here."]})
    try:
        assert text and h.pastes == [text + " "], (text, h.pastes)
        n = one(h.d.store, "SELECT COUNT(*) FROM artifacts WHERE job_id=?"
                " AND role LIKE 'raw_transcript%'", (job["job_id"],))[0]
        assert n == 1, f"control: {n} transcript artifacts"
    finally:
        sup.shutdown()
        h.close()


# =============================================================================
# XM-C033 — posted but unobservable stays posted_unverified everywhere
# =============================================================================

def _no_gold(store, example_id):
    env = _latest_env(store, example_id)
    q = store.submit(lambda c: ev.cleanup_qualification_in(c, example_id,
                                                            env))
    return env, q


@case("G06 XM-C033 (posted_unverified stays unverified in History, usage and"
      " review eligibility; no confirmation or label is minted)")
def g06_xm_c033_unverified_is_never_confirmed():
    for readable, want in ((False, "posted_unverified"),
                           (True, "confirmed")):
        a = _app_env(consent=True, window=0.3)
        try:
            f1 = a.w.fields["F1"]
            if not readable:
                f1.readable = False
                f1.settable = f1.range_settable = False
            text, job = _dictate(a)
            _svc_idle(a)
            store, jid = a.d.store, job["job_id"]
            raw = one(store, "SELECT state FROM insertions WHERE job_id=?"
                      " ORDER BY rowid DESC", (jid,))
            detail = HistoryQueryService(store).job_detail(jid)
            fact = _fact(store, jid)
            got = (raw and raw[0], (detail.get("insertion") or {}).get(
                "state"), fact and fact[0])
            assert got == (want, want, want), (
                f"{'control' if readable else 'no readback'}: raw/History/"
                f"usage outcomes {got}, expected {want}")
            exs = _example(store, jid)
            assert len(exs) == 1, f"fixture: examples {exs}"
            env, q = _no_gold(store, exs[0][0])
            outcome = env.get("outcome") or {}
            assert outcome.get("correctness") == "unreviewed", outcome
            assert not q.get("eligible") and q.get("reason") == \
                "no_intended_writing_mark", q
            labels = one(store, "SELECT (SELECT COUNT(*) FROM"
                         " correction_labels) + (SELECT COUNT(*) FROM"
                         " preference_observations)")[0]
            assert labels == 0, f"{labels} label/preference rows minted"
        finally:
            a.close()


# =============================================================================
# XM-C034 — refused revalidation stays saved_not_inserted with its words
# =============================================================================

class _FailingASR:
    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def transcribe(self, **kw):
        raise WorkerFailure("g06_scripted_asr_fault", stage="transcribe")


@case("G06 XM-C034 (refused revalidation stays saved_not_inserted with its"
      " text and words, distinct from a failed pipeline)")
def g06_xm_c034_refused_target_is_saved_not_failed():
    a = _app_env(consent=True, window=0.3)
    try:
        store = a.d.store
        mark = {}

        def switch(_job):
            mark["seq"] = a.w.seq
            a.w.focus("B")
        text, job = _dictate(a, before_finish=switch)
        _svc_idle(a)
        jid = job["job_id"]
        writes = [e for e in a.w.effects if e[0] > mark["seq"] and e[1] in (
            "ax_set_text", "ax_set_range", "paste_consumed", "ax_set_noop")]
        assert not writes, f"the refused insert wrote: {writes}"
        fact = _fact(store, jid)
        assert fact is not None, "no usage fact for the saved job"
        assert fact[0] == "saved_not_inserted" and \
            fact[1] == len(text.split()), (
            f"saved job: outcome/final_words {fact[:2]}, expected"
            f" saved_not_inserted/{len(text.split())}")
        detail = HistoryQueryService(store).job_detail(jid)
        cleaned = next(s for s in detail["lineage"]
                       if s["stage"] == "cleaned")["artifact"] or {}
        assert detail["state"] == "saved_not_inserted" and \
            cleaned.get("text") == text, (detail["state"],
                                          cleaned.get("text"), text)
        # A separate job whose ASR fails: failed, final_words unknown.
        a.w.focus("A")
        a.d.supervisor = _FailingASR(a.d.supervisor)
        _t, fjob = _dictate(a)
        ffact = _fact(store, fjob["job_id"])
        assert ffact is not None and ffact[0] == "failed" and \
            ffact[1] is None, f"failed job fact {ffact}"
        # Control: an unchanged target confirms and records its words.
        a.d.supervisor = a.d.supervisor.inner
        ctext, cjob = _dictate(a)
        _svc_idle(a)
        cfact = _fact(store, cjob["job_id"])
        assert cfact and cfact[0] == "confirmed" and \
            cfact[1] == len(ctext.split()), cfact
    finally:
        a.close()


# =============================================================================
# XM-C040 — metadata never grants insertion authority after revocation
# =============================================================================

def _field_touches(w, since, fids=("F1",)):
    reads = [r for r in w.reads if r[2] in fids and r[0] > since]
    writes = [e for e in w.effects if e[2] in fids and e[0] > since
              and e[1] in ("ax_set_text", "ax_set_range", "paste_consumed",
                           "ax_set_noop")]
    return reads, writes


def _repastes(store):
    return one(store, "SELECT COUNT(*) FROM usage_facts WHERE kind !="
               " 'dictation'")[0]


@case("G06 XM-C040 (after the lease is revoked, History and menu Paste"
      " Again make no read or write on the recorded target)")
def g06_xm_c040_revoked_lease_grants_no_authority():
    a = _app_env(consent=True, window=0.3)
    try:
        store = a.d.store
        text, job = _dictate(a)
        _svc_idle(a)
        jid = job["job_id"]
        assert a.w.text("F1") == text, "fixture: dictation not confirmed"
        # Control: before revocation History's Paste Again runs one
        # validated transaction into the cleared field.
        a.w.fields["F1"].text, a.w.fields["F1"].sel = "", (0, 0)
        reps0 = _repastes(store)
        from m08_world import pick_destination
        click = pick_destination(a.d)
        with inline_after():
            out = a.d.hubPasteText(text, job_id=jid)
            click()              # POLICY-D03: the user picks F1
        _svc_idle(a)
        assert out.get("outcome") == "choosing_destination" and \
            a.w.text("F1") == text and _repastes(store) == reps0 + 1, (
            f"control: {out} F1={a.w.text('F1')!r}")
        a.w.fields["F1"].text, a.w.fields["F1"].sel = "", (0, 0)
        fact_before = _fact(store, jid)
        target_before = rows(store, "SELECT app_name, app_bundle FROM"
                             " job_targets WHERE job_id=?", (jid,))
        reps1 = _repastes(store)
        store.delete_everywhere("job", jid)
        mark = a.w.seq
        with inline_after():
            out_hub = a.d.hubPasteText(text, job_id=jid)
            a.d.pasteLastResultAgain_(None)
        _svc_idle(a)
        reads, writes = _field_touches(a.w, mark)
        assert not reads and not writes, (
            f"after revocation: reads {reads[:3]} writes {writes[:3]}")
        assert out_hub.get("outcome") in ("job_deleted", "no_authority"), \
            out_hub
        assert _repastes(store) == reps1, "a repaste fact after revocation"
        assert _fact(store, jid) == fact_before, (
            f"usage app label changed: {fact_before} -> {_fact(store, jid)}")
        assert rows(store, "SELECT app_name, app_bundle FROM job_targets"
                    " WHERE job_id=?", (jid,)) == target_before
    finally:
        a.close()
    # Session lock: the recorded target is not an authority either —
    # after lock/unlock into app B, Paste Again acts on B's focus only.
    a = _app_env(consent=True, window=0.3)
    try:
        text, job = _dictate(a)
        _svc_idle(a)
        a.svc.note_session_locked()
        a.w.focus("B")
        a.svc.note_session_unlocked()
        mark = a.w.seq
        from m08_world import pick_destination
        click = pick_destination(a.d)
        with inline_after():
            a.d.hubPasteText(text, job_id=job["job_id"])
            click()              # the user picks B's field
            a.d.pasteLastResultAgain_(None)
        _svc_idle(a)
        reads, writes = _field_touches(a.w, mark)
        assert not reads and not writes, (
            f"after lock into B, the recorded F1 was touched: {reads[:3]}"
            f" {writes[:3]}")
        assert text in a.w.text("FB"), "fixture: no repaste reached B"
    finally:
        a.close()


# =============================================================================
# XM-MH17 — one clean dictation keeps one identity end to end
# =============================================================================

MH17_UTTERANCES = tuple(
    f"orion ledger {w} capture number {i} spoken plainly"
    for i, w in enumerate(("alpha", "bravo", "charlie", "delta", "echo",
                           "foxtrot", "golf", "hotel", "india", "juliet")))


def _sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest() if t is not None \
        else None


@case("G06 XM-MH17 (one clean dictation keeps one family and exact stage"
      " identities through History, usage, review, export and profile)")
def g06_xm_mh17_one_dictation_one_identity_everywhere():
    import test_normalization_pipeline as tnp
    from localflow.v2.curation.splits import SplitService
    from localflow.v2.training_data import TrainingDataService
    a = _app_env(consent=True, window=0.2)
    try:
        store = a.d.store
        ledger = []
        # Ten captures: the split floor (MIN_FAMILIES) must be reached
        # for any family to be exported; each one is its own ledger.
        for words in MH17_UTTERANCES:
            sup = tnp.RecordingSupervisor(
                words, cleaner=lambda t: t.capitalize() + ".")
            a.d.supervisor = sup
            text, job = _dictate(a)
            _svc_idle(a)
            normalized = sup.clean_inputs[-1]
            cleaned = normalized.capitalize() + "."
            assert text == cleaned, f"fixture: delivered {text!r}"
            ledger.append({"job": job["job_id"],
                           "family": job.get("family_id"),
                           "attempt": int(job.get("attempt", 1)),
                           "raw": _sha(words), "norm": _sha(normalized),
                           "clean": _sha(cleaned), "raw_text": words,
                           "raw_words": len(words.split()),
                           "final_words": len(cleaned.split())})
        for key in ("job", "family", "raw", "clean"):
            assert len({L[key] for L in ledger}) == len(ledger), \
                f"control: separate dictations share a {key}"
        td = TrainingDataService(store)
        for L in ledger:
            jid = L["job"]
            fam = one(store, "SELECT family_id FROM jobs WHERE job_id=?",
                      (jid,))[0]
            assert fam == L["family"], (fam, L["family"])
            detail = HistoryQueryService(store).job_detail(jid)
            stages = {s["stage"]: (s.get("artifact") or {})
                      for s in detail["lineage"]}
            assert _sha(stages["source"].get("text")) == L["raw"] and \
                _sha(stages["cleaned"].get("text")) == L["clean"], stages
            if stages["normalized"]:
                assert _sha(stages["normalized"].get("text")) == L["norm"]
            assert detail["lineage_attempt"] in (None, L["attempt"]), detail
            assert (detail.get("insertion") or {}).get("state") == \
                "confirmed", detail.get("insertion")
            fact = _fact(store, jid)
            assert fact and fact[0] == "confirmed" and \
                fact[1] == L["final_words"] and \
                fact[2] == L["raw_words"] and fact[5] == L["attempt"], fact
            exs = _example(store, jid)
            assert len(exs) == 1 and exs[0][1] == L["family"], exs
            L["example"] = ex = exs[0][0]
            env, q = _no_gold(store, ex)
            assert env["job_id"] == jid and env["family_id"] == L["family"] \
                and int(env["attempt"]) == L["attempt"], env
            assert env["outcome"].get("insertion") == "confirmed" and \
                env["outcome"].get("correctness") == "unreviewed", \
                env["outcome"]
            assert not q.get("eligible"), f"confirmation minted gold: {q}"
            owners = {r[0] for r in rows(
                store, "SELECT job_id FROM artifacts WHERE artifact_id IN"
                f" ({','.join('?' * len(env['artifact_ids']))})",
                tuple(env["artifact_ids"].values()))}
            assert owners == {jid}, f"envelope cites {owners}"
            texts = {r[0]: r[1] for r in rows(
                store, "SELECT artifact_id, content_text FROM artifacts"
                " WHERE job_id=?", (jid,))}
            assert _sha(texts.get(env["artifact_ids"]["source_text"])) == \
                L["raw"], "envelope source text is not the ASR output"
            assert _sha(texts.get(env["artifact_ids"]["applied_output"])) \
                == L["clean"], "envelope applied text is not the cleaned"
            td.set_verbatim(ex, L["raw_text"], listened_audio=True)
        SplitService(store).assign()
        dest = a.h.tmp / "mh17-export"
        export_mod.DatasetExporter(store).build(
            dest, task_views=("asr_supervised",))
        exported = M.read_jsonl(dest / "examples.jsonl")
        refs = {r["example_id"]: r for r in
                M.read_jsonl(dest / "references.jsonl")}
        by_ex = {r["example_id"]: r for r in exported}
        excluded = json.loads((dest / "dataset_manifest.json").read_text()
                              ).get("excluded")
        for L in ledger:
            r = by_ex.get(L["example"])
            assert r is not None, (
                f"a ledger example was not exported: excluded={excluded}"
                f" exported={len(exported)} state="
                f"{rows(store, 'SELECT state FROM training_examples WHERE example_id=?', (L['example'],))}"
                f" arts={sorted(_latest_env(store, L['example'])['artifact_ids'])}"
                f" members={rows(store, 'SELECT partition FROM training_memberships WHERE example_id=?', (L['example'],))}")
            lin = r["lineage"]
            assert lin["job_id"] == L["job"] and \
                r["family_id"] == L["family"], lin
            owners = {x[0] for x in rows(
                store, "SELECT job_id FROM artifacts WHERE artifact_id IN"
                f" ({','.join('?' * len(lin['inputs']))})",
                tuple(i.get("artifact_id") or i.get("id")
                      for i in lin["inputs"]))} if lin["inputs"] else set()
            assert owners <= {L["job"]}, f"export lineage cites {owners}"
            audio_sha = one(store, "SELECT sha256 FROM artifacts WHERE"
                            " job_id=? AND role='original_audio'",
                            (L["job"],))[0]
            assert r["audio_sha256"] == audio_sha, "exported audio differs"
            assert refs[L["example"]]["text_sha256"] == L["raw"], \
                "exported reference is not the ledger's raw text"
        snap = ProfileService(store).compute()
        ev_rows = rows(store, "SELECT DISTINCT e.example_id, t.job_id FROM"
                       " profile_evidence e JOIN training_examples t ON"
                       " t.example_id=e.example_id WHERE e.snapshot_id=?",
                       (snap.get("snapshot_id"),))
        want = {(L["example"], L["job"]) for L in ledger}
        assert set(ev_rows) <= want, f"profile evidence strays: {ev_rows}"
        assert snap["measured"]["eligible_examples"] == len(ledger), \
            snap["measured"]
    finally:
        a.close()


# =============================================================================
# runner (the shape of test_xm_remediation.py)
# =============================================================================

def redact(text):
    import re
    if not text:
        return text
    tmp = tempfile.gettempdir()
    for real, mark in ((str(ROOT), "<repo>"),
                       ("/private" + tmp, "<tmp>"), (tmp, "<tmp>"),
                       (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


def main(argv):
    out_path = None
    if "--json" in argv:
        i = argv.index("--json")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = set(argv)
    results = []
    for fn in CASES:
        if names and fn.__name__ not in names:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", (str(e) or "assertion")[:600]
        except Exception as e:  # noqa: BLE001
            status = "ERROR"
            tb = traceback.format_exc()
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + tb[-1200:])
        detail = redact(detail)
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("xm g06 batch A:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_g06_a.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_g06_a.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
