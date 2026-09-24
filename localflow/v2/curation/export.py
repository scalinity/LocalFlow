"""Portable dataset export (V2 M14, Spec S29.13, E19.5, contract
dataset_exports.md going live).

A dataset is a directory: ``dataset_manifest.json``,
``examples.jsonl``, ``references.jsonl``, ``preferences.jsonl``,
``artifacts/``, ``SHA256SUMS.txt`` and a small ``README.md`` (task
semantics, known missing fields, allowed uses). Relative paths only.
Task-specific SFT/preference views are derived from this graph at
validation time, never stored as a second truth.

Build discipline (S29.13): selection and content resolve from ONE
consistent store snapshot; the graph is written into a temp directory;
consent state and every selected example's liveness are RECHECKED
immediately before the atomic rename (a revocation or delete during
the build aborts with no export labeled complete — cancellation and
disk-full behave the same); hashes are computed over the written
bytes; the manifest carries a content fingerprint over the semantic
records excluding volatile fields (export ids/times) so identical
revisions reproduce identical fingerprints.

Eligibility is enforced per task view (S29.12): ASR supervised needs
retained audio plus an audio-reviewed verbatim reference AND the
review gate's blessing (a changed-intent or wrong-target fixture is
refused — M14-AC05); cleanup supervised needs the exact stage input
plus an explicit intended-writing mark; preference views need an
explicit comparable judgment over a same-task pair; a span graft is
exported only as its own weak view, never folded into gold. Split
leakage (a family spanning partitions, or a selected family not in
the requested partitions) refuses the whole export (M14-AC08).

Audio files are COPIED with streaming file I/O — never loaded into
RAM — so large datasets export within bounded memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil

from .. import ids
from ..store import TRAINABLE_STATES, Store
from . import review as review_mod

EXPORT_SCHEMA_VERSION = 1
EXPORTER_VERSION = "m14-v1"
ANNOTATION_VERSION = "m09-annotations-v1"
WORD_COUNT_VERSION = "whitespace-split-v1"

TASK_VIEWS = ("asr_supervised", "asr_span_graft_weak",
              "cleanup_supervised", "transform_supervised",
              "preference_pairs")

_LIVE_STATES = TRAINABLE_STATES
_COMPARABLE = ("prefer_a", "prefer_b", "tie", "neither", "uncertain")


class ExportError(Exception):
    """A refused export — the message is content-free (ids/reasons)."""


def _fingerprint(records: dict) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_file(path) -> str:
    """Streaming file hash — audio is never read into RAM whole."""
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _replaceable(destination: pathlib.Path) -> bool:
    """A destination the build may replace: an empty directory, or a
    previous LocalFlow export holding nothing but its own files (its
    manifest carries this exporter's version and its SHA256SUMS lists
    every file present). Anything else — including an earlier export
    the user has since added files to — is never removed."""
    if destination.is_symlink() or not destination.is_dir():
        return False
    if not any(destination.iterdir()):
        return True
    try:
        manifest = json.loads((destination / "dataset_manifest.json")
                              .read_text(encoding="utf-8"))
        sums = (destination / "SHA256SUMS.txt").read_text(
            encoding="utf-8")
    except (OSError, ValueError):
        return False
    if not isinstance(manifest, dict) or \
            "exporter_version" not in manifest:
        return False
    listed = {line.partition("  ")[2].strip()
              for line in sums.splitlines() if line.strip()}
    present = {p.relative_to(destination).as_posix()
               for p in destination.rglob("*")
               if (p.is_file() or p.is_symlink())
               and p.name != "SHA256SUMS.txt"}
    return present <= listed


def _conn_artifact(conn, artifact_id):
    row = conn.execute(
        "SELECT content_text, content_path, purged, sha256, kind, role,"
        " meta_json FROM artifacts WHERE artifact_id=?",
        (artifact_id,)).fetchone() if artifact_id else None
    if row is None or row[2]:
        return None
    return {"id": artifact_id, "text": row[0], "path": row[1],
            "sha256": row[3], "kind": row[4], "role": row[5],
            "meta": json.loads(row[6] or "{}")}


class DatasetExporter:
    """Build and validate portable datasets from the store's evidence
    graph. Construction is cheap; ``build`` is one long operation and
    runs on demand (never on the dictation path)."""

    def __init__(self, store: Store, emit=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)

    # ---- selection (one consistent read) --------------------------------------

    def _select(self, conn, task_views, partitions, assignment_version):
        memberships = {}
        if assignment_version is None:
            assignment_version = conn.execute(
                "SELECT COALESCE(MAX(assignment_version), 0) FROM"
                " split_assignments").fetchone()[0]
        problems = []
        if not assignment_version:
            problems.append(
                "no split assignment exists — assign families before"
                " exporting")
            return {"assignment_version": 0, "memberships": {},
                    "examples": {}, "excluded": [],
                    "problems": problems}
        family_partition = {}
        for ex_id, fam, part, exposed in conn.execute(
                "SELECT example_id, family_id, partition, exposed FROM"
                " training_memberships WHERE assignment_version=?",
                (assignment_version,)).fetchall():
            memberships[ex_id] = (fam, part, bool(exposed))
            prev = family_partition.setdefault(fam, part)
            if prev != part:
                problems.append(
                    f"split leakage: family {fam} spans partitions"
                    f" {prev}/{part}")
        latest = conn.execute(
            "SELECT example_id, envelope_json FROM training_revisions"
            " WHERE rowid IN (SELECT MAX(rowid) FROM training_revisions"
            " GROUP BY example_id)").fetchall()
        states = dict(conn.execute(
            "SELECT example_id, state FROM training_examples").fetchall())
        examples = {}
        excluded_rows = []
        latest_ids = {ex_id for ex_id, _payload in latest}
        # Members of the assignment whose revision graph is gone
        # (delete-everywhere drops revisions) surface as excluded rows
        # — never as silent omissions.
        for ex_id in sorted(set(memberships) - latest_ids):
            excluded_rows.append(
                {"example_id": ex_id, "reason": "revisions_absent"})
        for ex_id, payload in latest:
            if ex_id not in memberships:
                continue  # not part of this assignment version
            fam, part, exposed = memberships[ex_id]
            if part not in partitions:
                continue
            env = json.loads(payload)
            state = states.get(ex_id)
            if state not in _LIVE_STATES:
                excluded_rows.append(
                    {"example_id": ex_id, "reason": f"state_{state}"})
                continue
            if env.get("family_id") and env["family_id"] != fam:
                problems.append(
                    f"stale family assignment: {ex_id} now names a"
                    f" different family than assignment"
                    f" v{assignment_version} — reassign first")
                continue
            if exposed and part == "frozen_test":
                # An exposed family in the blind holdout is known
                # leakage (M14-AC08); exposed development families
                # export normally, flagged.
                problems.append(
                    f"split leakage: exposed family {fam} still in"
                    " frozen_test")
                continue
            examples[ex_id] = env
        return {
            "assignment_version": assignment_version,
            "memberships": memberships,
            "examples": examples,
            "excluded": excluded_rows,
            "problems": problems,
        }

    def _asr_rows(self, conn, sel, task_views):
        """ASR supervised rows: verbatim reference + retained audio +
        the review gate. Grafts land in their own weak view."""
        rows = []
        graft_rows = []
        if not any(v in task_views for v in
                   ("asr_supervised", "asr_span_graft_weak")):
            return rows, graft_rows
        for ex_id, env in sel["examples"].items():
            fam, part, exposed = sel["memberships"][ex_id]
            annotations = env.get("annotations") or []
            verbatim = next((a for a in annotations
                             if a.get("kind") == "verbatim_reference"
                             and a.get("listened_audio")), None)
            audio_aid = (env.get("artifact_ids") or {}).get(
                "original_audio")
            if "asr_supervised" in task_views and verbatim and audio_aid:
                eligible = review_mod.verified_asr_eligible_in(
                    conn, ex_id)
                if not eligible["eligible"]:
                    sel["excluded"].append(
                        {"example_id": ex_id,
                         "reason": f"asr_gate_{eligible['reason']}"})
                else:
                    vref = _conn_artifact(conn, verbatim["artifact_id"])
                    audio = _conn_artifact(conn, audio_aid)
                    if vref is None or audio is None \
                            or audio["path"] is None:
                        sel["excluded"].append(
                            {"example_id": ex_id,
                             "reason": "reference_or_audio_unavailable"})
                    else:
                        rows.append({
                            "example_id": ex_id, "family_id": fam,
                            "split": part, "exposed": exposed,
                            "audio_artifact": audio,
                            "inputs": [audio["id"], vref["id"]],
                            "verbatim_text": vref["text"],
                            "verbatim_annotation_id":
                                verbatim["annotation_id"],
                            "captured_at_utc": env.get("captured_at_utc"),
                            "time_quality": env.get("time_quality"),
                            "transcription_policy":
                                "verbatim_audio_reviewed_v1",
                            "alignment": None,
                            "alignment_note": "no aligner runs in V2"
                                              " (S29.5); clip-level"
                                              " audio only",
                            "consent_revision_id":
                                env.get("consent_revision_id"),
                        })
            if "asr_span_graft_weak" in task_views:
                graft_aid = conn.execute(
                    "SELECT graft_artifact_id FROM correction_labels"
                    " WHERE example_id=? AND graft_artifact_id IS NOT"
                    " NULL ORDER BY revision DESC LIMIT 1",
                    (ex_id,)).fetchone()
                if graft_aid:
                    graft = _conn_artifact(conn, graft_aid[0])
                    if graft is not None:
                        payload = json.loads(graft["text"])
                        if payload.get("coverage_kind") != "partial":
                            sel["problems"].append(
                                "partial graft mislabeled as full gold"
                                f" ({ex_id}) — refused")
                        else:
                            graft_rows.append({
                                "example_id": ex_id, "family_id": fam,
                                "split": part, "exposed": exposed,
                                "inputs": [graft["id"], audio_aid],
                                "graft_text": payload["grafted_text"],
                                "coverage": payload["coverage"],
                                "reference_quality": "weak_partial",
                                "audio_artifact": _conn_artifact(
                                    conn, audio_aid)
                                if audio_aid else None,
                            })
        return rows, graft_rows

    def _cleanup_rows(self, conn, sel, task_views):
        """Cleanup supervised rows (S29.12): the exact cleanup-stage
        input — the normalized text, which is the raw transcript when
        normalization changed nothing — plus every rendered model
        prompt the stage actually sent (instructions and permitted
        context included), the applied output and the explicit
        intended-writing mark."""
        rows = []
        if "cleanup_supervised" not in task_views:
            return rows
        for ex_id, env in sel["examples"].items():
            outcome = env.get("outcome") or {}
            if outcome.get("correctness") != "correct" or \
                    outcome.get("correctness_provenance") != \
                    "user_explicit_intended_writing":
                continue
            arts = env.get("artifact_ids") or {}
            source = _conn_artifact(conn, arts.get("source_text"))
            applied = _conn_artifact(conn, arts.get("applied_output"))
            norm = _conn_artifact(conn, arts.get("normalization"))
            if source is None or applied is None:
                sel["excluded"].append(
                    {"example_id": ex_id,
                     "reason": "stage_inputs_unavailable"})
                continue
            cleanup = env.get("cleanup") or {}
            prompts = []
            prompt_ids = []
            prompts_missing = None
            for p in cleanup.get("passes") or []:
                art = _conn_artifact(conn, p.get("prompt_artifact_id"))
                if art is None or art.get("text") is None:
                    prompts_missing = "prompt_artifact_unavailable"
                    continue
                prompts.append(art["text"])
                prompt_ids.append(art["id"])
            if not cleanup.get("passes"):
                prompts_missing = "no_model_pass_recorded"
            fam, part, exposed = sel["memberships"][ex_id]
            rows.append({
                "example_id": ex_id, "family_id": fam, "split": part,
                "exposed": exposed,
                "source_text": source["text"],
                "inputs": [source["id"], applied["id"],
                           norm["id"] if norm else None, *prompt_ids],
                "input_text": (norm["text"] if norm is not None
                               and norm["role"] == "normalized_text"
                               else source["text"]),
                "model_inputs": prompts,
                "model_inputs_missing_reason": prompts_missing,
                "output_text": applied["text"],
                "cleanup_path": cleanup.get("applied_path"),
                "change_coverage": "intended_writing_marked_whole",
            })
        return rows

    def _transform_rows(self, conn, sel, task_views):
        """Transform supervised rows: a task with retained candidates
        AND an explicit accept judgment (the reviewed desired output),
        one row per accepted candidate, carrying the transform's frozen
        definition revision (instructions and examples) so the task
        input reconstructs offline (S29.12)."""
        rows = []
        if "transform_supervised" not in task_views:
            return rows
        accepts = conn.execute(
            "SELECT task_key, candidate_id FROM preference_observations"
            " WHERE judgment='accept' GROUP BY task_key, candidate_id"
            " ORDER BY MIN(rowid)").fetchall()
        for task_key, candidate_id in accepts:
            cand = conn.execute(
                "SELECT transform_id, transform_revision,"
                " prompt_revision, source_artifact_id,"
                " output_artifact_id FROM transform_candidates WHERE"
                " candidate_id=? AND task_key=?",
                (candidate_id, task_key)).fetchone()
            if cand is None:
                continue
            source = _conn_artifact(conn, cand[3])
            output = _conn_artifact(conn, cand[4])
            definition = conn.execute(
                "SELECT definition_json FROM transform_revisions WHERE"
                " transform_id=? AND revision=?",
                (cand[0], cand[1])).fetchone()
            if source is None or output is None or definition is None:
                sel["excluded"].append(
                    {"candidate_id": candidate_id,
                     "reason": "transform_inputs_unavailable"})
                continue
            rows.append({
                "task_key": task_key,
                "transform_id": cand[0], "transform_revision": cand[1],
                "inputs": [cand[3], cand[4]],
                "prompt_revision": cand[2],
                "transform_definition": json.loads(definition[0]),
                "source_text": source["text"],
                "desired_output_text": output["text"],
            })
        return rows

    def _preference_rows(self, conn, sel, task_views):
        """Preference pair rows: same-task candidates plus an explicit
        comparable judgment (prefer_a/prefer_b/tie/neither/uncertain).
        The store refused cross-task pairs at write time; the export
        re-verifies the pair shares its task key AND its conditional
        input hashes (E19.5 negatives). Judgments are append-only, so
        the LATEST comparable judgment on each candidate pair is the
        one exported (a changed mind supersedes, never averages); slot
        A is the stored ``candidate_id``, slot B ``candidate_b_id``,
        and each candidate keeps its display order."""
        rows = []
        if "preference_pairs" not in task_views:
            return rows
        judgments = conn.execute(
            "SELECT task_key, candidate_id, candidate_b_id, judgment,"
            " created_at_utc FROM preference_observations WHERE"
            f" judgment IN ({','.join('?' * len(_COMPARABLE))})"
            " ORDER BY rowid DESC", _COMPARABLE).fetchall()
        seen_pairs = set()
        for task_key, cand_a, cand_b, judgment, created in judgments:
            pair_key = (task_key, frozenset((cand_a, cand_b)))
            if cand_b is None or pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            pair = conn.execute(
                "SELECT task_key, source_sha256, instructions_sha256,"
                " examples_revision, candidate_id, output_artifact_id,"
                " display_order FROM transform_candidates WHERE"
                " candidate_id IN (?,?)", (cand_a, cand_b)).fetchall()
            if len(pair) != 2 or any(p[0] != task_key for p in pair):
                sel["problems"].append(
                    "preference pair refuses export: candidates do not"
                    " share one task/input identity")
                continue
            if pair[0][1] != pair[1][1] or \
                    pair[0][2] != pair[1][2] or \
                    pair[0][3] != pair[1][3]:
                sel["problems"].append(
                    "preference pair refuses export: conditional input"
                    " hashes differ (S29.10)")
                continue
            by_id = {p[4]: p for p in pair}
            a = by_id[cand_a]
            rows.append({
                "task_key": task_key,
                "judgment": judgment,
                "inputs": [by_id[cand_a][5], by_id[cand_b][5]],
                "input_source_sha256": a[1],
                "instructions_sha256": a[2],
                "examples_revision": a[3],
                "chosen": ("a" if judgment == "prefer_a"
                           else "b" if judgment == "prefer_b" else None),
                "candidates": [
                    {"slot": slot, "display_order": by_id[cid][6],
                     "output_artifact": _conn_artifact(
                         conn, by_id[cid][5])}
                    for slot, cid in (("a", cand_a), ("b", cand_b))],
                "judged_at_utc": created,
            })
        return rows

    # ---- build ------------------------------------------------------------------

    def build(self, destination, *, task_views, partitions=("train",
                  "validation", "frozen_test"),
              assignment_version=None) -> dict:
        """Build one dataset into ``destination`` (a directory path).
        Returns the manifest summary; raises ExportError on any
        refusal with nothing left behind."""
        for view in task_views:
            if view not in TASK_VIEWS:
                raise ExportError(f"unknown task view {view!r}")
        destination = pathlib.Path(destination).expanduser()
        if destination.exists() and not _replaceable(destination):
            # Finalize replaces the destination; only an empty folder
            # or an earlier export may be replaced — never a folder of
            # the user's own files.
            raise ExportError(
                "destination exists and is not empty or a previous"
                " LocalFlow export — choose a new folder name")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.building"
        if staging.is_symlink() or (staging.exists()
                                    and not staging.is_dir()):
            raise ExportError(
                "the build's staging path is not a leftover build"
                " folder — nothing written")
        if staging.exists():
            shutil.rmtree(staging)  # an interrupted earlier build
        export_id = ids.new_id("export")

        def _consent_in(conn) -> str:
            # Inline (a ConsentManager call would nest a submit and
            # deadlock the writer — contracts/store.md).
            row = conn.execute(
                "SELECT state FROM consent_revisions ORDER BY rowid"
                " DESC").fetchone()
            return row[0] if row else "disabled"

        # The store's deletion epoch (tombstone count) when the build
        # read its snapshot — recorded in the manifest.
        baseline_tombstones = None

        def snapshot_op(conn):
            nonlocal baseline_tombstones
            baseline_tombstones = conn.execute(
                "SELECT COUNT(*) FROM deletion_tombstones").fetchone()[0]
            sel = self._select(conn, task_views, set(partitions),
                               assignment_version)
            asr_rows, graft_rows = self._asr_rows(conn, sel, task_views)
            cleanup_rows = self._cleanup_rows(conn, sel, task_views)
            transform_rows = self._transform_rows(conn, sel, task_views)
            preference_rows = self._preference_rows(conn, sel,
                                                    task_views)
            return {
                "sel": sel, "asr": asr_rows, "grafts": graft_rows,
                "cleanup": cleanup_rows,
                "transforms": transform_rows,
                "preferences": preference_rows,
                "consent": _consent_in(conn),
            }
        snap = self.store.submit(snapshot_op)
        problems = (snap["sel"].get("problems") or [])
        if problems:
            # Refusals discovered inside the writer op ride out as
            # data (an in-op ExportError would surface wrapped as a
            # RuntimeError and escape the caller's catch).
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error="refused")
            raise ExportError(problems[0])
        if snap["consent"] != "enabled":
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error="consent_not_enabled")
            raise ExportError(
                "collection consent is not enabled — an export needs"
                " the material to still be consented (S29.13)")
        try:
            staging.mkdir(parents=True)
            art_dir = staging / "artifacts"
            art_dir.mkdir()
            copied = {}

            def copy_audio(artifact):
                if artifact is None or artifact.get("path") is None:
                    return None
                rel = f"artifacts/{artifact['id']}.wav"
                if rel not in copied:
                    # Streaming copy and hash — never loads audio into
                    # RAM. The copy must match the hash recorded at
                    # capture: a damaged or swapped payload is refused
                    # rather than exported under the original's name.
                    shutil.copyfile(
                        self.store.artifacts_dir / artifact["path"],
                        staging / rel)
                    digest = _sha256_file(staging / rel)
                    if artifact["sha256"] and digest != artifact["sha256"]:
                        raise ExportError(
                            f"audio payload hash mismatch for"
                            f" {artifact['id']} — stale or damaged"
                            " source refused")
                    copied[rel] = digest
                return rel

            references = []
            examples = []
            for row in snap["asr"]:
                rel = copy_audio(row["audio_artifact"])
                if rel is None:
                    continue
                examples.append({
                    "example_id": row["example_id"],
                    "family_id": row["family_id"], "split": row["split"],
                    "task_kind": "asr_supervised",
                    "audio": rel,
                    "audio_sha256": copied[rel],
                    "captured_at_utc": row["captured_at_utc"],
                    "time_quality": row["time_quality"],
                    "exposed": row["exposed"],
                })
                references.append({
                    "example_id": row["example_id"],
                    "kind": "verbatim_speech",
                    "coverage": "full",
                    "text": row["verbatim_text"],
                    "transcription_policy":
                        row["transcription_policy"],
                    "listened_audio": True,
                    "reviewer": "hub_user",
                })
            for row in snap["grafts"]:
                rel = copy_audio(row.get("audio_artifact"))
                examples.append({
                    "example_id": row["example_id"],
                    "family_id": row["family_id"], "split": row["split"],
                    "task_kind": "asr_span_graft_weak",
                    "audio": rel,
                    "audio_sha256": copied.get(rel) if rel else None,
                    "exposed": row["exposed"],
                })
                references.append({
                    "example_id": row["example_id"],
                    "kind": "span_graft",
                    "coverage": "partial",
                    "coverage_spans": row["coverage"],
                    "grafted_text": row["graft_text"],
                    "reference_quality": "weak_partial",
                    "note": "unreviewed remainder unverified — never"
                            " full gold (S29.7)",
                })
            for row in snap["cleanup"]:
                examples.append({
                    "example_id": row["example_id"],
                    "family_id": row["family_id"], "split": row["split"],
                    "task_kind": "cleanup_supervised",
                    "input_text": row["input_text"],
                    "output_text": row["output_text"],
                    "cleanup_path": row["cleanup_path"],
                    "source_text": row["source_text"],
                    "model_inputs": row["model_inputs"],
                    "model_inputs_missing_reason":
                        row["model_inputs_missing_reason"],
                    "exposed": row["exposed"],
                })
                references.append({
                    "example_id": row["example_id"],
                    "kind": "intended_writing",
                    "coverage": "full",
                    "text": row["output_text"],
                    "provenance": "user_explicit_intended_writing",
                })
            for row in snap["transforms"]:
                examples.append({
                    "task_key": row["task_key"],
                    "task_kind": "transform_supervised",
                    "transform_id": row["transform_id"],
                    "transform_revision": row["transform_revision"],
                    "prompt_revision": row["prompt_revision"],
                    "input_text": row["source_text"],
                    "output_text": row["desired_output_text"],
                    "transform_definition": row["transform_definition"],
                })
            preferences = []
            for row in snap["preferences"]:
                cands = []
                for cand in row["candidates"]:
                    art = cand["output_artifact"]
                    if art is None or art.get("text") is None:
                        raise ExportError(
                            "preference candidate payload unavailable")
                    cands.append({"slot": cand["slot"],
                                  "display_order": cand["display_order"],
                                  "output_text": art["text"]})
                preferences.append({
                    "task_key": row["task_key"],
                    "task_kind": "preference",
                    "input_source_sha256":
                        row["input_source_sha256"],
                    "instructions_sha256":
                        row["instructions_sha256"],
                    "examples_revision": row["examples_revision"],
                    "judgment": row["judgment"],
                    "chosen": row["chosen"],
                    "candidates": cands,
                    "judged_at_utc": row["judged_at_utc"],
                })
            counts = {
                "asr_supervised": sum(
                    1 for e in examples
                    if e["task_kind"] == "asr_supervised"),
                "asr_span_graft_weak": sum(
                    1 for e in examples
                    if e["task_kind"] == "asr_span_graft_weak"),
                "cleanup_supervised": sum(
                    1 for e in examples
                    if e["task_kind"] == "cleanup_supervised"),
                "transform_supervised": sum(
                    1 for e in examples
                    if e["task_kind"] == "transform_supervised"),
                "preference_pairs": len(preferences),
            }
            semantic = {
                "examples": sorted(
                    examples, key=lambda e: json.dumps(
                        e, sort_keys=True)),
                "references": sorted(
                    references, key=lambda e: json.dumps(
                        e, sort_keys=True)),
                "preferences": sorted(
                    preferences, key=lambda e: json.dumps(
                        e, sort_keys=True)),
            }
            fingerprint = _fingerprint(semantic)
            manifest = {
                "training_schema_version": 1,
                "export_schema_version": EXPORT_SCHEMA_VERSION,
                "exporter_version": EXPORTER_VERSION,
                "annotation_version": ANNOTATION_VERSION,
                "word_count_version": WORD_COUNT_VERSION,
                "export_id": export_id,
                "task_views": sorted(task_views),
                "assignment_version": snap["sel"]["assignment_version"],
                "partitions": sorted(partitions),
                "counts": counts,
                "excluded": snap["sel"]["excluded"],
                "excluded_note": "content-free reasons only — no"
                                 " transcript excerpts (E19.5)",
                "content_fingerprint": fingerprint,
                # The store's deletion epoch (tombstone count) the build
                # read from — provenance for later comparison.
                # Manifest-level: it is not part of any record.
                "deletion_epoch": baseline_tombstones,
                "files": ["examples.jsonl", "references.jsonl",
                          "preferences.jsonl", "README.md"],
                "allowed_uses": "local personalization research on the"
                                " exporting machine; single-speaker"
                                " scope (S29.11)",
            }
            _write_jsonl(staging / "examples.jsonl", semantic["examples"])
            _write_jsonl(staging / "references.jsonl",
                         semantic["references"])
            _write_jsonl(staging / "preferences.jsonl",
                         semantic["preferences"])
            (staging / "README.md").write_text(_dataset_readme(
                manifest), encoding="utf-8")
            (staging / "dataset_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=1,
                           sort_keys=True), encoding="utf-8")
            _write_sums(staging)
            # --- finalize recheck: revocation, or deletion/expiry of
            # anything this build exported, aborts it; nothing is left
            # labeled complete. A deletion elsewhere in the store does
            # not concern this dataset and does not abort it.
            inputs = sorted({aid for key in ("asr", "grafts", "cleanup",
                                             "transforms", "preferences")
                             for row in snap[key]
                             for aid in row.get("inputs") or () if aid})

            def recheck_op(conn):
                if _consent_in(conn) != "enabled":
                    return False
                for i in range(0, len(inputs), 500):
                    chunk = inputs[i:i + 500]
                    if conn.execute(
                            "SELECT 1 FROM artifacts WHERE purged=1 AND"
                            f" artifact_id IN ({','.join('?' * len(chunk))})"
                            " LIMIT 1", chunk).fetchone():
                        return False
                for ex in examples:
                    ex_id = ex.get("example_id")
                    if not ex_id:
                        continue  # task-keyed rows (transform pairs)
                    row = conn.execute(
                        "SELECT state FROM training_examples WHERE"
                        " example_id=?", (ex_id,)).fetchone()
                    if row is None or row[0] not in _LIVE_STATES:
                        return False
                return True
            if not self.store.submit(recheck_op):
                raise ExportError(
                    "consent revoked or content deleted during the"
                    " build — export aborted before completion"
                    " (S29.13)")
            if destination.exists():
                if not _replaceable(destination):
                    raise ExportError(
                        "destination changed during the build and is"
                        " no longer replaceable — nothing written")
                shutil.rmtree(destination)
            os.rename(staging, destination)
        except ExportError:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error="refused")
            raise
        except Exception as e:
            # Disk full, a store stall during the recheck, anything:
            # nothing is left labeled complete and no staging remains.
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error=type(e).__name__)
            raise ExportError(f"export failed: {type(e).__name__}")
        summary = self._record(
            export_id, "complete", task_views, manifest, destination,
            fingerprint,
            {**counts,
             "examples": len(examples), "references": len(references),
             "preferences": len(preferences),
             "excluded": len(snap["sel"]["excluded"])})
        self.emit("export.completed", level="INFO",
                  reason_code=",".join(sorted(task_views)),
                  detail=f"examples={len(examples)}")
        return summary

    def _record(self, export_id, state, task_views, manifest,
                destination, fingerprint, counts, error=None):
        def op(conn):
            now = ids.now_utc_iso()
            conn.execute(
                "INSERT OR REPLACE INTO export_manifests(export_id,"
                " state, task_views_json, manifest_json, destination,"
                " fingerprint, examples_count, excluded_count, error,"
                " created_at_utc, finalized_at_utc)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (export_id, state, json.dumps(sorted(task_views)),
                 json.dumps(manifest, sort_keys=True) if manifest
                 else None, str(destination) if destination else None,
                 fingerprint,
                 (counts or {}).get("examples"),
                 (counts or {}).get("excluded"),
                 error, now,
                 now if state == "complete" else None))
            return {"export_id": export_id, "state": state,
                    "fingerprint": fingerprint,
                    "counts": counts, "error": error}
        return self.store.submit(op)

    def last_export(self) -> dict | None:
        def op(conn):
            row = conn.execute(
                "SELECT export_id, state, task_views_json,"
                " manifest_json, destination, fingerprint,"
                " examples_count, excluded_count, error, created_at_utc,"
                " finalized_at_utc FROM export_manifests ORDER BY rowid"
                " DESC LIMIT 1").fetchone()
            if row is None:
                return None
            return {"export_id": row[0], "state": row[1],
                    "task_views": json.loads(row[2]),
                    "manifest": json.loads(row[3]) if row[3] else None,
                    "destination": row[4], "fingerprint": row[5],
                    "examples_count": row[6],
                    "excluded_count": row[7], "error": row[8],
                    "created_at_utc": row[9], "finalized_at_utc": row[10]}
        return self.store.submit(op)


# ---- serialization helpers ------------------------------------------------


def _write_jsonl(path: pathlib.Path, rows: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")


def _write_sums(root: pathlib.Path):
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            lines.append(f"{_sha256_file(p)}"
                         f"  {p.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def _dataset_readme(manifest: dict) -> str:
    return (
        "# LocalFlow personal dataset export\n\n"
        f"Exporter {manifest['exporter_version']}, schema"
        f" {manifest['export_schema_version']}. Task views:"
        f" {', '.join(manifest['task_views'])}. Counts:"
        f" {json.dumps(manifest['counts'], sort_keys=True)}.\n\n"
        "Single-speaker personalization material (S29.11): no"
        " speaker-independent generalization is claimed. References"
        " carry their coverage; span grafts are weak/partial and never"
        " full gold. Known missing fields: no forced alignment, no"
        " token log-probabilities (unsupported by the current"
        " adapters). Allowed uses: local personalization research;"
        " provider upload is a separate explicit decision.\n"
        f"Content fingerprint: {manifest['content_fingerprint']}\n")


# ---- the standalone validator (no store, no network) ----------------------


def _safe_rel(rel) -> bool:
    """A relative POSIX path inside the dataset (no absolute path, no
    traversal)."""
    return isinstance(rel, str) and bool(rel) and \
        not rel.startswith("/") and \
        ".." not in pathlib.PurePosixPath(rel).parts


def validate_dataset(root) -> dict:
    """Validate a dataset directory WITHOUT the app database, from any
    working directory (E19.5 offline reconstruction): hashes, manifest
    structure, relative-path safety, task-input reconstructability and
    the graft/preference invariants. The directory is untrusted input:
    every structural surprise is an issue in the report, never an
    exception, and symlinks are reported, never followed. Returns a
    report with issues[] (empty ⇒ valid)."""
    root = pathlib.Path(root)
    issues = []
    if root.is_symlink() or not root.is_dir():
        return {"valid": False, "issues": ["not a directory"]}
    sums = root / "SHA256SUMS.txt"
    manifest_path = root / "dataset_manifest.json"
    for p in (sums, manifest_path):
        if p.is_symlink() or not p.is_file():
            return {"valid": False, "issues": [f"missing {p.name}"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sums_text = sums.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {"valid": False, "issues": ["manifest or sums unreadable"]}
    if not isinstance(manifest, dict):
        return {"valid": False, "issues": ["manifest is not an object"]}
    if manifest.get("export_schema_version") != EXPORT_SCHEMA_VERSION:
        issues.append("unsupported export schema version")
    symlinks = {p.relative_to(root).as_posix()
                for p in root.rglob("*") if p.is_symlink()}
    for rel in sorted(symlinks):
        issues.append(f"symlink in dataset: {rel}")
    # Hash every listed file; reject absolute/traversal paths. The sums
    # must be complete: every file in the directory is listed (an
    # unlisted file could be swapped in unverified), including the
    # manifest and the record files.
    listed = {}
    for line in sums_text.splitlines():
        if not line.strip():
            continue
        digest, _sep, rel = line.partition("  ")
        rel = rel.strip()
        if not _safe_rel(rel):
            issues.append(f"unsafe path in SHA256SUMS: {rel}")
            continue
        listed[rel] = digest
        p = root / rel
        if rel in symlinks:
            continue
        if not p.is_file():
            issues.append(f"missing file {rel}")
            continue
        if _sha256_file(p) != digest:
            issues.append(f"hash mismatch {rel}")
    present = {p.relative_to(root).as_posix()
               for p in root.rglob("*")
               if p.is_file() and not p.is_symlink()
               and p.name != "SHA256SUMS.txt"}
    for rel in sorted(present - set(listed)):
        issues.append(f"file not in SHA256SUMS: {rel}")
    for rel in ("dataset_manifest.json", "examples.jsonl",
                "references.jsonl", "preferences.jsonl"):
        if rel not in listed:
            issues.append(f"SHA256SUMS does not cover {rel}")
    # Reconstruct each view's required inputs.
    examples = _read_jsonl(root / "examples.jsonl", issues)
    references = _read_jsonl(root / "references.jsonl", issues)
    preferences = _read_jsonl(root / "preferences.jsonl", issues)
    for ex in examples:
        audio = ex.get("audio")
        if audio is None:
            if ex.get("task_kind") == "asr_supervised":
                issues.append(
                    f"asr example {ex.get('example_id')} missing audio")
            continue
        if not _safe_rel(audio):
            issues.append("unsafe audio path")
            continue
        if audio in symlinks or not (root / audio).is_file():
            issues.append(
                f"example {ex.get('example_id')} missing audio")
        elif listed.get(audio) != ex.get("audio_sha256"):
            issues.append(
                f"audio hash disagrees with SHA256SUMS for example"
                f" {ex.get('example_id')}")
    for ref in references:
        if ref.get("kind") == "span_graft" and \
                ref.get("coverage") != "partial":
            issues.append("graft reference not marked partial")
        if ref.get("kind") == "verbatim_speech" and \
                not ref.get("listened_audio"):
            issues.append("verbatim reference without audio review")
    for pref in preferences:
        cands = pref.get("candidates")
        if not isinstance(cands, list) or len(cands) != 2:
            issues.append("preference without a candidate pair")
            continue
        if pref.get("judgment") not in _COMPARABLE:
            issues.append("preference judgment not comparable")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        issues.append("manifest counts missing")
        counts = {}
    for kind in TASK_VIEWS:
        expected = counts.get(kind)
        actual = sum(1 for e in examples
                     if e.get("task_kind") == kind) \
            if kind != "preference_pairs" else len(preferences)
        if expected is not None and expected != actual:
            issues.append(
                f"manifest count mismatch {kind}:"
                f" {expected} vs {actual}")
    # Determinism support: the fingerprint must verify against the
    # semantic records (volatile fields excluded).
    semantic = {name: sorted(rows, key=lambda e: json.dumps(
                    e, sort_keys=True))
                for name, rows in (("examples", examples),
                                   ("references", references),
                                   ("preferences", preferences))}
    if manifest.get("content_fingerprint") and \
            _fingerprint(semantic) != manifest["content_fingerprint"]:
        issues.append("content fingerprint mismatch")
    return {"valid": not issues, "issues": sorted(set(issues)),
            "counts": {k: sum(1 for e in examples
                              if e.get("task_kind") == k)
                       for k in ("asr_supervised",
                                 "asr_span_graft_weak",
                                 "cleanup_supervised",
                                 "transform_supervised")} | {
                       "preference_pairs": len(preferences)}}


def _read_jsonl(path: pathlib.Path, issues: list) -> list[dict]:
    """The file's JSON-object rows; anything else is an issue."""
    if path.is_symlink() or not path.is_file():
        issues.append(f"missing {path.name}")
        return []
    rows = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        issues.append(f"{path.name} unreadable")
        return []
    for i, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            issues.append(f"{path.name}:{i + 1} unparsable")
            continue
        if not isinstance(row, dict):
            issues.append(f"{path.name}:{i + 1} is not an object")
            continue
        rows.append(row)
    return rows
