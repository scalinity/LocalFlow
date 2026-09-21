"""Identity, clock and provenance helpers for the V2 layer (Spec S06-S07).

Every identifier minted here is a UUID with a short kind prefix so log lines
and database rows are self-describing. Legacy imports keep their frozen
identity `legacy:<source-sha>:<physical-line-range>` (contracts/jobs.md)
and never reuse this mint.
"""

import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import time
import uuid

PIPELINE_REVISION = "v2.0"

_source_revision_cache: str | None = None


def new_id(kind: str) -> str:
    return f"{kind}-{uuid.uuid4().hex}"


def now_utc_iso(ts: float | None = None) -> str:
    """RFC 3339 UTC instant with millisecond precision."""
    if ts is None:
        ts = time.time()
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def local_zone_name() -> str | None:
    """Observed IANA zone when resolvable; never a guess."""
    tz = os.environ.get("TZ")
    if tz and "/" in tz:
        return tz
    try:
        target = os.readlink("/etc/localtime")
        # /var/db/timezone/zoneinfo/America/New_York -> America/New_York
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    except OSError:
        pass
    return None


def utc_offset_minutes(ts: float | None = None) -> int:
    if ts is None:
        ts = time.time()
    return int(dt.datetime.fromtimestamp(ts).astimezone().utcoffset().total_seconds() // 60)


def source_revision() -> str:
    """Commit the running code was built from; '+dirty' when the tree is not clean."""
    global _source_revision_cache
    if _source_revision_cache is None:
        root = pathlib.Path(__file__).resolve().parent.parent.parent
        try:
            sha = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            _source_revision_cache = "unknown:no-git"
            return _source_revision_cache
        try:
            dirty = bool(subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            dirty = True
        _source_revision_cache = sha + ("+dirty" if dirty else "")
    return _source_revision_cache


def resolve_model_revision(model_id: str) -> tuple[str | None, str | None]:
    """Snapshot hash the loader would resolve from the HF cache, or a reason."""
    cache = os.environ.get("HF_HUB_CACHE")
    if cache:
        hub = pathlib.Path(cache)
    else:
        home = os.environ.get("HF_HOME")
        base = pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "huggingface"
        hub = base / "hub"
    snaps = hub / ("models--" + model_id.replace("/", "--")) / "snapshots"
    if not snaps.is_dir():
        return None, "not_in_cache"
    names = sorted(s.name for s in snaps.iterdir() if s.is_dir())
    if len(names) != 1:
        return None, "ambiguous_snapshot" if names else "no_snapshot"
    return names[0], None


def config_hash(cfg: dict) -> str:
    payload = json.dumps(cfg, sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
