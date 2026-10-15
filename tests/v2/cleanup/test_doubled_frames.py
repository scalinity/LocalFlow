"""The frame a correction leaves doubled is said once.

"flag gaps longer than 6 hours, no wait, longer than 4 hours" deletes "6
hours, no wait" and leaves "longer than , longer than 4 hours"; the
cleanup writes "longer than 4 hours". Words right after the deletion that
repeat the words right before it are the restated frame, so one copy may
go. A single repeated word qualifies only as a function word or
preposition, or before a number that replaces a number. Repeats away from
a correction, a content word repeated before a non-number, and an output
that drops both copies still fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_doubled_frames.py
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


def clean(source, lines, output):
    def generate(prompt, max_tokens):
        text = "\n".join(lines) if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class DoubledFrameTests(unittest.TestCase):
    def test_the_restated_frame_is_said_once(self):
        for source, delete, marker, output in (
            ("Run the check and flag gaps longer than 6 hours, no wait, longer than 4 hours "
             "before Friday.", "6 hours, no wait", "no wait",
             "Run the check and flag gaps longer than 4 hours before Friday."),
            ("I already reviewed the first 40 entries, sorry, the first 45 entries, and they "
             "look fine.", "40 entries, sorry", "sorry",
             "I already reviewed the first 45 entries, and they look fine."),
            ("Send the draft by Thursday at noon, no sorry by Wednesday at noon, so I can "
             "read it.", "Thursday at noon, no sorry", "no sorry",
             "Send the draft by Wednesday at noon, so I can read it."),
            ("The scheduler failed on target 212, no wait, target 221, because the slit "
             "was booked.", "212, no wait", "no wait",
             "The scheduler failed on target 221, because the slit was booked."),
            ("Set the sample interval to about 15 minutes, sorry, about 20 minutes, because "
             "the radios drain.", "15 minutes, sorry", "sorry",
             "Set the sample interval to about 20 minutes, because the radios drain."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output, [span(source, delete, marker)]), set())
                result = clean(source, [delete], output)
                self.assertEqual((result.path, result.text), ("llm", output))

    def test_keeping_both_copies_still_passes(self):
        source = "Flag gaps longer than 6 hours, no wait, longer than 4 hours today."
        output = "Flag gaps longer than longer than 4 hours today."
        self.assertEqual(failures(source, output, [span(source, "6 hours, no wait", "no wait")]), set())

    def test_a_repeated_content_word_before_a_non_number_stays(self):
        source = "I think that this, no wait, that is right for the report."
        output = "I think that is right for the report."
        self.assertIn("coverage", failures(source, output, [span(source, "this, no wait", "no wait")]))

    def test_dropping_both_copies_still_fails(self):
        source = "Flag gaps longer than 6 hours, no wait, longer than 4 hours today."
        output = "Flag gaps 4 hours today."
        self.assertIn("coverage", failures(source, output, [span(source, "6 hours, no wait", "no wait")]))

    def test_a_repeat_without_a_correction_stays(self):
        source = "Copy the table and then and then build the new index on that copy."
        output = "Copy the table and then build the new index on that copy."
        self.assertIn("coverage", failures(source, output))

    def test_a_restated_negation_frame_survives_once(self):
        source = "Ship it without the 2 manuals, sorry, without the 3 manuals tomorrow."
        output = "Ship it without the 3 manuals tomorrow."
        self.assertEqual(failures(source, output, [span(source, "2 manuals, sorry", "sorry")]), set())
        dropped = "Ship it the 3 manuals tomorrow."
        self.assertTrue({"coverage", "negation_coverage"}
                        <= failures(source, dropped, [span(source, "2 manuals, sorry", "sorry")]))


if __name__ == "__main__":
    unittest.main()
