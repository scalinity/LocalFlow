"""Synthetic checks of the pre-registered analysis helpers; no artifacts, models or APIs."""
from pathlib import Path
import sys
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


if __name__ == "__main__":
    unittest.main()
