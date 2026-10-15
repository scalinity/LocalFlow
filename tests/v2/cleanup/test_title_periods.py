"""A title's period never cuts the sentence a scope word is read from.

"Do not ask Dr. Lee. Run the tests." holds its negation in the sentence
"Do not ask Dr. Lee.", so merging it with "Run the tests" fails. A
title's period can still end a sentence ("Do not drive past Elm Dr. Turn
left"), so a merge there fails too, and an output that writes a new
break after a title ("the Dr. Only after lunch") detaches the
restriction as any other break would.

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
    def test_a_title_keeps_its_sentence_whole(self):
        self.assertIn("clause_scope", failures("Do not ask Dr. Lee. Run the tests.",
                                               "Do not ask Dr. Lee, run the tests."))
        self.assertEqual(failures("Please call Dr. Okafor today and do not wait.",
                                  "Please call Dr. Okafor today and do not wait."), set())

    def test_a_title_period_that_ends_a_sentence_still_counts(self):
        for source, output in (
            ("Do not drive past Elm Dr. Turn left at the light.", "Do not drive past Elm Dr, turn left at the light."),
            ("Do not page the Prof. Email the lab instead.", "Do not page the Prof, email the lab instead."),
            ("Never forward it to Ms. Call her desk instead.", "Never forward it to Ms, call her desk instead."),
            ("Do not park on Elm Dr. use the garage.", "Do not park on Elm Dr, use the garage."),
            ("Do not page the Dr. Email the nurse instead.", "Do not page the Dr, email the nurse instead."),
            ("we will see the dr only after lunch", "We will see the Dr. Only after lunch."),
        ):
            with self.subTest(source=source):
                self.assertIn("clause_scope", failures(source, output))


if __name__ == "__main__":
    unittest.main()
