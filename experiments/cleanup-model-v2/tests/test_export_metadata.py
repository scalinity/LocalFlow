"""Lossless metadata compaction checks; every write uses a temporary fixture."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v2.export_metadata import compact_json_metadata
from v2 import training
from lfx.export import content_digest


class ExportMetadataTests(unittest.TestCase):
    def test_nested_values_strings_escapes_and_number_spellings_are_preserved(self):
        raw = ('{\n "unicode": "café Ω 🐈", "escaped": "\\u03a9",\n'
               ' "text": " two  spaces \\t \\n \\\" \\\\ ",\n'
               ' "values": [true, false, null, -0, 1.2300e+02, '
               '123456789012345678901234567890, {"x": [1, 2]}]\n}\n').encode()
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "tokenizer.json"
            file.write_bytes(raw)
            receipt = compact_json_metadata(directory)
            after = file.read_bytes()
            self.assertEqual(json.loads(raw), json.loads(after))
            for literal in (b'"\\u03a9"', b'-0', b'1.2300e+02', b' two  spaces '):
                self.assertIn(literal, after)
            record = receipt["files"][0]
            self.assertTrue(record["written"])
            self.assertTrue(record["parsed_values_equal"])
            self.assertEqual(record["before_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["after_sha256"], hashlib.sha256(after).hexdigest())
            self.assertEqual(record["saved_bytes"], len(raw) - len(after))

    def test_compact_files_are_not_rewritten_and_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "config.json"
            file.write_bytes(b'{"a":1}')
            before = file.stat()
            receipt = compact_json_metadata(directory)
            after = file.stat()
            self.assertFalse(receipt["files"][0]["written"])
            self.assertEqual(receipt["saved_bytes"], 0)
            self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
            file.write_bytes(b'{ "a": 1 }\n')
            compact_json_metadata(directory)
            first = file.stat()
            receipt = compact_json_metadata(directory)
            self.assertEqual(receipt["saved_bytes"], 0)
            self.assertEqual(first.st_mtime_ns, file.stat().st_mtime_ns)

    def test_weights_assets_and_nested_files_remain_byte_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            untouched = {"model.safetensors": b'\x00\xff { fake weights }',
                         "vocab.txt": b'one\n two\n',
                         "chat_template.jinja": b'{{ messages }}\n'}
            for name, content in untouched.items():
                (root / name).write_bytes(content)
            (root / "nested").mkdir()
            (root / "nested/config.json").write_bytes(b'{ "keep": true }')
            (root / "model.safetensors.index.json").write_bytes(
                b'{ "weight_map": { "layer": "model.safetensors" } }')
            before_names = sorted(p.relative_to(root) for p in root.rglob('*'))
            total = sum(p.stat().st_size for p in root.iterdir() if p.is_file())
            receipt = compact_json_metadata(root)
            self.assertEqual(receipt["artifact_before_bytes"], total)
            self.assertEqual(receipt["artifact_after_bytes"], total - receipt["saved_bytes"])
            self.assertEqual(before_names, sorted(p.relative_to(root) for p in root.rglob('*')))
            for name, content in untouched.items():
                self.assertEqual((root / name).read_bytes(), content)
            self.assertEqual((root / "nested/config.json").read_bytes(), b'{ "keep": true }')

    def test_invalid_json_aborts_before_any_metadata_write(self):
        for invalid in (b'{ broken }', b'{ "v": NaN }', b'{ "v": Infinity }'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                good = Path(directory) / "a.json"
                bad = Path(directory) / "z.json"
                good.write_bytes(b'{ "a": 1 }')
                bad.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    compact_json_metadata(directory)
                self.assertEqual(good.read_bytes(), b'{ "a": 1 }')
                self.assertEqual(bad.read_bytes(), invalid)

    def test_json_symlinks_and_file_arguments_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.json"
            outside.write_bytes(b'{ "a": 1 }')
            export = root / "export"
            export.mkdir()
            (export / "config.json").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                compact_json_metadata(export)
            for file in (outside, root / "model.safetensors"):
                with self.assertRaisesRegex(ValueError, "directory"):
                    compact_json_metadata(file)
            linked_directory = root / "linked"
            linked_directory.symlink_to(export, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "directory"):
                compact_json_metadata(linked_directory)
            self.assertEqual(outside.read_bytes(), b'{ "a": 1 }')

    def test_atomic_replace_failure_keeps_original_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "config.json"
            file.write_bytes(b'{ "a": 1 }')
            with patch('v2.export_metadata.os.replace', side_effect=OSError('fixture failure')):
                with self.assertRaises(OSError):
                    compact_json_metadata(directory)
            self.assertEqual(file.read_bytes(), b'{ "a": 1 }')
            self.assertEqual(list(Path(directory).iterdir()), [file])

    def test_permissions_and_large_numeric_spellings_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "config.json"
            file.write_bytes(b'{ "large": 1e400, "small": -1e-400 }')
            file.chmod(0o640)
            mode = file.stat().st_mode
            compact_json_metadata(directory)
            self.assertEqual(file.read_bytes(), b'{"large":1e400,"small":-1e-400}')
            self.assertEqual(file.stat().st_mode, mode)


class ExportIntegrationTests(unittest.TestCase):
    def test_opt_in_uses_distinct_export_and_records_post_compaction_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "train/fixture/ckpt-00001"
            adapter.mkdir(parents=True)
            (adapter / "adapters.safetensors").write_bytes(b"fixture adapter")
            original = root / "export/candidates/fixture-ckpt-00001"
            original.mkdir(parents=True)
            raw = b'{ "hidden_size": 8, "text": " keep  spaces " }\n'
            weights = b"unchanged fixture weights"
            (original / "config.json").write_bytes(raw)
            (original / "model.safetensors").write_bytes(weights)
            old_identity = root / "export/fixture-ckpt-00001.identity.json"
            old_identity.write_bytes(b'{ "preserved": true }\n')
            old_digest = content_digest(original)
            exported = original.with_name(original.name + "-compact")

            def make_candidate(adapter_path, name, base=None):
                self.assertEqual(adapter_path, adapter)
                self.assertEqual(name, "fixture-ckpt-00001-compact")
                exported.mkdir()
                (exported / "config.json").write_bytes(raw)
                (exported / "model.safetensors").write_bytes(weights)
                return exported

            with patch.object(training, "ART", root), \
                    patch("lfx.export.candidate", side_effect=make_candidate) as candidate, \
                    patch("builtins.print"):
                identity = training.export("fixture", "ckpt-00001", compact_metadata=True)
            candidate.assert_called_once_with(adapter, "fixture-ckpt-00001-compact", base=None)
            self.assertEqual(content_digest(original), old_digest)
            self.assertEqual((original / "config.json").read_bytes(), raw)
            self.assertEqual(old_identity.read_bytes(), b'{ "preserved": true }\n')
            self.assertEqual((exported / "model.safetensors").read_bytes(), weights)
            self.assertEqual(identity["quantized"], str(exported))
            self.assertEqual(identity["content_digest"], content_digest(exported))
            self.assertNotEqual(identity["content_digest"], old_digest)
            size = sum(p.stat().st_size for p in exported.iterdir() if p.is_file())
            self.assertEqual(identity["size_bytes"], size)
            self.assertEqual(identity["metadata_compaction"]["artifact_after_bytes"], size)
            self.assertGreater(identity["metadata_compaction"]["saved_bytes"], 0)
            self.assertEqual(identity["adapter_sha256"], hashlib.sha256(b"fixture adapter").hexdigest())
            saved = root / "export/fixture-ckpt-00001-compact.identity.json"
            self.assertEqual(json.loads(saved.read_bytes()), identity)

    def test_default_export_keeps_original_name_and_metadata_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "train/fixture/final"
            adapter.mkdir(parents=True)
            (adapter / "adapters.safetensors").write_bytes(b"fixture adapter")
            exported = root / "export/candidates/fixture-final"
            raw = b'{ "keep": "formatting" }\n'
            before = []

            def make_candidate(adapter_dir, name, base=None):
                exported.mkdir(parents=True)
                (exported / "config.json").write_bytes(raw)
                before.append(content_digest(exported))
                return exported

            with patch.object(training, "ART", root), \
                    patch("lfx.export.candidate", side_effect=make_candidate) as candidate, \
                    patch("v2.export_metadata.compact_json_metadata") as compact, \
                    patch("builtins.print"):
                identity = training.export("fixture")
            candidate.assert_called_once_with(adapter, "fixture-final", base=None)
            compact.assert_not_called()
            self.assertEqual((exported / "config.json").read_bytes(), raw)
            self.assertEqual(identity["content_digest"], before[0])
            self.assertEqual(identity["size_bytes"], len(raw))
            self.assertNotIn("metadata_compaction", identity)
            self.assertTrue((root / "export/fixture-final.identity.json").is_file())
            self.assertFalse((root / "export/fixture-final-compact.identity.json").exists())


if __name__ == '__main__':
    unittest.main()
