"""Each SURVIVING mutation (mutdrv.py: corpus runner, domain suite and app
suite all exit 0 under it) is behavior-changing: a witness that PASSES on the
unmodified tree FAILS under the mutation. Exit 1 when any behavior-changing
mutation survived (evidence gap)."""
import json, os, subprocess, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mutdrv import MUTATIONS, PY, W, S

WITNESS = r'''
import sys, json, tempfile, pathlib
sys.path.insert(0, W); sys.path.insert(0, W + "/tests/v2/vocabulary")
from m05_helpers import ent, run, vocab_edits, V, VS, TempStore
from localflow.v2.normalize import NormalizationPolicy, ContextSnapshot, normalize
res = {}
# claim_tie_ignored: equal-length right overlap, claim starts first
E = [ent("E-A", "Alpha Beta"), ent("E-B", "Zeta Q", ["beta gamma"])]
p1 = run("alpha beta gamma", E); p2 = run(p1.text, E)
res["claim_tie"] = (p1.text, p2.text, p2.text == p1.text == "Alpha Beta gamma")
# score_not_in_hint_id: same id, different score must be refused
snap = V.VocabularySnapshot([ent("E-1", "One"), ent("E-2", "Two")])
hs = V.RelevantVocabularySelector(5).select(snap, now_utc="t")
forged = [V.HintTerm(canonical=t.canonical, entry_id=t.entry_id, scope_kind=t.scope_kind,
          scope_value=t.scope_value, source=t.source, score=(9, 9, "9", 9, 9)) for t in hs.terms]
try:
    V.HintSet(hint_set_id=hs.hint_set_id, selector_revision=hs.selector_revision,
              vocabulary_revision=hs.vocabulary_revision, scope=dict(hs.scope),
              terms=forged, omitted=[dict(o) for o in hs.omitted], created_utc="t",
              term_limit=hs.term_limit)
    res["score_id"] = ("forged score accepted under the same id", False)
except ValueError:
    res["score_id"] = ("refused", True)
# revision_scope_blind: two scopes, one entry set -> revisions must differ
ents = [ent("E-W", "WsTerm", ["wuss"], scope_kind="workspace", scope_value="A")]
ra = V.VocabularySnapshot(ents, V.ScopeContext(workspace="A")).revision
rb = V.VocabularySnapshot(ents, V.ScopeContext(workspace="B")).revision
res["revision_scope"] = (ra, rb, ra != rb)
# sandbox_drops_masked: an unapproved suggestion an active contender would mask
out = V.sandbox_phrase("use clod code", V.VocabularySnapshot(
    [ent("E-U", "Claude Code", ["clod code"], approved=False),
     ent("E-A", "Cloud Code", ["clod code"])]))
m = [s for s in out["suggestions"] if s["entry_id"] == "E-U"]
res["sandbox_masked"] = (m, bool(m) and all(s.get("masked") for s in m))
# applied_rules_unbounded: manifest must hold ONLY the applied rules
sys.path.insert(0, W + "/tests/v2/vocabulary")
import test_m05_remediation as T
with tempfile.TemporaryDirectory() as td:
    st, col, events, ctx, job = T._collector(td)
    vs = VS.VocabularyStore(st)
    a = vs.add_entry("Zeta", ["zeeta"], approved=True)
    for i in range(3):
        vs.add_entry(f"Pin{i}", [], pinned=True, approved=True)
    snap = vs.snapshot(None)
    col.on_asr_result(ctx, "say zeeta", model_id="m", model_revision=None, stage_duration_ms=0.0)
    cctx = ContextSnapshot(vocabulary=snap)
    r = normalize("say zeeta", NormalizationPolicy(), cctx)
    col.on_normalization_result(ctx, r, source_text="say zeeta", policy=NormalizationPolicy(), context=cctx)
    col.on_cleanup_result(ctx, r.text)
    env = st.latest_revision(col.finalize(ctx))
    vb = env["normalization"]["vocabulary"]
    rules = json.loads(st.artifact_payload(vb["applied_rules_artifact"]))["rules"]
    st.close()
res["applied_bounded"] = ([x["entry_id"] == a for x in rules], [x["entry_id"] for x in rules] == [a])
print(json.dumps({k: v[-1] for k, v in res.items()}))
'''

KEY = {"claim_tie_ignored": "claim_tie", "score_not_in_hint_id": "score_id",
       "revision_scope_blind": "revision_scope", "sandbox_drops_masked": "sandbox_masked",
       "applied_rules_unbounded": "applied_bounded"}

def witness(name):
    code = ("import sys; sys.dont_write_bytecode=True\n"
            f"W={W!r}\nsys.path.insert(0, W); sys.path.insert(0, W + '/tests/v2/lifecycle')\n"
            + MUTATIONS[name] + WITNESS)
    p = subprocess.run([PY, "-c", code], cwd=str(S), capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=600)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if not line:
        raise SystemExit(p.stdout + p.stderr)
    return json.loads(line[-1])

base = witness("control_unmodified")
print("control witnesses (all must be true):", base)
assert all(base.values()), base
summ = json.loads((S / "mutdrv_summary.json").read_text())
bad = 0
for name, key in KEY.items():
    w = witness(name)
    survived = all(v["survived"] for v in summ[name].values())
    changed = not w[key]
    print(f"{name:26s} witness_{key}={w[key]!s:5s} behavior_changed={changed} "
          f"survived(corpus,domain,app)={survived}")
    if changed and survived:
        bad += 1
print("behavior-changing mutations surviving every evidence tool:", bad)
sys.exit(1 if bad else 0)
