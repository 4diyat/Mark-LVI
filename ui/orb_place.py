"""Where the desktop orb sits, and which pixels of its window are clickable.

WHY THIS IS NOT IN `ui/orb_overlay.py`
    That module is the WINDOW: it builds a widget, runs a timer, routes presses
    and survives a desktop that will not draw. This one is the arithmetic the
    window depends on — two chunks of it that are pure functions, need no
    display, and are the half a test can actually hold: the overlay's size and
    clickable circle, and the remembered drag position.

    It moved here when `orb_overlay` reached 739 lines against a 600-line
    ceiling. The split is not "make the number smaller": the 600 was a proxy for
    "one module, one job", and these are a different job from the widget's.

WHAT BOARD 1 ASKED FOR, AND WHY THESE NUMBERS
    `n01()` draws a ring of r=28 at (1180, 602) inside a dashed square of
    `r * 2.6` — 146 px — labelled "overlay ±150 px, click-through". Two things
    followed from taking that literally:

    1. THE WINDOW HAD TO GROW. It was `SIZE` (96 px, the ring plus its glow)
       while `paint_ring` draws its alert dot at `r * 2.24` — 62.7 px from the
       centre. Half of 96 is 48. The alarm was drawn 15 px outside the window
       and clipped, so the one indicator that says something needs the user
       never appeared, and no test compared the painter's reach with the
       window's size.

    2. THE CORNERS HAD TO STOP EATING CLICKS. `inside_hit_region` refused them
       AFTER the window had already taken them, so they vanished instead of
       reaching the desktop. `overlay_mask` is what hands that region back.

    The mask is a SQUARE, not a circle. Qt's `QRegion` does elliptical masks,
    but a square INSCRIBED in the hit ring refuses its diagonals — a click the
    hit test accepts would never reach the window. The bounding square is
    slightly generous and never refuses a click that the hit test allows; the
    hit test still decides what a press inside it means.

NOT PROVEN HERE
    That a window manager honours `setMask` on a frameless translucent window.
    The region is asserted to be built from these numbers and handed to the
    window; what Windows does with it is tested on Windows.
"""
from __future__ import annotations

from ui.orb_paint import HIT_RING, OVERLAY_PX, RADIUS, appearance

# A position in `api_keys.json` rather than a window-geometry blob, because
# `update_config` is the one writer this codebase trusts and it already handles
# a corrupt file, a read-only folder and a crash mid-write. Two integers do not
# deserve a second storage path.
POSITION_KEY = "orb_position"


def window_size(mode: str) -> tuple[int, int]:
    """Board 1's overlay box: 146 px, identical in every mode.

    The size does not vary by mode for an older reason than the artboard: a
    window that resizes under the cursor moves its own centre, and the click
    lands on nothing. The ring shrinks inside a fixed frame.
    """
    return (OVERLAY_PX, OVERLAY_PX)


def corner_anchor(area, size: int, margin: int = 24) -> tuple[int, int]:
    """Where the orb sits when nothing is remembered: bottom-right, clear of the
    taskbar.

    `area` is a screen's available geometry — the one thing about placement that
    can be decided without a window manager, and the one thing that was wrong
    for the face bubble on its first try (it sat on the taskbar).
    """
    x = area.x() + area.width() - size - margin
    y = area.y() + area.height() - size - margin
    return (max(area.x(), x), max(area.y(), y))


def hit_region(mode: str = "active") -> tuple[int, int, int]:
    """(cx, cy, radius) of the clickable circle, in window coordinates.

    THE CENTRE IS THE OVERLAY'S, NOT THE OLD 96 px WINDOW'S. That was the bug
    the 146 px change would otherwise have introduced: the painter moved to the
    new centre while the hit test stayed 25 px up and to the left, so clicking
    the drawn orb would have missed it by half a ring.
    """
    centre = OVERLAY_PX // 2
    ring = min(HIT_RING, appearance(mode).radius + 9)
    return (centre, centre, ring)


def inside_hit_region(x: int, y: int, mode: str = "active") -> bool:
    """Whether a point in window coordinates lands on the orb."""
    cx, cy, r = hit_region(mode)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def overlay_mask(mode: str = "active", region_factory=None):
    """A square `QRegion` covering only the clickable circle, for `setMask`.

    `region_factory` exists so the arithmetic can be tested without Qt — the
    same reason `orb_overlay.window_flags(Qt)` takes its enum as an argument.
    """
    _cx, _cy, ring = hit_region(mode)
    side = 2 * ring
    left = OVERLAY_PX // 2 - side // 2
    if region_factory is None:
        from PyQt6.QtGui import QRegion

        region_factory = QRegion
    return region_factory(left, left, side, side)


def screen_area():
    """The primary screen's available geometry, or None without a display."""
    try:
        from PyQt6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        return None if screen is None else screen.availableGeometry()
    except Exception:                               # noqa: BLE001
        return None


def read_position() -> tuple[int, int] | None:
    """The saved top-left corner, or None. Never raises.

    VALIDATED, NOT TRUSTED. The file is user-editable, so this can be a string, a
    one-element list, a float, or a point on a monitor that was unplugged since
    the last run. A position nobody can reach is worse than no position: the orb
    is there, drawn off-screen, and looks exactly like a crashed assistant.
    """
    try:
        from memory.config_manager import load_api_keys

        raw = load_api_keys().get(POSITION_KEY)
    except Exception:                               # noqa: BLE001
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        x, y = int(raw[0]), int(raw[1])
    except (TypeError, ValueError):
        return None

    area = screen_area()
    if area is None:
        return None                    # no screen to check against: use the corner
    try:
        # Keep it REACHABLE: the orb's centre must be on a real screen. A window
        # saved at 1915,1075 of a 1920x1080 desktop is technically "inside" and
        # practically lost.
        centre_x, centre_y = x + OVERLAY_PX // 2, y + OVERLAY_PX // 2
        if not (area.x() <= centre_x <= area.x() + area.width()
                and area.y() <= centre_y <= area.y() + area.height()):
            return None
    except Exception:                       # noqa: BLE001
        return None
    return (x, y)


def write_position(values: dict) -> bool:
    """Write a raw dict, so a test can plant a corrupt value.

    The app never calls this with anything but `{POSITION_KEY: (x, y)}`; the
    parameter shape is a test seam and is named as one.
    """
    try:
        from memory.config_manager import set_config_values

        return bool(set_config_values(**values))
    except Exception as e:                          # noqa: BLE001
        print(f"[JARVIS] Orb overlay: could not save the position — "
              f"{type(e).__name__}: {e}")
        return False


def save_position(x: int, y: int) -> bool:
    """Remember where the user put the orb. Returns whether it was written."""
    return write_position({POSITION_KEY: [int(x), int(y)]})


__all__ = ["POSITION_KEY", "RADIUS", "corner_anchor", "hit_region",
           "inside_hit_region", "overlay_mask", "read_position",
           "save_position", "screen_area", "window_size", "write_position"]
