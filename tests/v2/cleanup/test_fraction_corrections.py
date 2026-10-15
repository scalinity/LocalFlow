"""Fraction-head corrections retain their unit and surrounding details."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.correction_retention import correction_view, qualifier_retention
from localflow.v2.cleanup.lexicon import neighbourhood
from localflow.v2.cleanup.engine import (CleanupEngine, correction_marker_start,
                                        parse_correction_output)
from localflow.v2.cleanup.validation import validate


def clean(source, target, deletion, protected=()):
    def generate(prompt, max_tokens):
        return {"text": deletion if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(
        source, protected_spans=list(protected))


class FractionCorrectionTests(unittest.TestCase):
    def test_explicit_fraction_heads_need_no_qualifier_move(self):
        for prefix, old, new, suffix, marker in (
            ("Advance the rotor by ", "7 quarters of a turn", "1 half turn", ".", "sorry"),
            ("Pause for ", "3 halves of an hour", "1 quarter hour", ".", "sorry"),
            ("Trim the strip by ", "1 half of a centimeter", "1 quarter centimeter",
             ".", "sorry"),
            ("Mix ", "5 quarters of a litre", "1 half litre", ", with resin.", "sorry"),
            ("Give the technician ", "7 halves of a liter", "1 quarter liter", ".", "sorry"),
            ("The adjustment is ", "1 quarter of a rotation", "1 half rotation", ".", "actually"),
        ):
            with self.subTest(old=old, new=new):
                deletion = f"{old}, {marker}"
                source = f"{prefix}{deletion} {new}{suffix}"
                target = f"{prefix}{new}{suffix}"
                span = (len(prefix), len(prefix) + len(deletion))
                ms = correction_marker_start(source, span)
                self.assertEqual(qualifier_retention(neighbourhood(source, span, ms)), (None, None))
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual([(c.span, c.delete) for c in accepted], [(span, deletion)])
                self.assertFalse(rejected)
                self.assertEqual(correction_view(source, accepted)[:2],
                                 (source, [(*span, ms)]))
                result = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 1)
                record = next(o for o in result.observations
                              if o.get("kind") == "corrections_applied")
                self.assertEqual(record["proposals"][0]["span"], list(span))
                self.assertNotIn("retained_qualifiers", record)

    def test_known_measurement_units_keep_their_exact_spelling(self):
        for unit in ("turn", "rotation", "revolution", "hour", "week", "foot", "inch",
                     "megabyte", "bit", "pixel", "kilogram", "liter", "litre",
                     "nanometer", "micrometre", "millimeter", "kilometre", "Meter"):
            with self.subTest(unit=unit):
                deletion = f"2 quarters of a {unit}, sorry"
                source = f"The adjustment is {deletion} 1 half {unit}."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)

    def test_count_denominator_agreement_is_required(self):
        for numerator, denominator in (("1", "halves"), ("1", "quarters"),
                                       ("2", "half"), ("2", "quarter"),
                                       ("0", "quarters"), ("01", "quarter"),
                                       ("-2", "quarters"), ("+2", "quarters"),
                                       ("2.5", "quarters"), ("2", "thirds")):
            with self.subTest(numerator=numerator, denominator=denominator):
                deletion = f"{numerator} {denominator} of a turn, sorry"
                source = f"The adjustment is {deletion} 1 half turn."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)

    def test_arbitrary_nouns_and_different_units_remain_unsupported(self):
        for old, new in (
            ("2 quarters of a turn", "1 half meter"),
            ("2 quarters of a liter", "1 half milliliter"),
            ("2 quarters of a turn", "1 half revolution"),
            ("2 quarters of a Meter", "1 half meter"),
            ("2 quarters of a brother", "1 half brother"),
            ("2 quarters of a horse", "1 quarter horse"),
            ("2 bottles of a resin", "1 half resin"),
            ("2 cases of an issue", "1 half issue"),
            ("2 quarters of a turn", "1 half turn signal"),
            ("2 quarters of a turn", "1 half turn-like"),
            ("2 quarters of a turn", "1 half turn from zero"),
            ("2 quarters of a turn", "1 half"),
            ("2 quarters of the turn", "1 half turn"),
            ("2 quarters of each turn", "1 half turn"),
            ("2 quarters of a turn", "2 half turns"),
            ("2 quarters of a turn", "1 half of a turn"),
            ("2 quarters of a turn", "to request 1 half turn"),
        ):
            with self.subTest(old=old, new=new):
                deletion = f"{old}, sorry"
                source = f"The adjustment is {deletion} {new}."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)

    def test_numerator_must_start_a_complete_source_token(self):
        deletion = "9 quarters of a turn, sorry"
        for attached in ("-", "+", "−", "2.", "2,", "2/", ".", ",", "/",
                         "item", "item_", "2e", "$", "€", "£", "("):
            with self.subTest(attached=attached):
                source = f"Advance {attached}{deletion} 1 half turn."
                start = source.index(deletion)
                span = (start, start + len(deletion))
                ms = correction_marker_start(source, span)
                self.assertIsNotNone(qualifier_retention(neighbourhood(source, span, ms))[1])
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)
                result = clean(source, "Advance 1 half turn.", deletion)
                self.assertEqual(result.text, source)
        for prefix in ("", "Advance ", "Advance:\n", "Advance\t"):
            with self.subTest(prefix=prefix):
                source = f"{prefix}{deletion} 1 half turn."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)

    def test_explicit_markers_keep_their_existing_admission_rules(self):
        for marker in ("sorry", "actually", "scratch", "digo"):
            with self.subTest(marker=marker):
                deletion = f"2 quarters of a rotation, {marker}"
                source = f"Move {deletion} 1 half rotation."
                target = "Move 1 half rotation."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)
                self.assertEqual(clean(source, target, deletion).text, target)
        for replacement in ("1 half rotation.", "1 half rotation should occur.",
                            "1 half rotation of the shaft should occur."):
            with self.subTest(replacement=replacement):
                deletion = "2 quarters of a rotation, no"
                source = f"Allow {deletion} {replacement}"
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)
                self.assertEqual(clean(source, f"Allow {replacement}", deletion).text, source)

    def test_direct_word_tails_and_separate_predicates_remain_unsupported(self):
        for marker in ("sorry", "actually", "scratch", "digo", "no"):
            for tail in ("of resin.", "of resin was wasted.", "of resin should leak.",
                         "was wasted.", "for the technician.", "and keep the lid."):
                with self.subTest(marker=marker, tail=tail):
                    deletion = f"2 quarters of a liter, {marker}"
                    source = f"We used {deletion} 1 half liter {tail}"
                    candidate = f"We used 1 half liter {tail}"
                    accepted, rejected = parse_correction_output(deletion, source, [])
                    self.assertFalse(accepted)
                    self.assertTrue(rejected)
                    self.assertEqual(clean(source, candidate, deletion).text, source)

    def test_a_fully_bound_fraction_may_take_a_longer_marker(self):
        for source, deletion, target in (
            ("Pause for 3 halves of an hour, no wait, 1 quarter hour.",
             "3 halves of an hour, no wait", "Pause for 1 quarter hour."),
            ("Advance 7 quarters of a turn, I mean actually 1 half turn.",
             "7 quarters of a turn, I mean actually", "Advance 1 half turn."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(rejected, [])
                self.assertEqual([c.delete for c in accepted], [deletion])
                self.assertEqual(clean(source, target, deletion).text, target)
        # Over the ordinary cap, anything the fraction parse does not fully
        # bind stays too long: a two-word unit, a changed replacement head,
        # or a replacement that continues into a clause.
        for source, deletion in (
            ("Cover 3 quarters of a square meter, sorry, 1 half square meter.",
             "3 quarters of a square meter, sorry"),
            ("Advance 7 quarters of a turn, no wait, 2 half turns.",
             "7 quarters of a turn, no wait"),
            ("Advance 7 quarters of a turn, no wait, 1 half turn and lock it.",
             "7 quarters of a turn, no wait"),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["span_too_long"])

    def test_old_details_do_not_fit_by_expanding_the_span_limit(self):
        for old in ("2 quarters of a clockwise turn", "2 quarters of a liter of resin",
                    "2 quarters of a liter to the technician"):
            with self.subTest(old=old):
                deletion = f"{old}, sorry"
                source = f"Use {deletion} 1 half liter."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertEqual(rejected[0].reason, "span_too_long")

    def test_quotes_and_code_touching_the_correction_disable_the_exception(self):
        deletion = "2 quarters of a turn, sorry"
        for left, right in (("\"", "\""), ("‘", "’"), ("“", "”"), ("'", "'"), ("`", "`")):
            for source in (f"Copy {left}advance {deletion} 1 half turn before Monday{right} exactly.",
                           f"Note {left}first{right} and {left}advance {deletion} 1 half turn."):
                with self.subTest(source=source):
                    accepted, rejected = parse_correction_output(deletion, source, [])
                    self.assertFalse(accepted)
                    self.assertEqual([r.reason for r in rejected],
                                     ["unresolved_quantity_qualifier"])

    def test_contractions_and_distant_quotes_leave_the_exception_active(self):
        # Contractions are ordinary in dictation; only a quotation or code
        # span at the correction itself makes the rule abstain.
        deletion = "2 quarters of a turn, sorry"
        filler = ("It's a short run, so don't rush the housing. We can't skip "
                  "the log and it isn't optional for the 'night' shift. ") * 4
        for source in (f"{filler}Advance {deletion} 1 half turn. {filler}".strip(),
                       f"Don’t forget the cover. Advance {deletion} 1 half turn.",
                       f"Say \"ready\" first. Advance {deletion} 1 half turn. Use `fast` mode."):
            with self.subTest(source=source[-60:]):
                self.assertLessEqual(len(source.split()), 200)
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted, rejected)
                target = source.replace(f"{deletion} ", "")
                result = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_fraction_shape_does_not_propose_its_own_correction(self):
        source = "Advance 2 quarters of a turn and 1 half turn."
        accepted, rejected = parse_correction_output("2 quarters of a turn", source, [])
        self.assertFalse(accepted)
        self.assertEqual(rejected[0].reason, "no_marker_ending")

    def test_tilde_fences_disable_the_exception_but_single_tildes_do_not(self):
        deletion = "2 quarters of a rotation, sorry"
        for opening, closing in (("~~~\n", "\n~~~"),
                                 ("  ~~~~text\n", "\n  ~~~~"),
                                 ("\t~~~text\n", "\n\t~~~"),
                                 ("~~~\n", "")):
            with self.subTest(opening=opening, closing=closing):
                preface = "Record:\n" if opening[0] in " \t" else ""
                source = f"{preface}{opening}Move {deletion} 1 half rotation.{closing}"
                candidate = f"{preface}{opening}Move 1 half rotation.{closing}"
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)
                self.assertEqual(clean(source, candidate, deletion).text, source)
        for prefix in ("~ ", "~\n", "~~ ", "~~\n"):
            with self.subTest(prefix=prefix):
                source = f"{prefix}{deletion} 1 half rotation."
                target = f"{prefix}1 half rotation."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)
                self.assertEqual(clean(source, target, deletion).text, target)

    def test_triple_tilde_presence_abstains_inside_containers_and_inline(self):
        deletion = "2 quarters of a rotation, sorry"
        for opening, closing in (("> ~~~\n> ", "\n> ~~~"),
                                 (">> ~~~~text\n>> ", "\n>> ~~~~"),
                                 ("- ~~~\n  ", ""),
                                 ("1. ~~~\n   ", ""),
                                 ("> - ~~~\n>   ", ""),
                                 ("- > ~~~\n  > ", ""),
                                 ("Mark ~~~: ", "")):
            with self.subTest(opening=opening, closing=closing):
                source = f"{opening}Move {deletion} 1 half rotation.{closing}"
                candidate = f"{opening}Move 1 half rotation.{closing}"
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertFalse(accepted)
                self.assertTrue(rejected)
                result = clean(source, candidate, deletion)
                self.assertEqual(result.corrections["applied"], 0)
                self.assertIn(deletion, result.text)
                self.assertNotEqual(result.text, candidate)

    def test_protected_fraction_heads_remain_unchanged(self):
        deletion = "2 quarters of a turn, sorry"
        source = f"Advance {deletion} 1 half turn."
        start = source.index(deletion)
        protected = [(start, start + len(deletion), "literal")]
        accepted, rejected = parse_correction_output(deletion, source, protected)
        self.assertFalse(accepted)
        self.assertEqual(rejected[0].reason, "protected_span")
        self.assertEqual(clean(source, "Advance 1 half turn.", deletion, protected).text, source)

    def test_protected_replacement_still_requires_its_exact_text(self):
        deletion = "2 quarters of a turn, sorry"
        source = f"Advance {deletion} 1 half turn."
        start = source.index("1 half turn")
        protected = [(start, start + len("1 half turn"), "literal")]
        accepted, rejected = parse_correction_output(deletion, source, protected)
        self.assertTrue(accepted)
        self.assertFalse(rejected)
        target = "Advance 1 half turn."
        self.assertEqual(clean(source, target, deletion, protected).text, target)
        result = clean(source, "Advance 1 turn.", deletion, protected)
        self.assertIn("1 half turn", result.text)
        self.assertNotEqual(result.text, "Advance 1 turn.")

    def test_replacement_and_surrounding_words_remain_required(self):
        for prefix, suffix, damaged in (
            ("Give the technician ", ".", "Give 1 half liter."),
            ("Mix ", ", with resin.", "Mix 1 half liter."),
            ("Do not use ", ".", "Do use 1 half liter."),
            ("Use ", ".", "Use 1 half meter."),
            ("Use ", ".", "Use 1 liter."),
            ("Use ", ".", "Use 1 half liter and 2 quarters."),
        ):
            with self.subTest(prefix=prefix, suffix=suffix, damaged=damaged):
                deletion = "2 quarters of a liter, sorry"
                source = f"{prefix}{deletion} 1 half liter{suffix}"
                target = f"{prefix}1 half liter{suffix}"
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)
                view, spans, _ = correction_view(source, accepted)
                self.assertTrue(validate(view, target, correction_spans=spans).accepted)
                self.assertFalse(validate(view, damaged, correction_spans=spans).accepted)
                self.assertNotEqual(clean(source, damaged, deletion).text, damaged)

    def test_original_offsets_survive_unicode_and_an_independent_move(self):
        source = ("Mark the µ sample. Use 2 liters of resin, no wait 4 liters. "
                  "Advance 2 quarters of a turn, sorry 1 half turn.")
        target = "Mark the µ sample. Use 4 liters of resin. Advance 1 half turn."
        deletion = "2 quarters of a turn, sorry"
        result = clean(source, target, "2 liters of resin, no wait\n" + deletion)
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 2)
        record = next(o for o in result.observations
                      if o.get("kind") == "corrections_applied")
        self.assertEqual(record["proposals"][1]["span"],
                         [source.index(deletion), source.index(deletion) + len(deletion)])
        self.assertEqual(len(record["retained_qualifiers"]), 1)


if __name__ == "__main__":
    unittest.main()
