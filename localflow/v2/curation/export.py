"""Portable dataset export (V2 M14, Spec S29.13, E19.5, contract
dataset_exports.md going live).

A dataset is a directory: ``dataset_manifest.json``,
``examples.jsonl``, ``references.jsonl``, ``preferences.jsonl``,
``artifacts/``, ``SHA256SUMS.txt`` and a small ``README.md`` (task
semantics, known missing fields, allowed uses). Relative paths only.
Task-specific SFT/preference views are derived from this graph at
validation time, never stored as a second truth.

Evidence (m14-policy-r1 D11): every artifact a record uses is admitted
through ``curation.evidence`` — this example's (or this task's) own
retained artifact with its producer role and matching digest. Each
record carries its lineage (job, revision, family and assignment
version, consent revision, every input artifact's id/role/owner/digest
and the human decision it rests on) and the exact conditional inputs a
task needs, so the package reconstructs and qualifies offline.

Build discipline (S29.13, D09):

- selection and content resolve from ONE consistent store snapshot;
- the graph is written into a staging directory the build creates
  EXCLUSIVELY for itself (named with its export id, marked with an
  ownership file) — no pre-existing path is ever deleted or reused;
- audio is opened only as a plain managed file name through a no-follow
  descriptor and streamed (never loaded into RAM), its copy hashed and
  checked against the digest recorded at capture;
- publication is ONE store writer op: it re-checks consent and every
  selected dependency (artifacts present and unpurged, example state
  and revision, label revisions, current judgments) and renames the
  staging directory onto the destination. A deletion or revocation
  serialized before that op aborts the build; a deletion elsewhere in
  the store does not concern this dataset;
- the manifest carries a content fingerprint over the semantic records
  excluding volatile fields (export ids/times) so identical revisions
  reproduce identical fingerprints.

Eligibility is enforced per task view (S29.12) with the SAME typed
predicates readiness reports (M14-AUDIT-14). Split leakage — a family
spanning partitions, a selected family not in the requested
partitions, or a family exposed in ANY assignment version still in
frozen_test (D10) — refuses the whole export. Task-keyed transform and
preference rows carry no family and are exported, explicitly
unpartitioned, only when the requested partitions include train (D02).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil

from .. import ids
from ..store import TRAINABLE_STATES, Store, open_managed_file
from . import evidence as ev
from . import review as review_mod

EXPORT_SCHEMA_VERSION = 2
EXPORTER_VERSION = "m14-v2"
ANNOTATION_VERSION = "m09-annotations-v1"
WORD_COUNT_VERSION = "whitespace-split-v1"
LINEAGE_VERSION = "m14-lineage-v1"

TASK_VIEWS = ("asr_supervised", "asr_span_graft_weak",
              "cleanup_supervised", "transform_supervised",
              "preference_pairs")
_EXAMPLE_VIEWS = ("asr_supervised", "asr_span_graft_weak",
                  "cleanup_supervised")
_TASK_VIEWS = ("transform_supervised", "preference_pairs")

_LIVE_STATES = TRAINABLE_STATES
_COMPARABLE = ev.COMPARABLE
_OWNER_FILE = ".localflow-export-owner"


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
    manifest carries an exporter version and its SHA256SUMS lists
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


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _input(art: dict) -> dict:
    """A content-free lineage entry for one admitted input artifact."""
    return {"artifact_id": art["id"], "role": art["role"],
            "job_id": art["job_id"], "sha256": art["sha256"],
            "task_key": (art.get("meta") or {}).get("task_key")}


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
        # Exposure is forward-only across every NEW export (D10): a
        # family exposed in ANY assignment version is exposed now, even
        # when an older version is requested.
        exposed_ever = {r[0]: r[1] for r in conn.execute(
            "SELECT family_id, exposed_reason FROM training_memberships"
            " WHERE exposed=1 ORDER BY assignment_version").fetchall()}
        latest_version = conn.execute(
            "SELECT COALESCE(MAX(assignment_version), 0) FROM"
            " split_assignments").fetchone()[0]
        family_partition = {}
        for ex_id, fam, part, exposed in conn.execute(
                "SELECT example_id, family_id, partition, exposed FROM"
                " training_memberships WHERE assignment_version=?",
                (assignment_version,)).fetchall():
            memberships[ex_id] = (fam, part,
                                  bool(exposed) or fam in exposed_ever)
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
                # leakage (M14-AC08, D10); exposed development families
                # export normally, flagged.
                problems.append(
                    f"split leakage: exposed family {fam} still in"
                    " frozen_test")
                continue
            examples[ex_id] = env
        return {
            "assignment_version": assignment_version,
            "latest_assignment_version": latest_version,
            "memberships": memberships,
            "examples": examples,
            "excluded": excluded_rows,
            "problems": problems,
        }

    def _lineage(self, conn, sel, ex_id, env, inputs):
        fam, part, exposed = sel["memberships"][ex_id]
        sampling = [r[0] for r in conn.execute(
            "SELECT decision_id FROM sampling_decisions WHERE example_id=?"
            " ORDER BY rowid", (ex_id,)).fetchall()]
        # The authoritative owner is the example row's job, never a
        # value an envelope merely claims.
        return {"example_id": ex_id,
                "job_id": ev.conn_example_job(conn, ex_id),
                "revision_id": env.get("revision_id"),
                "family_id": fam, "split": part, "exposed": exposed,
                "assignment_version": sel["assignment_version"],
                "consent_revision_id": env.get("consent_revision_id"),
                "sampling_decision_ids": sampling,
                "inputs": [_input(a) for a in inputs]}

    def _asr_rows(self, conn, sel, task_views):
        """ASR supervised rows: the review gate's own admitted verbatim
        reference and audio. Grafts land in their own weak view."""
        rows = []
        graft_rows = []
        if not any(v in task_views for v in
                   ("asr_supervised", "asr_span_graft_weak")):
            return rows, graft_rows
        for ex_id, env in sel["examples"].items():
            fam, part, exposed = sel["memberships"][ex_id]
            judgment = review_mod.effective_judgment_in(conn, ex_id)
            has_verbatim = any(
                a.get("kind") == "verbatim_reference"
                and a.get("listened_audio")
                for a in env.get("annotations") or [])
            if "asr_supervised" in task_views and has_verbatim:
                gate = review_mod.verified_asr_eligible_in(conn, ex_id)
                if not gate["eligible"]:
                    sel["excluded"].append(
                        {"example_id": ex_id,
                         "reason": f"asr_gate_{gate['reason']}"})
                else:
                    ref, audio = gate["reference"], gate["audio"]
                    rows.append({
                        "example_id": ex_id, "family_id": fam,
                        "split": part, "exposed": exposed,
                        "audio_artifact": audio,
                        "inputs": [audio["id"], ref["id"]],
                        "lineage": self._lineage(conn, sel, ex_id, env,
                                                 [audio, ref]),
                        "verbatim_text": ref["text"],
                        "verbatim_annotation_id":
                            gate["annotation"].get("annotation_id"),
                        "effective_label_revision": (
                            judgment["effective"] or {}).get("revision"),
                        "captured_at_utc": env.get("captured_at_utc"),
                        "time_quality": env.get("time_quality"),
                        "transcription_policy":
                            "verbatim_audio_reviewed_v1",
                    })
            if "asr_span_graft_weak" in task_views:
                grow = conn.execute(
                    "SELECT graft_artifact_id, revision FROM"
                    " correction_labels WHERE example_id=? AND"
                    " graft_artifact_id IS NOT NULL ORDER BY revision"
                    " DESC LIMIT 1", (ex_id,)).fetchone()
                if not grow:
                    continue
                job_id = ev.conn_example_job(conn, ex_id)
                graft = ev.qualify(conn, grow[0], "span_graft",
                                   job_id=job_id)
                if not graft["ok"]:
                    sel["excluded"].append(
                        {"example_id": ex_id,
                         "reason": f"graft_{graft['reason']}"})
                    continue
                payload = json.loads(graft["artifact"]["text"])
                if payload.get("coverage_kind") != "partial":
                    sel["problems"].append(
                        "partial graft mislabeled as full gold"
                        f" ({ex_id}) — refused")
                    continue
                # The graft indexes the exact source the reviewer saw:
                # that source must still be retained (its own role/job)
                # and match the digest the graft recorded.
                src_id = payload.get("source_artifact_id") or \
                    graft["artifact"].get("meta", {}).get(
                        "source_artifact_id")
                src = ev.qualify(conn, src_id or conn.execute(
                    "SELECT parent_artifact_id FROM artifacts WHERE"
                    " artifact_id=?", (grow[0],)).fetchone()[0],
                    "source_text", job_id=job_id)
                if not src["ok"] or (
                        payload.get("source_sha256") and ids.sha256_text(
                            src["artifact"]["text"])
                        != payload["source_sha256"]):
                    sel["excluded"].append(
                        {"example_id": ex_id,
                         "reason": "graft_source_unavailable"})
                    continue
                audio_aid = (env.get("artifact_ids") or {}).get(
                    "original_audio")
                audio = ev.qualify(conn, audio_aid, "original_audio",
                                   job_id=job_id) if audio_aid else None
                audio_art = audio["artifact"] if audio and audio["ok"] \
                    else None
                inputs = [graft["artifact"], src["artifact"]] + (
                    [audio_art] if audio_art else [])
                graft_rows.append({
                    "example_id": ex_id, "family_id": fam,
                    "split": part, "exposed": exposed,
                    "inputs": [a["id"] for a in inputs],
                    "lineage": self._lineage(conn, sel, ex_id, env,
                                             inputs),
                    "label_revision": grow[1],
                    "graft_text": payload["grafted_text"],
                    "source_text": src["artifact"]["text"],
                    "coverage": payload["coverage"],
                    "reference_quality": "weak_partial",
                    "audio_artifact": audio_art,
                })
        return rows, graft_rows

    def _cleanup_rows(self, conn, sel, task_views):
        """Cleanup supervised rows (S29.12, D03): the shared cleanup
        predicate — an explicit correct intended-writing mark with the
        exact stage input and applied output this job produced — plus
        every retained rendered model prompt and the record's tier."""
        rows = []
        if "cleanup_supervised" not in task_views:
            return rows
        for ex_id, env in sel["examples"].items():
            q = ev.cleanup_qualification_in(conn, ex_id, env)
            if not q["eligible"]:
                if q["reason"] not in ("no_intended_writing_mark",):
                    sel["excluded"].append(
                        {"example_id": ex_id,
                         "reason": f"cleanup_{q['reason']}"})
                continue
            fam, part, exposed = sel["memberships"][ex_id]
            inputs = [q["source"], q["applied"]] + (
                [q["normalization"]] if q["normalization"] else []) \
                + q["prompts"]
            rows.append({
                "example_id": ex_id, "family_id": fam, "split": part,
                "exposed": exposed,
                "inputs": [a["id"] for a in inputs],
                "lineage": self._lineage(conn, sel, ex_id, env, inputs),
                "source_text": q["source"]["text"],
                "input_text": q["input_text"],
                "model_inputs": [p["text"] for p in q["prompts"]],
                "model_inputs_missing_reason":
                    q["model_inputs_missing_reason"],
                "qualification_tier": q["tier"],
                "output_text": q["applied"]["text"],
                "cleanup_path": (env.get("cleanup") or {}).get(
                    "applied_path"),
                "change_coverage": "intended_writing_marked_whole",
            })
        return rows

    def _task_rows_allowed(self, sel, partitions) -> bool:
        """Task-keyed rows carry no family (D02): they ride only with an
        export that includes train, never into a holdout-only package."""
        return "train" in partitions

    def _transform_rows(self, conn, sel, task_views, partitions):
        """Transform supervised rows (D07): one row per candidate whose
        CURRENT single-candidate decision is an explicit accept, with its
        exact task input and the transform's frozen definition revision
        so the task reconstructs offline (S29.12)."""
        rows = []
        if "transform_supervised" not in task_views:
            return rows
        cands = conn.execute(
            "SELECT task_key, candidate_id FROM preference_observations"
            " WHERE judgment='accept' AND candidate_b_id IS NULL GROUP BY"
            " task_key, candidate_id ORDER BY MIN(rowid)").fetchall()
        if not self._task_rows_allowed(sel, partitions):
            for task_key, candidate_id in cands:
                sel["excluded"].append(
                    {"candidate_id": candidate_id,
                     "reason": "task_keyed_unpartitioned"})
            return rows
        for task_key, candidate_id in cands:
            q = ev.transform_target_in(conn, task_key, candidate_id)
            if not q["eligible"]:
                sel["excluded"].append(
                    {"candidate_id": candidate_id,
                     "reason": f"transform_{q['reason']}"})
                continue
            # The gate's automated status stays beside the human accept
            # (a reviewed-then-accepted candidate is legitimate evidence,
            # but never indistinguishable from an applied one).
            decision = conn.execute(
                "SELECT artifact_id FROM artifacts WHERE"
                " parent_artifact_id=? AND role='transform_decision'"
                " AND purged=0 LIMIT 1", (q["output"]["id"],)).fetchone()
            inputs = [q["source"], q["output"]]
            rows.append({
                "task_key": task_key, "candidate_id": candidate_id,
                "transform_id": q["transform_id"],
                "transform_revision": q["transform_revision"],
                "inputs": [a["id"] for a in inputs],
                "lineage": {"task_key": task_key,
                            "candidate_id": candidate_id,
                            "judgment_observation_id":
                                q["judgment_observation_id"],
                            "inputs": [_input(a) for a in inputs]},
                "prompt_revision": q["prompt_revision"],
                "transform_definition": q["definition"],
                "source_text": q["source"]["text"],
                "desired_output_text": q["output"]["text"],
                "automated_path": q["automated_path"],
                "decision_artifact_id": decision[0] if decision else None,
                "judgment_observation_id": q["judgment_observation_id"],
            })
        return rows

    def _preference_rows(self, conn, sel, task_views, partitions):
        """Preference pair rows: the CURRENT comparable judgment on each
        same-task pair (prefer_a/prefer_b/tie/neither/uncertain) whose
        candidates share the task's exact retained input (M14-AUDIT-08)
        — the input text itself travels with both outputs and their
        display order. Slot A is the stored ``candidate_id``, slot B
        ``candidate_b_id``; neutral judgments name no winner."""
        rows = []
        if "preference_pairs" not in task_views:
            return rows
        judgments = ev.current_pair_judgments_in(conn)
        if not self._task_rows_allowed(sel, partitions):
            for task_key, *_rest in judgments:
                sel["excluded"].append(
                    {"task_key": task_key,
                     "reason": "task_keyed_unpartitioned"})
            return rows
        for task_key, cand_a, cand_b, judgment, created, obs_id in \
                judgments:
            q = ev.preference_pair_in(conn, task_key, cand_a, cand_b)
            if not q["eligible"]:
                if q["reason"] in ("not_same_task", "input_hashes_differ"):
                    sel["problems"].append(
                        "preference pair refuses export: candidates do"
                        " not share one task/input identity (S29.10)")
                else:
                    sel["excluded"].append(
                        {"task_key": task_key,
                         "reason": f"preference_{q['reason']}"})
                continue
            outs = q["outputs"]
            inputs = [q["source"], outs["a"]["artifact"],
                      outs["b"]["artifact"]]
            rows.append({
                "task_key": task_key,
                "judgment": judgment,
                "judgment_observation_id": obs_id,
                "inputs": [a["id"] for a in inputs],
                "lineage": {"task_key": task_key,
                            "judgment_observation_id": obs_id,
                            "inputs": [_input(a) for a in inputs]},
                "input_text": q["source"]["text"],
                "input_source_sha256": q["input_source_sha256"],
                "instructions_sha256": q["instructions_sha256"],
                "examples_revision": q["examples_revision"],
                "transform_id": q["transform_id"],
                "transform_revision": q["transform_revision"],
                "chosen": ("a" if judgment == "prefer_a"
                           else "b" if judgment == "prefer_b" else None),
                "candidates": [
                    {"slot": slot,
                     "candidate_id": outs[slot]["candidate_id"],
                     "display_order": outs[slot]["display_order"],
                     "output_text": outs[slot]["artifact"]["text"]}
                    for slot in ("a", "b")],
                "judged_at_utc": created,
            })
        return rows

    # ---- dependencies re-checked at publication ------------------------------

    def _dependencies(self, conn, snap):
        """Everything the selected records rest on, as the snapshot saw
        it: input artifacts, example states and revisions, label
        revision counts and current judgments."""
        inputs = sorted({aid for key in ("asr", "grafts", "cleanup",
                                         "transforms", "preferences")
                         for row in snap[key]
                         for aid in row.get("inputs") or () if aid})
        examples = {}
        for key in ("asr", "grafts", "cleanup"):
            for row in snap[key]:
                ex_id = row["example_id"]
                lin = row["lineage"]
                labels = conn.execute(
                    "SELECT COUNT(*) FROM correction_labels WHERE"
                    " example_id=?", (ex_id,)).fetchone()[0]
                examples[ex_id] = (lin["revision_id"], labels)
        pairs = {(r["task_key"], r["judgment_observation_id"])
                 for r in snap["preferences"]}
        accepts = {(r["task_key"], r["candidate_id"],
                    r["judgment_observation_id"])
                   for r in snap["transforms"]}
        return {"inputs": inputs, "examples": examples, "pairs": pairs,
                "accepts": accepts}

    @staticmethod
    def _dependencies_hold(conn, deps) -> str | None:
        """None when every dependency still holds, else a reason."""
        row = conn.execute(
            "SELECT state FROM consent_revisions ORDER BY rowid DESC"
        ).fetchone()
        if (row[0] if row else "disabled") != "enabled":
            return "consent_revoked"
        inputs = deps["inputs"]
        for i in range(0, len(inputs), 500):
            chunk = inputs[i:i + 500]
            n = conn.execute(
                "SELECT COUNT(*) FROM artifacts WHERE purged=0 AND"
                f" artifact_id IN ({','.join('?' * len(chunk))})",
                chunk).fetchone()[0]
            if n != len(chunk):
                return "input_purged_or_absent"
        for ex_id, (revision, labels) in deps["examples"].items():
            row = conn.execute(
                "SELECT state, latest_revision_id FROM training_examples"
                " WHERE example_id=?", (ex_id,)).fetchone()
            if row is None or row[0] not in _LIVE_STATES:
                return "example_not_live"
            if revision and row[1] and row[1] != revision:
                return "example_revised"
            if conn.execute(
                    "SELECT COUNT(*) FROM correction_labels WHERE"
                    " example_id=?", (ex_id,)).fetchone()[0] != labels:
                return "label_changed"
        current = {(r[0], r[5]) for r in ev.current_pair_judgments_in(conn)}
        if not deps["pairs"] <= current:
            return "judgment_changed"
        for task_key, cand, obs in deps["accepts"]:
            latest = conn.execute(
                "SELECT observation_id FROM preference_observations WHERE"
                " task_key=? AND candidate_id=? AND candidate_b_id IS NULL"
                " AND judgment IN ('accept','reject') ORDER BY rowid DESC"
                " LIMIT 1", (task_key, cand)).fetchone()
            if latest is None or latest[0] != obs:
                return "judgment_changed"
        return None

    # ---- build ------------------------------------------------------------------

    def build(self, destination, *, task_views, partitions=("train",
                  "validation", "frozen_test"),
              assignment_version=None, export_id=None) -> dict:
        """Build one dataset into ``destination`` (a directory path).
        Returns the manifest summary; raises ExportError on any refusal
        with nothing left behind but the refusal record. ``export_id``
        is the caller's operation identity: repeating a completed id
        returns its recorded receipt and builds nothing."""
        for view in task_views:
            if view not in TASK_VIEWS:
                raise ExportError(f"unknown task view {view!r}")
        destination = pathlib.Path(destination).expanduser()
        if export_id is not None:
            done = self._receipt(export_id)
            if done is not None:
                return done
        export_id = export_id or ids.new_id("export")
        for managed in (self.store.artifacts_dir, self.store.notes_dir):
            if _inside(destination, managed):
                raise ExportError(
                    "destination lies inside LocalFlow's managed data —"
                    " choose a folder outside it")
        if destination.exists() and not _replaceable(destination):
            # Publication replaces the destination; only an empty folder
            # or an earlier export may be replaced — never a folder of
            # the user's own files.
            raise ExportError(
                "destination exists and is not empty or a previous"
                " LocalFlow export — choose a new folder name")

        baseline_tombstones = None

        def snapshot_op(conn):
            nonlocal baseline_tombstones
            baseline_tombstones = conn.execute(
                "SELECT COUNT(*) FROM deletion_tombstones").fetchone()[0]
            row = conn.execute(
                "SELECT state FROM consent_revisions ORDER BY rowid"
                " DESC").fetchone()
            consent = row[0] if row else "disabled"
            if consent != "enabled":
                return {"consent": consent}
            parts = set(partitions)
            sel = self._select(conn, task_views, parts,
                               assignment_version)
            asr_rows, graft_rows = self._asr_rows(conn, sel, task_views)
            snap = {
                "sel": sel, "asr": asr_rows, "grafts": graft_rows,
                "cleanup": self._cleanup_rows(conn, sel, task_views),
                "transforms": self._transform_rows(conn, sel, task_views,
                                                   parts),
                "preferences": self._preference_rows(conn, sel,
                                                     task_views, parts),
                "consent": consent,
            }
            snap["deps"] = self._dependencies(conn, snap)
            return snap
        snap = self.store.submit(snapshot_op)
        if snap["consent"] != "enabled":
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error="consent_not_enabled")
            raise ExportError(
                "collection consent is not enabled — an export needs"
                " the material to still be consented (S29.13)")
        problems = (snap["sel"].get("problems") or [])
        if problems:
            # Refusals discovered inside the writer op ride out as
            # data (an in-op ExportError would surface wrapped as a
            # RuntimeError and escape the caller's catch).
            self._record(export_id, "failed", task_views, None,
                         destination, None, None, error="refused")
            raise ExportError(problems[0])
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / \
            f".{destination.name}.building-{export_id}"
        moved_aside = None
        try:
            # Exclusive: fails on ANY existing path (directory, file or
            # link) — the build only ever works inside what it created.
            os.mkdir(staging)
        except OSError:
            self._record(export_id, "failed", task_views, None,
                         destination, None, None, error="staging_collision")
            raise ExportError(
                "the build's own staging path already exists — nothing"
                " written or removed")
        (staging / _OWNER_FILE).write_text(export_id, encoding="utf-8")
        try:
            manifest, counts, fingerprint = self._write_graph(
                staging, snap, task_views, partitions, export_id,
                baseline_tombstones)
            (staging / _OWNER_FILE).unlink()
            _write_sums(staging)
            if destination.exists():
                if not _replaceable(destination):
                    raise ExportError(
                        "destination changed during the build and is no"
                        " longer replaceable — nothing written")
                moved_aside = destination.parent / \
                    f".{destination.name}.replaced-{export_id}"
                os.rename(destination, moved_aside)
            summary_counts = {
                **counts, "examples": counts["_examples"],
                "references": counts["_references"],
                "preferences": counts["preference_pairs"],
                "excluded": len(snap["sel"]["excluded"])}
            summary_counts = {k: v for k, v in summary_counts.items()
                              if not k.startswith("_")}
            deps = snap["deps"]

            def publish_op(conn):
                # The linearization point (D09): dependencies re-checked
                # and the directory published in ONE writer op — no
                # deletion or revocation can commit in between.
                reason = self._dependencies_hold(conn, deps)
                if reason is not None:
                    return {"refused": reason}
                if destination.exists():
                    return {"refused": "destination_appeared"}
                now = ids.now_utc_iso()
                # The completion row first, the rename last: a failing
                # rename raises, the op rolls back, nothing is published.
                conn.execute(
                    "INSERT OR REPLACE INTO export_manifests(export_id,"
                    " state, task_views_json, manifest_json, destination,"
                    " fingerprint, examples_count, excluded_count, error,"
                    " created_at_utc, finalized_at_utc)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (export_id, "complete", json.dumps(sorted(task_views)),
                     json.dumps(manifest, sort_keys=True),
                     str(destination), fingerprint,
                     summary_counts["examples"],
                     summary_counts["excluded"], None, now, now))
                os.rename(staging, destination)
                return {"published": True}
            out = self.store.submit(publish_op)
            if out.get("refused"):
                raise ExportError(
                    "consent revoked or selected content changed during"
                    f" the build ({out['refused']}) — export aborted"
                    " before completion (S29.13)")
        except ExportError as e:
            self._abort(staging, export_id, moved_aside, destination)
            self._record(export_id, "failed", task_views, None,
                         destination, None, None, error="refused")
            raise e
        except Exception as e:
            # Disk full, a store stall during the fence, anything:
            # nothing is left labeled complete; only this build's own
            # staging is removed.
            self._abort(staging, export_id, moved_aside, destination)
            self._record(export_id, "failed", task_views, None,
                         destination, None, None,
                         error=type(e).__name__)
            raise ExportError(f"export failed: {type(e).__name__}")
        if moved_aside is not None:
            shutil.rmtree(moved_aside, ignore_errors=True)
        self.emit("export.completed", level="INFO",
                  reason_code=",".join(sorted(task_views)),
                  detail=f"examples={summary_counts['examples']}")
        return {"export_id": export_id, "state": "complete",
                "fingerprint": fingerprint, "counts": summary_counts,
                "error": None}

    @staticmethod
    def _abort(staging, export_id, moved_aside, destination):
        """Remove only THIS build's staging (its ownership file, or an
        already-renamed graph that never published) and put a moved
        earlier export back."""
        try:
            owner = (staging / _OWNER_FILE)
            ours = staging.is_dir() and not staging.is_symlink() and (
                not owner.exists()
                or owner.read_text(encoding="utf-8") == export_id)
        except OSError:
            ours = False
        if ours:
            shutil.rmtree(staging, ignore_errors=True)
        if moved_aside is not None and moved_aside.exists() \
                and not destination.exists():
            try:
                os.rename(moved_aside, destination)
            except OSError:
                pass

    def _write_graph(self, staging, snap, task_views, partitions,
                     export_id, baseline_tombstones):
        art_dir = staging / "artifacts"
        art_dir.mkdir()
        copied = {}

        def copy_audio(artifact):
            if artifact is None or artifact.get("path") is None:
                return None
            rel = f"artifacts/{artifact['id']}.wav"
            if rel not in copied:
                # A plain managed name, opened no-follow and regular
                # only (M14-AUDIT-05); streamed, never loaded whole. The
                # copy must match the digest recorded at capture: a
                # damaged or swapped payload is refused rather than
                # exported under the original's name.
                src = open_managed_file(self.store.artifacts_dir,
                                        artifact["path"])
                if src is None:
                    raise ExportError(
                        f"audio payload for {artifact['id']} is not a"
                        " managed regular file — refused")
                with src, open(staging / rel, "xb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                digest = _sha256_file(staging / rel)
                if not artifact["sha256"] or digest != artifact["sha256"]:
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
            examples.append({
                "example_id": row["example_id"],
                "family_id": row["family_id"], "split": row["split"],
                "task_kind": "asr_supervised",
                "audio": rel, "audio_sha256": copied[rel],
                "captured_at_utc": row["captured_at_utc"],
                "time_quality": row["time_quality"],
                "exposed": row["exposed"],
                "effective_label_revision":
                    row["effective_label_revision"],
                "lineage": row["lineage"],
            })
            references.append({
                "example_id": row["example_id"],
                "task_kind": "asr_supervised",
                "kind": "verbatim_speech", "coverage": "full",
                "text": row["verbatim_text"],
                "text_sha256": ids.sha256_text(row["verbatim_text"]),
                "annotation_id": row["verbatim_annotation_id"],
                "transcription_policy": row["transcription_policy"],
                "listened_audio": True, "reviewer": "hub_user",
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
                "label_revision": row["label_revision"],
                "lineage": row["lineage"],
            })
            references.append({
                "example_id": row["example_id"],
                "task_kind": "asr_span_graft_weak",
                "kind": "span_graft", "coverage": "partial",
                "coverage_spans": row["coverage"],
                "source_text": row["source_text"],
                "source_sha256": ids.sha256_text(row["source_text"]),
                "grafted_text": row["graft_text"],
                "reference_quality": "weak_partial",
                "note": "unreviewed remainder unverified — never full"
                        " gold (S29.7)",
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
                "qualification_tier": row["qualification_tier"],
                "exposed": row["exposed"],
                "lineage": row["lineage"],
            })
            references.append({
                "example_id": row["example_id"],
                "task_kind": "cleanup_supervised",
                "kind": "intended_writing", "coverage": "full",
                "text": row["output_text"],
                "provenance": "user_explicit_intended_writing",
            })
        for row in snap["transforms"]:
            examples.append({
                "task_key": row["task_key"],
                "candidate_id": row["candidate_id"],
                "task_kind": "transform_supervised",
                "split": "unpartitioned", "holdout_qualified": False,
                "transform_id": row["transform_id"],
                "transform_revision": row["transform_revision"],
                "prompt_revision": row["prompt_revision"],
                "input_text": row["source_text"],
                "input_sha256": ids.sha256_text(row["source_text"]),
                "output_text": row["desired_output_text"],
                "transform_definition": row["transform_definition"],
                "automated_path": row.get("automated_path"),
                "decision_artifact_id": row.get("decision_artifact_id"),
                "judgment": "accept",
                "lineage": row["lineage"],
            })
        preferences = []
        for row in snap["preferences"]:
            preferences.append({
                "task_key": row["task_key"],
                "task_kind": "preference",
                "split": "unpartitioned", "holdout_qualified": False,
                "input_text": row["input_text"],
                "input_source_sha256": row["input_source_sha256"],
                "instructions_sha256": row["instructions_sha256"],
                "examples_revision": row["examples_revision"],
                "transform_id": row["transform_id"],
                "transform_revision": row["transform_revision"],
                "judgment": row["judgment"],
                "chosen": row["chosen"],
                "candidates": row["candidates"],
                "judged_at_utc": row["judged_at_utc"],
                "lineage": row["lineage"],
            })
        counts = {k: sum(1 for e in examples if e["task_kind"] == k)
                  for k in ("asr_supervised", "asr_span_graft_weak",
                            "cleanup_supervised", "transform_supervised")}
        counts["preference_pairs"] = len(preferences)
        tiers = {t: sum(1 for e in examples
                        if e["task_kind"] == "cleanup_supervised"
                        and e["qualification_tier"] == t)
                 for t in ev.CLEANUP_TIERS}
        semantic = {
            "examples": sorted(examples, key=lambda e: json.dumps(
                e, sort_keys=True)),
            "references": sorted(references, key=lambda e: json.dumps(
                e, sort_keys=True)),
            "preferences": sorted(preferences, key=lambda e: json.dumps(
                e, sort_keys=True)),
        }
        fingerprint = _fingerprint(semantic)
        sel = snap["sel"]
        manifest = {
            "training_schema_version": 1,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "exporter_version": EXPORTER_VERSION,
            "annotation_version": ANNOTATION_VERSION,
            "word_count_version": WORD_COUNT_VERSION,
            "lineage_version": LINEAGE_VERSION,
            "export_id": export_id,
            "task_views": sorted(task_views),
            "assignment_version": sel["assignment_version"],
            "exposure_checked_through_version":
                sel["latest_assignment_version"],
            "partitions": sorted(partitions),
            "partition_scope": {
                "family_partitioned": list(_EXAMPLE_VIEWS),
                "unpartitioned": list(_TASK_VIEWS),
                "note": "task-keyed rows carry no recording family: they"
                        " are unpartitioned, never holdout-qualified,"
                        " and ride only with exports that include train"
                        " (m14-policy-r1 D02)"},
            "counts": counts,
            "cleanup_tiers": tiers,
            "excluded": sel["excluded"],
            "excluded_note": "content-free reasons only — no transcript"
                             " excerpts (E19.5)",
            "content_fingerprint": fingerprint,
            "deletion_epoch": baseline_tombstones,
            "files": ["examples.jsonl", "references.jsonl",
                      "preferences.jsonl", "README.md"],
            "allowed_uses": "local personalization research on the"
                            " exporting machine; single-speaker scope"
                            " (S29.11)",
        }
        _write_jsonl(staging / "examples.jsonl", semantic["examples"])
        _write_jsonl(staging / "references.jsonl", semantic["references"])
        _write_jsonl(staging / "preferences.jsonl",
                     semantic["preferences"])
        (staging / "README.md").write_text(_dataset_readme(manifest),
                                           encoding="utf-8")
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1,
                       sort_keys=True), encoding="utf-8")
        counts_out = dict(counts)
        counts_out["_examples"] = len(examples)
        counts_out["_references"] = len(references)
        return manifest, counts_out, fingerprint

    def _receipt(self, export_id):
        def op(conn):
            return conn.execute(
                "SELECT state, fingerprint, manifest_json FROM"
                " export_manifests WHERE export_id=?",
                (export_id,)).fetchone()
        row = self.store.submit(op)
        if row is None or row[0] != "complete":
            return None
        manifest = json.loads(row[2]) if row[2] else {}
        return {"export_id": export_id, "state": "complete",
                "fingerprint": row[1],
                "counts": manifest.get("counts"), "error": None,
                "reconciled": True}

    def _record(self, export_id, state, task_views, manifest,
                destination, fingerprint, counts, error=None):
        def op(conn):
            now = ids.now_utc_iso()
            done = conn.execute(
                "SELECT state FROM export_manifests WHERE export_id=?",
                (export_id,)).fetchone()
            if done and done[0] == "complete":
                # A published export's record is never overwritten.
                return {"export_id": export_id, "state": "complete",
                        "fingerprint": None, "counts": None,
                        "error": None}
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
    tiers = manifest.get("cleanup_tiers") or {}
    return (
        "# LocalFlow personal dataset export\n\n"
        f"Exporter {manifest['exporter_version']}, schema"
        f" {manifest['export_schema_version']}. Task views:"
        f" {', '.join(manifest['task_views'])}. Counts:"
        f" {json.dumps(manifest['counts'], sort_keys=True)}.\n\n"
        "Single-speaker personalization material (S29.11): no"
        " speaker-independent generalization is claimed. Every record"
        " carries its lineage (job, revision, family and assignment"
        " version, consent revision, input artifacts with role, owner and"
        " digest) and the exact inputs its task needs. References carry"
        " their coverage; span grafts are weak/partial and never full"
        " gold. Cleanup records name their tier: model_task_complete"
        " (every rendered model prompt retained) or text_pair_only (an"
        " intended-writing text pair; the model task does not"
        f" reconstruct) — {json.dumps(tiers, sort_keys=True)}."
        " Transform and preference records are task-keyed: they carry"
        " no recording family, are unpartitioned and are never holdout"
        " material. Known missing fields: no forced alignment, no token"
        " log-probabilities (unsupported by the current adapters)."
        " Allowed uses: local personalization research; provider upload"
        " is a separate explicit decision.\n"
        f"Content fingerprint: {manifest['content_fingerprint']}\n")


# ---- the standalone validator (no store, no network) ----------------------


def _safe_rel(rel) -> bool:
    """A relative POSIX path inside the dataset (no absolute path, no
    traversal)."""
    return isinstance(rel, str) and bool(rel) and \
        not rel.startswith("/") and \
        ".." not in pathlib.PurePosixPath(rel).parts


def _sha_text(text) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() \
        if isinstance(text, str) else None


def validate_dataset(root) -> dict:
    """Validate a dataset directory WITHOUT the app database, from any
    working directory (E19.5 offline reconstruction): hashes, manifest
    structure, relative-path safety, and — independently of the
    checksums — the semantic lineage every record declares: each input
    belongs to the record's own job (or task) with the expected role,
    included texts match their recorded digests, references pair with
    their examples, a family occupies one partition, preference choices
    follow their judgments, and task inputs reconstruct from the
    package alone. A package whose checksums were recomputed around a
    semantic change still fails. The directory is untrusted input:
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
        return {"valid": False,
                "issues": ["unsupported export schema version"]}
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
    examples = _read_jsonl(root / "examples.jsonl", issues)
    references = _read_jsonl(root / "references.jsonl", issues)
    preferences = _read_jsonl(root / "preferences.jsonl", issues)
    _validate_semantics(examples, references, preferences, listed,
                        symlinks, root, issues)
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        issues.append("manifest counts missing")
        counts = {}
    for kind in TASK_VIEWS:
        expected = counts.get(kind)
        actual = sum(1 for e in examples
                     if e.get("task_kind") == kind) \
            if kind != "preference_pairs" else len(preferences)
        if expected != actual:
            issues.append(
                f"manifest count mismatch {kind}:"
                f" {expected} vs {actual}")
    tiers = manifest.get("cleanup_tiers")
    actual_tiers = {t: sum(1 for e in examples
                           if e.get("task_kind") == "cleanup_supervised"
                           and e.get("qualification_tier") == t)
                    for t in ev.CLEANUP_TIERS}
    if tiers != actual_tiers:
        issues.append("manifest cleanup tiers disagree with the records")
    # Determinism support: the fingerprint must verify against the
    # semantic records (volatile fields excluded).
    semantic = {name: sorted(rows, key=lambda e: json.dumps(
                    e, sort_keys=True))
                for name, rows in (("examples", examples),
                                   ("references", references),
                                   ("preferences", preferences))}
    if _fingerprint(semantic) != manifest.get("content_fingerprint"):
        issues.append("content fingerprint mismatch")
    return {"valid": not issues, "issues": sorted(set(issues)),
            "counts": {k: sum(1 for e in examples
                              if e.get("task_kind") == k)
                       for k in ("asr_supervised",
                                 "asr_span_graft_weak",
                                 "cleanup_supervised",
                                 "transform_supervised")} | {
                       "preference_pairs": len(preferences)}}


def _lineage_ok(rec, roles, issues, *, task=False):
    """Every declared input belongs to the record's own job (or, for a
    task-keyed record, its task) with an expected role."""
    lin = rec.get("lineage")
    label = rec.get("example_id") or rec.get("task_key")
    if not isinstance(lin, dict) or not isinstance(
            lin.get("inputs"), list) or not lin["inputs"]:
        issues.append(f"record {label} carries no lineage")
        return None
    if not task and lin.get("example_id") != rec.get("example_id"):
        issues.append(f"record {label} lineage names another example")
    if task and lin.get("task_key") != rec.get("task_key"):
        issues.append(f"record {label} lineage names another task")
    by_role = {}
    for inp in lin["inputs"]:
        if not isinstance(inp, dict):
            issues.append(f"record {label} lineage input malformed")
            continue
        role = inp.get("role")
        ok_role = role in roles or any(
            r.endswith("*") and isinstance(role, str)
            and role.startswith(r[:-1]) for r in roles)
        if not ok_role:
            issues.append(f"record {label} input has role {role}")
        if task:
            if inp.get("task_key") != rec.get("task_key"):
                issues.append(f"record {label} input of another task")
        elif inp.get("job_id") != lin.get("job_id") or not inp.get(
                "job_id"):
            issues.append(f"record {label} input of another job")
        by_role.setdefault(role, []).append(inp)
    return by_role


def _validate_semantics(examples, references, preferences, listed,
                        symlinks, root, issues):
    seen = set()
    families = {}
    refs = {}
    for ref in references:
        key = (ref.get("example_id"), ref.get("task_kind"))
        if key in refs:
            issues.append(f"duplicate reference {key[0]}")
        refs[key] = ref
        if ref.get("kind") == "span_graft" and \
                ref.get("coverage") != "partial":
            issues.append("graft reference not marked partial")
        if ref.get("kind") == "verbatim_speech" and \
                not ref.get("listened_audio"):
            issues.append("verbatim reference without audio review")
    for ex in examples:
        kind = ex.get("task_kind")
        key = (ex.get("example_id") or ex.get("candidate_id"), kind)
        if key in seen:
            issues.append(f"duplicate record {key[0]} ({kind})")
        seen.add(key)
        if kind in _EXAMPLE_VIEWS:
            fam, split = ex.get("family_id"), ex.get("split")
            if families.setdefault(fam, split) != split:
                issues.append(f"family {fam} spans partitions")
            ref = refs.get((ex.get("example_id"), kind))
            if ref is None:
                issues.append(f"{kind} example {ex.get('example_id')}"
                              " has no reference")
        audio = ex.get("audio")
        if kind == "asr_supervised" and audio is None:
            issues.append(
                f"asr example {ex.get('example_id')} missing audio")
        if audio is not None:
            if not _safe_rel(audio):
                issues.append("unsafe audio path")
            elif audio in symlinks or not (root / audio).is_file():
                issues.append(
                    f"example {ex.get('example_id')} missing audio")
            elif listed.get(audio) != ex.get("audio_sha256"):
                issues.append(
                    f"audio hash disagrees with SHA256SUMS for example"
                    f" {ex.get('example_id')}")
        if kind == "asr_supervised":
            by_role = _lineage_ok(ex, ("original_audio",
                                       "verbatim_reference"), issues)
            if by_role is not None:
                aud = by_role.get("original_audio") or [{}]
                if aud[0].get("sha256") != ex.get("audio_sha256"):
                    issues.append(f"asr example {ex.get('example_id')}"
                                  " audio is not its recorded capture")
                vref = by_role.get("verbatim_reference") or [{}]
                ref = refs.get((ex.get("example_id"), kind)) or {}
                if vref[0].get("sha256") != _sha_text(ref.get("text")) \
                        or ref.get("text_sha256") != vref[0].get("sha256"):
                    issues.append(f"asr example {ex.get('example_id')}"
                                  " reference is not its reviewed text")
        elif kind == "asr_span_graft_weak":
            by_role = _lineage_ok(ex, ("span_graft", "raw_transcript",
                                       "original_audio"), issues)
            ref = refs.get((ex.get("example_id"), kind)) or {}
            src = ref.get("source_text")
            if by_role is not None and (by_role.get("raw_transcript")
                                        or [{}])[0].get("sha256") \
                    != _sha_text(src):
                issues.append(f"graft {ex.get('example_id')} source is"
                              " not its reviewed source")
            for span in ref.get("coverage_spans") or []:
                if not (isinstance(span, list) and len(span) == 2
                        and isinstance(src, str)
                        and 0 <= span[0] <= span[1] <= len(src)):
                    issues.append(f"graft {ex.get('example_id')}"
                                  " coverage outside its source")
        elif kind == "cleanup_supervised":
            by_role = _lineage_ok(ex, ("raw_transcript", "applied_output",
                                       "normalized_text",
                                       "normalization_ledger",
                                       "cleanup_input_*"), issues)
            if by_role is not None:
                src = (by_role.get("raw_transcript") or [{}])[0]
                app = (by_role.get("applied_output") or [{}])[0]
                if src.get("sha256") != _sha_text(ex.get("source_text")):
                    issues.append(f"cleanup {ex.get('example_id')} source"
                                  " is not its recorded input")
                if app.get("sha256") != _sha_text(ex.get("output_text")):
                    issues.append(f"cleanup {ex.get('example_id')} output"
                                  " is not its recorded output")
                prompts = [i for r, ins in by_role.items()
                           if isinstance(r, str)
                           and r.startswith("cleanup_input_") for i in ins]
                if sorted(i.get("sha256") for i in prompts) != sorted(
                        _sha_text(t) for t in ex.get("model_inputs") or []):
                    issues.append(f"cleanup {ex.get('example_id')} model"
                                  " inputs do not match their lineage")
            tier = ex.get("qualification_tier")
            complete = bool(ex.get("model_inputs")) and \
                ex.get("model_inputs_missing_reason") is None
            if tier not in ev.CLEANUP_TIERS or (
                    tier == "model_task_complete") != complete:
                issues.append(f"cleanup {ex.get('example_id')} tier is"
                              " not supported by its inputs")
        elif kind == "transform_supervised":
            by_role = _lineage_ok(ex, ("transform_source",
                                       "transform_output"), issues,
                                  task=True)
            if ex.get("split") != "unpartitioned" or \
                    ex.get("holdout_qualified") is not False:
                issues.append("transform record claims a partition")
            if by_role is not None:
                src = (by_role.get("transform_source") or [{}])[0]
                out = (by_role.get("transform_output") or [{}])[0]
                if src.get("sha256") != _sha_text(ex.get("input_text")) \
                        or ex.get("input_sha256") != _sha_text(
                            ex.get("input_text")):
                    issues.append(f"transform {ex.get('task_key')} input"
                                  " is not its task input")
                if out.get("sha256") != _sha_text(ex.get("output_text")):
                    issues.append(f"transform {ex.get('task_key')} output"
                                  " is not its accepted candidate")
            if not isinstance(ex.get("transform_definition"), dict):
                issues.append("transform record without its definition")
        elif kind is not None:
            issues.append(f"unknown task kind {kind}")
    pairs = set()
    for pref in preferences:
        cands = pref.get("candidates")
        if not isinstance(cands, list) or len(cands) != 2 or \
                [c.get("slot") if isinstance(c, dict) else None
                 for c in cands] != ["a", "b"]:
            issues.append("preference without a candidate pair")
            continue
        judgment = pref.get("judgment")
        if judgment not in _COMPARABLE:
            issues.append("preference judgment not comparable")
        expected = {"prefer_a": "a", "prefer_b": "b"}.get(judgment)
        if pref.get("chosen") != expected:
            issues.append(f"preference {pref.get('task_key')} choice does"
                          " not follow its judgment")
        ids_pair = frozenset(c.get("candidate_id") for c in cands)
        if len(ids_pair) != 2:
            issues.append("preference pair repeats one candidate")
        key = (pref.get("task_key"), ids_pair)
        if key in pairs:
            issues.append("duplicate preference pair")
        pairs.add(key)
        if pref.get("split") != "unpartitioned" or \
                pref.get("holdout_qualified") is not False:
            issues.append("preference record claims a partition")
        if _sha_text(pref.get("input_text")) != \
                pref.get("input_source_sha256"):
            issues.append(f"preference {pref.get('task_key')} input does"
                          " not reconstruct its task")
        by_role = _lineage_ok(pref, ("transform_source",
                                     "transform_output"), issues, task=True)
        if by_role is not None:
            outs = sorted(i.get("sha256")
                          for i in by_role.get("transform_output") or [])
            if outs != sorted(_sha_text(c.get("output_text"))
                              for c in cands):
                issues.append(f"preference {pref.get('task_key')} outputs"
                              " are not its candidates'")


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
