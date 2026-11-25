"""The design's numbers, in one place.

WHY THIS MODULE EXISTS
    `docs/mockups/build.py` used **15 text sizes for about 5 roles** and **15
    vertical pitches** between two of them. Every one of those numbers was
    plausible on its own artboard and the set of them was incoherent: 10 / 10.5
    / 11 / 11.5 px were used interchangeably for the same kind of sentence.
    Copying that faithfully produced a panel that felt wrong while matching the
    drawing, because the drawing has no rule behind it.

    This module IS the rule. `docs/design/01-tokens.md` explains where each
    number comes from; this file is the same numbers in a form code can use.

THE RULE THIS FILE IS BUILT ON
    A page never writes a pixel size. It writes `tokens.BODY`. That is not
    style — it is the only thing that keeps the next page from inventing a 14th
    text size, and `tests/test_tokens.py` plus the no-literals test in
    `tests/test_design_tokens.py` are what enforce it.

WHAT IS NOT HERE
    No Qt, no imports from `ui/`. This module is data, and a test can import it
    without a screen — which matters, because the numbers are the one thing
    every page agrees on.

TRACEABILITY
    Every value below is one of:
      * MEASURED from `build.py` (the comment says how many times it appears),
      * DERIVED by arithmetic from other tokens (the comment gives the sum), or
      * DECLARED as a decision (the comment says so, and says why).
    A number that cannot be traced to one of those is a mistake, not a token.
"""
from __future__ import annotations

# ── Text ─────────────────────────────────────────────────────────────────────
# Six roles. `docs/design/01-tokens.md` maps each to the artboard sizes it
# replaces; the counts there are the number of call sites that used them.
LABEL = 11        # section marker: capitals, wide tracking. the ONE small size
META = 12         # a card's second line, help text, units
BODY = 13         # conversation text, row labels, button labels
CARD_TITLE = 16   # a card's name. DECLARED: artboard used 12.5-13, which sat
                  # 1 px from the body text and read as no hierarchy at all.
DISPLAY = 26      # large numbers, the installer's one question
WORDMARK = 13     # "JARVIS" in the panel head, weight 700

# Line box as a multiple of the type size. This is the factor the panel has
# always used (it reproduces `404 - 0.72 * 11.5 = 396`, pinned by
# `tests/test_tray_geometry.py`), kept because changing it would move every
# baseline on every page at once.
BASELINE_FACTOR = 0.72
LINE_FACTOR = 1.45

# Weight and tracking. Tracking is for capitals and the wordmark only: letters
# spaced out slow reading down.
WEIGHT_TITLE = 700
WEIGHT_LABEL = 500
TRACK_LABEL = 1.8
TRACK_WORDMARK = 1.4

# ── Spacing ──────────────────────────────────────────────────────────────────
# A 4 px scale, eight steps, nothing between them. The artboard had 15
# different pitches between the same two kinds of thing.
S1 = 4    # between a label and its value inside one row
S2 = 8    # between a card's title and its content
S3 = 12   # between cards in one list
S4 = 16   # padding inside a card, vertical
S5 = 24   # THE PANEL EDGE. every page starts at x=24. MEASURED: 135 call sites
S6 = 32   # between a section marker and its cards
S7 = 48   # between the panel head and the first content
S8 = 64   # between unrelated blocks

# ── Shape ────────────────────────────────────────────────────────────────────
R_CARD = 12    # cards, inputs, code boxes. MEASURED: 25 call sites
R_PANEL = 16   # the panel's own corner
R_PILL = 21    # pills, segments, toggles (h/2 for h=42); artboards use h/2
R_INSET = 10   # an element inside a card

# ── Panel geometry ───────────────────────────────────────────────────────────
# 460x660 is the PANEL size (nNN artboards). The bNN artboards draw 460x640
# and are 20 px short of the window the panel actually is — one of the two
# numbers had to be wrong, and the panel has been 660 since board 5.
PANEL_W = 460
PANEL_H = 660

CONTENT_W = PANEL_W - 2 * S5        # 412. every full-width element is this wide
CARD_PAD = 20                       # content starts at 24 + 20 = 44. MEASURED: 50x

# The head: orb at (24,40), title baseline 36 at x=62, subtitle baseline 54.
HEAD_H = 88                         # DERIVED in docs/design/02-screens.md: the
                                    # subtitle's line box ends at 69, the first
                                    # section label needs 11 px above its own
                                    # baseline, and 88 leaves 8 px of margin.
ORB_X, ORB_Y, ORB_R = 24, 40, 13
HEAD_TEXT_X = 62
HEAD_TITLE_BASELINE = 36
HEAD_SUBTITLE_BASELINE = 54

ACTION_H = 72                       # the fixed band at the bottom, when a page
                                    # has actions. S5 above and below a 40 px pill.

# 660 - 88 - 72 = 500. The vertical budget every page has, and the number that
# makes "the list must scroll" a fact about arithmetic rather than an opinion.
CONTENT_H = PANEL_H - HEAD_H - ACTION_H

# ── Components ───────────────────────────────────────────────────────────────
TOGGLE_W, TOGGLE_H = 40, 22         # MEASURED from `toggle(x, y, on, w=40, h=22)`
TOGGLE_KNOB_INSET = 3               # knob sits 3 px from the edge, r = h/2 - 3
PILL_H = 42                         # primary pill
PILL_H_SMALL = 40                   # secondary pill
SEG_H = 38                          # segmented control
SLIDER_TRACK_H = 3
SLIDER_KNOB_R = 7

# Card heights, DERIVED rather than listed. The artboard drew ten different card
# heights (60 62 64 66 104 116 130 150 158 176) for one shape with different
# content; these two sums are what those ten collapse to.
CARD_H_2LINE = S4 + CARD_TITLE + S1 + META + S4          # 64
CARD_H_3LINE = S4 + CARD_TITLE + S1 + META + S1 + BODY + S4  # 81

# Pitch = height + gap, and the artboard's own 70/72 becomes 76 because the
# card title grew 13 -> 16. Stated openly in the doc: the cost is 6 rows in the
# content area where the drawing showed 8, paid with a scrolling list.
LIST_PITCH = CARD_H_2LINE + S3      # 76
ROW_PITCH = 48 - S3                 # 36: a gesture row's content height

# How many full rows fit the content area. NOT a hard limit — it is the number
# of rows a page can draw before it must scroll, kept so a page can size its
# initial view and so a test can assert the arithmetic still holds.
ROWS_VISIBLE = CONTENT_H // LIST_PITCH   # 6

__all__ = [name for name in dir() if not name.startswith("_")]
