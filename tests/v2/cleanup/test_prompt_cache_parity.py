"""Opt-in: cached-prefix generation yields the uncached generator's tokens.

Loads the real cleanup model, so it is skipped unless enabled:

    LOCALFLOW_PREFIX_CACHE_PARITY=1 .venv/bin/python -m unittest \
        tests.v2.cleanup.test_prompt_cache_parity

LOCALFLOW_PARITY_MODEL overrides the model. Token identity depends on the
prefix being whole PREFILL_STEP blocks and on mlx-lm's prefill loop, which
is not pinned, so each run reports the mlx-lm version it checked.
"""
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup import prompts
from localflow.v2.cleanup.engine import CORRECTIONS_EXAMPLES, CORRECTIONS_INSTRUCTION
from localflow.v2.cleanup.model import PREFILL_STEP, ModelRunner

MODEL = os.environ.get("LOCALFLOW_PARITY_MODEL", "mlx-community/Qwen3-4B-Instruct-2507-4bit")
TOKENS = 48
PARAGRAPH = (
    "The night shift checks the boiler gauge every 2 hours and writes the reading "
    "in the blue log, then confirms the valve is closed before handing over. If the "
    "pressure is above 3 bar, call the on-call engineer and do not restart the pump "
    "until the reading settles. ")


@unittest.skipUnless(os.environ.get("LOCALFLOW_PREFIX_CACHE_PARITY") == "1",
                     "set LOCALFLOW_PREFIX_CACHE_PARITY=1 to load the model")
class PrefixCacheParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mlx_lm
        cls.version = mlx_lm.__version__
        cls.runner = ModelRunner(MODEL)
        cls.runner.load()

    def cleanup_messages(self, transcript):
        payload = {"mode": "clean", "locale": "en-US", "destination_profile": None,
                   "relevant_vocabulary": [],
                   "structure_hints": prompts.structure_hints(None),
                   "transcript": transcript}
        return prompts.build_messages(payload)

    def corrections_messages(self, transcript):
        messages = [{"role": "system", "content": CORRECTIONS_INSTRUCTION}]
        for raw, out in CORRECTIONS_EXAMPLES:
            messages += [{"role": "user", "content": raw},
                         {"role": "assistant", "content": out}]
        messages.append({"role": "user", "content": transcript})
        return messages

    def uncached(self, prompt):
        from mlx_lm.generate import stream_generate
        from mlx_lm.sample_utils import make_sampler
        return [r.token for r in stream_generate(
            self.runner._model, self.runner._tokenizer, prompt=prompt,
            max_tokens=TOKENS, sampler=make_sampler(temp=0.0),
            prefill_step_size=PREFILL_STEP)]

    def test_cached_generation_matches_uncached_tokens(self):
        cases = {
            "short cleanup": self.cleanup_messages(
                "um so send the report to mira by friday no wait by thursday"),
            "long cleanup": self.cleanup_messages(PARAGRAPH * 40),
            "corrections": self.corrections_messages(
                "set the timer for 20 minutes no wait 25 minutes"),
        }
        tokens = {name: len(self.runner._tokenizer.encode(self.runner.render(m)))
                  for name, m in cases.items()}
        self.assertGreater(tokens["long cleanup"], 2 * PREFILL_STEP)
        print(f"\nmlx_lm {self.version}; prompt tokens {tokens}")
        for name, messages in cases.items():
            with self.subTest(prompt=name):
                prompt = self.runner.render_cached(messages)
                expected = self.uncached(prompt)
                self.runner._prefix_caches.clear()
                for attempt in ("cold", "warm"):
                    got = [r.token for r in self.runner.stream(prompt, TOKENS)]
                    self.assertEqual(got, expected, f"{name} {attempt}, mlx_lm {self.version}")
                # The cleanup prefix spans a whole block; the corrections one does not.
                self.assertEqual(len(self.runner._prefix_caches), 0 if name == "corrections" else 1)


if __name__ == "__main__":
    unittest.main()
