"""M01: non-destructive snapshots of live LocalFlow user data.

Copies the live stats.db (via the SQLite backup API, so journal/WAL state is
consistent), dictionary.json, transforms.json and the text log into a private
evidence root OUTSIDE the Git repository. Nothing here writes to, truncates or
otherwise modifies a live file; every source is hashed before and after to
prove the originals are byte-identical.

The live log is appended to by the running app, so it is read exactly once
into memory; the before/after hashes of the on-disk file can legitimately
differ if the app dictated while the snapshot ran. That is recorded as an
append race, not treated as a mutation by this tool.

Usage:
    .venv/bin/python scripts/v2/snapshot_user_data.py [--root PATH]
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys

APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
LOG_PATH = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow.log"
DEFAULT_ROOT = APP_SUPPORT / "v2-evidence"

# Historical artifact identities from the v1.0 audit (Evaluation E02). Used
# only to label the byte-prefix of the live log; the live log is expected to
# be longer because dictation continued after the audit.
HISTORICAL_LOG_SHA256 = "51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0"
HISTORICAL_LOG_BYTES = 544221


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def snapshot_sqlite(src: pathlib.Path, dst: pathlib.Path) -> str:
    """Consistent snapshot via the SQLite backup API on a read-only source."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        backup = sqlite3.connect(dst)
        try:
            con.backup(backup)
        finally:
            backup.close()
    finally:
        con.close()
    return sha256_file(dst)


def snapshot_bytes(src: pathlib.Path, dst: pathlib.Path) -> str:
    data = src.read_bytes()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return sha256_bytes(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)
    root = args.root
    # The evidence root must live outside this repository: its contents are
    # private by contract, and a root inside the worktree would invite an
    # accidental commit regardless of .gitignore rules.
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    resolved = root.resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        ap.error("--root must live outside the repository "
                 f"(got {resolved} inside {repo_root})")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    entries = []

    def record(kind, src, dst, sha, note=None):
        entries.append(
            {
                "kind": kind,
                "source": str(src),
                "snapshot": str(dst),
                "sha256": sha,
                "bytes": dst.stat().st_size,
                "note": note,
            }
        )

    # --- SQLite: consistent backup, never a plain copy of a live DB -------
    stats_src = APP_SUPPORT / "stats.db"
    if stats_src.exists():
        before = sha256_file(stats_src)
        dst = root / stamp / "stats.db.bak"
        sha = snapshot_sqlite(stats_src, dst)
        after = sha256_file(stats_src)
        record(
            "sqlite_backup", stats_src, dst, sha,
            "source unchanged" if before == after else "SOURCE CHANGED DURING SNAPSHOT",
        )

    # --- JSON originals: byte copies with hashes --------------------------
    for name in ("dictionary.json", "transforms.json"):
        src = APP_SUPPORT / name
        if src.exists():
            before = sha256_file(src)
            dst = root / stamp / name
            sha = snapshot_bytes(src, dst)
            after = sha256_file(src)
            record(
                "file_copy", src, dst, sha,
                "source unchanged" if before == after else "SOURCE CHANGED DURING SNAPSHOT",
            )

    # --- Live log: read once; historical prefix extracted and verified ----
    if LOG_PATH.exists():
        data = LOG_PATH.read_bytes()
        dst = root / stamp / "LocalFlow.log.full"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        live_sha = sha256_bytes(data)
        prefix_sha = sha256_bytes(data[:HISTORICAL_LOG_BYTES])
        matches_historical = prefix_sha == HISTORICAL_LOG_SHA256
        record(
            "live_log_full", LOG_PATH, dst, live_sha,
            "read once; appender may extend the file concurrently",
        )
        if len(data) >= HISTORICAL_LOG_BYTES and matches_historical:
            pdst = root / stamp / "LocalFlow.log.historical-prefix"
            pdst.write_bytes(data[:HISTORICAL_LOG_BYTES])
            record(
                "historical_prefix", LOG_PATH, pdst, prefix_sha,
                f"first {HISTORICAL_LOG_BYTES} bytes == audited {HISTORICAL_LOG_SHA256[:12]}…",
            )
        else:
            entries.append(
                {
                    "kind": "historical_prefix",
                    "source": str(LOG_PATH),
                    "snapshot": None,
                    "sha256": prefix_sha if len(data) >= HISTORICAL_LOG_BYTES else None,
                    "bytes": min(len(data), HISTORICAL_LOG_BYTES),
                    "note": "live log does NOT extend the audited artifact as a byte prefix",
                }
            )

    manifest = {
        "schema_version": 1,
        "created_utc": stamp,
        "evidence_root": str(root),
        "privacy": "Private evidence. Never commit this root or its contents.",
        "entries": entries,
        "all_sources_unchanged": all(
            "SOURCE CHANGED" not in (e["note"] or "") for e in entries
        ),
    }
    out = root / stamp / "snapshot-manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    print(f"\nsnapshot manifest: {out}")
    mutated = any("SOURCE CHANGED" in (e["note"] or "") for e in entries)
    if mutated:
        print("ERROR: a source changed during snapshotting — investigate "
              "before trusting this snapshot", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
