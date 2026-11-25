"""The shapes every board page in the tray panel is made of. Qt, no state.

WHY THIS IS SHARED AND NOT COPIED
    Thirteen pages of cards, section headers, rows and toggles. Written the
    obvious way each page grew its own `_card()` and its own pitch constant, and
    the artboards are explicit that the pitch is the same on every page of this
    family (72 px rows, 16 px section gaps). Copies drift; a board that drifted
    would not match its artboard, which is the one thing these pages exist to do.

WHERE THE NUMBERS COME FROM
    `ui/tokens.py`, the same numbers the design renders from. Where a board
    disagrees with its siblings (board 10's memory detail is tighter than board
    9's list), the page passes its own pitch and this module does not argue.

WHAT IS NOT HERE
    Any decision. A helper that read `memory_manager` would be a second place
    the truth lives; the pages read their store, these functions place widgets.
"""
from __future__ import annotations

# The panel's own edges, shared with `tray_pages`. Repeated as constants rather
# than imported because `tray_pages` imports THIS module: importing it back
# would be a cycle, and the numbers are the panel's, not the pages'.
PANEL_W, PANEL_H = 460, 660
MARGIN = 24
CONTENT_W = 412                    # 460 − 2·24

ROW_PITCH = 72                     # board 6/9/16's permission-row pitch
CARD_H = 62                        # the 62 px row card inside that pitch
BODY_TOP = 62                      # first row's y, under the title pair

# How far down a page may draw before it would run under the panel's bottom
# edge. A page that needs more than this scrolls or paginates; drawing past it
# is the one thing a fixed-size panel cannot show.
BODY_BOTTOM = PANEL_H - 12


def card_rect(index: int, *, top: int = BODY_TOP, pitch: int = ROW_PITCH,
              height: int = CARD_H, x: int = MARGIN,
              width: int = CONTENT_W) -> tuple[int, int, int, int]:
    """The rectangle behind row `index`, in board 6's geometry.

    `index` is a row number, not a y coordinate: every page in this family
    stacks rows from the same top edge, and a page that passed y directly would
    be a page that could put two rows on top of each other without noticing.
    """
    return (int(x), int(top + index * pitch), int(width), int(height))


def row_ys(count: int, *, top: int = BODY_TOP, pitch: int = ROW_PITCH) -> list[int]:
    """The y of every row, so a page does not do this arithmetic in a loop body."""
    return [int(top + i * pitch) for i in range(int(count))]


def fits(count: int, *, top: int = BODY_TOP, pitch: int = ROW_PITCH,
         bottom: int = BODY_BOTTOM) -> bool:
    """Would `count` rows still end above the panel's bottom edge?

    A page that asks this can say "dan N lagi" instead of drawing rows nobody
    can see. Board 9's own copy counts its rows ("12 hal yang JARVIS ingat") and
    a count that contradicts the list under it is the kind of lie this build
    keeps removing.
    """
    if count <= 0:
        return True
    last = top + (int(count) - 1) * pitch + CARD_H
    return last <= bottom


def visible_count(count: int, *, top: int = BODY_TOP, pitch: int = ROW_PITCH,
                  bottom: int = BODY_BOTTOM) -> int:
    """How many rows fit. Never negative.

    The page draws this many and states the remainder, so nothing is silently
    dropped: board 9's header counts what the panel holds, not what fits.
    """
    count = max(0, int(count))
    laid_out = 0
    while laid_out < count and fits(laid_out + 1, top=top, pitch=pitch,
                                    bottom=bottom):
        laid_out += 1
    return laid_out


def section_ys(count: int, *, top: int, pitch: int, height: int) -> int:
    """Where a section header goes when `count` cards of `height` sit above it.

    Sections stack, and the gap between a section's last card and the next
    header is the pitch's own slack (10 px at the 72/62 pair), which is what the
    artboards draw. Computed rather than written so a page that adds a row
    cannot leave its header floating over the row above.
    """
    return int(top + max(0, count) * pitch + (pitch - height))


def at(parent, cls, rect, text: str = ""):
    """One label placed from a geometry TUPLE.

    `ui/tray_pages._at` takes the four numbers one at a time, which is right for
    a table read aloud and wrong at every call site: `GEOMETRY` stores tuples, so
    every caller writes `_at(page, QLabel, *g["key"], "")` and one extra `*` in
    the wrong place becomes an eight-argument call that fails at build time with
    a message about positional arguments rather than about labels. This takes the
    tuple the table actually holds.
    """
    label = cls(parent)
    label.setGeometry(*rect)
    label.setText(text)
    return label


__all__ = ["BODY_BOTTOM", "BODY_TOP", "CARD_H", "CONTENT_W", "MARGIN", "PANEL_H",
           "PANEL_W", "ROW_PITCH", "at", "card_rect", "fits", "row_ys",
           "section_ys", "visible_count"]


# ── the conversion every page needs and none of them did ────────────────────
#
# THE ARTBOARD PLACES TEXT BY ITS BASELINE; Qt PLACES A LABEL BY ITS TOP EDGE.
# The difference is about 0.7x the font size, and it is why thirteen pages sat
# 7-9 px low even where their x and y matched the drawing. Ignoring it looks
# like a 2 px disagreement in a table and reads as a whole row out of register
# on screen.
#
# THE 0.72 IS CALIBRATED, NOT DERIVED. It is the factor that reproduces the
# values already pinned against board 5 (`tests/test_tray_geometry.py`: the
# artboard's 11.5 px baseline at 404 is the 20 px label box at 396, and
# 404 - 0.72*11.5 = 395.7). Using anything else would move board 5, which is
# measured and correct, to fix pages that were merely wrong.
BASELINE_FACTOR = 0.72


def text_box(x: float, baseline: float, size: float, *,
             width: int = CONTENT_W, height: int | None = None) -> tuple[int, int, int, int]:
    """A QLabel box whose text lands on the artboard's baseline.

    `height` defaults to the artboard's own line box (1.45x the type size,
    rounded), so two labels stacked 20 px apart do not overlap.
    """
    top = round(baseline - size * BASELINE_FACTOR)
    box = height if height is not None else max(14, round(size * 1.45))
    return (int(round(x)), int(top), int(width), int(box))


# The header, from `design/new-ui-proposal/05-tray-panel.png` — the PANEL board, not the
# board artboards. `panel_head()` is what the 460x640 boards call and it draws
# the orb at x=38, pushing its text to x=62; the panel artboard draws the same
# two lines at x=24 with no orb. The panel's existing header is at (24, 22) and
# (24, 46), which is n05's (24, 34) and (24, 54) once the baseline is converted
# — so the header was already right and the pages were drawing a second one.
HEAD_TITLE = text_box(24, 34, 13, width=200)
HEAD_SUBTITLE = text_box(24, 54, 10.5, width=CONTENT_W)


__all__ += ["BASELINE_FACTOR", "HEAD_SUBTITLE", "HEAD_TITLE", "text_box"]
