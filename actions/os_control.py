"""Board 14's OS-control switch: the adapter between policy and transport.

WHAT THIS DOES
    Reads the current state from `memory.config_manager`, asks the pure policy
    in `core.os_control` what to do, and — only when the policy allows a
    CHANGE — applies it through the existing `ui.hand_feed.set_gesture_os`
    transport. The adapter never invents a state: the card shows the decision,
    not a guess.

THE GATE IS THE POLICY'S, NOT THE ADAPTER'S
    A bare toggle toward enabling is refused by `request` and never reaches the
    transport. The `confirm` path is the one input the artboard's sentence
    promises — a physical keystroke — and it is the only way to arm the switch.
    A failed apply (the transport returns False) leaves the decision recorded but
    reports the failure in the reason, so the card never claims a change that
    did not take.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                   # pragma: no cover
    from core.os_control import OsControlDecision


def read_state():
    """The current switch state, through the policy's safe read."""
    from core.os_control import is_enabled
    from memory.config_manager import get_gesture_os_enabled

    return is_enabled(get_gesture_os_enabled)


def _apply(decision) -> bool:
    """Apply an allowed, changed decision through the transport; True if it took.

    Only an allowed, changed decision reaches the transport. A no-op never
    touches it, so a toggle that changes nothing costs nothing and reports the
    unchanged state honestly. A transport that refuses is reported in the
    decision's reason rather than being claimed as a success.
    """
    if not decision.allowed or not decision.changed:
        return decision.allowed
    from ui import hand_feed

    try:
        ok = hand_feed.set_gesture_os(decision.desired)
    except Exception:                              # noqa: BLE001
        ok = False
    if not ok:
        decision.reason = "Kontrol OS tidak bisa diaktifkan: pipeline pointer gagal dimulai."
        return False
    return True


def toggle(desired: bool, confirmed: bool = False) -> "OsControlDecision":
    """Request a change and apply it. A bare enable is refused by the gate."""
    from core.os_control import request

    decision = request(read_state(), desired, confirmed)
    _apply(decision)
    return decision


def enable(confirmed: bool = True) -> "OsControlDecision":
    """Arm the switch. The physical confirmation is the caller's promise."""
    return toggle(True, confirmed)


def disable() -> "OsControlDecision":
    """Turn the switch off. Disable always proceeds, no confirmation needed."""
    return toggle(False)


def apply(decision) -> bool:
    """Apply a decision and report whether the change took effect."""
    return _apply(decision)


__all__ = ["apply", "disable", "enable", "read_state", "toggle"]
