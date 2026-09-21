"""M02: lossless legacy import into the V2 store (Spec S08, EV-03).

Imports the live user data — stats.db (via a verified SQLite-backup copy),
dictionary.json, transforms.json and the legacy text log — into the V2
store. Idempotent: re-running against identical sources adds zero rows; a
grown log imports only its new pairs via byte-prefix reconciliation.

Nothing is printed that contains transcript content; the JSON report holds
counts, hashes and locators only.

Usage:
    .venv/bin/python scripts/v2/import_legacy.py [--store PATH]
        [--backup-dir PATH] [--skip-log] [--output PATH]
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from localflow.v2 import ids, store, importer  # noqa: E402

APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
DEFAULT_STORE = APP_SUPPORT / "v2.db"
DEFAULT_BACKUPS = APP_SUPPORT / "v2-evidence" / "backups"
LEGACY_LOG = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow.log"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=pathlib.Path, default=DEFAULT_STORE)
    ap.add_argument("--backup-dir", type=pathlib.Path, default=DEFAULT_BACKUPS)
    ap.add_argument("--skip-log", action="store_true",
                    help="import only stats/dictionary/transforms")
    ap.add_argument("--output", type=pathlib.Path,
                    help="also write the JSON report to this path")
    args = ap.parse_args(argv)

    st = store.Store(args.store, backup_dir=args.backup_dir)
    try:
        imp = importer.LegacyImporter(st, args.backup_dir)
        report = {
            "schema_version": 1,
            "imported_utc": ids.now_utc_iso(),
            "store": str(args.store),
            "stats_db": imp.import_stats_db(APP_SUPPORT / "stats.db"),
            "dictionary": imp.import_dictionary(APP_SUPPORT / "dictionary.json"),
            "transforms": imp.import_transforms(APP_SUPPORT / "transforms.json"),
            "log": None if args.skip_log else imp.import_log(LEGACY_LOG),
            "totals": None,  # filled below
        }
        st.sync()
        n, raw_w, clean_w, dur, fixed, lo, hi = st.legacy_totals()
        report["totals"] = {
            "legacy_rows": n, "raw_words": raw_w, "cleaned_words": clean_w,
            "duration_sec": dur, "fixed_words": fixed,
            "captured_utc_range": [lo, hi],
            "dated_analytics_rows": st.dated_analytics_rows(),
        }
        report["consistency"] = st.verify()
    finally:
        st.close()

    out = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
