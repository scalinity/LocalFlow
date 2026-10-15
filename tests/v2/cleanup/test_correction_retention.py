"""Source-bound correction and copying repairs retain the original meaning."""
import pathlib
import json
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import (CleanupEngine,
                                        parse_correction_output,
                                        _has_correction_marker)
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
        for proposal in (target, target.replace(" of polish", ""),
                         target.replace("pallet fork", "palletfork")):
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

    def test_quantity_correction_retains_its_recipient(self):
        source = "Send 18 entries to the editor, sorry, 24 entries."
        target = "Send 24 entries to the editor."
        for proposal in (target, "Send 24 entries."):
            with self.subTest(proposal=proposal):
                result, inputs = clean(source, proposal,
                                       "18 entries to the editor, sorry")
                self.assertIn("24 entries to the editor", inputs[0])
                if proposal == target:
                    self.assertEqual(result.text, target)
                    self.assertEqual(result.path, "llm")
                else:
                    self.assertEqual(result.text, source)
                    self.assertEqual(result.corrections["applied"], 0)

    def test_quantity_correction_can_explicitly_replace_its_recipient(self):
        source = "Send 18 entries to the editor, sorry, 24 entries to the translator."
        target = "Send 24 entries to the translator."
        result, _ = clean(source, target, "18 entries to the editor, sorry")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        wrong, _ = clean(source, "Send 24 entries to the editor and the translator.",
                         "18 entries to the editor, sorry")
        self.assertEqual(wrong.text, source)

    def test_dropped_recipient_is_restored_within_the_existing_salvage_limit(self):
        ending = (" Keep each title attached to its entry, preserve the existing "
                  "spelling, and record the delivery in the shared register before "
                  "closing the review for this batch.")
        source = "Send 18 entries to the editor, sorry, 24 entries." + ending
        target = "Send 24 entries to the editor." + ending
        result, _ = clean(source, "Send 24 entries." + ending,
                           "18 entries to the editor, sorry")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 1)

    def test_recipient_retention_requires_the_same_quantity_head(self):
        source = "Send 18 entries to the editor, sorry, 24 files."
        result, _ = clean(source, "Send 24 files to the editor.",
                           "18 entries to the editor, sorry")
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)

    def test_infinitive_purpose_does_not_replace_a_recipient(self):
        for purpose in ("to be signed", "to deliver tomorrow", "to Be signed",
                        "to Deliver tomorrow", "to Be on file", "to Deliver before Friday"):
            with self.subTest(purpose=purpose):
                source = f"Send 18 entries to the editor, sorry, 24 entries {purpose}."
                result, _ = clean(source, f"Send 24 entries {purpose}.",
                                   "18 entries to the editor, sorry")
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)
                self.assertIn("unresolved_quantity_qualifier",
                              result.corrections["rejected_reasons"])

    def test_a_new_recipient_does_not_erase_an_old_purpose(self):
        source = "Send 18 entries to be signed, sorry, 24 entries to the editor."
        result, _ = clean(source, "Send 24 entries to the editor.",
                           "18 entries to be signed, sorry")
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)

    def test_recipient_replacement_accepts_bounded_noun_phrases_and_pronouns(self):
        for recipient in ("the senior editor", "the editor before Friday", "her",
                          "her before Friday"):
            with self.subTest(recipient=recipient):
                source = f"Send 18 entries to the editor, sorry, 24 entries to {recipient}."
                target = f"Send 24 entries to {recipient}."
                result, _ = clean(source, target, "18 entries to the editor, sorry")
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_capitalization_alone_does_not_classify_a_replacement_recipient(self):
        for old, new in (("the editor", "Nadia Vale"), ("Mira", "the editor")):
            with self.subTest(old=old, new=new):
                source = f"Send 18 entries to {old}, sorry, 24 entries to {new}."
                result, _ = clean(source, f"Send 24 entries to {new}.",
                                   f"18 entries to {old}, sorry")
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

    def test_retry_assembly_rebases_half_admissions_instead_of_recomputing(self):
        # The parent window holds an apostrophe that the half with the
        # correction does not. The assembly must reuse that half's admission
        # rather than re-deriving it against the parent text.
        first = ("Advance the rotor by 7 quarters of a turn, sorry, 1 half turn, "
                 "then lock the housing and log the reading.")
        second = "Don't open the cover until the gauge settles."
        source = first + " " + second
        target = ("Advance the rotor by 1 half turn, then lock the housing and "
                  "log the reading. " + second)
        calls = 0

        def generate(prompt, max_tokens):
            nonlocal calls
            if "Find the self-corrections" in prompt:
                return {"text": "7 quarters of a turn, sorry", "output_tokens": 8,
                        "limit_hit": False}
            calls += 1
            if calls == 1:
                return {"text": "Advance", "output_tokens": 1, "limit_hit": True}
            body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
            text = json.loads(body)["transcript"].replace("by , 1", "by 1")
            return {"text": text, "output_tokens": 15, "limit_hit": False}

        result = CleanupEngine(generate, model_id="fixture").clean(source)
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 1)
        assembly = [o for o in result.observations if o.get("stage") == "retry_assembly"]
        self.assertEqual([o["accepted"] for o in assembly], [True])

    def test_frame_led_quantity_keeps_its_detail_beside_the_replacement(self):
        for source, deletion, target, lossy in (
            ("Fill the tank with 4 liters of dye, sorry, with 6 liters.",
             "with 4 liters of dye, sorry", "Fill the tank with 6 liters of dye.",
             "Fill the tank with 6 liters."),
            ("Meet at 5 pm on Monday, sorry, at 6 pm.", "at 5 pm on Monday, sorry",
             "Meet at 6 pm on Monday.", "Meet at 6 pm."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(rejected, [])
                self.assertIsNotNone(accepted[0].move)
                result, _ = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                result, _ = clean(source, lossy, deletion)
                self.assertEqual(result.text, source)

    def test_unbindable_quantity_detail_keeps_the_source(self):
        # A spelled number, a determiner before the number, or a frame the
        # replacement does not repeat leaves the detail without a place.
        for source, deletion in (
            ("Fill the tank with four liters of dye, sorry, six liters.",
             "four liters of dye, sorry"),
            ("Fill the tank with the 4 liters of dye, sorry, 6 liters.",
             "the 4 liters of dye, sorry"),
            ("Fill the tank with 4 liters of dye, sorry, 6 liters.",
             "with 4 liters of dye, sorry"),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected],
                                 ["unresolved_quantity_qualifier"])
                lossy = source.replace(deletion + ", ", "").replace("with the ", "with ")
                result, _ = clean(source, lossy, deletion)
                self.assertEqual(result.text, source)

    def test_from_and_by_details_stay_beside_the_replacement(self):
        for source, deletion, target, lossy in (
            ("Pour 4 liters from the tank, sorry, 6 liters.", "4 liters from the tank, sorry",
             "Pour 6 liters from the tank.", "Pour 6 liters."),
            ("Cut 5 meters by 3 meters, sorry, 6 meters.", "5 meters by 3 meters, sorry",
             "Cut 6 meters by 3 meters.", "Cut 6 meters."),
        ):
            with self.subTest(source=source):
                result, _ = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                result, _ = clean(source, lossy, deletion)
                self.assertEqual(result.text, source)

    def test_detail_moves_before_a_following_subordinate_clause(self):
        for link in ("when", "once", "since"):
            with self.subTest(link=link):
                source = f"Use 4 liters of dye, no wait, 6 liters {link} the tank is clean."
                target = f"Use 6 liters of dye {link} the tank is clean."
                result, _ = clean(source, target, "4 liters of dye, no wait")
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

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
        view, moved_corrections, positions = correction_view(
            source, accepted, [(i, i + 1) for i in range(len(source))])
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

    def test_as_frame_replacement_must_close_its_clause(self):
        # Comparative and conditional frames continue past the first word,
        # so deleting the old complement would rewrite the clause.
        for source, deletion, wrong in (
            ("Mark the invoice as paid, actually, as soon as the bank confirms.",
             "as paid, actually", "Mark the invoice as soon as the bank confirms."),
            ("Log the call as resolved, actually, as soon as Mira confirms.",
             "as resolved, actually", "Log the call as soon as Mira confirms."),
            ("List it as optional, actually, as well as the cables.",
             "as optional, actually", "List it as well as the cables."),
            ("Treat it as suspect, actually, as fine and notify Mira.",
             "as suspect, actually", "Treat it as fine and notify Mira."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["not_parallel"])
                result, _ = clean(source, wrong, deletion)
                self.assertEqual(result.text, source)

    def test_single_word_replacement_that_opens_a_predicate_is_not_parallel(self):
        # The replacement is the subject of a new clause; a bare "no" there
        # is a negation, not a correction marker.
        for source, deletion, wrong in (
            ("Book it for Monday, no Tuesday is a holiday.", "Monday, no",
             "Book it for Tuesday is a holiday."),
            ("Set it to 5, no 6 is too many.", "5, no", "Set it to 6 is too many."),
            ("Order 4 trays, sorry, 6 trays are on the shelf.", "4 trays, sorry",
             "Order 6 trays are on the shelf."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["not_parallel"])
                result, _ = clean(source, wrong, deletion)
                self.assertEqual(result.text, source)
        for source, deletion in (
            ("Use 6 towels, no 5 towels for the corner suites.", "6 towels, no"),
            ("Do 5 exercises, actually 4 exercises that they can do at home.",
             "5 exercises, actually"),
            ("Meet on Tuesday, sorry, Thursday, at 10 AM.", "Tuesday, sorry"),
            ("Start at 8 am, no, 9 am, and take rooms 301 to 312.", "8 am, no"),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted, rejected)


class SourceRepairTests(unittest.TestCase):
    def test_metric_length_corrections_compare_typed_quantity_heads(self):
        for old, new in (("7 centimeters", "2 meters"),
                         ("0.8 kilometres", "900 metres"),
                         ("25 nanometers", "0.03 micrometers")):
            with self.subTest(old=old, new=new):
                source = f"Set the length to {old}, no {new}, then record it."
                target = f"Set the length to {new}, then record it."
                self.assertTrue(_has_correction_marker(source))
                result, _ = clean(source, target, f"{old}, no")
                self.assertEqual(result.text, target)
                self.assertEqual(result.corrections["applied"], 1)

    def test_metric_length_rule_rejects_untyped_or_unbounded_values(self):
        for old, new in (("7 centimeters", "2 grams"),
                         ("7 widgets", "2 meters"),
                         ("7 centimeters", "2 widgets"),
                         ("7 centimeters of ribbon", "2 meters"),
                         ("7 centimeters", "2 meters remain available"),
                         ("7 centimeters", "2 meters per roll"),
                         ("not 7 centimeters", "2 meters")):
            with self.subTest(old=old, new=new):
                source = f"Use {old}, no {new}."
                accepted, _ = parse_correction_output(f"{old}, no", source, [])
                self.assertFalse(accepted)
        source = "Use 7 centimeters. No 2 meters remain available."
        accepted, _ = parse_correction_output("7 centimeters. No", source, [])
        self.assertFalse(accepted)

    def test_untyped_nominal_replacements_remain_ambiguous(self):
        for verb in ("picked", "selected", "use"):
            source = (f"We {verb} the glass lens, sorry, the pinhole camera, "
                      "before the survey.")
            target = f"We {verb} the pinhole camera, before the survey."
            with self.subTest(verb=verb):
                result, _ = clean(source, target, "the glass lens, sorry")
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_nominal_rule_rejects_clauses_modifiers_and_changed_determiners(self):
        for source, deletion in (
            ("The singer left, sorry, the drummer stayed.", "The singer left, sorry"),
            ("We picked the lens with spots, sorry, the camera.",
             "the lens with spots, sorry"),
            ("We picked the glass lens, sorry, the camera that works.",
             "the glass lens, sorry"),
            ("We picked the glass lens, sorry, a pinhole camera.",
             "the glass lens, sorry"),
            ("We picked the glass lens, sorry, the camera and tripod.",
             "the glass lens, sorry"),
            ("We picked the glass lens, sorry, the camera is ready.",
             "the glass lens, sorry"),
            ("We picked the glass lens, sorry, the camera without spots.",
             "the glass lens, sorry"),
            ("We picked the blue notebook, sorry, the clerk left.",
             "the blue notebook, sorry"),
        ):
            with self.subTest(source=source):
                accepted, _ = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)

    def test_a_new_finite_clause_cannot_replace_an_unrelated_object(self):
        source = "We picked the blue notebook, sorry, the clerk left."
        result, _ = clean(source, "We picked the clerk left.", "the blue notebook, sorry")
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)

    def test_short_preposition_complements_remain_ambiguous(self):
        for deletion in ("by motor uh sorry", "motor uh sorry"):
            source = ("Power the winch by motor uh sorry by pulley handle "
                      "since the battery is empty.")
            target = "Power the winch by pulley handle since the battery is empty."
            with self.subTest(deletion=deletion):
                result, _ = clean(source, target, deletion)
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_repeated_preposition_rejects_changed_frames_and_extra_meaning(self):
        for old, new in (("by motor", "with pulley handle"),
                         ("by motor only", "by pulley handle"),
                         ("by motor", "by pulley handle fails"),
                         ("by motor", "by no pulley handle"),
                         ("by motor", "by pulley handle without rope"),
                         ("by motor and rope", "by pulley handle"),
                         ("by motor", "by pulley handle if ready")):
            with self.subTest(old=old, new=new):
                source = f"Power the winch {old}, sorry {new}."
                accepted, _ = parse_correction_output(f"{old}, sorry", source, [])
                self.assertFalse(accepted)

    def test_omitted_as_frame_remains_ambiguous(self):
        source = "Mark the seal as blue, no amber, and record the shade."
        target = "Mark the seal as amber, and record the shade."
        result, _ = clean(source, target, "blue, no")
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)
        accepted, _ = parse_correction_output("as blue, no", source, [])
        self.assertFalse(accepted)

    def test_ordinary_apologies_and_no_phrases_are_not_value_corrections(self):
        for source, deletion, wrong in (
            ("I wrote to Morgan, sorry to interrupt.", "to Morgan, sorry",
             "I wrote to interrupt."),
            ("This note is for Blair, sorry for interrupting.", "for Blair, sorry",
             "This note is for interrupting."),
            ("The meeting went as planned, no problem.", "planned, no",
             "The meeting went as problem."),
            ("The tool worked as expected, no doubt.", "expected, no",
             "The tool worked as doubt."),
        ):
            with self.subTest(source=source):
                accepted, _ = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                result, _ = clean(source, wrong, deletion)
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_predicative_as_rejects_unbounded_or_ambiguous_replacements(self):
        for source, deletion in (
            ("Mark the seal blue, no amber.", "blue, no"),
            ("Mark the seal as blue, no amber remains.", "blue, no"),
            ("Mark the seal as blue, no dark amber.", "blue, no"),
            ("Mark the seal as blue, no never.", "blue, no"),
            ("Mark the seal as blue. No amber.", "blue. No"),
            ("Mark it as blue, no amber, and mark it as blue, no red.", "blue, no"),
        ):
            with self.subTest(source=source):
                accepted, _ = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)

    def test_new_correction_shapes_keep_source_protection(self):
        for source, deletion, literal in (
            ("Use 7 centimeters, no 2 meters.", "7 centimeters, no", "7 centimeters"),
            ("We picked the lens, sorry, the camera.", "the lens, sorry", "the lens"),
            ("Power it by motor uh sorry by pulley handle.", "motor uh sorry", "by motor"),
            ("Mark it as blue, no amber.", "blue, no", "blue"),
        ):
            with self.subTest(source=source):
                start = source.index(literal)
                accepted, rejected = parse_correction_output(
                    deletion, source, [(start, start + len(literal), "literal")])
                self.assertFalse(accepted)
                self.assertEqual(rejected[0].reason, "protected_span")

    def test_new_shapes_do_not_waive_identifier_time_or_negation_failures(self):
        for source, target, deletion in (
            ("Set port_a to 0.7, no wait, port_b to 0.7.",
             "Set port_a to 0.7.", "port_a to 0.7, no wait"),
            ("Move it from 8:20 to 9:40, actually 10:50.",
             "Move it from 10:50.", "9:40, actually"),
            ("Ship on Friday, no Saturday, and wait not not longer than ten minutes.",
             "Ship on Saturday, and wait not longer than ten minutes.", "Friday, no"),
        ):
            with self.subTest(source=source):
                result, _ = clean(source, target, deletion)
                self.assertEqual(result.text, source)
                self.assertEqual(result.corrections["applied"], 0)

    def test_fused_proposal_resolves_only_to_the_unique_exact_source_span(self):
        source = "Replace the air vent, no wait, the roof panel."
        target = "Replace the roof panel."
        raw = "the airvent, no wait"
        result, _ = clean(source, target, raw)
        self.assertEqual(result.text, target)
        self.assertEqual(result.corrections["applied"], 1)
        proposal = next(o for o in result.observations if o.get("kind") == "corrections")
        self.assertEqual(proposal["output"], raw)
        applied = next(o for o in result.observations
                       if o.get("kind") == "corrections_applied")
        self.assertEqual(applied["proposals"][0]["delete"], "the air vent, no wait")

    def test_fused_proposals_reject_ambiguous_punctuated_and_other_changed_text(self):
        for source, deletion in (
            ("Replace the air vent, no wait, the roof panel; inspect the air vent.",
             "the airvent, no wait"),
            ("Replace the air vent, no wait, the roof panel; record airvent.",
             "the airvent, no wait"),
            ("Replace the air, vent, no wait, the roof panel.", "the airvent, no wait"),
            ("Replace the air vent roof panel, no wait, the fan.",
             "the airvent roofpanel, no wait"),
            ("Replace the air vent, no wait, the roof panel.", "the aerovent, no wait"),
            ("Replace the air vent, no wait, the roof panel.", "a airvent, no wait"),
            ("Replace the air vent, no wait, the roof panel.", "the airvent no wait"),
        ):
            with self.subTest(source=source, deletion=deletion):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertEqual(rejected[0].reason, "offsets_unresolved")

    def test_recovered_proposal_still_checks_protection_evidence_and_word_limit(self):
        source = "Replace the air vent, no wait, the roof panel."
        start = source.index("air vent")
        accepted, rejected = parse_correction_output(
            "the airvent, no wait", source, [(start, start + 8, "literal")])
        self.assertFalse(accepted)
        self.assertEqual(rejected[0].reason, "protected_span")
        for source, deletion, reason in (
            ("The air vent, sorry, we cannot replace it.",
             "The airvent, sorry", "not_parallel"),
            ("Replace the large rear air vent cover, no wait, the fan.",
             "the large rear airvent cover, no wait", "span_too_long"),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertEqual(rejected[0].reason, reason)

    def test_compound_correction_removes_only_the_exact_repeated_predicate(self):
        for predicate, unit in (("should be", "C"), ("must be", "psi"),
                                ("could be", "liters"), ("shall be", "psi")):
            with self.subTest(predicate=predicate, unit=unit):
                subject = "The ink temperature" if unit == "C" else "The reading"
                deletion = f"12 {unit}, I mean actually"
                source = (f"{subject} {predicate} {deletion} "
                          f"it {predicate} 14 {unit}.")
                target = f"{subject} {predicate} 14 {unit}."
                result, inputs = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 1)
                self.assertNotIn(f"{predicate} it {predicate}", inputs[0])
                record = next(o for o in result.observations
                              if o.get("kind") == "corrections_applied")
                start = source.index(deletion)
                end = start + len(deletion)
                self.assertEqual(record["proposals"][0]["span"], [start, end])
                self.assertEqual(record["repeated_restarts"][0]["span"],
                                 [end, end + len(f" it {predicate}")])

    def test_restart_must_repeat_subject_form_modality_and_unit_without_negation(self):
        for before, after in (
            ("The reading should be 12 psi,", "it must be 14 psi."),
            ("The reading should be 12 psi,", "she should be 14 psi."),
            ("The reading should be 12 psi,", "they should be 14 psi."),
            ("The reading should not be 12 psi,", "it should be 14 psi."),
            ("The reading should be 12 psi,", "it should not be 14 psi."),
            ("The reading should be 12 psi,", "it should be 14 bar."),
            ("The reading should be 12 psi.", "it should be 14 psi."),
            ("The reading should be 12 psi;", "it should be 14 psi."),
            ("The reading should be 12 psi,", "it should be checked at 14 psi."),
            ("The reading should be 12 psi,", "it should be 14 psi per hour."),
            ("The reading should be 12 MW,", "it should be 14 mW."),
            ("We should be 12 people,", "it should be 14 people."),
            ("The pressure and temperature should be 12 units,", "it should be 14 units."),
            ("The readings should be 12 psi,", "it should be 14 psi."),
            ("The children should be 12 years,", "it should be 14 years."),
            ("Neither reading should be 12 psi,", "it should be 14 psi."),
            ("These should be 12 psi,", "it should be 14 psi."),
            ("Those should be 12 psi,", "it should be 14 psi."),
            ("Both should be 12 psi,", "it should be 14 psi."),
            ("The readings from the sensor should be 12 psi,", "it should be 14 psi."),
            ("Both sides of the chamber should be 12 psi,", "it should be 14 psi."),
            ("The mice in the chamber should be 12 grams,", "it should be 14 grams."),
        ):
            with self.subTest(before=before, after=after):
                source = f"{before} I mean actually {after}"
                deletion = source[source.index("12"):source.index("actually") + 8]
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)
                result, _ = clean(source, "The reading should be 14 psi.", deletion)
                self.assertEqual(result.text, source)

    def test_restart_cannot_delete_a_protected_pronoun_or_predicate(self):
        source = "The reading should be 12 psi, I mean actually it should be 14 psi."
        start = source.index("it should be")
        result, _ = clean(source, "The reading should be 14 psi.",
                           "12 psi, I mean actually",
                           protected=[(start, start + len("it should be"), "literal")])
        self.assertEqual(result.text, source)
        self.assertEqual(result.corrections["applied"], 0)

    def test_restart_coordinates_survive_an_independent_qualifier_move(self):
        source = ("Use 4 liters of dye, no wait 6 liters. "
                  "The reading should be 12 psi, I mean actually it should be 14 psi.")
        target = "Use 6 liters of dye. The reading should be 14 psi."
        result, _ = clean(source, target,
                           "4 liters of dye, no wait\n12 psi, I mean actually")
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 2)

    def test_restart_is_reapplied_when_split_children_are_validated_together(self):
        first = ("The reading should be 1.25 C, I mean actually it should be 2.5 C, "
                 "and remain stable during the final measurement.")
        second = "Keep the label attached to the container until the review finishes."
        target = "The reading should be 2.5 C, and remain stable during the final measurement."
        calls = 0

        def generate(prompt, max_tokens):
            nonlocal calls
            if "Find the self-corrections" in prompt:
                return {"text": "1.25 C, I mean actually", "output_tokens": 8,
                        "limit_hit": False}
            calls += 1
            if calls == 1:
                return {"text": "The", "output_tokens": 1, "limit_hit": True}
            body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
            text = json.loads(body)["transcript"]
            return {"text": target if "2.5 C" in text else text,
                    "output_tokens": 15, "limit_hit": False}

        result = CleanupEngine(generate, model_id="fixture").clean(first + " " + second)
        self.assertEqual(result.text, target + " " + second)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 1)
        assembly = [o for o in result.observations if o.get("stage") == "retry_assembly"]
        self.assertEqual(len(assembly), 1)
        self.assertTrue(assembly[0]["accepted"])

    def test_restored_conjunction_keeps_its_original_attachment(self):
        source = ("Bring the bottle of water and I want the blue notebook from "
                  "the drawer before we leave for the afternoon meeting.")
        proposal = source.replace("water and I", "water. I")
        result, _ = clean(source, proposal, "NONE")
        self.assertEqual(result.text, source)
        self.assertEqual(result.path, "llm")
        decision = next(o for o in result.observations
                        if o.get("kind") == "cleanup_decision")
        self.assertEqual(decision["salvaged_words"], 1)
        self.assertTrue(decision["restriction_punctuation_restored"])

    def test_combined_repairs_do_not_accept_changed_numbers(self):
        source = ("Bring 2 bottles of water and I want the blue notebook from "
                  "the drawer before we leave for the afternoon meeting.")
        proposal = source.replace("water and I", "water. I").replace("2", "3")
        result, _ = clean(source, proposal, "NONE")
        self.assertEqual(result.text, source)
        self.assertNotEqual(result.path, "llm")

    def test_repeated_preposition_belongs_to_the_corrected_value(self):
        for source, deletion, target in (
            ("Send it by noon, no wait by 11 a.m.", "noon, no wait",
             "Send it by 11 a.m."),
            ("Send it to Mira, no wait to Lin.", "Mira, no wait",
             "Send it to Lin."),
            ("Move it from Monday, actually from Tuesday.", "Monday, actually",
             "Move it from Tuesday."),
            ("Meet at 4, sorry at 5.", "4, sorry", "Meet at 5."),
        ):
            with self.subTest(source=source):
                result, inputs = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertNotIn("by by", inputs[0])

    def test_repeated_frame_does_not_expand_across_a_clause_or_protection(self):
        source = "Send it to Mira, no wait to Lin."
        start = source.index("to Mira")
        accepted, rejected = parse_correction_output(
            "Mira, no wait", source, [(start, start + 2, "literal")])
        self.assertFalse(accepted)
        self.assertEqual(rejected[0].reason, "protected_span")
        source = "Send it to Mira and notify Sam, actually to Lin."
        accepted, _ = parse_correction_output(
            "Mira and notify Sam, actually", source, [])
        self.assertFalse(accepted)

    def test_unique_fused_pair_restores_exact_source_words(self):
        source = "Inspect the pallet fork and record the result."
        result, _ = clean(source, source.replace("pallet fork", "palletfork"), "NONE")
        self.assertEqual(result.text, source)
        self.assertEqual(result.path, "llm")
        decision = next(o for o in result.observations
                        if o.get("kind") == "cleanup_decision")
        self.assertTrue(decision["source_word_boundary_restored"])

    def test_word_split_never_licenses_other_novel_content(self):
        source = "Inspect the pallet fork and record the result."
        proposal = "Inspect the palletfork and record the successful result."
        result, _ = clean(source, proposal, "NONE")
        self.assertEqual(result.text, source)
        self.assertNotEqual(result.path, "llm")

    def test_ambiguous_repeated_or_punctuated_source_pair_stays_rejected(self):
        for source, proposal in (
            ("Inspect the pallet fork and then inspect the pallet fork again.",
             "Inspect the palletfork and then inspect the pallet fork again."),
            ("Inspect the pallet, fork and spring.", "Inspect the palletfork and spring."),
            ("Inspect the palletfork and the pallet fork.", "Inspect the palletfork and the palletfork."),
        ):
            with self.subTest(source=source):
                result, _ = clean(source, proposal, "NONE")
                self.assertEqual(result.text, source)
                self.assertNotEqual(result.path, "llm")


if __name__ == "__main__":
    unittest.main()
