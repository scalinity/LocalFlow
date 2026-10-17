"""Pure TRAIN-label edits for individually approved acknowledgment commas."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256


def normalize_approved_acknowledgment(row, *, expected_target_sha256, approval_reason,
                                    control_suffix="-ack-noop"):
    """Return an approved label copy and its unchanged TRAIN control.

    The caller supplies the reviewed row whitelist. A matching original-target
    hash and nonempty review reason are required for each call; this helper
    never decides whether an opening is an acknowledgment or direct address.
    """
    if row.get("split") != "train":
        raise ValueError("Acknowledgment edits require TRAIN rows")
    if not isinstance(approval_reason, str) or not approval_reason.strip():
        raise ValueError("An explicit per-row approval reason is required")
    target = row.get("target")
    if not isinstance(target, str) or sha256(target.encode("utf-8")).hexdigest() != expected_target_sha256:
        raise ValueError("Approved target hash does not match")
    sources = [row.get("raw_input"), row.get("model_input")]
    if any(not isinstance(text, str) or text[:5].casefold() != "okay " for text in sources):
        raise ValueError("Both sources must open with comma-free Okay followed by a space")
    if target[:6].casefold() != "okay, ":
        raise ValueError("Target must open with the approved acknowledgment comma")
    source_ids = {key: row.get(key) for key in ("pair_id", "case_id", "family_id")}
    if any(not isinstance(value, str) or not value for value in source_ids.values()):
        raise ValueError("Source pair, case and family IDs are required")
    if not isinstance(control_suffix, str) or not control_suffix.strip():
        raise ValueError("A nonempty control ID suffix is required")

    text = target[:4] + target[5:]
    normalized = deepcopy(row)
    normalized.update(target=text, is_noop=text == row["model_input"])
    normalized.pop("engine_oracle", None)
    normalized["acknowledgment_transform"] = {
        "kind": "approved_opening_comma_removal", "source_ids": source_ids,
        "approval_reason": approval_reason, "original_target_sha256": expected_target_sha256,
        "normalized_target_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "removed_byte": ",", "byte_offset": len(target[:4].encode("utf-8")),
    }
    control = deepcopy(normalized)
    for key in list(control):
        if key in {"engine_oracle", "normalization_edits", "source_coordinates", "source_map",
                   "offset_map", "edit_ledger", "calls", "observations", "target_claude"} or key.endswith(
                ("_offset", "_offsets", "_spans", "_span", "_range", "_ranges", "_coordinates")):
            control.pop(key)
    control.update({key: value + control_suffix for key, value in source_ids.items()})
    control.update(raw_input=text, model_input=text, target=text, is_noop=True, spec_is_noop=True,
                   gold_lines=[], gold_offsets=[], protected_spans=[], normalization_edits=[],
                   normalization_changed=False, obsolete_values=[], removed_fillers=[],
                   variant="acknowledgment_unchanged_control", deterministic_variant=True)
    control["acknowledgment_transform"].update(kind="approved_acknowledgment_unchanged_control",
                                             control_suffix=control_suffix)
    return normalized, control
