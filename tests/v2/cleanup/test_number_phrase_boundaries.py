"""A number-word phrase does not run across punctuation.

"load the Thursday list, not the Tuesday one. Four, set the exposure"
read "one. Four" as the single value 5, so the spoken list "One, … Four,
…" rendered as numbered items failed numeric_values. A phrase's words are
separated by spaces only. A changed or dropped number word still fails.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_number_phrase_boundaries.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402

SOURCE = ("Please do these in order. One, power on the mount. Two, load the Thursday list, "
          "not the Tuesday one. Three, set the exposure to 120 seconds.")


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class NumberPhraseBoundaryTests(unittest.TestCase):
    def test_a_sentence_boundary_ends_a_number_phrase(self):
        output = ("Please do these in order:\n1. Power on the mount.\n2. Load the Thursday list, "
                  "not the Tuesday one.\n3. Set the exposure to 120 seconds.")
        self.assertEqual(failures(SOURCE, output), set())
        self.assertEqual(failures("we need twenty five. Two more arrive later.",
                                  "We need 25. 2 more arrive later."), set())

    def test_a_changed_number_word_still_fails(self):
        self.assertIn("numeric_values", failures(
            "we need twenty five. Two more arrive later.", "We need 25. 3 more arrive later."))
        self.assertIn("numeric_values", failures(
            "the Tuesday one. Four, set it", "The Tuesday one. Five, set it."))
        self.assertIn("numeric_values", failures(
            "we need twenty five. Two more arrive later.", "We need 27. 2 more arrive later."))


if __name__ == "__main__":
    unittest.main()
