import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2 import refinement, training, evaluate
from v2.common import file_sha256, write_json
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


if __name__ == '__main__':
    unittest.main()
