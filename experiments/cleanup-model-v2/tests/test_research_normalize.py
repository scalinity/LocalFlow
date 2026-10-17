"""The minimal-edit rewrite tool on synthetic files: input, changed-only output and its record."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import research_normalize_dev as rn  # noqa: E402
from v2 import refinement  # noqa: E402
from v2.common import file_sha256  # noqa: E402


def upper_when_changed(source, target, pairs):
    return (target.upper(), ["upper"], None) if target.startswith("Change") else (target, [], None)


class NormalizeTests(unittest.TestCase):
    def write_cases(self, root):
        rows = [{"case_id": "a", "split": "test", "model_input": "keep", "target": "Keep.", "category": "c"},
                {"case_id": "b", "split": "test", "model_input": "change", "target": "Change me.", "category": "c"}]
        source = root / "cases.jsonl"
        source.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return source, rows

    def test_changed_rows_and_their_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, rows = self.write_cases(root)
            out, changed = root / "out.jsonl", root / "out-changed.jsonl"
            with patch.object(rn, "minimal_target", upper_when_changed):
                rn.main([str(out), "--input", str(source), "--changed", str(changed)])
            rewritten = [json.loads(line) for line in out.read_text().splitlines()]
            subset = [json.loads(line) for line in changed.read_text().splitlines()]
            self.assertEqual(rewritten[0], rows[0])
            self.assertEqual([(r["case_id"], r["target"]) for r in subset], [("b", "CHANGE ME.")])
            record = json.loads((root / "out.record.json").read_text())
            self.assertEqual((record["source_sha256"], record["rewritten_sha256"], record["changed_sha256"]),
                             (file_sha256(source), file_sha256(out), file_sha256(changed)))
            # The record is what require_final reads to accept the rewrite for judging.
            accepted = refinement.final_cases_accepted({"cases_sha256": file_sha256(source)}, changed)
            self.assertEqual(accepted, {file_sha256(source), file_sha256(out), file_sha256(changed)})

    def test_changed_output_must_sit_beside_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, _ = self.write_cases(root)
            (root / "elsewhere").mkdir()
            with patch.object(rn, "minimal_target", upper_when_changed), self.assertRaises(SystemExit):
                rn.main([str(root / "out.jsonl"), "--input", str(source),
                         "--changed", str(root / "elsewhere/changed.jsonl")])
            self.assertFalse((root / "out.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
