"""Design question (import upsert, D6): a file row that OMITS approved/kind/
pinned/priority/enabled overwrites an existing entry with the admission
defaults -- an approved, pinned skill becomes an unapproved, unpinned term
and stops applying, reported only as 'updated'."""
from _common import *
with TempStore() as t:
    eid = t.vs.add_entry("code-review", ["code review"], kind="skill", approved=True,
                         pinned=True, priority=4)
    r = import_doc(t, {"entries": [{"entry_id": "x", "canonical": "code-review",
                                    "aliases": [{"alias": "code review"}]}]})
    e = t.vs.entry(eid)
    got = {"kind": e.kind, "approved": e.approved, "pinned": e.pinned,
           "priority": e.priority, "verification": e.verification}
    print("import result:", r, "entry now:", got)
    expect("omitted fields do not silently de-approve/re-kind an existing entry",
           got["approved"] and got["kind"] == "skill", got)
done()
