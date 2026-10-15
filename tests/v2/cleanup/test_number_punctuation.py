"""A number keeps its identity when sentence punctuation follows a closing bracket.

"call estimate_cost(plan, 12) so run explain" becomes "call
estimate_cost(plan, 12). So run explain"; the new period after ")" made
"12)." parse as the identifier "12)" instead of the number 12, and every
later value then counted as reordered. A changed number inside brackets
still fails.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_number_punctuation.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class NumberPunctuationTests(unittest.TestCase):
    def test_a_period_after_a_closing_bracket_keeps_the_value(self):
        for source, output in (
            ("then it calls estimate_cost(plan, 12) so run explain on node db-eu-04",
             "Then it calls estimate_cost(plan, 12). So run explain on node db-eu-04."),
            ("call run_cohort(n_subjects=240, seed=7), the output goes to the archive",
             "Call run_cohort(n_subjects=240, seed=7). The output goes to the archive."),
            ('the label says "batch 7" so keep it', 'The label says "batch 7". So keep it.'),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_a_changed_number_in_brackets_still_fails(self):
        source = "then it calls estimate_cost(plan, 12) so run explain"
        self.assertIn("numeric_values",
                      failures(source, "Then it calls estimate_cost(plan, 13). So run explain."))
        self.assertIn("numeric_values",
                      failures("set seed=7) and rerun", "Set seed=8). And rerun."))


if __name__ == "__main__":
    unittest.main()
