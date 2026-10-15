import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import judge, judge_backends as backends
from v2.common import read_json, write_json, write_jsonl


def verdict(oid):
    return {"output_id": oid, "semantic_damage": False, "critical_fact_changed": False,
            "hallucination": False, "unwanted_edit": False, "cleanup": "complete",
            "punctuation": "improved", "self_correction": "not_applicable", "reason": "Toy fixture"}


def params(backend="openai"):
    return {"model": backends.MODELS[backend], "max_tokens": 2800,
            "system": [{"type": "text", "text": judge.SYSTEM}],
            "messages": [{"role": "user", "content": json.dumps({"source": "um go",
                "outputs": [{"output_id": "o1", "text": "Go."}], "vocabulary": []})}],
            "output_config": {"format": {"schema": judge.SCHEMA}}}


class FakeClient:
    def __init__(self):
        self.rows = []
        self.creates = 0
        self.completions = 0
        self.uploads = 0
        self.batches = []

    def upload(self, rows):
        self.uploads += 1
        self.rows = copy.deepcopy(rows)
        return "file-toy"

    def create_batch(self, file_id, metadata):
        self.creates += 1
        batch = {"id": "batch-toy", "metadata": metadata}
        self.batches.append(batch)
        return batch

    def list_batches(self):
        return self.batches

    def retrieve(self, batch_id):
        return {"id": batch_id, "status": "completed"}

    def answer(self, body):
        view = json.loads(body["messages"][1]["content"])
        return {"id": "response-toy", "model": body["model"],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps({"verdicts": [verdict(o["output_id"]) for o in view["outputs"]]})}}]}

    def results(self, batch):
        return [{"custom_id": r["custom_id"], "response": {"status_code": 200,
                 "body": self.answer(r["body"])}} for r in reversed(self.rows)]

    def complete(self, body):
        self.completions += 1
        return self.answer(body)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.network = patch.object(backends, "HTTPClient", side_effect=AssertionError("No real API client in tests"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def wave(self, backend="openai", client=None, name="toy", requests=None):
        return backends.OtherWave(name, requests or {"r1": params(backend)}, judge.parse_verdicts,
            backend, root=self.root, client=client or FakeClient(), log=lambda _: None, poll_seconds=0)

    def test_both_backends_resume_without_second_purchase_and_settle_usage(self):
        for backend in backends.MODELS:
            client = FakeClient()
            w = self.wave(backend, client)
            w.run()
            again = self.wave(backend, client)
            again.run()
            self.assertEqual(client.creates + client.completions, 1)
            self.assertEqual(again.outcomes["r1"]["value"], [verdict("o1")])
            ledger = read_json(self.root / "ledger-other.json")
            entry = next(e for e in ledger["entries"].values() if e["backend"] == backend)
            self.assertEqual(entry["state"], "settled")
            self.assertAlmostEqual(entry["actual_usd"], backends.charge(backend, {"input_tokens": 100, "output_tokens": 50}))

    def test_prompt_view_schema_and_output_limit_are_identical(self):
        for backend in backends.MODELS:
            original = params(backend)
            result = backends.request_params(original, backend)
            self.assertEqual(result["messages"][0]["content"], judge.SYSTEM)
            self.assertEqual(result["messages"][1], original["messages"][0])
            self.assertEqual(result["response_format"]["json_schema"]["schema"], judge.SCHEMA)
            self.assertEqual(result.get("max_completion_tokens", result.get("max_tokens")), 2800)

    def test_changed_requests_and_unpriced_models_are_refused(self):
        self.wave()
        changed = params(); changed["max_tokens"] = 6000
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.wave(requests={"r1": changed})
        changed["model"] = "unpriced-model"
        with self.assertRaisesRegex(ValueError, "price"):
            self.wave(name="new", requests={"r1": changed})

    def test_caps_count_other_reservations_and_refuse_before_client_use(self):
        for backend in backends.MODELS:
            write_json(self.root / "ledger-other.json", {"entries": {
                "prior": {"backend": backend, "state": "outstanding", "max_usd": backends.CAPS[backend]}}})
            client = FakeClient()
            with self.assertRaises(backends.BudgetExceeded):
                self.wave(backend, client).run()
            self.assertEqual((client.uploads, client.creates, client.completions), (0, 0, 0))

    def test_total_estimate_is_printed_and_over_cap_set_is_never_partly_submitted(self):
        client = FakeClient(); messages = {f"r{i}": params() for i in range(2)}
        w = self.wave(client=client, requests=messages)
        output = []; w.log = output.append
        with patch.dict(backends.CAPS, openai=0.02), self.assertRaises(backends.BudgetExceeded):
            w.run(chunk=1)
        self.assertIn("estimate_max_usd", output[0])
        self.assertEqual(client.uploads, 0)

    def test_ambiguous_openai_adopts_exact_metadata_only(self):
        client = FakeClient(); create = client.create_batch
        def lost_response(*args):
            create(*args)
            raise TimeoutError()
        client.create_batch = lost_response
        with self.assertRaises(backends.UnresolvedSubmission):
            self.wave(client=client).run()
        # A same-size unrelated batch is not identity evidence.
        client.batches.insert(0, {"id": "unrelated", "metadata": {}})
        self.wave(client=client).run()
        self.assertEqual(client.creates, 1)

    def test_ambiguous_with_no_identity_retains_reservation_on_rerun(self):
        for backend in backends.MODELS:
            client = FakeClient()
            def timeout(*args): raise TimeoutError()
            client.create_batch = timeout; client.complete = timeout
            for _ in range(2):
                with self.assertRaises(backends.UnresolvedSubmission):
                    self.wave(backend, client).run()
            entry = next(e for e in read_json(self.root / "ledger-other.json")["entries"].values() if e["backend"] == backend)
            self.assertEqual(entry["state"], "outstanding")

    def test_missing_usage_or_result_never_releases_budget(self):
        for variant in ("usage", "missing", "duplicate"):
            client = FakeClient(); original = client.results
            def results(batch):
                rows = original(batch)
                if variant == "usage": rows[0]["response"]["body"].pop("usage")
                if variant == "missing": return []
                if variant == "duplicate": return rows * 2
                return rows
            client.results = results
            with self.assertRaises(backends.UnresolvedSubmission):
                self.wave(client=client, name=variant).run()
            self.assertTrue(all(e["state"] == "outstanding" for e in read_json(self.root / "ledger-other.json")["entries"].values()))

    def test_malformed_and_truncated_responses_still_charge_returned_usage(self):
        for finish in ("stop", "length"):
            client = FakeClient(); original = client.answer
            def answer(body):
                result = original(body); result["choices"][0]["finish_reason"] = finish
                result["choices"][0]["message"]["content"] = '{}'
                return result
            client.answer = answer
            w = self.wave(client=client, name=finish); w.run()
            self.assertEqual(w.outcomes["r1"]["status"], "malformed" if finish == "stop" else "truncated")
            self.assertGreater(w.manifest["attempts"][0]["actual_usd"], 0)

    def test_definitive_rejection_settles_zero_but_does_not_resubmit(self):
        client = FakeClient()
        def reject(*args): raise backends.APIError(400)
        client.create_batch = reject
        for _ in range(2):
            with self.assertRaises(backends.UnresolvedSubmission): self.wave(client=client).run()
        entry = next(iter(read_json(self.root / "ledger-other.json")["entries"].values()))
        self.assertEqual(entry["actual_usd"], 0)

    def test_schema_rejects_wrong_types_enums_and_extra_fields(self):
        for changes in ({"semantic_damage": 1}, {"cleanup": "great"}, {"extra": True}):
            with self.assertRaises(ValueError):
                judge.parse_verdicts(json.dumps({"verdicts": [{**verdict("o1"), **changes}]}))

    def test_env_loader_uses_named_key_without_logging(self):
        env = self.root / ".env"
        env.write_text("export JUDGES_OPENAI_API_KEY='synthetic-fixture-value'\n")
        with patch.dict(os.environ, {}, clear=True), patch.object(backends, "ROOT", self.root), \
             patch.object(backends, "CONFIG", {"paths": {"env_file": ".env"}}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(backends.api_key("openai"), "synthetic-fixture-value")
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                backends.api_key("openrouter")
            self.assertEqual(output.getvalue(), "")

    def test_smoke_with_fake_prints_usage_and_cost_and_resumes(self):
        path = Path(__file__).resolve().parents[1] / "tools/judge_smoke.py"
        spec = importlib.util.spec_from_file_location("judge_smoke", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        client = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()):
            first = module.smoke(root=self.root, client=client)
            second = module.smoke(root=self.root, client=client)
        self.assertLess(first["estimate_max_usd"], .25)
        self.assertEqual(first["usage"], {"input_tokens": 300, "output_tokens": 150})
        self.assertAlmostEqual(first["actual_usd"], .00105)
        self.assertEqual(first, second); self.assertEqual(client.creates, 1)


class DataGateTests(unittest.TestCase):
    def test_openrouter_refuses_roles_paths_prefixes_origins_and_test_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for change in ({"role": "final"}, {"prefix": "fresh"}, {"prefix": "real_audio"},
                           {"prefix": "final"}, {"cases_file": root / "audio.jsonl"},
                           {"cases": [{"origin": "real_audio", "split": "validation"}]},
                           {"cases": [{"origin": "synthetic", "split": "test"}]}):
                args = dict(backend="openrouter", cases_file=root / "development.jsonl",
                            prefix="development", role="development", cases=[])
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "OpenRouter"):
                    judge.data_gate(**(args | change))

    def test_openai_final_requires_both_confirmation_and_freeze(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(judge, "ART", Path(directory)):
            for frozen, confirmed in ((False, False), (False, True), (True, False), (True, True)):
                if frozen: (Path(directory)/"research/prereg").mkdir(parents=True, exist_ok=True); (Path(directory)/"research/prereg/FROZEN").touch()
                if frozen and confirmed:
                    judge.data_gate("openai", "final.jsonl", "final", "final", confirm_final_eval=confirmed)
                else:
                    with self.assertRaisesRegex(ValueError, "confirm-final-eval"):
                        judge.data_gate("openai", "final.jsonl", "final", "final", confirm_final_eval=confirmed)

    def test_refusals_precede_file_reads_and_wave_construction(self):
        fake = Mock(side_effect=AssertionError("Gate must precede wave"))
        for backend, kwargs in (("openrouter", {"role": "final"}), ("openai", {"role": "final"})):
            with patch.object(judge, "read_jsonl", side_effect=AssertionError("Do not open restricted data")), \
                 self.assertRaises(ValueError):
                judge.run("final.jsonl", ["toy"], backend=backend, wave_factory=fake, **kwargs)
        fake.assert_not_called()

    def test_new_backend_integration_uses_fake_clients_and_saves_identity(self):
        for backend in backends.MODELS:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); cases = root / "development.jsonl"
                write_jsonl(cases, [{"case_id": "toy", "split": "validation", "origin": "synthetic",
                    "model_input": "um go", "target": "Go.", "is_noop": False}])
                write_jsonl(root / "eval/development-X.jsonl", [{"case_id": "toy", "delivered": "Go.", "model_only": "Go."}])
                client = FakeClient()
                def factory(n, r, p, m, purpose):
                    return backends.OtherWave(n, r, p, backend, root=root/"judge", client=client, log=lambda _:None)
                with patch.object(judge, "ART", root), contextlib.redirect_stdout(io.StringIO()):
                    judge.run(cases, ["X"], "development", "toy", backend=backend, wave_factory=factory)
                identity = read_json(root / f"judge/{backend}/toy/identity.json")
                self.assertEqual(identity["backend"], backend)
                self.assertEqual(identity["model_id"], backends.MODELS[backend])
                self.assertEqual(identity["prompt_sha256"], judge.sha256_text(judge.SYSTEM))
                self.assertIn("request_parameters", identity)


if __name__ == "__main__":
    unittest.main()
