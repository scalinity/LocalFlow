"""Rendered list labels are structure; a quantity never becomes one."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import validate


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


def clean(source, output):
    def generate(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class ListLabelTests(unittest.TestCase):
    def test_step_labels_and_quantities_stay_apart(self):
        source = "Step 1 preheat the oven. Step 2 add 3 cups of flour."
        self.assertEqual(failures(source, "1. Preheat the oven.\n2. Add 3 cups of flour."), set())
        for output, expected in (
            ("1. Preheat the oven.\n2. Add\n3. Cups of flour.", {"coverage", "numeric_values"}),
            ("1. Preheat the oven.\n2. Add cups of flour.", {"coverage", "numeric_values"}),
            ("1. Preheat the oven.\n2. Add 2 cups of flour.", {"coverage", "numeric_values"}),
        ):
            with self.subTest(output=output):
                self.assertEqual(failures(source, output), expected)

    def test_a_quantity_at_a_line_start_never_becomes_a_label(self):
        for source, output in (
            ("Shopping:\n1 apple\n2 pears", "Shopping:\n1. Apple\n2. Pears"),
            ("Pack 3 apples\n4 pears", "Pack\n3. Apples\n4. Pears"),
            ("Stock notes. 1 tablet is stored. 2 tablets are stored beside 2 bottles.",
             "Stock notes.\n1. Tablet is stored.\n2. Tablets are stored beside 2 bottles."),
            ("Rack notes. 1 test per rack. 2 test per rack with 2 labels.",
             "Rack notes.\n1. Test per rack.\n2. Test per rack with 2 labels."),
            ("We need 2, the big ones, and 1, the small one.",
             "We need:\n1. The big ones.\n2. The small one."),
        ):
            with self.subTest(source=source):
                self.assertIn("numeric_values", failures(source, output))
                self.assertEqual(clean(source, output).text, source)
        for output in ("Shopping:\n- 1 apple\n- 2 pears", "Shopping:\n1. 1 apple\n2. 2 pears"):
            with self.subTest(output=output):
                self.assertEqual(failures("Shopping:\n1 apple\n2 pears", output), set())

    def test_a_spoken_enumeration_may_become_the_labels(self):
        for source, output in (
            ("Do these in order. One, check the stops. Two, voice the oboe.",
             "Do these in order.\n\n1. Check the stops.\n2. Voice the oboe."),
            ("Please add these, 1 the east wing needs 6 attendants by nine, "
             "2 the cart must be restocked.",
             "Please add these:\n1. The east wing needs 6 attendants by nine.\n"
             "2. The cart must be restocked."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())
                self.assertEqual(clean(source, output).text, output)

    def test_labels_must_open_or_continue_a_list(self):
        self.assertEqual(failures("Keep it.", "Keep it.\n7. Done."), {"novelty", "numeric_values"})
        source = "first open the box second close the lid"
        self.assertIn("numeric_values", failures(source, "3. Open the box.\n4. Close the lid."))


if __name__ == "__main__":
    unittest.main()
