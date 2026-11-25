"""Board 15's custom gestures: the pure policy for rebinding a gesture.

WHAT THIS DECIDES
    Board 15 draws three custom gestures — open palm, pinch, fist — each with
    an action it triggers and an "ubah" (change) cell on the right. For a long
    time that cell said "fixed" because no rebinding existed. This is the
    policy that makes "ubah" a real control: it validates a requested action,
    reports whether it changed anything, and states the new binding — with no
    Qt and no config file, so the tests drive every path.

WHY THE DECISION IS PURE
    A gesture is one of three fixed slots and an action is one of a fixed set.
    Deciding whether a requested action is real, whether it differs from the
    current one, and what the summary says is arithmetic over those values;
    the store and the panel are the adapter's job. A UI that wrote the binding
    straight into the config would be a control with no validation and no
    honest readout.

THE THREE GESTURES, IN THE ARTBOARD'S ORDER
    open_palm  the first card, drawn with "Panggil antarmuka".
    pinch      the second card, drawn with "Klik".
    fist       the third card, drawn with "Jeda media".

WHAT THIS DOES NOT DO
    It does not capture a hand or run a camera. The binding is the CHOICE of
    which action a gesture triggers; recognising the gesture in the camera is
    the bridge's job and this policy records and reports the choice honestly
    without claiming to have recorded a new gesture.
"""
from __future__ import annotations

OPEN_PALM = "open_palm"
PINCH = "pinch"
FIST = "fist"

# The artboard's three gesture cards, left to right. Frozen: the gesture set
# is the product's, not a setting the user can extend from the panel.
GESTURES: tuple[str, ...] = (OPEN_PALM, PINCH, FIST)

# The actions a gesture may trigger, in the order the "ubah" cell cycles.
INTERFACE_CALL = "interface_call"
CLICK = "click"
MEDIA_PAUSE = "media_pause"
SCROLL = "scroll"
STOP = "stop"
SWITCH = "switch"

ACTIONS: tuple[str, ...] = (INTERFACE_CALL, CLICK, MEDIA_PAUSE, SCROLL, STOP, SWITCH)

# A short label per action, used by the summary and the readout.
_LABELS = {
    INTERFACE_CALL: "panggil antarmuka",
    CLICK: "klik",
    MEDIA_PAUSE: "jeda media",
    SCROLL: "gulir",
    STOP: "hentikan",
    SWITCH: "pindah",
}

# The default bindings, matching the artboard's three cards: each gesture
# starts on the action the drawing already shows for it.
DEFAULT_BINDINGS = {
    OPEN_PALM: INTERFACE_CALL,
    PINCH: CLICK,
    FIST: MEDIA_PAUSE,
}


class BindingDecision:
    """What the policy decided, and what the page should state.

    `current` is the action before, `desired` is what was asked for, `allowed`
    is whether the request is a real action, and `changed` whether it differs
    from the current one. A request that is not a real action leaves `desired`
    at the CURRENT action, so the card never claims a binding the policy
    refused.
    """

    __slots__ = ("gesture", "current", "desired", "allowed", "reason")

    def __init__(self, gesture, current: str, desired: str, allowed: bool,
                 reason: str) -> None:
        self.gesture = gesture
        self.current = current
        self.desired = desired if allowed else current
        self.allowed = allowed
        self.reason = reason

    @property
    def changed(self) -> bool:
        return self.desired != self.current

    def __repr__(self) -> str:                     # pragma: no cover
        return (f"BindingDecision(current={self.current}, "
                f"desired={self.desired}, allowed={self.allowed})")


def is_gesture(value) -> bool:
    """Whether a value is one of the three real gesture slots."""
    return value in GESTURES


def is_action(value) -> bool:
    """Whether a value is one of the actions a gesture may trigger."""
    return value in ACTIONS


def next_action(action) -> str:
    """The action after `action` in the cycle the "ubah" cell walks.

    An unknown current action starts the cycle at the first real action, so
    the cell never cycles onto a value the policy does not know.
    """
    if not is_action(action):
        return ACTIONS[0]
    index = ACTIONS.index(action)
    return ACTIONS[(index + 1) % len(ACTIONS)]


def current(read) -> dict:
    """The current bindings, read through an injected predicate.

    The predicate is `memory.config_manager.get_gesture_bindings`. A read that
    raises, returns a non-dict, or carries unknown gesture/action pairs falls
    back to the defaults: an unreadable binding must not leave the card
    claiming an action that does not exist, and a missing value has a defined
    answer.
    """
    try:
        value = read()
    except Exception:                              # noqa: BLE001
        return dict(DEFAULT_BINDINGS)
    if not isinstance(value, dict):
        return dict(DEFAULT_BINDINGS)
    out = dict(DEFAULT_BINDINGS)
    for gesture in GESTURES:
        action = value.get(gesture)
        if is_action(action):
            out[gesture] = action
    return out


def request(gesture, current_action, desired) -> BindingDecision:
    """Decide a rebinding request against the fixed action set.

    An unknown gesture is REFUSED: the artboard draws three cards, so a
    request for a fourth gesture is a control the page does not have, and
    recording it would make the card and the choice disagree. An unknown action
    is refused the same way. A request for the action already bound changes
    nothing.
    """
    if not is_gesture(gesture):
        return BindingDecision(
            gesture, current_action, current_action, False,
            "Gestur tidak mengenali pilihan itu.")
    if not is_action(desired):
        return BindingDecision(
            gesture, current_action, current_action, False,
            "Aksi tidak dikenal untuk gestur ini.")
    if desired == current_action:
        return BindingDecision(
            gesture, current_action, desired, True,
            f"Gestur sudah pada aksi itu: {_LABELS[desired]}.")
    return BindingDecision(
        gesture, current_action, desired, True,
        f"Gestur {_LABELS_GESTURE[gesture]} sekarang: {_LABELS[desired]}.")


_LABELS_GESTURE = {
    OPEN_PALM: "telapak terbuka",
    PINCH: "cubit",
    FIST: "kepalan",
}


def summary(gesture) -> str:
    """One sentence for the card, from the gesture's binding alone."""
    action = DEFAULT_BINDINGS.get(gesture, DEFAULT_BINDINGS[OPEN_PALM])
    return f"Gestur {_LABELS_GESTURE.get(gesture, _LABELS_GESTURE[OPEN_PALM])}: " \
           f"{_LABELS.get(action, _LABELS[INTERFACE_CALL])}."


__all__ = ["OPEN_PALM", "PINCH", "FIST", "GESTURES", "ACTIONS", "INTERFACE_CALL",
           "CLICK", "MEDIA_PAUSE", "SCROLL", "STOP", "SWITCH", "DEFAULT_BINDINGS",
           "BindingDecision", "is_gesture", "is_action", "next_action", "current",
           "request", "summary"]
