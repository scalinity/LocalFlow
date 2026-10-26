"""Isolated packaged-app data paths and source provenance."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow import config
from localflow.v2 import ids


def test_data_home():
    with patch.dict(os.environ, {}, clear=True):
        assert config.data_home() == pathlib.Path.home()
    with tempfile.TemporaryDirectory() as directory:
        with patch.dict(os.environ, {"LOCALFLOW_DATA_HOME": directory}, clear=True):
            path = config.user_override_path()
            assert path == pathlib.Path(directory) / "Library/Application Support/LocalFlow/config.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"hotkey":"right_option"}')
            assert config.load()["hotkey"] == "right_option"
    for value in ("", "relative"):
        with patch.dict(os.environ, {"LOCALFLOW_DATA_HOME": value}):
            try:
                config.data_home()
            except ValueError:
                pass
            else:
                raise AssertionError("relative override accepted")
    print("ok  default home unchanged; isolated config loaded; relative override refused")


def test_override_without_a_model_keeps_the_cleanup_model():
    # The Hub's settings write a one-key override, and load() takes the first
    # file that exists, so that file must never be able to change the model.
    shipped = json.loads((config.ROOT / "config.json").read_text())
    assert shipped["cleanup_model"] == config.DEFAULTS["cleanup_model"]
    with tempfile.TemporaryDirectory() as directory:
        with patch.dict(os.environ, {"LOCALFLOW_DATA_HOME": directory}, clear=True):
            path = config.user_override_path()
            path.parent.mkdir(parents=True)
            path.write_text('{"retention_usage_days":"keep"}')
            assert config.load()["cleanup_model"] == shipped["cleanup_model"]
    print("ok  an override without a model keeps the shipped cleanup model")


def test_package_revision():
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        with patch.object(ids, "__file__", str(root / "localflow/v2/ids.py")), \
                patch.object(ids.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "git")):
            for record, expected in (
                ({"source_revision": "a" * 40, "dirty": False}, "a" * 40),
                ({"source_revision": "b" * 40, "dirty": True}, "b" * 40 + "+dirty"),
                ({"source_revision": "invalid", "dirty": False}, "unknown:no-git"),
            ):
                (root / "BUILD.json").write_text(json.dumps(record))
                ids._source_revision_cache = None
                assert ids.source_revision() == expected
    ids._source_revision_cache = None
    print("ok  packaged source revision preserves clean/dirty provenance and rejects malformed stamps")


if __name__ == "__main__":
    test_data_home()
    test_override_without_a_model_keeps_the_cleanup_model()
    test_package_revision()
