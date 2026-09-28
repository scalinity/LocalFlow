"""Owned child process for MERGED-X14 (export rename vs SQLite commit).

    python xm_export_crash_child.py WORKDIR EXPORT_ID

Builds a synthetic store (the M14 world: 12 ASR families, one split
assignment), publishes a PRIOR LocalFlow export at WORKDIR/dataset, then
builds EXPORT_ID into the same destination. The instant the build's
staging directory has been renamed onto the destination — inside the
exporter's publication op, BEFORE the Store commits it — this process
writes WORKDIR/renamed.json (its store paths) and blocks the writer
forever. The parent kills exactly this process (SIGKILL) at that point:
the deterministic post-rename, pre-commit crash. Synthetic data only.
"""

import json
import os
import pathlib
import sys
import threading

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import xm_world as X  # noqa: E402,F401  (paths)
from xm_world import M  # noqa: E402


def main(workdir, export_id, mode="after_rename"):
    work = pathlib.Path(workdir)
    w = M.MWorld()
    w.families(12, asr=True)
    w.splits.assign()
    dest = work / "dataset"
    w.exporter.build(dest, task_views=("asr_supervised",),
                     export_id="export-prior")
    marker = work / "renamed.json"

    def stop_here():
        marker.write_text(json.dumps({
            "db": str(w.tmp / "v2.db"),
            "arts": str(w.store.artifacts_dir),
            "pid": os.getpid()}))
        threading.Event().wait()  # held until the parent kills us

    if mode == "after_rename":
        real_rename = os.rename

        def rename(src, dst, *a, **kw):
            real_rename(src, dst, *a, **kw)
            if pathlib.Path(dst) == dest and ".building-" in str(src):
                stop_here()
        os.rename = rename
    else:  # before_rename: inside the publication op, before its rename
        from localflow.v2.curation import export as export_mod

        def hold(conn, deps):
            stop_here()
        export_mod.DatasetExporter._dependencies_hold = staticmethod(hold)
    w.exporter.build(dest, task_views=("asr_supervised",),
                     export_id=export_id)
    # Reaching here means the hook never fired: say so to the parent.
    (work / "no_rename.json").write_text("{}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
