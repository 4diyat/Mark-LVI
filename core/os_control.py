"""Board 14's operating-system control switch: the pure policy.

WHAT THIS DECIDES
    Whether the bare-hand OS-control pointer pipeline may run. The switch is a
    single ON/OFF fact, but turning it ON is NOT a bare toggle — the artboard
    for board 14 draws a switch that says it is off and a sentence telling the
    user to enable it from the Security page and then confirm with a physical
    keystroke. That sentence is the rule: enabling needs a physical confirmation
    the UI cannot supply on its own, so the policy refuses a bare enable and
    the adapter's confirm path is the only way to arm it.

    Disable is always allowed: turning a control off never needs a physical
    keystroke, and requiring one for a disable would trap the user in a state
    they cannot leave.

WHY A PURE POLICY
    The decision and the transport are separate. This module decides from a
    current state + a desired state + whether a physical confirmation arrived;
    it touches no store and no UI. `actions/os_control.py` reads the current
    state from config, calls `request`, and applies the result through the
    existing `hand_feed.set_gesture_os` transport. A UI that toggled the switch
    directly would be a control with no gate, which is exactly what this
    board's artboard refuses to draw.

THE THREE HONEST STATES
    * OFF, no change, no confirmation — nothing happens, the switch stays off.
    * OFF, desired ON, no confirmation — REFUSED. The gate asks for the
      physical keystroke; the switch must not arm the pointer on its own.
    * OFF, desired ON, confirmed — the decision is to turn it on, and the
      adapter applies it.
"""
from __future__ import annotations

OFF = False
ON = True


class OsControlDecision:
    """What the policy decided, and what the card should state.

    `current` is what was true before, `desired` is what was asked for,
    `allowed` is whether the change may proceed, and `reason` is the sentence
    the UI says back to the user. A decision that is not allowed leaves
    `desired` at the CURRENT state, so the card never claims a change the
    policy refused.
    """

    __slots__ = ("current", "desired", "allowed", "reason")

    def __init__(self, current: bool, desired: bool, allowed: bool,
                 reason: str) -> None:
        self.current = current
        self.desired = desired if allowed else current
        self.allowed = allowed
        self.reason = reason

    @property
    def changed(self) -> bool:
        """Whether this decision actually moves the switch."""
        return self.desired != self.current

    def __repr__(self) -> str:                     # pragma: no cover
        return (f"OsControlDecision(current={self.current}, "
                f"desired={self.desired}, allowed={self.allowed}, "
                f"reason={self.reason!r})")


def is_enabled(read) -> bool:
    """The current state, read through an injected predicate.

    The predicate is `memory.config_manager.get_gesture_os_enabled`. A read
    that raises is treated as OFF: an unreadable config must not arm a
    control the user cannot see, and a missing value is the default.
    """
    try:
        return bool(read())
    except Exception:                              # noqa: BLE001
        return OFF


def request(current: bool, desired: bool, confirmed: bool) -> OsControlDecision:
    """Decide a switch request against the physical-confirmation gate.

    `confirmed` must be the boolean `True`, not a truthy string: a UI that
    sends "yes" has not pressed a physical key, and treating the string as a
    confirmation would let a bare toggle arm the pointer. Enable without the
    boolean is refused; disable always proceeds; a no-op (desired == current)
    is allowed without touching anything.
    """
    if current == desired:
        return OsControlDecision(
            current, desired, True,
            "Kontrol OS sudah dalam keadaan yang diminta.")
    if desired and confirmed is not True:
        return OsControlDecision(
            current, current, False,
            "Kontrol OS membutuhkan konfirmasi fisik untuk diaktifkan.")
    return OsControlDecision(
        current, desired, True,
        "Kontrol OS diaktifkan." if desired else "Kontrol OS dinonaktifkan.")


def summary(enabled: bool) -> str:
    """One sentence for the card, from the state alone."""
    if enabled:
        return "Kontrol OS aktif — kontrol tangan kosong, konfirmasi fisik untuk setiap perubahan."
    return "Kontrol OS nonaktif. Aktifkan dengan konfirmasi fisik."


__all__ = ["OFF", "ON", "OsControlDecision", "is_enabled", "request", "summary"]
