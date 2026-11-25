"""Board 12's window layout: the adapter between policy and the store.

WHAT THIS DOES
    Reads the current layout mode from `memory.config_manager`, asks the pure
    policy in `core.window_layout` what to do, and — only when the policy
    allows a CHANGE — persists the chosen mode. The adapter never invents a
    mode: the card shows the decision, not a guess.

WHY THE ADAPTERS SPLIT
    The policy validates the mode and decides whether it changed anything; it
    touches no store and no UI. This module is the one place that writes the
    choice to config, so a failed write is reported rather than claimed as a
    success — the card and the stored choice would otherwise disagree.
"""
from __future__ import annotations


def read_state():
    """The current layout mode, through the policy's safe read."""
    from core.window_layout import current
    from memory.config_manager import get_window_layout

    return current(get_window_layout)


def choose(mode) -> "LayoutDecision":
    """Request a layout. An unknown mode is refused by the policy."""
    from core.window_layout import request

    return request(read_state(), mode)


def apply(decision) -> bool:
    """Persist an allowed, changed decision; True if the write took.

    Only an allowed, changed decision reaches the store — a no-op or a
    refused request never writes, so re-picking the current mode costs
    nothing and the stored value stays honest.
    """
    if not decision.allowed or not decision.changed:
        return decision.allowed
    from memory.config_manager import save_window_layout

    try:
        ok = bool(save_window_layout(decision.desired))
    except Exception:                              # noqa: BLE001
        ok = False
    if not ok:
        decision.reason = "Susun jendela tidak bisa disimpan."
        return False
    return True


# Re-export for convenience; the type lives in the policy.
from core.window_layout import LayoutDecision  # noqa: E402,F401


__all__ = ["LayoutDecision", "apply", "choose", "read_state"]
