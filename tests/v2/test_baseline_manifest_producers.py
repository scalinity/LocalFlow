"""M01 remediation: independent producer tests for the baseline manifest
generator (M01-AUDIT-01..05, M01-AUDIT-15).

Every expectation here is either hand-specified from a synthetic fixture
(temporary Git repositories, fake bundles, fake HF caches, fake event logs)
or taken from the RUNTIME's own function (``localflow.config.load``,
``localflow.stt._model_cached``, ``localflow.v2.ids.resolve_model_revision``)
— never from the generator helper under test. The frozen September 21
document is checked separately in test_baseline_manifest.py.

Run: .venv/bin/python tests/v2/test_baseline_manifest_producers.py
"""

import contextlib
import io
import json
import os
import pathlib
import plistlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.v2.build_baseline_manifest as bm  # noqa: E402
from localflow import config as lf_config  # noqa: E402

TESTS = []


def case(fn):
    TESTS.append(fn)
    return fn


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def make_repo(td):
    r = pathlib.Path(td) / "repo"
    (r / "localflow").mkdir(parents=True)
    sh(r, "git", "init", "-q")
    sh(r, "git", "config", "user.email", "t@example.invalid")
    sh(r, "git", "config", "user.name", "t")
    (r / "localflow" / "a.py").write_text("A = 1\n")
    (r / "localflow" / "b.py").write_text("B = 1\n")
    (r / "config.json").write_text('{"cleanup": "llm"}')
    sh(r, "git", "add", "-A")
    sh(r, "git", "commit", "-q", "-m", "init")
    return r


# ---- M01-AUDIT-01: Git identity and content digest ---------------------------

@case
def test_dirty_digest_tracks_content_not_status_text():
    with tempfile.TemporaryDirectory() as td:
        r = make_repo(td)
        clean = bm.git_state(r)
        assert clean["clean_tree"] is True and clean["dirty_digest"] is None
        assert len(clean["head_commit"]) == 40
        (r / "localflow" / "a.py").write_text("A = 2\n")
        s2 = bm.git_state(r)
        (r / "localflow" / "a.py").write_text("A = 3\n")
        s3 = bm.git_state(r)
        assert s2["dirty_entries"] == s3["dirty_entries"] == [" M localflow/a.py"]
        assert s2["head_commit"] == s3["head_commit"]
        assert s2["dirty_digest"] != s3["dirty_digest"], \
            "different bytes at the same HEAD/status must differ"
    print("ok  dirty digest: same HEAD/status, different bytes -> different digest")


@case
def test_staged_unstaged_untracked_and_symlinks():
    with tempfile.TemporaryDirectory() as td:
        r = make_repo(td)
        # Staged change, worktree restored to HEAD bytes: status 'MM'.
        (r / "localflow" / "a.py").write_text("A = 9\n")
        sh(r, "git", "add", "localflow/a.py")
        (r / "localflow" / "a.py").write_text("A = 1\n")
        staged = bm.git_state(r)
        assert staged["clean_tree"] is False
        entry = staged["dirty_content"][0]
        assert entry["xy"] == "MM" and entry["path"] == "localflow/a.py"
        # Re-stage different content with the same worktree -> digest moves.
        (r / "localflow" / "a.py").write_text("A = 8\n")
        sh(r, "git", "add", "localflow/a.py")
        (r / "localflow" / "a.py").write_text("A = 1\n")
        assert bm.git_state(r)["dirty_digest"] != staged["dirty_digest"]
        sh(r, "git", "reset", "-q", "--", "localflow/a.py")
        assert bm.git_state(r)["clean_tree"] is True
        # Untracked file (inside an untracked dir) is in scope.
        (r / "localflow" / "new").mkdir()
        (r / "localflow" / "new" / "c.py").write_text("C = 1\n")
        u = bm.git_state(r)
        assert "?? localflow/new/c.py" in u["dirty_entries"], u["dirty_entries"]
        # Untracked symlink: identity is its target, never followed.
        outside = pathlib.Path(td) / "outside.txt"
        outside.write_text("one")
        (r / "link").symlink_to(outside)
        s1 = bm.git_state(r)
        outside.write_text("two")  # target content change: not followed
        assert bm.git_state(r)["dirty_digest"] == s1["dirty_digest"]
        (r / "link").unlink()
        (r / "link").symlink_to(pathlib.Path(td) / "elsewhere.txt")
        assert bm.git_state(r)["dirty_digest"] != s1["dirty_digest"]
    print("ok  staged/unstaged/untracked/symlink changes each move the digest")


@case
def test_generated_evidence_is_excluded_from_digest():
    with tempfile.TemporaryDirectory() as td:
        r = make_repo(td)
        out = r / "docs/v2/baseline/runs/x/manifest.json"
        out.parent.mkdir(parents=True)
        out.write_text("{}")
        s = bm.git_state(r)
        assert s["clean_tree"] is True, s["dirty_entries"]
        assert s["excluded_dirty_paths"] == ["docs/v2/baseline/runs/x/manifest.json"]
    print("ok  generated evidence outputs excluded from self-referential hashing")


@case
def test_failing_git_is_unknown_not_clean():
    with tempfile.TemporaryDirectory() as td:
        s = bm.git_state(pathlib.Path(td))  # not a repository
        assert s["clean_tree"] is None and s["dirty_digest"] is None
        assert s["head_commit"] is None and s["head_reason"]
        assert s["dirty_digest_reason"]
    print("ok  failing Git -> null with reason, never clean")


# ---- M01-AUDIT-02: bundle vs HEAD vs worktree ---------------------------------

def make_bundle(td, files):
    app = pathlib.Path(td) / "LocalFlow.app"
    res = app / "Contents" / "Resources"
    (res / "localflow").mkdir(parents=True)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "LocalFlow").write_bytes(b"launcher")
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleIdentifier": "com.example.test",
                       "CFBundleVersion": "1"}, f)
    for rel, text in files.items():
        (res / "localflow" / rel).parent.mkdir(parents=True, exist_ok=True)
        (res / "localflow" / rel).write_text(text)
    (res / "localflow" / "__pycache__").mkdir()
    (res / "localflow" / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"x")
    (res / "config.json").write_text('{"cleanup": "llm"}')
    return app


@case
def test_bundle_compared_against_head_and_worktree_separately():
    with tempfile.TemporaryDirectory() as td:
        r = make_repo(td)
        head = bm.git_state(r)["head_commit"]
        at_head = {"a.py": "A = 1\n", "b.py": "B = 1\n"}
        b = bm.bundle_state(make_bundle(pathlib.Path(td) / "1", at_head), r, head)
        assert b["embedded_code_matches_git_head"] is True
        assert b["embedded_code_matches_worktree"] is True
        assert b["identity"]["CFBundleIdentifier"] == "com.example.test"
        # Dirty worktree; bundle built from it -> matches worktree, NOT HEAD.
        (r / "localflow" / "a.py").write_text("A = 'dirty'\n")
        dirty = {"a.py": "A = 'dirty'\n", "b.py": "B = 1\n"}
        b = bm.bundle_state(make_bundle(pathlib.Path(td) / "2", dirty), r, head)
        assert b["embedded_code_matches_git_head"] is False
        assert b["divergence_from_head"]["differs"] == ["a.py"]
        assert b["embedded_code_matches_worktree"] is True
        # Bundle at HEAD while the worktree is dirty -> the reverse.
        b = bm.bundle_state(make_bundle(pathlib.Path(td) / "3", at_head), r, head)
        assert b["embedded_code_matches_git_head"] is True
        assert b["embedded_code_matches_worktree"] is False
        # An untracked file copied into the bundle diverges from HEAD.
        extra = dict(at_head, **{"untracked.py": "X = 1\n"})
        b = bm.bundle_state(make_bundle(pathlib.Path(td) / "4", extra), r, head)
        assert b["divergence_from_head"]["only_in_bundle"] == ["untracked.py"]
        # Unknown HEAD -> null with reason, never a vacuous match.
        b = bm.bundle_state(make_bundle(pathlib.Path(td) / "5", at_head), r, None)
        assert b["embedded_code_matches_git_head"] is None
        assert b["head_comparison_reason"]
        absent = bm.bundle_state(pathlib.Path(td) / "none.app", r, head)
        assert absent["installed"] is False and absent["reason"]
    print("ok  bundle vs HEAD vs worktree distinguished; unknown HEAD is null")


# ---- M01-AUDIT-03: configuration --------------------------------------------------

@contextlib.contextmanager
def runtime_env(home, repo_root, env_value):
    saved = (os.environ.get("HOME"), os.environ.get("LOCALFLOW_CONFIG"),
             lf_config.ROOT)
    os.environ["HOME"] = str(home)
    if env_value is None:
        os.environ.pop("LOCALFLOW_CONFIG", None)
    else:
        os.environ["LOCALFLOW_CONFIG"] = str(env_value)
    lf_config.ROOT = repo_root
    try:
        yield
    finally:
        for key, val in (("HOME", saved[0]), ("LOCALFLOW_CONFIG", saved[1])):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        lf_config.ROOT = saved[2]


def runtime_load(home, repo_root, env_value, explicit=None):
    with runtime_env(home, repo_root, env_value), \
            contextlib.redirect_stdout(io.StringIO()):
        return lf_config.load(explicit)


def resolve(home, repo_root, env_value, explicit=None):
    return bm.resolve_config(
        explicit, env_value,
        home / "Library" / "Application Support" / "LocalFlow" / "config.json",
        repo_root / "config.json")


@case
def test_config_resolution_mirrors_runtime_load():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        home = td / "home"
        support = home / "Library" / "Application Support" / "LocalFlow"
        support.mkdir(parents=True)
        repo = td / "repo"
        repo.mkdir()
        D = lf_config.DEFAULTS

        def check(name, env_value, expl, want_source, want_cleanup):
            got, _, winner = resolve(home, repo, env_value, expl)
            oracle = runtime_load(home, repo, env_value, expl)
            assert got == oracle, (name, "resolver disagrees with runtime load()")
            assert got["cleanup"] == want_cleanup, (name, got["cleanup"])
            rec, _ = bm.effective_config_record(
                name, explicit=expl, env_value=env_value,
                user_override=support / "config.json",
                bundled=repo / "config.json")
            assert rec["effective_source"] == want_source, (name, rec["effective_source"])
            return rec, winner

        # 1. No candidate files -> DEFAULTS.
        check("no candidates", None, None, "defaults", D["cleanup"])
        # 2. Partial repo config -> DEFAULTS + that key.
        (repo / "config.json").write_text('{"cleanup": "basic"}')
        check("partial repo", None, None, "bundled_or_repo_config", "basic")
        # 3. User override beats repo config.
        (support / "config.json").write_text('{"cleanup": "off"}')
        check("user override", None, None, "application_support_override", "off")
        # 4. Env var pointing at a file beats the override.
        envfile = td / "env.json"
        envfile.write_text('{"cleanup_model": "org/other"}')
        rec, _ = check("env file", envfile, None,
                       "environment_LOCALFLOW_CONFIG", D["cleanup"])
        assert rec["effective_values"]["cleanup_model"] == "org/other"
        assert rec["overridden_keys"] == ["cleanup_model"]
        # 5. Env var pointing at an EXISTING DIRECTORY: runtime stops there
        #    and keeps DEFAULTS (the old generator skipped to the next file).
        envdir = td / "cfgdir"
        envdir.mkdir()
        _, winner = check("env directory", envdir, None, "defaults", D["cleanup"])
        assert winner["outcome"] == "ignored_bad_config_defaults_used"
        assert winner["role"] == "environment_LOCALFLOW_CONFIG"
        # 6. Explicit path beats everything.
        explicit = td / "explicit.json"
        explicit.write_text('{"cleanup": "basic"}')
        check("explicit", envdir, explicit, "explicit_path", "basic")
        # 7. Env var naming an absent file is skipped.
        check("env absent", td / "missing.json", None,
              "application_support_override", "off")
    print("ok  config resolution == runtime load() across 7 precedence scenarios")


@case
def test_config_malformed_unreadable_and_non_object():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        home = td / "home"
        home.mkdir()
        repo = td / "repo"
        repo.mkdir()
        # Malformed JSON: runtime deliberately falls back to DEFAULTS — the
        # record must say so (defaults, with the error), not "unknown".
        (repo / "config.json").write_text("{bad")
        got, _, winner = resolve(home, repo, None)
        assert got == runtime_load(home, repo, None) == lf_config.DEFAULTS
        rec, _ = bm.effective_config_record(
            "m", user_override=home / "none.json", bundled=repo / "config.json")
        assert rec["effective_source"] == "defaults"
        assert rec["winner"]["error"] == "JSONDecodeError"
        assert rec["winner_file"]["parse"].startswith("invalid")
        assert rec["effective_values"]["model"] == lf_config.DEFAULTS["model"]
        # A JSON array: the runtime itself raises; record that honestly.
        (repo / "config.json").write_text("[1, 2]")
        try:
            runtime_load(home, repo, None)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError("precondition: runtime load() raises on a list")
        rec, cfg = bm.effective_config_record(
            "l", user_override=home / "none.json", bundled=repo / "config.json")
        assert cfg is None and rec["winner"]["outcome"] == "runtime_would_raise"
        assert rec["effective_values"] is None and rec["reason"]
        # File identity is recorded without values.
        (repo / "config.json").write_text('{"secret_key": "PRIVATE-CANARY"}')
        rec, _ = bm.effective_config_record(
            "p", user_override=home / "none.json", bundled=repo / "config.json")
        assert "PRIVATE-CANARY" not in json.dumps(rec)
        assert rec["winner_file"]["keys"] == ["secret_key"]
        assert len(rec["winner_file"]["sha256"]) == 64
    print("ok  malformed -> defaults(+error); list -> runtime raises; values private")


@case
def test_installed_app_context_uses_the_bundles_own_defaults():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        r = make_repo(td)
        app = make_bundle(td / "b", {"a.py": "A = 1\n"})
        res = app / "Contents" / "Resources"
        (res / "config.json").write_text('{"hotkey": "right_option"}')
        # An older embedded config.py: different defaults, no
        # cleanup_implementation key at all.
        (res / "localflow" / "config.py").write_text(
            'DEFAULTS = {"model": "org/old-asr", "cleanup": "basic",\n'
            '            "cleanup_model": "org/old-llm", "hotkey": "fn"}\n')
        home = td / "home"
        home.mkdir()
        saved = {k: os.environ.get(k) for k in ("HOME", "PATH")}
        bin_dir = td / "bin"
        bin_dir.mkdir()
        (bin_dir / "launchctl").write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / "launchctl").chmod(0o755)
        os.environ["HOME"] = str(home)
        os.environ["PATH"] = f"{bin_dir}:{saved['PATH']}"
        try:
            m = bm.build(root=r, app=app, env={}, hash_model_files=False)
        finally:
            for k, v in saved.items():
                os.environ[k] = v
        ctx = m["effective_configuration"]["contexts"]["installed_app"]
        assert ctx["defaults_source"] == "installed bundle localflow/config.py"
        assert ctx["effective_values"] == {
            "model": "org/old-asr", "cleanup": "basic",
            "cleanup_model": "org/old-llm", "cleanup_implementation": None,
            "hotkey": "right_option"}, ctx["effective_values"]
        assert ctx["overridden_keys"] == ["hotkey"]
        assert m["models"]["installed_app"]["asr"]["configured_id"] == "org/old-asr"
        repo_ctx = m["effective_configuration"]["contexts"]["repo_run"]
        assert repo_ctx["effective_values"]["cleanup_implementation"] == \
            lf_config.DEFAULTS["cleanup_implementation"]
    print("ok  installed-app context resolves with the bundle's own DEFAULTS")


# ---- M01-AUDIT-04: models and interpreters ------------------------------------

def make_hub(base, model_id, rev="rev1", *, config=True, weights=b"W" * 32,
             tokenizer='{"v": 1}', refs=None):
    d = base / ("models--" + model_id.replace("/", "--"))
    snap = d / "snapshots" / rev
    snap.mkdir(parents=True, exist_ok=True)
    (d / "refs").mkdir(exist_ok=True)
    (d / "refs" / "main").write_text(refs or rev)
    if weights is not None:
        (snap / "model.safetensors").write_bytes(weights)
    if config:
        (snap / "config.json").write_text("{}")
    (snap / "tokenizer.json").write_text(tokenizer)
    return snap


@case
def test_hub_root_follows_runtime_env_rules():
    import localflow.stt as stt
    from localflow.v2 import ids
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        mid = "org/model"
        override = td / "override-hub"
        make_hub(override, mid)
        for env in ({"HF_HUB_CACHE": str(override)},
                    {"HF_HOME": str(td / "hf-home")}):
            if "HF_HOME" in env:
                make_hub(td / "hf-home" / "hub", mid)
            saved = {k: os.environ.get(k) for k in ("HF_HUB_CACHE", "HF_HOME")}
            try:
                for k in saved:
                    os.environ.pop(k, None)
                os.environ.update(env)
                runtime_cached = stt._model_cached(mid)
                runtime_rev = ids.resolve_model_revision(mid)
            finally:
                for k, v in saved.items():
                    os.environ.pop(k, None)
                    if v is not None:
                        os.environ[k] = v
            hub, source = bm.hub_root_for(env)
            obs = bm.model_cache_observation(mid, hub, source)
            assert runtime_cached is True
            assert obs["resolution"]["stt_model_cached"] is runtime_cached
            assert (obs["resolution"]["ids_resolve_model_revision"],
                    obs["resolution"]["ids_resolve_reason"]) == runtime_rev
            assert source == next(iter(env))
    print("ok  HF_HUB_CACHE / HF_HOME overrides resolved like the runtime")


@case
def test_model_identity_covers_tokenizer_config_and_unusable_snapshots():
    with tempfile.TemporaryDirectory() as td:
        hub = pathlib.Path(td) / "hub"
        mid = "org/model"
        snap = make_hub(hub, mid)
        a = bm.model_cache_observation(mid, hub)
        (snap / "tokenizer.json").write_text('{"v": 2}')  # weights unchanged
        b = bm.model_cache_observation(mid, hub)
        sa, sb = a["snapshots"][0], b["snapshots"][0]
        assert sa["files_sha256"]["model.safetensors"] == \
            sb["files_sha256"]["model.safetensors"]
        assert sa["snapshot_digest"] != sb["snapshot_digest"], \
            "tokenizer change must change model identity"
        (snap / "config.json").write_text('{"changed": true}')
        c = bm.model_cache_observation(mid, hub)
        assert c["snapshots"][0]["snapshot_digest"] != sb["snapshot_digest"]
        # refs/main naming a missing snapshot
        (hub / "models--org--model" / "refs" / "main").write_text("gone")
        d = bm.model_cache_observation(mid, hub)
        assert d["resolution"]["refs_main_snapshot_present"] is False
        # unusable snapshot (no config.json) and dangling blob symlink
        hub2 = pathlib.Path(td) / "hub2"
        snap2 = make_hub(hub2, mid, config=False)
        (snap2 / "dangling.bin").symlink_to(pathlib.Path(td) / "missing-blob")
        e = bm.model_cache_observation(mid, hub2)
        assert e["snapshots"][0]["usable_by_stt_rule"] is False
        assert e["resolution"]["stt_model_cached"] is False
        assert e["snapshots"][0]["dangling_files"] == ["dangling.bin"]
        # two snapshots -> ambiguous, like ids.resolve_model_revision
        make_hub(hub, mid, rev="rev2")
        f = bm.model_cache_observation(mid, hub)
        assert f["resolution"]["ids_resolve_reason"] == "ambiguous_snapshot"
        # absent model
        g = bm.model_cache_observation("org/absent", hub)
        assert g["cache_observed"] is False
        assert g["resolution"]["ids_resolve_reason"] == "not_in_cache"
        # models_record never claims a loaded checkpoint
        rec = bm.models_record({"model": mid, "cleanup_model": mid,
                                "cleanup": "llm"}, {"HF_HUB_CACHE": str(hub)})
        for role in ("asr", "cleanup"):
            assert rec[role]["loaded"] is None and rec[role]["loaded_reason"]
    print("ok  model identity: tokenizer/config, refs, unusable, ambiguous, never 'loaded'")


@case
def test_distinct_interpreter_inventories():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        fake = td / "bundle-python"
        fake.write_text("#!/bin/sh\necho '{\"python\": \"3.14.7\", "
                        "\"executable\": \"/b/python\", \"prefix\": \"/b\", "
                        "\"packages\": {\"mlx\": \"0.31.2\"}}'\n")
        fake.chmod(0o755)
        real = bm.interpreter_inventory(pathlib.Path(sys.executable), "repo_venv")
        other = bm.interpreter_inventory(fake, "installed_bundle_venv")
        missing = bm.interpreter_inventory(td / "nope", "x")
        assert real["python"] == sys.version.split()[0]
        assert other["python"] == "3.14.7" and other["packages"] == {"mlx": "0.31.2"}
        assert real["label"] != other["label"] and real["packages"] != other["packages"]
        assert missing["exists"] is False and missing["reason"]
    print("ok  repo and bundle interpreters inventoried independently")


# ---- M01-AUDIT-05: current vs historical ------------------------------------------

def write_events(d, records):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "events-2026-09-24.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


@case
def test_readiness_is_scoped_to_the_latest_session():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td) / "Logs"
        write_events(d, [
            {"event": "app.ready", "session_id": "A",
             "timestamp_utc": "2026-09-20T10:00:00.000Z"},
            {"event": "worker.engine_state", "session_id": "A",
             "model_id": "org/q", "outcome": "ready",
             "timestamp_utc": "2026-09-20T10:00:05.000Z"},
            {"event": "app.ready", "session_id": "B",
             "timestamp_utc": "2026-09-24T09:00:00.000Z"},
            {"event": "worker.engine_state", "session_id": "B",
             "model_id": "org/q", "outcome": "failed",
             "reason_code": "cleanup_engine_failed",
             "timestamp_utc": "2026-09-24T09:00:05.000Z"},
        ])
        r = bm.current_session_readiness(d)
        assert r["session"]["session_id"] == "B"
        assert r["session"]["engine_state_by_model"]["org/q"]["outcome"] == "failed"
        empty = bm.current_session_readiness(pathlib.Path(td) / "none")
        assert empty["session"] is None and empty["reason"]
        log = pathlib.Path(td) / "LocalFlow.log"
        log.write_text(
            "[localflow] ready — hold fn to dictate, release to insert text.\n"
            "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
            "[localflow] ready — hold fn to dictate, release to insert text.\n"
            "[localflow] cleanup model unavailable, using basic cleanup: boom\n")
        seg = bm.legacy_log_last_segment(log)["last_segment"]
        assert seg == {"start_line": 3, "cleanup_state": "unavailable",
                       "cleanup_model": None}
    print("ok  readiness from the latest session only; old success never vouches")


@case
def test_historical_claims_are_not_regenerated_as_current():
    with tempfile.TemporaryDirectory() as td:
        r = make_repo(td)
        home = pathlib.Path(td) / "home"
        home.mkdir()
        saved = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        try:
            m = bm.build(root=r, app=pathlib.Path(td) / "absent.app",
                         env={}, hash_model_files=False)
        finally:
            os.environ["HOME"] = saved
        blob = json.dumps(m)
        # No candidate config file at all no longer crashes the generator.
        ctx = m["effective_configuration"]["contexts"]["repo_run"]
        assert ctx["effective_source"] == "bundled_or_repo_config"
        assert m["schema_version"] == 2 and m["kind"] == "current_run_observation"
        for stale in ('"pairs": 749', "User-stated provenance",
                      "byte-identical copies"):
            assert stale not in blob, stale
        assert m["historical_record"]["observed_utc_date"] == "2026-09-21"
        (r / "config.json").unlink()
        os.environ["HOME"] = str(home)
        try:
            m2 = bm.build(root=r, app=pathlib.Path(td) / "absent.app",
                          env={}, hash_model_files=False)
        finally:
            os.environ["HOME"] = saved
        assert m2["effective_configuration"]["contexts"]["repo_run"][
            "effective_source"] == "defaults"
        assert m2["models"]["repo_run"]["asr"]["configured_id"] == \
            lf_config.DEFAULTS["model"]
        # The frozen historical baseline can never be overwritten.
        target = r / bm.HISTORICAL_MANIFEST
        target.parent.mkdir(parents=True)
        target.write_text('{"frozen": true}')
        try:
            bm.write_manifest(m, target, root=r)
        except SystemExit:
            pass
        else:
            raise AssertionError("historical manifest overwritten")
        assert target.read_text() == '{"frozen": true}'
        out = r / "docs/v2/baseline/runs/x/manifest.json"
        bm.write_manifest(m, out, root=r)
        try:
            bm.write_manifest(m, out, root=r)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing run record replaced")
    print("ok  current run never re-asserts history; historical file frozen")


if __name__ == "__main__":
    for t in TESTS:
        t()
    print(f"all baseline manifest producer tests passed ({len(TESTS)})")
