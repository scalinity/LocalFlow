"""A title's period and a clock abbreviation's before a lowercase word end no sentence.

"Please call Dr. Okafor today and do not wait" holds one sentence, so an
output writing "Dr Okafor" merges nothing, and neither does "9 a.m
tomorrow". A clock abbreviation before a capitalized word and every other
period still end their sentence, so a merge next to a negated sentence
still fails.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_title_periods.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class TitlePeriodTests(unittest.TestCase):
    def test_title_and_clock_periods_end_no_sentence(self):
        for source, output in (
            ("Please call Dr. Okafor today and do not wait.", "Please call Dr Okafor today and do not wait."),
            ("Ask Mrs. Lee whether the room is not booked.", "Ask Mrs Lee whether the room is not booked."),
            ("Do not start before 9 a.m. tomorrow.", "Do not start before 9 a.m tomorrow."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_periods_still_end_their_sentence(self):
        for source, output in (
            ("Leave at 9 a.m. Do not wait for me.", "Leave at 9 a.m do not wait for me."),
            ("Do not deploy. Run the tests.", "Do not deploy, run the tests."),
        ):
            with self.subTest(source=source):
                self.assertIn("clause_scope", failures(source, output))


if __name__ == "__main__":
    unittest.main()
