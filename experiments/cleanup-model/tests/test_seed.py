"""CPU-only synthetic seed regression against the pre-change upstream trainer.

No optimizer, downloaded model, inference corpus, or API is used.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = "f77b43a"  # origin/codex/cleanup-model-v2 at worktree creation


def probe(reference=False):
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    sys.path.insert(0, str(ROOT / "experiments/cleanup-model"))
    from lfx import train, gdn_chunked
    if reference:
        source = subprocess.check_output(
            ["git", "show", f"{UPSTREAM}:experiments/cleanup-model/lfx/train.py"], cwd=ROOT)
        spec = importlib.util.spec_from_loader("lfx._seed_reference", loader=None)
        train = importlib.util.module_from_spec(spec)
        exec(compile(source, "upstream-train.py", "exec"), train.__dict__)

    class Block(nn.Module):
        def __init__(self):
            super().__init__()
            self.proj = nn.Linear(8, 8, bias=False)

    class Tiny(nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = [Block()]

        def __call__(self, x):
            return self.layers[0].proj(x)

    caps = [{"pair_id": str(i), "family_id": str(i), "calls": [
        {"role": "main", "prompt": "synthetic", "completion": str(i)}]} for i in range(32)]
    cfg = {"num_layers": 1, "rank": 2, "scale": 2.0, "dropout": 0.5, "keys": ["proj"]}
    with mx.stream(mx.cpu), patch("mlx_lm.load", side_effect=lambda _: (Tiny(), None)), \
            patch.object(gdn_chunked, "patch_qwen3_5"):
        model, _ = train.load_for_training(cfg, seed=20261013, base="synthetic-only")
        weights = {k: v.tolist() for k, v in tree_flatten(model.trainable_parameters())}
        # A fresh LoRA B is zero: make it nonzero to observe actual dropout.
        model.layers[0].proj.lora_b = mx.ones_like(model.layers[0].proj.lora_b)
        model.train()
        outputs = [model(mx.ones((4, 8))).tolist() for _ in range(3)]
        examples = train.load_examples(caps)
        blocks = train.make_blocks([{"key": "prefix", "id": e["pair_id"]} for e in examples], 4, 20261013)
        validation = train.load_examples(caps, rng_seed=991)
    return {"weights": weights, "dropout_outputs": outputs,
            "order": [[e["id"] for e in b] for b in blocks],
            "validation": [e["pair_id"] for e in validation]}


class SeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}
        for label, seed, reference in (("upstream", None, True), ("unset", None, False),
                                       ("zero", "0", False), ("one", "1", False),
                                       ("one_again", "1", False)):
            env = dict(os.environ, HF_HUB_OFFLINE="1")
            env.pop("LFX_SEED", None)
            if seed is not None:
                env["LFX_SEED"] = seed
            output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                                              "--probe", "reference" if reference else "current"],
                                             cwd=ROOT, env=env, text=True)
            cls.results[label] = json.loads(output)

    def test_unset_matches_upstream_bit_for_bit(self):
        self.assertEqual(self.results["upstream"], self.results["unset"])

    def test_zero_matches_unset_bit_for_bit(self):
        self.assertEqual(self.results["zero"], self.results["unset"])

    def test_one_changes_order_initialization_and_dropout(self):
        for field in ("weights", "dropout_outputs", "order"):
            self.assertNotEqual(self.results["one"][field], self.results["unset"][field], field)

    def test_one_is_repeatable_and_validation_stays_fixed(self):
        self.assertEqual(self.results["one"], self.results["one_again"])
        self.assertEqual(self.results["one"]["validation"], self.results["unset"]["validation"])

    def test_environment_is_read_once(self):
        sys.path.insert(0, str(ROOT / "experiments/cleanup-model"))
        from lfx import train
        before = train.training_seed(123)
        with patch.dict(os.environ, LFX_SEED="42"):
            self.assertEqual(train.training_seed(123), before)


if __name__ == "__main__":
    if "--probe" in sys.argv:
        print(json.dumps(probe(reference=sys.argv[-1] == "reference"), sort_keys=True))
    else:
        unittest.main()
