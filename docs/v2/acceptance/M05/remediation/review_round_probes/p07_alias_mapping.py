"""AUDIT-07 strict admission: an alias CONTAINER that is a mapping
{alias: approved_flag} is not refused -- _normalize_alias_items iterates the
keys, silently discards the False flag and admits the alias as APPROVED
(Alias default approved=True). add_entry and update_entry both accept it; the
approved entry then rewrites text with an alias the caller marked unapproved."""
from _common import *
with TempStore() as t:
    out = {}
    try:
        eid = t.vs.add_entry("Claude", {"clod": False}, approved=True)
        e = t.vs.entry(eid)
        out["add_entry"] = [(a.alias, a.approved) for a in e.aliases]
    except Exception as ex:
        eid = None
        out["add_entry"] = f"refused {type(ex).__name__}:{getattr(ex,'code','')}"
    expect("add_entry refuses a mapping alias container", isinstance(out["add_entry"], str), out["add_entry"])
    if eid:
        txt = run("ask clod now", (), snapshot=t.vs.snapshot()).text
        expect("alias flagged False never rewrites", txt == "ask clod now", txt)
    eid2 = t.vs.add_entry("Zeta", ["zeeta"], approved=True)
    try:
        e2 = t.vs.update_entry(eid2, aliases={"zed": False})
        out["update_entry"] = [(a.alias, a.approved) for a in e2.aliases]
    except Exception as ex:
        out["update_entry"] = f"refused {type(ex).__name__}:{getattr(ex,'code','')}"
    expect("update_entry refuses a mapping alias container", isinstance(out["update_entry"], str), out["update_entry"])
    try:
        eid3 = t.vs.add_entry("Omega", {}, approved=True)
        out["empty_mapping"] = "accepted"
    except Exception as ex:
        out["empty_mapping"] = f"refused {type(ex).__name__}"
    expect("{} alias container refused (contract lists {} as refused)", out["empty_mapping"] != "accepted", out["empty_mapping"])
done()
