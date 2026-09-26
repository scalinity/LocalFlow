"""AUDIT-18: when BOTH vocabulary_entries and vocabulary_history are lost
(repaired empty) the surviving alias rows are orphans that prove entries
vanished, but integrity_report counts vanished_entries only from history, so
the app treats the torn dictionary as 'vocabulary_on_partial' (a WARNING),
keeps vocabulary ON and SEEDS new entries over the torn state."""
from _common import *
import sqlite3, tempfile, pathlib
from m05_helpers import helpers
h = helpers()
from localflow.v2 import store as store_mod
with tempfile.TemporaryDirectory() as td:
    db = pathlib.Path(td) / "v2.db"
    st = store_mod.Store(db)
    vs = VS.VocabularyStore(st)
    vs.add_entry("Kubectl", ["cube cuddle"], approved=True)
    vs.add_entry("Helmfile", ["helm file"], approved=True)
    st.close()
    con = sqlite3.connect(db)
    con.execute("DROP TABLE vocabulary_entries")
    con.execute("DROP TABLE vocabulary_history")
    con.commit(); con.close()
    a = h.App(td, start_coordinator=False)
    try:
        d = a.d
        vocab_on = d._vocab is not None
        rep = d._vocab.integrity_report() if vocab_on else None
        con = sqlite3.connect(db)
        orphans = con.execute("SELECT count(*) FROM vocabulary_aliases a WHERE NOT EXISTS"
                              " (SELECT 1 FROM vocabulary_entries e WHERE e.entry_id=a.entry_id)").fetchone()[0]
        seeded = [r[0] for r in con.execute("SELECT canonical FROM vocabulary_entries")]
        con.close()
        blob = "".join(p.read_text() for p in (pathlib.Path(td) / "ev").rglob("*") if p.is_file())
    finally:
        a.close()
print({"vocab_on": vocab_on, "report": rep, "orphans": orphans, "seeded": seeded,
       "integrity_failed_event": "vocabulary.integrity_failed" in blob,
       "integrity_warning_event": "vocabulary.integrity_warning" in blob})
expect("torn entries+history (orphans only) refuses the vocabulary", not vocab_on, vocab_on)
expect("nothing seeded over the torn state", not seeded, seeded)
done()
