"""Explicit installer. Only owned files and an exact marked rc block change."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile

from .ipc import private_directory

START = "# >>> LocalFlow logical buffers >>>\n"
END = "# <<< LocalFlow logical buffers <<<\n"


def _write(path: Path, data: bytes, mode=0o600):
    fd, temp = tempfile.mkstemp(prefix=".localflow-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _rc_text(path: Path) -> tuple[str, int]:
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("unexpected_rc_path_or_symlink")
    if not path.exists():
        return "", 0o600
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("unexpected_rc_file")
    return path.read_bytes().decode("utf-8"), stat.S_IMODE(info.st_mode)


def _block(directory):
    quote = shlex.quote
    return (START + "typeset -g LOCALFLOW_TERMINAL_CLIENT=" +
            quote(str(directory / "localflow-buffer")) + "\nsource " +
            quote(str(directory / "zle.zsh")) + "\n" +
            "for _localflow_map in emacs viins; do\n" +
            "  if [[ \"$(bindkey -M $_localflow_map '^X^L')\" == *'undefined-key' ]]; then\n" +
            "    bindkey -M $_localflow_map '^X^L' localflow-transform\n" +
            "  fi\ndone\nunset _localflow_map\n" +
            "if (( ! ${+functions[codex-localflow]} )); then\n" +
            "  function codex-localflow() {\n" +
            "    VISUAL=" + quote(quote(str(directory / "localflow-editor"))) +
            " EDITOR=" + quote(quote(str(directory / "localflow-editor"))) +
            ' codex "$@"\n' +
            "  }\n  typeset -g LOCALFLOW_OWNED_CODEX_FUNCTION=$functions[codex-localflow]\nfi\n" + END)


def install(directory: Path, editor_root: Path, zshrc: Path | None = None):
    directory, editor_root = Path(directory), Path(editor_root)
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError("unexpected_install_directory")
    if not editor_root.is_absolute() or editor_root.resolve() != editor_root:
        raise ValueError("unexpected_editor_root")
    # Codex itself creates this directory; installation does not broaden roots.
    if editor_root.exists():
        info = editor_root.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or \
                stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("unsafe_editor_root")
    root = Path(__file__).resolve().parents[3]
    command = ("PYTHONPATH=" + shlex.quote(str(root)) + " exec " +
               shlex.quote(sys.executable) + " -m localflow.v2.integrations.cli ")
    editor = directory / "localflow-editor"
    # VISUAL is shell-tokenized by Codex; quote paths with spaces a second time.
    editor_command = shlex.quote(str(editor))
    files = {
        "localflow-buffer": "#!/bin/sh\n" + command + '"$@"\n',
        "localflow-editor": "#!/bin/sh\n" + command + "editor --root " +
            shlex.quote(str(editor_root)) + ' "$@"\n',
        "codex-localflow": "#!/bin/sh\nVISUAL=" + shlex.quote(editor_command) +
            " EDITOR=" + shlex.quote(editor_command) +
            ' exec "${LOCALFLOW_CODEX:-codex}" "$@"\n',
        "zle.zsh": Path(__file__).with_name("zle.zsh").read_text(),
    }
    encoded = {name: data.encode() for name, data in files.items()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in encoded.items()}
    rc, mode = _rc_text(zshrc) if zshrc else ("", 0o600)
    block = _block(directory)
    if START in rc and (rc.count(START) != 1 or block not in rc):
        raise ValueError("rc_block_modified_or_owned_elsewhere")
    manifest = {"version": 1, "files": hashes, "zshrc": str(zshrc) if zshrc else None,
                "rc_block": block if zshrc else None,
                "rc_added_newline": bool(zshrc and rc and not rc.endswith("\n"))}
    if directory.exists():
        private_directory(directory)
        existing = directory / "manifest.json"
        if not existing.is_file() or existing.is_symlink():
            raise ValueError("install_directory_not_owned")
        old = json.loads(existing.read_text())
        if old["files"] != hashes or old["zshrc"] != manifest["zshrc"]:
            raise ValueError("different_installation_exists")
        for name, digest in old["files"].items():
            path = directory / name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("installed_file_modified")
        if zshrc and block not in rc:
            raise ValueError("rc_block_missing")
        return
    private_directory(directory, create=True)
    for name, data in encoded.items():
        _write(directory / name, data, 0o700 if name != "zle.zsh" else 0o600)
    _write(directory / "manifest.json", json.dumps(manifest, indent=2).encode())
    if zshrc and block not in rc:
        _write(zshrc, (rc + ("\n" if manifest["rc_added_newline"] else "") + block).encode(), mode)


def uninstall(directory: Path, zshrc: Path | None = None):
    directory = Path(directory)
    if not directory.exists() and not directory.is_symlink():
        return
    private_directory(directory)
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("manifest_symlink")
    manifest = json.loads(manifest_path.read_text())
    expected_rc = Path(manifest["zshrc"]) if manifest["zshrc"] else None
    if zshrc is not None and Path(zshrc) != expected_rc:
        raise ValueError("different_rc_file")
    for name, digest in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("invalid_manifest")
        path = directory / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("installed_file_modified")
    if expected_rc:
        rc, mode = _rc_text(expected_rc)
        block = manifest["rc_block"]
        if rc.count(block) != 1:
            raise ValueError("rc_block_modified_or_missing")
        # Restore the separator too, even if other unrelated lines were added.
        if manifest["rc_added_newline"]:
            block = "\n" + block
            if block not in rc:
                raise ValueError("rc_separator_changed")
        _write(expected_rc, rc.replace(block, "", 1).encode(), mode)
    for name in manifest["files"]:
        (directory / name).unlink()
    manifest_path.unlink()
    if not any(directory.iterdir()):
        directory.rmdir()
