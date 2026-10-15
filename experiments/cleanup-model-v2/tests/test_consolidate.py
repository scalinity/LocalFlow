import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import copy
from v2 import consolidate
from v2.common import file_sha256, read_json, read_jsonl, write_json, write_jsonl


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
        rows = copy.deepcopy(rows) if rows is not None else [row('exact', True), row('vetoed', False)]
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

    def test_default_freeze_bytes_match_the_previous_builder(self):
        # Captured from the builder before ablation switches, using only fake_capture.
        hashes = {False: '3fb88706b583681b449b700e3964c73505032c39147e585bc3d1038a135d1d2f',
                  True: 'af61a9399897a49cd7ff43efea0251e81178d0252ff7522e3c625708f97f0b97'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl',
                        [{**row('dev', True), 'split': 'validation'}])
            for consistent, digest in hashes.items():
                with self.subTest(consistent=consistent), \
                        patch.object(consolidate, 'utc_now', return_value='2026-01-01T00:00:00+00:00'):
                    dataset = root / str(consistent)
                    freeze, _ = self.build(root, dataset, consistent=consistent, exclude_sources=[])
                    self.assertEqual(file_sha256(dataset / 'freeze.json'), digest)
                    self.assertNotIn('created_omitted', freeze)
                    self.assertNotIn('build_options', freeze)

    def test_source_exclusions_remove_only_the_collected_origins(self):
        rows = [{**row('keep', True), 'consolidated_origin': 'diverse'},
                {**row('contrast', True), 'consolidated_origin': 'contrast'},
                {**row('vetoed', False), 'consolidated_origin': 'c-era'}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl',
                        [{**row('dev', True), 'split': 'validation'}])
            self.build(root, root / 'full', rows=rows, consistent=True)
            freeze, capture = self.build(root, root / 'minus', rows=rows, consistent=True,
                                         exclude_sources=['contrast'])
            for name in ('train.jsonl', 'train_captures.jsonl'):
                expected = [r for r in read_jsonl(root / 'full' / name)
                            if r.get('case_id', r.get('pair_id')) != 'contrast']
                self.assertEqual(read_jsonl(root / 'minus' / name), expected)
            for name in ('validation.jsonl', 'validation_captures.jsonl', 'replay_captures.jsonl'):
                self.assertEqual((root / 'full' / name).read_bytes(), (root / 'minus' / name).read_bytes())
            self.assertEqual([c.args[0]['case_id'] for c in capture.call_args_list], ['keep', 'vetoed', 'dev'])
            self.assertEqual(freeze['stats']['excluded_sources'], {'contrast': 1})
            # Collection describes the common pre-ablation pool; capture counts describe this arm.
            self.assertEqual(freeze['stats']['collect']['kept'], 3)
            self.assertEqual(freeze['stats']['train']['captured'], 2)
            self.assertEqual(freeze['build_options'], {'consistent': True, 'exclude_sources': ['contrast'],
                                                       'unfiltered_vetoed': False})
            self.assertTrue(freeze['created_omitted'])
            self.assertNotIn('created', freeze)

    def test_source_exclusion_freezes_are_identical_across_clocks_and_option_order(self):
        rows = [{**row('keep', True), 'consolidated_origin': 'diverse'},
                {**row('remove', False), 'consolidated_origin': 'contrast'}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i, sources in enumerate((['contrast', 'c-era', 'contrast'], ['c-era', 'contrast'])):
                with patch.object(consolidate, 'utc_now', return_value=f'clock-{i}'):
                    self.build(root, root / str(i), rows=rows, consistent=True, exclude_sources=sources)
            self.assertEqual(file_sha256(root / '0' / 'freeze.json'), file_sha256(root / '1' / 'freeze.json'))
            again, capture = self.build(root, root / '0', consistent=True, exclude_sources=['contrast', 'c-era'])
            capture.assert_not_called()
            self.assertEqual(again, read_json(root / '0' / 'freeze.json'))
            for sources in ([], ['contrast'], ['longform']):
                with self.subTest(sources=sources), self.assertRaisesRegex(RuntimeError, 'other build options'):
                    self.build(root, root / '0', consistent=True, exclude_sources=sources)

    def test_source_exclusion_can_leave_no_rows_and_rejects_unknown_sources_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freeze, _ = self.build(root, root / 'empty', rows=[{**row('only', True), 'consolidated_origin': 'contrast'}],
                                   exclude_sources=['contrast'])
            self.assertEqual(freeze['stats']['train']['captured'], 0)
            self.assertEqual(read_jsonl(root / 'empty' / 'train.jsonl'), [])
            with patch.object(consolidate, 'collect') as collect, self.assertRaisesRegex(ValueError, 'Unknown sources'):
                consolidate.build(root / 'invalid', exclude_sources=['contrats'])
            collect.assert_not_called()
            self.assertFalse((root / 'invalid').exists())

    def test_unfiltered_vetoed_keeps_all_calls_without_changing_other_supervision(self):
        rows = [row('exact', True), row('vetoed', False), row('nothing', False),
                row('failed', False), row('bad-label', False)]
        defects = [{'pair_id': 'bad-label', 'kind': 'dropped_word', 'detail': 'and'}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'refinement' / 'dataset' / 'validation.jsonl',
                        [{**row('dev-vetoed', False), 'split': 'validation'}])
            self.build(root, root / 'consistent', rows=rows, defects=defects, consistent=True)
            freeze, _ = self.build(root, root / 'unfiltered', rows=rows, defects=defects,
                                   consistent=True, unfiltered_vetoed=True)
            before = {c['pair_id']: c for c in read_jsonl(root / 'consistent' / 'train_captures.jsonl')}
            after = {c['pair_id']: c for c in read_jsonl(root / 'unfiltered' / 'train_captures.jsonl')}
            self.assertEqual(before['exact'], after['exact'])
            self.assertEqual(before['vetoed']['calls'], after['vetoed']['calls'][:1])
            self.assertEqual(after['vetoed']['calls'], [call('corrections'), call('main')])
            self.assertNotIn('nothing', before)
            self.assertEqual(after['nothing']['calls'], [call('corrections'), call('main')])
            self.assertEqual(set(after), {'exact', 'vetoed', 'nothing'})
            for name in ('validation.jsonl', 'validation_captures.jsonl', 'replay_captures.jsonl'):
                self.assertEqual((root / 'consistent' / name).read_bytes(), (root / 'unfiltered' / name).read_bytes())
            before_rows = read_jsonl(root / 'consistent' / 'train.jsonl')
            after_rows = read_jsonl(root / 'unfiltered' / 'train.jsonl')
            for old, new in zip(before_rows, after_rows, strict=True):
                self.assertEqual(old['case_id'], new['case_id'])
                if old['case_id'] in ('vetoed', 'nothing'):
                    old['engine_oracle'].pop('supervision')
                self.assertEqual(old, new)
            self.assertEqual(freeze['mode'], 'unfiltered-vetoed')
            self.assertEqual(freeze['stats']['train']['unfiltered_vetoed_by_focus'], {'restatement': 2})
            self.assertEqual(freeze['stats']['train']['capture_failures'],
                             {'fixture_capture_failure': 1, 'validation_label_defect': 1})
            self.assertNotIn('partially_supervised_by_focus', freeze['stats']['train'])
            self.assertEqual(freeze['build_options'], {'consistent': True, 'exclude_sources': [],
                                                       'unfiltered_vetoed': True})
            again, capture = self.build(root, root / 'unfiltered', consistent=True, unfiltered_vetoed=True)
            capture.assert_not_called()
            self.assertEqual(again, freeze)
            with self.assertRaisesRegex(RuntimeError, 'other supervision mode'):
                self.build(root, root / 'unfiltered', consistent=True)
            with self.assertRaisesRegex(RuntimeError, 'other supervision mode'):
                self.build(root, root / 'consistent', consistent=True, unfiltered_vetoed=True)
            with self.assertRaisesRegex(RuntimeError, 'other build options'):
                self.build(root, root / 'unfiltered', unfiltered_vetoed=True)

    def test_unfiltered_freezes_are_deterministic_alone_and_with_source_exclusions(self):
        rows = [{**row('exact', True), 'consolidated_origin': 'contrast'},
                {**row('vetoed', False), 'consolidated_origin': 'diverse'}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for sources in ([], ['contrast']):
                for i in range(2):
                    with patch.object(consolidate, 'utc_now', return_value=f'clock-{i}'):
                        freeze, _ = self.build(root, root / f'{sources}-{i}', rows=rows,
                                               exclude_sources=sources, unfiltered_vetoed=True)
                    self.assertTrue(freeze['created_omitted'])
                    self.assertNotIn('created', freeze)
                    self.assertEqual(freeze['mode'], 'unfiltered-vetoed')
                    self.assertEqual(freeze['build_options']['exclude_sources'], sources)
                    self.assertFalse(freeze['build_options']['consistent'])
                self.assertEqual(file_sha256(root / f'{sources}-0' / 'freeze.json'),
                                 file_sha256(root / f'{sources}-1' / 'freeze.json'))



class RestoredConjunctionTests(unittest.TestCase):
    def test_restoration_applies_the_gold_deletions_and_skips_an_unanchored_line(self):
        row = {'case_id': 'c', 'model_input': 'we booked 16 rooms, sorry 17 rooms and before noon we call the hotel',
               'gold_lines': ['16 rooms, sorry']}
        target = 'We booked 17 rooms. Before noon we call the hotel.'
        self.assertEqual(consolidate._restored_conjunctions(row, target),
                         'We booked 17 rooms. And before noon we call the hotel.')
        self.assertIsNone(consolidate._restored_conjunctions({**row, 'gold_lines': ['nine rooms, sorry']}, target))


class CollectTests(unittest.TestCase):
    @unittest.skipUnless((consolidate.ART / 'contrast' / 'train.normalized.jsonl').exists(),
                         'private contrast TRAIN source is unavailable')
    def test_all_324_normalized_contrast_rows_survive_collect(self):
        source = read_jsonl(consolidate.ART / 'contrast' / 'train.normalized.jsonl')
        self.assertEqual(len(source), 324)
        rows, summary = consolidate.collect()
        contrast = [r for r in rows if r['consolidated_origin'] == 'contrast']
        self.assertEqual(len(contrast), 324)
        self.assertEqual(summary['stats']['kept_contrast'], 324)
        self.assertEqual({r['case_id']: r['target'] for r in contrast},
                         {r['case_id']: r['target'] for r in source})

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
