"""A title or time abbreviation does not end the correction's sentence."""
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


class AbbreviationPeriodTests(unittest.TestCase):
    def test_title_and_time_periods_stay_inside_the_sentence(self):
        for source, proposal, deleted, target in (
            ("Send the target list to Dr. Okafor, I mean Dr. Bellweather, before noon.",
             "Dr. Okafor, I mean", "Dr. Okafor, I mean",
             "Send the target list to Dr. Bellweather, before noon."),
            # The restated article goes with the old value.
            ("Put Ines on the 8 a.m. slot, sorry, the 9 a.m. slot, and log the run.",
             "8 a.m. slot, sorry", "the 8 a.m. slot, sorry",
             "Put Ines on the 9 a.m. slot, and log the run."),
            ("The second show starts at 7 p.m. actually 8 p.m., and the doors open early.",
             "7 p.m. actually", "7 p.m. actually",
             "The second show starts at 8 p.m., and the doors open early."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([deleted], []))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_a_real_sentence_end_still_bounds_the_correction(self):
        for source, proposal in (
            # A capitalized word after the time opens a new sentence.
            ("The show starts at 7 p.m. Sorry, the doors open at 6 p.m.", "7 p.m. Sorry"),
            # The title's period is not the only one in the span.
            ("I called Dr. Okafor. Sorry, Dr. Lindqvist called me.", "Dr. Okafor. Sorry"),
            # A lowercase unit abbreviation is not a title.
            ("The latency is 5 ms. sorry, 6 ms on the second run.", "5 ms. sorry"),
            # A title's period opens no sentence either, so this old value
            # is the tail of one and its restatement repeats no end.
            ("Please email Dr. Okafor rescheduled the review to Friday. Sorry, Okafor "
             "rescheduled the review to Thursday.", "Okafor rescheduled the review to Friday. Sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["crosses_sentence"]))


if __name__ == "__main__":
    unittest.main()
