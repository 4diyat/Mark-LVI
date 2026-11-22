"""Board 1: the overlay is the artboard's box, and only the ring takes clicks.

WHAT BOARD 1 PROMISES
    `n01()` draws the orb at (1180, 602) with r=28 inside a dashed square that
    is `r * 2.6` on each side — 146 px — and labels it "overlay ±150 px,
    click-through". So the drawing claims two things the code did not do:

    1. THE WINDOW WAS TOO SMALL. 96 px, while the painter's own furthest mark —
       the amber alert dot at `r * 2.24` from the centre — needs 125 px. On a
       real desktop that alarm dot was drawn OUTSIDE the window and clipped, so
       the one indicator that says "something needs you" never appeared. This is
       arithmetic, not opinion: the numbers are asserted below.

    2. OUTSIDE THE RING WAS NOT CLICK-THROUGH. The 96 px window swallowed clicks
       in its transparent corners and dropped them, because the hit test
       answered False and nobody told the window manager. `DESIGN-ambient.md`
       defended that as deliberate, twice. The owner has since chosen the
       artboard's behaviour instead: a window mask, so the desktop keeps the
       clicks that were never ours.

WHAT IS NOT PROVEN HERE
    That a real window manager honours `setMask` on a frameless translucent
    window. The mask is asserted to be BUILT from the artboard's numbers and
    handed to the window; what Windows does with it is tested on Windows.
"""
from __future__ import annotations

import math
import sys
import types

import pytest

from tests import qtstub


@pytest.fixture()
def orb(isolated_config):
    """`ui.orb_overlay` over the repo's Qt stub, with the config redirected.

    THE CONFIG MUST BE REDIRECTED, and an env var does not do it: 
    `memory.config_manager` resolves `CONFIG_FILE` once, at import time, from the
    repository root, so `JARVIS_CONFIG_DIR` is never read. A first version of
    this fixture set that variable and every drag test wrote its position into
    the developer's real `config/api_keys.json` — which then made the NEXT test
    fail, because the orb came back where the previous one left it. That is the
    cross-test leak the suite's `isolated_config` fixture exists to prevent.
    """
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
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


# ── 1. the box the artboard draws ──────────────────────────────────────────

def test_the_window_is_the_artboards_146_px_box(orb):
    """`half = r * 2.6` = 72.8, so the dashed square is 145.6 px — the window
    rounds up to 146 and the square is drawn at 1:1 inside it."""
    assert orb.window_size("active") == (orb.OVERLAY_PX, orb.OVERLAY_PX)
    assert orb.OVERLAY_PX == 146
    # and the artboard's own arithmetic is what produced it
    assert orb.OVERLAY_PX == round(orb.RADIUS * 2 * 2.6)


def test_the_window_is_the_same_size_in_every_mode(orb):
    """A window that resizes on a mode change moves its own centre under the
    cursor, and the click lands on nothing."""
    assert {orb.window_size(m) for m in ("active", "focus", "quiet")} == {(146, 146)}


def test_the_window_is_bigger_than_every_mark_the_painter_draws(orb):
    """THE CLIPPING BUG, AS ARITHMETIC.

    `paint_ring` draws, at most, `r * 2.24` from the centre (the alert dot);
    with the largest radius the orb ever uses, that has to fit in half the
    window. At 96 px it did not — 62.7 px of drawing in a 48 px half — which is
    why the alarm never showed and nothing failed.
    """
    largest = orb.RADIUS            # active is 28, focus/quiet are smaller
    deepest = largest * 2.24        # the alert tick's dot, the furthest mark
    assert deepest + 1 <= orb.OVERLAY_PX / 2, (
        f"the painter reaches {deepest:.1f} px but the window's half is "
        f"{orb.OVERLAY_PX / 2:.1f} px — the mark is clipped")


def test_the_overlay_still_covers_the_click_ring_with_room_to_spare(orb):
    cx, cy, r = orb.hit_region("active")
    assert (cx, cy) == (orb.OVERLAY_PX // 2, orb.OVERLAY_PX // 2)
    assert cx + r < orb.OVERLAY_PX and cy + r < orb.OVERLAY_PX


# ── 2. only the ring takes clicks ──────────────────────────────────────────

def test_the_mask_is_a_circle_round_the_orb(orb):
    """`overlay_mask` returns a QRegion, and it is asked for the CENTRE of the
    window — an off-by-a-few-corners mask would leave a crescent of dead
    desktop, or a crescent of desktop that cannot be clicked."""
    made = {}

    class _Region:
        def __init__(self, *a):
            made["args"] = a

    region = orb.overlay_mask(region_factory=_Region)
    assert isinstance(region, _Region)
    left, top, width, height = made["args"]
    # a square region centred in the window, sized by the hit ring
    assert width == height == 2 * orb.HIT_RING
    assert left + width // 2 == orb.OVERLAY_PX // 2
    assert top + height // 2 == orb.OVERLAY_PX // 2


def test_the_mask_follows_the_mode_it_is_asked_for(orb):
    """Focus dims the ring, and the clickable circle follows the drawing. A mask
    fixed at active's size would hand the user a target that is not there."""
    for mode in ("active", "focus", "quiet"):
        _cx, _cy, r = orb.hit_region(mode)
        got = orb.overlay_mask(mode, region_factory=_Sized).radius_of_region()
        assert got == r, f"{mode}: the mask is {got} px, the hit test says {r}"


class _Sized:
    """A region that remembers the square it was built from."""

    def __init__(self, x, y, w, h):
        self.box = (x, y, w, h)

    def radius_of_region(self):
        return self.box[2] // 2


def test_a_started_orb_puts_the_mask_on_the_window(orb):
    """The mask is only useful if it is APPLIED. Building it and forgetting to
    hand it to the window is the same bug as not building it."""
    overlay = orb.OrbOverlay()
    assert overlay.start(), overlay.error
    assert overlay._mask_applied is True
    overlay.stop()


def test_a_mask_that_raises_does_not_stop_the_orb(orb, monkeypatch):
    """No mask means the corners eat clicks again; it does not mean no orb."""
    class _Refuses:
        def __init__(self, *a):
            raise RuntimeError("no masks on this platform")

    monkeypatch.setattr(orb, "overlay_mask",
                        lambda **k: _Refuses())
    overlay = orb.OrbOverlay()
    assert overlay.start() is True
    assert overlay._mask_applied is False          # honest, not silent
    overlay.stop()


def test_the_hit_test_and_the_mask_agree(orb):
    """Two ways of answering "is this click ours" must not disagree, or the
    desktop loses clicks inside the mask and receives them outside it."""
    _cx, _cy, r = orb.hit_region("active")
    half = orb.OVERLAY_PX // 2
    for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r),
                   (int(r / math.sqrt(2)), int(r / math.sqrt(2)))):
        assert orb.inside_hit_region(half + dx, half + dy) is True
    for dx, dy in ((r + 2, 0), (0, -r - 2)):
        assert orb.inside_hit_region(half + dx, half + dy) is False


# ── 4. the things the mutation pass found unguarded ────────────────────────
#
# Each of the three below was removed from the code ON PURPOSE, and the suite
# still passed. A test that cannot tell a feature from its absence is not a
# test, so these are the assertions that were missing.

def test_changing_the_mode_actually_re_masks_the_window(orb):
    """Focus shrinks the clickable circle from 37 px to 27. If a mode change
    does not re-apply the mask, the window keeps handing the hit test a ring
    the user can no longer see — a click target around an orb that is not
    drawn there.

    The earlier mask test called `overlay_mask(mode)` DIRECTLY, so it tested
    the arithmetic and never the wiring: deleting `_apply_mask()` from
    `set_mode` left every assertion green.
    """
    overlay = orb.OrbOverlay()
    assert overlay.start(), overlay.error
    sizes = []
    real_set_mask = overlay._window.setMask

    def spy(region):
        sizes.append(region)
        return real_set_mask(region)

    overlay._window.setMask = spy
    overlay.set_mode("focus")
    overlay.set_mode("active")
    assert len(sizes) == 2, (
        f"set_mode applied the mask {len(sizes)} times, expected 2 — "
        "a mode change must re-mask the window")
    overlay.stop()


def test_a_release_that_moved_enough_does_not_also_count_as_a_click(orb):
    """The press/release split exists so a drag does not open the command bar.
    Press on the ring, drag 40 px, release: the click handler must NOT fire.

    M10 turned `if max(...) < limit` into `if False:` — every release became a
    drag — and nothing failed, because no test ever drove a press AND a release
    through the canvas with a handler attached.
    """
    fired = []
    overlay = orb.OrbOverlay(on_click=lambda: fired.append(1))
    assert overlay.start(), overlay.error
    overlay.begin_drag(40, 40)
    assert overlay.end_drag(80, 40) is True        # a drag, not a click
    assert fired == [], "a drag must not open the command bar"
    overlay.stop()


def test_a_release_without_a_move_does_count_as_a_click(orb):
    """And the other direction: press and release on the same pixel must reach
    the handler, or the orb stops opening anything at all."""
    fired = []
    overlay = orb.OrbOverlay(on_click=lambda: fired.append(1))
    assert overlay.start(), overlay.error
    overlay.begin_drag(50, 50)
    assert overlay.end_drag(51, 50) is False       # a click
    assert overlay.handle_click(50, 50) is True
    assert fired == [1]
    overlay.stop()


def test_drag_move_follows_the_pointer_relative_to_the_press(orb):
    """The orb moves BY THE DELTA the pointer travelled, not to the pointer.

    M11 made `drag_move` return immediately, so the window never moved while
    the button was down — and the release still saved a position, so the orb
    would remember a place it never went. The test drives the arithmetic
    directly because the stub's `move`/`pos` are inert.
    """
    overlay = orb.OrbOverlay()
    assert overlay.start(), overlay.error
    overlay.drag_to(500, 400)
    overlay.begin_drag(40, 40, gx=1000, gy=800)
    assert overlay._drag_from == (1000, 800, 500, 400)
    assert overlay.drag_move(1030, 810) is True
    # +30, +10 from where the press started — expressed through `_drag_from`
    x0, y0, wx, wy = overlay._drag_from
    assert (wx + 1030 - x0, wy + 810 - y0) == (530, 410)
    overlay.stop()


def test_the_dashed_box_is_actually_drawn(orb):
    """Board 1's "overlay ±150 px" box has to reach a painter.

    M13 deleted the `paint_overlay_box` call from the canvas and the whole
    suite stayed green: every test asserted the box's SIZE and none asserted
    that anything draws one. The same failure the module's own docstring
    records — "the window was created, shown, translucent and empty" — in
    miniature, for a second time.

    `drawRect` is the mark: `paint_ring` never draws a rectangle (a filled one
    would be an opaque square on someone's wallpaper), so one `drawRect` can
    only be this box.
    """
    marks = []

    class _Painter:
        def setPen(self, *a):
            pass

        def setBrush(self, *a):
            pass

        def drawRect(self, *a):
            marks.append("rect")

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            return lambda *a, **k: None

    overlay = orb.OrbOverlay()
    assert overlay.start(), overlay.error
    canvas = overlay._canvas
    canvas.paintEvent(types.SimpleNamespace(painter=_Painter()))
    overlay.stop()

    assert marks.count("rect") == 1, (
        f"the canvas drew {marks.count('rect')} rectangles; "
        "board 1's overlay boundary should be exactly one")
