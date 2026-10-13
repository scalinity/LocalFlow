"""Fresh comparisons cannot silently reuse a different dataset or source."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2 import evaluate, judge, remediation
from v2.common import write_json, write_jsonl, file_sha256


class FreshComparisonTests(unittest.TestCase):
    def test_freeze_refuses_already_started_candidate_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / 'eval/fresh-F.jsonl', [{'case_id': 'one'}])
            with patch.object(remediation, 'ART', root), patch.object(remediation, 'RUN', root / 'remediation'):
                with self.assertRaisesRegex(RuntimeError, 'already started'):
                    remediation.freeze_final()

    def test_evaluation_and_judging_refuse_unfrozen_or_changed_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'cases.jsonl'
            write_jsonl(cases, [{'case_id': 'one', 'split': 'test'}])
            write_json(root / 'dataset/freeze.json', {})
            for freeze in (None, {'cases_sha256': 'not-the-case-hash'}):
                if freeze is not None:
                    write_json(root / 'remediation/freeze.json', freeze)
                with patch.object(evaluate, 'ART', root), patch.object(evaluate, 'Runner') as runner:
                    with self.assertRaisesRegex(RuntimeError, 'exact frozen'):
                        evaluate.evaluate('F', cases, 'fresh-F', updated_engine=True)
                    runner.assert_not_called()
                with patch.object(judge, 'ART', root), patch.object(judge, 'wave') as wave:
                    with self.assertRaisesRegex(ValueError, 'exact frozen'):
                        judge.run(cases, ['F'], prefix='fresh')
                    wave.assert_not_called()

    def test_updated_source_cannot_change_after_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = root / 'cases.jsonl'
            write_jsonl(cases, [{'case_id': 'one', 'split': 'test'}])
            write_json(root / 'dataset/freeze.json', {})
            write_json(root / 'remediation/freeze.json', {
                'cases_sha256': file_sha256(cases), 'source_hashes': {'engine.py': 'old-source-hash'}})
            with patch.object(evaluate, 'ART', root), patch.object(evaluate, 'Runner') as runner:
                with self.assertRaisesRegex(RuntimeError, 'source changed'):
                    evaluate.evaluate('F', cases, 'fresh-F', updated_engine=True)
                runner.assert_not_called()

    def test_development_judging_still_refuses_final_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = Path(directory) / 'cases.jsonl'
            write_jsonl(cases, [{'case_id': 'one', 'split': 'test'}])
            with self.assertRaisesRegex(ValueError, 'Development judging'):
                judge.run(cases, ['F'], prefix='dev')


if __name__ == '__main__':
    unittest.main()
