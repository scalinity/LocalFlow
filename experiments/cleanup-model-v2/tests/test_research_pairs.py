import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import research_pairs as pairs
from v2.common import read_json, read_jsonl, write_jsonl


class ResearchPairsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.cases = self.root / "development.jsonl"
        self.rows = [{"case_id":f"toy-{i:03}", "category": "large" if i < 30 else "small",
                      "split":"validation", "origin":"synthetic", "model_input":f"um toy {i}",
                      "vocabulary_pairs":[["toy","Toy"]]} for i in range(50)]
        write_jsonl(self.cases, self.rows)
        self.outputs = {s:[{"case_id":c["case_id"], "model":s, "delivered":f"Toy output {i} {s}.",
                          "model_only":f"Toy raw {i} {s}."} for i,c in enumerate(self.rows)] for s in ("X","Y","Z")}
        for system, rows in self.outputs.items():
            write_jsonl(self.root / f"eval/development-{system}.jsonl", rows)

    def build(self, **kwargs):
        return pairs.build_pairs(self.cases, ["X","Y","Z"], n=10, eval_dir=self.root/"eval",
                                 output_dir=self.root/"annotation", **kwargs)

    def test_stratification_blinding_orientation_ids_and_exact_duplicates(self):
        result = self.build()
        self.assertEqual(result["category_counts"], {"large":6,"small":4})
        self.assertEqual(result["duplicate_pairs"],1); self.assertEqual(result["total_pairs"],11)
        packet=read_jsonl(self.root/"annotation/pairs.jsonl"); key=read_json(self.root/"annotation/pairs-key.json")
        indexed={p["pair_id"]:p for p in packet}
        self.assertEqual(len(indexed),11)
        for p in packet:
            self.assertEqual(set(p), {"pair_id","case_id","source","a","b","vocabulary"})
            self.assertEqual(set(p["a"]), {"text"}); self.assertEqual(set(p["b"]), {"text"})
            k=key[p["pair_id"]]
            self.assertEqual(set(k), {"a_system","b_system","a_output_id","b_output_id","duplicate_of"})
            self.assertNotEqual(k["a_system"],k["b_system"])
            self.assertEqual(k["a_output_id"],pairs.output_id(p["case_id"],k["a_system"],"delivered"))
            if k["duplicate_of"]:
                self.assertEqual(p | {"pair_id":k["duplicate_of"]}, indexed[k["duplicate_of"]])
                self.assertEqual(k | {"duplicate_of":None}, key[k["duplicate_of"]])
        self.assertGreater(len({k["a_system"] for k in key.values()}),1)

    def test_seed_and_input_order_are_reproducible_and_same_packet_resumes(self):
        first=self.build()
        contents=(self.root/"annotation/pairs.jsonl").read_bytes()
        write_jsonl(self.cases,list(reversed(self.rows)))
        self.assertEqual(first,self.build())
        self.assertEqual(contents,(self.root/"annotation/pairs.jsonl").read_bytes())

    def test_changed_packet_is_refused_without_overwriting(self):
        self.build(); packet=self.root/"annotation/pairs.jsonl"; before=packet.read_bytes()
        with self.assertRaisesRegex(ValueError,"packet exists"): self.build(seed=2)
        self.assertEqual(packet.read_bytes(),before)

    def test_unavailable_outputs_and_population_mismatch_are_refused(self):
        for variant in ("missing","empty","wrong-system","duplicate"):
            rows=copy.deepcopy(self.outputs["X"])
            if variant=="missing":rows.pop()
            if variant=="empty":rows[0]["delivered"]=None
            if variant=="wrong-system":rows[0]["model"]="unknown"
            if variant=="duplicate":rows.append(rows[0])
            write_jsonl(self.root/"eval/development-X.jsonl",rows)
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.build()
        self.assertFalse((self.root/"annotation/pairs.jsonl").exists())

    def test_only_development_and_no_read_of_restricted_paths(self):
        with patch.object(Path,"read_text",side_effect=AssertionError("No restricted reads")),self.assertRaises(ValueError):
            pairs.build_pairs(self.root/"final.jsonl",["X","Y"],prefix="final")
        self.rows[0]["split"]="test";write_jsonl(self.cases,self.rows)
        with self.assertRaises(ValueError):self.build()

    def test_sample_size_and_system_requirements(self):
        for systems,n in ((["X"],10),(["X","X"],10),(["../X","Y"],10),(["X","Y"],51),(["X","Y"],0)):
            with self.subTest(systems=systems,n=n),self.assertRaises(ValueError):
                pairs.build_pairs(self.cases,systems,n=n,eval_dir=self.root/"eval",output_dir=self.root/"annotation")

    def test_small_sample_rounds_duplicate_count_up_and_uses_selected_stage(self):
        result=pairs.build_pairs(self.cases,["X","Y"],n=1,stage="model_only",eval_dir=self.root/"eval",output_dir=self.root/"annotation")
        self.assertEqual(result["duplicate_pairs"],1)
        self.assertIn("raw",read_jsonl(self.root/"annotation/pairs.jsonl")[0]["a"]["text"])


if __name__ == "__main__":
    unittest.main()
