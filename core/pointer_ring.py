"""The on-screen ring that shows where the camera thinks the hand is.

WHY THIS IS A CORE MODULE AND NOT A STYLESHEET IN THE UI
    There are now TWO places a hand can point: inside the workspace (the window
    moves a widget) and on the desktop (the OS cursor moves). Before this module
    the ring — a 42px cyan circle that highlights when you pinch — existed only
    in `ui/hand_gesture.py` as a Qt stylesheet string, so "the same pointer" was
    only true by coincidence: two copies would drift the first time somebody
    nudged a colour in one of them.

    So the ring is defined once, here, as data. The workspace uses it at its own
    size and the desktop overlay uses it at the same size, and a test asserts
    the two call sites consume the same constants rather than their own copies.

WHAT IT IS NOT
    It does not draw anything and it does not know about Qt. `style()` returns a
    string, `size()` returns an integer, and `where()` returns the top-left
    corner for a ring centred on a point — all testable without a display.

THE ONE THING THAT MATTERS ABOUT `where()`
    The OS pointer's position is decided by `gesture_os.coordinate()`, and the
    ring must sit exactly where that puts the cursor. If the two used different
    arithmetic the ring would drift from the pointer at the screen edges, which
    is precisely where a user looks to check whether the gesture is working. So
    `where()` takes the coordinate it is given and does not re-derive it.
"""
from __future__ import annotations

# The ring's own geometry. 42 is what the workspace has always used, and the
# desktop must look identical or the "same pointer" claim is decorative.
RADIUS = 21
SIZE = RADIUS * 2

# Colours, as the stylesheet fragments that produce them. Kept as strings
# because that is what Qt takes, and kept HERE because both call sites need the
# same string rather than two strings that currently match.
_RESTING = ("background: rgba(20, 92, 120, 45); "
            "border: 2px solid #86eaff; border-radius: 21px;")
_PINCHED = ("background: rgba(20, 150, 180, 95); "
            "border: 3px solid #9afaff; border-radius: 21px;")


def style(pinched: bool) -> str:
    """The ring's stylesheet. Pinch is the only state that changes it."""
    return _PINCHED if pinched else _RESTING


def size() -> int:
    """Width and height of the ring, in device-independent pixels."""
    return SIZE


def where(x: int, y: int, radius: int | None = None) -> tuple[int, int]:
    """Top-left corner for a ring centred on `(x, y)`.

    `x`/`y` are SCREEN coordinates, and the caller gets them from
    `gesture_os.coordinate()` — the same function that places the pointer. This
    function only offsets by the radius; it deliberately does no scaling, so a
    ring can never disagree with the cursor about where the hand is.
    """
    r = RADIUS if radius is None else max(0, int(radius))
    return (int(x) - r, int(y) - r)


def visible(fit, enabled: bool, frozen: bool) -> bool:
    """Should the ring be on screen at all?

    Three conditions and each exists for a different failure:

      * `enabled` — OS mode is on. A ring on the desktop for a mode that is off
        is a pointer the user cannot explain.
      * not `frozen` — we are not driving our own surfaces. A ring over the
        confirmation banner would look like the hand is about to press it.
      * `fit.allowed` — the policy refused this platform or this action.

    The ring is a CLAIM about what the program is doing, so it is shown under
    exactly the conditions the program is doing it.
    """
    return bool(enabled and not frozen and getattr(fit, "allowed", False))


__all__ = ["RADIUS", "SIZE", "size", "style", "visible", "where"]
