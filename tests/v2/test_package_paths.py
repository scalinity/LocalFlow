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
    test_package_revision()
