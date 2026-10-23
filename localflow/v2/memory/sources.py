"""Bounded, explicitly selected local imports and memory-specific eligibility."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat

MAX_TEXT = 32_000
MAX_FILE_BYTES = 128_000
MAX_IMPORT_FILES = 16
IGNORED = frozenset({'.git', '.cache', '__pycache__', 'node_modules', '.venv',
                     'venv', 'dist', 'build', 'target', '.next', '.ssh', '.aws',
                     '.codex', '.claude', 'cookies', 'keychains'})
SECRET_NAME = re.compile(r'(^\.env($|\.)|credentials|secrets?|id_rsa|id_ed25519|'
                         r'\.(pem|key|p12|pfx|keystore)$)', re.I)
SECRET_TEXT = re.compile(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|'
                         r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b|'
                         r'(?im:^\s*(?:api[_-]?key|password|secret[_-]?key|access[_-]?token)'
                         r'\s*[:=]\s*\S{8,})')
AUTOMATIC_KINDS = frozenset({'user_dictation', 'user_instruction', 'manual_correction'})


def text_checked(text: str, *, max_length=MAX_TEXT) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > max_length:
        raise ValueError('invalid_memory_text')
    if '\x00' in text or SECRET_TEXT.search(text):
        raise ValueError('excluded_secret_or_binary')
    return text.strip()


def approved_root(root) -> Path:
    path = Path(root).expanduser().resolve(strict=True)
    home = Path.home()
    broad = {Path('/'), Path('/Users'), home, home / 'Documents', home / 'Desktop',
             home / 'Downloads', home / 'Library', Path('/Applications'), Path('/System')}
    if not path.is_dir() or path in broad or any(
            p.lower() in IGNORED or SECRET_NAME.search(p) for p in path.parts):
        raise ValueError('choose_specific_project_root')
    return path


def read_approved_file(root: str, selected: str) -> tuple[str, str]:
    """No crawling: one selected text file, resolved under an approved root.

    O_NOFOLLOW plus fstat and resolved-path revalidation bind reads to the file
    inspected before opening. Symlink escape and changed-file reads fail closed.
    """
    base = Path(root).resolve(strict=True)
    path = Path(selected)
    if not path.is_absolute():
        path = base / path
    if any(p.lower() in IGNORED or SECRET_NAME.search(p) for p in path.parts):
        raise ValueError('excluded_project_file')
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        raise ValueError('outside_approved_root') from None
    if any(p.lower() in IGNORED or SECRET_NAME.search(p) for p in relative.parts):
        raise ValueError('excluded_project_file')
    if resolved.suffix.lower() not in {'.txt', '.md', '.json', '.rst', '.py', '.js',
                                      '.ts', '.tsx', '.jsx', '.svelte', '.swift',
                                      '.m', '.h', '.rs', '.c', '.cpp', '.css',
                                      '.html', '.toml', '.yaml', '.yml'}:
        raise ValueError('unsupported_context_file')
    before = resolved.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
        raise ValueError('context_file_limit')
    fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_ino, opened.st_dev) != (before.st_ino, before.st_dev):
            raise ValueError('context_file_changed')
        raw = os.read(fd, MAX_FILE_BYTES + 1)
        after = os.fstat(fd)
        if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError('context_file_changed')
        if path.resolve(strict=True) != resolved or len(raw) > MAX_FILE_BYTES:
            raise ValueError('context_file_changed')
    finally:
        os.close(fd)
    try:
        return str(resolved), text_checked(raw.decode('utf-8-sig'))
    except UnicodeError:
        raise ValueError('context_file_encoding') from None


def eligibility(source: dict, *, automatic=False) -> tuple[bool, str]:
    if source.get('secure') or source.get('denied'):
        return False, 'denied_source'
    if (source.get('quoted') or source.get('kind') in {'model_output', 'selection', 'third_party'}
            or source.get('author_role') in {'model', 'third_party', 'unknown'}):
        return False, 'not_user_evidence'
    if source.get('confidence_label') == 'low':
        return False, 'low_confidence'
    if automatic:
        if source.get('confidence_label') != 'high':
            return False, 'uncertain_authorship_or_transcription'
        if source.get('kind') not in AUTOMATIC_KINDS or source.get('author_role') != 'user':
            return False, 'not_approved_activity'
        if source.get('sensitive') or source.get('temporary'):
            return False, 'requires_deliberate_memory_action'
    return True, 'eligible'
