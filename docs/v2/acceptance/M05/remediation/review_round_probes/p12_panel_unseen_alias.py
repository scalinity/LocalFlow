"""Panel CAS scope (AUDIT-08/06): the panel re-reads the selected entry at
ACTION time and passes THAT revision as expected_revision, so an alias added
by another surface (Hub/import) after the user selected/saw the entry is
approved by the click, never reviewed. Expected (safe): the approval is
refused as stale, or the unseen alias is not approved.
(Also: the Add button's conflict preview is computed against the listing's
stale entry list, missing a contender added since the last refresh.)"""
from _common import *
from m05_helpers import panel
with TempStore() as t:
    b = t.vs.add_entry("Beta", ["beeta"], approved=False)
    ctl = panel(t.vs)
    ctl.phrase.v = "1"; ctl.runSandbox_(None)          # user selects Beta (sees alias 'beeta')
    seen_rev = t.vs.entry(b).revision
    # another surface adds an alias the user never saw
    t.vs.update_entry(b, aliases=[("beeta", False), ("bay tah", False)])
    ctl.approveEntry_(None)
    e = t.vs.entry(b)
    txt = run("say bay tah", (), snapshot=t.vs.snapshot()).text
    print("panel message:", ctl.sandbox.v, "| seen rev", seen_rev, "now", e.revision)
    expect("unseen alias not approved by the click",
           not any(a.alias == "bay tah" and a.approved for a in e.aliases) or not e.approved,
           [(a.alias, a.approved) for a in e.aliases])
    expect("unseen alias does not rewrite text", txt == "say bay tah", txt)
with TempStore() as t:
    ctl = panel(t.vs)                                     # listing read now (empty)
    t.vs.add_entry("Cloud", ["clod"], approved=True)      # another surface
    ctl.canonical.v, ctl.alias.v = "Claude", "clod"
    ctl.addEntry_(None)
    print("panel add message:", repr(ctl.sandbox.v))
    expect("add preview names the same-scope contender added since refresh",
           "same_scope_mask" in ctl.sandbox.v, ctl.sandbox.v)
done()
