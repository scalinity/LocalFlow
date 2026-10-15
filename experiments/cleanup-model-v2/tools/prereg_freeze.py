"""Bind a preregistration to explicit dataset manifests, rows and judge sources.

Offline and standard-library only. Dataset arguments are pairs: FREEZE_JSON
ROWS_JSONL. Repeat a manifest with each row file that must be bound. No dataset
discovery, model imports or case text is included in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PREREG = Path("docs/v2/research/PREREGISTRATION.md")
JUDGE = Path("experiments/cleanup-model-v2/v2/judge.py")
OUTPUT = Path("experiments/cleanup-model-v2/artifacts/research/prereg")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_path(repo, value):
    path = Path(value)
    return path if path.is_absolute() else repo / path


def identifier(repo, path):
    # Preserve the checkout-relative spelling of ignored artifact symlinks.
    path = path.absolute()
    return str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path)


def rows_identity(path):
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            digest.update(line)
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise ValueError(f"Invalid JSON row at line {line_number}") from None
            if not isinstance(row, dict):
                raise ValueError(f"Expected a JSON object at line {line_number}")
            count += 1
    return digest.hexdigest(), count


def record(repo, datasets, prompts, created_at):
    entries = []
    for freeze, rows in datasets:
        freeze, rows = local_path(repo, freeze), local_path(repo, rows)
        frozen_bytes = freeze.read_bytes()
        manifest = json.loads(frozen_bytes)
        if not isinstance(manifest, dict):
            raise ValueError("A dataset freeze must be a JSON object")
        digest, count = rows_identity(rows)
        files = manifest.get("files", {})
        expected = files.get(rows.name, files.get(rows.stem))
        if isinstance(expected, str) and expected != digest:
            raise ValueError("Dataset row hash disagrees with its freeze manifest")
        entries.append({"freeze_file": identifier(repo, freeze),
                        "freeze_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
                        "rows_file": identifier(repo, rows),
                        "rows_sha256": digest, "row_count": count})
    entries.sort(key=lambda item: (item["freeze_file"], item["rows_file"]))
    if not entries or len({(e["freeze_file"], e["rows_file"]) for e in entries}) != len(entries):
        raise ValueError("Provide distinct dataset freeze/row-file pairs")
    prompt_paths = {identifier(repo, local_path(repo, p)) for p in [JUDGE, *prompts]}
    return {"created_at_utc": created_at, "git_commit": git(repo, "rev-parse", "HEAD"),
            "preregistration": {"file": str(PREREG), "sha256": sha256(repo / PREREG)},
            "datasets": entries,
            "judge_prompt_files": [{"file": p, "sha256": sha256(local_path(repo, p))}
                                   for p in sorted(prompt_paths)]}


def seal(repo, output):
    freeze = output / "FREEZE.json"
    if not freeze.is_file():
        raise ValueError("--seal requires an existing FREEZE.json")
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("--seal requires a clean working tree, including untracked files")
    frozen_bytes = freeze.read_bytes()
    frozen = json.loads(frozen_bytes)
    current = record(repo,
                     [(e["freeze_file"], e["rows_file"]) for e in frozen["datasets"]],
                     [e["file"] for e in frozen["judge_prompt_files"]],
                     frozen["created_at_utc"])
    if current != frozen:
        raise ValueError("Freeze inputs or checkout commit changed; regenerate before sealing")
    with (output / "FROZEN").open("x", encoding="utf-8") as stream:
        stream.write(hashlib.sha256(frozen_bytes).hexdigest() + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--dataset-freeze", nargs=2, action="append", default=[],
                        metavar=("FREEZE_JSON", "ROWS_JSONL"))
    parser.add_argument("--judge-prompt", action="append", default=[], metavar="FILE",
                        help="Additional prompt/template files; v2/judge.py is always included")
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve()
        if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
            raise ValueError("--repo must name the checkout root")
        output = repo / OUTPUT
        if (output / "FROZEN").exists():
            raise ValueError("Already sealed; preserve this record")
        if args.dataset_freeze:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            frozen = record(repo, args.dataset_freeze, args.judge_prompt, stamp)
            output.mkdir(parents=True, exist_ok=True)
            temporary = output / "FREEZE.json.tmp"
            temporary.write_text(json.dumps(frozen, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            temporary.replace(output / "FREEZE.json")
        elif not args.seal or args.judge_prompt:
            raise ValueError("Provide --dataset-freeze pairs, or --seal an existing record")
        if args.seal:
            seal(repo, output)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"prereg freeze failed: {exc}\n")
    print(str(output / ("FROZEN" if args.seal else "FREEZE.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
