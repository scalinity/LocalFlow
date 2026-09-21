"""Configuration loading for LocalFlow."""

import json
import os
import pathlib

DEFAULTS = {
    # STT model (Parakeet V3, multilingual, runs on-device via MLX)
    "model": "mlx-community/parakeet-tdt-0.6b-v3",
    # Hold-to-dictate key: "fn" | "right_option" | "right_command"
    "hotkey": "fn",
    "sample_rate": 16000,
    # Recordings shorter than this are treated as accidental taps
    "min_duration_sec": 0.3,
    # Safety cap — recording auto-stops and transcribes at this length.
    # 0 disables the cap (recording runs until you release the key).
    "max_duration_sec": 0,
    # Append a trailing space so consecutive dictations don't collide
    "append_space": True,
    # Put the previous clipboard contents back after pasting
    "restore_clipboard": True,
    # Input device name substring or index; null = system default
    "input_device": None,
    # Transcript cleanup: "llm" (fillers, self-corrections, formatting via a
    # small local model), "basic" (instant regex filler removal), or "off"
    "cleanup": "llm",
    "cleanup_model": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
    # Write raw and cleaned transcripts to ~/Library/Logs/LocalFlow.log
    # (local only) so cleanup edits can be inspected and debugged
    "log_transcripts": True,
    # V2 retention knobs (Spec S25) — visible and adjustable here; the Hub
    # surfaces them visually from M09. Values are days unless named otherwise.
    "events_retention_days": 14,
    "events_cap_mib": 100,
    "retention_transcript_days": 30,
    "retention_audio_success_days": 7,
    "retention_audio_failed_days": 30,
    "retention_metadata_days": 14,
    "training_buffer_days": 30,
}

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(path=None) -> dict:
    """First match wins: explicit path, $LOCALFLOW_CONFIG, user override
    in Application Support, then the config.json shipped next to the code."""
    candidates = [
        path,
        os.environ.get("LOCALFLOW_CONFIG"),
        pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow" / "config.json",
        ROOT / "config.json",
    ]
    cfg = dict(DEFAULTS)
    for c in candidates:
        if not c:
            continue
        p = pathlib.Path(c)
        if p.exists():
            try:
                cfg.update(json.loads(p.read_text()))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[localflow] ignoring bad config {p}: {e}")
            break
    return cfg
