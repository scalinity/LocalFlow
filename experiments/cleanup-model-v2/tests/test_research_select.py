"""Synthetic checks of the model-selection rule; no artifacts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import research_select as rs


def arm(primary, cross=0.5, damage=0.01, facts=0.0, noop=0.98, sd=0.01):
    return {rs.PRIMARY: {"mean": primary, "seed_sd": sd}, rs.CROSS: {"mean": cross}, rs.DAMAGE: {"mean": damage},
            rs.FACTS: {"mean": facts}, rs.NOOP: {"mean": noop}}


def analysis(**arms):
    return {"available_arms": list(arms), "arm_values": arms}


LATENCY = {a: {"total_cleanup_ms": {"median": 1000.0}} for a in ("C", "M1", "M2", "M3")}
SIZES = {"C": 100, "M1": 100, "M2": 100, "M3": 100}


class SelectionTests(unittest.TestCase):
    def test_higher_primary_wins_when_the_gap_exceeds_the_seed_sd(self):
        a = analysis(C=arm(0.5), M1=arm(0.60), M2=arm(0.70), M3=arm(0.55))
        self.assertEqual(rs.select(a, LATENCY, SIZES)["winner"], "M2")

    def test_a_tie_goes_to_the_lower_latency_then_to_m2(self):
        a = analysis(C=arm(0.5), M1=arm(0.700), M2=arm(0.705), M3=arm(0.60))
        faster = {**LATENCY, "M1": {"total_cleanup_ms": {"median": 900.0}}}
        self.assertEqual(rs.select(a, faster, SIZES)["winner"], "M1")
        self.assertEqual(rs.select(a, LATENCY, SIZES)["winner"], "M2")

    def test_a_gate_failure_removes_the_candidate(self):
        a = analysis(C=arm(0.5), M1=arm(0.60), M2=arm(0.80, damage=0.05), M3=arm(0.55))
        self.assertEqual(rs.select(a, LATENCY, SIZES)["winner"], "M1")
        big = {**SIZES, "M1": 400, "M3": 400, "M2": 400}
        self.assertEqual(rs.select(a, LATENCY, big)["decision"], "KEEP_C")

    def test_latency_gate_is_relative_to_c(self):
        a = analysis(C=arm(0.5), M1=arm(0.60), M2=arm(0.70), M3=arm(0.55))
        slow = {**LATENCY, "M2": {"total_cleanup_ms": {"median": 1600.0}}}
        self.assertEqual(rs.select(a, slow, SIZES)["winner"], "M1")

    def test_the_other_vendors_pass_rate_must_not_fall_below_c(self):
        a = analysis(C=arm(0.5, cross=0.6), M1=arm(0.60, cross=0.5), M2=arm(0.70, cross=0.55), M3=arm(0.55, cross=0.5))
        self.assertEqual(rs.select(a, LATENCY, SIZES)["decision"], "JUDGE_DISAGREEMENT")

    def test_missing_reference_values_are_not_evaluable(self):
        self.assertEqual(rs.select(analysis(M2=arm(0.7)), LATENCY, SIZES)["decision"], "NOT_EVALUABLE")


if __name__ == "__main__":
    unittest.main()
