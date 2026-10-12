"""Response-only masking and the truncation guard, with the real Qwen3.5
tokenizer and an exact engine-rendered prompt."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx import train  # noqa: E402
from lfx.capture import capture, tokenizer  # noqa: E402
from lfx.synth import prepare_family  # noqa: E402

FAMILY = {"family_id": "m1", "spoken_input": "Um, book the room for Tuesday, no wait, Thursday at 3 and tell Priya.",
          "target": "Book the room for Thursday at 3 and tell Priya.", "is_noop": False,
          "critical_facts": [{"text": "Thursday", "kind": "date_time"}, {"text": "Priya", "kind": "name"}],
          "corrections": [{"deleted_span": "Tuesday, no wait", "obsolete_value": "Tuesday", "marker": "no wait",
                           "replacement": "Thursday"}], "removed_fillers": ["Um"], "vocabulary": [], "notes": ""}
SPEC = {"split": "train", "category": "self_correction_single", "destination_profile": "messaging",
        "length": "short", "is_noop": False}


class MaskingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = tokenizer("qwen35")
        pair = prepare_family(FAMILY, SPEC)
        cls.cap = capture(pair)
        assert cls.cap["accepted"], cls.cap["reject"]

    def check(self, call):
        ex = {"prompt": call["prompt"], "completion": call["completion"]}
        tokens, off = train.encode_example(self.tok, ex)
        batch, lengths = train.make_batch(tokens, off)
        mask = train.loss_mask(lengths, batch.shape[1] - 1)
        targets = batch[0, 1:].tolist()
        scored = [t for t, m in zip(targets, mask[0].tolist()) if m]
        self.assertEqual(self.tok.decode(scored), call["completion"] + "<|im_end|>")
        # Nothing from the prompt and no padding is scored.
        self.assertEqual(len(scored), len(tokens) - off)
        self.assertEqual(sum(mask[0].tolist()), len(tokens) - off)
        # Prompt ends with the non-thinking generation prefix.
        self.assertTrue(call["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"))
        self.assertEqual(tokens[:off], train.encode_prompt(self.tok, call["prompt"]))

    def test_both_roles_mask_exactly_the_completion(self):
        roles = [c["role"] for c in self.cap["calls"]]
        self.assertEqual(roles, ["corrections", "main"])
        for call in self.cap["calls"]:
            self.check(call)

    def test_default_mlx_lm_mask_scores_one_pad_position(self):
        """Documents why response_loss differs from mlx-lm 0.31.3's default."""
        import mlx.core as mx
        call = self.cap["calls"][-1]
        tokens, off = train.encode_example(self.tok, {"prompt": call["prompt"], "completion": call["completion"]})
        batch, lengths = train.make_batch(tokens, off)
        steps = mx.arange(1, batch.shape[1])
        default = mx.logical_and(steps >= lengths[:, 0:1], steps <= lengths[:, 1:])
        self.assertEqual(int(default.sum().item()), len(tokens) - off + 1)

    def test_truncation_guard(self):
        ex = [{"prompt": "x " * 50, "completion": "y"}]
        with self.assertRaises(ValueError):
            train.train_loop(None, self.tok, ex, [], Path("/nonexistent"), lr=1e-4, warmup=1, grad_accum=1,
                             checkpoints=1, max_seq_length=10, lora_cfg={})

    def test_role_caps(self):
        caps = [{"pair_id": f"p{i}", "family_id": f"f{i}", "calls": [
            {"role": "corrections", "prompt": "a", "completion": "NONE" if i % 2 else "x no wait"},
            {"role": "main", "prompt": "b", "completion": "c"}]} for i in range(100)]
        ex = train.load_examples(caps)
        corr = [e for e in ex if e["role"] == "corrections"]
        self.assertLessEqual(len(corr) / len(ex), 0.25 + 1e-9)
        self.assertEqual(sum(e["role"] == "main" for e in ex), 100)


if __name__ == "__main__":
    unittest.main()
