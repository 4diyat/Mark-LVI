"""The canvas that puts the orb on the desktop window.

WHY THIS IS NOT IN `ui/orb_overlay.py`
    It was, until the overlay crossed the 600-line ceiling. The boundary is the
    one that file has always drawn: `orb_overlay` owns the WINDOW — flags, size,
    placement, timer, mask, press routing — and this module owns the only code
    in that pair that draws. A module that both decides where a window goes and
    records what a `QPainter` was asked to draw is two jobs.

    It also has the test story of a painter: `tests/test_orb_overlay.py` drives
    `paint_orb` through a recording painter, and `_painter_for` exists so
    `paintEvent` can be driven the same way. Nothing here builds a window.

WHY THE CLASS IS MADE INSIDE A FUNCTION
    A `QWidget` subclass needs Qt at class-creation time, and this module is
    imported on machines with no display. So `_build_canvas` creates it after Qt
    is already being imported.

WHY IT EXISTS AT ALL, AND THE BUG IT FIXES
    The first version kept the painter in a plain object with an `update()` that
    forwarded to the window, and there was no `paintEvent` anywhere. Nothing
    ever called `paint_orb`, so the orb window was created, shown, translucent —
    and empty. Every test passed, because the geometry, the modes and the hit
    region were all correct and none of them is what puts a pixel on screen.
"""
from __future__ import annotations

# THE IMPORTS COME FROM `orb_paint`, NOT FROM `orb_overlay`. The overlay imports
# this module, so importing the overlay back would be a cycle — and the drawing
# never needed the window in the first place: it needs the geometry and the one
# painter.
from ui.orb_paint import OVERLAY_PX, appearance, paint_overlay_box, paint_ring

def _is_right(event) -> bool:
    """Whether this press was the right button. False when it cannot be read.

    FAILING TOWARDS THE LEFT BUTTON is deliberate: an unreadable button on a
    platform whose events this sandbox cannot see should still open the panel.
    A silent menu is recoverable with a chord; a dead orb is not.
    """
    try:
        from PyQt6.QtCore import Qt

        return event.button() == Qt.MouseButton.RightButton
    except Exception as e:                          # noqa: BLE001
        print(f"[JARVIS] Orb overlay: could not read the mouse button "
              f"({type(e).__name__}: {e}); treating it as a left click")
        return False


def _painter_for(widget, event=None):
    """A `QPainter` on `widget` — or the one handed in as `event.painter`.

    WHY THE PAINTER CAN BE INJECTED, WHICH IS NOT A NORMAL Qt PATTERN
        `paintEvent` builds its own `QPainter`, so a test that wants to see what
        was drawn cannot pass a recorder in — and the suite's `QPainter` stub is
        a bare object whose every method is a silent no-op. That combination
        made the one thing board 1 adds (a dashed box) unassertable: deleting
        the draw call left the suite green, which is exactly the "the window was
        shown, translucent and empty" bug this module already has a docstring
        about.

        A recorder supplied as `event.painter` is used INSTEAD of a real one.
        Nothing in the app passes that; `paintEvent(event)` from Qt always
        builds its own.
    """
    supplied = getattr(event, "painter", None) if event is not None else None
    if supplied is not None:
        return supplied
    from PyQt6.QtGui import QPainter

    return QPainter(widget)


def _build_canvas(parent, owner):
    """Build the widget that actually paints the ring.

    WHY THIS IS A FUNCTION AND NOT A CLASS AT MODULE SCOPE
        A `QWidget` subclass has to import Qt when the class is created, and this
        module is imported by tests on machines with no display and by CI that
        installs only the test tooling. So the class is created inside `start()`,
        where Qt is already being imported anyway.

    WHY IT EXISTS AT ALL, AND THE BUG IT FIXES
        The first version kept the painter in a plain object with an `update()`
        that forwarded to the window, and there was no `paintEvent` anywhere.
        Nothing ever called `paint_orb`, so the orb window was created, shown,
        translucent — and empty. Every test passed, because the geometry, the
        modes and the hit region were all correct and none of them is what puts
        a pixel on screen. That is the difference between the design being
        implemented and being VISIBLE.
    """
    from PyQt6.QtWidgets import QWidget

    class _OrbCanvas(QWidget):
        """The ring. Owns no state: it asks the overlay what to draw."""

        def paintEvent(self, event=None):           # noqa: N802 — Qt's name
            try:
                painter = _painter_for(self, event)
                try:
                    # `SIZE` rather than `self.width()`: the test stub has no
                    # geometry, and the window is a fixed size anyway. A painter
                    # that trusted the widget's reported size would draw nothing
                    # under the stub and so could not be tested at all.
                    paint_orb(painter, OVERLAY_PX, owner.mode, owner.state,
                              owner.audio_level)
                    # The dashed boundary, at the artboard's `r * 2.6 / 2`,
                    # which is what the window is sized for. Drawn after the
                    # ring so the ring is never crossed by a dash.
                    paint_overlay_box(painter, OVERLAY_PX / 2.0, OVERLAY_PX / 2.0,
                                      OVERLAY_PX / 2.0 - 1)
                finally:
                    painter.end()
            except Exception as e:                  # noqa: BLE001
                # A failed repaint costs a frame. Letting it escape would take
                # down the event loop of a window with no other purpose.
                print(f"[JARVIS] Orb overlay: could not paint — "
                      f"{type(e).__name__}: {e}")

        def mousePressEvent(self, event):           # noqa: N802 — Qt's name
            """Remember where the press started; do not act on it yet.

            The click used to happen HERE, which made a drag impossible: every
            attempt to move the orb also opened the command bar. Press records,
            release decides — a release within a few pixels is the click.
            """
            try:
                pos = event.position()
                x, y = int(pos.x()), int(pos.y())
                # WHICH BUTTON, BEFORE ANYTHING ELSE. Board 4 gives the right
                # button its own job, and the canvas only ever handled presses —
                # it treated every one as the left button, so a right click
                # opened the panel and the menu was unreachable.
                if _is_right(event):
                    if owner.handle_click(x, y, button="right"):
                        event.accept()
                    return
                gx = gy = None
                try:
                    glob = event.globalPosition()
                    gx, gy = int(glob.x()), int(glob.y())
                except Exception as e:              # noqa: BLE001
                    # The click still works; the orb just cannot be dragged
                    # this session. Said out loud rather than swallowed.
                    print(f"[JARVIS] Orb overlay: no global press point, drag "
                          f"disabled ({type(e).__name__}: {e})")
                owner.begin_drag(x, y, gx, gy)
                event.accept()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Orb overlay: press not handled — "
                      f"{type(e).__name__}: {e}")

        def mouseMoveEvent(self, event):            # noqa: N802 — Qt's name
            """Follow the pointer while the button is down.

            THIS HANDLER IS THE DRAG. Without it the release still SAVED a
            position, so the orb would have remembered a place it never moved
            to — a test would pass and the orb would be immovable.
            """
            try:
                if owner._press_at is None:
                    return
                glob = event.globalPosition()
                owner.drag_move(int(glob.x()), int(glob.y()))
                event.accept()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Orb overlay: drag move dropped — "
                      f"{type(e).__name__}: {e}")

        def mouseReleaseEvent(self, event):         # noqa: N802 — Qt's name
            """A moved release is a drag; a still one is the click."""
            try:
                pos = event.position()
                x, y = int(pos.x()), int(pos.y())
                if owner.end_drag(x, y):
                    event.accept()
                    return
                if owner.handle_click(x, y):
                    event.accept()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Orb overlay: release not handled — "
                      f"{type(e).__name__}: {e}")

    return _OrbCanvas(parent)


def paint_orb(painter, size: int, mode: str, state: str, level: float = 0.0) -> None:
    """Draw this window's orb. Delegates to `ui.orb_paint.paint_ring`.

    WHY THIS IS NOW THREE LINES
        It used to be the only painter that knew about presence modes, and the
        main window had a second one that did not. Two painters meant the design
        work reached whichever surface was edited last — which was this one, so
        the 56 px ring dimmed in Fokus while the HUD kept drawing the old orb.
        The sizes stay here (the window is 96 px and its hit test depends on
        that); the drawing lives in one module for every surface.

    THE BACKGROUND IS NOT FILLED, and that is deliberate. Drawing happens on a
    translucent frameless window, where a filled rect is an opaque square on
    the user's wallpaper.
    """
    paint_ring(painter, size / 2.0, size / 2.0, float(appearance(mode).radius),
               mode=mode, state=state, level=level)
