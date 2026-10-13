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
from v2.common import read_jsonl, write_jsonl


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


if __name__ == '__main__':
    unittest.main()
