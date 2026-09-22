"""Typed numeric and spoken-syntax normalization (V2 M04, Spec S10).

Public surface:
- ``normalize(text, policy, context=None) -> NormalizationResult``
- ``NormalizationPolicy`` / ``ContextSnapshot`` (immutable inputs)
- ``preview_phrase`` — test-phrase API for the future Dictionary and
  Developer UI (M04 task 5)
- ``scoring`` — ITN-independent short-command scoring

Placement (S06/S24): this package is deterministic, model-free code and
runs in the parent coordinator thread between ASR and cleanup — not in
the model worker. The worker protocol is unchanged.
"""

from .engine import normalize  # noqa: F401
from .policy import (  # noqa: F401
    ContextSnapshot,
    NormalizationPolicy,
    load_profiles,
)
from .scoring import score_command_corpus, separate_scores  # noqa: F401
from .span_types import (  # noqa: F401
    NUMERIC_CLASSES,
    EditRecord,
    NormalizationResult,
    Proposal,
    ProtectedSpan,
    RejectedProposal,
    Span,
)


def preview_phrase(text: str,
                   policy: NormalizationPolicy | None = None,
                   context: ContextSnapshot | None = None) -> dict:
    """Test-phrase API for the future Dictionary/Developer UI (task 5):
    what would normalization do to this phrase, edit by edit, without
    touching the pipeline."""
    from .policy import NormalizationPolicy as _P
    pol = policy or _P()
    res = normalize(text, pol, context)
    return {
        "input": text,
        "output": res.text,
        "changed": res.text != text,
        "policy_revision": res.policy_revision,
        "edits": [
            {
                "before": e.input_text.strip(),
                "after": e.output_text.strip() or e.output_text,
                "cls": e.cls,
                "op": e.op,
                "value": str(e.value) if e.value is not None else None,
                "unit": e.unit,
                "input_span": e.input_span.as_pair(),
            }
            for e in res.edits
        ],
        "rejected": [
            {"before": r.input_text, "after": r.output_text,
             "cls": r.cls, "reason": r.reason}
            for r in res.rejected
        ],
        "protected": [p.to_json() for p in res.protected],
        "idempotent": res.is_idempotent(pol, context),
    }
