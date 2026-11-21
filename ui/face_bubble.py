"""The face on the desktop — JARVIS's presence when no window is open.

WHY THIS EXISTS
    Ambient mode (see ui/lifecycle.py) removed the window, and the tray icon
    replaced it. That is enough to USE JARVIS but not enough to be aware of it:
    a tray icon has no state a glance can read, which is why the tooltip had to
    carry the whole answer. This is the third mode — the assistant's face,
    small, on top, and honest about what it is doing, with a double-click to get
    the full interface back.

WHY IT BUILDS A SECOND `HudCanvas` RATHER THAN BORROWING THE WINDOW'S
    `MainWindow.hud` already exists and already animates, and reusing it would
    have saved this file. It cannot be done: a widget has one parent, and
    re-parenting the window's canvas into a floating bubble would leave the
    window with an empty centre the moment the user summoned it — the two
    surfaces take turns being visible, so they cannot share one widget.

    A separate HudCanvas costs one more animated avatar at 30 fps, which is the
    price of the mode and is why `set_state` mirrors the state onto both rather
    than either one guessing. `HudCanvas` is a plain `QWidget` subclass with no
    window assumptions, and `ui/desktop_workspace.py` already hosts one in a
    small stage — so this is an existing use, not a new one.

WHAT IT DOES NOT DO
    It does not talk to `JarvisLive`. Every method here is called by
    `ui/lifecycle.py` or `ui/window.py` with a value they already have, so the
    bubble never becomes a second place that knows what the assistant is doing.
"""
from __future__ import annotations

from typing import Callable

# The size the face is drawn at. 260 is large enough that the avatar's eyes
# still read as eyes (the mesh is drawn from geometry, not a bitmap, so it
# scales), and small enough to sit in a corner without owning it.
DEFAULT_SIZE = 260

# Where OSes disagree about what "no window frame" means. Qt needs the three
# flags together: FramelessWindowHint drops the chrome, ToolWindowHint keeps it
# off the taskbar (a second taskbar entry for a bubble is confusing) and
# WindowStaysOnTopHint is the whole point of the mode.
_FLAGS = ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint")


def window_flags(Qt) -> int:
    """The frameless + always-on-top flag combination, built from `Qt`.

    Pulled out as a function because `Qt.WindowType` differs between binding
    versions and a hard-coded integer is unreadable. Tested against a stub that
    only offers the three names, so a flag that does not exist fails here rather
    than on the user's desktop.
    """
    flags = Qt.WindowType
    # No `int()` around this: in PyQt6 the enum OR already yields the int Qt
    # wants, and wrapping it made the function refuse the one shape that is not
    # an int — which is how the repo's own Qt stub caught it.
    return (getattr(flags, _FLAGS[0]) | getattr(flags, _FLAGS[1])
            | getattr(flags, _FLAGS[2]))


class FaceBubble:
    """A small always-on-top window showing the animated avatar.

    `on_double_click` is how the user gets the interface back without hunting
    for the tray icon. `on_close` is not offered on purpose: a bubble that can
    be closed is a bubble that can be lost, and the tray's INTERFACE button is
    where that decision belongs.
    """

    def __init__(self, face_path: str, assistant_name: str = "J.A.R.V.I.S",
                 on_double_click: Callable[[], None] | None = None,
                 size: int = DEFAULT_SIZE):
        self._face_path = face_path
        self._name = assistant_name
        self._size = max(120, int(size))
        self._on_double_click = on_double_click
        self._window = None
        self._canvas = None
        self._state = "idle"
        self._drag = None            # (cursor, origin) while being dragged
        self._placed = False         # has an initial position been chosen?

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def visible(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.isVisible())
        except Exception:                           # noqa: BLE001
            return False

    @property
    def canvas(self):
        """The `HudCanvas`, for the caller that wants to push audio into it."""
        return self._canvas

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Build and show the bubble. Returns `available`; never raises.

        A failure here is survivable by design: the tray still exists, so the
        user keeps a working assistant and loses only the decoration. That is
        why this returns a bool instead of logging and continuing — the caller
        reports it and shows the tray.
        """
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QWidget
            from ui.hud_canvas import HudCanvas

            window = QWidget()
            # Not `Qt.WindowType(...)`: the OR already produces the value
            # Qt wants, and calling the enum on it is a TypeError.
            window.setWindowFlags(window_flags(Qt))
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setWindowTitle(self._name)
            window.setFixedSize(self._size, self._size)

            canvas = HudCanvas(self._face_path, self._name, window)
            canvas.setGeometry(0, 0, self._size, self._size)
            canvas.setMinimumSize(1, 1)

            # Dragging: a frameless window does not move itself, and a bubble
            # that cannot be moved out of the way is worse than no bubble.
            window.mousePressEvent = self._on_press
            window.mouseMoveEvent = self._on_move
            window.mouseReleaseEvent = self._on_release
            window.mouseDoubleClickEvent = self._on_double_click_event

            self._window, self._canvas = window, canvas
            self._place()
            window.show()
            self.set_state(self._state)
            return True
        except Exception as e:                      # noqa: BLE001
            self._window = None
            self._canvas = None
            self._error = f"{type(e).__name__}: {e}"
            return False

    def stop(self) -> None:
        """Take the bubble down and stop its animation timer."""
        window, self._window = self._window, None
        self._canvas = None
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: could not remove the window — "
                  f"{type(e).__name__}: {e}")

    # ── state ────────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Mirror the assistant's state onto the face.

        The same words the window's canvas uses, so the avatar looks the same in
        both places — and so a state added later only has to be understood once.
        """
        self._state = str(state or "idle").strip() or "idle"
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.state = self._state.upper()
            canvas.speaking = self._state.upper() == "SPEAKING"
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: state '{state}' not applied — "
                  f"{type(e).__name__}: {e}")

    def set_audio_level(self, level: float) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.set_audio_level(level)
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: audio level dropped — {type(e).__name__}: {e}")

    def push_visemes(self, frames, hop: float, at: float) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.push_visemes(frames, hop, at)
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: visemes dropped — {type(e).__name__}: {e}")

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.glance(dx, dy, hold)
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: glance dropped — {type(e).__name__}: {e}")

    # ── placement ────────────────────────────────────────────────────────────

    def _place(self) -> None:
        """First show: bottom-right, clear of the taskbar and of the tray.

        Done once. After that the user's own dragging wins — a bubble that
        re-positions itself on every show is a bubble the user keeps having to
        move, and the whole point of dragging it is that the position was wrong.
        """
        if self._placed or self._window is None:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()       # excludes the taskbar
            margin = 24
            x = area.x() + area.width() - self._size - margin
            y = area.y() + area.height() - self._size - margin
            self._window.move(max(area.x(), x), max(area.y(), y))
            self._placed = True
        except Exception as e:                      # noqa: BLE001
            # Qt places it somewhere sensible on its own. Worth a line only
            # because the DEFAULT corner is the difference between "out of the
            # way" and "in front of the window I was reading".
            print(f"[JARVIS] Face bubble: could not choose a corner — "
                  f"{type(e).__name__}: {e}")

    # ── mouse: drag, and the way back ────────────────────────────────────────

    def _on_press(self, event) -> None:
        try:
            button = event.button()
            # The enum, not a fresh call: comparing `event.button()` with
            # `event.button().LeftButton` asks the event for the button TWICE,
            # and a Qt event answers the second question with nothing.
            if button == button.LeftButton:
                self._drag = (event.globalPosition().toPoint(),
                              self._window.pos())
        except Exception as e:                      # noqa: BLE001
            self._drag = None
            print(f"[JARVIS] Face bubble: drag not started — {type(e).__name__}: {e}")

    def _on_move(self, event) -> None:
        if self._drag is None or self._window is None:
            return
        try:
            cursor, origin = self._drag
            delta = event.globalPosition().toPoint() - cursor
            self._window.move(origin + delta)
        except Exception as e:                      # noqa: BLE001
            self._drag = None
            print(f"[JARVIS] Face bubble: drag stopped — {type(e).__name__}: {e}")

    def _on_release(self, _event) -> None:
        self._drag = None

    def _on_double_click_event(self, event) -> None:
        """Double-click anywhere on the face: open the real interface."""
        cb = self._on_double_click
        if cb is None:
            return
        try:
            cb()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Face bubble: summon failed — {type(e).__name__}: {e}")
        try:
            event.accept()
        except Exception:                           # noqa: BLE001
            # The event is already delivered and the summon already happened;
            # an event object that cannot be accepted changes nothing.
            print("[JARVIS] Face bubble: event could not be accepted (ignored)")
