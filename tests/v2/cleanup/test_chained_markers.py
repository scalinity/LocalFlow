"""A marker chained before the proposal's own is no part of the old value."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class ChainedMarkerTests(unittest.TestCase):
    def test_the_value_before_a_chained_marker_is_compared(self):
        for source, proposal, target in (
            ("The group tried the lever on Tuesday, I mean no, on Wednesday, and found it.",
             "on Tuesday, I mean no",
             "The group tried the lever on Wednesday, and found it."),
            ("The screen is set for Tuesday, actually sorry, Wednesday at 9:15 in the cold room.",
             "Tuesday, actually sorry",
             "The screen is set for Wednesday at 9:15 in the cold room."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_chained_markers_alone_are_no_old_value(self):
        for source, proposal, reason in (
            ("We actually, no, we did not ship it.", "We actually, no", "no_outdated_value"),
            # Stripping the chained marker leaves no parallel value.
            ("Give it to the nurse, I mean no, the pharmacist.", "the nurse, I mean no",
             "not_parallel"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], [reason]))


if __name__ == "__main__":
    unittest.main()
