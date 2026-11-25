"""Board 12's window layout: the pure policy for arranging windows.

WHAT THIS DECIDES
    Which of the three window arrangements the desktop uses: two columns,
    three columns, or focus (one window, the rest dimmed). Board 12's artboard
    draws these as three thumbnails, and for a long time the panel showed them
    with a sentence saying no window manager existed behind them. This is the
    policy that makes the thumbnails a real choice: it validates a requested
    mode, reports whether it changed anything, and states what the selection
    is — with no Qt and no config file, so the tests drive every path.

WHY THE DECISION IS PURE
    The three modes are a fixed set and the choice is one value. Deciding
    whether a request is a real mode, whether it differs from the current one,
    and what the summary says is arithmetic over that value; the store and the
    panel are the adapter's job. A UI that wrote the mode straight into the
    config would be a control with no validation and no honest readout.

THE THREE MODES, IN THE ARTBOARD'S ORDER
    columns2   two columns of windows.
    columns3   three columns of windows.
    focus      one focused window, the rest dimmed behind it.

WHAT THIS DOES NOT DO
    It does not arrange a real desktop. The modes describe a LAYOUT the user
    chose; the actual window arrangement is the desktop's job and this policy
    records and reports the choice honestly without claiming to move windows.
"""
from __future__ import annotations

COLUMNS2 = "columns2"
COLUMNS3 = "columns3"
FOCUS = "focus"

# The artboard's three thumbnails, left to right. Frozen: the layout set is
# the product's, not a setting the user can extend from the panel.
MODES: tuple[str, ...] = (COLUMNS2, COLUMNS3, FOCUS)

# A short label per mode, used by the summary and the readout.
_LABELS = {
    COLUMNS2: "two columns",
    COLUMNS3: "three columns",
    FOCUS: "focus",
}

# The default when no choice has been made: the artboard's first thumbnail.
DEFAULT = COLUMNS2


class LayoutDecision:
    """What the policy decided, and what the page should state.

    `current` is the mode before, `desired` is what was asked for, `allowed`
    is whether the request is a real mode, and `changed` whether it differs
    from the current one. A request that is not a real mode leaves `desired`
    at the CURRENT mode, so the card never claims a layout the policy refused.
    """

    __slots__ = ("current", "desired", "allowed", "reason")

    def __init__(self, current: str, desired: str, allowed: bool,
                 reason: str) -> None:
        self.current = current
        self.desired = desired if allowed else current
        self.allowed = allowed
        self.reason = reason

    @property
    def changed(self) -> bool:
        return self.desired != self.current

    def __repr__(self) -> str:                     # pragma: no cover
        return (f"LayoutDecision(current={self.current}, "
                f"desired={self.desired}, allowed={self.allowed})")


def is_mode(value) -> bool:
    """Whether a value is one of the three real layout modes."""
    return value in MODES


def current(read) -> str:
    """The current mode, read through an injected predicate.

    The predicate is `memory.config_manager.get_window_layout`. A read that
    raises or returns an unknown value falls back to the default: an
    unreadable choice must not leave the card claiming a mode that does not
    exist, and a missing value has a defined answer.
    """
    try:
        value = read()
    except Exception:                              # noqa: BLE001
        return DEFAULT
    return value if is_mode(value) else DEFAULT


def request(current_mode: str, desired) -> LayoutDecision:
    """Decide a layout request against the fixed mode set.

    An unknown mode is REFUSED: the artboard draws three thumbnails, so a
    request for a fourth layout is a control the page does not have, and
    recording it would make the card and the choice disagree. A request for
    the mode already in use is allowed and changes nothing.
    """
    if not is_mode(desired):
        return LayoutDecision(
            current_mode, current_mode, False,
            "Susun jendela tidak mengenali pilihan itu.")
    if desired == current_mode:
        return LayoutDecision(
            current_mode, desired, True,
            "Susun jendela sudah pada pilihan itu.")
    return LayoutDecision(
        current_mode, desired, True,
        f"Susun jendela: {_LABELS[desired]}.")


def summary(mode: str) -> str:
    """One sentence for the card, from the mode alone."""
    return f"Susun jendela: {_LABELS.get(mode, _LABELS[DEFAULT])}."


__all__ = ["COLUMNS2", "COLUMNS3", "FOCUS", "MODES", "DEFAULT",
           "LayoutDecision", "is_mode", "current", "request", "summary"]
