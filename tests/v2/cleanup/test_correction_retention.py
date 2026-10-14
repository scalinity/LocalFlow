"""Exact source qualifiers survive elliptical value corrections."""
import pathlib
import json
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import (CleanupEngine, correction_marker_start,
                                        parse_correction_output)
from localflow.v2.cleanup.correction_retention import correction_view


def clean(source, proposal, corrections, *, protected=()):
    inputs = []

    def generate(prompt, max_tokens):
        is_correction = "Find the self-corrections" in prompt
        if not is_correction:
            inputs.append(prompt)
        return {"text": corrections if is_correction else proposal,
                "output_tokens": 12, "limit_hit": False}

    return CleanupEngine(generate, model_id="fixture").clean(
        source, protected_spans=list(protected)), inputs


class CorrectionRetentionTests(unittest.TestCase):
    def test_quantity_qualifier_survives_with_other_independent_corrections(self):
        source = ("The pallet fork needs 0.4 millimeters of polish, no wait, "
                  "0.2 millimeters, and the test runs for 6 hours, sorry, "
                  "8 hours, then flag the hairspring as suspect, actually, as fine.")
        target = ("The pallet fork needs 0.2 millimeters of polish, and the test "
                  "runs for 8 hours, then flag the hairspring as fine.")
        for proposal in (target, target.replace(" of polish", "")):
            with self.subTest(proposal=proposal):
                result, inputs = clean(source, proposal,
                                       "0.4 millimeters of polish, no wait\n"
                                       "6 hours, sorry\nas suspect, actually")
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 3)
                self.assertIn("0.2 millimeters of polish", inputs[0])

    def test_inherited_postmodifiers_are_source_text_not_new_content(self):
        for detail in ("of varnish", "for finishing", "of batch_12", "at 30%"):
            with self.subTest(detail=detail):
                source = f"Use 4 liters {detail}, sorry, 6 liters."
                target = f"Use 6 liters {detail}."
                result, _ = clean(source, target, f"4 liters {detail}, sorry")
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_retained_identifier_and_quantity_cannot_change(self):
        for detail, changed in (("of batch_12", "of batch_21"),
                                ("at 30%", "at 40%")):
            with self.subTest(detail=detail):
                source = f"Use 4 liters {detail}, sorry, 6 liters."
                result, _ = clean(source, f"Use 6 liters {changed}.",
                                   f"4 liters {detail}, sorry")
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_multiple_retained_qualifiers_keep_independent_anchors(self):
        source = ("Use 4 liters of dye, no wait, 6 liters, and reserve "
                  "3 grams of varnish, no wait, 5 grams for finishing.")
        target = "Use 6 liters of dye, and reserve 5 grams of varnish for finishing."
        result, _ = clean(source, target,
                           "4 liters of dye, no wait\n3 grams of varnish, no wait")
        self.assertEqual(result.text, target)
        self.assertEqual(result.corrections["applied"], 2)

    def test_protected_replacement_occurrence_is_rebased_without_changing_it(self):
        source = "Use 4 liters of dye, no wait, 6 liters and label the container."
        literal = "6 liters"
        start = source.index(literal)
        target = "Use 6 liters of dye and label the container."
        result, _ = clean(source, target, "4 liters of dye, no wait",
                           protected=[(start, start + len(literal), "literal")])
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")

    def test_overlapping_correction_does_not_delete_an_inherited_qualifier(self):
        source = "Use 4 liters of dye, no wait, 6 liters, no wait, 8 liters."
        result, _ = clean(source, "Use 8 liters.",
                           "4 liters of dye, no wait\n6 liters, no wait")
        self.assertEqual(result.text, source)
        self.assertIn("overlapping_retention_replacement",
                      result.corrections["rejected_reasons"])

    def test_retry_assembly_uses_the_same_retained_source_view(self):
        first = "Use 4 liters of dye, no wait, 6 liters for the first finishing pass."
        second = "Keep the label attached to the container until the review finishes."
        source = first + " " + second
        first_target = "Use 6 liters of dye for the first finishing pass."
        target = first_target + " " + second
        calls = 0

        def generate(prompt, max_tokens):
            nonlocal calls
            if "Find the self-corrections" in prompt:
                return {"text": "4 liters of dye, no wait", "output_tokens": 8,
                        "limit_hit": False}
            calls += 1
            body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
            text = json.loads(body)["transcript"]
            if calls == 1:
                return {"text": "Use", "output_tokens": 1, "limit_hit": True}
            return {"text": first_target if "6 liters" in text else text,
                    "output_tokens": 15, "limit_hit": False}

        result = CleanupEngine(generate, model_id="fixture").clean(source)
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 1)
        assembly = [o for o in result.observations if o.get("stage") == "retry_assembly"]
        self.assertEqual(len(assembly), 1)
        self.assertTrue(assembly[0]["accepted"])

    def test_qualifier_cannot_move_to_another_equal_quantity(self):
        source = ("Use 4 liters of dye, no wait, 6 liters, "
                  "and reserve 6 liters for cleaning.")
        target = "Use 6 liters of dye, and reserve 6 liters for cleaning."
        good, _ = clean(source, target, "4 liters of dye, no wait")
        self.assertEqual(good.text, target)
        wrong = "Use 6 liters, and reserve 6 liters of dye for cleaning."
        bad, _ = clean(source, wrong, "4 liters of dye, no wait")
        self.assertEqual(bad.text, source)

    def test_explicit_replacement_postmodifier_supersedes_old_one(self):
        source = "Use 4 liters of dye, no wait, 6 liters of solvent."
        target = "Use 6 liters of solvent."
        result, _ = clean(source, target, "4 liters of dye, no wait")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")

    def test_explicit_absence_replaces_same_presence_description(self):
        source = "Use 4 liters with dye, no wait, 6 liters without dye."
        target = "Use 6 liters without dye."
        result, inputs = clean(source, target, "4 liters with dye, no wait")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertNotIn("6 liters with dye without dye", inputs[0])
        wrong = "Use 6 liters with dye without dye."
        result, _ = clean(source, wrong, "4 liters with dye, no wait")
        self.assertEqual(result.text, source)

    def test_opposing_relation_does_not_waive_negation_or_guess_substance(self):
        for old, new in (("without dye", "with dye"),
                         ("of dye", "without dye"),
                         ("without dye", "of dye")):
            with self.subTest(old=old, new=new):
                source = f"Use 4 liters {old}, no wait, 6 liters {new}."
                wrong = f"Use 6 liters {old} {new}."
                result, _ = clean(source, wrong, f"4 liters {old}, no wait")
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_different_presence_and_absence_descriptions_still_coexist(self):
        for old, new in (("with dye", "without solvent"),
                         ("with red dye", "without blue dye")):
            with self.subTest(old=old, new=new):
                source = f"Use 4 liters {old}, sorry, 6 liters {new}."
                target = f"Use 6 liters {old} {new}."
                result, _ = clean(source, target, f"4 liters {old}, sorry")
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_article_variation_does_not_hide_an_opposing_description(self):
        source = "Use 4 liters with the dye, sorry, 6 liters without dye."
        result, _ = clean(source, "Use 6 liters with the dye without dye.",
                           "4 liters with the dye, sorry")
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)

    def test_comparison_copy_preserves_every_character_coordinate_across_moves(self):
        source = ("Note α: Use 4 liters of dye, no wait, 6 liters, and reserve "
                  "3 grams of varnish, no wait, 5 grams for batch_12.")
        accepted, rejected = parse_correction_output(
            "4 liters of dye, no wait\n3 grams of varnish, no wait", source, [])
        self.assertFalse(rejected)
        spans = [(a, b, correction_marker_start(source, (a, b)))
                 for (a, b), _ in accepted]
        view, moved_corrections, positions = correction_view(
            source, spans, [(i, i + 1) for i in range(len(source))])
        self.assertEqual(view,
                         "Note α: Use 4 liters, no wait, 6 liters of dye, and reserve "
                         "3 grams, no wait, 5 grams of varnish for batch_12.")
        for index, (start, end) in enumerate(positions):
            self.assertEqual(view[start:end], source[index:index + 1], index)
        self.assertEqual([view[a:b] for a, b, _ in moved_corrections],
                         ["4 liters, no wait", "3 grams, no wait"])
        self.assertEqual([view[m:b] for _a, b, m in moved_corrections],
                         ["no wait", "no wait"])

    def test_multiple_moves_rebase_admitted_protected_occurrences(self):
        source = ("Note α: Use 4 liters of dye, no wait, 6 liters, and reserve "
                  "3 grams of varnish, no wait, 5 grams for batch_12.")
        target = "Note α: Use 6 liters of dye, and reserve 5 grams of varnish for batch_12."
        protections = [(source.index(text), source.index(text) + len(text), "literal")
                       for text in ("Note α", "6 liters", "and reserve", "5 grams", "batch_12")]
        result, _ = clean(source, target,
                           "4 liters of dye, no wait\n3 grams of varnish, no wait",
                           protected=protections)
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")

    def test_old_value_cannot_return_with_the_retained_qualifier(self):
        source = "Use 4 liters of dye, no wait, 6 liters."
        wrong = "Use 6 liters of dye and 4 liters."
        result, _ = clean(source, wrong, "4 liters of dye, no wait")
        self.assertEqual(result.text, source)
        source = "Send it to Mark no wait to Lisa."
        result, _ = clean(source, "Send it to Lisa and Mark.", "to Mark no wait")
        self.assertEqual(result.text, source)

    def test_retention_cannot_change_a_protected_replacement_phrase(self):
        source = "Use 4 liters of dye, no wait, 6 liters for cleaning."
        literal = "6 liters for cleaning"
        start = source.index(literal)
        result, _ = clean(source, "Use 6 liters of dye for cleaning.",
                           "4 liters of dye, no wait",
                           protected=[(start, start + len(literal), "literal")])
        self.assertEqual(result.text, source)

    def test_repeated_as_frame_admits_explicit_complement_replacement(self):
        for source, deletion, target in (
            ("Flag it as suspect, actually, as fine.", "as suspect, actually", "Flag it as fine."),
            ("Flag it as suspect, actually, as fine.", "suspect, actually", "Flag it as fine."),
            ("Treat this as a draft, actually, as final.", "as a draft, actually", "Treat this as final."),
            ("Treat this as a draft, actually, as final.", "a draft, actually", "Treat this as final."),
        ):
            with self.subTest(source=source):
                result, _ = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_as_frame_does_not_authorize_an_unrelated_clause_or_emphasis(self):
        for source, deletion in (
            ("We actually shipped it.", "We actually"),
            ("Treat it as suspect and notify Mira, actually, as fine.",
             "as suspect and notify Mira, actually"),
            ("Act as guide. Actually, as host.", "as guide. Actually"),
        ):
            with self.subTest(source=source):
                accepted, _ = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)


if __name__ == "__main__":
    unittest.main()
