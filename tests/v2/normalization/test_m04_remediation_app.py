"""M04 remediation: app-seam regressions (M04-AUDIT-13, -16, -21).

Drives the REAL AppDelegate methods (``_vocab_job_state``,
``_finalized_policy``, ``_m10_finalize_upgrade``, ``hubPreviewPhrase``,
``_retry_job`` and the coordinator ``_worker``) and the real
``EvidenceCollector`` on temporary roots, with the DECLARED non-native
shims of tests/v2/lifecycle (AppKit/PyObjC/sounddevice stand-ins, the
microphone and main-thread seams). A pass is a portable orchestration
result — never native verification.

Run: .venv/bin/python tests/v2/normalization/test_m04_remediation_app.py
"""

import ast
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tests" / "v2" / "lifecycle"))

import m03_helpers as h  # noqa: E402  (installs the declared shims)

from localflow.v2 import ids, store as store_mod, training  # noqa: E402
from localflow.v2.normalize import NormalizationPolicy, normalize  # noqa: E402

M10_EMPTY = {"skill_records": (), "skill_records_rev": None}


def _m10(profile):
    return dict(M10_EMPTY, norm_profile=profile)


def test_13_inherit_resolves_against_configuration():
    """Sequential jobs through the real seam: an explicit style on job A
    never becomes job B's inherited profile — on cache miss, cache hit,
    with and without a vocabulary store, and at finalize."""
    for configured, explicit in (("technical", "standard"),
                                 ("standard", "technical")):
        with tempfile.TemporaryDirectory() as td:
            a = h.App(td, cfg={"normalization_profile": configured},
                      start_coordinator=False)
            try:
                d = a.d
                pA, _, _ = d._vocab_job_state(None, m10=_m10(explicit))
                assert pA.profile == explicit
                pB, _, _ = d._vocab_job_state(None, m10=_m10(None))
                assert pB.profile == configured, (configured, pB.profile)
                pC, _, _ = d._vocab_job_state(None, m10=_m10(None))  # hit
                assert pC.profile == configured
                pN, _, _ = d._vocab_job_state(None, m10=None)       # no m10
                assert pN.profile == configured
                # Finalize: hotkey-down explicit, re-resolved to inherit.
                pF = d._finalized_policy(pA, _m10(None), None)
                assert pF.profile == configured, pF.profile
                # _m10_finalize_upgrade, unchanged skill records: the
                # explicit hotkey-down profile re-resolved to inherit
                # must reach the job's policy.
                import types
                import localflow.app as app_mod
                recs = d._m10_skill_records((), None)
                m10 = dict(_m10(None), skill_records=recs,
                           skill_records_rev=app_mod.v2_skills
                           .records_revision(recs), wp=None,
                           snippet_snapshot=None)
                job = {"job_id": "j", "m10": m10, "norm_policy": pA,
                       "norm_context": None,
                       "context_snapshot": types.SimpleNamespace(
                           field=None, workspace=None)}
                d._m10_finalize_upgrade(job)
                assert job["norm_policy"].profile == configured, \
                    job["norm_policy"].profile
                # Vocabulary store unavailable: the fallback path too.
                d._vocab_job_state(None, m10=_m10(explicit))
                vocab = d._vocab
                d._vocab = None
                try:
                    pV, _, _ = d._vocab_job_state(None, m10=_m10(None))
                finally:
                    d._vocab = vocab
                assert pV.profile == configured, pV.profile
                # The designated bare-integer contrast.
                want = "12 retries failed" if configured == "technical" \
                    else "twelve retries failed"
                assert normalize("twelve retries failed", pB).text == want
                # Pipeline info reports the configured policy, not the
                # last job's.
                assert d._pipeline_info()["normalization_policy_revision"] \
                    == NormalizationPolicy(profile=configured).policy_revision
            finally:
                a.close()
    print("ok  13: inherit → configured profile after an explicit style "
          "(miss, hit, no-m10, no-vocab, finalize)")


def test_13b_preview_inherits_configuration():
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            d._vocab_job_state(None, m10=_m10("standard"))
            out = d.hubPreviewPhrase("twelve retries failed")
            assert out["output"] == "12 retries failed", out
        finally:
            a.close()
    print("ok  13b: Hub preview under inherit uses the configured profile")


def _collector(td):
    st = store_mod.Store(pathlib.Path(td) / "v2.db")
    events = []

    def rec(name, **kw):
        events.append((name, kw))

    consent = training.ConsentManager(st, rec)
    col = training.EvidenceCollector(st, rec, consent, lambda: {"live": "x"})
    consent.set("enabled")
    return st, col, events


def test_16_retention_failure_is_visible_and_clean():
    steps = ("normalized_text_write", "normalized_text_lease",
             "ledger_write", "ledger_lease")
    for fail_at in steps:
        for text in ("twelve percent", "nothing to change"):
            if text == "nothing to change" and fail_at.startswith(
                    "normalized_text"):
                continue  # no text artifact when nothing changed
            with tempfile.TemporaryDirectory() as td:
                st, col, events = _collector(td)
                ctx = col.job_started(
                    ids.new_id("job"), ids.new_id("fam"),
                    captured_at_utc=ids.now_utc_iso(), timezone=None,
                    utc_offset_minutes=None)
                col.on_asr_result(ctx, text, model_id="m",
                                  model_revision=None,
                                  stage_duration_ms=0.0)
                real_w, real_l = st.write_text_artifact, st.grant_lease
                roles = {}

                def w(**kw):
                    if kw.get("stage") == "normalization":
                        step = ("ledger_write"
                                if kw.get("role") == "normalization_ledger"
                                else "normalized_text_write")
                        if step == fail_at:
                            raise OSError("synthetic")
                    aid = real_w(**kw)
                    roles[aid] = kw.get("role")
                    return aid

                def lease(aid, holder, days=None):
                    step = {"normalized_text": "normalized_text_lease",
                            "normalization_ledger": "ledger_lease"}.get(
                                roles.get(aid))
                    if step == fail_at:
                        raise OSError("synthetic")
                    return real_l(aid, holder, days=days)

                st.write_text_artifact, st.grant_lease = w, lease
                pol = NormalizationPolicy()
                res = normalize(text, pol)
                col.on_normalization_result(ctx, res, source_text=text,
                                            policy=pol)
                st.write_text_artifact, st.grant_lease = real_w, real_l
                col.on_cleanup_result(ctx, res.text)
                env = st.latest_revision(col.finalize(ctx))
                assert env["normalization"] is None
                assert env["missing_reasons"]["normalization"] == \
                    "retention_write_failed", env["missing_reasons"]
                if fail_at.startswith("ledger") and text != res.text:
                    # the fully published normalized text stays
                    # referenced (review R16)
                    aid = env["artifact_ids"]["normalization"]
                    assert st.artifact(aid)["role"] == "normalized_text"
                else:
                    assert "normalization" not in env["artifact_ids"]
                fails = [kw for n, kw in events
                         if n == "training.capture_failed"
                         and kw.get("stage") == "normalization"]
                assert len(fails) == 1 and fails[0]["detail"] == fail_at \
                    and fails[0]["outcome"] == "normalization_not_retained"
                # Content-free: no transcript text in the event.
                assert text not in repr(fails[0])
                assert st.verify()["ok"]
                st.close()
    # Success and skipped stages keep their honest shapes.
    with tempfile.TemporaryDirectory() as td:
        st, col, events = _collector(td)
        ctx = col.job_started(ids.new_id("job"), ids.new_id("fam"),
                              captured_at_utc=ids.now_utc_iso(),
                              timezone=None, utc_offset_minutes=None)
        col.on_asr_result(ctx, "twelve percent", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        col.on_cleanup_result(ctx, "twelve percent")
        env = st.latest_revision(col.finalize(ctx))
        assert env["missing_reasons"]["normalization"] == \
            "not_captured_at_stage"
        st.close()
    print("ok  16: each normalization write/lease failure → event with the "
          "step, retention_write_failed, no partial refs")


def _recoverable(a, text="twelve retries failed"):
    d = a.d
    jid, _ = d.store.create_job(boot_id="boot-previous",
                                captured_at_utc=h.T0, time_quality="known",
                                state="capturing")
    a.journal.mkdir(parents=True, exist_ok=True)
    h.v1_journal(a.journal / f"job-{jid}.blk", jid, h.blocks_of(12))
    d._recover_journals()
    info = next(i for i in d._recoverable if i["job_id"] == jid)
    return jid, info


def test_21_retry_uses_identified_default_snapshot():
    """A retry of retained audio after a live job with an explicit style:
    normalization runs ONCE on the new raw ASR, under the configured
    profile, and the evidence says the snapshot was a new default one."""
    import localflow.app as app_mod
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            d.consent.set("enabled")
            d._vocab_job_state(None, m10=_m10("standard"))  # previous job
            jid, info = _recoverable(a)
            rev = d.store.current_consent_id()
            d.store.upsert_example(job_id=jid, family_id=info["family_id"],
                                   consent_revision_id=rev)
            sup = h.GateSup(text="twelve retries failed")
            seen = []
            real_clean = sup.clean

            def clean(**kw):
                seen.append(kw.get("raw_text"))
                return real_clean(**kw)

            sup.clean = clean
            calls = []
            real_norm = app_mod.v2_normalize.normalize

            def counting(text, policy, context=None):
                calls.append((text, policy.profile))
                return real_norm(text, policy, context)

            app_mod.v2_normalize.normalize = counting
            try:
                a.set_sup(sup)
                a.start_coordinator()
                d._retry_job(info)
                assert a.wait_call("_finishWithText_", 15)
                a.drain()
            finally:
                app_mod.v2_normalize.normalize = real_norm
            d.store.sync()
            assert calls == [("twelve retries failed", "technical")], calls
            assert seen == ["12 retries failed"], seen
            env = a.envelope(jid)
            norm = env["normalization"]
            assert norm["policy_source"] == "retry_unscoped_default", norm
            assert norm["policy_revision"] == \
                NormalizationPolicy().policy_revision
        finally:
            a.close()
    print("ok  21: retry normalizes the new raw ASR once, configured "
          "profile, source labeled retry_unscoped_default")


def test_21b_live_job_labels_its_own_snapshot():
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td)
        try:
            d = a.d
            d.consent.set("enabled")
            a.set_sup(h.GateSup(text="twelve percent"))
            jid, _ = a.dictate(blocks=12)
            assert a.wait_call("_finishWithText_", 15)
            a.drain()
            d.store.sync()
            env = a.envelope(jid)
            assert env["normalization"]["policy_source"] == "job_snapshot"
        finally:
            a.close()
    print("ok  21b: a live job's evidence names its own captured snapshot")


# The reviewed inventory of normalization callers outside the package
# (M04-AUDIT-21). Only ONE applies its output to a dictation — the
# coordinator worker, on the raw ASR text; the rest are previews or
# diagnostics whose output is never inserted. A new caller fails this
# test until it is reviewed and added here.
CALLERS = {
    ("localflow/app.py", "_worker", "normalize"): "APPLIED: raw ASR → M04",
    ("localflow/app.py", "hubPreviewPhrase", "normalize"): "preview only",
    ("localflow/v2/vocabulary.py", "sandbox_phrase", "normalize"):
        "M05 sandbox preview only",
    ("localflow/v2/training.py", "on_normalization_result",
     "is_idempotent"): "diagnostic second pass, never applied",
}


def test_21c_caller_inventory():
    found = set()
    for py in sorted((ROOT / "localflow").rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith("localflow/v2/normalize/"):
            continue
        tree = ast.parse(py.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.attr if isinstance(f, ast.Attribute) else \
                        getattr(f, "id", None)
                    if name in ("normalize", "preview_phrase",
                                "is_idempotent"):
                        found.add((rel, fn.name, name))
    missing = set(CALLERS) - found
    extra = found - set(CALLERS)
    assert not missing, missing
    assert not extra, extra
    # The applied call passes the raw transcript.
    src = (ROOT / "localflow" / "app.py").read_text()
    assert "v2_normalize.normalize(\n                            raw," in src
    print(f"ok  21c: {len(CALLERS)} reviewed normalization callers; one "
          "applied (raw ASR), the rest preview/diagnostic")


def main():
    print(h.shim_banner())
    test_13_inherit_resolves_against_configuration()
    test_13b_preview_inherits_configuration()
    test_16_retention_failure_is_visible_and_clean()
    test_21_retry_uses_identified_default_snapshot()
    test_21b_live_job_labels_its_own_snapshot()
    test_21c_caller_inventory()
    print("all M04 app-seam remediation tests passed")
    return 0


if __name__ == "__main__":
    import os
    code = main()
    sys.stdout.flush()
    os._exit(code)
