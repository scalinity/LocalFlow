"""A negative answer keeps contrast evidence anywhere in its sentence."""
import unittest

from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output


LONG_ANSWER = (
    "the proposal about archiving old laboratory records in the locked storage room, "
    "moving the spare cabinets away from the emergency exit, copying the revised "
    "maintenance schedule into the shared calendar, updating the inventory of "
    "replacement cables in the workshop, replacing the damaged window blinds beside "
    "the reception desk, checking the batteries in every portable scanner before "
    "delivery, cleaning the filters in the ventilation units above the benches, "
    "reviewing the instructions supplied with the replacement pressure sensors, "
    "preparing the monthly summary of equipment inspections for the committee, "
    "reorganizing the spare components according to their manufacturer specifications, "
    "returning the borrowed calibration instruments to the engineering department, "
    "documenting the modifications made during the previous maintenance visit, "
    "collecting the completed checklists from every supervisor before the deadline, "
    "confirming the delivery addresses for replacement equipment ordered by the "
    "laboratory manager"
)
PROPOSAL = "to the third, no"


class YesNoContrastTests(unittest.TestCase):
    def test_a_long_sentence_keeps_both_answers(self):
        for answer in ("a" * 1000, LONG_ANSWER):
            source = "Say yes to " + answer + ", and to the third, no to the fourth."
            with self.subTest(answer=answer[:20]):
                accepted, rejected = parse_correction_output(PROPOSAL, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["not_parallel"])

                def generate(prompt, max_tokens):
                    return {"text": PROPOSAL if "Find the self-corrections" in prompt
                            else source.replace(PROPOSAL + " ", ""),
                            "output_tokens": 160, "limit_hit": False}

                result = CleanupEngine(generate, model_id="fixture").clean(source)
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_an_earlier_sentence_does_not_block_a_correction(self):
        for boundary in (". ", "! ", "? ", "\n"):
            source = "Say yes to " + LONG_ANSWER + boundary + "Move it to the third, no to the fourth."
            with self.subTest(boundary=boundary):
                accepted, rejected = parse_correction_output(PROPOSAL, source, [])
                self.assertEqual([a.delete for a in accepted], [PROPOSAL])
                self.assertEqual(rejected, [])

    def test_a_different_frame_does_not_contrast(self):
        source = "Say yes for " + LONG_ANSWER + ", and to the third, no to the fourth."
        accepted, rejected = parse_correction_output(PROPOSAL, source, [])
        self.assertEqual([a.delete for a in accepted], [PROPOSAL])
        self.assertEqual(rejected, [])

    def test_punctuation_touching_the_marker_keeps_the_prefix_boundary(self):
        accepted, rejected = parse_correction_output(
            "3.no", "Say yes 4, then choose 3.no 4.", [])
        self.assertEqual([a.delete for a in accepted], ["3.no"])
        self.assertEqual(rejected, [])


if __name__ == "__main__":
    unittest.main()
