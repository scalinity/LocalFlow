"""A doubled "they" or a doubled modal that is never a noun is a stutter.

"Then they they punch the holes" and "we should should rehearse" say the
word once in the cleanup, like "we we". "had had", "that that", "will
will" ("the will will be read") and "can can" ("the can can be opened")
can be grammatical and keep both copies.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_pronoun_modal_stutter.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class PronounModalStutterTests(unittest.TestCase):
    def test_a_doubled_they_or_modal_is_said_once(self):
        for source, output in (
            ("Then they they punch the holes along the spine.", "Then they punch the holes along the spine."),
            ("Note to self we should should rehearse the migration.", "Note to self, we should rehearse the migration."),
            ("It would would help to rerun it.", "It would help to rerun it."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_grammatical_doubles_keep_both_copies(self):
        for source, output in (
            ("She had had enough of the delays.", "She had enough of the delays."),
            ("I think that that is right.", "I think that is right."),
            ("The will will be read on Monday.", "The will be read on Monday."),
            ("The can can be opened by hand.", "The can be opened by hand."),
        ):
            with self.subTest(source=source):
                self.assertIn("coverage", failures(source, output))


if __name__ == "__main__":
    unittest.main()
