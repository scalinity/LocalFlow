"""Codex editor-file adapter. Only an explicitly approved editor root is read."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .buffers import MAX_TEXT_BYTES, validate_text


class EditorFile:
    def __init__(self, path: Path, root: Path):
        self.path, self.root = Path(path), Path(root)
        if not self.root.is_absolute() or self.root.resolve() != self.root or \
                not self.path.is_absolute() or self.path.parent != self.root or \
                self.path.resolve() != self.path or self.path.suffix != ".md":
            raise ValueError("unexpected_editor_path")
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or \
                stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("unsafe_editor_root")
        self._dirfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.original, self.identity = self._read()
            self.text = validate_text(self.original.decode("utf-8"))
        except BaseException:
            self.close()
            raise

    def _read(self):
        fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=self._dirfd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or \
                    info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077 or \
                    info.st_size > MAX_TEXT_BYTES:
                raise ValueError("unsafe_editor_file")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(MAX_TEXT_BYTES + 1)
            if len(data) > MAX_TEXT_BYTES:
                raise ValueError("buffer_too_large")
            return data, (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
        finally:
            os.close(fd)

    def commit(self, text: str):
        data = validate_text(text).encode("utf-8")
        if self.root.resolve() != self.root or self.root.stat().st_ino != \
                os.fstat(self._dirfd).st_ino:
            raise ValueError("editor_root_changed")
        current, identity = self._read()
        if identity != self.identity or current != self.original:
            raise ValueError("buffer_changed")
        # Stage beside the owned file, then revalidate before the atomic rename.
        fd, staged = tempfile.mkstemp(prefix=".localflow-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            current, identity = self._read()
            if identity != self.identity or current != self.original:
                raise ValueError("buffer_changed")
            os.replace(Path(staged).name, self.path.name,
                       src_dir_fd=self._dirfd, dst_dir_fd=self._dirfd)
            actual, _ = self._read()
            if actual != data:
                raise ValueError("readback_failed")
            return hashlib.sha256(actual).hexdigest()
        finally:
            try:
                os.unlink(Path(staged).name, dir_fd=self._dirfd)
            except FileNotFoundError:
                pass

    def close(self):
        if self._dirfd is not None:
            os.close(self._dirfd)
            self._dirfd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
