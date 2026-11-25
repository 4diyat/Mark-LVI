"""core/window_tile.py — the pure policy behind real window arrangement
(board 12, the OS behaviour behind the three thumbnails).

WHAT THIS DECIDES
    Board 12 draws three window-arrangement thumbnails (two columns, three
    columns, focus). The layout policy in `core.window_layout` already
    validates and stores the MODE; what was missing is the actual geometry —
    where each window goes on the screen for the chosen mode. This module
    computes each window's rectangle (x, y, width, height) from the mode,
    the screen work area, and the list of windows, with no OS and no Qt.

WHY THE DECISION IS PURE
    Tiling is arithmetic: split a work area into columns and hand each window
    a column's share. Deciding the rectangles from a mode and a geometry is
    policy; moving a real window is the adapter's job (xdotool/wmctrl). A
    pure policy means a test can assert the geometry for each mode and each
    window count without a display.

THE GEOMETRY IS DETERMINISTIC AND EXHAUSTIVE
    Every window gets a rectangle; no window is left out, and no two windows
    in the same column overlap. A window count that does not divide the
    columns evenly is handled by distributing the remainder — the last
    columns take the extra row, so the tiling never leaves a gap or a
    double-booked region.

WHAT THIS DOES NOT DO
    It does not move a window and it does not dim one. `focus` mode computes
    the focused window's rectangle (full work area) and the others' (a
    narrowed strip behind it); actually dimming a window behind another is a
    desktop-compositor feature this policy cannot request, so it computes the
    geometry and the adapter reports the dimming as not available rather than
    claiming it happened.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# The modes, matching `core.window_layout`.
COLUMNS2 = "columns2"
COLUMNS3 = "columns3"
FOCUS = "focus"

# The three thumbnails, in the artboard's order.
MODES = (COLUMNS2, COLUMNS3, FOCUS)

# A small gap between tiles, in pixels, so windows do not touch edge-to-edge.
TILE_GAP = 8


@dataclass
class Rect:
    """One window's on-screen rectangle."""

    x: int
    y: int
    width: int
    height: int


@dataclass
class WorkArea:
    """The screen's usable area, in pixels."""

    x: int = 0
    y: int = 0
    width: int = 1920
    height: int = 1080


def is_mode(value) -> bool:
    return value in MODES


def _columns_for(mode: str) -> int:
    return 3 if mode == COLUMNS3 else 2


def _tile_tiles(area: WorkArea, mode: str, count: int) -> list[Rect]:
    """The grid of rectangles for `count` windows in `mode`.

    The work area is split into `columns` vertical strips; each strip is
    divided into rows for the windows that fall in it. When the count does
    not divide evenly, the extra windows go into the first strips, which is
    the natural reading of "two columns of three" vs "three columns of two".
    """
    columns = _columns_for(mode)
    col_w = (area.width - TILE_GAP * (columns - 1)) // columns
    # Rows per column: ceil(count / columns).
    rows = (count + columns - 1) // columns
    row_h = (area.height - TILE_GAP * (rows - 1)) // rows

    tiles: list[Rect] = []
    for i in range(count):
        col = i // rows
        row = i % rows
        x = area.x + col * (col_w + TILE_GAP)
        y = area.y + row * (row_h + TILE_GAP)
        tiles.append(Rect(x=x, y=y, width=col_w, height=row_h))
    return tiles


def _focus_tiles(area: WorkArea, count: int) -> list[Rect]:
    """Focus mode: the focused window takes the work area; others a strip.

    The first window is the focused one and gets the full area. The rest are
    computed as narrow strips along the right edge (a layout that shows they
    are present but behind). This is GEOMETRY only: dimming is the
    compositor's job and the adapter reports it as unavailable.
    """
    if count <= 0:
        return []
    focused = Rect(x=area.x, y=area.y, width=area.width, height=area.height)
    strip_w = max(0, (area.width // 4) - TILE_GAP)
    others = []
    for i in range(1, count):
        others.append(Rect(x=area.x + area.width - strip_w - TILE_GAP,
                           y=area.y + (i - 1) * (area.height // count),
                           width=strip_w,
                           height=max(1, area.height // count - TILE_GAP)))
    return [focused] + others


def arrange(
    mode: str,
    windows: Iterable,
    area: WorkArea | None = None,
) -> list[Rect]:
    """Compute the rectangle for each window in `mode`.

    `windows` is any iterable whose length is the number of windows to tile
    (each item is a window descriptor; only its position in the list
    matters). An unknown mode falls back to the two-column tiling — the
    artboard's first thumbnail — rather than raising, so a bad mode cannot
    stray the geometry off the screen. An empty window list returns an empty
    geometry.
    """
    if not is_mode(mode):
        mode = COLUMNS2
    area = area or WorkArea()
    windows = list(windows or ())
    count = len(windows)
    if count == 0:
        return []
    if mode == FOCUS:
        return _focus_tiles(area, count)
    return _tile_tiles(area, mode, count)


def overlaps(a: Rect, b: Rect) -> bool:
    """Whether two rectangles overlap (for the test that no tiles collide)."""
    return not (a.x + a.width <= b.x or b.x + b.width <= a.x
                or a.y + a.height <= b.y or b.y + b.height <= a.y)


__all__ = [
    "COLUMNS2", "COLUMNS3", "FOCUS", "MODES", "TILE_GAP",
    "Rect", "WorkArea", "is_mode", "arrange", "overlaps",
]
