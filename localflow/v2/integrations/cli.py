"""Editor clients and explicit, reversible integration installation."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .buffers import BufferSnapshot, MAX_TEXT_BYTES, validate_text
from .editor import EditorFile
from .ipc import request_edit


def snapshot(kind, text, cursor, start=0, end=None, tty="", marker=""):
    if not tty:
        for fd in (0, 1, 2):
            if os.isatty(fd):
                tty = os.ttyname(fd)
                break
    return BufferSnapshot(kind, text, cursor, start, len(text) if end is None else end,
                          str(os.getsid(0)), os.getpid(), os.getppid(), tty, os.getcwd(), marker)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    editor = sub.add_parser("editor", help="Codex external editor (whole prompt)")
    editor.add_argument("--root", type=Path, required=True)
    editor.add_argument("file", type=Path)
    zle = sub.add_parser("zle", help="Read ZLE buffer on stdin; emit NUL-framed result")
    zle.add_argument("--cursor", type=int, required=True)
    zle.add_argument("--mark", type=int, required=True)
    zle.add_argument("--region", type=int, choices=(0, 1, 2), required=True)
    zle.add_argument("--tty", default="")
    for action in ("install", "uninstall"):
        command = sub.add_parser(action)
        command.add_argument("--directory", type=Path, required=True)
        command.add_argument("--zshrc", type=Path)
        if action == "install":
            command.add_argument("--editor-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action in ("install", "uninstall"):
            from .install import install, uninstall
            if args.action == "install":
                install(args.directory, args.editor_root, args.zshrc)
            else:
                uninstall(args.directory, args.zshrc)
            return 0
        if args.action == "editor":
            with EditorFile(args.file, args.root) as draft:
                from .origin import terminal_marker
                with terminal_marker() as marker:
                    capture = snapshot("codex", draft.text, len(draft.text), marker=marker)
                    result = request_edit(capture, args.socket)
                if result["status"] == "accepted":
                    # Installed Codex trims the editor result before applying it.
                    # Refuse an edit it cannot return faithfully, instead of
                    # reporting an exact replacement that silently loses data.
                    if result["text"] != result["text"].rstrip():
                        raise ValueError("Codex trims trailing whitespace; keep this result in LocalFlow")
                    draft.commit(result["text"])
                else:
                    # A zero exit would make Codex apply trim_end even to an
                    # unchanged file. Nonzero leaves the composer untouched.
                    return 130
            return 0
        raw = sys.stdin.buffer.read(MAX_TEXT_BYTES + 1)
        text = validate_text(raw.decode("utf-8"))
        start, end = 0, len(text)
        if args.region:
            if not 0 <= args.mark <= len(text):
                raise ValueError("invalid_mark")
            start, end = sorted((args.cursor, args.mark))
            if args.region == 2:
                start = text.rfind("\n", 0, start) + 1
                newline = text.find("\n", end)
                end = len(text) if newline < 0 else newline + 1
        from .origin import terminal_marker
        with terminal_marker() as marker:
            capture = snapshot("zle", text, args.cursor, start, end, args.tty, marker=marker)
            result = request_edit(capture, args.socket)
        if result["status"] != "accepted":
            print("LocalFlow: " + result.get("reason", "cancelled"), file=sys.stderr)
            return 1
        # NUL framing preserves every trailing newline and cannot be evaluated
        # as shell syntax. Text containing NUL was rejected before IPC.
        sys.stdout.buffer.write(str(result["cursor"]).encode() + b"\0" +
                                result["text"].encode("utf-8") + b"\0")
        return 0
    except (OSError, ValueError, EOFError, UnicodeError) as error:
        print("LocalFlow editor unavailable: " + str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("LocalFlow editor cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
