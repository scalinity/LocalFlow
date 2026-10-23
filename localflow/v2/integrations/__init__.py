"""Opt-in logical-buffer bridges. No provider, store, or keystroke authority.

The application owns a BufferServer and opens its ordinary preview through a
PreviewAdapter. Its insertion coordinator calls PendingEdit.accept only after
explicit acceptance. The terminal client alone updates its own logical buffer.
"""

from .buffers import BufferSnapshot, PendingEdit, PreviewAdapter
from .ipc import BufferServer, default_socket_path

__all__ = ["BufferSnapshot", "PendingEdit", "PreviewAdapter", "BufferServer",
           "default_socket_path"]
