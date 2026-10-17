"""A sentence next to a negated or conditional sentence keeps its boundary.

Merging two sentences can move one into the other's condition ("If the
migration fails, roll back the release, and we should notify the
client") or widen a negation, and conditions open in too many ways
("whenever", "as long as", "in case", "provided", "assuming", ...) for a
word list to tell a safe merge from an unsafe one. So every merge at a
source boundary beside a scope sentence fails clause_scope, whatever
conjunction opens the second sentence.

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
    def test_a_merge_beside_a_scope_sentence_fails(self):
        for source, output in (
            ("Do not deploy the build. Run the tests.", "Do not deploy the build, run the tests."),
            ("Do not open the valve. Or the vent.", "Do not open the valve, or the vent."),
            ("The calendar showed the room as free. But the confirmation email said the slot "
             "was not open.",
             "The calendar showed the room as free, but the confirmation email said the slot "
             "was not open."),
            ("If the migration fails, roll back the release. And we should notify the client.",
             "If the migration fails, roll back the release, and we should notify the client."),
            ("Whenever the build fails, do not deploy. And we should alert the team.",
             "Whenever the build fails, do not deploy, and we should alert the team."),
            ("As long as the client is on the call, share the dashboard. But do not show the "
             "invoices.",
             "As long as the client is on the call, share the dashboard, but do not show the "
             "invoices."),
            ("In case the vendor calls, take a message. But don't promise a date.",
             "In case the vendor calls, take a message, but don't promise a date."),
            ("Assuming the tests pass, don't block the merge. But we should rerun the benchmarks.",
             "Assuming the tests pass, don't block the merge, but we should rerun the benchmarks."),
        ):
            with self.subTest(source=source):
                self.assertIn("clause_scope", failures(source, output))


if __name__ == "__main__":
    unittest.main()
