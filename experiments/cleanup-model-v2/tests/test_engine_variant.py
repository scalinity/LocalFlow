"""Parser repair must accept separators without relaxing meaning guards."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.engine_variant import load
from localflow.v2.cleanup import engine as production


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.variant = load()

    def check_span(self, source, deletion, accepted, reason=None, protected=()):
        got, rejected = self.variant.parse_correction_output(deletion, source, list(protected))
        self.assertEqual(bool(got), accepted, (source, got, rejected))
        if reason:
            self.assertIn(reason, [p.reason for p in rejected])

    def test_comma_parallel_values(self):
        for source, deletion in [
            ("Use 3, sorry, 4 samples.", "3, sorry"),
            ("Meet Monday, actually, Tuesday at noon.", "Monday, actually"),
            ("Send 12, no, 15 copies.", "12, no"),
            ("Schedule June, sorry, July visits.", "June, sorry"),
            ("Use 2.5, actually, 3.5 mL.", "2.5, actually"),
        ]:
            with self.subTest(source=source):
                self.check_span(source, deletion, True)

    def test_original_failure_reproduced(self):
        got, rejected = production.parse_correction_output("3, sorry", "Use 3, sorry, 4 samples.", [])
        self.assertFalse(got)
        self.assertEqual(rejected[0].reason, "not_parallel")

    def test_nonparallel_and_ordinary_language(self):
        for source, deletion, reason in [
            ("The answer is no, we checked.", "answer is no", "not_parallel"),
            ("We actually, shipped the patch.", "We actually", "no_outdated_value"),
            ("I mean, it is essential.", "I mean", "bare_marker"),
            ("Three I mean, it is essential.", "Three I mean", "emphasis_not_correction"),
            ("Use 3, sorry, not 4 samples.", "3, sorry", "not_parallel"),
            ("At 3. Sorry, 4 works.", "3. Sorry", "crosses_sentence"),
            ("Move the review Monday, sorry, Tuesday.", "review Monday, sorry", "overbroad_calendar_value"),
            ("Use 3, sorry.", "3, sorry", "no_replacement"),
        ]:
            with self.subTest(source=source):
                self.check_span(source, deletion, False, reason)

    def test_existing_safeguards(self):
        self.check_span("Use 3, sorry, 4 samples.", "3, sorry", False, "protected_span", [(4,12,"literal")])
        self.check_span("3, sorry, 4 then 3, sorry, 4.", "3, sorry", False, "ambiguous_occurrence")
        got, rejected = self.variant.parse_correction_output("3, sorry", "Use 3, sorry, 4.", [], limit_hit=True)
        self.assertFalse(got)
        self.assertEqual(rejected[0].reason, "batch_truncated")

    def test_production_module_unchanged(self):
        self.assertIsNot(production, self.variant)
        self.assertEqual(production._evidence_reason("Use 3, sorry, 4.", (4,12)), "not_parallel")
        self.assertIsNone(self.variant._evidence_reason("Use 3, sorry, 4.", (4,12)))


if __name__ == "__main__":
    unittest.main()
