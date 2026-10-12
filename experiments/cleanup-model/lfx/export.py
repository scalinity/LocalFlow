"""Fuse a LoRA checkpoint into the bf16 base and quantize it with B's recipe.

The quantization command is the one shown (by ``recipe_check.json``) to
reproduce mlx-community/Qwen3.5-4B-4bit bit-for-bit from the same base, so
B and C differ only by the fine-tune. Tokenizer and template files are copied
verbatim from B (fuse/convert re-save them under the venv's transformers).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .common import ART, CONFIG, expand, file_sha256, utc_now, write_json

EXPORT = ART / "export"
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "vocab.json", "merges.txt")


def _py() -> str:
    return str(expand(CONFIG["paths"]["localai_python"]))


def _env() -> dict:
    env = dict(os.environ)
    env.update(HF_HOME=str(expand(CONFIG["paths"]["hf_home"])), HF_HUB_OFFLINE="1")
    return env


def b_snapshot() -> Path:
    from .capture import snapshot
    b = CONFIG["models"]["B"]
    return snapshot(b["repository_id"], b["revision"])


def fuse(adapter_dir: Path, out: Path) -> Path:
    from .train import base_path
    if out.exists():
        shutil.rmtree(out)
    subprocess.run([_py(), "-m", "mlx_lm", "fuse", "--model", str(base_path()), "--adapter-path", str(adapter_dir),
                    "--save-path", str(out)], check=True, env=_env(), stdout=subprocess.DEVNULL)
    return out


def quantize(fused: Path, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    subprocess.run([_py(), "-m", "mlx_lm", "convert", "--hf-path", str(fused), "--mlx-path", str(out), "-q",
                    "--q-bits", "4", "--q-group-size", "64"], check=True, env=_env(), stdout=subprocess.DEVNULL)
    b = b_snapshot()
    for f in TOKENIZER_FILES:
        if (b / f).exists():
            shutil.copyfile(b / f, out / f)
    assert file_sha256(out / "chat_template.jinja") == file_sha256(b / "chat_template.jinja"), "template differs from B"
    q = json.loads((out / "config.json").read_text()).get("quantization", {})
    assert q.get("bits") == 4 and q.get("group_size") == 64, q
    return out


def candidate(adapter_dir: Path, name: str, keep_fused: bool = False) -> Path:
    """Fuse + quantize one checkpoint into artifacts/export/candidates/NAME."""
    fused = EXPORT / f"fused-{name}"
    q = EXPORT / "candidates" / name
    if (q / "config.json").exists():
        return q
    fuse(adapter_dir, fused)
    quantize(fused, q)
    if not keep_fused:
        shutil.rmtree(fused)
    return q


def content_digest(model_dir: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(model_dir.iterdir()):
        if f.is_file():
            h.update(f.name.encode())
            h.update(file_sha256(f).encode())
    return h.hexdigest()[:40]


def install_c(q_dir: Path, adapter_dir: Path, selection: dict) -> dict:
    """Place C in the LocalAI hub (HF cache layout) and the adapter in
    ~/Documents/LocalAI/adapters; never touches LocalFlow's own cache/config."""
    hub = expand(CONFIG["paths"]["hf_home"]) / "hub"
    repo = CONFIG["models"]["C"]["repository_id"]
    root = hub / f"models--{repo.replace('/', '--')}"
    digest = content_digest(q_dir)
    snap = root / "snapshots" / digest
    if not snap.exists():
        snap.mkdir(parents=True)
        for f in q_dir.iterdir():
            shutil.copyfile(f, snap / f.name)
        (root / "refs").mkdir(exist_ok=True)
        (root / "refs" / "main").write_text(digest)
    adapters = expand(CONFIG["paths"]["adapters_root"]) / "localflow-cleanup-qwen3.5-4b-r16"
    adapters.mkdir(parents=True, exist_ok=True)
    for f in adapter_dir.iterdir():
        shutil.copyfile(f, adapters / f.name)
    size = sum(f.stat().st_size for f in snap.iterdir())
    info = {"installed": utc_now(), "repository_id": repo, "revision": digest, "snapshot_path": str(snap),
            "size_bytes": size, "adapter_path": str(adapters),
            "adapter_sha256": file_sha256(adapters / "adapters.safetensors"),
            "base": CONFIG["models"]["base_bf16"], "quantization": "4-bit affine, group 64 (identical command to B)",
            "tokenizer_files_from": str(b_snapshot()), "selection": selection,
            "weights_sha256": {f.name: file_sha256(f) for f in snap.iterdir() if f.suffix == ".safetensors"}}
    write_json(EXPORT / "C_identity.json", info)
    write_json(adapters / "identity.json", info)
    return info


def fused_logit_check(adapter_dir: Path, fused_dir: Path, prompt: str) -> dict:
    """Fusing must preserve the adapter: |fused - (base+adapter)| should be far
    smaller than the adapter's own effect |base - (base+adapter)|."""
    code = f"""
import mlx.core as mx, json
from mlx_lm import load
p = {prompt!r}
m, t = load({str(_base())!r}, adapter_path={str(adapter_dir)!r})
ids = mx.array([t.encode(p)])
a = m(ids)[0, -16:].astype(mx.float32); mx.eval(a); del m
m, _ = load({str(_base())!r})
base = m(ids)[0, -16:].astype(mx.float32); mx.eval(base); del m
m, _ = load({str(fused_dir)!r})
f = m(ids)[0, -16:].astype(mx.float32); mx.eval(f)
r = lambda x: (mx.mean(mx.abs(x)).item(), mx.max(mx.abs(x)).item())
print(json.dumps({{"fused_vs_adapter_mean_max": r(f - a), "base_vs_adapter_mean_max": r(base - a),
                  "argmax_fused_eq_adapter": float(mx.mean((f.argmax(-1) == a.argmax(-1)).astype(mx.float32)).item()),
                  "argmax_base_eq_adapter": float(mx.mean((base.argmax(-1) == a.argmax(-1)).astype(mx.float32)).item())}}))
"""
    out = subprocess.run([_py(), "-c", code], capture_output=True, text=True, env=_env(), check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def _base() -> Path:
    from .train import base_path
    return base_path()
