"""Run with LocalFlow's production .venv: load a cleanup model through the
production ModelRunner and clean one dictation with the real engine.

    loader_check.py MODEL_PATH REPO_ROOT ["text to clean"]
"""
import json
import sys
import time

sys.path.insert(0, sys.argv[2])
from localflow.v2.cleanup import ModelRunner  # noqa: E402

text = sys.argv[3] if len(sys.argv) > 3 else "Um, book the room for Tuesday, no wait, Thursday at 3 and tell Priya."
r = ModelRunner(sys.argv[1])
t = time.perf_counter()
r.load()
res = r.engine().clean(text, locale="en-US")
print(json.dumps({"model": sys.argv[1], "load_s": round(time.perf_counter() - t, 2), "path": res.path,
                  "text": res.text, "template_revision": r.template_revision}))
