"""Deterministic M15-A contracts. No microphone, clipboard, UI or models."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts/v2")]
import cleanup_benchmark as b
import benchmark_cleanup_candidates as runner
from localflow.v2.cleanup import CleanupEngine
from localflow.v2.cleanup.model import render_messages


class FakeProcess:
    def __init__(self, *args, **kwargs):
        self.alive = False
    def start(self): self.alive = True
    def is_alive(self): return self.alive
    def join(self, seconds): self.alive = False
    def terminate(self): self.alive = False
    def kill(self): self.alive = False


class FakePipe:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
    def poll(self, seconds): return bool(self.replies)
    def recv(self): return self.replies.pop(0)
    def send(self, value): self.sent.append(value)
    def close(self): pass


class FakeContext:
    def __init__(self, replies): self.pipe = FakePipe(replies)
    def Pipe(self): return self.pipe, SimpleNamespace(close=lambda: None)
    def Process(self, **kwargs): return FakeProcess()


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.manifest = json.loads((ROOT / "docs/v2/benchmarks/m15-cleanup-candidates.json").read_text())
        self.candidate = self.manifest["candidates"][0]
        (self.base / "input.txt").write_text("keep café and 30")
        b.atomic_json(self.base / "ref.json", {"text": "Keep café and 30."})
        self.case = {"case_id": "opaque_case", "family_id": "opaque_family", "stratum": "numeric",
            "origin": "human", "split": "held_out", "exposed": False, "reviewed": True,
            "reference_type": "intended_writing", "normalization_revision": "frozen-v1",
            "normalized": {"path": "input.txt", "sha256": b.file_hash(self.base / "input.txt")},
            "reference": {"path": "ref.json", "sha256": b.file_hash(self.base / "ref.json")}}
        self.corpus = {"schema": "m15-frozen-corpus/1", "reference_state": "frozen", "cases": [self.case]}
    def tearDown(self): self.tmp.cleanup()
    def write_corpus(self):
        b.atomic_json(self.base / "corpus.json", self.corpus)
        return self.base / "corpus.json"
    def test_manifest_schema(self):
        self.assertEqual(len(b.validate_manifest(self.manifest)), 7)
    def test_duplicate_candidates(self):
        self.manifest["candidates"].append(copy.deepcopy(self.candidate))
        with self.assertRaisesRegex(ValueError, "duplicate"): b.validate_manifest(self.manifest)
    def test_revision_must_be_immutable(self):
        self.candidate["immutable_revision"] = "main"
        with self.assertRaisesRegex(ValueError, "immutable"): b.validate_manifest(self.manifest)
    def test_absolute_identity_forbidden(self):
        self.candidate["repository_id"] = "/Users/example/Documents/LocalAI/model"
        with self.assertRaisesRegex(ValueError, "identity"): b.validate_manifest(self.manifest)
    def test_sampling_cannot_drift(self):
        self.candidate["sampling"]["temperature"] = .7
        with self.assertRaisesRegex(ValueError, "sampling"): b.validate_manifest(self.manifest)
    def test_cache_uses_revision_and_environment(self):
        snapshot = self.base / self.candidate["immutable_revision"]
        snapshot.mkdir()
        for n in ("config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors"):
            (snapshot / n).write_text("stub")
        candidate = {k: v for k, v in self.candidate.items() if k != "source_file_sizes"}
        with patch("huggingface_hub.snapshot_download", return_value=str(snapshot)) as download:
            self.assertEqual(b.resolve_cache(candidate), snapshot)
        self.assertEqual(download.call_args.kwargs, {"revision": self.candidate["immutable_revision"], "local_files_only": True})
    def test_missing_shard_refuses(self):
        snapshot = self.base / self.candidate["immutable_revision"]
        snapshot.mkdir()
        for n in ("config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors"):
            (snapshot / n).write_text("stub")
        b.atomic_json(snapshot / "model.safetensors.index.json", {"weight_map": {"w": "absent.safetensors"}})
        with patch("huggingface_hub.snapshot_download", return_value=str(snapshot)):
            with self.assertRaisesRegex(ValueError, "shard"): b.resolve_cache(self.candidate)
    def test_asr_cache_does_not_require_chat_tokenizer(self):
        snapshot = self.base / self.candidate["immutable_revision"]
        snapshot.mkdir()
        (snapshot / "config.json").write_text("{}")
        (snapshot / "model.safetensors").write_text("stub")
        candidate = {k: v for k, v in self.candidate.items() if k != "source_file_sizes"}
        with patch("huggingface_hub.snapshot_download", return_value=str(snapshot)):
            self.assertEqual(b.resolve_cache(candidate, tokenizer_required=False), snapshot)
            with self.assertRaisesRegex(ValueError, "tokenizer"):
                b.resolve_cache(candidate)
    def test_frozen_text_fanout(self):
        self.assertEqual(b.load_corpus(self.write_corpus())["cases"], [self.case])
        inputs = [b.frozen_case(self.base, self.case)[0] for _ in self.manifest["candidates"]]
        self.assertEqual(len(set(inputs)), 1)
    def test_audio_hash(self):
        (self.base / "audio.wav").write_bytes(b"frozen-audio")
        self.case["audio"] = {"path": "audio.wav", "sha256": b.file_hash(self.base / "audio.wav")}
        b.load_corpus(self.write_corpus())
        (self.base / "audio.wav").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"): b.frozen_case(self.base, self.case)
    def test_reference_immutable(self):
        b.load_corpus(self.write_corpus())
        b.atomic_json(self.base / "ref.json", {"text": "changed"})
        with self.assertRaisesRegex(ValueError, "hash mismatch"): b.frozen_case(self.base, self.case)
    def test_relative_paths_and_symlinks(self):
        for name in ("../outside", "/private/outside"):
            with self.assertRaises(ValueError): b.asset(self.base, {"path": name, "sha256": "a"*64})
        (self.base / "linked.txt").symlink_to(self.base / "input.txt")
        with self.assertRaisesRegex(ValueError, "symlink"):
            b.asset(self.base, {"path": "linked.txt", "sha256": self.case["normalized"]["sha256"]})
    def test_review_cannot_be_fabricated(self):
        self.case["reviewed"] = False
        with self.assertRaisesRegex(ValueError, "adjudicated"): b.load_corpus(self.write_corpus())
    def test_holdout_exposure(self):
        self.case["exposed"] = True
        with self.assertRaisesRegex(ValueError, "exposed"): b.load_corpus(self.write_corpus())
    def test_family_leakage(self):
        other = {**self.case, "case_id": "second", "split": "dev"}
        self.corpus["cases"].append(other)
        with self.assertRaisesRegex(ValueError, "leakage"): b.load_corpus(self.write_corpus())
    def test_m07_denominators(self):
        self.case["m07_v002"] = True
        with self.assertRaisesRegex(ValueError, "30/10/20"): b.load_corpus(self.write_corpus())
    def test_m07_reuse_exact_splits(self):
        self.corpus["cases"] = [{**self.case, "case_id": f"case_{i}", "family_id": f"family_{i}",
            "split": "dev" if i < 30 else "validation" if i < 40 else "held_out", "m07_v002": True}
            for i in range(60)]
        self.assertEqual(len(b.load_corpus(self.write_corpus())["cases"]), 60)
    def good_reply(self):
        return {"status": "COMPLETE", "metrics": {"critical_failure": False, "useful_cleanup": True,
            "fallback": False, "correction_opportunities": 1, "correct_resolutions": 1,
            "accepted_correction_count": 1, "correction_precision_denominator": 1}, "timing_ms": {"cleanup": 12},
            "memory": {"mlx_peak_bytes": 300}}
    def row(self, **changes):
        return {"candidate_id": "fake", "case_id": "case", "origin": "human", "track": "cleanup-only",
                "stratum": "correction", "length_band": "short", "split": "held_out",
                "reference_type": "intended_writing", **self.good_reply(), **changes}
    def test_human_synthetic_denominators(self):
        cohorts = b.grouped([self.row(), self.row(origin="synthetic", case_id="synthetic")])
        self.assertEqual(len(cohorts), 2)
        self.assertEqual([c["completed"] for c in cohorts], [1, 1])
    def test_failure_isolation(self):
        contexts = [FakeContext([{"status": "OOM"}]), FakeContext([
            {"status": "READY", "identity": {}}, self.good_reply(), {"status": "UNLOADED", "settled": {}}])]
        with patch.object(runner.mp, "get_context", side_effect=lambda _: contexts[0]):
            failed, _ = runner.run_candidate(self.candidate, [self.case], self.corpus, self.base,
                        self.base / "first", {}, "cleanup-only", 1, 1, warmup=False)
        contexts.pop(0)
        with patch.object(runner.mp, "get_context", side_effect=lambda _: contexts[0]):
            good, _ = runner.run_candidate({**self.candidate, "candidate_id": "second"}, [self.case],
                self.corpus, self.base, self.base / "second", {}, "cleanup-only", 1, 1, warmup=False)
        self.assertEqual(failed[0]["status"], "OOM")
        self.assertEqual(good[0]["status"], "COMPLETE")
    def test_oom_status(self): self.assertEqual(b.failure_state(MemoryError()), "OOM")
    def test_timeout_status(self): self.assertEqual(b.failure_state(TimeoutError()), "TIMEOUT")
    def test_template_status(self): self.assertEqual(b.failure_state(b.TemplateError()), "TEMPLATE_INCOMPATIBLE")
    def test_bounded_timeout_kills_worker(self):
        process = FakeProcess(); process.start()
        with patch("cleanup_candidate_adapter.system_memory", return_value={"swapouts": 0, "system_available_bytes": 10**10}):
            self.assertEqual(runner.receive(FakePipe([]), process, .001)["status"], "TIMEOUT")
        self.assertFalse(process.is_alive())
    def test_resume_skips_completed(self):
        ctx = FakeContext([{"status": "READY", "identity": {}}, self.good_reply(), {"status": "UNLOADED", "settled": {}}])
        with patch.object(runner.mp, "get_context", return_value=ctx):
            first, _ = runner.run_candidate(self.candidate, [self.case], self.corpus, self.base,
                           self.base / "run", {}, "cleanup-only", 1, 1, warmup=False)
        with patch.object(runner.mp, "get_context", side_effect=AssertionError("must not reload")):
            second, load = runner.run_candidate(self.candidate, [self.case], self.corpus, self.base,
                           self.base / "run", {}, "cleanup-only", 1, 1, warmup=False)
        self.assertEqual(first, second); self.assertIsNone(load)
    def test_resume_identity_drift(self):
        path = runner.checkpoint_path(self.base, self.candidate["candidate_id"], self.case["case_id"], 0, "cleanup-only")
        b.atomic_json(path, {"status": "COMPLETE", "run_identity": {"old": True}})
        with self.assertRaisesRegex(ValueError, "identity drift"):
            runner.run_candidate(self.candidate, [self.case], self.corpus, self.base, self.base, {}, "cleanup-only", 1, 1)
    def test_failed_units_retry_on_resume(self):
        path = runner.checkpoint_path(self.base, self.candidate["candidate_id"], self.case["case_id"], 0, "cleanup-only")
        b.atomic_json(path, {"status": "TIMEOUT", "run_identity": {}})
        ctx = FakeContext([{"status": "READY", "identity": {}}, self.good_reply(), {"status": "UNLOADED", "settled": {}}])
        with patch.object(runner.mp, "get_context", return_value=ctx):
            rows, _ = runner.run_candidate(self.candidate, [self.case], self.corpus, self.base, self.base, {}, "cleanup-only", 1, 1, warmup=False)
        self.assertEqual(rows[0]["status"], "COMPLETE")
    def test_correction_scoring(self):
        source = "meet monday no wait tuesday"
        def generate(prompt, maximum):
            return {"text": "monday no wait" if "Find the self-corrections" in prompt else "Meet Tuesday.", "limit_hit": False}
        result = CleanupEngine(generate).clean(source)
        metrics = b.score(source, {"text": "Meet Tuesday.", "correction_spans": [[5, 19]]}, result)
        self.assertEqual(metrics["correct_resolutions"], 1)
        self.assertEqual(metrics["wrong_corrections"], 0)
        self.assertEqual(metrics["missed_corrections"], 0)
        self.assertEqual(b.aggregate([self.row(metrics=metrics)])["correction_recall"], 1)
    def test_wrong_correction_and_miss(self):
        source = "meet monday no wait tuesday"
        result = CleanupEngine(lambda p, n: {"text": "monday no wait" if "Find the self-corrections" in p else "Meet Tuesday."}).clean(source)
        metrics = b.score(source, {"text": "Meet Monday no wait Tuesday.", "correction_spans": []}, result)
        self.assertEqual(metrics["wrong_corrections"], 1)
        self.assertTrue(metrics["critical_failure"])
    def test_fallback_is_not_useful(self):
        source = "keep 30 and do not deploy"
        result = CleanupEngine(lambda p, n: {"text": "Deploy 300."}).clean(source)
        metrics = b.score(source, {"text": source}, result)
        self.assertTrue(metrics["fallback"]); self.assertFalse(metrics["useful_cleanup"])
        self.assertTrue(metrics["validator_reject"])
    def test_unchanged_is_not_useful(self):
        source = "keep 30"
        metrics = b.score(source, {"text": source}, CleanupEngine(lambda p,n: {"text": source}).clean(source))
        self.assertFalse(metrics["useful_cleanup"])
    def test_latency_and_failed_denominator(self):
        s = b.aggregate([self.row(), self.row(status="TIMEOUT")])
        self.assertEqual(s["timing_ms"]["cleanup"]["p95"], 12)
        self.assertEqual(s["timing_ms"]["cleanup"]["failures"], 1)
        self.assertEqual(s["semantic_gate"], "INCOMPLETE")
        self.assertIsNone(b.quantiles([])["p95"])
    def test_nonfinite_latency_refuses(self):
        for v in (float("nan"), float("inf"), -1):
            with self.assertRaises(ValueError): b.quantiles([v])
    def test_memory_validation(self):
        m = {"mechanism": "ps_rss+resource_ru_maxrss+mlx_allocator+vm_stat", "missing_reason": "not_measured"}
        b.validate_memory(m)
        for v in (-1, float("nan"), "123", True):
            with self.assertRaises(ValueError): b.validate_memory({**m, "rss_bytes": v})
    def test_pareto_fronts(self):
        p = [{"candidate_id": "a", "f": 0, "ms": 10}, {"candidate_id": "b", "f": 1, "ms": 12},
             {"candidate_id": "c", "f": 1, "ms": 5}, {"candidate_id": "d", "f": None, "ms": 0}]
        self.assertEqual(b.pareto(p, ["f", "ms"]), ["a", "c"])
    def test_audio_replay_measures_actual_stages(self):
        import numpy as np
        import soundfile as sf
        from cleanup_candidate_adapter import CandidateAdapter
        adapter = CandidateAdapter(self.candidate)
        adapter.identity = {"chat_template_sha256": "fake-template-for-mechanics"}
        adapter.asr = SimpleNamespace(model_sample_rate=lambda: 16000,
                                      transcribe=lambda samples: "keep thirty percent")
        adapter.asr_identity = {"repository_id": "test/asr", "immutable_revision": "a"*40}
        adapter.render = render_messages
        adapter.generate = lambda prompt, maximum: {"text": json.loads(
            prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0])["transcript"]}
        sf.write(self.base / "replay.wav", np.zeros(1600, dtype=np.float32), 16000, subtype="FLOAT")
        source, result, timing, identity = adapter.audio_replay(self.base / "replay.wav", self.case)
        self.assertIn("30%", source)
        self.assertEqual(result.text, source)
        self.assertGreater(timing["end_to_end"], 0)
        self.assertGreaterEqual(timing["end_to_end"], timing["cleanup"])
        self.assertIn("normalization_revision", identity)
        self.assertEqual(identity["asr"], adapter.asr_identity)
    def test_audio_replay_refuses_wrong_rate(self):
        import numpy as np
        import soundfile as sf
        from cleanup_candidate_adapter import CandidateAdapter
        adapter = CandidateAdapter(self.candidate)
        adapter.asr = SimpleNamespace(model_sample_rate=lambda: 16000,
                      transcribe=lambda samples: (_ for _ in ()).throw(AssertionError("must not decode")))
        sf.write(self.base / "bad.wav", np.zeros(100, dtype=np.float32), 8000)
        with self.assertRaisesRegex(ValueError, "format"):
            adapter.audio_replay(self.base / "bad.wav", self.case)
    def test_blind_cli_reads_completed_units_only(self):
        self.write_corpus()
        for cid, text in ((self.candidate["candidate_id"], "output one"),
                          (self.manifest["candidates"][1]["candidate_id"], "output two")):
            b.atomic_json(runner.checkpoint_path(self.base / "run", cid, self.case["case_id"], 0, "cleanup-only"),
                {"status": "COMPLETE", "input_sha256": self.case["normalized"]["sha256"], "private": {"output": text}})
        args = ["runner", "--corpus", str(self.base / "corpus.json"), "--output", str(self.base / "run"),
                "--blind-finalists", self.candidate["candidate_id"] + "," + self.manifest["candidates"][1]["candidate_id"]]
        # This unit owns blind-queue mechanics; the CLI gate regression below
        # separately proves that unreviewed acceptance cannot start models.
        with patch.object(sys, "argv", args), patch.object(runner, "private_output", return_value=self.base / "run"), \
                patch.object(runner, "validate_freeze_lock"):
            self.assertEqual(runner.main(), 0)
        queue = (self.base / "run/blind-finalists.json").read_text()
        self.assertNotIn(self.candidate["candidate_id"], queue)
        self.assertIn("Output A", queue)
    def test_blind_queue(self):
        shown, key = b.blind_queue("case", "source", "reference", {"secret_model_one": "x", "secret_model_two": "y"})
        self.assertNotIn("secret_model", json.dumps(shown))
        self.assertEqual(set(key.values()), {"case", "secret_model_one", "secret_model_two"})
        self.assertEqual(shown["labels"], ["A", "B", "tie", "neither", "uncertain"])
    def test_private_redaction(self):
        row = {**self.row(), "private": {"source": "PRIVATE-SENTINEL", "output": "PRIVATE-SENTINEL"},
               "prompt": "PRIVATE-SENTINEL", "exception": "PRIVATE-SENTINEL",
               "identity": {"rendered_prompt": "PRIVATE-SENTINEL"},
               "metrics": {**self.row()["metrics"], "raw_output": "PRIVATE-SENTINEL"}}
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(b.public_row(row)))
        b.write_report(self.base / "public", [row], {}, [])
        self.assertNotIn("PRIVATE-SENTINEL", (self.base / "public/results.json").read_text())
    def test_production_default_unchanged(self):
        import subprocess
        for path in ("localflow/config.py", "localflow/v2/cleanup/model.py", "localflow/v2/cleanup/engine.py", "localflow/v2/cleanup/validation.py"):
            # Integration preserves the authorized M07 engine repair; M15-A
            # still changes no production defaults, model or validation.
            revision = ("8c08b82f15e75e83fb06bcd5aa2e102c50761903"
                        if path.endswith("/engine.py") else
                        "5da68360a0e5b1ea9303f799ea5c550db4f210fe")
            original = subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)
            self.assertEqual((ROOT / path).read_bytes(), original)
    def test_atomic_checkpoint_no_partial(self):
        b.atomic_json(self.base / "checkpoint.json", {"status": "COMPLETE"})
        self.assertEqual(json.loads((self.base / "checkpoint.json").read_text())["status"], "COMPLETE")
        self.assertFalse(list(self.base.glob(".checkpoint-*")))

    def freeze_fixture(self):
        """Synthetic test declarations, never an owner corpus or gold."""
        import numpy as np
        import soundfile as sf
        corpus = copy.deepcopy(self.corpus)
        corpus["owner_review_complete"] = True
        corpus["asr"] = {"repository_id": "mlx-community/parakeet-tdt-0.6b-v3",
                         "immutable_revision": "ed2b7e8c15f9aaa0b5772e2efb986255eaef7e15"}
        normalizer = ROOT / "localflow/v2/normalize"
        files = sorted([*normalizer.rglob("*.py"), *normalizer.rglob("*.json")])
        corpus["normalized_input_identity"] = {"asr": corpus["asr"],
            "normalizer_files_sha256": b.digest({str(p.relative_to(ROOT)): b.file_hash(p) for p in files}),
            "runtime": b.runtime_versions()}
        b.atomic_json(self.base / "ref.json", {"text": "Keep café and 30.", "author": "owner", "candidate_output_used": False})
        b.atomic_json(self.base / "negative.json", {"text": "", "author": "owner", "candidate_output_used": False})
        (self.base / "verbatim.txt").write_text("synthetic fixture words")
        corpus["cases"] = []
        tags = ["ordinary_prose", "long_developer_prompt", "corrections", "standalone_markers",
                "numeric", "technical_names", "questions", "negation_constraints", "literal",
                "lists_steps", "paragraphs", "multilingual", "quiet", "noisy"]
        for n in range(220):
            case = copy.deepcopy(self.case)
            case.update(case_id=f"case_{n}", family_id=f"family_{n}",
                        split="dev", exposed=False, adjudication_status="CONFIRMED",
                        retention_status="OWNER_APPROVED", privacy_class="PRIVATE_OWNER_ONLY")
            case["reference"] = {"path": "ref.json", "sha256": b.file_hash(self.base / "ref.json")}
            if n < 160:
                wav = self.base / f"audio_{n}.wav"
                sf.write(wav, np.full(160, n / 1000, dtype=np.float32), 16000, subtype="FLOAT")
                case["audio"] = {"path": wav.name, "sha256": b.file_hash(wav)}
            if n < 140:
                case.update(speech_band="short" if n < 60 else "diverse", coverage_tags=tags,
                    verbatim_reference={"path": "verbatim.txt", "sha256": b.file_hash(self.base / "verbatim.txt")})
            elif n < 160:
                case.update(reference_type="negative", negative_type="silence")
                case["reference"] = {"path": "negative.json", "sha256": b.file_hash(self.base / "negative.json")}
            else:
                case.update(m07_v002=True, m07_source="legacy_749",
                            split="dev" if n < 190 else "validation" if n < 200 else "held_out")
            corpus["cases"].append(case)
        path = self.base / "freeze.json"
        b.atomic_json(path, corpus)
        return path, corpus

    def test_freeze_requires_owner_review(self):
        with self.assertRaisesRegex(ValueError, "owner review"):
            b.freeze_requirements(self.write_corpus(), self.corpus)

    def test_cli_freeze_gate_precedes_model_work(self):
        args = ["benchmark_cleanup_candidates.py", "--corpus", str(self.write_corpus()),
                "--output", str(self.base)]
        with patch.object(sys, "argv", args), patch.object(runner, "private_output", return_value=self.base), \
                patch.object(runner, "run_candidate") as run:
            with self.assertRaisesRegex(ValueError, "owner review"):
                runner.main()
            run.assert_not_called()

    def test_freeze_requires_full_coverage(self):
        path, corpus = self.freeze_fixture()
        corpus["cases"].pop(0)
        with self.assertRaisesRegex(ValueError, "60 short"):
            b.freeze_requirements(path, corpus)

    def test_freeze_rejects_candidate_gold(self):
        path, corpus = self.freeze_fixture()
        b.atomic_json(self.base / "ref.json", {"text": "Keep café and 30.", "author": "owner", "candidate_output_used": True})
        for case in corpus["cases"]:
            if case["reference"]["path"] == "ref.json":
                case["reference"]["sha256"] = b.file_hash(self.base / "ref.json")
        with self.assertRaisesRegex(ValueError, "owner reference provenance"):
            b.freeze_requirements(path, corpus)

    def test_freeze_requires_verbatim_reference(self):
        path, corpus = self.freeze_fixture()
        del corpus["cases"][0]["verbatim_reference"]
        with self.assertRaisesRegex(ValueError, "asset schema"):
            b.freeze_requirements(path, corpus)

    def test_freeze_requires_legacy_reuse(self):
        path, corpus = self.freeze_fixture()
        del corpus["cases"][-1]["m07_source"]
        with self.assertRaisesRegex(ValueError, "legacy provenance"):
            b.freeze_requirements(path, corpus)

    def test_freeze_lock_protects_split_and_context(self):
        path, corpus = self.freeze_fixture()
        b.atomic_json(str(path) + ".freeze-lock.json", {"state": "M15A_CORPUS_FROZEN_READY_TO_BENCHMARK",
                                                       "corpus_sha256": b.file_hash(path)})
        b.validate_freeze_lock(path, b.load_corpus(path))
        corpus["cases"][0]["destination_profile"] = "changed"
        b.atomic_json(path, corpus)
        with self.assertRaisesRegex(ValueError, "freeze lock drift"):
            b.validate_freeze_lock(path, b.load_corpus(path))

    def test_freeze_rechecks_verbatim_bytes(self):
        path, corpus = self.freeze_fixture()
        (self.base / "verbatim.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            b.frozen_case(path.parent, corpus["cases"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
