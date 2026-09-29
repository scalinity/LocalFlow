"""GATE-G06 mandatory drivers, batch C part 2 (History actions after a
retry or a transform, Teach admission, correction learning into the next
frozen job, typed and mixed-origin notes, span corrections in export).

Every driver crosses the real interface its case names — the real
coordinator ``_worker``/``_retry_job`` and EvidenceCollector
(``test_lifecycle.Harness``), the real Hub controller headless, the real
M08 InsertionService and OutcomeObserver over the insertion suite's
fixture target, the real M07 CleanupEngine (a fake model's generate
function only), the real M12 NoteStore/NotesEditorModel, the real M14
services and DatasetExporter — and grades it with an independent oracle:
raw rows, exported files, what the Hub rendered and put on the private
pasteboard, what the fake model actually received. Orderings are decided
by latches (``xm_world.Latch``) and ``MainQueue``, never by sleeps.

Run (AppKit headless, desktop isolated — a private pasteboard):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/crossmilestone/test_xm_g06_c2.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402
from xm_world import ALPHA, BETA, one, rows  # noqa: E402

ROOT = X.ROOT
for p in (ROOT / "tests" / "v2" / "ui", ROOT / "tests" / "v2" / "lifecycle",
          ROOT / "tests" / "v2" / "insertion",
          ROOT / "tests" / "v2" / "fidelity",
          ROOT / "tests" / "v2" / "transforms"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication().setActivationPolicy_(1)

from test_lifecycle import FakeSupervisor, Harness  # noqa: E402
from m09_world import MainQueue  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2.history_queries import (HistoryQueryService,  # noqa: E402
                                          final_text)
from localflow.v2.supervisor import WorkerFailure  # noqa: E402

CASES = []


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


TEACH_RAW = "please check the modul today"
TEACH_FIX = "please check the module today"
APP_A = "com.synthetic.editor"
APP_B = "com.synthetic.other"
TYPED_CANARY = "TYPEDONLYCANARY"


# =============================================================================
# the fake model worker (ASR scripted; cleanup = the REAL M07 engine over a
# fake generate function) and the fake OS context reader
# =============================================================================

def _transcript_of(prompt):
    """The transcript field of the engine's rendered cleanup prompt (the
    fidelity suite's reading of the plain test rendering)."""
    body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
    try:
        return json.loads(body)["transcript"]
    except (ValueError, KeyError, TypeError):
        return body


class Scripted(FakeSupervisor):
    """A worker whose ASR text is chosen per (job, attempt) and whose
    cleanup can fail after ASR for chosen attempts (the remediation
    suite's shape). Records the exact text cleanup RECEIVED."""

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


class EngineWorker(FakeSupervisor):
    """The model worker with only the MODEL faked: ASR returns the
    scripted text, and cleanup runs the real ``CleanupEngine.clean`` with
    the exact field mapping of ``worker._clean_v2`` over a fake
    ``generate_fn`` (identity by default; ``edit`` rewrites what the
    fake model answers). Records every cleanup input payload (the
    independent input oracle) and every engine result text."""

    def __init__(self, asr, edit=None, transforms=None):
        super().__init__()
        self.asr = asr if callable(asr) else (lambda j, a, t=asr: t)
        self.edit = edit or (lambda text: text)
        self.clean_inputs = []
        self.clean_outputs = []
        self.transform_outputs = list(transforms or [])
        self.transform_calls = []

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        out = super().transcribe(job_id=job_id, attempt=attempt,
                                 audio_name=audio_name,
                                 sample_rate=sample_rate)
        out["text"] = self.asr(job_id, attempt)
        return out

    def clean(self, *, job_id, attempt, raw_text, **ctx):
        from localflow.v2.cleanup import CleanupEngine
        ctx.pop("revoked", None)
        self.calls.append("clean")
        self.clean_inputs.append({"raw_text": raw_text, **ctx})

        def gen(prompt, max_tokens):
            return {"text": self.edit(_transcript_of(prompt)),
                    "output_tokens": 8, "limit_hit": False,
                    "prompt": prompt}
        result = CleanupEngine(gen, model_id="fake-llm").clean(
            raw_text,
            destination_profile=ctx.get("destination_profile"),
            locale=ctx.get("locale") or "en-US",
            relevant_vocabulary=ctx.get("relevant_vocabulary") or [],
            protected_spans=[tuple(s)
                             for s in ctx.get("protected_spans") or []],
            vocabulary_pairs=[tuple(p)
                              for p in ctx.get("vocabulary_pairs") or []])
        self.clean_outputs.append(result.text)
        meta = {k: v for k, v in result.to_json().items()
                if k not in ("text", "observations")}
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": result.path,
                "fallback_reason": result.fallback_reason,
                "observations": result.observations, "v2": meta,
                "text": result.text}

    def transform(self, **payload):
        """The worker's transform op shape (test_transform_pipeline's
        M11Supervisor): scripted output/path per call."""
        self.transform_calls.append(payload)
        output, path = self.transform_outputs.pop(0) \
            if self.transform_outputs else ("", "applied")
        cov = {"atoms": 0, "covered": 0, "uncertain": 0, "missing": 0}
        return {
            "attempt": payload.get("attempt", 1),
            "generation": self.generation, "output": output,
            "coverage": [], "review_excerpts": [],
            "task_manifest": {"task_key": "ttask:g06"},
            "result": {"path": path, "reason": None if path == "applied"
                       else "requirement_coverage_uncertain",
                       "output_tokens": 20, "limit_hit": False,
                       "duration_ms": 1.0, "coverage": cov, "diff": None},
            "prompt": "<g06 transform prompt>"}


class ContextReader:
    """The OS destination reader faked (the M06 ContextCollector's
    identity/finalize shape): the destination app is whatever ``bundle``
    says at press time; with a fixture ``target`` the snapshot is that
    target's live identity (the object insertion revalidates)."""

    def __init__(self, bundle=APP_A, *, category="other", target=None):
        self.bundle = bundle
        self.category = category
        self.target = target

    def _target(self, tsid=None):
        from localflow.v2.context.snapshot import TargetSnapshot
        t = self.target
        return TargetSnapshot(
            target_snapshot_id=tsid or ids.new_id("tgt"),
            app_bundle=t.bundle if t is not None else self.bundle,
            app_name="Synthetic", app_pid=t.pid if t is not None else 42,
            denied=False, category=self.category,
            captured_at_utc=ids.now_utc_iso())

    def capture_identity(self):
        return self._target()

    def begin(self, identity):
        return ("handle", identity)

    def abandon(self):
        pass

    def finalize(self, *, coll=None, job_id, target_snapshot_id=None):
        from localflow.v2.context.snapshot import (ContextSnapshot,
                                                   FieldContext)
        t = self.target
        sel = (tuple(t.selection) if t is not None else (0, 0))
        return ContextSnapshot(
            context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
            target=self._target(target_snapshot_id),
            field=FieldContext(role=t.role if t is not None
                               else "AXTextArea", subrole=None,
                               classification="text", selected_text=None,
                               selected_range=sel),
            window_title=None)

    def take_downstream(self, handle):
        return None


# =============================================================================
# the real coordinator and the real Hub (copied remediation conventions)
# =============================================================================

def dictate(h):
    """One capture through the REAL hotkey -> _worker -> main-thread
    finish path. Returns the job id."""
    h.press()
    h.release()
    job = h.d._active_jobs[-1] if h.d._active_jobs else None
    fn, a = h.run_coordinator()
    fn(*a)
    return (job or a[1])["job_id"]


def examples_of(store, job_id):
    return rows(store, "SELECT example_id FROM training_examples WHERE"
                " job_id=? ORDER BY rowid", (job_id,))


def envelope(store, example_id):
    return json.loads(one(store, "SELECT r.envelope_json FROM"
                          " training_examples e JOIN training_revisions r"
                          " ON r.revision_id=e.latest_revision_id WHERE"
                          " e.example_id=?", (example_id,))[0])


def job_envelope(store, job_id):
    exs = examples_of(store, job_id)
    return envelope(store, exs[-1][0]) if exs else None


def applied_rule_ids(store, job_id):
    env = job_envelope(store, job_id) or {}
    return list(((env.get("normalization") or {}).get("vocabulary")
                 or {}).get("applied_rule_ids") or [])


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


def show_history_row(hub, mq, job):
    """The user opens History and selects the job's row (the state
    selection the table's delegate makes), then the detail renders."""
    open_view(hub, mq, "history")
    hub.state.select_history_row("job", job)
    assert mq.drain(hub.state, 60)
    return hub._rendered.get("history_detail")


def hub_teach(hub, mq, corrected):
    hub.teach_field.setStringValue_(corrected)
    hub.historyTeach_(None)
    mq.drain(hub.state, 60)
    return hub.history_detail.string()


class TeachSpy:
    """Records the admission arguments the Hub hands the REAL
    ``teach_correction`` (which still runs)."""

    def __init__(self, learning):
        self.learning = learning
        self.calls = []
        self.real = learning.teach_correction

        def spy(job_id, corrected, **kw):
            self.calls.append({"job_id": job_id, "corrected": corrected,
                               **kw})
            return self.real(job_id, corrected, **kw)
        learning.teach_correction = spy

    def close(self):
        del self.learning.teach_correction


def board():
    from AppKit import NSPasteboard, NSPasteboardTypeString
    pb = NSPasteboard.generalPasteboard()
    return pb.changeCount(), pb.stringForType_(NSPasteboardTypeString)


def consent_rows(store):
    return rows(store, "SELECT * FROM consent_revisions ORDER BY rowid")


def candidates_of(store, job_id=None):
    sql = ("SELECT candidate_id, example_id, job_id, source, status,"
           " proposed_alias, proposed_canonical, proposed_scope_kind,"
           " proposed_scope_value, changed_spans_json, before_artifact_id,"
           " after_artifact_id, classification_json, observation_id"
           " FROM learning_candidates")
    got = rows(store, sql + (" WHERE job_id=?" if job_id else "")
               + " ORDER BY rowid", (job_id,) if job_id else ())
    keys = ("candidate_id", "example_id", "job_id", "source", "status",
            "alias", "canonical", "scope_kind", "scope_value", "spans",
            "before_aid", "payload_aid", "classification",
            "observation_id")
    return [dict(zip(keys, r)) for r in got]


def payload_of(store, cand):
    row = one(store, "SELECT content_text FROM artifacts WHERE"
              " artifact_id=?", (cand["payload_aid"],))
    return json.loads(row[0]) if row and row[0] else None


def count(store, sql, args=()):
    return one(store, sql, args)[0]


# =============================================================================
# XM-R18 — a History read of attempt 1 held while a retry commits attempt 2
# =============================================================================

def _failed_attempt_one(h):
    """Attempt 1 (collection on) transcribes ALPHA and fails in cleanup —
    a failed_recoverable job whose History shows attempt 1's own stage.
    The retry's attempt 2 transcribes BETA and succeeds."""
    h.d.consent.set("enabled")
    sup = Scripted(asr=lambda j, a: ALPHA if a == 1 else BETA,
                   fail_clean={1})
    h.d.supervisor = sup
    job = dictate(h)
    assert h.job_state(job) == "failed_recoverable", \
        f"fixture: attempt 1 state {h.job_state(job)}"
    return job, sup


def _retry_from_hub_coordinator(h, job):
    """The Hub's Retry entry (``hubRetryJob`` -> ``_retry_job``) and the
    real worker running attempt 2 to its finish."""
    out = h.d.hubRetryJob(job) or {}
    assert out.get("outcome") in (None, "requeued", "queued"), \
        f"fixture: retry refused {out}"
    fn, a = h.run_coordinator()
    fn(*a)
    h.d.store.sync()


def _attempt_two_final(h, sup, job):
    got = [t for j, a, t in sup.clean_inputs if j == job and a == 2]
    assert len(got) == 1, f"fixture: attempt 2 cleanup inputs {got}"
    expected = got[0].upper()
    cleaned = rows(h.d.store, "SELECT artifact_id FROM artifacts WHERE"
                   " job_id=? AND role='applied_output' AND content_text=?",
                   (job, expected))
    assert cleaned, "fixture: attempt 2 wrote no applied output"
    return expected, cleaned[-1][0]


def _history_actions(h, hub, mq, spy, expected):
    """What the rendered History detail and its action targets say:
    the rendered lineage attempt, whether attempt 1's text is on screen,
    what Copy put on the private pasteboard and which final Teach bound
    itself to."""
    rendered = hub._rendered.get("history_detail") or {}
    pane = hub.history_detail.string()
    hub.historyCopy_(None)
    _gen, copied = board()
    hub.teach_field.setStringValue_(expected.replace("WORDS", "WORLDS"))
    hub.historyTeach_(None)
    mq.drain(hub.state, 60)
    teach = spy.calls[-1] if spy.calls else {}
    return {"rendered_attempt": rendered.get("lineage_attempt"),
            "rendered_final": final_text(rendered),
            "alpha_on_screen": ALPHA in pane or ALPHA.upper() in pane,
            "copied": copied,
            "teach_expected_artifact": teach.get(
                "expected_final_artifact_id"),
            "note": hub.history_detail.string().rsplit("\n", 1)[-1]}


@case("G06 XM-R18 (History never publishes attempt-1 action authority"
      " after a known attempt-2 commit)")
def g06_xm_r18_retry_commits_while_history_read_is_held():
    h = Harness(durations=[1.0])
    spy = None
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            h.d._hub = hub
            assert mq.drain(hub.state, 60)
            job, sup = _failed_attempt_one(h)
            open_view(hub, mq, "history")
            svc = hub.state.history_service
            real = svc.job_detail
            latch = X.Latch("history_detail_read_of_attempt_1")

            def held(job_id):
                detail = real(job_id)
                if job_id == job and not latch.reached.is_set():
                    latch.observed = detail
                    latch.hit()  # after the read, before publication
                return detail
            svc.job_detail = held
            try:
                hub.state.select_history_row("job", job)
                assert latch.reached.wait(10), \
                    "fixture: the History detail read never ran"
                assert latch.observed.get("lineage_attempt") == 1, (
                    "fixture: the held read did not observe attempt 1:"
                    f" {latch.observed.get('lineage_attempt')}")
                _retry_from_hub_coordinator(h, job)
                attempt = one(h.d.store, "SELECT attempt FROM jobs WHERE"
                              " job_id=?", (job,))[0]
                assert attempt == 2, f"fixture: job attempt {attempt}"
                expected, cleaned_aid = _attempt_two_final(h, sup, job)
            finally:
                latch.release()
            assert mq.drain(hub.state, 60)
            del svc.job_detail
            spy = TeachSpy(h.d._learning)
            got = _history_actions(h, hub, mq, spy, expected)
        want = {"rendered_attempt": 2, "rendered_final": expected,
                "alpha_on_screen": False, "copied": expected,
                "teach_expected_artifact": cleaned_aid}
        bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
        assert not bad, (
            "after the retry committed attempt 2, the Hub published and"
            " kept attempt 1's detail as current (got, want): "
            + json.dumps(bad, default=str) + f"; note {got['note']!r}")
    finally:
        if spy is not None:
            spy.close()
        h.close()


@case("G06 XM-R18 control (a read after the commit renders attempt 2;"
      " no retry renders attempt 1)", kind="control")
def g06_xm_r18_control_reads_on_either_side_of_the_commit():
    h = Harness(durations=[1.0])
    spy = None
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            h.d._hub = hub
            assert mq.drain(hub.state, 60)
            job, sup = _failed_attempt_one(h)
            rendered = show_history_row(hub, mq, job) or {}
            pane = hub.history_detail.string()
            assert rendered.get("lineage_attempt") == 1 and ALPHA in pane, (
                "no-retry control: History did not render attempt 1"
                f" ({rendered.get('lineage_attempt')})")
            _retry_from_hub_coordinator(h, job)
            expected, cleaned_aid = _attempt_two_final(h, sup, job)
            # The read after the commit: select another view and back
            # to the row (a fresh selection admits a fresh read).
            hub.state.select_history_row("job", None)
            mq.drain(hub.state, 60)
            show_history_row(hub, mq, job)
            spy = TeachSpy(h.d._learning)
            got = _history_actions(h, hub, mq, spy, expected)
        want = {"rendered_attempt": 2, "rendered_final": expected,
                "alpha_on_screen": False, "copied": expected,
                "teach_expected_artifact": cleaned_aid}
        bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
        assert not bad, ("a read after attempt 2 committed does not render"
                         " attempt 2: " + json.dumps(bad, default=str))
    finally:
        if spy is not None:
            spy.close()
        h.close()


# =============================================================================
# XM-C020 / XM-MH06 — a recoverable failure retried through the coordinator
# into the real InsertionService: one logical dictation in usage and Insights
# =============================================================================

_WRITES = ("ax_set_text", "ax_set_range", "paste_consumed", "ax_set_noop")


def _run_inline(a, *, snapshot):
    """The coordinator's next main-thread handoff run inline (callbacks
    too), then the real service settled. ``snapshot`` attaches the M08
    world's destination to a fresh capture, as AppEnv.dictate does; a
    retry keeps whatever job ``_retry_job`` built."""
    import localflow.app as app_mod
    from m08_world import wait_for
    from test_m08_remediation import snap
    fn, args = a.h.run_coordinator()
    if snapshot and fn == a.d._finishWithText_:
        s = snap(a.w)
        args[1]["context_snapshot"] = s
        args[1]["target"] = s.target
    real = app_mod.AppHelper.callAfter
    app_mod.AppHelper.callAfter = lambda f, *x: f(*x)
    try:
        fn(*args)
        assert wait_for(lambda: not a.d._active_jobs and not a.svc.pending,
                        10), "fixture: the job never settled"
    finally:
        app_mod.AppHelper.callAfter = real
    a.d.store.sync()


def _instant(text):
    from datetime import datetime
    return datetime.fromisoformat(text).isoformat() if text else text


def _facts(store, job):
    return rows(store, "SELECT insertion_outcome, attempt, activity_at_utc,"
                " final_words, day_local FROM usage_facts WHERE job_id=?"
                " AND kind='dictation'", (job,))


def _one_logical_dictation(retry):
    """One capture in AppEnv (the real app, its own InsertionService over
    the M08 world, F1 focused). With ``retry`` attempt 1 (ALPHA) fails in
    cleanup and History's Retry runs attempt 2 (BETA) to insertion.
    Returns the witness ledger and what the product recorded."""
    from test_m08_remediation import AppEnv
    import localflow.app as app_mod
    a = AppEnv(consent=True, window=0.3)
    try:
        app_mod.AUDIO_DEBUG_DIR = a.h.tmp / "dbg"
        a.d.recorder.durations.extend([1.0] * 4)
        sup = Scripted(asr=lambda j, n: ALPHA if n == 1 else BETA,
                       fail_clean={1} if retry else ())
        a.d.supervisor = sup
        store = a.d.store
        since = a.w.effects[-1][0] if a.w.effects else 0
        # A clock that moves 5 ms per read across the press: the mic-open
        # latency a real capture has, so every instant minted at the
        # capture boundary is distinguishable.
        real_now, ticks = ids.now_utc_iso, [0]

        def ticking(ts=None):
            ticks[0] += 1
            return real_now(ts if ts is not None
                            else time.time() + 0.005 * ticks[0])
        ids.now_utc_iso = ticking
        try:
            a.h.press_release()
        finally:
            ids.now_utc_iso = real_now
        _run_inline(a, snapshot=True)
        job = one(store, "SELECT job_id FROM jobs ORDER BY rowid DESC")[0]
        captured = one(store, "SELECT captured_at_utc FROM jobs WHERE"
                       " job_id=?", (job,))[0]
        want_attempt = 1
        if retry:
            assert one(store, "SELECT state FROM jobs WHERE job_id=?",
                       (job,))[0] == "failed_recoverable", \
                "fixture: attempt 1 did not fail recoverably"
            first = _facts(store, job)
            assert [f[0] for f in first] == ["failed"], \
                f"fixture: attempt 1's usage fact {first}"
            out = a.d.hubRetryJob(job) or {}
            assert out.get("outcome") in (None, "requeued", "queued"), \
                f"fixture: retry refused {out}"
            _run_inline(a, snapshot=False)
            want_attempt = 2
        text = [t for j, n, t in sup.clean_inputs
                if j == job and n == want_attempt]
        assert len(text) == 1, f"fixture: cleanup inputs {text}"
        final = one(store, "SELECT content_text FROM artifacts WHERE"
                    " job_id=? AND role='applied_output' ORDER BY rowid"
                    " DESC", (job,))[0]
        assert final == text[0].upper(), \
            f"fixture: applied final {final!r} is not attempt" \
            f" {want_attempt}'s cleanup"
        settled = one(store, "SELECT state FROM insertions WHERE job_id=?"
                      " ORDER BY rowid DESC", (job,))[0]
        facts = _facts(store, job)
        day = facts[0][4] if facts else None
        # The independent daily recomputation, from the raw facts.
        recomputed = one(store, "SELECT COUNT(*), SUM(final_words) FROM"
                         " usage_facts WHERE kind='dictation' AND"
                         " day_local=?", (day,))
        daily = {r["day"]: r for r in a.d._insights.report()["daily"]}
        writes = [e for e in a.w.effects if e[2] == "F1" and e[0] > since
                  and e[1] in _WRITES]
        return {
            # Instants compared as instants: the job row and the fact
            # write the same time at different fractional precision.
            "facts": [(f[0], f[1], _instant(f[2]), f[3]) for f in facts],
            "want_fact": [(settled, want_attempt, _instant(captured),
                           len(final.split()))],
            "settled": settled,
            "report_day": {k: (daily.get(day) or {}).get(k) for k in
                           ("dictations", "final_words", "transforms")},
            "want_day": {"dictations": recomputed[0],
                         "final_words": recomputed[1], "transforms": 0},
            "one_day_row": recomputed[0] == 1,
            "transform_facts": one(store, "SELECT COUNT(*) FROM usage_facts"
                                   " WHERE kind='transform'")[0],
            "f1": a.w.text("F1"), "final": final,
            "f1_writes": len(writes),
        }
    finally:
        a.close()


def _ledger_violations(got):
    bad = {}
    if got["facts"] != got["want_fact"]:
        bad["usage_fact"] = (got["facts"], got["want_fact"])
    if got["settled"] in ("failed", None):
        bad["settled"] = got["settled"]
    if got["report_day"] != got["want_day"] or not got["one_day_row"]:
        bad["insights_day"] = (got["report_day"], got["want_day"])
    if got["transform_facts"]:
        bad["transform_facts"] = got["transform_facts"]
    if got["f1"].strip() != got["final"] or got["f1_writes"] != 1:
        bad["F1"] = (got["f1"], got["final"], got["f1_writes"])
    return bad


@case("G06 XM-C020 / XM-MH06 (a failed attempt retried through the"
      " coordinator and inserted by the real service is one logical"
      " dictation: attempt 2's outcome, the original instant, counted once)")
def g06_xm_c020_mh06_retry_is_one_logical_dictation():
    got = _one_logical_dictation(retry=True)
    bad = _ledger_violations(got)
    assert not bad, ("the retried capture's usage, Insights or insertion"
                     " ledger (got, want): " + json.dumps(bad, default=str))


@case("G06 XM-C020 / XM-MH06 control (one clean capture has the same"
      " one-fact ledger with attempt 1)", kind="control")
def g06_xm_c020_mh06_control_clean_capture():
    got = _one_logical_dictation(retry=False)
    bad = _ledger_violations(got)
    assert not bad, ("a clean capture's ledger (got, want): "
                     + json.dumps(bad, default=str))


# =============================================================================
# XM-MH13 — the applied transformed final from the real pipeline, and Teach
# =============================================================================

MAIL = "com.apple.mail"
TF_TEXT = "Please check the modul today, formally."


def _transform_harness(consent):
    """The real dictation path with an opted-in auto-apply transform
    (test_transform_pipeline's M11-AC04 setup): a mail destination whose
    style rule resolves Polish, builtin:polish auto-applying."""
    h = Harness(durations=[1.0, 1.0], cfg={"log_transcripts": True})
    if consent:
        h.d.consent.set("enabled")
    h.d._context = ContextReader(MAIL, category="mail")
    h.d._styles.add_rule(name="Mail polish", scope_kind="category",
                         scope_value="email", mode="polish")
    h.d._tf_store.update_transform("builtin:polish", auto_apply=True)
    sup = EngineWorker(TEACH_RAW, transforms=[(TF_TEXT, "applied")])
    h.d.supervisor = sup
    return h, sup


def _transform_artifact(store, job):
    """(artifact id, text) of the job's retained transform output, read
    from the rows (History's own artifact, or the training manifest's
    transform output when collection held the job)."""
    got = rows(store, "SELECT artifact_id, content_text FROM artifacts"
               " WHERE job_id=? AND role='transform_output' AND purged=0",
               (job,))
    if got:
        return got[-1]
    env = job_envelope(store, job) or {}
    aid = (((env.get("transform") or {}).get("artifact_ids") or {})
           .get("output"))
    row = one(store, "SELECT artifact_id, content_text FROM artifacts"
              " WHERE artifact_id=?", (aid,)) if aid else None
    return row


@case("G06 XM-MH13 (History shows the pipeline's applied transformed final"
      " and Teach refuses it explicitly)")
def g06_xm_mh13_transformed_final_teach_refused():
    problems = {}
    for consent in (False, True):
        h, sup = _transform_harness(consent)
        spy = None
        try:
            with MainQueue() as mq:
                hub = make_hub(h)
                assert mq.drain(hub.state, 60)
                job = dictate(h)
                store = h.d.store
                store.sync()
                tf = _transform_artifact(store, job)
                assert sup.transform_calls and tf and tf[1] == TF_TEXT and \
                    h.pastes and h.pastes[-1].strip() == TF_TEXT, (
                    f"fixture (collection {consent}): the transform did"
                    f" not apply: calls={len(sup.transform_calls)}"
                    f" artifact={tf} pastes={h.pastes}")
                rendered = show_history_row(hub, mq, job) or {}
                spy = TeachSpy(h.d._learning)
                note = hub_teach(hub, mq, TF_TEXT.replace("modul",
                                                          "module"))
            got = {"final_stage": rendered.get("final_stage"),
                   "rendered_final": final_text(rendered),
                   "refusal_shown": "Teach refused: this dictation's final"
                                    " text came from a transform" in note,
                   "service_called": bool(spy.calls),
                   "candidates": count(store, "SELECT COUNT(*) FROM"
                                       " learning_candidates WHERE job_id=?",
                                       (job,))}
            want = {"final_stage": "transformed", "rendered_final": tf[1],
                    "refusal_shown": True, "service_called": False,
                    "candidates": 0}
            bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
            if bad:
                problems[f"collection_{consent}"] = bad
        finally:
            if spy is not None:
                spy.close()
            h.close()
    assert not problems, ("the transformed final was not shown or Teach"
                          " did not refuse it (got, want): "
                          + json.dumps(problems, default=str))


@case("G06 XM-MH13 (a cleaned render superseded by the job's applied"
      " transform: Teach never teaches against raw or unseen text)")
def g06_xm_mh13_cleaned_render_then_transform_commits():
    """The governing final changes after render inside the job's own
    attempt: History is read after the Clean output is retained and
    before the transform's History artifact commits (a latch at that
    write), then the transform commits. The recorded Teach admission
    contract (contracts/learning.md, hub.md): Teach carries the rendered
    cleaned-stage artifact id and hash, the service compares the job's
    applied output, a different/purged/changed one refuses stale_final,
    and only a row RENDERED as transformed is refused in the Hub. So the
    Teach may be admitted against exactly the cleaned text the user saw,
    or refused — never measured against the raw transcript or the unseen
    transform output."""
    h, sup = _transform_harness(consent=False)
    spy = None
    store = h.d.store
    real_write = store.write_text_artifact
    latch = X.Latch("before_transform_history_write")

    def write(*a, **kw):
        if kw.get("role") == "transform_output" and \
                not latch.reached.is_set():
            latch.hit()
        return real_write(*a, **kw)
    try:
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            finished = threading.Event()
            mq.on_post = lambda fn, a: (
                finished.set() if fn == h.d._finishWithText_ else None)
            store.write_text_artifact = write
            h.press()
            h.release()
            job = h.d._active_jobs[-1]["job_id"]
            threading.Thread(target=h.d._worker, daemon=True,
                             name="g06-coordinator").start()
            try:
                assert latch.reached.wait(15), \
                    "fixture: the transform's History write never came"
                rendered = show_history_row(hub, mq, job) or {}
                shown = next((s.get("artifact") for s in
                              rendered.get("lineage") or []
                              if s["stage"] == "cleaned"), None) or {}
                assert rendered.get("final_stage") == "cleaned" and \
                    shown.get("text"), (
                    "fixture: History did not render the cleaned final"
                    f" before the transform committed: {rendered}")
            finally:
                latch.release()
            assert finished.wait(15), "fixture: the job never finished"
            mq.flush()
            del store.write_text_artifact
            store.sync()
            current = HistoryQueryService(store).job_detail(job)
            tf = _transform_artifact(store, job)
            assert current["final_stage"] == "transformed" and tf and \
                tf[1] == TF_TEXT, (
                "fixture: the governing final did not change to the"
                f" transform: {current['final_stage']} {tf}")
            assert (hub._rendered.get("history_detail") or {}).get(
                "final_stage") == "cleaned", "fixture: the render moved"
            spy = TeachSpy(h.d._learning)
            note = hub_teach(hub, mq, shown["text"].replace("modul",
                                                            "module"))
            raw_aid = one(store, "SELECT artifact_id FROM artifacts WHERE"
                          " job_id=? AND role='raw_transcript'", (job,))[0]
        cands = candidates_of(store, job)
        taught = [{"before_aid": c["before_aid"],
                   "before": (payload_of(store, c) or {}).get("before")}
                  for c in cands]
        wrong = [t for t in taught
                 if t["before_aid"] != shown["artifact_id"]
                 or t["before"] != shown["text"]
                 or t["before_aid"] == raw_aid or t["before"] == TF_TEXT]
        explicit = bool(cands) or "refused" in note
        assert not wrong and explicit and len(cands) <= 1, (
            "Teach after the governing final changed was measured against"
            " text the user did not see, or silently did nothing:"
            f" taught={taught} rendered_cleaned={shown.get('artifact_id')}"
            f" raw={raw_aid} note={note.rsplit(chr(10), 1)[-1]!r}")
        print(f"       MH13 in-flight variant outcome:"
              f" {'admitted against the rendered cleaned text' if cands else 'refused'}"
              f" ({note.rsplit(chr(10), 1)[-1]})")
    finally:
        if spy is not None:
            spy.close()
        h.close()


@case("G06 XM-MH13 control (a cleaned final unchanged after render teaches"
      " exactly one candidate)", kind="control")
def g06_xm_mh13_control_cleaned_final_teaches_once():
    h = Harness(durations=[1.0], cfg={"log_transcripts": True})
    try:
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker(TEACH_RAW)
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            job = dictate(h)
            rendered = show_history_row(hub, mq, job) or {}
            shown = next(s["artifact"] for s in rendered["lineage"]
                         if s["stage"] == "cleaned")
            assert rendered.get("final_stage") == "cleaned" and shown, \
                f"fixture: {rendered.get('final_stage')}"
            note = hub_teach(hub, mq, shown["text"].replace("modul",
                                                            "module"))
        cands = candidates_of(h.d.store, job)
        assert len(cands) == 1 and \
            cands[0]["before_aid"] == shown["artifact_id"] and \
            (payload_of(h.d.store, cands[0]) or {}).get("before") == \
            shown["text"], (f"control: {len(cands)} candidates;"
                             f" note {note.rsplit(chr(10), 1)[-1]!r}")
    finally:
        h.close()


# =============================================================================
# XM-C110 — a Hub Teach with collection off
# =============================================================================

def _teach_world_counts(store, job):
    return {"consent_rows": consent_rows(store),
            "training_examples": count(store, "SELECT COUNT(*) FROM"
                                       " training_examples"),
            "job_candidates": candidates_of(store, job)}


def _c110_violations(before, after, state_before, state_after, job):
    """The C110 oracle over raw rows (independent of the service):
    exactly one new job-bound explicit-intent candidate with no example,
    no training example, the consent history untouched, collection still
    disabled."""
    new = [c for c in after["job_candidates"]
           if c["candidate_id"] not in {x["candidate_id"]
                                        for x in before["job_candidates"]}]
    got = {"new_candidates": len(new),
           "job_bound": [c["job_id"] == job and c["example_id"] is None
                         and c["source"] == "explicit_teach"
                         and json.loads(c["classification"] or "{}").get(
                             "evidence_status") == "explicit_intent_review"
                         for c in new],
           "training_examples": after["training_examples"],
           "consent_rows_unchanged":
               after["consent_rows"] == before["consent_rows"],
           "consent_state": (state_before, state_after)}
    want = {"new_candidates": 1, "job_bound": [True],
            "training_examples": 0,
            "consent_rows_unchanged": True,
            "consent_state": ("disabled", "disabled")}
    return {k: (got[k], v) for k, v in want.items() if got[k] != v}


def _collection_off_teach(h, mq, hub, job):
    store = h.d.store
    state0 = h.d.consent.state()
    before = _teach_world_counts(store, job)
    show_history_row(hub, mq, job)
    note = hub_teach(hub, mq, TEACH_FIX)
    return before, _teach_world_counts(store, job), state0, \
        h.d.consent.state(), note


@case("G06 XM-C110 (a Hub Teach with collection off makes one job-bound"
      " candidate, never enables collection or a training example)")
def g06_xm_c110_collection_off_hub_teach():
    h = Harness(durations=[1.0], cfg={"log_transcripts": True})
    try:
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker(TEACH_RAW)
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            job = dictate(h)
            assert h.d.consent.state() == "disabled" and \
                h.d.store.current_consent_id() is None, \
                "fixture: the harness has a consent revision"
            assert rows(h.d.store, "SELECT 1 FROM artifacts WHERE job_id=?"
                        " AND role='applied_output'", (job,)), \
                "fixture: the job left no History final"
            before, after, s0, s1, note = _collection_off_teach(
                h, mq, hub, job)
        bad = _c110_violations(before, after, s0, s1, job)
        assert not bad, ("the collection-off Teach broke its contract"
                         " (got, want): " + json.dumps(bad, default=str)
                         + f"; note {note.rsplit(chr(10), 1)[-1]!r}")
    finally:
        h.close()


@case("G06 XM-C110 control (collection on binds the example; a teach path"
      " that enables collection fails the oracle)", kind="control")
def g06_xm_c110_control_example_bound_and_mutant():
    # Positive control: consent enabled, a live example — the candidate
    # binds to it and the consent history is still untouched by Teach.
    h = Harness(durations=[1.0])
    try:
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker(TEACH_RAW)
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            job = dictate(h)
            (ex,), = examples_of(h.d.store, job)
            c0 = consent_rows(h.d.store)
            show_history_row(hub, mq, job)
            hub_teach(hub, mq, TEACH_FIX)
        cands = candidates_of(h.d.store, job)
        assert len(cands) == 1 and cands[0]["example_id"] == ex, \
            f"control: candidate not bound to the example: {cands}"
        assert consent_rows(h.d.store) == c0, "control: Teach wrote consent"
    finally:
        h.close()
    # Mutant control: the same collection-off Hub Teach through a teach
    # path that appends consent 'enabled' must fail the C110 oracle.
    h = Harness(durations=[1.0], cfg={"log_transcripts": True})
    try:
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker(TEACH_RAW)
        learning = h.d._learning
        real = learning.teach_correction

        def mutant(job_id, corrected, **kw):
            h.d.consent.set("enabled", note="mutant teach")
            return real(job_id, corrected, **kw)
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            job = dictate(h)
            learning.teach_correction = mutant
            before, after, s0, s1, _note = _collection_off_teach(
                h, mq, hub, job)
            del learning.teach_correction
        bad = _c110_violations(before, after, s0, s1, job)
        assert "consent_rows_unchanged" in bad and "consent_state" in bad, \
            f"mutant control: the oracle missed an enabling teach: {bad}"
    finally:
        h.close()


# =============================================================================
# XM-C116 + XM-MR08 — unapproved learning evidence vs the next frozen job
# =============================================================================

def _note_mined_candidate(h, job, text):
    """A real M12 note-family candidate: the dictation's text arrives in
    a note (attributed to its job), then a typed correction inside it;
    mining runs the real ``_mine_note_candidates``."""
    notes = h.d._notes_store
    n = notes.create_note(text, origin="dictated", source_job_id=job)
    notes.append_revision(n["note_id"], text.replace("modul", "module"),
                          origin="typed", trigger="autosave")
    return h.d._learning.mine_observation_candidates()


def _probe_world(variant):
    """One world: the same seed dictation, the variant's evidence
    through the real services, then the same probe dictation through the
    real coordinator (frozen at its press). Returns what the probe's
    runtime produced: the normalized text cleanup received, the whole
    cleanup input payload, the applied rule ids and the inserted text."""
    h = Harness(durations=[1.0, 1.0], cfg={"profile_min_words": 1})
    try:
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        sup = EngineWorker(TEACH_RAW)
        h.d.supervisor = sup
        seed = dictate(h)
        (ex,), = examples_of(h.d.store, seed)
        seed_final = h.pastes[-1].strip()
        L = h.d._learning
        fx = {}
        if variant in ("pending", "all", "approved"):
            fx["teach"] = L.teach_correction(seed, TEACH_FIX)
        if variant in ("mined", "all"):
            fx["mined"] = _note_mined_candidate(h, seed, seed_final)
        if variant in ("sampled", "all"):
            fx["sampled"] = h.d._sampling.refresh(percent=100.0)
        if variant in ("labeled", "all"):
            fx["label"] = h.d._review.record_label(
                ex, edit_kind="recognition_error", origin_stages=("asr",))
        if variant in ("rejected", "all"):
            other = L.teach_correction(
                seed, TEACH_FIX.replace("today", "tomorrow"))
            fx["rejected"] = L.reject(other["candidate_id"])
        if variant in ("profile", "all"):
            fx["profile"] = bool(h.d._profile.compute().get("snapshot_id"))
        if variant == "approved":
            fx["approved"] = L.approve(fx["teach"]["candidate_id"])
        statuses = sorted(r[0] for r in rows(
            h.d.store, "SELECT status FROM learning_candidates"))
        probe = dictate(h)
        return {"normalized": sup.clean_inputs[-1]["raw_text"],
                "cleanup_input": json.dumps(sup.clean_inputs[-1],
                                            sort_keys=True, default=str),
                "applied_rule_ids": applied_rule_ids(h.d.store, probe),
                "final": h.pastes[-1],
                "entry": (fx.get("approved") or {}).get("entry_id"),
                "statuses": statuses,
                "labels": count(h.d.store, "SELECT COUNT(*) FROM"
                                " correction_labels"),
                "sampled": count(h.d.store, "SELECT COUNT(*) FROM"
                                 " sampling_decisions"),
                "profiles": count(h.d.store, "SELECT COUNT(*) FROM"
                                  " profile_snapshots")}
    finally:
        h.close()


@case("G06 XM-C116 + XM-MR08 (pending, mined, sampled, labeled, rejected"
      " or profile evidence never changes normalization or cleanup; only"
      " approval does)")
def g06_xm_c116_mr08_unapproved_evidence_never_changes_output():
    base = _probe_world("baseline")
    assert base["applied_rule_ids"] == [] and "modul " in \
        base["normalized"] + " " and base["statuses"] == [], \
        f"fixture: the baseline world is not a no-evidence world: {base}"
    worlds = {v: _probe_world(v) for v in ("pending", "mined", "sampled",
                                           "labeled", "rejected",
                                           "profile", "all", "approved")}
    reached = {
        "pending": "pending" in worlds["pending"]["statuses"],
        "mined": "pending" in worlds["mined"]["statuses"],
        "sampled": worlds["sampled"]["sampled"] > 0,
        "labeled": worlds["labeled"]["labels"] > 0,
        "rejected": "rejected" in worlds["rejected"]["statuses"],
        "profile": worlds["profile"]["profiles"] > 0,
        "all": {"pending", "rejected"} <= set(worlds["all"]["statuses"])
        and worlds["all"]["labels"] and worlds["all"]["sampled"]
        and worlds["all"]["profiles"]}
    assert all(reached.values()), \
        f"fixture: an evidence variant never reached the store: {reached}"
    keys = ("normalized", "cleanup_input", "applied_rule_ids", "final")
    changed = {v: [k for k in keys if w[k] != base[k]]
               for v, w in worlds.items() if v != "approved"}
    changed = {v: k for v, k in changed.items() if k}
    approved = worlds["approved"]
    control = {
        "differs": [k for k in keys if approved[k] != base[k]],
        "applied_rule_ids": approved["applied_rule_ids"],
        "entry": approved["entry"],
        "corrected": "module" in approved["final"]
        and "modul " not in approved["final"] + " "}
    assert control["entry"] and control["applied_rule_ids"] == [
        control["entry"]] and control["corrected"] and \
        set(control["differs"]) == set(keys), (
        "positive control: approval did not change the next job's"
        f" normalization/cleanup exactly: {control}")
    assert not changed, (
        "unapproved learning evidence changed the next frozen job's"
        " runtime output (variant -> fields differing from the"
        " no-evidence world): " + json.dumps(changed)
        + " | " + json.dumps({v: {k: worlds[v][k] for k in keys}
                              for v in changed}, default=str)[:300])


# =============================================================================
# XM-MH14 — an approval landing mid-flight applies from the next frozen job
# =============================================================================

def _reverting_model(text):
    """A fake model that undoes the learned correction (answers the
    alias where the canonical stood): the canonical must survive the
    engine's validation, or the job's final loses it."""
    return text.replace("module", "modul")


def _usage(store):
    return {job: (n, hits) for job, n, hits in rows(
        store, "SELECT job_id, COUNT(*), SUM(dictionary_hits) FROM"
        " usage_facts WHERE kind='dictation' GROUP BY job_id")}


def _mid_flight_chain(approve_before_job1):
    """Seed job 0 in APP_A is taught; the approval lands between job 1's
    press and release (or before job 1's press in the control); job 2 in
    APP_A and job 3 in APP_B follow. Every job runs the real coordinator
    with the real CleanupEngine over a reverting fake model."""
    h = Harness(durations=[1.0] * 4)
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        ctx = ContextReader(APP_A)
        h.d._context = ctx
        sup = EngineWorker(TEACH_RAW, edit=_reverting_model)
        h.d.supervisor = sup
        job0 = dictate(h)
        cand = h.d._learning.teach_correction(job0, TEACH_FIX)
        cid = cand["candidate_id"]
        assert (cand.get("suggestion") or {}).get("alias") == "modul", \
            f"fixture: no modul -> module suggestion: {cand}"
        if approve_before_job1:
            out = h.d._learning.approve(cid)
            h.press()
        else:
            h.press()
            out = h.d._learning.approve(cid)  # mid-flight, job 1 frozen
        h.release()
        job1 = h.d._active_jobs[-1]["job_id"]
        fn, a = h.run_coordinator()
        fn(*a)
        final1 = h.pastes[-1]
        job2 = dictate(h)
        final2 = h.pastes[-1]
        ctx.bundle = APP_B
        job3 = dictate(h)
        final3 = h.pastes[-1]
        store.sync()
        eid = out["entry_id"]

        def vocab_block(job):
            env = job_envelope(store, job) or {}
            return (env.get("normalization") or {}).get("vocabulary") or {}
        vocab2 = vocab_block(job2)
        frozen = one(store, "SELECT content_text FROM artifacts WHERE"
                     " job_id=? AND role='vocabulary_applied_rules'",
                     (job2,))
        frozen = json.loads(frozen[0]) if frozen and frozen[0] else {}
        delta = json.loads(one(store, "SELECT delta_json FROM"
                               " learning_vocabulary_deltas WHERE"
                               " candidate_id=?", (cid,))[0])
        return {
            "entry": eid, "scope": one(
                store, "SELECT scope_kind, scope_value FROM"
                " vocabulary_entries WHERE entry_id=?", (eid,)),
            "jobs": (job0, job1, job2, job3),
            "final1": final1, "final2": final2, "final3": final3,
            "applied1": applied_rule_ids(store, job1),
            "applied2": vocab2.get("applied_rule_ids"),
            "revision2": vocab2.get("revision"),
            # The snapshot revision each job froze (job 0 and job 1 both
            # before the approval took effect, job 2 after it).
            "snapshot_revisions": [vocab_block(j).get("revision")
                                   for j in (job0, job1, job2)],
            # Job 2's frozen applied-rules record vs the approval's own
            # recorded delta (the entry revision the approval left).
            "frozen_rules": [(r.get("entry_id"), r.get("revision"))
                             for r in frozen.get("rules") or []],
            "frozen_snapshot_revision": frozen.get("vocabulary_revision"),
            "delta": (delta.get("entry_id"),
                      delta.get("revision_after_approval")),
            "applied3": applied_rule_ids(store, job3),
            "usage_count": one(store, "SELECT usage_count FROM"
                               " vocabulary_entries WHERE entry_id=?",
                               (eid,))[0],
            "usage": _usage(store),
            "model_saw2": sup.clean_inputs[2]["raw_text"],
            "model_answered2": _reverting_model(
                sup.clean_inputs[2]["raw_text"])}
    finally:
        h.close()


@case("G06 XM-MH14 (an approval between press and release applies only from"
      " the next frozen job: one scoped rewrite, exact revision, kept"
      " through cleanup, counted once)")
def g06_xm_mh14_mid_flight_approval_applies_from_next_job():
    r = _mid_flight_chain(approve_before_job1=False)
    job0, job1, job2, job3 = r["jobs"]
    assert r["scope"] == ("app", APP_A) and \
        "module" in r["model_saw2"] and \
        "module" not in r["model_answered2"], (
        "fixture: the rule is not app-scoped or the fake model never"
        f" tried to revert the canonical: {r['scope']}"
        f" saw={r['model_saw2']!r}")
    rev0, rev1, rev2 = r["snapshot_revisions"]
    got = {
        "job1_uncorrected": "modul " in r["final1"] + " "
        and r["applied1"] == [],
        "job2_applied": r["applied2"],
        "job1_froze_pre_approval_snapshot": rev1 == rev0 != rev2,
        "job2_frozen_rules": r["frozen_rules"],
        "job2_frozen_record_revision": r["frozen_snapshot_revision"],
        "job2_final_keeps_canonical": "module" in r["final2"],
        "job3_out_of_scope_uncorrected": "modul " in r["final3"] + " "
        and r["applied3"] == [],
        "usage_count": r["usage_count"],
        "facts": {j: r["usage"].get(j) for j in (job1, job2, job3)}}
    want = {
        "job1_uncorrected": True, "job2_applied": [r["entry"]],
        "job1_froze_pre_approval_snapshot": True,
        "job2_frozen_rules": [r["delta"]],
        "job2_frozen_record_revision": rev2,
        "job2_final_keeps_canonical": True,
        "job3_out_of_scope_uncorrected": True, "usage_count": 1,
        "facts": {job1: (1, 0), job2: (1, 1), job3: (1, 0)}}
    bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    assert not bad, ("the mid-flight approval did not apply exactly once"
                     " from the next frozen job (got, want): "
                     + json.dumps(bad, default=str))


@case("G06 XM-MH14 control (approval before job 1's press corrects job 1)",
      kind="control")
def g06_xm_mh14_control_approval_before_press():
    r = _mid_flight_chain(approve_before_job1=True)
    assert "module" in r["final1"] and r["applied1"] == [r["entry"]] and \
        "modul " in r["final3"] + " ", (
        "control: an approval before job 1's press did not correct job 1"
        f" (or leaked out of scope): final1={r['final1']!r}"
        f" applied1={r['applied1']} final3={r['final3']!r}")


# =============================================================================
# XM-MH09 — the real M08 observer's certified edit into mining, approval and
# the next job
# =============================================================================

def _wait(cond, what, timeout=15.0, mq=None):
    """Wait for a CONDITION (never a fixed delay as proof): pump the main
    queue while polling."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mq is not None:
            mq.flush()
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError(f"fixture: {what} never happened")


def _observed_dictation(h, mq, target, act=None, window=10.0):
    """One dictation inserted by the REAL InsertionService into the
    insertion suite's fixture target (a certified AX surface), with the
    coordinator's own observation wiring (``_observationStarted_`` ->
    ``OutcomeObserver`` -> ``_observationFinished_`` ->
    ``EvidenceCollector.on_observation_closed``). ``act(target)`` runs
    once the observer holds its baseline (its first intact tick)."""
    from localflow.v2.insertion.service import InsertionService
    stub = h.d._insertion
    h.d._insertion = InsertionService(
        host=target, pasteboard=target.pb, keyboard=target,
        store=h.d.store, emit=h.d.v2log.emit, restore_clipboard=False,
        observation_window_sec=window, settle_sec=0.05)
    seen = {}

    def on_post(fn, a):
        if fn == h.d._observationStarted_:
            seen["observer"] = a[0].get("observer")
        elif fn == h.d._observationFinished_:
            seen["finished"] = True
    mq.on_post = on_post
    try:
        h.press()
        h.release()
        fn, a = h.run_coordinator()
        job = a[1]["job_id"]
        fn(*a)
        _wait(lambda: seen.get("observer") is not None,
              "the observation window opening", mq=mq)
        obs = seen["observer"]
        inserted = target.content
        _wait(lambda: obs.ticks >= 1 and obs._base_total is not None
              or obs.stop_reason is not None, "the observer's baseline")
        if act is not None:
            act(target)
        obs.join(window + 10)
        _wait(lambda: seen.get("finished"), "the observation closing",
              mq=mq)
        mq.flush()
        h.d.store.sync()
        return job, obs, inserted
    finally:
        mq.on_post = None
        h.d._insertion = stub


def _fix_inside(target):
    target.set_content(target.content.replace("modul ", "module "))


@case("G06 XM-MH09 (only the real observer's certified in-range edit"
      " supports a candidate, and only approval creates one app-scoped"
      " effect in the next job)")
def g06_xm_mh09_certified_edit_to_scoped_next_job():
    from fixture_target import FixtureTargetApp
    h = Harness(durations=[1.0] * 4)
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        target = FixtureTargetApp(bundle=APP_A)
        ctx = ContextReader(target=target)
        h.d._context = ctx
        h.d.supervisor = EngineWorker(TEACH_RAW)
        with MainQueue() as mq:
            job1, obs, inserted = _observed_dictation(
                h, mq, target, act=_fix_inside)
            env1 = job_envelope(store, job1) or {}
            recorded = ((env1.get("outcome") or {}).get("observation")
                        or {})
            assert obs.stop_reason == "owned_range_edited" and \
                recorded.get("stop_reason") == "owned_range_edited" and \
                "modul " in inserted, (
                "fixture: the certified edit was not observed/recorded:"
                f" observer={obs.stop_reason} envelope={recorded}"
                f" inserted={inserted!r}")
            ctx.target = None
            ctx.bundle = APP_A
            mined = h.d._learning.mine_observation_candidates()
            cands = [c for c in candidates_of(store, job1)
                     if c["source"] == "edit_observation"]
            before_text = one(store, "SELECT content_text FROM artifacts"
                              " WHERE artifact_id=(SELECT"
                              " before_artifact_id FROM"
                              " insertion_observations WHERE"
                              " observation_id=?)", (obs.observation_id,))
            start = inserted.index("modul ")
            expected_spans = [{"start": start, "end": start + len("modul")}]
            got_spans = json.loads(cands[0]["spans"]) if cands else None
            pre = dictate(h)
            pre_final = h.pastes[-1]
            out = h.d._learning.approve(cands[0]["candidate_id"]) \
                if cands else {}
            eid = out.get("entry_id")
            post = dictate(h)
            post_final = h.pastes[-1]
            ctx.bundle = APP_B
            other = dictate(h)
            other_final = h.pastes[-1]
        got = {
            "mined": mined, "candidates": len(cands),
            "observed_before_is_owned_text":
                (before_text or [None])[0] == inserted,
            "spans": got_spans,
            "pre_approval_uncorrected": "modul " in pre_final + " "
            and applied_rule_ids(store, pre) == [],
            "entry_scope": one(store, "SELECT scope_kind, scope_value FROM"
                               " vocabulary_entries WHERE entry_id=?",
                               (eid,)) if eid else None,
            "history_rows": count(store, "SELECT COUNT(*) FROM"
                                  " vocabulary_history WHERE entry_id=?",
                                  (eid,)) if eid else 0,
            "learned_entries": count(
                store, "SELECT COUNT(*) FROM vocabulary_aliases WHERE"
                " lower(alias)='modul' AND approved=1"),
            "next_in_scope_corrected": "module" in post_final
            and applied_rule_ids(store, post) == [eid],
            "other_app_uncorrected": "modul " in other_final + " "
            and applied_rule_ids(store, other) == []}
        want = {
            "mined": 1, "candidates": 1,
            "observed_before_is_owned_text": True,
            "spans": expected_spans, "pre_approval_uncorrected": True,
            "entry_scope": ("app", APP_A), "history_rows": 1,
            "learned_entries": 1, "next_in_scope_corrected": True,
            "other_app_uncorrected": True}
        bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
        assert not bad, ("the M08 -> M14 -> next-job chain broke (got,"
                         " want): " + json.dumps(bad, default=str))
    finally:
        h.close()


@case("G06 XM-MH09 control (no-edit window, outside-range typing and focus"
      " loss mint nothing)", kind="control")
def g06_xm_mh09_control_unattributable_windows_mint_nothing():
    from fixture_target import FixtureTargetApp
    h = Harness(durations=[1.0] * 3)
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        ctx = ContextReader(APP_A)
        h.d._context = ctx
        h.d.supervisor = EngineWorker(TEACH_RAW)

        def outside(t):
            t.type_text("typed before ", at=0)

        def focus_away(t):
            t.frontmost_info = {"bundle": "com.synthetic.elsewhere",
                                "name": "Elsewhere", "pid": 777}
        stops = {}
        jobs = []
        with MainQueue() as mq:
            for name, act, window in (("no_edit", None, 0.4),
                                      ("outside_range", outside, 1.0),
                                      ("focus_lost", focus_away, 10.0)):
                target = FixtureTargetApp(bundle=APP_A)
                ctx.target = target
                job, obs, _ins = _observed_dictation(h, mq, target, act,
                                                     window)
                stops[name] = (obs.stop_reason, obs.edited, obs.reanchors)
                jobs.append(job)
        assert stops["no_edit"][0] == "window_elapsed" and \
            stops["outside_range"][:2] == ("window_elapsed", False) and \
            stops["outside_range"][2] >= 1 and \
            stops["focus_lost"][0] == "focus_lost", \
            f"fixture: the negative windows did not stop as scripted: {stops}"
        mined = h.d._learning.mine_observation_candidates()
        minted = [c for j in jobs for c in candidates_of(store, j)]
        assert mined == 0 and not minted, (
            f"an unattributable window minted candidates: {minted}"
            f" (stops {stops})")
    finally:
        h.close()


# =============================================================================
# XM-MH24 — a collection-off Teach approved in scope with a counterexample
# =============================================================================

NON_FLIP = "the modular design ships"


def _mh24_world(counterexample):
    h = Harness(durations=[1.0] * 3, cfg={"log_transcripts": True})
    try:
        store = h.d.store
        ctx = ContextReader(APP_A)
        h.d._context = ctx
        h.d.supervisor = EngineWorker(TEACH_RAW)
        with MainQueue() as mq:
            hub = make_hub(h)
            assert mq.drain(hub.state, 60)
            job0 = dictate(h)
            c0, s0 = consent_rows(store), h.d.consent.state()
            show_history_row(hub, mq, job0)
            note = hub_teach(hub, mq, TEACH_FIX)
        cands = candidates_of(store, job0)
        assert len(cands) == 1 and cands[0]["example_id"] is None and \
            cands[0]["scope_kind"] == "app" and \
            cands[0]["scope_value"] == APP_A, (
            f"fixture: the collection-off Teach made {cands};"
            f" note {note.rsplit(chr(10), 1)[-1]!r}")
        out = h.d._learning.approve(cands[0]["candidate_id"],
                                    counterexamples=(counterexample,))
        job1 = dictate(h)
        final1 = h.pastes[-1]
        ctx.bundle = APP_B
        dictate(h)
        final2 = h.pastes[-1]
        return {"approval": out, "final_in_scope": final1,
                "final_out_of_scope": final2,
                "consent_rows_unchanged": consent_rows(store) == c0,
                "consent_state": (s0, h.d.consent.state()),
                "deltas": count(store, "SELECT COUNT(*) FROM"
                                " learning_vocabulary_deltas"),
                "verbatim_references": count(
                    store, "SELECT COUNT(*) FROM artifacts WHERE"
                    " role='verbatim_reference'"),
                "correction_labels": count(store, "SELECT COUNT(*) FROM"
                                           " correction_labels"),
                "job1": job1}
    finally:
        h.close()


@case("G06 XM-MH24 (a collection-off Teach approved in scope with a"
      " non-flipping counterexample changes only the next in-scope job)")
def g06_xm_mh24_collection_off_teach_approved_in_scope():
    r = _mh24_world(NON_FLIP)
    assert r["approval"].get("entry_id") and \
        r["approval"]["counterexample_check"]["tested"] == 1, \
        f"fixture: the approval did not land: {r['approval']}"
    got = {k: r[k] for k in ("consent_rows_unchanged", "consent_state",
                             "deltas", "verbatim_references",
                             "correction_labels")}
    got["in_scope_corrected"] = "module" in r["final_in_scope"]
    got["out_of_scope_uncorrected"] = \
        "modul " in r["final_out_of_scope"] + " "
    want = {"consent_rows_unchanged": True,
            "consent_state": ("disabled", "disabled"), "deltas": 1,
            "verbatim_references": 0, "correction_labels": 0,
            "in_scope_corrected": True, "out_of_scope_uncorrected": True}
    bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    assert not bad, ("the collection-off Teach → approval chain broke its"
                     " contract (got, want): "
                     + json.dumps(bad, default=str))


@case("G06 XM-MH24 control (an adverse counterexample refuses the approval;"
      " the next job stays uncorrected)", kind="control")
def g06_xm_mh24_control_adverse_counterexample():
    r = _mh24_world(TEACH_RAW)
    assert r["approval"].get("entry_id") is None and \
        r["approval"].get("flips") and r["deltas"] == 0 and \
        "modul " in r["final_in_scope"] + " ", (
        f"control: the flipping phrase did not block: {r['approval']}"
        f" deltas={r['deltas']} final={r['final_in_scope']!r}")


# =============================================================================
# XM-C123 — a typed-only note contributes nothing
# =============================================================================

def _per_job_asr(*texts):
    """ASR text per job in dictation order (a retry keeps its job's)."""
    queue, assigned = list(texts), {}

    def asr(job_id, attempt):
        if job_id not in assigned:
            assigned[job_id] = queue.pop(0)
        return assigned[job_id]
    return asr


def _profile_rows(store):
    """Every profile_* table's rows (the canary scan's haystack) and the
    evidence rows keyed without snapshot identity."""
    tables = [t for (t,) in rows(store, "SELECT name FROM sqlite_master"
                                 " WHERE type='table' AND name LIKE"
                                 " 'profile_%'")]
    dump = {t: rows(store, f"SELECT * FROM {t}") for t in tables}
    latest = one(store, "SELECT snapshot_id FROM profile_snapshots ORDER"
                 " BY rowid DESC LIMIT 1")
    evidence = sorted(rows(store, "SELECT example_id, card_id, role,"
                           " included FROM profile_evidence WHERE"
                           " snapshot_id=?", (latest[0],))) if latest else []
    return dump, evidence


def _measured(snapshot):
    m = dict(snapshot.get("measured") or {})
    return m


@case("G06 XM-C123 (a note created and edited only by typing yields no"
      " example, no candidate and no user-speech word contribution)")
def g06_xm_c123_typed_only_note_contributes_nothing():
    from localflow.v2.notes import NotesEditorModel
    h = Harness(durations=[1.0], cfg={"profile_min_words": 1})
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker("baseline spoken words for the"
                                      " profile population")
        dictate(h)
        p0 = h.d._profile.compute()
        _dump0, ev0 = _profile_rows(store)
        before = {t: count(store, f"SELECT COUNT(*) FROM {t}")
                  for t in ("training_examples", "note_evidence_links",
                            "learning_candidates")}
        notes = h.d._notes_store
        text = f"{TYPED_CANARY} typed plan about the modul rollout"
        n = notes.create_note(text, origin="typed")
        notes.append_revision(n["note_id"],
                              text.replace("modul", "module"),
                              origin="typed", trigger="autosave")
        cur = one(store, "SELECT current_revision_id FROM notes WHERE"
                  " note_id=?", (n["note_id"],))[0]
        model = NotesEditorModel(n["note_id"], cur,
                                 text.replace("modul", "module"))
        model.edit(text.replace("modul", "module") + " typed tail words")
        flushed = model.flush(notes)
        assert flushed.get("outcome") == "flushed", \
            f"fixture: the editor flush did not commit: {flushed}"
        revs = rows(store, "SELECT origin, spans_json FROM note_revisions"
                    " WHERE note_id=? ORDER BY rowid", (n["note_id"],))
        assert len(revs) == 3, f"fixture: {len(revs)} revisions"
        mined = h.d._learning.mine_observation_candidates()
        p1 = h.d._profile.compute()
        dump1, ev1 = _profile_rows(store)
        after = {t: count(store, f"SELECT COUNT(*) FROM {t}")
                 for t in before}
        m0, m1 = _measured(p0), _measured(p1)
        got = {
            "origins": sorted({o for o, _s in revs}),
            "attributed_spans": [s for _o, sj in revs
                                 for s in json.loads(sj or "[]")
                                 if len(s) < 3 or s[2] != "typed"],
            "counts": after, "mined": mined,
            "measured_changed": sorted(k for k in set(m0) | set(m1)
                                       if m0.get(k) != m1.get(k)),
            "evidence_rows_equal": ev0 == ev1,
            "canary_in_profile": TYPED_CANARY.lower() in json.dumps(
                dump1, default=str).lower()}
        want = {"origins": ["typed"], "attributed_spans": [],
                "counts": before, "mined": 0, "measured_changed": [],
                "evidence_rows_equal": True, "canary_in_profile": False}
        bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
        assert not bad, ("a typed-only note contributed evidence (got,"
                         " want): " + json.dumps(bad, default=str))
    finally:
        h.close()


@case("G06 XM-C123 control (a real dictated arrival into a note grows the"
      " eligible population and a typed fix inside it mines one"
      " candidate)", kind="control")
def g06_xm_c123_control_dictated_arrival_counts():
    from localflow.v2.notes import NotesEditorModel
    h = Harness(durations=[1.0, 1.0], cfg={"profile_min_words": 1})
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        h.d.supervisor = EngineWorker(_per_job_asr(
            "baseline spoken words for the profile population", TEACH_RAW))
        dictate(h)
        p0 = h.d._profile.compute()
        job = dictate(h)
        final = h.pastes[-1].strip()
        notes = h.d._notes_store
        intro = "typed intro line"
        n = notes.create_note(intro, origin="typed")
        model = NotesEditorModel(n["note_id"], n["revision"], intro)
        body = f"{intro} {final}"
        model.receive(body, origin="dictated", source_job_id=job,
                      inserted_at_chars=len(intro) + 1, inserted_text=final)
        assert model.flush(notes).get("outcome") == "flushed"
        p1 = h.d._profile.compute()
        model.edit(body.replace("modul ", "module "))
        assert model.flush(notes).get("outcome") == "flushed"
        h.d._learning.mine_observation_candidates()
        cands = [c for c in candidates_of(store, job)
                 if c["source"] == "note_revision"]
        links = count(store, "SELECT COUNT(*) FROM note_evidence_links"
                      " WHERE job_id=?", (job,))
        grew = _measured(p1)["eligible_examples"] == \
            _measured(p0)["eligible_examples"] + 1
        assert grew and links == 1 and len(cands) == 1, (
            f"control: population grew={grew} links={links}"
            f" candidates={len(cands)}")
    finally:
        h.close()


# =============================================================================
# XM-C125 — a verified span correction stays partial in every view
# =============================================================================

def _export_views(root):
    ex = [json.loads(line) for line in (root / "examples.jsonl")
          .read_text().splitlines() if line.strip()]
    refs = [json.loads(line) for line in (root / "references.jsonl")
            .read_text().splitlines() if line.strip()]
    return ex, refs


def _ids(examples, kind):
    return {e.get("example_id") for e in examples
            if e.get("task_kind") == kind}


VIEWS3 = ("asr_supervised", "asr_span_graft_weak", "cleanup_supervised")


@case("G06 XM-C125 (span corrections covering every word stay partial and"
      " never make the recording ASR or cleanup gold)")
def g06_xm_c125_span_corrections_never_whole_gold():
    with X.M.MWorld() as w:
        raw = "cloud report friday"
        j = w.job(raw)
        ex = j["example_id"]
        for word, fixed in (("cloud", "Claude"), ("report", "memo"),
                            ("friday", "Friday")):
            s = raw.index(word)
            w.training.add_span_correction(
                ex, "source_text", s, s + len(word), fixed,
                expected_artifact_id=j["raw_aid"],
                expected_sha256=ids.sha256_text(raw))
        env = w.envelope(ex)
        anns = [a for a in env.get("annotations") or []
                if a.get("kind") == "span_correction"]
        covered = sorted(tuple(a["span"]) for a in anns)
        assert covered == [(0, 5), (6, 12), (13, 19)], \
            f"fixture: the spans do not cover every word: {covered}"
        asr_ctrl = w.ready_asr("verbatim control words")["example_id"]
        clean_ctrl = w.ready_cleanup("cleanup control words")["example_id"]
        w.families(10)
        w.splits.assign()
        w.export("ds", VIEWS3)
        examples, refs = _export_views(w.tmp / "ds")
        te = w.training.readiness()["readiness_metrics"][
            "task_eligibility"]
        got = {
            "coverage": sorted({a.get("coverage") for a in anns}),
            "correctness": (env.get("outcome") or {}).get("correctness"),
            "asr_supervised": _ids(examples, "asr_supervised"),
            "cleanup_supervised": _ids(examples, "cleanup_supervised"),
            "refs_for_example": sorted({r.get("coverage") for r in refs
                                        if r.get("example_id") == ex}),
            "readiness_asr": te["asr_supervised"]["count"],
            "readiness_cleanup": te["cleanup_supervised"]["count"]}
        want = {"coverage": ["partial"], "correctness": "unreviewed",
                "asr_supervised": {asr_ctrl},
                "cleanup_supervised": {clean_ctrl},
                "refs_for_example": [c for c in got["refs_for_example"]
                                     if c == "partial"],
                "readiness_asr": len(got["asr_supervised"]),
                "readiness_cleanup": len(got["cleanup_supervised"])}
        bad = {k: (sorted(got[k]) if isinstance(got[k], set) else got[k],
                   sorted(v) if isinstance(v, set) else v)
               for k, v in want.items() if got[k] != v}
        assert not bad, ("a span-corrected recording became whole-example"
                         " gold (got, want): "
                         + json.dumps(bad, default=str))


# =============================================================================
# XM-MH11 — a mixed-origin note: mining and export
# =============================================================================

A_TEXT = "alpha dictated modul words"
# No word repeats across the note's regions: M12's occurrence-safe rebase
# (M12-AUDIT-17) drops a span whose covered word's count changes, so a
# shared word would end A's attribution before the witness edits it.
B_TEXT = "bravo spoken report today"
TF_ARRIVAL = "transform polished phrase"


def _mixed_note(h):
    """Two real dictations (A, B) arrive in one note between typed text
    and a transform output, through the Scratchpad editor model
    (``NotesEditorModel.receive`` -> ``flush`` -> NoteStore -> the
    collector's note evidence links)."""
    from localflow.v2.notes import NotesEditorModel
    h.d.supervisor = EngineWorker(_per_job_asr(A_TEXT, B_TEXT))
    job_a = dictate(h)
    fin_a = h.pastes[-1].strip()
    job_b = dictate(h)
    fin_b = h.pastes[-1].strip()
    notes = h.d._notes_store
    intro = f"typed intro {TYPED_CANARY}"
    n = notes.create_note(intro, origin="typed")
    model = NotesEditorModel(n["note_id"], n["revision"], intro)
    c1 = f"{intro} {fin_a}"
    model.receive(c1, origin="dictated", source_job_id=job_a,
                  inserted_at_chars=len(intro) + 1, inserted_text=fin_a)
    c2 = f"{c1} {TF_ARRIVAL}"
    model.receive(c2, origin="transform", transform_id="builtin:polish",
                  transform_revision=1, inserted_at_chars=len(c1) + 1,
                  inserted_text=TF_ARRIVAL)
    c3 = f"{c2} {fin_b}"
    model.receive(c3, origin="dictated", source_job_id=job_b,
                  inserted_at_chars=len(c2) + 1, inserted_text=fin_b)
    assert model.flush(h.d._notes_store).get("outcome") == "flushed"
    spans = json.loads(one(h.d.store, "SELECT spans_json FROM"
                           " note_revisions WHERE note_id=? ORDER BY rowid"
                           " DESC LIMIT 1", (n["note_id"],))[0])
    kinds = sorted((s[2], s[3] if len(s) > 3 else None) for s in spans)
    assert kinds == sorted([("dictated", job_a), ("dictated", job_b),
                            ("transform", None)]), \
        f"fixture: the note's span map is not the witness's: {spans}"
    links = {r[0] for r in rows(h.d.store, "SELECT job_id FROM"
                                " note_evidence_links WHERE note_id=?",
                                (n["note_id"],))}
    assert links == {job_a, job_b}, f"fixture: evidence links {links}"
    return model, c3, job_a, job_b


def _filler_families(store, n=10):
    """Synthetic filler families (no reference, no mark — never in any
    view) so the split assignment reaches its family floor
    (splits.MIN_FAMILIES) and the witnesses are assigned at all."""
    for i in range(n):
        job, fam = store.create_job()
        aid = store.write_text_artifact(
            job_id=job, stage="asr", role="raw_transcript",
            text=f"filler family {i} utterance", retention_class="training")
        ex = store.upsert_example(job_id=job, family_id=fam,
                                  consent_revision_id=
                                  store.current_consent_id())
        store.append_revision(ex, {
            "example_id": ex, "job_id": job, "family_id": fam,
            "origin": "live_capture", "attempt": 1,
            "artifact_ids": {"source_text": aid}, "outcome": {},
            "annotations": [], "missing_reasons": {}})


def _export_linked(h, dest, views=("asr_supervised",
                                    "asr_span_graft_weak")):
    _filler_families(h.d.store)
    out = h.d._splits.assign()
    assert out.get("families", 0) >= 10 and \
        not out.get("assigned", {}).get("unassigned"), \
        f"fixture: the split assignment left examples unassigned: {out}"
    h.d._exporter.build(h.tmp / dest, task_views=views)
    return _export_views(h.tmp / dest)


@case("G06 XM-MH11 (edits across dictated, typed and transform spans mine"
      " only the dictated word pair; the mixed note never exports as"
      " whole-recording gold)")
def g06_xm_mh11_mixed_note_mines_only_the_dictated_pair():
    h = Harness(durations=[1.0, 1.0])
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        model, c3, job_a, job_b = _mixed_note(h)
        # One typed revision touching the typed intro, the transform
        # output and ONE word of dictation A.
        c4 = (c3.replace("intro", "introduction")
              .replace("polished", "polish").replace("modul ", "module "))
        model.edit(c4)
        assert model.flush(h.d._notes_store).get("outcome") == "flushed"
        h.d._learning.mine_observation_candidates()
        cands_a = candidates_of(store, job_a)
        regions = [(r.get("before_words"), r.get("after_words"),
                    r.get("start"), r.get("end"))
                   for c in cands_a
                   for r in (payload_of(store, c) or {}).get("regions",
                                                               [])]
        joined = " ".join(c3.split())
        start = joined.index("modul ")
        expected = [(["modul"], ["module"], start, start + len("modul"))]
        # A second typed revision touching the typed text and ONE word of
        # dictation B (A's span ended with its edit): only B's pair.
        c5 = c4.replace("typed", "typing").replace("report", "reports")
        model.edit(c5)
        assert model.flush(h.d._notes_store).get("outcome") == "flushed"
        h.d._learning.mine_observation_candidates()
        after = {j: len(candidates_of(store, j)) for j in (job_a, job_b)}
        joined4 = " ".join(c4.split())
        b_start = joined4.index("report")
        regions_b = [(r.get("before_words"), r.get("after_words"),
                      r.get("start"), r.get("end"))
                     for c in candidates_of(store, job_b)
                     for r in (payload_of(store, c) or {}).get("regions",
                                                                 [])]
        ex_a, ex_b = (examples_of(store, j)[-1][0] for j in (job_a, job_b))
        examples, refs = _export_linked(h, "ds")
        got = {"candidates_a": len(cands_a), "regions": regions,
               "after_second_edit": after, "regions_b": regions_b,
               "asr_supervised_linked": sorted(
                   _ids(examples, "asr_supervised") & {ex_a, ex_b}),
               "linked_ref_coverage": sorted(
                   {r.get("coverage") for r in refs
                    if r.get("example_id") in (ex_a, ex_b)}
                   - {"partial"})}
        want = {"candidates_a": 1, "regions": expected,
                "after_second_edit": {job_a: 1, job_b: 1},
                "regions_b": [(["report"], ["reports"], b_start,
                               b_start + len("report"))],
                "asr_supervised_linked": [], "linked_ref_coverage": []}
        bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
        assert not bad, ("the mixed-origin note mined or exported more"
                         " than the admissible speech correction (got,"
                         " want): " + json.dumps(bad, default=str))
    finally:
        h.close()


@case("G06 XM-MH11 control (an edit inside A alone mints one A candidate;"
      " audio-reviewed verbatims export as asr_supervised)", kind="control")
def g06_xm_mh11_control_single_region_and_verbatim_export():
    from localflow.v2.training_data import TrainingDataService
    h = Harness(durations=[1.0, 1.0])
    try:
        store = h.d.store
        h.d.consent.set("enabled")
        h.d._context = ContextReader(APP_A)
        model, c3, job_a, job_b = _mixed_note(h)
        model.edit(c3.replace("modul ", "module "))
        assert model.flush(h.d._notes_store).get("outcome") == "flushed"
        h.d._learning.mine_observation_candidates()
        per_job = {j: len(candidates_of(store, j)) for j in (job_a, job_b)}
        tds = TrainingDataService(store)
        ex_a, ex_b = (examples_of(store, j)[-1][0] for j in (job_a, job_b))
        for ex, text in ((ex_a, A_TEXT), (ex_b, B_TEXT)):
            tds.set_verbatim(ex, text, listened_audio=True)
        gates = {ex: h.d._review.verified_asr_eligible(ex).get("reason")
                 for ex in (ex_a, ex_b)}
        examples, _refs = _export_linked(h, "ds_ctrl")
        manifest = json.loads((h.tmp / "ds_ctrl" / "dataset_manifest.json")
                              .read_text())
        exported = _ids(examples, "asr_supervised") & {ex_a, ex_b}
        assert per_job == {job_a: 1, job_b: 0} and \
            exported == {ex_a, ex_b}, (
            f"control: candidates {per_job}; asr_supervised"
            f" {sorted(exported)}; gates {gates}; excluded"
            f" {manifest.get('excluded')}; exported"
            f" {[(e.get('example_id'), e.get('task_kind')) for e in examples]}"
            f" ids {[ex_a, ex_b]} counts {manifest.get('counts')}")
    finally:
        h.close()


# =============================================================================
# runner (the remediation suite's, same record shape)
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
    print("xm g06 c2:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/crossmilestone/test_xm_g06_c2.py",
            "code": X.code_stamp(
                "tests/v2/crossmilestone/test_xm_g06_c2.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
