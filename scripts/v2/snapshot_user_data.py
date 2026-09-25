"""M01: non-destructive snapshots of live LocalFlow user data.

Copies the live stats.db (via the SQLite backup API, so journal/WAL state is
consistent), dictionary.json, transforms.json and the text log into a private
evidence root OUTSIDE the Git repository. Nothing here writes to, truncates or
otherwise modifies a live file; every source is fingerprinted before and after
to prove the originals did not change underneath the snapshot.

Run allocation and publication (M01 remediation, M01-AUDIT-06/12):

- Every run gets a unique id (UTC microsecond stamp + random suffix) and is
  written into an exclusively created, owner-only staging directory
  ``.<run-id>.partial``. Files are created with O_EXCL|O_NOFOLLOW at mode
  0600, so no pre-existing file or symlink is ever followed or overwritten.
- The run is published by one rename to ``<run-id>/`` only after every file
  and the manifest are written. A crash, permission failure or full disk
  leaves an unpublished ``.partial`` directory and a nonzero exit — never a
  directory that looks like a finished run.
- The evidence root must be outside the repository, must not itself be a
  symlink, must be owned by the current user and must not be writable by
  group/other. A newly created root is 0700.
- SQLite change detection covers the main file AND its ``-wal``/``-journal``
  companions (a WAL-mode write leaves the main file untouched); ``-shm`` is
  inventoried but not hashed (readers legitimately modify it).
- The live log is read once; afterwards the file is checked to still begin
  with exactly those bytes. Growth is recorded as an append (the running app
  appends), anything else as a change.
- All four expected sources are inventoried explicitly; a missing required
  source is recorded as ``missing`` and makes the run ``incomplete``
  (exit 2), an unreadable/corrupt one is ``error`` (exit 1).

Usage:
    .venv/bin/python scripts/v2/snapshot_user_data.py [--root PATH]

Exit codes: 0 complete, 1 failed (source changed, unreadable, or the run
could not be written/published), 2 incomplete (a required source missing).
"""

import argparse
import datetime as dt
import errno
import hashlib
import json
import os
import pathlib
import secrets
import sqlite3
import stat
import subprocess
import sys

APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
LOG_PATH = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow.log"
DEFAULT_ROOT = APP_SUPPORT / "v2-evidence"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

SCHEMA_VERSION = 2
MANIFEST_NAME = "snapshot-manifest.json"
PARTIAL_SUFFIX = ".partial"

# Historical artifact identities from the v1.0 audit (Evaluation E02). Used
# only to label the byte-prefix of the live log; the live log is expected to
# be longer because dictation continued after the audit.
HISTORICAL_LOG_SHA256 = "51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0"
HISTORICAL_LOG_BYTES = 544221

SQLITE_COMPANIONS_HASHED = ("-wal", "-journal")
SQLITE_COMPANIONS_INVENTORIED = ("-shm",)


class EvidenceRootError(Exception):
    """The evidence root is unsafe to write private evidence into."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def new_run_id(now=None) -> str:
    """Unique, chronologically sortable run id (never second-granular)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + secrets.token_hex(4)


# ---- private, exclusive file creation ---------------------------------------

def _write_exclusive(path: pathlib.Path, data: bytes) -> None:
    """Create ``path`` (never existing before, never through a symlink) at
    mode 0600 regardless of umask, write ``data`` fully and fsync."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir_private(path: pathlib.Path) -> None:
    """Exclusive owner-only directory (fails if anything exists there)."""
    os.mkdir(path, 0o700)
    os.chmod(path, 0o700, follow_symlinks=False)
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):  # pragma: no cover - raced replacement
        raise EvidenceRootError(f"{path} is not the directory just created")


def _fsync_dir(path: pathlib.Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def snapshot_bytes(src: pathlib.Path, dst: pathlib.Path) -> str:
    """Byte copy into a NEW private file; returns the sha256 of the bytes
    read (the single read that the copy was made from)."""
    data = src.read_bytes()
    if not dst.parent.exists():
        dst.parent.mkdir(parents=True, mode=0o700)
    _write_exclusive(dst, data)
    return sha256_bytes(data)


def snapshot_sqlite(src: pathlib.Path, dst: pathlib.Path) -> str:
    """Consistent snapshot via the SQLite backup API on a read-only source,
    into a NEW private file (pre-created exclusively at 0600)."""
    if not dst.parent.exists():
        dst.parent.mkdir(parents=True, mode=0o700)
    _write_exclusive(dst, b"")  # empty file == empty database for SQLite
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        backup = sqlite3.connect(dst)
        try:
            con.backup(backup)
        finally:
            backup.close()
    finally:
        con.close()
    os.chmod(dst, 0o600)
    return sha256_file(dst)


# ---- source fingerprints ------------------------------------------------------

def _file_identity(p: pathlib.Path):
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return None
    return {"bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "inode": st.st_ino,
            "is_symlink": stat.S_ISLNK(st.st_mode)}


def sqlite_fingerprint(src: pathlib.Path) -> dict:
    """Hash of the main database file plus every companion that can hold
    committed-but-uncheckpointed content. An absent and a zero-length
    companion both hold no content (None): SQLite's read-only open of a
    WAL-mode database with no other connection creates an empty -wal."""
    fp = {"main": sha256_file(src)}
    for suffix in SQLITE_COMPANIONS_HASHED:
        comp = pathlib.Path(str(src) + suffix)
        fp[suffix] = sha256_file(comp) if comp.is_file() \
            and comp.stat().st_size > 0 else None
    return fp


def _companions_present(src: pathlib.Path) -> set:
    return {suffix for suffix in SQLITE_COMPANIONS_HASHED
            + SQLITE_COMPANIONS_INVENTORIED
            if pathlib.Path(str(src) + suffix).exists()}


def sqlite_companion_inventory(src: pathlib.Path) -> dict:
    inv = {}
    for suffix in SQLITE_COMPANIONS_HASHED + SQLITE_COMPANIONS_INVENTORIED:
        comp = pathlib.Path(str(src) + suffix)
        ident = _file_identity(comp)
        inv[suffix] = {"exists": ident is not None,
                       "bytes": ident["bytes"] if ident else None,
                       "hashed_for_change_detection":
                           suffix in SQLITE_COMPANIONS_HASHED}
    return inv


# ---- evidence root ------------------------------------------------------------

def prepare_root(root: pathlib.Path, repo_root: pathlib.Path = REPO_ROOT) -> dict:
    """Validate (or create) the evidence root. Raises EvidenceRootError."""
    resolved = root.resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        raise EvidenceRootError(
            f"--root must live outside the repository (got {resolved} "
            f"inside {repo_root})")
    created = False
    try:
        st = os.lstat(root)
    except FileNotFoundError:
        root.parent.mkdir(parents=True, exist_ok=True)
        _mkdir_private(root)
        created = True
        st = os.lstat(root)
    if stat.S_ISLNK(st.st_mode):
        raise EvidenceRootError(f"evidence root {root} is a symlink; pass the "
                                "real directory")
    if not stat.S_ISDIR(st.st_mode):
        raise EvidenceRootError(f"evidence root {root} is not a directory")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise EvidenceRootError(f"evidence root {root} is owned by uid "
                                f"{st.st_uid}, not the current user")
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o022:
        raise EvidenceRootError(f"evidence root {root} is group/other-writable "
                                f"(mode {oct(mode)}); fix with chmod 700")
    return {"path": str(root), "created_by_this_run": created,
            "mode": oct(mode),
            "readable_by_others": bool(mode & 0o055),
            "note": None if not mode & 0o055 else
                "root is readable by group/other; the run directory itself "
                "is 0700 — consider chmod 700 on the root"}


def _tool_revision():
    try:
        r = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return {"commit": None, "reason": f"git unavailable: {type(e).__name__}"}
    if r.returncode != 0:
        return {"commit": None, "reason": f"git rev-parse failed: "
                                          f"{r.stderr.strip()[:160]}"}
    return {"commit": r.stdout.strip(), "reason": None}


# ---- capture ------------------------------------------------------------------

def _capture_sqlite(src, staging, final, name):
    entry = {"kind": "sqlite_backup", "source": str(src), "required": True,
             "snapshot": None, "sha256": None, "bytes": None}
    if not src.exists():
        entry.update(status="missing", note="required source absent")
        return entry
    entry["source_identity"] = _file_identity(src)
    entry["companions"] = sqlite_companion_inventory(src)
    present_before = _companions_present(src)
    try:
        before = sqlite_fingerprint(src)
        sha = snapshot_sqlite(src, staging / name)
        after = sqlite_fingerprint(src)
        created = sorted(_companions_present(src) - present_before)
        # Recorded, never hidden and never deleted: SQLite itself creates
        # empty -wal/-shm files when a WAL-mode database is opened read-only
        # with no other connection. They carry no database content.
        entry["companions_created_by_read"] = created
        check = sqlite3.connect(f"file:{staging / name}?mode=ro", uri=True)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
    except sqlite3.DatabaseError as e:
        entry.update(status="error",
                     note=f"unreadable SQLite source: {type(e).__name__}: {e}")
        return entry
    except PermissionError as e:
        entry.update(status="error", note=f"permission denied: {e.strerror}")
        return entry
    entry.update(snapshot=str(final / name), sha256=sha,
                 bytes=(staging / name).stat().st_size,
                 source_fingerprint_before=before,
                 source_fingerprint_after=after,
                 snapshot_integrity_check=integrity)
    if before != after:
        entry.update(status="changed_during_snapshot",
                     note="SOURCE CHANGED DURING SNAPSHOT (main, -wal or "
                          "-journal differ before/after)")
    elif integrity != "ok":
        entry.update(status="error", note=f"backup integrity_check: {integrity}")
    else:
        entry.update(status="unchanged", note="source unchanged")
    return entry


def _capture_file(src, staging, final, name):
    entry = {"kind": "file_copy", "source": str(src), "required": True,
             "snapshot": None, "sha256": None, "bytes": None}
    if not src.exists():
        entry.update(status="missing", note="required source absent")
        return entry
    entry["source_identity"] = _file_identity(src)
    try:
        sha = snapshot_bytes(src, staging / name)
        after = sha256_file(src)
    except PermissionError as e:
        entry.update(status="error", note=f"permission denied: {e.strerror}")
        return entry
    entry.update(snapshot=str(final / name), sha256=sha,
                 bytes=(staging / name).stat().st_size)
    if sha != after:
        entry.update(status="changed_during_snapshot",
                     note="SOURCE CHANGED DURING SNAPSHOT")
    else:
        entry.update(status="unchanged", note="source unchanged")
    return entry


def _capture_log(src, staging, final, entries):
    entry = {"kind": "live_log_full", "source": str(src), "required": True,
             "snapshot": None, "sha256": None, "bytes": None}
    if not src.exists():
        entry.update(status="missing", note="required source absent")
        entries.append(entry)
        return
    entry["source_identity"] = _file_identity(src)
    try:
        data = src.read_bytes()
    except PermissionError as e:
        entry.update(status="error", note=f"permission denied: {e.strerror}")
        entries.append(entry)
        return
    _write_exclusive(staging / "LocalFlow.log.full", data)
    # Post-read check: the file must still begin with exactly the bytes read.
    with open(src, "rb") as f:
        again = f.read(len(data))
    size_after = os.stat(src).st_size
    if again != data:
        status, note = ("changed_during_snapshot",
                        "SOURCE CHANGED DURING SNAPSHOT (bytes read are no "
                        "longer a prefix of the live log)")
    elif size_after > len(data):
        status, note = ("appended_during_snapshot",
                        f"read once; the running app appended "
                        f"{size_after - len(data)} bytes afterwards (allowed)")
    else:
        status, note = "unchanged", "read once; source unchanged"
    entry.update(snapshot=str(final / "LocalFlow.log.full"),
                 sha256=sha256_bytes(data), bytes=len(data),
                 source_bytes_after=size_after, status=status, note=note)
    entries.append(entry)

    prefix = data[:HISTORICAL_LOG_BYTES]
    prefix_sha = sha256_bytes(prefix)
    if len(data) >= HISTORICAL_LOG_BYTES and prefix_sha == HISTORICAL_LOG_SHA256:
        _write_exclusive(staging / "LocalFlow.log.historical-prefix", prefix)
        entries.append({
            "kind": "historical_prefix", "source": str(src), "required": False,
            "snapshot": str(final / "LocalFlow.log.historical-prefix"),
            "sha256": prefix_sha, "bytes": len(prefix), "status": "verified",
            "note": f"first {HISTORICAL_LOG_BYTES} bytes == audited "
                    f"{HISTORICAL_LOG_SHA256[:12]}…"})
    else:
        entries.append({
            "kind": "historical_prefix", "source": str(src), "required": False,
            "snapshot": None,
            "sha256": prefix_sha if len(data) >= HISTORICAL_LOG_BYTES else None,
            "bytes": min(len(data), HISTORICAL_LOG_BYTES),
            "status": "not_present",
            "note": "live log does NOT extend the audited artifact as a byte "
                    "prefix (historical reproduction must be reported as "
                    "skipped/pending, never passed)"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)
    root = args.root
    try:
        root_info = prepare_root(root)
    except EvidenceRootError as e:
        ap.error(str(e))

    created = dt.datetime.now(dt.timezone.utc)
    run_id = new_run_id(created)
    staging = root / f".{run_id}{PARTIAL_SUFFIX}"
    final = root / run_id
    entries = []
    try:
        _mkdir_private(staging)
        entries.append(_capture_sqlite(APP_SUPPORT / "stats.db", staging,
                                       final, "stats.db.bak"))
        for name in ("dictionary.json", "transforms.json"):
            entries.append(_capture_file(APP_SUPPORT / name, staging, final,
                                         name))
        _capture_log(LOG_PATH, staging, final, entries)

        changed = [e for e in entries if e["status"] == "changed_during_snapshot"]
        errors = [e for e in entries if e["status"] == "error"]
        missing = [e for e in entries
                   if e["status"] == "missing" and e["required"]]
        if changed or errors:
            outcome, code = "failed", 1
        elif missing:
            outcome, code = "incomplete", 2
        else:
            outcome, code = "complete", 0
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "created_utc": created.isoformat(),
            "evidence_root": root_info,
            "run_dir": str(final),
            "tool": {"script": "scripts/v2/snapshot_user_data.py",
                     "revision": _tool_revision()},
            "privacy": "Private evidence. Never commit this root or its contents.",
            "entries": entries,
            "outcome": outcome,
            "complete": outcome == "complete",
            "missing_required": [e["source"] for e in missing],
            "all_sources_unchanged": not changed,
        }
        blob = (json.dumps(manifest, indent=2) + "\n").encode()
        _write_exclusive(staging / MANIFEST_NAME, blob)
        _fsync_dir(staging)
        if os.path.lexists(final):
            raise FileExistsError(errno.EEXIST, "run directory already exists",
                                  str(final))
        os.rename(staging, final)
        _fsync_dir(root)
    except OSError as e:
        print(f"ERROR: snapshot run not published ({type(e).__name__}: {e}); "
              f"partial private data (if any) remains in {staging}",
              file=sys.stderr)
        return 1

    print(json.dumps(manifest, indent=2))
    print(f"\nsnapshot manifest: {final / MANIFEST_NAME}")
    if code == 1:
        print("ERROR: a source changed or could not be read — investigate "
              "before trusting this snapshot", file=sys.stderr)
    elif code == 2:
        print("INCOMPLETE: required source(s) missing: "
              + ", ".join(manifest["missing_required"]), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
