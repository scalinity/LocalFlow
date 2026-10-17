"""Synthetic baseline tests; no weights, real pools, clients, or inference."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from v2 import research_baselines as b, baseline_cost as cost
from v2.common import file_sha256, read_json, read_jsonl, write_json, write_jsonl
from lfx.common import sha256_json


def make_pool(root, split, n=8):
    directory = root / split
    directory.mkdir(parents=True)
    rows = [{"case_id": f"{split}-{i}", "split": split, "origin": "synthetic",
             "model_input": f"synthetic {split} item {i}", "target": f"Synthetic {split} item {i}.",
             "category": "punctuation", "is_noop": False, "gold_lines": [],
             "critical_facts": [], "protected_spans": [], "vocabulary_pairs": []} for i in range(n)]
    path = directory / ("train.jsonl" if split == "train" else "validation.jsonl")
    write_jsonl(path, rows)
    if split == "train":
        captures = [{"pair_id": r["case_id"], "family_id": r["case_id"], "calls": [
            {"role": "main", "prompt": '<|im_start|>user\n' + json.dumps({"transcript": r["model_input"]}) +
             '<|im_end|>\n<|im_start|>assistant\n', "completion": r["target"]}]} for r in rows]
        write_jsonl(directory / "train_captures.jsonl", captures)
    write_json(directory / "freeze.json", {"files": {p.name: file_sha256(p) for p in directory.glob("*.jsonl")}})
    return path, rows


def ledger():
    return {"entries": {"g": {"purpose": "generation", "state": "settled", "actual_usd": 0.1,
                              "max_usd": 1, "usage": {"input": 1000, "output": 50}},
                         "j": {"purpose": "judging", "state": "settled", "actual_usd": 0.2,
                               "max_usd": 1, "usage": {"input": 2000, "output": 100}}}, "reservations": {}}


class PoolTests(unittest.TestCase):
    def test_selector_is_deterministic_order_independent_and_train_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = make_pool(Path(tmp), "train")
            manifest = b.select_fewshot(path, Path(tmp) / "fewshot.json")
            self.assertEqual(manifest, b.select_fewshot(path, Path(tmp) / "fewshot.json"))
            self.assertEqual(len(manifest["examples"]), 5)
            self.assertTrue(all(e["case_id"].startswith("train-") and e["split"] == "train" for e in manifest["examples"]))
            self.assertNotEqual(manifest["examples"], b.select_fewshot(path, seed=1)["examples"])
            captures_path = path.with_name("train_captures.jsonl")
            write_jsonl(captures_path, list(reversed(read_jsonl(captures_path))))
            freeze = read_json(path.with_name("freeze.json"))
            freeze["files"][captures_path.name] = file_sha256(captures_path)
            write_json(path.with_name("freeze.json"), freeze)
            self.assertEqual(manifest["examples"], b.select_fewshot(path)["examples"])

    def test_forbidden_paths_rejected_before_any_open(self):
        with patch.object(b, "read_json", side_effect=AssertionError("data opened")):
            for name in ("final", "test", "audio", "fresh", "locked", "comparison"):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Forbidden"):
                    b.pool(Path("/tmp") / name / "validation.jsonl", "development")

    def test_wrong_split_and_unfrozen_train_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, rows = make_pool(Path(tmp), "train")
            rows[0]["split"] = "validation"
            write_jsonl(path, rows)
            with self.assertRaisesRegex(ValueError, "frozen"):
                b.select_fewshot(path)
            freeze = read_json(path.with_name("freeze.json"))
            freeze["files"][path.name] = file_sha256(path)
            write_json(path.with_name("freeze.json"), freeze)
            with self.assertRaisesRegex(ValueError, "declared split"):
                b.select_fewshot(path)

    def test_foreign_capture_cannot_enter_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = make_pool(Path(tmp), "train")
            caps = path.with_name("train_captures.jsonl")
            rows = read_jsonl(caps)
            rows[0]["pair_id"] = "development-0"
            write_jsonl(caps, rows)
            freeze = read_json(path.with_name("freeze.json"))
            freeze["files"][caps.name] = file_sha256(caps)
            write_json(path.with_name("freeze.json"), freeze)
            with self.assertRaisesRegex(ValueError, "outside TRAIN"):
                b.select_fewshot(path)

    def test_development_overlap_and_manifest_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, rows = make_pool(Path(tmp), "train")
            manifest = b.select_fewshot(path)
            with self.assertRaisesRegex(ValueError, "overlaps"):
                b.validate_fewshot(manifest, rows)
            manifest["examples"][0]["main_answer"] = "changed"
            with self.assertRaisesRegex(ValueError, "Invalid"):
                b.validate_fewshot(manifest, [])


class CostTests(unittest.TestCase):
    def plans(self, max_tokens=100):
        return [{"system": s, "requests": {"a": {"model": m, "max_tokens": max_tokens,
                 "messages": [{"role": "user", "content": "synthetic"}]}}} for s, m in cost.CLOUD.items()]

    def test_settled_generation_and_judging_drive_projection(self):
        result = cost.require_budget(ledger(), self.plans())
        self.assertTrue(result["allowed"])
        self.assertEqual(result["settled_usage"]["input"], 3000)
        self.assertAlmostEqual(result["historical_actual_to_reserved_ratio"], 0.15)
        self.assertGreater(result["new_upper_usd"], result["estimated_usd"])

    def test_combined_cap_and_global_reservations_refuse(self):
        with self.assertRaisesRegex(RuntimeError, "cap exceeded"):
            cost.require_budget(ledger(), self.plans(int(cost.CAP_USD * 1_000_000)))
        led = ledger()
        led["reservations"]["other-work"] = 127
        with self.assertRaisesRegex(RuntimeError, "cap exceeded"):
            cost.require_budget(led, self.plans())
        led = ledger()
        led["entries"]["baseline"] = {"purpose": cost.PURPOSE, "state": "outstanding", "max_usd": cost.CAP_USD - 0.01}
        with self.assertRaisesRegex(RuntimeError, "cap exceeded"):
            cost.require_budget(led, [], new_upper=0.02)

    def test_missing_history_and_invalid_amounts_refuse(self):
        led = ledger()
        del led["entries"]["j"]
        with self.assertRaisesRegex(ValueError, "generation and judging"):
            cost.estimate(led, self.plans())
        for v in (-1, float("nan"), float("inf")):
            led = ledger()
            led["entries"]["g"]["actual_usd"] = v
            with self.assertRaisesRegex(ValueError, "finite"):
                cost.estimate(led, self.plans())


class HarnessTests(unittest.TestCase):
    def setup_plan(self, root):
        train, _ = make_pool(root, "train")
        cases, rows = make_pool(root, "validation", 2)
        fewshot = root / "fewshot.json"
        b.select_fewshot(train, fewshot)
        plans = []
        for system in cost.CLOUD:
            out = root / (system + ".json")
            b.plan(system, cases, fewshot, out)
            plans.append(out)
        return cases, rows, plans

    def test_cloud_plan_has_exactly_five_examples_and_no_client(self):
        with tempfile.TemporaryDirectory() as tmp, patch("v2.common.anthropic_client", side_effect=AssertionError("client created")):
            cases, rows, plans = self.setup_plan(Path(tmp))
            for path in plans:
                plan = read_json(path)
                self.assertEqual(len(plan["requests"]), len(rows))
                for params in plan["requests"].values():
                    self.assertEqual(len(params["messages"]), 11)
                    self.assertEqual(params["system"], b.production.prompts.build_messages({"transcript": "x"})[0]["content"])
                    self.assertNotIn("temperature", params)
                    self.assertEqual({k: params[k] for k in b.THINKING[plan["system"]]}, b.THINKING[plan["system"]])

    def test_local_render_keeps_exact_production_messages(self):
        messages = b.production.prompts.build_messages({"transcript": "synthetic input"})
        runner = b.BaselineRunner("base-4b-prod-prompt")
        runner.mr = SimpleNamespace(render=lambda x: x)
        self.assertEqual(runner.render(messages), messages)
        self.assertGreater(len(messages), 2)

    def test_local_fake_records_prompt_response_and_replay_fields(self):
        runner = b.BaselineRunner("base-4b-prod-prompt")
        def stream(prompt, max_tokens):
            messages = json.loads(prompt)
            source = json.loads(messages[-1]["content"])["transcript"]
            yield SimpleNamespace(text=source.capitalize() + ".", finish_reason="stop")
        runner.mr = SimpleNamespace(render=lambda messages: json.dumps(messages), stream=stream,
                                    template_revision="synthetic-template")
        row = runner.clean({"case_id": "validation-fake", "model_input": "synthetic item"})
        call = row["calls"][0]
        self.assertEqual(call["output"], "Synthetic item.")
        self.assertEqual(call["window"], row["model_only_windows"][0]["range"])
        self.assertIn("prompt", call)
        self.assertEqual(call["input"], "synthetic item")
        self.assertEqual(row["model"], "base-4b-prod-prompt")

    def test_batch_fakes_roundtrip_raw_calls_resume_and_score(self):
        from lfx import batches
        from v2.score import aggregate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases, rows, plans = self.setup_plan(root)
            created = []

            def factory(name, requests, model):
                created.append(name)
                directory = root / "fake-waves" / name
                outcomes, results = {}, []
                for rid, params in requests.items():
                    source = json.loads(params["messages"][-1]["content"])["transcript"]
                    message = {"stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 3},
                               "content": [{"type": "text", "text": source.capitalize() + "."}]}
                    cid = rid + "-a1"
                    results.append({"custom_id": cid, "result": {"type": "succeeded", "message": message}})
                    outcomes[rid] = {"status": "succeeded", "batch_id": "fake", "custom_id": cid}
                write_jsonl(directory / "results-fake.jsonl", results)
                return SimpleNamespace(dir=directory, requests=requests, outcomes=outcomes,
                                       manifest={"attempts": [{"state": "collected", "batch_id": "fake"}]},
                                       run=lambda **kw: None)

            with patch.object(b, "ART", root), patch.object(b, "RESEARCH", root / "research"), \
                    patch.object(batches, "ledger", side_effect=ledger):
                b.batch_run("sonnet-5-5-fewshot", cases, plans, wave_factory=factory)
                output = read_jsonl(root / "eval/development-sonnet-5-5-fewshot.jsonl")
                self.assertEqual(len(output), len(rows))
                self.assertIn("synthetic", aggregate(rows, output))
                for row in output:
                    raw = row["calls"][0]
                    self.assertEqual(raw["output"], row["model_only_windows"][0]["text"])
                    self.assertEqual(raw["role"], "cleanup")
                    self.assertEqual(raw["depth"], 0)
                    self.assertIn("raw_response", raw)
                    self.assertIn("input_sha256", raw)
                    runner = b.BaselineRunner("sonnet-5-5-fewshot", fewshot=read_json(plans[0])["fewshot"],
                                              responses=read_json(root / "research/sonnet-5-5-fewshot/responses.json"))
                    case = next(c for c in rows if c["case_id"] == row["case_id"])
                    self.assertEqual(runner.clean(case)["delivered"], row["delivered"])
                b.batch_run("sonnet-5-5-fewshot", cases, plans, wave_factory=factory)
                self.assertEqual(len(created), 1)
                self.assertEqual(len(read_jsonl(root / "eval/development-sonnet-5-5-fewshot.jsonl")), len(rows))

    def test_truncation_raw_message_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            raw = {"custom_id": "r-a1", "result": {"type": "succeeded", "message": {
                "stop_reason": "max_tokens", "usage": {"output_tokens": 96},
                "content": [{"type": "text", "text": "partial response"}]}}}
            write_jsonl(path / "results-fake.jsonl", [raw])
            w = SimpleNamespace(dir=path, requests={"r": {}},
                                manifest={"attempts": [{"state": "collected", "batch_id": "fake"}]},
                                outcomes={"r": {"status": "truncated", "batch_id": "fake", "custom_id": "r-a1"}})
            response = b.responses_from_wave(w)["r"]
            self.assertTrue(response["limit_hit"])
            self.assertEqual(response["text"], "partial response")
            w.outcomes["r"]["status"] = "refused"
            with self.assertRaisesRegex(RuntimeError, "Missing/failed"):
                b.responses_from_wave(w)

    def test_adaptive_corrections_and_truncation_keep_every_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train, _ = make_pool(root, "train")
            manifest = b.select_fewshot(train)
            runner = b.BaselineRunner("opus-5-5-fewshot", fewshot=manifest)
            case = {"case_id": "validation-correction", "model_input": "use 2 no wait 3 samples for the synthetic experiment at noon. Send the notes.",
                    "split": "validation", "origin": "synthetic"}
            observed = []
            for _ in range(16):
                try:
                    row = runner.clean(case)
                    break
                except b.NeedCall as needed:
                    observed.append(needed.params)
                    last = needed.params["messages"][-1]["content"]
                    correction = not last.startswith("{")
                    output = "NONE" if correction else json.loads(last)["transcript"]
                    # Truncate the first main call; both child windows then
                    # need their own calls with their exact input payloads.
                    truncated = not correction and sum(not x["messages"][-1]["content"].startswith("{")
                                                       for x in observed) == len(observed) - 1
                    runner.responses[needed.request_id] = {
                        "text": output, "output_tokens": needed.params["max_tokens"] if truncated else 5,
                        "limit_hit": truncated, "finish_reason": "max_tokens" if truncated else "end_turn"}
            else:
                self.fail("Adaptive fake did not finish")
            self.assertTrue(any(c["role"] == "corrections" for c in row["calls"]))
            self.assertTrue(any(c["depth"] == 1 for c in row["calls"]))
            self.assertTrue(any(c["limit_hit"] for c in row["calls"]))
            self.assertEqual(len(row["calls"]), len(observed))
            self.assertEqual(runner.clean(case)["delivered"], row["delivered"])

    def test_capped_wave_never_submits_above_combined_or_global_cap(self):
        from lfx import batches
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = SimpleNamespace(messages=SimpleNamespace(batches=SimpleNamespace(create=unittest.mock.Mock())))
            led = ledger()
            led["entries"]["other-baseline"] = {"purpose": cost.PURPOSE, "state": "outstanding", "max_usd": cost.CAP_USD}
            params = {"model": "claude-sonnet-5-5", "max_tokens": 100, "messages": [{"role": "user", "content": "fake"}]}
            with patch.object(b, "RESEARCH", root / "research"), \
                    patch.object(batches, "CLAUDE_DIR", root / "claude"), patch.object(batches, "LEDGER", root / "claude" / "ledger.json"), \
                    patch.object(batches, "ledger", return_value=led), \
                    patch("v2.common.anthropic_client", return_value=client):
                wave = b.capped_wave("synthetic-cap", {"r": params}, params["model"])
                with self.assertRaisesRegex(RuntimeError, "cap exceeded"):
                    wave.submit_pending()
                client.messages.batches.create.assert_not_called()
                led["entries"].pop("other-baseline")
                led["reservations"]["parallel-work"] = 128
                with self.assertRaisesRegex(RuntimeError, "cap exceeded"):
                    wave.submit_pending()
                client.messages.batches.create.assert_not_called()

    def test_identity_refuses_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(b, "ART", Path(tmp)):
            _, meta_path, _, meta = b.output_state("base-4b-prod-prompt", {"hash": "a"})
            write_json(meta_path, meta)
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                b.output_state("base-4b-prod-prompt", {"hash": "b"})

    def test_memory_and_precision_substitution_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "weights.safetensors").write_bytes(b"synthetic")
            with self.assertRaisesRegex(RuntimeError, "cannot fit"):
                b.memory_fit(path, 1)
            write_json(path / "config.json", {"quantization": {"bits": 8, "group_size": 64}})
            with self.assertRaisesRegex(ValueError, "precision substitution"):
                b.validate_local(path, "base-9b-prod-prompt", {"quantization": "4-bit affine, group 64"})

    def test_base_receipt_checks_architecture_weights_and_adapter_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            cfg = {"quantization": {"bits": 4, "group_size": 64, "mode": "affine"},
                   "text_config": {"model_type": "qwen3_5_text", "hidden_size": 4096,
                                   "intermediate_size": 12288, "num_hidden_layers": 32}}
            write_json(path / "config.json", cfg)
            (path / "weights.safetensors").write_bytes(b"synthetic weights")
            receipt = {"base_repository": "Qwen/Qwen3.5-9B", "adapter": None,
                       "files": {p.name: file_sha256(p) for p in path.iterdir()}}
            write_json(path / "baseline-identity.json", receipt)
            c = {"quantization": "4-bit affine, group 64"}
            self.assertTrue(b.validate_local(path, "base-9b-prod-prompt", c))
            with self.assertRaisesRegex(ValueError, "architecture"):
                b.validate_local(path, "base-4b-prod-prompt", c)
            (path / "weights.safetensors").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                b.validate_local(path, "base-9b-prod-prompt", c)
            receipt["adapter"] = "synthetic adapter"
            write_json(path / "baseline-identity.json", receipt)
            with self.assertRaisesRegex(ValueError, "unfine-tuned"):
                b.validate_local(path, "base-9b-prod-prompt", c)



def make_final_pool(root, n=2):
    directory = root / "refinement/dataset"
    directory.mkdir(parents=True)
    rows = [{"case_id": f"test-{i}", "split": "test", "origin": "synthetic",
             "model_input": f"synthetic final item {i}", "target": f"Synthetic final item {i}.",
             "category": "punctuation", "is_noop": False, "gold_lines": [],
             "critical_facts": [], "protected_spans": [], "vocabulary_pairs": []} for i in range(n)]
    path = directory / "test.jsonl"
    write_jsonl(path, rows)
    write_json(directory / "freeze.json", {"files": {"test.jsonl": file_sha256(path)}})
    return path, rows


def seal(root):
    (root / "research/prereg").mkdir(parents=True, exist_ok=True)
    (root / "research/prereg/FROZEN").write_text("sealed\n")


class FinalSplitTests(unittest.TestCase):
    def test_final_pool_needs_the_seal_before_opening_anything(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(b, "ART", Path(tmp)):
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "sealed"):
                b.pool(root / "refinement/dataset/test.jsonl", "final")  # does not exist: refused before any open
            path, rows = make_final_pool(root)
            with self.assertRaisesRegex(ValueError, "sealed"):
                b.pool(path, "final")
            seal(root)
            self.assertEqual(b.pool(path, "final"), rows)
            other, _ = make_pool(root, "validation")
            with self.assertRaisesRegex(ValueError, "frozen final test.jsonl"):
                b.pool(other, "final")
            self.assertEqual(len(b.pool(other, "development")), 8)
            write_jsonl(path, rows[:1])
            with self.assertRaisesRegex(ValueError, "matching frozen"):
                b.pool(path, "final")

    def test_final_batch_writes_its_own_outputs_and_cache(self):
        from lfx import batches
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train, _ = make_pool(root, "train")
            fewshot = root / "fewshot.json"
            b.select_fewshot(train, fewshot)
            path, rows = make_final_pool(root)
            seal(root)

            def factory(name, requests, model):
                directory = root / "fake-waves" / name
                outcomes, results = {}, []
                for rid, params in requests.items():
                    source = json.loads(params["messages"][-1]["content"])["transcript"]
                    message = {"stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 3},
                               "content": [{"type": "text", "text": source.capitalize() + "."}]}
                    results.append({"custom_id": rid + "-a1", "result": {"type": "succeeded", "message": message}})
                    outcomes[rid] = {"status": "succeeded", "batch_id": "fake", "custom_id": rid + "-a1"}
                write_jsonl(directory / "results-fake.jsonl", results)
                return SimpleNamespace(dir=directory, requests=requests, outcomes=outcomes,
                                       manifest={"attempts": [{"state": "collected", "batch_id": "fake"}]},
                                       run=lambda **kw: None)

            with patch.object(b, "ART", root), patch.object(b, "RESEARCH", root / "research"), \
                    patch.object(batches, "ledger", side_effect=ledger):
                manifest = read_json(fewshot)
                for system in cost.CLOUD:
                    write_json(root / f"eval/development-{system}.meta.json",
                               {"identity": {"fewshot_sha256": "other examples"}})
                with self.assertRaisesRegex(ValueError, "differ from the development run"):
                    b.plan("sonnet-5-5-fewshot", path, fewshot, root / "refused.json", "final")
                plans = []
                for system in cost.CLOUD:
                    write_json(root / f"eval/development-{system}.meta.json",
                               {"identity": {"fewshot_sha256": sha256_json(manifest)}})
                    plans.append(root / f"{system}-final.json")
                    b.plan(system, path, fewshot, plans[-1], "final")
                b.batch_run("sonnet-5-5-fewshot", path, plans, wave_factory=factory, split="final")
                self.assertEqual(len(read_jsonl(root / "eval/final-sonnet-5-5-fewshot.jsonl")), len(rows))
                self.assertTrue((root / "research/final/sonnet-5-5-fewshot/responses.json").is_file())
                self.assertFalse((root / "eval/development-sonnet-5-5-fewshot.jsonl").exists())
                self.assertFalse((root / "research/sonnet-5-5-fewshot").exists())

    def test_final_local_run_needs_the_development_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, _ = make_final_pool(root)
            seal(root)
            write_json(root / "eval/development-base-9b-prod-prompt.meta.json",
                       {"identity": {"model_content_digest": "development weights"}})
            with patch.object(b, "ART", root), patch.object(b, "validate_local", return_value="other weights"):
                with self.assertRaisesRegex(ValueError, "differ from the development run"):
                    b.local_run("base-9b-prod-prompt", path, root / "model", "final")


if __name__ == "__main__":
    unittest.main()
