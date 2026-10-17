"""Synthetic checks of the pre-registered analysis helpers; no artifacts, models or APIs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import research_analysis as ra


class AnalysisHelperTests(unittest.TestCase):
    def test_judged_pass_needs_no_flag_and_a_complete_or_unneeded_cleanup(self):
        base = {"semantic_damage": False, "critical_fact_changed": False, "hallucination": False, "unwanted_edit": False,
                "cleanup": "complete", "punctuation": "improved", "self_correction": "not_applicable"}
        self.assertEqual(ra.judged_metrics(base)["judged_pass"], 1.0)
        self.assertEqual(ra.judged_metrics({**base, "cleanup": "none_needed"})["judged_pass"], 1.0)
        self.assertEqual(ra.judged_metrics({**base, "cleanup": "partial"})["judged_pass"], 0.0)
        for flag in ra.FLAGS:
            self.assertEqual(ra.judged_metrics({**base, flag: True})["judged_pass"], 0.0)

    def test_polarity_flags_lower_is_better_metrics(self):
        self.assertEqual(ra.polarity("engine_damage"), -1)
        self.assertEqual(ra.polarity("anthropic:judged_unwanted_edit"), -1)
        self.assertEqual(ra.polarity("anthropic:judged_pass"), 1)
        self.assertEqual(ra.polarity("engine_noop_preserved"), 1)

    def test_holm_is_monotone_and_missing_contrasts_count_as_p_one(self):
        adjusted = ra.holm_adjust([0.001, 0.02, 0.5, 1.0, 1.0, 1.0, 1.0])
        self.assertAlmostEqual(adjusted[0], 0.007)
        self.assertEqual(adjusted, sorted(adjusted[:3]) + adjusted[3:])
        self.assertTrue(all(0 <= p <= 1 for p in adjusted))

    def test_one_set_of_resamples_is_shared_and_repeatable(self):
        ids = list(range(40))
        diffs = {"a": {i: 1.0 for i in ids}, "b": {i: float(i % 2) for i in ids}}
        first = ra.bootstrap(diffs, ids, resamples=200, seed=7)
        second = ra.bootstrap(diffs, ids, resamples=200, seed=7)
        self.assertEqual(first, second)
        self.assertTrue(all(abs(x - 1.0) < 1e-12 for x in first["a"]))
        self.assertLess(ra.p_two_sided(first["a"]), 0.02)

    def test_interval_levels_nest(self):
        samples = [i / 100 for i in range(-50, 51)]
        wide, narrow = ra.interval(samples, 1 - 0.05 / 7), ra.interval(samples, 0.95)
        self.assertLessEqual(wide[0], narrow[0])
        self.assertGreaterEqual(wide[1], narrow[1])

    def test_stage2_claims_carry_the_amendment_thresholds(self):
        claims = ra.stage2_components()
        self.assertEqual({k: [c[1] for c in v] for k, v in claims.items()},
                         {"C1": [0.0, 0.0, -0.01], "C2": [0.0], "C3": [0.0, 0.0], "C4": [0.05, 0.05], "C5": [-0.02, -0.02],
                          "H5 sonnet-5-5-fewshot": [-0.03, -0.03], "H5 opus-5-5-fewshot": [-0.03, -0.03]})
        judged = [c[0] for v in claims.values() for c in v if "damage" not in c[0]]
        for judge in ra.STAGE2_JUDGES:
            self.assertEqual(sum(f"({judge})" in name for name in judged), len(judged) // 2)

    def test_stage2_component_passes_only_above_its_threshold(self):
        cases = list(range(60))
        vectors = {"A": {"m": {i: 1.0 for i in cases}}, "B": {"m": {i: 0.0 for i in cases}}}
        terms = [(1, "A", "m"), (-1, "B", "m")]
        self.assertEqual(ra.stage2_component(vectors, cases, "A - B", 0.5, terms, resamples=200)["outcome"], "pass")
        self.assertEqual(ra.stage2_component(vectors, cases, "A - B", 1.0, terms, resamples=200)["outcome"], "fail")

    def test_stage2_missing_outcomes_never_help_the_claim(self):
        cases = list(range(100))
        vectors = {"A": {"m": {i: 1.0 for i in range(40)}}, "B": {"m": {i: 0.0 for i in cases}}}
        terms = [(1, "A", "m"), (-1, "B", "m")]
        row = ra.stage2_component(vectors, cases, "A - B", 0.5, terms, resamples=200)
        self.assertEqual((row["n_complete"], row["estimate"]), (40, 1.0))
        # Set against the claim, the 60 missing outcomes bring A - B down to 0.4.
        self.assertLess(row["ci99_missing_against_claim"][0], 0.5)
        self.assertEqual(row["outcome"], "not evaluable")
        self.assertEqual(ra.stage2_component({}, cases, "no data", 0.0, terms, resamples=200)["outcome"], "not evaluable")

    def test_stage2_claim_needs_every_component(self):
        cases = list(range(60))
        vectors = {"A": {"m": {i: 1.0 for i in cases}}, "B": {"m": {i: 0.0 for i in cases}}}
        good = ("A - B", 0.5, [(1, "A", "m"), (-1, "B", "m")])
        bad = ("B - A", 0.0, [(1, "B", "m"), (-1, "A", "m")])
        unmeasured = ("C - B", 0.0, [(1, "C", "m"), (-1, "B", "m")])
        result = ra.stage2(vectors, cases, {"x": [good, good], "y": [good, bad, unmeasured], "z": [good, unmeasured]},
                           resamples=200)
        self.assertEqual({k: v["outcome"] for k, v in result.items()},
                         {"x": "supported", "y": "not supported", "z": "not evaluable"})

    def test_stage2_rewritten_key_shift_pools_both_forms(self):
        # Original key: the earlier data is ahead in both forms. Rewritten key: level in one, new data ahead in the other.
        original = {"M2": 0.0, "A2prime": 1.0, "M1": 0.0, "A2": 1.0}
        rewritten = {"M2": 1.0, "A2prime": 1.0, "M1": 1.0, "A2": 0.0}
        cases = list(range(30))
        vectors = {arm: {"j:judged_pass": {i: original[arm] for i in cases},
                         "j:rewritten_judged_pass": {i: rewritten[arm] for i in cases}} for arm in original}
        name, threshold, terms = ra.stage2_components(judges=("j",))["C3"][0]
        row = ra.stage2_component(vectors, cases, name, threshold, terms, resamples=200)
        self.assertAlmostEqual(row["estimate"], 1.5)  # ((0 - (-1)) + (1 - (-1))) / 2
        self.assertEqual(row["outcome"], "pass")

    def test_judge_table_leaves_stage2_gaps_unverified(self):
        verdict = {"semantic_damage": False, "critical_fact_changed": False, "hallucination": False, "unwanted_edit": False,
                   "cleanup": "complete", "punctuation": "improved", "self_correction": "not_applicable"}
        rows = [{"case_id": "a", "model": "M", "stage": "delivered", "status": "judged", "verdict": verdict},
                {"case_id": "b", "model": "M", "stage": "delivered", "status": "UNVERIFIED", "verdict": None}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verdicts.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            stage1, _ = ra.judge_table(path)
            stage2, missing = ra.judge_table(path, None)
        self.assertEqual((stage1[("b", "M")]["judged_pass"], stage2[("b", "M")]["judged_pass"], missing), (0.0, None, 1))
        self.assertEqual(stage2[("a", "M")]["judged_pass"], 1.0)


if __name__ == "__main__":
    unittest.main()
