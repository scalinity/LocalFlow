"""A temporary terminal-title marker binds a logical buffer to its pane.

The marker is routing metadata, never project evidence. The terminal's title
stack restores its prior title after the editor returns or is cancelled.
"""
from contextlib import contextmanager
import os
import secrets
import subprocess
import time


def _write_all(descriptor, data):
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0 or written > len(remaining):
            raise OSError('terminal_title_write_incomplete')
        remaining = remaining[written:]


@contextmanager
def terminal_marker():
    descriptor, marker, pushed = None, '', False
    try:
        try:
            descriptor = os.open('/dev/tty', os.O_WRONLY | os.O_NOCTTY)
            if not os.isatty(descriptor):
                os.close(descriptor)
                descriptor = None
            else:
                # Save the title before writing any new one. A failed save
                # must not pop an unrelated preexisting title-stack entry.
                _write_all(descriptor, b'\x1b[22;0t')
                pushed = True
                candidate = 'LocalFlow buffer ' + secrets.token_hex(16)
                _write_all(descriptor, b'\x1b]0;' + candidate.encode('ascii') + b'\x07')
                marker = candidate
        except OSError:
            if descriptor is not None:
                try:
                    _write_all(descriptor, b'\x18')  # cancel a partial escape sequence
                except OSError:
                    pass
        yield marker
    finally:
        if descriptor is not None:
            try:
                if pushed:
                    _write_all(descriptor, b'\x1b[23;0t')
            finally:
                os.close(descriptor)


def has_ancestor(pid, ancestor, *, read_parent=None):
    """Bounded OS process metadata; the client cannot nominate another parent."""
    def native_parent(child):
        result = subprocess.run(['/bin/ps', '-o', 'ppid=', '-p', str(child)],
            capture_output=True, text=True, timeout=.2)
        return int(result.stdout.strip()) if result.returncode == 0 else 0
    read_parent = read_parent or native_parent
    seen = set()
    try:
        for _ in range(16):
            if pid == ancestor:
                return True
            if pid <= 1 or pid in seen:
                break
            seen.add(pid); pid = read_parent(pid)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass
    return False


def window_has_marker(host, pid, marker):
    if not marker or not marker.startswith('LocalFlow buffer ') or len(marker) != 49:
        return False
    if (host.frontmost() or {}).get('pid') != pid:
        return False
    element = host.focused_element_for(pid)
    if element is None or host.element_pid(element) != pid:
        return False
    window = host.attribute(element, 'AXWindow')
    return bool(window is not None and host.element_pid(window) == pid
                and marker in (host.attribute(window, 'AXTitle') or ''))


def await_window_marker(host, edit, ready, missing, schedule, *, timeout=.5,
                        clock=time.monotonic):
    """Let the terminal render its OSC title without blocking AppKit.

    IPC and terminal output use separate queues. Bind the existing focused
    pane before waiting; a later window or pane cannot acquire this request.
    The coordinator still repeats its full policy check before generation.
    """
    front = host.frontmost() or {}
    pid = front.get('pid')
    if not edit.active or pid is None or not has_ancestor(edit.snapshot.pid, pid):
        return False
    element = host.focused_element_for(pid)
    window = host.attribute(element, 'AXWindow') if element is not None else None
    if window is None or host.element_pid(element) != pid or host.element_pid(window) != pid:
        return False
    deadline = clock() + timeout

    def poll():
        if not edit.active:
            return
        current = host.focused_element_for(pid)
        current_window = host.attribute(current, 'AXWindow') if current is not None else None
        if (host.frontmost() or {}).get('pid') != pid or current != element \
                or current_window != window:
            missing()
        elif window_has_marker(host, pid, edit.snapshot.marker):
            ready()
        elif clock() >= deadline:
            missing()
        else:
            schedule(.02, poll)

    schedule(.02, poll)
    return True
