"""Authored controls for independently scored incomplete-opening deletions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2.strict_score import SCORER_VERSION, aggregate, score_case


SOURCE = "The result that we that we should publish is negative."
CLEAN = "The result that we should publish is negative."
SECOND = "Keep the version which they which they will release tomorrow."
SECOND_CLEAN = "Keep the version which they will release tomorrow."
ABSENT = object()


def example(source=SOURCE, target=ABSENT, **metadata):
    result = {"case_id": "authored-restart", "model_input": source, **metadata}
    if target is not ABSENT:
        result["target"] = target
    return result


# The 27 authored design controls have no experiment or held-out inputs.
DESIGN_CONTROLS = (
    ("P01", SOURCE, CLEAN, True, None),
    ("P02", SECOND, SECOND_CLEAN, True, None),
    ("P03", "The colleague whom I whom I had contacted replied.",
     "The colleague whom I had contacted replied.", True, None),
    ("P04", "Use the entries that she\tthat she has checked already.",
     "Use the entries that she has checked already.", True, None),
    ("N01", "She had had lunch before the lecture began.", "She had lunch before the lecture began.", False, None),
    ("N02", "We can can peaches in the kitchen today.", "We can peaches in the kitchen today.", False, None),
    ("N03", "We know we know the answer.", "We know the answer.", False, None),
    ("N04", "The result was very very important.", "The result was very important.", False, None),
    ("N05", "This is not not allowed.", "This is not allowed.", False, None),
    ("N06", "Maybe maybe the test will finish.", "Maybe the test will finish.", False, None),
    ("N07", "The result that we maybe that we should publish is negative.", CLEAN, False, None),
    ("N08", "I meant then, then repeated it.", "I meant then repeated it.", False, None),
    ("N09", 'The phrase "that we that we" stays unchanged.', 'The phrase "that we" stays unchanged.', False, None),
    ("N10", "Keep 'that we that we' exactly.", "Keep 'that we' exactly.", False, None),
    ("N11", "Keep `that we that we` exactly.", "Keep `that we` exactly.", False, None),
    ("N12", SOURCE, CLEAN, False, "that we that we"),
    ("N13", "The result that we should publish, that we should publish, is negative.", CLEAN, False, None),
    ("N14", SOURCE.replace("we that", "we, that"), CLEAN, False, None),
    ("N15", SOURCE.replace("we that", "we\nthat"), CLEAN, False, None),
    ("N16", SOURCE, "The result should publish is negative.", False, None),
    ("N17", SOURCE, CLEAN.replace("negative", "positive"), False, None),
    ("N18", "The first result that we that we should publish is negative. The second result that we should publish is positive.",
     "The first result should publish is negative. The second result that we should publish is positive.", False, None),
    ("N19", "The thing that had that had gone.", "The thing that had gone.", False, None),
    ("N20", "The question of who had who had confused everyone.", "The question of who had confused everyone.", False, None),
    ("D01", "The neighbors who had who had bicycles waited outside.",
     "The neighbors who had bicycles waited outside.", False, None),
    ("D02", "If the printer is busy then then the editor reads the draft.",
     "If the printer is busy then the editor reads the draft.", False, None),
    ("D03", "If the meeting was then then we missed it.", "If the meeting was then we missed it.", False, None),
)


class StrictIncompleteRestartTests(unittest.TestCase):
    def test_version_distinguishes_new_authorization(self):
        self.assertEqual(SCORER_VERSION, "strict-lexical-v2-word-bounded-corrections")

    def test_all_27_design_controls_with_and_without_targets(self):
        self.assertEqual(len(DESIGN_CONTROLS), 27)
        for name, source, proposal, expected, protected in DESIGN_CONTROLS:
            metadata = {}
            if protected:
                start = source.index(protected)
                metadata["protected_spans"] = [[start, start + len(protected), "authored-literal"]]
            for target in (ABSENT, proposal, source):
                with self.subTest(control=name, target=target):
                    result = score_case(example(source, target, **metadata), proposal)
                    authorization = result["incomplete_restart_authorization"]
                    self.assertEqual(bool(authorization["candidate_spans"]), expected)
                    if expected:
                        self.assertFalse(result["introduced_edit_flag"])
                        self.assertEqual(result["unclassified_source_omissions"], [])
                        self.assertEqual(result["metadata_issues"], [])
                        self.assertEqual(len(authorization["candidate_spans"]), 1)
                    self.assertEqual(result["semantic_assessment"], "NOT_ASSESSED")

    def test_target_and_candidate_authorization_are_separate(self):
        repaired = score_case(example(target=SOURCE), CLEAN)
        self.assertEqual(repaired["incomplete_restart_authorization"]["candidate_spans"], [[11, 18]])
        self.assertEqual(repaired["incomplete_restart_authorization"]["reference_spans"], [])
        self.assertFalse(repaired["reference_exact"])
        self.assertEqual(repaired["missing_target_words"], [{"token": "that", "count": 1}, {"token": "we", "count": 1}])
        self.assertFalse(repaired["introduced_edit_flag"])
        unchanged = score_case(example(target=CLEAN), SOURCE)
        self.assertEqual(unchanged["incomplete_restart_authorization"]["candidate_spans"], [])
        self.assertEqual(unchanged["incomplete_restart_authorization"]["reference_spans"], [[11, 18]])
        self.assertFalse(unchanged["introduced_edit_flag"])
        self.assertEqual(unchanged["metadata_issues"], [])

    def test_invalid_target_does_not_bless_or_damage_candidate(self):
        bad_target = "The result should publish is negative."
        for candidate in (SOURCE, CLEAN):
            with self.subTest(candidate=candidate):
                result = score_case(example(target=bad_target), candidate)
                self.assertFalse(result["introduced_edit_flag"])
                self.assertIn("target_omits_words_without_checked_authorization", result["metadata_issues"])
                self.assertEqual(result["incomplete_restart_authorization"]["reference_spans"], [])
        bad_candidate = score_case(example(target=CLEAN), bad_target)
        self.assertTrue(bad_candidate["introduced_edit_flag"])
        self.assertEqual(bad_candidate["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_identity_and_punctuation_identity_grant_no_permission(self):
        for target in (ABSENT, CLEAN, SOURCE):
            for output in (SOURCE, SOURCE[:-1] + "!"):
                with self.subTest(target=target, output=output):
                    result = score_case(example(target=target), output)
                    self.assertFalse(result["introduced_edit_flag"])
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_status"], "unchanged_lexical_sequence")

    def test_multiple_and_partial_identity_sites(self):
        source = SOURCE + " " + SECOND
        for output, count in ((CLEAN + " " + SECOND_CLEAN, 2), (CLEAN + " " + SECOND, 1),
                              (SOURCE + " " + SECOND_CLEAN, 1), (source, 0)):
            for target in (ABSENT, output, source):
                with self.subTest(output=output, target=target):
                    result = score_case(example(source, target), output)
                    self.assertEqual(len(result["incomplete_restart_authorization"]["candidate_spans"]), count)
                    self.assertFalse(result["introduced_edit_flag"])

    def test_overlapping_retained_auxiliary_can_anchor_next_site(self):
        source = "The result that we that we should that we that we should publish is negative."
        output = "The result that we should that we should publish is negative."
        result = score_case(example(source), output)
        self.assertEqual(len(result["incomplete_restart_authorization"]["candidate_spans"]), 2)
        self.assertFalse(result["introduced_edit_flag"])

    def test_source_and_output_boundaries_are_required(self):
        cases = [(SOURCE.replace("result that", "result. That"), CLEAN),
                 (SOURCE.replace("The result ", ""), CLEAN.replace("The result ", "")),
                 (SOURCE.replace("that we that we", "that we that we that we"), CLEAN),
                 (SOURCE, CLEAN.replace("result that", "result. That")),
                 (SOURCE, CLEAN.replace("that we", "that. We")),
                 (SOURCE, CLEAN.replace("we should", "we. Should")),
                 (SOURCE, CLEAN.replace("result that", "result\nthat"))]
        for source, output in cases:
            for target in (ABSENT, output):
                with self.subTest(source=source, output=output, target=target):
                    result = score_case(example(source, target), output)
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
                    self.assertIn("incomplete_restart_authorization_underdetermined", result["review_flags"])

    def test_missing_or_changed_subject_auxiliary_predicate_stays_flagged(self):
        for output in ("The result that should publish is negative.", "The result that we publish is negative.",
                       "The result that we should is negative.", CLEAN.replace("we should", "they should"),
                       CLEAN.replace("should", "must"), CLEAN.replace("publish", "suppress")):
            with self.subTest(output=output):
                result = score_case(example(), output)
                self.assertTrue(result["introduced_edit_flag"])
                self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_removed_words_cannot_fund_new_or_moved_occurrences(self):
        outputs = [CLEAN[:-1] + ", that we.", CLEAN[:-1] + ", we that.",
                   CLEAN[:-1] + " and we know that.", CLEAN.replace("The result", "That result")]
        for output in outputs:
            for target in (ABSENT, CLEAN, output):
                with self.subTest(output=output, target=target):
                    result = score_case(example(target=target), output)
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
                    self.assertIn("incomplete_restart_authorization_underdetermined", result["review_flags"])

    def test_later_equal_phrase_cannot_replace_local_opening(self):
        source = SOURCE + " Keep that we intact."
        target = CLEAN + " Keep that we intact."
        output = SOURCE + " Keep intact."
        result = score_case(example(source, target), output)
        self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
        self.assertIn("incomplete_restart_authorization_underdetermined", result["review_flags"])
        self.assertTrue(result["unclassified_source_omissions"])

    def test_quotes_apostrophes_backticks_and_unmatched_quotes_abstain(self):
        for first, last in (("\"", "\""), ("'", "'"), ("`", "`"), ("“", "”"), ("‘", "’"), ("\"", "")):
            source, output = "Keep " + first + SOURCE + last, "Keep " + first + CLEAN + last
            result = score_case(example(source), output)
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
            self.assertTrue(result["introduced_edit_flag"])
        result = score_case(example("Don't alter it. " + SOURCE), "Don't alter it. " + CLEAN)
        self.assertEqual(result["incomplete_restart_authorization"]["candidate_status"], "quoted_or_apostrophe_source")

    def test_protected_correction_and_vocabulary_overlap_abstain(self):
        for start, end in ((4, 10), (11, 18), (19, 26), (27, 33)):
            for metadata in ({"protected_spans": [[start, end, "literal"]]}, {"gold_offsets": [[start, end]]},
                             {"vocabulary_pairs": [[SOURCE[start:end], "Replacement"]]}):
                with self.subTest(metadata=metadata):
                    result = score_case(example(**metadata), CLEAN)
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
        for metadata in ({"protected_spans": [[11, 999, "literal"]]}, {"gold_offsets": [[11, 999]]}):
            result = score_case(example(**metadata), CLEAN)
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_lists_and_numeric_anchors_abstain(self):
        for prefix in ("• ", "-\t", "*\t", "1.\t", "  •\t", "+\t"):
            source, output = prefix + SOURCE, prefix + CLEAN
            for target in (ABSENT, output, source):
                with self.subTest(prefix=prefix, target=target):
                    result = score_case(example(source, target), output)
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
        for source, output in (("1. " + SOURCE, "1. " + CLEAN), ("- " + SOURCE, "- " + CLEAN),
                               (SOURCE.replace("result that", "result 2 that"), CLEAN.replace("result that", "result 2 that")),
                               (SOURCE.replace("result that", "result twenty five that"), CLEAN.replace("result that", "result 25 that"))):
            with self.subTest(source=source):
                result = score_case(example(source), output)
                self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
        for anchor in ("thirty percent", "ten dollars", "one hundred", "one million"):
            source = SOURCE.replace("result that", anchor + " that")
            output = CLEAN.replace("result that", anchor + " that")
            for target in (ABSENT, output):
                with self.subTest(anchor=anchor, target=target):
                    result = score_case(example(source, target), output)
                    self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_existing_optional_deletions_and_numeric_normalization_can_coexist(self):
        cases = [("Um, " + SOURCE, CLEAN, {}),
                 ("Use the the form. " + SOURCE, "Use the form. " + CLEAN, {}),
                 ("Send thirty forms. " + SOURCE, "Send 30 forms. " + CLEAN, {}),
                 ("Send it to Mark no wait Lisa. " + SOURCE, "Send it to Lisa. " + CLEAN,
                  {"gold_offsets": [[11, 24]]})]
        for source, output, metadata in cases:
            for target in (ABSENT, output):
                with self.subTest(source=source, target=target):
                    result = score_case(example(source, target, **metadata), output)
                    self.assertEqual(len(result["incomplete_restart_authorization"]["candidate_spans"]), 1)
                    self.assertFalse(result["introduced_edit_flag"])

    def test_unrelated_vocabulary_replacement_conservatively_abstains(self):
        source = "Inspect minihub. " + SOURCE
        output = "Inspect Mini Hub. " + CLEAN
        result = score_case(example(source, vocabulary_pairs=[["minihub", "Mini Hub"]]), output)
        self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
        self.assertEqual(result["incomplete_restart_authorization"]["candidate_status"], "output_sequence_not_proven")
        self.assertIn("incomplete_restart_authorization_underdetermined", result["review_flags"])

    def test_new_list_rendering_conservatively_abstains(self):
        source = "First buy milk second buy bread. " + SOURCE
        output = "1. Buy milk.\n2. Buy bread.\n" + CLEAN
        for target in (ABSENT, output):
            result = score_case(example(source, target), output)
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_status"], "output_sequence_not_proven")
            self.assertIn("incomplete_restart_authorization_underdetermined", result["review_flags"])

    def test_negation_and_hedge_words_cannot_disappear(self):
        source = SOURCE.replace("should publish", "should not publish, perhaps")
        clean = CLEAN.replace("should publish", "should not publish, perhaps")
        self.assertFalse(score_case(example(source), clean)["introduced_edit_flag"])
        for changed in (clean.replace("not ", ""), clean.replace(", perhaps", ""), clean.replace("perhaps", "probably")):
            result = score_case(example(source), changed)
            self.assertTrue(result["introduced_edit_flag"])
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_legacy_single_word_stutter_policy_is_not_broadened(self):
        for source, output, old_flag in (("Use the the folder.", "Use the folder.", False),
                                         ("This is not not allowed.", "This is not allowed.", False),
                                         ("We. We need the file.", "We need the file.", True),
                                         ("If it was then then we missed it.", "If it was then we missed it.", True)):
            result = score_case(example(source), output)
            self.assertEqual(result["introduced_edit_flag"], old_flag)
            self.assertEqual(result["incomplete_restart_authorization"]["candidate_spans"], [])

    def test_missing_output_is_not_a_measured_edit(self):
        result = score_case(example(target=CLEAN), None)
        self.assertIsNone(result["introduced_edit_flag"])
        self.assertEqual(result["incomplete_restart_authorization"]["candidate_status"], "unavailable")
        self.assertIn("output_unavailable", result["review_flags"])

    def test_aggregate_target_free_repair_has_no_introduced_omission(self):
        result = aggregate([example()], [{"case_id": "authored-restart", "delivered": CLEAN}])
        self.assertEqual(result["scorer_version"], SCORER_VERSION)
        self.assertEqual(result["counts"]["introduced_edit_flag"], 0)
        self.assertEqual(result["counts"]["introduced_required_omissions"], 0)
        self.assertEqual(result["counts"]["unclassified_source_omissions"], 0)


if __name__ == "__main__":
    unittest.main()
