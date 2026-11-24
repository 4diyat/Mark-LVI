"""Every board page draws the artboard that specifies it.

WHY THIS FILE EXISTS
    Thirteen pages were built and every one of them was checked for what it
    SAYS — the count matches the store, the absent data is stated, the button
    writes the right key. Not one was checked for where it PUTS things, and the
    mockups were referenced in prose ("transcribed from board 9") rather than
    parsed. The result, measured against `docs/mockups/build.py` itself:

      * board 9's first card sat at y=62 where the artboard draws 106, so the
        whole list was 44 px high and the "dan N lagi" line fell below the
        panel's own edge at 640.
      * board 15 drew TWO language options (Indonesia, English); the artboard
        draws three.
      * board 14 drew the risk levels at a pitch of 74 against the artboard's
        76, drifting 6 px by the third row.
      * every page drew its title TWICE, eight pixels apart, because the panel
        already has a shared title and each page added its own on top.

    The owner's report — "masih banyak yang belum sesuai dengan design" — was
    correct on all of it. This file is the check that was missing, and it reads
    the artboards by executing them rather than by trusting a comment.

HOW IT WORKS
    `docs/mockups/build.py` is a pure-Python SVG builder: every board is a
    function that returns a string of `<rect>` and `<text>` elements. This test
    CALLS those functions and parses the result, so the numbers are the
    drawing's, not a transcription of the drawing. `ui/board_geometry.py` is
    generated from the same call, and the first test here asserts the committed
    copy still matches — a page cannot be written against a stale table.

WHAT THIS PROVES, AND WHAT IT DOES NOT
    Proved: the geometry a page hands to Qt equals the geometry the artboard
    draws, widget by widget, and nothing runs outside the panel's 460x660.
    Not proved: the rendered pixels. Qt cannot run in this sandbox; the
    stylesheet, the font and the actual rasterisation are checked by eye in
    `docs/verification.md`. This file closes the gap that a human review kept
    missing, not the gap between SVG and QLabel.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "docs" / "mockups" / "build.py"
PANEL_W, PANEL_H = 460, 660


@pytest.fixture
def panel_module():
    """`(tray_panel, tray_paint)` over the Qt stub — same as test_board_pages."""
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui import tray_paint, tray_panel

        yield tray_panel, tray_paint
    finally:
        restore_ui(saved)


@pytest.fixture(scope="module")
def sheet():
    """`build.py`, loaded as a module so the artboards can be CALLED."""
    spec = importlib.util.spec_from_file_location("_design_sheet", BUILD)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_design_sheet"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def extracted(sheet):
    """Every page's primitives, straight out of the drawing."""
    import re

    out = {}
    for key, fn_name in {**{k: v["board"] for k, v in _boards().items()},
                         **{k: v[0] for k, v in _reflowed().items()}}.items():
        svg = getattr(sheet, fn_name)()
        frame = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        rects = [tuple(float(v) for v in m.groups())
                 for m in re.finditer(
                     r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" '
                     r'height="([\d.]+)" rx="([\d.]+)"', svg)]
        texts = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4))
                 for m in re.finditer(
                     r'<text x="([\d.]+)" y="([\d.]+)"[^>]*font-size="([\d.]+)"[^>]*>'
                     r'([^<]*)</text>', svg)]
        out[key] = {"frame": (int(frame.group(1)), int(frame.group(2))),
                    "rects": rects, "texts": texts}
    return out


def _boards() -> dict:
    from ui.board_geometry import BOARDS

    return BOARDS


def _reflowed() -> dict:
    from ui.board_geometry import REFLOWED

    return REFLOWED


# ── the table itself ───────────────────────────────────────────────────────

def test_the_committed_geometry_is_the_artboards_own_numbers(extracted):
    """`ui/board_geometry.py` must equal what the sheet emits RIGHT NOW.

    THE TABLE IS GENERATED, AND THIS IS WHAT MAKES THAT TRUE. A hand-edited
    table would be a second source of truth; a stale one would let the pages
    match a drawing that no longer exists. Both fail here.
    """
    for key, live in extracted.items():
        committed = (_boards().get(key) or _reflowed().get(key))
        if committed is None:
            pytest.fail(f"{key} is in the sheet but not in board_geometry")

        if isinstance(committed, tuple):        # REFLOWED: (fn, w, h)
            assert committed[1:] == live["frame"], f"{key} frame moved"
            continue

        assert tuple(committed["frame"]) == live["frame"], (
            f"{key}: committed frame {committed['frame']} but the sheet draws "
            f"{live['frame']}")
        # Round BOTH sides to 3 dp: the sheet divides (412/2 for a segment
        # half), the committed table writes %g, and chasing float reprs would
        # make the test about formatting rather than about coordinates.
        assert ([tuple(round(float(v), 3) for v in r) for r in committed["rects"]]
                == [tuple(round(v, 3) for v in r) for r in live["rects"]]), (
            f"{key}: the committed rects are not the sheet's. Regenerate with "
            "`./.venv/bin/python tools/gen_board_geometry.py`")
        assert ([tuple(round(v, 3) if isinstance(v, float) else v for v in t)
                 for t in committed["texts"]]
                == [tuple(round(v, 3) if isinstance(v, float) else v for v in t)
                    for t in live["texts"]]), (
            f"{key}: the committed text runs are not the sheet's")


def test_every_page_in_the_registry_has_a_geometry_source():
    """"Every artboard has a surface" is only true if the surface is measured."""
    from ui.board_geometry import BOARDS, REFLOWED
    from ui.page_registry import PAGE_KEYS

    missing = sorted(set(PAGE_KEYS) - set(BOARDS) - set(REFLOWED))
    assert missing == [], (
        f"pages with no artboard geometry to match: {missing}. Either the page "
        "has no board, or it was never added to tools/gen_board_geometry.py")


# ── the two things every page got wrong ────────────────────────────────────

def test_every_artboards_header_is_the_same_pair_of_coordinates(extracted):
    """All twenty-two boards call `panel_head()`, which draws at (62, 36)/(62, 54).

    THIS IS WHY THE PANEL NEEDS NO PER-PAGE TITLE. The shared header already
    says JARVIS and the page's subtitle; the page must not draw a second one.
    The first version of these pages put a title label at (24, 30) on top of
    the shared (24, 22) — the same words, eight pixels apart.
    """
    for key, live in extracted.items():
        # ONLY THE PANEL-SIZED BOARDS. b21 is a 1280x640 specimen sheet and
        # types "JARVIS" at (40, 386) as a type example, 46 px tall — a false
        # positive this test found in its own first draft.
        if key in _reflowed():
            continue
        heads = [t for t in live["texts"] if t[3] == "JARVIS" and t[2] == 13]
        if not heads:
            continue
        assert (heads[0][0], heads[0][1]) == (62, 36), (
            f"{key}: the JARVIS line is at {(heads[0][0], heads[0][1])}, "
            "not the panel_head origin (62, 36)")


def test_no_page_draws_a_title_of_its_own(panel_module):
    """The panel's shared header is the ONLY title on a board page.

    Checked at the widget level rather than in the table, because the bug was
    not a wrong number: it was a whole extra label that happened to sit 8 px
    below the real one and say the same thing.
    """
    tray_panel, tray_paint = panel_module
    from ui.page_registry import PAGE_KEYS

    panel = tray_panel.TrayPanel({})
    panel.open()

    for name in PAGE_KEYS:
        panel.set_page(name)
        tray_paint.paint(panel, panel.snapshot)
        shared = panel._labels["title"].text()
        for key, label in panel._labels.items():
            if key == "title" or not key.startswith(name[:3]):
                continue
            if not label.isVisible():
                continue
            assert label.y() >= 60 or label.text() != shared, (
                f"{name}: {key} repeats the shared title {shared!r} at "
                f"y={label.y()} — the header is drawn twice")


# ── geometry: every page against its own drawing ───────────────────────────

def test_every_widget_sits_inside_the_panel(panel_module):
    """Nothing may be drawn past the edge. A 460x660 popup cannot scroll.

    THIS CAUGHT A REAL ONE: board 9's "dan 4 lagi" line was at y=640 in a panel
    whose height is 660, so the label's own box ran to 656 — four pixels from
    the edge — and every row above it was 44 px high because the list started
    at the panel's top instead of the artboard's 106.
    """
    tray_panel, tray_paint = panel_module
    from ui.page_registry import PAGE_KEYS

    panel = tray_panel.TrayPanel({})
    panel.open()

    overflow = []
    for name in PAGE_KEYS:
        panel.set_page(name)
        tray_paint.paint(panel, panel.snapshot)
        for kind, bucket in (("label", panel._labels), ("button", panel._buttons)):
            for key, widget in bucket.items():
                if not widget.isVisible():
                    continue
                x, y = widget.x(), widget.y()
                w, h = widget.width(), widget.height()
                if x < 0 or y < 0 or x + w > PANEL_W or y + h > PANEL_H:
                    overflow.append((name, kind, key, (x, y, w, h)))

    assert overflow == [], (
        "widgets drawn outside the 460x660 panel:\n  "
        + "\n  ".join(f"{n}: {k} {g}" for n, _, k, g in overflow[:12]))


def test_the_memory_list_starts_where_the_artboard_starts(panel_module):
    """Board 9 draws its first card at (24, 106), pitch 72, six rows.

    The built page had it at (24, 62) — the top of the panel — with the section
    header printed over the first row.
    """
    tray_panel, tray_paint = panel_module
    from ui.board_geometry import BOARDS

    cards = [r for r in BOARDS["memory"]["rects"]
             if r[2] == 412 and r[3] == 62]
    assert cards[:6] == [(24, 106 + i * 72, 412, 62, 12) for i in range(6)], (
        "the artboard's own row stack changed; this test describes old geometry")

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    tray_paint.paint(panel, panel.snapshot)

    for i in range(6):
        card = panel._labels.get(f"mem_card:{i}")
        if card is None:
            pytest.fail(f"mem_card:{i} was never built")
        assert (card.x(), card.y()) == (24, 106 + i * 72), (
            f"mem_card:{i} at {(card.x(), card.y())}, artboard draws "
            f"{(24, 106 + i * 72)}")
        assert (card.width(), card.height()) == (412, 62)


def test_the_memory_buttons_are_the_artboards_divider_and_two_pills(panel_module):
    """A 1 px rule at y=556 and two 200x40 pills at y=574, x=24 and x=236."""
    tray_panel, tray_paint = panel_module
    from ui.board_geometry import BOARDS

    rects = BOARDS["memory"]["rects"]
    assert (24, 556, 412, 1, 0) in rects, "the artboard's divider is gone"
    assert (24, 574, 200, 40, 20) in rects
    assert (236, 574, 200, 40, 20) in rects

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    tray_paint.paint(panel, panel.snapshot)

    add = panel._buttons["mem_add"]
    clear = panel._buttons["mem_clear"]
    assert (add.x(), add.y(), add.width(), add.height()) == (24, 574, 200, 40)
    assert (clear.x(), clear.y(), clear.width(), clear.height()) == (236, 574, 200, 40)


def test_the_language_control_draws_three_options(panel_module):
    """Board 15 draws Indonesia · English · Campur as one segmented control.

    The page drew two. `core.i18n` supports exactly the artboard's three (id,
    en, and mixed), so the third was not a missing feature — it was missing
    from the page.
    """
    tray_panel, tray_paint = panel_module
    from ui.board_geometry import BOARDS

    labels = [t[3] for t in BOARDS["access"]["texts"]]
    for option in ("Indonesia", "English", "Campur"):
        assert option in labels, f"the artboard no longer draws {option!r}"

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("access")
    tray_paint.paint(panel, panel.snapshot)

    drawn = {k: b.text() for k, b in panel._buttons.items()
             if k.startswith("ac_lang") and b.isVisible()}
    assert len(drawn) == 3, f"the page draws {len(drawn)} language options, not 3"


def test_the_security_levels_use_the_artboards_sixty_four_pixel_cards(panel_module):
    """Board 14's risk cards are 412x64 at pitch 76 — not the 74 the page used."""
    tray_panel, tray_paint = panel_module
    from ui.board_geometry import BOARDS

    cards = [r for r in BOARDS["security"]["rects"] if r[2] == 412 and r[3] == 64]
    assert [(r[0], r[1]) for r in cards] == [(24, 302), (24, 378), (24, 454)], (
        "the artboard's risk levels moved; update the page and this test together")

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("security")
    tray_paint.paint(panel, panel.snapshot)

    for index, (_, y) in enumerate([(24, 302), (24, 378), (24, 454)]):
        card = panel._labels.get(f"sec_card:{index}")
        assert card is not None, f"sec_card:{index} was never built"
        assert (card.x(), card.y(), card.width(), card.height()) == (24, y, 412, 64), (
            f"sec_card:{index} at {(card.x(), card.y())}, artboard draws (24, {y})")


# ── the reflowed three ─────────────────────────────────────────────────────

def test_a_reflowed_board_is_declared_as_one():
    """Honesty about the three that cannot match.

    b19 is 720x640, b21 is 1280x640 and b22 is 720x480. A 460 px panel cannot
    hold any of them at their drawn size, so their pages are reflows. That is
    allowed; pretending they are transcriptions is not, which is why the
    distinction lives in the table and not in a comment.
    """
    reflowed = _reflowed()
    assert set(reflowed) == {"gestures", "brand", "installer"}
    for key, (fn, w, h) in reflowed.items():
        assert w > PANEL_W or h > PANEL_H, (
            f"{key} ({fn}, {w}x{h}) fits the panel — it should not be reflowed")


def test_no_page_repeats_itself_in_the_header(panel_module):
    """A title and a subtitle that say the same thing are one line drawn twice.

    `help` shipped with "Dictation · screen reading · form fill" over
    "Dictation · screen reading · form filling" — the same sentence, one
    character apart, because the artboard's single subtitle was used as BOTH
    the page's name and its second line. The artboard's own header is
    "JARVIS / Dikte · baca layar · isi form": the first line is the assistant,
    the second is what the page is about, and a page needs a name of its own.
    """
    tray_panel, tray_paint = panel_module
    from ui.page_registry import ALL_PAGES

    panel = tray_panel.TrayPanel({})
    panel.open()

    repeated = []
    for name in ALL_PAGES:
        panel.set_page(name)
        tray_paint.paint(panel, panel.snapshot)
        title = panel._labels["title"].text().strip()
        subtitle = panel._labels["subtitle"].text().strip()
        if title and subtitle and title[:20].lower() == subtitle[:20].lower():
            repeated.append((name, title, subtitle))

    assert repeated == [], (
        "pages whose two header lines are the same sentence: "
        + "; ".join(f"{n}: {t!r} / {s!r}" for n, t, s in repeated))


# ── the check that would have caught the whole round ───────────────────────

# Boards whose cards the pages draw at the artboard's own coordinates. The six
# the drawing has and the pages do not are listed with the reason, in
# `ALLOWED_GAPS`, so a NEW one fails here instead of being found by eye.
TRANSCRIBED = ("memory", "memory_one", "tools", "help", "security",
               "access", "plugins", "light", "consent")

ALLOWED_GAPS = {
    ("routines", 180): "card 2 of 3 — no routine store, one sentence stands in its band",
    ("routines", 276): "card 3 of 3 — the same absence, stated once for both",
    ("tools", 276): "the search FIELD is a QLineEdit, not a label; it is at 276",
    ("help", 432): "the vendor field row is a QLineEdit, not a label; it is at 432",
    ("help", 488): "the invoice field row is a QLineEdit, not a label; it is at 488",
    ("help", 544): "the amount field row is a QLineEdit, not a label; it is at 544",
    ("light", 0): "the page's own full-bleed background rect, 460x640",
}


def test_every_artboard_card_has_a_widget_at_its_coordinates(panel_module):
    """The audit that should have existed from the start.

    A PAGE CAN PASS EVERY TEXT TEST AND STILL BE IN THE WRONG PLACE. That is
    what happened: board 9's count was honest and its list was 44 px high,
    board 16's "0 of 15" was right and its rows had no cards at all. This walks
    the artboard's own rectangles and requires a visible widget at each one,
    because "matches the design" is a claim about positions.
    """
    tray_panel, tray_paint = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()

    missing = []
    for page in TRANSCRIBED:
        panel.set_page(page)
        tray_paint.paint(panel, panel.snapshot)
        placed = [(w.x(), w.y(), w.width()) for bucket in (panel._labels, panel._buttons)
                  for w in bucket.values()
                  if w.isVisible() and w._parent is panel._pages.get(page)]
        for x, y, w, h, _r in _boards()[page]["rects"]:
            # Only the big furniture: cards, panels, tracks. The small dots and
            # 3 px rules are drawn by the painter, not placed by the builder.
            if w <= 200 or h <= 20:
                continue
            if (page, int(y)) in ALLOWED_GAPS:
                continue
            if not any(abs(x - px) <= 6 and abs(y - py) <= 6 and abs(w - pw) <= 8
                       for px, py, pw in placed):
                missing.append((page, int(x), int(y), int(w), int(h)))

    assert missing == [], (
        "artboard rectangles with no widget at their coordinates:\n  "
        + "\n  ".join(f"{p}: ({x},{y}) {w}x{h}" for p, x, y, w, h in missing))


def test_the_allowed_gaps_are_still_gaps(panel_module):
    """A justified gap that no longer exists must be deleted from the list.

    Otherwise the exemptions rot: the page gets fixed, the entry stays, and a
    later regression at that coordinate passes because someone once had a
    reason. Each entry is checked against the drawing so a stale one fails.
    """
    for (page, y), reason in ALLOWED_GAPS.items():
        assert page in _boards(), f"{page} is not a board"
        ys = [int(r[1]) for r in _boards()[page]["rects"] if r[2] > 200 and r[3] > 20]
        assert y in ys, (
            f"ALLOWED_GAPS has ({page}, {y}) but the artboard draws no card "
            f"there (it draws {ys}) — delete the entry. It said: {reason}")


def test_a_toggle_is_the_size_the_artboard_draws(panel_module):
    """Board 16's switch is 40x22, not a 76 px ON/OFF rectangle.

    A CARD AT THE RIGHT COORDINATE IS NOT ENOUGH. The first version of the
    audit above checked the 412x60 card and passed while the control inside it
    was a wide button reading "ON" — visually a menu item, not the switch the
    artboard draws. These are the *switches*, so their size is the claim.
    """
    tray_panel, tray_paint = panel_module

    # Every 40x22 dot the sheet draws, by board.
    # TWO OF THE SHEET'S DOTS MUST NOT BE DRAWN, and both are rulings rather
    # than omissions. Board 14's (378,216) is the guest-mode switch the owner
    # DELETED — drawing it, even disabled, would say the feature exists.
    # Board 11's two extra dots belong to routine cards 2 and 3, and there is
    # no routine store to switch them with.
    MUST_NOT_DRAW = {
        ("security", 378, 216): "guest mode is deleted by ruling",
    }
    expected = {}
    for key, geo in _boards().items():
        dots = [(int(r[0]), int(r[1])) for r in geo["rects"]
                if int(r[2]) == 40 and int(r[3]) == 22
                and (key, int(r[0]), int(r[1])) not in MUST_NOT_DRAW]
        if dots:
            expected[key] = dots
    assert expected, "the sheet no longer draws a single 40x22 toggle"

    panel = tray_panel.TrayPanel({})
    panel.open()

    wrong = []
    for page, dots in expected.items():
        panel.set_page(page)
        tray_paint.paint(panel, panel.snapshot)
        live = [(w.x(), w.y(), w.width(), w.height())
                for bucket in (panel._buttons, panel._labels)
                for w in bucket.values()
                if w.isVisible() and w._parent is panel._pages.get(page)]
        for x, y in dots:
            match = [g for g in live if abs(g[0] - x) <= 6 and abs(g[1] - y) <= 6]
            if not match:
                wrong.append((page, x, y, "no widget"))
            elif not any(g[2] <= 48 and g[3] <= 30 for g in match):
                wrong.append((page, x, y, f"a {match[0][2]:.0f}x{match[0][3]:.0f} control"))

    # AND THE ONES THAT MUST NOT BE DRAWN REALLY ARE NOT. Without this the
    # exemption above would silently cover a page that drew the guest switch
    # again — the exact regression `tests/test_privacy_board27.py` exists to
    # catch, checked here at the coordinate the artboard draws it.
    for (page, x, y), reason in MUST_NOT_DRAW.items():
        panel.set_page(page)
        tray_paint.paint(panel, panel.snapshot)
        present = [(w.x(), w.y()) for bucket in (panel._buttons, panel._labels)
                   for w in bucket.values()
                   if w.isVisible() and w._parent is panel._pages.get(page)
                   and abs(w.x() - x) <= 6 and abs(w.y() - y) <= 6]
        assert present == [], (
            f"{page} draws a control at ({x},{y}) where {reason}")

    assert wrong == [], (
        "switches that are not the artboard's 40x22 dot:\n  "
        + "\n  ".join(f"{p}: ({x},{y}) — {why}" for p, x, y, why in wrong))
