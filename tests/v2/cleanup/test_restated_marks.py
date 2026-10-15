"""A hedge or negation in a correction's old value that the replacement restates.

"sessions take about 45 minutes, no sorry about 50 minutes" deletes "about
45 minutes, no sorry"; the output keeps one "about", the replacement's. The
deleted copy is not a lost hedge. The replacement restates a word only in
the same place: the same word at the same position after the deletion. A
correction that removes a hedge or negation without restating it, a hedge
or negation elsewhere in the sentence, and an output that drops the
restated one still fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_restated_marks.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import validate  # noqa: E402


def span(source, delete, marker):
    start = source.index(delete)
    return start, start + len(delete), start + delete.rindex(marker)


def failures(source, output, corrections):
    return {c.name for c in validate(source, output, correction_spans=corrections).critical_failures}


def clean(source, lines, output):
    def generate(prompt, max_tokens):
        text = "\n".join(lines) if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class RestatedMarkTests(unittest.TestCase):
    def test_a_restated_hedge_or_negation_survives_once(self):
        for source, delete, marker, output in (
            ("Mention that sessions take about 45 minutes, no sorry about 50 minutes, "
             "because we added a clip.", "about 45 minutes, no sorry", "no sorry",
             "Mention that sessions take about 50 minutes, because we added a clip."),
            ("The finding reads no acute pneumothorax, sorry, no acute pleural effusion, "
             "and the interval stays.", "no acute pneumothorax, sorry", "sorry",
             "The finding reads no acute pleural effusion, and the interval stays."),
            ("The slide should say it is not approved for children, I mean, not approved "
             "for infants.", "not approved for children, I mean", "I mean",
             "The slide should say it is not approved for infants."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output, [span(source, delete, marker)]), set())
                result = clean(source, [delete], output)
                self.assertEqual((result.path, result.text), ("llm", output))

    def test_a_correction_that_drops_a_hedge_or_negation_still_fails(self):
        for source, delete, marker, output, name in (
            ("Hold each kick for about 60 seconds, sorry, for 60 seconds.",
             "for about 60 seconds, sorry", "sorry",
             "Hold each kick for 60 seconds.", "uncertainty_coverage"),
            ("Please do not send the report, sorry, send the report today.",
             "do not send the report, sorry", "sorry",
             "Please send the report today.", "negation_coverage"),
        ):
            with self.subTest(source=source):
                self.assertIn(name, failures(source, output, [span(source, delete, marker)]))

    def test_a_mark_elsewhere_in_the_sentence_restates_nothing(self):
        for source, triple, output, name in (
            ("Please do not send the report, sorry, send the report today, but do not cc Sam.",
             (7, 36, 31), "Please send the report today, but do not cc Sam.", "negation_coverage"),
            ("We spent about 2 hours, sorry, 3 hours, talking about the launch.",
             (9, 29, 24), "We spent 3 hours, talking about the launch.", "uncertainty_coverage"),
        ):
            with self.subTest(source=source):
                self.assertIn(name, failures(source, output, [triple]))
                result = clean(source, [source[triple[0]:triple[1]]], output)
                self.assertNotEqual(result.path, "llm")

    def test_the_restated_hedge_itself_is_still_required(self):
        source = "Sessions take about 45 minutes, no sorry about 50 minutes, on average."
        output = "Sessions take 50 minutes, on average."
        self.assertIn("uncertainty_coverage", failures(
            source, output, [span(source, "about 45 minutes, no sorry", "no sorry")]))


if __name__ == "__main__":
    unittest.main()
