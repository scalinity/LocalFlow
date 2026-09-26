"""AUDIT-11/07 admission: an import file whose entry repeats an alias is not
refused by the up-front validation (add_entry/update_entry refuse it as
AdmissionError duplicate_alias); it reaches the writer, the SQLite PK fails,
the store emits an ERROR store.write_failed event and the caller gets
ImportRejected('write_failed') instead of a pre-write content-free refusal.
Case variants ('Clod'/'clod') are admitted as two alias rows."""
from _common import *
# public API refuses the duplicate
with TempStore() as t:
    try:
        t.vs.add_entry("Claude", ["clod", "clod"], approved=True); api = "accepted"
    except Exception as e:
        api = f"{type(e).__name__}:{getattr(e, 'code', '')}"
    print("add_entry duplicate alias ->", api)
    try:
        t.vs.add_entry("Claude", ["Clod", "clod"], approved=True); api2 = "accepted"
    except Exception as e:
        api2 = f"{type(e).__name__}:{getattr(e, 'code', '')}"
    print("add_entry case-variant alias ->", api2)
with TempStore() as t:
    doc = {"entries": [{"entry_id": "x", "canonical": "Claude", "approved": True,
                        "aliases": [{"alias": "clod"}, {"alias": "clod"}]}]}
    try:
        r = import_doc(t, doc); res = ("ok", r)
    except Exception as e:
        res = (type(e).__name__, getattr(e, "code", None))
    wf = [ev for ev in t.events if ev["event"] == "store.write_failed"]
    print("import dup alias ->", res, "store.write_failed events:", len(wf), wf[:1])
    expect("dup alias refused BEFORE the writer (content-free code, not write_failed)",
           res[0] == "ImportRejected" and res[1] != "write_failed", res)
    expect("no store.write_failed ERROR event for a validation outcome", not wf, len(wf))
with TempStore() as t:
    doc = {"entries": [{"entry_id": "x", "canonical": "Claude", "approved": True,
                        "aliases": [{"alias": "Clod"}, {"alias": "clod"}]}]}
    try:
        r = import_doc(t, doc); res = ("ok", r)
    except Exception as e:
        res = (type(e).__name__, getattr(e, "code", None))
    rows = t.sql("SELECT alias FROM vocabulary_aliases ORDER BY alias")
    print("import case-variant aliases ->", res, rows)
    expect("import admission agrees with add_entry (case-variant duplicate refused)",
           res[0] != "ok" or len(rows) == 1, (res, rows))
done()
