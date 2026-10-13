"""Reuse the first experiment's implementations with isolated output paths.

Import this module before importing lfx modules. No first-experiment file,
installed model, production setting, or application process is changed.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
OLD = ROOT / "experiments/cleanup-model"
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(ROOT))

from lfx import common as shared

OLD_ART = OLD / "artifacts"
ART = EXP / "artifacts"
CONFIG = copy.deepcopy(shared.CONFIG)
CONFIG["experiment_id"] = "localflow-cleanup-v2-20261013"
CONFIG["paths"]["artifacts"] = str(ART)
CONFIG["paths"]["report_dir"] = "reports/localflow-cleanup-comparison-v2"
# The active budget is $40 beyond the $35.7297738 already recorded when
# the additional allowance was authorized. Retain one dollar of headroom.
CONFIG["claude"].update(spend_cap_usd=75.7297738, stop_at_usd=74.7297738)
CONFIG["targets"]["max_words"] = 650
CONFIG["training"].update(seed=20261013, learning_rate=5e-5)
shared.CONFIG = CONFIG
shared.ART = ART
shared.REPORT_DIR = ROOT / CONFIG["paths"]["report_dir"]

from lfx.common import (read_json, read_jsonl, write_json, write_jsonl,
                        file_sha256, sha256_text, utc_now, anthropic_client)

PRICES = {
    # Haiku requests in this experiment are far below the 100k input tier.
    "claude-haiku-5-5": {"input": 0.05, "output": 0.25, "cache_write": 0.0625, "cache_read": 0.005},
    "claude-sonnet-5-5": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.05},
    "claude-opus-5-5": {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.1},
}


def use_model(model: str):
    CONFIG["claude"]["model"] = model
    CONFIG["claude"]["price_batch"] = PRICES[model]


def c_identity():
    return read_json(OLD_ART / "export/C_identity.json")


def environment():
    import os
    return dict(os.environ, PYTHONPATH=str(EXP),
                HF_HOME=str(Path(CONFIG["paths"]["hf_home"]).expanduser()),
                HF_HUB_OFFLINE="1", TOKENIZERS_PARALLELISM="false")


PYTHON = str(Path(CONFIG["paths"]["localai_python"]).expanduser())
