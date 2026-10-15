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
        ):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source), ([], ["additive_replacement"]))
                self.assertFalse(_has_correction_marker(source))

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
