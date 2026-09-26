"""Second-pass drift without overlap: (a) a narrower-scope alias equal to a
broader entry's canonical rewrites that canonical on pass 2 (clod -> Cloud ->
Claude); (b) an entry whose canonical KEY is masked by a same-scope alias
loses its canonical claim, so a shorter alias inside its output rewrites on
pass 2. Neither is refused at admission nor reported by the preview."""
from _common import *
ws = V.ScopeContext(workspace="W")
E = [ent("E-G", "Cloud", ["clod"]),
     ent("E-W", "Claude", ["cloud"], scope_kind="workspace", scope_value="W")]
p1 = run("ask clod now", E, ws); p2 = run(p1.text, E, ws)
print("chain:", p1.text, "->", p2.text, vocab_edits(p2))
expect("chain: pass 2 is a no-op", p2.text == p1.text, (p1.text, p2.text))
prev = V.preview_entry_conflicts(E[1], [E[0]])
print("preview for E-W:", [(c["alias"], c["kind"]) for c in prev])
E2 = [ent("E-X", "Claude Code", ["clod code"]),
      ent("E-Y", "Clawed Code", ["claude code"]),
      ent("E-Z", "Kode", ["code"])]
q1 = run("use clod code", E2); q2 = run(q1.text, E2)
print("masked canonical:", q1.text, "->", q2.text, vocab_edits(q2))
expect("masked canonical key: pass 2 is a no-op", q2.text == q1.text, (q1.text, q2.text))
done()
