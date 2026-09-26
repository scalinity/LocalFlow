import sys, json
from _common import *
order = sys.argv[1]
with TempStore() as t:
    aliases = [{"alias": "Clod"}, {"alias": "clod"}, {"alias": "klod"}]
    if order == "rev":
        aliases = aliases[::-1]
    ents = [{"entry_id": "x", "canonical": "Claude", "approved": True, "aliases": aliases},
            {"entry_id": "y", "canonical": "Zed", "approved": True, "aliases": [{"alias": "zedd"}]}]
    if order == "rev":
        ents = ents[::-1]
    import_doc(t, {"entries": ents})
    # canonical ids differ per run (minted); normalize ids for comparison
    snap = t.vs.snapshot(None)
    by_can = {e.canonical: e for e in snap.entries}
    single = t.vs.entry(by_can["Claude"].entry_id)
    print(json.dumps({"aliases_entries()": [a.alias for a in by_can["Claude"].aliases],
                      "aliases_entry()": [a.alias for a in single.aliases]}))
