import collections
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from v2 import contrast_data, data
from v2.common import read_json, read_jsonl, write_json
from v2.contrast_data import NAME, RETRY, plan, twin_check
from lfx import batches
from lfx.synth import normalize_text

# Field set of A/longform/train.jsonl rows, which consolidate.collect already reads.
LONGFORM_KEYS = {
    "case_id", "category", "contrast_group_id", "critical_facts", "destination_profile", "family_id", "focus",
    "gold_lines", "gold_offsets", "human_reviewed", "is_noop", "label", "length", "machine_generated",
    "model_input", "normalization_changed", "normalization_edits", "notes", "obsolete_values", "origin", "pair_id",
    "protected_spans", "provenance", "raw_input", "reject", "relevant_vocabulary", "removed_fillers",
    "scenario_family", "spec_is_noop", "split", "target", "target_claude", "variant", "verification",
    "vocabulary_pairs"}

# (focus, mentions steps or list, twin) -> (transcript, target); the two twins of each pair agree.
TEMPLATES = {
    ("steps", True, "list"): ("here are the steps for the gate step one open the gate step two lock the shed",
                              "Here are the steps for the gate:\n1. Open the gate.\n2. Lock the shed."),
    ("steps", True, "prose"): ("here are the steps for the gate first open the gate second lock the shed",
                               "Here are the steps for the gate. First open the gate. Second lock the shed."),
    ("steps", False, "list"): ("for the gate step one open the gate step two lock the shed. then call me",
                               "For the gate:\n1. Open the gate.\n2. Lock the shed.\nThen call me."),
    ("steps", False, "prose"): ("for the gate first open the gate second lock the shed. then call me",
                                "For the gate first open the gate. Second lock the shed. Then call me."),
    ("items", True, "list"): ("here is my packing list rain jacket headlamp and a spare water filter",
                              "Here is my packing list:\n- rain jacket\n- headlamp\n- a spare water filter"),
    ("items", True, "prose"): ("here is my packing list first rain jacket second headlamp and third a spare water filter",
                               "Here is my packing list. First rain jacket, second headlamp and third a spare water filter."),
    ("items", False, "list"): ("for saturday the shopping list eggs flour and butter. pay with the card",
                               "For Saturday the shopping list:\n- eggs\n- flour\n- butter\nPay with the card."),
    ("items", False, "prose"): ("for saturday we need first eggs second flour and third butter. pay with the card",
                                "For Saturday we need first eggs, second flour and third butter. Pay with the card."),
    ("question", False, "split"): ("can you send me the new rota because i'm off on friday",
                                   "Can you send me the new rota? Because I'm off on Friday."),
    ("question", False, "statement"): ("i was wondering if you could send me the new rota because i'm off on friday",
                                       "I was wondering if you could send me the new rota because I'm off on Friday."),
}


def row(transcript, target, **extra):
    model_input = normalize_text(transcript).text
    return {"model_input": model_input, "target": normalize_text(target).text if model_input != transcript else target,
            **extra}


def twins(focus, mention):
    sides = contrast_data.SIDES[focus]
    return [row(*TEMPLATES[(focus, mention, side)]) for side in sides]


def no_client(*args, **kwargs):
    raise AssertionError("a test reached the real Anthropic client")


def fake_wave(calls, verdict=lambda pair_id: "PASS"):
    """Answer generation from TEMPLATES and verification with verdict(pair_id); record every call."""
    def wave(name, requests, parse, model, purpose):
        calls.append({"name": name, "requests": copy.deepcopy(requests), "model": model, "purpose": purpose})
        outcomes = {}
        for rid, params in requests.items():
            shown = json.loads(params["messages"][0]["content"].split("\n", 1)[1])
            if purpose == "generation":
                value = [{"family_id": s["family_id"], "is_noop": False, "critical_facts": [], "corrections": [],
                          "removed_fillers": [], "vocabulary": [], "notes": "fixture",
                          **dict(zip(("spoken_input", "target"),
                                     TEMPLATES[(s["focus"], s["mentions_steps_or_list"], s["twin"])]))}
                         for s in shown]
            else:
                value = [{"pair_id": p["pair_id"], "verdict": verdict(p["pair_id"]), "reasons": [],
                          "explanation": "fixture"} for p in shown]
            outcomes[rid] = {"status": "succeeded", "value": value, "batch_id": "fixture", "custom_id": rid + "-a1"}
        return SimpleNamespace(outcomes=outcomes, run=lambda **kw: None)
    return wave


def exact_capture(inexact=(), broken=()):
    """Engine capture stand-in: oracle-exact unless the row's case is listed."""
    def capture(row):
        if row["pair_id"] in broken:
            raise ValueError("window_plan_mismatch")
        row.update(protected_spans=[], gold_offsets=[],
                   engine_oracle={"exact": row["pair_id"] not in inexact, "fallback_reason": "validation_rejected:coverage"})
        return {"pair_id": row["pair_id"]}
    return capture


class PlanTests(unittest.TestCase):
    def test_plan_balance(self):
        specs = plan()
        self.assertEqual(specs, plan())
        self.assertEqual(len(specs), 400)
        self.assertEqual(len({s["family_id"] for s in specs}), 400)
        self.assertTrue(all(s["split"] == "train" and s["is_noop"] is False for s in specs))
        self.assertFalse(any(s["category"] == "long_instructions" for s in specs))
        families = collections.Counter(s["focus"] for s in specs[::2])
        self.assertEqual(families, {"steps": 60, "items": 60, "question": 80})
        for first, second in zip(specs[::2], specs[1::2]):
            self.assertEqual(first["contrast_group_id"], second["contrast_group_id"])
            self.assertEqual((first["twin"], second["twin"]), contrast_data.SIDES[first["focus"]])
            for key in ("focus", "length", "destination_profile", "topic_anchors", "technique",
                        "mentions_steps_or_list", "variation"):
                self.assertEqual(first[key], second[key], key)
        mentions = collections.Counter((s["focus"], s["mentions_steps_or_list"]) for s in specs[::2])
        self.assertEqual(mentions, {("steps", True): 30, ("steps", False): 30, ("items", True): 30,
                                    ("items", False): 30, ("question", False): 80})

    def test_retry_keeps_the_plan_and_only_changes_the_wording_seed(self):
        first, retry = plan(NAME), plan(RETRY)
        self.assertEqual([{k: v for k, v in s.items() if k != "variation"} for s in first],
                         [{k: v for k, v in s.items() if k != "variation"} for s in retry])
        self.assertTrue(all(a["variation"] != b["variation"] for a, b in zip(first, retry)))

    def test_domains_are_disjoint_from_every_other_source(self):
        from v2 import longform_data, refinement_data
        used = set(data.DOMAINS) | set(longform_data.DOMAINS) | {d for ds in refinement_data.DOMAINS.values() for d in ds}
        self.assertFalse(set(contrast_data.DOMAINS) & used)
        self.assertEqual({s["topic_anchors"][0] for s in plan()}, set(contrast_data.DOMAINS))


class TwinCheckTests(unittest.TestCase):
    def test_matching_twins_pass(self):
        for focus, mention in [("steps", True), ("steps", False), ("items", True), ("items", False), ("question", False)]:
            with self.subTest(focus=focus, mention=mention):
                self.assertIsNone(twin_check(focus, mention, *twins(focus, mention)))

    def test_question_frame_may_change_the_verb_after_shared_words(self):
        split = row("did the courier from the north depot deliver the parcel, because the camera shows nothing",
                    "Did the courier from the north depot deliver the parcel? Because the camera shows nothing.")
        statement = row("i wonder whether the courier from the north depot delivered the parcel, because the camera shows nothing",
                        "I wonder whether the courier from the north depot delivered the parcel, because the camera shows nothing.")
        self.assertIsNone(twin_check("question", False, split, statement))

    def check(self, focus, mention, side, transcript=None, target=None):
        pair = twins(focus, mention)
        index = contrast_data.SIDES[focus].index(side)
        pair[index] = row(transcript or TEMPLATES[(focus, mention, side)][0], target or TEMPLATES[(focus, mention, side)][1])
        return twin_check(focus, mention, *pair)

    def test_failures_name_the_difference(self):
        cases = [
            (("steps", True, "prose", "here are the steps for the gate first open the door second lock the shed",
              "Here are the steps for the gate. First open the door. Second lock the shed."), "sources_differ_beyond_triggers"),
            (("steps", True, "prose", "here are the steps, for the gate first open the gate second lock the shed",
              "Here are the steps, for the gate. First open the gate. Second lock the shed."), "source_marks_differ"),
            (("steps", True, "list", None, "Here are the steps for the gate\n1. Open the gate.\n2. Lock the shed."),
             "introduction_without_colon"),
            (("steps", False, "list", None, "For the gate:\n1. Open the gate.\n\n2. Lock the shed.\nThen call me."),
             "list_not_one_run"),
            (("steps", False, "list", None, "For the gate:\n1. Open the gate.\n2. Lock the shed.\n\nThen call me."), "blank_line"),
            (("steps", True, "list", None, "Here are the steps for the gate:\n1. Open the gate.\n3. Lock the shed."),
             "numbering_does_not_match_labels"),
            (("steps", True, "list", None, "Here are the steps for the gate:\n1. Open the gate.\n2. Lock."),
             "targets_differ_beyond_triggers"),
            (("steps", True, "prose", None, "Here are the steps for the gate:\n1. Open the gate.\n2. Lock the shed."),
             "ordinal_twin_not_prose"),
            (("steps", True, "prose", None, "Here are the steps for the gate. Open the gate. Second lock the shed."),
             "ordinal_twin_not_prose"),
            (("steps", True, "prose", "here are the steps for the gate step one open the gate step two lock the shed", None),
             "trigger_words_missing"),
            (("steps", True, "list", None, "Here are the steps for the gate:\n1. Open the gate and\n2. Lock the shed."),
             "list_join_kept"),
            (("items", True, "list", None, "Here is my packing list:\n- rain jacket\n- headlamp\n- and a spare water filter"),
             "list_join_kept"),
            (("items", True, "list", None, "Here is my packing list:\n- rain jacket\n- headlamp\n- a water filter"),
             "targets_differ_beyond_triggers"),
            (("items", False, "list", "for saturday grab eggs flour and butter. pay with the card",
              "For Saturday grab:\n- eggs\n- flour\n- butter\nPay with the card."), "introductions_differ_beyond_lead_in"),
            (("question", False, "split", None, "Can you send me the new rota because I'm off on Friday?"),
             "direct_question_not_split"),
            (("question", False, "statement", None, "I was wondering if you could send me the new rota? Because I'm off on Friday."),
             "indirect_question_not_a_statement"),
            (("question", False, "statement", "i was wondering if you could send me the new rota because i'm off on monday", None),
             "question_frames_differ_beyond_opening"),
            (("question", False, "split", "can you send me the new rota because i'm off because of friday",
              "Can you send me the new rota? Because I'm off because of Friday."), "because_not_said_once"),
        ]
        for args, reason in cases:
            with self.subTest(args=args):
                self.assertEqual(self.check(*args), reason)

    def test_prose_and_statement_twins_add_no_punctuation_beyond_their_repairs(self):
        steps = row("for the gate step one open the gate and step two lock the shed",
                    "For the gate:\n1. Open the gate.\n2. Lock the shed.")
        items = row("here is my packing list, rain jacket headlamp and a spare water filter",
                    "Here is my packing list:\n- rain jacket\n- headlamp\n- a spare water filter")
        split = row("can you send me the new rota because i'm off on friday and the shop is shut",
                    "Can you send me the new rota? Because I'm off on Friday and the shop is shut.")
        steps_prose = "for the gate first open the gate and second lock the shed"
        items_prose = "here is my packing list, first rain jacket second headlamp and third a spare water filter"
        statement = "i was wondering if you could send me the new rota because i'm off on friday and the shop is shut"
        cases = [
            ("steps", False, steps, steps_prose, "For the gate first open the gate and second lock the shed.", None),
            ("steps", False, steps, steps_prose, "For the gate first open the gate. And second lock the shed.",
             "prose_adds_sentence_break"),
            ("steps", False, steps, steps_prose, "For the gate first, open the gate and second lock the shed.",
             "prose_adds_comma_at_ordinal"),
            ("items", True, items, items_prose,
             "Here is my packing list, first rain jacket, second headlamp and third a spare water filter.", None),
            ("items", True, items, items_prose,
             "Here is my packing list. First rain jacket, second headlamp and third a spare water filter.",
             "prose_adds_sentence_break"),
            ("items", True, items, items_prose,
             "Here is my packing list, first rain jacket, second headlamp, and third a spare water filter.",
             "prose_adds_comma_at_ordinal"),
            ("question", False, split, statement,
             "I was wondering if you could send me the new rota because I'm off on Friday and the shop is shut.", None),
            ("question", False, split, statement,
             "I was wondering if you could send me the new rota because I'm off on Friday. And the shop is shut.",
             "statement_adds_sentence_break"),
        ]
        for focus, mention, first, transcript, target, reason in cases:
            with self.subTest(target=target):
                self.assertEqual(twin_check(focus, mention, first, row(transcript, target)), reason)

    def test_mentions_must_match_the_plan(self):
        self.assertEqual(twin_check("steps", False, *twins("steps", True)), "mention_does_not_match_plan")
        self.assertEqual(twin_check("items", True, *twins("items", False)), "mention_does_not_match_plan")


class FunnelTests(unittest.TestCase):
    def wave(self):
        """Nine families, each stopped by a different stage except the first."""
        cases = [("steps", True), ("steps", False), ("items", False), ("question", False), ("items", True),
                 ("steps", False), ("steps", False), ("question", False), ("items", False)]
        specs, returned = [], []
        for n, (focus, mention) in enumerate(cases):
            for side, pair in zip(contrast_data.SIDES[focus], twins(focus, mention)):
                fid = f"g{n}-{side}"
                specs.append({"family_id": fid, "contrast_group_id": f"g{n}", "focus": focus, "twin": side,
                              "mentions_steps_or_list": mention})
                returned.append(dict(pair, family_id=fid, pair_id=fid + "-base", reject=[]))
        returned = [r for r in returned if r["family_id"] != "g1-list"]
        next(r for r in returned if r["family_id"] == "g2-prose")["reject"] = ["fact_missing"]
        g5 = next(r for r in returned if r["family_id"] == "g5-list")
        g5["target"] = g5["target"].replace("\nThen", "\n\nThen")
        g6 = next(r for r in returned if r["family_id"] == "g6-prose")
        for field in ("model_input", "target"):
            g6[field] = g6[field].replace("open the gate", "open the door")
        verdicts = {r["pair_id"]: {"verdict": "FAIL" if r["family_id"] == "g3-split" else "PASS",
                                   "reasons": ["punctuation_or_casing_error"] if r["family_id"] == "g3-split" else []}
                    for r in returned if not r["reject"]}
        accepted = {r["family_id"]: r for r in returned if verdicts.get(r["pair_id"], {}).get("verdict") == "PASS"}
        held_out = {" ".join(next(r for r in returned if r["family_id"] == "g4-prose")["target"].casefold().split())}
        return ({"name": NAME, "specs": specs, "returned": returned, "accepted": accepted, "verdicts": verdicts,
                 "statuses": {"g1-list": "truncated"}}, held_out)

    def test_every_row_records_why_it_was_kept_or_dropped(self):
        wave, held_out = self.wave()
        records, kept = contrast_data.funnel(wave, held_out, exact_capture(inexact={"g7-statement-base"},
                                                                           broken={"g8-list-base"}))
        reasons = {r["family_id"]: (r["stage"], r["reason"]) for r in records}
        self.assertEqual(reasons, {
            "g0-list": ("final", "kept"), "g0-prose": ("final", "kept"),
            "g1-list": ("generation", "not_returned:truncated"), "g1-prose": ("generation", "sibling_dropped:generation"),
            "g2-list": ("generation", "sibling_dropped:generation"), "g2-prose": ("generation", "structural:fact_missing"),
            "g3-split": ("verification", "verifier_FAIL:punctuation_or_casing_error"),
            "g3-statement": ("verification", "sibling_dropped:verification"),
            "g4-list": ("held_out", "sibling_dropped:held_out"),
            "g4-prose": ("held_out", "shares_text_with_development_or_final"),
            "g5-list": ("minimal_target", "minimal_target:invented_paragraph"),
            "g5-prose": ("minimal_target", "sibling_dropped:minimal_target"),
            "g6-list": ("twin", "twin:sources_differ_beyond_triggers"),
            "g6-prose": ("twin", "twin:sources_differ_beyond_triggers"),
            "g7-split": ("capture", "sibling_dropped:capture"),
            "g7-statement": ("capture", "oracle_not_exact:validation_rejected:coverage"),
            "g8-list": ("capture", "capture_error:window_plan_mismatch"),
            "g8-prose": ("capture", "sibling_dropped:capture")})
        self.assertEqual(set(kept), {"g0"})
        self.assertEqual([r["family_id"] for r in kept["g0"]], ["g0-list", "g0-prose"])
        verdicts = {r["family_id"]: r["verdict"] for r in records}
        self.assertEqual((verdicts["g1-list"], verdicts["g2-prose"], verdicts["g3-split"], verdicts["g3-statement"]),
                         (None, None, "FAIL", "PASS"))
        oracle = {r["family_id"]: r["oracle_exact"] for r in records}
        self.assertEqual((oracle["g7-split"], oracle["g7-statement"], oracle["g8-prose"], oracle["g6-list"]),
                         (True, False, True, None))
        table = contrast_data.counts(records)["all"]
        self.assertEqual(table, {"planned": 18, "returned": 17, "structurally_valid": 16, "verifier_pass": 15,
                                 "both_twins_pass": 12, "held_out": 10, "minimal_target": 8, "twin": 6,
                                 "oracle_exact": 4, "final": 2})


class PipelineTests(unittest.TestCase):
    def test_submission_budget_counts_paid_retries_and_outstanding_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = SimpleNamespace(messages=SimpleNamespace(batches=SimpleNamespace(
                create=Mock(return_value=SimpleNamespace(id="fixture-batch")))))
            with patch.object(batches, "CLAUDE_DIR", root), patch.object(batches, "LEDGER", root / "ledger.json"), \
                    patch.object(batches, "max_charge", return_value=2.0), \
                    patch.dict(batches.CONFIG["claude"], {"stop_at_usd": 100.0}):
                write_json(root / "ledger.json", {"entries": {
                    "ver-" + NAME + "#a1": {"state": "settled", "actual_usd": 12.0, "max_usd": 12.0},
                    "other-lane#a1": {"state": "settled", "actual_usd": 50.0, "max_usd": 50.0}},
                    "reservations": {}})
                args = ({"request": {"max_tokens": 100}}, lambda text: text, lambda params: 10)
                wave = contrast_data._BudgetedWave(NAME, *args, client_noretry=client, log=lambda text: None)
                wave.submit_pending()
                self.assertEqual(client.messages.batches.create.call_count, 1)
                retry = contrast_data._BudgetedWave(RETRY, *args, client_noretry=client, log=lambda text: None)
                with self.assertRaisesRegex(batches.BudgetExceeded, "lane's"):
                    retry.submit_pending()
                batches._settle(NAME + "#a1", 2.0, {})
                wave.manifest["attempts"][0]["state"] = "collected"
                wave.outcomes = {"request": {"status": "malformed", "attempts": 1}}
                with self.assertRaisesRegex(batches.BudgetExceeded, "lane's"):
                    wave.submit_pending()
                self.assertEqual(client.messages.batches.create.call_count, 1)
                self.assertNotIn(NAME + "#a2", batches.ledger()["entries"])
                with patch.dict(batches.CONFIG["claude"], {"stop_at_usd": 63.0}), \
                        patch.object(batches, "max_charge", return_value=0.5):
                    with self.assertRaisesRegex(batches.BudgetExceeded, "exceeds stop"):
                        wave.submit_pending()

    def test_wave_restores_submission_class_when_generation_fails(self):
        original = data.Wave
        def fail(*args, **kwargs):
            self.assertIs(data.Wave, contrast_data._BudgetedWave)
            raise RuntimeError("fixture generation failure")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(contrast_data, "ART", Path(directory)), \
                patch.object(contrast_data, "_check_budget"), patch.object(data, "generate", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "fixture generation failure"):
                contrast_data._wave(NAME, self.specs(), (0.0, 0.0))
        self.assertIs(data.Wave, original)

    def run_wave(self, root, specs, calls, rates=(0.0, 0.0), guidance="", name=NAME):
        with patch.object(data, "ART", root), patch.object(contrast_data, "ART", root), \
                patch.object(data, "wave", fake_wave(calls)), patch.object(data, "anthropic_client", no_client), \
                patch.object(batches, "LEDGER", root / "claude" / "ledger.json"), contextlib.redirect_stdout(io.StringIO()):
            contrast_data._wave(name, specs, rates, guidance)

    def specs(self, wave=NAME):
        wanted = {"v6-tr-steps-000", "v6-tr-steps-001", "v6-tr-items-000", "v6-tr-items-001", "v6-tr-question-000"}
        return [s for s in plan(wave) if s["contrast_group_id"] in wanted]

    def test_retry_submits_only_complete_missing_families_or_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_wave(root, self.specs(), [])
            for inexact in ((), ("v6-tr-items-001-prose-base",)):
                with self.subTest(inexact=inexact), patch.object(contrast_data, "ART", root), \
                        patch.object(contrast_data, "KINDS", {"steps": 2, "items": 2, "question": 1}), \
                        patch("v2.consolidate._held_out_texts", return_value=set()), \
                        patch("v2.assemble.capture", exact_capture(inexact=inexact)), \
                        patch.object(contrast_data, "_rates", return_value=(0.1, 0.2)) as rates, \
                        patch.object(contrast_data, "_wave") as submit, contextlib.redirect_stdout(io.StringIO()):
                    contrast_data.retry()
                    if inexact:
                        expected = [s for s in plan(RETRY) if s["contrast_group_id"] == "v6-tr-items-001"]
                        self.assertEqual([s["twin"] for s in expected], ["list", "prose"])
                        submit.assert_called_once_with(RETRY, expected, (0.1, 0.2), contrast_data.RETRY_GUIDANCE)
                        rates.assert_called_once_with(NAME)
                    else:
                        submit.assert_not_called()
                        rates.assert_not_called()

    def test_assembly_prefers_the_first_successful_wave_for_each_family(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_wave(root, self.specs(), [])
            self.run_wave(root, self.specs(RETRY), [], name=RETRY)
            retry_path = root / "accepted" / (RETRY + ".jsonl")
            retry_rows = read_jsonl(retry_path)
            for row in retry_rows:
                row["notes"] = "retry fixture"
            contrast_data.write_jsonl(retry_path, retry_rows)
            first_path = root / "accepted" / (NAME + ".jsonl")
            first_rows = read_jsonl(first_path)
            first_rows = [r for r in first_rows if r["family_id"] != "v6-tr-items-001-prose"]
            contrast_data.write_jsonl(first_path, first_rows)
            with patch.object(contrast_data, "ART", root), \
                    patch.object(batches, "LEDGER", root / "claude" / "ledger.json"):
                summary = contrast_data.assemble(held_out=set(), capture=exact_capture())
            self.assertEqual((summary["accepted"], summary["families"]), (10, 5))
            rows = read_jsonl(root / "contrast" / "train.jsonl")
            self.assertEqual({r["family_id"] for r in rows if r["notes"] == "retry fixture"},
                             {"v6-tr-items-001-list", "v6-tr-items-001-prose"})
            receipt = read_json(root / "contrast" / "train.selection.json")
            selected = collections.Counter(r["wave"] for r in receipt["records"] if r["selected"])
            self.assertEqual(selected, {NAME: 8, RETRY: 2})

    def test_one_request_per_family_and_the_contract_is_restored(self):
        gen, verify = data.GEN_SYSTEM, data.VERIFY_SYSTEM
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_wave(root, self.specs(), calls, guidance=contrast_data.RETRY_GUIDANCE)
            accepted = read_jsonl(root / "accepted" / (NAME + ".jsonl"))
        self.assertEqual((data.GEN_SYSTEM, data.VERIFY_SYSTEM), (gen, verify))
        generation, verification = calls
        self.assertEqual((generation["model"], generation["purpose"]), ("claude-sonnet-5-5", "generation"))
        self.assertEqual((verification["model"], verification["purpose"]), ("claude-opus-5-5", "verification"))
        self.assertEqual(len(generation["requests"]), 5)
        for params in generation["requests"].values():
            shown = json.loads(params["messages"][0]["content"].split("\n", 1)[1])
            self.assertEqual(len({s["contrast_group_id"] for s in shown}), 1)
            self.assertEqual([s["twin"] for s in shown], list(contrast_data.SIDES[shown[0]["focus"]]))
            self.assertIn(contrast_data.POLICY, params["system"][0]["text"])
            self.assertTrue(params["system"][0]["text"].endswith(contrast_data.PAIRING + contrast_data.RETRY_GUIDANCE))
        for params in verification["requests"].values():
            self.assertTrue(params["system"][0]["text"].endswith(contrast_data.LEAD_VERIFY + contrast_data.POLICY))
        self.assertEqual(len(accepted), 10)
        self.assertTrue(all(r["contrast_group_id"] and r["focus"] for r in accepted))

    def test_budget_is_checked_before_anything_is_submitted(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "claude" / "ledger.json", {"entries": {
                NAME + "#a1": {"state": "settled", "max_usd": 9.0, "actual_usd": 9.0},
                "ver-" + RETRY + "#a1": {"state": "settled", "max_usd": 5.0, "actual_usd": 5.5},
                "other-lane#a1": {"state": "settled", "max_usd": 50.0, "actual_usd": 50.0}}, "reservations": {}})
            with self.assertRaises(batches.BudgetExceeded):
                self.run_wave(root, self.specs(), calls, rates=(0.06, 0.0))
            with patch.object(batches, "LEDGER", root / "claude" / "ledger.json"):
                self.assertEqual(contrast_data.spend(), {NAME: 9.0, "ver-" + NAME: 0.0, RETRY: 0.0, "ver-" + RETRY: 5.5})
        self.assertEqual(calls, [])

    def test_assembly_writes_longform_rows_with_stable_ids_and_a_record_per_row(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = self.specs()
            self.run_wave(root, specs, calls)
            with patch.object(contrast_data, "ART", root), \
                    patch.object(batches, "LEDGER", root / "claude" / "ledger.json"), \
                    contextlib.redirect_stdout(io.StringIO()):
                summary = contrast_data.assemble(held_out=set(), capture=exact_capture(inexact={"v6-tr-items-001-prose-base"}))
                again = contrast_data.assemble(held_out=set(), capture=exact_capture())
            rows = read_jsonl(root / "contrast" / "train.jsonl")
            receipt = read_json(root / "contrast" / "train.selection.json")
        self.assertEqual(again, {"already_assembled": 8})
        self.assertEqual((summary["accepted"], summary["families"]), (8, 4))
        for r in rows:
            self.assertEqual(set(r), LONGFORM_KEYS)
            self.assertEqual((r["origin"], r["split"], r["verification"]["verdict"]), ("contrast", "train", "PASS"))
        planned = [s["family_id"] for s in specs if s["contrast_group_id"] != "v6-tr-items-001"]
        self.assertEqual([r["family_id"] for r in rows], planned)
        self.assertEqual([r["case_id"] for r in receipt["records"]], [s["family_id"] + "-base" for s in specs])
        self.assertEqual(sum(r["selected"] for r in receipt["records"]), 8)
        self.assertEqual(receipt["final"]["all"], 8)
        self.assertEqual(receipt["by_wave"][NAME]["items/prose"]["oracle_exact"], 1)

    def test_interrupted_receipt_write_cannot_report_assembly_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_wave(root, self.specs(), [])
            with patch.object(contrast_data, "ART", root), \
                    patch.object(batches, "LEDGER", root / "claude" / "ledger.json"), \
                    patch.object(contrast_data, "write_json", side_effect=OSError("fixture receipt failure")):
                with self.assertRaisesRegex(OSError, "fixture receipt failure"):
                    contrast_data.assemble(held_out=set(), capture=exact_capture())
            dest = root / "contrast" / "train.jsonl"
            saved = dest.read_bytes()
            self.assertFalse((root / "contrast" / "train.selection.json").exists())
            with patch.object(contrast_data, "ART", root), \
                    patch("v2.consolidate._held_out_texts", side_effect=AssertionError("unexpected data read")):
                with self.assertRaisesRegex(RuntimeError, "lack a matching selection receipt"):
                    contrast_data.assemble()
            self.assertEqual(dest.read_bytes(), saved)

    def test_assembly_rejects_mismatched_or_orphaned_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_wave(root, self.specs(), [])
            with patch.object(contrast_data, "ART", root), \
                    patch.object(batches, "LEDGER", root / "claude" / "ledger.json"):
                contrast_data.assemble(held_out=set(), capture=exact_capture())
            dest = root / "contrast" / "train.jsonl"
            receipt_path = root / "contrast" / "train.selection.json"
            receipt, saved = read_json(receipt_path), dest.read_bytes()
            with patch.object(contrast_data, "ART", root), \
                    patch("v2.consolidate._held_out_texts", side_effect=AssertionError("unexpected data read")):
                self.assertEqual(contrast_data.assemble(), {"already_assembled": 10})
                for field, value in (("sha256", "mismatch"), ("accepted", 9)):
                    with self.subTest(field=field):
                        write_json(receipt_path, dict(receipt, **{field: value}))
                        with self.assertRaisesRegex(RuntimeError, "lack a matching selection receipt"):
                            contrast_data.assemble()
                        self.assertEqual(dest.read_bytes(), saved)
                receipt_path.write_text("{")
                with self.assertRaisesRegex(RuntimeError, "invalid selection receipt"):
                    contrast_data.assemble()
                dest.unlink()
                with self.assertRaisesRegex(RuntimeError, "without its TRAIN rows"):
                    contrast_data.assemble()
                self.assertEqual(receipt_path.read_text(), "{")


if __name__ == "__main__":
    unittest.main()
