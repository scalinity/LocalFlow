"""M14 corpus drivers, group f: offline validation, readiness and
profile eligibility.

Binds the frozen corpus entries
- cases LF-M14-C159 … C166 (offline_validation), C167 … C175
  (readiness) and C176 … C183 (profile_eligibility);
- stateful probes LF-M14-S022 (offline validator without DB) and
  LF-M14-S028 (readiness/export parity);
- metamorphic relation LF-M14-MR014 (pack relocation).

Offline validation runs the declared validator runtime
(``scripts/v2/validate_dataset.py``) as a subprocess from a different
working directory, after the store is closed and its database file
renamed away and the export moved to another temporary root. An audited
wrapper (a PEP 578 audit hook installed before the script runs) records
every file the validator opens under a forbidden root, every sqlite3
event and every socket event (socket events are refused — the network
is denied). Consistent tampers recompute every checksum and the content
fingerprint with this module's own writer (the manifest's documented
formula: sha256 of the sorted-key JSON of the sorted semantic records),
and each first proves that an unchanged rewrite still validates.

Readiness compares ``TrainingDataService.readiness()`` task counts with
the membership of an export over the same assignment and with literal
counts the fixture established. Profile eligibility counts words by
whitespace split and deduplicates by this module's own normalization of
the declared policy (lower-cased word sequence), never by calling the
profile service's helpers.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
from m14_drivers_common import check, drives, invalid  # noqa: E402
from m14_world import (A_CANARY, B_CANARY, Latch, MWorld,  # noqa: E402
                       after_each_op, patched, read_jsonl, sha256_file)

from localflow.v2.curation import export as export_mod  # noqa: E402

ROOT = W.ROOT
VALIDATOR = ROOT / "scripts" / "v2" / "validate_dataset.py"
ALL_VIEWS = ("asr_supervised", "asr_span_graft_weak", "cleanup_supervised",
             "transform_supervised", "preference_pairs")
KINDS = ("asr_supervised", "cleanup_supervised", "transform_supervised",
         "preference_pairs")
DECISION = "m14-policy-r1"


# =============================================================================
# shared helpers (independent side)
# =============================================================================


def _export(w, dest, views, **kw):
    try:
        return w.export(dest, views, **kw), None
    except export_mod.ExportError as e:
        return None, str(e)


def _records(root):
    root = pathlib.Path(root)
    return (read_jsonl(root / "examples.jsonl"),
            read_jsonl(root / "references.jsonl"),
            read_jsonl(root / "preferences.jsonl"))


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_text(t: str) -> str:
    return _sha_bytes(t.encode("utf-8"))


def _fingerprint(examples, references, preferences) -> str:
    """The manifest's documented content fingerprint, recomputed here."""
    semantic = {n: sorted(r, key=lambda e: json.dumps(e, sort_keys=True))
                for n, r in (("examples", examples),
                             ("references", references),
                             ("preferences", preferences))}
    return _sha_text(json.dumps(semantic, ensure_ascii=False,
                                sort_keys=True))


def _write_sums(root):
    root = pathlib.Path(root)
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() \
                and p.name != "SHA256SUMS.txt":
            lines.append(f"{sha256_file(p)}  {p.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")


def _rewrite(root, *, examples=None, references=None, preferences=None,
             manifest=None, extra_sums=()):
    """Rewrite record files and recompute the fingerprint and every
    checksum consistently (``manifest(m)`` mutates the manifest)."""
    root = pathlib.Path(root)
    for name, rows in (("examples.jsonl", examples),
                       ("references.jsonl", references),
                       ("preferences.jsonl", preferences)):
        if rows is not None:
            (root / name).write_text("".join(
                json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                for r in rows), encoding="utf-8")
    ex, refs, prefs = _records(root)
    m = json.loads((root / "dataset_manifest.json").read_text())
    m["content_fingerprint"] = _fingerprint(ex, refs, prefs)
    if manifest is not None:
        manifest(m)
    (root / "dataset_manifest.json").write_text(json.dumps(
        m, ensure_ascii=False, indent=1, sort_keys=True))
    _write_sums(root)
    if extra_sums:
        with open(root / "SHA256SUMS.txt", "a", encoding="utf-8") as f:
            for line in extra_sums:
                f.write(line + "\n")


def _variant(base, parent, name):
    dst = pathlib.Path(parent) / name
    shutil.copytree(base, dst, symlinks=True)
    return dst


def _validate_inproc(root):
    try:
        return export_mod.validate_dataset(root)
    except Exception as e:  # noqa: BLE001 — an uncontrolled crash
        return {"valid": None, "crash": type(e).__name__, "issues": []}


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env.update(extra)
    return env


def _run_validator_plain(target, cwd, script=VALIDATOR):
    """The declared validator runtime, exactly as documented."""
    p = subprocess.run([sys.executable, str(script), str(target)],
                       cwd=str(cwd), capture_output=True, text=True,
                       env=_clean_env(), timeout=180)
    return {"code": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "valid_line": (p.stdout.splitlines() or [""])[0]}


_AUDIT_WRAPPER = r'''
import contextlib, io, json, os, runpy, sys, traceback
def _real(p):
    try:
        return os.path.realpath(os.fsdecode(p))
    except Exception:
        return None
FORBID = [_real(p) for p in json.loads(os.environ.get("M14F_FORBID", "[]"))]
ALLOW = [_real(p) for p in json.loads(os.environ.get("M14F_ALLOW", "[]"))]
HITS, NET, DB = [], [], []
def _under(p, roots):
    return any(r and (p == r or p.startswith(r + os.sep)) for r in roots)
def _hook(name, args):
    if name == "open":
        if not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        p = _real(args[0])
        if p and _under(p, FORBID) and not _under(p, ALLOW):
            HITS.append(p)
    elif name.startswith("socket."):
        NET.append(name)
        raise PermissionError("network denied (m14 driver f)")
    elif name.startswith("sqlite3."):
        DB.append(name)
sys.addaudithook(_hook)
script = sys.argv[1]
out = []
for target in sys.argv[2:]:
    del HITS[:], NET[:], DB[:]
    sys.argv = [script, target]
    rec = {"target": os.path.basename(target)}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            runpy.run_path(script, run_name="__main__")
        rec["code"] = 0
    except SystemExit as e:
        rec["code"] = e.code if isinstance(e.code, int) else (
            0 if e.code is None else 1)
    except BaseException as e:
        rec["code"] = None
        rec["crash"] = type(e).__name__
        rec["trace"] = traceback.format_exc()[-600:]
    rec["stdout"] = buf.getvalue()
    rec["forbidden_opens"] = list(HITS)
    rec["network"] = list(NET)
    rec["sqlite"] = list(DB)
    out.append(rec)
probe = os.environ.get("M14F_PROBE")
probe_seen = None
if probe:
    del HITS[:]
    open(probe, "rb").close()
    probe_seen = bool(HITS)
lf = sys.modules.get("localflow")
print("\nM14F_AUDIT " + json.dumps({
    "runs": out, "probe_seen": probe_seen,
    "localflow_file": getattr(lf, "__file__", None),
    "localflow_modules": sorted(m for m in sys.modules
                                if m.startswith("localflow")),
    "numpy_loaded": "numpy" in sys.modules}))
'''


def _run_validator_audited(targets, cwd, *, forbid, allow=(), probe=None,
                           script=VALIDATOR):
    env = _clean_env(M14F_FORBID=json.dumps([str(p) for p in forbid]),
                     M14F_ALLOW=json.dumps([str(p) for p in allow]))
    if probe:
        env["M14F_PROBE"] = str(probe)
    p = subprocess.run([sys.executable, "-c", _AUDIT_WRAPPER, str(script),
                        *[str(t) for t in targets]], cwd=str(cwd),
                       capture_output=True, text=True, env=env, timeout=300)
    marker = [ln for ln in p.stdout.splitlines()
              if ln.startswith("M14F_AUDIT ")]
    if not marker:
        return {"error": f"wrapper rc={p.returncode}",
                "stderr": p.stderr[-800:]}
    return json.loads(marker[-1][len("M14F_AUDIT "):])


def _hide_db(w):
    """Close the store and rename its database files away."""
    w.store.close()
    hidden = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = w.tmp / f"v2.db{suffix}"
        if p.exists():
            q = w.tmp / f"hidden-{p.name}.gone"
            os.rename(p, q)
            hidden.append(p.name)
    return hidden


# ---- the common export fixture ----------------------------------------------


def _seed_all(w, *, n_asr=10, pair_family=False):
    fx = {"asr": [w.ready_asr() for _ in range(n_asr)]}
    if pair_family:
        fam = "fam-synth-f-pair-0"
        fx["pair"] = [w.ready_asr(f"pair witness {k} shared family",
                                  family=fam) for k in range(2)]
    fx["clean_full"] = w.ready_cleanup(f"cleanup full words {A_CANARY}")
    fx["clean_bare"] = w.ready_cleanup("cleanup bare words", prompts=0)
    t = w.transform_task(f"transform source {A_CANARY}",
                         [f"Transform A {A_CANARY}.",
                          f"Transform B {B_CANARY}."])
    w.accept(t, t["candidates"][0]["candidate_id"])
    p = w.transform_task(f"pref source {B_CANARY}",
                         ["Pref output one.", "Pref output two."])
    w.judge(p, p["candidates"][0]["candidate_id"],
            p["candidates"][1]["candidate_id"], "prefer_b")
    fx["transform"], fx["pref"] = t, p
    return fx


def _facts(w, fx):
    """What the fixture put in, read from files/rows by this driver."""
    asr = {}
    for j in fx["asr"] + fx.get("pair", []):
        row = w.artifact_row(j["audio_aid"])
        asr[j["example_id"]] = {
            "audio_sha": sha256_file(w.store.artifacts_dir / row[4]),
            "verbatim": j["raw"]}
    cleanup = {j["example_id"]: (j["raw"], j["applied"], tier)
               for j, tier in ((fx["clean_full"], "model_task_complete"),
                               (fx["clean_bare"], "text_pair_only"))}
    t, p = fx["transform"], fx["pref"]
    c0 = t["candidates"][0]
    transform = {(t["task_key"], c0["candidate_id"]): (t["source"],
                                                        c0["text"])}
    pref = {p["task_key"]: (p["source"], "b",
                            [c["text"] for c in p["candidates"]])}
    return {"asr": asr, "cleanup": cleanup, "transform": transform,
            "pref": pref}


def _reconstruct(root, facts):
    """Rebuild every qualified input/output from the package alone and
    compare with what the fixture put in. Returns mismatch names."""
    root = pathlib.Path(root)
    ex, refs, prefs = _records(root)
    bad = []
    ref_by = {(r.get("example_id"), r.get("task_kind")): r for r in refs}
    asr = {e["example_id"]: e for e in ex
           if e.get("task_kind") == "asr_supervised"}
    if set(asr) != set(facts["asr"]):
        bad.append("asr membership")
    for ex_id, f in facts["asr"].items():
        e = asr.get(ex_id)
        if e is None:
            continue
        audio = root / e["audio"]
        if not audio.is_file() or _sha_bytes(audio.read_bytes()) \
                != f["audio_sha"]:
            bad.append(f"asr audio {ex_id}")
        r = ref_by.get((ex_id, "asr_supervised")) or {}
        if r.get("text") != f["verbatim"]:
            bad.append(f"asr reference {ex_id}")
    cl = {e["example_id"]: (e.get("input_text"), e.get("output_text"),
                            e.get("qualification_tier"))
          for e in ex if e.get("task_kind") == "cleanup_supervised"}
    if cl != facts["cleanup"]:
        bad.append("cleanup records")
    tf = {(e.get("task_key"), e.get("candidate_id")):
          (e.get("input_text"), e.get("output_text"))
          for e in ex if e.get("task_kind") == "transform_supervised"}
    if tf != facts["transform"]:
        bad.append("transform records")
    pf = {p.get("task_key"): (p.get("input_text"), p.get("chosen"),
                              [c.get("output_text") for c in
                               p.get("candidates") or []])
          for p in prefs}
    if pf != facts["pref"]:
        bad.append("preference records")
    return bad


def _recount(root):
    ex, _refs, prefs = _records(root)
    out = {k: sum(1 for e in ex if e.get("task_kind") == k)
           for k in ("asr_supervised", "asr_span_graft_weak",
                     "cleanup_supervised", "transform_supervised")}
    out["preference_pairs"] = len(prefs)
    return out


def _built_world_with_export(pair_family=False):
    w = MWorld()
    fx = _seed_all(w, pair_family=pair_family)
    w.splits.assign()
    out, err = _export(w, "ds", ALL_VIEWS)
    return w, fx, out, err


# =============================================================================
# offline validation
# =============================================================================


@drives("LF-M14-C159")
def c159_positive_offline(entry):
    w, fx, out, err = _built_world_with_export()
    away = tempfile.TemporaryDirectory(prefix="m14f-away-")
    elsewhere = tempfile.TemporaryDirectory(prefix="m14f-cwd-")
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        facts = _facts(w, fx)
        hidden = _hide_db(w)
        moved = pathlib.Path(away.name) / "relocated" / "pack"
        moved.parent.mkdir(parents=True)
        shutil.move(str(w.tmp / "ds"), str(moved))
        plain = _run_validator_plain(moved, elsewhere.name)
        aud = _run_validator_audited([moved], elsewhere.name,
                                     forbid=[w.tmp],
                                     probe=w.tmp / hidden_probe(w))
        if "error" in aud:
            return invalid("audit wrapper failed", aud)
        run = aud["runs"][0]
        bad = _reconstruct(moved, facts)
        counts = _recount(moved)
        obs = {"plain_rc": plain["code"], "plain": plain["valid_line"],
               "audited_rc": run["code"], "db_hidden": hidden,
               "forbidden_opens": len(run["forbidden_opens"]),
               "sqlite": run["sqlite"], "network": run["network"],
               "probe_seen": aud["probe_seen"], "recount": counts,
               "reconstruct_mismatch": bad}
        if not aud["probe_seen"]:
            return invalid("audit oracle did not see a deliberate"
                           " forbidden open", obs)
        return check({
            "validator_valid": plain["code"] == 0
            and plain["valid_line"] == "valid: True",
            "audited_valid": run["code"] == 0,
            "no_store_reads": not run["forbidden_opens"],
            "no_sqlite": not run["sqlite"],
            "no_network": not run["network"],
            "reconstructs": not bad,
            "counts_literal": counts == {
                "asr_supervised": 10, "asr_span_graft_weak": 0,
                "cleanup_supervised": 2, "transform_supervised": 1,
                "preference_pairs": 1},
        }, obs, witness="store closed, v2.db renamed, export moved to"
                        " another temp root; validate_dataset.py run as a"
                        " subprocess from another cwd under an audit hook"
                        " (sqlite/socket/open) with a live-probe control")
    finally:
        w.close()
        away.cleanup()
        elsewhere.cleanup()


def hidden_probe(w):
    """A file inside the forbidden store root the audit oracle must
    see when the wrapper opens it deliberately."""
    p = w.tmp / "m14f-probe.bin"
    p.write_bytes(b"probe")
    return p.name


@drives("LF-M14-C160")
def c160_no_repo_source(entry):
    w, fx, out, err = _built_world_with_export()
    away = tempfile.TemporaryDirectory(prefix="m14f-away-")
    dist = tempfile.TemporaryDirectory(prefix="m14f-dist-")
    bare = tempfile.TemporaryDirectory(prefix="m14f-bare-")
    elsewhere = tempfile.TemporaryDirectory(prefix="m14f-cwd-")
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        facts = _facts(w, fx)
        _hide_db(w)
        pack = pathlib.Path(away.name) / "pack"
        shutil.move(str(w.tmp / "ds"), str(pack))
        # The declared runtime without the checkout: only the localflow
        # package and the script, laid out as the script expects.
        d = pathlib.Path(dist.name)
        shutil.copytree(ROOT / "localflow", d / "localflow",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (d / "scripts" / "v2").mkdir(parents=True)
        shutil.copy2(VALIDATOR, d / "scripts" / "v2" / VALIDATOR.name)
        dist_script = d / "scripts" / "v2" / VALIDATOR.name
        probe = w.tmp / hidden_probe(w)
        aud = _run_validator_audited(
            [pack], elsewhere.name, forbid=[w.tmp, ROOT],
            allow=[ROOT / ".venv"], probe=probe, script=dist_script)
        if "error" in aud:
            return invalid("audit wrapper failed", aud)
        run = aud["runs"][0]
        # The script with no runtime at all: must say what is missing.
        b = pathlib.Path(bare.name)
        (b / "scripts" / "v2").mkdir(parents=True)
        shutil.copy2(VALIDATOR, b / "scripts" / "v2" / VALIDATOR.name)
        nort = _run_validator_plain(pack, elsewhere.name,
                                    script=b / "scripts" / "v2"
                                    / VALIDATOR.name)
        lf_file = aud.get("localflow_file") or ""
        obs = {"dist_rc": run["code"], "dist_stdout": run["stdout"][:40],
               "localflow_from_dist": lf_file.startswith(
                   os.path.realpath(d)) or lf_file.startswith(str(d)),
               "forbidden_opens": [os.path.relpath(h, "/")[-60:]
                                   for h in run["forbidden_opens"]][:5],
               "sqlite": run["sqlite"], "probe_seen": aud["probe_seen"],
               "runtime_modules": len(aud["localflow_modules"]),
               "numpy_required": aud["numpy_loaded"],
               "no_runtime_rc": nort["code"],
               "no_runtime_reports": "No module named 'localflow'"
               in nort["stderr"],
               "reconstruct_mismatch": _reconstruct(pack, facts)}
        if not aud["probe_seen"]:
            return invalid("audit oracle inactive", obs)
        return check({
            "dist_validates": run["code"] == 0
            and run["stdout"].startswith("valid: True"),
            "runtime_is_the_dist_copy": obs["localflow_from_dist"],
            "no_checkout_or_store_reads": not run["forbidden_opens"],
            "no_sqlite": not run["sqlite"],
            "missing_runtime_is_explicit": nort["code"] != 0
            and obs["no_runtime_reports"],
            "reconstructs": not obs["reconstruct_mismatch"],
        }, obs, witness="validator run from a copy of only the localflow"
                        " package + script (no checkout, store or DB on"
                        " the read path); declared runtime = the localflow"
                        " package plus numpy from the venv; the bare script"
                        " reports ModuleNotFoundError localflow")
    finally:
        w.close()
        for t in (away, dist, bare, elsewhere):
            t.cleanup()


@drives("LF-M14-C161")
def c161_hash_tamper(entry):
    w, fx, out, err = _built_world_with_export()
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants"
        vdir.mkdir()
        clean = _validate_inproc(base)
        listed = dict((ln.partition("  ")[2], ln.partition("  ")[0])
                      for ln in (base / "SHA256SUMS.txt").read_text()
                      .splitlines() if ln.strip())
        results = {}
        # audio bytes changed, checksum untouched
        va = _variant(base, vdir, "audio")
        wav = sorted((va / "artifacts").glob("*.wav"))[0]
        data = bytearray(wav.read_bytes())
        data[-1] ^= 0x01
        wav.write_bytes(bytes(data))
        rel = wav.relative_to(va).as_posix()
        results["audio"] = (_validate_inproc(va), rel,
                            sha256_file(wav) != listed[rel])
        # reference text changed, checksum untouched
        vt = _variant(base, vdir, "text")
        refs = (vt / "references.jsonl").read_text()
        (vt / "references.jsonl").write_text(
            refs.replace(A_CANARY, "A_ONLY_42", 1))
        results["text"] = (_validate_inproc(vt), "references.jsonl",
                           sha256_file(vt / "references.jsonl")
                           != listed["references.jsonl"])
        # a record's text changed AND its file checksum updated, but the
        # content fingerprint left alone
        vf = _variant(base, vdir, "fingerprint")
        ex = (vf / "examples.jsonl").read_text()
        (vf / "examples.jsonl").write_text(ex.replace(
            "cleanup bare words", "cleanup bare wordz", 1))
        _write_sums(vf)
        results["fingerprint"] = (_validate_inproc(vf), "fingerprint",
                                  True)
        obs = {k: {"valid": r["valid"], "tamper_effective": eff,
                   "names_target": any(t in i for i in r["issues"])}
               for k, (r, t, eff) in results.items()}
        obs["clean_valid"] = clean["valid"]
        return check({
            "clean_valid": clean["valid"] is True,
            "tampers_effective": all(e for _r, _t, e in results.values()),
            "audio_rejected": results["audio"][0]["valid"] is False
            and obs["audio"]["names_target"],
            "text_rejected": results["text"][0]["valid"] is False
            and obs["text"]["names_target"],
            "fingerprint_rejected": results["fingerprint"][0]["valid"]
            is False and any("fingerprint" in i for i in
                             results["fingerprint"][0]["issues"]),
        }, obs, witness="byte-flipped WAV and edited reference with sums"
                        " untouched; edited record with sums recomputed"
                        " but fingerprint stale")
    finally:
        w.close()


def _consistent_variants(base, vdir, mutations):
    """Each mutation(examples, refs, prefs) -> kwargs for _rewrite.
    Returns {name: report} plus the unchanged-rewrite report."""
    out = {}
    unchanged = _variant(base, vdir, "unchanged")
    ex, refs, prefs = _records(unchanged)
    _rewrite(unchanged, examples=ex, references=refs, preferences=prefs)
    out["_unchanged"] = _validate_inproc(unchanged)
    for name, mut in mutations.items():
        v = _variant(base, vdir, name)
        ex, refs, prefs = _records(v)
        kw = mut(ex, refs, prefs, v)
        if kw is not None:
            _rewrite(v, **kw)
        out[name] = _validate_inproc(v)
    return out


def _by_kind(ex, kind):
    return [e for e in ex if e.get("task_kind") == kind]


def _lin(rec):
    lin = rec.get("lineage")
    return lin if isinstance(lin, dict) else {}


def _inp(rec, role):
    """The record's lineage input for ``role`` (a detached dict when the
    record carries no lineage — the audited base — so the mutation lands
    on nothing and the validator's verdict shows it)."""
    return next((i for i in _lin(rec).get("inputs") or []
                 if isinstance(i, dict) and i.get("role") == role), {})


@drives("LF-M14-C162")
def c162_semantic_consistent_tamper(entry):
    w, fx, out, err = _built_world_with_export()
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants"
        vdir.mkdir()

        def foreign_lineage(ex, refs, prefs, _v):
            a, b = _by_kind(ex, "asr_supervised")[:2]
            _inp(a, "original_audio")["job_id"] = _lin(b).get("job_id")
            return {"examples": ex}

        def foreign_audio(ex, refs, prefs, _v):
            a, b = _by_kind(ex, "asr_supervised")[:2]
            a["audio"], a["audio_sha256"] = b["audio"], b["audio_sha256"]
            return {"examples": ex}

        def wrong_role(ex, refs, prefs, _v):
            a = _by_kind(ex, "asr_supervised")[0]
            _inp(a, "verbatim_reference")["role"] = "applied_output"
            return {"examples": ex}

        def wrong_task(ex, refs, prefs, _v):
            t = _by_kind(ex, "transform_supervised")[0]
            _lin(t)["task_key"] = prefs[0]["task_key"]
            return {"examples": ex}

        def wrong_example(ex, refs, prefs, _v):
            a, b = _by_kind(ex, "asr_supervised")[:2]
            _lin(a)["example_id"] = b["example_id"]
            return {"examples": ex}

        def swapped_output(ex, refs, prefs, _v):
            c1, c2 = _by_kind(ex, "cleanup_supervised")[:2]
            c1["output_text"] = c2["output_text"]
            return {"examples": ex}

        def chosen_contradicts(ex, refs, prefs, _v):
            prefs[0]["chosen"] = "a"
            return {"preferences": prefs}

        muts = {"foreign_lineage": foreign_lineage,
                "foreign_audio": foreign_audio, "wrong_role": wrong_role,
                "wrong_task": wrong_task, "wrong_example": wrong_example,
                "swapped_output": swapped_output,
                "chosen_contradicts": chosen_contradicts}
        rep = _consistent_variants(base, vdir, muts)
        obs = {k: (r["valid"], len(r["issues"])) for k, r in rep.items()}
        if rep["_unchanged"]["valid"] is not True:
            return invalid("unchanged consistent rewrite did not validate",
                           obs)
        conds = {f"{k}_rejected": rep[k]["valid"] is False for k in muts}
        return check(conds, obs,
                     witness="every checksum and the fingerprint recomputed"
                             " by this driver; unchanged rewrite validates")
    finally:
        w.close()


_CANARY_RE = re.compile(r"A_ONLY_|B_ONLY_|witness|cleanup (full|bare)"
                        r"|Transform [AB]|Pref output|pref source"
                        r"|transform source")


@drives("LF-M14-C163")
def c163_missing_payload(entry):
    w, fx, out, err = _built_world_with_export()
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants"
        vdir.mkdir()
        rep = {"_clean": _validate_inproc(base)}
        # 1. an exported audio payload removed, sums untouched
        v = _variant(base, vdir, "audio_gone")
        wav = sorted((v / "artifacts").glob("*.wav"))[0]
        wav.unlink()
        rep["audio_gone"] = _validate_inproc(v)
        # 2. the same, with its sums line removed too (consistent)
        v = _variant(base, vdir, "audio_gone_consistent")
        sorted((v / "artifacts").glob("*.wav"))[0].unlink()
        _rewrite(v)
        rep["audio_gone_consistent"] = _validate_inproc(v)

        def drop_definition(ex, refs, prefs, _v):
            for e in _by_kind(ex, "transform_supervised"):
                e.pop("transform_definition", None)
            return {"examples": ex}

        def drop_review(ex, refs, prefs, _v):
            a = _by_kind(ex, "asr_supervised")[0]
            refs = [r for r in refs if not (
                r.get("example_id") == a["example_id"]
                and r.get("task_kind") == "asr_supervised")]
            return {"references": refs}

        def drop_source(ex, refs, prefs, _v):
            prefs[0].pop("input_text", None)
            return {"preferences": prefs}

        def drop_records_file(ex, refs, prefs, v):
            (v / "references.jsonl").unlink()
            _write_sums(v)
            return None
        rep.update(_consistent_variants(base, vdir, {
            "definition_gone": drop_definition, "review_gone": drop_review,
            "source_gone": drop_source,
            "references_file_gone": drop_records_file}))
        leaks = {k: [i for i in r["issues"] if _CANARY_RE.search(i)]
                 for k, r in rep.items()}
        obs = {k: {"valid": r["valid"], "issues": len(r["issues"]),
                   "content_in_reason": len(leaks[k])}
               for k, r in rep.items()}
        want = {"audio_gone": "missing", "audio_gone_consistent": "missing",
                "definition_gone": "definition", "review_gone":
                "no reference", "source_gone": "reconstruct",
                "references_file_gone": "references.jsonl"}
        if rep["_clean"]["valid"] is not True or \
                rep["_unchanged"]["valid"] is not True:
            return invalid("clean package or unchanged rewrite invalid", obs)
        conds = {}
        for k, needle in want.items():
            conds[f"{k}_refused"] = rep[k]["valid"] is False
            conds[f"{k}_names_missing_target"] = any(
                needle in i for i in rep[k]["issues"])
            conds[f"{k}_content_free"] = not leaks[k]
        return check(conds, obs, witness="audio payload, transform"
                     " definition, verbatim review reference, preference"
                     " task input and a record file removed; no rights"
                     " object is carried by the package (consent is a"
                     " lineage id only)")
    finally:
        w.close()


@drives("LF-M14-C164")
def c164_unsupported_schema(entry):
    w, fx, out, err = _built_world_with_export()
    elsewhere = tempfile.TemporaryDirectory(prefix="m14f-cwd-")
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants"
        vdir.mkdir()
        targets = {"clean": base}

        def mk(name, fn):
            v = _variant(base, vdir, name)
            fn(v)
            targets[name] = v

        def schema99(v):
            _rewrite(v, manifest=lambda m: m.__setitem__(
                "export_schema_version", 99))
        mk("schema_99", schema99)
        mk("manifest_not_json", lambda v: (
            (v / "dataset_manifest.json").write_text("{not json"),
            _write_sums(v)))
        mk("manifest_array", lambda v: (
            (v / "dataset_manifest.json").write_text("[1, 2]"),
            _write_sums(v)))
        mk("jsonl_garbage", lambda v: (
            (v / "examples.jsonl").write_text(
                (v / "examples.jsonl").read_text() + "{broken\n[3]\n"),
            _write_sums(v)))

        def typed(fn):
            def go(v):
                ex, refs, prefs = _records(v)
                fn(ex, refs, prefs)
                _rewrite(v, examples=ex, references=refs,
                         preferences=prefs)
            return go
        mk("example_id_object", typed(lambda ex, r, p: ex[0].__setitem__(
            "example_id", {"nested": 1})))
        mk("task_kind_list", typed(lambda ex, r, p: ex[0].__setitem__(
            "task_kind", ["asr_supervised"])))
        mk("lineage_string", typed(lambda ex, r, p: ex[0].__setitem__(
            "lineage", "not-an-object")))
        mk("candidates_scalar", typed(lambda ex, r, p: p[0].__setitem__(
            "candidates", 7)))
        mk("family_list", typed(lambda ex, r, p: ex[0].__setitem__(
            "family_id", ["f"])))
        mk("counts_list", lambda v: _rewrite(v, manifest=lambda m:
                                             m.__setitem__("counts", [1])))
        aud = _run_validator_audited(list(targets.values()),
                                     elsewhere.name, forbid=[])
        if "error" in aud:
            return invalid("audit wrapper failed", aud)
        runs = dict(zip(targets, aud["runs"]))
        plain = _run_validator_plain(targets["schema_99"], elsewhere.name)
        obs = {k: {"rc": r["code"], "crash": r.get("crash"),
                   "first": r["stdout"].splitlines()[0]
                   if r["stdout"] else None} for k, r in runs.items()}
        for k, r in runs.items():
            if r.get("crash"):
                obs[k]["at"] = [ln.strip() for ln in (r.get("trace") or "")
                                .splitlines() if ln.strip()][-3:]
        obs["plain_schema_99"] = [plain["code"], plain["valid_line"],
                                  "Traceback" in plain["stderr"]]
        if runs["clean"]["code"] != 0:
            return invalid("clean package did not validate", obs)
        conds = {}
        for k, r in runs.items():
            if k == "clean":
                continue
            conds[f"{k}_structured_refusal"] = r["code"] == 1 and \
                not r.get("crash") and \
                r["stdout"].startswith("valid: False")
        conds["schema_reason"] = "unsupported export schema version" in \
            runs["schema_99"]["stdout"]
        conds["plain_no_traceback"] = plain["code"] == 1 and \
            "Traceback" not in plain["stderr"]
        return check(conds, obs, witness="validate_dataset.py over unsupported"
                     " schema, non-JSON / non-object manifest, unparsable"
                     " rows and wrongly typed fields (sums recomputed)")
    finally:
        w.close()
        elsewhere.cleanup()


@drives("LF-M14-C165")
def c165_unsafe_paths(entry):
    w, fx, out, err = _built_world_with_export()
    elsewhere = tempfile.TemporaryDirectory(prefix="m14f-cwd-")
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants" / "nest"
        vdir.mkdir(parents=True)
        outside = w.tmp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.wav"
        sentinel.write_bytes(b"RIFF-outside-sentinel-bytes")
        probe = outside / "probe.bin"
        probe.write_bytes(b"probe")
        sdig = sha256_file(sentinel)
        targets = {"clean": base}

        def mk(name, fn):
            v = _variant(base, vdir, name)
            fn(v)
            targets[name] = v

        mk("sums_absolute", lambda v: _rewrite(
            v, extra_sums=[f"{sdig}  {sentinel}"]))
        mk("sums_parent", lambda v: _rewrite(
            v, extra_sums=[f"{sdig}  ../../../outside/sentinel.wav"]))

        def sym_file(v):
            os.symlink(sentinel, v / "artifacts" / "link.wav")
            _rewrite(v, extra_sums=[f"{sdig}  artifacts/link.wav"])
        mk("symlink_file", sym_file)

        def sym_audio(v):
            os.symlink(sentinel, v / "artifacts" / "link.wav")
            ex, refs, prefs = _records(v)
            a = _by_kind(ex, "asr_supervised")[0]
            a["audio"], a["audio_sha256"] = "artifacts/link.wav", sdig
            _rewrite(v, examples=ex,
                     extra_sums=[f"{sdig}  artifacts/link.wav"])
        mk("symlink_audio", sym_audio)

        def abs_audio(v):
            ex, refs, prefs = _records(v)
            a = _by_kind(ex, "asr_supervised")[0]
            a["audio"], a["audio_sha256"] = str(sentinel), sdig
            _rewrite(v, examples=ex)
        mk("absolute_audio", abs_audio)

        def parent_audio(v):
            ex, refs, prefs = _records(v)
            a = _by_kind(ex, "asr_supervised")[0]
            a["audio"] = "../../../outside/sentinel.wav"
            a["audio_sha256"] = sdig
            _rewrite(v, examples=ex)
        mk("parent_audio", parent_audio)

        def sym_dir(v):
            os.symlink(outside, v / "extra")
            _rewrite(v, extra_sums=[f"{sdig}  extra/sentinel.wav"])
        mk("symlink_dir", sym_dir)

        def sym_dir_audio(v):
            os.symlink(outside, v / "extra")
            ex, refs, prefs = _records(v)
            a = _by_kind(ex, "asr_supervised")[0]
            a["audio"], a["audio_sha256"] = "extra/sentinel.wav", sdig
            _rewrite(v, examples=ex,
                     extra_sums=[f"{sdig}  extra/sentinel.wav"])
        mk("symlink_dir_audio", sym_dir_audio)

        aud = _run_validator_audited(list(targets.values()), elsewhere.name,
                                     forbid=[outside], probe=probe)
        if "error" in aud:
            return invalid("audit wrapper failed", aud)
        runs = dict(zip(targets, aud["runs"]))
        obs = {k: {"rc": r["code"], "crash": r.get("crash"),
                   "outside_reads": len(r["forbidden_opens"])}
               for k, r in runs.items()}
        obs["probe_seen"] = aud["probe_seen"]
        if not aud["probe_seen"]:
            return invalid("audit oracle inactive", obs)
        if runs["clean"]["code"] != 0:
            return invalid("clean package did not validate", obs)
        conds = {}
        for k, r in runs.items():
            if k == "clean":
                continue
            conds[f"{k}_invalid"] = r["code"] == 1 and not r.get("crash")
            conds[f"{k}_no_outside_read"] = not r["forbidden_opens"]
        return check(conds, obs, witness="absolute/parent sums and audio"
                     " paths, symlinked file and symlinked directory"
                     " entries; audit hook records every open under the"
                     " outside root (live-probe control)")
    finally:
        w.close()
        elsewhere.cleanup()


@drives("LF-M14-C166")
def c166_counts_and_duplicates(entry):
    w, fx, out, err = _built_world_with_export(pair_family=True)
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        base = w.tmp / "ds"
        vdir = w.tmp / "variants"
        vdir.mkdir()
        manifest = json.loads((base / "dataset_manifest.json").read_text())
        recount = _recount(base)
        pair_ids = {j["example_id"] for j in fx["pair"]}

        def bump(kind, n=1):
            def m(man):
                man["counts"][kind] += n
            return m

        def count_off(ex, refs, prefs, _v):
            return {"manifest": bump("asr_supervised")}

        def dup_example(ex, refs, prefs, _v):
            asr = _by_kind(ex, "asr_supervised")
            if not asr:
                return None
            return {"examples": ex + [json.loads(json.dumps(asr[0]))],
                    "manifest": bump("asr_supervised")}

        def dup_reference(ex, refs, prefs, _v):
            asr_ids = {e.get("example_id") for e in
                       _by_kind(ex, "asr_supervised")}
            pick = [x for x in refs if x.get("example_id") in asr_ids]
            if not pick:
                return None
            return {"references": refs + [json.loads(json.dumps(pick[0]))]}

        # A mutation whose target the package does not carry is left
        # unapplied (None): the variant then validates and the case
        # fails on it, with positive_package_complete naming why.
        def dup_pair(ex, refs, prefs, _v):
            if not prefs:
                return None
            return {"preferences": prefs + [json.loads(json.dumps(
                prefs[0]))], "manifest": bump("preference_pairs")}

        def choice_flip(ex, refs, prefs, _v):
            if not prefs or prefs[0].get("chosen") not in ("a", "b"):
                return None
            prefs[0]["chosen"] = {"a": "b", "b": "a"}[prefs[0]["chosen"]]
            return {"preferences": prefs}

        def family_split(ex, refs, prefs, _v):
            pair = [e for e in ex if e.get("example_id") in pair_ids
                    and e.get("task_kind") == "asr_supervised"]
            if not pair:
                return None
            a = pair[0]
            new = "validation" if a["split"] != "validation" else "train"
            a["split"] = new
            _lin(a)["split"] = new
            return {"examples": ex}

        def tiers_off(ex, refs, prefs, _v):
            def m(man):
                tiers = man.setdefault("cleanup_tiers", {})
                tiers["text_pair_only"] = tiers.get("text_pair_only", 0) + 1
            return {"manifest": m}

        muts = {"count_off": count_off, "dup_example": dup_example,
                "dup_reference": dup_reference, "dup_pair": dup_pair,
                "choice_flip": choice_flip, "family_split": family_split,
                "tiers_off": tiers_off}
        rep = _consistent_variants(base, vdir, muts)
        pair_splits = {e["split"] for e in _records(base)[0]
                       if e.get("example_id") in pair_ids}
        obs = {k: (r["valid"], len(r["issues"])) for k, r in rep.items()}
        obs.update(recount=recount, manifest_counts=manifest["counts"],
                   pair_family_splits=sorted(pair_splits))
        if rep["_unchanged"]["valid"] is not True:
            return invalid("unchanged consistent rewrite did not validate",
                           obs)
        conds = {"manifest_equals_recount": manifest["counts"] == recount,
                 "positive_package_complete": recount == {
                     "asr_supervised": 12, "asr_span_graft_weak": 0,
                     "cleanup_supervised": 2, "transform_supervised": 1,
                     "preference_pairs": 1},
                 "pair_family_one_partition": len(pair_splits) == 1}
        conds.update({f"{k}_rejected": rep[k]["valid"] is False
                      for k in muts})
        return check(conds, obs, witness="counts, duplicate example/"
                     "reference/pair, choice mapping, family partition and"
                     " tier counts altered with every checksum recomputed")
    finally:
        w.close()


# =============================================================================
# readiness
# =============================================================================


def _te(w):
    return w.training.readiness()["readiness_metrics"]["task_eligibility"]


def _membership(root):
    ex, _refs, prefs = _records(root)
    return {
        "asr_supervised": {e.get("example_id") for e in ex
                           if e.get("task_kind") == "asr_supervised"},
        "cleanup_supervised": {e.get("example_id") for e in ex
                               if e.get("task_kind") == "cleanup_supervised"},
        "transform_supervised": {(e.get("task_key"), e.get("candidate_id"))
                                 for e in ex if e.get("task_kind")
                                 == "transform_supervised"},
        "preference_pairs": {p.get("task_key") for p in prefs},
        "tiers": {t: sum(1 for e in ex
                         if e["task_kind"] == "cleanup_supervised"
                         and e.get("qualification_tier") == t)
                  for t in ("model_task_complete", "text_pair_only")},
    }


def _parity(w, dest, views=ALL_VIEWS):
    out, err = _export(w, dest, views)
    if out is None:
        return None, err, None
    mem = _membership(w.tmp / dest)
    te = _te(w)
    ready = {k: (te.get(k) or {}).get("count") for k in KINDS}
    exported = {k: len(mem[k]) for k in KINDS}
    return {"ready": ready, "exported": exported, "mem": mem,
            "tiers_ready": {t: ((te.get("cleanup_supervised") or {}).get(
                "tiers") or {}).get(t, 0) for t in mem["tiers"]},
            "te": te}, None, out


@drives("LF-M14-C167")
def c167_positive_parity(entry):
    with MWorld() as w:
        fx = _seed_all(w)
        w.splits.assign()
        p, err, out = _parity(w, "ds")
        if p is None:
            return invalid(f"positive export refused: {err}")
        rm = w.training.readiness()["readiness_metrics"]
        want = {"asr_supervised": 10, "cleanup_supervised": 2,
                "transform_supervised": 1, "preference_pairs": 1}
        asr_ids = {j["example_id"] for j in fx["asr"]}
        integ = rm["export_integrity"]
        vr = rm["verbatim_reference_coverage"]
        obs = {"ready": p["ready"], "exported": p["exported"],
               "tiers_ready": p["tiers_ready"], "tiers": p["mem"]["tiers"],
               "captured_tasks": p["te"]["transform_supervised"].get(
                   "captured_tasks"),
               "integrity_keys": sorted(integ) if isinstance(integ, dict)
               else integ, "reviewed_seconds": vr.get("reviewed_seconds"),
               "retained_seconds": vr.get("retained_seconds")}
        return check({
            "ready_equals_literal": p["ready"] == want,
            "export_equals_literal": p["exported"] == want,
            "asr_membership": p["mem"]["asr_supervised"] == asr_ids,
            "cleanup_membership": p["mem"]["cleanup_supervised"] == {
                fx["clean_full"]["example_id"],
                fx["clean_bare"]["example_id"]},
            "tiers_separated": p["tiers_ready"] == p["mem"]["tiers"] == {
                "model_task_complete": 1, "text_pair_only": 1},
            "captured_tier_separate": obs["captured_tasks"] == 2,
            "m13_last_export_label": isinstance(integ, dict)
            and integ.get("last_state") == "complete"
            and integ.get("last_fingerprint") == out["fingerprint"],
            "m13_reviewed_seconds_full_clips": vr.get("reviewed_seconds")
            == 10.0 and vr.get("retained_seconds") == 12.0,
        }, obs, grading="decision", decision=f"{DECISION}:D03",
            witness="readiness task_eligibility vs export membership over"
                    " the same assignment; cleanup tiers per D03")


def _asr_cohort(w, n=10):
    return [w.ready_asr() for _ in range(n)]


@drives("LF-M14-C168")
def c168_foreign_audio(entry):
    with MWorld() as w:
        cohort = _asr_cohort(w)
        a, b = cohort[0], cohort[1]
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("original_audio", b["audio_aid"]))
        w.splits.assign()
        p, err, _o = _parity(w, "ds", ("asr_supervised",))
        if p is None:
            return invalid(f"export refused: {err}")
        gate = w.review.verified_asr_eligible(a["example_id"])
        mem = p["mem"]["asr_supervised"]
        obs = {"ready": p["ready"]["asr_supervised"],
               "exported": len(mem), "a_in": a["example_id"] in mem,
               "b_in": b["example_id"] in mem, "gate": gate["eligible"]}
        return check({
            "control_b_exported": obs["b_in"],
            "a_refused_by_export": not obs["a_in"],
            "a_refused_by_gate": gate["eligible"] is False,
            "ready_equals_export": obs["ready"] == obs["exported"] == 9,
        }, obs, grading="decision", decision=f"{DECISION}:D11",
            witness="A's envelope names B's original_audio")


@drives("LF-M14-C169")
def c169_wrong_cleanup_source(entry):
    with MWorld() as w:
        _asr_cohort(w)
        a = w.ready_cleanup(f"cleanup alpha {A_CANARY}")
        b = w.ready_cleanup(f"cleanup bravo {B_CANARY}")
        c = w.ready_cleanup("cleanup charlie text")
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", b["raw_aid"]))
        w.rewrite_envelope(c["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", c["applied_aid"]))
        w.splits.assign()
        p, err, _o = _parity(w, "ds", ("cleanup_supervised",))
        if p is None:
            return invalid(f"export refused: {err}")
        mem = p["mem"]["cleanup_supervised"]
        obs = {"ready": p["ready"]["cleanup_supervised"],
               "exported": sorted(x == b["example_id"] for x in mem)}
        return check({
            "control_exported": b["example_id"] in mem,
            "foreign_not_counted": a["example_id"] not in mem,
            "wrong_stage_not_counted": c["example_id"] not in mem,
            "ready_equals_export": p["ready"]["cleanup_supervised"]
            == len(mem) == 1,
        }, obs, grading="decision", decision=f"{DECISION}:D11",
            witness="A's source_text is B's raw transcript; C's is its own"
                    " applied output")


@drives("LF-M14-C170")
def c170_incorrect_intended(entry):
    with MWorld() as w:
        _asr_cohort(w)
        good = w.ready_cleanup("cleanup marked correct")
        bad = w.ready_cleanup("cleanup marked incorrect", correct=False)
        w.splits.assign()
        p, err, _o = _parity(w, "ds", ("cleanup_supervised",))
        if p is None:
            return invalid(f"export refused: {err}")
        mem = p["mem"]["cleanup_supervised"]
        src_kept = w.artifact_row(bad["raw_aid"])
        obs = {"ready": p["ready"]["cleanup_supervised"],
               "exported": len(mem), "incorrect_source_retained":
               bool(src_kept and not src_kept[2])}
        return check({
            "correct_control_exported": good["example_id"] in mem,
            "incorrect_not_target": bad["example_id"] not in mem,
            "source_retained": obs["incorrect_source_retained"],
            "ready_equals_export": obs["ready"] == obs["exported"] == 1,
        }, obs, witness="explicit 'not what I meant' mark with source"
                        " retained")


@drives("LF-M14-C171")
def c171_blocked_asr(entry):
    with MWorld() as w:
        cohort = _asr_cohort(w)
        changed = w.ready_asr("changed intent witness")
        amb = w.ready_asr("ambiguous unresolved witness")
        resolved = w.ready_asr("ambiguous resolved witness")
        w.review.record_label(changed["example_id"],
                              edit_kind="changed_intent",
                              origin_stages=("user_intent",))
        w.review.record_label(amb["example_id"], edit_kind="ambiguous")
        w.review.record_label(resolved["example_id"], edit_kind="ambiguous")
        w.review.record_label(resolved["example_id"],
                              edit_kind="recognition_error",
                              origin_stages=("asr",))
        w.splits.assign()
        p, err, _o = _parity(w, "ds", ("asr_supervised",))
        if p is None:
            return invalid(f"export refused: {err}")
        mem = p["mem"]["asr_supervised"]
        want = {j["example_id"] for j in cohort} | {resolved["example_id"]}
        obs = {"ready": p["ready"]["asr_supervised"], "exported": len(mem),
               "changed_in": changed["example_id"] in mem,
               "amb_in": amb["example_id"] in mem,
               "resolved_in": resolved["example_id"] in mem}
        return check({
            "membership_follows_policy": mem == want,
            "ready_equals_export": obs["ready"] == len(mem) == 11,
        }, obs, grading="decision", decision=f"{DECISION}:D01",
            witness="changed_intent (permanent), unresolved ambiguous and"
                    " ambiguous resolved by a later recognition_error")


@drives("LF-M14-C172")
def c172_latest_preference(entry):
    with MWorld() as w:
        _asr_cohort(w)
        tasks = {}
        for name, later in (("to_tie", "tie"), ("to_uncertain", "uncertain"),
                            ("to_b", "prefer_b"), ("only_a", None)):
            t = w.transform_task(f"latest pref source {name}",
                                 [f"{name} out one.", f"{name} out two."])
            a, b = (c["candidate_id"] for c in t["candidates"])
            w.judge(t, a, b, "prefer_a")
            if later:
                w.judge(t, a, b, later)
            tasks[name] = t
        w.splits.assign()
        p, err, _o = _parity(w, "ds", ("preference_pairs",))
        if p is None:
            return invalid(f"export refused: {err}")
        prefs = {r["task_key"]: (r["judgment"], r["chosen"])
                 for r in _records(w.tmp / "ds")[2]}
        got = {n: prefs.get(t["task_key"]) for n, t in tasks.items()}
        want = {"to_tie": ("tie", None), "to_uncertain": ("uncertain", None),
                "to_b": ("prefer_b", "b"), "only_a": ("prefer_a", "a")}
        obs = {"ready": p["ready"]["preference_pairs"],
               "exported": len(prefs), "records": got}
        return check({
            "current_judgment_exported": got == want,
            "ready_equals_export": obs["ready"] == len(prefs) == 4,
        }, obs, witness="prefer_a superseded by tie / uncertain / prefer_b"
                        " (dataset_exports.md: latest comparable judgment)")


def _two_member_family(w, fam="fam-synth-f-span-0"):
    return [w.ready_asr(f"span family member {k}", family=fam)
            for k in range(2)], fam


def _inject_contamination(w, version, frozen_fam, span_fam):
    def op(c):
        c.execute("UPDATE training_memberships SET exposed=1,"
                  " exposed_reason='inspected_during_tuning' WHERE"
                  " assignment_version=? AND family_id=?",
                  (version, frozen_fam))
        row = c.execute("SELECT example_id, partition FROM"
                        " training_memberships WHERE assignment_version=?"
                        " AND family_id=? ORDER BY example_id LIMIT 1",
                        (version, span_fam)).fetchone()
        other = "validation" if row[1] != "validation" else "train"
        c.execute("UPDATE training_memberships SET partition=? WHERE"
                  " assignment_version=? AND example_id=?",
                  (other, version, row[0]))
    w.store.submit(op)


def _sql_contamination(w, version):
    spanning = w.one(
        "SELECT COUNT(*) FROM (SELECT family_id FROM training_memberships"
        " WHERE assignment_version=? GROUP BY family_id HAVING"
        " COUNT(DISTINCT partition) > 1)", (version,))[0]
    exposed = w.one(
        "SELECT COUNT(DISTINCT family_id) FROM training_memberships WHERE"
        " assignment_version=? AND exposed=1 AND partition='frozen_test'",
        (version,))[0]
    return spanning, exposed


def _split_metric(w):
    sc = w.training.readiness()["readiness_metrics"]["split_contamination"]
    if not isinstance(sc, dict):
        return sc
    return (sc["assignment_version"], sc["families_spanning_partitions"],
            sc["exposed_frozen_families"])


@drives("LF-M14-C173")
def c173_split_current(entry):
    obs = {}
    conds = {}
    for order in ("old_dirty_current_clean", "old_clean_current_dirty"):
        with MWorld() as w:
            w.families(30, asr=True, frozen=3)
            _two_member_family(w)
            frozen = W.frozen_family_id(0)
            span = "fam-synth-f-span-0"
            v1 = w.splits.assign()["assignment_version"]
            if order == "old_dirty_current_clean":
                _inject_contamination(w, v1, frozen, span)
                v2 = w.splits.assign()["assignment_version"]
            else:
                v2 = w.splits.assign()["assignment_version"]
                _inject_contamination(w, v2, frozen, span)
            sql = {v: _sql_contamination(w, v) for v in (v1, v2)}
            metric = _split_metric(w)
            out, err = _export(w, "ds", ("asr_supervised",))
            obs[order] = {"sql": sql, "metric": metric,
                          "export": out is not None}
            if order == "old_dirty_current_clean":
                conds[f"{order}_fixture"] = sql[v1] == (1, 1) \
                    and sql[v2] == (0, 0)
                conds[f"{order}_metric_current_only"] = metric == (v2, 0, 0)
                conds[f"{order}_export_ok"] = out is not None
            else:
                conds[f"{order}_fixture"] = sql[v1] == (0, 0) \
                    and sql[v2] == (1, 1)
                conds[f"{order}_metric_current_only"] = metric == (v2, 1, 1)
                conds[f"{order}_export_refused"] = out is None and \
                    "leakage" in (err or "")
    return check(conds, obs, witness="contamination (spanning family +"
                 " exposed frozen family) injected into the old or the"
                 " current assignment version; recounted by SQL")


@drives("LF-M14-C174")
def c174_last_export_label(entry):
    with MWorld() as w:
        cohort = _asr_cohort(w, 11)
        w.splits.assign()
        out, err = _export(w, "ds", ("asr_supervised",))
        if out is None:
            return invalid(f"export refused: {err}")
        n_old = len(read_jsonl(w.tmp / "ds" / "examples.jsonl"))
        fp_old = json.loads((w.tmp / "ds" / "dataset_manifest.json")
                            .read_text())["content_fingerprint"]
        before = w.training.readiness()["readiness_metrics"]
        w.purge(cohort[0]["audio_aid"])  # source change after the export
        after = w.training.readiness()["readiness_metrics"]
        integ = after["export_integrity"]
        asr_now = after["task_eligibility"]["asr_supervised"]["count"]
        out2, err2 = _export(w, "ds2", ("asr_supervised",))
        n_new = len(read_jsonl(w.tmp / "ds2" / "examples.jsonl")) \
            if out2 else None
        again = w.training.readiness()["readiness_metrics"][
            "export_integrity"]
        keys = sorted(integ) if isinstance(integ, dict) else []
        claims_current = [k for k in keys if k in (
            "valid", "qualified", "current", "current_valid",
            "dataset_qualified")]
        obs = {"keys": keys, "n_old": n_old, "asr_now": asr_now,
               "last_examples": integ.get("last_examples")
               if isinstance(integ, dict) else None,
               "after_reexport": again.get("last_examples")
               if isinstance(again, dict) else None, "n_new": n_new}
        return check({
            "labeled_last": bool(keys) and all(
                k.startswith("last_") or k in ("finalized_at_utc", "note")
                for k in keys),
            "no_current_claim": not claims_current,
            "unchanged_by_source_change": integ == before[
                "export_integrity"],
            "describes_last_export": integ.get("last_examples") == n_old
            and integ.get("last_fingerprint") == fp_old
            and integ.get("last_state") == "complete",
            "current_eligibility_moved": asr_now == n_old - 1,
            "tracks_next_export": out2 is not None and
            again.get("last_examples") == n_new == n_old - 1,
        }, obs, witness="export, then purge one exported audio; the"
                        " integrity metric keeps describing the last"
                        " export while task eligibility moves")


@drives("LF-M14-C175")
def c175_reviewed_seconds(entry):
    with MWorld() as w:
        full = w.job("full listened clip words")
        w.verbatim(full["example_id"], full["raw"])
        span = w.job("partial span clip words")
        w.training.add_span_correction(span["example_id"], "source_text",
                                       0, 7, "Partial")
        noaudio = w.job("verbatim without audio", audio=False)
        w.verbatim(noaudio["example_id"], noaudio["raw"])
        vr = w.training.readiness()["readiness_metrics"][
            "verbatim_reference_coverage"]
        span_env = w.envelope(span["example_id"])
        span_ann = [a for a in span_env.get("annotations") or []
                    if a.get("kind") == "span_correction"]
        obs = {"reviewed_seconds": vr.get("reviewed_seconds"),
               "retained_seconds": vr.get("retained_seconds"),
               "examples": vr.get("examples"),
               "without_audio": vr.get("references_without_audio"),
               "span_recorded": len(span_ann)}
        if not span_ann:
            return invalid("span correction never recorded", obs)
        return check({
            "full_clip_only": vr.get("reviewed_seconds") == 1.0,
            "retained_both_clips": vr.get("retained_seconds") == 2.0,
            "one_verified_clip": vr.get("examples") == 1,
            "reference_without_audio_named": vr.get(
                "references_without_audio") == 1,
        }, obs, witness="1.0 s clip with a listened verbatim, 1.0 s clip"
                        " with only a partial span, verbatim with no audio")


# =============================================================================
# profile eligibility
# =============================================================================


def _text(tag, n):
    return " ".join(f"{tag}w{k}" for k in range(n))


def _norm_key(text):
    """This driver's normalization of the declared repeat policy: the
    lower-cased word sequence (letters/digits/underscore runs)."""
    out, cur = [], []
    for ch in text.lower():
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return " ".join(out)


def _card_ids(snap):
    return {e for c in snap["cards"] for e in c["evidence_example_ids"]}


def _floor_world(sizes, *, labels=0, counts=()):
    w = MWorld()
    jobs = []
    for i, n in enumerate(sizes):
        kw = {}
        if i < len(counts) and counts[i] is not None:
            kw["cleanup_counts"] = {"applied": counts[i]}
        jobs.append(w.job(_text(f"d{i}x", n), audio=False, **kw))
    for j in jobs[:labels]:
        w.review.record_label(j["example_id"],
                              edit_kind="recognition_error",
                              origin_stages=("asr",))
    return w, jobs


@drives("LF-M14-C176")
def c176_positive_floor(entry):
    w, jobs = _floor_world([200] * 10, labels=3,
                           counts=(2, 0, 1, 0))
    try:
        snap = w.profile.compute()
        m = snap["measured"]
        ids_ = {j["example_id"] for j in jobs}
        words = sum(len(j["raw"].split()) for j in jobs)
        cards = {c["card_id"]: c for c in snap["cards"]}
        ev_rows = {r[0] for r in w.rows(
            "SELECT example_id FROM profile_evidence WHERE snapshot_id=?"
            " AND role='measured'", (snap["snapshot_id"],))}
        sc = m["self_corrections"]
        obs = {"examples": m["eligible_examples"],
               "words": m["eligible_words"], "cards": sorted(cards),
               "available": snap["interpretive_available"],
               "self_corrections": [sc["dictations_with"], sc["applied"],
                                    sc["denominator"]]}
        return check({
            "counts_equal_oracle": (m["eligible_examples"],
                                    m["eligible_words"]) == (10, words)
            and words == 2000,
            "interpretive_at_floor": snap["interpretive_available"] is True
            and "style-length" in cards,
            "cards_cite_eligible_only": _card_ids(snap) <= ids_,
            "focus_card_supported": set(cards.get(
                "correction-focus", {}).get("evidence_example_ids", []))
            == {j["example_id"] for j in jobs[:3]},
            "no_unsupported_card": "technical-vocabulary" not in cards,
            "style_matches_median": cards.get("style-length", {}).get(
                "title") == "long-form utterances",
            "evidence_rows_exact": ev_rows == ids_,
            "m13_self_correction_known_only": obs["self_corrections"]
            == [2, 3, 4],
        }, obs, witness="ten 200-word dictations (floor exactly met);"
                        " three labeled; four with a recorded"
                        " self-correction count")
    finally:
        w.close()


@drives("LF-M14-C177")
def c177_below_words(entry):
    w, jobs = _floor_world([200] * 9 + [199])
    wc, _jc = _floor_world([200] * 10)
    try:
        snap = w.profile.compute()
        ctrl = wc.profile.compute()
        m = snap["measured"]
        obs = {"words": m["eligible_words"],
               "examples": m["eligible_examples"],
               "cards": len(snap["cards"]),
               "note": bool(snap["interpretive_note"]),
               "control_cards": len(ctrl["cards"])}
        return check({
            "counts_exact": (m["eligible_examples"], m["eligible_words"])
            == (10, 1999),
            "measured_only": snap["interpretive_available"] is False
            and snap["cards"] == [] and bool(snap["interpretive_note"]),
            "control_at_floor_interprets": ctrl["interpretive_available"]
            is True and len(ctrl["cards"]) > 0,
        }, obs, witness="ten dictations, 1,999 words vs a 2,000-word"
                        " same-shape control")
    finally:
        w.close()
        wc.close()


@drives("LF-M14-C178")
def c178_below_dictations(entry):
    w, jobs = _floor_world([230] * 9)
    wc, _jc = _floor_world([230] * 10)
    try:
        snap = w.profile.compute()
        ctrl = wc.profile.compute()
        m = snap["measured"]
        obs = {"words": m["eligible_words"],
               "examples": m["eligible_examples"],
               "cards": len(snap["cards"]),
               "control_cards": len(ctrl["cards"])}
        return check({
            "counts_exact": (m["eligible_examples"], m["eligible_words"])
            == (9, 2070),
            "measured_only": snap["interpretive_available"] is False
            and snap["cards"] == [] and bool(snap["interpretive_note"]),
            "control_ten_interprets": ctrl["interpretive_available"]
            is True and len(ctrl["cards"]) > 0,
        }, obs, witness="nine dictations with 2,070 words vs ten")
    finally:
        w.close()
        wc.close()


@drives("LF-M14-C179")
def c179_restricted(entry):
    with MWorld(min_words=50) as w:
        live = [w.job(_text(f"live{i}x", 20) + " falcon nebula"
                      if i < 2 else _text(f"live{i}x", 20), audio=False)
                for i in range(11)]
        restricted = {}
        for name in ("deleted", "expired", "quarantined", "excluded",
                     "purged"):
            restricted[name] = w.job(
                _text(f"r{name}x", 20) + " zebra quantum", audio=False)
        w.training.delete_everywhere(restricted["deleted"]["example_id"])
        w.set_state(restricted["expired"]["example_id"], "expired")
        w.set_state(restricted["quarantined"]["example_id"],
                    "quarantined_sensitive")
        w.training.exclude(restricted["excluded"]["example_id"])
        w.purge(restricted["purged"]["raw_aid"])
        s1 = w.profile.compute()
        w.profile.exclude_evidence(s1["snapshot_id"],
                                   live[5]["example_id"])
        s2 = w.profile.compute()
        rids = {j["example_id"] for j in restricted.values()}
        live_ids = {j["example_id"] for j in live}
        ev_ids = {r[0] for r in w.rows(
            "SELECT example_id FROM profile_evidence WHERE included=1")}
        blob = json.dumps([s1["measured"], s1["cards"], s2["measured"],
                           s2["cards"]])
        words1 = sum(len(j["raw"].split()) for j in live)
        words2 = words1 - len(live[5]["raw"].split())
        m1, m2 = s1["measured"], s2["measured"]
        obs = {"s1": [m1["eligible_examples"], m1["eligible_words"]],
               "s2": [m2["eligible_examples"], m2["eligible_words"],
                      m2["excluded"].get("user_excluded")],
               "restricted_in_evidence": len(rids & ev_ids),
               "cards": [len(s1["cards"]), len(s2["cards"])]}
        phrases1 = {p["phrase"] for p in m1["frequent_phrases"]}
        return check({
            "s1_counts": (m1["eligible_examples"], m1["eligible_words"])
            == (11, words1),
            "s2_counts": (m2["eligible_examples"], m2["eligible_words"])
            == (10, words2) and m2["excluded"].get("user_excluded") == 1,
            "restricted_zero_evidence": not (rids & ev_ids),
            "restricted_zero_cards": not (rids & (_card_ids(s1)
                                                  | _card_ids(s2))),
            "restricted_phrase_absent": "zebra quantum" not in blob,
            "live_phrase_control": "falcon nebula" in phrases1,
            "user_excluded_absent": live[5]["example_id"]
            not in _card_ids(s2) and live[5]["example_id"] not in {
                r[0] for r in w.rows(
                    "SELECT example_id FROM profile_evidence WHERE"
                    " snapshot_id=?", (s2["snapshot_id"],))},
            "cards_rendered": bool(s1["cards"]) and bool(s2["cards"]),
            "live_evidence_only": ev_ids <= live_ids,
        }, obs, witness="deleted-everywhere, expired, quarantined,"
                        " training-excluded, raw-purged and user-excluded"
                        " evidence beside eleven live controls")


@drives("LF-M14-C180")
def c180_snippet_background(entry):
    with MWorld(min_words=50) as w:
        controls = [w.job(_text(f"c{i}x", 15) + (" falcon nebula"
                                                  if i < 2 else ""),
                          audio=False) for i in range(10)]
        snip = [w.job(_text(f"s{i}x", 15) + " zebra quantum",
                      audio=False, snippets=True) for i in range(2)]
        bg_latest = w.job(_text("bgl", 15) + " zebra quantum", audio=False)
        bg_old = w.job(_text("bgo", 15), audio=False)
        bg_abst = w.job(_text("bga", 15), audio=False)
        R = w.review.record_label
        R(bg_latest["example_id"], edit_kind="recognition_error")
        R(bg_latest["example_id"], edit_kind="recognition_error",
          domains=("background_speech",))
        R(bg_old["example_id"], edit_kind="recognition_error",
          domains=("background_speech",))
        R(bg_old["example_id"], edit_kind="recognition_error")
        R(bg_abst["example_id"], edit_kind="recognition_error",
          domains=("background_speech",))
        R(bg_abst["example_id"], edit_kind="ambiguous", abstained=True)
        snap = w.profile.compute()
        m = snap["measured"]
        eligible = controls + [bg_old, bg_abst]
        words = sum(len(j["raw"].split()) for j in eligible)
        ev_ids = {r[0] for r in w.rows(
            "SELECT example_id FROM profile_evidence WHERE snapshot_id=?"
            " AND role='measured'", (snap["snapshot_id"],))}
        phrases = {p["phrase"] for p in m["frequent_phrases"]}
        obs = {"examples": m["eligible_examples"],
               "words": m["eligible_words"], "excluded": m["excluded"]}
        return check({
            "counts_exact": (m["eligible_examples"], m["eligible_words"])
            == (12, words),
            "excluded_counts": m["excluded"].get("snippet_expanded") == 2
            and m["excluded"].get("background_speech") == 1,
            "evidence_exact": ev_ids == {j["example_id"] for j in eligible},
            "excluded_phrase_absent": "zebra quantum" not in phrases,
            "control_phrase_present": "falcon nebula" in phrases,
        }, obs, grading="decision", decision=f"{DECISION}:D01",
            witness="two snippet-expanded; background_speech on the latest"
                    " label (excluded), only on an older label (eligible),"
                    " and under an abstained latest revision (eligible:"
                    " abstention counts as no current label)")


@drives("LF-M14-C181")
def c181_repeat_variants(entry):
    with MWorld(min_words=10) as w:
        base = "Please ship the quarterly report today"
        variants = [
            ("orig", base, "2026-09-20T09:00:00.000Z"),
            ("exact", base, "2026-09-20T10:00:00.000Z"),
            ("case", base.upper(), "2026-09-20T11:00:00.000Z"),
            ("punct", "Please, ship the quarterly report today!",
             "2026-09-20T12:00:00.000Z"),
            ("space", "Please  ship the\tquarterly   report today",
             "2026-09-20T13:00:00.000Z"),
            ("word_diff", "Please ship the quarterly report tomorrow",
             "2026-09-20T14:00:00.000Z"),
            ("reorder", "Please ship today the quarterly report",
             "2026-09-20T15:00:00.000Z"),
        ]
        jobs = {n: w.job(t, audio=False, captured_at=at)
                for n, t, at in variants}
        others = [w.job(_text(f"o{i}x", 12), audio=False,
                        captured_at=f"2026-09-21T0{i}:00:00.000Z")
                  for i in range(3)]
        # Independent oracle: first-seen by capture time, then id.
        order = sorted(list(jobs.values()) + others,
                       key=lambda j: (w.envelope(j["example_id"])[
                           "captured_at_utc"], j["example_id"]))
        seen, kept = set(), []
        for j in order:
            k = _norm_key(j["raw"])
            if k in seen:
                continue
            seen.add(k)
            kept.append(j)
        want_words = sum(len(j["raw"].split()) for j in kept)
        snap = w.profile.compute()
        m = snap["measured"]
        ev_ids = {r[0] for r in w.rows(
            "SELECT example_id FROM profile_evidence WHERE snapshot_id=?"
            " AND role='measured'", (snap["snapshot_id"],))}
        obs = {"examples": m["eligible_examples"],
               "words": m["eligible_words"],
               "repeated": m["excluded"].get("repeated_verbatim"),
               "kept": sorted(n for n, j in jobs.items() if j in kept)}
        return check({
            "oracle_shape": len(kept) == 6 and obs["kept"] == [
                "orig", "reorder", "word_diff"],
            "counts_exact": (m["eligible_examples"], m["eligible_words"])
            == (len(kept), want_words),
            "repeats_counted": m["excluded"].get("repeated_verbatim") == 4,
            "first_seen_kept": ev_ids == {j["example_id"] for j in kept},
        }, obs, witness="exact / case / punctuation / whitespace variants"
                        " dedup to the earliest; changed-word and reordered"
                        " utterances stay (declared: normalized word"
                        " sequence)")


@drives("LF-M14-C182")
def c182_foreign_raw(entry):
    with MWorld(min_words=10) as w:
        a = w.job(f"alpha speaks {A_CANARY} words", audio=False)
        b = w.job(f"bravo speaks {B_CANARY} with more words", audio=False)
        c = w.job("charlie foreign words never spoken by alpha",
                  audio=False, example=False)
        d = w.job("delta points at bravo raw text now", audio=False)
        e = w.job("echo points at its own applied output", audio=False)
        ctrl = w.job("foxtrot control utterance stays", audio=False)
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", c["raw_aid"]))
        w.rewrite_envelope(d["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", b["raw_aid"]))
        w.rewrite_envelope(e["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", e["applied_aid"]))
        snap = w.profile.compute()
        m = snap["measured"]
        ev_ids = {r[0] for r in w.rows(
            "SELECT example_id FROM profile_evidence WHERE snapshot_id=?"
            " AND role='measured'", (snap["snapshot_id"],))}
        want = {b["example_id"], ctrl["example_id"]}
        words = len(b["raw"].split()) + len(ctrl["raw"].split())
        blob = json.dumps(m)
        obs = {"examples": m["eligible_examples"],
               "words": m["eligible_words"],
               "evidence": len(ev_ids)}
        return check({
            "own_speech_only": ev_ids == want,
            "counts_exact": (m["eligible_examples"], m["eligible_words"])
            == (2, words),
            "no_foreign_text": "charlie" not in blob,
        }, obs, grading="decision", decision=f"{DECISION}:D11",
            witness="source_text re-pointed at a non-example job's raw, at"
                    " another example's raw and at the own applied output")


@drives("LF-M14-C183")
def c183_owning_input_changes(entry):
    with MWorld(min_words=20) as w:
        jobs = [w.job(_text(f"k{i}x", 12), audio=False) for i in range(10)]
        for j in jobs[:4]:
            w.review.record_label(j["example_id"],
                                  edit_kind="recognition_error",
                                  origin_stages=("asr",))
        s0 = w.profile.compute()
        idle = w.profile.compute(only_if_changed=True)
        obs = {"idle_skipped": bool(idle.get("skipped"))}
        conds = {"unchanged_idle_skips": bool(idle.get("skipped"))}
        sigs = [s0["measured"]["evidence_signature"]]
        stable = (s0["measured"]["eligible_examples"],
                  s0["measured"]["eligible_words"])

        def step(name):
            s = w.profile.compute(only_if_changed=True)
            if s.get("skipped"):
                conds[f"{name}_recomputed"] = False
                return None
            conds[f"{name}_recomputed"] = True
            m = s["measured"]
            conds[f"{name}_counts_stable"] = (m["eligible_examples"],
                                              m["eligible_words"]) == stable
            conds[f"{name}_signature_moved"] = \
                m["evidence_signature"] not in sigs
            sigs.append(m["evidence_signature"])
            return s

        # (a) source revision: an own new raw transcript, same word count
        tgt = jobs[0]
        new_raw = " ".join(["osprey", "lantern"]
                           + tgt["raw"].split()[2:])
        aid = w.text_artifact(tgt["job_id"], "raw_transcript", new_raw,
                              stage="asr")
        w.rewrite_envelope(tgt["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", aid))
        tail = jobs[1]
        aid2 = w.text_artifact(tail["job_id"], "raw_transcript",
                               " ".join(["osprey", "lantern"]
                                        + tail["raw"].split()[2:]),
                               stage="asr")
        w.rewrite_envelope(tail["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("source_text", aid2))
        sa = step("revision")
        conds["revision_output_reacts"] = bool(sa) and "osprey lantern" in {
            p["phrase"] for p in sa["measured"]["frequent_phrases"]}
        # (b) latest label changes kind (count of labeled stays 4)
        w.review.record_label(jobs[2]["example_id"],
                              edit_kind="style_preference",
                              origin_stages=("cleanup",))
        sb = step("label")
        conds["label_output_reacts"] = bool(sb) and sb["measured"][
            "corrections_by_kind"] == {"recognition_error": 3,
                                       "style_preference": 1}
        # (c) exclusion plus a same-size newcomer (overall counts stable)
        last = sb or sa or s0
        w.profile.exclude_evidence(last["snapshot_id"],
                                   jobs[5]["example_id"])
        w.job(_text("newcomer", 12), audio=False)
        sc = step("exclusion")
        conds["exclusion_output_reacts"] = bool(sc) and \
            sc["measured"]["excluded"].get("user_excluded") == 1 and \
            jobs[5]["example_id"] not in {r[0] for r in w.rows(
                "SELECT example_id FROM profile_evidence WHERE"
                " snapshot_id=?", (sc["snapshot_id"],))}
        # (d) a label change committed between the read and publication
        seam = {"read": 0, "fired": 0}

        def wrap(original):
            def read(self, conn, example_ids):
                seam["read"] += 1
                return original(self, conn, example_ids)
            return read

        def hook():
            if seam["read"] and not seam["fired"]:
                seam["fired"] += 1
                w.review.record_label(jobs[3]["example_id"],
                                      edit_kind="punctuation_or_structure",
                                      origin_stages=("cleanup",))
        with patched(type(w.profile), "_read_candidates", wrap), \
                after_each_op(w.store, hook):
            sd = w.profile.compute()
        if not seam["fired"]:
            return invalid("read/publication seam never reached", obs)
        conds["fence_publishes_current_label"] = sd["measured"][
            "corrections_by_kind"] == {"recognition_error": 2,
                                       "style_preference": 1,
                                       "punctuation_or_structure": 1}
        obs.update(stable=list(stable), seam=seam,
                   signatures=len(set(sigs)),
                   kinds=sd["measured"]["corrections_by_kind"])
        return check(conds, obs, grading="decision",
                     decision=f"{DECISION}:D16",
                     witness="idle recompute skipped when unchanged; source"
                             " revision, latest label and exclusion changes"
                             " at stable counts each recompute with a new"
                             " evidence signature; label committed between"
                             " read and write op (after_each_op seam)")


# =============================================================================
# stateful probes
# =============================================================================


@drives("LF-M14-S022")
def s022_offline_validator_without_db(entry):
    latch = Latch("m14_s022_authority_boundary", block=False)
    runs = {}
    tmps = []
    try:
        for order in ("control_db_present", "move_then_deny",
                      "deny_then_move"):
            w, fx, out, err = _built_world_with_export()
            away = tempfile.TemporaryDirectory(prefix="m14f-s022-")
            cwd = tempfile.TemporaryDirectory(prefix="m14f-s022cwd-")
            tmps += [away, cwd]
            try:
                if out is None:
                    return invalid(f"positive export refused: {err}")
                facts = _facts(w, fx)
                pack = pathlib.Path(away.name) / "pack"
                if order == "deny_then_move":
                    _hide_db(w)
                    shutil.move(str(w.tmp / "ds"), str(pack))
                else:
                    w.store.close()
                    shutil.move(str(w.tmp / "ds"), str(pack))
                    latch.hit()  # after valid export is closed and moved
                    if order == "move_then_deny":
                        _hide_db(w)
                db_present = (w.tmp / "v2.db").exists()
                probe = w.tmp / hidden_probe(w)
                aud = _run_validator_audited([pack], cwd.name,
                                             forbid=[w.tmp], probe=probe)
                if "error" in aud:
                    return invalid("audit wrapper failed", aud)
                r = aud["runs"][0]
                runs[order] = {
                    "rc": r["code"], "db_present": db_present,
                    "store_reads": len(r["forbidden_opens"]),
                    "sqlite": r["sqlite"], "network": r["network"],
                    "probe_seen": aud["probe_seen"],
                    "counts": r["stdout"].splitlines()[-1]
                    if r["stdout"] else None,
                    "reconstruct": _reconstruct(pack, facts)}
            finally:
                w.close()
        if not latch.reached.is_set():
            return invalid("barrier never reached", runs)
        if not all(v["probe_seen"] for v in runs.values()):
            return invalid("audit oracle inactive", runs)
        return check({
            "all_valid": all(v["rc"] == 0 for v in runs.values()),
            "no_store_or_db_reads": all(not v["store_reads"]
                                        and not v["sqlite"]
                                        for v in runs.values()),
            "no_network": all(not v["network"] for v in runs.values()),
            "db_denied_in_variants": not runs["move_then_deny"][
                "db_present"] and not runs["deny_then_move"]["db_present"]
            and runs["control_db_present"]["db_present"],
            "same_result_every_order": len({v["counts"] for v in
                                            runs.values()}) == 1,
            "reconstructs": all(not v["reconstruct"]
                                for v in runs.values()),
        }, runs, reached=latch.hits,
            witness="latch after close+move; DB renamed after (and, in the"
                    " alternate order, before) the move; control keeps the"
                    " DB; audited validator subprocess from another cwd")
    finally:
        for t in tmps:
            t.cleanup()


def _s028_mutations():
    def foreign_audio(w, fx):
        a, b = fx["asr"][0], fx["asr"][1]
        w.rewrite_envelope(a["example_id"], lambda env: env[
            "artifact_ids"].__setitem__("original_audio", b["audio_aid"]))
        return "asr_supervised", a["example_id"]

    def blocking_label(w, fx):
        a = fx["asr"][0]
        w.review.record_label(a["example_id"], edit_kind="changed_intent",
                              origin_stages=("user_intent",))
        return "asr_supervised", a["example_id"]

    def cleanup_source_purged(w, fx):
        c = fx["clean_full"]
        w.purge(c["raw_aid"])
        return "cleanup_supervised", c["example_id"]

    def transform_rejected(w, fx):
        t = fx["transform"]
        c = t["candidates"][0]["candidate_id"]
        w.accept(t, c, "reject")
        return "transform_supervised", (t["task_key"], c)

    def pref_source_purged(w, fx):
        p = fx["pref"]
        for c in p["candidates"]:
            w.purge(c["source_aid"])
        return "preference_pairs", p["task_key"]
    return {"foreign_audio": foreign_audio,
            "blocking_label": blocking_label,
            "cleanup_source_purged": cleanup_source_purged,
            "transform_rejected": transform_rejected,
            "pref_source_purged": pref_source_purged}


@drives("LF-M14-S028")
def s028_readiness_export_parity(entry):
    latch = Latch("m14_s028_authority_boundary", block=False)
    base = {"asr_supervised": 10, "cleanup_supervised": 2,
            "transform_supervised": 1, "preference_pairs": 1}
    obs, conds = {}, {}
    plans = [("control", None, "after_assign")] + [
        (name, fn, order) for name, fn in _s028_mutations().items()
        for order in ("after_assign", "before_assign")]
    for name, fn, order in plans:
        with MWorld() as w:
            fx = _seed_all(w)
            if order == "after_assign":
                w.splits.assign()
                latch.hit()  # common positive cohort/assignment seeded
            mutated = fn(w, fx) if fn else None
            if order == "before_assign":
                w.splits.assign()
            p, err, _o = _parity(w, "ds")
            key = f"{name}/{order}"
            if p is None:
                obs[key] = {"export_refused": err}
                conds[f"{key}_exported"] = False
                continue
            want = dict(base)
            if mutated:
                want[mutated[0]] -= 1
            obs[key] = {"ready": p["ready"], "exported": p["exported"]}
            conds[f"{key}_parity"] = p["ready"] == p["exported"] == want
            conds[f"{key}_tiers"] = p["tiers_ready"] == p["mem"]["tiers"]
            if mutated:
                conds[f"{key}_member_removed"] = \
                    mutated[1] not in p["mem"][mutated[0]]
    if not latch.reached.is_set():
        return invalid("barrier never reached", obs)
    return check(conds, obs, reached=latch.hits,
                 witness="one gate-breaking mutation per world, applied"
                         " after (and, alternately, before) the"
                         " assignment; readiness counts vs export"
                         " membership vs literal counts")


# =============================================================================
# metamorphic relation
# =============================================================================


@drives("LF-M14-MR014")
def mr014_pack_relocation(entry):
    w, fx, out, err = _built_world_with_export()
    away = tempfile.TemporaryDirectory(prefix="m14f-mr014-")
    cwd = tempfile.TemporaryDirectory(prefix="m14f-mr014cwd-")
    try:
        if out is None:
            return invalid(f"positive export refused: {err}")
        facts = _facts(w, fx)
        src = w.tmp / "ds"
        before = _run_validator_plain(src, cwd.name)
        rec_before = {n: sha256_file(src / n) for n in (
            "examples.jsonl", "references.jsonl", "preferences.jsonl",
            "dataset_manifest.json")}
        fp_before = json.loads((src / "dataset_manifest.json")
                               .read_text())["content_fingerprint"]
        tmp_marks = [str(w.tmp).encode(), os.path.realpath(
            w.tmp).encode()]
        path_hits = [p.name for p in src.rglob("*") if p.is_file()
                     and any(m in p.read_bytes() for m in tmp_marks)]
        _hide_db(w)
        dest = pathlib.Path(away.name) / "a" / "b" / "moved-pack"
        dest.parent.mkdir(parents=True)
        shutil.move(str(src), str(dest))
        probe = w.tmp / hidden_probe(w)
        aud = _run_validator_audited([dest], cwd.name, forbid=[w.tmp],
                                     probe=probe)
        if "error" in aud:
            return invalid("audit wrapper failed", aud)
        after = aud["runs"][0]
        rec_after = {n: sha256_file(dest / n) for n in rec_before}
        ex, refs, prefs = _records(dest)
        fp_after_recomputed = _fingerprint(ex, refs, prefs)
        obs = {"before": before["valid_line"], "after_rc": after["code"],
               "counts_before": before["stdout"].splitlines()[-1],
               "counts_after": after["stdout"].splitlines()[-1]
               if after["stdout"] else None,
               "path_hits": path_hits,
               "store_reads": len(after["forbidden_opens"]),
               "probe_seen": aud["probe_seen"]}
        if not aud["probe_seen"]:
            return invalid("audit oracle inactive", obs)
        return check({
            "valid_before": before["code"] == 0,
            "valid_after": after["code"] == 0,
            "same_counts": obs["counts_before"] == obs["counts_after"],
            "records_byte_identical": rec_before == rec_after,
            "fingerprint_stable": fp_after_recomputed == fp_before,
            "no_absolute_origin_paths": not path_hits,
            "no_store_reads": not after["forbidden_opens"]
            and not after["sqlite"],
            "tasks_reconstruct": not _reconstruct(dest, facts),
        }, obs, witness="validated in place, then moved three levels deep"
                        " under another temp root with the DB renamed;"
                        " fingerprint recomputed by this driver")
    finally:
        w.close()
        away.cleanup()
        cwd.cleanup()
