"""The orb: what it looks like in each mode, and where a click counts as ours.

WHY THE ARITHMETIC IS TESTED AND THE PAINTING IS NOT
    A pixel comparison would prove nothing on a machine with no display, and the
    Qt stub answers every call with a lambda. What CAN be wrong without a display
    is the part the user notices: whether Focus and Quiet actually change the
    orb (the owner's decision, made explicitly), whether the window stays
    clickable in every mode, and whether a click three pixels outside the ring
    is passed through to the desktop instead of being eaten.

    The painter is exercised through the same stub the window smoke test uses,
    so a name Qt does not have (`Qt.PenStyle.DotLine`, `Qt.BrushStyle.NoBrush`)
    fails here rather than on a user's desktop.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from tests import qtstub

ROOT = Path(__file__).resolve().parent.parent


class _Flag:
    """A distinct window-flag bit, so OR-ing can be verified."""

    def __init__(self, bit):
        self.bit = bit

    def __or__(self, other):
        return _Flag(self.bit | getattr(other, "bit", 0))

    def __ror__(self, other):
        return self.__or__(other)

    def __and__(self, other):
        return self.bit & getattr(other, "bit", 0)

    def __eq__(self, other):
        return self.bit == getattr(other, "bit", other)

    def __hash__(self):
        return self.bit

    def __int__(self):
        return self.bit


WINDOW_FLAGS = {"FramelessWindowHint": 0x800, "Tool": 0x2,
                "WindowStaysOnTopHint": 0x40000}


@pytest.fixture()
def orb(monkeypatch):
    """`ui.orb_overlay` loaded over the repo's Qt stub.

    Same mechanism as `tests/test_face_bubble.py`: import the smoke test by
    path, install its stub modules, purge any cached `ui.*`, then import. A
    second, hand-written stub would drift from the one the rest of the suite
    trusts.
    """
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.orb_overlay as module
        yield module
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


# ── the flags ─────────────────────────────────────────────────────────────

def test_the_orb_window_asks_for_all_three_flags(orb):
    WindowType = types.SimpleNamespace(
        **{name: _Flag(bit) for name, bit in WINDOW_FLAGS.items()})
    combined = orb.window_flags(types.SimpleNamespace(WindowType=WindowType))
    for name, bit in WINDOW_FLAGS.items():
        assert (combined & _Flag(bit)) == bit, f"{name} is missing from the flag set"


def test_the_orb_is_not_click_through(orb):
    """The opposite of the pointer ring, and it matters: this is the surface the
    command bar opens from. A click-through orb looks identical in a screenshot
    and cannot be clicked."""
    assert "WindowTransparentForInput" not in orb._FLAGS


def test_the_flag_names_are_the_three_the_mode_needs(orb):
    assert tuple(orb._FLAGS) == (
        "FramelessWindowHint", "Tool", "WindowStaysOnTopHint")


# ── the answered product question ─────────────────────────────────────────

def test_active_is_full_brightness_with_a_glow(orb):
    look = orb.appearance("active")
    assert look.radius == orb.RADIUS
    assert look.glow is True
    assert look.dotted is False
    assert look.alpha == 255


def test_focus_dims_the_orb_and_drops_the_glow(orb):
    """The owner's decision: Focus dims the orb, not only the notifications."""
    look = orb.appearance("focus")
    assert look.radius < orb.RADIUS
    assert look.glow is False
    assert look.alpha < 255


def test_quiet_dims_it_further_and_changes_the_shape(orb):
    """Two states must not be distinguishable by hue alone."""
    quiet, focus = orb.appearance("quiet"), orb.appearance("focus")
    assert quiet.radius < focus.radius
    assert quiet.alpha < focus.alpha
    assert quiet.dotted is True
    assert focus.dotted is False


def test_an_unknown_mode_leaves_the_assistant_visible(orb):
    """Falling back to `quiet` would make a typo look like a crashed app."""
    assert orb.appearance("sideways") == orb.appearance("active")
    assert orb.appearance(None) == orb.appearance("active")


def test_the_three_modes_are_all_different(orb):
    looks = {orb.appearance(m) for m in ("active", "focus", "quiet")}
    assert len(looks) == 3


# ── geometry: the window never moves under the cursor ─────────────────────

def test_the_window_is_the_same_size_in_every_mode(orb):
    """Resizing on a mode change would shift the centre and lose the click.

    The SIZE IS NO LONGER `SIZE` — it is board 1's 146 px overlay, because 96 px
    clipped the painter's own alert dot. See `test_orb_overlay_board1.py` for
    that arithmetic; what this test has always been about is that the number
    does not change with the mode.
    """
    sizes = {orb.window_size(m) for m in ("active", "focus", "quiet")}
    assert len(sizes) == 1
    assert sizes.pop() == (orb.OVERLAY_PX, orb.OVERLAY_PX)


def test_the_window_is_big_enough_for_the_glow(orb):
    assert orb.SIZE >= (orb.RADIUS + orb.GLOW) * 2


def test_the_hit_region_is_round_the_orb_and_inside_the_window(orb):
    """The centre follows the WINDOW, and the window is the overlay now.

    This assertion is the one that caught the change from 96 to 146 px doing
    half a job: the painter moved to the new centre and the hit test did not,
    which would have made the drawn orb unclickable by half a ring.
    """
    cx, cy, r = orb.hit_region("active")
    assert (cx, cy) == (orb.OVERLAY_PX // 2, orb.OVERLAY_PX // 2)
    assert r >= orb.RADIUS
    assert cx + r <= orb.OVERLAY_PX and cy + r <= orb.OVERLAY_PX


def test_a_click_on_the_ring_is_ours(orb):
    assert orb.inside_hit_region(orb.OVERLAY_PX // 2, orb.OVERLAY_PX // 2) is True


def test_a_click_a_few_pixels_outside_the_ring_is_the_desktops(orb):
    """The transparent corner belongs to whatever is underneath.

    AND SINCE BOARD 1 IT BELONGS THERE IN FACT, not just in this function: the
    window carries a mask of the same circle, so the press never arrives here to
    be refused. This assertion is the second half of that rule — the hit test
    still says no, so nothing changes for a click that does reach us.
    """
    assert orb.inside_hit_region(0, 0) is False
    assert orb.inside_hit_region(orb.OVERLAY_PX - 1, orb.OVERLAY_PX - 1) is False


def test_the_hit_ring_does_not_shrink_when_the_orb_dims(orb):
    """A smaller drawing must not make the orb harder to click — but it also
    must not claim a click 20 px out. It follows the drawing, plus the slack."""
    ring_quiet = orb.hit_region("quiet")[2]
    assert ring_quiet >= orb.appearance("quiet").radius
    assert ring_quiet <= orb.HIT_RING


class _Area:
    """A screen rect with Qt's accessors. Methods, not attributes: the real
    `QRect` answers x() and width(), and a test that used plain attributes
    would pass while the production call raised TypeError."""

    def __init__(self, x, y, w, h):
        self._x, self._y, self._w, self._h = x, y, w, h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h


def test_the_corner_anchor_clears_the_taskbar(orb):
    x, y = orb.corner_anchor(_Area(0, 0, 1280, 680), orb.SIZE)
    assert x + orb.SIZE <= 1280
    assert y + orb.SIZE <= 680, "the orb is under the taskbar"
    assert x > 1280 // 2 and y > 680 // 2, "not the bottom-right corner"


def test_the_corner_anchor_respects_a_screen_that_does_not_start_at_zero(orb):
    x, y = orb.corner_anchor(_Area(1920, 0, 1280, 680), orb.SIZE)
    assert x >= 1920


# ── the object: no Qt call may become the caller's exception ──────────────

def test_the_orb_starts_and_reports_available(orb):
    shell = orb.OrbOverlay()
    assert shell.start() is True
    assert shell.available is True
    shell.stop()


def test_setting_state_before_start_is_a_no_op_not_an_error(orb):
    shell = orb.OrbOverlay()
    shell.set_state("speaking")
    shell.set_mode("focus")
    assert shell.state == "speaking"
    assert shell.mode == "focus"


def test_a_click_handler_that_raises_does_not_reach_the_caller(orb):
    def boom():
        raise RuntimeError("command bar is not built yet")

    shell = orb.OrbOverlay(on_click=boom)
    assert shell.start() is True
    assert shell.handle_click(orb.SIZE // 2, orb.SIZE // 2) is False
    shell.stop()


def test_a_click_off_the_ring_never_calls_the_handler(orb):
    called = []
    shell = orb.OrbOverlay(on_click=lambda: called.append(1))
    assert shell.handle_click(0, 0) is False
    assert called == []


def test_a_click_on_the_ring_calls_the_handler_once(orb):
    called = []
    shell = orb.OrbOverlay(on_click=lambda: called.append(1))
    assert shell.handle_click(orb.SIZE // 2, orb.SIZE // 2) is True
    assert called == [1]


def test_a_started_orb_repaints_when_the_state_changes(orb):
    shell = orb.OrbOverlay()
    shell.start()
    painted = []
    shell._canvas = types.SimpleNamespace(update=lambda: painted.append(1))
    shell.set_state("listening")
    assert painted == [1]
    shell.stop()


def test_stopping_twice_is_harmless(orb):
    shell = orb.OrbOverlay()
    shell.start()
    shell.stop()
    shell.stop()
    assert shell.available is False


def test_the_painter_runs_in_every_mode_without_a_real_qt(orb):
    """The painter is where a name Qt does not have becomes a desktop crash."""
    calls = []

    class Painter:
        """Every call the painter makes, recorded.

        `drawLine` and `drawArc` are here because the states are told apart by
        SHAPE: listening is a crown of spikes, thinking is a sweeping arc. A
        fake painter without them would turn a real change into an
        AttributeError that reads like a broken test.
        """

        def setPen(self, *a):
            calls.append("pen")

        def setBrush(self, *a):
            calls.append("brush")

        def drawEllipse(self, *a):
            calls.append("ellipse")

        def drawLine(self, *a):
            calls.append("line")

        def drawArc(self, *a):
            calls.append("arc")

    for mode in ("active", "focus", "quiet"):
        for state in ("idle", "listening", "speaking", "thinking"):
            orb.paint_orb(Painter(), orb.SIZE, mode, state, 0.5)
    assert calls.count("ellipse") > 0


def test_the_canvas_is_a_widget_with_a_paint_event(orb):
    """THE BUG THIS FILE MISSED THE FIRST TIME.

    Every geometry and mode test passed while the orb drew nothing at all: the
    painter was a plain object whose `update()` forwarded to the window, and
    nothing in the module had a `paintEvent`. The window was created, shown,
    translucent and empty.

    So the assertion is not "the maths is right" — it is "something is wired to
    the paint cycle", which is a structural fact and answerable without a
    display.
    """
    import inspect

    canvas = orb._build_canvas(None, orb.OrbOverlay())
    assert hasattr(canvas, "paintEvent"), "the orb widget has no paintEvent"
    # And that handler must call the painter. A `pass`-body paintEvent would
    # pass the line above and still draw nothing.
    source = inspect.getsource(type(canvas).paintEvent)
    assert "paint_orb(" in source


def test_a_started_orb_builds_a_canvas_that_can_paint(orb):
    shell = orb.OrbOverlay()
    assert shell.start() is True
    assert shell._canvas is not None
    assert hasattr(shell._canvas, "paintEvent")
    shell.stop()


def test_the_audio_level_is_clamped_before_the_painter_sees_it(orb):
    """Qt refuses a gradient with an out-of-range stop value; the failure shows
    up as a plain ring with no explanation."""
    shell = orb.OrbOverlay()
    shell.set_audio_level(40)
    assert shell.audio_level == 1.0
    shell.set_audio_level(-3)
    assert shell.audio_level == 0.0
    shell.set_audio_level(float("nan"))
    assert 0.0 <= shell.audio_level <= 1.0 or shell.audio_level == 0.0


def test_the_painter_never_fills_the_whole_window(orb):
    """A filled rect would be a 96 px dark square on the user's desktop — the
    single most visible way this widget can be wrong."""
    source = (ROOT / "ui" / "orb_canvas.py").read_text(encoding="utf-8")
    paint = source.split("def paint_orb", 1)[1]
    assert "fillRect" not in paint
