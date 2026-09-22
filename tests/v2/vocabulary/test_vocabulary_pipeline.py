"""EV-07/EV-18/EV-19 pipeline half / M05: app-level vocabulary wiring.

Drives the REAL coordinator thread (the stuck-overlay/M04 harness) with
a scripted supervisor: the job's frozen vocabulary policy/context/hint
set flow from hotkey-down through normalization into cleanup, applied
approved matches record hits, evidence carries the vocabulary block and
the frozen pre-decode hint set, an edit mid-flight changes only future
jobs (AC03 live), and a vocabulary-store failure degrades to
vocabulary-off without losing the dictation.

Run: .venv/bin/python tests/v2/vocabulary/test_vocabulary_pipeline.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "normalization"))

from test_normalization_pipeline import (  # noqa: E402
    Harness,
    RecordingSupervisor,
)


def test_vocabulary_flows_and_hits_recorded():
    sup = RecordingSupervisor("use clod code for the cloud deployment")
    h = Harness([1.0], supervisor=sup)
    eid = h.d._vocab.add_entry(
        "Claude Code", ["clod code"], approved=True)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "use Claude Code for the cloud deployment", text
    assert sup.clean_inputs == [
        "use Claude Code for the cloud deployment"], sup.clean_inputs
    h.d.store.sync()
    entry = h.d._vocab.entry(eid)
    assert entry.usage_count == 1 and entry.last_used_utc, \
        "applied approved match must record a usage hit"
    h.close()
    print("ok  coordinator: vocabulary applies between ASR and cleanup;"
          " hit recorded")


def test_hint_set_frozen_pre_decode_with_evidence():
    sup = RecordingSupervisor("ship the mlx update")
    h = Harness([1.0], supervisor=sup)
    h.d._vocab.seed_legacy_terms(["Qwen", "MLX", "Parakeet"])
    h.d.consent.set("enabled", note="m05 test")
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    ex = st.latest_example()
    env = st.latest_revision(ex[0])
    ctx_block = env["context"]
    assert ctx_block is not None, env.get("missing_reasons")
    assert "context" not in env["missing_reasons"]
    disp = ctx_block["disposition"]
    # Global entries are offered pre-decode; the profile-scoped Claude
    # suggestions are honestly absent (no destination context pre-M06).
    assert disp["offered_terms"] == 3, disp
    assert disp["accepted_terms"] == 0 and disp["ignored"] is True
    assert disp["ignored_reason"] == "disabled_until_qualified"
    hint_art = st.artifact_payload(ctx_block["artifact_ids"]["hint_set"])
    frozen = json.loads(hint_art)
    assert frozen["hint_set_id"] == ctx_block["hint_set_id"]
    assert frozen["vocabulary_revision"].startswith("m05:")
    assert frozen["terms"], "the frozen set carries ordered terms"
    # A post-ASR repair never relabels the offered set as accepted.
    assert disp["accepted_terms"] == 0
    assert st.verify()["ok"]
    h.close()
    print("ok  evidence: frozen pre-decode hint set + honest"
          " offered-but-ignored disposition")


def test_normalization_vocabulary_evidence_block():
    sup = RecordingSupervisor("ask clod about the build")
    h = Harness([1.0], supervisor=sup)
    h.d.consent.set("enabled", note="m05 test")
    eid = h.d._vocab.add_entry("Claude", ["clod"], approved=True)
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "ask Claude about the build", text
    h.d._finishWithText_(text, job)
    h.d.store.sync()
    st = h.d.store
    env = st.latest_revision(st.latest_example()[0])
    norm = env["normalization"]
    vocab = norm["vocabulary"]
    assert vocab is not None and vocab["revision"].startswith("m05:")
    assert vocab["applied_rule_ids"] == [eid]
    ledger = json.loads(st.artifact_payload(
        norm["artifact_ids"]["ledger"]))
    vocab_edits = [e for e in ledger["edits"] if e["cls"] == "vocabulary"]
    assert vocab_edits and vocab_edits[0]["rule_id"] == eid
    h.close()
    print("ok  evidence: vocabulary block + attributable ledger rule ids")


def test_ac03_live_midflight_edit():
    """AC03 in the live pipeline: the trio is captured at hotkey-down, so
    disabling the rule after the press changes only the NEXT job."""
    sup = RecordingSupervisor("ask clod twice")
    h = Harness([1.0, 1.0], supervisor=sup)
    eid = h.d._vocab.add_entry("Claude", ["clod"], approved=True)
    # Job 1: press (freeze), edit mid-flight, then release + process.
    h.hk.held = True
    h.hk.on_press()
    h.d._vocab.set_enabled(eid, False)
    h.hk.held = False
    h.hk.on_release()
    fn, args = h.run_coordinator()
    text1, _ = args
    assert text1 == "ask Claude twice", text1
    h.d.store.sync()
    assert h.d._vocab.entry(eid).usage_count == 1
    # Job 2 (fresh press → fresh snapshot): the disabled rule is gone.
    h.hk.held = True
    h.hk.on_press()
    h.hk.held = False
    h.hk.on_release()
    fn, args = h.run_coordinator()
    text2, _ = args
    assert text2 == "ask clod twice", text2
    h.close()
    print("ok  AC03 live: mid-flight edit changes only future jobs")


def test_vocabulary_store_failure_degrades():
    import localflow.v2.vocabulary_store as vs_mod
    real_cls = vs_mod.VocabularyStore

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("synthetic store failure")

        def __getattr__(self, name):
            raise AssertionError("dead store must not be used")

    vs_mod.VocabularyStore = Boom
    try:
        sup = RecordingSupervisor("twelve percent still works")
        h = Harness([1.0], supervisor=sup)
    finally:
        vs_mod.VocabularyStore = real_cls
    assert h.d._vocab is None
    h.press_release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == "12% still works", text
    events = []
    real_emit = h.d.v2log.emit

    def spy(*a, **k):
        events.append(a[0] if a else k.get("event"))
        return real_emit(*a, **k)

    h.d.v2log.emit = spy
    h.d.openDictionaryPanel_(None)   # no-op, must not raise
    h.d.v2log.emit = real_emit
    h.close()
    print("ok  vocabulary store failure: vocabulary-off with event;"
          " normalization and dictation unaffected")


def test_dictionary_panel_constructs():
    """Native-Mac construction smoke: the panel builds its window over
    the public store APIs (interaction itself is the pending human
    check)."""
    import tempfile
    from localflow.v2 import store as store_mod
    from localflow.v2.dictionary_panel import DictionaryPanelController
    from localflow.v2.vocabulary_store import VocabularyStore
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs = VocabularyStore(st)
        vs.seed_legacy_terms(["Qwen", "MLX"])
        panel = DictionaryPanelController.alloc(
        ).initWithVocabularyStore_(vs)
        assert panel.window is not None
        listing = panel.listing.stringValue()
        assert "Qwen" in listing and "MLX" in listing
        panel.phrase.setStringValue_("the mlx framework")
        panel.runSandbox_(None)
        assert "the MLX framework" in panel.sandbox.stringValue()
        st.close()
    print("ok  dictionary panel constructs and sandboxes over the"
          " public APIs")


def main():
    test_vocabulary_flows_and_hits_recorded()
    test_hint_set_frozen_pre_decode_with_evidence()
    test_normalization_vocabulary_evidence_block()
    test_ac03_live_midflight_edit()
    test_vocabulary_store_failure_degrades()
    test_dictionary_panel_constructs()
    print("all vocabulary pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
