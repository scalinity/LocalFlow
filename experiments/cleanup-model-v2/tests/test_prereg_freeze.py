"""Freeze/seal checks use disposable repositories and synthetic rows only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "prereg_freeze", Path(__file__).resolve().parents[1] / "tools/prereg_freeze.py")
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


class PreregFreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.run_git("init", "-q")
        self.write(".gitignore", "/data/\n/experiments/cleanup-model-v2/artifacts/\n")
        self.write(freeze.PREREG, "# Synthetic preregistration fixture\n")
        self.write(freeze.JUDGE, 'SYSTEM = "Synthetic prompt"\n')
        self.run_git("add", ".gitignore", str(freeze.PREREG), str(freeze.JUDGE))
        self.run_git("commit", "-qm", "Add synthetic freeze fixtures")
        self.write("data/train.jsonl", '{"id":"synthetic-a"}\n\n{"id":"synthetic-b"}')
        self.write("data/dev.jsonl", '{"id":"synthetic-c"}\n')
        self.write("data/freeze.json", json.dumps({"files": {
            name: freeze.sha256(self.repo / "data" / name)
            for name in ("train.jsonl", "dev.jsonl")}}))
        self.pairs = [("data/freeze.json", "data/train.jsonl"),
                      ("data/freeze.json", "data/dev.jsonl")]
        self.output = self.repo / freeze.OUTPUT

    def write(self, path, content):
        path = self.repo / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_git(self, *args):
        # Inherit the configured identity; never set or replace name/email.
        return subprocess.check_output(["git", "-C", str(self.repo), *args],
                                       text=True, stderr=subprocess.STDOUT).strip()

    def generate(self, extra=()):
        args = ["--repo", str(self.repo)]
        for pair in self.pairs:
            args.extend(["--dataset-freeze", *pair])
        with contextlib.redirect_stdout(io.StringIO()):
            freeze.main([*args, *extra])
        return json.loads((self.output / "FREEZE.json").read_text())

    def test_hashes_counts_and_deterministic_order(self):
        first = freeze.record(self.repo, self.pairs, [], "2026-01-01T00:00:00Z")
        second = freeze.record(self.repo, list(reversed(self.pairs)),
                               [freeze.JUDGE, freeze.JUDGE], "2026-01-01T00:00:00Z")
        self.assertEqual(first, second)
        self.assertEqual([e["row_count"] for e in first["datasets"]], [1, 2])
        self.assertEqual(first["git_commit"], self.run_git("rev-parse", "HEAD"))
        self.assertEqual(first["preregistration"]["sha256"], freeze.sha256(self.repo / freeze.PREREG))
        self.assertEqual(first["judge_prompt_files"][0]["sha256"], freeze.sha256(self.repo / freeze.JUDGE))
        self.assertEqual(first["datasets"][0]["freeze_sha256"], freeze.sha256(self.repo / "data/freeze.json"))
        self.assertEqual(first["datasets"][1]["rows_sha256"], freeze.sha256(self.repo / "data/train.jsonl"))
        self.assertNotIn("synthetic-a", json.dumps(first))

    def test_cli_timestamp_and_seal(self):
        generated = self.generate(["--seal"])
        self.assertRegex(generated["created_at_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual((self.output / "FROZEN").read_text().strip(),
                         hashlib.sha256((self.output / "FREEZE.json").read_bytes()).hexdigest())
        before = (self.output / "FREEZE.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.generate()
        self.assertEqual((self.output / "FREEZE.json").read_bytes(), before)

    def test_seal_requires_record_and_clean_tree(self):
        with self.assertRaisesRegex(ValueError, "existing FREEZE"):
            freeze.seal(self.repo, self.output)
        self.generate()
        for dirty in ["untracked.txt", freeze.PREREG]:
            with self.subTest(dirty=dirty):
                path = self.repo / dirty
                original = path.read_bytes() if path.exists() else None
                self.write(dirty, "changed\n")
                with self.assertRaisesRegex(ValueError, "clean working tree"):
                    freeze.seal(self.repo, self.output)
                self.assertFalse((self.output / "FROZEN").exists())
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
        with contextlib.redirect_stdout(io.StringIO()):
            freeze.main(["--repo", str(self.repo), "--seal"])
        self.assertTrue((self.output / "FROZEN").is_file())

    def test_seal_rejects_changed_commit(self):
        self.generate()
        self.write(freeze.PREREG, "# Changed protocol\n")
        self.run_git("add", str(freeze.PREREG))
        self.run_git("commit", "-qm", "Revise synthetic protocol fixture")
        with self.assertRaisesRegex(ValueError, "changed"):
            freeze.seal(self.repo, self.output)
        self.assertFalse((self.output / "FROZEN").exists())

    def test_seal_rechecks_ignored_prompt_and_dataset(self):
        self.write("data/prompt.txt", "Synthetic extra prompt\n")
        self.generate(["--judge-prompt", "data/prompt.txt"])
        self.write("data/prompt.txt", "Changed prompt\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            freeze.seal(self.repo, self.output)
        self.write("data/prompt.txt", "Synthetic extra prompt\n")
        self.write("data/train.jsonl", '{"id":"changed"}\n')
        with self.assertRaisesRegex(ValueError, "disagrees"):
            freeze.seal(self.repo, self.output)
        self.assertFalse((self.output / "FROZEN").exists())

    def test_invalid_rows_and_duplicate_pairs(self):
        for content in ['not JSON\n', '["not an object"]\n']:
            self.write("data/train.jsonl", content)
            with self.assertRaises(ValueError):
                freeze.record(self.repo, self.pairs, [], "2026-01-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "distinct"):
            freeze.record(self.repo, [self.pairs[1], self.pairs[1]], [], "2026-01-01T00:00:00Z")

    def test_cli_is_byte_stable_with_fixed_clock(self):
        with patch.object(freeze, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "2026-01-01T00:00:00Z"
            self.generate()
            first = (self.output / "FREEZE.json").read_bytes()
            self.pairs.reverse()
            self.generate()
            self.assertEqual(first, (self.output / "FREEZE.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
