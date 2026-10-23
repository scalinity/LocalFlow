"""Private, bounded, same-user AF_UNIX editor handoff; no TCP listener."""
from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import secrets
import select
import socket
import stat
import struct
import sys
import threading

from .buffers import BufferSnapshot, PendingEdit, PreviewAdapter

MAX_FRAME = 2 * 1024 * 1024


def default_socket_path() -> Path:
    return Path.home() / "Library/Caches/LocalFlow/buffers/editor.sock"


def private_directory(path: Path, *, create: bool = False):
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("unexpected_directory_or_symlink")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or \
            stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("directory_must_be_private_and_owned")


def peer_identity(conn: socket.socket) -> tuple[int, int]:
    """Kernel UID/PID, never a client-provided identity."""
    if sys.platform == "darwin":
        uid, gid = ctypes.c_uint(), ctypes.c_uint()
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.getpeereid(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid)):
            raise OSError(ctypes.get_errno(), "getpeereid")
        pid = struct.unpack("i", conn.getsockopt(0, 2, 4))[0]  # LOCAL_PEERPID
        return uid.value, pid
    if hasattr(socket, "SO_PEERCRED"):
        pid, uid, _ = struct.unpack("3i", conn.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid, pid
    raise ValueError("peer_credentials_unavailable")


def send_frame(conn: socket.socket, value: dict):
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_FRAME:
        raise ValueError("frame_too_large")
    conn.sendall(struct.pack("!I", len(data)) + data)


def receive_frame(conn: socket.socket) -> dict:
    def read_exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                raise EOFError("editor_disconnected")
            data.extend(chunk)
        return data
    size = struct.unpack("!I", read_exact(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise ValueError("frame_too_large")
    result = json.loads(read_exact(size))
    if not isinstance(result, dict):
        raise ValueError("invalid_frame")
    return result


class BufferServer:
    """One preview at a time, finite editor lease, promptly revoked on EOF.

    start/stop belong to app lifecycle, after the app's single-instance lock.
    A stopped listener's private socket can be reclaimed after ECONNREFUSED;
    active endpoints, unexpected files, and symlinks remain untouched.
    """

    def __init__(self, adapter: PreviewAdapter, path: Path | None = None,
                 *, timeout: float = 120):
        if not 0 < timeout <= 600:
            raise ValueError("invalid_timeout")
        self.adapter = adapter
        self.path = Path(path) if path is not None else default_socket_path()
        self.timeout = timeout
        self._stopping = threading.Event()
        self._active_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(4)
        self._connections = set()
        self._connection_lock = threading.Lock()
        self._thread = None

    def start(self):
        private_directory(self.path.parent, create=True)
        if len(os.fsencode(self.path)) >= 104:
            raise ValueError("socket_path_too_long")
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or \
                    stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("endpoint_exists")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as existing:
                existing.settimeout(.2)
                try:
                    existing.connect(str(self.path))
                except OSError as error:
                    if error.errno != errno.ECONNREFUSED:
                        raise ValueError("endpoint_exists") from error
                else:
                    raise ValueError("endpoint_exists")
            if self.path.lstat() != info:
                raise ValueError("endpoint_changed")
            self.path.unlink()
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._socket.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self._inode = self.path.lstat().st_ino
            self._socket.listen(4)
            self._socket.settimeout(0.1)
        except Exception:
            self._socket.close()
            raise
        self._thread = threading.Thread(target=self._serve, daemon=True,
                                        name="LocalFlow buffer IPC")
        self._thread.start()
        return self

    def _serve(self):
        while not self._stopping.is_set():
            try:
                conn, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self._slots.acquire(blocking=False):
                conn.close()
                continue
            with self._connection_lock:
                self._connections.add(conn)
            threading.Thread(target=self._handle, args=(conn,), daemon=True,
                             name="LocalFlow editor lease").start()

    def _handle(self, conn):
        edit = None
        acquired = False
        try:
            conn.settimeout(3)
            uid, pid = peer_identity(conn)
            if uid != os.getuid() or pid <= 0:
                raise ValueError("wrong_peer")
            # Challenge is one-use and confined to this authenticated connection.
            token = secrets.token_urlsafe(32)
            send_frame(conn, {"version": 1, "token": token})
            request = receive_frame(conn)
            if request.get("token") != token or request.get("version") != 1:
                raise ValueError("invalid_token_or_version")
            snapshot = BufferSnapshot(**request["snapshot"])
            if snapshot.pid != pid or snapshot.session != str(os.getsid(pid)) or \
                    request.get("revision") != snapshot.revision:
                raise ValueError("peer_or_revision_mismatch")
            acquired = self._active_lock.acquire(blocking=False)
            if not acquired:
                send_frame(conn, {"status": "cancelled", "reason": "preview_busy"})
                return
            edit = PendingEdit(snapshot, token, self.timeout)
            self.adapter.open(edit)
            while edit.active and not self._stopping.is_set():
                ready, _, _ = select.select([conn], [], [], 0.05)
                if ready:
                    # Any subsequent bytes mean cancel; requests cannot be replayed.
                    edit.cancel("editor_disconnected" if not conn.recv(1)
                                else "client_cancelled")
            if edit.result() is None:
                edit.cancel("shutdown" if self._stopping.is_set() else "timeout")
            result = ({"status": "cancelled", "reason": "shutdown"}
                      if self._stopping.is_set() else edit.result())
            result["operation_id"] = token
            send_frame(conn, result)
        except (OSError, EOFError, ValueError, TypeError, KeyError):
            if edit:
                edit.cancel("editor_disconnected")
        except Exception:
            if edit:
                edit.cancel("preview_failed")
        finally:
            if edit:
                try:
                    self.adapter.close(edit)
                except Exception:
                    pass  # a closing AppKit dispatcher cannot retain IPC ownership
            if acquired:
                self._active_lock.release()
            conn.close()
            with self._connection_lock:
                self._connections.discard(conn)
            self._slots.release()

    def stop(self):
        self._stopping.set()
        if self._thread is None:
            return
        self._socket.close()
        with self._connection_lock:
            for conn in tuple(self._connections):
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self._thread.join(timeout=1)
        # Remove only this listener's endpoint, never a replacement or symlink.
        try:
            info = self.path.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_ino == self._inode:
                self.path.unlink()
        except FileNotFoundError:
            pass


def request_edit(snapshot: BufferSnapshot, path: Path | None = None,
                 *, timeout: float = 125) -> dict:
    path = Path(path) if path is not None else default_socket_path()
    private_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or \
            stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("unsafe_endpoint")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(str(path))
        if peer_identity(conn)[0] != os.getuid():
            raise ValueError("wrong_server")
        challenge = receive_frame(conn)
        if challenge.get("version") != 1 or not isinstance(challenge.get("token"), str):
            raise ValueError("unsupported_protocol")
        from dataclasses import asdict
        send_frame(conn, {"version": 1, "token": challenge["token"],
                          "snapshot": asdict(snapshot), "revision": snapshot.revision})
        result = receive_frame(conn)
        if result.get("status") == "accepted":
            if result.get("operation_id") != challenge["token"] or \
                    result.get("revision") != snapshot.revision:
                raise ValueError("response_revision_mismatch")
            from .buffers import validate_text
            validate_text(result["text"])
            cursor = result["cursor"]
            if type(cursor) is not int or not snapshot.start <= cursor <= len(result["text"]):
                raise ValueError("response_cursor_invalid")
            if result["text"] != (snapshot.text[:snapshot.start] +
                                  result["text"][snapshot.start:cursor] +
                                  snapshot.text[snapshot.end:]):
                raise ValueError("response_changed_unowned_region")
        elif result.get("status") != "cancelled":
            raise ValueError("invalid_response")
        return result
