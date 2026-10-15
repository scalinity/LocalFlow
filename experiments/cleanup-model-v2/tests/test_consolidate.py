import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2 import consolidate
from v2.common import read_json, read_jsonl, write_jsonl


def row(case_id, exact):
    return {'case_id': case_id, 'pair_id': case_id, 'family_id': case_id, 'split': 'train', 'focus': 'restatement',
            'model_input': 'source', 'target': 'target', 'exact': exact}


def call(role):
    return {'role': role, 'prompt': 'prompt', 'completion': 'NONE' if role == 'corrections' else 'target',
            'max_tokens': 8, 'window': [0, 6]}


def fake_capture(pair):
    pair['engine_oracle'] = {'exact': pair.get('exact', True)}
    return {'pair_id': pair['pair_id'], 'family_id': pair['family_id'], 'split': pair['split'],
            'calls': [call('corrections'), call('main')]}


class BuildTests(unittest.TestCase):
    def build(self, root, dataset):
        rows = [row('exact', True), row('vetoed', False)]
        with patch.object(consolidate, 'collect', return_value=(rows, {'kept': 2})), \
                patch.object(consolidate, 'REFINEMENT', root / 'refinement'), \
                patch('v2.refinement.SOURCE_FILES', []), \
                patch('v2.assemble.capture', side_effect=fake_capture) as capture:
            return consolidate.build(dataset), capture

    def test_build_writes_another_directory_and_keeps_only_exact_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl', [{**row('dev', True), 'split': 'validation'}])
            freeze, _ = self.build(root, root / 'next')
            self.assertEqual([c['pair_id'] for c in read_jsonl(root / 'next' / 'train_captures.jsonl')], ['exact'])
            self.assertEqual(freeze['stats']['train']['captured'], 1)
            self.assertEqual(freeze['stats']['train']['engine_vetoed_by_focus'], {'restatement': 1})
            self.assertEqual(read_json(root / 'next' / 'freeze.json'), freeze)
            # A frozen directory is returned unchanged and never recaptured.
            again, capture = self.build(root, root / 'next')
            self.assertEqual(again, freeze)
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
