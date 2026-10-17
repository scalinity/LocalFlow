"""Reply quote styling survives current cleanup and versioned evaluation."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v2 import evaluate
from lfx.evaluate import postprocess as historical_postprocess
from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


class QuoteUnwrapTests(unittest.TestCase):
    def test_equivalent_curly_double_source_retains_model_ascii_quotes(self):
        source = "“The draft is final.”"
        raw = '"The draft is final."'
        self.assertEqual(evaluate.postprocess(raw, source), raw)
        self.assertTrue(validate(source, raw).accepted)
        # Historical output interpretation remains explicit and unchanged.
        self.assertEqual(historical_postprocess(raw, source), "The draft is final.")

    def test_engine_and_evaluator_agree_on_literal_and_wrapper_controls(self):
        cases = (
            ("“The draft is final.”", '"The draft is final."', '"The draft is final."'),
            ("“the draft is final.”", '"The draft is final."', '"The draft is final."'),
            ('"The draft is final."', '"The draft is final."', '"The draft is final."'),
            ("“The draft is final.”", "“The draft is final.”", "“The draft is final.”"),
            ("The draft is final.", '"The draft is final."', "The draft is final."),
            ("“The draft is final.”", '"“The draft is final.”"', "“The draft is final.”"),
            ("‘The draft is final.’", '"‘The draft is final.’"', "‘The draft is final.’"),
            ('He said "stop".', '"He said "stop"."', 'He said "stop".'),
        )
        for source, raw, expected in cases:
            with self.subTest(source=source, raw=raw):
                def generate(prompt, max_tokens):
                    return {"text": raw, "output_tokens": 9,
                            "limit_hit": False, "prompt": prompt}
                result = CleanupEngine(generate, model_id="fixture").clean(source)
                self.assertEqual(result.text, expected)
                self.assertEqual(result.path, "llm")
                self.assertEqual(evaluate.postprocess(raw, source), expected)

    def test_think_block_and_outer_space_cleanup_remain_permitted(self):
        raw = '\n <think>internal reply preparation</think> \n "The draft is final." \n'
        self.assertEqual(evaluate.postprocess(raw, " “The draft is final.” "),
                         '"The draft is final."')
        self.assertEqual(evaluate.postprocess(raw, "The draft is final."),
                         "The draft is final.")
        self.assertEqual(evaluate.postprocess(None, "The draft is final."), "")

    def test_actual_quote_loss_still_falls_back(self):
        source = "“The draft is final.”"
        raw = "The draft is final."
        def generate(prompt, max_tokens):
            return {"text": raw, "output_tokens": 7,
                    "limit_hit": False, "prompt": prompt}
        result = CleanupEngine(generate, model_id="fixture").clean(source)
        self.assertEqual(result.text, source)
        self.assertIn("literal_spans", result.fallback_reason)
        self.assertEqual(evaluate.postprocess(raw, source), raw)


class PostprocessIdentityTests(unittest.TestCase):
    def test_identity_binds_version_and_code_and_rejects_old_or_changed_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            model.mkdir()
            (model / "config.json").write_text('{"fixture": true}')
            cases = root / "cases.jsonl"
            cases.write_text('{"case_id":"fixture","split":"validation"}\n')
            loads = []

            class Runner:
                def __init__(self, *args):
                    self.path = model
                    self.module = evaluate.production
                    self.mx = types.SimpleNamespace(get_peak_memory=lambda: 0)
                def load(self):
                    loads.append(True)
                    return {"fixture": True}
                def clean(self, case):
                    return {"case_id": case["case_id"], "model_only": "fixture"}
                def unload(self):
                    pass

            with patch.object(evaluate, "ART", root), \
                    patch.object(evaluate, "Runner", Runner), \
                    patch.object(evaluate.importlib.metadata, "version", return_value="fixture"):
                args = ("G-fixture", cases, "fixture")
                self.assertEqual(evaluate.evaluate(*args, path=str(model), updated_engine=True),
                                 {"complete": 1})
                meta_path = root / "eval/fixture.meta.json"
                meta = json.loads(meta_path.read_text())
                expected = {
                    "version": evaluate.MODEL_ONLY_POSTPROCESS_VERSION,
                    "source_sha256": hashlib.sha256(
                        inspect.getsource(evaluate.postprocess).encode()).hexdigest(),
                }
                self.assertEqual(meta["identity"]["model_only_postprocess"], expected)
                self.assertEqual(evaluate.evaluate(*args, path=str(model), updated_engine=True),
                                 {"already_complete": 1})
                for binding in (None, {**expected, "version": "legacy"},
                                {**expected, "source_sha256": "different"}):
                    changed = json.loads(json.dumps(meta))
                    if binding is None:
                        del changed["identity"]["model_only_postprocess"]
                    else:
                        changed["identity"]["model_only_postprocess"] = binding
                    meta_path.write_text(json.dumps(changed))
                    with self.subTest(binding=binding), self.assertRaisesRegex(
                            RuntimeError, "another artifact or dataset"):
                        evaluate.evaluate(*args, path=str(model), updated_engine=True)
                self.assertEqual(len(loads), 1)


if __name__ == "__main__":
    unittest.main()
