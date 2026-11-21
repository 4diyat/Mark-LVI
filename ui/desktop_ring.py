"""The same ring, on the desktop, following the real OS cursor.

WHY THIS EXISTS AT ALL
    `ui/hand_gesture.py` has always drawn a 42px cyan ring where the camera
    thinks the hand is, INSIDE the window. When OS mode moves the actual mouse
    pointer, the user's own cursor disappears off into whatever the hand
    touched, and the ring stays behind in the window — so the one moment the
    feature needs a visible reference is the moment it has none.

    This overlay draws that same ring at the OS pointer's position. The way it
    learns that position is the important part.

WHY IT READS THE CURSOR INSTEAD OF DRAWING THE INTENT
    The tempting version draws the ring at `gesture_os.coordinate(x, y, ...)` —
    where the hand ASKED the pointer to go. That version lies. `pyautogui`
    clamps, the platform may refuse the move, a fullscreen window can swallow
    it, and a ghost sample released between two frames leaves the cursor where
    it was. A ring drawn from the intent shows a position the pointer may never
    have reached, and the user only finds out by clicking something.

    So once per frame this reads `QApplication`'s cursor position — the position
    the desktop is actually using — and draws the ring there. The ring cannot
    disagree with the cursor because it is drawn from it.

WHAT IT DOES NOT DO
    * It never takes focus, never accepts mouse events, and never appears in a
      taskbar: it is a decoration, and a decoration that steals a click is a bug.
    * It does not decide when to appear. `core/pointer_ring.py::visible()` owns
      that, and it takes the mode, the freeze state and the policy's `Fit`.
    * It does not open the camera or read samples. `ui/hand_gesture.py` feeds it.
"""
from __future__ import annotations

from core import logbook, pointer_ring


class DesktopRing:
    """A frameless, click-through ring that follows the system cursor."""

    def __init__(self):
        self._w = None                      # built lazily, on first show
        self._shown = False

    # ── lifecycle ─────────────────────────────────────────────────────────

    def _build(self):
        if self._w is not None:
            return self._w
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QLabel

        w = QLabel()
        # Frameless + Tool + StayOnTop is the same trio `ui/face_bubble.py`
        # won the same argument with: no title bar, no taskbar entry, and above
        # the thing it is commenting on.
        w.setWindowFlags(Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput)
        # Click-through: the ring sits on top of whatever the hand is about to
        # click, so a ring that accepts the click would eat the gesture it is
        # showing. `WindowTransparentForInput` is Qt's own answer; the attribute
        # is the belt to that braces, because some compositors honour only one.
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        w.setFixedSize(pointer_ring.size(), pointer_ring.size())
        w.setStyleSheet(pointer_ring.style(False))
        w.setAccessibleName("hand pointer")
        self._w = w
        return w

    def show(self, pinched: bool = False) -> None:
        """Put the ring where the cursor is, and make it visible."""
        w = self._build()
        self._place(w)
        w.setStyleSheet(pointer_ring.style(pinched))
        if not self._shown:
            try:
                w.show()
            except Exception as e:          # noqa: BLE001 — a desktop edge
                logbook.get(__name__).debug("could not show the ring: %s", e)
                return
            self._shown = True
        try:
            w.raise_()
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not raise the ring: %s", e)

    def hide(self) -> None:
        """Take it away. Called whenever the pointer is not being driven."""
        if self._w is None or not self._shown:
            return
        try:
            self._w.hide()
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not hide the ring: %s", e)
        self._shown = False

    @property
    def visible(self) -> bool:
        return self._shown

    # ── following the cursor ──────────────────────────────────────────────

    def _place(self, w) -> None:
        point = cursor_position()
        if point is None:
            return
        x, y = pointer_ring.where(point[0], point[1])
        try:
            w.move(x, y)
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not move the ring: %s", e)

    def tick(self, pinched: bool = False) -> None:
        """One frame: follow the cursor, and repaint only when the state flips.

        Called at the tracking loop's rate. The stylesheet is compared before it
        is applied because `setStyleSheet` is a full restyle of the widget, and
        doing that 30 times a second for one changed boolean is how a decoration
        becomes a performance problem.
        """
        w = self._build()
        self._place(w)
        wanted = pointer_ring.style(pinched)
        if w.styleSheet() != wanted:
            w.setStyleSheet(wanted)


def cursor_position() -> tuple[int, int] | None:
    """Where the desktop's pointer is, or None when it cannot be read.

    Read from `QCursor.pos()`, which asks the window system rather than
    remembering an intention. Returns None instead of raising: a compositor
    that refuses the query must not take the tracking loop down with it, and the
    caller simply skips that frame's move.
    """
    try:
        from PyQt6.QtGui import QCursor
        point = QCursor.pos()
        return (point.x(), point.y())
    except Exception as e:                  # noqa: BLE001 — no display, no cursor
        logbook.get(__name__).debug("no cursor position: %s", e)
        return None


__all__ = ["DesktopRing", "cursor_position"]
