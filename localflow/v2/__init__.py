"""LocalFlow V2: dated observability, persistent store, training evidence.

M02 introduced this package: `eventlog` writes the dated JSONL event stream
(Spec S07), `store` owns the single-writer SQLite database and its artifacts
(Spec S08/S29), `importer` performs the lossless legacy import, and
`training` implements the opt-in evidence collector (Spec S29.1-S29.4).

M03 adds the resilient capture/inference layer (Spec S06/S09):
`capture_journal` persists audio blocks off the callback for crash
recovery, `capabilities` publishes the conservative ASR manifest (S30.1),
and `supervisor` owns the fresh model-worker subprocess. The worker entry
point itself (`worker`) is deliberately not imported here: it runs only as
`python -m localflow.v2.worker` in its own process, and `importer` stays
out because it reaches into scripts/ (app bundle does not ship it).

M05 adds the scoped-vocabulary layer (Spec S11/S30.1): `vocabulary`
(entries, immutable snapshots, the Relevant Vocabulary Selector and its
frozen HintSet, sandbox/conflict-preview APIs) and `vocabulary_store`
(the dictionary tables inside the single-writer store).
"""

from . import (capabilities, capture_journal, eventlog, ids, store,  # noqa: F401
               supervisor, training, vocabulary, vocabulary_store)
