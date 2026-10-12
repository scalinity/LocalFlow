"""Paths, config, atomic JSON and the in-process API-key loader."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import yaml

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[1]
SCRIPTS_V2 = REPO_ROOT / "scripts" / "v2"

for p in (str(REPO_ROOT), str(SCRIPTS_V2)):
    if p not in sys.path:
        sys.path.insert(0, p)


def load_config() -> dict:
    return yaml.safe_load((EXP_DIR / "config.yaml").read_text())


CONFIG = load_config()
ART = REPO_ROOT / CONFIG["paths"]["artifacts"]
REPORT_DIR = REPO_ROOT / CONFIG["paths"]["report_dir"]


def expand(p: str) -> Path:
    """~ expands to the home folder; relative paths resolve against the repo root."""
    path = Path(os.path.expanduser(p))
    return path if path.is_absolute() else REPO_ROOT / path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_json(value) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, ensure_ascii=False))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(data)
    os.replace(tmp, path)


def write_json(path: Path, value) -> None:
    atomic_write(path, json.dumps(value, indent=1, ensure_ascii=False, sort_keys=False))


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_jsonl(path: Path, rows) -> None:
    atomic_write(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def anthropic_api_key() -> str:
    """Read ANTHROPIC_API_KEY from the repository's .env without exporting,
    printing or persisting it."""
    path = expand(CONFIG["paths"]["env_file"])
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise RuntimeError(f"ANTHROPIC_API_KEY not found in {path}")


def anthropic_client(max_retries: int = 2):
    import anthropic
    return anthropic.Anthropic(api_key=anthropic_api_key(), max_retries=max_retries)
