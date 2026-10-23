"""Offline tests; provider and judge responses are always synthetic.

For a retained older worktree, point LOCALFLOW_CONTEXT_OUTCOME_REPO at the
integrated checkout. No key, provider, model download or active-app access.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
PRODUCTION = Path(os.environ.get("LOCALFLOW_CONTEXT_OUTCOME_REPO", ROOT)).resolve()
SPEC = importlib.util.spec_from_file_location("context_outcome_eval_under_test",
    ROOT / "scripts/v2/transform_context_outcome_eval.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def response(text='{"issues":[]}', model="claude-haiku-5-5", **extra):
    return {"text": text, "model": model, "reasoning": "off", "input_tokens": 100,
            "output_tokens": 30, **extra}


class FixtureTests(unittest.TestCase):
    def test_context_is_exactly_four_sources_times_three_conditions(self):
        self.assertEqual(len(evaluation.CONTEXT_CASES), 4)
        self.assertEqual(len(evaluation.PROJECTS), 2)
        self.assertEqual(len(evaluation.CONTEXT_CASES) * (len(evaluation.PROJECTS) + 1), 12)
        self.assertEqual(len({c["source"] for c in evaluation.CONTEXT_CASES}), 4)
        self.assertEqual(evaluation.GENERATOR, ("claude-sonnet-5-5", "xhigh"))
        self.assertEqual(evaluation.RECIPIENT, ("claude-haiku-5-5", "off"))

    def test_downstream_fixtures_are_four_frozen_exact_answers(self):
        self.assertEqual(len(evaluation.DOWNSTREAM_CASES), 4)
        for case in evaluation.DOWNSTREAM_CASES:
            self.assertTrue(evaluation.check_answer(json.dumps(case["expected"]), case)["correct"])
            self.assertFalse(evaluation.check_answer("{}", case)["correct"])
            self.assertFalse(evaluation.check_answer("```json\n{}\n```", case)["correct"])
            self.assertEqual(set(case["schema"]["required"]), set(case["expected"]))
            self.assertFalse(case["schema"]["additionalProperties"])

    def test_fixture_expected_answers_recomputed_without_models(self):
        expected = {c["id"]: c["expected"] for c in evaluation.DOWNSTREAM_CASES}
        orders = [("Miri", "HOLD", 725), ("Nox", "PAID", 1360), ("Luma", "VOID", 90)]
        buyer, _, cents = next(o for o in orders if o[1] == "PAID")
        self.assertEqual(expected["paid-order"], {"buyer": buyer, "total_cents": cents})
        tickets = [("orchard", "open"), ("orchard", "closed"), ("marsh", "open"),
                   ("orchard", "open"), ("orchard", "pending"), ("marsh", "closed")]
        self.assertEqual(expected["ticket-count"], {"open_orchard_count": tickets.count(("orchard", "open"))})
        slots = [("09:00", "09:30"), ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00")]
        allowed = [s for s in slots if s != slots[1] and s not in (slots[0], slots[2])]
        self.assertEqual(expected["shared-slot"], dict(zip(("start", "end"), allowed[0])))
        parcels = [("P1", 3, True, False), ("P2", 2, True, True),
                   ("P3", 1, False, False), ("P4", 4, True, False)]
        selected = sorted((p for p in parcels if p[2] and not p[3]), key=lambda p: p[1])
        self.assertEqual(expected["urgent-parcels"], {"ids": [p[0] for p in selected], "total_mass": sum(p[1] for p in selected)})

    def test_checker_rejects_type_coercion_duplicates_extra_keys_and_nonfinite(self):
        case = evaluation.DOWNSTREAM_CASES[1]
        for value in ('{"open_orchard_count": true}', '{"open_orchard_count": 2.0}',
                      '{"open_orchard_count": "2"}', '{"open_orchard_count": 2, "extra": 0}',
                      '{"open_orchard_count": 0, "open_orchard_count": 2}', '{"open_orchard_count": NaN}'):
            self.assertFalse(evaluation.check_answer(value, case)["correct"], value)
        self.assertFalse(evaluation.strict_equal(["P4", "P1"], ["P1", "P4"]))

    def test_cross_scope_labels_and_off_do_not_invent_semantic_proof(self):
        labels = evaluation.scope_labels("Use Python and CalDAV polling.", "cedar")
        self.assertEqual(len(labels["cross_scope_mentions"]), 3)
        self.assertEqual(len(labels["missing_target_signals"]), 3)
        self.assertEqual(evaluation.scope_labels("Keep the implementation unknown.", "off")["cross_scope_mentions"], [])
        self.assertIn("labels", labels["limitation"])

    def test_actual_context_ids_revisions_and_omissions_are_separate(self):
        pack = {"items": [{"id": "m1", "revision": 2}, {"id": "m2", "revision": 1}]}
        labels = evaluation.grounding_labels({"used_context": [{"id": "m1", "revision": 1}]}, pack)
        self.assertEqual(labels["invalid_used_context"], [{"id": "m1", "revision": 1}])
        self.assertEqual(labels["omitted_from_used_context"], ["m2"])
        self.assertEqual(evaluation.grounding_labels(None, {"items": []})["used_context"], [])

    def test_report_is_inert_and_partial_status_is_explicit(self):
        with tempfile.TemporaryDirectory() as td, patch.object(evaluation, "load_helpers", side_effect=AssertionError("must not load providers")):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(evaluation.main(["report", "--repo-root", td]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["context"]["status"], "BLOCKED_OR_NOT_RUN")
            self.assertIsNone(report["downstream"]["matched_accuracy_delta"])
            self.assertEqual(list(Path(td).rglob("*")), [])

    def test_missing_ledger_is_blocked_without_creating_one(self):
        with tempfile.TemporaryDirectory() as td, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(evaluation.main(["context", "--repo-root", td, "--live"]), 2)
            self.assertIn("existing_shared_budget_required", output.getvalue())
            self.assertFalse((Path(td) / "build").exists())

    def test_shared_ledger_validation_never_resets_or_raises_ceiling(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "build/transforms-intelligence/evaluation-budget.json"
            path.parent.mkdir(parents=True)
            state = {"ceiling_usd": 25, "calls": {"old": {"reserved_usd": .8, "actual_usd": None}}}
            path.write_text(json.dumps(state))
            before = path.read_bytes()
            self.assertEqual(evaluation.checked_ledger(td), path)
            self.assertEqual(path.read_bytes(), before)
            path.write_text(json.dumps({**state, "ceiling_usd": 26}))
            with self.assertRaisesRegex(ValueError, "ceiling"):
                evaluation.checked_ledger(td)


@unittest.skipUnless((PRODUCTION / "scripts/v2/transform_role_eval.py").is_file(),
                     "integrated checkout required; set LOCALFLOW_CONTEXT_OUTCOME_REPO")
class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = evaluation.load_helpers(PRODUCTION)
        cls.runtime = cls.helper.load_runtime(PRODUCTION)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lf-outcome-")
        self.root = Path(self.temp.name)
        self.ledger = self.runtime.evaluation.EvalBudget(self.root / "budget.json")
        # Any accidental live client access fails locally before a key read.
        self.no_native = patch.object(self.runtime.claude.Transformer, "_get_client", side_effect=AssertionError("offline provider guard"))
        self.no_native.start()

    def tearDown(self):
        self.no_native.stop()
        self.temp.cleanup()

    def runner(self, phase="context", **kwargs):
        return evaluation.OutcomeRunner(self.runtime, self.helper, self.root / "output", self.ledger,
            phase=phase, **kwargs)

    def test_full_identity_covers_fixtures_context_compiler_models_schema_and_role(self):
        runner = self.runner()
        case = evaluation.CONTEXT_CASES[0]
        original = runner.identity("context", case, "cedar", context={"fingerprint": "one"})
        for kwargs in ({"condition": "off"}, {"role": "recipient"}, {"repeat": 1},
                       {"case": {**case, "source": case["source"] + " Changed."}},
                       {"context": {"fingerprint": "two"}}, {"extra": {"request_schema": "changed"}}):
            args = {"role": "context", "case": case, "condition": "cedar", "context": {"fingerprint": "one"}, **kwargs}
            self.assertNotEqual(original, runner.identity(**args))
        for key in ("sources", "compiler", "verifier", "verifier_schema", "judge", "judge_schema", "recipient_system", "output_cap"):
            saved = runner.contract[key]
            runner.contract[key] = "changed"
            self.assertNotEqual(original, runner.identity("context", case, "cedar", context={"fingerprint": "one"}))
            runner.contract[key] = saved

    def test_real_selected_file_import_scope_paths_callbacks_off_and_resume(self):
        # Real production Store, MemoryStore, imports, MiniLM when cached, and
        # callbacks. Temporary test paths avoid the production build exclusion.
        sandbox = evaluation.ContextSandbox(self.runtime, self.helper, self.root / "fixture")
        try:
            packs = {key: sandbox.pack(evaluation.CONTEXT_CASES[0]["source"], key) for key in evaluation.PROJECTS}
            identities = {key: [(i["id"], i["revision"]) for i in pack["items"]] for key, pack in packs.items()}
            for key, pack in packs.items():
                self.assertTrue(pack["items"])
                self.assertTrue(sandbox.callbacks["pack_valid"](pack))
                self.assertEqual({i["scope_id"] for i in pack["items"]}, {sandbox.projects[key]})
                self.assertTrue(all(ref["author_role"] == "approved_document" for i in pack["items"] for ref in i["evidence_refs"]))
                selected = sandbox.folder / "projects" / key / "project.md"
                self.assertEqual(sandbox.memory.resolve_project(path=selected), sandbox.projects[key])
            self.assertFalse(sandbox.memory.learning())
            self.assertEqual(sandbox.audit["warm_memory_off"]["items"], 0)
            self.assertEqual(sandbox.pack("Existing runtime?", "off")["retrieval_mode"], "off")
            self.assertTrue(sandbox.audit["embedding"].startswith("minilm"))
            for mode in sandbox.audit["retrieval_modes"].values():
                self.assertIn(mode, ("semantic+lexical", "semantic_partial+lexical", "lexical_degraded"))
        finally:
            sandbox.close()
        resumed = evaluation.ContextSandbox(self.runtime, self.helper, self.root / "fixture")
        try:
            for key in evaluation.PROJECTS:
                pack = resumed.pack(evaluation.CONTEXT_CASES[0]["source"], key)
                self.assertEqual([(i["id"], i["revision"]) for i in pack["items"]], identities[key])
        finally:
            resumed.close()

    def test_production_build_ancestor_rejection_is_specific_and_not_bypassed(self):
        with self.assertRaises(self.helper.Blocked) as error:
            evaluation.ContextSandbox(self.runtime, self.helper, self.root / "build" / "fixture")
        self.assertEqual(str(error.exception), "production_rejects_build_project_roots")
        self.assertEqual(self.ledger.state()["calls"], {})

    def test_context_cli_persists_the_specific_setup_block_without_any_admission(self):
        ledger = self.root / "build/transforms-intelligence/evaluation-budget.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"ceiling_usd": 25, "calls": {}}))
        with patch.object(evaluation, "load_helpers", return_value=self.helper), patch.object(self.helper, "load_runtime", return_value=self.runtime), patch("sys.stdout", new_callable=io.StringIO) as output:
            code = evaluation.main(["context", "--repo-root", str(self.root), "--live"])
        self.assertEqual(code, 2)
        self.assertIn("production_rejects_build_project_roots", output.getvalue())
        folder = self.root / evaluation.ARTIFACT_SUBDIR / "context-outcome-v1"
        report = evaluation.summarize(evaluation.read_records(folder))
        self.assertEqual(report["blocked_units"][0]["reason"], "production_rejects_build_project_roots")
        self.assertEqual(json.loads(ledger.read_text())["calls"], {})

    def test_forgotten_source_revokes_real_callback_guard(self):
        sandbox = evaluation.ContextSandbox(self.runtime, self.helper, self.root / "fixture")
        try:
            pack = sandbox.pack(evaluation.CONTEXT_CASES[0]["source"], "cedar")
            sandbox.memory.forget(pack["items"][0]["id"])
            self.assertFalse(sandbox.callbacks["pack_valid"](pack))
            self.assertEqual(sandbox.pack("Existing runtime?", "off")["items"], ())
        finally:
            sandbox.close()

    def test_missing_retained_fixture_db_blocks_instead_of_new_evaluation_ids(self):
        folder = self.root / "missing-fixture"
        folder.mkdir()
        (folder / "setup.json").write_text("{}")
        with self.assertRaisesRegex(self.helper.Blocked, "database_missing"):
            evaluation.ContextSandbox(self.runtime, self.helper, folder)

    def test_phase_cap_and_call_cap_preserve_other_unknown_reservations(self):
        old = self.ledger.reserve(.8, identity="prior", role="other_evaluation")
        phase = evaluation.PhaseBudget(self.ledger, self.helper, self.root, "context", "one", .3, 1)
        token = phase.reserve(.2, identity="new", role="generation")
        with self.assertRaisesRegex(self.helper.Blocked, "phase_budget_or_call_limit"):
            phase.reserve(.01, identity="second", role="verification")
        state = self.ledger.state()
        self.assertIsNone(state["calls"][old]["actual_usd"])
        self.assertIsNone(state["calls"][token]["actual_usd"])
        self.assertEqual(state["ceiling_usd"], 25)

    def test_budget_admitted_before_every_synthetic_native_call_and_response_cache(self):
        runner = self.runner(live=True)
        admitted = []
        def perform(calls):
            def send(cap):
                self.assertEqual(cap, 4096)
                self.assertTrue(runner.budget.state()["calls"])
                admitted.append(True)
                return response()
            data = calls.invoke("native", "generation", {"model": evaluation.RECIPIENT[0]}, send)
            return {"synthetic_output": data["text"]}
        case = evaluation.CONTEXT_CASES[0]
        first = runner.unit("context", case, "off", perform)
        second = runner.unit("context", case, "off", perform)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertTrue(second["record_cached"])
        self.assertEqual(len(admitted), 1)

    def test_offline_unit_makes_no_admission_and_can_resume_live(self):
        runner = self.runner()
        case = evaluation.CONTEXT_CASES[0]
        def perform(calls):
            return {"value": calls.invoke("native", "generation", {}, lambda _: response())["text"]}
        blocked = runner.unit("synthetic", case, "off", perform)
        self.assertEqual(blocked["reason"], "live_provider_disabled")
        self.assertEqual(self.ledger.state()["calls"], {})
        runner.live = True
        finished = runner.unit("synthetic", case, "off", perform)
        self.assertEqual(finished["status"], "COMPLETE")
        self.assertEqual(evaluation.summarize(evaluation.read_records(runner.folder))["blocked_units"], [])

    def test_unknown_submission_stops_replay_and_redacts_error_thinking(self):
        runner = self.runner(live=True)
        count = []
        def perform(calls):
            def fail(_):
                count.append(True)
                raise TimeoutError("sk-proj-neverExposeThisSyntheticCredential123 private transport")
            calls.invoke("native", "generation", {}, fail)
            return {}
        for _ in range(2):
            record = runner.unit("context", evaluation.CONTEXT_CASES[0], "off", perform)
            self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(count, [True])
        self.assertEqual(len(self.ledger.state()["calls"]), 1)
        for path in runner.folder.rglob("*.json"):
            self.assertNotIn("neverExpose", path.read_text())
            self.assertNotIn("private transport", path.read_text())

    def test_current_engine_generation_and_verifier_are_budgeted_and_pinned(self):
        runner = self.runner(live=True)
        case = evaluation.CONTEXT_CASES[0]
        observed = []
        output = case["source"] + " Preserve the supplied project facts."
        def fake_call(client, **request):
            observed.append(request)
            self.assertEqual(request["max_tokens"], 4096)
            self.assertEqual(len(self.ledger.state()["calls"]), len(observed))
            if request["model"] == self.runtime.quality.VERIFIER[0]:
                return response(model=request["model"])
            text = json.dumps({"prompt": output, "requirements": [], "uncertain": [], "enrichments": [], "used_context": [], "warnings": []})
            return response(text, model=request["model"])
        calls = self.helper.PaidCalls(self.runtime, runner.budget, runner.folder, "real-engine", live=True)
        with patch.object(self.runtime.claude.Transformer, "_get_client", return_value=SimpleNamespace()), patch.object(self.runtime.claude, "call", side_effect=fake_call):
            result = runner.transform(case["source"], calls)
        self.assertEqual(result["output"], output)
        self.assertEqual([(r["model"], r["reasoning"]) for r in observed], [evaluation.GENERATOR, self.runtime.quality.VERIFIER])
        self.assertEqual(result["result"]["path"], "applied")

    def test_context_guard_blocks_before_any_request(self):
        runner = self.runner(live=True)
        calls = self.helper.PaidCalls(self.runtime, runner.budget, runner.folder, "revoked", live=True)
        with self.assertRaisesRegex(self.helper.Blocked, "context_revoked_before_admission"):
            runner.transform(evaluation.CONTEXT_CASES[0]["source"], calls, pack={"items": []}, guard=lambda _: False)
        self.assertEqual(calls.calls, [])
        self.assertEqual(self.ledger.state()["calls"], {})

    def test_engine_does_not_hide_phase_cap_as_successful_original_fallback(self):
        runner = self.runner(live=True, max_usd=.000001)
        calls = self.helper.PaidCalls(self.runtime, runner.budget, runner.folder, "phase-cap", live=True)
        with self.assertRaisesRegex(self.helper.Blocked, "phase_budget_or_call_limit"):
            runner.transform(evaluation.CONTEXT_CASES[0]["source"], calls)
        self.assertEqual(self.ledger.state()["calls"], {})

    def test_full_twelve_context_cells_use_real_retrieval_and_resumable_budgeted_wiring(self):
        runner = self.runner(live=True)
        observed = []
        verdict = {"grounded": True, "unsupported_assertions": [], "omitted_relevant_facts": [],
                   "scope_leaks": [], "instruction_fidelity_issues": [], "notes": "Synthetic wiring verdict."}
        def fake_call(client, **request):
            observed.append(("native", request["model"]))
            payload = json.loads(request["messages"][-1]["content"])
            if request["model"] == self.runtime.quality.VERIFIER[0]:
                return response(model=request["model"], reasoning=request["reasoning"])
            items = payload["context"].get("items", [])
            refs = [{"id": i["id"], "revision": i["revision"]} for i in items]
            output = payload["source"] + " Supplied project evidence: " + " ".join(i["text"] for i in items)
            return response(json.dumps({"prompt": output, "requirements": [], "uncertain": [],
                "enrichments": [], "used_context": refs, "warnings": []}),
                model=request["model"], reasoning=request["reasoning"])
        def fake_judge(body):
            observed.append(("judge", body["model"]))
            self.assertEqual(len(self.ledger.state()["calls"]), len(observed))
            return {"model": evaluation.JUDGE[0], "usage": {"prompt_tokens": 100, "completion_tokens": 30},
                    "choices": [{"message": {"content": json.dumps(verdict)}}]}
        runner._judge = SimpleNamespace(jb=SimpleNamespace(request_params=lambda params, _: params),
                                        http=SimpleNamespace(complete=fake_judge))
        with patch.object(self.runtime.claude.Transformer, "_get_client", return_value=SimpleNamespace()), patch.object(self.runtime.claude, "call", side_effect=fake_call), patch("sys.stdout", new_callable=io.StringIO):
            records = runner.context()
            resumed = runner.context()
        self.assertEqual(len(records), 12)
        self.assertEqual(len(observed), 36)
        self.assertTrue(all(r["record_cached"] for r in resumed))
        self.assertTrue(all(r["guard_valid"] for r in records))
        self.assertTrue(all(r["grounding"]["used_context"] for r in records if r["condition"] != "off"))
        self.assertTrue(all(not r["grounding"]["used_context"] for r in records if r["condition"] == "off"))
        summary = evaluation.summarize(records)
        self.assertEqual(summary["context"]["completed"], 12)
        self.assertEqual(summary["context"]["grounded"], 12)
        self.assertEqual(summary["context"]["unverified"], 0)
        for case in evaluation.CONTEXT_CASES:
            self.assertEqual({r["source"] for r in records if r["case_id"] == case["id"]}, {case["source"]})

    def test_independent_judge_uses_existing_adapter_and_reserves_before_admission(self):
        runner = self.runner(live=True)
        verdict = {"grounded": True, "unsupported_assertions": [], "omitted_relevant_facts": ["state format"],
                   "scope_leaks": [], "instruction_fidelity_issues": [], "notes": "Synthetic verdict."}
        def complete(body):
            self.assertEqual(len(self.ledger.state()["calls"]), 1)
            self.assertEqual(body["max_tokens"], 4096)
            self.assertEqual(body["reasoning_effort"], "medium")
            return {"model": "gpt-6.1-sol", "usage": {"prompt_tokens": 80, "completion_tokens": 20},
                    "choices": [{"message": {"content": json.dumps(verdict)}}]}
        runner._judge = SimpleNamespace(jb=SimpleNamespace(request_params=lambda params, _: params),
                                        http=SimpleNamespace(complete=complete))
        calls = self.helper.PaidCalls(self.runtime, runner.budget, runner.folder, "judge", live=True)
        result = runner.grade_context({"source": "synthetic", "output": "synthetic", "context": {}}, calls)
        self.assertTrue(result["grounded"])
        self.assertEqual(result["omitted_relevant_facts"], ["state format"])
        self.assertEqual(calls.calls[0]["backend"], "judge")

    def test_baseline_import_reuses_existing_runner_without_key_constructor(self):
        with patch.object(self.runtime.claude, "read_api_key", side_effect=AssertionError("must not read key")):
            old = evaluation.baseline_engine(PRODUCTION)
        self.assertNotEqual(old.VALIDATOR_REVISION, self.runtime.engine.VALIDATOR_REVISION)
        self.assertTrue(callable(old.job_for_definition))

    def test_real_baseline_engine_has_one_budgeted_generation_and_no_claimed_verifier(self):
        runner = self.runner(phase="downstream", live=True)
        old = evaluation.baseline_engine(PRODUCTION)
        case = evaluation.DOWNSTREAM_CASES[0]
        calls = self.helper.PaidCalls(self.runtime, runner.budget, runner.folder, "actual-baseline", live=True)
        expected = case["source"] + " Preserve the fictional data."
        value = json.dumps({"prompt": expected, "requirements": [], "uncertain": []})
        with patch.object(self.runtime.claude.Transformer, "_get_client", return_value=SimpleNamespace()), patch.object(self.runtime.claude, "call", return_value=response(value, model=evaluation.GENERATOR[0])) as generate:
            result = runner.transform(case["source"], calls, actual_engine=old)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["output"], expected)
        self.assertFalse(result["independent_verification_ran"])
        self.assertEqual(result["actual_compiler"]["baseline"], "96a65f8")
        self.assertEqual(len(self.ledger.state()["calls"]), 1)

    def test_missing_embedding_is_explicit_lexical_degradation_without_download(self):
        from localflow.v2.memory.embeddings import MiniLMEmbedding
        with patch.object(MiniLMEmbedding, "encode", return_value=None), patch.object(MiniLMEmbedding, "download", side_effect=AssertionError("no downloads")):
            sandbox = evaluation.ContextSandbox(self.runtime, self.helper, self.root / "degraded")
            try:
                self.assertTrue(sandbox.audit["degraded"])
                self.assertEqual(set(sandbox.audit["retrieval_modes"].values()), {"lexical_degraded"})
                for key in evaluation.PROJECTS:
                    pack = sandbox.pack(evaluation.CONTEXT_CASES[0]["source"], key)
                    self.assertTrue(pack["items"])
                    self.assertEqual({i["scope_id"] for i in pack["items"]}, {sandbox.projects[key]})
            finally:
                sandbox.close()

    def test_source_change_refuses_old_manifest_before_new_admission(self):
        runner = self.runner()
        modified = SimpleNamespace(**vars(self.runtime))
        modified.source_hashes = {**self.runtime.source_hashes, "compiler-test": "changed"}
        with self.assertRaisesRegex(ValueError, "immutable_artifact_conflict"):
            evaluation.OutcomeRunner(modified, self.helper, runner.output, self.ledger, phase="context")
        self.assertEqual(self.ledger.state()["calls"], {})

    def test_response_thinking_and_transport_secrets_are_not_retained_in_new_artifacts(self):
        runner = self.runner(live=True)
        def perform(calls):
            value = response(_continuation=[{"type": "thinking", "thinking": "private trace", "signature": "private"}],
                headers={"Authorization": "Bearer syntheticCredential123456"})
            result = calls.invoke("native", "synthetic", {}, lambda _: value)
            return {"answer": result["text"]}
        runner.unit("synthetic", evaluation.CONTEXT_CASES[0], "off", perform)
        for path in runner.folder.rglob("*.json"):
            for secret in ("private trace", "Authorization", "syntheticCredential", '"_continuation":'):
                self.assertNotIn(secret, path.read_text())

    def test_context_omission_and_review_are_not_counted_as_unsupported_assertions(self):
        rows = [{"evaluation_identity": "one", "role": "context", "status": "COMPLETE", "case_id": "one",
            "condition": "cedar", "repeat": 0, "grounded": True, "omissions": ["runtime"], "unverified": True,
            "memory_audit": {"degraded": True}, "scope_labels": {"cross_scope_mentions": []}, "calls": []}]
        summary = evaluation.summarize(rows)["context"]
        self.assertEqual(summary["grounded"], 1)
        self.assertEqual(summary["with_omissions"], 1)
        self.assertEqual(summary["unverified"], 1)
        self.assertEqual(summary["degraded_retrieval"], 1)

    def test_complete_matched_downstream_shape_and_trials_without_providers(self):
        runner = self.runner(phase="downstream")
        events = []
        def fake_transform(source, calls, **kwargs):
            events.append(("transform", source))
            return {"output": source, "result": {"path": "applied"}, "independent_verification_ran": True}
        class SyntheticProvider:
            def __init__(self, runtime, calls, config, *, role):
                self.config = config
            def _request(self, system, messages, schema, **kwargs):
                self_case = next(c for c in evaluation.DOWNSTREAM_CASES if c["source"] == messages[0]["content"])
                events.append(("recipient", self_case["id"]))
                return response(json.dumps(self_case["expected"]))
            def close(self):
                pass
        with patch.object(evaluation, "baseline_engine", return_value=SimpleNamespace()), patch.object(runner, "transform", side_effect=fake_transform), patch.object(self.helper, "BudgetedProvider", SyntheticProvider), patch("sys.stdout", new_callable=io.StringIO):
            records = runner.downstream()
        self.assertEqual(sum(e[0] == "transform" for e in events), 8)
        self.assertEqual(sum(e[0] == "recipient" for e in events), 16)
        self.assertEqual([e[0] for e in events[:8]], ["transform"] * 8)
        report = evaluation.summarize(records)
        self.assertEqual(report["downstream"]["completed_pairs"], 8)
        self.assertEqual(report["downstream"]["matched_accuracy_delta"], 0)
        self.assertEqual(report["downstream"]["baseline_correct"], 8)

    def test_unmatched_recipient_never_counts_as_positive_gain(self):
        base = {"role": "recipient", "status": "COMPLETE", "case_id": "paid-order", "repeat": 0,
                "answer_check": {"correct": True}, "unverified_transform": False, "calls": []}
        rows = [{**base, "evaluation_identity": "a", "condition": "current"}]
        self.assertIsNone(evaluation.summarize(rows)["downstream"]["matched_accuracy_delta"])
        rows.append({**base, "evaluation_identity": "b", "condition": "baseline-96a65f8"})
        self.assertEqual(evaluation.summarize(rows)["downstream"]["matched_accuracy_delta"], 0)
        rows[0]["answer_check"] = {"correct": False}
        self.assertEqual(evaluation.summarize(rows)["downstream"]["matched_accuracy_delta"], -1)


if __name__ == "__main__":
    unittest.main()
