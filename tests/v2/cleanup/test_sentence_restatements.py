"""A correction may replace the sentence, or the sentence-final value, that
the next sentence restates."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, _has_correction_marker, parse_correction_output


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class SentenceRestatementTests(unittest.TestCase):
    def test_a_restated_sentence_replaces_the_old_one(self):
        for source, proposal, target in (
            ("Route it to her desk. The rehearsal starts at seven. Sorry, the rehearsal "
             "starts at 7:30, and the room is booked.",
             "The rehearsal starts at seven. Sorry",
             "Route it to her desk. The rehearsal starts at 7:30, and the room is booked."),
            # Past the word cap the restatement still proves the extent.
            ("We should schedule the pointing check on Tuesday. Sorry, we should schedule "
             "the pointing check on Wednesday.",
             "We should schedule the pointing check on Tuesday. Sorry",
             "We should schedule the pointing check on Wednesday."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                self.assertTrue(_has_correction_marker(source))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_a_value_that_ends_its_sentence_takes_the_next_ones_value(self):
        for source, proposal, target in (
            ("The first act starts at 7:40. I mean 8:40, so please update the sheet.",
             "7:40. I mean", "The first act starts at 8:40, so please update the sheet."),
            ("Spin at 2,000 g for 15 minutes. Actually, 10 minutes, the amendment cut it.",
             "15 minutes. Actually",
             "Spin at 2,000 g for 10 minutes, the amendment cut it."),
            # A restatement that repeats the old value's end joins its sentence.
            ("The report lists 14 duplicate rows in batch C. Sorry, 41 duplicate rows in "
             "batch C, which we flagged.", "14 duplicate rows in batch C. Sorry",
             "The report lists 41 duplicate rows in batch C, which we flagged."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                self.assertEqual(clean(source, target, proposal).text, target)

    def test_other_sentence_pairs_stay_separate(self):
        for source, proposal in (
            # The next sentence starts like the old one but restates nothing.
            ("The meeting is at noon. Sorry, the meeting room is booked.",
             "The meeting is at noon. Sorry"),
            # A parallel value that opens a new predicate.
            ("We counted 4 bugs. Sorry, 6 bugs were reported later.", "4 bugs. Sorry"),
            # A noun the next sentence names again is no typed value.
            ("Finish before the door test. I mean the cable test can wait.",
             "before the door test. I mean"),
            ("Weights go on with the supervisor present. No supervisor, no reset.",
             "with the supervisor present. No"),
            # Merged into the old sentence, a restated noun phrase that starts
            # a new statement replaces nothing.
            ("Put the receipts in the blue folder on the counter. Actually, the blue folder "
             "is only for returns, so use the tray.", "the blue folder on the counter. Actually"),
            ("Check what was in the earlier notes. I mean, the earlier notes were fine, but "
             "the folder name changed.", "in the earlier notes. I mean"),

            # A question is answered, not corrected.
            ("Is it 4 chairs? No, 6 chairs.", "4 chairs? No"),
            # Two sentence ends inside the span.
            ("Noted. It starts at seven. Sorry, it starts at 7:30.",
             "Noted. It starts at seven. Sorry"),
            # A quoted sentence pair may be a literal.
            ('He logged "The review closes on Friday. Sorry, the review closes on '
             'Thursday." without comment.', "The review closes on Friday. Sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["crosses_sentence"]))
        # An apology opens the next sentence: "sorry" is no marker there.
        source = "Run it end to end, including the reload. Sorry to say, the reload drops a second."
        self.assertEqual(reasons("including the reload. Sorry", source), ([], ["not_parallel"]))
        self.assertFalse(_has_correction_marker(source))


if __name__ == "__main__":
    unittest.main()
