"""Repeated frequency frames stay attached to corrected quantities."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output


def clean(source, target, proposal, protected=()):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(
        source, protected_spans=list(protected))


class RepeatedQuantityFrameTests(unittest.TestCase):
    def test_repeated_every_marks_a_frequency_correction(self):
        source = ("Review the lexicon every month, no every quarter, because the "
                  "monthly cadence was too heavy.")
        target = "Review the lexicon every quarter, because the monthly cadence was too heavy."
        accepted, rejected = parse_correction_output("every month, no", source, [])
        self.assertEqual(rejected, [])
        self.assertEqual([c.delete for c in accepted], ["every month, no"])
        result = clean(source, target, "every month, no")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")

    def test_value_only_proposal_includes_repeated_frequency_frame(self):
        for old, new, unit in (("18", "27", "cycles"), ("2.5", "3.5", "hours")):
            with self.subTest(unit=unit):
                source = f"Inspect the relay every {old} {unit}, sorry, every {new} {unit}."
                target = f"Inspect the relay every {new} {unit}."
                proposal = f"{old} {unit}, sorry"
                accepted, rejected = parse_correction_output(proposal, source, [])
                self.assertFalse(rejected)
                self.assertEqual(accepted[0].delete, f"every {old} {unit}, sorry")
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 1)

    def test_retained_frequency_and_restrictions_remain_required(self):
        source = ("Inspect every 18 cycles, sorry, every 27 cycles on the test rig only. "
                  "The reserve rig must never start.")
        target = ("Inspect every 27 cycles on the test rig only. "
                  "The reserve rig must never start.")
        for bad in (target.replace("27", "28"), target.replace("every ", ""),
                    target.replace(" only", ""), target.replace(" never", "")):
            with self.subTest(bad=bad):
                result = clean(source, bad, "18 cycles, sorry")
                self.assertNotEqual(result.text, bad)
                if "28" in bad:
                    self.assertEqual(result.corrections["applied"], 0)

    def test_changed_or_incomplete_replacement_does_not_expand(self):
        for replacement in ("every 27 minutes", "each 27 cycles",
                            "every cycle", "every -27 cycles",
                            "every 27 cycles-long"):
            with self.subTest(replacement=replacement):
                source = f"Inspect every 18 cycles, sorry, {replacement}."
                accepted, _ = parse_correction_output("18 cycles, sorry", source, [])
                self.assertTrue(all(not delete.startswith("every ")
                                    for delete in (c.delete for c in accepted)))

    def test_old_qualifier_and_clause_are_not_swallowed(self):
        for old in ("18 cycles on the spare rig", "18 cycles and restart"):
            source = f"Inspect every {old}, sorry, every 27 cycles."
            accepted, _ = parse_correction_output(f"{old}, sorry", source, [])
            self.assertTrue(all(not delete.startswith("every ")
                                for delete in (c.delete for c in accepted)))

    def test_protected_frame_cannot_be_added_to_deletion(self):
        source = "Inspect every 18 cycles, sorry, every 27 cycles."
        start = source.index("every")
        accepted, rejected = parse_correction_output(
            "18 cycles, sorry", source, [(start, start + 5, "literal")])
        self.assertFalse(accepted)
        self.assertEqual(rejected[0].reason, "protected_span")

    def test_repetition_without_a_correction_is_not_a_stutter(self):
        source = "Keep the label every every on the fixture."
        result = clean(source, "Keep the label every on the fixture.", "NONE")
        self.assertEqual(result.text, source)

    def test_other_correction_and_frequency_remain_independent(self):
        source = ("Inspect every 18 cycles, sorry, every 27 cycles, "
                  "using 5 probes, no, 8 probes.")
        target = "Inspect every 27 cycles, using 8 probes."
        result = clean(source, target, "18 cycles, sorry\n5 probes, no")
        self.assertEqual(result.text, target)
        self.assertEqual(result.corrections["applied"], 2)


if __name__ == "__main__":
    unittest.main()
