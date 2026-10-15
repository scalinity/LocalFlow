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

    def test_final_freeze_preserves_capture_and_serving_source_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / 'artifacts'
            run = artifacts / 'refinement'
            dataset = run / 'dataset'
            source = root / 'prompts.py'
            source.write_text('original capture prompt')
            capture_hash = file_sha256(source)
            write_jsonl(dataset / 'test.jsonl', [{'case_id': 'synthetic-0', 'split': 'test'}])
            write_json(dataset / 'freeze.json', {
                'files': {'test.jsonl': file_sha256(dataset / 'test.jsonl')},
                'capture_source_hashes': {'prompts.py': capture_hash},
            })
            dataset_freeze_hash = file_sha256(dataset / 'freeze.json')
            audio = [{'case_id': f'audio-{i}', 'split': 'test'} for i in range(300)]
            write_jsonl(run / 'audio-asr.jsonl', audio)
            write_jsonl(run / 'audio-cases.jsonl', audio)
            models = {}
            for key in ('C', 'F', 'G'):
                model = root / key
                model.mkdir()
                (model / 'weights.safetensors').write_text('fixed fixture weights ' + key)
                models[key] = {'path': str(model), 'content_digest': content_digest(model)}
            write_json(artifacts / 'export/diverse-6000-ckpt-00761.identity.json', {
                'quantized': models['F']['path'], 'content_digest': models['F']['content_digest'],
            })
            # G was trained on another dataset than the one holding the final labels.
            other = root / 'other-dataset'
            write_json(other / 'freeze.json', {'capture_source_hashes': {'prompts.py': 'other capture'}})
            request = artifacts / 'train/G-run/request.json'
            write_json(request, {'dataset_dir': str(other), 'dataset_freeze_sha256': file_sha256(other / 'freeze.json')})
            write_json(run / 'candidate-selection.json', {
                'ready_for_final': True, 'candidate': {'key': 'G', 'training_run': 'G-run', **models['G']},
            })
            source.write_text('updated serving prompt')
            serving_hash = file_sha256(source)
            with patch.multiple(refinement, ROOT=root, ART=artifacts, RUN=run,
                                DATASET=dataset, SOURCE_FILES=['prompts.py']), \
                    patch.object(training, 'ROOT', root), \
                    patch.object(refinement, 'c_identity', return_value={
                        'snapshot_path': models['C']['path'], 'revision': models['C']['content_digest'],
                    }):
                freeze = refinement.freeze_final()
                self.assertEqual(freeze['capture_source_hashes'], {'prompts.py': capture_hash})
                self.assertEqual(freeze['source_hashes'], {'prompts.py': serving_hash})
                self.assertEqual(freeze['data_freeze_sha256'], dataset_freeze_hash)
                self.assertEqual(file_sha256(dataset / 'freeze.json'), dataset_freeze_hash)
                self.assertEqual(freeze['n'], 301)
                self.assertEqual(freeze['candidate_training'], {
                    'run': 'G-run', 'request_sha256': file_sha256(request), 'dataset_dir': str(other),
                    'dataset_freeze_sha256': file_sha256(other / 'freeze.json'),
                    'capture_source_hashes': {'prompts.py': 'other capture'}})
                self.assertNotEqual(freeze['candidate_training']['dataset_freeze_sha256'], freeze['data_freeze_sha256'])
                refinement.require_final(run / 'final-cases.jsonl', candidate=True,
                                         key='G', model_path=models['G']['path'], engine='updated_source')
                source.write_text('later serving prompt')
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    refinement.require_final(run / 'final-cases.jsonl', candidate=True)
                (run / 'final-freeze.json').unlink()
                write_json(other / 'freeze.json', {'capture_source_hashes': {'prompts.py': 'recaptured'}})
                with self.assertRaisesRegex(RuntimeError, 'training dataset changed'):
                    refinement.freeze_final()
                write_json(run / 'candidate-selection.json', {'ready_for_final': True, 'candidate': models['G'] | {'key': 'G'}})
                with self.assertRaisesRegex(RuntimeError, 'training run'):
                    refinement.freeze_final()

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
    def test_capture_source_is_required_by_default_but_optional_for_serving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / 'dataset'
            source = root / 'prompts.py'
            source.write_text('original capture prompt')
            write_jsonl(dataset / 'train_captures.jsonl', [{'input': 'fixed capture'}])
            freeze = {
                'files': {'train_captures.jsonl': file_sha256(dataset / 'train_captures.jsonl')},
                'capture_source_hashes': {'prompts.py': file_sha256(source)},
            }
            write_json(dataset / 'freeze.json', freeze)
            with patch.object(training, 'ROOT', root):
                self.assertEqual(training.checked_dataset(dataset), freeze)
                source.write_text('updated serving prompt')
                with self.assertRaisesRegex(RuntimeError, 'prompt source changed'):
                    training.checked_dataset(dataset)
                self.assertEqual(training.checked_dataset(dataset, require_current_capture_source=False), freeze)
                write_jsonl(dataset / 'train_captures.jsonl', [{'input': 'changed capture'}])
                with self.assertRaisesRegex(RuntimeError, 'dataset file changed'):
                    training.checked_dataset(dataset, require_current_capture_source=False)

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
        # The spans are not real correction lines, so only the negation rule is under test.
        with patch('v2.label_defects.label_defect', return_value=None):
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
                'train': [row('train-conflict'), row('train-reviewed', 'And ready.', 'Ready.'),
                          row('train-kept', 'Ready.', 'Ready.'),
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
            review = {'source_sha256': file_sha256(run / 'synthetic-train.jsonl'),
                      'exclusions': {'train-reviewed': 'Deletes an original connective without authorization'}}
            write_json(run / 'training-label-review.json', review)
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
                write_json(run / 'training-label-review.json', {**review, 'source_sha256': 'stale'})
                with self.assertRaisesRegex(ValueError, 'current TRAIN labels'):
                    refinement.prepare()
                self.assertFalse(captured)
                write_json(run / 'training-label-review.json', review)
                freeze = refinement.prepare()
            self.assertEqual(captured, ['validation-conflict', 'train-kept', 'train-failure', 'replay-kept'])
            self.assertEqual(freeze['stats']['train']['captured'], 1)
            self.assertEqual([c['case_id'] for c in freeze['stats']['train']['label_conflicts']],
                             ['train-conflict', 'train-reviewed'])
            self.assertEqual(freeze['training_label_review'], review)
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
