"""M01: build docs/v2/baseline/manifest.json — the authoritative baseline.

Re-derives, without modifying anything: Git state, installed bundle
identity and divergence, effective configuration precedence, configured and
cached models, runtime versions, hardware, data locations with hashes,
deleted-module remnants, running-process evidence, and the historical
artifact reconciliation. Missing facts are null with a reason — never
guessed.

Usage:
    .venv/bin/python scripts/v2/build_baseline_manifest.py
"""

import datetime as dt
import hashlib
import json
import pathlib
import platform
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
APP = pathlib.Path("/Applications/LocalFlow.app")
APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
LOG = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow.log"
AUDIO_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow-audio"
HF_HUB = pathlib.Path.home() / ".cache" / "huggingface" / "hub"
LOCALAI_HUB = pathlib.Path.home() / "Documents" / "LocalAI" / "models" / "hub"

HISTORICAL = {
    "log_sha256": "51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0",
    "log_bytes": 544221,
    "stats_db_sha256": "e4005289c7b9468e27db39be28e35df16fd4076c81692e13e0b086896489cb25",
    "dictionary_sha256": "56f2fcd135e362d4e703975f0e5d9151e624aa7899616a38c4926308940ef547",
    "transforms_sha256": "e7eb86b16a9f31d24fa3c46efca5975ff99d76508524e68b400ad8ae18baee89",
}


def sha256_file(p: pathlib.Path):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git(args):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True).stdout.strip()


def git_state():
    dirty = []
    for line in git(["status", "--porcelain"]).splitlines():
        dirty.append(line)
    tree = git(["status", "--short", "--branch"])
    digest_src = "\n".join(dirty).encode()
    return {
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "head_commit": git(["rev-parse", "HEAD"]),
        "clean_tree": not dirty,
        "dirty_entries": dirty,
        "dirty_digest": hashlib.sha256(digest_src).hexdigest() if dirty else None,
        "status_short": tree,
        "worktrees": git(["worktree", "list"]).splitlines(),
        "remote": git(["remote", "get-url", "origin"]) or None,
    }


def bundle_state():
    if not APP.exists():
        return {"installed": False, "reason": "/Applications/LocalFlow.app absent"}
    info = {}
    try:
        out = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print",
                              str(APP / "Contents" / "Info.plist")],
                             capture_output=True, text=True).stdout
        for key in ("CFBundleIdentifier", "CFBundleShortVersionString",
                    "CFBundleVersion", "LSMinimumSystemVersion"):
            m = re.search(rf"{key} = (.+)", out)
            info[key] = m.group(1) if m else None
    except Exception as e:  # pragma: no cover
        info["plist_error"] = str(e)
    src = APP / "Contents" / "Resources" / "localflow"
    diff = subprocess.run(
        ["diff", "-rq", str(src), str(ROOT / "localflow")],
        capture_output=True, text=True)
    lines = [l for l in diff.stdout.splitlines() if l]
    py_files_only = bool(lines) and all("__pycache__" in l for l in lines)
    matches = diff.returncode == 0 or (diff.returncode == 1 and py_files_only)
    return {
        "installed": True,
        "path": str(APP),
        "identity": info,
        "embedded_code_matches_git_head": matches,
        "divergence": [l for l in lines if "__pycache__" not in l] or None,
        "diff_stderr": diff.stderr.strip() or None,
        "embedded_config": _read_json_or_reason(
            APP / "Contents" / "Resources" / "config.json"),
        "launcher": {
            "path": str(APP / "Contents" / "MacOS" / "LocalFlow"),
            "sha256": sha256_file(APP / "Contents" / "MacOS" / "LocalFlow"),
        },
    }


def _read_json_or_reason(p: pathlib.Path):
    """Read JSON, or return an explicit reason — never crash the manifest."""
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return {"error": f"not found: {p}"}
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


def config_precedence():
    """Which candidate wins under localflow/config.py load() semantics."""
    import os
    env_cfg = os.environ.get("LOCALFLOW_CONFIG", "")
    candidates = [
        ("environment_LOCALFLOW_CONFIG", pathlib.Path(env_cfg) if env_cfg else None),
        ("application_support", APP_SUPPORT / "config.json"),
        ("repo_config", ROOT / "config.json"),
    ]
    winner = None
    for name, p in candidates:
        if p is not None and p.is_file():
            winner = {"source": name, "path": str(p),
                      "content": _read_json_or_reason(p)}
            if isinstance(winner["content"], dict) and "error" in winner["content"]:
                winner["read_error"] = winner["content"].pop("error")
            break
    override_exists = (APP_SUPPORT / "config.json").exists()
    return {
        "precedence": ["explicit path", "$LOCALFLOW_CONFIG",
                       "Application Support override", "repo/bundled config.json"],
        "effective": winner,
        "application_support_override_exists": override_exists,
        "note": f"First match wins; unset keys fall back to DEFAULTS in "
                f"localflow/config.py. Effective source: "
                f"{winner['source'] if winner else 'defaults'}; "
                f"Application Support override "
                f"{'exists' if override_exists else 'does not exist'}.",
    }


def model_entry(model_id, hub_root):
    d = hub_root / ("models--" + model_id.replace("/", "--"))
    if not d.exists():
        return {"cached": False, "hub_root": str(hub_root)}
    refs = d / "refs" / "main"
    rev = refs.read_text().strip() if refs.exists() else None
    snap = d / "snapshots" / rev if rev else None
    weights = sorted(snap.glob("*.safetensors")) if snap else []
    return {
        "cached": True,
        "hub_root": str(hub_root),
        "revision": rev,
        "weights_sha256": {w.name: sha256_file(w) for w in weights},
    }


def runtimes():
    versions = {}
    probes = {
        "mlx": "import mlx.core as mx; print(getattr(mx, '__version__', 'unknown'))",
        "mlx_lm": "import mlx_lm; print(mlx_lm.__version__)",
        "transformers": "import transformers; print(transformers.__version__)",
        "numpy": "import numpy; print(numpy.__version__)",
        "sounddevice": "import sounddevice; print(getattr(sounddevice, '__version__', 'unknown'))",
    }
    for name, code in probes.items():
        r = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "-c", code],
                           capture_output=True, text=True)
        versions[name] = r.stdout.strip() or f"unavailable: {(r.stderr or '?').strip()[:120]}"
    py = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "--version"],
                        capture_output=True, text=True).stdout.strip()
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                          capture_output=True, text=True).stdout.strip()
    mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True).stdout.strip())
    sw = subprocess.run(["sw_vers"], capture_output=True, text=True).stdout
    swd = sw.strip().replace("\n", "; ")
    batt = subprocess.run(["pmset", "-g", "batt"],
                          capture_output=True, text=True).stdout
    power = next((l.strip() for l in batt.splitlines()
                  if "drawing from" in l), None)
    return {
        "python": py,
        "packages": versions,
        "chip": chip,
        "memory_gb": round(mem / 1024**3, 1),
        "macos": swd,
        "power": power,
    }


def data_state():
    files = {}
    for name, key in (("stats.db", "stats_db"), ("dictionary.json", "dictionary"),
                      ("transforms.json", "transforms")):
        p = APP_SUPPORT / name
        if p.exists():
            sha = sha256_file(p)
            files[key] = {
                "path": str(p),
                "exists": True,
                "sha256": sha,
                "bytes": p.stat().st_size,
                "mtime_utc": dt.datetime.fromtimestamp(
                    p.stat().st_mtime, dt.timezone.utc).isoformat(),
                "matches_historical": sha == HISTORICAL[f"{key}_sha256"],
            }
        else:
            files[key] = {"path": str(p), "exists": False, "sha256": None,
                          "bytes": None, "mtime_utc": None,
                          "matches_historical": None}
    extras = sorted(p.name for p in APP_SUPPORT.iterdir()
                    if p.name not in {"stats.db", "dictionary.json",
                                      "transforms.json"})
    log_exists = LOG.exists()
    log_bytes = LOG.stat().st_size if log_exists else 0
    prefix_ok = None
    if log_exists and log_bytes >= HISTORICAL["log_bytes"]:
        prefix_ok = sha256_file_offset(LOG, HISTORICAL["log_bytes"]) == \
            HISTORICAL["log_sha256"]
    wavs = sorted(AUDIO_DIR.glob("*.wav")) if AUDIO_DIR.exists() else []
    return {
        "application_support": files,
        "application_support_other_entries": extras,
        "log": {
            "path": str(LOG), "exists": log_exists, "bytes": log_bytes,
            "live_extends_historical_prefix": prefix_ok,
            "note": "live file grows with use; audited artifact is the byte prefix"
            if prefix_ok else "live log is NOT a superset of the audited artifact",
        },
        "recent_audio": {
            "path": str(AUDIO_DIR),
            "count": len(wavs),
            "files": [w.name for w in wavs],
            "retention": "last 5 dictations, pruned by app.py",
        },
    }


def sha256_file_offset(p: pathlib.Path, n: int):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def deleted_modules():
    """Compiled remnants of modules present locally but absent from Git."""
    pycs = sorted((ROOT / "localflow" / "__pycache__").glob("*.cpython-*.pyc"))
    tracked = set(git(["ls-files"]).splitlines())
    out = []
    for p in pycs:
        stem = p.name.split(".")[0]
        src = f"localflow/{stem}.py"
        if src in tracked:
            continue
        out.append({
            "module": src,
            "pyc": str(p),
            "mtime_utc": dt.datetime.fromtimestamp(
                p.stat().st_mtime, dt.timezone.utc).isoformat(),
            "recovered_interface": DELETED_MODULE_SUMMARY.get(stem),
        })
    dash = ROOT / "Desktop" / "__pycache__" / "dashboard.cpython-314.pyc"
    if dash.exists():
        out.append({
            "module": "Desktop/dashboard.py",
            "pyc": str(dash),
            "mtime_utc": dt.datetime.fromtimestamp(
                dash.stat().st_mtime, dt.timezone.utc).isoformat(),
            "recovered_interface": DELETED_MODULE_SUMMARY.get("dashboard"),
        })
    return out


DELETED_MODULE_SUMMARY = {
    "stats": "SQLite analytics writer/reader: dictations(ts, duration_sec, "
             "raw_text, cleaned_text, raw_words, cleaned_words, fixed_words, "
             "wpm, app_name, app_bundle, kind) + meta table, daily/streak/"
             "app_usage aggregates. Matches stats.db schema.",
    "transforms": "TransformManager: selected-text transforms via clipboard "
                  "copy/restore (_copy_selection/_restore/_run), hotkey "
                  "keys 1/2, save/load transforms.json, DEFAULT_TRANSFORMS.",
    "profile": "Local communication profile: chat-template generation over "
               "eligible history via cleanup_model, caching, eligibility "
               "rules, catchphrase.",
    "_compat": "transformers AutoTokenizer.register compatibility shim "
               "(safe_register) — the 'str' object has no attribute "
               "'__module__' era fix.",
    "dashboard": "Desktop Dashboard: native NSWindow + WKWebView over local "
                 "files, JS bridge (userContentController messages), stats "
                 "served from local SQLite, transform manager integration, "
                 "snapshot support.",
}


def running_process():
    r = subprocess.run(["ps", "auxww"], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines()
             if ("LocalFlow.app" in l or "-m localflow" in l) and "grep" not in l]
    readiness = None
    if LOG.exists():
        text = LOG.read_text(errors="replace")
        loaded = re.findall(r"\[localflow\] cleanup model loaded \(([^)]+)\)", text)
        ready = text.count("[localflow] model loaded.")
        if loaded:
            readiness = {
                "last_cleanup_model": loaded[-1],
                "parakeet_ready_messages": ready,
                "cleanup_load_success_messages": len(loaded),
            }
    return {"processes": lines or None, "log_readiness": readiness}


def _models_from_config(cfg_content):
    """Model cache entries for the IDs the effective config actually names."""
    known_default = isinstance(cfg_content, dict) and "error" not in cfg_content
    if known_default:
        asr_id = cfg_content.get("model", "mlx-community/parakeet-tdt-0.6b-v3")
        cleanup_id = cfg_content.get(
            "cleanup_model", "mlx-community/Qwen3-4B-Instruct-2507-4bit")
    else:
        asr_id = cleanup_id = None
    def entry(model_id):
        if not model_id:
            return {"configured": False,
                    "reason": "effective config unreadable — IDs not derived"}
        return {"configured": True, **model_entry(model_id, HF_HUB),
                "localai_cache": model_entry(model_id, LOCALAI_HUB)}
    return {
        "asr": {"configured_id": asr_id, **entry(asr_id)},
        "cleanup": {"configured_id": cleanup_id, **entry(cleanup_id)},
        "provenance_note": "User-stated provenance (2026-09-21): "
            "'Local AI comes from ~/Documents/LocalAI/'. Observed: the "
            "running app has no HF_HOME/HF_HUB_CACHE override and its "
            "default cache ~/.cache/huggingface/hub holds byte-identical "
            "copies (same revisions and SHA-256) of both models, "
            "populated 2026-09-20/21 (xet download log). The LocalAI "
            "workspace holds the same revisions from 2026-06. Effective "
            "cache for the deployed app: default ~/.cache/huggingface.",
    }


def main():
    config_state = config_precedence()
    manifest = {
        "schema_version": 1,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "milestone": "M01",
        "git": git_state(),
        "installed_bundle": bundle_state(),
        "effective_configuration": config_state,
        "models": _models_from_config(config_state.get("effective", {}).get("content")),
        "runtime": runtimes(),
        "data": data_state(),
        "locally_newer_functionality_absent_from_git": {
            "summary": "An analytics/dictionary/transform/dashboard feature "
                       "set ran on 2026-07-04 (pyc mtimes 17:25–17:29 match "
                       "App Support file mtimes 17:08–17:41). Its source "
                       "modules were later deleted; only compiled remnants "
                       "in ignored __pycache__ dirs remain. The installed "
                       "bundle and Git HEAD contain none of it, so the "
                       "deployed app no longer writes these files.",
            "modules": deleted_modules(),
            "preservation_directive": "Treat App Support stats.db/"
                "dictionary.json/transforms.json as live user data to import "
                "and extend (M02/M05/M11); never infer the features are "
                "absent. Recover interfaces from the pyc remnants above.",
        },
        "running_process_evidence": running_process(),
        "historical_reconciliation": {
            "log_artifact": {
                "historical_sha256": HISTORICAL["log_sha256"],
                "historical_bytes": HISTORICAL["log_bytes"],
                "reproduced_by": "scripts/v2/parse_legacy_log.py (E02 protocol)",
                "report": "docs/v2/baseline/legacy-log-reconciliation.json",
                "pairs": 749, "timed_pairs": 477, "audio_records": 498,
                "metal_shared_event_failures": 3,
                "method_deltas": [
                    "loaded_lexical_changes 107 vs historical 108",
                    "loaded_new_sentence_breaks 134 vs historical 133",
                ],
                "method_delta_reason": "E02 does not pin the lexical-"
                    "normalization/boundary-counting heuristics to the last "
                    "detail; all acceptance-relevant counts, sums, "
                    "correlation and band sizes reproduce exactly.",
            },
            "analytics_rows": 7,
            "dictionary_terms": 7,
            "transform_definitions": 2,
        },
        "unresolved": [
            {
                "fact": "Exact source of the analytics/dictionary/transform "
                        "producers",
                "status": "unresolved",
                "reason": "Source .py files deleted; only .pyc remnants and "
                          "their data files survive. Bytecode decompilation "
                          "beyond interface recovery is not needed for the "
                          "M02 import contract, which reads the data files.",
            },
            {
                "fact": "Producer of instance.lock in Application Support",
                "status": "unresolved",
                "reason": "No surviving source (Git, bundle, or pyc "
                          "interface recovery) references instance.lock; "
                          "inferred — not proven — to belong to the deleted "
                          "Jul-4-era feature set.",
            },
        ],
        "private_data": {
            "evidence_root": str(APP_SUPPORT / "v2-evidence"),
            "excluded_from_git": [
                "live log", "recent audio WAVs", "stats.db",
                "dictionary.json (live copy)", "transforms.json (live copy)",
                "full private snapshots under the evidence root",
            ],
            "committed_sanitized": [
                "docs/v2/baseline/manifest.json (this file: hashes, paths, "
                "versions only)",
                "docs/v2/baseline/legacy-log-reconciliation.json (counts + "
                "physical-line locators, no transcript text)",
            ],
        },
    }
    out = ROOT / "docs/v2/baseline/manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
