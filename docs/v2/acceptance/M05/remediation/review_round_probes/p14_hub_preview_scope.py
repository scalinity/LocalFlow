"""AUDIT-13 class on the Hub surface: hubPreviewPhrase (the Hub's phrase
sandbox, same store APIs) normalizes with the app's CACHED _norm_context, i.e.
the vocabulary scope of whichever job ran last. The same phrase previews
differently depending on the previous dictation's destination, and the
result carries no scope label (the M05 panel sandbox echoes its scope)."""
from _common import *
from m05_helpers import AppRun
r = AppRun("hello")
try:
    r.d._vocab.add_entry("Claude", ["clod"], scope_kind="app", scope_value="app.A",
                         approved=True)
    pre0 = r.d.hubPreviewPhrase("ask clod now")
    r.job("app.A")
    preA = r.d.hubPreviewPhrase("ask clod now")
    r.job("app.B")
    preB = r.d.hubPreviewPhrase("ask clod now")
finally:
    r.close()
print("before any job:", pre0.get("output"), "| after app.A job:", preA.get("output"),
      "| after app.B job:", preB.get("output"), "| keys:", sorted(preA))
expect("Hub preview of one phrase does not depend on the last job's destination",
       preA.get("output") == preB.get("output"), (preA.get("output"), preB.get("output")))
expect("Hub preview echoes the scope it tested", "scope" in preA, sorted(preA))
done()
