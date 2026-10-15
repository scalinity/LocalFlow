"""A sentence that opens with its own conjunction may join the previous one at a comma.

"the calendar showed it as free. But the confirmation email said the slot
was not open" becomes "free, but the confirmation email said …": the kept
"but" starts a new clause, so the merge cannot widen a negation or a
condition. "and"/"or" qualify only before their own finite verb ("Or
should I skip it"). A merge without a conjunction, without a comma, or
with an "or" that may share the previous predicate still fails.

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
            ("When I booked the room, the calendar showed it as free. But the confirmation "
             "email said the slot was not open.",
             "When I booked the room, the calendar showed it as free, but the confirmation "
             "email said the slot was not open."),
            ("Do I add the butter only if the dough feels dry. Or should I skip it unless "
             "the recipe says otherwise?",
             "Do I add the butter only if the dough feels dry, or should I skip it unless "
             "the recipe says otherwise?"),
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
        ):
            with self.subTest(source=source):
                self.assertIn("clause_scope", failures(source, output))


if __name__ == "__main__":
    unittest.main()
