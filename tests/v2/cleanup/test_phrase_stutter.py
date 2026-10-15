"""Function-word stutters across a filler and as a repeated phrase.

"on the uh the matte stock" and "flag that in the in the comment thread"
repeat function words the way "the the" does; the cleanup says them once.
A filler between the copies does not break a stutter, and a repeated
function-word phrase that ends in an article is a stutter because a noun
phrase must follow an article. Repeats that can be grammatical ("you and
I and I think", "those who could, could leave"), other repeated phrases
and quoted text still keep every word.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_phrase_stutter.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class PhraseStutterTests(unittest.TestCase):
    def test_a_stutter_is_said_once(self):
        for source, output in (
            ("Print a proof on the uh the matte stock, not the glossy.",
             "Print a proof on the matte stock, not the glossy."),
            ("I want the reviewer to flag that in the in the comment thread today.",
             "I want the reviewer to flag that in the comment thread today."),
            ("Re-torque the turnbuckles on the, on the backstay before noon.",
             "Re-torque the turnbuckles on the backstay before noon."),
            ("Check which of the um of the 2 branches drops packets.",
             "Check which of the 2 branches drops packets."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_repeats_keep_every_word(self):
        for source, output in (
            ("Between you and I and I think it works.", "Between you and I think it works."),
            ("Pin the image so that so that the build stays identical.",
             "Pin the image so that the build stays identical."),
            ("We know we know the risk already.", "We know the risk already."),
            ('Fix the phrase "in the in the" in chapter two.', 'Fix the phrase "in the" in chapter two.'),
            ("Put it in the box and the lid on the shelf.", "Put it in the box on the shelf."),
            # A doubled modal can be grammatical: "those who could, could leave".
            ("Those who could, could leave early.", "Those who could leave early."),
            ("Those who should, should leave early.", "Those who should leave early."),
        ):
            with self.subTest(source=source):
                self.assertIn("coverage", failures(source, output))


if __name__ == "__main__":
    unittest.main()
