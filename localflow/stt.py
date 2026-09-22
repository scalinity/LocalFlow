"""Parakeet V3 transcription via MLX — fully on-device, no network after download."""

import os
import pathlib
import threading

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np


def _model_cached(model_id: str) -> bool:
    """True if the model is already in the local HF cache (symlink-aware)."""
    cache = os.environ.get("HF_HUB_CACHE")
    if cache:
        hub = pathlib.Path(cache)
    else:
        home = os.environ.get("HF_HOME")
        base = pathlib.Path(home) if home else pathlib.Path.home() / ".cache" / "huggingface"
        hub = base / "hub"
    snaps = hub / ("models--" + model_id.replace("/", "--")) / "snapshots"
    if not snaps.is_dir():
        return False
    return any(
        (s / "config.json").exists() and any(s.glob("*.safetensors"))
        for s in snaps.iterdir()
    )


class Transcriber:
    """Owns the Parakeet model. load() once (slow); transcribe() per utterance.

    Feeds raw audio straight into the model's log-mel frontend, so no ffmpeg
    and no temp files are involved.
    """

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.ready = threading.Event()
        self.load_error = None
        self._model = None
        self._lock = threading.Lock()
        # M03 (S29.5): the original-sample ranges actually decoded for the
        # last transcribe() call — [[start, end], ...], half-open, exact.
        self.last_decode_ranges = None

    def load(self, on_phase=None):
        """on_phase("loading"|"warming") lets a caller report engine
        lifecycle states (Spec S09) while load() stays one call."""
        try:
            import mlx.core as mx
            from parakeet_mlx import from_pretrained
            from parakeet_mlx.audio import get_logmel

            if on_phase is not None:
                on_phase("loading")
            model = from_pretrained(self.model_id)
            if on_phase is not None:
                on_phase("warming")
            # Warm up on half a second of silence so Metal kernels compile
            # now, not on the first real dictation.
            silence = mx.zeros(int(0.5 * model.preprocessor_config.sample_rate))
            model.generate(get_logmel(silence, model.preprocessor_config))
            self._model = model
        except Exception as e:
            self.load_error = e
            raise
        finally:
            self.ready.set()

    # Recordings longer than this get chunked so memory and latency stay
    # bounded; the library's token-merge stitches the overlaps seamlessly.
    CHUNK_SEC = 60.0
    OVERLAP_SEC = 15.0

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono at the model's sample rate, values in [-1, 1]."""
        self.ready.wait(timeout=600)
        if self._model is None:
            raise RuntimeError(f"model not loaded: {self.load_error}")
        if audio.size == 0:
            self.last_decode_ranges = []
            return ""

        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        model = self._model
        cfg = model.preprocessor_config
        audio = audio.astype(np.float32)

        with self._lock:
            if audio.size / cfg.sample_rate <= self.CHUNK_SEC * 1.5:
                self.last_decode_ranges = [[0, int(audio.size)]]
                mel = get_logmel(mx.array(audio), cfg)
                return model.generate(mel)[0].text.strip()
            return self._transcribe_chunked(model, cfg, audio).strip()

    def _transcribe_chunked(self, model, cfg, audio: np.ndarray) -> str:
        import mlx.core as mx
        from parakeet_mlx.alignment import (
            merge_longest_common_subsequence,
            merge_longest_contiguous,
            sentences_to_result,
            tokens_to_sentences,
        )
        from parakeet_mlx.audio import get_logmel
        from parakeet_mlx.parakeet import DecodingConfig

        chunk = int(self.CHUNK_SEC * cfg.sample_rate)
        overlap = int(self.OVERLAP_SEC * cfg.sample_rate)
        all_tokens = []
        ranges = []
        for start in range(0, len(audio), chunk - overlap):
            end = min(start + chunk, len(audio))
            if end - start < cfg.hop_length:
                break
            ranges.append([int(start), int(end)])
            mel = get_logmel(mx.array(audio[start:end]), cfg)
            result = model.generate(mel)[0]
            offset = start / cfg.sample_rate
            for sentence in result.sentences:
                for token in sentence.tokens:
                    token.start += offset
                    token.end = token.start + token.duration
            if not all_tokens:
                all_tokens = result.tokens
            else:
                try:
                    all_tokens = merge_longest_contiguous(
                        all_tokens, result.tokens, overlap_duration=self.OVERLAP_SEC
                    )
                except RuntimeError:
                    all_tokens = merge_longest_common_subsequence(
                        all_tokens, result.tokens, overlap_duration=self.OVERLAP_SEC
                    )
        self.last_decode_ranges = ranges
        sentences = tokens_to_sentences(all_tokens, DecodingConfig().sentence)
        return sentences_to_result(sentences).text
