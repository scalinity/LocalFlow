"""Dataset integrity: deterministic gates, normalization re-anchoring, byte-exact
capture acceptance, family-level splits and leakage, near-duplicate removal."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx import assemble, synth  # noqa: E402
from lfx.capture import capture  # noqa: E402
from lfx.common import ART, read_jsonl  # noqa: E402

SPEC = {"split": "train", "category": "self_correction_single", "destination_profile": None, "length": "short", "is_noop": False}


def fam(**kw):
    base = {"family_id": "t", "spoken_input": "", "target": "", "is_noop": False, "critical_facts": [],
            "corrections": [], "removed_fillers": [], "vocabulary": [], "notes": ""}
    base.update(kw)
    return base


class GateTests(unittest.TestCase):
    def test_normalization_reanchors_gold_span(self):
        f = fam(spoken_input="The price went from ten to twelve, no wait, to fifteen dollars.",
                target="The price went from ten to fifteen dollars.",
                critical_facts=[{"text": "fifteen dollars", "kind": "number"}],
                corrections=[{"deleted_span": "to twelve, no wait", "obsolete_value": "twelve", "marker": "no wait",
                              "replacement": "to fifteen dollars"}])
        p = synth.prepare_family(f, SPEC)
        self.assertEqual(p["reject"], [])
        self.assertIn("$15", p["model_input"])
        self.assertEqual(p["gold_lines"], ["to twelve, no wait"])
        self.assertTrue(capture(p)["accepted"])

    def test_changed_number_rejected(self):
        f = fam(spoken_input="Set the timeout to 30 seconds.", target="Set the timeout to 40 seconds.",
                critical_facts=[{"text": "30 seconds", "kind": "number"}])
        p = synth.prepare_family(f, SPEC)
        self.assertTrue(p["reject"] or not capture(p)["accepted"])

    def test_added_negation_rejected(self):
        f = fam(spoken_input="Merge the release branch today.", target="Do not merge the release branch today.")
        p = synth.prepare_family(f, SPEC)
        self.assertIn("negation_added", p["reject"])

    def test_obsolete_value_kept_rejected(self):
        f = fam(spoken_input="Meet on Tuesday, no wait, Thursday.", target="Meet on Tuesday, Thursday.",
                corrections=[{"deleted_span": "Tuesday, no wait", "obsolete_value": "Tuesday", "marker": "no wait",
                              "replacement": "Thursday"}])
        self.assertIn("obsolete_value_kept", synth.prepare_family(f, SPEC)["reject"])

    def test_noop_must_be_identical(self):
        f = fam(spoken_input="Ship it on Friday.", target="Ship it on Friday!", is_noop=True)
        self.assertIn("noop_target_differs", synth.prepare_family(f, SPEC)["reject"])


class CaptureTests(unittest.TestCase):
    def pair(self, inp, tgt, noop=False):
        p = synth.prepare_family(fam(spoken_input=inp, target=tgt, is_noop=noop), SPEC)
        return p

    def test_added_word_caught_even_when_validator_tolerates_it(self):
        p = self.pair("Send the report to Ana.", "Please send the report to Ana.")
        self.assertEqual(assemble.added_words(p), ["please"])
        self.assertEqual(assemble.added_words(self.pair("Send it, um, to Ana.", "Send it to Ana.")), [])

    def test_quote_wrapped_reply_not_accepted_as_gold(self):
        # The engine strips one pair of whole-reply quotes, so a quoted gold
        # would be delivered without quotes: not byte-identical.
        p = self.pair("Send the report to Ana.", '"Send the report to Ana."')
        self.assertFalse(capture(p)["accepted"])

    def test_dropped_word_salvaged_is_rejected(self):
        c = capture(self.pair("We need the logs from the staging cluster today.",
                              "We need the logs from the cluster today."))
        self.assertFalse(c["accepted"])

    def test_role_keyed_answers(self):
        p = synth.prepare_family(fam(spoken_input="Book it for Monday, no wait, Tuesday.", target="Book it for Tuesday.",
                                     corrections=[{"deleted_span": "Monday, no wait", "obsolete_value": "Monday",
                                                   "marker": "no wait", "replacement": "Tuesday"}]), SPEC)
        c = capture(p)
        self.assertTrue(c["accepted"], c["reject"])
        self.assertEqual([x["role"] for x in c["calls"]], ["corrections", "main"])
        self.assertEqual(c["calls"][0]["completion"], "Monday, no wait")


class SplitTests(unittest.TestCase):
    def test_near_duplicates_removed_across_splits(self):
        a = {"family_id": "f1", "pair_id": "f1-base", "variant": "base",
             "model_input": "please rotate the signing key on tuesday and tell the platform team before noon",
             "target": "Please rotate the signing key on Tuesday and tell the platform team before noon."}
        b = dict(a, family_id="f2", pair_id="f2-base")
        kept, dropped = assemble.dedup({"test": [a], "validation": [], "train": [b]})
        self.assertEqual(len(kept["test"]), 1)
        self.assertEqual(len(kept["train"]), 0)

    def test_built_splits_have_disjoint_families(self):
        test = ART / "frozen" / "test_synthetic.jsonl"
        val = ART / "dataset" / "validation.jsonl"
        train = ART / "dataset" / "train.jsonl"
        if not (test.exists() and val.exists()):
            self.skipTest("datasets not built yet")
        fams = {name: {p["family_id"] for p in read_jsonl(path)} for name, path in
                (("test", test), ("validation", val), ("train", train)) if path.exists()}
        names = list(fams)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                self.assertFalse(fams[names[i]] & fams[names[j]], f"{names[i]} and {names[j]} share families")

    def test_test_pairs_verified_and_labelled(self):
        test = ART / "frozen" / "test_synthetic.jsonl"
        if not test.exists():
            self.skipTest("not frozen yet")
        rows = read_jsonl(test)
        self.assertTrue(all(r["verification"] == "PASS" for r in rows))
        self.assertTrue(all(r["machine_generated"] and not r["human_reviewed"] for r in rows))
        self.assertTrue(all(r["label"] == "PRODUCT_AUTOGENERATED" for r in rows))


if __name__ == "__main__":
    unittest.main()
