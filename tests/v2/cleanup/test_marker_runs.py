"""Consecutive correction markers are one marker.

A deletion such as "0.5 seconds no I mean" ends with the marker "I mean",
and the "no" before it is a marker too, not a lost negation. A deletion
that ends at "no" in "ten, no, sorry, eleven" leaves "sorry" behind, and
that "sorry" belongs to the same marker. A negation that is content (in
the old value, or opening the replacement) is still required.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_marker_runs.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import validate  # noqa: E402


def span(source, delete, marker):
    """(start, end, marker_start) of ``delete`` in ``source``."""
    start = source.index(delete)
    return start, start + len(delete), start + delete.rindex(marker)


def failures(source, output, corrections):
    return {c.name for c in validate(source, output, correction_spans=corrections).critical_failures}


def clean(source, lines, output):
    def generate(prompt, max_tokens):
        text = "\n".join(lines) if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class MarkerRunTests(unittest.TestCase):
    def test_a_marker_before_the_recorded_marker_is_not_a_negation(self):
        source = "Wait for the lag to drop below 0.5 seconds no I mean 0.3 seconds before you start."
        output = "Wait for the lag to drop below 0.3 seconds before you start."
        self.assertEqual(failures(source, output, [span(source, "0.5 seconds no I mean", "I mean")]), set())
        result = clean(source, ["0.5 seconds no I mean"], output)
        self.assertEqual((result.path, result.text), ("llm", output))

    def test_a_marker_left_after_the_deletion_belongs_to_it(self):
        for source, delete, marker, output in (
            ("We meet on Thursday at ten, no, sorry, Thursday at eleven, in the small room.",
             "Thursday at ten, no", "no", "We meet on Thursday at eleven, in the small room."),
            ("Take the water samples at 6 am no make that 7 am and use the small net.",
             "6 am no", "no", "Take the water samples at 7 am and use the small net."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output, [span(source, delete, marker)]), set())
                result = clean(source, [delete], output)
                self.assertEqual((result.path, result.text), ("llm", output))

    def test_a_negation_in_the_old_value_is_still_required(self):
        source = "Use no sugar, I mean less sugar, in the second batch."
        output = "Use less sugar, in the second batch."
        self.assertIn("negation_coverage",
                      failures(source, output, [span(source, "no sugar, I mean", "I mean")]))

    def test_a_no_opening_the_replacement_is_content(self):
        source = "Set the limit to 5, no wait, no more than 6 jobs."
        output = "Set the limit to more than 6 jobs."
        self.assertIn("negation_coverage",
                      failures(source, output, [span(source, "5, no wait", "no wait")]))

    def test_markers_alone_are_not_an_old_value(self):
        source = "Start the pump, no I mean the valve, at noon."
        output = "Start the pump, the valve, at noon."
        self.assertIn("negation_coverage",
                      failures(source, output, [span(source, "no I mean", "I mean")]))

    def test_a_dropped_negation_elsewhere_still_fails(self):
        source = "Wait below 0.5 seconds no I mean 0.3 seconds and do not start the build."
        output = "Wait below 0.3 seconds and do start the build."
        self.assertIn("negation_coverage",
                      failures(source, output, [span(source, "0.5 seconds no I mean", "I mean")]))


if __name__ == "__main__":
    unittest.main()
