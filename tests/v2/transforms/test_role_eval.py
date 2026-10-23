"""Offline role runner checks. All provider/judge responses are synthetic.

In an isolated older checkout, set LOCALFLOW_ROLE_EVAL_REPO to the integrated
checkout whose production interfaces are being tested. No keys are read.
"""

from __future__ import annotations

import copy
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
SPEC = importlib.util.spec_from_file_location("transform_role_eval", ROOT / "scripts/v2/transform_role_eval.py")
role_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(role_eval)
FIXTURES = json.loads((ROOT / "tests/v2/transforms/fixtures_roles.json").read_text())
PRODUCTION = Path(os.environ.get("LOCALFLOW_ROLE_EVAL_REPO", ROOT))


def response(**changes):
    return {"text": '{"issues":[]}', "model": "claude-haiku-5-5", "reasoning": "off",
            "input_tokens": 100, "output_tokens": 20, "latency_ms": 1, **changes}


class FixtureTests(unittest.TestCase):
    def test_invalid_empty_sample_label_is_rejected_before_admission(self):
        fixtures = json.loads(json.dumps(FIXTURES))
        sample = next(s for s in fixtures["authoring"][0]["unseen_samples"] if not s["input"].strip())
        sample["expected"] = {"refuse": True}
        with self.assertRaisesRegex(ValueError, "invalid_authoring_sample_expectation"):
            role_eval.validate_fixtures(fixtures)
        sample["expected"] = {"refusal": False}
        with self.assertRaisesRegex(ValueError, "empty_authoring_sample_requires_refusal"):
            role_eval.validate_fixtures(fixtures)

    def test_full_synthetic_fixture_coverage_and_split_families(self):
        role_eval.validate_fixtures(FIXTURES)
        self.assertGreaterEqual(len(FIXTURES["authoring"]), 12)
        families = {}
        for case in FIXTURES["authoring"]:
            self.assertGreaterEqual(len([s for s in case["unseen_samples"] if s["input"]]), 2)
            self.assertTrue(any(s["expected"].get("refusal") for s in case["unseen_samples"]))
            self.assertNotIn(case["family"], families)
            families[case["family"]] = case["split"]
            shown = {e["before"] for e in case["demonstrations"]}
            self.assertFalse(shown & {s["input"] for s in case["unseen_samples"]})
        self.assertEqual(sum(not c["expected_issue"] for c in FIXTURES["verification"]), 20)
        self.assertEqual(sum(c["expected_issue"] for c in FIXTURES["verification"]), 20)
        self.assertTrue(any("Remove" in c["followup"] for c in FIXTURES["refinement"]))
        self.assertTrue(all(sum(weights.values()) == 100 for weights in role_eval.RUBRICS.values()))
        self.assertEqual(role_eval.SHORTLIST, (("claude-haiku-5-5", "off"),
            ("claude-sonnet-5-5", "low"), ("claude-sonnet-5-5", "xhigh")))

    def test_no_secret_or_thinking_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "artifact.json"
            role_eval.write_once(path, {"api_key": "never-store-this", "headers": {"Authorization": "hidden"},
                "text": "sk-proj-syntheticSecretCredential123", "_continuation": [
                    {"type": "thinking", "thinking": "private narrative", "signature": "private"}],
                "content": [{"type": "thinking", "thinking": "another private narrative"},
                            {"type": "text", "text": "safe"}]})
            output = path.read_text()
            for value in ("never-store-this", "syntheticSecret", "narrative", "Authorization", "_continuation"):
                self.assertNotIn(value, output)
            self.assertIn("[redacted]", output)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "immutable_artifact_conflict"):
                role_eval.write_once(path, {"different": True})

    def test_summary_keeps_blocked_unknown_and_distinct_clean_pairs(self):
        records = [{"role": "verification", "config": ["model", "off"], "cohort": "one",
            "case_id": "one-case", "status": "PASS", "expected_issue": False,
            "false_positive": False, "end_to_end_ms": 10, "calls": [], "judge": None}
            for _ in range(20)]
        summary = next(iter(role_eval.summarize(records).values()))
        self.assertEqual(summary["status"], "BLOCKED")
        self.assertEqual(summary["distinct_clean_pairs"], 1)
        records[0].update(status="BLOCKED", calls=[{"call_id": "x", "cost_usd": None,
                                                     "reserved_usd": .2}])
        summary = next(iter(role_eval.summarize(records).values()))
        self.assertIsNone(summary["cost_usd"])
        self.assertEqual(summary["reserved_unknown_usd"], .2)


@unittest.skipUnless((PRODUCTION / "localflow/v2/transforms/evaluation.py").exists(),
                     "integrated production checkout required; set LOCALFLOW_ROLE_EVAL_REPO")
class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = role_eval.load_runtime(PRODUCTION)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.budget = self.runtime.evaluation.EvalBudget(self.root / "budget.json", ceiling=25)

    def tearDown(self):
        self.temp.cleanup()

    def calls(self, identity="unit:one", live=True, **kwargs):
        return role_eval.PaidCalls(self.runtime, self.budget, self.root, identity, live=live, **kwargs)

    def test_identity_changes_with_all_evaluation_inputs_and_repeats(self):
        case = FIXTURES["refinement"][0]
        args = [self.runtime, case, role_eval.digest(FIXTURES), "refinement",
                role_eval.SHORTLIST[0], 0, "run"]
        baseline = role_eval.identity(*args)
        for index, value in ((1, {**case, "source": "Changed source"}), (2, "changed split manifest"),
                             (3, "authoring"), (4, role_eval.SHORTLIST[1]), (5, 1), (6, "other-run")):
            changed = list(args)
            changed[index] = value
            self.assertNotEqual(baseline, role_eval.identity(*changed))
        changed = list(args)
        changed[1] = {**case, "context": {"items": [{"id": "new", "revision": 2}]}}
        self.assertNotEqual(baseline, role_eval.identity(*changed))
        self.assertNotEqual(baseline, role_eval.identity(*args, judge=False))
        self.assertNotEqual(baseline, role_eval.identity(*args, max_calls=2))
        runtime = SimpleNamespace(**vars(self.runtime))
        runtime.source_hashes = {**runtime.source_hashes, "compiler": "changed"}
        changed = list(args)
        changed[0] = runtime
        self.assertNotEqual(baseline, role_eval.identity(*changed))

    def test_reserve_before_admission_settle_and_cache_no_duplicate(self):
        performed = []
        request = {"model": "claude-haiku-5-5", "source": "Synthetic source"}

        def perform(cap):
            self.assertEqual(len(self.budget.state()["calls"]), 1)
            self.assertEqual(cap, 4096)
            performed.append(True)
            return response()
        first = self.calls().invoke("native", "verify", request, perform)
        second_calls = self.calls()
        second = second_calls.invoke("native", "verify", request, lambda cap: self.fail("cache replayed request"))
        self.assertEqual(first, second)
        self.assertEqual(len(performed), 1)
        self.assertTrue(second_calls.calls[0]["cached"])
        state = self.budget.state()
        self.assertEqual(len(state["calls"]), 1)
        self.assertIsNotNone(next(iter(state["calls"].values()))["actual_usd"])

    def test_uncertain_submission_never_retries_and_does_not_log_exception(self):
        def failed(_cap):
            raise TimeoutError("Bearer syntheticSecretCredential123")
        for _ in range(2):
            with self.assertRaisesRegex(role_eval.Blocked, "submission_outcome_unknown"):
                self.calls().invoke("native", "verify", {}, failed)
        self.assertEqual(len(self.budget.state()["calls"]), 1)
        reservation = next(iter(self.budget.state()["calls"].values()))
        self.assertIsNone(reservation["actual_usd"])
        self.assertGreater(reservation["reserved_usd"], 0)
        for path in (self.root / "calls").glob("*/*.json"):
            self.assertNotIn("syntheticSecret", path.read_text())

    def test_reservation_without_response_blocks_crash_replay(self):
        request = {"text": "Synthetic"}
        call_id = role_eval.digest({"unit": "unit:crash", "ordinal": 1, "backend": "native",
                                   "tag": "verify", "request": request, "output_cap": 4096})
        self.budget.reserve(.1, identity=call_id, role="role_eval:verify")
        with self.assertRaisesRegex(role_eval.Blocked, "prior_submission_without_recoverable_response"):
            self.calls("unit:crash").invoke("native", "verify", request,
                                             lambda cap: self.fail("replayed admitted request"))
        self.assertEqual(len(self.budget.state()["calls"]), 1)

    def test_resume_request_drift_cannot_replay_uncertain_ordinal(self):
        def uncertain(cap):
            raise TimeoutError("synthetic timeout")
        with self.assertRaises(role_eval.Blocked):
            self.calls().invoke("judge", "grade", {"random_id": "one"}, uncertain)
        with self.assertRaisesRegex(role_eval.Blocked, "prior_submission_without_recoverable_response"):
            self.calls().invoke("judge", "grade", {"random_id": "two"},
                                lambda cap: self.fail("replayed same uncertain turn"))
        self.assertEqual(len(self.budget.state()["calls"]), 1)

    def test_judge_evidence_excludes_random_ids_and_runtime_metrics(self):
        one = {"quotes": ["Synthetic quote"], "failures": [], "published_records": [
            {"id": "one", "updated_at": 1, "text": "Synthetic quote", "kind": "note", "status": "proposed"}]}
        two = copy.deepcopy(one)
        two["published_records"][0].update(id="two", updated_at=2)
        self.assertEqual(role_eval.stable_judge_evidence("memory", one),
                         role_eval.stable_judge_evidence("memory", two))

    def test_budget_stop_and_offline_stop_admit_nothing(self):
        tiny = self.runtime.evaluation.EvalBudget(self.root / "tiny.json", ceiling=.000001)
        calls = role_eval.PaidCalls(self.runtime, tiny, self.root, "tiny", live=True)
        with self.assertRaisesRegex(role_eval.Blocked, "shared_budget"):
            calls.invoke("native", "test", {}, lambda cap: self.fail("spent after budget stop"))
        self.assertFalse(tiny.state()["calls"])
        with self.assertRaisesRegex(role_eval.Blocked, "live_provider_disabled"):
            self.calls(live=False).invoke("native", "test", {}, lambda cap: self.fail("offline network"))
        self.assertFalse(self.budget.state()["calls"])

    def test_live_cli_cannot_substitute_an_unshared_budget(self):
        with patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                role_eval.main(["verification", "--live", "--repo-root", str(PRODUCTION),
                                "--budget", str(self.root / "not-the-shared-ledger.json")])
        self.assertEqual(stopped.exception.code, 2)
        self.assertFalse((self.root / "not-the-shared-ledger.json").exists())

    def test_live_cli_requires_explicit_authorization_for_a_raised_ceiling(self):
        shared = self.root / "build/transforms-intelligence/evaluation-budget.json"
        budget = self.runtime.evaluation.EvalBudget(shared, ceiling=40)
        budget.state()
        args = ["suggestions", "--live", "--repo-root", str(self.root),
                "--fixtures", str(PRODUCTION / "tests/v2/transforms/fixtures_roles.json"),
                "--limit", "1"]
        runner = SimpleNamespace(manifest="synthetic", run_case=lambda *a: {
            "evaluation_identity": "synthetic", "status": "PASS"})
        with patch.object(role_eval, "load_runtime", return_value=self.runtime), \
                patch.object(role_eval, "RoleRunner", return_value=runner) as create, \
                patch.object(role_eval, "summarize", return_value={"host": {"status": "PASS"}}), \
                patch("sys.stderr", io.StringIO()), patch("sys.stdout", io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                role_eval.main(args)
            self.assertEqual(stopped.exception.code, 2)
            create.assert_not_called()
            self.assertEqual(role_eval.main(args + ["--authorized-ceiling", "40"]), 0)
        self.assertFalse(budget.state()["calls"])

    def test_unknown_usage_stays_reserved_and_private_continuation_is_not_saved(self):
        calls = self.calls("usage")
        calls.invoke("native", "test", {}, lambda cap: response(input_tokens=None))
        self.assertEqual(calls.blocked, "usage_unknown")
        self.assertIsNone(next(iter(self.budget.state()["calls"].values()))["actual_usd"])
        tool_response = response(tool_calls=[{"id": "one", "name": "read_definition", "input": {}}],
            _continuation=[{"type": "thinking", "thinking": "private narrative", "signature": "sig"}])
        self.calls("continuation").invoke("native", "tool", {"tools": []}, lambda cap: tool_response)
        resumed = self.calls("continuation")
        resumed.invoke("native", "tool", {"tools": []}, lambda cap: self.fail("cached tool replay"))
        with self.assertRaisesRegex(role_eval.Blocked, "native_continuation_not_retained"):
            resumed.invoke("native", "tool", {"tools": [{"name": "read_definition"}]},
                           lambda cap: self.fail("spent without native continuation"))
        for path in (self.root / "calls").glob("*/*.json"):
            self.assertNotIn("private narrative", path.read_text())

    def test_independent_role_judge_budget_and_score_validation(self):
        seen = []

        def complete(body):
            seen.append(body)
            self.assertEqual(body["reasoning_effort"], "medium")
            self.assertEqual(len(self.budget.state()["calls"]), 1)
            return {"model": "gpt-6.1-sol", "usage": {"prompt_tokens": 100, "completion_tokens": 30},
                    "choices": [{"message": {"content": json.dumps({
                        "scores": role_eval.RUBRICS["refinement"], "hard_failures": [], "notes": "Synthetic verdict."})}}]}
        fake = SimpleNamespace(jb=SimpleNamespace(request_params=lambda body, backend: body),
                               http=SimpleNamespace(complete=complete))
        runner = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget,
                                     live=True, judge_factory=lambda: fake)
        result = runner.grade("refinement", {"synthetic": True}, self.calls())
        self.assertEqual(result["score"], 100)
        self.assertEqual(len(seen), 1)
        invalid = SimpleNamespace(jb=fake.jb, http=SimpleNamespace(complete=lambda body: {
            "model": "gpt-6.1-sol", "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "choices": [{"message": {"content": json.dumps({"scores": {
                **role_eval.RUBRICS["refinement"], "grounding": 1000}, "hard_failures": [], "notes": "Invalid."})}}]}))
        other = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget,
                                    live=True, judge_factory=lambda: invalid)
        with self.assertRaisesRegex(ValueError, "invalid_judge_verdict"):
            other.grade("refinement", {}, self.calls("invalid-judge"))

    def test_memory_model_false_proposal_remains_a_failure_after_host_rejection(self):
        class FakeTransformer:
            def _get_client(self):
                return SimpleNamespace(with_options=lambda **kwargs: object())

            def close(self):
                pass

        def incorrect(_client, **request):
            self.assertEqual((request["model"], request["reasoning"]), role_eval.SHORTLIST[1])
            return response(text=json.dumps({"facts": [{"quote": "I use an invented database.",
                                                        "kind": "project_fact"}]}),
                            model=request["model"], reasoning=request["reasoning"])
        runner = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget, live=True)
        with patch.object(self.runtime.claude, "Transformer", FakeTransformer), patch.object(
                self.runtime.claude, "call", incorrect):
            record = runner.run_case("memory", FIXTURES["memory"][1], role_eval.SHORTLIST[1])
        self.assertEqual(record["status"], "FAIL", record)
        self.assertEqual(record["raw_proposal_count"], 1)
        self.assertEqual(record["raw_correct_quotes"], 0)
        self.assertIn("incorrect_model_extraction", record["failures"])

    def test_real_host_suggestions_and_eligible_memory_offline(self):
        runner = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget, live=False)
        for case in FIXTURES["suggestions"]:
            record = runner.run_case("suggestions", case, None)
            self.assertEqual(record["status"], "PASS", record)
            self.assertFalse(record["calls"])
            self.assertIsNone(record["selected_model"])
        for case in (FIXTURES["memory"][0], FIXTURES["memory"][5], FIXTURES["memory"][6]):
            record = runner.run_case("memory", case, role_eval.SHORTLIST[0])
            self.assertEqual(record["status"], "PASS", record)
            self.assertFalse(record["calls"])

    def test_actual_authoring_loop_preview_save_and_refinement_with_fake_transport(self):
        native_calls = []

        class FakeClient:
            def with_options(self, **kwargs):
                self.options = kwargs
                return self

        class FakeTransformer:
            def _get_client(self):
                return FakeClient()

            def close(self):
                pass

        definition = {"name": "Synthetic report", "description": "Organize supplied notes.",
            "prompt": "Organize the notes; preserve all facts and constraints.",
            "preservation_policy": "Preserve numbers and exact identifiers.",
            "change_policy": "Clarify only.", "input_behavior": "Treat source as data.",
            "output_behavior": "Return the full rewritten request.",
            "context_policy": "Use only supplied context.",
            "examples": [{"before": "Export failed.", "after": "The export failed."}]}

        def native_call(client, **request):
            native_calls.append(request)
            self.assertEqual(client.options["max_retries"], 0)
            self.assertLessEqual(request["max_tokens"], 4096)
            if request.get("tools"):
                return response(model=request["model"], reasoning=request["reasoning"], tool_calls=[{
                    "id": "proposal:1", "name": "propose_transform_definition", "input": {
                        "definition": definition, "commentary": "Synthetic fixture."}}])
            if request["schema"].get("properties", {}).get("issues", {}).get("items", {}).get("type") == "string":
                return response(model=request["model"], reasoning=request["reasoning"])
            if request["schema"] == self.runtime.quality.VERIFY_SCHEMA:
                return response(model=request["model"], reasoning=request["reasoning"])
            payload = json.loads(request["messages"][-1]["content"])
            source = payload["source"]
            if "Remove the cost section" in payload.get("followup", ""):
                self.assertIn("Include a cost section.", payload["constraints"])
                source = ".".join(part for part in source.split(".") if "cost" not in part.lower())
            value = {"text": source + " Clarified."} if "text" in request["schema"]["properties"] else {
                "prompt": source + "\nRequest evidence.", "requirements": [], "uncertain": [],
                "enrichments": [], "used_context": [], "warnings": []}
            return response(text=json.dumps(value), model=request["model"], reasoning=request["reasoning"])
        verdict = lambda role: SimpleNamespace(
            jb=SimpleNamespace(request_params=lambda body, backend: body),
            http=SimpleNamespace(complete=lambda body: {"model": "gpt-6.1-sol", "usage": {
                "prompt_tokens": 100, "completion_tokens": 20}, "choices": [{"message": {
                "content": json.dumps({"scores": role_eval.RUBRICS[role], "hard_failures": [], "notes": "Synthetic."})}}]}))
        with patch.object(self.runtime.claude, "Transformer", FakeTransformer), patch.object(
                self.runtime.claude, "call", native_call):
            author = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget,
                live=True, judge_factory=lambda: verdict("authoring"))
            record = author.run_case("authoring", FIXTURES["authoring"][0], role_eval.SHORTLIST[0])
            self.assertEqual(record["status"], "PASS", record)
            self.assertTrue(record["save_reload"])
            self.assertEqual(len(record["unseen_results"]), 3)
            self.assertGreaterEqual(len(record["calls"]), 8)
            self.assertEqual(tuple(record["created_transform_execution"]), self.runtime.claude.recommended("custom"))
            generated = [r for r in native_calls if not r.get("tools") and
                         "text" in r.get("schema", {}).get("properties", {})]
            self.assertTrue(generated)
            self.assertTrue(all((r["model"], r["reasoning"]) == self.runtime.claude.recommended("custom")
                                for r in generated))
            before = len(native_calls)
            repeated = author.run_case("authoring", FIXTURES["authoring"][0], role_eval.SHORTLIST[0])
            self.assertTrue(repeated["record_cached"])
            self.assertEqual(before, len(native_calls))
            refine = role_eval.RoleRunner(self.runtime, FIXTURES, self.root, self.budget,
                live=True, judge_factory=lambda: verdict("refinement"))
            record = refine.run_case("refinement", FIXTURES["refinement"][0], role_eval.SHORTLIST[0])
            self.assertEqual(record["status"], "PASS", record)
            self.assertIn("reader.py", record["output"])
            self.assertGreater(record["session_revision"], 1)
            removed = refine.run_case("refinement", FIXTURES["refinement"][1], role_eval.SHORTLIST[0])
            self.assertEqual(removed["status"], "PASS", removed)
            self.assertNotIn("cost section", removed["output"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
