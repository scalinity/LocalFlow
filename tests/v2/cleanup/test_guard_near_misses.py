"""Near misses that only one admission guard rejects (or only one path admits).

Each case pins a single guard: removing that guard changes the result.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import _has_correction_marker, parse_correction_output

BODY = ("crates of bottled water at the eastern gate tonight after the long ride home from the "
        "high ridge above the old quarry road again")


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class GuardNearMissTests(unittest.TestCase):
    def test_restatement_guards(self):
        for source, proposal in (
            # A quoted repeat may be a literal.
            ('The sign says "turn left at the north gate, no wait, turn right at the north '
             'gate today" in both languages.', "turn left at the north gate, no wait"),
            # Only function words repeat.
            ("Put it in the box on the, no wait, in the bag on the shelf.",
             "in the box on the, no wait"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["span_too_long"]))

    def test_sentence_crossing_guards(self):
        for source, proposal in (
            # A typed value that opens a predicate.
            ("We counted 4 bugs. Sorry, 6 bugs were.", "4 bugs. Sorry"),
            # A sentence-final old value of more than three words.
            ("The first act starts at the main stage at 7:40. I mean 8:40, so please update "
             "the sheet.", "main stage at 7:40. I mean"),
            # Two sentence ends inside the span, though the next sentence
            # restates the last one.
            ("Wait. Ok. It starts at seven. Sorry, ok it starts at 7:30.",
             "Ok. It starts at seven. Sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["crosses_sentence"]))
        # Weekdays are typed values too.
        self.assertEqual(reasons("Tuesday. I mean",
                                 "The review moves to Tuesday. I mean Wednesday, after lunch."),
                         (["Tuesday. I mean"], []))

    def test_repeated_frame_guards(self):
        for source, proposal in (
            # An article on one side only.
            ("Leave it on the shelf, no, on Monday.", "on the shelf, no"),
            # An auxiliary in the old complement.
            ("Leave it to whoever is free, sorry, to Marta.", "to whoever is free, sorry"),
            # A negation in the old complement, then in the new one.
            ("Write to no one, sorry, to Marta.", "to no one, sorry"),
            ("Send it to Marta, sorry, to no one.", "to Marta, sorry"),
            ("Leave it with someone who isn’t busy, no, with Marta.",
             "with someone who isn’t busy, no"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["not_parallel"]))

    def test_code_token_needs_function_words_before_it(self):
        self.assertEqual(reasons("new peaks_final.csv, no",
                                 "Use the new peaks_final.csv, no, peaks_merged.csv, today."),
                         ([], ["not_parallel"]))

    def test_a_word_before_the_span_is_taken_in_only_when_restated_before_a_new_value(self):
        for source, proposal in (
            # The replacement repeats the old value's own "the", not the
            # word before the span.
            ("Measure the the 10 minutes of rest, no the 15 more minutes of rest.",
             "the 10 minutes of rest, no"),
            # The repeated "on" replaces the value instead of leading a new one.
            ("It was slower on 12 of the queries, no on of the queries.", "12 of the queries, no"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))

    def test_length_guards(self):
        # A bound quantity keeps the 80-character limit.
        self.assertEqual(reasons(
            "2 boxes of the extraordinarily expensive hypoallergenic adhesive electrodes, sorry",
            "Bring 2 boxes of the extraordinarily expensive hypoallergenic adhesive electrodes, "
            "sorry, 3 boxes for the sensors."), ([], ["span_too_long"]))
        # A restated line over 160 characters is not read.
        line = f"The north crew should stage 6 {BODY}. Sorry"
        source = f"Plan the route. {line}, the north crew should stage 8 {BODY}."
        self.assertGreater(len(line), 160)
        self.assertEqual(reasons(line, source), ([], ["span_too_long"]))
        # Nor does the trigger reach that far back.
        self.assertFalse(_has_correction_marker(source))
        # A long line that does not resolve, or resolves twice, is rejected
        # for its length.
        self.assertEqual(reasons("go over the long night shift report, no",
                                 "Please go over the shift report, no, the night report."),
                         ([], ["span_too_long"]))
        twice = "the long blue extension cord in the hall, sorry"
        self.assertEqual(reasons(twice, f"Bring {twice}, the hall cord, or {twice}, the van cord."),
                         ([], ["span_too_long"]))

    def test_the_trigger_needs_a_proved_span(self):
        # "barn" repeats, but only in a ten-word candidate nothing proves.
        self.assertFalse(_has_correction_marker(
            "It was the barn we saw by the old mill near the river, no, the barn."))

    def test_token_joiners(self):
        for source, proposal in (
            ("Open C:\\data\\run_4, no, C:\\data\\run_5 first.", "run_4, no"),
            ("Mail ops@hq-4, no, ops@hq-5 today.", "hq-4, no"),
            ("Close #4, no, #5 first.", "4, no"),
            ("Open name%2Done, no, name%2Dtwo now.", "2Done, no"),
            ("Ask R&D, no, Q&A first.", "D, no"),
            ("Open ~/notes, no, ~/drafts now.", "/notes, no"),
            # A period joins the marker to what follows.
            ("Pick option 4, no.5 is better.", "4, no"),
        ):
            with self.subTest(source=source):
                self.assertEqual(reasons(proposal, source), ([], ["offsets_unresolved"]))

    def test_titles_and_times_end_no_sentence(self):
        for title in ("Mr.", "Mrs.", "Ms.", "Prof."):
            with self.subTest(title=title):
                proposal = f"{title} Okafor, I mean"
                self.assertEqual(reasons(proposal, f"Send it to {proposal} {title} Bell, before noon."),
                                 ([proposal], []))
        self.assertEqual(reasons("6 p.m. 2 hours, sorry",
                                 "Set it to 6 p.m. 2 hours, sorry, 3 hours after that."),
                         (["6 p.m. 2 hours, sorry"], []))

    def test_a_two_word_value_opens_a_predicate(self):
        self.assertEqual(reasons("Monday, no", "We meet Monday, no, Tuesday morning is fine."),
                         ([], ["not_parallel"]))
        self.assertEqual(reasons("Monday, no", "We meet Monday, no, Tuesday morning at 9."),
                         (["Monday, no"], []))

    def test_a_title_hides_no_predicate(self):
        self.assertEqual(reasons("Dr. Okafor, sorry",
                                 "Send it to Dr. Okafor, sorry, Dr. Bellweather is on call."),
                         ([], ["not_parallel"]))
        self.assertEqual(reasons("Dr. Okafor, sorry",
                                 "Send it to Dr. Okafor, sorry, Dr. Ann Bellweather is on call."),
                         ([], ["not_parallel"]))
        self.assertEqual(reasons("Dr. Okafor, sorry",
                                 "Send it to Dr. Okafor, sorry, Dr. Bellweather, before noon."),
                         (["Dr. Okafor, sorry"], []))

    def test_apology_and_contrast_limits(self):
        # A weekday after "sorry to" is the replacement, not an apology.
        self.assertEqual(reasons("Friday, sorry", "Move the review to Friday, sorry to Monday."),
                         (["to Friday, sorry"], []))
        # A "yes" in an earlier sentence contrasts with nothing here.
        self.assertEqual(reasons("to the shelf, no",
                                 "Say yes to it. Then move it to the shelf, no to the desk."),
                         (["to the shelf, no"], []))

    def test_an_additive_word_after_a_clause_link_belongs_to_that_clause(self):
        self.assertEqual(reasons("the 4 large steel trays, sorry",
                                 "Use the 4 large steel trays, sorry, 6 trays and lids too."),
                         (["the 4 large steel trays, sorry"], []))


if __name__ == "__main__":
    unittest.main()
