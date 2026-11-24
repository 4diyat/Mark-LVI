"""The shapes every board page is built from, now reading `ui/tokens`.

WHY THIS MODULE IS SEPARATE FROM `page_kit`
    `page_kit` holds the geometry HELPERS (`text_box`, `at`) — the arithmetic
    that turns an artboard baseline into a Qt box. That was the right answer
    when the artboards were the source of truth. They are not any more
    (`docs/design/README.md`), so the shapes move here and take their sizes
    from `ui/tokens` instead of from a generated table of artboard
    coordinates.

THE ONE THING THIS MODULE EXISTS TO MAKE POSSIBLE
    `scroll_list()` — a list that scrolls. The panel is 460x660 and the content
    area is 500 px tall (`tokens.CONTENT_H`), which holds six cards at the
    design's pitch. Two of the thirteen pages have lists that can be longer
    than that today (memory, plugins) and the old build drew a FIXED number of
    rows and printed "and N more" underneath, because there was no way to
    scroll. That is a limitation of the container, not a design decision, and
    it is what principle 2 forbids: everything that grows must scroll.

WHY NOT A LAYOUT PER PAGE
    Absolute placement is not the enemy — 102 hand-typed `setGeometry` calls
    were. A card whose height comes from its content, placed in a vertical
    column that scrolls, is still exact; it just does not need a number per
    row. What this module removes is the arithmetic a page had to redo.

WHAT IS STILL ALLOWED
    A page may position a widget it knows the place of (the head, a fixed
    band). It may not pick its own text size, its own card height, or its own
    row pitch — those come from here.
"""
from __future__ import annotations

from ui import tokens

# The colours live in `ui/tray_pages.PALETTES` and are NOT duplicated here.
# Two palettes existed before the design round and they are already measured
# (`tests/test_tokens.py` asserts every text pair clears 4.5:1); copying them
# into a second module is how a palette becomes two palettes.

__all__ = [
    "card_height", "list_pitch", "row_pitch",
    "toggle_style", "pill_style", "card_style",
    "scroll_list",
]


# ── heights, as arithmetic ─────────────────────────────────────────────────

def card_height(lines: int = 2) -> int:
    """The height a card needs for `lines` of content.

    Two shapes, not ten. The artboard drew 60 / 62 / 64 / 66 / 104 / 116 / 130
    / 150 / 158 / 176 px for the same rounded rectangle with different amounts
    of text in it; these two sums are what those ten collapse to. A caller that
    wants a third shape is asking for a component, not a number.
    """
    if lines == 2:
        return tokens.CARD_H_2LINE
    if lines == 3:
        return tokens.CARD_H_3LINE
    raise ValueError(f"a card holds 2 or 3 lines, not {lines}; "
                     "see docs/design/01-tokens.md")


def list_pitch() -> int:
    """Distance from one card's top to the next card's top."""
    return tokens.LIST_PITCH


def row_pitch() -> int:
    """Distance between compact rows (gestures, permissions)."""
    return tokens.ROW_PITCH + tokens.S3


# ── stylesheets, built from tokens ─────────────────────────────────────────
# These return the `setStyleSheet` string a widget needs. They exist so a page
# never writes `border-radius:12px` itself: the radius is a token, and a page
# that typed it would be the 102-`setGeometry` problem in CSS form.

def card_style(palette: dict) -> str:
    return (f"background:{palette['card']};"
            f"border-radius:{tokens.R_CARD}px;"
            f"border:1px solid {palette['line']};")


def toggle_style(palette: dict, *, checked: bool) -> str:
    """A 40x22 switch. The knob is drawn by the indicator, not by text.

    WHY THERE IS NO TEXT IN A TOGGLE. `b15()` draws a bare pill; the state is
    the knob's position. An earlier version wrote "Motion on" inside it, which
    overflowed a 40 px control and said in words what the position says.
    """
    track = palette["accent"] if checked else palette["line"]
    return (f"QPushButton{{background:{track};"
            f"border:none;border-radius:{tokens.TOGGLE_H // 2}px;}}")


def pill_style(palette: dict, *, primary: bool) -> str:
    """A pill button. Primary is filled; secondary is outlined."""
    radius = tokens.PILL_H // 2
    if primary:
        return (f"QPushButton{{background:{palette['accent']};"
                f"color:{palette['on_accent']};"
                f"border:none;border-radius:{radius}px;"
                f"font-size:{tokens.BODY}px;font-weight:{tokens.WEIGHT_LABEL};}}")
    return (f"QPushButton{{background:transparent;"
            f"color:{palette['text']};"
            f"border:1px solid {palette['line_accent']};"
            f"border-radius:{radius}px;"
            f"font-size:{tokens.BODY}px;}}")


# ── the scrolling column ───────────────────────────────────────────────────

def scroll_list(parent, *, x: int, y: int, width: int, height: int):
    """A vertical column of widgets that scrolls when it outgrows its box.

    Returns `(viewport, layout)` — put widgets in the layout, and the viewport
    into the page. THIS IS THE POINT OF THE WHOLE DESIGN ROUND: before it, a
    page drew a fixed number of rows and said "and N more", because a widget
    placed at a fixed y cannot move and the panel cannot grow. Six cards fit
    500 px, fifteen plugins do not, and a memory store has no upper bound.

    Qt IS IMPORTED INSIDE THE FUNCTION, deliberately. `ui/page_kit` and
    `ui/tokens` are importable without a screen and the tests rely on that;
    a module-scope `from PyQt6.QtWidgets import ...` would make every headless
    test that touches this module need Qt, which is how the 600-line split
    files already do it (`ui/pages_admin.py` imports Qt inside each builder).

    `setWidgetResizable(True)` IS NOT OPTIONAL. Without it the inner widget
    keeps its size hint instead of the viewport's width, and a 412 px card
    inside a 412 px viewport gets a horizontal scrollbar for a rounding error.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    viewport = QScrollArea(parent)
    viewport.setGeometry(x, y, width, height)
    viewport.setWidgetResizable(True)
    viewport.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    viewport.setFrameShape(viewport.Shape.NoFrame)
    viewport.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                           "QScrollArea>QWidget>QWidget{background:transparent;}")

    inner = QWidget(viewport)
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(tokens.S3)
    layout.addStretch(1)
    viewport.setWidget(inner)
    return viewport, layout
