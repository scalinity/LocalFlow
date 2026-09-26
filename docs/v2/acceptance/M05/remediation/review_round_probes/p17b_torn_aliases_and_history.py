"""AUDIT-18: losing vocabulary_aliases together with vocabulary_history is
SILENT -- integrity_report derives 'entries_missing_aliases' only from
history, so every approved alias vanishes with an all-zero report and the
app boots the dictionary as healthy (no integrity event)."""
from _common import *
import sqlite3, tempfile, pathlib
from localflow.v2 import store as store_mod
with tempfile.TemporaryDirectory() as td:
    db = pathlib.Path(td) / "v2.db"
    st = store_mod.Store(db)
    vs = VS.VocabularyStore(st)
    vs.add_entry("Kubectl", ["cube cuddle"], approved=True)
    st.close()
    con = sqlite3.connect(db)
    con.execute("DROP TABLE vocabulary_aliases")
    con.execute("DROP TABLE vocabulary_history")
    con.commit(); con.close()
    st2 = store_mod.Store(db, backup_dir=pathlib.Path(td) / "bk")
    vs2 = VS.VocabularyStore(st2)
    rep = vs2.integrity_report()
    aliases = [[a.alias for a in e.aliases] for e in vs2.entries()]
    out = run("run cube cuddle", (), snapshot=vs2.snapshot()).text
    st2.close()
print({"report": rep, "aliases_now": aliases, "dictation": out})
expect("alias loss is reported (non-zero integrity report)", any(rep.values()), rep)
done()
