"""REV-FAM-1 (reviewer-authored, not in the corpus): adjacent-bundle app scope
with a sibling suggestion, driven through the REAL AppDelegate (declared
shims): hotkey-down identity -> _vocab_job_state -> M06 finalize ->
coordinator normalization -> usage hits -> cleanup inputs.
Expectations were fixed BEFORE the first run (EXPECTED below is unedited)."""
import json, sys
sys.dont_write_bytecode = True
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
sys.path.insert(0, W); sys.path.insert(0, W + "/tests/v2/vocabulary")
from m05_helpers import AppRun

TERM, NEIGH = "com.example.term", "com.example.terminal"
EXPECTED = {
 "C1": {"role": "positive", "bundle": TERM, "input": "run cube cuddle and helm file",
        "text": "run Kubectl and Helmfile", "usage": {"E-APP": 1, "E-GLB": 1, "E-SUG": 0},
        "pairs_have": [["cube cuddle", "Kubectl"], ["helm file", "Helmfile"]],
        "pairs_lack_alias": ["custom eyes"]},
 "C2": {"role": "negative:no_leak_to_neighbor_bundle", "bundle": NEIGH,
        "input": "run cube cuddle and helm file", "text": "run cube cuddle and Helmfile",
        "usage": {"E-APP": 1, "E-GLB": 2, "E-SUG": 0}, "pairs_have": [["helm file", "Helmfile"]],
        "pairs_lack_alias": ["cube cuddle", "custom eyes"], "hint_lacks": ["Kubectl"]},
 "C3": {"role": "negative:no_rewrite_across_barrier", "bundle": TERM,
        "input": "run cube, cuddle and helm file", "text": "run cube, cuddle and Helmfile",
        "usage": {"E-APP": 1, "E-GLB": 3, "E-SUG": 0}},
 "C4": {"role": "negative:suggestion_never_rewrites_or_counts", "bundle": TERM,
        "input": "run custom eyes", "text": "run custom eyes",
        "usage": {"E-APP": 1, "E-GLB": 3, "E-SUG": 0}, "pairs_lack_alias": ["custom eyes"]},
 "C5": {"role": "negative:no_leak_on_store_read_failure", "bundle": NEIGH, "fault": True,
        "input": "run cube cuddle", "text": "run cube cuddle",
        "usage": {"E-APP": 1, "E-GLB": 3, "E-SUG": 0}, "pairs_lack_alias": ["cube cuddle"]},
 "C6": {"role": "negative:no_leak_on_failed_identity", "bundle": None,
        "input": "run cube cuddle", "text": "run cube cuddle",
        "usage": {"E-APP": 1, "E-GLB": 3, "E-SUG": 0}},
}

r = AppRun("x")
results = []
try:
    v = r.d._vocab
    v.add_entry("Kubectl", ["cube cuddle"], scope_kind="app", scope_value=TERM,
                approved=True, entry_id="E-APP")
    v.add_entry("Kustomize", ["custom eyes"], scope_kind="app", scope_value=TERM,
                approved=False, entry_id="E-SUG")
    v.add_entry("Helmfile", ["helm file"], approved=True, entry_id="E-GLB")
    # warm the cache on TERM before C5/C6 is implicit in the order below
    for cid in ("C1", "C2", "C3", "C4", "C5", "C6"):
        exp = EXPECTED[cid]
        r.sup.text = exp["input"]
        restore = None
        if exp.get("fault"):
            real = r.d._vocab.revision
            def boom():
                raise RuntimeError("injected revision read failure")
            r.d._vocab.revision = boom
            restore = lambda: setattr(r.d._vocab, "revision", real)
        try:
            out = r.job(exp["bundle"])
        finally:
            if restore:
                restore()
        usage = {e: v.entry(e).usage_count for e in ("E-APP", "E-GLB", "E-SUG")}
        pairs = [list(p) for p in out["pairs"]]
        hs = (out["job"] or {}).get("hint_set")
        hint = [t.canonical for t in hs.terms] if hs is not None else []
        ok = out["finished"] and out["text"] == exp["text"] and usage == exp["usage"]
        ok = ok and all(p in pairs for p in exp.get("pairs_have", []))
        ok = ok and not any(p[0] in exp.get("pairs_lack_alias", []) for p in pairs)
        ok = ok and not any(c in hint for c in exp.get("hint_lacks", []))
        results.append({"case_id": f"REV-FAM-1-{cid}", "role": exp["role"],
                        "input": exp["input"],
                        "setup": {"bundle": exp["bundle"], "fault": bool(exp.get("fault"))},
                        "expected": {k: exp[k] for k in exp if k not in ("role", "input", "bundle", "fault")},
                        "observed": {"text": out["text"], "usage": usage, "pairs": pairs, "hint": hint},
                        "pass": ok})
finally:
    r.close()
for x in results:
    print(("PASS " if x["pass"] else "FAIL ") + x["case_id"], x["role"], json.dumps(x["observed"]))
json.dump(results, open(__file__.replace(".py", "_results.json"), "w"), indent=1)
sys.exit(0 if all(x["pass"] for x in results) else 1)
