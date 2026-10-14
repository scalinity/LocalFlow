"""Quoted literal boundaries and occurrence counts survive cleanup."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


def literal_component(source, output):
    return next(c for c in validate(source, output).components
                if c.name == "literal_spans")


class LiteralBoundaryTests(unittest.TestCase):
    def test_outer_quotes_and_each_delimiter_are_required(self):
        for opening, closing in (("\"", "\""), ("“", "”"), ("‘", "’")):
            body = "Okay send the report by noon."
            source = opening + body + closing
            for output in (body, opening + body, body + closing):
                with self.subTest(source=source, output=output):
                    self.assertEqual(literal_component(source, output).status, "fail")

    def test_every_repeated_literal_needs_a_distinct_quoted_occurrence(self):
        for source, output in (
            ('Say "go" then "go".', 'Say "go" then go.'),
            ('Say "go" then "Go".', 'Say go then "Go".'),
            ('Say “go” then "go".', 'Say “go” then go.'),
            ('Say ‘go’ then ‘go’.', 'Say go then ‘go’.'),
        ):
            with self.subTest(output=output):
                result = literal_component(source, output)
                self.assertEqual(result.status, "fail")
                self.assertEqual(result.detail, {"literal_spans": 2, "missing": 1})

    def test_expanded_shortened_or_merged_boundaries_are_rejected(self):
        for source, output in (
            ('Set "alpha" beta.', 'Set "alpha beta".'),
            ('Set alpha "beta".', 'Set "alpha beta".'),
            ('Say "red blue".', 'Say "red" blue.'),
            ('Say "red" and "blue".', 'Say "red and blue".'),
            ('Read "stop" before stopping.', 'Read stop before "stopping".'),
        ):
            with self.subTest(output=output):
                self.assertEqual(literal_component(source, output).status, "fail")

    def test_literal_punctuation_whitespace_and_noninitial_case_stay_exact(self):
        for source, output in (
            ('Read "Okay send the report."', 'Read "Okay, send the report."'),
            ('Read "two  spaces"', 'Read "two spaces"'),
            ('Read " stop "', 'Read "stop"'),
            ('Read "blue sky"', 'Read "Blue Sky"'),
            ('Read "Stop"', 'Read "stop"'),
            ('Read "3.5"', 'Read "35"'),
        ):
            with self.subTest(output=output):
                self.assertEqual(literal_component(source, output).status, "fail")

    def test_initial_capitalization_and_double_quote_glyph_style_are_allowed(self):
        for source, output in (
            ('"send the report"', '"Send the report"'),
            ('Read “stop”', 'Read "stop".'),
            ('Read "stop"', 'Read “stop”.'),
            ('Read ‘stop’', 'Read ‘Stop’.'),
            ('Read "go" then "go"', 'Read “Go” then "go".'),
        ):
            with self.subTest(output=output):
                self.assertTrue(validate(source, output).accepted)

    def test_existing_quote_kinds_are_not_interchangeable(self):
        for source, output in (
            ('Read ‘stop’', 'Read "stop"'),
            ('Read "stop"', 'Read ‘stop’'),
        ):
            with self.subTest(output=output):
                self.assertEqual(literal_component(source, output).status, "fail")

    def test_ordinary_apostrophes_do_not_create_quoted_literals(self):
        for source in (
            "Anna's dogs' collars aren't loose and we're ready.",
            "Anna’s dogs’ collars aren’t loose and we’re ready.",
            "Rock 'n' roll and the '90s collection.",
            "The marker reads 'single quoted' here.",
        ):
            with self.subTest(source=source):
                result = literal_component(source, source)
                self.assertEqual(result.status, "pass")
                self.assertEqual(result.detail["literal_spans"], 0)

    def test_cleanup_outside_literals_preserves_existing_boundaries(self):
        for source, output in (
            ('um read "stop" then leave', 'Read "stop", then leave.'),
            ('He said “don\'t touch it” uh and left',
             'He said "don\'t touch it" and left.'),
            ('Read "two  spaces" uh then stop', 'Read "two  spaces", then stop.'),
            ('He said "write ‘quiet’ on the label" uh then left',
             'He said "write ‘quiet’ on the label", then left.'),
        ):
            with self.subTest(output=output):
                self.assertTrue(validate(source, output).accepted)

    def test_nested_quote_loss_changes_the_literal_body(self):
        source = 'He said "write ‘quiet’ on the label".'
        output = 'He said "write quiet on the label".'
        self.assertEqual(literal_component(source, output).status, "fail")

    def test_engine_rolls_back_the_unquoted_complete_sentence(self):
        source = '"Okay send the report by noon."'

        def generate(prompt, max_tokens):
            return {"text": source[1:-1], "output_tokens": 9,
                    "limit_hit": False, "prompt": prompt}

        result = CleanupEngine(generate, model_id="fixture").clean(source)
        self.assertEqual(result.text, source)
        self.assertIn("literal_spans", result.fallback_reason)


if __name__ == "__main__":
    unittest.main()
