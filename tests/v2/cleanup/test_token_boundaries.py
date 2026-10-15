"""A correction span starts and ends on a token boundary."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import parse_correction_output


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class TokenBoundaryTests(unittest.TestCase):
    def test_a_span_inside_a_token_does_not_resolve(self):
        for source, proposal in (
            # Inside a path: deleting it would leave "/shop/pipes/" behind.
            ("Save it under /shop/pipes/voicing_A.md, no, /shop/pipes/voicing_B.md, then close it.",
             "voicing_A.md, no"),
            # Inside a decimal number.
            ("The run takes 1.5 hours, sorry, 2.5 hours per batch.", "5 hours, sorry"),
            # Inside a grouped number.
            ("Order 1,500 meters, no, 1,800 meters of cable.", "500 meters, no"),
            # Inside a flag value.
            ("Export with --format=stl, no, --format=obj, for the printer.", "stl, no"),
            # Ending inside a hyphenated word.
            ("Mark 3 guests, no-show, and seat the rest.", "3 guests, no"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["offsets_unresolved"]))

    def test_the_whole_token_still_resolves(self):
        for source, proposal in (
            ("The run takes 1.5 hours, sorry, 2.5 hours per batch.", "1.5 hours, sorry"),
            ("Pick it up on (the fourth, no, the fifth day) and bring the case.",
             "the fourth, no"),
            # A sentence period after the span is no joiner.
            ("We meet on the fourth, no, the fifth. Bring the case.", "the fourth, no"),
            # A dash is no joiner.
            ("The length—12 meters, no, 14 meters, fits the room.", "12 meters, no"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))


if __name__ == "__main__":
    unittest.main()
