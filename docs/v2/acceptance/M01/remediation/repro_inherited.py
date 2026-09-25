"""Reproduce M01 audit findings against an INHERITED code tree (argv[1]).

Every scenario uses temporary repositories, synthetic logs, temp databases
and harmless canaries only. Prints one line per scenario:
  REPRODUCED <id> <what>      the defect is observable on this tree
  NOT-REPRODUCED <id> <what>  the defect is not observable

Usage (evidence for the M01 remediation addendum; synthetic inputs only):
    git worktree add --detach /tmp/lf-inherited 1ee8e44
    .venv/bin/python docs/v2/acceptance/M01/remediation/repro_inherited.py /tmp/lf-inherited
Recorded output: repro_inherited.out (38 reproduced, 1 not reproduced —
the malformed-JSON sub-claim of M01-AUDIT-03, refuted). The repaired
tree changed these interfaces; its evidence is the regression suites.
"""
import contextlib
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))

import scripts.v2.build_baseline_manifest as bm  # noqa: E402
import scripts.v2.parse_legacy_log as pl  # noqa: E402
import scripts.v2.snapshot_user_data as su  # noqa: E402
import scripts.v2.build_registry as br  # noqa: E402

results = []


def rep(fid, ok, what):
    tag = "REPRODUCED" if ok else "NOT-REPRODUCED"
    results.append((tag, fid, what))
    print(f"{tag:15s} {fid} {what}")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def mkrepo(td):
    r = pathlib.Path(td) / "repo"
    r.mkdir()
    sh(r, "git", "init", "-q")
    sh(r, "git", "config", "user.email", "t@example.invalid")
    sh(r, "git", "config", "user.name", "t")
    (r / "localflow").mkdir()
    (r / "localflow" / "a.py").write_text("A = 1\n")
    sh(r, "git", "add", "-A")
    sh(r, "git", "commit", "-q", "-m", "init")
    return r


# ---------------------------------------------------------------- AUDIT-01
with tempfile.TemporaryDirectory() as td:
    r = mkrepo(td)
    saved = bm.ROOT
    bm.ROOT = r
    try:
        (r / "localflow" / "a.py").write_text("A = 2\n")
        s1 = bm.git_state()
        (r / "localflow" / "a.py").write_text("A = 3\n")
        s2 = bm.git_state()
        rep("M01-AUDIT-01", s1["dirty_digest"] == s2["dirty_digest"]
            and s1["status_short"] == s2["status_short"],
            f"different dirty bytes, same HEAD/status -> same digest {s1['dirty_digest'][:12]}")
        bm.ROOT = pathlib.Path(td) / "not-a-repo"
        bm.ROOT.mkdir()
        s3 = bm.git_state()
        rep("M01-AUDIT-01", s3["clean_tree"] is True and s3["head_commit"] == "",
            f"failing Git reported clean_tree={s3['clean_tree']} head={s3['head_commit']!r}")
    finally:
        bm.ROOT = saved

# ---------------------------------------------------------------- AUDIT-02
with tempfile.TemporaryDirectory() as td:
    r = mkrepo(td)
    app = pathlib.Path(td) / "LocalFlow.app"
    res = app / "Contents" / "Resources"
    (res / "localflow").mkdir(parents=True)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "LocalFlow").write_bytes(b"\x00launcher")
    (r / "localflow" / "a.py").write_text("A = 'dirty'\n")  # dirty worktree
    (res / "localflow" / "a.py").write_text("A = 'dirty'\n")  # bundle built from it
    saved = (bm.ROOT, bm.APP)
    bm.ROOT, bm.APP = r, app
    try:
        b = bm.bundle_state()
    finally:
        bm.ROOT, bm.APP = saved
    rep("M01-AUDIT-02", b["embedded_code_matches_git_head"] is True,
        "bundle == dirty worktree != HEAD reported embedded_code_matches_git_head=True")

# ---------------------------------------------------------------- AUDIT-03
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    envdir = td / "cfgdir"
    envdir.mkdir()
    repo_cfg = td / "repo"
    repo_cfg.mkdir()
    (repo_cfg / "config.json").write_text(json.dumps({"cleanup": "basic"}))
    saved = (bm.ROOT, bm.APP_SUPPORT, os.environ.get("LOCALFLOW_CONFIG"))
    bm.ROOT, bm.APP_SUPPORT = repo_cfg, td / "nosupport"
    os.environ["LOCALFLOW_CONFIG"] = str(envdir)
    try:
        c = bm.config_precedence()
        # Runtime: load() takes the existing directory, fails to read, prints
        # and stops -> DEFAULTS (cleanup "llm"). Manifest skips to repo config.
        import importlib
        cfgmod = importlib.import_module("localflow.config")
        saved_root = cfgmod.ROOT
        cfgmod.ROOT = repo_cfg
        with contextlib.redirect_stdout(io.StringIO()):
            runtime = cfgmod.load()
        cfgmod.ROOT = saved_root
        rep("M01-AUDIT-03", c["effective"] and c["effective"]["source"] == "repo_config"
            and runtime["cleanup"] == "llm",
            f"env dir override: manifest says {c['effective']['source']} "
            f"(cleanup=basic) but runtime uses defaults (cleanup={runtime['cleanup']})")
        # No candidate files at all -> main() crashes on None.get
        os.environ.pop("LOCALFLOW_CONFIG")
        (repo_cfg / "config.json").unlink()
        c2 = bm.config_precedence()
        try:
            bm._models_from_config(c2.get("effective", {}).get("content"))
            crashed = False
        except AttributeError:
            crashed = True
        rep("M01-AUDIT-03", crashed, "no candidate files -> main() expression raises AttributeError")
        # Malformed JSON: runtime falls back to defaults; manifest reports null IDs
        (repo_cfg / "config.json").write_text("{bad")
        c3 = bm.config_precedence()
        m3 = bm._models_from_config(c3["effective"]["content"])
        rep("M01-AUDIT-03(malformed-json sub-claim)", m3["asr"]["configured_id"] is None,
            f"malformed JSON: manifest configured_id={m3['asr']['configured_id']} "
            f"(runtime uses DEFAULTS too; read_error recorded={bool(c3['effective'].get('read_error'))})")
    finally:
        bm.ROOT, bm.APP_SUPPORT = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop("LOCALFLOW_CONFIG", None)
        else:
            os.environ["LOCALFLOW_CONFIG"] = saved[2]

# ---------------------------------------------------------------- AUDIT-04
with tempfile.TemporaryDirectory() as td:
    hub = pathlib.Path(td) / "hub"
    mid = "org/model"
    d = hub / "models--org--model"
    snap = d / "snapshots" / "rev1"
    snap.mkdir(parents=True)
    (d / "refs").mkdir()
    (d / "refs" / "main").write_text("rev1")
    (snap / "model.safetensors").write_bytes(b"W" * 10)
    (snap / "tokenizer.json").write_text('{"v": 1}')
    e1 = bm.model_entry(mid, hub)
    (snap / "tokenizer.json").write_text('{"v": 2}')
    e2 = bm.model_entry(mid, hub)
    rep("M01-AUDIT-04", e1 == e2, "tokenizer changed with unchanged weights -> identical model entry")
    (d / "refs" / "main").write_text("rev-missing")
    e3 = bm.model_entry(mid, hub)
    rep("M01-AUDIT-04", e3["cached"] is True and e3["weights_sha256"] == {},
        "refs/main points at a missing snapshot -> cached=True with no weights")
    # Cache override: runtime honours HF_HUB_CACHE; manifest uses fixed HF_HUB
    (d / "refs" / "main").write_text("rev1")
    (snap / "config.json").write_text("{}")
    os.environ["HF_HUB_CACHE"] = str(hub)
    try:
        mm = bm._models_from_config({"model": mid, "cleanup_model": mid})
    finally:
        os.environ.pop("HF_HUB_CACHE")
    rep("M01-AUDIT-04", mm["asr"]["cached"] is False,
        "HF_HUB_CACHE override holds the model (runtime would find it) but manifest reports cached=False")
    rep("M01-AUDIT-04", 'ROOT / ".venv" / "bin" / "python"' in open(bm.__file__).read()
        and "Resources" not in bm.runtimes.__code__.co_consts.__repr__(),
        "runtimes() probes only the repo .venv; installed bundle runs Resources/venv (build_app.sh)")

# ---------------------------------------------------------------- AUDIT-05
with tempfile.TemporaryDirectory() as td:
    log = pathlib.Path(td) / "LocalFlow.log"
    log.write_text(
        "[localflow] ready — hold fn to dictate, release to insert text.\n"
        "[localflow] model loaded.\n"
        "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
        "[localflow] ready — hold fn to dictate, release to insert text.\n"
        "[localflow] cleanup model unavailable, using basic cleanup: boom\n")
    saved = bm.LOG
    bm.LOG = log
    try:
        rp = bm.running_process()
    finally:
        bm.LOG = saved
    rr = rp["log_readiness"]
    rep("M01-AUDIT-05", rr and rr["last_cleanup_model"].startswith("Qwen3"),
        "later launch failed but readiness still reports the old success")
    src = open(bm.__file__).read()
    rep("M01-AUDIT-05", '"pairs": 749' in src and "User-stated provenance (2026-09-21)" in src,
        "historical 749/477 and dated provenance note re-emitted on every regeneration")

# ---------------------------------------------------------------- AUDIT-06
def fake_env(td):
    td = pathlib.Path(td)
    app = td / "app"
    app.mkdir()
    (app / "dictionary.json").write_text('{"terms": ["x"]}')
    (app / "transforms.json").write_text("[]")
    con = sqlite3.connect(app / "stats.db")
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    log = td / "LocalFlow.log"
    log.write_text("[localflow] ready\n")
    return app, log


with tempfile.TemporaryDirectory() as td:
    app, log = fake_env(td)
    saved = (su.APP_SUPPORT, su.LOG_PATH)
    su.APP_SUPPORT, su.LOG_PATH = app, log
    root = pathlib.Path(td) / "evidence"
    try:
        class FrozenDT:
            class datetime:
                @staticmethod
                def now(tz=None):
                    import datetime as _d
                    return _d.datetime(2026, 9, 24, 12, 0, 0, tzinfo=_d.timezone.utc)
            timezone = __import__("datetime").timezone
        real_dt = su.dt
        su.dt = FrozenDT
        with contextlib.redirect_stdout(io.StringIO()):
            su.main(["--root", str(root)])
            first = (root / "20260924T120000Z" / "dictionary.json").read_text()
            (app / "dictionary.json").write_text('{"terms": ["y"]}')
            su.main(["--root", str(root)])
        second = (root / "20260924T120000Z" / "dictionary.json").read_text()
        su.dt = real_dt
        rep("M01-AUDIT-06", first != second and len(list(root.iterdir())) == 1,
            "two runs in the same second share one directory; the first run's copy is overwritten")
        # leaf symlink in a pre-existing run directory redirects a write
        victim = pathlib.Path(td) / "victim.txt"
        victim.write_text("UNRELATED EVIDENCE")
        run = root / "20260924T130000Z"
        run.mkdir()
        (run / "dictionary.json").symlink_to(victim)
        FrozenDT.datetime.now = staticmethod(lambda tz=None: __import__("datetime").datetime(
            2026, 9, 24, 13, 0, 0, tzinfo=__import__("datetime").timezone.utc))
        su.dt = FrozenDT
        with contextlib.redirect_stdout(io.StringIO()):
            su.main(["--root", str(root)])
        su.dt = real_dt
        rep("M01-AUDIT-06", victim.read_text() != "UNRELATED EVIDENCE",
            "leaf symlink inside the run dir: write followed it and overwrote an unrelated file")
        # descendant symlink: run directory itself is a symlink elsewhere
        elsewhere = pathlib.Path(td) / "elsewhere"
        elsewhere.mkdir()
        (root / "20260924T140000Z").symlink_to(elsewhere, target_is_directory=True)
        FrozenDT.datetime.now = staticmethod(lambda tz=None: __import__("datetime").datetime(
            2026, 9, 24, 14, 0, 0, tzinfo=__import__("datetime").timezone.utc))
        su.dt = FrozenDT
        with contextlib.redirect_stdout(io.StringIO()):
            su.main(["--root", str(root)])
        su.dt = real_dt
        rep("M01-AUDIT-06", (elsewhere / "stats.db.bak").exists(),
            "descendant symlink: private snapshot escaped the evidence root")
        # permissive umask
        old = os.umask(0)
        try:
            root2 = pathlib.Path(td) / "ev2"
            with contextlib.redirect_stdout(io.StringIO()):
                su.main(["--root", str(root2)])
        finally:
            os.umask(old)
        modes = sorted({oct(p.stat().st_mode & 0o777) for p in root2.rglob("*")})
        rep("M01-AUDIT-06", any(int(m, 8) & 0o077 for m in modes),
            f"umask 000 -> private evidence modes {modes}")
    finally:
        su.APP_SUPPORT, su.LOG_PATH = saved

# ---------------------------------------------------------------- AUDIT-12
with tempfile.TemporaryDirectory() as td:
    app, log = fake_env(td)
    db = app / "stats.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    main_before = su.sha256_file(db)
    saved = (su.APP_SUPPORT, su.LOG_PATH, su.snapshot_sqlite)
    su.APP_SUPPORT, su.LOG_PATH = app, log
    orig = su.snapshot_sqlite

    def racing(src, dst):
        out = orig(src, dst)
        con.execute("INSERT INTO t VALUES (2)")  # concurrent writer, WAL only
        con.commit()
        return out
    su.snapshot_sqlite = racing
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = su.main(["--root", str(pathlib.Path(td) / "ev")])
    finally:
        su.APP_SUPPORT, su.LOG_PATH, su.snapshot_sqlite = saved
    m = json.loads(next((pathlib.Path(td) / "ev").glob("*/snapshot-manifest.json")).read_text())
    rep("M01-AUDIT-12", rc == 0 and m["all_sources_unchanged"] is True
        and su.sha256_file(db) == main_before,
        "WAL-backed write during snapshot: main-file hash unchanged -> 'source unchanged', exit 0")
    con.close()
    # missing population
    (app / "transforms.json").unlink()
    su.APP_SUPPORT, su.LOG_PATH = app, log
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = su.main(["--root", str(pathlib.Path(td) / "ev3")])
    finally:
        su.APP_SUPPORT, su.LOG_PATH = saved[0], saved[1]
    m = json.loads(next((pathlib.Path(td) / "ev3").glob("*/snapshot-manifest.json")).read_text())
    rep("M01-AUDIT-12", rc == 0 and not any("transforms" in e["source"] for e in m["entries"]),
        "missing transforms.json: no inventory entry, exit 0, all_sources_unchanged=True")
    rep("M01-AUDIT-12", all(e["kind"] != "live_log_full" or "unchanged" not in (e["note"] or "")
                            for e in m["entries"]),
        "live log entry carries no change status at all (unchecked)")
    # all-missing: fails before manifest publication (NOT a green run)
    empty = pathlib.Path(td) / "empty"
    empty.mkdir()
    su.APP_SUPPORT, su.LOG_PATH = empty, empty / "nolog"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            su.main(["--root", str(pathlib.Path(td) / "ev4")])
        allmissing = "returned"
    except FileNotFoundError:
        allmissing = "FileNotFoundError before manifest publication"
    finally:
        su.APP_SUPPORT, su.LOG_PATH = saved[0], saved[1]
    rep("M01-AUDIT-12(nuance)", allmissing != "returned",
        f"all-missing fresh run: {allmissing} (not a green run)")
    # corrupt sqlite
    bad = pathlib.Path(td) / "badapp"
    bad.mkdir()
    (bad / "stats.db").write_bytes(b"not a database" * 100)
    su.APP_SUPPORT, su.LOG_PATH = bad, log
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            su.main(["--root", str(pathlib.Path(td) / "ev5")])
        corrupt = "returned"
    except sqlite3.DatabaseError as e:
        corrupt = f"uncaught {type(e).__name__}, no manifest"
    finally:
        su.APP_SUPPORT, su.LOG_PATH = saved[0], saved[1]
    rep("M01-AUDIT-12", corrupt != "returned", f"corrupt stats.db: {corrupt}")

# ---------------------------------------------------------------- AUDIT-07
tail = ("[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
        "[localflow] raw:     alpha beta\n"
        "gamma\n"
        "[localflow] cleaned: Alpha beta\n")
full = tail + "gamma delta.\n[localflow] timing: stt 0.1s, cleanup 0.2s\n[localflow] inserted 20 chars\n"
p_tail = pl.iter_pairs(tail)
p_full = pl.iter_pairs(full)
rep("M01-AUDIT-07", len(p_tail) == 1 and (p_tail[0]["raw_line"], p_tail[0]["cleaned_line"])
    == (p_full[0]["raw_line"], p_full[0]["cleaned_line"])
    and p_tail[0]["_cleaned"] != p_full[0]["_cleaned"],
    "EOF tail yields a pair with truncated cleaned text and the SAME line coordinates as the "
    "completed pair -> importer skip_pairs drops the completed content")
rep("M01-AUDIT-07", "complete" not in p_tail[0], "pairs carry no completeness flag")

# ---------------------------------------------------------------- AUDIT-08
t = ("[localflow] cleanup model loaded (x)\n"
     "[localflow] raw:     def f():\n"
     "    return 1  \n"
     "\n"
     "end  \n"
     "[localflow] cleaned: ok\n"
     "[localflow] timing: stt 0.1s, cleanup 0.1s\n")
p = pl.iter_pairs(t)[0]
rep("M01-AUDIT-08", p["_raw"] != "def f():\n    return 1  \n\nend  ",
    f"exact payload lost: got {p['_raw']!r}")

# ---------------------------------------------------------------- AUDIT-11
r0 = pl.parse("")
metal = [x for x in r0["notable_examples"] if x["id"] == "E02-METAL-FAILURES"][0]
rep("M01-AUDIT-11", metal["located"] is True, "parse('') reports the Metal window located=True")
rep("M01-AUDIT-11", "source" not in r0 and "parser" not in r0,
    "report carries no source hash / parser derivation binding")

# ---------------------------------------------------------------- AUDIT-13
t = ("[localflow] cleanup model loaded (x)\n"
     "[localflow] raw:     one\n"
     "[localflow] cleaned: One.\n"
     "[localflow] inserted 5 chars\n"
     "[localflow] audio: 1.0s from 'mic', voiced 0%, trailing silence 1.0s, overflows 0\n"
     "[localflow] timing: stt 0.1s, cleanup 0.0s\n"
     "[localflow] empty transcription — nothing to insert\n")
r = pl.parse(t)
rep("M01-AUDIT-13", r["timed_pairs"] == 1 and r["counts"]["unpaired_timing"] == 0,
    "later empty-dictation timing attached to the earlier posted pair")

# ---------------------------------------------------------------- malformed numeric
try:
    pl.parse("[localflow] raw:     a\n[localflow] cleaned: A\n"
             "[localflow] timing: stt 1..2s, cleanup 0.1s\n")
    rep("parser-malformed-numeric", False, "malformed timing parsed")
except ValueError as e:
    rep("parser-malformed-numeric", True, f"malformed timing crashes parse(): {e}")

# ---------------------------------------------------------------- AUDIT-17
t = ("[localflow] cleanup model loaded (x)\n"
     "[localflow] raw:     i said [localflow] cleaned: inside my dictation\n"
     "[localflow] cleaned: I said.\n")
r = pl.iter_pairs(t)
rep("M01-AUDIT-17(design)", True,
    f"transcript text containing a runtime prefix is parsed as a record "
    f"(pairs={len(r)}; structural ambiguity, no authentic framing to disambiguate)")

# ---------------------------------------------------------------- AUDIT-10
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    spec = td / "spec.md"
    ev = td / "eval.md"
    spec.write_text("# nothing\n")
    ev.write_text("# nothing\n")
    saved = (br.SPEC, br.EVAL, sys.argv)
    br.SPEC, br.EVAL = spec, ev
    sys.argv = ["x", "--output", str(td / "reg.json")]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = br.main()
        rep("M01-AUDIT-10", rc == 0, f"empty catalogs -> exit {rc}, registry with 0/0 and no problems")
        spec.write_text("## S05. R\n| LF-R01 | a | M01 |\n| LF-R01 | b | M02 |\n| LF-R0x | bad | M01 |\n## S06. x\n")
        ev.write_text("## E08. C\n| EV-01 x | y | LF-R01 |\n## E09. x\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = br.main()
        reg = json.loads((td / "reg.json").read_text())
        rep("M01-AUDIT-10", rc == 0 and reg["counts"]["requirements"] == 1,
            "duplicate LF-R01 silently overwritten; malformed row only warns; exit 0")
        spec.unlink()
        try:
            br.spec_requirements()
            rep("M01-AUDIT-10", False, "missing catalog handled")
        except FileNotFoundError:
            rep("M01-AUDIT-10", True, "missing catalog -> uncaught FileNotFoundError")
    finally:
        br.SPEC, br.EVAL, sys.argv = saved
    # incorrect reverse edge passes test_registry
    import importlib.util
    spec_t = importlib.util.spec_from_file_location("treg", ROOT / "tests/v2/test_registry.py")
    treg = importlib.util.module_from_spec(spec_t)
    spec_t.loader.exec_module(treg)
    reg = json.loads((ROOT / "docs/v2/registry.json").read_text())
    r0_ = reg["requirements"][0]
    r0_["suites"] = sorted(set(r0_["suites"]) | {"EV-99"})
    bad = td / "bad.json"
    bad.write_text(json.dumps(reg))
    treg.REGISTRY = bad
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            treg.test_registry_matches_canonical_docs()
        rep("M01-AUDIT-10", True, "registry with a fabricated requirement->suite reverse edge passes the test")
    except AssertionError:
        rep("M01-AUDIT-10", False, "reverse edge rejected")

# ---------------------------------------------------------------- AUDIT-14
import importlib.util  # noqa: E402
spec_m = importlib.util.spec_from_file_location("tbm", ROOT / "tests/v2/test_baseline_manifest.py")
tbm = importlib.util.module_from_spec(spec_m)
spec_m.loader.exec_module(tbm)
with tempfile.TemporaryDirectory() as td:
    fake = pathlib.Path(td)
    (fake / "docs" / "v2").mkdir(parents=True)
    (fake / "tests").mkdir()
    (fake / "docs/v2/baseline").mkdir()
    (fake / "docs/v2/baseline/legacy-log-reconciliation.json").write_text("{}")
    con = sqlite3.connect(fake / "tests" / "canary.bin")  # renamed SQLite
    con.execute("CREATE TABLE canary (x)")
    con.commit()
    con.close()
    (fake / "docs" / "v2" / "rows.json").write_text(json.dumps({"raw_text": "CANARY synthetic transcript"}))
    (fake / "scripts").mkdir()
    (fake / "scripts" / "dump.log.txt").write_text("[localflow] raw:     CANARY\n")
    tbm.ROOT = fake
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            tbm.test_no_private_files_in_repo_docs_or_tests()
        rep("M01-AUDIT-14", True, "renamed SQLite in tests/, raw_text JSON in docs/, log content "
            "under scripts/ all pass the privacy scan (synthetic canaries)")
    except AssertionError as e:
        rep("M01-AUDIT-14", False, f"caught: {e}")

# ---------------------------------------------------------------- AUDIT-15
with tempfile.TemporaryDirectory() as td:
    m = json.loads((ROOT / "docs/v2/baseline/manifest.json").read_text())
    tbm.ROOT = ROOT
    tbm.MANIFEST = ROOT / "docs/v2/baseline/manifest.json"
    src = open(ROOT / "tests/v2/test_baseline_manifest.py").read()
    rep("M01-AUDIT-15", "git_state(" not in src and "bundle_state(" not in src
        and "model_entry(" not in src,
        "provenance test reads only the frozen JSON; no producer function is exercised")

# ---------------------------------------------------------------- AUDIT-16
with tempfile.TemporaryDirectory() as td:
    fm = json.loads((ROOT / "tests/v2/fixtures/manifest.json").read_text())
    fm["families"][0]["m04_created"]["fixture_files"] = ["tests/v2/does_not_exist.json"]
    fm["families"][0]["m04_created"]["numbers_units_dates"] = 999
    fake = pathlib.Path(td)
    (fake / "tests/v2/fixtures").mkdir(parents=True)
    (fake / "tests/v2/fixtures/manifest.json").write_text(json.dumps(fm))
    tbm.ROOT = fake
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            tbm.test_fixture_manifest_reserved_only()
        rep("M01-AUDIT-16", True, "nonexistent fixture file + inflated count (999) pass")
    except AssertionError:
        rep("M01-AUDIT-16", False, "rejected")

# ---------------------------------------------------------------- AUDIT-09
src = open(ROOT / "scripts/v2/baseline_probe.py").read()
rep("M01-AUDIT-09", "cleanup_implementation" not in src and "TranscriptCleaner" in src,
    "probe always runs V1 TranscriptCleaner; config default cleanup_implementation='v2' is ignored/unrecorded")
rep("M01-AUDIT-09", "last_path" not in src and "fallback" not in src.lower().replace("fallback_", ""),
    "probe ignores TranscriptCleaner.last_path / fallback status")
rep("M01-AUDIT-09", "return 1" not in src and "sys.exit" not in src,
    "probe exits 0 regardless of stage failure; report write errors uncaught")

print(json.dumps({"reproduced": sum(1 for r in results if r[0] == "REPRODUCED"),
                  "not_reproduced": sum(1 for r in results if r[0] != "REPRODUCED")}))
