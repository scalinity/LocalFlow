"""A rejected correction the cleanup applied anyway is put back as dictated."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine
from localflow.v2.cleanup.validation import restore_source_spans


def clean(source, output, corrections):
    def generate(prompt, max_tokens):
        text = corrections if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def decision(result):
    return next(o for o in result.observations if o.get("kind") == "cleanup_decision")


class RejectedCorrectionSalvageTests(unittest.TestCase):
    def test_one_rejected_correction_does_not_cost_the_other_two(self):
        source = ("use 3 lamps i mean 4 lamps for the booth then bring the large grey case "
                  "from the lab sorry the small case and add 10 milliliters per participant "
                  "no wait 12 milliliters per participant")
        corrections = ("3 lamps i mean\nthe large grey case from the lab sorry\n"
                       "10 milliliters per participant no wait")
        output = ("Use 4 lamps for the booth, then bring the small case and add "
                  "12 milliliters per participant.")
        result = clean(source, output, corrections)
        self.assertEqual(result.text, (
            "Use 4 lamps for the booth, then bring the large grey case from the lab sorry "
            "the small case and add 12 milliliters per participant."))
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 2)
        self.assertEqual(result.corrections["rejected_reasons"], ["span_too_long"])
        self.assertEqual(decision(result)["rejected_corrections_restored"], 1)

    def test_a_correction_rejected_to_protect_meaning_returns_verbatim(self):
        source = "Book it for Monday, no Tuesday is a holiday, and send 5, sorry, 6 copies."
        output = "Book it for Tuesday is a holiday, and send 6 copies."
        result = clean(source, output, "Monday, no\n5, sorry")
        self.assertEqual(result.text, "Book it for Monday, no Tuesday is a holiday, and send 6 copies.")
        self.assertEqual(result.corrections["applied"], 1)
        self.assertEqual(result.corrections["rejected_reasons"], ["not_parallel"])

    def test_the_window_still_falls_back_when_other_damage_remains(self):
        source = "Use 3 lamps, I mean 4 lamps, and the large grey case from the lab, sorry, the small case."
        output = "Use 4 lamps, and the small box."
        result = clean(source, output, "3 lamps, I mean\nthe large grey case from the lab, sorry")
        self.assertEqual(result.text, source)
        self.assertNotEqual(result.path, "llm")

    def test_restoration_needs_the_whole_span_dropped_in_one_place(self):
        source = "Bring the large grey case from the lab, sorry, the small case today."
        span = (source.index("the large"), source.index(", the small"))
        # Kept in place: nothing to restore.
        self.assertIsNone(restore_source_spans(source, source, [span]))
        # Only part of it dropped: the output still holds words where it was.
        self.assertIsNone(restore_source_spans(
            source, "Bring the grey case, the small case today.", [span]))
        restored = restore_source_spans(source, "Bring the small case today.", [span])
        self.assertEqual(restored, (source, 1))


if __name__ == "__main__":
    unittest.main()
