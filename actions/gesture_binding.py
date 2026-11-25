"""Board 15's custom gestures: the adapter between policy and the store.

WHAT THIS DOES
    Reads the current gesture bindings from `memory.config_manager`, asks the
    pure policy in `core.gesture_binding` what to do, and — only when the
    policy allows a CHANGE — persists the chosen binding. The adapter never
    invents an action: the card shows the decision, not a guess.

WHY THE ADAPTERS SPLIT
    The policy validates the action and decides whether it changed anything; it
    touches no store and no UI. This module is the one place that writes the
    choice to config, so a failed write is reported rather than claimed as a
    success — the card and the stored choice would otherwise disagree.
"""
from __future__ import annotations


def read_state() -> dict:
    """The current bindings, through the policy's safe read."""
    from core.gesture_binding import current
    from memory.config_manager import get_gesture_bindings

    return current(get_gesture_bindings)


def rebind(gesture, action) -> "BindingDecision":
    """Request a binding. An unknown gesture or action is refused by the policy."""
    from core.gesture_binding import request

    bindings = read_state()
    return request(gesture, bindings.get(gesture, action), action)


def cycle(gesture) -> "BindingDecision":
    """The decision for the next action in the cycle, from the current one."""
    from core.gesture_binding import next_action, request

    bindings = read_state()
    current_action = bindings.get(gesture)
    return request(gesture, current_action, next_action(current_action))


def apply(decision) -> bool:
    """Persist an allowed, changed decision; True if the write took.

    Only an allowed, changed decision reaches the store — a no-op or a
    refused request never writes, so re-picking the current action costs
    nothing and the stored value stays honest.
    """
    if not decision.allowed or not decision.changed:
        return decision.allowed
    from memory.config_manager import save_gesture_binding

    try:
        ok = bool(save_gesture_binding(decision.gesture, decision.desired))
    except Exception:                              # noqa: BLE001
        ok = False
    if not ok:
        decision.reason = "Pengikatan gestur tidak bisa disimpan."
        return False
    return True


# Re-export for convenience; the type lives in the policy.
from core.gesture_binding import BindingDecision  # noqa: E402,F401


__all__ = ["BindingDecision", "apply", "cycle", "read_state", "rebind"]
