"""Small CPU models exercise real MLX caches and the stream adapter.

No downloaded weights, audio, or personal text are used.
"""
import codecs
import contextlib
import copy
import importlib
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

# The cleanup suite loads without MLX (model.py); only these cases need it.
HAVE_MLX = all(importlib.util.find_spec(name) for name in ('mlx', 'mlx_lm'))
if HAVE_MLX:
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.models.qwen3_5 import TextModel, TextModelArgs
    from mlx_lm.tokenizer_utils import TokenizerWrapper

from localflow.v2.cleanup.lookup import stream_lookup, verified_tokens


@unittest.skipUnless(HAVE_MLX, 'MLX is not installed')
class LookupMLXTests(unittest.TestCase):
    def test_rejected_draft_restores_real_recurrent_and_attention_caches(self):
        with mx.stream(mx.cpu):
            mx.random.seed(17)
            model = TextModel(TextModelArgs(model_type='qwen3_5', hidden_size=32,
                intermediate_size=64, num_hidden_layers=2, num_attention_heads=2,
                num_key_value_heads=1, head_dim=16, vocab_size=32,
                linear_num_value_heads=2, linear_num_key_heads=1,
                linear_key_head_dim=8, linear_value_head_dim=8,
                full_attention_interval=2))
            model.train()  # CPU recurrent operations, without a Metal kernel.
            prefix = make_prompt_cache(model)
            def step(model, cache, tokens):
                logits = model(mx.array([tokens]), cache=cache)[0]
                return mx.argmax(logits - mx.logsumexp(logits, axis=-1, keepdims=True), axis=-1).tolist()
            def evaluate(model, cache, tokens):
                model(mx.array([tokens]), cache=cache)
                mx.eval([c.state for c in cache])
            first = step(model, prefix, [4, 5])[-1]
            frozen = [[None if a is None else a.tolist() for a in c.state] for c in prefix]
            baseline = [first]
            baseline_cache = copy.deepcopy(prefix)
            for _ in range(15):
                baseline.append(step(model, baseline_cache, [baseline[-1]])[0])
            stats = {}
            # Force a proposal that agrees twice and then differs, even if
            # the untrained model happens to repeat a token indefinitely.
            def wrong(history, source, width):
                start = len(history)
                draft = baseline[start:start + width]
                if len(draft) > 2:
                    draft[2] = (draft[2] + 1) % 32
                return draft
            with patch('localflow.v2.cleanup.lookup.propose', side_effect=wrong):
                got = list(verified_tokens(model, copy.deepcopy(prefix), first, [],
                    max_tokens=16, eos_ids=set(), step=step, evaluate=evaluate, stats=stats))
            self.assertEqual(got, baseline)
            self.assertGreater(stats['replay_rounds'], 0)
            self.assertGreater(stats['accepted_tokens'], 0)
            self.assertEqual(frozen, [[None if a is None else a.tolist() for a in c.state] for c in prefix])
            gen = importlib.import_module('mlx_lm.generate')
            def fallback(model, cache, pending, remaining):
                for token, _ in gen.generate_step(mx.array([pending]), model,
                        prompt_cache=cache, max_tokens=remaining):
                    yield token
            with patch.object(gen, 'generation_stream', mx.new_stream(mx.cpu)):
                got = list(verified_tokens(model, copy.deepcopy(prefix), first, [],
                    max_tokens=16, eos_ids=set(), step=step, evaluate=evaluate,
                    stats=stats, fallback=fallback))
            self.assertEqual(got, baseline)
            self.assertEqual(stats['fallbacks'], 1)

    def test_adapter_matches_library_for_eos_limits_and_utf8_boundaries(self):
        gen = importlib.import_module('mlx_lm.generate')
        class Buffered:
            def reset(self):
                self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
                self.last_segment = ''
            def __init__(self):
                self.reset()
            def add_token(self, token):
                self.last_segment = self.decoder.decode({1:b'\xe2', 2:b'\x82', 3:b'\xac'}[(token - 1) % 3 + 1])
            def finalize(self):
                self.last_segment += self.decoder.decode(b'', final=True)
        class Tokenizer(TokenizerWrapper):
            def __init__(self):
                pass
            @property
            def eos_token_ids(self):
                return {0}
            @property
            def detokenizer(self):
                return Buffered()
        class Scripted(nn.Module):
            def __call__(self, inputs, cache=None):
                following = mx.array([0] + list(range(2, 13)) + [0, 1])[inputs]
                return mx.eye(14)[following] * 100
        tok, model = Tokenizer(), Scripted()
        runner = types.SimpleNamespace(_model=model, _tokenizer=tok,
                                      _make_prompt_cache=lambda _: [])
        with patch.object(gen, 'generation_stream', mx.new_stream(mx.cpu)), \
                patch.object(gen, 'wired_limit', lambda *a: contextlib.nullcontext()):
            for budget in (1, 2, 3, 4, 8, 16):
                for draft in ([], [1, 2, 3, 0], [1, 4, 3, 0]):
                    with self.subTest(budget=budget, draft=draft):
                        expected = list(gen.stream_generate(model, tok, [13], max_tokens=budget, prompt_cache=[]))
                        actual = list(stream_lookup(runner, [13], [], draft, budget))
                        fields = lambda rows: [(r.text, r.token, r.finish_reason, r.generation_tokens) for r in rows]
                        self.assertEqual(fields(actual), fields(expected))
                        if not draft and budget > 4:
                            self.assertEqual(runner.lookup_stats['fallbacks'], 1)


if __name__ == '__main__':
    unittest.main()
