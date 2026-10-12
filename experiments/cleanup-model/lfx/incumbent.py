"""Read-only verification of the cleanup model the installed app actually uses."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from pathlib import Path

from .common import ART, CONFIG, file_sha256, utc_now, write_json


def verify() -> dict:
    a = CONFIG["models"]["A"]
    home = Path.home()
    out = {"checked": utc_now(), "expected": a}
    configs = {}
    for path in [Path("/Applications/LocalFlow.app/Contents/Resources/config.json"),
                 home / "Library/Application Support/LocalFlow/config.json"]:
        if path.exists():
            data = json.loads(path.read_text())
            configs[str(path)] = {k: v for k, v in data.items() if "cleanup" in k or k == "model"}
    out["config_files"] = configs
    from localflow import config as lf_config
    out["config_default_cleanup_model"] = lf_config.DEFAULTS.get("cleanup_model") \
        if hasattr(lf_config, "DEFAULTS") else None
    # The live app's own event log records which cleanup model it loaded.
    seen = {}
    for f in sorted(glob.glob(str(home / "Library/Logs/LocalFlow/events-*.jsonl")))[-3:]:
        for m in re.finditer(r'"model_id":\s*"([^"]+)"', Path(f).read_text(errors="ignore")):
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    out["event_log_model_ids_last_3_days"] = seen
    try:
        ps = subprocess.run(["pgrep", "-fl", "localflow.v2.worker"], capture_output=True, text=True).stdout
        out["live_worker_running"] = bool(ps.strip())
    except Exception:
        out["live_worker_running"] = None
    hashes = {}
    for root in [home / ".cache/huggingface/hub", Path(os.path.expanduser(CONFIG["paths"]["hf_home"])) / "hub"]:
        snap = root / f"models--{a['repository_id'].replace('/', '--')}" / "snapshots" / a["revision"]
        if snap.exists():
            hashes[str(root)] = {f: file_sha256(snap / f) for f in ("model.safetensors", "config.json", "chat_template.jinja")}
    out["weight_hashes"] = hashes
    vals = [tuple(sorted(h.items())) for h in hashes.values()]
    out["caches_identical"] = len(vals) >= 2 and len(set(vals)) == 1
    out["verified"] = (a["repository_id"] in seen or any(a["repository_id"] in json.dumps(c) for c in configs.values())) \
        and out["caches_identical"]
    write_json(ART / "incumbent.json", out)
    return out
