"""Historical comparisons keep their recorded source after product changes."""
import sys
import hashlib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.baseline import load
from v2.engine_variant import load as load_variant
from localflow.v2.cleanup import engine as current


class BaselineTests(unittest.TestCase):
    def test_baseline_isolated_from_current_engine_and_validator(self):
        old = load()
        self.assertIsNot(old, current)
        self.assertIsNot(old.validate, current.validate)
        original = current.SALVAGE_MAX_WORDS
        try:
            current.SALVAGE_MAX_WORDS = 0
            self.assertEqual(old.SALVAGE_MAX_WORDS, 8)
        finally:
            current.SALVAGE_MAX_WORDS = original

    def test_e_keeps_its_original_validator_and_separator_change(self):
        old, variant = load(), load_variant()
        self.assertIs(old.validate, variant.validate)
        self.assertEqual(old._evidence_reason("Use 3, sorry, 4.", (4, 12)), "not_parallel")
        self.assertIsNone(variant._evidence_reason("Use 3, sorry, 4.", (4, 12)))

    def test_recorded_f_matches_evaluated_source_and_stays_isolated(self):
        recorded = load(recorded_f=True)
        # Source identities recorded before the completed 494-case F comparison.
        frozen = {
            'engine.py': 'a21e585a68eace9a90e8bd56b63be2f5c980ff277ed1523c9ab17240dc026fcb',
            'validation.py': '3cadd77ce48706dc9cf46ab8e3318f5589295e44db7e37ba53071f153bc80142',
            'prompts.py': 'b87a70528c78a7c734a235beb46053106ccf8156e49e4224de56fdd6c663aa3a',
            'document_nodes.py': 'cf2437faa0dfb4a6045d98ec12b0c1258ba58df385a6e012a33552d0a1c9a49d',
        }
        for name, digest in frozen.items():
            self.assertEqual(hashlib.sha256(Path(recorded.__file__).with_name(name).read_bytes()).hexdigest(), digest)
        self.assertIsNot(recorded, current)
        self.assertIsNot(recorded.validate, current.validate)
        self.assertIsNot(recorded, load())
        self.assertIsNone(recorded._evidence_reason("Use 3, sorry, 4.", (4, 12)))

    def test_multiple_engine_selections_are_rejected_before_loading(self):
        from v2.evaluate import Runner
        with self.assertRaisesRegex(ValueError, 'Choose one'):
            Runner('F', recorded_f=True, updated_engine=True)

    def test_recorded_inference_does_not_acquire_new_prefix_cache(self):
        from v2.baseline import load_runner
        from localflow.v2.cleanup.model import ModelRunner
        for recorded_f in (False, True):
            old = load_runner(recorded_f)
            self.assertIsNot(old, ModelRunner)
            self.assertFalse(hasattr(old, '_cached_prompt'))
            self.assertIs(old, load_runner(recorded_f))


if __name__ == "__main__":
    unittest.main()
