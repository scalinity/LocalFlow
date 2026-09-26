"""Run the frozen M10 adversarial corpus against the current code.

    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/profiles/m10_corpus_runner.py [--json OUT] [--only IDS]
        [--quiet]

The corpus file is verified byte-identical (sha256) before anything
runs; results, bindings and code stamps go to separate files. Every case
is bound to a driver (``m10_drivers*.py``); a case without a binding is
NOT_RUN and is counted as such, never as a pass. The 20 stateful probes
are the corpus's C201–C220 with the barriers each driver actually
reached; the 12 metamorphic relations run here (``MR``).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "transforms"))
sys.path.insert(0, str(HERE.parents[1] / "insertion"))

CORPUS = HERE.parent / "m10_audit_corpus.json"
CORPUS_SHA256 = \
    "3cc5a9288f432a45ddf85c0ecaa7b1c1f83c0e550ea774a4a326f5e23780f755"
ORACLE_VERSION = "m10-corpus-oracles-r1"
ADJ_PATH = HERE.parents[3] / "docs" / "v2" / "acceptance" / "M10" \
    / "remediation" / "adjudications.json"

import m10_drivers as drivers  # noqa: E402
import m10_drivers_b  # noqa: E402,F401
import m10_drivers_c  # noqa: E402,F401
import m10_world as w  # noqa: E402
import test_m10_remediation as rem  # noqa: E402

from localflow.v2 import profiles as prof  # noqa: E402
from localflow.v2 import snippets as snip_mod  # noqa: E402
from localflow.v2.developer import file_tags  # noqa: E402
from localflow.v2.developer import skills as skills_mod  # noqa: E402
from localflow.v2.normalize import (ContextSnapshot,  # noqa: E402
                                    NormalizationPolicy, normalize)

try:
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
except Exception:  # pragma: no cover
    NSApplication = None


# ---- metamorphic relations ----------------------------------------------------------

MR = {}


def mr(mid):
    def deco(fn):
        MR[mid] = fn
        return fn
    return deco


def _r(rid, kind="global", value=None, mode="clean", np="inherit"):
    return prof.StyleRule(rule_id=rid, name=rid, scope_kind=kind,
                          scope_value=value, mode=mode, number_policy=np)


@mr("M10-MR01")
def narrower_scope():
    broad = [_r("r:app", "app", "com.example.e", "raw", "standard")]
    dest = prof.Destination(app_bundle="com.example.e", workspace="W")
    a = prof.resolve(None, broad, dest)
    b = prof.resolve(None, broad + [_r("r:ws", "workspace", "W", "clean",
                                       "technical")], dest)
    return (a.rule_id, a.mode, a.number_policy) == ("r:app", "raw",
                                                    "standard") \
        and (b.rule_id, b.mode, b.number_policy) == ("r:ws", "clean",
                                                     "technical")


@mr("M10-MR02")
def disabled_authority():
    h, sup, ctx = w.hooked_harness()
    try:
        rid = h.d._styles.add_rule(name="A", scope_kind="app",
                                   scope_value="com.example.editor",
                                   mode="raw")
        ctx.on_finalize = lambda: h.d._styles.set_enabled(rid, False)
        ta, _ = w.run_job(h, "we retried three times today")
        ctx.on_finalize = None
        tb, _ = w.run_job(h, "we retried three times today")
    finally:
        h.close()
    return ta == "we retried three times today" \
        and tb == "we retried 3 times today"


@mr("M10-MR03")
def freeze():
    out = drivers.DRIVERS["M10-C202"]({"id": "M10-C202"})
    out2 = drivers.DRIVERS["M10-C201"]({"id": "M10-C201"})
    rem.r11_manifest_edit_after_freeze_never_reaches_the_job()
    out3 = drivers.DRIVERS["M10-C211"]({"id": "M10-C211"})
    return all(o.status == "PASS" for o in (out, out2, out3))


@mr("M10-MR04")
def literal_protection():
    qr = snip_mod.Snippet(snippet_id="s", trigger="quick reply", name="n",
                          content="ACK")
    fr = file_tags.FileTagResolver(["alpha.py"])
    pol = NormalizationPolicy(registered_skills={"review": "review"})
    ctx = ContextSnapshot(snippets=snip_mod.SnippetSnapshot([qr]),
                          file_resolver=fr)
    plain = "quick reply then slash review and attach file alpha dot py"
    wrapped = f'"{plain}"'

    def actions(t):
        return {e.cls for e in normalize(t, pol, ctx).edits} & {
            "snippet", "skill", "file_tag"}
    return actions(plain) == {"snippet", "skill", "file_tag"} \
        and actions(wrapped) <= actions(plain) and not actions(wrapped)


@mr("M10-MR05")
def ambiguity():
    r1 = file_tags.FileTagResolver(["src/config.json"]).resolve(
        ["config", "dot", "json"])
    r2 = file_tags.FileTagResolver(["src/config.json",
                                    "tests/config.json"]).resolve(
        ["config", "dot", "json"])
    a = snip_mod.Snippet(snippet_id="a", trigger="slash go", name="n",
                         content="A")
    u = normalize("slash go", NormalizationPolicy(),
                  ContextSnapshot(snippets=snip_mod.SnippetSnapshot([a])))
    amb = normalize("slash go", NormalizationPolicy(
        registered_skills={"go": "go"}),
        ContextSnapshot(snippets=snip_mod.SnippetSnapshot([a])))
    return r1.status == "resolved" and r2.status == "ambiguous" \
        and u.text == "A" and amb.text == "slash go"


@mr("M10-MR06")
def filesystem_authority():
    with w.FixtureRoot() as fx:
        w.write(fx.allowed / "a" / "one" / "SKILL.md", w.skill_md("one"))
        w.write(fx.allowed / "b" / "two" / "SKILL.md", w.skill_md("two"))
        full = set(w.discover_names([fx.allowed / "a", fx.allowed / "b"]))
        less = set(w.discover_names([fx.allowed / "a"]))
    return less <= full and less == {"one"} and full == {"one", "two"}


@mr("M10-MR07")
def preview_parity():
    return drivers.DRIVERS["M10-C216"]({"id": "M10-C216"}).status == "PASS" \
        and drivers.DRIVERS["M10-C173"]({"id": "M10-C173"}).status \
        == "PASS"


@mr("M10-MR08")
def candidate_permutation():
    rules = [_r("r:1", "global", None, "raw"), _r("r:2", "global", None,
                                                    "clean")]
    a = prof.resolve(None, rules, prof.Destination())
    b = prof.resolve(None, list(reversed(rules)), prof.Destination())
    files = ["src/x.py", "tests/x.py", "y.py"]
    ra = file_tags.FileTagResolver(files).resolve(["x", "dot", "py"])
    rb = file_tags.FileTagResolver(list(reversed(files))).resolve(
        ["x", "dot", "py"])
    s1 = snip_mod.Snippet(snippet_id="1", trigger="aa bb", name="n",
                          content="X")
    s2 = snip_mod.Snippet(snippet_id="2", trigger="aa bb cc", name="n",
                          content="Y")
    t1 = normalize("aa bb cc", NormalizationPolicy(), ContextSnapshot(
        snippets=snip_mod.SnippetSnapshot([s1, s2]))).text
    t2 = normalize("aa bb cc", NormalizationPolicy(), ContextSnapshot(
        snippets=snip_mod.SnippetSnapshot([s2, s1]))).text
    return a.to_json() == b.to_json() and (ra.status, ra.candidates) \
        == (rb.status, rb.candidates) and t1 == t2 == "Y"


@mr("M10-MR09")
def strict_boolean():
    results = []
    for cid in ("M10-C048", "M10-C052", "M10-C056", "M10-C060",
                "M10-C064"):
        c = next(x for x in CASES if x["id"] == cid)
        results.append(drivers.DRIVERS[cid](c).status == "PASS")
    return all(results)


@mr("M10-MR10")
def evidence_deletion():
    rem.r23_applied_definition_survives_config_deletion()
    return True


@mr("M10-MR11")
def benchmark_noop():
    outs = [drivers.DRIVERS[cid](next(x for x in CASES if x["id"] == cid))
            for cid in ("M10-C194", "M10-C195", "M10-C196", "M10-C197")]
    return all(o.status == "PASS" for o in outs)


@mr("M10-MR12")
def terminal_separator():
    outs = [drivers.DRIVERS[cid](next(x for x in CASES if x["id"] == cid))
            for cid in ("M10-C150", "M10-C151", "M10-C152", "M10-C153",
                        "M10-C154", "M10-C155", "M10-C156")]
    return all(o.status == "PASS" for o in outs)


# ---- runner ---------------------------------------------------------------------------

CASES = []


def main(argv):
    global CASES
    data = CORPUS.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != CORPUS_SHA256:
        print(f"ERROR corpus changed: {sha}")
        return 2
    corpus = json.loads(data)
    CASES = corpus["cases"]
    adj = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    quiet = "--quiet" in argv
    results = []
    for c in CASES:
        if only and c["id"] not in only:
            continue
        fn = drivers.DRIVERS.get(c["id"])
        t0 = time.monotonic()
        if fn is None:
            o = drivers.Outcome("NOT_RUN", {}, note="no driver bound")
        else:
            try:
                o = fn(c)
            except AssertionError as e:
                o = drivers.Outcome("FAIL", {}, note=str(e)[:400])
            except Exception as e:
                o = drivers.Outcome("ERROR", {},
                                    note=f"{type(e).__name__}: {e}"[:400])
                if not quiet:
                    traceback.print_exc()
        # A policy-dependent case is graded only under a recorded
        # decision (adjudications.json); otherwise it cannot be green.
        ca = adj["case_adjudications"].get(c["id"])
        adjudication = None
        if ca is not None:
            if ca["decision"] not in adj["decisions"]:
                o = drivers.Outcome("ERROR", o.observed, o.barriers,
                                    note=f"unknown decision {ca['decision']}")
            adjudication = {"decision": ca["decision"],
                            "policy_revision": adj["policy_revision"]}
        elif c["expected"].get("policy_adjudication") is not None \
                and o.status == "PASS":
            o = drivers.Outcome("ERROR", o.observed, o.barriers,
                                note="policy-dependent case without a"
                                     " recorded adjudication")
        results.append({"id": c["id"], "category": c["category"],
                        "execution_kind": c["execution_kind"],
                        "related_findings": c["related_findings"],
                        "driver": fn.__name__ if fn else None,
                        "status": o.status, "note": o.note,
                        "adjudication": adjudication,
                        "barriers_reached": o.barriers,
                        "observed": _jsonable(o.observed),
                        "seconds": round(time.monotonic() - t0, 3)})
        print(f"{o.status:8} {c['id']} {c['name'][:60]}"
              + (f" — {o.note[:120]}" if o.note and o.status != "PASS"
                 else ""), flush=True)
    mr_results = []
    if not only or any(m in only for m in MR):
        for mid, fn in MR.items():
            if only and mid not in only and not any(
                    x.startswith("M10-C") for x in only):
                continue
            try:
                ok = bool(fn())
                status = "PASS" if ok else "FAIL"
                note = ""
            except AssertionError as e:
                status, note = "FAIL", str(e)[:300]
            except Exception as e:
                status, note = "ERROR", f"{type(e).__name__}: {e}"[:300]
            mr_results.append({"id": mid, "status": status, "note": note})
            print(f"{status:8} {mid}", flush=True)
    stateful = []
    for p in corpus["stateful_probes"]:
        r = next((x for x in results if x["id"] == p["case_id"]), None)
        if r is None:
            continue
        # Every required barrier is reached under its own label, under
        # the label a binding names, or is bound as structural in the
        # repaired design; anything else is ERROR, never a pass.
        binds = adj["barrier_bindings"].get(p["id"], {})
        missing = [b for b in p["required_barriers"]
                   if b not in r["barriers_reached"]
                   and binds.get(b) not in r["barriers_reached"]
                   and not str(binds.get(b, "")).startswith("structural:")]
        status = r["status"]
        if missing and status == "PASS":
            status = "ERROR"
            r["status"], r["note"] = "ERROR", f"barriers not reached: {missing}"
            print(f"ERROR    {r['id']} — {r['note'][:120]}", flush=True)
        stateful.append({"id": p["id"], "case_id": p["case_id"],
                         "status": status,
                         "required_barriers": p["required_barriers"],
                         "barrier_bindings": binds,
                         "barriers_missing": missing,
                         "barriers_reached": r["barriers_reached"]})
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = {"cases": len(results), "counts": counts,
               "metamorphic": {s: sum(1 for m in mr_results
                                      if m["status"] == s)
                               for s in ("PASS", "FAIL", "ERROR")},
               "stateful": {s: sum(1 for p in stateful if p["status"] == s)
                            for s in ("PASS", "FAIL", "ERROR", "NOT_RUN")}}
    print(json.dumps(summary))
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            **w.code_stamp("tests/v2/profiles/m10_corpus_runner.py"),
            "oracle_version": ORACLE_VERSION,
            "corpus": "tests/v2/profiles/m10_audit_corpus.json",
            "corpus_sha256": sha,
            "adjudications": {
                "path": "docs/v2/acceptance/M10/remediation/adjudications.json",
                "sha256": hashlib.sha256(ADJ_PATH.read_bytes()).hexdigest(),
                "policy_revision": adj["policy_revision"]},
            "summary": summary,
            "results": results, "metamorphic": mr_results,
            "stateful": stateful}, indent=1) + "\n")
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
