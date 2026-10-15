"""A negation word hyphenated into a name negates no clause.

"use the flag dash dash no-cache, actually dash dash fresh-index"
corrects the flag; its "no" is part of the name "no-cache", not a
negation the correction removes. negation_coverage exempts that deleted
source occurrence, while surviving atoms count on both sides regardless
of hyphenation. Coverage and novelty still keep or forbid the word itself.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_hyphenated_negations.py
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


def failures(source, output, corrections=()):
    return {c.name for c in validate(source, output, correction_spans=list(corrections)).critical_failures}


class HyphenatedNegationTests(unittest.TestCase):
    def test_hyphenation_preserves_surviving_negation_atoms(self):
        for source, output in (
            ("This is a not for profit organization.", "This is a not-for-profit organization."),
            ("Use a no-cost account.", "Use a no cost account."),
        ):
            for original, candidate in ((source, output), (output, source)):
                with self.subTest(source=original, output=candidate):
                    self.assertEqual(failures(original, candidate), set())
                    result = CleanupEngine(
                        lambda prompt, max_tokens: {"text": candidate, "output_tokens": 20,
                                                   "limit_hit": False},
                        model_id="fixture").clean(original)
                    self.assertEqual((result.path, result.text), ("llm", candidate))

    def test_a_corrected_name_with_no_in_it_drops_no_negation(self):
        source = "For the dry run use the flag dash dash no-cache, actually dash dash fresh-index, so we start clean."
        output = "For the dry run, use the flag dash dash fresh-index, so we start clean."
        self.assertEqual(failures(source, output, [span(source, "dash dash no-cache, actually", "actually")]), set())

    def test_negations_and_the_word_itself_still_count(self):
        for source, output, name in (
            ("Do not use the no-cache flag today.", "Do use the no-cache flag today.", "negation_coverage"),
            ("Use the no-cache flag today.", "Use the cache flag today.", "coverage"),
            ("Use the cache flag today.", "Use the no-cache flag today.", "novelty"),
        ):
            with self.subTest(source=source):
                self.assertIn(name, failures(source, output))


if __name__ == "__main__":
    unittest.main()
