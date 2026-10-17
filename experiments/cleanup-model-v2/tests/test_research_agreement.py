import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v2 import research_agreement as agreement, stats
from v2.common import write_json, write_jsonl


def packet():
    pairs=[{"pair_id":f"p{i}","case_id":f"c{i}","source":"Toy dictation.",
            "a":{"text":"Toy A."},"b":{"text":"Toy B."},"vocabulary":[]} for i in range(4)]
    key={p["pair_id"]:{"a_system":"X","b_system":"Y","a_output_id":f"x{i}","b_output_id":f"y{i}","duplicate_of":None}
         for i,p in enumerate(pairs)}
    for i in range(2):
        pid=f"repeat{i}"; pairs.append(pairs[i] | {"pair_id":pid})
        key[pid]=key[f"p{i}"] | {"duplicate_of":f"p{i}"}
    return pairs,key


def annotation(pid,choice,at="2026-01-01T00:00:00Z"):
    return dict(pair_id=pid,choice=choice,note="",seconds=2,annotated_at=at)


def verdict(oid,**overrides):
    return dict(output_id=oid,semantic_damage=False,critical_fact_changed=False,hallucination=False,
                unwanted_edit=False,cleanup="complete",punctuation="improved",self_correction="not_applicable",
                reason="Synthetic fixture") | overrides


RULE={"failure_fields":["semantic_damage","critical_fact_changed","hallucination","unwanted_edit"],
      "quality":[{"field":"cleanup","tiers":[["wrong"],["partial"],["complete","none_needed"]]}]}


class AgreementTests(unittest.TestCase):
    def test_accuracy_kappa_confusion_and_duplicate_consistency(self):
        pairs,key=packet()
        human=[annotation(f"p{i}",c) for i,c in enumerate(("a","b","tie","both_wrong"))]
        human += [annotation("repeat0","b"),annotation("repeat1","b")]
        judge=[{"pair_id":pid,"choice":c} for pid,c in zip(key,("a","b","a","both_wrong","a","b"))]
        result=agreement.agreement(pairs,key,human,{"toy":judge})
        measured=result["judges"]["toy"]
        self.assertEqual(measured["n"],4);self.assertEqual(measured["accuracy"],.75)
        self.assertAlmostEqual(measured["kappa"]["kappa"],2/3)
        self.assertEqual(measured["confusion_human_rows_judge_columns"]["tie"]["a"],1)
        self.assertEqual(measured["including_duplicates"]["n"],6)
        self.assertEqual(result["human_test_retest"]["completed"],2)
        self.assertEqual(result["human_test_retest"]["consistency"],.5)

    def test_last_file_record_wins_and_null_undoes_regardless_of_timestamp(self):
        rows=[annotation("p0","a","2099-01-01"),annotation("p0","b","2000-01-01"),annotation("p1","a"),annotation("p1",None)]
        self.assertEqual(agreement.latest_annotations(rows,{"p0","p1"}),{"p0":"b"})
        pairs,key=packet()
        result=agreement.agreement(pairs,key,rows,{"empty":[]})
        self.assertEqual(result["human_completed"],1)
        self.assertEqual(result["judges"]["empty"]["judge_missing"],1)
        self.assertIsNone(result["judges"]["empty"]["accuracy"])

    def test_unannotated_retests_are_undefined_and_undone_duplicates_are_excluded(self):
        pairs,key=packet()
        rows=[annotation("p0","a"),annotation("repeat0","a"),annotation("repeat0",None)]
        result=agreement.agreement(pairs,key,rows,{"empty":[]})
        self.assertEqual(result["human_test_retest"]["completed"],0)
        self.assertIsNone(result["human_test_retest"]["consistency"])

    def test_unknown_ids_invalid_choices_and_duplicate_judge_rows_are_refused(self):
        pairs,key=packet();indexed=stats.index_rows(pairs,"pair_id")
        for rows in ([annotation("unknown","a")],[annotation("p0","bad")]):
            with self.assertRaises(ValueError):agreement.latest_annotations(rows,indexed)
        with self.assertRaises(ValueError):agreement.judge_choices([{"pair_id":"p0","choice":"a"}]*2,indexed,key)

    def test_duplicate_packet_cannot_silently_swap_outputs(self):
        pairs,key=packet(); pairs[-1]["a"]={"text":"Changed."}
        with self.assertRaisesRegex(ValueError,"exact duplicates"):agreement.validate_packet(pairs,key)
        pairs,key=packet();key["repeat0"]["duplicate_of"]="repeat1"
        with self.assertRaisesRegex(ValueError,"duplicate reference"):agreement.validate_packet(pairs,key)

    def test_expanded_verdict_adapter_requires_declared_rule_and_handles_dedup(self):
        pairs,key=packet();indexed=stats.index_rows(pairs,"pair_id")
        rows=[{"case_id":"c0","model":"X","stage":"delivered","status":"judged","verdict":verdict("x0",cleanup="partial")},
              {"case_id":"c0","model":"Y","stage":"delivered","status":"judged","verdict":verdict("y0")},
              {"case_id":"c1","model":"X","stage":"delivered","status":"judged","verdict":verdict("shared")},
              {"case_id":"c1","model":"Y","stage":"delivered","status":"judged","verdict":verdict("shared")},
              {"case_id":"c2","model":"X","stage":"delivered","status":"UNVERIFIED","verdict":None}]
        with self.assertRaisesRegex(ValueError,"pre-declared"):agreement.judge_choices(rows,indexed,key)
        choices=agreement.judge_choices(rows,indexed,key,rule=RULE)
        self.assertEqual(choices,{"p0":"b","p1":"tie","repeat0":"b","repeat1":"tie"})
        result=agreement.agreement(pairs,key,[annotation("p2","a")],{"j":rows},rule=RULE)
        self.assertEqual(result["judges"]["j"]["judge_missing"],1)

    def test_rule_failure_and_ordinal_semantics_are_explicit(self):
        agreement.validate_rule(RULE)
        good=verdict("a");bad=verdict("b",semantic_damage=True)
        self.assertEqual(agreement.verdict_choice(good,bad,RULE),"a")
        self.assertEqual(agreement.verdict_choice(bad,good,RULE),"b")
        self.assertEqual(agreement.verdict_choice(bad,bad,RULE),"both_wrong")
        self.assertEqual(agreement.verdict_choice(good,good,RULE),"tie")
        bad_rule=copy.deepcopy(RULE);bad_rule["quality"][0]["tiers"]=[["complete"]]
        with self.assertRaises(ValueError):agreement.validate_rule(bad_rule)
        with self.assertRaises(ValueError):agreement.validate_rule({"failure_fields":["reason"],"quality":[]})

    def test_positions_follow_actual_blinded_request_order_and_skip_equal_text(self):
        pairs,key=packet();indexed=stats.index_rows(pairs,"pair_id")
        rows=[{"case_id":"c0","model":"X","stage":"delivered","verdict":verdict("x0")},
              {"case_id":"c0","model":"Y","stage":"delivered","verdict":verdict("y0")},
              {"case_id":"c1","model":"X","stage":"delivered","verdict":verdict("shared")},
              {"case_id":"c1","model":"Y","stage":"delivered","verdict":verdict("shared")}]
        def identity(order):return {"request_parameters":{"initial":{"r0":{"messages":[{"role":"user","content":json.dumps({"outputs":[{"output_id":o} for o in order]})}]}}}}
        forward=agreement.presented_choices(rows,indexed,key,{"p0":"a","p1":"tie"},identity(["x0","y0","shared"]),"delivered")
        swapped=agreement.presented_choices(rows,indexed,key,{"p0":"a","p1":"tie"},identity(["shared","y0","x0"]),"delivered")
        self.assertEqual(len(forward),1);self.assertEqual(forward[0]["a_system"],"X")
        self.assertEqual(swapped[0]["a_system"],"Y");self.assertEqual(swapped[0]["choice"],"b")
        self.assertEqual(stats.position_bias(stats.index_rows(forward,"pair_id"),stats.index_rows(swapped,"pair_id"))["first_minus_second"],0)

    def test_cli_exports_nulls_for_missing_ratings_and_analysis_summary(self):
        pairs,key=packet()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            write_jsonl(root/"pairs.jsonl",pairs);write_json(root/"pairs-key.json",key)
            write_jsonl(root/"annotations.jsonl",[annotation("p0","a")])
            write_jsonl(root/"judge.jsonl",[{"pair_id":"p0","choice":"a"}])
            agreement.main([str(root/"pairs.jsonl"),str(root/"pairs-key.json"),str(root/"annotations.jsonl"),
                "--judge","toy="+str(root/"judge.jsonl"),"--output",str(root/"agreement.json"),"--choices-dir",str(root/"choices")])
            self.assertEqual(json.loads((root/"agreement.json").read_text())["judges"]["toy"]["accuracy"],1)
            self.assertEqual(len(stats.read_rows(root/"choices/human.jsonl")),4)
            self.assertIsNone(stats.read_rows(root/"choices/toy.jsonl")[1]["choice"])


if __name__ == "__main__":
    unittest.main()
