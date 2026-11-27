"""Session-only switches for actions which actually pass through action_gate.

This is not an OS permission or a sandbox. It cannot cover direct device access,
other processes, or stop an action that has already started.
"""
import threading

from core import risk_policy

_lock = threading.RLock()
_allowed = {level: True for level in risk_policy.LEVELS}


def is_allowed(level: str) -> bool:
    with _lock:
        return _allowed.get(level, False)


def set_allowed(level: str, allowed: bool) -> None:
    if level not in risk_policy.LEVELS or not isinstance(allowed, bool):
        raise ValueError('invalid risk level or permission')
    with _lock:
        _allowed[level] = allowed


def snapshot() -> dict[str, bool]:
    with _lock:
        return dict(_allowed)


def reset() -> None:
    """Restore defaults, e.g. for a fresh test process."""
    with _lock:
        _allowed.update({level: True for level in risk_policy.LEVELS})
