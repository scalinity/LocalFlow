"""Development-only input checks shared by offline research tools."""
from __future__ import annotations

import json
import re
from pathlib import Path


def development_cases(path, prefix="development"):
    path = Path(path)
    forbidden = re.compile(r"(?:^|[^a-z])(final|test|fresh|locked)(?:[^a-z]|$)", re.I)
    if prefix != "development" or forbidden.search(str(path)) or forbidden.search(str(path.resolve())):
        raise ValueError("Research annotation/export accepts development data only")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or any(r.get("split") not in ("validation", "development", "dev") for r in rows):
        raise ValueError("Cases must explicitly belong to the development split")
    ids = [r["case_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate development case IDs")
    return rows
