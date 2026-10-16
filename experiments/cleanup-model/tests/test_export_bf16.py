"""CPU-only checks of the bf16-base export path; every subprocess call is a fake and every write is temporary."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lfx import export


class Bf16CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        adapter = self.root / "adapter"
        adapter.mkdir()
        self.adapter = adapter

    def fake_fuse(self, adapter, out, base=None):
        self.calls.append(("fuse", base))
        out.mkdir(parents=True)
        (out / "config.json").write_text("fused")
        return out

    def fake_quantize(self, fused, out):
        self.calls.append(("quantize", fused.exists()))
        out.mkdir(parents=True)
        (out / "config.json").write_text("quantized")
        return out

    def run_candidate(self, **kwargs):
        with patch.object(export, "EXPORT", self.root / "export"), patch.object(export, "fuse", self.fake_fuse), \
                patch.object(export, "quantize", self.fake_quantize):
            return export.candidate(self.adapter, "run-final", **kwargs)

    def test_4b_override_fuses_into_the_local_bf16_4b_then_quantizes_and_drops_the_fused_copy(self):
        out = self.run_candidate(base="/workspace/pod/base", bf16_base="4b")
        self.assertEqual(self.calls, [("fuse", None), ("quantize", True)])
        self.assertEqual((out / "config.json").read_text(), "quantized")
        self.assertFalse((self.root / "export" / "fused-run-final").exists())

    def test_directory_override_fuses_into_that_directory_and_ignores_the_pod_base(self):
        base = self.root / "bf16-9b"
        base.mkdir()
        with patch.object(export, "require_same_template") as check:
            self.run_candidate(base="/workspace/gpu-trial/base-9b", bf16_base=str(base))
        check.assert_called_once_with(base)
        self.assertEqual(self.calls, [("fuse", str(base)), ("quantize", True)])

    def test_without_the_override_a_recorded_base_still_takes_the_in_place_4bit_branch(self):
        quant = '{"quantization": {"bits": 4, "group_size": 64}}'
        base = self.root / "base4bit"
        base.mkdir()

        def fuse_in_place(adapter, out, base=None):
            self.calls.append(("fuse", base))
            out.mkdir(parents=True)
            (out / "config.json").write_text(quant)
            return out

        with patch.object(export, "EXPORT", self.root / "export"), patch.object(export, "fuse", fuse_in_place), \
                patch.object(export, "quantize", self.fake_quantize):
            export.candidate(self.adapter, "run-final", base=str(base))
        self.assertEqual(self.calls, [("fuse", str(base))])

    def test_without_any_base_it_fuses_into_the_bf16_base_and_quantizes_as_before(self):
        self.run_candidate()
        self.assertEqual(self.calls, [("fuse", None), ("quantize", True)])

    def test_an_existing_candidate_is_reused(self):
        existing = self.root / "export" / "candidates" / "run-final"
        existing.mkdir(parents=True)
        (existing / "config.json").write_text("kept")
        self.assertEqual(self.run_candidate(bf16_base="4b"), existing)
        self.assertEqual(self.calls, [])

    def test_a_different_chat_template_names_both_files(self):
        b = self.root / "B"
        other = self.root / "bf16-9b"
        b.mkdir()
        other.mkdir()
        (b / "chat_template.jinja").write_text("template B")
        (other / "chat_template.jinja").write_text("another template")
        with patch.object(export, "b_snapshot", return_value=b):
            with self.assertRaisesRegex(RuntimeError, "chat template differs") as caught:
                export.require_same_template(other)
            self.assertIn(str(other / "chat_template.jinja"), str(caught.exception))
            self.assertIn(str(b / "chat_template.jinja"), str(caught.exception))
            (other / "chat_template.jinja").write_text("template B")
            export.require_same_template(other)


if __name__ == "__main__":
    unittest.main()
