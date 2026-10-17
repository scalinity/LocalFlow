"""A filler next to a correction marker is no part of either value."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, _has_correction_marker, parse_correction_output


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class FillerValueTests(unittest.TestCase):
    def test_a_filler_before_the_marker_does_not_hide_the_old_value(self):
        for source, proposal, target in (
            ("Run the dry run against replica db-stage-02 uh, sorry, db-stage-03, using "
             "the reindex script.", "db-stage-02 uh, sorry",
             "Run the dry run against replica db-stage-03, using the reindex script."),
            ("We meet on Tuesday uh no Wednesday at nine.", "Tuesday uh no",
             "We meet on Wednesday at nine."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                self.assertTrue(_has_correction_marker(source))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_a_filler_is_neither_an_old_value_nor_evidence(self):
        for source, proposal, reason in (
            ("Okay, uh, sorry, the cable is loose.", "Okay, uh, sorry", "not_parallel"),
            ("So uh, sorry, the cable is loose.", "uh, sorry", "no_outdated_value"),
            ("Mark the tray, uh, sorry, I dropped it.", "the tray, uh, sorry", "not_parallel"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], [reason]))
        self.assertFalse(_has_correction_marker("Mark the tray, uh, sorry, I dropped it."))


if __name__ == "__main__":
    unittest.main()
