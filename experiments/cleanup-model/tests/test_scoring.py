"""Deterministic metrics on handcrafted outputs, one defect at a time."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx import score  # noqa: E402

CASE = {"case_id": "c1", "category": "self_correction_single", "is_noop": False,
        "model_input": "Um, book the room for Tuesday, no wait, Thursday at 3 and do not invite Priya.",
        "target": "Book the room for Thursday at 3 and do not invite Priya.",
        "critical_facts": [{"text": "Thursday", "kind": "date_time"}, {"text": "3", "kind": "number"},
                           {"text": "Priya", "kind": "name"}, {"text": "not", "kind": "negation"}],
        "obsolete_values": ["Tuesday"], "gold_lines": ["Tuesday, no wait"], "gold_offsets": [[22, 38]]}
NOOP = {"case_id": "c2", "category": "preservation_discourse", "is_noop": True,
        "model_input": "I think we could, like, maybe ship it on Friday.",
        "target": "I think we could, like, maybe ship it on Friday.", "critical_facts": [], "obsolete_values": []}


def s(case, text):
    return score.score_synthetic(case, text, delivered=False)


class ScoringTests(unittest.TestCase):
    def test_correct_repair(self):
        m = s(CASE, CASE["target"])
        self.assertTrue(m["repair_success"])
        self.assertFalse(m["damage"])
        self.assertTrue(m["correction_success"])
        self.assertEqual(m["wer_errors"], 0)

    def test_fallback_input_has_no_damage_but_no_repair(self):
        m = s(CASE, CASE["model_input"])
        self.assertFalse(m["damage"])
        self.assertFalse(m["repair_success"])
        self.assertFalse(m["correction_success"])
        self.assertGreater(m["filler_residue"], 0)

    def test_changed_number_is_damage(self):
        m = s(CASE, "Book the room for Thursday at 4 and do not invite Priya.")
        self.assertTrue(m["damage"])
        self.assertTrue(m["facts_changed"])

    def test_dropped_negation(self):
        m = s(CASE, "Book the room for Thursday at 3 and do invite Priya.")
        self.assertTrue(m["negation_changed"])
        self.assertTrue(m["damage"])

    def test_wrong_value_kept(self):
        m = s(CASE, "Book the room for Tuesday at 3 and do not invite Priya.")
        self.assertFalse(m["correction_success"])
        self.assertTrue(m["damage"])           # Thursday (a kept fact) is gone

    def test_hallucinated_addition_and_missing_ending(self):
        m = s(CASE, "Book the conference room for Thursday at 3.")
        self.assertTrue(m["hallucination"])
        self.assertTrue(m["omission"])
        self.assertTrue(m["missing_ending"])

    def test_unwanted_answer(self):
        q = dict(CASE, category="question_or_request_as_content", gold_lines=[], gold_offsets=[], obsolete_values=[],
                 model_input="Can you check why the build failed?", target="Can you check why the build failed?",
                 critical_facts=[])
        m = s(q, "The build failed because the cache key changed after the dependency update.")
        self.assertTrue(m["unwanted_answer"])
        self.assertTrue(m["damage"])

    def test_noop_preservation(self):
        self.assertTrue(s(NOOP, NOOP["target"])["noop_preserved"])
        m = s(NOOP, "I think we could maybe ship it on Friday.")
        self.assertFalse(m["noop_preserved"])
        self.assertTrue(m["unnecessary_edit"])
        self.assertTrue(m["omission"])             # 'like' carries voice

    def test_number_words_equal_digits(self):
        self.assertEqual(score.lex("twenty five dollars"), score.lex("25 dollars"))

    def test_correct_resolution_with_repeated_word_is_not_omission(self):
        case = dict(CASE, model_input="I switch from tab 2 actually tab 3, so check it.",
                    target="I switch from tab 3, so check it.", critical_facts=[], obsolete_values=["2"],
                    gold_lines=["tab 2 actually"], gold_offsets=[[14, 28]])
        m = s(case, "I switch from tab 3, so check it.")
        self.assertFalse(m["omission"], m["omitted_content"])
        self.assertTrue(m["repair_success"])
        unresolved = s(case, case["model_input"])
        self.assertFalse(unresolved["hallucination"])
        self.assertFalse(unresolved["correction_success"])

    def test_currency_representation_is_equivalent(self):
        case = dict(CASE, model_input="I booked 4 seats for 120 dollars each.", target="I booked 4 seats for 120 dollars each.",
                    critical_facts=[{"text": "120 dollars", "kind": "number"}], obsolete_values=[], gold_lines=[],
                    gold_offsets=[])
        m = s(case, "I booked 4 seats for $120 each.")
        self.assertFalse(m["damage"], m)

    def test_lists_counted(self):
        self.assertEqual(score.list_items("Intro:\n- a\n- b\n\nBye."), 2)
        self.assertEqual(score.list_items("Steps:\n1. a\n2. b"), 2)

    def test_bootstrap_detects_clear_difference(self):
        a = {f"c{i}": i % 10 == 0 for i in range(300)}
        b = {f"c{i}": i % 2 == 0 for i in range(300)}
        r = score.family_bootstrap(a, b, None, {}, n=500)
        self.assertGreater(r["ci95"][0], 0.3)

    def test_real_unauthorized_edits(self):
        case = {"source": "fleurs", "lexical_reference": "the cat sat on the mat"}
        asr = {"normalized": "The cat sat on the mat."}
        self.assertFalse(score.score_real(case, asr, "The cat sat on the mat.")["unauthorized_edit"])
        m = score.score_real(case, asr, "The cat was sitting on the mat.")
        self.assertTrue(m["unauthorized_edit"])
        self.assertGreater(m["wer_errors"], 0)


if __name__ == "__main__":
    unittest.main()
