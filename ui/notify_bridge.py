"""The shell's side of the desktop-notification policy.

WHY THIS IS A MODULE
    `core/notify.Notifier` owns the policy — one message per finished turn, at
    most once a minute, never while the interface is visible. The shell owns
    two facts the policy needs: the current state word, and the last sentence
    the assistant said. Keeping that glue here means `ui/shell.py` fits under
    its line ceiling and the policy can be read in one place instead of two.

WHY IT IS THREAD-SAFE WITHOUT A QUEUE
    It touches no widget. `get_desktop_notifications()` reads one JSON key,
    and `Notifier.observe` decides and then sends — the sending is
    `core/notify`'s business, and it already owns its own locks. So this can be
    called from whatever thread changed the state, and it must be: a
    notification that waited behind the Qt thread would arrive after the words
    it was about.
"""
from __future__ import annotations


def announce(shell, word: str) -> None:
    """Feed the notification policy. Never raises, reports once."""
    from ui.shell import _note_once

    try:
        from core.notify import Notifier
        from memory.config_manager import get_desktop_notifications

        if not get_desktop_notifications():
            return
        notifier = getattr(shell, "_notifier", None)
        if notifier is None:
            notifier = Notifier(visible=lambda: interface_visible(shell))
            shell._notifier = notifier
        notifier.observe(word, getattr(shell, "_last_answer", "") or "")
    except Exception as e:                          # noqa: BLE001
        # A status update must never be the thing that raises — but silence
        # here is "notifications never appear", which is unanswerable.
        _note_once("notify", f"notification policy unavailable — "
                             f"{type(e).__name__}: {e}")


def interface_visible(shell) -> bool:
    """Whether anything the user can SEE is on screen.

    `Notifier` suppresses a notification while this is True: a banner that
    repeats what is already in front of the reader is the fastest way to get
    the feature switched off. With no window, "visible" means the face.
    """
    bubble = getattr(shell, "_bubble", None)
    surface = getattr(shell, "_main_surface", None)
    window = getattr(surface, "window", None)
    return bool(getattr(bubble, "visible", False) or
                (window is not None and window.isVisible()))
