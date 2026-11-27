"""Process-lifetime guest switch for JARVIS history and long-term memory.

This is not private browsing: tools, plugins, diagnostics, and AI providers
can still retain data, and the current Live session may contain earlier context.
Once enabled, it stays on until process exit so in-flight work cannot write
transcripts or memory after a premature toggle-off.
"""
import threading
from contextlib import contextmanager

_lock = threading.RLock()
_enabled = False


class GuestModeError(RuntimeError):
    """A persistent JARVIS memory write was refused in guest mode."""


def active() -> bool:
    with _lock:
        return _enabled


def enable() -> None:
    """Wait for already-started guarded writes, then refuse future writes."""
    global _enabled
    with _lock:
        _enabled = True


@contextmanager
def storage_guard():
    """Keep an enable transition atomic with an entire guarded write."""
    with _lock:
        yield not _enabled


def _reset_for_tests():
    global _enabled
    with _lock:
        _enabled = False
