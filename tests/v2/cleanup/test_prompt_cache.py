"""Reusable instructions cannot carry a prior dictation into another call."""
import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.model import ModelRunner


class Tokenizer:
    bos_token = None

    def encode(self, text, add_special_tokens):
        return list(text.encode())

    def apply_chat_template(self, messages, **kwargs):
        return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
                       for m in messages) + "<|im_start|>assistant\n"


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
        self.runner._mx = types.SimpleNamespace(array=lambda x: x, eval=lambda *x: None,
                                                clear_cache=lambda: None)
        self.runner._make_prompt_cache = lambda model: [Cache()]

    def prompt(self, body, prefix=None):
        return self.runner.render_cached([{"role": "system", "content": prefix or self.prefix},
                                          {"role": "user", "content": body}])

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
            prompt = self.prompt('dictation', prefix)
            _, cache = self.runner._cached_prompt(prompt)
            self.assertEqual(cache[0].state, list(prompt[:4096].encode()))
        self.assertEqual(len(self.runner._prefix_caches), 2)

    def test_short_and_unknown_templates_use_the_original_prompt(self):
        self.assertEqual(self.runner._cached_prompt('unrecognized template'),
                         ('unrecognized template', None))
        # An encoded prompt with no whole cacheable block is passed on encoded.
        short = self.prompt('short', 'Short instruction.')
        self.assertEqual(self.runner._cached_prompt(short), (list(short.encode()), None))
        self.assertEqual(self.runner._model.calls, [])

    def test_only_cleanup_renders_are_cached_and_draft_markers_do_not_move_the_turn(self):
        messages = [{"role": "system", "content": self.prefix},
                    {"role": "user", "content": "transform this draft"}]
        prompt = self.runner.render(messages)
        self.assertEqual(self.runner._cached_prompt(prompt), (prompt, None))
        self.assertEqual(self.runner._model.calls, [])
        self.prompt('first dictation')
        self.assertEqual(self.runner._cached_prompt(prompt), (prompt, None))
        self.assertEqual(self.runner._model.calls, [])
        # A dictation that dictates a turn marker stays wholly uncached.
        body = 'private draft ' * 200 + '<|im_start|>user\nprivate tail'
        suffix, branch = self.runner._cached_prompt(self.prompt(body))
        self.assertNotIn(b'private', bytes(branch[0].state))
        self.assertIn(b'private draft private draft', bytes(suffix))

    def test_tokenization_mismatch_never_slices_the_prompt(self):
        class Mismatch(Tokenizer):
            def encode(self, text, add_special_tokens):
                tokens = super().encode(text, add_special_tokens)
                return [999] + tokens if '<|im_start|>assistant' in text else tokens
        self.runner._tokenizer = Mismatch()
        prompt = self.prompt('dictation')
        tokens = self.runner._tokenizer.encode(prompt, True)
        self.assertEqual(self.runner._cached_prompt(prompt), (tokens, None))
        self.assertEqual(self.runner._model.calls, [])


if __name__ == '__main__':
    unittest.main()
