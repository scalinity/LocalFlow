"""Load the recorded pre-remediation engine without changing live imports.

New cleanup source must not silently change the C and E baselines. The source
revision is local Git history; cached files are verified against its bytes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys

from .common import ART, ROOT, write_json

REVISION = "fac0a48"
PACKAGE = "localflow.v2.cleanup._experiment_baseline"
FILES = ("document_nodes.py", "prompts.py", "validation.py", "engine.py")


def load():
    if PACKAGE + ".engine" in sys.modules:
        return sys.modules[PACKAGE + ".engine"]
    directory = ART / "remediation/baseline_cleanup"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name in FILES:
        content = subprocess.run(
            ["git", "show", f"{REVISION}:localflow/v2/cleanup/{name}"],
            cwd=ROOT, check=True, capture_output=True).stdout
        path = directory / name
        if path.exists() and path.read_bytes() != content:
            raise RuntimeError(f"Recorded baseline source changed: {name}")
        path.write_bytes(content)
        manifest[name] = hashlib.sha256(content).hexdigest()
    init = directory / "__init__.py"
    init.write_text("")
    spec = importlib.util.spec_from_file_location(
        PACKAGE, init, submodule_search_locations=[str(directory)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = package
    spec.loader.exec_module(package)
    for filename in FILES:
        name = PACKAGE + "." + filename[:-3]
        spec = importlib.util.spec_from_file_location(name, directory / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    write_json(ART / "remediation/baseline-manifest.json",
               {"revision": REVISION, "files": manifest})
    return sys.modules[PACKAGE + ".engine"]
