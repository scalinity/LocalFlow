"""M09 audit corpus runner: the 135 supplied cases and 14 metamorphic
relations, executed on the current tree.

The supplied corpus is frozen byte-for-byte in ``m09_audit_corpus.json``
(sha256 below) and stays NOT_RUN: outcomes go to a separate results
file keyed by case id and stamped with the code SHA, the environment,
the corpus hash, the adjudicated policy revision and this runner's
oracle version.

Every case maps to exactly one of:

- a DRIVER here (or a regression in ``test_m09_remediation.py``) that
  runs the case's schedule over synthetic fixtures through the real Hub
  actions / HubState / services / coordinator, with an oracle derived
  from the fixture definition — PASS or FAIL;
- NARROWED — a driver ran the automatable part of the oracle and the
  named remainder needs a native or human observation (the remainder
  is stated, never counted as passed);
- MANUAL_PENDING — Daniel's check (the M09-V00x runbook entry);
- BLOCKED — cannot run here, with the reason.

A driver that crashes or cannot reach its oracle records ERROR — never a
pass. Statuses are counted only from what ran in this process.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/ui/m09_corpus_runner.py --json OUT [-k CASE_OR_MR]
         [--only ID,ID,...]   (exact case ids; relations are skipped)
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import platform
import subprocess
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "lifecycle"))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))


from m09_world import code_stamp  # noqa: E402

CORPUS = HERE.parent / "m09_audit_corpus.json"
CORPUS_SHA256 = \
    "a00f6618121e9881592be7d25cb4a03696ab298af9c16eefda8df697399dbcb8"
ORACLE_VERSION = "m09-corpus-oracles-r1"
# The adjudicated policies the oracles assume (docs/v2/contracts/hub.md,
# M09 remediation addendum): per-key query generations; delete-
# everywhere removes a job from History; explicit-offset timestamps
# accepted, zone-less ones Undated; a replay request for another item
# stops the current one; the listening gate is a successful playback
# START; queued insertion work defers Hub activation, a pending
# clipboard payload does not.
POLICY_REVISION = "m09-policy-r1"

# Registries, decorators and every driver live in m09_drivers.py (one
# module object, so registrations are never lost to a __main__ copy).
from m09_drivers import (CASE_DRIVERS, DEPENDENCIES, MR_DRIVERS,  # noqa: E402
                         Narrowed)


# ---- runner ----------------------------------------------------------------

def _environment():
    def sh(*a):
        p = subprocess.run(a, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    return {"mac_model": sh("sysctl", "-n", "hw.model"),
            "chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "macos": platform.mac_ver()[0],
            "python": sys.version.split()[0],
            "dispatcher": "m09_world.MainQueue (callAfter queued, drained"
                          " on the script's main thread)",
            "desktop_isolation": "tests/v2/context/run_isolated.py"}


def _run_one(fn):
    t0 = time.monotonic()
    try:
        evidence = fn() or {}
        return {"status": "PASS", "detail": None, "evidence": evidence,
                "seconds": round(time.monotonic() - t0, 3)}
    except Narrowed as e:
        return {"status": "NARROWED", "detail": str(e)[:600],
                "remainder": e.remainder,
                "seconds": round(time.monotonic() - t0, 3)}
    except AssertionError as e:
        last = traceback.extract_tb(e.__traceback__)[-1]
        return {"status": "FAIL", "detail": str(e)[:600],
                "where": f"{pathlib.Path(last.filename).name}:{last.lineno}"
                         f" {last.line}",
                "seconds": round(time.monotonic() - t0, 3)}
    except Exception as e:
        traceback.print_exc()
        return {"status": "ERROR",
                "detail": f"{type(e).__name__}: {e}"[:600],
                "seconds": round(time.monotonic() - t0, 3)}


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = argv[argv.index("-k") + 1] if "-k" in argv else None
    exact = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    raw = CORPUS.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == CORPUS_SHA256, f"frozen corpus changed: {sha}"
    corpus = json.loads(raw)
    if "--unmapped" in argv:
        ids = [c["id"] for c in corpus["cases"]
               if c["id"] not in CASE_DRIVERS and c["id"] not in DEPENDENCIES]
        print(" ".join(ids) or "all cases mapped", len(ids))
        return 0
    results = {}
    for c in corpus["cases"]:
        cid = c["id"]
        if (only and only not in cid) or (exact and cid not in exact):
            continue
        rec = {"name": c["name"], "finding_ids": c["finding_ids"],
               "corpus_environment": c["environment"]}
        if cid in DEPENDENCIES:
            status, reason = DEPENDENCIES[cid]
            rec.update({"status": status, "detail": reason,
                        "environment_run": None})
        elif cid in CASE_DRIVERS:
            fn, env = CASE_DRIVERS[cid]
            rec.update(_run_one(fn))
            rec["environment_run"] = env
        else:
            rec.update({"status": "NOT_RUN",
                        "detail": "no driver implemented"})
        results[cid] = rec
        note = " ".join(str(rec[k]) for k in ("detail", "where")
                        if rec.get(k))
        print(f"{rec['status']:<14} {cid} {c['name']}"
              + (f" — {note}" if rec["status"] != "PASS" and note else ""),
              flush=True)
    relations = {}
    for mr in corpus["metamorphic_relations"]:
        mid = mr["id"]
        if (only and only not in mid) or exact:
            continue
        fn = MR_DRIVERS.get(mid)
        rec = {"name": mr["name"], "case_ids": mr["case_ids"]}
        rec.update(_run_one(fn) if fn else
                   {"status": "NOT_RUN", "detail": "no driver"})
        relations[mid] = rec
        print(f"{rec['status']:<14} {mid} {mr['name']}", flush=True)
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    mr_counts = {}
    for r in relations.values():
        mr_counts[r["status"]] = mr_counts.get(r["status"], 0) + 1
    print(f"cases: {counts}  relations: {mr_counts}")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "schema_version": 1,
            "runner": "tests/v2/ui/m09_corpus_runner.py",
            "corpus": "tests/v2/ui/m09_audit_corpus.json",
            "corpus_sha256": sha,
            "oracle_version": ORACLE_VERSION,
            "policy_revision": POLICY_REVISION,
            **code_stamp("tests/v2/ui/m09_corpus_runner.py"),
            "environment": _environment(),
            "case_counts": counts, "relation_counts": mr_counts,
            "cases": results, "relations": relations,
        }, indent=1, ensure_ascii=False) + "\n")
    bad = sum(counts.get(s, 0) for s in ("FAIL", "ERROR", "NOT_RUN")) + \
        sum(mr_counts.get(s, 0) for s in ("FAIL", "ERROR", "NOT_RUN"))
    return 0 if bad == 0 else 1


if __name__ == "__main__":

    raise SystemExit(main(sys.argv[1:]))
