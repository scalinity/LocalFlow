"""M01: build a versioned baseline manifest of what is actually running.

Re-derives, without modifying anything: Git state with a content digest of
every dirty path, installed bundle identity compared separately against Git
HEAD and against the working tree, effective configuration per launch
context (mirroring ``localflow.config.load``), configured vs cache-observed
vs resolvable models (mirroring the runtime's HF cache semantics), runtime
inventories of BOTH the repository venv and the installed bundle's venv,
hardware, data locations with hashes, deleted-module remnants and
current-session engine readiness from the dated event log. Missing facts are
null with a reason — never guessed.

Historical vs current (M01 remediation, M01-AUDIT-05): the September 21
baseline at ``docs/v2/baseline/manifest.json`` (schema 1) is a frozen
historical record and is never overwritten. Each run of this generator
writes a new schema-2 record under ``docs/v2/baseline/runs/<run-id>/``
(or ``--output``). Historical findings appear only inside the
``historical_record`` block, labelled with their observation date and
source, never re-asserted as current observations.

What this manifest can NOT prove: which checkpoint a process actually
loaded. Cache observations say what the loader *would* resolve; loaded
identity comes only from runtime load records (``models.*.loaded``).

Usage:
    .venv/bin/python scripts/v2/build_baseline_manifest.py [--output PATH]
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import plistlib
import re
import secrets
import stat
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from localflow import config as lf_config  # noqa: E402  (stdlib-only module)

APP = pathlib.Path("/Applications/LocalFlow.app")
APP_SUPPORT = pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
LOG = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow.log"
EVENT_LOG_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow"
AUDIO_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow-audio"
LOCALAI_HUB = pathlib.Path.home() / "Documents" / "LocalAI" / "models" / "hub"

SCHEMA_VERSION = 2
HISTORICAL_MANIFEST = "docs/v2/baseline/manifest.json"
RUNS_DIR = "docs/v2/baseline/runs"

# Generated evidence outputs are excluded from the dirty-content digest so
# that writing a manifest (or a probe report) cannot change the identity of
# the source it describes. Everything else in the tree is in scope.
GENERATED_EVIDENCE_PREFIXES = (
    "docs/v2/baseline/runs/",
    "docs/v2/benchmarks/",
)

# Configuration keys whose effective VALUES are safe to commit (model and
# pipeline selection). Every other key is recorded by name only.
SAFE_CONFIG_KEYS = ("model", "cleanup", "cleanup_model",
                    "cleanup_implementation", "hotkey")

PACKAGES = ("mlx", "mlx-lm", "parakeet-mlx", "transformers", "numpy",
            "sounddevice", "huggingface-hub", "pyobjc-core")

HISTORICAL = {
    "log_sha256": "51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0",
    "log_bytes": 544221,
    "stats_db_sha256": "e4005289c7b9468e27db39be28e35df16fd4076c81692e13e0b086896489cb25",
    "dictionary_sha256": "56f2fcd135e362d4e703975f0e5d9151e624aa7899616a38c4926308940ef547",
    "transforms_sha256": "e7eb86b16a9f31d24fa3c46efca5975ff99d76508524e68b400ad8ae18baee89",
}

LOADED_REASON = ("a cache observation is not proof of a loaded checkpoint; "
                 "loaded identity comes only from a runtime load record "
                 "(see VERIFICATION.html M01-V003)")


# ---- small helpers ------------------------------------------------------------

def sha256_file(p: pathlib.Path):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """Git's object id for blob content (what ``git ls-tree`` reports)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     ensure_ascii=True).encode()).hexdigest()


def run_cmd(args, cwd=None, timeout=60):
    """Run a command; never raises. Returns ok/stdout/stderr/returncode."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "stdout": "", "returncode": None,
                "stderr": f"{type(e).__name__}: {e}"}
    return {"ok": r.returncode == 0, "stdout": r.stdout,
            "stderr": r.stderr.strip(), "returncode": r.returncode}


def git(args, root=None, timeout=60):
    return run_cmd(["git", "-C", str(root or ROOT), *args], timeout=timeout)


def _reason(res, what):
    return f"{what} failed (exit {res['returncode']}): {res['stderr'][:200]}"


# ---- Git: identity and dirty-content digest (M01-AUDIT-01) --------------------

def _parse_porcelain_z(out: str):
    """Entries from ``git status --porcelain=v1 -z``: [(XY, path)]."""
    items = out.split("\0")
    entries = []
    i = 0
    while i < len(items):
        item = items[i]
        if not item:
            i += 1
            continue
        xy, path = item[:2], item[3:]
        entries.append((xy, path))
        if "R" in xy or "C" in xy:  # rename/copy (index or worktree side):
            # the next NUL-separated item is the source path
            entries.append(("R-", items[i + 1]))
            i += 1
        i += 1
    return entries


def _worktree_state(path: pathlib.Path) -> str:
    """Content identity of one path without following symlinks."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    except OSError as e:
        return f"unreadable:{e.errno}"
    if stat.S_ISLNK(st.st_mode):
        return "symlink:" + hashlib.sha256(
            os.readlink(path).encode("utf-8", "surrogateescape")).hexdigest()
    if stat.S_ISDIR(st.st_mode):
        return "directory"  # nested repository/submodule: not descended
    if not stat.S_ISREG(st.st_mode):
        return "special"
    try:
        return "sha256:" + sha256_file(path)
    except OSError as e:
        return f"unreadable:{e.errno}"


def _index_state(root, path):
    # --literal-pathspecs: a path like "a[1].txt" must not glob-match "a1.txt"
    res = git(["--literal-pathspecs", "ls-files", "--stage", "-z", "--", path],
              root)
    if not res["ok"]:
        return f"unknown:{res['returncode']}"
    entry = res["stdout"].split("\0")[0]
    if not entry:
        return "absent"
    mode, blob = entry.split(" ")[:2]
    return f"{mode}:{blob}"


def git_state(root=None, exclude=GENERATED_EVIDENCE_PREFIXES):
    root = pathlib.Path(root or ROOT)
    out = {"content_scope": "tracked and untracked (non-ignored) paths; "
                            "worktree bytes + index blob per dirty path; "
                            "symlinks by target, never followed; excluded "
                            "generated-evidence prefixes: "
                            + ", ".join(exclude),
           "excluded_prefixes": list(exclude)}
    head = git(["rev-parse", "--verify", "HEAD"], root)
    out["head_commit"] = head["stdout"].strip() if head["ok"] else None
    out["head_reason"] = None if head["ok"] else _reason(head, "git rev-parse")
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    out["branch"] = branch["stdout"].strip() if branch["ok"] else None
    status = git(["status", "--porcelain=v1", "-z", "--untracked-files=all"],
                 root)
    if not status["ok"]:
        out.update(clean_tree=None, dirty_entries=None, dirty_digest=None,
                   dirty_digest_reason=_reason(status, "git status"),
                   excluded_dirty_paths=None)
    else:
        entries, excluded = [], []
        for xy, path in _parse_porcelain_z(status["stdout"]):
            if path.startswith(tuple(exclude)):
                excluded.append(path)
                continue
            entries.append({"xy": xy, "path": path,
                            "worktree": _worktree_state(root / path),
                            "index": _index_state(root, path)})
        entries.sort(key=lambda e: (e["path"], e["xy"]))
        out.update(
            clean_tree=not entries,
            dirty_entries=[f"{e['xy']} {e['path']}" for e in entries],
            dirty_content=entries,
            dirty_digest=canonical_sha256(entries) if entries else None,
            dirty_digest_reason=None,
            excluded_dirty_paths=sorted(excluded))
    short = git(["status", "--short", "--branch"], root)
    out["status_short"] = short["stdout"].strip() if short["ok"] else None
    wt = git(["worktree", "list"], root)
    out["worktrees"] = wt["stdout"].splitlines() if wt["ok"] else None
    remote = git(["remote", "get-url", "origin"], root)
    out["remote"] = remote["stdout"].strip() if remote["ok"] else None
    return out


# ---- installed bundle (M01-AUDIT-02) -------------------------------------------

def _tree_files(base: pathlib.Path):
    """Relative path -> git blob id, skipping bytecode caches (build_app.sh
    strips __pycache__ from the bundle)."""
    files = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if "__pycache__" in rel.parts or p.suffix == ".pyc":
            continue
        if p.is_symlink():
            files[rel.as_posix()] = git_blob_sha1(
                os.readlink(p).encode("utf-8", "surrogateescape"))
        elif p.is_file():
            files[rel.as_posix()] = git_blob_sha1(p.read_bytes())
    return files


def _compare(a: dict, b: dict):
    return {"only_in_bundle": sorted(set(a) - set(b)),
            "only_in_other": sorted(set(b) - set(a)),
            "differs": sorted(k for k in set(a) & set(b) if a[k] != b[k])}


def head_tree_files(root, head, prefix="localflow"):
    res = git(["ls-tree", "-r", "-z", head, "--", prefix], root)
    if not res["ok"]:
        return None, _reason(res, "git ls-tree")
    files = {}
    for item in res["stdout"].split("\0"):
        if not item:
            continue
        meta, path = item.split("\t", 1)
        mode, kind, blob = meta.split(" ")
        if kind == "blob":
            files[path[len(prefix) + 1:]] = blob
    return files, None


def bundle_state(app=None, root=None, head=None):
    app = pathlib.Path(app or APP)
    root = pathlib.Path(root or ROOT)
    if not app.exists():
        return {"installed": False, "path": str(app),
                "reason": f"{app} absent"}
    info = {}
    plist = app / "Contents" / "Info.plist"
    try:
        with open(plist, "rb") as f:
            pl = plistlib.load(f)
        for key in ("CFBundleIdentifier", "CFBundleShortVersionString",
                    "CFBundleVersion", "LSMinimumSystemVersion"):
            info[key] = pl.get(key)
    except (OSError, plistlib.InvalidFileException, ValueError) as e:
        info = {"error": f"{type(e).__name__}: {e}"}
    res = app / "Contents" / "Resources"
    embedded = _tree_files(res / "localflow") if (res / "localflow").is_dir() else None
    out = {"installed": True, "path": str(app), "identity": info,
           "embedded_code_file_count": len(embedded) if embedded is not None else None}
    if embedded is None:
        out.update(embedded_code_matches_git_head=None,
                   embedded_code_matches_worktree=None,
                   comparison_reason="bundle has no Resources/localflow")
    else:
        if head:
            head_files, why = head_tree_files(root, head)
        else:
            head_files, why = None, "Git HEAD unknown"
        if head_files is None:
            out.update(embedded_code_matches_git_head=None,
                       head_comparison_reason=why, divergence_from_head=None)
        else:
            d = _compare(embedded, head_files)
            out.update(embedded_code_matches_git_head=not any(d.values()),
                       head_comparison_reason=None, divergence_from_head=d)
        wt = _tree_files(root / "localflow")
        d = _compare(embedded, wt)
        out.update(embedded_code_matches_worktree=not any(d.values()),
                   divergence_from_worktree=d)
    cfg = res / "config.json"
    out["embedded_config"] = config_file_identity(cfg)
    launcher = app / "Contents" / "MacOS" / "LocalFlow"
    out["launcher"] = {"path": str(launcher),
                       "sha256": sha256_file(launcher) if launcher.is_file() else None,
                       "reason": None if launcher.is_file() else "launcher absent"}
    out["interpreter"] = str(res / "venv" / "bin" / "python")
    return out


# ---- configuration (M01-AUDIT-03) ------------------------------------------------

def config_file_identity(p: pathlib.Path):
    """File identity only: existence, kind, bytes hash, parse status, key
    NAMES — never private values."""
    p = pathlib.Path(p)
    ident = {"path": str(p), "exists": p.exists(), "is_dir": p.is_dir(),
             "sha256": None, "parse": None, "keys": None}
    if p.is_file():
        try:
            data = p.read_bytes()
        except OSError as e:
            ident["parse"] = f"unreadable: {type(e).__name__}"
            return ident
        ident["sha256"] = hashlib.sha256(data).hexdigest()
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            ident["parse"] = f"invalid: {type(e).__name__}"
            return ident
        ident["parse"] = "object" if isinstance(obj, dict) else \
            f"not_an_object:{type(obj).__name__}"
        if isinstance(obj, dict):
            ident["keys"] = sorted(obj)
    return ident


_NO_UPDATE = object()


def resolve_config(explicit=None, env_value=None, user_override=None,
                   bundled=None, defaults=None):
    """Mirror of ``localflow.config.load``: first candidate that EXISTS
    (directories included) wins; a read/parse failure keeps DEFAULTS and
    stops the search; a non-object JSON value makes the runtime raise."""
    defaults = dict(lf_config.DEFAULTS if defaults is None else defaults)
    roles = [("explicit_path", explicit), ("environment_LOCALFLOW_CONFIG", env_value),
             ("application_support_override", user_override),
             ("bundled_or_repo_config", bundled)]
    cfg = dict(defaults)
    candidates, winner = [], None
    for role, c in roles:
        entry = {"role": role, "path": str(c) if c else None,
                 "considered": bool(c) and winner is None}
        if c and winner is None:
            p = pathlib.Path(c)
            entry["exists"] = p.exists()
            if p.exists():
                winner = {"role": role, "path": str(p)}
                try:
                    obj = json.loads(p.read_text())
                except (json.JSONDecodeError, OSError) as e:
                    winner.update(outcome="ignored_bad_config_defaults_used",
                                  error=type(e).__name__)
                    obj = _NO_UPDATE
                except UnicodeDecodeError as e:
                    # load() does not catch this: the runtime would raise.
                    winner.update(outcome="runtime_would_raise",
                                  error=type(e).__name__)
                    cfg = None
                    obj = _NO_UPDATE
                if obj is not _NO_UPDATE:
                    try:
                        cfg.update(obj)
                    except (TypeError, ValueError) as e:
                        winner.update(outcome="runtime_would_raise",
                                      error=type(e).__name__)
                        cfg = None
                    else:
                        winner.update(outcome="applied", error=None)
        candidates.append(entry)
    return cfg, candidates, winner


def load_defaults_from(config_py: pathlib.Path):
    """DEFAULTS of the localflow/config.py a launch context actually runs
    (the installed bundle embeds its own, possibly older, copy)."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            f"_lf_config_{abs(hash(str(config_py)))}", config_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return dict(mod.DEFAULTS), None
    except Exception as e:  # absent/unparseable bundle config.py
        return None, f"{type(e).__name__}: {e}"


def effective_config_record(context, *, explicit=None, env_value=None,
                            env_observation=None, user_override=None,
                            bundled=None, defaults=None,
                            defaults_source="repository localflow/config.py"):
    defaults = dict(lf_config.DEFAULTS if defaults is None else defaults)
    cfg, candidates, winner = resolve_config(explicit, env_value,
                                             user_override, bundled, defaults)
    rec = {"context": context, "defaults_source": defaults_source,
           "env_LOCALFLOW_CONFIG": env_observation,
           "candidates": candidates,
           "winner": winner,
           "effective_source": winner["role"] if winner and
               winner["outcome"] == "applied" else
               ("defaults" if cfg is not None else None),
           "winner_file": config_file_identity(winner["path"])
               if winner else None}
    if cfg is None:
        rec.update(effective_values=None, effective_config_sha256=None,
                   overridden_keys=None,
                   reason="runtime load() would raise on this file")
    else:
        rec.update(
            effective_values={k: cfg.get(k) for k in SAFE_CONFIG_KEYS},
            effective_config_sha256=canonical_sha256(cfg),
            overridden_keys=sorted(k for k in cfg
                                   if cfg[k] != defaults.get(k, object())),
            reason=None)
    return rec, cfg


def launchd_env(name):
    """Value LaunchServices-launched apps inherit, or an explicit unknown."""
    res = run_cmd(["launchctl", "getenv", name], timeout=10)
    if res["returncode"] is None:
        return None, {"observed": False, "reason": res["stderr"][:160]}
    val = res["stdout"].strip() or None
    return val, {"observed": True, "set": val is not None,
                 "method": "launchctl getenv"}


# ---- models (M01-AUDIT-04) ------------------------------------------------------

def hub_root_for(env):
    """Same rule as localflow/stt.py::_model_cached and
    localflow/v2/ids.py::resolve_model_revision."""
    if env.get("HF_HUB_CACHE"):
        return pathlib.Path(env["HF_HUB_CACHE"]), "HF_HUB_CACHE"
    if env.get("HF_HOME"):
        return pathlib.Path(env["HF_HOME"]) / "hub", "HF_HOME"
    return pathlib.Path.home() / ".cache" / "huggingface" / "hub", "default"


def _snapshot_record(snap: pathlib.Path, hash_files=True):
    files = {}
    for p in sorted(snap.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(snap).as_posix()
        if not p.exists():  # dangling symlink into a missing blob
            files[rel] = None
            continue
        files[rel] = sha256_file(p) if hash_files else None
    has_config = (snap / "config.json").exists()
    has_weights = any(snap.glob("*.safetensors"))
    rec = {"revision": snap.name, "files_sha256": files,
           "dangling_files": sorted(k for k, v in files.items()
                                    if v is None and hash_files),
           "has_config_json": has_config, "has_safetensors": has_weights,
           "usable_by_stt_rule": has_config and has_weights}
    rec["snapshot_digest"] = canonical_sha256(files) if hash_files else None
    return rec


def model_cache_observation(model_id, hub_root, hub_root_source="explicit",
                            hash_files=True):
    """Configured -> cache-observed -> resolvable. Never 'loaded'."""
    hub_root = pathlib.Path(hub_root)
    d = hub_root / ("models--" + model_id.replace("/", "--"))
    obs = {"model_id": model_id, "hub_root": str(hub_root),
           "hub_root_source": hub_root_source, "cache_observed": d.is_dir()}
    if not d.is_dir():
        obs.update(snapshots=[], refs_main=None, resolution={
            "stt_model_cached": False,
            "ids_resolve_model_revision": None,
            "ids_resolve_reason": "not_in_cache",
            "refs_main_snapshot_present": None})
        return obs
    refs = d / "refs" / "main"
    refs_main = refs.read_text().strip() if refs.is_file() else None
    snaps_dir = d / "snapshots"
    snaps = sorted(s for s in snaps_dir.iterdir() if s.is_dir()) \
        if snaps_dir.is_dir() else []
    records = [_snapshot_record(s, hash_files) for s in snaps]
    if not snaps:
        rev, why = None, "not_in_cache" if not snaps_dir.is_dir() else "no_snapshot"
    elif len(snaps) != 1:
        rev, why = None, "ambiguous_snapshot"
    else:
        rev, why = snaps[0].name, None
    obs.update(
        refs_main=refs_main,
        snapshots=records,
        resolution={
            "stt_model_cached": any(r["usable_by_stt_rule"] for r in records),
            "ids_resolve_model_revision": rev,
            "ids_resolve_reason": why,
            "refs_main_snapshot_present": (refs_main is not None and
                                           (snaps_dir / refs_main).is_dir())
                                          if refs_main else None,
        })
    return obs


def models_record(cfg, env, *, hash_files=True, localai_hub=None):
    hub, source = hub_root_for(env)
    out = {}
    for role, key in (("asr", "model"), ("cleanup", "cleanup_model")):
        mid = cfg.get(key) if cfg else None
        rec = {"configured_id": mid, "configured_from": key,
               "loaded": None, "loaded_reason": LOADED_REASON}
        if role == "cleanup" and cfg and cfg.get("cleanup") != "llm":
            rec["note"] = (f"cleanup mode is {cfg.get('cleanup')!r}: the "
                           "cleanup model is not loaded by design")
        if mid:
            rec["cache"] = model_cache_observation(mid, hub, source, hash_files)
            if localai_hub is not None and pathlib.Path(localai_hub).is_dir():
                la = model_cache_observation(mid, localai_hub, "localai_workspace",
                                             hash_files)
                eff = {s["revision"]: s["snapshot_digest"]
                       for s in rec["cache"]["snapshots"]}
                la["same_snapshot_digest_as_effective_cache"] = {
                    s["revision"]: (eff.get(s["revision"]) == s["snapshot_digest"]
                                    if s["revision"] in eff else None)
                    for s in la["snapshots"]}
                rec["secondary_cache"] = la
        else:
            rec["cache"] = None
            rec["reason"] = "effective configuration unknown"
        out[role] = rec
    return out


# ---- runtimes (M01-AUDIT-04) ----------------------------------------------------

_PKG_PROBE = (
    "import json, sys, importlib.metadata as md\n"
    "out = {}\n"
    "for n in sys.argv[1:]:\n"
    "    try: out[n] = md.version(n)\n"
    "    except md.PackageNotFoundError: out[n] = None\n"
    "print(json.dumps({'python': sys.version.split()[0],"
    " 'executable': sys.executable, 'prefix': sys.prefix, 'packages': out}))\n"
)


def interpreter_inventory(python: pathlib.Path, label: str):
    python = pathlib.Path(python)
    rec = {"label": label, "path": str(python), "exists": python.exists()}
    if not python.exists():
        rec["reason"] = "interpreter absent"
        return rec
    rec["realpath"] = os.path.realpath(python)
    res = run_cmd([str(python), "-c", _PKG_PROBE, *PACKAGES], timeout=120)
    if not res["ok"]:
        rec["reason"] = _reason(res, "package probe")
        return rec
    try:
        rec.update(json.loads(res["stdout"]))
    except json.JSONDecodeError:
        rec["reason"] = "package probe returned non-JSON"
    rec["method"] = "importlib.metadata (installed distributions, not loaded)"
    return rec


def hardware():
    def sysctl(name):
        r = run_cmd(["sysctl", "-n", name], timeout=10)
        return r["stdout"].strip() if r["ok"] else None
    mem = sysctl("hw.memsize")
    sw = run_cmd(["sw_vers"], timeout=10)
    batt = run_cmd(["pmset", "-g", "batt"], timeout=10)
    return {
        "chip": sysctl("machdep.cpu.brand_string"),
        "memory_gb": round(int(mem) / 1024**3, 1) if mem and mem.isdigit() else None,
        "macos": sw["stdout"].strip().replace("\n", "; ") if sw["ok"] else None,
        "power": next((l.strip() for l in batt["stdout"].splitlines()
                       if "drawing from" in l), None) if batt["ok"] else None,
        "platform": platform.platform(),
        "reason": None if sysctl("hw.memsize") else
            "macOS system facts unavailable on this host",
    }


# ---- current-session readiness (M01-AUDIT-05) -----------------------------------

def current_session_readiness(event_dir=None):
    """Engine readiness for the MOST RECENT app session in the dated event
    log. Earlier sessions never vouch for the current one."""
    event_dir = pathlib.Path(event_dir or EVENT_LOG_DIR)
    files = sorted(event_dir.glob("events-*.jsonl")) if event_dir.is_dir() else []
    if not files:
        return {"source": str(event_dir), "session": None,
                "reason": "no dated event log files"}
    events = []
    for f in files:
        try:
            for line in f.read_text(errors="replace").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event") in ("app.ready", "worker.engine_state"):
                    events.append(rec)
        except OSError:
            continue
    ready = [e for e in events if e.get("event") == "app.ready"]
    if not ready:
        return {"source": str(event_dir), "session": None,
                "reason": "no app.ready event recorded"}
    last = max(ready, key=lambda e: e.get("timestamp_utc") or "")
    sid = last.get("session_id")
    states = [e for e in events if e.get("session_id") == sid
              and e.get("event") == "worker.engine_state"]
    latest = {}
    for e in sorted(states, key=lambda e: (e.get("timestamp_utc") or "",
                                           e.get("sequence") or 0)):
        latest[e.get("model_id")] = {
            "outcome": e.get("outcome"), "reason_code": e.get("reason_code"),
            "timestamp_utc": e.get("timestamp_utc"),
            "worker_generation": e.get("worker_generation")}
    return {"source": str(event_dir),
            "session": {"session_id": sid,
                        "ready_at_utc": last.get("timestamp_utc"),
                        "process_id": last.get("process_id"),
                        "source_revision": last.get("source_revision"),
                        "config_hash": last.get("config_hash"),
                        "engine_state_by_model": latest or None},
            "reason": None if latest else
                "session recorded no engine_state events"}


def legacy_log_last_segment(log=None):
    """Readiness in the LAST launch segment of the legacy text log only.
    Whole-log success counts are history, not current evidence."""
    log = pathlib.Path(log or LOG)
    if not log.exists():
        return {"source": str(log), "last_segment": None,
                "reason": "legacy log absent"}
    lines = log.read_text(errors="replace").splitlines()
    start = None
    for n, line in enumerate(lines, start=1):
        if "[localflow] ready — hold" in line:
            start = n
    if start is None:
        return {"source": str(log), "last_segment": None,
                "reason": "no legacy launch marker (current builds log "
                          "readiness to the dated event log)"}
    state, model = None, None
    for line in lines[start:]:
        m = re.search(r"\[localflow\] cleanup model loaded \(([^)]+)\)", line)
        if m:
            state, model = "loaded", m.group(1)
        elif "[localflow] cleanup model unavailable" in line:
            state, model = "unavailable", None
    return {"source": str(log),
            "last_segment": {"start_line": start, "cleanup_state": state,
                             "cleanup_model": model},
            "reason": None}


def running_processes():
    r = run_cmd(["ps", "-axo", "pid,lstart,command"], timeout=10)
    if not r["ok"]:
        return {"processes": None, "reason": _reason(r, "ps")}
    lines = [l.strip() for l in r["stdout"].splitlines()
             if ("LocalFlow.app" in l or "-m localflow" in l) and "grep" not in l]
    return {"processes": lines, "reason": None}


# ---- data locations ----------------------------------------------------------------

def data_state(app_support=None, log=None, audio_dir=None):
    app_support = pathlib.Path(app_support or APP_SUPPORT)
    log = pathlib.Path(log or LOG)
    audio_dir = pathlib.Path(audio_dir or AUDIO_DIR)
    files = {}
    for name, key in (("stats.db", "stats_db"), ("dictionary.json", "dictionary"),
                      ("transforms.json", "transforms")):
        p = app_support / name
        if p.is_file():
            sha = sha256_file(p)
            st = p.stat()
            files[key] = {"path": str(p), "exists": True, "sha256": sha,
                          "bytes": st.st_size,
                          "mtime_utc": dt.datetime.fromtimestamp(
                              st.st_mtime, dt.timezone.utc).isoformat(),
                          "matches_historical": sha == HISTORICAL[f"{key}_sha256"]}
        else:
            files[key] = {"path": str(p), "exists": False, "sha256": None,
                          "bytes": None, "mtime_utc": None,
                          "matches_historical": None}
    for suffix in ("-wal", "-shm", "-journal"):
        c = app_support / f"stats.db{suffix}"
        files[f"stats_db{suffix}"] = {"exists": c.exists(),
                                      "bytes": c.stat().st_size if c.exists() else None}
    extras = sorted(p.name for p in app_support.iterdir()
                    if p.name not in {"stats.db", "dictionary.json",
                                      "transforms.json"}) \
        if app_support.is_dir() else None
    prefix_ok = None
    log_bytes = log.stat().st_size if log.exists() else None
    if log_bytes is not None and log_bytes >= HISTORICAL["log_bytes"]:
        with open(log, "rb") as f:
            prefix_ok = hashlib.sha256(f.read(HISTORICAL["log_bytes"])).hexdigest() \
                == HISTORICAL["log_sha256"]
    wavs = sorted(audio_dir.glob("*.wav")) if audio_dir.is_dir() else []
    return {"application_support": files,
            "application_support_other_entries": extras,
            "log": {"path": str(log), "exists": log_bytes is not None,
                    "bytes": log_bytes,
                    "live_extends_historical_prefix": prefix_ok},
            "recent_audio": {"path": str(audio_dir), "count": len(wavs)}}


def deleted_modules(root=None):
    """Compiled remnants of modules present locally but absent from Git."""
    root = pathlib.Path(root or ROOT)
    tracked = git(["ls-files"], root)
    if not tracked["ok"]:
        return {"modules": None, "reason": _reason(tracked, "git ls-files")}
    tracked = set(tracked["stdout"].splitlines())
    out = []
    for p in sorted((root / "localflow" / "__pycache__").glob("*.cpython-*.pyc")):
        src = f"localflow/{p.name.split('.')[0]}.py"
        if src in tracked:
            continue
        out.append({"module": src, "pyc": str(p),
                    "mtime_utc": dt.datetime.fromtimestamp(
                        p.stat().st_mtime, dt.timezone.utc).isoformat()})
    for dash in sorted((root / "Desktop" / "__pycache__").glob("dashboard.*.pyc")):
        out.append({"module": "Desktop/dashboard.py", "pyc": str(dash),
                    "mtime_utc": dt.datetime.fromtimestamp(
                        dash.stat().st_mtime, dt.timezone.utc).isoformat()})
    return {"modules": out, "reason": None}


def historical_record():
    """Pointer to the frozen September 21 observations — dated, sourced,
    never re-asserted as current."""
    return {
        "kind": "historical_record_pointer",
        "observed_utc_date": "2026-09-21",
        "source_documents": [HISTORICAL_MANIFEST,
                             "docs/v2/baseline/legacy-log-reconciliation.json",
                             "docs/v2/acceptance/M01/results.json"],
        "note": "Findings recorded on 2026-09-21 (installed bundle == 7cdd904, "
                "legacy-log aggregates, user-stated LocalAI cache provenance, "
                "deleted-module interface recovery) live only in those "
                "documents. This run re-observes current state; it does not "
                "carry historical claims forward.",
        "historical_artifact_hashes": HISTORICAL,
    }


# ---- assembly --------------------------------------------------------------------

def build(*, root=None, app=None, env=None, hash_model_files=True):
    root = pathlib.Path(root or ROOT)
    env = dict(os.environ if env is None else env)
    g = git_state(root)
    bundle = bundle_state(app, root, g["head_commit"])

    if root.resolve() == ROOT.resolve():
        repo_defaults, repo_defaults_source = None, "repository localflow/config.py"
    else:
        # --repo-root: the described checkout's own config.py, which may be
        # at another commit than the script's checkout.
        repo_defaults, why = load_defaults_from(root / "localflow" / "config.py")
        repo_defaults_source = (f"described checkout {root}/localflow/config.py"
                                if repo_defaults is not None else
                                f"script checkout localflow/config.py (described "
                                f"checkout defaults unreadable: {why})")
    repo_ctx, repo_cfg = effective_config_record(
        "repo_run (this shell: ./run.sh or the generator's environment)",
        defaults=repo_defaults, defaults_source=repo_defaults_source,
        env_value=env.get("LOCALFLOW_CONFIG"),
        env_observation={"observed": True, "set": bool(env.get("LOCALFLOW_CONFIG")),
                         "method": "generator process environment"},
        user_override=lf_config.user_override_path(),
        bundled=root / "config.json")
    contexts = {"repo_run": repo_ctx}
    models = {"repo_run": models_record(repo_cfg, env,
                                        hash_files=hash_model_files,
                                        localai_hub=LOCALAI_HUB)}
    if bundle.get("installed"):
        la_env = {}
        la_obs = {}
        for name in ("LOCALFLOW_CONFIG", "HF_HUB_CACHE", "HF_HOME"):
            val, obs = launchd_env(name)
            la_obs[name] = obs
            if val:
                la_env[name] = val
        resources = pathlib.Path(bundle["path"]) / "Contents" / "Resources"
        app_defaults, why = load_defaults_from(
            resources / "localflow" / "config.py")
        app_ctx, app_cfg = effective_config_record(
            "installed_app (LaunchServices; launchd user environment)",
            env_value=la_env.get("LOCALFLOW_CONFIG"),
            env_observation=la_obs["LOCALFLOW_CONFIG"],
            user_override=lf_config.user_override_path(),
            bundled=resources / "config.json",
            defaults=app_defaults,
            defaults_source="installed bundle localflow/config.py"
            if app_defaults is not None else
            f"repository localflow/config.py (bundle defaults unreadable: {why})")
        app_ctx["launchd_environment_observations"] = la_obs
        contexts["installed_app"] = app_ctx
        models["installed_app"] = models_record(app_cfg, la_env,
                                                hash_files=hash_model_files)

    interpreters = [interpreter_inventory(root / ".venv" / "bin" / "python",
                                          "repo_venv")]
    if bundle.get("installed"):
        interpreters.append(interpreter_inventory(
            pathlib.Path(bundle["interpreter"]), "installed_bundle_venv"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "current_run_observation",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "milestone": "M01",
        "generator": {"script": "scripts/v2/build_baseline_manifest.py",
                      "schema_version": SCHEMA_VERSION},
        "git": g,
        "installed_bundle": bundle,
        "effective_configuration": {
            "precedence": ["explicit path", "$LOCALFLOW_CONFIG",
                           "Application Support override",
                           "config.json next to the running code "
                           "(repo for ./run.sh, Contents/Resources for the app)"],
            "semantics": "localflow/config.py::load — first EXISTING candidate "
                         "wins (a directory counts and yields DEFAULTS); a "
                         "read/parse failure yields DEFAULTS",
            "contexts": contexts},
        "models": models,
        "runtime": {"interpreters": interpreters, "hardware": hardware()},
        "data": data_state(),
        "locally_newer_functionality_absent_from_git": deleted_modules(root),
        "readiness": {"current_session": current_session_readiness(),
                      "legacy_log_last_segment": legacy_log_last_segment(),
                      "processes": running_processes()},
        "historical_record": historical_record(),
        "private_data": {
            "evidence_root": str(APP_SUPPORT / "v2-evidence"),
            "committed_sanitized": "hashes, paths, versions, key names and "
                                   "model-selection values only; no config "
                                   "payloads, transcripts or database rows"},
    }


def default_output(root=None):
    root = pathlib.Path(root or ROOT)
    run_id = (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
              + "-" + secrets.token_hex(3))
    return root / RUNS_DIR / run_id / "manifest.json"


def write_manifest(manifest, out: pathlib.Path, root=None):
    root = pathlib.Path(root or ROOT)
    if out.resolve() == (root / HISTORICAL_MANIFEST).resolve():
        raise SystemExit(f"refusing to overwrite the frozen historical "
                         f"baseline {HISTORICAL_MANIFEST}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x") as f:  # never replaces an existing record
        f.write(json.dumps(manifest, indent=2) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=pathlib.Path,
                    help=f"default: {RUNS_DIR}/<run-id>/manifest.json")
    ap.add_argument("--skip-model-hashes", action="store_true",
                    help="record model file names without hashing contents")
    ap.add_argument("--repo-root", type=pathlib.Path,
                    help="describe this checkout instead of the one holding "
                         "the script (e.g. run the repaired generator from a "
                         "verification worktree against your main checkout)")
    ap.add_argument("--app", type=pathlib.Path,
                    help=f"installed bundle to inspect (default {APP}; "
                         "build_app.sh falls back to ~/Applications)")
    args = ap.parse_args(argv)
    root = args.repo_root.resolve() if args.repo_root else ROOT
    manifest = build(root=root, app=args.app,
                     hash_model_files=not args.skip_model_hashes)
    manifest["generator"]["script_checkout"] = str(ROOT)
    manifest["generator"]["described_checkout"] = str(root)
    out = args.output or default_output()
    write_manifest(manifest, out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
