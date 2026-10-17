"""A replacement that adds to the old value keeps it: no correction."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import _has_correction_marker, parse_correction_output


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class AdditiveReplacementTests(unittest.TestCase):
    def test_too_also_and_as_well_add_rather_than_replace(self):
        for source, proposal in (
            ("The tests passed on Linux. Sorry, the tests passed on macOS too.",
             "The tests passed on Linux. Sorry"),
            ("The tests passed on Linux. No, the tests passed on macOS as well.",
             "The tests passed on Linux. No"),
            ("Marta will review the grid export, sorry, Jonas will review the grid export too.",
             "Marta will review the grid export, sorry"),
            ("The tests passed on Linux, sorry, on macOS too.", "on Linux, sorry"),
            ("Use 4 trays, sorry, also 6 trays for the oven.", "4 trays, sorry"),
            ("Marta will review the draft, sorry, Jonas will also review the draft.",
             "Marta will review the draft, sorry"),
            ("The first build failed. Sorry, the second build failed too.",
             "The first build failed. Sorry"),
        ):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source), ([], ["additive_replacement"]))
                self.assertFalse(_has_correction_marker(source))

    def test_either_adds_as_too_does(self):
        for source, proposal in (
            ("The kitchen is not ready. Actually, the bathroom is not ready either.",
             "The kitchen is not ready. Actually"),
            ("Marta won't review the draft, sorry, Jonas won't review the draft either.",
             "Marta won't review the draft, sorry"),
            ("The kitchen is ready. Actually, the bathroom is ready too.",
             "The kitchen is ready. Actually"),
        ):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source), ([], ["additive_replacement"]))
        # "either" opening a later clause is about that clause.
        source = "We can't use the north gate, sorry, the south gate, either way it is closed."
        self.assertEqual(reasons("the north gate, sorry", source), (["the north gate, sorry"], []))

    def test_an_intensifying_too_and_a_later_clause_still_correct(self):
        for source, proposal in (
            ("The soup is too cold, sorry, too hot.", "too cold, sorry"),
            # "too", "also" or "as well" in another clause is about that one.
            ("Use 4 trays, sorry, 6 trays, and bring the lids too.", "4 trays, sorry"),
            ("It took 40 minutes, sorry, 55 minutes while the export was also running.",
             "40 minutes, sorry"),
            ("Ask Dr. Varga, I mean Dr. Varadi to sign the transfer sheet as well.",
             "Dr. Varga, I mean"),
            ("The tests passed on Linux. Sorry, the tests passed on macOS.",
             "The tests passed on Linux. Sorry"),
        ):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source), ([proposal], []))


if __name__ == "__main__":
    unittest.main()
