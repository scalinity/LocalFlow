"""Qualified evidence resolution for every M14 consumer (V2 M14,
m14-policy-r1 D11, contracts/dataset_exports.md).

An artifact id is never evidence by itself. ``qualify`` admits one
artifact for one semantic slot only when it exists, is unpurged,
belongs to the expected job (or, for a transform artifact written
detached from any job, to the expected task), carries the role its
producer writes for that slot, still holds its payload and matches its
recorded digest. The ASR promotion gate, the export views, readiness
task eligibility, stage attribution for mining/teach and the profile's
speech read all resolve through here — one predicate, never parallel
copies that drift.

The task predicates below (cleanup, transform target, preference pair)
return a typed result with a content-free reason, shared by the
exporter and readiness so the two can never disagree about who is
eligible (M14-AUDIT-14).

Everything runs INSIDE a writer op (``conn``): a nested ``Store.submit``
from here would deadlock the single writer.
"""

from __future__ import annotations

import json

from .. import ids
from ..store import managed_name_ok, open_managed_file

# The producers' own roles per slot (training.py, insertion/observation.py,
# transforms_store.py, training_data.py, curation/review.py, learning.py).
SLOT_ROLES = {
    "source_text": ("raw_transcript",),
    "applied_output": ("applied_output",),
    "normalization": ("normalized_text", "normalization_ledger"),
    "original_audio": ("original_audio",),
    "verbatim_reference": ("verbatim_reference",),
    "span_graft": ("span_graft",),
    "transform_source": ("transform_source",),
    "transform_output": ("transform_output",),
    "observation_before": ("observation_before_range",),
    "observation_after": ("observation_after_range",),
    "candidate_observation": ("candidate_observation",),
}
# A cleanup pass prompt is ``cleanup_input_<kind>`` (kind model_input).
_PROMPT_PREFIX = "cleanup_input_"
_AUDIO_SLOTS = ("original_audio",)

CLEANUP_TIERS = ("model_task_complete", "text_pair_only")


def slot_role_ok(slot: str, role) -> bool:
    if slot == "cleanup_prompt":
        return isinstance(role, str) and role.startswith(_PROMPT_PREFIX)
    return role in SLOT_ROLES.get(slot, ())


def conn_example_job(conn, example_id):
    row = conn.execute(
        "SELECT job_id FROM training_examples WHERE example_id=?",
        (example_id,)).fetchone() if example_id else None
    return row[0] if row else None


def qualify(conn, artifact_id, slot: str, *, job_id=None, task_key=None,
            digest: bool = True, artifacts_dir=None) -> dict:
    """``{"ok": True, "artifact": {...}}`` for an artifact admitted as
    evidence for ``slot``, else ``{"ok": False, "reason": code}`` with a
    content-free code naming the slot and the failed condition.

    ``job_id`` (the owning job) and/or ``task_key`` (a transform
    artifact's task, recorded in its meta) are the expected owner; at
    least one must be given — an owner-less check is not a check."""
    if job_id is None and task_key is None:
        raise ValueError("qualify needs an expected owner")
    if not artifact_id:
        return {"ok": False, "reason": f"{slot}_missing"}
    row = conn.execute(
        "SELECT job_id, role, purged, content_text, content_path, sha256,"
        " meta_json, kind FROM artifacts WHERE artifact_id=?",
        (artifact_id,)).fetchone()
    if row is None:
        return {"ok": False, "reason": f"{slot}_absent"}
    owner, role, purged, text, path, sha, meta_raw, kind = row
    if purged:
        return {"ok": False, "reason": f"{slot}_purged"}
    if not slot_role_ok(slot, role):
        return {"ok": False, "reason": f"{slot}_wrong_role"}
    try:
        meta = json.loads(meta_raw or "{}")
    except ValueError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    if job_id is not None and owner != job_id:
        return {"ok": False, "reason": f"{slot}_foreign_job"}
    if task_key is not None and meta.get("task_key") != task_key:
        return {"ok": False, "reason": f"{slot}_foreign_task"}
    if slot in _AUDIO_SLOTS:
        # Audio lives as ONE plain managed file name in the artifact
        # directory; anything else (absolute, traversal, a separator)
        # is never opened (M14-AUDIT-05). The id names the exported copy
        # (``artifacts/<id>.wav``), so it must be a plain name too.
        if not path or not managed_name_ok(path) or \
                not managed_name_ok(artifact_id):
            return {"ok": False, "reason": f"{slot}_path_refused"}
        # Given the artifact directory, the payload must be there as a
        # regular file too — a gate that admits a vanished file would
        # disagree with the export that has to copy it.
        if artifacts_dir is not None:
            handle = open_managed_file(artifacts_dir, path)
            if handle is None:
                return {"ok": False, "reason": f"{slot}_payload_absent"}
            handle.close()
    else:
        if text is None:
            return {"ok": False, "reason": f"{slot}_payload_absent"}
        if digest and sha and ids.sha256_text(text) != sha:
            return {"ok": False, "reason": f"{slot}_digest_mismatch"}
    return {"ok": True, "artifact": {
        "id": artifact_id, "job_id": owner, "role": role, "text": text,
        "path": path, "sha256": sha, "meta": meta, "kind": kind}}


# ---- task predicates (shared by readiness and export) -------------------


def cleanup_qualification_in(conn, example_id, env, job_id=None) -> dict:
    """The cleanup_supervised predicate (S29.12, m14-policy-r1 D03):
    an explicit intended-writing ``correct`` mark AND the exact stage
    input and applied output, owned by the example's job with their
    producer roles. ``tier`` says whether every recorded model pass's
    exact prompt is retained too (``model_task_complete``) or the
    record is an intended-writing text pair only."""
    # The owner is the example row's job — never what an envelope claims.
    job_id = job_id or conn_example_job(conn, example_id)
    outcome = (env or {}).get("outcome") or {}
    correctness = outcome.get("correctness")
    if outcome.get("correctness_provenance") != \
            "user_explicit_intended_writing" or correctness not in (
                "correct", "incorrect"):
        return {"eligible": False, "reason": "no_intended_writing_mark"}
    if correctness != "correct":
        # An explicit "not what I meant" is review evidence, never a
        # supervised target (the applied text is known to be wrong).
        return {"eligible": False, "reason": "intended_writing_incorrect"}
    arts = (env or {}).get("artifact_ids") or {}
    source = qualify(conn, arts.get("source_text"), "source_text",
                     job_id=job_id)
    if not source["ok"]:
        return {"eligible": False, "reason": source["reason"]}
    applied = qualify(conn, arts.get("applied_output"), "applied_output",
                      job_id=job_id)
    if not applied["ok"]:
        return {"eligible": False, "reason": applied["reason"]}
    norm = None
    if arts.get("normalization"):
        norm_q = qualify(conn, arts["normalization"], "normalization",
                         job_id=job_id)
        if not norm_q["ok"]:
            return {"eligible": False, "reason": norm_q["reason"]}
        norm = norm_q["artifact"]
    input_text = norm["text"] if norm is not None \
        and norm["role"] == "normalized_text" else source["artifact"]["text"]
    passes = ((env or {}).get("cleanup") or {}).get("passes") or []
    prompts = []
    missing = None
    for p in passes:
        q = qualify(conn, p.get("prompt_artifact_id"), "cleanup_prompt",
                    job_id=job_id)
        if not q["ok"]:
            missing = q["reason"]
            continue
        prompts.append(q["artifact"])
    if not passes:
        missing = "no_model_pass_recorded"
    tier = "model_task_complete" if passes and missing is None \
        else "text_pair_only"
    return {"eligible": True, "reason": None, "tier": tier,
            "source": source["artifact"], "applied": applied["artifact"],
            "normalization": norm, "input_text": input_text,
            "prompts": prompts, "model_inputs_missing_reason": missing}


def transform_target_in(conn, task_key, candidate_id) -> dict:
    """The transform_supervised predicate (m14-policy-r1 D07): the
    candidate's latest single-candidate accept/reject is ``accept``
    (an undo is an insertion reversal and changes nothing; automatic
    application is never a judgment), its source and output are this
    task's retained artifacts, the source is the exact task input
    (digest equal to the task's source hash) and the frozen definition
    revision exists."""
    cand = conn.execute(
        "SELECT transform_id, transform_revision, prompt_revision,"
        " source_artifact_id, output_artifact_id, path, source_sha256"
        " FROM transform_candidates WHERE candidate_id=? AND task_key=?",
        (candidate_id, task_key)).fetchone()
    if cand is None:
        return {"eligible": False, "reason": "candidate_absent"}
    latest = conn.execute(
        "SELECT judgment, observation_id FROM preference_observations"
        " WHERE task_key=? AND candidate_id=? AND candidate_b_id IS NULL"
        " AND judgment IN ('accept','reject') ORDER BY rowid DESC"
        " LIMIT 1", (task_key, candidate_id)).fetchone()
    if latest is None or latest[0] != "accept":
        return {"eligible": False, "reason": "no_current_accept"}
    source = qualify(conn, cand[3], "transform_source", task_key=task_key)
    if not source["ok"]:
        return {"eligible": False, "reason": source["reason"]}
    if ids.sha256_text(source["artifact"]["text"]) != cand[6]:
        return {"eligible": False, "reason": "source_digest_mismatch"}
    output = qualify(conn, cand[4], "transform_output", task_key=task_key)
    if not output["ok"]:
        return {"eligible": False, "reason": output["reason"]}
    definition = conn.execute(
        "SELECT definition_json FROM transform_revisions WHERE"
        " transform_id=? AND revision=?", (cand[0], cand[1])).fetchone()
    if definition is None:
        return {"eligible": False, "reason": "definition_absent"}
    return {"eligible": True, "reason": None,
            "transform_id": cand[0], "transform_revision": cand[1],
            "prompt_revision": cand[2], "automated_path": cand[5],
            "source": source["artifact"], "output": output["artifact"],
            "definition": json.loads(definition[0]),
            "judgment_observation_id": latest[1]}


# ---- operation receipts (m14-policy-r1 D09/D12, M14-AUDIT-17) ------------


class OperationReused(ValueError):
    """An operation id already names a different kind of action."""


def receipt_in(conn, operation_id, kind):
    """The recorded receipt of a completed operation (a retry of the
    same logical action returns it and writes nothing), or None."""
    if not operation_id:
        return None
    row = conn.execute(
        "SELECT kind, receipt_json FROM m14_operation_receipts WHERE"
        " operation_id=?", (operation_id,)).fetchone()
    if row is None:
        return None
    if row[0] != kind:
        raise OperationReused("operation_id_reused")
    return json.loads(row[1])


def record_receipt_in(conn, operation_id, kind, target_id, receipt):
    """Record the outcome in the SAME op as the effect it describes."""
    if not operation_id:
        return receipt
    conn.execute(
        "INSERT INTO m14_operation_receipts(operation_id, kind, target_id,"
        " receipt_json, created_at_utc) VALUES(?,?,?,?,?)",
        (operation_id, kind, target_id,
         json.dumps(receipt, sort_keys=True), ids.now_utc_iso()))
    return receipt


COMPARABLE = ("prefer_a", "prefer_b", "tie", "neither", "uncertain")


def current_pair_judgments_in(conn):
    """The CURRENT comparable judgment per unordered same-task pair:
    judgments append, the latest one on a pair is its current one (a
    changed mind supersedes, never averages). Returns rows
    (task_key, cand_a, cand_b, judgment, created_at_utc, observation_id)
    in the slot order the latest judgment recorded."""
    seen = set()
    out = []
    for row in conn.execute(
            "SELECT task_key, candidate_id, candidate_b_id, judgment,"
            " created_at_utc, observation_id FROM preference_observations"
            f" WHERE judgment IN ({','.join('?' * len(COMPARABLE))})"
            " AND candidate_b_id IS NOT NULL ORDER BY rowid DESC",
            COMPARABLE).fetchall():
        key = (row[0], frozenset((row[1], row[2])))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def preference_pair_in(conn, task_key, cand_a, cand_b) -> dict:
    """The preference_pairs predicate (S29.10, M14-AUDIT-08): both
    candidates belong to this task with identical conditional input
    hashes, both outputs and the task source are this task's retained
    artifacts with their producer roles, and the retained source is the
    exact input the task hash names. Returns the reconstructable task:
    the input text and both outputs."""
    rows = conn.execute(
        "SELECT candidate_id, task_key, source_sha256,"
        " instructions_sha256, examples_revision, source_artifact_id,"
        " output_artifact_id, display_order, transform_id,"
        " transform_revision, prompt_revision FROM transform_candidates"
        " WHERE candidate_id IN (?,?)", (cand_a, cand_b)).fetchall()
    by_id = {r[0]: r for r in rows}
    if len(by_id) != 2 or any(r[1] != task_key for r in rows):
        return {"eligible": False, "reason": "not_same_task"}
    a, b = by_id[cand_a], by_id[cand_b]
    if a[2:5] != b[2:5]:
        return {"eligible": False, "reason": "input_hashes_differ"}
    source = None
    for cand in (a, b):
        q = qualify(conn, cand[5], "transform_source", task_key=task_key)
        if not q["ok"]:
            return {"eligible": False, "reason": q["reason"]}
        if ids.sha256_text(q["artifact"]["text"]) != cand[2]:
            return {"eligible": False, "reason": "source_digest_mismatch"}
        source = q["artifact"]
    outputs = {}
    for slot, cand in (("a", a), ("b", b)):
        q = qualify(conn, cand[6], "transform_output", task_key=task_key)
        if not q["ok"]:
            return {"eligible": False, "reason": q["reason"]}
        outputs[slot] = {"candidate_id": cand[0], "display_order": cand[7],
                         "artifact": q["artifact"]}
    return {"eligible": True, "reason": None, "source": source,
            "input_source_sha256": a[2], "instructions_sha256": a[3],
            "examples_revision": a[4], "transform_id": a[8],
            "transform_revision": a[9], "prompt_revision": a[10],
            "outputs": outputs}
