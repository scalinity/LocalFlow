"""A sentence that opens with its own conjunction may join the previous one at a comma.

"the calendar showed it as free. But the confirmation email said the slot
was not open" becomes "free, but the confirmation email said …": the kept
"but" starts a new clause, so the merge cannot widen the negation.
"and"/"or" qualify only before their own finite verb ("Or is it better").
A merge without a conjunction or a comma, an "or" that may share the
previous predicate, and any merge next to a condition or restriction (a
joined clause can fall inside "If …", "When …", "… unless …", "only …")
still fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_coordinate_merges.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class CoordinateMergeTests(unittest.TestCase):
    def test_a_conjunction_sentence_joins_at_a_comma(self):
        for source, output in (
            ("The calendar showed the room as free. But the confirmation email said the slot "
             "was not open.",
             "The calendar showed the room as free, but the confirmation email said the slot "
             "was not open."),
            ("Mention that gonioscopy was not performed. Or is it better to leave that out?",
             "Mention that gonioscopy was not performed, or is it better to leave that out?"),
            ("The pressure was 38 mmHg. And there is no history of trauma.",
             "The pressure was 38 mmHg, and there is no history of trauma."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_merges_still_fail(self):
        for source, output in (
            ("Do not deploy the build. Run the tests.", "Do not deploy the build, run the tests."),
            ("Do not open the valve. Or the vent.", "Do not open the valve, or the vent."),
            ("Do not deploy the build. But run the tests.", "Do not deploy the build but run the tests."),
            ("Book it only if the rotor is free. Then tell Dana.",
             "Book it only if the rotor is free, then tell Dana."),
            ("If the migration fails, roll back the release. And we should notify the client.",
             "If the migration fails, roll back the release, and we should notify the client."),
            ("If the migration fails, roll back the release. But we should notify the client.",
             "If the migration fails, roll back the release, but we should notify the client."),
            ("When the light turns green, go. But we should check the mirror.",
             "When the light turns green, go, but we should check the mirror."),
            ("Ship it unless the tests fail. And we should tell Dana.",
             "Ship it unless the tests fail, and we should tell Dana."),
            ("Book the centrifuge for Tuesday. But only if the rotor is not cracked.",
             "Book the centrifuge for Tuesday, but only if the rotor is not cracked."),
        ):
            with self.subTest(source=source):
                self.assertIn("clause_scope", failures(source, output))


if __name__ == "__main__":
    unittest.main()
