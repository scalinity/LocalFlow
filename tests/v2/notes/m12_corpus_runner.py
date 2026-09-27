"""Run the frozen M12 adversarial corpus against the current code.

    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/notes/m12_corpus_runner.py [--json OUT] [--only IDS]
        [--native NATIVE_RECORD.json] [--skip-perf] [--quiet]

The corpus file is verified byte-identical (sha256) before anything
runs; results, bindings and code stamps go to separate files. Every
case is bound to a driver (``m12_drivers*.py``); a case without a
binding is NOT_RUN and counted as such, never as a pass.

- Portable and stateful cases run here. A stateful case passes only
  when every declared barrier was reached under its own name, under the
  name the adjudication binds it to, or is bound as structural.
- Native cases (N001–N012) are graded from the native qualification
  record (``--native``): PASS only when that record passed the case on
  the SAME production tree (``git rev-parse HEAD:localflow``) with a
  clean production tree; otherwise NOT_RUN with the reason.
- Performance cases (B001–B010) are work-VALIDITY checks: the
  benchmark's independent oracles hold AND the matching ``--noop``
  variant is rejected as invalid (exit 3). Timing is qualified by the
  separate isolated benchmark run, never here.
- The 14 metamorphic relations run here (``MR``).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
ROOT = HERE.parents[3]

CORPUS = HERE.parent / "m12_audit_corpus.json"
CORPUS_SHA256 = \
    "0c1e9cc51d82da29e1e4d3ad91097a8532a9c078eb6c3ce31ca1509349fc5be9"
ORACLE_VERSION = "m12-corpus-oracles-r1"
ADJ_PATH = ROOT / "docs" / "v2" / "acceptance" / "M12" / "remediation" \
    / "adjudications.json"
BENCH = ROOT / "scripts" / "v2" / "benchmark_m12.py"

import m12_world as w  # noqa: E402
import m12_drivers as drivers  # noqa: E402
import m12_drivers_b  # noqa: E402,F401
import m12_drivers_c  # noqa: E402,F401
import test_m12_remediation as rem  # noqa: E402

from localflow.v2 import notes as notes_mod  # noqa: E402
from localflow.v2.notes import (ORIGIN_DICTATED, ORIGIN_TYPED,  # noqa: E402
                                TRIGGER_AUTOSAVE, TRIGGER_SYSTEM)

Outcome = drivers.Outcome


def git(*a):
    p = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True,
                       text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def production_tree():
    return {"localflow_tree": git("rev-parse", "HEAD:localflow"),
            "production_tree_modified": bool(git(
                "status", "--porcelain", "--untracked-files=no", "--",
                "localflow"))}


# ---- performance: benchmark validity ------------------------------------------

_BENCH_CACHE = {}


def bench(*args):
    key = tuple(args)
    if key not in _BENCH_CACHE:
        p = subprocess.run([sys.executable, str(BENCH), "--runs", "3",
                            *args], capture_output=True, text=True,
                           timeout=900)
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            doc = None
        _BENCH_CACHE[key] = (p.returncode, doc)
    return _BENCH_CACHE[key]


PERF = {"LF-M12-B001": (["note_open_10k", "note_open_cold"], "open"),
        "LF-M12-B002": (["search_200_notes"], "search"),
        "LF-M12-B003": (["autosave_commit"], "save"),
        "LF-M12-B004": (["snapshot_explicit"], "save"),
        "LF-M12-B005": (["restore"], "restore"),
        "LF-M12-B006": (["dirty_note_switch"], "switch"),
        "LF-M12-B007": (["dictated_save"], "dictation"),
        "LF-M12-B008": (["version_headers_200", "version_headers_201"],
                        "open"),
        "LF-M12-B009": (["export_markdown", "export_plain"], "export"),
        "LF-M12-B010": (["autosave_commit_during_search"], None)}


def perf_driver(case):
    comps, noop = PERF[case["id"]]
    rc, doc = bench()
    if doc is None:
        return Outcome("ERROR", {}, note="benchmark produced no record")
    val = doc.get("validity") or {}
    checks = {f"valid:{c}": bool((val.get(c) or {}).get("valid"))
              for c in comps}
    checks["run_not_invalid"] = rc in (0, 2)
    if noop:
        nrc, ndoc = bench("--noop", noop)
        checks[f"noop_{noop}_rejected"] = nrc == 3 and bool(
            ndoc and ndoc.get("verdict") == "INVALID_WORK")
    return drivers.verdict(checks, {"validity": {c: val.get(c)
                                                 for c in comps}})


# ---- native: graded from the native record ----------------------------------

NATIVE = {}


def native_driver(case):
    rec = NATIVE.get("record")
    if rec is None:
        return Outcome("NOT_RUN", {}, note="no native record supplied")
    here = production_tree()
    if rec.get("localflow_tree") != here["localflow_tree"] \
            or rec.get("production_tree_modified") \
            or here["production_tree_modified"]:
        return Outcome("NOT_RUN", {"record_tree": rec.get("localflow_tree"),
                                   "tree": here["localflow_tree"]},
                       note="native record is for another production tree")
    got = next((c for c in rec.get("cases", [])
                if c.get("corpus_id") == case["id"]), None)
    if got is None:
        return Outcome("NOT_RUN", {}, note="case absent from native record")
    return Outcome(got["status"], {"native_case": got.get("id"),
                                   "tier": got.get("tier")},
                   note=got.get("note", ""))


# ---- metamorphic relations ------------------------------------------------------

MR = {}


def mr(mid):
    def deco(fn):
        MR[mid] = fn
        return fn
    return deco


def _passes(*cids):
    return all(drivers.DRIVERS[c](CASEMAP[c]).status == "PASS"
               for c in cids)


@mr("LF-M12-MR01")
def mr01():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("seed")["note_id"]
        for t, o in (("seed typed", ORIGIN_TYPED),
                     ("seed typed X", ORIGIN_DICTATED)):
            before = nw.revisions(n)
            nw.notes.append_revision(n, t, origin=o, trigger=TRIGGER_SYSTEM,
                                     inserted_at_chars=len(before[-1][4]),
                                     inserted_text=t[len(before[-1][4]):])
            if nw.revisions(n)[:len(before)] != before:
                return False
        before = nw.revisions(n)
        nw.notes.restore(n, before[0][0])
        return nw.revisions(n)[:len(before)] == before


@mr("LF-M12-MR02")
def mr02():
    return _passes("LF-M12-S003", "LF-M12-C065", "LF-M12-C053")


@mr("LF-M12-MR03")
def mr03():
    return _passes("LF-M12-C062", "LF-M12-C059", "LF-M12-C061")


@mr("LF-M12-MR04")
def mr04():
    return _passes("LF-M12-C057")


@mr("LF-M12-MR05")
def mr05():
    return _passes("LF-M12-C125", "LF-M12-S011", "LF-M12-C117",
                   "LF-M12-S010")


@mr("LF-M12-MR06")
def mr06():
    return _passes(*[c for c in CASEMAP if c.startswith("LF-M12-C0")
                     and 66 <= int(c[-3:]) <= 83])


@mr("LF-M12-MR07")
def mr07():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("")["note_id"]
        nw.notes.append_revision(n, "alpha beta", origin=ORIGIN_DICTATED,
                                 trigger=TRIGGER_SYSTEM,
                                 source_job_id="job-synthetic",
                                 inserted_at_chars=0,
                                 inserted_text="alpha beta")
        for t in ("alpha beta gamma", "alpha beta gamma delta",
                  "alpha beta GAMMA delta"):
            nw.notes.append_revision(n, t, origin=ORIGIN_TYPED,
                                     trigger=TRIGGER_AUTOSAVE)
            rev = rem._latest(nw, n)
            owned = drivers.spans_of(rev["content"], rev["spans"],
                                     ORIGIN_DICTATED)
            if owned != ["alpha", "beta"]:
                return False
        return True


@mr("LF-M12-MR08")
def mr08():
    return _passes("LF-M12-C009", "LF-M12-C121")


@mr("LF-M12-MR09")
def mr09():
    with w.NoteWorld() as nw:
        n = nw.notes.create_note("r")["note_id"]
        rid = "nrev-synthetic-retry"
        hold = w.WriterHold(nw.store)
        try:
            with w.short_submit_timeout(nw.store, 0.1):
                nw.notes.append_revision(n, "r once", origin=ORIGIN_TYPED,
                                         trigger=TRIGGER_AUTOSAVE,
                                         revision_id=rid)
            first = "committed_in_time"
        except TimeoutError:
            first = "unknown"
        finally:
            hold.release()
        nw.store.sync()
        nw.notes.append_revision(n, "r once", origin=ORIGIN_TYPED,
                                 trigger=TRIGGER_AUTOSAVE, revision_id=rid)
        count = nw.rows("SELECT COUNT(*) FROM note_revisions WHERE"
                        " note_id=?", (n,))[0][0]
        return first == "unknown" and count == 2 \
            and _passes("LF-M12-S023")


@mr("LF-M12-MR10")
def mr10():
    return _passes("LF-M12-S016", "LF-M12-C091")


@mr("LF-M12-MR11")
def mr11():
    return _passes("LF-M12-C114")


@mr("LF-M12-MR12")
def mr12():
    base = drivers._editor("AB", 1, 0)
    pre = drivers._editor("😀AB", 3, 0)
    try:
        u = (base._native_range()[0], pre._native_range()[0])
        cp = (base.insertion_point(), pre.insertion_point())
        base.receive("X", origin=ORIGIN_DICTATED, at_chars=cp[0])
        pre.receive("X", origin=ORIGIN_DICTATED, at_chars=cp[1])
        return u[1] - u[0] == 2 and cp[1] - cp[0] == 1 \
            and str(base.current_content()) == "AXB" \
            and str(pre.current_content()) == "😀AXB"
    finally:
        base.close()
        pre.close()


@mr("LF-M12-MR13")
def mr13():
    rc0, d0 = bench()
    rc1, d1 = bench("--delay", "note_open_10k=30")
    if not d0 or not d1 or "timing" not in d0 or "timing" not in d1:
        return False
    t0, t1 = d0["timing"], d1["timing"]
    moved = t1["note_open_10k"]["p50_ms"] - t0["note_open_10k"]["p50_ms"]
    other = t1["search_200_notes"]["p50_ms"] - \
        t0["search_200_notes"]["p50_ms"]
    return moved >= 25.0 and other < 10.0


@mr("LF-M12-MR14")
def mr14():
    return _passes("LF-M12-C123", "LF-M12-C122")


# ---- runner ------------------------------------------------------------------------

CASES = []
CASEMAP = {}


def run_case(c, adj):
    kind = c["kind"]
    if kind == "native":
        fn = native_driver
    elif kind == "performance":
        fn = None if "--skip-perf" in sys.argv else perf_driver
    else:
        fn = drivers.DRIVERS.get(c["id"])
    del w.REACHED[:]
    t0 = time.monotonic()
    if fn is None:
        o = Outcome("NOT_RUN", {}, note="no driver bound"
                    if kind != "performance" else "--skip-perf")
    else:
        try:
            o = fn(c)
        except AssertionError as e:
            o = Outcome("FAIL", {}, list(w.REACHED), str(e)[:400])
        except Exception as e:  # noqa: BLE001
            o = Outcome("ERROR", {}, list(w.REACHED),
                        f"{type(e).__name__}: {e}"[:400])
            if "--quiet" not in sys.argv:
                traceback.print_exc()
    ca = adj["case_adjudications"].get(c["id"])
    adjudication = None
    if ca is not None:
        if ca["decision"] not in adj["decisions"]:
            o = Outcome("ERROR", o.observed, o.barriers,
                        f"unknown decision {ca['decision']}")
        adjudication = {"decision": ca["decision"],
                        "policy_revision": adj["policy_revision"]}
    elif c.get("policy_dependencies") and o.status == "PASS":
        o = Outcome("ERROR", o.observed, o.barriers,
                    "policy-dependent case without a recorded adjudication")
    missing = []
    binds = adj["barrier_bindings"].get(c["id"], {})
    if kind == "stateful" and o.status == "PASS":
        missing = [b for b in c.get("barriers", [])
                   if b not in o.barriers
                   and binds.get(b) not in o.barriers
                   and not str(binds.get(b, "")).startswith("structural:")]
        if missing:
            o = Outcome("ERROR", o.observed, o.barriers,
                        f"barriers not reached: {missing}")
    return {"id": c["id"], "kind": kind, "category": c["category"],
            "finding_ids": c["finding_ids"],
            "driver": getattr(fn, "__name__", None),
            "status": o.status, "note": o.note,
            "adjudication": adjudication,
            "barriers_declared": c.get("barriers", []),
            "barrier_bindings": binds,
            "barriers_reached": sorted(set(o.barriers)),
            "barriers_missing": missing,
            "observed": _jsonable(o.observed),
            "seconds": round(time.monotonic() - t0, 3)}


def main(argv):
    global CASES
    data = CORPUS.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != CORPUS_SHA256:
        print(f"ERROR corpus changed: {sha}")
        return 2
    corpus = json.loads(data)
    CASES = corpus["cases"]
    CASEMAP.update({c["id"]: c for c in CASES})
    adj = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    if "--native" in argv:
        p = pathlib.Path(argv[argv.index("--native") + 1])
        NATIVE["record"] = json.loads(p.read_text()) if p.is_file() \
            else None
        NATIVE["path"] = p.name
    results = []
    for c in CASES:
        if only and c["id"] not in only:
            continue
        r = run_case(c, adj)
        results.append(r)
        print(f"{r['status']:8} {c['id']} {c['title'][:58]}"
              + (f" — {r['note'][:120]}" if r["note"]
                 and r["status"] != "PASS" else ""), flush=True)
    mr_results = []
    for mid, fn in MR.items():
        if only and mid not in only:
            continue
        del w.REACHED[:]
        try:
            status = "PASS" if fn() else "FAIL"
            note = ""
        except AssertionError as e:
            status, note = "FAIL", str(e)[:300]
        except Exception as e:  # noqa: BLE001
            status, note = "ERROR", f"{type(e).__name__}: {e}"[:300]
        mr_results.append({"id": mid, "status": status, "note": note})
        print(f"{status:8} {mid}", flush=True)
    counts, by_kind = {}, {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        k = by_kind.setdefault(r["kind"], {})
        k[r["status"]] = k.get(r["status"], 0) + 1
    summary = {"cases": len(results), "counts": counts, "by_kind": by_kind,
               "metamorphic": {s: sum(1 for m in mr_results
                                      if m["status"] == s)
                               for s in ("PASS", "FAIL", "ERROR")}}
    print(json.dumps(summary))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            **w.code_stamp("tests/v2/notes/m12_corpus_runner.py"),
            **production_tree(),
            "driver_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(HERE.parent.glob("m12_drivers*.py"))},
            "oracle_version": ORACLE_VERSION,
            "corpus": "tests/v2/notes/m12_audit_corpus.json",
            "corpus_sha256": sha,
            "adjudications": {
                "path": "docs/v2/acceptance/M12/remediation/adjudications.json",
                "sha256": hashlib.sha256(ADJ_PATH.read_bytes()).hexdigest(),
                "policy_revision": adj["policy_revision"]},
            "native_record": NATIVE.get("path"),
            "summary": summary, "results": results,
            "metamorphic": mr_results}, indent=1) + "\n")
    bad = counts.get("FAIL", 0) + counts.get("ERROR", 0) + sum(
        1 for m in mr_results if m["status"] != "PASS")
    return 0 if not bad else 1


def _jsonable(obj):
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return json.loads(json.dumps(obj, default=str))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
