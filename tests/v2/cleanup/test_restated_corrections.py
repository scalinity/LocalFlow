"""An exact restatement with a new number authorizes dropping the old copy."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


def clean(source, output, protected=()):
    def generate(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(
        source, protected_spans=list(protected))


def failures(source, output, **kwargs):
    return {c.name for c in validate(source, output, **kwargs).critical_failures}


class RestatedCorrectionTests(unittest.TestCase):
    def test_restated_copy_with_a_new_number_replaces_the_old_copy(self):
        for source, target in (
            ("For tomorrow's rota, assign 4 rooms with extra linen needs to Marta. "
             "Sorry, 6 rooms with extra linen needs to Marta. Floors three and four only.",
             "For tomorrow's rota, assign 6 rooms with extra linen needs to Marta. "
             "Floors three and four only."),
            ("Start with 30 seconds of head turns per set, no, 45 seconds of head turns "
             "per set, if they tolerate it.",
             "Start with 45 seconds of head turns per set, if they tolerate it."),
            ("Assign 4 rooms per attendant on the north wing only, actually 6 rooms per "
             "attendant on the north wing only, and keep the suites separate.",
             "Assign 6 rooms per attendant on the north wing only, and keep the suites "
             "separate."),
            ("Please assign 4 rooms to Marta. Sorry, assign 6 rooms to Marta.",
             "Please assign 6 rooms to Marta."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, target), set())
                result = clean(source, target)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_anything_beyond_the_number_must_be_restated_exactly(self):
        for source, output, expected in (
            # A dropped qualifier, a changed recipient and a changed identifier.
            ("Assign 4 rooms with extra linen to Marta. Sorry, 6 rooms to Marta.",
             "Assign 6 rooms to Marta.", {"coverage", "numeric_values"}),
            ("Assign 4 rooms to Marta. Sorry, 6 rooms to Lena.",
             "Assign 6 rooms to Lena.", {"coverage", "numeric_values"}),
            ("Copy run_4 to the cache. Sorry, run_5 to the cache.",
             "Copy run_5 to the cache.", {"coverage", "numeric_values", "technical_tokens"}),
            # The same number is a repetition, not a correction.
            ("Book 4 rooms for Marta. Sorry, 4 rooms for Marta.",
             "Book 4 rooms for Marta.", {"coverage", "numeric_values"}),
            # An apology that opens a new clause restates nothing.
            ("We have 4 rooms for Marta. Sorry, 6 rooms for Marta would be too many.",
             "We have 6 rooms for Marta would be too many.", {"coverage", "numeric_values"}),
            # A negation in the old copy still counts, and its sentence keeps
            # its boundary.
            ("Leave 4 rooms not cleaned today. Sorry, 6 rooms not cleaned today.",
             "Leave 6 rooms not cleaned today.", {"clause_scope", "negation_coverage"}),
            # Both copies hold the same words; the number decides which survived.
            ("Assign 4 rooms with extra linen to Marta. Sorry, 6 rooms with extra linen "
             "to Marta.", "Assign 4 rooms with extra linen to Marta.", {"numeric_values"}),
            ('Write "assign 4 rooms to Marta, sorry, 6 rooms to Marta" on the board.',
             'Write "assign 6 rooms to Marta" on the board.',
             {"coverage", "numeric_values", "literal_spans"}),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), expected)
                self.assertEqual(clean(source, output).text, source)

    def test_a_protected_old_copy_stays(self):
        source = "Assign 4 rooms to Marta. Sorry, 6 rooms to Marta."
        output = "Assign 6 rooms to Marta."
        start = source.index("4 rooms")
        protected = [(start, start + len("4 rooms"))]
        self.assertIn("coverage", failures(source, output, protected_positions=protected))
        self.assertEqual(clean(source, output, protected).text, source)


if __name__ == "__main__":
    unittest.main()
