"""The hand on the camera tile: where it is, and what shape to draw.

WHY THIS IS ITS OWN MODULE AND NOT PART OF THE OVERLAY
    Three different questions were living in one file: WHEN the overlay is up
    (`ui/voice_overlay`), WHAT the frame looks like (`ui/voice_paint`), and WHAT
    THE HAND IS DOING — which is this. The third one is the only piece that
    comes from outside the program (`core.workspace_gesture.hand_sample`), and
    the 600-line ceiling fell exactly on it.

    It also keeps the dependency arrow one-way: the painter imports this, the
    overlay imports this, and this imports neither. A `Hand` that lived in the
    painter would have made the state module import the Qt module at collection
    time, and every test in this repo runs with no display.

WHY A `Hand` AND NOT 21 LANDMARKS
    `hand_sample` publishes `(x, y, pinch, scroll)` and the tile needs the first
    three. Holding the landmark array would make the drawing depend on
    mediapipe's ordering, which is the part that changes between versions of it.
"""
from __future__ import annotations

from dataclasses import dataclass


# The artboard is 1280×720; these are its numbers, not a scale factor.
REFERENCE = (1280, 720)
CAMERA = (940, 40, 300, 200)        # x, y, w, h — corner tile


@dataclass(frozen=True)
class Hand:
    """What the tile draws. Deliberately small enough to clamp in one place."""

    x: float = 0.5          # 0..1 across the tile
    y: float = 0.5          # 0..1 down the tile
    pinch: bool = False

    def clamped(self) -> "Hand":
        return Hand(_unit(self.x), _unit(self.y), bool(self.pinch))


def _unit(value) -> float:
    """Clamp to 0..1, and survive a NaN without taking a repaint down.

    The position arrives from a camera thread that can produce anything in the
    first frames after a camera opens. A painter that trusted it would draw a
    skeleton at (nan, nan) — silently nothing, which reads as "the feature is
    broken" rather than "one frame was bad".
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if number != number:                         # NaN, and NaN != NaN
        return 0.5
    return max(0.0, min(1.0, number))


def hand_from_sample(sample) -> Hand:
    """`hand_sample()`'s `(x, y, pinch, scroll)` tuple → what the tile needs.

    Accepts a tuple, a list, or anything with the three attributes, because the
    gesture module has been through both shapes and this function is the seam
    where that is absorbed rather than spread.
    """
    if sample is None:
        return Hand()
    if isinstance(sample, Hand):
        return sample.clamped()
    try:
        if isinstance(sample, (tuple, list)):
            x, y = sample[0], sample[1]
            pinch = bool(sample[2]) if len(sample) > 2 else False
        else:
            x, y = sample.x, sample.y
            pinch = bool(getattr(sample, "pinch", False))
    except (IndexError, TypeError, AttributeError):
        return Hand()
    return Hand(_unit(x), _unit(y), pinch)


def tile_rect() -> tuple[int, int, int, int]:
    """The camera tile, in reference coordinates."""
    return CAMERA


def hand_point(hand: Hand) -> tuple[float, float]:
    """Where the palm is drawn, in reference coordinates.

    Mirrored horizontally: a camera sees the user the way another person does,
    so a hand moving to the user's right arrives on the LEFT of the frame. A
    tile that did not mirror would show the user their own hand going the wrong
    way, and the pointer would follow the screen position rather than the hand.
    """
    x, y, w, h = CAMERA
    clamped = hand.clamped()
    return (x + (1.0 - clamped.x) * w, y + clamped.y * h)


def _finger_joints(palm, spread: float,
                   pose: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Four fingers as `(base, tip)` pairs, in the artboard's own proportions.

    The numbers are `hand()` in `docs/mockups/build.py` scaled to a 0.95 hand:
    bases across the palm, lengths index→little. Keeping them in one list means
    the tile is the same silhouette as the artboard, which is the only thing a
    person comparing the two would notice.
    """
    bases = ((-13, -6), (-4, -10), (5, -9), (13, -5))
    lengths = (34, 40, 37, 30)
    extended = {
        "open": (0, 1, 2, 3), "point": (0,), "pinch": (0,), "fist": (),
        "two": (0, 1),
    }.get(pose, (0, 1, 2, 3))
    joints = []
    for index, (bx, by) in enumerate(bases):
        base = (palm[0] + bx * spread, palm[1] + 8 * spread)
        if index in extended:
            if pose == "pinch" and index == 0:
                # Curled toward the thumb, as the artboard draws it: a straight
                # finger would read as "pointing", which is a different intent.
                tip = (palm[0] - 22 * spread, palm[1] + 2 * spread)
            else:
                tip = (base[0] + bx * 0.22 * spread, base[1] - lengths[index] * spread)
        else:
            tip = (base[0] + bx * 0.06 * spread, base[1] - 9 * spread)
        joints.append((base, tip))
    return joints


def pose_of(hand: Hand) -> str:
    """Which skeleton to draw. Pinch is the only pose this build can observe.

    `core.gesture_os` reports a pinch hold and nothing else about the shape of
    the hand, so anything finer would be drawn from a guess. An open hand is
    the honest default: it is what the camera sees when the user is not
    pinching, and what the artboard draws behind the pinch ring.
    """
    return "pinch" if hand.pinch else "open"


__all__ = ["CAMERA", "Hand", "REFERENCE", "hand_from_sample", "hand_point",
           "pose_of", "tile_rect"]
