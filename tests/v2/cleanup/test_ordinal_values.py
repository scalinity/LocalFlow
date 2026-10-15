"""A spelled ordinal is a value a correction may replace."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class OrdinalValueTests(unittest.TestCase):
    def test_an_ordinal_is_replaced_by_an_ordinal_or_a_full_date(self):
        for source, proposal, target in (
            ("Pick it up on the fourth, no, the fifth, and bring the case.",
             "the fourth, no", "Pick it up on the fifth, and bring the case."),
            ("Book the dome for the twenty-first, sorry, the twenty-second, at dusk.",
             "the twenty-first, sorry", "Book the dome for the twenty-second, at dusk."),
            ("Book the coronagraph for the fourteenth, no, March 16, and set the exposure.",
             "the fourteenth, no",
             "Book the coronagraph for March 16, and set the exposure."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_an_ordinal_beside_other_words_is_not_a_value_pair(self):
        for source, proposal in (
            # A month name without its day may be the modal "may".
            ("Meet me on the fourth, no, may I ask why?", "the fourth, no"),
            ("Do the first, no, I will do it.", "the first, no"),
            ("Take the second, sorry, the blue one.", "the second, sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["not_parallel"]))

    def test_a_yes_no_contrast_is_not_a_correction(self):
        for source, proposal in (("Say yes to the first, no to the second.", "to the first, no"),
                                 ("Say yes to 3, no to 4.", "3, no")):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source)[0], [])
        # An answer before a real correction is no contrast.
        self.assertEqual(reasons("4 chairs, no", "Yes, we need 4 chairs, no, 6 chairs."),
                         (["4 chairs, no"], []))


if __name__ == "__main__":
    unittest.main()
