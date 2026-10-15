"""An introduced list's final "and" may become a bullet separator.

The introduction is the last sentence before the colon, so a paragraph
that opens with another sentence ("Orla is sorting presents today. Here is
a list of gift ideas:") or a clause before "here is" still introduces the
list, and so does "the camping gear list is:". Fillers between items are
dropped anyway. An item never runs past a source sentence boundary, so a
closing sentence glued onto the last bullet, and lists without an
introduction, still fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_list_introductions.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class ListIntroductionTests(unittest.TestCase):
    def test_the_last_sentence_before_the_colon_introduces_the_list(self):
        for source, output in (
            ("Orla is sorting presents today. Here is a list of gift ideas a scarf a candle set "
             "and a puzzle box.",
             "Orla is sorting presents today. Here is a list of gift ideas:\n- a scarf\n"
             "- a candle set\n- a puzzle box"),
            ("and then the setup notes, here is a list of cache checks, uh, confirm the prefix "
             "is stable, check the TTL is 300 seconds, and log the hit rate",
             "And then the setup notes, here is a list of cache checks:\n- confirm the prefix "
             "is stable\n- check the TTL is 300 seconds\n- log the hit rate"),
            ("the camping gear list is a tent, 2 sleeping bags, and a camp stove",
             "The camping gear list is:\n- a tent\n- 2 sleeping bags\n- a camp stove"),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_lists_keep_their_and(self):
        for source, output in (
            # A closing sentence glued onto the last bullet.
            ("Here is a list of gift ideas a scarf a candle set and a puzzle box. Also remember "
             "the tokens expire.",
             "Here is a list of gift ideas:\n- a scarf\n- a candle set\n- a puzzle box Also "
             "remember the tokens expire."),
            # No introduction.
            ("we bought a scarf a candle set and a puzzle box",
             "We bought:\n- a scarf\n- a candle set\n- a puzzle box"),
        ):
            with self.subTest(source=source):
                self.assertIn("coverage", failures(source, output))


if __name__ == "__main__":
    unittest.main()
