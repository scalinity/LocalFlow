"""Every proposal line the parser does not admit is recorded as rejected."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CORRECTIONS_MAX, CleanupEngine, parse_correction_output

SOURCE = ("Use 2 trays, no 3 trays, then 3 cups, no 4 cups, then 5 pans, no 6 pans, then "
          "7 jars, no 8 jars, then 9 lids, no 10 lids, then 11 bags, no 12 bags, then "
          "13 boxes, no 14 boxes.")
PROPOSALS = ["2 trays, no", "3 cups, no", "5 pans, no", "7 jars, no", "9 lids, no",
             "11 bags, no", "13 boxes, no"]


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class UnadmittedLineTests(unittest.TestCase):
    def test_lines_past_the_cap_are_rejected_and_put_back(self):
        accepted, rejected = parse_correction_output("\n".join(PROPOSALS), SOURCE, [])
        self.assertEqual([c.delete for c in accepted], PROPOSALS[:CORRECTIONS_MAX])
        self.assertEqual([(r.reason, r.delete) for r in rejected],
                         [("too_many_corrections", "13 boxes, no")])
        # The cleanup applies all seven; the seventh is put back as dictated
        # and the window keeps the other six.
        target = ("Use 3 trays, then 4 cups, then 6 pans, then 8 jars, then 10 lids, then "
                  "12 bags, then 14 boxes.")
        result = clean(SOURCE, target, "\n".join(PROPOSALS))
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.text, target.replace("then 14 boxes", "then 13 boxes, no 14 boxes"))

    def test_a_restated_line_may_run_past_the_character_limit(self):
        source = ("Plan the route. The north crew should stage 6 crates of bottled water before "
                  "the lead riders arrive. Sorry, the north crew should stage 8 crates of bottled "
                  "water before the lead riders arrive.")
        line = ("The north crew should stage 6 crates of bottled water before the lead riders "
                "arrive. Sorry")
        self.assertGreater(len(line), 80)
        accepted, rejected = parse_correction_output(line, source, [])
        self.assertEqual(([c.delete for c in accepted], rejected), ([line], []))
        target = ("Plan the route. The north crew should stage 8 crates of bottled water before "
                  "the lead riders arrive.")
        self.assertEqual(clean(source, target, line).text, target)
        # Past the second limit no line is read, restated or not.
        long_source = "Note this. " + " ".join(["The crew"] * 30) + " left. Sorry, the crew stayed."
        long_line = " ".join(["The crew"] * 30) + " left. Sorry"
        self.assertGreater(len(long_line), 160)
        self.assertEqual([r.reason for r in parse_correction_output(long_line, long_source, [])[1]],
                         ["span_too_long"])

    def test_a_line_over_the_character_limit_is_rejected_not_dropped(self):
        source = ("Bring the long blue outdoor extension cord from the storage room on the second "
                  "floor, sorry, the short one.")
        line = ("the long blue outdoor extension cord from the storage room on the second floor, "
                "sorry")
        self.assertGreater(len(line), 80)
        accepted, rejected = parse_correction_output(line, source, [])
        self.assertEqual(accepted, [])
        self.assertEqual([(r.reason, r.delete) for r in rejected], [("span_too_long", line)])


if __name__ == "__main__":
    unittest.main()
