"""Historical comparisons keep their recorded source after product changes."""
import sys
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


if __name__ == "__main__":
    unittest.main()
