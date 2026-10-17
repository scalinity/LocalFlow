"""Lossless whitespace compaction for a newly created model export."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def _compact_whitespace(raw: bytes) -> bytes:
    """Leave strings, escape sequences and numeric spellings byte-exact."""
    out = bytearray()
    quoted = escaped = False
    for char in raw:
        if quoted:
            out.append(char)
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
            out.append(char)
        elif char not in b" \t\r\n":
            out.append(char)
    return bytes(out)


def _reject_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def compact_json_metadata(path) -> dict:
    """Compact top-level JSON in a new export, returning a per-file receipt.

    All JSON is checked before any write. Weight files, non-JSON assets and
    subdirectories are untouched. Original JSON spellings are retained;
    only whitespace outside strings is removed. Existing exports must be
    copied or newly exported by the caller before using this function.
    """
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected a real model export directory")
    entries = sorted(root.iterdir())
    candidates = [p for p in entries if p.suffix.lower() == ".json"]
    if any(p.is_symlink() for p in candidates):
        raise ValueError("JSON metadata symlinks are not supported")
    before_total = sum(p.stat().st_size for p in entries if p.is_file())
    plans, records = [], []
    for file in candidates:
        if not file.is_file():
            continue
        raw = file.read_bytes()
        value = json.loads(raw, parse_constant=_reject_constant)
        compact = _compact_whitespace(raw)
        if json.loads(compact, parse_constant=_reject_constant) != value:
            raise ValueError(f"JSON values changed: {file.name}")
        smaller = len(compact) < len(raw)
        after = compact if smaller else raw
        records.append({
            "file": file.name, "before_bytes": len(raw), "after_bytes": len(after),
            "saved_bytes": len(raw) - len(after),
            "before_sha256": hashlib.sha256(raw).hexdigest(),
            "after_sha256": hashlib.sha256(after).hexdigest(),
            "parsed_values_equal": True, "written": smaller,
        })
        if smaller:
            plans.append((file, compact, stat.S_IMODE(file.stat().st_mode)))
    for file, compact, mode in plans:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, prefix=f".{file.name}.",
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(compact)
                os.fchmod(stream.fileno(), mode)
            os.replace(temporary, file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    saved = sum(r["saved_bytes"] for r in records)
    return {
        "directory": str(root.resolve()), "strategy": "json_whitespace_only",
        "files": records, "saved_bytes": saved,
        "artifact_before_bytes": before_total,
        "artifact_after_bytes": before_total - saved,
        "untouched_entries": [p.name for p in entries
                              if p.name not in {r["file"] for r in records}],
    }
