"""Scope identity hole: a 'global' entry may carry a non-null scope_value
(VocabularyEntry, add_entry, update_entry and import all admit it). It still
applies everywhere (scope_matches ignores the value) but is a DIFFERENT store
identity from the plain global entry, and preview_entry_conflicts compares
(kind, value) so it reports NO same-scope mask while the committed snapshot
masks the alias (preview != committed, AUDIT-13)."""
from _common import *
with TempStore() as t:
    a = t.vs.add_entry("Claude", ["clod"], approved=True)
    try:
        b = t.vs.add_entry("Claude", ["klod"], approved=True,
                           scope_kind="global", scope_value="anything")
        dup = "accepted"
    except Exception as e:
        dup = type(e).__name__
    expect("second global 'Claude' refused as duplicate identity", dup != "accepted", dup)
    c = t.vs.add_entry("Cloud", ["clod"], approved=True, scope_kind="global",
                       scope_value="x")
    cand = t.vs.entry(c)
    others = [e for e in t.vs.entries() if e.entry_id != c]
    prev = V.preview_entry_conflicts(cand, others)
    snap = t.vs.snapshot(V.ScopeContext(app_bundle="com.any"))
    masked = [dict(x) for x in snap.conflicts]
    out = run("ask clod now", (), snapshot=snap).text
    print("preview:", prev)
    print("committed conflicts:", masked, "output:", out)
    expect("preview reports the committed same-scope mask on 'clod'",
           any(p["alias"] == "clod" and p["kind"] == "same_scope_mask" for p in prev),
           [(p["alias"], p["kind"]) for p in prev])
done()
