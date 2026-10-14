"""Cleanup repairs stay source-bound without authorizing grammar completion."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


def clean_proposal(source, proposal):
    def generate(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 10, "limit_hit": False,
                "prompt": prompt}

    return CleanupEngine(generate, model_id="fixture").clean(source)


class AddedWordTests(unittest.TestCase):
    def test_function_words_are_not_free_insertions(self):
        cases = (
            ("The northern part Ridge range is snowy.",
             "The northern part of the Ridge range is snowy."),
            ("Send report.", "Send the report."),
            ("We review reports.", "We have had to review reports."),
            ("Save results.", "Save results for her."),
            ("Drop pin.", "Drop your pin."),
            ("Write RFC.", "Write an RFC."),
        )
        for source, output in cases:
            with self.subTest(output=output):
                report = validate(source, output)
                self.assertIn("novelty", [c.name for c in report.critical_failures])
                self.assertEqual(clean_proposal(source, output).text, source)

    def test_existing_article_substitution_has_no_extra_occurrence(self):
        self.assertTrue(validate("Write a RFC.", "Write an RFC.").accepted)
        self.assertFalse(validate("Write a RFC.", "Write an RFC and an RFC.").accepted)

    def test_explicit_vocabulary_can_supply_function_words(self):
        self.assertTrue(validate(
            "Inspect mini hub.", "Inspect the hub.",
            vocabulary_pairs=(("mini hub", "the hub"),)).accepted)
        self.assertFalse(validate(
            "Inspect mini hub.", "Inspect the hub for her.",
            vocabulary_pairs=(("mini hub", "the hub"),)).accepted)

    def test_obsolete_value_cannot_return_as_an_added_recipient(self):
        source = "Send it to Mark no wait to Lisa."
        span = (source.index("Mark"), source.index(" to Lisa"), source.index("no wait"))
        self.assertTrue(validate(source, "Send it to Lisa.",
                                 correction_spans=[span]).accepted)
        self.assertFalse(validate(source, "Send it to Lisa and Mark.",
                                  correction_spans=[span]).accepted)


class TechnicalPunctuationTests(unittest.TestCase):
    def test_prose_terminal_punctuation_can_follow_exact_token(self):
        for token in ("/var/data/run.log", "ana@example.org", "https://example.org/a"):
            for punctuation in (".", "?", "!"):
                with self.subTest(token=token, punctuation=punctuation):
                    self.assertTrue(validate("Use " + token,
                                             "Use " + token + punctuation).accepted)

    def test_path_period_does_not_discard_other_cleanup(self):
        source = "run cue_sync uh and log to /var/data/run.log"
        output = "Run cue_sync and log to /var/data/run.log."
        self.assertEqual(clean_proposal(source, output).text, output)

    def test_token_prefix_extensions_and_existing_terminal_bytes_stay_exact(self):
        for source, output in (
            ("Use /tmp/run.log", "Use /tmp/run.log.bak."),
            ("Use /tmp/run.log", "Use /tmp/run.log/extra."),
            ("Use /tmp/run.log", "Use /tmp/run.logger."),
            ("Use /tmp/release. now", "Use /tmp/release now"),
            ("Email ana@example.org", "Email ana@example.org.uk."),
            ("Visit https://example.org/a", "Visit https://example.org/a/b."),
        ):
            with self.subTest(output=output):
                self.assertIn("technical_tokens", [c.name for c in
                              validate(source, output).critical_failures])

    def test_each_repeated_token_needs_its_own_occurrence(self):
        source = "Use /tmp/run.log and /tmp/run.log"
        self.assertTrue(validate(source, source + ".").accepted)
        self.assertIn("technical_tokens", [c.name for c in
                      validate(source, "Use /tmp/run.log.").critical_failures])


class RestrictionAndPreservationTests(unittest.TestCase):
    def test_new_sentence_boundary_cannot_leave_a_conjunction_behind(self):
        for conjunction in ("and", "or", "but", "nor"):
            source = f"bring water {conjunction} I want towels"
            output = f"Bring water {conjunction}. I want towels."
            with self.subTest(conjunction=conjunction):
                self.assertIn("clause_scope", [c.name for c in
                              validate(source, output).critical_failures])
                self.assertEqual(clean_proposal(source, output).text,
                                 f"Bring water {conjunction} I want towels.")

    def test_conjunction_repair_keeps_other_valid_cleanup(self):
        source = "um bring water and i want towels"
        output = "Bring water and. I want towels."
        self.assertEqual(clean_proposal(source, output).text,
                         "Bring water and I want towels.")

    def test_conjunction_mentions_existing_boundaries_and_wrapping_stay_valid(self):
        for source, output in (
            ('The final word is "and" then stop', 'The final word is "and". Then stop.'),
            ("The final word is 'or' then stop", "The final word is 'or'. Then stop."),
            ("The label is and. Follow the arrow.", "The label is and. Follow the arrow."),
            ("Bring water and I want towels", "Bring water. And I want towels."),
            ("Bring water and I want towels", "Bring water and\nI want towels."),
        ):
            with self.subTest(output=output):
                self.assertTrue(validate(source, output).accepted)

    def test_protected_conjunction_mention_can_end_a_sentence(self):
        source = "The operator is and then read the expression"
        start = source.index("and")
        self.assertTrue(validate(
            source, "The operator is and. Then read the expression.",
            protected_positions=[(start, start + 3)]).accepted)

    def test_only_with_clear_new_subject_and_predicate_can_start_a_sentence(self):
        for source, output in (
            ("Do not power cycle the controller only the vendor tool may reset it",
             "Do not power cycle the controller. Only the vendor tool may reset it."),
            ("Finish the test only Mira can approve it",
             "Finish the test. Only Mira can approve it."),
            ("Save the draft only she can publish it",
             "Save the draft. Only she can publish it."),
        ):
            with self.subTest(output=output):
                self.assertTrue(validate(source, output).accepted)
                self.assertEqual(clean_proposal(source, output).text, output)

    def test_attached_only_does_not_become_a_new_instruction(self):
        for source, output in (
            ("Use the carbon copy only do not change the original",
             "Use the carbon copy. Only do not change the original."),
            ("Release the package only if the checks pass",
             "Release the package. Only if the checks pass."),
            ("Use the file only after the owner has approved it",
             "Use the file. Only after the owner has approved it."),
            ("Keep the notes only for the review",
             "Keep the notes. Only for the review."),
            ("Use the station only during testing do not open the panel",
             "Use the station. Only during testing do not open the panel."),
            ("Use copies only since the originals are missing",
             "Use copies. Only since the originals are missing."),
        ):
            with self.subTest(output=output):
                self.assertFalse(validate(source, output).accepted)

    def test_valid_punctuation_and_readable_prose_stay_verbatim(self):
        for source in (
            "Okay so the first scene is ready, but maybe the second needs work.",
            "Run the small batch first, then inspect it before opening the next one.",
            "Sorry, I need to flag this one, the sensor stopped responding.",
            "Take the sample at noon. Only Mira may open the container.",
        ):
            with self.subTest(source=source):
                self.assertEqual(clean_proposal(source, source).text, source)

    def test_required_punctuation_repairs_are_still_available(self):
        for source, output in (
            ("set the pressure to 8 then check the gauge",
             "Set the pressure to 8. Then check the gauge."),
            ("can you check the log also what failed",
             "Can you check the log? Also, what failed?"),
            ("finish calibration only then start recording",
             "Finish calibration. Only then start recording."),
        ):
            with self.subTest(output=output):
                self.assertTrue(validate(source, output).accepted)


if __name__ == "__main__":
    unittest.main()
