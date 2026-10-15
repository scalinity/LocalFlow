import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from v2 import evaluate
from v2.common import read_json, read_jsonl, write_jsonl
from localflow.v2.cleanup import engine as production


class TornTailTests(unittest.TestCase):
    def test_only_a_partial_final_row_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'out.jsonl'
            path.write_bytes(b'{"case_id": "a"}\n{"case_id": "b", "deliv')
            note = evaluate.drop_torn_tail(path)
            self.assertEqual(path.read_bytes(), b'{"case_id": "a"}\n')
            self.assertEqual(note['bytes'], len(b'{"case_id": "b", "deliv'))
            path.write_bytes(b'{"case_id": "a", "text": "caf\xc3')
            self.assertIsNotNone(evaluate.drop_torn_tail(path))
            self.assertEqual(path.read_bytes(), b'')

    def test_complete_rows_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'out.jsonl'
            for data, settled in ((b'{"case_id": "a"}\n', b'{"case_id": "a"}\n'),
                                  (b'{"case_id": "a"}', b'{"case_id": "a"}\n'),
                                  (b'{"case_id": "a"}\nnot json\n', b'{"case_id": "a"}\nnot json\n')):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    self.assertIsNone(evaluate.drop_torn_tail(path))
                    self.assertEqual(path.read_bytes(), settled)
            self.assertIsNone(evaluate.drop_torn_tail(Path(directory) / 'missing.jsonl'))


class FakeRunner:
    def __init__(self, key, path, variant, updated_engine, recorded_f):
        self.path, self.module = Path(path), production
        self.mx = SimpleNamespace(get_peak_memory=lambda: 0)

    def load(self):
        return {}

    def clean(self, case):
        return {'case_id': case['case_id'], 'delivered': case['model_input']}

    def unload(self):
        pass


class ResumeTests(unittest.TestCase):
    def test_resume_after_a_torn_final_row_records_the_dropped_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / 'model'
            model.mkdir()
            (model / 'weights.safetensors').write_text('fixture weights')
            cases = root / 'cases.jsonl'
            write_jsonl(cases, [{'case_id': f'dev-{i}', 'split': 'validation', 'model_input': f'Keep {i}.'}
                                for i in range(3)])
            out = root / 'eval/run.jsonl'
            with patch.object(evaluate, 'ART', root), patch.object(evaluate, 'Runner', FakeRunner):
                evaluate.evaluate('G', cases, 'run', path=str(model), updated_engine=True)
                complete = out.read_bytes()
                out.write_bytes(complete[:-10])
                self.assertEqual(evaluate.evaluate('G', cases, 'run', path=str(model), updated_engine=True),
                                 {'complete': 3})
            self.assertEqual(out.read_bytes(), complete)
            self.assertEqual([r['case_id'] for r in read_jsonl(out)], ['dev-0', 'dev-1', 'dev-2'])
            runs = read_json(out.with_suffix('.meta.json'))['runs']
            self.assertNotIn('dropped_partial_row', runs[0])
            self.assertEqual(runs[1]['dropped_partial_row']['bytes'],
                             len(complete.splitlines()[-1]) - 9)
            self.assertEqual(runs[1]['todo'], 1)


if __name__ == '__main__':
    unittest.main()
