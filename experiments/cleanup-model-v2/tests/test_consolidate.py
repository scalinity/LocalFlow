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


def fake_capture(pair, consistent_only=False):
    """An exact row, or a vetoed row whose cleanup call disagrees with its prompt."""
    exact = pair.get('exact', True)
    pair['engine_oracle'] = {'exact': exact}
    calls = [call('corrections'), call('main')]
    if consistent_only and not exact:
        pair['engine_oracle']['supervision'] = [
            {'role': 'corrections', 'window': [0, 6], 'kept': True, 'why': 'corrections_target_is_gold_lines'},
            {'role': 'main', 'window': [0, 6], 'kept': False, 'why': 'input_is_not_label_pre_cleanup'}]
        calls = calls[:1]
    return {'pair_id': pair['pair_id'], 'family_id': pair['family_id'], 'split': pair['split'], 'calls': calls}


class BuildTests(unittest.TestCase):
    def build(self, root, dataset, **options):
        rows = [row('exact', True), row('vetoed', False)]
        with patch.object(consolidate, 'collect', return_value=(rows, {'kept': 2})), \
                patch.object(consolidate, 'REFINEMENT', root / 'refinement'), \
                patch('v2.refinement.SOURCE_FILES', []), \
                patch('v2.assemble.capture', side_effect=fake_capture) as capture:
            return consolidate.build(dataset, **options), capture

    def test_default_build_keeps_only_exact_rows_and_another_directory_holds_the_consistent_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl', [{**row('dev', True), 'split': 'validation'}])
            freeze, _ = self.build(root, root / 'default')
            self.assertEqual([c['pair_id'] for c in read_jsonl(root / 'default' / 'train_captures.jsonl')], ['exact'])
            self.assertEqual(freeze['stats']['train']['captured'], 1)
            self.assertEqual(freeze['stats']['train']['engine_vetoed_by_focus'], {'restatement': 1})
            self.assertNotIn('supervision', freeze)
            self.assertNotIn('partially_supervised_by_focus', freeze['stats']['train'])

            freeze, _ = self.build(root, root / 'consistent', consistent=True)
            captures = read_jsonl(root / 'consistent' / 'train_captures.jsonl')
            self.assertEqual([(c['pair_id'], [k['role'] for k in c['calls']]) for c in captures],
                             [('exact', ['corrections', 'main']), ('vetoed', ['corrections'])])
            train = freeze['stats']['train']
            self.assertEqual(train['captured'], 2)
            self.assertEqual(train['engine_vetoed_by_focus'], {})
            self.assertEqual(train['partially_supervised_by_focus'], {'restatement': 1})
            self.assertEqual(train['vetoed_row_calls'], {'corrections:corrections_target_is_gold_lines': 1,
                                                         'main:input_is_not_label_pre_cleanup': 1})
            vetoed = read_jsonl(root / 'consistent' / 'train.jsonl')[1]
            self.assertEqual([s['kept'] for s in vetoed['engine_oracle']['supervision']], [True, False])
            self.assertEqual(read_json(root / 'consistent' / 'freeze.json'), freeze)

            # A frozen directory is returned unchanged and never recaptured.
            again, capture = self.build(root, root / 'default', consistent=True)
            self.assertEqual(again['stats']['train']['captured'], 1)
            capture.assert_not_called()



class RestoredConjunctionTests(unittest.TestCase):
    def test_restoration_applies_the_gold_deletions_and_skips_an_unanchored_line(self):
        row = {'case_id': 'c', 'model_input': 'we booked 16 rooms, sorry 17 rooms and before noon we call the hotel',
               'gold_lines': ['16 rooms, sorry']}
        target = 'We booked 17 rooms. Before noon we call the hotel.'
        self.assertEqual(consolidate._restored_conjunctions(row, target),
                         'We booked 17 rooms. And before noon we call the hotel.')
        self.assertIsNone(consolidate._restored_conjunctions({**row, 'gold_lines': ['nine rooms, sorry']}, target))

if __name__ == '__main__':
    unittest.main()
