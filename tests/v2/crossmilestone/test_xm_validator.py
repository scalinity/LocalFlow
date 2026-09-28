"""GATE-G09 — the offline package validator decides from the package
alone (cross-milestone remediation of 340c566; Audit C TEST-GAP-09,
Audit B CROSS-AUDIT-08/15).

A real synthetic export (the M14 world: 12 ASR families with audio, one
assignment) is COPIED out of its world, the world (its store, artifacts
and folders) is deleted, and ``scripts/v2/validate_dataset.py`` runs in
a separate process from an unrelated directory with an empty HOME — no
store, no artifacts, no source data reachable. The untouched copy must
validate; each single-fault variant must not. Crash/restart publication
is MERGED-X14 (test_xm_remediation.py).

Run:
  .venv/bin/python tests/v2/crossmilestone/test_xm_validator.py [--json OUT]
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402

ROOT = X.ROOT
CLI = ROOT / "scripts" / "v2" / "validate_dataset.py"


def validate_offline(package, workdir):
    home = pathlib.Path(workdir) / "empty-home"
    home.mkdir(exist_ok=True)
    elsewhere = pathlib.Path(workdir) / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    p = subprocess.run([sys.executable, str(CLI), str(package)],
                       capture_output=True, text=True, cwd=str(elsewhere),
                       env={**os.environ, "HOME": str(home)}, timeout=120)
    return p.returncode, p.stdout


def resum(pkg):
    lines = []
    for f in sorted(pkg.rglob("*")):
        if f.is_file() and f.name != "SHA256SUMS.txt":
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}"
                         f"  {f.relative_to(pkg).as_posix()}")
    (pkg / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")


def tamper_manifest(pkg):
    m = json.loads((pkg / "dataset_manifest.json").read_text())
    m["export_id"] = "export-forged"
    (pkg / "dataset_manifest.json").write_text(json.dumps(m))


def tamper_text_resummed(pkg):
    """Change the included verbatim reference text (asr_supervised keeps
    its text in references.jsonl) and recompute every checksum around the
    change: only the semantic lineage check can catch it."""
    path = pkg / "references.jsonl"
    before = path.read_text()
    rows = [json.loads(line) for line in before.splitlines()
            if line.strip()]
    changed = False
    for r in rows:
        if isinstance(r.get("text"), str) and r["text"]:
            r["text"] = r["text"] + " altered"
            changed = True
            break
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert changed and path.read_text() != before, \
        "fixture: the tamper changed nothing"
    resum(pkg)  # the checksums follow the change: semantics must catch it


def bad_hash(pkg):
    s = (pkg / "SHA256SUMS.txt").read_text().splitlines()
    s[0] = "0" * 64 + s[0][64:]
    (pkg / "SHA256SUMS.txt").write_text("\n".join(s) + "\n")


def missing_audio(pkg):
    wavs = sorted((pkg / "artifacts").glob("*.wav"))
    assert wavs, "fixture: no exported audio"
    wavs[0].unlink()


def malformed_path(pkg):
    with open(pkg / "SHA256SUMS.txt", "a") as f:
        f.write("0" * 64 + "  ../outside.txt\n" + "0" * 64
                + "  /etc/hosts\n")


def unrelated_file(pkg):
    (pkg / "notes-from-elsewhere.txt").write_text("unrelated")


VARIANTS = {"tampered_manifest": tamper_manifest,
            "tampered_text_with_recomputed_sums": tamper_text_resummed,
            "bad_hash": bad_hash, "missing_audio": missing_audio,
            "malformed_paths": malformed_path,
            "unrelated_file": unrelated_file}


def main(argv):
    out = None
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
    results = {}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        with X.M.MWorld() as w:
            w.families(12, asr=True)
            w.splits.assign()
            w.exporter.build(w.tmp / "ds", task_views=("asr_supervised",))
            shutil.copytree(w.tmp / "ds", td / "pristine")
        # The world — store, artifacts, everything the export came from —
        # is gone now: only the package copy remains.
        code, text = validate_offline(td / "pristine", td)
        results["control_store_and_source_gone"] = {
            "exit": code, "valid": code == 0}
        for name, fn in VARIANTS.items():
            pkg = td / name
            shutil.copytree(td / "pristine", pkg)
            fn(pkg)
            code, text = validate_offline(pkg, td)
            results[name] = {"exit": code, "valid": code == 0,
                             "first_issue": next(
                                 (ln.strip() for ln in text.splitlines()
                                  if ln.strip().startswith("-")), None)}
    ok = results["control_store_and_source_gone"]["valid"] and not any(
        r["valid"] for k, r in results.items()
        if k != "control_store_and_source_gone")
    for k, r in results.items():
        print(f"{'valid  ' if r['valid'] else 'invalid'}  {k}"
              + (f"  — {r.get('first_issue')}" if r.get("first_issue")
                 else ""))
    print("xm validator:", "PASS" if ok else "FAIL")
    if out:
        pathlib.Path(out).write_text(json.dumps({
            "kind": "xm_offline_validator_matrix",
            "status": "PASS" if ok else "FAIL", "results": results,
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_validator.py")},
            indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
