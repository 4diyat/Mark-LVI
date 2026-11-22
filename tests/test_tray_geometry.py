"""Board 5's geometry, compared with the artboard that draws it.

WHY THIS FILE EXISTS
    `ui/tray_pages.py` claimed to be "transcribed from the artboard and nowhere
    else" and four values had drifted: the suggestion card was never built, its
    two lines sat 8 px high, the whole IZIN block sat 18-26 px high, and the
    permission rows had no toggle column at all. Nothing failed, because the
    only geometry test in the suite checked where the PANEL GOES on a screen and
    nothing checked what is drawn inside it.

    A call to `setGeometry(24, 452, ...)` is not a fact anybody can assert
    against a drawing. A table is: the numbers below are read from
    `docs/mockups/build.py: n05()` by parsing it, not by copying it, so the two
    cannot quietly disagree again.

HOW THE ARTBOARD IS READ
    `n05()` is a list of `rect(...)` and `txt(...)` calls in SVG coordinates.
    The test extracts the ones this table claims to mirror and compares them by
    value. It does not try to interpret the drawing — only the coordinates that
    `GEOMETRY` says it copied.

WHAT THIS DOES NOT PROVE
    That the panel LOOKS like the artboard. Qt renders a stylesheet, the
    artboard renders SVG, and PyQt6 cannot be imported in this sandbox. What is
    proved is that the numbers agree, which is the part a human review keeps
    missing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "docs" / "mockups" / "build.py"


@pytest.fixture(scope="module")
def n05() -> str:
    """The `n05()` function body — board 5 as the sheet actually draws it."""
    source = BUILD.read_text(encoding="utf-8")
    match = re.search(r"^def n05\(\):(.*?)(?=^def )", source, re.S | re.M)
    assert match, "n05() is gone: board 5 was renamed or removed"
    return match.group(1)


@pytest.fixture(scope="module")
def geometry() -> dict:
    from ui.tray_pages import GEOMETRY

    return GEOMETRY


def _rects(body: str) -> list[tuple[int, ...]]:
    return [tuple(int(v) for v in m.groups())
            for m in re.finditer(r"rect\((\d+), (\d+), (\d+), (\d+)", body)]


def _txt_positions(body: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in
            re.findall(r"txt\((\d+), (\d+),", body)]


# ── the values that had drifted ────────────────────────────────────────────

def test_the_suggestion_card_is_the_artboards_rectangle(geometry, n05):
    """412x62 at (24, 380) with a 3x38 amber bar at (24, 392). The card was
    simply absent from the build — the text floated on the panel."""
    assert geometry["suggestion_card"] == (24, 380, 412, 62)
    assert geometry["suggestion_bar"] == (24, 392, 3, 38)
    rects = _rects(n05)
    assert (24, 380, 412, 62) in rects
    assert (24, 392, 3, 38) in rects


def test_the_suggestion_lines_sit_where_the_artboard_puts_them(geometry, n05):
    """404 and 424 in the artboard's baseline coordinates. The panel drew them
    at 396 and 416 — eight pixels high, both of them."""
    positions = _txt_positions(n05)
    title_y = geometry["suggestion_title"][1]
    quota_y = geometry["suggestion_quota"][1]
    # The artboard places text by BASELINE; a QLabel is placed by its top
    # edge, and the label box is 20 px tall around an 11.5 px line. The table
    # therefore records the box, and the relationship asserted here is the
    # one that must hold: the two lines are 20 px apart, and the pair sits
    # inside the card's 380..442 band.
    assert quota_y - title_y == 20
    assert (44, 404) in positions and (44, 424) in positions
    top, bottom = geometry["suggestion_card"][1], 380 + 62
    assert top <= title_y < quota_y + 18 <= bottom


def test_the_permission_block_starts_where_the_artboard_starts(geometry, n05):
    """IZIN header at y=478 and the first row at 492 — 30 px pitch. The panel
    had 452 and 474, so the whole block floated 18-26 px high."""
    assert geometry["perm_header"][1] == 478
    assert geometry["perm_row_y"] == 492
    assert geometry["perm_pitch"] == 30
    assert (24, 478) in _txt_positions(n05)


def test_every_permission_row_has_a_toggle_in_the_artboards_column(geometry, n05):
    """The artboard draws a 40x22 dot at x=396 for each of the three rows.

    The panel had no toggle at all: each row was one full-width pill, which
    read as a menu item rather than a switch. Both the dot's x and the fact
    that there are three of them are asserted from the drawing.
    """
    assert geometry["perm_toggle_x"] == 396
    # `n05()` has ONE `toggle(396, y + 4, v)` call site and a three-row loop
    # around it, so the drawing shows three toggles and the source contains
    # one. Asserting three occurrences asserted the wrong thing: the earlier
    # version of this test counted call sites and failed on a correct
    # artboard — the exact confusion that makes a geometry test worthless.
    #
    # The row loop itself is what proves the count: `for i, (n, v) in
    # enumerate((("Mikrofon", True), ("Kamera", False), ("Layar", True)))`.
    assert len(re.findall(r"toggle\((\d+),", n05)) == 1
    assert n05.count('("Mikrofon", True)') == 1, "the three-row tuple is gone"
    assert re.search(r"toggle\(\d+, y \+ 4, v\)", n05), (
        "the toggle moved off the row's own y offset")
    assert sorted({int(x) for x in re.findall(r"toggle\((\d+),", n05)}) == \
        sorted({geometry["perm_toggle_x"]})
    rows = re.search(r"for i, \(n, v\) in enumerate\(\((.+?)\)\):", n05)
    assert rows and rows.group(1).count("(") == 3, (
        "the artboard no longer draws three permission rows")


def test_the_command_line_is_a_340_wide_field_and_a_disc(geometry, n05):
    """The artboard's input is 340x40 at x=24 and its send control is a circle
    centred at (404, 616) with r=18 — a 36 px disc, not a 50x40 rectangle."""
    assert geometry["field"] == (24, 596, 340, 40)
    assert (24, 596, 340, 40) in _rects(n05)
    # The circle is inside an f-string in `build.py`, so its raw source has
    # backslash-escaped quotes. Rather than escape a pattern by hand — which
    # produced `\\\\"` and matched nothing, twice — the numbers are pulled
    # out of the quoted attribute values generically.
    circle = [ln for ln in n05.splitlines() if "circle cx=" in ln][0]
    values = re.findall(r'="(\d+)"', circle)
    assert len(values) >= 3, circle
    cx, cy, r = values[:3]
    assert (int(cx), int(cy), int(r)) == (404, 616, 18)
    send_x, send_y, send_w, send_h = geometry["send"]
    assert send_w == send_h == 2 * int(r)
    assert abs(send_x + send_w / 2 - int(cx)) <= 1
    assert abs(send_y + send_h / 2 - int(cy)) <= 1


def test_the_quick_rows_are_unchanged_because_they_were_already_right(geometry, n05):
    """140 for the header and 154 + 48n for the rows. Asserted anyway: a table
    that only checks what was once wrong is a table that stops checking."""
    assert geometry["quick_header"][1] == 140
    assert geometry["quick_row_y"] == 154
    assert geometry["quick_pitch"] == 48
    assert (24, 140) in _txt_positions(n05)


# ── the things that must NOT be "fixed" ────────────────────────────────────

def test_the_panel_is_taller_than_the_artboard_on_purpose():
    """660 vs 640, and `DESIGN-ambient.md` says why. A future change that
    "corrects" this to 640 must fail here and read the note first."""
    from ui.tray_pages import PANEL_H, PANEL_W

    assert (PANEL_W, PANEL_H) == (460, 660)
    design = (ROOT / "docs" / "mockups" / "DESIGN-ambient.md").read_text(encoding="utf-8")
    assert "460×660" in design, "the 660 decision lost its explanation"


def test_every_geometry_entry_is_a_rectangle_inside_the_panel(geometry):
    """A typo in the table is a widget drawn off the panel, which Qt shows as
    a control the user cannot reach."""
    from ui.tray_pages import PANEL_H, PANEL_W

    for name, value in geometry.items():
        if not isinstance(value, tuple) or len(value) != 4:
            continue
        x, y, w, h = value
        assert x >= 0 and y >= 0, f"{name} starts outside the panel"
        assert x + w <= PANEL_W, f"{name} runs past the right edge"
        assert y + h <= PANEL_H, f"{name} runs past the bottom edge"


def test_the_palettes_still_match_the_artboard_tokens():
    """The tray panel's two palettes against `build.py`'s own constants.

    This is the test the theme work has needed since board 28: the light
    palette is a table copied by hand, and a hand-copied hex string is the
    quietest possible drift.
    """
    from ui.tray_pages import PALETTES

    # A tiny parser for the constant section at the top of `build.py`, which
    # uses both `A = "x"` and `A, B, C = "x", "y", "z"`. Written once and
    # verified by this test: a cleverer version tried to slice the line by
    # constant name and mismatched BASE with PANEL, which looked exactly like a
    # palette bug.
    source = BUILD.read_text(encoding="utf-8")
    constants: dict[str, str] = {}
    for line in source.splitlines():
        m = re.match(r"^([A-Z_,\s]+)\s*=\s*(.+)$", line)
        if not m:
            continue
        names = [n.strip() for n in m.group(1).split(",")]
        values = [v.strip().strip('"') for v in m.group(2).split(",")]
        if len(names) == len(values):
            constants.update(dict(zip(names, values)))
    assert constants.get("BASE", "").startswith("#"), "the constant block moved"

    dark = {
        "base": "BASE", "panel": "PANEL", "line": "LINE",
        "line_accent": "LINE_ACC", "accent": "CYAN", "amber": "AMBER",
        "text": "TEXT", "muted": "MUTED",
    }
    light = {
        "base": "LBASE", "panel": "LPANEL", "line": "LLINE",
        "line_accent": "LACC", "accent": "LACC", "amber": "LAMBER",
        "text": "LTEXT", "muted": "LMUTED",
    }
    checked = 0
    for palette, mapping in (("dark", dark), ("light", light)):
        for key, constant in mapping.items():
            expected = constants[constant]
            assert PALETTES[palette][key].upper() == expected.upper(), (
                f"{palette}[{key}] is {PALETTES[palette][key]}, "
                f"artboard {constant} is {expected}")
            checked += 1
    # A loop that silently skipped every entry would pass this test while
    # checking nothing — the failure mode this suite keeps designing against.
    assert checked == 16, f"only {checked} palette entries were compared"
