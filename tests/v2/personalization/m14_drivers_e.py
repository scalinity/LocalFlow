"""M14 corpus drivers, group e: dataset eligibility, export safety and
export concurrency.

Binds the frozen corpus entries
- cases LF-M14-C132..C140 (dataset_eligibility: the five task views,
  cleanup intended-writing and tier (D03), transform accept (D07), weak
  grafts, restricted sources),
- cases LF-M14-C141..C149 (export_safety: absent/empty/non-empty
  destinations, unowned staging (D09), symlinks, managed-tree nesting,
  outside audio paths (D11), path/id escape, the export CLI's --db),
- cases LF-M14-C150..C158 (export_concurrency: the publication fence
  (D09), selected vs unrelated deletions, consent revocation, judgment
  changes, a deleted dependency row, two same-destination builds and
  crash boundaries in killed subprocesses),
- stateful probes LF-M14-S019, S020, S021, S030, S032,
- metamorphic relation LF-M14-MR010 (export dependency locality).

Every driver builds its own synthetic ``MWorld``, drives the real
``DatasetExporter.build`` and grades with independent oracles: literal
fixture texts and ids, raw SQL rows, file bytes, a SHA256SUMS recount
done here with hashlib, and directory inventories taken before and
after. Interleavings use op seams only (the exporter's first file hash,
the publication rename, a staging-creation barrier) — a hook that runs
inside the store writer thread only queues work with
``store._submit(fn)`` and never waits.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import threading

HERE = pathlib.Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import m14_world as W  # noqa: E402
from m14_world import MWorld, accepts, patched, read_jsonl  # noqa: E402
from m14_drivers_common import (DECISIONS_VERSION, check, drives,  # noqa: E402
                                invalid)

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.curation import classify  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402

ALL_VIEWS = ("asr_supervised", "asr_span_graft_weak", "cleanup_supervised",
             "transform_supervised", "preference_pairs")
WRITER = "localflow-v2-store"
GRAFT_RAW = "send the cloud report on friday"
GRAFT_FIX = "send the Claude report on friday"
DEFINITION = {"transform_id": "builtin:polish", "revision": 1,
              "instructions": "Polish the synthetic draft.", "examples": []}
SENTINEL = b"unrelated-user-bytes-\x00\x01\x02\xff-keep"
REQUIRED_FILES = ("dataset_manifest.json", "examples.jsonl",
                  "references.jsonl", "preferences.jsonl", "README.md")


def dec(n):
    return f"{DECISIONS_VERSION}:{n}"


# ---- small independent helpers ---------------------------------------------


def _sha(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _is_sentinel(path) -> bool:
    """Byte-for-byte sentinel comparison; a vanished file is False."""
    try:
        p = pathlib.Path(path)
        return not p.is_symlink() and p.read_bytes() == SENTINEL
    except OSError:
        return False


def _dest(w, dest):
    return w.tmp / dest if isinstance(dest, str) else pathlib.Path(dest)


def _export(w, dest, views=ALL_VIEWS, **kw):
    """(summary, None) on success, (None, reason) on a refusal. A raw
    non-ExportError is reported as a refusal too, labeled ``raw:``."""
    try:
        return w.exporter.build(_dest(w, dest), task_views=views, **kw), None
    except export_mod.ExportError as e:
        return None, f"refused: {e}"[:240]
    except Exception as e:  # noqa: BLE001 — a base-tree raw failure
        return None, f"raw:{type(e).__name__}: {e}"[:240]


def _eid_kw(w, eid):
    return {"export_id": eid} if accepts(w.exporter.build, "export_id") \
        else {}


def _complete(out):
    return isinstance(out, dict) and out.get("state") == "complete"


def _inventory(root, skip=()):
    """{relpath: ("dir",) | ("link", target) | ("file", sha256)} under
    ``root`` without following links; ``skip`` names relpaths (and
    their subtrees) left out."""
    root = pathlib.Path(root)
    out = {}
    if not root.exists() and not root.is_symlink():
        return out

    def skipped(rel):
        return any(rel == s or rel.startswith(s + "/") for s in skip)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        d = pathlib.Path(dirpath)
        keep = []
        for n in list(dirnames) + list(filenames):
            p = d / n
            rel = p.relative_to(root).as_posix()
            if skipped(rel):
                continue
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("dir",)
                keep.append(n)
            else:
                out[rel] = ("file", _sha(p))
        dirnames[:] = [n for n in dirnames if n in keep]
    return out


def _sums_problems(root) -> list:
    """An independent SHA256SUMS recount: every regular file (but the
    sums file) is listed with its hashlib digest, nothing else is
    listed, no symlink, and the required record files exist."""
    root = pathlib.Path(root)
    if root.is_symlink() or not root.is_dir():
        return ["not a directory"]
    try:
        text = (root / "SHA256SUMS.txt").read_text(encoding="utf-8")
    except OSError:
        return ["no SHA256SUMS.txt"]
    problems = []
    listed = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            problems.append("malformed sums line")
            continue
        listed[rel] = digest
    files = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            problems.append(f"symlink {rel}")
        elif p.is_file() and rel != "SHA256SUMS.txt":
            files[rel] = _sha(p)
    if set(listed) != set(files):
        problems.append(f"listing differs (+{len(set(files) - set(listed))}"
                        f" -{len(set(listed) - set(files))})")
    for rel, digest in listed.items():
        if rel in files and files[rel] != digest:
            problems.append(f"hash {rel}")
    for rel in REQUIRED_FILES:
        if rel not in files:
            problems.append(f"missing {rel}")
    return problems


def _records(root):
    root = pathlib.Path(root)
    out = []
    for name in ("examples.jsonl", "references.jsonl", "preferences.jsonl"):
        p = root / name
        out.append(read_jsonl(p) if p.is_file() else [])
    return tuple(out)


def _manifest(root):
    try:
        return json.loads((pathlib.Path(root) / "dataset_manifest.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ids_by_kind(examples, prefs=()):
    out = {k: set() for k in ALL_VIEWS}
    for e in examples:
        k = e.get("task_kind")
        key = e.get("example_id") or e.get("candidate_id")
        out.setdefault(k, set()).add(key)
    out["preference_pairs"] = {p.get("task_key") for p in prefs}
    return out


def _audio_paths_ok(root, examples) -> list:
    """Every exported audio path is ``artifacts/<one plain name>`` that
    exists inside the dataset (strict path admission, read here)."""
    bad = []
    root = pathlib.Path(root).resolve()
    for e in examples:
        rel = e.get("audio")
        if rel is None:
            continue
        parts = rel.split("/")
        if len(parts) != 2 or parts[0] != "artifacts" or not parts[1] \
                or parts[1] in (".", ".."):
            bad.append("unsafe")
            continue
        p = root / parts[0] / parts[1]
        if p.is_symlink() or not p.is_file():
            bad.append("missing")
    return bad


def _leftovers(parent, name):
    parent = pathlib.Path(parent)
    if not parent.is_dir():
        return []
    return sorted(n for n in os.listdir(parent)
                  if n.startswith(f".{name}.building-")
                  or n.startswith(f".{name}.replaced-"))


def _rows(w):
    return w.rows("SELECT export_id, state, error, destination FROM"
                  " export_manifests ORDER BY rowid")


def _verbatim_aid(w, example_id):
    anns = [a for a in (w.envelope(example_id).get("annotations") or [])
            if a.get("kind") == "verbatim_reference"]
    return anns[-1]["artifact_id"] if anns else None


def _graft(w, raw=GRAFT_RAW, fix=GRAFT_FIX):
    """A job whose reviewed recognition span is grafted (weak view)."""
    j = w.job(raw)
    spans = classify.changed_regions(raw, fix)
    kw = {}
    if accepts(w.review.record_label, "expected_source_artifact_id"):
        kw = {"expected_source_artifact_id": j["raw_aid"],
              "expected_source_sha256": ids.sha256_text(raw)}
    w.review.record_label(j["example_id"], edit_kind="recognition_error",
                          origin_stages=("asr",),
                          confirmed_spans=[spans[0]], **kw)
    row = w.one("SELECT graft_artifact_id FROM correction_labels WHERE"
                " example_id=? AND graft_artifact_id IS NOT NULL ORDER BY"
                " revision DESC LIMIT 1", (j["example_id"],))
    j["graft_aid"] = row[0] if row else None
    j["spans"] = [[spans[0]["start"], spans[0]["end"]]]
    return j


def _cleanup(w, raw, applied, *, correct=True, prompts=1):
    j = w.job(raw, applied, prompts=prompts)
    if correct is not None:
        w.training.mark_intended(j["example_id"], correct)
    return j


def _prompt_text(raw, i=0):
    return f"Clean this dictation (pass {i}):\n{raw}"


@contextlib.contextmanager
def _at_first_hash(action):
    """Run ``action()`` once, in the build's own thread, at the first
    file hash — after the snapshot read, while the graph is staged and
    before the publication fence."""
    st = {"n": 0, "fired": False}

    def wrap(original):
        def sha(path):
            st["n"] += 1
            if not st["fired"]:
                st["fired"] = True
                st["thread"] = threading.current_thread().name
                action()
            return original(path)
        return sha
    with patched(export_mod, "_sha256_file", wrap):
        yield st


@contextlib.contextmanager
def _at_publish_rename(action):
    """``action(in_writer)`` once, just before the staging directory is
    renamed onto the destination. Inside the writer thread the action
    must only queue work (``store._submit(fn)``), never wait."""
    st = {"hook": 0, "in_writer": None}
    real = os.rename

    def rename(src, dst, *a, **k):
        if ".building" in os.path.basename(os.fspath(src)) \
                and not st["hook"]:
            st["hook"] += 1
            st["in_writer"] = threading.current_thread().name == WRITER
            action(st["in_writer"])
        return real(src, dst, *a, **k)
    os.rename = rename
    try:
        yield st
    finally:
        os.rename = real


def _asr_world(w, n=10):
    fams = w.families(n, asr=True)
    return {f["example_id"]: f for f in fams}


# =============================================================================
# dataset_eligibility — C132..C140
# =============================================================================


@drives("LF-M14-C132")
def c132_positive_five_views(entry):
    with MWorld() as w:
        asr = _asr_world(w)
        g = _graft(w)
        c = _cleanup(w, "cleanup five views witness",
                     "Cleanup five views witness.")
        t = w.transform_task("transform five views source",
                             ["Transform five views output."])
        tcand = t["candidates"][0]
        obs = w.accept(t, tcand["candidate_id"])
        p = w.transform_task("pair five views source",
                             ["Pair left.", "Pair right."])
        pa, pb = p["candidates"]
        w.judge(p, pa["candidate_id"], pb["candidate_id"], "prefer_b")
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err},
                         witness="build refused on the positive fixture")
        root = w.tmp / "ds"
        exs, refs, prefs = _records(root)
        kinds = _ids_by_kind(exs, prefs)
        expected = {
            "asr_supervised": set(asr),
            "asr_span_graft_weak": {g["example_id"]},
            "cleanup_supervised": {c["example_id"]},
            "transform_supervised": {tcand["candidate_id"]},
            "preference_pairs": {p["task_key"]},
        }
        lineage_bad = []
        want_roles = {}
        for ex_id, f in asr.items():
            want_roles[("asr_supervised", ex_id)] = (f["job_id"], {
                f["audio_aid"]: "original_audio",
                _verbatim_aid(w, ex_id): "verbatim_reference"})
        want_roles[("asr_span_graft_weak", g["example_id"])] = (
            g["job_id"], {g["graft_aid"]: "span_graft",
                          g["raw_aid"]: "raw_transcript",
                          g["audio_aid"]: "original_audio"})
        cl = {c["raw_aid"]: "raw_transcript",
              c["applied_aid"]: "applied_output",
              c["norm_aid"]: "normalization_ledger"}
        cl.update({a: "cleanup_input_cleanup" for a in c["prompt_aids"]})
        want_roles[("cleanup_supervised", c["example_id"])] = (c["job_id"],
                                                                cl)
        for e in exs:
            kind = e.get("task_kind")
            lin = e.get("lineage") or {}
            got = {i.get("artifact_id"): i.get("role")
                   for i in lin.get("inputs") or []}
            if kind == "transform_supervised":
                if got != {tcand["source_aid"]: "transform_source",
                           tcand["output_aid"]: "transform_output"} or \
                        lin.get("judgment_observation_id") != obs or \
                        lin.get("task_key") != t["task_key"]:
                    lineage_bad.append(kind)
                continue
            want = want_roles.get((kind, e.get("example_id")))
            if want is None:
                lineage_bad.append(f"{kind}:unexpected")
                continue
            job_id, roles = want
            if got != roles or lin.get("job_id") != job_id or \
                    lin.get("example_id") != e.get("example_id") or \
                    any(i.get("job_id") != job_id
                        for i in lin.get("inputs") or []):
                lineage_bad.append(kind)
        task_arts = {pa["source_aid"], pb["source_aid"], pa["output_aid"],
                     pb["output_aid"]}
        for pr in prefs:
            got = {i.get("artifact_id")
                   for i in (pr.get("lineage") or {}).get("inputs") or []}
            if not ({pa["output_aid"], pb["output_aid"]} <= got <= task_arts)\
                    or pr.get("chosen") != "b":
                lineage_bad.append("preference_pairs")
        observed = {k: len(v) for k, v in kinds.items()}
        return check({
            "each_view_exactly_its_witnesses": all(
                kinds.get(k, set()) == expected[k] for k in expected),
            "no_foreign_task_kind": set(kinds) <= set(ALL_VIEWS),
            "complete_task_lineage": not lineage_bad,
            "references_pair_examples": len(refs) == len(asr) + 2,
        }, {"view_counts": observed, "lineage_bad": sorted(
            set(lineage_bad))},
            witness="five-view fixture exported; per-view membership and"
                    " lineage recounted from fixture ids")


@drives("LF-M14-C133")
def c133_cleanup_intended_correct(entry):
    raw, applied = "please send the budget notes", \
        "Please send the budget notes."
    with MWorld() as w:
        asr = _asr_world(w)
        c = _cleanup(w, raw, applied)
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        exs, refs, _p = _records(w.tmp / "ds")
        mine = [e for e in exs if e.get("example_id") == c["example_id"]]
        cl = [e for e in mine if e.get("task_kind") == "cleanup_supervised"]
        rec = cl[0] if len(cl) == 1 else {}
        my_refs = [r for r in refs if r.get("example_id") == c["example_id"]]
        inputs = {i.get("artifact_id") for i in
                  (rec.get("lineage") or {}).get("inputs") or []}
        return check({
            "cleanup_record_once": len(cl) == 1,
            "only_cleanup_view": {e.get("task_kind") for e in mine}
            == {"cleanup_supervised"},
            "exact_input_output": rec.get("input_text") == raw
            and rec.get("source_text") == raw
            and rec.get("output_text") == applied,
            "exact_prompt_retained": rec.get("model_inputs")
            == [_prompt_text(raw)]
            and rec.get("qualification_tier") == "model_task_complete",
            "lineage_is_own_retained_inputs": inputs == {
                c["raw_aid"], c["applied_aid"], c["norm_aid"],
                *c["prompt_aids"]},
            "reference_is_intended_writing_not_acoustic": [
                (r.get("kind"), r.get("text"), r.get("provenance"))
                for r in my_refs] == [("intended_writing", applied,
                                       "user_explicit_intended_writing")],
            "asr_control_exported": {e["example_id"] for e in exs
                                     if e.get("task_kind")
                                     == "asr_supervised"} == set(asr),
        }, {"kinds": sorted({e.get("task_kind") for e in mine}),
            "tier": rec.get("qualification_tier")},
            witness="explicit correct mark; exported cleanup record"
                    " compared to literal fixture texts")


@drives("LF-M14-C134")
def c134_cleanup_incorrect(entry):
    with MWorld() as w:
        _asr_world(w)
        good = _cleanup(w, "cleanup good witness", "Cleanup good witness.")
        bad = _cleanup(w, "cleanup wrong witness", "Cleanup wrong output.",
                       correct=False)
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        root = w.tmp / "ds"
        exs, refs, _p = _records(root)
        man = _manifest(root) or {}
        ready = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]["cleanup_supervised"]
        cl = {e["example_id"] for e in exs
              if e.get("task_kind") == "cleanup_supervised"}
        bad_anywhere = [e for e in exs + refs
                        if e.get("example_id") == bad["example_id"]]
        return check({
            "incorrect_not_a_target": not bad_anywhere,
            "correct_control_exported": cl == {good["example_id"]},
            "manifest_tiers_honest": man.get("cleanup_tiers") == {
                "model_task_complete": 1, "text_pair_only": 0},
            "readiness_count_honest": ready.get("count") == 1,
            "readiness_tiers_honest": ready.get("tiers") in (
                None, {"model_task_complete": 1},
                {"model_task_complete": 1, "text_pair_only": 0}),
        }, {"cleanup_count": len(cl), "readiness": ready.get("count"),
            "readiness_tiers": ready.get("tiers"),
            "manifest_tiers": man.get("cleanup_tiers")},
            witness="explicit incorrect mark vs correct control")


@drives("LF-M14-C135")
def c135_cleanup_no_edit(entry):
    with MWorld() as w:
        _asr_world(w)
        good = _cleanup(w, "marked cleanup control", "Marked cleanup control.")
        same = _cleanup(w, "unmarked unchanged words",
                        "unmarked unchanged words", correct=None)
        edited = _cleanup(w, "unmarked edited words",
                          "Unmarked edited words.", correct=None)
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        exs, refs, _p = _records(w.tmp / "ds")
        silent = {same["example_id"], edited["example_id"]}
        leaked = [r for r in exs + refs if r.get("example_id") in silent]
        gold = [r for r in refs if r.get("kind") == "intended_writing"]
        ready = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]["cleanup_supervised"]
        return check({
            "no_inferred_gold": not leaked,
            "only_marked_is_gold": {r.get("example_id") for r in gold}
            == {good["example_id"]},
            "readiness_counts_marked_only": ready.get("count") == 1,
        }, {"leaked": len(leaked), "gold": len(gold),
            "readiness": ready.get("count")},
            witness="no-edit and edited-unmarked jobs vs marked control")


@drives("LF-M14-C136")
def c136_cleanup_missing_prompt(entry):
    with MWorld() as w:
        _asr_world(w)
        full = _cleanup(w, "prompt kept witness", "Prompt kept witness.")
        none = _cleanup(w, "no pass witness", "No pass witness.", prompts=0)
        gone = _cleanup(w, "prompt purged witness", "Prompt purged witness.")
        half = _cleanup(w, "one of two purged", "One of two purged.",
                        prompts=2)
        w.purge(gone["prompt_aids"][0])
        w.purge(half["prompt_aids"][1])
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err},
                         grading="decision", decision=dec("D03"))
        root = w.tmp / "ds"
        exs, _r, _p = _records(root)
        by = {e["example_id"]: e for e in exs
              if e.get("task_kind") == "cleanup_supervised"}
        man = _manifest(root) or {}
        ready = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]["cleanup_supervised"]

        def tier(j):
            return (by.get(j["example_id"]) or {}).get("qualification_tier")

        def reason(j):
            return (by.get(j["example_id"]) or {}).get(
                "model_inputs_missing_reason")
        incomplete = (none, gone, half)
        return check({
            "full_is_model_task_complete": tier(full)
            == "model_task_complete" and reason(full) is None
            and by[full["example_id"]].get("model_inputs")
            == [_prompt_text(full["raw"])],
            "incomplete_are_text_pair_only": all(
                tier(j) == "text_pair_only" for j in incomplete),
            "missing_reason_honest": all(
                isinstance(reason(j), str) and reason(j)
                for j in incomplete),
            "no_silent_reconstruction": (by.get(half["example_id"]) or {})
            .get("model_inputs") == [_prompt_text(half["raw"], 0)]
            and (by.get(gone["example_id"]) or {}).get("model_inputs") == [],
            "manifest_tiers": man.get("cleanup_tiers") == {
                "model_task_complete": 1, "text_pair_only": 3},
            "readiness_tiers": ready.get("tiers") == {
                "model_task_complete": 1, "text_pair_only": 3},
        }, {"tiers": sorted((tier(j) or "-") for j in (full, *incomplete)),
            "reasons": sorted(str(reason(j)) for j in incomplete),
            "readiness_tiers": ready.get("tiers")},
            witness="D03: prompts=0, purged prompt, one-of-two purged vs"
                    " full control", grading="decision", decision=dec("D03"))


@drives("LF-M14-C137")
def c137_transform_explicit_accept(entry):
    src, outtext = "transform accept source words", "Transform accepted out."
    with MWorld() as w:
        _asr_world(w)
        t = w.transform_task(src, [outtext])
        cand = t["candidates"][0]
        obs = w.accept(t, cand["candidate_id"])
        w.splits.assign()
        out, err = _export(w, "ds", ("transform_supervised",))
        if not _complete(out):
            return check({"export_completed": False}, {"err": err},
                         grading="decision", decision=dec("D07"))
        exs, _r, _p = _records(w.tmp / "ds")
        rows = [e for e in exs if e.get("task_kind")
                == "transform_supervised"]
        rec = rows[0] if len(rows) == 1 else {}
        lin = rec.get("lineage") or {}
        return check({
            "one_target": len(rows) == 1
            and rec.get("candidate_id") == cand["candidate_id"],
            "exact_task_io": rec.get("input_text") == src
            and rec.get("input_sha256") == hashlib.sha256(
                src.encode()).hexdigest()
            and rec.get("output_text") == outtext,
            "frozen_definition": rec.get("transform_definition")
            == DEFINITION and rec.get("transform_revision") == 1,
            "explicit_accept_cited": rec.get("judgment") == "accept"
            and lin.get("judgment_observation_id") == obs,
            "retained_evidence": {i.get("artifact_id") for i in
                                  lin.get("inputs") or []}
            == {cand["source_aid"], cand["output_aid"]},
            "unpartitioned": rec.get("split") == "unpartitioned"
            and rec.get("holdout_qualified") is False,
        }, {"rows": len(rows)}, witness="single-candidate explicit accept",
            grading="decision", decision=dec("D07"))


@drives("LF-M14-C138")
def c138_transform_auto_only(entry):
    with MWorld() as w:
        _asr_world(w)
        auto = w.transform_task("auto applied source", ["Auto applied out."])
        undo = w.transform_task("auto undone source", ["Auto undone out."])
        ctl = w.transform_task("accepted control source",
                               ["Accepted control out."])
        undo_recorded = True
        try:
            w.accept(undo, undo["candidates"][0]["candidate_id"], "undo")
        except ValueError:
            undo_recorded = False
        w.accept(ctl, ctl["candidates"][0]["candidate_id"])
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err},
                         grading="decision", decision=dec("D07"))
        exs, _r, prefs = _records(w.tmp / "ds")
        kinds = _ids_by_kind(exs, prefs)
        auto_ids = {auto["candidates"][0]["candidate_id"],
                    undo["candidates"][0]["candidate_id"]}
        return check({
            "auto_not_target": not (kinds["transform_supervised"]
                                    & auto_ids),
            "auto_not_preference": not (kinds["preference_pairs"] & {
                auto["task_key"], undo["task_key"]}),
            "accepted_control_exported": kinds["transform_supervised"]
            == {ctl["candidates"][0]["candidate_id"]},
        }, {"undo_variant": undo_recorded,
            "targets": len(kinds["transform_supervised"])},
            witness="applied-path candidates with no accept (and an undo)"
                    " vs accepted control", grading="decision",
            decision=dec("D07"))


@drives("LF-M14-C139")
def c139_weak_graft_isolated(entry):
    with MWorld() as w:
        asr = _asr_world(w)
        g = _graft(w)
        w.splits.assign()
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        exs, refs, _p = _records(w.tmp / "ds")
        mine = [e for e in exs if e.get("example_id") == g["example_id"]]
        my_refs = [r for r in refs if r.get("example_id") == g["example_id"]]
        ref = my_refs[0] if len(my_refs) == 1 else {}
        asr_ids = {e["example_id"] for e in exs
                   if e.get("task_kind") == "asr_supervised"}
        ready = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]["asr_supervised"]
        audio_rec = mine[0] if len(mine) == 1 else {}
        return check({
            "weak_view_only": [e.get("task_kind") for e in mine]
            == ["asr_span_graft_weak"],
            "full_asr_population_uncontaminated": asr_ids == set(asr),
            "partial_reference": ref.get("kind") == "span_graft"
            and ref.get("coverage") == "partial"
            and ref.get("reference_quality") == "weak_partial"
            and ref.get("coverage_spans") == g["spans"],
            "exact_source_and_graft": ref.get("source_text") == GRAFT_RAW
            and ref.get("grafted_text") == GRAFT_FIX,
            "retained_audio_carried": audio_rec.get("audio_sha256")
            == W.sha256_file(w.store.artifacts_dir
                             / f"{g['audio_aid']}.wav"),
            "readiness_asr_excludes_graft": ready.get("count") == len(asr),
        }, {"kinds": [e.get("task_kind") for e in mine],
            "asr": len(asr_ids)}, witness="span graft + verbatim witnesses")


@drives("LF-M14-C140")
def c140_restricted_all_views(entry):
    restrictions = ("deleted", "expired", "quarantined_sensitive",
                    "excluded")
    with MWorld() as w:
        asr_ctl = _asr_world(w)
        g_ctl = _graft(w)
        c_ctl = _cleanup(w, "cleanup restricted control",
                         "Cleanup restricted control.")
        restricted = {}
        for r in restrictions:
            restricted[(r, "asr")] = w.ready_asr(f"restricted asr {r} words")
            restricted[(r, "graft")] = _graft(w)
            restricted[(r, "cleanup")] = _cleanup(
                w, f"restricted cleanup {r}", f"Restricted cleanup {r}.")
        t_ctl = w.transform_task("task control source", ["Task control."])
        w.accept(t_ctl, t_ctl["candidates"][0]["candidate_id"])
        t_src = w.transform_task("task purged source", ["Task src gone."])
        w.accept(t_src, t_src["candidates"][0]["candidate_id"])
        t_out = w.transform_task("task purged output", ["Task out gone."])
        w.accept(t_out, t_out["candidates"][0]["candidate_id"])
        p_ctl = w.transform_task("pair control source", ["PL.", "PR."])
        w.judge(p_ctl, p_ctl["candidates"][0]["candidate_id"],
                p_ctl["candidates"][1]["candidate_id"], "prefer_a")
        p_bad = w.transform_task("pair purged source", ["QL.", "QR."])
        w.judge(p_bad, p_bad["candidates"][0]["candidate_id"],
                p_bad["candidates"][1]["candidate_id"], "prefer_a")
        w.splits.assign()
        for (r, _view), j in restricted.items():
            if r == "deleted":
                w.store.delete_everywhere("example", j["example_id"])
            else:
                w.set_state(j["example_id"], r)
        w.purge(t_src["candidates"][0]["source_aid"])
        w.purge(t_out["candidates"][0]["output_aid"])
        w.purge(p_bad["candidates"][1]["output_aid"])
        out, err = _export(w, "ds")
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        root = w.tmp / "ds"
        exs, refs, prefs = _records(root)
        man = _manifest(root) or {}
        excluded = man.get("excluded") or []
        ex_reason = {x.get("example_id"): x.get("reason") for x in excluded
                     if x.get("example_id")}
        cand_reason = {x.get("candidate_id"): x.get("reason")
                       for x in excluded if x.get("candidate_id")}
        task_reason = {x.get("task_key"): x.get("reason") for x in excluded
                       if x.get("task_key")}
        rids = {j["example_id"] for j in restricted.values()}
        ghosts = [x for x in exs + refs if x.get("example_id") in rids]
        kinds = _ids_by_kind(exs, prefs)
        dead_cands = {t_src["candidates"][0]["candidate_id"],
                      t_out["candidates"][0]["candidate_id"]}
        te = w.training.readiness()["readiness_metrics"]["task_eligibility"]
        return check({
            "no_ghost_records": not ghosts
            and not (kinds["transform_supervised"] & dead_cands)
            and p_bad["task_key"] not in kinds["preference_pairs"],
            "every_restricted_example_reason_coded": all(
                isinstance(ex_reason.get(i), str) and ex_reason[i]
                for i in rids),
            "restricted_tasks_reason_coded": all(
                cand_reason.get(c) for c in dead_cands)
            and bool(task_reason.get(p_bad["task_key"])),
            "controls_exported": kinds["asr_supervised"] == set(asr_ctl)
            and kinds["asr_span_graft_weak"] == {g_ctl["example_id"]}
            and kinds["cleanup_supervised"] == {c_ctl["example_id"]}
            and kinds["transform_supervised"]
            == {t_ctl["candidates"][0]["candidate_id"]}
            and kinds["preference_pairs"] == {p_ctl["task_key"]},
            "readiness_no_ghosts": te["asr_supervised"].get("count")
            == len(asr_ctl) and te["cleanup_supervised"].get("count") == 1,
        }, {"reasons": sorted({str(v) for v in ex_reason.values()}),
            "task_reasons": sorted({str(v) for v in
                                    list(cand_reason.values())
                                    + list(task_reason.values())}),
            "ghosts": len(ghosts)},
            witness="4 restrictions x 3 example views + purged task"
                    " sources/outputs, each with a live control")


# =============================================================================
# export_safety — C141..C149, S021
# =============================================================================


@drives("LF-M14-C141")
def c141_positive_absent_destination(entry):
    with MWorld() as w:
        asr = _asr_world(w)
        c = _cleanup(w, "absent destination cleanup", "Absent cleanup.")
        dest = w.tmp / "fresh" / "nested" / "ds"
        w.splits.assign()
        out, err = _export(w, dest, ("asr_supervised", "cleanup_supervised"))
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        problems = _sums_problems(dest)
        exs, refs, _p = _records(dest)
        audio_ok = []
        for e in exs:
            if e.get("task_kind") != "asr_supervised":
                continue
            src = asr[e["example_id"]]["audio_aid"]
            audio_ok.append(
                (dest / e["audio"]).read_bytes()
                == (w.store.artifacts_dir / f"{src}.wav").read_bytes())
        wavs = sorted(p.name for p in (dest / "artifacts").iterdir())
        moved = w.tmp / "elsewhere" / "copy"
        shutil.copytree(dest, moved, symlinks=True)
        report = export_mod.validate_dataset(moved)
        rows = _rows(w)
        return check({
            "complete_receipt": [r[1] for r in rows] == ["complete"]
            and rows[0][0] == out.get("export_id"),
            "nonempty_complete_graph": len(exs) == len(asr) + 1
            and len(refs) == len(asr) + 1
            and len(wavs) == len(asr) and not problems,
            "audio_bytes_identical": len(audio_ok) == len(asr)
            and all(audio_ok),
            "no_staging_left": sorted(os.listdir(dest.parent)) == ["ds"],
            "offline_validation": report.get("valid") is True,
        }, {"records": len(exs), "sums_problems": problems[:4],
            "validator_issues": (report.get("issues") or [])[:3]},
            witness="new nested destination; sums recounted with hashlib,"
                    " copy validated elsewhere")


@drives("LF-M14-C142")
def c142_empty_destination(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        parent = w.tmp / "out"
        dest = parent / "ds"
        dest.mkdir(parents=True)
        (parent / "UNRELATED.bin").write_bytes(SENTINEL)
        (parent / "other").mkdir()
        (parent / "other" / "KEEP").write_bytes(SENTINEL)
        before = _inventory(parent, skip=("ds",))
        out1, err1 = _export(w, dest, ("asr_supervised",))
        mid = _inventory(parent, skip=("ds",))
        ok1 = _complete(out1) and not _sums_problems(dest)
        # The documented second replacement: an earlier export of ours.
        out2, err2 = _export(w, dest, ("asr_supervised",))
        after = _inventory(parent, skip=("ds",))
        man = _manifest(dest) or {}
        return check({
            "empty_folder_replaced_by_dataset": ok1,
            "previous_export_replaced": _complete(out2)
            and not _sums_problems(dest)
            and man.get("export_id") == (out2 or {}).get("export_id"),
            "no_unrelated_path_touched": before == mid == after
            and _is_sentinel(parent / "UNRELATED.bin")
            and _is_sentinel(parent / "other" / "KEEP"),
            "no_staging_or_replaced_left": not _leftovers(parent, "ds"),
        }, {"err1": err1, "err2": err2, "siblings": len(before)},
            witness="empty chosen folder, then re-export over our own export")


@drives("LF-M14-C143")
def c143_nonempty_destination(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        dest = w.tmp / "ds"
        dest.mkdir()
        (dest / "MY_NOTES.bin").write_bytes(SENTINEL)
        before = _inventory(dest)
        out, err = _export(w, dest, ("asr_supervised",))
        after = _inventory(dest)
        # Variant: a previous export the user has since added a file to.
        prev = w.tmp / "prev"
        outp, errp = _export(w, prev, ("asr_supervised",))
        (prev / "USER_ADDED.bin").write_bytes(SENTINEL)
        prev_before = _inventory(prev)
        out3, err3 = _export(w, prev, ("asr_supervised",))
        prev_after = _inventory(prev)
        # Same-shape eligible companion: an absent destination.
        outc, errc = _export(w, "ds-control", ("asr_supervised",))
        return check({
            "nonempty_refused": out is None and err is not None,
            "sentinel_bytes_preserved": before == after
            and _is_sentinel(dest / "MY_NOTES.bin"),
            "user_added_export_refused_and_preserved": _complete(outp)
            and out3 is None and prev_before == prev_after
            and _is_sentinel(prev / "USER_ADDED.bin"),
            "no_staging_left": not _leftovers(w.tmp, "ds")
            and not _leftovers(w.tmp, "prev"),
            "absent_destination_control_completes": _complete(outc),
        }, {"err": err and err[:80], "err3": err3 and err3[:80],
            "errc": errc}, witness="sentinel in chosen folder and in an"
                                   " earlier export")


@drives("LF-M14-C144")
def c144_unowned_staging_directory(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        unowned = w.tmp / ".ds.building"
        (unowned / "nested").mkdir(parents=True)
        (unowned / "nested" / "UNRELATED_KEEP").write_bytes(SENTINEL)
        (unowned / "TOP_KEEP").write_bytes(SENTINEL)
        snap = _inventory(unowned)
        w.store.append_consent("disabled")
        out_d, err_d = _export(w, "ds", ("asr_supervised",))
        after_disabled = _inventory(unowned)
        w.store.append_consent("enabled")
        out_e, err_e = _export(w, "ds", ("asr_supervised",))
        after_enabled = _inventory(unowned)
        collision = None
        if accepts(w.exporter.build, "export_id"):
            eid = "export-m14e-collision-0001"
            own = w.tmp / f".ds2.building-{eid}"
            (own / "nested").mkdir(parents=True)
            (own / "nested" / "KEEP").write_bytes(SENTINEL)
            csnap = _inventory(own)
            out_c, err_c = _export(w, "ds2", ("asr_supervised",),
                                   export_id=eid)
            collision = {"refused": out_c is None,
                         "preserved": _inventory(own) == csnap,
                         "no_dest": not (w.tmp / "ds2").exists()}
        return check({
            "consent_refusal_preserves_unowned": out_d is None
            and after_disabled == snap,
            "enabled_build_never_reuses_unowned": _complete(out_e)
            and after_enabled == snap
            and not _sums_problems(w.tmp / "ds"),
            "true_collision_refused_and_preserved": collision is None
            or all(collision.values()),
            "sentinel_bytes": _is_sentinel(
                unowned / "nested" / "UNRELATED_KEEP"),
        }, {"err_disabled": err_d and err_d[:60], "err_enabled": err_e,
            "collision": collision},
            witness="D09: unowned .ds.building across consent refusal and"
                    " success; exclusive .building-<id> collision",
            grading="decision", decision=dec("D09"))


@drives("LF-M14-C145")
def c145_symlinks(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        views = ("asr_supervised",)
        outside = w.tmp / "outside"
        outside.mkdir()
        (outside / "SECRET.bin").write_bytes(SENTINEL)
        empty_out = w.tmp / "outside-empty"
        empty_out.mkdir()
        results = {}

        def outside_same(snap):
            return _inventory(w.tmp, skip=("arts", "bk", "v2.db",
                                           "v2.db-wal", "v2.db-shm",
                                           "work")) == snap

        def snap_outside():
            return _inventory(w.tmp, skip=("arts", "bk", "v2.db",
                                           "v2.db-wal", "v2.db-shm",
                                           "work"))
        work = w.tmp / "work"
        work.mkdir()
        # (a) destination is a link to an outside non-empty folder.
        os.symlink(outside, work / "ds-a")
        s = snap_outside()
        out, err = _export(w, work / "ds-a", views)
        results["dest_link_nonempty"] = out is None and outside_same(s) \
            and os.readlink(work / "ds-a") == str(outside)
        # (b) destination is a link to an outside EMPTY folder.
        os.symlink(empty_out, work / "ds-b")
        s = snap_outside()
        out, err = _export(w, work / "ds-b", views)
        results["dest_link_empty"] = not any(empty_out.iterdir()) \
            and outside_same(s) and (work / "ds-b").is_symlink()
        # (c) the legacy staging name is a link to outside.
        os.symlink(outside, work / ".ds-c.building")
        s = snap_outside()
        out, err = _export(w, work / "ds-c", views)
        results["legacy_staging_link"] = outside_same(s) and \
            (work / ".ds-c.building").is_symlink()
        # (d) the build's own staging name pre-exists as a link.
        if accepts(w.exporter.build, "export_id"):
            eid = "export-m14e-link-0001"
            os.symlink(outside, work / f".ds-d.building-{eid}")
            s = snap_outside()
            out, err = _export(w, work / "ds-d", views, export_id=eid)
            results["own_staging_link_refused"] = out is None and \
                outside_same(s) and not (work / "ds-d").exists()
        # (e) a previous export whose listed child became a link, and one
        # holding an extra unlisted link to an outside folder.
        out, err = _export(w, work / "ds-e", views)
        (work / "ds-e" / "README.md").unlink()
        os.symlink(outside / "SECRET.bin", work / "ds-e" / "README.md")
        s = snap_outside()
        out_e, _ = _export(w, work / "ds-e", views)
        results["listed_child_link"] = _is_sentinel(
            outside / "SECRET.bin") and _inventory(outside) == {
                "SECRET.bin": ("file", _sha(outside / "SECRET.bin"))}
        out, err = _export(w, work / "ds-f", views)
        os.symlink(outside, work / "ds-f" / "extra-link")
        s = snap_outside()
        out_f, _ = _export(w, work / "ds-f", views)
        results["unlisted_child_link_refused"] = out_f is None and \
            outside_same(s)
        # (g) an ancestor link: the user's chosen parent is a link.
        real_parent = w.tmp / "real-parent"
        real_parent.mkdir()
        (real_parent / "SIBLING.bin").write_bytes(SENTINEL)
        os.symlink(real_parent, work / "link-parent")
        out_g, err_g = _export(w, work / "link-parent" / "ds", views)
        names = sorted(os.listdir(real_parent))
        results["ancestor_link_only_destination"] = \
            _is_sentinel(real_parent / "SIBLING.bin") and \
            names in (["SIBLING.bin"], ["SIBLING.bin", "ds"]) and \
            (work / "link-parent").is_symlink()
        outc, errc = _export(w, work / "plain", views)
        results["plain_control_completes"] = _complete(outc) and \
            not _sums_problems(work / "plain")
        return check(results, {"variants": len(results),
                               "ancestor_outcome": "complete"
                               if _complete(out_g) else "refused",
                               "child_link_outcome": "complete"
                               if _complete(out_e) else "refused"},
                     witness="destination/staging/child/ancestor link"
                             " variants; outside tree inventoried")


@drives("LF-M14-C146")
def c146_nested_source_root(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        views = ("asr_supervised",)
        arts = w.store.artifacts_dir
        notes = w.store.notes_dir
        os.symlink(arts, w.tmp / "arts-link")
        variants = {"inside_artifacts": arts / "ds",
                    "nested_in_artifacts": arts / "sub" / "ds",
                    "inside_notes": notes / "ds",
                    "via_link_into_artifacts": w.tmp / "arts-link" / "ds",
                    "artifacts_dir_itself": arts}
        refused, touched = {}, []
        for name, dest in variants.items():
            a0, n0 = _inventory(arts), _inventory(notes)
            notes_existed = notes.exists()
            out, err = _export(w, dest, views)
            refused[name] = out is None
            if _inventory(arts) != a0 or _inventory(notes) != n0 or \
                    notes.exists() != notes_existed:
                touched.append(name)
        db_bytes = (w.tmp / "v2.db").stat().st_size
        out_db, _ = _export(w, w.tmp, views)
        outc, errc = _export(w, w.tmp / "outside-ds", views)
        return check({
            "managed_destinations_refused": all(refused.values()),
            "managed_tree_untouched": not touched,
            "db_folder_refused": out_db is None
            and (w.tmp / "v2.db").exists()
            and (w.tmp / "v2.db").stat().st_size >= db_bytes,
            "outside_control_completes": _complete(outc),
        }, {"refused": refused, "touched": touched, "errc": errc},
            witness="destinations inside artifacts/notes (direct, nested,"
                    " via link) vs an outside control")


@drives("LF-M14-C147")
def c147_outside_audio_path(entry):
    with MWorld() as w:
        a = w.ready_asr()
        _asr_world(w)
        outside = w.tmp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.wav"
        store_mod.write_wav_f32(sentinel, W.tone(911.0), W.RATE)
        digest = _sha(sentinel)
        st = os.stat(sentinel)
        ino = (st.st_dev, st.st_ino)
        sentinel_bytes = sentinel.read_bytes()
        os.symlink(sentinel, w.store.artifacts_dir / "link-to-outside.wav")
        orig = w.artifact_row(a["audio_aid"])
        reads = []
        real_open, real_os_open = open, os.open

        def note(fd):
            try:
                s = os.fstat(fd)
                if (s.st_dev, s.st_ino) == ino:
                    reads.append(1)
            except OSError:
                pass

        def tracking_open(*args, **kw):
            f = real_open(*args, **kw)
            try:
                note(f.fileno())
            except (OSError, ValueError, AttributeError):
                pass
            return f

        def tracking_os_open(*args, **kw):
            fd = real_os_open(*args, **kw)
            note(fd)
            return fd
        import builtins
        leaks, outcomes = [], {}
        variants = (str(sentinel), "../outside/sentinel.wav",
                    "link-to-outside.wav")
        for i, variant in enumerate(variants):
            w.store.submit(lambda c, v=variant: c.execute(
                "UPDATE artifacts SET content_path=?, sha256=? WHERE"
                " artifact_id=?", (v, digest, a["audio_aid"])))
            w.splits.assign()
            builtins.open, os.open = tracking_open, tracking_os_open
            try:
                out, err = _export(w, f"ds-{i}", ("asr_supervised",))
            finally:
                builtins.open, os.open = real_open, real_os_open
            outcomes[i] = "complete" if _complete(out) else "refused"
            root = w.tmp / f"ds-{i}"
            if root.is_dir():
                for f in (root / "artifacts").glob("*"):
                    if _sha(f) == digest:
                        leaks.append(i)
        n_reads = len(reads)
        w.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET content_path=?, sha256=? WHERE"
            " artifact_id=?", (orig[4], orig[5], a["audio_aid"])))
        w.splits.assign()
        outc, errc = _export(w, "ds-control", ("asr_supervised",))
        exs, _r, _p = _records(w.tmp / "ds-control")
        mine = [e for e in exs if e.get("example_id") == a["example_id"]]
        return check({
            "no_outside_open": n_reads == 0,
            "no_outside_copy": not leaks,
            "sentinel_unchanged": sentinel.is_file()
            and sentinel.read_bytes() == sentinel_bytes,
            "managed_control_exports_audio": _complete(outc)
            and len(mine) == 1 and mine[0].get("audio_sha256") == orig[5],
        }, {"outcomes": outcomes, "outside_opens": n_reads,
            "leaks": leaks, "errc": errc},
            witness="absolute / traversal / symlink content_path with the"
                    " sentinel's digest; opens tracked by inode",
            grading="decision", decision=dec("D11"))


@drives("LF-M14-C148")
def c148_path_and_id_escape(entry):
    bad_ids = {"traversal_id": "../../escape-id",
               "absolute_id": "/abs-escape-id",
               "nested_traversal_id": "sub/../../escape-two",
               "unicode_id": "art-‮gnpé"}
    results, observed = {}, {}
    for name, bad in list(bad_ids.items()) + [("well_formed_control",
                                               "art-m14ewellformed01")]:
        with MWorld() as w:
            asr = _asr_world(w)
            a = next(iter(asr.values()))

            def op(c, bad=bad, a=a):
                cols = [r[1] for r in c.execute(
                    "PRAGMA table_info(artifacts)").fetchall()]
                row = c.execute(
                    f"SELECT {','.join(cols)} FROM artifacts WHERE"
                    " artifact_id=?", (a["audio_aid"],)).fetchone()
                d = dict(zip(cols, row))
                d["artifact_id"] = bad
                c.execute(f"INSERT INTO artifacts({','.join(cols)}) VALUES"
                          f"({','.join('?' * len(cols))})",
                          [d[k] for k in cols])
            w.store.submit(op)
            w.rewrite_envelope(a["example_id"], lambda env, bad=bad: env[
                "artifact_ids"].__setitem__("original_audio", bad))
            w.splits.assign()
            base = w.tmp / "out" / "deep"
            base.mkdir(parents=True)
            skip = ("out/deep/ds", "v2.db", "v2.db-wal", "v2.db-shm")
            before = _inventory(w.tmp, skip=skip)
            out, err = _export(w, base / "ds", ("asr_supervised",))
            after = _inventory(w.tmp, skip=skip)
            escaped = sorted(set(after) - set(before))
            dest = base / "ds"
            bad_paths = []
            exported_bad = False
            if dest.is_dir():
                exs, _r, _p = _records(dest)
                bad_paths = _audio_paths_ok(dest, exs)
                exported_bad = any(e.get("example_id") == a["example_id"]
                                   for e in exs)
                sums = _sums_problems(dest)
            else:
                sums = []
            observed[name] = {"outcome": "complete" if _complete(out)
                              else "refused", "escaped": len(escaped),
                              "bad_paths": bad_paths,
                              "sums": sums[:2],
                              "exported": exported_bad}
            if name == "well_formed_control":
                results["well_formed_id_exported"] = _complete(out) and \
                    exported_bad and not bad_paths and not sums
            else:
                results[f"{name}_no_escape"] = not escaped
                results[f"{name}_strict_admission"] = not bad_paths and \
                    not sums
    return check(results, observed,
                 witness="audio artifact rows re-keyed with traversal /"
                         " absolute / unicode ids; tree outside the"
                         " destination inventoried; sums recounted")


@drives("LF-M14-C149")
def c149_cli_explicit_db(entry):
    w = MWorld(artifacts="v2-artifacts")
    try:
        _asr_world(w)
        w.splits.assign()
        w.store.close()
        db = w.tmp / "v2.db"

        def user_version():
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                return con.execute("PRAGMA user_version").fetchone()[0]
            finally:
                con.close()
        uv0 = user_version()
        home = w.tmp / "home"
        env = dict(os.environ, HOME=str(home))
        script = str(W.ROOT / "scripts/v2/export_dataset.py")
        runs = {}
        for tag, args in (("relative", ["cli-rel", "--db", "v2.db"]),
                          ("absolute", [str(w.tmp / "cli-abs"), "--db",
                                        str(db)])):
            p = subprocess.run(
                [sys.executable, script, *args, "--views",
                 "asr_supervised"], capture_output=True, text=True,
                env=env, cwd=str(w.tmp), timeout=180)
            runs[tag] = (p.returncode, "export complete" in p.stdout)
        uv1 = user_version()
        dests = {t: w.tmp / n for t, n in (("relative", "cli-rel"),
                                           ("absolute", "cli-abs"))}
        return check({
            "both_runs_complete": all(rc == 0 and ok
                                      for rc, ok in runs.values()),
            "path_conversion_correct": all(
                d.is_dir() and not _sums_problems(d)
                and len(_records(d)[0]) == 10 for d in dests.values()),
            "live_default_untouched": not home.exists(),
            "schema_unchanged_no_unprotected_migration": uv0 == uv1,
        }, {"runs": runs, "user_version": [uv0, uv1]},
            witness="export_dataset.py subprocess, HOME=temp, relative and"
                    " absolute --db; current-schema db so no migration ran")
    finally:
        w.closed = True
        w._tmp.cleanup()


@drives("LF-M14-S021")
def s021_preexisting_destination_and_staging(entry):
    views = ("asr_supervised",)
    out_rec = {}
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        # Seam "before build starts": both sentinels placed, then build.
        dest = w.tmp / "ds"
        dest.mkdir()
        (dest / "USER.bin").write_bytes(SENTINEL)
        stag = w.tmp / ".ds.building"
        (stag / "deep").mkdir(parents=True)
        (stag / "deep" / "USER.bin").write_bytes(SENTINEL)
        snap_d, snap_s = _inventory(dest), _inventory(stag)
        w.store.append_consent("disabled")
        o1, _ = _export(w, dest, views)
        w.store.append_consent("enabled")
        o2, _ = _export(w, dest, views)
        kept_1 = _inventory(dest) == snap_d and _inventory(stag) == snap_s
        # Staging sentinel alone (destination absent): consent refused,
        # then enabled (the build must not reuse or remove it).
        dest2 = w.tmp / "ds2"
        stag2 = w.tmp / ".ds2.building"
        (stag2 / "deep").mkdir(parents=True)
        (stag2 / "deep" / "USER.bin").write_bytes(SENTINEL)
        snap2 = _inventory(stag2)
        w.store.append_consent("disabled")
        o3, _ = _export(w, dest2, views)
        w.store.append_consent("enabled")
        o4, e4 = _export(w, dest2, views)
        kept_2 = _inventory(stag2) == snap2
        # Alternate order: sentinel added after a completed export.
        dest3 = w.tmp / "ds3"
        o5, _ = _export(w, dest3, views)
        (dest3 / "USER.bin").write_bytes(SENTINEL)
        snap3 = _inventory(dest3)
        o6, _ = _export(w, dest3, views)
        kept_3 = _inventory(dest3) == snap3
        # Positive control: nothing pre-existing.
        oc, ec = _export(w, w.tmp / "ds-clean", views)
        out_rec = {"o2": "complete" if _complete(o2) else "refused",
                   "o4": "complete" if _complete(o4) else "refused",
                   "e4": e4, "ec": ec}
        return check({
            "dest_sentinel_refused_both_consents": o1 is None and o2 is None,
            "dest_and_staging_bytes_preserved": kept_1,
            "staging_sentinel_preserved_on_refusal_and_success":
                o3 is None and kept_2 and _complete(o4),
            "later_user_file_refused_and_preserved": _complete(o5)
            and o6 is None and kept_3,
            "clean_control_completes": _complete(oc),
        }, out_rec, witness="sentinels placed before build (dest and"
                            " .ds.building), consent disabled/enabled",
            grading="decision", decision=dec("D09"),
            reached="before build starts")


# =============================================================================
# export_concurrency — C150..C158, S019, S020, S030, S032, MR010
# =============================================================================


@drives("LF-M14-C150")
def c150_positive_no_change(entry):
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        eid = "export-m14e-c150-0001"
        kw = _eid_kw(w, eid)
        out, err = _export(w, "ds", ("asr_supervised",), **kw)
        if not _complete(out):
            return check({"export_completed": False}, {"err": err})
        dest = w.tmp / "ds"
        rows = _rows(w)
        snap = _inventory(dest)
        idem = None
        if kw:
            out2, err2 = _export(w, "ds", ("asr_supervised",), **kw)
            idem = _complete(out2) and \
                out2.get("fingerprint") == out.get("fingerprint") and \
                _inventory(dest) == snap and _rows(w) == rows
        return check({
            "one_complete_destination": not [
                n for n in os.listdir(w.tmp) if n.startswith(".ds")]
            and not _sums_problems(dest),
            "one_success_receipt": [(r[0], r[1]) for r in rows]
            == [(out["export_id"], "complete")]
            and rows[0][3] == str(dest),
            "manifest_names_receipt": (_manifest(dest) or {}).get(
                "export_id") == out["export_id"],
            "retry_returns_receipt": idem in (None, True),
        }, {"rows": len(rows), "idempotent_retry": idem},
            witness="undisturbed build; export_id retry when accepted")


def _selected_purge_scenario():
    """S019/C151: purge a selected dependency after the snapshot read
    (graph staged) and before the fence; plus the undisturbed control
    and the alternate order (purge before the build)."""
    out = {}
    with MWorld() as w:
        asr = _asr_world(w)
        victim = next(iter(asr))
        ref = _verbatim_aid(w, victim)
        w.splits.assign()
        unowned = w.tmp / ".ds.building"
        (unowned / "nested").mkdir(parents=True)
        (unowned / "nested" / "KEEP").write_bytes(SENTINEL)
        usnap = _inventory(unowned)
        with _at_first_hash(lambda: w.purge(ref)) as seam:
            o, err = _export(w, "ds", ("asr_supervised",))
        out["reached"] = seam["fired"]
        out["purged"] = w.one("SELECT purged FROM artifacts WHERE"
                              " artifact_id=?", (ref,))[0] == 1
        out["aborted"] = o is None and not (w.tmp / "ds").exists()
        out["no_complete_row"] = not [r for r in _rows(w)
                                      if r[1] == "complete"]
        out["owned_staging_removed"] = not _leftovers(w.tmp, "ds")
        out["unowned_preserved"] = _inventory(unowned) == usnap
        out["err"] = err and err[:90]
        # Alternate serialization: the purge committed before the build.
        o2, err2 = _export(w, "ds-after", ("asr_supervised",))
        exs, _r, _p = _records(w.tmp / "ds-after")
        out["alternate_excludes_only_dependent"] = _complete(o2) and \
            {e["example_id"] for e in exs} == set(asr) - {victim}
    with MWorld() as w:
        asr = _asr_world(w)
        w.splits.assign()
        with _at_first_hash(lambda: None) as seam:
            o3, err3 = _export(w, "ds", ("asr_supervised",))
        exs, _r, _p = _records(w.tmp / "ds")
        out["control_completes"] = seam["fired"] and _complete(o3) and \
            {e["example_id"] for e in exs} == set(asr)
    return out


@drives("LF-M14-C151", "LF-M14-S019")
def c151_s019_selected_purge_before_fence(entry):
    s = _selected_purge_scenario()
    if not s["reached"]:
        return invalid("first-hash seam never reached", {"err": s["err"]})
    if not s["purged"]:
        return invalid("interleaved purge did not commit")
    return check({k: s[k] for k in (
        "aborted", "no_complete_row", "owned_staging_removed",
        "unowned_preserved", "alternate_excludes_only_dependent",
        "control_completes")}, {"err": s["err"]},
        witness="verbatim reference purged at the first staged file hash"
                " (after read, before fence)", reached="after source read",
        grading="decision", decision=dec("D09"))


def _unrelated_delete_run(mode):
    """Build with an unrelated deletion interleaved after the read
    (``mode`` = mid) or committed before the build (``before``), next
    to a baseline build of the same world."""
    with MWorld() as w:
        asr = _asr_world(w)
        job_only = w.job("unrelated job only words", audio=False,
                         example=False)
        side = w.job("unrelated unselected example words")
        w.splits.assign()
        base, berr = _export(w, "ds-base", ("asr_supervised",))
        b_ex, b_ref, _p = _records(w.tmp / "ds-base")

        def delete():
            w.store.delete_everywhere("job", job_only["job_id"])
            w.store.delete_everywhere("example", side["example_id"])
        if mode == "before":
            delete()
            seam = {"fired": True}
            o, err = _export(w, "ds", ("asr_supervised",))
        else:
            with _at_first_hash(delete) as seam:
                o, err = _export(w, "ds", ("asr_supervised",))
        tomb = w.one("SELECT COUNT(*) FROM deletion_tombstones")[0]
        exs, refs, _p = _records(w.tmp / "ds")
        return {
            "reached": seam["fired"], "deleted": tomb > 0,
            "complete": _complete(o) and _complete(base),
            "records_identical": exs == b_ex and refs == b_ref
            and {e["example_id"] for e in exs} == set(asr),
            "fingerprint_retained": _complete(o) and _complete(base)
            and o["fingerprint"] == base["fingerprint"],
            "err": err or berr,
        }


@drives("LF-M14-C152", "LF-M14-S020")
def c152_s020_unrelated_delete(entry):
    mid = _unrelated_delete_run("mid")
    before = _unrelated_delete_run("before")
    if not mid["reached"]:
        return invalid("first-hash seam never reached", {"err": mid["err"]})
    if not (mid["deleted"] and before["deleted"]):
        return invalid("unrelated deletion did not commit")
    return check({
        "completes_normally": mid["complete"],
        "records_retained": mid["records_identical"],
        "fingerprint_retained": mid["fingerprint_retained"],
        "alternate_order_same": before["complete"]
        and before["records_identical"] and before["fingerprint_retained"],
    }, {"err": mid["err"]}, witness="delete_everywhere of a job-only and an"
                                    " unselected example at the first"
                                    " staged hash", reached="after read")


def _publication_fence_run(action_kind):
    """Purge or revoke at the publication rename. Inside the writer the
    action is queued (serialized after publication) and records what it
    saw; outside it is committed first (serialized before)."""
    with MWorld() as w:
        asr = _asr_world(w)
        victim = next(iter(asr))
        aid = asr[victim]["audio_aid"]
        w.splits.assign()
        dest = w.tmp / "ds"
        seen = {}

        def act(in_writer):
            if action_kind == "purge":
                def op():
                    seen["complete_rows"] = w.store._db.execute(
                        "SELECT COUNT(*) FROM export_manifests WHERE"
                        " state='complete'").fetchone()[0]
                    seen["dest_existed"] = dest.is_dir()
                    w.store._purge_artifact(aid, reason="retention")
                    w.store._purge_pending = True
                if in_writer:
                    w.store._submit(op)
                else:
                    w.store._submit(op, wait=True)
            else:
                def look():
                    seen["complete_rows"] = w.store._db.execute(
                        "SELECT COUNT(*) FROM export_manifests WHERE"
                        " state='complete'").fetchone()[0]
                    seen["dest_existed"] = dest.is_dir()
                if in_writer:
                    w.store._submit(look)
                    w.store.append_consent("disabled")
                else:
                    w.store._submit(look, wait=True)
                    w.store.append_consent("disabled")
                    w.store.sync()
        with _at_publish_rename(act) as st:
            o, err = _export(w, dest, ("asr_supervised",))
        w.store.sync()
        applied = (w.one("SELECT purged FROM artifacts WHERE artifact_id=?",
                         (aid,))[0] == 1) if action_kind == "purge" else \
            w.store.consent_state() == "disabled"
        # After the governing action, a NEW build never publishes the
        # removed source (purge) or anything at all (revocation).
        o2, err2 = _export(w, "ds-next", ("asr_supervised",))
        if action_kind == "purge":
            exs, _r, _p = _records(w.tmp / "ds-next")
            next_ok = _complete(o2) and victim not in {
                e["example_id"] for e in exs}
        else:
            next_ok = o2 is None and not (w.tmp / "ds-next").exists()
        return {"reached": bool(st["hook"]), "in_writer": st["in_writer"],
                "applied": applied, "complete": _complete(o),
                "dest": dest.is_dir(), "seen": seen, "next_ok": next_ok,
                "err": err}


@drives("LF-M14-C153", "LF-M14-S030")
def c153_s030_purge_after_fence(entry):
    runs = {k: _publication_fence_run(k) for k in ("purge", "revoke")}
    if not all(r["reached"] for r in runs.values()):
        return invalid("publication rename seam never reached",
                       {k: r["err"] for k, r in runs.items()})
    if not all(r["applied"] for r in runs.values()):
        return invalid("interleaved action did not commit")
    conds = {}
    for k, r in runs.items():
        if r["in_writer"]:
            # Serialized after the one publication op: the export was
            # already complete when the action committed.
            conds[f"{k}_linearized_after_publication"] = r["complete"] and \
                r["dest"] and r["seen"].get("complete_rows") == 1 and \
                r["seen"].get("dest_existed") is True
        else:
            conds[f"{k}_before_publication_not_published"] = \
                not r["complete"] and not r["dest"]
        conds[f"{k}_no_later_unauthorized_export"] = r["next_ok"]
    s = _selected_purge_scenario()
    conds["alternate_order_purge_before_fence_aborts"] = s["reached"] and \
        s["aborted"]
    conds["control_completes"] = s["control_completes"]
    return check(conds, {k: {"in_writer": r["in_writer"],
                             "complete": r["complete"]}
                         for k, r in runs.items()},
                 witness="os.rename of .building at publication; action"
                         " queued from the writer thread (no wait)",
                 reached="after final recheck before rename",
                 grading="decision", decision=dec("D09"))


@drives("LF-M14-C154")
def c154_consent_revoke(entry):
    res = {}
    with MWorld() as w:  # revoked at the snapshot (serialized before it)
        _asr_world(w)
        w.splits.assign()
        w.store.append_consent("disabled")
        o, _ = _export(w, "ds", ("asr_supervised",))
        res["snapshot_refused"] = o is None and not (w.tmp / "ds").exists() \
            and not [r for r in _rows(w) if r[1] == "complete"]
        w.store.append_consent("enabled")
        o, err = _export(w, "ds", ("asr_supervised",))
        res["reenabled_control_completes"] = _complete(o)
    with MWorld() as w:  # revoked while staged, before the fence
        _asr_world(w)
        w.splits.assign()

        def revoke():
            w.store.append_consent("disabled")
            w.store.sync()
        with _at_first_hash(revoke) as seam:
            o, _ = _export(w, "ds", ("asr_supervised",))
        res["staged_revoke_aborts"] = seam["fired"] and o is None and \
            not (w.tmp / "ds").exists() and not _leftovers(w.tmp, "ds")
    r = _publication_fence_run("revoke")
    if not (seam["fired"] and r["reached"]):
        return invalid("a revocation seam was never reached")
    if r["in_writer"]:
        res["publication_boundary_linearized"] = r["complete"] and \
            r["seen"].get("complete_rows") == 1
    else:
        res["publication_boundary_linearized"] = not r["complete"] and \
            not r["dest"]
    res["no_new_export_after_revocation"] = r["next_ok"]
    return check(res, {"publication_in_writer": r["in_writer"]},
                 witness="revocation at snapshot, while staged, and at the"
                         " publication rename",
                 grading="decision", decision=dec("D09"))


@drives("LF-M14-C155")
def c155_label_preference_change(entry):
    res, obs = {}, {}

    def fixture(w):
        asr = _asr_world(w)
        p = w.transform_task("staged pair source", ["Stage A.", "Stage B."])
        a, b = (c["candidate_id"] for c in p["candidates"])
        w.judge(p, a, b, "prefer_b")
        t = w.transform_task("staged accept source", ["Stage accepted."])
        tc = t["candidates"][0]["candidate_id"]
        w.accept(t, tc)
        w.splits.assign()
        return asr, p, a, b, t, tc
    changes = {
        "preference": lambda w, f: w.judge(f[1], f[2], f[3], "prefer_a"),
        "label": lambda w, f: w.review.record_label(
            next(iter(f[0])), edit_kind="changed_intent",
            origin_stages=("user_intent",)),
        "accept": lambda w, f: w.accept(f[4], f[5], "reject"),
    }
    for name, change in changes.items():
        with MWorld() as w:
            f = fixture(w)
            with _at_first_hash(lambda: change(w, f)) as seam:
                o, err = _export(w, "ds")
            if not seam["fired"]:
                return invalid(f"{name}: staged seam never reached")
            res[f"{name}_staged_change_not_mixed"] = o is None and \
                not (w.tmp / "ds").exists() and not _leftovers(w.tmp, "ds")
            obs[name] = err and err[:80]
            # Explicit requalification: a fresh build after the change
            # reflects the changed judgment alone.
            o2, err2 = _export(w, "ds-requal")
            exs, _r, prefs = _records(w.tmp / "ds-requal")
            kinds = _ids_by_kind(exs, prefs)
            if name == "preference":
                ok = _complete(o2) and [pp.get("chosen") for pp in prefs] \
                    == ["a"]
            elif name == "label":
                ok = _complete(o2) and next(iter(f[0])) not in \
                    kinds["asr_supervised"]
            else:
                ok = _complete(o2) and f[5] not in \
                    kinds["transform_supervised"]
            res[f"{name}_requalified_build_reflects_change"] = ok
    with MWorld() as w:
        f = fixture(w)
        o, err = _export(w, "ds")
        exs, _r, prefs = _records(w.tmp / "ds")
        res["unchanged_control_completes"] = _complete(o) and \
            [pp.get("chosen") for pp in prefs] == ["b"] and \
            f[5] in _ids_by_kind(exs, prefs)["transform_supervised"]
    return check(res, obs, witness="judgment flip / changed_intent label /"
                                   " accept->reject at the first staged hash",
                 grading="decision", decision=dec("D09"))


@drives("LF-M14-C156")
def c156_missing_dependency_row(entry):
    with MWorld() as w:
        asr = _asr_world(w)
        victim = next(iter(asr))
        ref = _verbatim_aid(w, victim)
        w.splits.assign()

        def drop_row():
            w.store.submit(lambda c: c.execute(
                "DELETE FROM artifacts WHERE artifact_id=?", (ref,)))
        with _at_first_hash(drop_row) as seam:
            o, err = _export(w, "ds", ("asr_supervised",))
        gone = w.one("SELECT COUNT(*) FROM artifacts WHERE artifact_id=?",
                     (ref,))[0] == 0
        if not seam["fired"]:
            return invalid("first-hash seam never reached", {"err": err})
        if not gone:
            return invalid("dependency row was not deleted")
        res = {"absence_detected": o is None and not (w.tmp / "ds").exists()
               and not _leftovers(w.tmp, "ds")
               and not [r for r in _rows(w) if r[1] == "complete"]}
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        with _at_first_hash(lambda: None) as seam2:
            o2, _ = _export(w, "ds", ("asr_supervised",))
        res["undisturbed_control_completes"] = seam2["fired"] and \
            _complete(o2)
    return check(res, {"err": err and err[:90]},
                 witness="artifact row of a selected verbatim reference"
                         " DELETEd (not flagged) while staged",
                 grading="decision", decision=dec("D09"))


def _two_builds(same_id=False):
    """Two same-destination builds released together at staging
    creation (a Barrier inside os.mkdir for the staging name)."""
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        dest = w.tmp / "ds"
        prefix = ".ds.building"
        barrier = threading.Barrier(2, timeout=30)
        lock = threading.Lock()
        st = {"arrived": 0, "broken": False, "created": [],
              "dest_at_barrier": None, "mkdir_failed": 0}
        real_mkdir = os.mkdir

        def mkdir(path, *a, **k):
            name = os.path.basename(os.fspath(path))
            if name.startswith(prefix) and threading.current_thread() \
                    .name.startswith("m14e-builder"):
                with lock:
                    st["arrived"] += 1
                try:
                    if barrier.wait() == 0:
                        st["dest_at_barrier"] = dest.exists()
                except threading.BrokenBarrierError:
                    st["broken"] = True
                try:
                    out = real_mkdir(path, *a, **k)
                except OSError:
                    with lock:
                        st["mkdir_failed"] += 1
                    raise
                with lock:
                    st["created"].append(name)
                return out
            return real_mkdir(path, *a, **k)
        outcomes = {}
        kw = _eid_kw(w, "export-m14e-same-0001") if same_id else {}

        def run(tag):
            try:
                outcomes[tag] = ("ok", w.exporter.build(
                    dest, task_views=("asr_supervised",), **kw))
            except export_mod.ExportError as e:
                outcomes[tag] = ("refused", str(e)[:80])
            except Exception as e:  # noqa: BLE001
                outcomes[tag] = ("raw", f"{type(e).__name__}")
        os.mkdir = mkdir
        try:
            threads = [threading.Thread(target=run, args=(t,),
                                        name=f"m14e-builder-{t}")
                       for t in ("A", "B")]
            for t in threads:
                t.start()
            for t in threads:
                t.join(90)
            alive = any(t.is_alive() for t in threads)
        finally:
            os.mkdir = real_mkdir
        rows = _rows(w)
        ok_ids = [o[1]["export_id"] for o in outcomes.values()
                  if o[0] == "ok"]
        man = _manifest(dest) or {}
        retry = None
        if same_id and kw:
            snap = _inventory(dest)
            o3, _ = _export(w, dest, ("asr_supervised",), **kw)
            retry = _complete(o3) and _inventory(dest) == snap
        return {"w_rows": rows, "alive": alive, "st": st,
                "outcomes": {k: v[0] for k, v in outcomes.items()},
                "raw": [v[1] for v in outcomes.values() if v[0] == "raw"],
                "ok_ids": ok_ids, "dest_id": man.get("export_id"),
                "dest_valid": dest.is_dir() and not _sums_problems(dest),
                "leftovers": _leftovers(w.tmp, "ds"), "retry": retry,
                "id_supported": bool(kw) or not same_id}


def _sequential_builds():
    with MWorld() as w:
        _asr_world(w)
        w.splits.assign()
        o1, _ = _export(w, "ds", ("asr_supervised",))
        o2, _ = _export(w, "ds", ("asr_supervised",))
        man = _manifest(w.tmp / "ds") or {}
        return _complete(o1) and _complete(o2) and \
            man.get("export_id") == o2["export_id"] and \
            not _leftovers(w.tmp, "ds") and not _sums_problems(w.tmp / "ds")


@drives("LF-M14-C157", "LF-M14-S032")
def c157_s032_two_builds(entry):
    r = _two_builds()
    if r["alive"]:
        return invalid("a builder never finished (deadlock guard)")
    st = r["st"]
    if st["broken"] or st["arrived"] != 2:
        return invalid("both builders never met at staging creation",
                       {"arrived": st["arrived"], "broken": st["broken"]})
    rows = r["w_rows"]
    complete_rows = [x for x in rows if x[1] == "complete"]
    failed_rows = [x for x in rows if x[1] != "complete"]
    n_ok = sum(1 for v in r["outcomes"].values() if v == "ok")
    n_ref = sum(1 for v in r["outcomes"].values() if v == "refused")
    conds = {
        "ownership_unresolved_at_barrier": st["dest_at_barrier"] is False,
        "exclusive_owned_staging": len(st["created"]) == 2
        and len(set(st["created"])) == 2 and st["mkdir_failed"] == 0,
        "no_raw_or_unknown_outcome": not r["raw"]
        and n_ok + n_ref == 2 and n_ok >= 1,
        "receipts_match_outcomes": sorted(x[0] for x in complete_rows)
        == sorted(r["ok_ids"]) and len(failed_rows) == n_ref
        and all(x[2] == "refused" for x in failed_rows),
        "destination_is_one_coherent_export": r["dest_valid"]
        and r["dest_id"] in r["ok_ids"],
        "no_shared_staging_left": not r["leftovers"],
        "alternate_order_sequential_completes": _sequential_builds(),
    }
    observed = {"outcomes": r["outcomes"], "created": len(st["created"]),
                "rows": [x[1] for x in rows]}
    same = _two_builds(same_id=True)
    if same["id_supported"] and not same["alive"] and \
            not same["st"]["broken"]:
        s_rows = same["w_rows"]
        conds["same_operation_id_one_coherent_operation"] = \
            [x[1] for x in s_rows] == ["complete"] and \
            same["dest_id"] == "export-m14e-same-0001" and \
            same["dest_valid"] and same["retry"] is True and \
            not same["leftovers"] and not same["raw"]
        observed["same_id_outcomes"] = same["outcomes"]
    else:
        observed["same_id_variant"] = "not run (export_id unsupported)"
    return check(conds, observed,
                 witness="threading.Barrier inside os.mkdir of the staging"
                         " name; both builders past destination checks",
                 reached="both builders at staging creation",
                 grading="decision", decision=dec("D09"))


_CRASH_SCRIPT = r"""
import os, pathlib, shutil, sys
root, db, arts, bk, dest, boundary, marker = sys.argv[1:8]
sys.path.insert(0, root)
from localflow.v2 import store as store_mod
from localflow.v2.curation import export as export_mod
def die():
    pathlib.Path(marker).write_text(boundary)
    os._exit(86)
if boundary == "record_write":
    def wj(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"partial": ')
            f.flush()
        die()
    export_mod._write_jsonl = wj
elif boundary == "audio_copy":
    def cpo(src, dst, length=0):
        dst.write(src.read(4096))
        dst.flush()
        die()
    def cpf(src, dst, *a, **k):
        with open(src, "rb") as s, open(dst, "wb") as d:
            d.write(s.read(4096))
        die()
    shutil.copyfileobj = cpo
    shutil.copyfile = cpf
elif boundary == "sums":
    def ws(r):
        pathlib.Path(r, "SHA256SUMS.txt").write_text("partial")
        die()
    export_mod._write_sums = ws
elif boundary in ("before_rename", "after_rename"):
    real = os.rename
    def rn(src, dst, *a, **k):
        hit = ".building" in os.path.basename(os.fspath(src))
        if hit and boundary == "before_rename":
            die()
        out = real(src, dst, *a, **k)
        if hit:
            die()
        return out
    os.rename = rn
store = store_mod.Store(pathlib.Path(db), artifacts_dir=pathlib.Path(arts),
                        backup_dir=pathlib.Path(bk))
ex = export_mod.DatasetExporter(store)
ex.build(pathlib.Path(dest), task_views=("asr_supervised",
                                          "cleanup_supervised"))
print("NO_CRASH")
store.close()
"""


@drives("LF-M14-C158")
def c158_crash_boundaries(entry):
    boundaries = ("record_write", "audio_copy", "sums", "before_rename",
                  "after_rename")
    w = MWorld()
    store = None
    try:
        _asr_world(w)
        _cleanup(w, "crash boundary cleanup", "Crash boundary cleanup.")
        w.splits.assign()
        w.store.close()
        out = w.tmp / "out"
        out.mkdir()
        (out / "UNRELATED.bin").write_bytes(SENTINEL)
        for b in boundaries:
            (out / f".ds-{b}.building" / "nested").mkdir(parents=True)
            (out / f".ds-{b}.building" / "nested" / "KEEP").write_bytes(
                SENTINEL)
        env = dict(os.environ, HOME=str(w.tmp / "home"))
        per, conds = {}, {}
        reached_all = True

        def unowned_skip():
            skip = []
            for b in boundaries:
                skip.append(f"ds-{b}")
                skip.extend(_leftovers(out, f"ds-{b}"))
            return tuple(skip)
        for b in boundaries:
            dest = out / f"ds-{b}"
            marker = w.tmp / f"marker-{b}"
            before = _inventory(out, skip=unowned_skip())
            p = subprocess.run(
                [sys.executable, "-c", _CRASH_SCRIPT, str(W.ROOT),
                 str(w.tmp / "v2.db"), str(w.tmp / "arts"),
                 str(w.tmp / "bk"), str(dest), b, str(marker)],
                capture_output=True, text=True, env=env, timeout=180)
            reached = p.returncode == 86 and marker.is_file()
            reached_all = reached_all and reached
            store = store_mod.Store(w.tmp / "v2.db",
                                    artifacts_dir=w.tmp / "arts",
                                    backup_dir=w.tmp / "bk",
                                    now_fn=w.clock)
            rows = store.submit(lambda c: c.execute(
                "SELECT export_id, state, destination FROM"
                " export_manifests").fetchall())
            dest_state = "absent" if not dest.exists() else (
                "complete" if not _sums_problems(dest) else "partial")
            dest_id = (_manifest(dest) or {}).get("export_id")
            false_complete = [r for r in rows if r[1] == "complete" and (
                not pathlib.Path(r[2]).is_dir()
                or (_manifest(r[2]) or {}).get("export_id") != r[0]
                or _sums_problems(r[2]))]
            left = _leftovers(out, f"ds-{b}")
            left_snap = {n: _inventory(out / n) for n in left}
            unowned_kept = _inventory(out, skip=unowned_skip()) == before
            # Recovery: a fresh build to the same destination completes
            # and never removes another operation's leftovers.
            exporter = export_mod.DatasetExporter(store)
            try:
                rec = exporter.build(dest, task_views=(
                    "asr_supervised", "cleanup_supervised"))
            except export_mod.ExportError as e:
                rec = {"state": f"refused: {str(e)[:60]}"}
            store.close()
            store = None
            leftovers_kept = all(
                (out / n).exists() and _inventory(out / n) == s
                for n, s in left_snap.items())
            per[b] = {"reached": reached, "rc": p.returncode,
                      "dest": dest_state, "leftovers": len(left),
                      "false_complete_rows": len(false_complete),
                      "recovery": rec.get("state")}
            conds[f"{b}_no_partial_finalized"] = dest_state != "partial" \
                and not false_complete and (dest_state == "absent"
                                            or dest_id is not None)
            conds[f"{b}_unowned_untouched"] = unowned_kept and \
                _is_sentinel(out / "UNRELATED.bin") and \
                _is_sentinel(out / f".ds-{b}.building" / "nested" / "KEEP")
            conds[f"{b}_recovery_completes_without_removing_leftovers"] = \
                rec.get("state") == "complete" and leftovers_kept and \
                not _sums_problems(dest)
        if not reached_all:
            return invalid("a crash boundary was never reached",
                           {k: (v["reached"], v["rc"])
                            for k, v in per.items()})
        return check(conds, per,
                     witness="exporter killed (os._exit) in a subprocess at"
                             " record write / audio copy / sums / before and"
                             " after the publication rename",
                     grading="decision", decision=dec("D09"))
    finally:
        if store is not None:
            store.close()
        w.closed = True
        w._tmp.cleanup()


@drives("LF-M14-MR010")
def mr010_export_dependency_locality(entry):
    # Follow-up 1: remove ONE selected source (mid-build, then as the
    # committed state a later build sees).
    s = _selected_purge_scenario()
    # Follow-up 2: remove an UNRELATED source in a separate run.
    u = _unrelated_delete_run("mid")
    if not (s["reached"] and u["reached"]):
        return invalid("a removal seam was never reached")
    if not (s["purged"] and u["deleted"]):
        return invalid("a removal did not commit")
    return check({
        "selected_removal_fails_authorization": s["aborted"],
        "selected_removal_drops_only_dependent_record":
            s["alternate_excludes_only_dependent"],
        "unrelated_removal_does_not_invalidate": u["complete"]
        and u["records_identical"] and u["fingerprint_retained"],
        "source_run_completes": s["control_completes"],
    }, {"selected_err": s["err"], "unrelated_err": u["err"]},
        witness="selected verbatim purge vs unrelated job/example deletion,"
                " both at the first staged hash")
