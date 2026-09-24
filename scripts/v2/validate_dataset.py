#!/usr/bin/env python3

"""Standalone dataset validator (V2 M14, Spec S29.13/E19.5).

Usage:
    .venv/bin/python scripts/v2/validate_dataset.py DATASET_DIR

Validates a portable export WITHOUT the app database, from any working
directory, offline: hash manifest, structure, relative-path safety and
task-input reconstruction. Exit 0 = valid; exit 1 = issues (printed).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2.curation.export import validate_dataset  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    report = validate_dataset(pathlib.Path(sys.argv[1]))
    print(f"valid: {report['valid']}")
    for issue in report.get("issues") or []:
        print(f"  - {issue}")
    counts = report.get("counts") or {}
    if counts:
        print(f"counts: {counts}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
