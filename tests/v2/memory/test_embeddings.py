"""CPU-only encoder boundary and explicit download cancellation tests."""

import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

from localflow.v2.memory.embeddings import MiniLMEmbedding


class DownloadResponse(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.headers = {'Content-Length': str(len(value))}


class EmbeddingBoundaryTests(unittest.TestCase):
    def test_existing_complete_cache_is_reused_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / 'model.onnx').write_bytes(b'synthetic-cache-model')
            (path / 'tokenizer.json').write_bytes(b'synthetic-cache-tokenizer')
            with patch('urllib.request.urlopen', side_effect=AssertionError('unexpected_download')):
                result = MiniLMEmbedding.download(path)
            self.assertTrue(all(item['cached'] for item in result.values()))

    def test_download_is_explicit_cancellable_and_preserves_existing_model(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / 'model.onnx').write_bytes(b'previous-complete-model')
            cancelled = [False]
            progress = []
            def report(name, count, total):
                progress.append((name, count, total))
                if count:
                    cancelled[0] = True
            with patch('urllib.request.urlopen', return_value=DownloadResponse(b'x' * 200000)) as request:
                with self.assertRaises(InterruptedError):
                    MiniLMEmbedding.download(path, progress=report, cancelled=lambda: cancelled[0])
                self.assertIn(MiniLMEmbedding.revision, request.call_args.args[0])
            self.assertEqual(b'previous-complete-model', (path / 'model.onnx').read_bytes())
            self.assertEqual(['model.onnx'], sorted(p.name for p in path.iterdir()))
            self.assertGreater(len(progress), 1)

    def test_asset_download_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            response = DownloadResponse(b'small')
            response.headers['Content-Length'] = '35000001'
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(ValueError):
                    MiniLMEmbedding.download(td)
            self.assertEqual([], list(Path(td).iterdir()))

    def test_incomplete_response_is_not_published(self):
        with tempfile.TemporaryDirectory() as td:
            response = DownloadResponse(b'incomplete')
            response.headers['Content-Length'] = '1000'
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'incomplete'):
                    MiniLMEmbedding.download(td)
            self.assertEqual([], list(Path(td).iterdir()))

    def test_pooling_ignores_padding_and_cancellation_stops_inference(self):
        class Session:
            calls = 0
            def get_inputs(self):
                return [types.SimpleNamespace(name=name) for name in
                        ('input_ids', 'attention_mask', 'token_type_ids')]
            def run(self, _, inputs):
                self.calls += 1
                result = np.zeros((1, 3, 384), dtype=np.float32)
                result[0, 0, 0], result[0, 1, 1] = 2, 2
                result[0, 2, :] = 9999
                return [result]
        chunk = types.SimpleNamespace(ids=[101, 102, 0], attention_mask=[1, 1, 0],
                                      type_ids=[0, 0, 0], overflowing=[])
        embedding = MiniLMEmbedding('/unused')
        embedding._attempted = True
        embedding._session = Session()
        embedding._tokenizer = types.SimpleNamespace(encode=lambda _: chunk)
        vector = embedding.encode('Synthetic text.')
        np.testing.assert_allclose(vector[:2], np.array([1, 1]) / np.sqrt(2), rtol=1e-6)
        self.assertTrue(np.all(vector[2:] == 0))
        self.assertIsNone(embedding.encode('cancelled', cancelled=lambda: True))
        self.assertEqual(1, embedding._session.calls)


if __name__ == '__main__':
    unittest.main()
