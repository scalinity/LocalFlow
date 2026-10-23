"""Local CPU sentence embeddings from macOS NaturalLanguage, pinned to en/r1.

Uses the existing PyObjC runtime, without loading an MLX model, requesting an
asset download, or taking the audio GPU lock. Initialization/encode belong on
the caller's background job, never an AppKit callback. Missing OS assets or
PyObjC yield an explicitly degraded lexical mode. No substitute semantic model
is silently selected. A different model/revision requires an index rebuild.
"""

from __future__ import annotations

import threading
from pathlib import Path
import hashlib
import os
import tempfile
import urllib.request

import numpy as np


class LocalEmbedding:
    implementation = 'apple-natural-language-sentence-en-revision-1-d512'
    dimensions = 512

    def __init__(self):
        self._model = None
        self._attempted = False
        self._lock = threading.Lock()
        self.unavailable_reason = None

    def encode(self, text: str) -> np.ndarray | None:
        with self._lock:
            if not self._attempted:
                self._attempted = True
                try:
                    import objc
                    objc.loadBundle('NaturalLanguage', {}, bundle_path=
                                    '/System/Library/Frameworks/NaturalLanguage.framework')
                    cls = objc.lookUpClass('NLEmbedding')
                    self._model = cls.sentenceEmbeddingForLanguage_revision_('en', 1)
                    if self._model is None or self._model.dimension() != self.dimensions:
                        self._model = None
                        self.unavailable_reason = 'local_embedding_asset_unavailable'
                except (ImportError, OSError, RuntimeError, AttributeError):
                    self.unavailable_reason = 'local_embedding_runtime_unavailable'
            if self._model is None:
                return None
            try:
                vector = self._model.vectorForString_(text)
                if vector is None:
                    return None
                result = np.asarray(vector, dtype='<f4')
                norm = np.linalg.norm(result)
                if result.shape != (self.dimensions,) or not np.isfinite(norm) or norm == 0:
                    return None
                return result / norm
            except (ValueError, RuntimeError):
                return None


class MiniLMEmbedding:
    """Pinned quantized MiniLM inference, exclusively on ONNX Runtime CPU.

    Construction and encode never download assets or install packages. The
    explicit download method reports bytes, accepts cancellation, and publishes
    each public artifact atomically. No source text leaves the machine.
    """

    model_id = 'sentence-transformers/all-MiniLM-L6-v2'
    revision = 'c9745ed1d9f207416be6d2e6f8de32d1f16199bf'
    implementation = 'minilm-l6-v2-c9745ed-int8-arm64-mean384-cpu-v1'
    dimensions = 384
    artifacts = {'model.onnx': 'onnx/model_qint8_arm64.onnx', 'tokenizer.json': 'tokenizer.json'}

    def __init__(self, model_dir=None):
        self.model_dir = Path(model_dir) if model_dir else (
            Path.home() / '.cache/localflow/embeddings' / self.implementation)
        cached = (Path.home() / '.cache/huggingface/hub' /
                  ('models--' + self.model_id.replace('/', '--')) / 'snapshots' / self.revision)
        if model_dir is None and all((cached / remote).is_file() for remote in self.artifacts.values()):
            self.model_dir = cached
        self._lock = threading.Lock()
        self._attempted = False
        self._session = self._tokenizer = None
        self.unavailable_reason = None

    def _paths(self):
        return {name: self.model_dir / (name if (self.model_dir / name).is_file() else remote)
                for name, remote in self.artifacts.items()}

    @classmethod
    def download(cls, model_dir=None, *, progress=lambda name, received, total: None,
                 cancelled=lambda: False):
        """Explicit user-requested public download, bounded below 35 MB/file."""
        if cancelled():
            raise InterruptedError('embedding_download_cancelled')
        candidate = cls(model_dir)
        existing = candidate._paths()
        if all(path.is_file() for path in existing.values()):
            return {name: {'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                           'cached': True} for name, path in existing.items()}
        target = candidate.model_dir
        target.mkdir(parents=True, exist_ok=True)
        result = {}
        for filename, remote in cls.artifacts.items():
            if cancelled():
                raise InterruptedError('embedding_download_cancelled')
            url = f'https://huggingface.co/{cls.model_id}/resolve/{cls.revision}/{remote}'
            temporary = None
            try:
                with urllib.request.urlopen(url, timeout=15) as response:
                    total = int(response.headers.get('Content-Length', 0)) or None
                    if total is not None and total > 35_000_000:
                        raise ValueError('embedding_download_size_limit')
                    received, checksum = 0, hashlib.sha256()
                    progress(filename, 0, total)
                    with tempfile.NamedTemporaryFile(dir=target, prefix='.download-', delete=False) as output:
                        temporary = Path(output.name)
                        while True:
                            if cancelled():
                                raise InterruptedError('embedding_download_cancelled')
                            block = response.read(128 * 1024)
                            if not block:
                                break
                            received += len(block)
                            if received > 35_000_000:
                                raise ValueError('embedding_download_size_limit')
                            output.write(block)
                            checksum.update(block)
                            progress(filename, received, total)
                        output.flush()
                        os.fsync(output.fileno())
                if total is not None and received != total:
                    raise ValueError('embedding_download_incomplete')
                if cancelled():
                    raise InterruptedError('embedding_download_cancelled')
                os.replace(temporary, target / filename)
                temporary = None
                result[filename] = {'bytes': received, 'sha256': checksum.hexdigest()}
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return result

    def _load(self):
        self._attempted = True
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            paths = self._paths()
            if not all(path.is_file() for path in paths.values()):
                self.unavailable_reason = 'local_embedding_model_not_downloaded'
                return
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            self._session = ort.InferenceSession(str(paths['model.onnx']),
                                                sess_options=options,
                                                providers=['CPUExecutionProvider'])
            self._tokenizer = Tokenizer.from_file(str(paths['tokenizer.json']))
            self._tokenizer.enable_truncation(max_length=256, stride=32)
        except ImportError:
            self.unavailable_reason = 'local_embedding_runtime_unavailable'
        except (OSError, RuntimeError, ValueError):
            self._session = self._tokenizer = None
            self.unavailable_reason = 'local_embedding_model_unavailable'

    def encode(self, text, *, cancelled=lambda: False):
        with self._lock:
            if not self._attempted:
                self._load()
            if self._session is None or self._tokenizer is None:
                return None
            encoded = self._tokenizer.encode(text)
            chunks = [encoded, *encoded.overflowing]
            # Index all chunks, rather than silently dropping a fact's tail.
            # Memory's input bound makes this finite even for long notes.
            if len(chunks) > 128:
                self.unavailable_reason = 'local_embedding_input_limit'
                return None
            embeddings = []
            for chunk in chunks:
                if cancelled():
                    return None
                inputs = {'input_ids': np.asarray([chunk.ids], dtype=np.int64),
                          'attention_mask': np.asarray([chunk.attention_mask], dtype=np.int64),
                          'token_type_ids': np.asarray([chunk.type_ids], dtype=np.int64)}
                feed = {value.name: inputs[value.name] for value in self._session.get_inputs()}
                output = self._session.run(None, feed)[0]
                if output.ndim == 3:
                    mask = inputs['attention_mask'][..., None]
                    output = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
                vector = np.asarray(output[0], dtype='<f4')
                if vector.shape != (self.dimensions,) or not np.isfinite(vector).all():
                    return None
                embeddings.append(vector)
            result = np.mean(embeddings, axis=0)
            norm = np.linalg.norm(result)
            return result / norm if norm > 0 else None
