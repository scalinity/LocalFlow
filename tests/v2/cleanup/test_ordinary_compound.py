"""Ordinary compound corrections do not authorize repeated predicates."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.correction_retention import correction_view, repeated_restart
from localflow.v2.cleanup.engine import (CleanupEngine, correction_marker_start,
                                        parse_correction_output)
from localflow.v2.cleanup.validation import validate


def clean(source, target, deletion):
    def generate(prompt, max_tokens):
        return {"text": deletion if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


class OrdinaryCompoundTests(unittest.TestCase):
    def test_plain_replacements_keep_original_spans_without_an_extra_restart(self):
        for prefix, old, new, suffix in (
            ("Set the relay threshold to ", "7 volts", "9 volts", "."),
            ("The meter reading should be ", "7 volts", "9 volts", "."),
            ("The meter reading should not be ", "7 volts", "9 volts", "."),
            ("The meter reading should be ", "7 volts", "9 amps", "."),
            ("Review the sketch on ", "Monday", "Thursday", "."),
            ("Review the sketch in ", "March", "May", "."),
            ("Send the sketch to ", "Juniper", "Rowan", "."),
            ("Send the sketch to ", "Juniper", "Will", "."),
            ("Send the sketch to ", "Juniper", "May", "."),
            ("Load ", "draft_a.toml", "draft_b.toml", "."),
            ("Review the sketch at ", "4:15", "5:45", "."),
            ("Use ", "draft", "final version", "."),
            ("Use ", "draft", "the final version", "."),
            ("The meter reading should be ", "7 volts", "9 volts",
             ", and it should remain steady during the reading."),
        ):
            with self.subTest(old=old, new=new, prefix=prefix, suffix=suffix):
                deletion = f"{old}, I mean actually"
                source = f"{prefix}{deletion} {new}{suffix}"
                target = f"{prefix}{new}{suffix}"
                span = (len(prefix), len(prefix) + len(deletion))
                marker = correction_marker_start(source, span)
                self.assertEqual(repeated_restart(source, span, marker), (None, None))
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual([(c.span, c.delete) for c in accepted], [(span, deletion)])
                self.assertFalse(rejected)
                self.assertEqual(correction_view(source, accepted)[:2],
                                 (source, [(*span, marker)]))
                result = clean(source, target, deletion)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.corrections["applied"], 1)
                record = next(o for o in result.observations
                              if o.get("kind") == "corrections_applied")
                self.assertEqual(record["proposals"][0]["span"], list(span))
                self.assertNotIn("repeated_restarts", record)

    def test_ordinary_admission_checks_still_reject_invalid_proposals(self):
        for source, deletion, reason in (
            ("Use draft, I mean actually.", "draft, I mean actually", "no_replacement"),
            ("Use draft, I mean actually her.", "draft, I mean actually", "no_replacement"),
            ("Schedule sketch Monday, I mean actually Thursday.",
             "sketch Monday, I mean actually", "overbroad_calendar_value"),
            ("Schedule sketch March, I mean actually May.",
             "sketch March, I mean actually", "overbroad_calendar_value"),
            ("Use draft. I mean actually final.",
             "draft. I mean actually", "crosses_sentence"),
            ("Use the old large blue draft, I mean actually final.",
             "the old large blue draft, I mean actually", "span_too_long"),
            ("Use draft, I mean actually final. Use draft, I mean actually final.",
             "draft, I mean actually", "ambiguous_occurrence"),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], [reason])

    def test_pronouns_and_named_predicates_are_not_plain_replacements(self):
        for replacement in (
            "she should be 9 volts", "they should be 9 volts",
            "he should be 9 volts", "we should be 9 volts",
            "you should be 9 volts", "I should be 9 volts",
            "this should be 9 volts", "that should be 9 volts",
            "these should be 9 volts", "those should be 9 volts",
            "it's 9 volts", "she’s 9 volts", "they'd be 9 volts",
            "Rowan should be 9 volts", "the other reading should be 9 volts",
            "Rowan is 9 volts", "the other reading was 9 volts",
            "Casey May", "She", "It", "that", "this",
        ):
            with self.subTest(replacement=replacement):
                deletion = "7 volts, I mean actually"
                source = f"The meter should be {deletion} {replacement}."
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["unresolved_repeated_restart"])
                result = clean(source, "The meter should be 9 volts.", deletion)
                self.assertEqual(result.text, source)

    def test_ordinary_corrections_do_not_authorize_other_source_words(self):
        for source, deletion, target, damaged in (
            ("The meter should not be 7 volts, I mean actually 9 volts.",
             "7 volts, I mean actually", "The meter should not be 9 volts.",
             "The meter should be 9 volts."),
            ("The meter should be 7 volts, I mean actually 9 amps.",
             "7 volts, I mean actually", "The meter should be 9 amps.",
             "The meter should be 9 volts."),
            ("Give the technician 3 liters, I mean actually 5 liters of resin.",
             "3 liters, I mean actually", "Give the technician 5 liters of resin.",
             "Give 5 liters of resin."),
            ("The meter should be 7 volts, I mean actually 9 volts, and it should remain steady.",
             "7 volts, I mean actually", "The meter should be 9 volts, and it should remain steady.",
             "The meter should be 9 volts, and remain steady."),
            ("The meter should be 7 volts, I mean actually Rowan needs 9 volts.",
             "7 volts, I mean actually", "The meter should be Rowan needs 9 volts.",
             "The meter should be 9 volts."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted)
                self.assertFalse(rejected)
                view, spans, _ = correction_view(source, accepted)
                self.assertTrue(validate(view, target, correction_spans=spans).accepted)
                # The admitted correction never covers the words the damage drops.
                report = validate(view, damaged, correction_spans=spans)
                self.assertIn("coverage", [c.name for c in report.critical_failures])

    def test_protected_original_span_stays_rejected(self):
        deletion = "draft_a.toml, I mean actually"
        source = f"Load {deletion} draft_b.toml."
        start = source.index("draft_a.toml")
        accepted, rejected = parse_correction_output(
            deletion, source, [(start, start + len("draft_a.toml"), "literal")])
        self.assertEqual(accepted, [])
        self.assertEqual([r.reason for r in rejected], ["protected_span"])

    def test_original_coordinates_survive_unicode_and_a_qualifier_move(self):
        source = ("Label the µ sample. Use 3 liters of resin, no wait 5 liters. "
                  "The meter should be 7 volts, I mean actually 9 volts.")
        target = ("Label the µ sample. Use 5 liters of resin. "
                  "The meter should be 9 volts.")
        deletion = "7 volts, I mean actually"
        result = clean(source, target, "3 liters of resin, no wait\n" + deletion)
        self.assertEqual(result.text, target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 2)
        record = next(o for o in result.observations
                      if o.get("kind") == "corrections_applied")
        self.assertEqual(record["proposals"][1]["span"],
                         [source.index(deletion), source.index(deletion) + len(deletion)])
        self.assertNotIn("repeated_restarts", record)

    def test_split_retry_reuses_ordinary_and_exact_restart_permissions(self):
        first = ("The meter should be 7 volts, I mean actually 9 volts, "
                 "and remain steady during the final reading.")
        second = "The dial should be 2 amps, I mean actually it should be 4 amps."
        first_target = ("The meter should be 9 volts, "
                        "and remain steady during the final reading.")
        second_target = "The dial should be 4 amps."
        calls = 0

        def generate(prompt, max_tokens):
            nonlocal calls
            if "Find the self-corrections" in prompt:
                deletions = [d for d in ("7 volts, I mean actually", "2 amps, I mean actually")
                             if d in prompt]
                return {"text": "\n".join(deletions) or "NONE", "output_tokens": 10,
                        "limit_hit": False}
            calls += 1
            if calls == 1:
                return {"text": "The", "output_tokens": 1, "limit_hit": True}
            body = prompt.rsplit("<|user|>\n", 1)[1].rsplit("<|assistant|>", 1)[0]
            text = json.loads(body)["transcript"]
            return {"text": first_target if "9 volts" in text else second_target,
                    "output_tokens": 20, "limit_hit": False}

        result = CleanupEngine(generate, model_id="fixture").clean(first + " " + second)
        self.assertEqual(result.text, first_target + " " + second_target)
        self.assertEqual(result.path, "llm")
        self.assertEqual(result.corrections["applied"], 2)
        assembly = [o for o in result.observations if o.get("stage") == "retry_assembly"]
        self.assertEqual(len(assembly), 1)
        self.assertTrue(assembly[0]["accepted"])


if __name__ == "__main__":
    unittest.main()
