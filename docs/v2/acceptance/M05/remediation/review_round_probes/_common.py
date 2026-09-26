import sys, os, json, tempfile, pathlib
sys.dont_write_bytecode = True
import os as _os
W = _os.environ.get('M05_CODE', "/tmp/claude-0/-home-user-LocalFlow/60feaa92-3367-5b00-af84-78a53bb5703a/scratchpad/review_fp")
sys.path.insert(0, W); sys.path.insert(0, W + "/tests/v2/vocabulary")
from m05_helpers import ent, run, vocab_edits, TempStore, V, VS, race  # noqa
FAILS = []
def expect(label, cond, observed):
    print(("OK   " if cond else "FAIL ") + label + " :: " + repr(observed))
    if not cond:
        FAILS.append(label)
def done():
    print("VIOLATIONS:", len(FAILS), FAILS)
    sys.exit(1 if FAILS else 0)
def import_doc(t, doc, name="f.json"):
    p = t.dir / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return t.vs.import_json(p)
