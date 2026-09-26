"""AUDIT-12 (post-remediation rows): an alias created NOW with an explicit
language equal to its entry's language is silently converted to 'inherit' by
the next entry-language change (the pre-remediation heuristic
'row == previous entry language => inherited' is applied to every row),
so an explicit override is not 'kept across entry-language changes'."""
from _common import *
with TempStore() as t:
    eid = t.vs.add_entry("Claude", [("clod", True, "en"), ("klod", True, None)],
                         language="en", approved=True)
    before = [(a.alias, a.language) for a in t.vs.entry(eid).aliases]
    t.vs.update_entry(eid, language="fr")
    e = t.vs.entry(eid)
    after = [(a.alias, a.language, a.language or e.language) for a in e.aliases]
    print("stored before:", before, "after language change:", after)
    expect("explicit 'en' override on clod survives the entry-language change",
           ("clod", "en", "en") in after, after)
done()
