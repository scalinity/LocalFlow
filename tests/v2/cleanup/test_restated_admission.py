"""A correction proved by a restatement of its old value is admitted."""
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


def reasons(proposal, source, protected=()):
    accepted, rejected = parse_correction_output(proposal, source, list(protected))
    return [c.delete for c in accepted], [r.reason for r in rejected]


class RestatedAdmissionTests(unittest.TestCase):
    def test_a_restated_old_value_may_exceed_the_word_cap(self):
        for source, proposal, target in (
            ("Mix 3 liters of developer at one to two dilution, no sorry, 4 liters of "
             "developer at one to two dilution, and keep it warm.",
             "3 liters of developer at one to two dilution, no sorry",
             "Mix 4 liters of developer at one to two dilution, and keep it warm."),
            # The replacement may repeat the frame word before the old value,
            # which then goes with it.
            ("The new build was slower on 12 of the 22 queries no sorry on 13 of the 22 "
             "queries and faster on the rest.",
             "on 12 of the 22 queries no sorry",
             "The new build was slower on 13 of the 22 queries and faster on the rest."),
            # A marker chained before the proposal's own belongs to the marker.
            ("Run the first session on Tuesday at 2.5 hours, actually no wait, Thursday "
             "at 2.5 hours, because the build is late.",
             "Tuesday at 2.5 hours, actually no wait",
             "Run the first session on Thursday at 2.5 hours, because the build is late."),
            # Same-length changes may share a word in place.
            ("Fit the socket with the students at the lab on Monday, I mean actually in "
             "the clinic on Monday, and bring the liners.",
             "at the lab on Monday, I mean actually",
             "Fit the socket with the students in the clinic on Monday, and bring the liners."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 1)

    def test_a_repeated_word_before_the_old_value_goes_with_it(self):
        source = ("Measure it after 10 minutes of quiet rest, no after 15 minutes of quiet "
                  "rest, then log it.")
        accepted, rejected = parse_correction_output("10 minutes of quiet rest, no", source, [])
        self.assertEqual(rejected, [])
        self.assertEqual(accepted[0].delete, "after 10 minutes of quiet rest, no")
        target = "Measure it after 15 minutes of quiet rest, then log it."
        self.assertEqual(clean(source, target, "10 minutes of quiet rest, no").text, target)

    def test_a_restated_predicate_is_parallel_through_an_ordinary_marker(self):
        source = ("Maria will own the grid export, sorry, Jonas will own the grid export, "
                  "since Maria is away.")
        proposal = "Maria will own the grid export, sorry"
        self.assertEqual(reasons(proposal, source), ([proposal], []))
        self.assertTrue(_has_correction_marker(source))
        target = "Jonas will own the grid export, since Maria is away."
        self.assertEqual(clean(source, target, proposal).text, target)

    def test_a_restated_detail_needs_no_move(self):
        for source, proposal in (
            ("Thread the warp at 40 ends per inch, no sorry, thirty-six ends per inch, "
             "and keep the tension even.", "40 ends per inch, no sorry"),
            ("The adjustment is 2 quarters of a turn, sorry, 1 half of a turn.",
             "2 quarters of a turn, sorry"),
        ):
            with self.subTest(proposal=proposal):
                accepted, rejected = parse_correction_output(proposal, source, [])
                self.assertEqual(rejected, [])
                self.assertIsNone(accepted[0].move)

    def test_open_or_unrestated_replacements_keep_the_cap(self):
        for source, proposal, reason in (
            # An open replacement restates nothing.
            ("Order 12 meters of the blue climbing rope, no, send the rest to Marta.",
             "12 meters of the blue climbing rope, no", "span_too_long"),
            # Only function words repeat.
            ("Give the report for the board on Friday, sorry, the board wants it sooner.",
             "the report for the board on Friday, sorry", "span_too_long"),
            # An unchanged repeat corrects nothing.
            ("Send the draft to the review board, sorry, send the draft to the review "
             "board.", "Send the draft to the review board, sorry", "span_too_long"),
            # More than three changed words.
            ("Use the narrow phonetic transcription for the first drill, no wait, use the "
             "broad phonemic transcription style for the first drill.",
             "Use the narrow phonetic transcription for the first drill, no wait",
             "span_too_long"),
            # A quoted repeat may be a literal.
            ('The sign says "turn left at the north gate, no wait, turn right at the '
             'north gate" in both languages.',
             "turn left at the north gate, no wait", "span_too_long"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], [reason]))

    def test_a_restated_short_value_still_needs_its_marker_evidence(self):
        # Under the cap a single-word marker still needs parallel words: the
        # restatement must repeat a content word, not only articles.
        source = "Give it to the nurse, sorry, the pharmacist."
        self.assertEqual(reasons("the nurse, sorry", source), ([], ["not_parallel"]))

    def test_a_changed_relation_keeps_the_opposing_qualifier_rule(self):
        source = "Stir in 2 cups of sugar, sorry, 2 cups without sugar, then bake."
        self.assertEqual(reasons("2 cups of sugar, sorry", source),
                         ([], ["opposing_quantity_qualifier"]))


if __name__ == "__main__":
    unittest.main()
