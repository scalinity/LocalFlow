"""AUDIT-07/17 at the app boundary: the selector refuses a non-integer or
non-positive budget, but the app builds it with int(cfg['hint_term_limit'])
(coercing true->1, 2.9->2, "7"->7) inside the SAME try block as the store
open, so a refused knob (0, "abc") turns the WHOLE dictionary off and is
reported as vocabulary.store_unavailable (wrong reason)."""
from _common import *
import tempfile, pathlib
from m05_helpers import helpers
h = helpers()
rows = {}
for val in (0, "abc", True, 2.9, "7"):
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, cfg={"hint_term_limit": val}, start_coordinator=False)
        try:
            d = a.d
            ev = "".join(p.read_text() for p in (pathlib.Path(td) / "ev").rglob("*") if p.is_file())
            rows[repr(val)] = {"vocab_on": d._vocab is not None,
                               "max_terms": getattr(d._hint_selector, "max_terms", None),
                               "store_unavailable_event": "vocabulary.store_unavailable" in ev}
        finally:
            a.close()
for k, v in rows.items():
    print(k, v)
expect("a bad hint budget never disables the dictionary", all(v["vocab_on"] for v in rows.values()),
       {k: v["vocab_on"] for k, v in rows.items()})
expect("malformed budgets are refused, not coerced (True/2.9/'7')",
       all(rows[k]["max_terms"] in (None, 100) for k in ("True", "2.9", "'7'")),
       {k: rows[k]["max_terms"] for k in ("True", "2.9", "'7'")})
done()
