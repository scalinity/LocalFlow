"""Row-order determinism: two stores with identical content imported in
different orders must yield identical alias order (the alias tuple is part of
the snapshot revision serialization). Case-variant aliases (admitted by
import, R3) tie under 'ORDER BY alias COLLATE NOCASE'."""
import subprocess, os, json, sys
PY = "/home/user/LocalFlow/.venv/bin/python"
outs = {}
for order in ("fwd", "rev"):
    for seed in ("0", "12345"):
        p = subprocess.run([PY, "p06_det_child.py", order], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1"))
        outs[(order, seed)] = p.stdout.strip() or p.stderr[-500:]
for k, v in outs.items():
    print(k, v)
vals = set(outs.values())
print("distinct alias orders:", len(vals))
sys.exit(1 if len(vals) > 1 else 0)
