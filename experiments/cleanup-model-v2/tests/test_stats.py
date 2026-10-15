import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import stats
from v2.research_inputs import development_cases


class StatisticsTests(unittest.TestCase):
    def test_constant_paired_difference_has_exact_interval(self):
        result = stats.paired_bootstrap({"c": 4, "a": 2, "b": 3}, {"a": 1, "b": 2, "c": 3})
        self.assertEqual(result["difference_a_minus_b"], 1)
        self.assertEqual(result["ci"], [1, 1])
        self.assertEqual(result["resamples"], 10000)

    def test_bootstrap_is_seeded_order_independent_and_pairs_whole_cases(self):
        a = {"a": 1, "b": 0}; b = {"a": 0, "b": 1}
        r = stats.paired_bootstrap(a, b, seed=23)
        self.assertEqual(r["ci"], [-1, 1]); self.assertEqual(r["difference_a_minus_b"], 0)
        self.assertEqual(r, stats.paired_bootstrap(dict(reversed(list(a.items()))), b, seed=23))
        self.assertEqual(stats.quantile([0, 1, 2, 3], .25), .75)

    def test_pair_population_and_finite_observations_are_enforced(self):
        for a,b in (({}, {}), ({"a":1}, {"b":1}), ({"a":math.nan}, {"a":1}), ({"a":None}, {"a":1})):
            with self.assertRaises(ValueError): stats.paired_bootstrap(a, b)
        with self.assertRaises(ValueError): stats.paired_bootstrap({"a":1}, {"a":1}, resamples=0)

    def test_exact_mcnemar_known_tail_and_no_discordance(self):
        # Six discordances, all in the same direction: 2 / 2**6.
        a = {str(i):True for i in range(6)}; b = {str(i):False for i in range(6)}
        r = stats.exact_mcnemar(a, b)
        self.assertEqual(r["p_two_sided"], 1/32); self.assertEqual(r["a_only_failures"], 6)
        self.assertEqual(stats.exact_mcnemar(a, a)["p_two_sided"], 1)
        # Discordant counts 1 and 7: 2*(1+8)/256.
        r = stats.exact_mcnemar({str(i):i != 0 for i in range(8)}, {str(i):i == 0 for i in range(8)})
        self.assertEqual(r["p_two_sided"], 18/256)
        with self.assertRaises(ValueError): stats.exact_mcnemar({"a":2}, {"a":1})

    def test_kappa_known_perfect_chance_negative_and_constant(self):
        self.assertEqual(stats.cohen_kappa([0,1], [0,1])["kappa"], 1)
        self.assertEqual(stats.cohen_kappa([0,0,1,1], [0,1,0,1])["kappa"], 0)
        self.assertEqual(stats.cohen_kappa([0,1], [1,0])["kappa"], -1)
        self.assertIsNone(stats.cohen_kappa([0,0], [0,0])["kappa"])
        self.assertEqual(stats.cohen_kappa([0,None,1], [0,0,1])["omitted"], 1)
        with self.assertRaises(ValueError): stats.cohen_kappa([0], [])

    def test_alpha_known_coincidence_counts_and_missing_ratings(self):
        self.assertEqual(stats.krippendorff_alpha([[0,0], [1,1]])["alpha"], 1)
        # Marginals (2,2): De=2/3; two disagreeing units: Do=1; alpha=-1/2.
        self.assertEqual(stats.krippendorff_alpha([[0,1], [1,0]])["alpha"], -.5)
        # Pairable ratings (0,0,1) and (1,1), marginals (2,3): Do=.4, De=.6.
        r = stats.krippendorff_alpha([[0,0,1], [1,1,None], [None,0,None]])
        self.assertAlmostEqual(r["alpha"], 1/3); self.assertEqual(r["omitted_units"], 1)
        self.assertIsNone(stats.krippendorff_alpha([[0,0], [0,None]])["alpha"])
        self.assertIsNone(stats.krippendorff_alpha([[None,1]])["alpha"])

    def test_swapped_positions_cancel_system_preference(self):
        def row(a,b,c): return dict(a_system=a,b_system=b,choice=c)
        f = {"p":row("X","Y","a")}
        self.assertEqual(stats.position_bias(f, {"p":row("Y","X","b")})["first_minus_second"], 0)
        self.assertEqual(stats.position_bias(f, {"p":row("Y","X","a")})["first_minus_second"], 1)
        self.assertEqual(stats.position_bias({"p":row("X","Y","b")}, {"p":row("Y","X","b")})["first_minus_second"], -1)
        with self.assertRaises(ValueError): stats.position_bias(f, f)

    def test_across_seed_sd_is_sample_sd_and_single_seed_is_undefined(self):
        self.assertEqual(stats.across_seeds([1,2,3]), {"n":3,"mean":2,"sd":1,"sd_ddof":1})
        self.assertIsNone(stats.across_seeds([7])["sd"])
        with self.assertRaises(ValueError): stats.across_seeds([])

    def test_holm_known_monotone_adjustment_in_declared_order(self):
        rows = [{"name":"c","p":.04}, {"name":"a","p":.01}, {"name":"b","p":.03}]
        r = stats.holm(rows)
        self.assertEqual([x["p_holm"] for x in r], [.06,.03,.06])
        self.assertEqual([x["reject"] for x in r], [False,True,False])
        with self.assertRaises(ValueError): stats.holm(rows+[rows[0]])
        with self.assertRaises(ValueError): stats.holm([{"name":"x","p":None}])

    def test_offline_clis_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); a=root/"a.jsonl"; b=root/"b.jsonl"
            a.write_text('{"case_id":"toy","score":1,"failure":false}\n')
            b.write_text('{"case_id":"toy","score":0,"failure":true}\n')
            with contextlib.redirect_stdout(io.StringIO()) as out:
                stats.main(["paired", str(a), str(b), "--score", "score", "--failure", "failure"])
            r=json.loads(out.getvalue()); self.assertEqual(r["bootstrap"]["ci"], [1,1])
            with self.assertRaises(ValueError): stats.index_rows([{"case_id":"a"}]*2)

    def test_development_loader_checks_metadata_and_restricted_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); f=root/"development.jsonl"
            f.write_text('{"case_id":"toy","split":"test"}\n')
            with self.assertRaisesRegex(ValueError,"development"): development_cases(f)
            # Refused before reading a nonexistent held-out file.
            with self.assertRaises(ValueError): development_cases(root/"final.jsonl")
            f.write_text('{"case_id":"toy","split":"validation"}\n')
            self.assertEqual(len(development_cases(f)),1)

    def test_export_reuses_per_case_metrics_with_synthetic_fixture(self):
        from v2 import common
        from v2.common import write_jsonl
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); f=root/"development.jsonl"; out=root/"scores.jsonl"
            write_jsonl(f,[{"case_id":"toy","split":"validation","origin":"synthetic","model_input":"Keep five bolts.",
                "target":"Keep five bolts.","is_noop":True,"critical_facts":[],"vocabulary_pairs":[],"gold_lines":[],"category":"preserve_plain"}])
            write_jsonl(root/"eval/development-X.jsonl",[{"case_id":"toy","delivered":"Keep five bolts."}])
            with patch.object(common,"ART",root):
                stats.export_scores(f,out,prefix="development",system="X",stage="delivered")
            row=stats.read_rows(out)[0]; self.assertTrue(row["reference_complete"])


if __name__ == "__main__":
    unittest.main()
