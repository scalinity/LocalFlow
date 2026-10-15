"""Literal pipes retain their count and their surrounding source content."""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


def clean(source, output, protected=()):
    def generate(prompt, max_tokens):
        return {"text": "NONE" if "Find the self-corrections" in prompt else output,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(
        source, protected_spans=list(protected))


CASES = (
    ("delete_one", "Write red | blue on the label.", "Write red blue on the label.", False),
    ("delete_one_of_two", "Keep red | blue and green | yellow.",
     "Keep red blue and green | yellow.", False),
    ("delete_both", "Keep red | blue and green | yellow.",
     "Keep red blue and green yellow.", False),
    ("invent_pipe", "Write red blue on the label.", "Write red | blue on the label.", False),
    ("duplicate_pipe", "Write red | blue on the label.",
     "Write red | blue | on the label.", False),
    ("move_left_across_word", "Write red | blue on the label.",
     "Write | red blue on the label.", False),
    ("move_right_across_word", "Write red | blue on the label.",
     "Write red blue | on the label.", False),
    ("move_with_equal_words", "Keep red | red red.", "Keep red red | red.", False),
    ("move_across_digits", "Compare 2 | 5 options.", "Compare | 2 5 options.", False),
    ("move_punctuation_adjacent_pipe", "The marker is |.", "The marker is. |", False),
    ("merge_single_pipes", "Keep red | | blue.", "Keep red || blue.", False),
    ("pipe_to_comma", "Write red | blue on the label.", "Write red, blue on the label.", False),
    ("word_pipe_to_symbol_is_not_cleanup", "Keep the word pipe beside the label.",
     "Keep the word | beside the label.", False),
    ("symbol_to_word_is_not_cleanup", "Keep the sign | beside the label.",
     "Keep the sign pipe beside the label.", False),
    ("quoted_literal_already_protected", 'Read "red | blue" aloud.',
     'Read "red blue" aloud.', False),
    ("identity", "Write red | blue on the label.", "Write red | blue on the label.", True),
    ("case_and_final_period", "write red | blue on the label",
     "Write red | blue on the label.", True),
    ("horizontal_spacing", "Write red  |\t blue on the label.",
     "Write red|blue on the label.", True),
    ("comma_elsewhere", "choose red | blue and wait", "Choose red | blue, and wait.", True),
    ("pure_filler_elsewhere", "um choose red | blue for the label",
     "Choose red | blue for the label.", True),
    ("numeric_identity", "Compare 2 | 5 options.", "Compare 2 | 5 options.", True),
    ("article_polish", "Read red | an user should copy it.",
     "Read red | a user should copy it.", True),
    ("legitimate_bullet_list", "Here is a list of things: red | blue, and green | yellow.",
     "Here is a list of things:\n\n- Red | blue\n- Green | yellow", True),
    ("legitimate_spoken_steps", "Do these steps: first copy red | blue, second save green | yellow.",
     "Do these steps:\n\n1. Copy red | blue.\n2. Save green | yellow.", True),
    ("no_pipe_punctuation", "bring water and write notes", "Bring water and write notes.", True),
    ("leading_pipe_identity", "| Red is the first entry.", "| Red is the first entry.", True),
    ("trailing_pipe_identity", "The final sign is |", "The final sign is |", True),
    ("punctuation_adjacent_pipe_identity", "The marker is |.", "The marker is |.", True),
)


class PipePreservationTests(unittest.TestCase):
    def assert_pipe_rejected(self, source, output, **kwargs):
        report = validate(source, output, **kwargs)
        self.assertFalse(report.accepted)
        self.assertIn("technical_tokens", [c.name for c in report.critical_failures])

    def test_original_count_gap_and_allowed_edit_controls(self):
        for name, source, output, accepted in CASES:
            with self.subTest(name=name):
                report = validate(source, output)
                self.assertEqual(report.accepted, accepted)
                if not accepted:
                    self.assertIn("technical_tokens", [c.name for c in report.critical_failures])
                self.assertEqual(clean(source, output).text, output if accepted else source)

    def test_original_protected_pipe_controls_do_not_reduce_to_minimum_counts(self):
        for name, source, output, _ in CASES[:7]:
            with self.subTest(name=name):
                self.assert_pipe_rejected(source, output, protected=["|"] * source.count("|"))
                positions = [(m.start(), m.end(), "literal") for m in re.finditer(r"\|", source)]
                self.assertEqual(clean(source, output, positions).text, source)

    def test_zero_word_inputs_preserve_pipe_order_and_runs(self):
        for source, output in (("|", "|"), ("|", " |\t"), ("||", "||"),
                               ("| |", "|\t|"), ("|\n|", "|\n|"), ("2 | 5", "2 | 5")):
            with self.subTest(source=source, output=output):
                self.assertTrue(validate(source, output).accepted)
        for source, output in (("|", ""), ("", "|"), ("| |", "||"),
                               ("||", "| |"), ("|||", "|| |"),
                               ("|\n|", "| |"), ("2 | 5", "| 2 5")):
            with self.subTest(source=source, output=output):
                self.assert_pipe_rejected(source, output)

    def test_isolated_runs_stay_in_their_original_gap(self):
        for source, output in (("Keep red || blue.", "Keep || red blue."),
                               ("Keep red || blue.", "Keep red | | blue."),
                               ("Keep red | | blue.", "Keep red || blue."),
                               ("Keep red | blue || green.", "Keep red || blue | green.")):
            with self.subTest(output=output):
                self.assert_pipe_rejected(source, output)
                self.assertEqual(clean(source, output).text, source)
        self.assertTrue(validate("Keep red || blue.", "Keep red||blue.").accepted)

    def test_leading_trailing_and_repeated_word_occurrences_do_not_move(self):
        for source, output in (("| Red is first.", "Red | is first."),
                               ("The last sign is |", "The last sign | is"),
                               ("red | red | red", "red red | | red"),
                               ("| red red |", "red | red |"),
                               ("Read λ | λ again.", "Read λ λ | again.")):
            with self.subTest(output=output):
                self.assert_pipe_rejected(source, output)

    def test_same_count_does_not_exchange_attached_and_isolated_occurrences(self):
        self.assert_pipe_rejected("Keep red | blue and green|yellow.",
                                  "Keep red blue and green|yellow |.")

    def test_quote_and_protected_literal_guards_still_apply(self):
        for source, output in (('Read "red | blue" aloud.', 'Read "red|blue" aloud.'),
                               ("Read ‘red | blue’ aloud.", "Read ‘red|blue’ aloud."),
                               ('Read “red|blue” aloud.', 'Read “red blue|” aloud.')):
            with self.subTest(output=output):
                self.assertEqual([c.name for c in validate(source, output).critical_failures],
                                 ["literal_spans"])
                self.assertEqual(clean(source, output).text, source)
        source, output = "Read red | blue aloud.", "Read red|blue aloud."
        span = (source.index("red"), source.index(" blue") + len(" blue"), "literal")
        self.assertEqual(clean(source, output, [span]).text, source)

    def test_unresolved_local_changes_abstain(self):
        for source, output in (("Compare 1,000 | 2,000 samples.", "Compare 1000 | 2000 samples."),
                               ("Choose red um | blue for the label.", "Choose red | blue for the label."),
                               ("Choose red | blue for the label.", "Choose red |\nblue for the label.")):
            with self.subTest(output=output):
                self.assert_pipe_rejected(source, output)
                self.assertEqual(clean(source, output).text, source)

    def test_alias_or_correction_changes_do_not_move_a_pipe_gap(self):
        self.assertTrue(validate("Choose mini hub.", "Choose sensor.",
                                 vocabulary_pairs=(("mini hub", "sensor"),)).accepted)
        self.assert_pipe_rejected("Choose mini hub | blue.", "Choose sensor | blue.",
                                  vocabulary_pairs=(("mini hub", "sensor"),))
        source = "Choose red no wait green | blue."
        span = (source.index("red"), source.index(" green"), source.index("no wait"))
        self.assertTrue(validate(source, "Choose green | blue.", correction_spans=[span]).accepted)
        self.assert_pipe_rejected("Choose red | no wait green.", "Choose green.",
                                  correction_spans=[(7, 20, 13)])

    def test_existing_word_attached_pipe_relocation_is_outside_this_slice(self):
        self.assertTrue(validate("Keep red|blue and yellow.", "Keep red blue|and yellow.").accepted)
        self.assert_pipe_rejected("Keep red|blue.", "Keep red blue.")


if __name__ == "__main__":
    unittest.main()
