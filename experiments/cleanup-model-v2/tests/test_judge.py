import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import judge
from v2.common import file_sha256, read_jsonl, write_json, write_jsonl


class JudgeRecoveryTests(unittest.TestCase):
    def test_missing_output_retry_preserves_known_verdicts_and_resumes(self):
        cached = {}
        submitted = []
        expected = {}
        known_id = None

        def verdict(oid, reason):
            return dict(output_id=oid, semantic_damage=False,
                        critical_fact_changed=False, hallucination=False,
                        unwanted_edit=False, cleanup='complete',
                        punctuation='unchanged_ok', self_correction='not_applicable',
                        reason=reason)

        def fake_wave(name, requests, *args):
            nonlocal known_id
            if name in cached:
                self.assertEqual(requests, cached[name][0])
                return SimpleNamespace(outcomes=cached[name][1], run=lambda **kw: None)
            submitted.append(name)
            outcomes = {}
            for rid, params in requests.items():
                outputs = json.loads(params['messages'][0]['content'])['outputs']
                ids = sorted(r['output_id'] for r in outputs)
                if name == 'final-judge':
                    known_id = ids[0]
                    values = [verdict(oid, 'original') for oid in ids[:-1]]
                    expected.update({v['output_id']: v for v in values})
                else:
                    self.assertEqual(len(ids), 1)
                    self.assertNotIn(ids[0], expected)
                    values = [verdict(ids[0], 'recovered')]
                    expected[ids[0]] = values[0]
                    # A retry must not replace a known verdict, even if returned.
                    values.append(verdict(known_id, 'unexpected replacement'))
                outcomes[rid] = {'status': 'succeeded', 'value': values}
            cached[name] = (copy.deepcopy(requests), outcomes)
            return SimpleNamespace(outcomes=outcomes, run=lambda **kw: None)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root/'cases.jsonl'
            write_jsonl(cases, [{'case_id': 'case1', 'split': 'test', 'origin': 'synthetic',
                                'model_input': 'Keep alpha.', 'target': 'Keep alpha.',
                                'is_noop': True}])
            write_jsonl(root/'eval/final-C.jsonl', [
                {'case_id': 'case1', 'delivered': 'Keep alpha.', 'model_only': 'Keep alpha.'}])
            write_jsonl(root/'eval/final-D.jsonl', [
                {'case_id': 'case1', 'delivered': 'Keep beta.', 'model_only': 'Keep gamma.'}])
            with patch.object(judge, 'ART', root), patch.object(judge, 'wave', fake_wave), contextlib.redirect_stdout(io.StringIO()):
                judge.run(cases, ['C', 'D'])
                first = read_jsonl(root/'judge/verdicts.jsonl')
                judge.run(cases, ['C', 'D'])
                second = read_jsonl(root/'judge/verdicts.jsonl')
            self.assertEqual(submitted, ['final-judge', 'final-judge-missing-1'])
            self.assertEqual(first, second)
            self.assertEqual(len(first), 4)
            self.assertTrue(all(row['status'] == 'judged' for row in first))
            for row in first:
                self.assertEqual(row['verdict'], expected[row['verdict']['output_id']])

    def test_duplicate_and_unrequested_output_ids_are_not_accepted(self):
        outcomes = {'r': {'status': 'succeeded', 'value': [
            {'output_id': 'a'}, {'output_id': 'a'},
            {'output_id': 'b'}, {'output_id': 'unrequested'}]}}
        self.assertEqual(judge.valid_verdicts(outcomes, {'r': {'a', 'b'}}),
                         {'b': {'output_id': 'b'}})



def complete_wave(calls):
    """A wave that answers every requested output and records how it was called."""
    def fake_wave(name, requests, parse, model, purpose):
        calls.append({'name': name, 'requests': copy.deepcopy(requests), 'model': model})
        outcomes = {rid: {'status': 'succeeded', 'value': [
            {'output_id': r['output_id']} for r in json.loads(params['messages'][0]['content'])['outputs']]}
            for rid, params in requests.items()}
        return SimpleNamespace(outcomes=outcomes, run=lambda **kw: None)
    return fake_wave


class JudgeIdentityTests(unittest.TestCase):
    def judge(self, root, prefix, wave=None, **kwargs):
        calls = []
        split = 'test' if prefix in ('final', 'fresh') else 'validation'
        cases = root / f'{prefix}-cases.jsonl'
        write_jsonl(cases, [{'case_id': 'case1', 'split': split, 'origin': 'synthetic', 'model_input': 'Keep alpha.',
                             'target': 'Keep alpha.', 'is_noop': True, 'vocabulary_pairs': [['alfa', 'alpha']]}])
        write_jsonl(root / f'eval/{prefix}-C.jsonl', [{'case_id': 'case1', 'delivered': 'Keep alpha.', 'model_only': 'Keep alpha'}])
        if prefix == 'fresh':
            write_json(root / 'remediation/freeze.json', {'cases_sha256': file_sha256(cases)})
        with patch.object(judge, 'ART', root), patch.object(judge, 'wave', wave or complete_wave(calls)), \
                contextlib.redirect_stdout(io.StringIO()):
            judge.run(cases, ['C'], prefix, prefix + '-judge', **kwargs)
        identity = json.loads((root / f'judge/{prefix}-judge/identity.json').read_text()) \
            if prefix != 'final' else json.loads((root / 'judge/identity.json').read_text())
        return calls, identity

    def test_prompt_states_rules_only_in_terms_of_the_view(self):
        with tempfile.TemporaryDirectory() as directory:
            calls, _ = self.judge(Path(directory), 'dev')
        view = json.loads(calls[0]['requests']['dev-judge-0000']['messages'][0]['content'])
        self.assertEqual(set(view), {'source', 'outputs', 'vocabulary', 'reference', 'is_noop'})
        for field in view:
            self.assertIn(field, judge.SYSTEM)
        for absent in ('protected', 'window', 'accepted correction'):
            self.assertNotIn(absent, judge.SYSTEM.lower())

    def test_judge_model_follows_role_and_is_recorded(self):
        for prefix, kwargs, role, model in (
                ('dev', {}, 'development', 'claude-opus-5-5'),
                ('final', {}, 'final', 'claude-sonnet-5-5'),
                ('fresh', {}, 'final', 'claude-sonnet-5-5'),
                ('dev', {'role': 'final'}, 'final', 'claude-sonnet-5-5'),
                ('dev', {'model': 'claude-haiku-5-5'}, 'development', 'claude-haiku-5-5')):
            with self.subTest(prefix=prefix, kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                calls, identity = self.judge(Path(directory), prefix, **kwargs)
                self.assertEqual([c['model'] for c in calls], [model])
                self.assertEqual({r['model'] for r in calls[0]['requests'].values()}, {model})
                self.assertEqual((identity['role'], identity['judge_model']), (role, model))

    def test_receipts_survive_a_refused_change_to_a_recorded_wave(self):
        recorded = {}
        answer = complete_wave([])

        def guarded_wave(name, requests, parse, model, purpose):
            # Like batches.Wave: a recorded name refuses a different request set.
            if recorded.setdefault(name, copy.deepcopy(requests)) != requests:
                raise RuntimeError('requests changed since the manifest was written')
            return answer(name, requests, parse, model, purpose)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.judge(root, 'dev', guarded_wave)
            receipts = {n: (root / 'judge/dev-judge' / n).read_bytes() for n in ('blind-map.json', 'identity.json')}
            with self.assertRaisesRegex(RuntimeError, 'requests changed'):
                self.judge(root, 'dev', guarded_wave, model='claude-haiku-5-5')
            for n, content in receipts.items():
                self.assertEqual((root / 'judge/dev-judge' / n).read_bytes(), content)

if __name__ == '__main__':
    unittest.main()
