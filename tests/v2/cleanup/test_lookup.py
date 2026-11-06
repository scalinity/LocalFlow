"""Target verification, recurrent-cache rollback and output boundaries."""
import unittest
import copy

from localflow.v2.cleanup.lookup import propose, verified_tokens


class LookupTests(unittest.TestCase):
    def generate(self, target, source, limit=100):
        calls, replays = [], []

        def step(model, cache, tokens):
            predictions = []
            for token in tokens:
                cache.append(token)
                # An independently defined target sequence: a rejected
                # proposal poisons later predictions unless rolled back.
                predictions.append(target[len(cache)] if (
                    cache == target[:len(cache)] and len(cache) < len(target)
                ) else 999)
            calls.append(list(cache))
            return predictions

        def evaluate(model, cache, tokens):
            cache.extend(tokens)
            replays.append(list(cache))
            self.assertEqual(cache, target[:len(cache)])

        result = list(verified_tokens(
            None, [], target[0], source, max_tokens=limit, eos_ids={0},
            step=step, evaluate=evaluate))
        self.assertEqual(result, target[:limit])
        return calls, replays

    def test_full_acceptance_uses_one_verification(self):
        calls, replays = self.generate([1, 2, 3, 4, 0], [1, 2, 3, 4])
        self.assertEqual(len(calls), 1)
        self.assertEqual(replays, [])

    def test_partial_rejection_restores_recurrent_state(self):
        _, replays = self.generate([1, 2, 3, 4, 0], [1, 2, 99, 4])
        self.assertEqual(replays[0], [1, 2])

    def test_first_proposal_rejection(self):
        _, replays = self.generate([1, 2, 3, 0], [1, 99, 3])
        self.assertEqual(replays[0], [1])

    def test_eos_in_draft_does_not_publish_suffix(self):
        self.generate([1, 2, 0], [1, 2, 0, 99])

    def test_limits_and_empty_draft(self):
        for limit in (1, 2, 3, 4, 5, 100):
            for draft in ([], [1, 2, 3, 4], [1, 99, 3, 4]):
                with self.subTest(limit=limit, draft=draft):
                    self.generate([1, 2, 3, 4, 0], draft, limit)

    def test_first_token_eos(self):
        calls, _ = self.generate([0], [0, 1, 2])
        self.assertEqual(calls, [])

    def test_longest_suffix_disambiguates_repeated_tokens(self):
        self.assertEqual(propose([7, 1, 2], [1, 2, 9, 7, 1, 2, 3]), [3])

    def test_exception_consumes_private_branch_only(self):
        def step(model, cache, tokens):
            cache.extend(tokens)
            raise RuntimeError("synthetic model failure")
        prefix = []
        cache = copy.deepcopy(prefix)
        gen = verified_tokens(None, cache, 1, [1, 2], max_tokens=5,
                              eos_ids={0}, step=step, evaluate=lambda *a: None)
        self.assertEqual(next(gen), 1)
        with self.assertRaises(RuntimeError):
            next(gen)
        self.assertNotEqual(cache, [])
        self.assertEqual(prefix, [])

    def test_three_misses_resume_ordinary_decoder_at_current_cache(self):
        calls = []
        def step(model, cache, tokens):
            out = []
            for token in tokens:
                cache.append(token)
                out.append(token + 1)
            return out
        def fallback(model, cache, pending, remaining):
            calls.append((list(cache), pending, remaining))
            yield from range(pending + 1, pending + 1 + remaining)
        stats = {}
        got = list(verified_tokens(None, [], 1, [], max_tokens=7,
            eos_ids={0}, step=step, evaluate=lambda *a: None,
            stats=stats, fallback=fallback))
        self.assertEqual(got, list(range(1, 8)))
        self.assertEqual(calls, [([1, 2, 3], 4, 3)])
        self.assertEqual(stats['disabled'], 1)


if __name__ == '__main__':
    unittest.main()
