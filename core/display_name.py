"""What to call the assistant in a label, from anywhere.

WHY THIS IS NOT IN ui/window.py ANY MORE
    The helper was written there because two of its call sites are dialog
    handlers with no window in scope. That was true and it was still the wrong
    place: `ui/hud_panels.py` needs it too, and importing it from `ui.window`
    would mean a panel importing the whole window to get one string — the
    circular import this split is trying to avoid, not create.

CONTRACT
    Never raises. A label must not break a dialog, so a missing config reads as
    the default name rather than propagating.
"""
from __future__ import annotations


def assistant_display() -> str:
    """The assistant's name for a label built outside __init__.

    A module-level helper because two of the call sites are dialog handlers
    with no window in scope, and because the name is a SETTING: reading it here
    keeps 'JARVIS' out of the catalogue, where it would be wrong for everyone
    who renamed the assistant (which the setup screen invites).
    """
    try:
        from memory.config_manager import get_assistant_name
        return get_assistant_name()
    except Exception:      # noqa: BLE001 — a label must never break a dialog
        return "JARVIS"
