"""R: idempotence break when a winning alias's canonical is SHORTER than
the overlapping losing alias (claims arbitrate by char length of the
CANONICAL on pass 2, proposals won by char length of the ALIAS on pass 1).
Contract vocabulary.md 'Canonical claims (AUDIT-03)': the first pass's
winner is also the second pass's; idempotent under left AND right overlaps."""
import sys; sys.dont_write_bytecode = True
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
sys.path.insert(0, W); sys.path.insert(0, W + "/tests/v2/vocabulary")
from m05_helpers import ent, run, vocab_edits
E = [ent("vx", "Red Status", ["reddish status"]),
     ent("vy", "Orange Page", ["status page"])]
bad = 0
for text in ["reddish status page", "the reddish status page is up"]:
    r1 = run(text, E); r2 = run(r1.text, E)
    print(repr(text), "->", repr(r1.text), "->", repr(r2.text), vocab_edits(r2))
    if r2.text != r1.text:
        bad += 1
# left-overlap mirror: loser on the LEFT
E2 = [ent("va", "Orange Status", ["red status"]),
      ent("vb", "Status Up", ["status paging now"])]
for text in ["red status paging now"]:
    r1 = run(text, E2); r2 = run(r1.text, E2)
    print(repr(text), "->", repr(r1.text), "->", repr(r2.text), vocab_edits(r2))
    if r2.text != r1.text:
        bad += 1
print("NON-IDEMPOTENT cases:", bad)
sys.exit(1 if bad else 0)
