"""Conservative ASR capability manifest (Spec S30.1, contract asr_hints.md, M03).

Capabilities are qualified per adapter + checkpoint + runtime, never assumed
from the model family. The current dictation adapter (localflow.stt over
parakeet_mlx, Parakeet TDT 0.6B v3, MLX) exposes text only; every optional
feature is declared unsupported with a reason until a real implementation is
separately qualified. ``unknown`` is not ``supported``, and a ``False`` here
is a boundary statement, not a claim about every possible Parakeet decoder.

Contextual biasing and key terms stay disabled until a supported
implementation passes qualification; ignoring unsupported hints is explicit
and logged (the supervisor/collector record the disposition), and hints are
never concatenated into the transcript and called acoustic context support.
"""

CAPABILITY_FIELDS = (
    "contextual_biasing", "key_terms", "language_hint", "word_timestamps",
    "word_confidence", "n_best", "token_log_probs", "independent_itn",
)

# Reasons are free-form strings for the manifest itself; envelope
# missing_reasons stay within the controlled six-value vocabulary.
_DISABLED_UNTIL_QUALIFIED = "disabled_until_qualified"
_UNSUPPORTED = "unsupported_by_adapter"
_NOT_EXPOSED = "not_exposed_on_dictation_path"


def asr_capability_manifest(model_id, model_revision=None, runtime=None):
    """The M03 manifest for the current adapter: all optional features off."""
    return {
        "adapter": "localflow.stt.Transcriber(parakeet_mlx)",
        "model_id": model_id,
        "model_revision": model_revision,
        "runtime": dict(runtime or {}),
        "capabilities": {
            "contextual_biasing": {
                "supported": False, "reason": _DISABLED_UNTIL_QUALIFIED,
                "evidence": "no qualified biasing implementation exists for"
                            " this adapter (contracts/asr_hints.md baseline)"},
            "key_terms": {
                "supported": False, "reason": _DISABLED_UNTIL_QUALIFIED,
                "evidence": "no qualified key-terms implementation exists for"
                            " this adapter"},
            "language_hint": {
                "supported": False, "reason": _UNSUPPORTED,
                "evidence": "the adapter accepts audio only; no language"
                            " parameter is plumbed through parakeet_mlx"
                            " generate()"},
            "word_timestamps": {
                "supported": False, "reason": _NOT_EXPOSED,
                "evidence": "parakeet_mlx produces token timings used"
                            " internally for long-audio merging; the"
                            " dictation path does not return them, so the"
                            " capability is not qualified as exposed"},
            "word_confidence": {
                "supported": False, "reason": _UNSUPPORTED,
                "evidence": "adapter returns text without scores"},
            "n_best": {
                "supported": False, "reason": _UNSUPPORTED,
                "evidence": "adapter requests a single hypothesis"},
            "token_log_probs": {
                "supported": False, "reason": _UNSUPPORTED,
                "evidence": "adapter does not sample or expose log"
                            " probabilities"},
            "independent_itn": {
                "supported": False, "reason": _UNSUPPORTED,
                "evidence": "inverse-text-normalization is not separately"
                            " controllable on this adapter"},
        },
        "manifest_revision": "m03-conservative-v1",
    }


def missing_reason_for(field: str, manifest=None) -> str:
    """Controlled-vocabulary missing reason for an optional ASR field.

    Maps the manifest's boundary statement into the envelope vocabulary:
    anything the adapter does not expose is ``unsupported_by_adapter``
    (never a fabricated value and never zero)."""
    manifest = manifest or asr_capability_manifest(None)
    cap = manifest["capabilities"].get(field)
    if cap is None:
        return "not_captured_at_stage"
    return "unsupported_by_adapter" if not cap["supported"] else \
        "not_captured_at_stage"


def hint_disposition(manifest=None, hint_set=None) -> dict:
    """What happens to an offered hint set under this manifest (S30.1).

    With M05 a real HintSet can be offered; on this adapter contextual
    biasing stays disabled, so the honest disposition is offered-but-
    ignored — never a fabricated acceptance and never terms silently
    concatenated onto the transcript."""
    manifest = manifest or asr_capability_manifest(None)
    caps = manifest["capabilities"]
    biasing_off = not caps["contextual_biasing"]["supported"]
    offered = len(hint_set.terms) if hint_set is not None else 0
    return {
        "offered_terms": offered,
        "accepted_terms": 0,
        "ignored": bool(biasing_off and offered),
        "ignored_reason": ("disabled_until_qualified"
                           if biasing_off else "unsupported_by_adapter")
        if offered else None,
        "hint_set_id": getattr(hint_set, "hint_set_id", None),
        "vocabulary_revision": getattr(hint_set, "vocabulary_revision",
                                       None),
        "note": "pre-decode biasing stays disabled until qualified and is"
                " never emulated by concatenating terms onto the"
                " transcript; a post-ASR dictionary repair is recorded as"
                " normalization, never as a decoder hit",
    }


def asr_hint_request_fields(hint_set, manifest=None,
                            context_snapshot_id=None) -> dict | None:
    """S30.1 request-field extension point: the engine-neutral fields a
    *qualified* adapter would receive. Returns None on this adapter —
    the dict is built only when the capability manifest actually
    supports contextual biasing, so no request ever pretends to carry
    hints the decoder ignored. The wiring is: qualified adapter →
    serialize these fields into the decode request; unqualified adapter
    → None plus the logged hint_disposition above. M06 feeds
    ``context_snapshot_id`` from the frozen pre-decode
    ``context.ContextSnapshot``."""
    manifest = manifest or asr_capability_manifest(None)
    if not manifest["capabilities"]["contextual_biasing"]["supported"]:
        return None
    return {
        "hint_set_id": hint_set.hint_set_id,
        "context_snapshot_id": context_snapshot_id,
        "terms": [
            {"canonical": t.canonical, "scope": [t.scope_kind,
                                                 t.scope_value],
             "source": t.source, "score": list(t.score)}
            for t in hint_set.terms],
        "language_hint": None,         # language_hint is separately
                                       # qualified; None until then
        "term_limit": hint_set.term_limit,
    }
