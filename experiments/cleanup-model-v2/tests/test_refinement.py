import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2 import refinement, training, evaluate
from v2.common import file_sha256, write_json, write_jsonl, read_jsonl
from lfx.export import content_digest


class FinalIsolationTests(unittest.TestCase):
    def freeze(self, root, cases, **fields):
        write_json(root / 'candidate-selection.json', {'ready_for_final': True})
        write_json(root / 'dataset/freeze.json', {'files': {}})
        value = {'cases_sha256': file_sha256(cases), 'source_hashes': {}, 'models': {},
                 'selection_sha256': file_sha256(root / 'candidate-selection.json'),
                 'data_freeze_sha256': file_sha256(root / 'dataset/freeze.json'), **fields}
        write_json(root / 'final-freeze.json', value)

    def test_missing_and_mismatched_final_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'cases.jsonl'
            cases.write_text('original cases')
            with patch.object(refinement, 'RUN', root), patch.object(refinement, 'DATASET', root / 'dataset'):
                with self.assertRaisesRegex(ValueError, 'exact frozen'):
                    refinement.require_final(cases)
                self.freeze(root, cases)
                refinement.require_final(cases)
                cases.write_text('changed cases')
                with self.assertRaisesRegex(ValueError, 'exact frozen'):
                    refinement.require_final(cases)

    def test_changed_candidate_source_does_not_inherit_frozen_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases, source = root / 'cases.jsonl', root / 'engine.py'
            cases.write_text('cases')
            source.write_text('fixed candidate')
            self.freeze(root, cases, source_hashes={'engine.py': file_sha256(source)})
            with patch.object(refinement, 'RUN', root), patch.object(refinement, 'ROOT', root), patch.object(refinement, 'DATASET', root / 'dataset'):
                refinement.require_final(cases, candidate=True)
                source.write_text('tuned candidate')
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    refinement.require_final(cases, candidate=True)
                refinement.require_final(cases, candidate=False)

    def test_changed_selection_model_or_engine_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'cases.jsonl'
            cases.write_text('fixed cases')
            model = root / 'model'
            model.mkdir()
            (model / 'weights.safetensors').write_text('fixed weights')
            self.freeze(root, cases, models={'G': {'path': str(model.resolve()), 'engine': 'updated_source',
                                                 'content_digest': content_digest(model)}})
            with patch.object(refinement, 'RUN', root), patch.object(refinement, 'DATASET', root / 'dataset'):
                refinement.require_final(cases, key='G', model_path=model, engine='updated_source')
                for key, path, engine in [('G', model, 'production'), ('G', root / 'other', 'updated_source'), ('H', model, 'updated_source')]:
                    with self.assertRaisesRegex(ValueError, 'model or engine'):
                        refinement.require_final(cases, key=key, model_path=path, engine=engine)
                (model / 'weights.safetensors').write_text('changed weights')
                with self.assertRaisesRegex(ValueError, 'model files changed'):
                    refinement.require_final(cases, key='G', model_path=model, engine='updated_source')
                write_json(root / 'candidate-selection.json', {'ready_for_final': False})
                with self.assertRaisesRegex(ValueError, 'selection changed'):
                    refinement.require_final(cases)

    def test_final_test_path_cannot_bypass_freeze_with_another_output_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'refinement/dataset/test.jsonl'
            cases.parent.mkdir(parents=True)
            cases.write_text('{"case_id":"fixed-test","split":"test"}\n')
            write_json(root / 'dataset/freeze.json', {'frozen': True})
            with patch.object(evaluate, 'ART', root), patch.object(refinement, 'RUN', root / 'refinement'):
                with self.assertRaisesRegex(ValueError, 'exact frozen'):
                    evaluate.evaluate('G', cases, 'another-name', path=str(root / 'model'), updated_engine=True)

    def test_evaluation_cannot_resume_outputs_without_identity_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'cases.jsonl'
            cases.write_text('{"case_id":"dev","split":"validation"}\n')
            (root / 'eval').mkdir()
            (root / 'eval/run.jsonl').write_text('{"case_id":"dev"}\n')
            with patch.object(evaluate, 'ART', root):
                with self.assertRaisesRegex(RuntimeError, 'no identity metadata'):
                    evaluate.evaluate('G', cases, 'run', path=str(root / 'model'), updated_engine=True)


class TrainingIdentityTests(unittest.TestCase):
    def test_legacy_split_name_freeze_remains_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('test', 'validation'):
                (root / (name + '.jsonl')).write_text('fixed legacy split ' + name)
            write_json(root / 'freeze.json', {'files': {name: file_sha256(root / (name + '.jsonl'))
                                                       for name in ('test', 'validation')}})
            training.checked_dataset(root)
            (root / 'test.jsonl').write_text('changed split')
            with self.assertRaisesRegex(RuntimeError, 'dataset file changed'):
                training.checked_dataset(root)

    def test_changed_frozen_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'train_captures.jsonl'
            data.write_text('original captures')
            write_json(root / 'freeze.json', {'files': {data.name: file_sha256(data)}})
            training.checked_dataset(root)
            data.write_text('changed captures')
            with self.assertRaisesRegex(RuntimeError, 'dataset file changed'):
                training.checked_dataset(root)

    def test_completed_training_cannot_satisfy_a_different_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, adapter = root / 'dataset', root / 'adapter'
            adapter.mkdir()
            (adapter / 'adapters.safetensors').write_text('fixed source adapter')
            write_json(data / 'freeze.json', {'files': {}})
            write_json(root / 'train/run/completion.json', {'complete': True})
            request = {'name':'run', 'count':10, 'start':0, 'control':False, 'lr':3e-5,
                       'dataset_dir':str(data.resolve()), 'dataset_freeze_sha256':file_sha256(data / 'freeze.json'),
                       'initial_adapter':str(adapter.resolve()), 'initial_adapter_sha256':file_sha256(adapter / 'adapters.safetensors'),
                       'training_config':training.CONFIG['training']}
            write_json(root / 'train/run/request.json', request)
            with patch.object(training, 'ART', root):
                self.assertEqual(training.run('run', 10, initial_adapter=adapter), {'complete': True})
                with self.assertRaisesRegex(RuntimeError, 'another or unrecorded request'):
                    training.run('run', 11, initial_adapter=adapter)
                with self.assertRaisesRegex(RuntimeError, 'another or unrecorded request'):
                    training.run('run', 10, initial_adapter=adapter, lr=2e-5)


class TrainingLabelConflictTests(unittest.TestCase):
    def test_adjacent_negation_deletion_is_a_label_conflict(self):
        for source, target, word in (
                ('The service is not not up.', 'The service is not up.', 'not'),
                ('Never never skip this check.', 'Never skip this check.', 'never'),
                ('No\tno bypass is allowed.', 'No bypass is allowed.', 'no'),
                ("We can't can't proceed.", "We can't proceed.", "can't"),
                ('We can’t can’t proceed.', 'We can’t proceed.', "can't"),
                ('NOT not not ready.', 'Not not ready.', 'not')):
            with self.subTest(source=source):
                conflict = refinement.training_label_conflict({'model_input': source, 'target': target})
                self.assertEqual(conflict['reason'], 'ambiguous_repeated_negation_deletion')
                self.assertEqual(conflict['negations'][0]['word'], word)
                self.assertGreater(conflict['negations'][0]['source_count'], conflict['negations'][0]['target_count'])

    def test_punctuation_separated_and_retained_negations_remain_eligible(self):
        for source, target in (
                ('Not. Not ready.', 'Not ready.'),
                ('No, no bypass.', 'No bypass.'),
                ('Not—not ready.', 'Not ready.'),
                ('The service is not not up', 'The service is not not up.'),
                ('The service is not not up.', 'The service is not not up.'),
                ('The the service is up.', 'The service is up.')):
            with self.subTest(source=source):
                self.assertIsNone(refinement.training_label_conflict({'model_input': source, 'target': target}))

    def test_authorized_correction_spans_are_excluded_before_counting(self):
        row = {'model_input': 'Not not ready.', 'target': 'Not ready.', 'gold_offsets': [[0, 4]]}
        self.assertIsNone(refinement.training_label_conflict(row))
        source = 'Not not ready, not sorry, now ready.'
        start = source.index('not sorry')
        row = {'model_input': source, 'target': 'Not not ready, now ready.',
               'gold_offsets': [[start, start + len('not sorry, ')]]}
        self.assertIsNone(refinement.training_label_conflict(row))
        # An authorized deletion must not turn separate words into a new repeat.
        source = 'Not old sorry not ready.'
        row = {'model_input': source, 'target': 'Not ready.',
               'gold_offsets': [[source.index('old'), source.index('not ready')]]}
        self.assertIsNone(refinement.training_label_conflict(row))

    def test_prepare_excludes_only_train_capture_and_keeps_label_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'refinement'
            dataset = run / 'dataset'

            def row(cid, source='Not not ready.', target='Not ready.'):
                return {'case_id': cid, 'model_input': source, 'target': target, 'gold_offsets': []}

            labels = {
                'train': [row('train-conflict'), row('train-kept', 'Ready.', 'Ready.'),
                          row('train-failure', 'Keep this.', 'Keep this.')],
                'validation': [row('validation-conflict')],
                'test': [row('test-conflict')],
            }
            original_bytes = {}
            for split, values in labels.items():
                for path in (root / 'accepted' / ('refinement-' + split + '.jsonl'),
                             run / ('synthetic-' + split + '.jsonl')):
                    write_jsonl(path, values)
                    original_bytes[path] = path.read_bytes()
            replay = [row('replay-conflict'), row('replay-kept', 'Ready.', 'Ready.')]
            for value in replay:
                value['engine_oracle'] = {'exact': True}
            replay_path = root / 'dataset/train.jsonl'
            write_jsonl(replay_path, replay)
            original_bytes[replay_path] = replay_path.read_bytes()
            captured = []

            def capture(value):
                captured.append(value['case_id'])
                if value['case_id'] == 'train-failure':
                    raise ValueError('fixture_capture_failure')
                value['engine_oracle'] = {'exact': True}
                return {'case_id': value['case_id']}

            with patch.object(refinement, 'ART', root), patch.object(refinement, 'RUN', run), \
                    patch.object(refinement, 'DATASET', dataset), patch.object(refinement, 'SOURCE_FILES', []), \
                    patch('v2.refinement_data.assemble'), patch('v2.assemble.capture', side_effect=capture), \
                    patch('v2.refinement.random.Random.shuffle'):
                freeze = refinement.prepare()
            self.assertEqual(captured, ['validation-conflict', 'train-kept', 'train-failure', 'replay-kept'])
            self.assertEqual(freeze['stats']['train']['captured'], 1)
            self.assertEqual([c['case_id'] for c in freeze['stats']['train']['label_conflicts']], ['train-conflict'])
            self.assertEqual(freeze['stats']['train']['capture_failures'],
                             [{'case_id': 'train-failure', 'reason': 'fixture_capture_failure'}])
            self.assertEqual([c['case_id'] for c in freeze['stats']['replay']['label_conflicts']], ['replay-conflict'])
            self.assertEqual(freeze['stats']['validation']['captured'], 1)
            self.assertNotIn('label_conflicts', freeze['stats']['validation'])
            self.assertFalse((dataset / 'test_captures.jsonl').exists())
            for path, content in original_bytes.items():
                self.assertEqual(path.read_bytes(), content)
            for split in labels:
                self.assertEqual((dataset / (split + '.jsonl')).read_bytes(),
                                 (run / ('synthetic-' + split + '.jsonl')).read_bytes())
            self.assertEqual(read_jsonl(dataset / 'train_captures.jsonl'), [{'case_id': 'train-kept'}])


if __name__ == '__main__':
    unittest.main()
