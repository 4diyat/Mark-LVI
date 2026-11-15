"""In-process guard while a human is reviewing an MT5 order.

Not a sandbox or proof of physical input: external apps and already-running
workers can still affect the desktop. Gesture control is stopped separately.
"""
import threading

_lock = threading.Lock()
_active = False


def begin():
    global _active
    with _lock:
        if _active:
            return False
        _active = True
        return True


def end():
    global _active
    with _lock:
        _active = False


def active():
    with _lock:
        return _active
