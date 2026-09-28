"""GATE-G05 — generic events stay content-free across the composed
product (cross-milestone remediation of 340c566; Audit C TEST-GAP-05).

One real AppDelegate session (``test_lifecycle.Harness``: the real
coordinator, collector, Store, services and event writer on temporary
roots) drives distinct canaries through dictation, teach and approval,
the dictionary, notes and an attachment, Your Voice, transforms,
snippets and a dataset export — including refusals, an admitted
timeout, a vocabulary import refusal and a tampered dataset. The
oracle is the raw event files the writer produced: no canary may appear
in any field of any record (``detail`` included — it is stored
verbatim). Events contract invariants 2 and 4: metadata, sizes, timings
and reason codes, never raw or cleaned text.

Run (AppKit headless, desktop isolated):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_privacy.py [--json OUT]
"""

from __future__ import annotations

import json
import pathlib
import sys
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "lifecycle",):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import FakeSupervisor, Harness  # noqa: E402

CANARIES = {
    "transcript": "canarytranscriptqz",
    "correction": "canaryfixqz",
    "vocabulary": "canarytermqz",
    "note": "canarynoteqz",
    "filename": "canaryfileqz",
    "profile_phrase": "canaryphraseqz",
    "transform": "canarytransformqz",
    "snippet": "canarysnippetqz",
    "dataset_path": "canarydestqz",
    "dataset_text": "canarydatasetqz",
}


def scan(events_dir):
    """{canary kind: [(event, field)]} over every record of every file."""
    hits = {k: [] for k in CANARIES}
    records = 0
    for f in sorted(pathlib.Path(events_dir).rglob("*")):
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8", errors="replace") \
                .splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                rec = {"_unparsed": line}
            records += 1
            for field, value in rec.items():
                low = json.dumps(value).lower()
                for kind, canary in CANARIES.items():
                    if canary in low:
                        hits[kind].append((rec.get("event"), field))
    return hits, records


def session(h):
    """Drive every path once; failures of a step are recorded, never
    hidden (a step that could not run is reported as NOT_RUN)."""
    d, s = h.d, h.d.store
    steps = {}

    def step(name, fn):
        try:
            fn()
            steps[name] = "ran"
        except Exception as e:  # noqa: BLE001 — the refusal is the path
            steps[name] = f"raised {type(e).__name__}: {str(e)[:60]}"

    d.consent.set("enabled")

    class Sup(FakeSupervisor):
        def transcribe(self, **kw):
            out = super().transcribe(**kw)
            out["text"] = (f"please check the {CANARIES['transcript']}"
                           f" modul today")
            return out

        def clean(self, **kw):
            out = super().clean(**kw)
            out["text"] = kw["raw_text"]  # identity cleanup
            return out

    d.supervisor = Sup()

    def dictation():
        h.press()
        h.release()
        fn, a = h.run_coordinator()
        fn(*a)
    step("dictation", dictation)
    job = X.rows(s, "SELECT job_id FROM jobs ORDER BY rowid DESC LIMIT 1")
    job = job[0][0] if job else None

    def teach_approve():
        final = X.one(s, "SELECT content_text FROM artifacts WHERE job_id=?"
                      " AND role='applied_output' ORDER BY rowid DESC"
                      " LIMIT 1", (job,))[0]
        fixed = final.replace("modul", CANARIES["correction"]) \
            if "modul" in final else final + " " + CANARIES["correction"]
        cid = d._learning.teach_correction(job, fixed)["candidate_id"]
        d._learning.approve(cid)
    step("teach_approve", teach_approve)
    step("vocabulary_add", lambda: d._vocab.add_entry(
        CANARIES["vocabulary"].title(), [(CANARIES["vocabulary"], True)],
        approved=True))
    step("vocabulary_duplicate_refused", lambda: d._vocab.add_entry(
        CANARIES["vocabulary"].title(), [(CANARIES["vocabulary"], True)]))
    bad = h.tmp / f"{CANARIES['vocabulary']}.json"
    bad.write_text(json.dumps({"entries": [{"canonical": 5,
                                            "aliases": [CANARIES[
                                                "vocabulary"]]}]}))
    step("vocabulary_import_refused", lambda: d._vocab.import_json(bad))

    def notes():
        n = d._notes_store.create_note(f"{CANARIES['note']} body text")
        png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        d._notes_store.add_attachment(n["note_id"], png, "image/png",
                                      f"{CANARIES['filename']}.png")
    step("notes_and_attachment", notes)

    def note_timeout():
        with X.WriterHold(s) as hold, X.caller_timeout(s):
            try:
                d._notes_store.create_note(f"{CANARIES['note']} late")
            finally:
                hold.release()
        s.sync()
    step("note_admitted_timeout", note_timeout)

    def profile():
        for i in range(12):
            j, fam = s.create_job()
            aid = s.write_text_artifact(
                job_id=j, stage="asr", role="raw_transcript",
                text=f"{CANARIES['profile_phrase']} zeta words {i}",
                retention_class="training")
            ex = s.upsert_example(job_id=j, family_id=fam,
                                  consent_revision_id=
                                  s.current_consent_id())
            s.append_revision(ex, {
                "example_id": ex, "job_id": j, "family_id": fam,
                "origin": "live_capture",
                "artifact_ids": {"source_text": aid}, "outcome": {},
                "annotations": [], "missing_reasons": {}})
        from localflow.v2.profile import ProfileService
        ProfileService(s, emit=d.v2log.emit, min_words=10).compute()
    step("profile", profile)

    def transforms():
        t = d._tf_store.add_transform(name=CANARIES["transform"],
                                      mode="custom",
                                      prompt=f"{CANARIES['transform']} p",
                                      shortcut="q")
        d._tf_store.add_transform(name="other", mode="custom", prompt="x",
                                  shortcut="q")  # refused: collision
        del t
    step("transforms_with_refusal", transforms)

    def snippets():
        d._snip_store.add_snippet(trigger=f"insert {CANARIES['snippet']}",
                                  name="n", content=CANARIES["snippet"])
        d._snip_store.add_snippet(trigger=f"insert {CANARIES['snippet']}",
                                  name="n", content="dup")  # refused
    step("snippets_with_refusal", snippets)

    def export():
        # A populated synthetic world (12 ASR families, one assignment)
        # exported by an exporter that emits into THIS session's writer.
        from localflow.v2.curation.export import (DatasetExporter,
                                                  validate_dataset)
        with X.M.MWorld() as w:
            w.families(12, asr=True)
            w.splits.assign()
            dest = h.tmp / CANARIES["dataset_path"] / "ds"
            DatasetExporter(w.store, emit=d.v2log.emit).build(
                dest, task_views=("asr_supervised",))
            ex = dest / "examples.jsonl"
            ex.write_text(ex.read_text() + json.dumps(
                {"text": CANARIES["dataset_text"]}) + "\n")
            steps["tampered_validate"] = str(
                validate_dataset(dest)["valid"])
    step("export_and_tampered_validate", export)

    def managed_files():
        """Managed payload authority: a FIFO, a symlink, a traversal and
        a symlinked ancestor are refused (None, never a hang or a read
        outside the managed directory)."""
        import os
        from localflow.v2.store import read_managed_file
        root = h.tmp / "managed"
        (root / "sub").mkdir(parents=True)
        outside = h.tmp / f"{CANARIES['filename']}-outside.txt"
        outside.write_text(CANARIES["note"])
        os.mkfifo(root / f"{CANARIES['filename']}.fifo")
        os.symlink(outside, root / f"{CANARIES['filename']}.link")
        os.symlink(root / "sub", h.tmp / "linked-ancestor")
        (root / "sub" / "ok.bin").write_bytes(b"x")
        got = {
            "fifo": read_managed_file(root, f"{CANARIES['filename']}.fifo"),
            "symlink": read_managed_file(root,
                                         f"{CANARIES['filename']}.link"),
            "traversal": read_managed_file(root, "../" + outside.name),
            "linked_ancestor": read_managed_file(h.tmp / "linked-ancestor",
                                                 "ok.bin")}
        steps["managed_refusals"] = {k: v is None for k, v in got.items()}
        assert all(v is None for v in got.values()), steps[
            "managed_refusals"]
    step("managed_file_authority", managed_files)

    def validator_hostile():
        import os
        from localflow.v2.curation.export import validate_dataset
        ds = h.tmp / "hostile-ds"
        ds.mkdir()
        (ds / "dataset_manifest.json").write_text(json.dumps(
            {"exporter_version": 1, "files": [
                f"../{CANARIES['filename']}-outside.txt"]}))
        (ds / "SHA256SUMS.txt").write_text(
            "0" * 64 + f"  ../{CANARIES['filename']}-outside.txt\n")
        os.mkfifo(ds / "examples.jsonl")
        os.symlink(h.tmp / f"{CANARIES['filename']}-outside.txt",
                   ds / "references.jsonl")
        rep = validate_dataset(ds)
        steps["hostile_validator"] = {"valid": rep["valid"],
                                      "issues": len(rep["issues"])}
        assert not rep["valid"], rep
    step("validator_hostile_package", validator_hostile)
    s.sync()
    d.v2log.flush()
    return steps


def main(argv):
    out = None
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
    h = Harness(durations=[1.0])
    try:
        try:
            steps = session(h)
            error = None
        except Exception:  # noqa: BLE001
            steps, error = {}, traceback.format_exc()[-800:]
        import localflow.app as app_mod
        hits, records = scan(app_mod.V2_EVENTS_DIR)
    finally:
        h.close()
    leaked = {k: sorted(set(v)) for k, v in hits.items() if v}
    status = "PASS" if not leaked and not error else "FAIL"
    record = {"kind": "xm_event_privacy_census", "status": status,
              "records_scanned": records, "steps": steps,
              "leaks": {k: [list(x) for x in v] for k, v in leaked.items()},
              "error": X.strict(error) if error else None,
              "canary_kinds": sorted(CANARIES),
              "code": X.code_stamp("tests/v2/crossmilestone/"
                                   "test_xm_privacy.py")}
    print(f"{status}  records={records} steps={steps}")
    for k, v in leaked.items():
        print(f"  LEAK {k}: {v[:6]}")
    if out:
        pathlib.Path(out).write_text(json.dumps(record, indent=1))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
