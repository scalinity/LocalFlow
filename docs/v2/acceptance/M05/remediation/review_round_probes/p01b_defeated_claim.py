"""AUDIT-03: a canonical claim that itself LOSES to a longer overlapping
alias proposal still suppresses a third proposal it would have beaten. As a
proposal the claim would have been rejected (overlap loser) and the third
proposal would apply; so pass 1 under-applies and pass 2 (claim gone) drifts.
Contract: claims 'arbitrate like proposals (longer span, then earlier
start)' and the first pass's winner is the second pass's."""
from _common import *
E = [ent("E-C", "Bb Cc"), ent("E-P", "Zz", ["aaaaaa bb"]), ent("E-Q", "Yy", ["cc dd"])]
text = "aaaaaa Bb Cc dd"
p1 = run(text, E); p2 = run(p1.text, E)
print(repr(text), "->", repr(p1.text), vocab_edits(p1), "->", repr(p2.text), vocab_edits(p2))
expect("pass 2 is a no-op", p2.text == p1.text, (p1.text, p2.text))
# Proposal-equivalent oracle: replace the claim by a real proposal with the same span
# (canonical 'Bb Cc' reached from alias 'bb cc' on lowercase input) -> engine order.
low = run("aaaaaa bb cc dd", E)
print("lowercase input (claim is a real proposal):", repr(low.text), vocab_edits(low))
expect("claim arbitrates like the equivalent proposal (same winners)",
       [r for _, _, r in vocab_edits(p1)] == [r for _, _, r in vocab_edits(low) if r != "E-C"],
       ([r for _, _, r in vocab_edits(p1)], [r for _, _, r in vocab_edits(low)]))
done()
