"""core/presence_mode.py — how much of the assistant's presence is allowed now.

WHY THIS IS NOT A UI SETTING
    Aktif / Fokus / Senyap is drawn in the tray panel, so the tempting thing is
    to store it in the widget and read it from the widget. That breaks the one
    rule the ambient mode depends on: with no window there is no widget to read.
    The mode also decides whether a TOAST is shown, which happens on a scheduler
    thread long before any widget exists, so the decision has to live below the
    interface.

WHY THESE THREE, AND WHAT EACH ONE ACTUALLY CHANGES
    The names are about the user's attention, not about features:

        active   the assistant may speak up. suggestions and banners are shown.
        focus    the user is working. suggestions are HELD, with a count, and
                 appear when focus ends. Nothing is silently dropped, because a
                 cap the user cannot see is indistinguishable from a bug.
        quiet    the user asked for silence. no banners at all, the orb dims,
                 but a direct question is still answered — quiet is not off.

    Held suggestions live in this module rather than in the toast widget so a
    windows-less session and the tray panel read the same number.

WHAT THIS DOES NOT DO
    It does not persist anything itself. `memory.config_manager` already owns
    the config file and the write helpers; this module holds the in-memory state
    and delegates the save, so a failed write cannot leave the two out of step
    with each other in two different ways.
"""

from __future__ import annotations

import threading

ACTIVE, FOCUS, QUIET = "active", "focus", "quiet"
MODES = (ACTIVE, FOCUS, QUIET)

_state = ACTIVE
_held: list[str] = []
_lock = threading.Lock()

# Optional persistence hooks, installed by the layer that owns the config file.
# Kept as callables so this module stays importable — and testable — without
# `memory.config_manager`, which reads a real file on import.
_reader = None
_writer = None


def bind(read=None, write=None) -> None:
    """Wire persistence. Both may be None, which makes the mode in-memory only."""
    global _reader, _writer
    _reader, _writer = read, write


def current() -> str:
    """The mode in force. Reads the bound store first, so a restart agrees."""
    global _state
    if _reader is not None:
        try:
            value = str(_reader() or "").strip().lower()
        except Exception as e:                      # noqa: BLE001
            print(f"[Presence] could not read the saved mode: {e}")
            value = ""
        if value in MODES:
            with _lock:
                _state = value
    with _lock:
        return _state


def set_mode(mode: str) -> bool:
    """Change the mode. False for an unknown name, so a typo cannot blank it.

    Ending focus flushes whatever was held; the caller does that by draining
    `take_held()` so the toasts appear in the order they were produced.
    """
    global _state
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return False
    with _lock:
        _state = mode
        if mode != FOCUS:
            held = list(_held)
            _held.clear()
        else:
            held = []
    if _writer is not None:
        try:
            _writer(mode)
        except Exception as e:                      # noqa: BLE001
            # The mode took effect in memory. Saying so is better than pretending
            # it will survive a restart.
            print(f"[Presence] could not save the mode: {e}")
    if held:
        # Re-entering active/quiet with held items: they were produced while
        # held and are now allowed, so hand them back to the caller's queue.
        _requeue(held)
    return True


def _requeue(items: list[str]) -> None:
    with _lock:
        _held[:0] = items


def allows_banner() -> bool:
    """Whether a suggestion or toast may be shown right now."""
    return current() != QUIET


def should_hold() -> bool:
    """Whether a suggestion should be held for later rather than shown now."""
    return current() == FOCUS


def offer(text: str) -> str:
    """What to do with one suggestion: 'show', 'hold', or 'drop'.

    Three answers rather than a bool because the caller does something different
    in each case, and collapsing 'hold' into 'drop' is exactly the silent cap
    this module exists to avoid.
    """
    mode = current()
    if mode == QUIET:
        return "drop"
    if mode == FOCUS:
        with _lock:
            _held.append(str(text))
        return "hold"
    return "show"


def held_count() -> int:
    with _lock:
        return len(_held)


def take_held() -> list[str]:
    """Drain the held suggestions, oldest first. Caller shows them if allowed."""
    with _lock:
        items = list(_held)
        _held.clear()
    return items


def reset() -> None:
    """Back to Aktif with nothing held. For tests and for privacy-erase."""
    global _state
    with _lock:
        _state = ACTIVE
        _held.clear()
