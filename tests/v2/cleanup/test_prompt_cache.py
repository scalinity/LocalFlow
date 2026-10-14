"""Reusable instructions cannot carry a prior dictation into another call."""
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.model import ModelRunner


class Tokenizer:
    bos_token = None

    def encode(self, text, add_special_tokens):
        return list(text.encode())


class Cache:
    def __init__(self):
        self.state = []


class Model:
    def __init__(self):
        self.calls = []

    def __call__(self, tokens, cache):
        self.calls.append(list(tokens[0]))
        cache[0].state.extend(tokens[0])


class PromptCacheTests(unittest.TestCase):
    def setUp(self):
        self.runner = ModelRunner('fixture')
        self.runner._model = Model()
        self.runner._tokenizer = Tokenizer()
        self.prefix = 'Shared instruction. ' * 240
        modules = {
            'mlx.core': types.SimpleNamespace(array=lambda x: x, eval=lambda *x: None, clear_cache=lambda: None),
            'mlx_lm.models.cache': types.SimpleNamespace(make_prompt_cache=lambda model: [Cache()]),
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def prompt(self, body, prefix=None):
        return (prefix or self.prefix) + '<|im_start|>user\n' + body + '<|im_start|>assistant\n'

    def test_final_dictation_is_never_cached_or_reused(self):
        first = self.prompt('private alpha dictation')
        suffix, branch = self.runner._cached_prompt(first)
        calls = len(self.runner._model.calls)
        self.assertGreater(calls, 0)
        self.assertTrue(all(len(c) == 2048 for c in self.runner._model.calls))
        self.assertNotIn(b'private', bytes(branch[0].state))
        self.assertIn(b'private alpha', bytes(suffix))
        branch[0].state.extend(b'private generated suffix')
        suffix2, branch2 = self.runner._cached_prompt(self.prompt('private beta dictation'))
        self.assertEqual(len(self.runner._model.calls), calls)
        self.assertNotIn(b'private', bytes(branch2[0].state))
        self.assertIn(b'private beta', bytes(suffix2))
        self.assertNotIn(b'private alpha', bytes(suffix2))
        self.assertIsNot(branch[0], branch2[0])

    def test_changed_instruction_selects_different_cache_and_bound_is_finite(self):
        for prefix in ('A' * 5000, 'B' * 5000, 'C' * 5000):
            _, cache = self.runner._cached_prompt(self.prompt('dictation', prefix))
            self.assertEqual(cache[0].state, list(prefix[:4096].encode()))
        self.assertEqual(len(self.runner._prefix_caches), 2)

    def test_short_and_unknown_templates_use_the_original_prompt(self):
        for prompt in ('unrecognized template', '<|im_start|>user\nshort'):
            self.assertEqual(self.runner._cached_prompt(prompt), (prompt, None))
        self.assertEqual(self.runner._model.calls, [])

    def test_tokenization_mismatch_never_slices_the_prompt(self):
        class Mismatch(Tokenizer):
            def encode(self, text, add_special_tokens):
                tokens = super().encode(text, add_special_tokens)
                return [999] + tokens if '<|im_start|>assistant' in text else tokens
        self.runner._tokenizer = Mismatch()
        prompt = self.prompt('dictation')
        self.assertEqual(self.runner._cached_prompt(prompt), (prompt, None))
        self.assertEqual(self.runner._model.calls, [])


if __name__ == '__main__':
    unittest.main()
