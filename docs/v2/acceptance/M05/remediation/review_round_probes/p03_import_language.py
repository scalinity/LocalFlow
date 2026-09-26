"""AUDIT-12/10: an import that changes the entry language while carrying an
EXPLICIT alias override equal to the entry's OLD language loses the override
(alias row stays NULL -> inherits the NEW language), and the same file then
re-imports as 'updated' (not idempotent)."""
from _common import *
with TempStore() as t:
    eid = t.vs.add_entry("Claude", ["clod"], language="en", approved=True)
    doc = {"entries": [{"entry_id": "x", "canonical": "Claude", "language": "fr",
                        "scope": ["global", None], "approved": True,
                        "verification": "explicit",
                        "aliases": [{"alias": "clod", "approved": True, "language": "en"}]}]}
    r1 = import_doc(t, doc, "a.json")
    e = t.vs.entry(eid)
    eff = [(a.alias, a.language, a.language or e.language) for a in e.aliases]
    print("after import 1:", r1, "entry.language=", e.language, "aliases=", eff)
    expect("explicit alias override 'en' kept after import", eff == [("clod", "en", "en")], eff)
    r2 = import_doc(t, doc, "b.json")
    expect("same file re-import is unchanged", r2 == {"created": 0, "updated": 0, "unchanged": 1}, r2)
    hist = t.vs.history(eid)
    print("history actions:", [h["action"] for h in hist])
done()
