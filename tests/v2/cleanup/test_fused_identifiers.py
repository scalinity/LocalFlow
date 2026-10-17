"""A number dictated right after a word may be written fused to it.

"the datum is WGS eighty four" becomes "the datum is WGS84" and "use PROJ
four" becomes "use PROJ.4": the identifier is the dictated word and the
dictated number, so numeric_values binds the number to it instead of
reading an invented identifier. A changed number, different letters, a
number that was not dictated right after that word, a function word
("a 1 liter") and an identifier the source already holds still fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_fused_identifiers.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output, **kwargs):
    return {c.name for c in validate(source, output, **kwargs).critical_failures}


class FusedIdentifierTests(unittest.TestCase):
    def test_decimal_fusions_keep_each_technical_number_spelling(self):
        for source, output in (
            ("Use PROJ 4.1.", "Use PROJ4.1."),
            ("Use ISO 2.5.", "Use ISO2.5."),
            ("Use PROJ 4.1 and PROJ 4.1.", "Use PROJ4.1 and PROJ4.1."),
            ("Use PROJ 4.1.", "Use PROJ.4.1."),
            ("Use PROJ 4.1.", "Use PROJ-4.1."),
            ("Use PROJ one point zero and 1.0.", "Use PROJ1.0 and 1.0."),
        ):
            with self.subTest(source=source, output=output):
                self.assertEqual(failures(source, output), set())
                result = CleanupEngine(
                    lambda prompt, max_tokens: {"text": output, "output_tokens": 20,
                                               "limit_hit": False},
                    model_id="fixture").clean(source)
                self.assertEqual((result.path, result.text), ("llm", output))
        for source, output, component in (
            ("Use PROJ 4.10.", "Use PROJ4.1.", "numeric_values"),
            ("Copy from PROJ to PROJ 4.1.", "Copy from PROJ4.1 to PROJ.", "numeric_values"),
            ("Use PROJ 4.1 and 4.1.", "Use PROJ4.1 and.", "technical_tokens"),
            ("Use PROJ 4.1 and 4.1.", "Use PROJ-4.1 and.", "technical_tokens"),
            ("Use PROJ 4.1 and 4.1.", "Use PROJ.4.1 and.", "technical_tokens"),
            ("Use PROJ one point zero and 1.0.", "Use PROJ1.0 and 1.", "technical_tokens"),
        ):
            with self.subTest(source=source, output=output):
                self.assertIn(component, failures(source, output))

    def test_vocabulary_fusions_bind_to_their_original_occurrences(self):
        for source, output, vocabulary in (
            ("Use WGS eighty four.", "Use WGS84.", (("WGS eighty four", "WGS84"),)),
            ("Check cox one and cox 1.", "Check COX1 and COX1.", (("cox one", "COX1"),)),
            ("Use kern pair v 2.1.", "Use kerning v2.1.", (("kern pair v 2.1", "kerning v2.1"),)),
            ("Use proj four.", "Use PROJ.4.", (("proj four", "PROJ.4"),)),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output, vocabulary_pairs=vocabulary), set())
                result = CleanupEngine(
                    lambda prompt, max_tokens: {"text": output, "output_tokens": 20,
                                               "limit_hit": False},
                    model_id="fixture").clean(source, vocabulary_pairs=vocabulary)
                self.assertEqual((result.path, result.text), ("llm", output))
        source = "Copy from channel to channel 3."
        vocabulary = (("channel 3", "channel3"),)
        self.assertIn("numeric_values", failures(
            source, "Copy from channel3 to channel.", vocabulary_pairs=vocabulary))
        self.assertEqual(failures(
            source, "Copy from channel to channel3.", vocabulary_pairs=vocabulary), set())

    def test_case_exact_fusions_keep_their_source_case_word(self):
        for source, output in (
            ("Use WGS eighty four.", "Use WGS84."),
            ("Use WGS 84.", "Use WGS84."),
            ("Use ISO nine thousand.", "Use ISO9000."),
            ("Copy PROJ four.", "Copy PROJ4."),
            ("Copy PROJ four.", "Copy PROJ.4."),
            ("Copy PROJ four.", "Copy PROJ-4."),
            ("Use iOS 4.", "Use iOS4."),
            ("Compare WGS with WGS 84.", "Compare WGS with WGS84."),
        ):
            with self.subTest(source=source, output=output):
                self.assertEqual(failures(source, output), set())
                result = CleanupEngine(
                    lambda prompt, max_tokens: {"text": output, "output_tokens": 20,
                                               "limit_hit": False},
                    model_id="fixture").clean(source)
                self.assertEqual((result.path, result.text), ("llm", output))

    def test_fusion_preserves_case_and_each_source_occurrence(self):
        for source, output, component in (
            ("Use iOS 4.", "Use IOS4.", "numeric_values"),
            ("Use WGS 84.", "Use wgs84.", "numeric_values"),
            ("Compare WGS with WGS 84.", "Compare WGS84 with WGS.", "numeric_values"),
            ("Compare WGS with WGS 84.", "Compare with WGS84.", "coverage"),
        ):
            with self.subTest(source=source, output=output):
                self.assertIn(component, failures(source, output))

    def test_a_number_fuses_only_with_its_own_word_occurrence(self):
        for source, wrong, right in (
            ("Copy from channel to channel 3.", "Copy from channel3 to channel.",
             "Copy from channel to channel3."),
            ("Compare version with version 2.", "Compare version2 with version.",
             "Compare version with version2."),
            ("Read code and code 5.", "Read code5 and code.", "Read code and code5."),
            ("Copy from channel to (channel 3).", "Copy from channel3 to (channel).",
             "Copy from channel to (channel3)."),
        ):
            with self.subTest(source=source):
                self.assertIn("numeric_values", failures(source, wrong))
                self.assertEqual(failures(source, right), set())
                for candidate in (wrong, right):
                    result = CleanupEngine(
                        lambda prompt, max_tokens: {"text": candidate, "output_tokens": 20,
                                                   "limit_hit": False},
                        model_id="fixture").clean(source)
                    if candidate == wrong:
                        self.assertNotEqual(result.text, wrong)
                    else:
                        self.assertEqual((result.path, result.text), ("llm", right))

    def test_a_word_and_its_number_may_fuse(self):
        for source, output in (
            ("this transform assumes the datum is wgs eighty four, but the input uses etrs eighty "
             "nine.", "This transform assumes the datum is WGS84, but the input uses ETRS89."),
            ("check cox one in the field notes", "Check COX1 in the field notes."),
            ("the helper still calls PROJ four for the transform", "The helper still calls PROJ.4 for the transform."),
            ("pin the parser to version 2 for now", "Pin the parser to version2 for now."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_fusions_still_fail(self):
        for source, output in (
            ("the datum is WGS eighty four", "The datum is WGS85."),
            ("the datum is WGS eighty four", "The datum is WGT84."),
            ("the WGS datum, version 84, is old", "The WGS84 datum, version, is old."),
            # The digits are the dictated number as written: no new zero or version part.
            ("board flight ba eighty four at noon", "Board flight BA084 at noon."),
            ("the helper still calls PROJ four for the transform", "The helper still calls PROJ.4.0 for the transform."),
            ("pin the parser to version 2 for now", "Pin the parser to version02 for now."),
            # A function word fuses with nothing.
            ("take a 1 liter sample", "Take A1 liter sample."),
            # "a 1 liter sample" fuses nothing, and "A1" is the source's own station.
            ("start at station A1 and take a 1 liter sample, then go to A6",
             "Start at station A1 and take a liter sample, then go to A1."),
        ):
            with self.subTest(source=source):
                self.assertIn("numeric_values", failures(source, output))


if __name__ == "__main__":
    unittest.main()
