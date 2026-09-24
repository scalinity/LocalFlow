#!/usr/bin/env python3
"""Build a portable dataset export from the live store (V2 M14,
Spec S29.13).

Usage:
    .venv/bin/python scripts/v2/export_dataset.py DEST_DIR \
        [--views asr_supervised,cleanup_supervised,preference_pairs] \
        [--partitions train,validation,frozen_test] [--db PATH]

Runs against the live store by default (single application writer:
the exporter submits through the same writer thread and exits). The
build is atomic — nothing is left labeled complete on a refusal.
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("destination", type=pathlib.Path)
    ap.add_argument("--views", default="asr_supervised,"
                                       "cleanup_supervised,"
                                       "preference_pairs")
    ap.add_argument("--partitions", default="train,validation,"
                                            "frozen_test")
    ap.add_argument("--db", default=pathlib.Path.home()
                      / "Library/Application Support/LocalFlow/v2.db")
    args = ap.parse_args()
    views = [v.strip() for v in args.views.split(",") if v.strip()]
    partitions = tuple(p.strip() for p in args.partitions.split(",")
                       if p.strip())
    # Opening an older store migrates it; the pre-migration backup goes
    # where the app puts it (never a migration without a backup).
    store = store_mod.Store(
        args.db,
        artifacts_dir=args.db.parent / "v2-artifacts",
        backup_dir=args.db.parent / "v2-evidence" / "backups")
    try:
        exporter = export_mod.DatasetExporter(store)
        out = exporter.build(args.destination, task_views=views,
                             partitions=partitions)
    except export_mod.ExportError as e:
        print(f"export refused: {e}")
        return 1
    finally:
        store.close()
    print(f"export {out['state']} · {out['export_id']}")
    print(f"counts: {out.get('counts')}")
    print(f"fingerprint: {out.get('fingerprint')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
