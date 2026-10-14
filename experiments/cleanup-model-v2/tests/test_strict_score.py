"""Independent edit checks retain permissive legacy scores as separate history."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.strict_score import aggregate, score_case


def case(source, target=None, **metadata):
    return {"case_id": "one", "model_input": source,
            "target": source if target is None else target, **metadata}


class StrictScoreTests(unittest.TestCase):
    def test_preposition_substitution_is_an_added_and_missing_word(self):
        source = "Send the file to Mina after the planning meeting tomorrow morning."
        result = score_case(case(source), source.replace("to Mina", "from Mina"))
        self.assertEqual(result["unsupported_additions"], [{"token": "from", "count": 1}])
        self.assertEqual(result["introduced_required_omissions"], [{"token": "to", "count": 1}])
        self.assertTrue(result["introduced_edit_flag"])

    def test_identifier_case_and_count_are_exact(self):
        source = "Call getID and preserve the result until tomorrow morning."
        result = score_case(case(source), source.replace("getID", "getId"))
        self.assertTrue(result["introduced_edit_flag"])
        self.assertEqual({x["identifier"] for x in result["identifier_count_changes"]}, {"getID", "getId"})
        repeated = score_case(case(source), source + " Call getID.")
        self.assertEqual(next(x for x in repeated["identifier_count_changes"]
                              if x["identifier"] == "getID")["output_count"], 2)
        annotated = case("Call scan tomorrow.", critical_facts=[{"text": "scan", "kind": "identifier"}])
        self.assertTrue(score_case(annotated, "Call SCAN tomorrow.")["identifier_count_changes"])

    def test_noun_well_is_not_an_optional_interjector(self):
        source = "Inspect the well before the planning meeting tomorrow morning."
        result = score_case(case(source), source.replace("the well", "the"))
        self.assertEqual(result["introduced_required_omissions"], [{"token": "well", "count": 1}])

    def test_valid_correction_and_unchanged_fallback_are_distinct(self):
        source = "Use gain_v2, no wait gain_v3 tomorrow."
        target = "Use gain_v3 tomorrow."
        item = case(source, target, gold_lines=["gain_v2, no wait"], obsolete_values=["gain_v2"])
        repaired = score_case(item, target)
        self.assertFalse(repaired["introduced_edit_flag"])
        self.assertEqual(repaired["unresolved_corrections"], [])
        fallback = score_case(item, source)
        self.assertFalse(fallback["introduced_edit_flag"])
        self.assertTrue(fallback["unresolved_corrections"])
        self.assertFalse(fallback["reference_exact"])

    def test_retained_qualifier_overrides_overbroad_correction_metadata(self):
        source = "Remove 0.4 millimeters of polish, no wait 0.2 millimeters."
        target = "Remove 0.2 millimeters of polish."
        item = case(source, target, gold_lines=["0.4 millimeters of polish, no wait"])
        result = score_case(item, "Remove 0.2 millimeters.")
        self.assertEqual(result["introduced_required_omissions"],
                         [{"token": "of", "count": 1}, {"token": "polish", "count": 1}])

    def test_fillers_and_function_word_stutters_have_narrow_controls(self):
        source = "Um send the the file tomorrow morning."
        target = "Send the file tomorrow morning."
        self.assertFalse(score_case(case(source, target), target)["introduced_edit_flag"])
        quoted = 'Keep "um" in the transcript tomorrow morning.'
        self.assertTrue(score_case(case(quoted), quoted.replace('"um"', '""'))["introduced_edit_flag"])
        repeated = "We. We need the file tomorrow morning."
        self.assertTrue(score_case(case(repeated), "We need the file tomorrow morning.")["introduced_edit_flag"])

    def test_spoken_list_does_not_invent_numeric_words(self):
        source = "First buy milk second buy bread."
        target = "1. Buy milk.\n2. Buy bread."
        result = score_case(case(source, target, category="formatting"), target)
        self.assertFalse(result["introduced_edit_flag"])
        self.assertEqual(result["metadata_issues"], [])
        wrong = score_case(case(source, target, category="formatting"), "1. Buy 10 milk.\n2. Buy bread.")
        self.assertEqual(wrong["unsupported_additions"], [{"token": "10", "count": 1}])

    def test_numeric_formatting_preserves_values(self):
        source = "Use twenty five samples at 3.50 percent tomorrow."
        target = "Use 25 samples at 3.5% tomorrow."
        result = score_case(case(source, target), target)
        self.assertFalse(result["introduced_edit_flag"])
        self.assertEqual(result["metadata_issues"], [])
        self.assertTrue(score_case(case(source, target), target.replace("25", "26"))["introduced_edit_flag"])
        fractional = case("Use -.5 grams tomorrow.", "Use -0.50 grams tomorrow.")
        self.assertFalse(score_case(fractional, fractional["target"])["introduced_edit_flag"])
        self.assertTrue(score_case(fractional, "Use -5 grams tomorrow.")["introduced_edit_flag"])

    def test_vocabulary_requires_a_full_paired_substitution(self):
        source = "Use tensor flow for the report tomorrow."
        target = "Use TensorFlow for the report tomorrow."
        item = case(source, target, vocabulary_pairs=[["tensor flow", "TensorFlow"]])
        result = score_case(item, target)
        self.assertFalse(result["introduced_edit_flag"])
        self.assertEqual(result["metadata_issues"], [])
        unchanged = score_case(item, source)
        self.assertFalse(unchanged["introduced_edit_flag"])
        self.assertEqual(unchanged["metadata_issues"], [])
        self.assertTrue(score_case(item, source + " TensorFlow.")["introduced_edit_flag"])
        self.assertTrue(score_case(item, "Use for the report tomorrow.")["introduced_edit_flag"])
        overlapping = case("Use alias tomorrow.", "Use CanonicalName ExtraName tomorrow.",
                           vocabulary_pairs=[["alias", "CanonicalName"], ["alias", "ExtraName"]])
        result = score_case(overlapping, overlapping["target"])
        self.assertIn("empty_or_overlapping_vocabulary_alias", result["metadata_issues"])
        self.assertTrue(result["unsupported_additions"])

    def test_critical_fact_missing_only_from_target_is_not_new_damage(self):
        item = case("Use the blue unit.", "Use the blue unit at noon.",
                    critical_facts=[{"text": "at noon", "kind": "other"}])
        result = score_case(item, item["model_input"])
        self.assertEqual(result["missing_critical_facts"], ["at noon"])
        self.assertEqual(result["introduced_missing_critical_facts"], [])
        self.assertFalse(result["introduced_edit_flag"])

    def test_period_after_path_is_punctuation_not_identifier_mutation(self):
        source = "Read logs/run.log"
        self.assertFalse(score_case(case(source, source + "."), source + ".")["introduced_edit_flag"])

    def test_reference_only_word_is_incomplete_not_introduced_omission(self):
        source = "Send file tomorrow."
        result = score_case(case(source, "Send the file tomorrow."), source)
        self.assertFalse(result["introduced_edit_flag"])
        self.assertEqual(result["missing_target_words"], [{"token": "the", "count": 1}])
        self.assertIn("target_adds_words_without_checked_authorization", result["metadata_issues"])

    def test_underannotated_target_deletion_is_explicitly_unclassified(self):
        source = "Use PLN:4412, I mean PLN:4421 tomorrow."
        target = "Use PLN:4421 tomorrow."
        result = score_case(case(source, target), target)
        self.assertFalse(result["introduced_edit_flag"])
        self.assertTrue(result["unclassified_source_omissions"])
        self.assertIn("target_omits_words_without_checked_authorization", result["metadata_issues"])
        self.assertIn("source_omission_authorization_underdetermined", result["review_flags"])

    def test_bad_offsets_and_missing_reference_remain_explicit(self):
        source = "Keep the original file tomorrow."
        result = score_case(case(source, gold_offsets=[[0, 1000]]), source)
        self.assertIn("invalid_correction_offset", result["metadata_issues"])
        self.assertFalse(result["introduced_edit_flag"])
        unreferenced = score_case({"case_id": "audio", "model_input": source}, source)
        self.assertIsNone(unreferenced["missing_target_words"])
        self.assertIn("no_cleanup_target_reference", unreferenced["review_flags"])

    def test_missing_output_is_unavailable_never_an_observed_damage_or_pass(self):
        result = score_case(case("Keep the file."), None)
        self.assertFalse(result["available"])
        self.assertIsNone(result["introduced_edit_flag"])
        self.assertEqual(result["semantic_assessment"], "NOT_ASSESSED")

    def test_aggregate_rejects_missing_duplicate_or_extra_cases(self):
        cases = [case("Keep the file.")]
        row = {"case_id": "one", "delivered": "Keep the file."}
        for rows in ([], [row, row], [{**row, "case_id": "extra"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                aggregate(cases, rows)
        result = aggregate(cases, [row])
        self.assertEqual(result["available"], 1)
        self.assertEqual(result["counts"]["introduced_edit_flag"], 0)


if __name__ == "__main__":
    unittest.main()
