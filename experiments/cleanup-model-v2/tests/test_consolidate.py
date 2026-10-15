import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2 import consolidate
from v2.common import read_json, read_jsonl, write_json, write_jsonl


def row(case_id, exact):
    return {'case_id': case_id, 'pair_id': case_id, 'family_id': case_id, 'split': 'train', 'focus': 'restatement',
            'model_input': 'source', 'target': 'target', 'exact': exact}


def call(role):
    return {'role': role, 'prompt': 'prompt', 'completion': 'NONE' if role == 'corrections' else 'target',
            'max_tokens': 8, 'window': [0, 6]}


def fake_capture(pair, consistent_only=False):
    """An exact row, or a vetoed row whose cleanup call disagrees with its prompt."""
    if pair['case_id'] == 'failed':
        raise ValueError('fixture_capture_failure')
    exact = pair.get('exact', True)
    pair['engine_oracle'] = {'exact': exact}
    calls = [call('corrections'), call('main')]
    if consistent_only and not exact and pair['case_id'] == 'nothing':
        pair['engine_oracle']['supervision'] = [
            {'role': 'main', 'window': [0, 6], 'kept': False, 'why': 'input_is_not_label_pre_cleanup'}]
        calls = []
    elif consistent_only and not exact:
        pair['engine_oracle']['supervision'] = [
            {'role': 'corrections', 'window': [0, 6], 'kept': True, 'why': 'gold_lines_applied_by_engine'},
            {'role': 'main', 'window': [0, 6], 'kept': False, 'why': 'input_is_not_label_pre_cleanup'}]
        calls = calls[:1]
    return {'pair_id': pair['pair_id'], 'family_id': pair['family_id'], 'split': pair['split'], 'calls': calls}


class BuildTests(unittest.TestCase):
    def build(self, root, dataset, rows=None, defects=(), **options):
        rows = rows or [row('exact', True), row('vetoed', False)]
        write_jsonl(root / 'label-defects.jsonl', list(defects))
        with patch.object(consolidate, 'collect', return_value=(rows, {'kept': len(rows)})), \
                patch.object(consolidate, 'REFINEMENT', root / 'refinement'), \
                patch.object(consolidate, 'LABEL_DEFECTS', root / 'label-defects.jsonl'), \
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
            self.assertEqual(freeze['mode'], 'exact')
            self.assertNotIn('supervision', freeze)
            self.assertNotIn('partially_supervised_by_focus', freeze['stats']['train'])

            freeze, _ = self.build(root, root / 'consistent', consistent=True)
            self.assertEqual(freeze['mode'], 'consistent')
            captures = read_jsonl(root / 'consistent' / 'train_captures.jsonl')
            self.assertEqual([(c['pair_id'], [k['role'] for k in c['calls']]) for c in captures],
                             [('exact', ['corrections', 'main']), ('vetoed', ['corrections'])])
            train = freeze['stats']['train']
            self.assertEqual(train['captured'], 2)
            self.assertEqual(train['engine_vetoed_by_focus'], {})
            self.assertEqual(train['partially_supervised_by_focus'], {'restatement': 1})
            self.assertEqual(train['vetoed_row_calls'], {'corrections:gold_lines_applied_by_engine': 1,
                                                         'main:input_is_not_label_pre_cleanup': 1})
            vetoed = read_jsonl(root / 'consistent' / 'train.jsonl')[1]
            self.assertEqual([s['kept'] for s in vetoed['engine_oracle']['supervision']], [True, False])
            self.assertEqual(read_json(root / 'consistent' / 'freeze.json'), freeze)

            # A frozen directory is returned unchanged and never recaptured, but only for its own mode.
            for directory, consistent in ((root / 'default', False), (root / 'consistent', True)):
                again, capture = self.build(root, directory, consistent=consistent)
                self.assertEqual(again, read_json(directory / 'freeze.json'))
                capture.assert_not_called()
            for directory, consistent in ((root / 'default', True), (root / 'consistent', False)):
                with self.assertRaisesRegex(RuntimeError, 'other supervision mode'):
                    self.build(root, directory, consistent=consistent)



    def test_a_vetoed_row_with_no_consistent_call_counts_as_vetoed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl', [{**row('dev', True), 'split': 'validation'}])
            freeze, _ = self.build(root, root / 'next', rows=[row('exact', True), row('nothing', False)], consistent=True)
            captures = read_jsonl(root / 'next' / 'train_captures.jsonl')
        self.assertEqual([c['pair_id'] for c in captures], ['exact'])
        self.assertEqual(freeze['stats']['train']['engine_vetoed_by_focus'], {'restatement': 1})
        self.assertEqual(freeze['stats']['train']['partially_supervised_by_focus'], {})

    def test_a_row_that_fails_capture_records_why_and_no_earlier_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl', [{**row('dev', True), 'split': 'validation'}])
            failed = {**row('failed', True), 'engine_oracle': {'exact': True, 'path': 'llm'}}
            recovered = {**row('exact', True), 'capture_error': 'earlier_failure'}
            freeze, _ = self.build(root, root / 'next', rows=[recovered, failed])
            written = {r['case_id']: r for r in read_jsonl(root / 'next' / 'train.jsonl')}
        self.assertEqual(freeze['stats']['train']['capture_failures'], {'fixture_capture_failure': 1})
        self.assertNotIn('engine_oracle', written['failed'])
        self.assertEqual(written['failed']['capture_error'], 'fixture_capture_failure')
        # A row that captures now keeps no error from an earlier capture of its source dataset.
        self.assertNotIn('capture_error', written['exact'])

    def test_a_label_the_validation_lane_found_wrong_is_excluded_after_the_label_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl', [{**row('dev', True), 'split': 'validation'}])
            defects = [{'pair_id': 'vetoed', 'kind': 'dropped_word', 'detail': 'and'},
                       {'pair_id': 'failed', 'kind': 'dropped_word', 'detail': 'so'}]
            freeze, _ = self.build(root, root / 'next', rows=[row('exact', True), row('vetoed', False), row('failed', True)],
                                   defects=defects, consistent=True)
            written = {r['case_id']: r for r in read_jsonl(root / 'next' / 'train.jsonl')}
            captures = read_jsonl(root / 'next' / 'train_captures.jsonl')
        self.assertEqual([c['pair_id'] for c in captures], ['exact'])
        self.assertEqual(freeze['stats']['train']['capture_failures'],
                         {'validation_label_defect': 1, 'fixture_capture_failure': 1})
        self.assertEqual(written['vetoed']['label_conflict'],
                         {'reason': 'validation_label_defect', 'defects': [{'kind': 'dropped_word', 'detail': 'and'}]})
        self.assertNotIn('engine_oracle', written['vetoed'])
        self.assertEqual(written['failed']['capture_error'], 'fixture_capture_failure')

    def test_build_refuses_a_directory_holding_unfrozen_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'longform' / 'train.jsonl', [row('kept', True)])
            before = (root / 'longform' / 'train.jsonl').read_bytes()
            with patch.object(consolidate, 'collect') as collect, \
                    self.assertRaisesRegex(RuntimeError, 'without a freeze'):
                consolidate.build(root / 'longform')
            collect.assert_not_called()
            self.assertEqual((root / 'longform' / 'train.jsonl').read_bytes(), before)

class RestoredConjunctionTests(unittest.TestCase):
    def test_restoration_applies_the_gold_deletions_and_skips_an_unanchored_line(self):
        row = {'case_id': 'c', 'model_input': 'we booked 16 rooms, sorry 17 rooms and before noon we call the hotel',
               'gold_lines': ['16 rooms, sorry']}
        target = 'We booked 17 rooms. Before noon we call the hotel.'
        self.assertEqual(consolidate._restored_conjunctions(row, target),
                         'We booked 17 rooms. And before noon we call the hotel.')
        self.assertIsNone(consolidate._restored_conjunctions({**row, 'gold_lines': ['nine rooms, sorry']}, target))


class CollectTests(unittest.TestCase):
    def collect(self, root, labels, comma_kinds=None):
        write_json(root / 'refinement' / 'dataset' / 'freeze.json', {'stats': {'train': {'label_conflicts': []}}})
        write_jsonl(root / 'refinement' / 'dataset' / 'train.jsonl', labels)
        if comma_kinds is not None:
            write_json(root / 'comma-kinds.json', comma_kinds)
        with patch.object(consolidate, 'ART', root), patch.object(consolidate, 'REFINEMENT', root / 'refinement'), \
                patch.object(consolidate, 'OLD_ART', root / 'old'), \
                patch.object(consolidate, 'COMMA_KINDS', root / 'comma-kinds.json'):
            rows, summary = consolidate.collect()
        return {r['case_id']: r['target'] for r in rows}, summary

    def test_collect_refuses_to_run_without_the_comma_table(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, 'missing'):
            self.collect(Path(directory), [])

    def test_rows_teaching_the_final_vocative_comma_keep_every_added_comma(self):
        with tempfile.TemporaryDirectory() as directory:
            targets, summary = self.collect(Path(directory), [
                {'case_id': 'vocative', 'focus': consolidate.VOCATIVE_FOCUS, 'is_noop': False,
                 'model_input': 'can you run the batch then check it sam',
                 'target': 'Can you run the batch, then check it, Sam?'},
                {'case_id': 'plain', 'focus': 'restatement', 'is_noop': False,
                 'model_input': 'could you run the tests then check them sam',
                 'target': 'Could you run the tests, then check them, Sam?'}], {'kept_kinds': ['list'], 'rows': {}})
        # Unclassified, the addressed name keeps its comma; only the reviewed rows keep the optional one too.
        self.assertEqual(targets, {'vocative': 'Can you run the batch, then check it, Sam?',
                                   'plain': 'Could you run the tests then check them, Sam?'})

    def test_classified_commas_that_do_a_job_stay_and_the_rest_revert(self):
        listed = {'case_id': 'listed', 'pair_id': 'listed', 'is_noop': False,
                  'model_input': 'pack the tent the stove and the water then drive',
                  'target': 'Pack the tent, the stove, and the water, then drive.'}
        unclassified = {**listed, 'case_id': 'unclassified', 'pair_id': 'unclassified',
                        'model_input': 'load the tent the stove and the water then drive',
                        'target': 'Load the tent, the stove, and the water, then drive.'}
        table = {'kept_kinds': ['list', 'addressed', 'meaning', 'convention'],
                 'rows': {'listed': {'3': 'list', '5': 'list', '8': 'style'}}, 'unclassified_rows': ['unclassified']}
        with tempfile.TemporaryDirectory() as directory:
            targets, summary = self.collect(Path(directory), [listed, unclassified], table)
        # A row the table could not classify keeps every comma: when unsure, keep.
        self.assertEqual(targets, {'listed': 'Pack the tent, the stove, and the water then drive.',
                                   'unclassified': 'Load the tent, the stove, and the water, then drive.'})
        self.assertEqual(len(summary['comma_kinds_sha256']), 64)
        # A kept gap that no longer holds a comma means the label changed after classification.
        stale = {**table, 'rows': {'listed': {'2': 'list', '5': 'list'}}}
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, 'stale for listed'):
            self.collect(Path(directory), [listed], stale)


if __name__ == '__main__':
    unittest.main()
