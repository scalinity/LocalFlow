"""LocalFlow V2: dated observability, persistent store, training evidence.

M02 introduces this package. It layers on the existing V1 pipeline without
changing dictation behavior: `eventlog` writes the dated JSONL event stream
(Spec S07), `store` owns the single-writer SQLite database and its artifacts
(Spec S08/S29), `importer` performs the lossless legacy import, and
`training` implements the opt-in evidence collector (Spec S29.1-S29.4).
`importer` is deliberately not imported here: it reaches into scripts/
(which the app bundle does not ship) and only the import CLI/tests use it.
"""

from . import ids, eventlog, store, training  # noqa: F401
