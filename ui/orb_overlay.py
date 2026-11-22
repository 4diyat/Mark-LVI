"""The passive orb that stays on the desktop when no window is open.

WHY THIS IS NOT `ui/face_bubble.py`
    The bubble is 260 px and shows the avatar, because it is the assistant's
    FACE: it is meant to be looked at, dragged, and double-clicked to get the
    window back. The orb is 56 px and shows only that the assistant is there —
    idle, listening, speaking, thinking. Two different questions ("who is this"
    and "is it awake") do not want one widget answering both, and shrinking the
    bubble to 56 px makes the avatar's eyes unreadable and its drag target
    unusable.

    What they DO share is the window plumbing: frameless, off the taskbar,
    always on top. That is why `window_flags()` below exists in the same shape
    as the bubble's — the flag names are the part that goes wrong, and the test
    checks them by name rather than by integer.

WHERE THE DIM RULE LIVES NOW
    Focus and Quiet dim the orb. That is a product decision the owner made
    explicitly, and it is expressed as a table (`appearance`) rather than as
    numbers scattered through the paint code, because the paint code is the one
    place a future change would forget. `focus` shrinks 28 → 18 px and drops the
    glow; `quiet` shrinks to 14 px and turns the ring into a dotted one. Shape
    changes as well as colour, so a colour-blind user reads the same difference
    a sighted one does.

    The table and the drawing both moved to `ui/orb_paint.py`, because keeping
    them here meant the HUD drew a second, older orb — see that module. This
    file kept the window: 96 px, frameless, one click target.

WHAT IT DOES NOT DO
    It does not talk to `JarvisLive` and it does not decide the presence mode. It
    is told, twice a second at most, what to look like. Every method is a no-op
    until `start()` succeeds, because a widget that failed to build must not
    turn the assistant's state update into an exception on the caller's thread.
"""
from __future__ import annotations

from typing import Callable

# THE GEOMETRY AND THE MODE TABLE MOVED to `ui/orb_paint.py`, which now draws
# the main window's orb as well as this one. Re-exported here because every
# module that asks "how big is the ring" (`lifecycle`, the tray, the tests) has
# always asked this file, and a move is not a rename.
from ui.orb_paint import (                      # noqa: F401 — re-exported
    _APPEARANCE, GLOW, HIT_RING, RADIUS, SIZE, Appearance, appearance,
    paint_ring,
)

# Where the window's three flags are named. A missing name is a TypeError on the
# user's desktop and nowhere else, so the list is pinned by a test.
_FLAGS = ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint")

# Redrawn at 12 fps, not 30: the orb has no mouth to animate and the glow is
# static except while speaking. A 30 fps timer on a 96 px window is a wake-up
# 30 times a second to draw the same ellipse.
FRAME_MS = 83


def window_size(mode: str) -> tuple[int, int]:
    """The window is the same size in every mode, on purpose.

    Resizing the window would move its centre unless the position is recomputed,
    and a window that changes size under the cursor is a click that lands on
    nothing. So the ring shrinks inside a fixed frame.
    """
    return (SIZE, SIZE)


def hit_region(mode: str = "active") -> tuple[int, int, int]:
    """(cx, cy, radius) of the clickable circle, in window coordinates."""
    centre = SIZE // 2
    ring = min(HIT_RING, appearance(mode).radius + 9)
    return (centre, centre, ring)


def inside_hit_region(x: int, y: int, mode: str = "active") -> bool:
    """Whether a point in window coordinates lands on the orb.

    Used instead of a Qt input mask: the mask needs a `QRegion` per mode and is
    the part that cannot be verified without a window manager. This answers the
    question the mask exists for, and a wrong answer here is testable.
    """
    cx, cy, r = hit_region(mode)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def window_flags(Qt) -> int:
    """Frameless + off the taskbar + always on top. Same trio as the bubble.

    `WindowTransparentForInput` is NOT in this list. The orb is the one surface
    that must accept a click — it is how the command bar opens. The flags that
    make the pointer ring click-through would make the orb unclickable, and the
    two look identical in a screenshot.
    """
    flags = Qt.WindowType
    return (getattr(flags, _FLAGS[0]) | getattr(flags, _FLAGS[1])
            | getattr(flags, _FLAGS[2]))


def corner_anchor(area, size: int, margin: int = 24) -> tuple[int, int]:
    """Where the orb sits: bottom-right, clear of the taskbar.

    `area` is a screen's available geometry (a rect with x/y/width/height) — the
    one thing about placement that can be decided without a window manager, and
    the one thing that was wrong for the bubble on its first try (it sat on the
    taskbar).
    """
    x = area.x() + area.width() - size - margin
    y = area.y() + area.height() - size - margin
    return (max(area.x(), x), max(area.y(), y))


def _assistant_name() -> str:
    """The name the user gave the assistant, for the window title.

    Not a translated string: it is a value the user typed, and `i18n.label()`
    has no key for it. Falling back on any failure, because a widget constructor
    that raises because a config file is unreadable turns a cosmetic surface
    into a crash.
    """
    try:
        from memory.config_manager import get_assistant_name

        return str(get_assistant_name() or "JARVIS")
    except Exception:                               # noqa: BLE001
        return "JARVIS"


class OrbOverlay:
    """A small always-on-top ring that reports the assistant's state.

    `on_click` is called once per click on the ring. It is not called for a
    click anywhere else in the window, which is what keeps the orb from eating
    clicks meant for the desktop.
    """

    def __init__(self, mode: str = "active",
                 on_click: Callable[[], None] | None = None):
        self._mode = mode
        self._on_click = on_click
        self._window = None
        self._canvas = None
        self._state = "idle"
        self._level = 0.0           # 0..1, only the glow uses it
        self._placed = False
        self._timer = None
        self._error = ""

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def error(self) -> str:
        return self._error

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def state(self) -> str:
        return self._state

    @property
    def audio_level(self) -> float:
        """How loud the assistant is, 0..1. Clamped here so the painter can
        trust it: a NaN or a 40 would otherwise become a gradient Qt refuses
        to build, and the failure would show up as a plain ring."""
        try:
            return max(0.0, min(1.0, float(self._level)))
        except (TypeError, ValueError):
            return 0.0

    @property
    def visible(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.isVisible())
        except Exception:                           # noqa: BLE001
            return False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Build and show the orb. Returns `available`; never raises.

        A failure is survivable: the tray icon still exists, so the user keeps a
        working assistant and loses the decoration. That is why this returns a
        bool — the caller reports it and carries on in the tray.
        """
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QWidget

            window = QWidget()
            window.setWindowFlags(window_flags(Qt))
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setWindowTitle(_assistant_name())
            window.setFixedSize(*window_size(self._mode))

            canvas = _build_canvas(window, self)
            canvas.setGeometry(0, 0, *window_size(self._mode))

            self._window, self._canvas = window, canvas
            self._place()
            window.show()
            self._start_timer()
            return True
        except Exception as e:                      # noqa: BLE001
            self._window = None
            self._canvas = None
            self._error = f"{type(e).__name__}: {e}"
            return False

    def stop(self) -> None:
        """Take the orb down and stop its timer."""
        self._stop_timer()
        window, self._window = self._window, None
        self._canvas = None
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: could not remove the window — "
                  f"{type(e).__name__}: {e}")

    def show(self) -> None:
        self._apply_visibility(True)

    def hide(self) -> None:
        self._apply_visibility(False)

    def _apply_visibility(self, visible: bool) -> None:
        window = self._window
        if window is None:
            return
        try:
            if visible:
                window.show()
                self._start_timer()
                self._repaint()
            else:
                window.hide()
                self._stop_timer()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: could not change visibility — "
                  f"{type(e).__name__}: {e}")

    # ── state ────────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Idle / listening / speaking / thinking — the same words the HUD uses."""
        self._state = str(state or "idle").strip().lower() or "idle"
        self._repaint()

    def set_audio_level(self, level: float) -> None:
        """The glow follows the voice while speaking. Cheap and idempotent:
        this is called from the audio thread, and the orb is decoration."""
        self._level = level
        if self._state == "speaking":
            self._repaint()

    def set_mode(self, mode: str) -> None:
        """Active / focus / quiet. Redraws, never resizes the window."""
        self._mode = str(mode or "active").strip().lower() or "active"
        self._repaint()

    def _repaint(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.update()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: repaint dropped — {type(e).__name__}: {e}")

    # ── timer ────────────────────────────────────────────────────────────────

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        try:
            from PyQt6.QtCore import QTimer
            timer = QTimer()
            timer.setInterval(FRAME_MS)
            timer.timeout.connect(self._repaint)
            timer.start()
            self._timer = timer
        except Exception as e:                      # noqa: BLE001
            # A static orb is still a working orb; the timer only exists so the
            # glow can follow the audio level while speaking.
            print(f"[JARVIS] Orb overlay: no animation timer — {type(e).__name__}: {e}")

    def _stop_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: timer would not stop — {type(e).__name__}: {e}")

    # ── placement and clicks ─────────────────────────────────────────────────

    def _place(self) -> None:
        """First show: bottom-right, clear of the taskbar. The user's drag wins."""
        if self._placed or self._window is None:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            x, y = corner_anchor(screen.availableGeometry(), SIZE)
            self._window.move(x, y)
            self._placed = True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: could not choose a corner — "
                  f"{type(e).__name__}: {e}")

    def handle_click(self, x: int, y: int) -> bool:
        """Route one click. True if it landed on the ring and was handled.

        Separate from the Qt event so the rule — a click three pixels outside
        the ring belongs to the desktop, not to us — can be tested without a
        display.
        """
        if not inside_hit_region(x, y, self._mode):
            return False
        cb = self._on_click
        if cb is None:
            return False
        try:
            cb()
            return True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: click handler failed — "
                  f"{type(e).__name__}: {e}")
            return False


def _build_canvas(parent, owner: "OrbOverlay"):
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

        def paintEvent(self, _event):               # noqa: N802 — Qt's name
            try:
                from PyQt6.QtGui import QPainter

                painter = QPainter(self)
                try:
                    # `SIZE` rather than `self.width()`: the test stub has no
                    # geometry, and the window is a fixed size anyway. A painter
                    # that trusted the widget's reported size would draw nothing
                    # under the stub and so could not be tested at all.
                    paint_orb(painter, SIZE, owner.mode, owner.state,
                              owner.audio_level)
                finally:
                    painter.end()
            except Exception as e:                  # noqa: BLE001
                # A failed repaint costs a frame. Letting it escape would take
                # down the event loop of a window with no other purpose.
                print(f"[JARVIS] Orb overlay: could not paint — "
                      f"{type(e).__name__}: {e}")

        def mousePressEvent(self, event):           # noqa: N802 — Qt's name
            """Route the press: the child covers the window, so it comes first."""
            try:
                pos = event.position()
                if owner.handle_click(int(pos.x()), int(pos.y())):
                    event.accept()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Orb overlay: press not handled — "
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
