"""Cross-milestone remediation suite (the merged three-audit campaign
over 340c566: Audit A XF-AUDIT-*, Audit C CROSS-AUDIT-*/LF-CROSS-F*,
Audit B CROSS-AUDIT-*). MERGED-X01 lives in test_xm_store_families.py.

At least one fail-first regression per merged finding plus positive
controls. Every case crosses the real interface the finding names — the
real coordinator ``_worker``/``_retry_job`` and EvidenceCollector
(``test_lifecycle.Harness``), the real Hub controller headless, the real
M08 InsertionService, the real Store writer — and grades it with an
independent oracle: literal values the witness chose, raw rows, file
bytes, what a scripted worker actually received. Ordering is decided by
latches and the writer hold of ``xm_world``, never by sleeps.

The same file runs on the audited base (copied into a detached base
worktree) and on the repaired tree. A case that needs a surface the
repair adds degrades to the base's nearest path so the base reproduces
the BEHAVIOR, else reports ERROR — never PASS.

Run (AppKit headless, desktop isolated — a private pasteboard):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_remediation.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import traceback
import types

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import (ALPHA, BETA, NEW_FINAL, OLD_RAW, WriterHold,  # noqa: E402
                      caller_timeout, one, rows)

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle",
          ROOT / "tests" / "v2" / "insertion"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import FakeSupervisor, Harness  # noqa: E402
from m09_world import MainQueue  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2.curation import evidence as ev  # noqa: E402
from localflow.v2.history_queries import (HistoryQueryService,  # noqa: E402
                                          final_text)
from localflow.v2.profile import ProfileService  # noqa: E402
from localflow.v2.supervisor import WorkerFailure  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402

CASES = []


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# =============================================================================
# the real coordinator, scripted worker replies
# =============================================================================

class Scripted(FakeSupervisor):
    """A worker whose ASR text is chosen per (job, attempt) and whose
    cleanup can fail after ASR for chosen attempts. Records the exact
    text cleanup RECEIVED (the independent input oracle)."""

    def __init__(self, asr=None, fail_clean=()):
        super().__init__()
        self.asr = asr or (lambda job_id, attempt: f"raw {attempt}")
        self.fail_clean = set(fail_clean)
        self.clean_inputs = []

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        out = super().transcribe(job_id=job_id, attempt=attempt,
                                 audio_name=audio_name,
                                 sample_rate=sample_rate)
        out["text"] = self.asr(job_id, attempt)
        return out

    def clean(self, *, job_id, attempt, raw_text, **ctx):
        self.calls.append("clean")
        self.clean_inputs.append((job_id, attempt, raw_text))
        if attempt in self.fail_clean:
            raise WorkerFailure("scripted_cleanup_fault", stage="clean",
                                fatal=False, attempt=attempt, generation=1)
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
                "text": raw_text.upper(),
                "observations": [{"kind": "cleanup", "input": raw_text,
                                  "system_prompt": "SYS",
                                  "examples_count": 0,
                                  "prompt": f"<prompt {job_id}>\n{raw_text}",
                                  "max_tokens": 64,
                                  "output": raw_text.upper()}]}


def dictate(h):
    """One capture through the REAL hotkey -> _worker -> main-thread
    finish path. Returns the job id."""
    h.press()
    h.release()
    job = h.d._active_jobs[-1] if h.d._active_jobs else None
    fn, a = h.run_coordinator()
    fn(*a)
    return (job or a[1])["job_id"]


def retry(h, info):
    out = h.d._retry_job(dict(info))
    assert out is None or out.get("outcome") in (None, "requeued",
                                                 "queued"), out
    fn, a = h.run_coordinator()
    fn(*a)


def examples_of(store, job_id):
    return rows(store, "SELECT example_id FROM training_examples WHERE"
                " job_id=? ORDER BY rowid", (job_id,))


def envelope(store, example_id):
    return json.loads(one(store, "SELECT r.envelope_json FROM"
                          " training_examples e JOIN training_revisions r"
                          " ON r.revision_id=e.latest_revision_id WHERE"
                          " e.example_id=?", (example_id,))[0])


# =============================================================================
# MERGED-X02 — Recovery Copy Last Raw vs a pending M08 payload
# =============================================================================

def _pending_payload_service(store):
    """The REAL M08 InsertionService over the process's general
    pasteboard (private under run_isolated) — the board the legacy
    ``copy_text`` also writes — with the M08 synthetic world's host and
    a keyboard that drops the paste: the posted, unverified payload is
    kept for its late consumer (readback_pending)."""
    from m08_world import standard_world
    from test_m08_remediation import job as m08_job, snap
    from localflow.v2.insertion.hosts import SystemPasteboard
    from localflow.v2.insertion.service import InsertionService
    w, _pb, kb = standard_world(text_f1="abc", sel_f1=(3, 3))
    for fid in ("F1", "FB"):
        w.fields[fid].settable = False  # the clipboard method
    svc = InsertionService(host=w, pasteboard=SystemPasteboard(),
                           keyboard=kb, store=store,
                           emit=lambda *a, **k: None,
                           restore_clipboard=True,
                           observation_window_sec=0.0, settle_sec=0.1)
    kb.mode = "drop"
    done = threading.Event()
    box = {}
    svc.submit(NEW_FINAL, m08_job("job-pending", snap(w)),
               lambda r: (box.setdefault("r", r), done.set()))
    assert done.wait(10), "insertion never finished"
    return svc, box["r"]


def _board():
    from AppKit import NSPasteboard, NSPasteboardTypeString
    pb = NSPasteboard.generalPasteboard()
    return pb.changeCount(), pb.stringForType_(NSPasteboardTypeString)


@case("MERGED-X02 (XF-AUDIT-01, B CROSS-AUDIT-04)")
def x02_recovery_copy_never_replaces_a_pending_payload():
    h = Harness(durations=[1.0])
    try:
        svc, r = _pending_payload_service(h.d.store)
        assert r.reason_code == "readback_pending", r.reason_code
        assert svc.clipboard_payload_pending, "fixture: nothing pending"
        gen0, text0 = _board()
        assert text0 == NEW_FINAL, f"fixture: board holds {text0!r}"
        job, _fam = h.d.store.create_job(state="failed_recoverable")
        h.d._insertion = svc
        h.d._last_failed = {"job_id": job, "raw": OLD_RAW, "wav": None,
                            "attempt": 1}
        h.d.copyLastRaw_(None)  # the Recovery menu action itself
        gen1, text1 = _board()
        assert (gen1, text1) == (gen0, text0), (
            "Copy Last Raw replaced the payload reserved for a pending"
            f" insertion: board {text0!r}@{gen0} -> {text1!r}@{gen1}")
        assert svc.clipboard_payload_pending
    finally:
        h.close()


@case("MERGED-X02 control", kind="control")
def c_recovery_copy_publishes_when_nothing_is_pending():
    h = Harness(durations=[1.0])
    try:
        job, _fam = h.d.store.create_job(state="failed_recoverable")
        h.d._last_failed = {"job_id": job, "raw": OLD_RAW, "wav": None,
                            "attempt": 1}
        h.d.copyLastRaw_(None)
        assert _board()[1] == OLD_RAW, _board()
    finally:
        h.close()


# =============================================================================
# MERGED-X05 — failed normalized-input retention vs model_task_complete
# =============================================================================

NORM_RAW = "twelve percent of the orders shipped"


def _cleanup_record(h, fail_role=None, raw=NORM_RAW):
    """Dictate through the real coordinator with collection on; when
    ``fail_role`` is set the store refuses exactly that artifact write
    (the collector's retention step), nothing else. Returns (what
    cleanup actually received, the qualification, the envelope)."""
    h.d.consent.set("enabled")
    sup = Scripted(asr=lambda j, a: raw)
    h.d.supervisor = sup
    store = h.d.store
    real = store.write_text_artifact
    fired = {"n": 0}

    def write(*a, **kw):
        if fail_role is not None and kw.get("role") == fail_role:
            fired["n"] += 1
            raise OSError("synthetic retention failure")
        return real(*a, **kw)
    store.write_text_artifact = write
    try:
        job = dictate(h)
    finally:
        store.write_text_artifact = real
    if fail_role is not None:
        assert fired["n"] == 1, f"retention fault reached {fired['n']}x"
    received = [t for j, _a, t in sup.clean_inputs if j == job]
    assert len(received) == 1, sup.clean_inputs
    (ex,), = examples_of(store, job)
    TrainingDataService(store).mark_intended(ex, True)
    env = envelope(store, ex)
    q = store.submit(lambda c: ev.cleanup_qualification_in(c, ex, env))
    return received[0], q, env


@case("MERGED-X05 (XF-AUDIT-04)")
def x05_failed_normalized_retention_is_never_a_complete_task():
    h = Harness(durations=[1.0])
    try:
        received, q, env = _cleanup_record(h, fail_role="normalized_text")
        assert received != NORM_RAW, (
            f"fixture: normalization did not change the input: {received!r}")
        assert (env.get("missing_reasons") or {}).get("normalization") \
            == "retention_write_failed", env.get("missing_reasons")
        if q.get("eligible"):
            assert q["input_text"] == received, (
                "the cleanup_supervised record binds input the cleanup"
                f" model never received: exported {q['input_text']!r},"
                f" actual {received!r} (tier {q.get('tier')})")
    finally:
        h.close()


@case("MERGED-X05 control", kind="control")
def c_retained_changed_normalization_exports_the_exact_input():
    h = Harness(durations=[1.0])
    try:
        received, q, _env = _cleanup_record(h)
        assert received != NORM_RAW, "fixture: nothing normalized"
        assert q.get("eligible") and q["input_text"] == received \
            and q["tier"] == "model_task_complete", q
    finally:
        h.close()


@case("MERGED-X05 control", kind="control")
def c_unchanged_normalization_keeps_raw_input_complete():
    h = Harness(durations=[1.0])
    try:
        received, q, _env = _cleanup_record(h, raw="plain words only here")
        assert received == "plain words only here", received
        assert q.get("eligible") and q["input_text"] == received \
            and q["tier"] == "model_task_complete", q
    finally:
        h.close()


@case("MERGED-X05 control", kind="control")
def c_ledger_failure_with_unchanged_text_keeps_raw_input():
    h = Harness(durations=[1.0])
    try:
        received, q, env = _cleanup_record(
            h, fail_role="normalization_ledger", raw="plain words only here")
        assert received == "plain words only here", received
        assert (env.get("missing_reasons") or {}).get("normalization") \
            == "retention_write_failed", env.get("missing_reasons")
        assert q.get("eligible") and q["input_text"] == received \
            and q["tier"] == "model_task_complete", q
    finally:
        h.close()


@case("MERGED-X05 control", kind="control")
def c_ledger_failure_after_retained_text_exports_normalized_input():
    h = Harness(durations=[1.0])
    try:
        received, q, _env = _cleanup_record(
            h, fail_role="normalization_ledger")
        assert received != NORM_RAW, "fixture: nothing normalized"
        assert q.get("eligible") and q["input_text"] == received, q
    finally:
        h.close()


# =============================================================================
# MERGED-X06 — History after a collection-off retry
# =============================================================================

def _collection_off_retry(h):
    """Attempt 1 with collection ON transcribes ALPHA and fails in
    cleanup (a legitimate partial manifest); collection is then turned
    off and the SAME job is retried: attempt 2 transcribes BETA and
    succeeds, writing its History artifacts."""
    h.d.consent.set("enabled")
    h.d.cfg["log_transcripts"] = True
    sup = Scripted(asr=lambda j, a: ALPHA if a == 1 else BETA,
                   fail_clean={1})
    h.d.supervisor = sup
    job = dictate(h)
    assert h.job_state(job) == "failed_recoverable", h.job_state(job)
    info = dict(h.d._last_failed)
    h.d.consent.set("disabled")
    retry(h, info)
    return job, sup


def attempt_final(sup, job, attempt):
    """The final the scripted cleanup produced for (job, attempt): the
    upper-cased text it RECEIVED (normalization ran before it)."""
    got = [t for j, a, t in sup.clean_inputs if j == job and a == attempt]
    assert len(got) == 1, sup.clean_inputs
    return got[0].upper()


@case("MERGED-X06 (B CROSS-AUDIT-01)")
def x06_history_resolves_the_current_attempt_after_collection_off_retry():
    h = Harness(durations=[1.0])
    try:
        job, sup = _collection_off_retry(h)
        expected = attempt_final(sup, job, 2)
        store = h.d.store
        attempt = one(store, "SELECT attempt FROM jobs WHERE job_id=?",
                      (job,))[0]
        assert attempt == 2, f"fixture: job attempt {attempt}"
        detail = HistoryQueryService(store).job_detail(job)
        shown = final_text(detail)
        lineage = {s["stage"]: (s.get("artifact") or {}).get("text")
                   for s in detail["lineage"]}
        assert ALPHA not in json.dumps(lineage), (
            "History shows attempt 1's text as the current job:"
            f" lineage_attempt={detail.get('lineage_attempt')}"
            f" source={lineage.get('source')!r}")
        assert detail.get("lineage_attempt") == attempt, detail.get(
            "lineage_attempt")
        assert shown == expected, (
            f"current final not resolved: {shown!r} (lineage source"
            f" {detail.get('lineage_source')})")
        # Downstream: the rendered row's Copy and Save to Scratchpad.
        out = h.d.hubSaveHistoryRow("job", job)
        assert out.get("outcome") == "copied", out
        note = one(store, "SELECT r.content_text FROM notes n JOIN"
                   " note_revisions r ON r.revision_id ="
                   " n.current_revision_id WHERE n.note_id=?",
                   (out["note_id"],))[0]
        assert note == expected, (note, expected)
        # Teach admission against the rendered current final (the Hub
        # passes the artifact it showed).
        cleaned = next(s for s in detail["lineage"]
                       if s["stage"] == "cleaned")["artifact"]
        fixed = expected.replace("WORDS", "WORLDS")
        try:
            got = h.d._learning.teach_correction(
                job, fixed,
                expected_final_artifact_id=cleaned["artifact_id"])
            refusal = None
        except ValueError as e:
            got, refusal = None, str(e)
        assert refusal not in ("stale_final", "no_retained_final_text"), (
            f"Teach refused the rendered current final: {refusal}")
        if got:
            ex = one(store, "SELECT example_id FROM learning_candidates"
                     " WHERE candidate_id=?", (got["candidate_id"],))[0]
            assert ex is None or envelope(store, ex).get("attempt") == 2, \
                "the teach was bound to attempt 1's evidence"
    finally:
        h.close()


@case("MERGED-X06 control", kind="control")
def c_collection_on_retry_resolves_the_new_manifest():
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        sup = Scripted(asr=lambda j, a: ALPHA if a == 1 else BETA,
                       fail_clean={1})
        h.d.supervisor = sup
        job = dictate(h)
        retry(h, dict(h.d._last_failed))
        detail = HistoryQueryService(h.d.store).job_detail(job)
        assert detail["lineage_attempt"] == 2, detail["lineage_attempt"]
        assert final_text(detail) == attempt_final(sup, job, 2), \
            final_text(detail)
    finally:
        h.close()


# =============================================================================
# MERGED-X07 — Your Voice counts logical captures, not attempts
# =============================================================================

def _words(tag, n=210):
    return " ".join(f"{tag}{i % 97}w{i}" for i in range(n))


@case("MERGED-X07 (C CROSS-AUDIT-03, B CROSS-AUDIT-02)")
def x07_retries_never_manufacture_dictations_or_words():
    h = Harness(durations=[1.0] * 10)
    try:
        h.d.consent.set("enabled")
        sup = Scripted(asr=lambda j, a: _words(f"a{a}{j[-6:]}"),
                       fail_clean={1})
        h.d.supervisor = sup
        jobs = []
        for _ in range(5):
            job = dictate(h)
            retry(h, dict(h.d._last_failed))
            jobs.append(job)
        store = h.d.store
        per_job = {j: len(examples_of(store, j)) for j in jobs}
        assert all(n == 2 for n in per_job.values()), (
            f"fixture: expected two eligible attempts per job {per_job}")
        # M13's one-logical-job identity is the compatibility oracle.
        facts = {j: one(store, "SELECT COUNT(*) FROM usage_facts WHERE"
                        " job_id=?", (j,))[0] for j in jobs}
        assert set(facts.values()) == {1}, facts
        snap = ProfileService(store).compute()
        m = snap["measured"]
        assert m["eligible_examples"] <= 5 and m["eligible_words"] <= \
            5 * 210, (
            f"5 logical captures counted as {m['eligible_examples']}"
            f" dictations / {m['eligible_words']} words")
        assert not snap["interpretive_available"], (
            "retries crossed the 10-dictation / 2,000-word interpretation"
            " floor with only 5 captures")
    finally:
        h.close()


@case("MERGED-X07 control", kind="control")
def c_ten_independent_captures_reach_the_floor():
    h = Harness(durations=[1.0] * 10)
    try:
        h.d.consent.set("enabled")
        h.d.supervisor = Scripted(asr=lambda j, a: _words(f"c{j[-6:]}"))
        for _ in range(10):
            dictate(h)
        snap = ProfileService(h.d.store).compute()
        assert snap["measured"]["eligible_examples"] == 10, snap["measured"]
        assert snap["interpretive_available"], snap["measured"]
    finally:
        h.close()


# =============================================================================
# Hub helpers (the real controller, headless)
# =============================================================================

def make_hub(h):
    from localflow.v2.training_data import TrainingDataService as TDS
    from localflow.v2.ui import HubController, ReplayService
    d = h.d
    return HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TDS(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d, "replay": ReplayService(
            sound_factory=lambda b: None),
        "capabilities": d._capability_manifest,
        "styles_service": d._styles, "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
        "insights_service": d._insights,
        "learning_service": d._learning, "review_service": d._review,
        "sampling_service": d._sampling, "splits_service": d._splits,
        "profile_service": d._profile, "export_service": d._exporter,
        "transforms_store": d._tf_store})


def open_view(hub, mq, view):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index(view))
    hub.state.select_view(view)
    assert mq.drain(hub.state, 60)


SELECTION_ERRORS = []


def select_row(hub, mq, table_name, key, value):
    """Select a rendered row the way AppKit delivers it: an exception
    raised by the delegate callback is reported (recorded here) and the
    event loop carries on with whatever the callback had already done."""
    import Foundation
    rows = hub._rendered_rows.get(table_name) or []
    idx = next(i for i, r in enumerate(rows) if r.get(key) == value)
    # The table notifies its delegate synchronously from the selection
    # call itself; the explicit notification repeats what a click does.
    for deliver in (
            lambda: getattr(hub, table_name)
            .selectRowIndexes_byExtendingSelection_(
                Foundation.NSIndexSet.indexSetWithIndex_(idx), False),
            lambda: hub.tableViewSelectionDidChange_(
                Foundation.NSNotification.notificationWithName_object_(
                    "x", getattr(hub, table_name)))):
        try:
            deliver()
        except Exception as e:  # noqa: BLE001 — AppKit reports, continues
            SELECTION_ERRORS.append(f"{type(e).__name__}: {e}")
    assert mq.drain(hub.state, 60)


def transform_row(store, tid):
    return one(store, "SELECT name, prompt, auto_apply, enabled, revision"
               " FROM transforms WHERE transform_id=?", (tid,))


def transforms_named(store, name):
    return rows(store, "SELECT transform_id FROM transforms WHERE name=?",
                (name,))


# =============================================================================
# MERGED-X03 — one transform revision, one definition
# =============================================================================

@case("MERGED-X03 (XF-AUDIT-02, C CROSS-AUDIT-02)")
def x03_interleaved_updates_preserve_the_committed_definition():
    """Two real ``update_transform`` calls: A (rename) is held right
    before it submits its mutation — after any reading it does outside
    the writer — while B (new instruction) commits; then A commits. The
    live row and the preserved revision it names must be the same
    definition, and an accepted candidate at that revision must export
    the definition that is live."""
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        tfs = h.d._tf_store
        t = tfs.add_transform(name="N0", mode="custom", prompt="P0")
        gate = X.Latch("A_before_mutation")
        real = store.submit

        def submit(fn, wait=True, timeout=15.0):
            inner = getattr(fn, "__qualname__", "")
            if threading.current_thread().name == "updater-A" \
                    and "update_transform" in inner and gate.hits == 0:
                gate.hit()
            return real(fn, wait=wait, timeout=timeout)
        store.submit = submit
        errs = []

        def updater_a():
            try:
                tfs.update_transform(t.transform_id, name="N1")
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        a = threading.Thread(target=updater_a, name="updater-A")
        try:
            a.start()
            assert gate.reached.wait(10), "A never reached its mutation"
            tfs.update_transform(t.transform_id, prompt="P1")  # B commits
            gate.release()
            a.join(10)
        finally:
            gate.release()
            del store.submit
        live = transform_row(store, t.transform_id)
        revision = live[4]
        preserved = json.loads(one(store, "SELECT definition_json FROM"
                                   " transform_revisions WHERE"
                                   " transform_id=? AND revision=?",
                                   (t.transform_id, revision))[0])
        assert (preserved["name"], preserved["prompt"]) == live[:2], (
            f"revision {revision} names two definitions: live"
            f" {live[:2]}, preserved {(preserved['name'], preserved['prompt'])}"
            + (f" (A raised {errs[0]!r})" if errs else ""))
        # The exporter's reader (transform_target_in) resolves a task's
        # definition from this preserved row.
        assert preserved["prompt"] == live[1]
    finally:
        h.close()


@case("MERGED-X03 control", kind="control")
def c_sequential_updates_each_preserve_their_definition():
    h = Harness(durations=[1.0])
    try:
        tfs = h.d._tf_store
        t = tfs.add_transform(name="N0", mode="custom", prompt="P0")
        tfs.update_transform(t.transform_id, name="N1")
        tfs.update_transform(t.transform_id, prompt="P1")
        revs = {r["revision"]: (r["definition"]["name"],
                                r["definition"]["prompt"])
                for r in tfs.revisions_of(t.transform_id)}
        assert revs == {1: ("N0", "P0"), 2: ("N1", "P0"),
                        3: ("N1", "P1")}, revs
    finally:
        h.close()


# =============================================================================
# MERGED-X04 — a stale transform form never re-enables auto-apply
# =============================================================================

def _auto_transform(h, mq, hub):
    tfs = h.d._tf_store
    t = tfs.add_transform(name="Opt-out witness", mode="custom",
                          prompt="Rewrite formally.", auto_apply=True)
    open_view(hub, mq, "transforms")
    select_row(hub, mq, "transforms_table", "transform_id", t.transform_id)
    assert hub.tf_auto.state() == 1, "fixture: form not rendered with auto"
    return t


@case("MERGED-X04 (XF-AUDIT-03, C CROSS-AUDIT-05)")
def x04_stale_form_never_reverses_a_newer_opt_out():
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            t = _auto_transform(h, mq, hub)
            # Another supported write opts out while the form is open.
            h.d._tf_store.update_transform(t.transform_id,
                                           auto_apply=False)
            hub.tf_name.setStringValue_("Opt-out witness renamed")
            hub.transformsUpdate_(None)
            mq.drain(hub.state, 60)
            row = transform_row(h.d.store, t.transform_id)
            assert row[2] == 0, (
                "Update from the stale form re-enabled auto-apply (the"
                f" user edited only the name): {row}; status"
                f" {hub.transforms_status.stringValue()!r}")
            if row[0] != "Opt-out witness renamed":
                # A refused stale form keeps the user's unsaved edit.
                assert hub.tf_name.stringValue() == \
                    "Opt-out witness renamed", "unsaved edit lost"
    finally:
        h.close()


@case("MERGED-X04 (single-Hub path through an unknown Update)")
def x04_unknown_update_then_stale_refill_never_reenables_auto():
    """The production-reachable single-Hub path: the user unchecks
    auto-apply and presses Update while the store is busy — the caller
    times out, the op still commits the opt-out. Re-selecting the row
    and editing only the name must not send auto-apply back."""
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        with MainQueue() as mq:
            hub = make_hub(h)
            t = _auto_transform(h, mq, hub)
            hub.tf_auto.setState_(0)
            with X.hold_at(store, "update_transform") as held:
                hub.transformsUpdate_(None)
                assert held.reached, "fixture: mutation never admitted"
            store.sync()
            assert transform_row(store, t.transform_id)[2] == 0, \
                "fixture: the opt-out did not commit"
            mq.drain(hub.state, 60)
            select_row(hub, mq, "transforms_table", "transform_id",
                       t.transform_id)
            hub.tf_name.setStringValue_("Renamed after busy store")
            hub.transformsUpdate_(None)
            mq.drain(hub.state, 60)
            row = transform_row(store, t.transform_id)
            assert row[2] == 0, (
                "the committed opt-out was reversed by a form refilled"
                f" from the stale list: {row}")
    finally:
        h.close()


@case("MERGED-X04 control", kind="control")
def c_fresh_form_update_changes_only_the_edited_field():
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            t = _auto_transform(h, mq, hub)
            hub.tf_name.setStringValue_("Fresh rename")
            hub.transformsUpdate_(None)
            mq.drain(hub.state, 60)
            row = transform_row(h.d.store, t.transform_id)
            assert row[:3] == ("Fresh rename", "Rewrite formally.", 1), row
    finally:
        h.close()


@case("LOCAL-XM-01 (GATE-G07 transform prompt editability)")
def local01_selected_transform_fills_its_own_instruction():
    """Found while reproducing MERGED-X04: selecting a Transforms row must
    render THAT row's instruction, so a name-only Update keeps it."""
    h = Harness(durations=[1.0])
    try:
        tfs = h.d._tf_store
        a = tfs.add_transform(name="Prompt witness A", mode="custom",
                              prompt="INSTRUCTION ALPHA")
        b = tfs.add_transform(name="Prompt witness B", mode="custom",
                              prompt="INSTRUCTION BETA")
        del SELECTION_ERRORS[:]
        with MainQueue() as mq:
            hub = make_hub(h)
            open_view(hub, mq, "transforms")
            select_row(hub, mq, "transforms_table", "transform_id",
                       a.transform_id)
            select_row(hub, mq, "transforms_table", "transform_id",
                       b.transform_id)
            shown = hub.tf_prompt.string()
            hub.tf_name.setStringValue_("Prompt witness B renamed")
            hub.transformsUpdate_(None)
            mq.drain(hub.state, 60)
        prompt = transform_row(h.d.store, b.transform_id)[1]
        assert prompt == "INSTRUCTION BETA", (
            f"a name-only Update replaced B's instruction with {prompt!r}"
            f" (the form showed {shown!r}; selection errors:"
            f" {SELECTION_ERRORS[:1]})")
        assert not SELECTION_ERRORS, SELECTION_ERRORS[:1]
    finally:
        h.close()


# =============================================================================
# MERGED-X08 — an admitted Add timeout is unknown, and a retry reconciles
# =============================================================================

@case("MERGED-X08 (XF-AUDIT-05, C CROSS-AUDIT-06)")
def x08_admitted_add_timeout_is_unknown_and_one_transform_results():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        with MainQueue() as mq:
            hub = make_hub(h)
            open_view(hub, mq, "transforms")
            hub.tf_name.setStringValue_("Add witness")
            hub.tf_prompt.setString_("Summarize in one line.")
            hub.tf_shortcut.setStringValue_("")
            with WriterHold(store) as hold, caller_timeout(store):
                hub.transformsAdd_(None)
                status = hub.transforms_status.stringValue()
                hold.release()
            store.sync()
            mq.drain(hub.state, 60)
            hub.transformsAdd_(None)  # the user repeats the same Add
            mq.drain(hub.state, 60)
            n = len(transforms_named(store, "Add witness"))
            assert "not saved" not in status.lower(), (
                f"an admitted timeout was reported as not saved: {status!r}")
            assert n == 1, f"one logical Add made {n} transforms"
    finally:
        h.close()


@case("MERGED-X08 (sibling: Enable/Disable)")
def x08_admitted_toggle_timeout_is_not_reported_as_failed():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        with MainQueue() as mq:
            hub = make_hub(h)
            t = h.d._tf_store.add_transform(name="Toggle witness",
                                            mode="custom", prompt="x")
            open_view(hub, mq, "transforms")
            select_row(hub, mq, "transforms_table", "transform_id",
                       t.transform_id)
            with X.hold_at(store, "update_transform") as held:
                hub.transformsToggle_(None)
                status = hub.transforms_status.stringValue()
                assert held.reached, "fixture: mutation never admitted"
            store.sync()
            assert transform_row(store, t.transform_id)[3] == 0, \
                "fixture: the toggle did not commit"
            assert "not toggled" not in status.lower(), (
                f"an admitted toggle was reported as failed: {status!r}")
    finally:
        h.close()


@case("MERGED-X08 control", kind="control")
def c_refused_add_saves_nothing_and_a_fixed_form_adds_once():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        with MainQueue() as mq:
            hub = make_hub(h)
            h.d._tf_store.add_transform(name="Holder", mode="custom",
                                        prompt="x", shortcut="k")
            open_view(hub, mq, "transforms")
            hub.tf_name.setStringValue_("Refused add")
            hub.tf_prompt.setString_("x")
            hub.tf_shortcut.setStringValue_("k")  # collides: refused
            hub.transformsAdd_(None)
            assert not transforms_named(store, "Refused add")
            hub.tf_shortcut.setStringValue_("")
            hub.transformsAdd_(None)
            mq.drain(hub.state, 60)
            assert len(transforms_named(store, "Refused add")) == 1
    finally:
        h.close()


# =============================================================================
# MERGED-X09 — Save Transform to Scratchpad keeps the note identity
# =============================================================================

def _transform_result(text):
    from localflow.v2.transforms.engine import TransformResult
    return TransformResult(job=None, output=text, path="applied")


def notes_with(store, text):
    return rows(store, "SELECT n.note_id FROM notes n JOIN note_revisions r"
                " ON r.revision_id = n.current_revision_id WHERE"
                " r.content_text=?", (text,))


@case("MERGED-X09 (XF-AUDIT-06)")
def x09_admitted_save_timeout_then_retry_makes_one_note():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        assert h.d._notes_store is not None, "fixture: Scratchpad off"
        text = "TRANSFORMNOTECANARY saved output"
        result = _transform_result(text)
        defn = types.SimpleNamespace(name="Witness transform")
        with WriterHold(store) as hold, caller_timeout(store):
            h.d.tfSaveToScratchpad(result, defn)
            hold.release()
        store.sync()
        h.d.tfSaveToScratchpad(result, defn)  # the same logical Save
        store.sync()
        got = notes_with(store, text)
        assert len(got) == 1, f"one logical Save made {len(got)} notes"
    finally:
        h.close()


@case("MERGED-X09 control", kind="control")
def c_distinct_saves_make_distinct_notes():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        defn = types.SimpleNamespace(name="Witness transform")
        h.d.tfSaveToScratchpad(_transform_result("first output"), defn)
        h.d.tfSaveToScratchpad(_transform_result("second output"), defn)
        store.sync()
        assert len(notes_with(store, "first output")) == 1
        assert len(notes_with(store, "second output")) == 1
    finally:
        h.close()


# =============================================================================
# MERGED-X10 — History Move reports an unknown source deletion truthfully
# =============================================================================

def _history_job(h):
    h.d.cfg["log_transcripts"] = True
    h.d.supervisor = Scripted(asr=lambda j, a: "move witness words")
    return dictate(h)


@case("MERGED-X10 (XF-AUDIT-07)")
def x10_unknown_source_deletion_is_reported_and_retry_settles():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        job = _history_job(h)
        real = store.delete_everywhere
        held = []

        def hooked(*a, **kw):
            hold = WriterHold(store, "delete_phase")
            hold.__enter__()
            held.append(hold)
            with caller_timeout(store):
                return real(*a, **kw)
        store.delete_everywhere = hooked
        try:
            first = h.d.hubSaveHistoryRow("job", job, move=True)
        finally:
            store.delete_everywhere = real
            for hold in held:
                hold.release()
        store.sync()
        assert held, "fixture: the move never reached its delete phase"
        deleted = one(store, "SELECT 1 FROM job_deletions WHERE job_id=?",
                      (job,)) is not None
        assert deleted, "fixture: the admitted deletion did not commit"
        assert first.get("outcome") != "move_failed_note_copied", (
            "the source deletion was reported as definitely failed while"
            f" it was admitted and later committed: {first}")
        second = h.d.hubSaveHistoryRow("job", job, move=True)
        notes = rows(store, "SELECT note_id FROM notes")
        assert len(notes) == 1, f"retry made {len(notes)} notes"
        assert second.get("outcome") == "moved" and \
            second.get("note_id") == first.get("note_id"), (
            f"retry did not settle the move: {first} then {second}")
    finally:
        h.close()


@case("MERGED-X10 (census: History Copy after create_unknown)")
def x10_unknown_copy_create_then_retry_makes_one_note():
    """The caller census (GATE-G01) found the same caller's CREATE phase
    minting a fresh note id per call: after an admitted create the
    user's repeated Copy must reconcile, not make a second note."""
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        job = _history_job(h)
        with X.hold_at(store, "_append") as held:
            first = h.d.hubSaveHistoryRow("job", job)
            assert held.reached, "fixture: the create was never admitted"
        store.sync()
        assert first.get("outcome") == "create_unknown", first
        second = h.d.hubSaveHistoryRow("job", job)
        store.sync()
        notes = rows(store, "SELECT note_id FROM notes")
        assert len(notes) == 1, (
            f"a repeated Copy after an unknown create made {len(notes)}"
            f" notes: {first} then {second}")
    finally:
        h.close()


@case("MERGED-X10 control", kind="control")
def c_unknown_create_never_deletes_the_source():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        job = _history_job(h)
        real_append = h.d._notes_store._append
        holds = []

        def append(*a, **kw):
            hold = WriterHold(store, "create_phase")
            hold.__enter__()
            holds.append(hold)
            with caller_timeout(store):
                return real_append(*a, **kw)
        h.d._notes_store._append = append
        try:
            out = h.d.hubSaveHistoryRow("job", job, move=True)
        finally:
            del h.d._notes_store._append
            for hold in holds:
                hold.release()
        store.sync()
        assert out.get("outcome") == "create_unknown", out
        assert one(store, "SELECT 1 FROM job_deletions WHERE job_id=?",
                   (job,)) is None, "source deleted after an unknown create"
    finally:
        h.close()


# =============================================================================
# MERGED-X11 — speech-derived technical terms keep their applied spelling
# =============================================================================

def _term_world(h):
    h.d.consent.set("enabled")
    eid = h.d._vocab.add_entry("Orion SDK", [("orion s d k", True)],
                               approved=True)
    h.d.supervisor = Scripted(
        asr=lambda j, a: "we ship the orion s d k release today")
    job = dictate(h)
    (ex,), = examples_of(h.d.store, job)
    env = envelope(h.d.store, ex)
    vocab = (env.get("normalization") or {}).get("vocabulary") or {}
    assert eid in (vocab.get("applied_rule_ids") or []), (
        f"fixture: the rule did not apply: {vocab}")
    return eid


def _terms(store):
    snap = ProfileService(store, min_words=1).compute()
    return [t["term"] for t in snap["measured"]["technical_terms"]]


@case("MERGED-X11 (C CROSS-AUDIT-04, B CROSS-AUDIT-03)")
def x11_renamed_entry_never_relabels_historical_speech():
    h = Harness(durations=[1.0])
    try:
        eid = _term_world(h)
        e = h.d._vocab.entry(eid)
        h.d._vocab.update_entry(eid, expected_revision=e.revision,
                                canonical="Lyra SDK")
        terms = _terms(h.d.store)
        assert "Lyra SDK" not in terms, (
            "speech captured under 'Orion SDK' is now cited as 'Lyra SDK'"
            f" (no new speech): {terms}")
    finally:
        h.close()


@case("MERGED-X11 (missing frozen record)")
def x11_missing_frozen_record_is_unrecorded_never_relabeled():
    h = Harness(durations=[1.0])
    try:
        eid = _term_world(h)
        store = h.d.store
        (aid,), = rows(store, "SELECT artifact_id FROM artifacts WHERE"
                       " role='vocabulary_applied_rules'")
        store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_text=NULL WHERE"
            " artifact_id=?", (aid,)))
        e = h.d._vocab.entry(eid)
        h.d._vocab.update_entry(eid, expected_revision=e.revision,
                                canonical="Lyra SDK")
        snap = ProfileService(store, min_words=1).compute()
        m = snap["measured"]
        names = [t["term"] for t in m["technical_terms"]]
        assert not names and m.get("technical_terms_unrecorded", {}).get(
            "dictations") == 1, (names, m.get("technical_terms_unrecorded"))
    finally:
        h.close()


@case("MERGED-X11 control", kind="control")
def c_disabled_rule_no_longer_counts():
    h = Harness(durations=[1.0])
    try:
        eid = _term_world(h)
        h.d._vocab.set_enabled(eid, False)
        assert _terms(h.d.store) == [], _terms(h.d.store)
    finally:
        h.close()


@case("MERGED-X11 control", kind="control")
def c_unrenamed_entry_cites_its_applied_term():
    h = Harness(durations=[1.0])
    try:
        _term_world(h)
        assert _terms(h.d.store) == ["Orion SDK"], _terms(h.d.store)
    finally:
        h.close()


# =============================================================================
# MERGED-X12 / X13 — Export Validate: result lifetime and the UI thread
# =============================================================================

def _invalid_dataset(root):
    root.mkdir()
    (root / "dataset_manifest.json").write_text('{"not": "a manifest"}')
    (root / "SHA256SUMS.txt").write_text("")
    return root


def _export_tab(h, mq, hub):
    from localflow.v2.ui.state import VIEWS
    hub._select_view_index(VIEWS.index("models"))
    hub.state.select_models_subview("training")
    assert mq.drain(hub.state, 60)
    hub.state.select_training_tab("export")
    assert mq.drain(hub.state, 60)


@case("MERGED-X12 (C CROSS-AUDIT-07, B CROSS-AUDIT-06)")
def x12_older_refresh_never_repaints_over_a_validate_result():
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            _export_tab(h, mq, hub)
            dest = _invalid_dataset(h.tmp / "invalid-ds")
            hub.export_dest.setStringValue_(str(dest))
            # An older refresh: its read is held on the query thread.
            gate = X.Latch("refresh_read")
            svc = hub.state.export_service
            real = svc.last_export

            def last_export():
                gate.hit()
                return real()
            svc.last_export = last_export
            try:
                hub.state.reload_training()
                assert gate.reached.wait(10), "refresh never read"
                hub.exportValidate_(None)
                # Validate completes (in whatever thread it runs).
                deadline = time.monotonic() + 15
                while "valid: False" not in \
                        hub.export_text.string() and \
                        time.monotonic() < deadline:
                    mq.flush()
                    time.sleep(0.01)
                shown = hub.export_text.string()
                assert "valid: False" in shown, (
                    f"fixture: validation never showed: {shown!r}")
                gate.release()
                assert mq.drain(hub.state, 60)
            finally:
                gate.release()
                del svc.last_export
            after = hub.export_text.string()
            assert "valid: False" in after, (
                "the older refresh repainted over the completed Validate"
                f" result: {after[:120]!r}")
    finally:
        h.close()


@case("MERGED-X13 (B CROSS-AUDIT-07)")
def x13_validate_never_runs_filesystem_work_on_the_ui_thread():
    from localflow.v2.curation import export as export_mod
    h = Harness(durations=[1.0])
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            _export_tab(h, mq, hub)
            dest = _invalid_dataset(h.tmp / "invalid-ds")
            hub.export_dest.setStringValue_(str(dest))
            gate = X.Latch("validator_read")
            seen = {}
            real = export_mod.validate_dataset

            def validate(root):
                seen["main"] = threading.current_thread() is \
                    threading.main_thread()
                gate.reached.set()
                gate.release_evt.wait(3)  # the held filesystem read
                return real(root)
            export_mod.validate_dataset = validate
            try:
                t0 = time.monotonic()
                hub.exportValidate_(None)
                ack = time.monotonic() - t0
                gate.release()
                assert mq.drain(hub.state, 60)
            finally:
                export_mod.validate_dataset = real
            assert seen, "fixture: the validator never ran"
            assert not seen["main"], (
                "Export Validate ran the validator's filesystem work on the"
                f" Hub's UI thread (callback held {ack:.2f}s)")
            assert "valid: False" in hub.export_text.string(), \
                hub.export_text.string()[:120]
    finally:
        h.close()


# =============================================================================
# MERGED-X15 — Undo Approval is a functional Hub action
# =============================================================================

TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"


@case("MERGED-X15 (C DESIGN-01, B CROSS-AUDIT-09)")
def x15_hub_offers_undo_approval_for_the_rendered_candidate():
    h = Harness(durations=[1.0])
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        # A producer-shaped dictation (the M14 world's taught() shape).
        job, fam = store.create_job()
        raw = store.write_text_artifact(
            job_id=job, stage="asr", role="raw_transcript", text=TEACH_RAW,
            retention_class="training")
        applied = store.write_text_artifact(
            job_id=job, stage="cleanup", role="applied_output",
            text=TEACH_RAW, retention_class="training",
            parent_artifact_id=raw, meta={"cleanup_path": "model"})
        for aid in (raw, applied):
            store.grant_lease(aid, "training", days=30)
        ex = store.upsert_example(job_id=job, family_id=fam,
                                  consent_revision_id=
                                  store.current_consent_id())
        store.append_revision(ex, {
            "example_id": ex, "job_id": job, "family_id": fam,
            "origin": "live_capture", "attempt": 1,
            "artifact_ids": {"source_text": raw,
                             "applied_output": applied},
            "outcome": {}, "annotations": [], "missing_reasons": {}})
        cid = h.d._learning.teach_correction(job, TEACH_FIX)["candidate_id"]
        out = h.d._learning.approve(cid)
        eid = out["entry_id"]
        with MainQueue() as mq:
            hub = make_hub(h)
            from localflow.v2.ui.state import VIEWS
            hub._select_view_index(VIEWS.index("models"))
            hub.state.select_models_subview("training")
            assert mq.drain(hub.state, 60)
            hub.state.select_training_tab("review")
            assert mq.drain(hub.state, 60)
            action = getattr(hub, "reviewUndoApproval_", None)
            assert action is not None, (
                "the Hub has no Undo approval action for an approved"
                " learned rule (service undo is unreachable)")
            hub._review_select_candidate(cid) \
                if hasattr(hub, "_review_select_candidate") else None
            action(None)
            mq.drain(hub.state, 60)
        status = one(store, "SELECT status FROM learning_candidates WHERE"
                     " candidate_id=?", (cid,))[0]
        enabled = one(store, "SELECT enabled FROM vocabulary_entries WHERE"
                      " entry_id=?", (eid,))[0]
        assert (status, enabled) == ("pending", 0), (status, enabled)
    finally:
        h.close()


@case("MERGED-X15 control", kind="control")
def c_service_undo_reverses_exactly_and_keeps_user_edits():
    """First prove the existing service Undo stays safe: it reverses its
    own created entry, and refuses once the user edited that entry."""
    with X.M.MWorld() as w:
        j = w.job(TEACH_RAW)
        cid = w.learning.teach_correction(j["job_id"],
                                          TEACH_FIX)["candidate_id"]
        eid = w.learning.approve(cid)["entry_id"]
        assert w.learning.undo_approval(cid) == "undone"
        assert w.one("SELECT enabled FROM vocabulary_entries WHERE"
                     " entry_id=?", (eid,))[0] == 0
        j2 = w.job("please restart the servr today")
        cid2 = w.learning.teach_correction(
            j2["job_id"], "please restart the server today")["candidate_id"]
        eid2 = w.learning.approve(cid2)["entry_id"]
        e = w.vocab.entry(eid2)
        w.vocab.update_entry(eid2, expected_revision=e.revision,
                             canonical="module-user-edit")
        try:
            w.learning.undo_approval(cid2)
            refused = False
        except ValueError as ex:
            refused = "user_modified" in str(ex)
        assert refused, "undo overwrote a later user edit"
        assert w.one("SELECT canonical, enabled FROM vocabulary_entries"
                     " WHERE entry_id=?", (eid2,)) == ("module-user-edit", 1)


# =============================================================================
# MERGED-X14 — a crash after the export rename, before the SQLite commit
# =============================================================================

def _crash_after_rename(td, export_id):
    """Run the owned child to the post-rename barrier, SIGKILL it, and
    reopen a COPY of its store (with the hot journal SQLite rolls back).
    Returns (reopened store, destination, workdir)."""
    import os
    import shutil
    import signal
    import subprocess
    from localflow.v2 import store as store_mod
    work = pathlib.Path(td)
    child = subprocess.Popen(
        [sys.executable, str(HERE.parent / "xm_export_crash_child.py"),
         str(work), export_id], stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    marker = work / "renamed.json"
    deadline = time.monotonic() + 120
    while not marker.exists() and child.poll() is None \
            and time.monotonic() < deadline:
        time.sleep(0.05)  # waiting for the child's own barrier file
    if not marker.exists():
        child.kill()
        err = child.stderr.read().decode(errors="replace")[-600:]
        raise AssertionError(f"child never reached the barrier: {err}")
    info = json.loads(marker.read_text())
    os.kill(child.pid, signal.SIGKILL)
    child.wait(30)
    copy = work / "reopened"
    copy.mkdir()
    for suffix in ("", "-journal", "-wal", "-shm"):
        src = pathlib.Path(info["db"] + suffix)
        if src.exists():
            shutil.copy2(src, copy / ("v2.db" + suffix))
    shutil.copytree(info["arts"], copy / "arts")
    store = store_mod.Store(copy / "v2.db", artifacts_dir=copy / "arts",
                            backup_dir=copy / "bk")
    return store, work / "dataset", work


def _validate_offline(dest):
    import subprocess
    p = subprocess.run([sys.executable,
                        str(ROOT / "scripts" / "v2" / "validate_dataset.py"),
                        str(dest)], capture_output=True, text=True,
                       cwd=str(dest.parent))
    return p.returncode == 0, p.stdout


@case("MERGED-X14 (C DESIGN-02, B CROSS-AUDIT-08)")
def x14_post_rename_crash_is_recognized_not_lost_or_relabeled():
    import tempfile
    from localflow.v2.curation.export import DatasetExporter, ExportError
    export_id = "export-crash-x14"
    with tempfile.TemporaryDirectory() as td:
        store, dest, work = _crash_after_rename(td, export_id)
        try:
            ok, out = _validate_offline(dest)
            manifest = json.loads((dest / "dataset_manifest.json")
                                  .read_text())
            assert ok and manifest.get("export_id") == export_id, (
                f"fixture: the orphan package is not {export_id}: {out}")
            aside = [p.name for p in dest.parent.iterdir()
                     if p.name.startswith(".dataset.replaced-")]
            assert aside, "fixture: the prior export was not moved aside"
            ex = DatasetExporter(store)
            try:
                ex.build(dest, task_views=("asr_supervised",),
                         export_id=export_id)
                retry = "built"
            except ExportError as e:
                retry = f"refused: {e}"
            except Exception as e:  # noqa: BLE001
                retry = f"{type(e).__name__}: {e}"
            state = one(store, "SELECT state FROM export_manifests WHERE"
                        " export_id=?", (export_id,))
            # Nothing valid was deleted or overwritten by the retry.
            prior_kept = any(
                (dest.parent / n / "dataset_manifest.json").exists()
                for n in aside)
            still = json.loads((dest / "dataset_manifest.json")
                               .read_text()).get("export_id") \
                if dest.exists() else None
            assert prior_kept, "the retry removed the moved-aside prior export"
            assert state is not None and state[0] not in (
                "failed", "complete"), (
                "after the crash the store records the published package"
                f" of {export_id} as {state[0] if state else 'absent'}"
                f" (retry: {retry}); destination holds {still}")
            assert still == export_id, (
                f"the recognized package was replaced by {still}")
        finally:
            store.close()


# =============================================================================
# MERGED-X16 / X17 — the current-state projection and the M07 runbook
# =============================================================================

@case("MERGED-X16 (XF-AUDIT-08, C CROSS-AUDIT-08, B CROSS-AUDIT-10)")
def x16_status_separates_current_state_from_historical_record():
    from localflow.v2 import store as store_mod
    status = json.loads((ROOT / "docs/v2/STATUS.json").read_text())
    current = status.get("current_state")
    assert isinstance(current, dict), (
        "STATUS.json has no explicit current-state projection; its"
        " implementation-era narrative (\"Store schema v10\", 54/50.3 ms"
        " waits, one benchmark run) reads as current")
    assert current.get("store_schema_version") == \
        max(store_mod._MIGRATIONS), current.get("store_schema_version")
    for ref in current.get("evidence") or []:
        assert (ROOT / ref).exists(), f"current evidence missing: {ref}"
    hist = status.get("historical_implementation") or {}
    assert "Store schema v10" in json.dumps(hist) or \
        "Store schema v10" not in status.get("status_reason", ""), (
        "the v10 implementation claim is neither labeled historical nor"
        " current")


@case("MERGED-X17 (B CROSS-AUDIT-11)")
def x17_m07_obligations_have_stable_runbook_ownership():
    import re
    html = (ROOT / "docs/v2/VERIFICATION.html").read_text()
    m = re.search(r'<section class="milestone" id="M07".*?</section>',
                  html, re.S)
    assert m, "no M07 section"
    sec = m.group(0)
    checks = re.findall(r'<article class="check[^"]*" id="(M07-V\d{3})"',
                        sec)
    assert checks, (
        "the M07 runbook section is an empty placeholder while M07's"
        " long-prompt trial and adjudicated real-text stratum are still"
        " open")
    for oblig in ("long-prompt", "real-text"):
        assert oblig in sec.lower(), f"M07 obligation not owned: {oblig}"


# =============================================================================
# runner
# =============================================================================

def redact(text):
    import re
    import tempfile
    if not text:
        return text
    tmp = tempfile.gettempdir()
    for real, mark in ((str(ROOT), "<repo>"),
                       ("/private" + tmp, "<tmp>"), (tmp, "<tmp>"),
                       (str(pathlib.Path.home()), "<home>")):
        text = text.replace(real, mark)
    text = re.sub(r"[^\s'\"()]*scratchpad/[^\s'\"()]*", "<scratch>", text)
    return re.sub(r"/private/var/folders/[^\s'\"()]*|/var/folders/"
                  r"[^\s'\"()]*", "<tmp>", text)


def main(argv):
    out_path = None
    if "--json" in argv:
        i = argv.index("--json")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = set(argv)
    results = []
    for fn in CASES:
        if names and fn.__name__ not in names:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", (str(e) or "assertion")[:600]
        except Exception as e:  # noqa: BLE001
            status = "ERROR"
            tb = traceback.format_exc()
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + tb[-1200:])
        detail = redact(detail)
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("xm remediation:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_remediation.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_remediation.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
