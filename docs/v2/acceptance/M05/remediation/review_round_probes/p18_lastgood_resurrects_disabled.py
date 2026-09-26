"""Design question (AUDIT-02 fallback): on a store READ failure the job is
rescoped from the last good frozen entry set, which predates COMMITTED
edits. A rule the user disabled (write succeeded, revision bumped) rewrites
the next dictation and records a usage hit on the disabled entry."""
from _common import *
from m05_helpers import AppRun
r = AppRun("ask clod now")
try:
    v = r.d._vocab
    eid = v.add_entry("Claude", ["clod"], approved=True)
    a = r.job("app.A")                       # warm: last good set has the rule enabled
    v.set_enabled(eid, False)                # committed disable
    real = v.revision
    v.revision = lambda: (_ for _ in ()).throw(RuntimeError("read failure"))
    try:
        b = r.job("app.A")
    finally:
        v.revision = real
    usage = v.entry(eid).usage_count
    outcomes = [e.get("outcome") for e in r.events if e["event"] == "vocabulary.refresh_failed"]
finally:
    r.close()
print({"warm": a["text"], "after_disable_with_read_failure": b["text"], "usage": usage,
       "outcomes": outcomes})
expect("a disabled rule never rewrites a later dictation", b["text"] == "ask clod now", b["text"])
expect("a disabled rule records no new usage hit", usage == 1, usage)
done()
