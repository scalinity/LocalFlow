"""EV-12 / EV-19 / M10: styles, snippets and developer registries
through the REAL coordinator.

Drives the shared lifecycle Harness (real AppDelegate + real worker
loop + stubbed insertion) with scripted supervisors and a scripted
context collector: the M10 freeze at hotkey-down, the finalize
re-resolution, Raw mode's stage skips, the resolved writing category
reaching cleanup's destination profile, snippet expansion +
protection through the live pipeline, the S29.4 profile/skill
provenance in the evidence envelope, the one-job override, the
quick-menu exposure and the Hub command surface.

EV-19 producer fixtures live here: snippet expansion, explicit literal
text and a changed profile between jobs.

Run: .venv/bin/python tests/v2/profiles/test_profiles_pipeline.py
"""

import json
import pathlib
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] /
                       "lifecycle"))

import localflow.app as app_mod  # noqa: E402
from localflow.app import AppDelegate  # noqa: E402
from localflow.hotkey import HotkeyListener  # noqa: E402
from localflow.v2 import ids, store as store_mod  # noqa: E402
from localflow.v2.context.snapshot import (  # noqa: E402
    ContextSnapshot as CtxSnap, FieldContext, TargetSnapshot)

CFG = {
    "model": "test", "hotkey": "fn", "sample_rate": 16000,
    "min_duration_sec": 0.3, "max_duration_sec": 0, "append_space": False,
    "restore_clipboard": False, "input_device": None, "cleanup": "llm",
    "cleanup_model": "test-llm", "log_transcripts": False,
    "capture_journal": True, "hands_free": "off", "mouse_trigger": None,
    "cleanup_not_ready_policy": "basic",
    "normalization_profile": "technical", "normalization_locale": "en-US",
    "context_enabled": False,  # a scripted collector replaces it per test
    "skill_manifest_paths": [],
    "workspace_skill_dirs": [],
}


class FakeRecorder:
    def __init__(self, durations):
        self.durations = list(durations)
        self.recording = False
        self.journal = None
        self.stats = {}
        self.health = {"ok": True}

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        dur = self.durations.pop(0)
        journal, self.journal = self.journal, None
        js = journal.finalize() if journal is not None else {}
        self.stats = {
            "duration_sec": dur, "device": "fake", "voiced_pct": 50.0,
            "trailing_silence_sec": 0.0, "overflow_blocks": 0,
            "journal_dropped_blocks": js.get("queue_dropped", 0),
            "incomplete_tail": js.get("finalized") is False,
        }
        return np.zeros(int(dur * 16000), dtype=np.float32)

    def capture_health(self):
        return dict(self.health)


class FakeOverlay:
    def __init__(self):
        self.visible = False
        self.mode = None

    def showWithMode_(self, mode):
        self.visible = True
        self.mode = mode

    def setMode_(self, mode):
        self.mode = mode

    def hide(self):
        self.visible = False


class M10Supervisor:
    """Fake worker capturing the FULL clean payload (the M07 permitted
    context) so destination profile and protected spans are assertable."""

    def __init__(self, asr_text):
        self.asr_text = asr_text
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"
        self.clean_kwargs = None

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "decode_ranges": [[0, 16000]],
                "text": self.asr_text}

    def clean(self, *, job_id, attempt, raw_text, **kwargs):
        self.clean_kwargs = kwargs
        return {"attempt": attempt, "generation": self.generation,
                "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
                "text": raw_text, "observations": []}

    def wait_engine(self, engine, timeout):
        return "ready"

    def shutdown(self, timeout=5.0):
        pass


class StubInsertionService:
    def __init__(self, delegate):
        self.d = delegate
        self.pastes = []

    def submit(self, text, job, on_done, on_observation=None):
        from localflow.v2.insertion import InsertionResult
        self.pastes.append(text)
        self.d._insertionDone_(
            InsertionResult.legacy_posted(len(text)), job)

    def note_new_dictation(self):
        pass

    def note_session_locked(self):
        pass

    def note_session_unlocked(self):
        pass

    def undo_last(self):
        return {"outcome": "nothing_to_undo"}

    def paste_again(self):
        return {"outcome": "nothing_to_paste"}

    def last_result(self):
        return None


class FakeContextCollector:
    """The scripted M06 surface: a fixed PTT identity and a finalized
    snapshot (origin/workspace/document) the M10 upgrade consumes."""

    def __init__(self, bundle, category, *, origin=None, workspace=None,
                 document_url=None):
        self.bundle = bundle
        self.category = category
        self.origin = origin
        self.workspace = workspace
        self.document_url = document_url

    def capture_identity(self):
        return TargetSnapshot(
            target_snapshot_id=ids.new_id("tgt"),
            app_bundle=self.bundle, app_name=self.bundle, app_pid=42,
            category=self.category)

    def begin(self, identity):
        return ("handle", identity)

    def abandon(self):
        pass

    def finalize(self, *, job_id, target_snapshot_id=None):
        field = FieldContext(role="AXTextArea",
                             classification="text",
                             document_url=self.document_url)
        return CtxSnap(
            context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
            target=TargetSnapshot(
                target_snapshot_id=target_snapshot_id or ids.new_id("tgt"),
                app_bundle=self.bundle, app_name=self.bundle, app_pid=42,
                category=self.category),
            field=field, site_origin=self.origin,
            workspace=self.workspace)

    def take_downstream(self, handle):
        return None


class Harness:
    def __init__(self, durations, cfg=None, supervisor=None, context=None):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        app_mod.V2_DB = tmp / "v2.db"
        app_mod.V2_ARTIFACTS = tmp / "artifacts"
        app_mod.V2_BACKUPS = tmp / "backups"
        app_mod.V2_EVENTS_DIR = tmp / "events"
        app_mod.V2_JOURNAL = tmp / "journal"
        self.tmp = tmp
        merged = dict(CFG)
        merged.update(cfg or {})
        d = AppDelegate.alloc().init()
        d.configure(merged)
        d.recorder = FakeRecorder(durations)
        d.overlay = FakeOverlay()
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation,
                            d.cancelDictation)
        hk.physically_down = lambda: True
        d.hotkey = hk
        d.supervisor = supervisor
        d._insertion = StubInsertionService(d)
        if context is not None:
            d._context = context
        self.d = d
        self.hk = hk

    def close(self):
        self.d.store.sync()
        self.d.store.close()
        self.d.v2log.close()
        self._tmp.cleanup()

    def press_release(self):
        self.hk.held = True
        self.hk.on_press()
        self.hk.held = False
        self.hk.on_release()

    def run_coordinator(self, timeout=15.0):
        results = []
        real_after = app_mod.AppHelper.callAfter

        def fake_after(fn, *a):
            results.append((fn, a))

        app_mod.AppHelper.callAfter = fake_after
        try:
            t = threading.Thread(target=self.d._worker, daemon=True)
            t.start()
            deadline = time.monotonic() + timeout
            while not results and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.05)
        finally:
            app_mod.AppHelper.callAfter = real_after
        assert results, "coordinator did not finish the job"
        for fn, a in results:
            if fn == self.d._finishWithText_:
                return (fn, a)
        raise AssertionError("no finish callback captured")


def make_mode_item(d):
    """The status menu is built in applicationDidFinishLaunching, which
    never runs headless — create the one item _set_mode_menu writes."""
    from AppKit import NSMenuItem
    d.mode_menu_item = NSMenuItem.alloc()\
        .initWithTitle_action_keyEquivalent_("", None, "")
    return d.mode_menu_item


def latest_envelope(store):
    row = store.latest_example()
    assert row, "no training example"
    ex_id = row[0]
    return ex_id, store.latest_revision(ex_id)


def test_default_pipeline_unchanged_without_rules():
    """Regression: zero rules + no override = exactly the shipped
    behavior — Clean mode, the config normalization profile, and the
    category-derived destination profile."""
    sup = M10Supervisor("the timeout is thirty seconds")
    ctx = FakeContextCollector("com.microsoft.VSCode", "ide")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "the timeout is 30 seconds", text
        m10 = job["m10"]
        assert m10["wp"].mode == "clean"
        assert m10["wp"].source == "category_default"
        assert m10["wp"].category == "coding"
        # The derived writing category reaches cleanup (M07 hints).
        assert sup.clean_kwargs["destination_profile"] == "coding"
        # No skills/snippets configured: registries are empty but real.
        assert m10["snippet_snapshot"] is None or \
            len(m10["snippet_snapshot"].snippets) == 0
        assert m10["skills"].manifest_count == 0
    finally:
        h.close()
    print("ok  default: Clean + config profile + coding category hints")


def test_raw_mode_rule_skips_stages():
    sup = M10Supervisor("the timeout is thirty percent")
    ctx = FakeContextCollector("com.apple.Terminal", "terminal")
    h = Harness([1.0], supervisor=sup, context=ctx)
    states = []
    try:
        rid = h.d._styles.add_rule(
            name="Terminal raw", scope_kind="app",
            scope_value="com.apple.Terminal", mode="raw")
        make_mode_item(h.d)
        h.d.consent.set("enabled", note="test")  # envelope assertions
        real_state = h.d._job_state

        def spy(job_id, state, reason=None, retry=False):
            states.append(state)
            real_state(job_id, state, reason=reason, retry=retry)

        h.d._job_state = spy
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        h.d._job_state = real_state
        assert text == "the timeout is thirty percent", text
        assert "normalizing" not in states, states
        assert "cleaning" not in states, states
        assert sup.clean_kwargs is None  # cleanup never ran
        assert job["m10"]["wp"].mode == "raw"
        assert job["m10"]["wp"].rule_id == rid
        # The quick-menu line exposes the effective mode (S15).
        assert "Raw" in h.d.mode_menu_item.title()
        # The recorded path is honest about raw mode.
        env_ex, env = latest_envelope(h.d.store)
        assert env["cleanup"]["applied_path"] == "raw"
    finally:
        h.close()
    print("ok  raw mode: normalization and cleanup skipped, honest path")


def test_number_policy_rule_applies_per_destination():
    sup = M10Supervisor("we retried three times today")
    ctx = FakeContextCollector("com.apple.Terminal", "terminal")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d._styles.add_rule(
            name="Terminal standard numbers", scope_kind="app",
            scope_value="com.apple.Terminal", mode="clean",
            number_policy="standard")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        # Standard keeps bare integers as words (the technical default
        # would render "3 times").
        assert text == "we retried three times today", text
        assert job["m10"]["wp"].number_policy == "standard"
        assert job["norm_policy"].profile == "standard"
        assert sup.clean_kwargs["destination_profile"] == "terminal"
    finally:
        h.close()
    print("ok  number policy: per-destination profile through the job")


def test_one_job_override_consumed_once():
    sup = M10Supervisor("one two three")
    ctx = FakeContextCollector("com.apple.Notes", "editor")
    h = Harness([1.0, 1.0], supervisor=sup, context=ctx)
    try:
        out = h.d.hubSetNextJobMode("raw")
        assert out == {"outcome": "set"}
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "one two three"  # raw: nothing converted
        assert job["m10"]["wp"].source == "job_override"
        assert h.d._next_job_mode is None  # consumed
        # The next dictation runs under the rules again (Clean).
        sup.asr_text = "we retried three times today"
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert job["m10"]["wp"].source != "job_override"
        assert text == "we retried 3 times today", text
    finally:
        h.close()
    print("ok  one-job override: consumed by exactly one job")


def test_snippet_expansion_and_protection_through_pipeline():
    sup = M10Supervisor("please sign off comma Danny")
    ctx = FakeContextCollector("com.apple.mail", "mail")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d._snip_store.add_snippet(
            trigger="sign off", name="Sign-off",
            content="Best,\n{{name}}\nLocalFlow", kind="signature")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert "Best,\nDanny\nLocalFlow" in text, text
        # The expansion is protected for cleanup: the exact content is
        # a protected span the clean op received.
        spans = sup.clean_kwargs.get("protected_spans") or []
        assert spans, "no protected spans reached cleanup"
        norm_text = job["normalized"]
        protected_text = [norm_text[s:e] for s, e in spans]
        assert any("Best," in t for t in protected_text), protected_text
        # Usage recorded as statistics (one hit, state counter quiet).
        def usage(db):
            return db.execute(
                "SELECT usage_count FROM snippets").fetchone()[0]
        assert h.d.store.submit(usage) == 1
    finally:
        h.close()
    print("ok  snippet: live expansion + protection spans + usage hit")


def test_ev19_evidence_provenance_and_changed_profile():
    """EV-19 producer fixtures: snippet expansion + explicit literal
    text + a changed profile between jobs, all in the S29.4 envelope."""
    sup = M10Supervisor("sign off")
    ctx = FakeContextCollector("com.apple.mail", "mail")
    h = Harness([1.0, 1.0, 1.0], supervisor=sup, context=ctx)
    try:
        make_mode_item(h.d)
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(
            trigger="sign off", name="Sign-off", content="Best,\nX")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "Best,\nX", text
        ex1, env1 = latest_envelope(h.d.store)
        norm1 = env1["normalization"]
        assert norm1["snippets"]["expansions"] == 1
        assert norm1["snippets"]["rule_ids"], norm1["snippets"]
        prof1 = env1["profile"]
        assert prof1["mode"] == "clean"
        assert prof1["category"] == "email"
        assert prof1["style_revision"].startswith("m10:")
        assert "skill_registry_revision" in prof1
        # Job 2: change the profile between jobs (EV-19) — a raw rule
        # for this app changes BOTH the mode and the envelope.
        sup.asr_text = "sign off"  # raw mode: trigger stays literal
        h.d._styles.add_rule(
            name="Mail raw", scope_kind="app", scope_value="com.apple.mail",
            mode="raw")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text2, job2 = args
        assert text2 == "sign off", text2
        ex2, env2 = latest_envelope(h.d.store)
        assert ex2 != ex1
        assert env2["profile"]["mode"] == "raw"
        assert env2["profile"]["style_revision"] != \
            prof1["style_revision"]
        # Raw mode skips normalization entirely: the honest absent
        # stage (not a fabricated empty one).
        assert env2["normalization"] is None, env2["normalization"]
        # Explicit literal text (EV-19): the escape wins over the
        # snippet trigger and the envelope keeps the ledger honest.
        sup.asr_text = "write the phrase sign off alone"
        h.d._styles.delete_rule(
            next(r.rule_id for r in h.d._styles.rules()))
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text3, _ = args
        assert "sign off" in text3 and "Best," not in text3
        ex3, env3 = latest_envelope(h.d.store)
        assert env3["profile"]["mode"] == "clean"
        assert env3["normalization"]["snippets"] is None
    finally:
        h.close()
    print("ok  EV-19: snippet/literal/changed-profile provenance")


def test_ac05_verbatim_gate_on_snippet_example():
    """M10-AC05: generated snippet text is not an acoustic reference —
    the M09 per-example listen gate refuses verbatim without listening,
    even though the applied output contains the expanded content."""
    from localflow.v2.training_data import TrainingDataService
    sup = M10Supervisor("sign off")
    ctx = FakeContextCollector("com.apple.mail", "mail")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(
            trigger="sign off", name="Sign-off", content="Best,\nX")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        ex_id, env = latest_envelope(h.d.store)
        assert env["normalization"]["snippets"]
        svc = TrainingDataService(h.d.store)
        try:
            svc.set_verbatim(ex_id, "Best, X", listened_audio=False)
            raise AssertionError("unlistened verbatim accepted")
        except ValueError:
            pass
        # With listening (the gate's own honest path), it saves — the
        # gate governs provenance, not the presence of snippets.
        rev = svc.set_verbatim(ex_id, "Best, X", listened_audio=True)
        assert rev
    finally:
        h.close()
    print("ok  AC05: snippet-expanded example keeps the listen gate")


def test_hub_commands_and_menu():
    sup = M10Supervisor("slash brainstorm now")
    ctx = FakeContextCollector("com.apple.Terminal", "terminal")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        eff = h.d.hubEffectiveProfile()
        assert eff["styles_available"] and eff["snippets_available"]
        assert eff["next_job_mode"] is None
        assert "raw" in eff["modes"] and "prompt_engineer" in eff["modes"]
        # A manifest skill resolves through the live pipeline (the
        # registry feeds layer 3 like dictionary skills).
        manifest = pathlib.Path(h.tmp) / "manifest.json"
        manifest.write_text(json.dumps(
            {"skills": [{"name": "brainstorm",
                         "aliases": ["idea storm"]}]}),
            encoding="utf-8")
        make_mode_item(h.d)
        h.d._skill_manifest_paths = (str(manifest),)
        h.d._skill_cache_key = None  # force re-discovery
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "/brainstorm now", text
        skills = job["m10"]["skills"]
        assert "brainstorm" in skills.policy_skills
        assert skills.manifest_count == 1
        # Preview + collision commands.
        prev = h.d.hubPreviewPhrase("slash idea storm")
        assert prev["output"] == "/brainstorm", prev
        h.d._snip_store.add_snippet(trigger="idea storm", name="x",
                                    content="template")
        col = h.d.hubSnippetCollisionPreview("idea storm")
        assert any(c["kind"] == "ambiguous_with_skill" for c in col), col
        # The menu line reflects the last destination.
        assert "Mode: Clean" in h.d.mode_menu_item.title()
    finally:
        h.close()
    print("ok  hub commands: effective profile, preview, collisions,"
          " manifest skill live")


def test_scope_upgrade_keeps_manifest_skills():
    """Review C2 regression: the M06 finalize scope upgrade rebuilds
    the job's policy from the widened vocabulary snapshot — the frozen
    manifest skills must survive it (AC03 on site-resolving
    destinations, the exact ai_prompt case the feature targets)."""
    sup = M10Supervisor("slash brainstorm now")
    ctx = FakeContextCollector("com.google.Chrome", "browser",
                               origin="https://claude.ai")
    h = Harness([1.0, 1.0], supervisor=sup, context=ctx)
    try:
        manifest = pathlib.Path(h.tmp) / "skills.json"
        manifest.write_text(json.dumps(
            {"skills": [{"name": "brainstorm"}]}), encoding="utf-8")
        h.d._skill_manifest_paths = (str(manifest),)
        h.d._skill_cache_key = None
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert job.get("scope_upgraded") is True, "upgrade branch ran"
        assert text == "/brainstorm now", text
        assert "brainstorm" in job["norm_policy"].registered_skills
        # The envelope's registry and the pipeline agree.
        h.d.consent.set("enabled", note="test")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        _, env = latest_envelope(h.d.store)
        assert text == "/brainstorm now", text
        assert env["profile"]["manifest_skills"] == 1
        assert env["profile"]["category"] == "ai_prompt"
    finally:
        h.close()
    print("ok  review C2: scope upgrade keeps manifest skills (AC03)")


def test_finalize_only_rule_reaches_normalization():
    """Review W3 regression: a site-scoped rule that only matches once
    the finalized origin resolves must change the job's normalization
    (not only the envelope's profile block)."""
    sup = M10Supervisor("we retried three times today")
    ctx = FakeContextCollector("com.google.Chrome", "browser",
                               origin="https://chat.openai.com")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d._styles.add_rule(
            name="Chat standard numbers", scope_kind="site",
            scope_value="https://chat.openai.com",
            number_policy="standard")
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert job["m10"]["wp"].number_policy == "standard"
        assert job["norm_policy"].profile == "standard"
        assert text == "we retried three times today", text
    finally:
        h.close()
    print("ok  review W3: finalize-only rule changes normalization")


def test_stale_workspace_recorded_on_switch():
    """Review W2 regression: switching workspaces between jobs records
    stale_workspace in the rebuilt registry (S29.4 provenance that was
    previously always False). Workspace skills resolve from the active
    document's directory."""
    sup = M10Supervisor("ok")
    td_ctx = FakeContextCollector(
        "com.microsoft.VSCode", "ide", workspace="project-a",
        document_url=None)
    h = Harness([1.0, 1.0], supervisor=sup, context=td_ctx,
                cfg={"workspace_skill_dirs": [".claude/skills"]})
    try:
        ws_a = pathlib.Path(h.tmp, "project-a", ".claude", "skills",
                            "ws-one")
        ws_a.mkdir(parents=True)
        (ws_a / "SKILL.md").write_text(
            "---\nname: ws-one\n---\nbody\n", encoding="utf-8")
        (pathlib.Path(h.tmp, "project-a", "main.py")
         ).write_text("x", encoding="utf-8")
        td_ctx.document_url = str(pathlib.Path(h.tmp, "project-a",
                                               "main.py"))
        fn, args = (h.press_release(), h.run_coordinator())[1]
        _, job1 = args
        assert "ws-one" in job1["m10"]["skills"].policy_skills
        assert job1["m10"]["skills"].stale_workspace is False
        # Job 2 in a DIFFERENT workspace (its skill dir exists too):
        ws_b = pathlib.Path(h.tmp, "project-b", ".claude", "skills",
                            "ws-two")
        ws_b.mkdir(parents=True)
        (ws_b / "SKILL.md").write_text(
            "---\nname: ws-two\n---\nbody\n", encoding="utf-8")
        (pathlib.Path(h.tmp, "project-b", "main.py")
         ).write_text("x", encoding="utf-8")
        td_ctx.workspace = "project-b"
        td_ctx.document_url = str(pathlib.Path(h.tmp, "project-b",
                                               "main.py"))
        fn, args = (h.press_release(), h.run_coordinator())[1]
        _, job2 = args
        skills2 = job2["m10"]["skills"]
        assert "ws-two" in skills2.policy_skills
        assert "ws-one" not in skills2.policy_skills
        assert skills2.stale_workspace is True, "stale flag recorded"
    finally:
        h.close()
    print("ok  review W2: workspace switch records stale_workspace")


def test_profile_scoped_vocabulary_applies_in_category():
    """Review W3-CA1 regression: an APPROVED profile-scoped dictionary
    entry now applies in its category destination (the freeze derives
    the writing category from the PTT identity)."""
    sup = M10Supervisor("check clod code now")
    ctx = FakeContextCollector("com.microsoft.VSCode", "ide")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        h.d._vocab.approve_entry(next(
            e.entry_id for e in h.d._vocab.entries()
            if e.canonical == "Claude Code"))
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "check Claude Code now", text
        assert job["m10"]["wp"].profile_name == "coding"
    finally:
        h.close()
    print("ok  profile-scoped vocabulary applies in coding destinations")


def test_degraded_vocabulary_keeps_manifest_skills():
    """The vocabulary-store-failure branch: manifest skills still feed
    layer 3 without any dictionary (skills-only context)."""
    sup = M10Supervisor("slash brainstorm now")
    ctx = FakeContextCollector("com.apple.Terminal", "terminal")
    h = Harness([1.0], supervisor=sup, context=ctx)
    try:
        manifest = pathlib.Path(h.tmp) / "skills.json"
        manifest.write_text(json.dumps(
            {"skills": [{"name": "brainstorm"}]}), encoding="utf-8")
        h.d._skill_manifest_paths = (str(manifest),)
        h.d._skill_cache_key = None
        h.d._vocab = None  # the degraded case
        fn, args = (h.press_release(), h.run_coordinator())[1]
        text, job = args
        assert text == "/brainstorm now", text
    finally:
        h.close()
    print("ok  degraded vocabulary: manifest skills still register")


def main():
    test_default_pipeline_unchanged_without_rules()
    test_raw_mode_rule_skips_stages()
    test_number_policy_rule_applies_per_destination()
    test_one_job_override_consumed_once()
    test_snippet_expansion_and_protection_through_pipeline()
    test_ev19_evidence_provenance_and_changed_profile()
    test_ac05_verbatim_gate_on_snippet_example()
    test_hub_commands_and_menu()
    test_scope_upgrade_keeps_manifest_skills()
    test_finalize_only_rule_reaches_normalization()
    test_stale_workspace_recorded_on_switch()
    test_profile_scoped_vocabulary_applies_in_category()
    test_degraded_vocabulary_keeps_manifest_skills()
    print("all profiles pipeline tests passed")


if __name__ == "__main__":
    main()
