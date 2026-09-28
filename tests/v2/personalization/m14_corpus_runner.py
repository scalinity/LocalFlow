"""M14 corpus runner: every frozen case, stateful probe and metamorphic
relation through its bound driver (tests/v2/personalization/
m14_drivers_*.py, protocol in m14_drivers_common.py).

The frozen corpus (tests/v2/personalization/m14_audit_corpus.json) is
verified by sha256 and never modified; results are written to a
separate run record keyed by entry id and stamped with the code SHA, the
driver file hashes and the decision record. Per entry: id, category,
kind, finding ids, policy flag, status (PASS / FAIL / ERROR / INVALID /
NOT_APPLICABLE / NOT_RUN), grading, the adopted decision for a
policy-gated entry, observed values, the witness and any note. A driver
exception is ERROR, never the defect it failed to reach; NOT_RUN,
INVALID and NOT_APPLICABLE are never PASS. Native entries are graded
from ``--native`` (the owned-window suite's record) and performance
entries from ``--bench`` (the benchmark record); without them they are
NOT_RUN.

  .venv/bin/python tests/v2/context/run_isolated.py \\
      tests/v2/personalization/m14_corpus_runner.py --out RECORD.json \\
      [--native NATIVE.json] [--bench BENCH.json] [--only ID,...]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
import m14_drivers_common as C  # noqa: E402

CORPUS = HERE.parent / "m14_audit_corpus.json"
CORPUS_SHA = "83c6462496e8a581987fbf9c730df9d49a95d4d0fed4505ed60776dc5fe27cb1"
DECISIONS = W.ROOT / "docs/v2/acceptance/M14/remediation/decisions.json"
DRIVER_VERSION = "m14-drivers-r1"
DRIVER_MODULES = ("m14_drivers_a", "m14_drivers_b", "m14_drivers_c",
                  "m14_drivers_d", "m14_drivers_e", "m14_drivers_f",
                  "m14_drivers_g", "m14_drivers_h")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run_entry(reg, entry_id, entry):
    drv = reg.get(entry_id)
    if drv is None:
        return {"status": "NOT_RUN", "note": "no driver bound"}
    t0 = time.monotonic()
    try:
        r = dict(drv(entry))
    except Exception as e:  # noqa: BLE001
        r = {"status": "ERROR",
             "note": f"{type(e).__name__}: {e}"[:300] + " | "
             + traceback.format_exc()[-900:]}
    r["seconds"] = round(time.monotonic() - t0, 2)
    r["driver"] = getattr(drv, "__name__", "?")
    if r.get("note"):
        r["note"] = redact(str(r["note"]))
    return r


def redact(text):
    """Records carry repository-relative names only."""
    import re
    import tempfile
    tmp = tempfile.gettempdir()
    for real, mark in ((str(W.ROOT), "<repo>"), ("/private" + tmp, "<tmp>"),
                       (tmp, "<tmp>"), (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


def tally(rows, key="status"):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--native")
    ap.add_argument("--bench")
    ap.add_argument("--only")
    ap.add_argument("--modules", help="driver module letters (a,b,…);"
                                      " default all")
    args = ap.parse_args(argv)
    corpus_sha = sha256(CORPUS)
    if corpus_sha != CORPUS_SHA:
        sys.exit(f"frozen corpus changed ({corpus_sha}); refusing")
    corpus = json.loads(CORPUS.read_text())
    loaded, missing = [], []
    modules = DRIVER_MODULES if not args.modules else tuple(
        f"m14_drivers_{m.strip()}" for m in args.modules.split(","))
    for name in modules:
        try:
            importlib.import_module(name)
            loaded.append(name)
        except ModuleNotFoundError as e:
            if e.name != name:
                raise
            missing.append(name)
    if args.native:
        C.NATIVE.update(json.loads(pathlib.Path(args.native).read_text()))
    if args.bench:
        C.BENCH.update(json.loads(pathlib.Path(args.bench).read_text()))
    decisions = json.loads(DECISIONS.read_text())
    only = set(args.only.split(",")) if args.only else None

    def selected(eid):
        return only is None or eid in only

    cases = []
    for case in corpus["cases"]:
        if not selected(case["id"]):
            continue
        r = run_entry(C.DRIVERS, case["id"], case)
        rec = {"id": case["id"], "category": case["category"],
               "kind": case["kind"], "title": case["title"],
               "finding_ids": case["finding_ids"],
               "policy_adjudication_required":
                   case["policy_adjudication_required"], **r}
        cases.append(rec)
        print(f"{rec['status']:14} {case['id']} [{case['category']}]"
              + (f" — {str(rec.get('note'))[:140]}"
                 if rec["status"] != "PASS" and rec.get("note") else ""),
              flush=True)
    probes = []
    for p in corpus["stateful_probes"]:
        if not selected(p["id"]):
            continue
        r = run_entry(C.PROBES, p["id"], p)
        probes.append({"id": p["id"], "category": p["category"],
                       "finding_ids": p["finding_ids"],
                       "barrier": p["barrier"]["name"], **r})
        print(f"{r['status']:14} {p['id']} [probe]"
              + (f" — {str(r.get('note'))[:140]}"
                 if r["status"] != "PASS" and r.get("note") else ""),
              flush=True)
    relations = []
    for rel in corpus["metamorphic_relations"]:
        if not selected(rel["id"]):
            continue
        r = run_entry(C.RELATIONS, rel["id"], rel)
        relations.append({"id": rel["id"], "category": rel["category"],
                          "finding_ids": rel["finding_ids"], **r})
        print(f"{r['status']:14} {rel['id']} [relation]"
              + (f" — {str(r.get('note'))[:140]}"
                 if r["status"] != "PASS" and r.get("note") else ""),
              flush=True)
    by_kind = {}
    for c in cases:
        k = by_kind.setdefault(c["kind"], {})
        k[c["status"]] = k.get(c["status"], 0) + 1
    grading = tally([c for c in cases if c["status"] == "PASS"
                     and c.get("grading")], "grading")
    record = {
        "schema": "m14-corpus-run", "driver_version": DRIVER_VERSION,
        "decision_record": decisions["policy_id"],
        "corpus": {"path": "tests/v2/personalization/m14_audit_corpus.json",
                   "sha256": corpus_sha},
        "code": W.code_stamp(
            "tests/v2/personalization/m14_corpus_runner.py"),
        "drivers_loaded": loaded, "drivers_missing": missing,
        "drivers_sha256": {p.name: sha256(p) for p in sorted(
            HERE.parent.glob("m14_*.py"))},
        "native_record": args.native and pathlib.Path(args.native).name,
        "bench_record": args.bench and pathlib.Path(args.bench).name,
        "counts": {"cases": tally(cases), "cases_by_kind": by_kind,
                   "probes": tally(probes), "relations": tally(relations),
                   "pass_grading": grading},
        "cases": cases, "probes": probes, "relations": relations}
    pathlib.Path(args.out).write_text(json.dumps(record, indent=1,
                                                 default=str))
    print("cases:", record["counts"]["cases"], "| by kind:", by_kind)
    print("probes:", record["counts"]["probes"], "| relations:",
          record["counts"]["relations"], "| pass grading:", grading)
    return 0


if __name__ == "__main__":
    sys.exit(main())
