"""Board 4: what the orb does when you click it, and where it lands when dropped.

WHAT BOARD 4 PROMISES, IN ITS OWN WORDS
    "KLIK KIRI — buka panel baki"
    "KLIK KANAN — menu cepat"
    "SERET — pindah, menempel ke tepi"
    "posisi lain · disimpan antar sesi"

    Three of those four were not true of the build. The fourth was: board 1
    already made the position survive a restart.

    1. LEFT CLICK OPENED THE COMMAND BAR. `ambient_shell.start_orb` passes
       `on_click=lambda: open_command_bar(shell)`, so the orb opened a one-line
       bar instead of the 460x660 panel the board draws — and the note beside
       board 1 still said "it is how the command bar opens", which was true and
       was the bug.

    2. RIGHT CLICK DID NOTHING. There was no handler for it at all.

    3. DRAG DID NOT SNAP. `end_drag` saved wherever the pointer let go, so the
       orb came to rest in the middle of the desktop with nothing behind it.

WHY THE SNAP IS ITS OWN MODULE AND NOT A FEW LINES IN THE CANVAS
    Board 4 draws the orb at TWO more positions, both of them against the right
    or bottom edge, and labels them "posisi lain". A snap is arithmetic about a
    screen and a window; it belongs where a test can drive it with a rectangle
    and no display. `ui/orb_snap.py` is that, and it is deliberately 40 lines —
    the interesting part is the corner rule, not the code.

WHAT IS NOT PROVEN
    That a real Windows window manager places the frameless window exactly where
    `move()` asked. The arithmetic is asserted; the placement is not.
"""
from __future__ import annotations

import sys

import pytest

from tests import qtstub


@pytest.fixture()
def snap():
    """`ui.orb_snap` — pure arithmetic, no Qt needed."""
    import importlib

    import ui.orb_snap as module

    return importlib.reload(module)


class _Area:
    """A screen's available rectangle, in the shape Qt's geometry has."""

    def __init__(self, x=0, y=0, w=1920, h=1040):
        self._box = (x, y, w, h)

    def x(self):
        return self._box[0]

    def y(self):
        return self._box[1]

    def width(self):
        return self._box[2]

    def height(self):
        return self._box[3]


# ── 1. the snap: "menempel ke tepi" ───────────────────────────────────────

def test_a_drop_near_the_right_edge_snaps_to_it(snap):
    """The board's own two extra positions are both against an edge. Dropped
    within `EDGE_PX` of a side, the orb sits ON it, at the board's 24 px margin;
    otherwise it stays where it was let go."""
    area = _Area()
    # 1740 is 34 px from the right edge (1920 - 146 = 1774 is the limit), which
    # is inside EDGE_PX. The first version of this test dropped at 1500 — 274 px
    # away — and asserted a snap that must not happen.
    x, y = snap.snap_to_edge(area, 1740, 400, 146)
    assert x == 1920 - 146 - snap.MARGIN
    assert y == 400, "a snap to one axis must not move the other"


def test_a_drop_near_the_bottom_edge_snaps_to_it(snap):
    area = _Area()
    x, y = snap.snap_to_edge(area, 900, 880, 146)
    assert y == 1040 - 146 - snap.MARGIN
    assert x == 900


def test_a_drop_in_the_open_middle_does_not_snap(snap):
    """`n04()` labels the orb "pindah" — moved — and only the EXTRAS are against
    an edge. Snapping from the middle would make the drag feel like it is
    fighting the hand."""
    area = _Area()
    assert snap.snap_to_edge(area, 800, 400, 146) == (800, 400)


def test_a_drop_near_a_corner_snaps_to_both_edges(snap):
    area = _Area()
    x, y = snap.snap_to_edge(area, 1750, 900, 146)
    assert (x, y) == (1920 - 146 - snap.MARGIN, 1040 - 146 - snap.MARGIN)


def test_the_edge_threshold_is_wide_enough_to_hit_and_narrow_to_ignore(snap):
    """A 4 px threshold snaps constantly; a 400 px one makes the desktop unusable
    as a drag target. 64 px is roughly a fingertip at arm's length."""
    assert 24 <= snap.EDGE_PX <= 96


def test_a_snap_never_leaves_the_orb_off_screen(snap):
    """A window dropped past the right edge by a fast drag must come BACK, not
    stay half outside. This is the case a clamp alone would get wrong: it would
    keep the orb exactly where the pointer left it."""
    area = _Area()
    x, y = snap.snap_to_edge(area, 5000, -400, 146)
    assert x + 146 <= 1920
    assert y >= 0


def test_a_screen_that_does_not_start_at_zero(snap):
    """A second monitor to the left has negative x. The snap is to the AVAILABLE
    area's edges, not to zero."""
    area = _Area(-1920, 0, 1920, 1040)
    # -1880 is 40 px inside the LEFT edge of that monitor; -400 would be its
    # middle, and a drop in the middle must not move (the test above).
    x, _y = snap.snap_to_edge(area, -1880, 400, 146)
    assert x == -1920 + snap.MARGIN


def test_the_margin_is_the_one_the_orb_already_uses(snap):
    """Board 1's corner anchor uses 24. Two margins for one widget is how the
    orb lands 24 px from one edge and 12 from another."""
    from ui.orb_place import corner_anchor

    area = _Area()
    anchored = corner_anchor(area, 146)
    assert anchored == (1920 - 146 - snap.MARGIN, 1040 - 146 - snap.MARGIN)


def test_snapping_is_idempotent(snap):
    """Running the snap on an already-snapped position must not move it, or a
    dropped-and-reopened orb would creep inward with every launch."""
    area = _Area()
    once = snap.snap_to_edge(area, 1740, 400, 146)
    assert snap.snap_to_edge(area, *once, 146) == once


# ── 2. the orb's three clicks ─────────────────────────────────────────────

@pytest.fixture()
def overlay(monkeypatch, isolated_config):
    """`ui.orb_overlay` over the repo's Qt stub, with the config redirected."""
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(qtstub.install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.orb_overlay as module
        yield module
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [n for n in list(sys.modules) if n.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_a_left_click_on_the_ring_calls_the_left_handler(overlay):
    left, right = [], []
    orb = overlay.OrbOverlay(on_click=lambda: left.append(1),
                             on_menu=lambda: right.append(1))
    assert orb.start(), orb.error
    orb.begin_drag(73, 73)
    assert orb.end_drag(73, 73) is False            # a click, not a drag
    assert orb.handle_click(73, 73, button="left") is True
    assert left == [1] and right == []


def test_a_right_click_on_the_ring_calls_the_menu_handler(overlay):
    """"KLIK KANAN — menu cepat". Until this existed, a right click on the orb
    did nothing at all: the canvas only handled presses, and every press was
    treated as the left button."""
    left, right = [], []
    orb = overlay.OrbOverlay(on_click=lambda: left.append(1),
                             on_menu=lambda: right.append(1))
    assert orb.start(), orb.error
    assert orb.handle_click(73, 73, button="right") is True
    assert right == [1] and left == [], "a right click must not also open the panel"


def test_a_right_click_outside_the_ring_is_the_desktops(overlay):
    right = []
    orb = overlay.OrbOverlay(on_menu=lambda: right.append(1))
    assert orb.start(), orb.error
    assert orb.handle_click(2, 2, button="right") is False
    assert right == []


def test_a_right_click_with_no_menu_handler_is_not_an_error(overlay):
    """The menu is optional: a caller that only wants the panel must not get an
    exception, and must not fall through to opening the panel either."""
    left = []
    orb = overlay.OrbOverlay(on_click=lambda: left.append(1))
    assert orb.start(), orb.error
    assert orb.handle_click(73, 73, button="right") is False
    assert left == []


def test_the_canvas_routes_the_right_button_to_the_menu(overlay):
    """The handler being right is not enough — the canvas has to ASK which
    button it was. M-routing below deletes that check and the whole suite has to
    notice."""
    right = []
    orb = overlay.OrbOverlay(on_menu=lambda: right.append(1))
    assert orb.start(), orb.error

    class _Event:
        def position(self):
            class _P:
                def x(self):
                    return 73

                def y(self):
                    return 73
            return _P()

        def button(self):
            from PyQt6.QtCore import Qt
            return Qt.MouseButton.RightButton

        def accept(self):
            pass

    orb._canvas.mousePressEvent(_Event())
    assert right == [1]
    orb.stop()


# ── 3. the left click opens the PANEL, not the bar ────────────────────────

def test_the_orb_opens_the_tray_panel_and_not_the_command_bar():
    """`ambient_shell.start_orb` is the one line that decides this, and the board
    is explicit. Read as source because the alternative is constructing a shell,
    a panel and a QApplication to assert one lambda."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "ui" / "ambient_shell.py").read_text(encoding="utf-8")
    # the orb is built with a left handler that opens the panel
    assert "toggle_panel" in source, (
        "the orb's left click must reach the tray panel (board 4)")
    start = source[source.index("def start_orb"):]
    start = start[:start.index("\ndef ")]
    assert "open_command_bar" not in start, (
        "start_orb still hands the orb the command bar; board 4 says panel")
    # `start_orb` calls `toggle_orb_panel`, which is where `toggle_panel` is
    # reached. Asserting the string "toggle_panel" inside `start_orb` itself was
    # wrong: it is one call away, and the test failed against correct code.
    assert "toggle_orb_panel" in start
    helper = source[source.index("def toggle_orb_panel"):]
    helper = helper[:helper.index("\ndef ")]
    assert "tray_panel_wiring.toggle_panel" in helper, (
        "the orb's left click does not reach the tray panel")


def test_the_command_bar_is_still_reachable_by_chord():
    """Moving the orb's left click must not orphan the bar: The bar uses a distinct chord from push-to-talk."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "ui" / "ambient_shell.py").read_text(encoding="utf-8")
    assert 'BAR_CHORD = ("ctrl", "alt", "b")' in source


# ── 4. the snap is wired into the release, not just available ─────────────

def test_dropping_near_the_edge_makes_the_orb_sit_on_it(overlay, monkeypatch):
    """M-snap below deletes the call in `end_drag` and the suite must notice.

    Board 4's "menempel ke tepi" is a behaviour, not an exported function: a
    `snap_to_edge` that nothing calls is arithmetic with no user.
    """
    from ui import orb_place

    class _Area:
        def x(self):
            return 0

        def y(self):
            return 0

        def width(self):
            return 1920

        def height(self):
            return 1040

    monkeypatch.setattr(overlay, "_screen_area", _Area)
    orb = overlay.OrbOverlay()
    assert orb.start(), orb.error
    orb.drag_to(1740, 400)                      # 34 px from the right edge
    orb.begin_drag(40, 40)
    assert orb.end_drag(80, 40) is True
    saved = orb_place.read_position()
    assert saved is not None
    assert saved[0] == 1920 - 146 - 24, (
        f"the orb was saved at {saved}, not snapped to the right edge")
    orb.stop()


def test_a_drop_in_the_middle_is_saved_where_it_was_dropped(overlay, monkeypatch):
    """The snap must not fire from the middle: board 4 calls the drag "pindah",
    and a free desktop is the point of moving it."""
    from ui import orb_place

    class _Area:
        def x(self):
            return 0

        def y(self):
            return 0

        def width(self):
            return 1920

        def height(self):
            return 1040

    monkeypatch.setattr(overlay, "_screen_area", _Area)
    orb = overlay.OrbOverlay()
    assert orb.start(), orb.error
    orb.drag_to(700, 400)
    orb.begin_drag(40, 40)
    assert orb.end_drag(80, 40) is True
    assert orb_place.read_position() == (700, 400)
    orb.stop()


def test_a_drop_far_off_screen_comes_back_onto_it(overlay):
    """Every drop, anywhere, lands inside the available rectangle.

    THE CLAMP THIS TEST WAS WRITTEN FOR NO LONGER EXISTS, and its removal is the
    honest outcome: a mutation proved it could never change a result, because
    each branch already lands inside the rectangle. What the test still holds is
    the property a clamp was there to guarantee — including a drop thousands of
    pixels off, which is what a fast drag on a 3-monitor desktop produces.
    """
    from ui import orb_snap

    class _Area:
        def x(self):
            return 0

        def y(self):
            return 0

        def width(self):
            return 1920

        def height(self):
            return 1040

    x, y = orb_snap.snap_to_edge(_Area(), 5000, -900, 146)
    assert 0 <= x <= 1920 - 146, f"x={x} is off-screen"
    assert 0 <= y <= 1040 - 146, f"y={y} is off-screen"


def test_the_orb_is_handed_a_menu_handler_at_startup():
    """M13 set `on_menu=None` in `start_orb` and nothing failed: the unit tests
    prove the overlay CAN open a menu, and none of them prove the shell ever
    gives it one. Board 4's "KLIK KANAN — menu cepat" lives in that one line."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "ui" / "ambient_shell.py").read_text(encoding="utf-8")
    start = source[source.index("def start_orb"):]
    start = start[:start.index("\ndef ")]
    assert "on_menu=open_quick_menu" in start.replace("lambda: ", "lambda ") \
        or "open_quick_menu(shell)" in start, (
        "start_orb builds the orb without a menu handler; board 4 says right "
        "click opens one")
    assert "open_quick_menu" in start


def test_the_quick_menu_offers_the_three_modes_and_quits():
    """The menu board 4 draws is not specified item by item, so what is asserted
    is the minimum a user needs at the orb: the three presence modes, and a way
    out. A menu that cannot set the mode is a menu that sends you to the panel."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "ui" / "ambient_shell.py").read_text(encoding="utf-8")
    body = source[source.index("def open_quick_menu"):]
    body = body[:body.index("\ndef ")]
    for word in ("Aktif", "Fokus", "Senyap", "Keluar"):
        assert word in body, f"the quick menu has no {word!r} item"
    assert "set_presence" in body, "the mode items do nothing"
