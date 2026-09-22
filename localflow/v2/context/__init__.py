"""Local context snapshots and destination awareness (V2 M06, Spec S12).

One bounded snapshot per dictation feeds three consumers without
forking per-purpose context reads: the M05 vocabulary ScopeContext, the
M04 normalization engine context (destination/path/identifiers) and the
S30.1 ``context_snapshot_id`` in the ASR hint request. Identity is cheap
at PTT start; providers collect asynchronously during recording; the
finalize at release is bounded by the S12 deadline (75 ms default).
"""

from .collector import ContextCollector, DEFAULT_DEADLINE_MS
from .providers import (
    IDENTIFIER_LIMIT,
    NEARBY_CHARS,
    SystemAXHost,
    categorize,
    extract_identifiers,
    system_frontmost,
)
from .snapshot import (
    FIELD_NONE,
    FIELD_SECURE,
    FIELD_TEXT,
    FIELD_UNCLASSIFIABLE,
    STAGE_DOWNSTREAM,
    STAGE_PRE_DECODE,
    ContextSnapshot,
    FieldContext,
    TargetSnapshot,
    classify_field,
)

__all__ = [
    "ContextCollector", "DEFAULT_DEADLINE_MS",
    "SystemAXHost", "system_frontmost", "categorize",
    "extract_identifiers", "NEARBY_CHARS", "IDENTIFIER_LIMIT",
    "TargetSnapshot", "ContextSnapshot", "FieldContext",
    "classify_field",
    "FIELD_NONE", "FIELD_SECURE", "FIELD_TEXT", "FIELD_UNCLASSIFIABLE",
    "STAGE_PRE_DECODE", "STAGE_DOWNSTREAM",
]
