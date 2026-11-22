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
    _APPEARANCE, GLOW, HIT_RING, OVERLAY_PX, RADIUS, SIZE, Appearance,
    appearance, paint_overlay_box, paint_ring,
)

# The window's arithmetic moved to `ui/orb_place.py` when this file reached 739
# lines: the size, the clickable circle, the mask and the remembered drag are
# pure functions with no display in them, and they are what a test can hold.
# Re-exported here because every caller has always asked this module.
from ui.orb_snap import snap_to_edge

from ui.orb_place import (                      # noqa: F401 — re-exported
    POSITION_KEY, corner_anchor, hit_region, inside_hit_region, overlay_mask,
    read_position, save_position, screen_area as _screen_area, window_size,
    write_position,
)

# THE CANVAS AND ITS PAINTER LIVE IN `ui/orb_canvas.py`, split off when this
# file crossed the 600-line ceiling. The boundary is the one this module has
# always had: everything above is the WINDOW (flags, size, placement, timer,
# mask, press routing); the canvas is the only code that puts a pixel on
# screen. Imported at the top because `start()` calls it, and re-exported
# because `paint_orb` has always been reachable from this module.
from ui.orb_canvas import (                     # noqa: F401 — re-exported
    _build_canvas, _painter_for, paint_orb,
)

# Where the window's three flags are named. A missing name is a TypeError on the
# user's desktop and nowhere else, so the list is pinned by a test.
_FLAGS = ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint")

# Redrawn at 12 fps, not 30: the orb has no mouth to animate and the glow is
# static except while speaking. A 30 fps timer on a 146 px window is a wake-up
# 30 times a second to draw the same ellipse.
FRAME_MS = 83

# How far the pointer may move between press and release and still be a click.
# 4 px absorbs a shaky hand; anything larger turns a deliberate nudge into a
# click, and anything smaller turns a click into a 1 px drag.
DRAG_THRESHOLD = 4


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
                 on_click: Callable[[], None] | None = None,
                 on_menu: Callable[[], None] | None = None):
        self._mode = mode
        self._on_click = on_click
        # Board 4: "KLIK KANAN — menu cepat". Optional, because a caller that
        # only wants the panel must not be forced to build a menu, and a right
        # click with no handler is consumed and does nothing — it must not fall
        # through to the left handler, which would make the same click open the
        # panel on a machine with no menu.
        self._on_menu = on_menu
        self._window = None
        self._canvas = None
        self._state = "idle"
        self._level = 0.0           # 0..1, only the glow uses it
        self._placed = False
        self._timer = None
        self._error = ""
        # Whether `setMask` was actually applied. Public-ish because "the mask
        # failed" and "the mask was never attempted" are different problems, and
        # the difference is invisible from a screenshot.
        self._mask_applied = False
        self._press_at: tuple[int, int] | None = None
        self._drag_from: tuple[int, int, int, int] | None = None

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
    def mask_applied(self) -> bool:
        """Whether clicks outside the ring reach the desktop."""
        return self._mask_applied

    @property
    def position(self) -> tuple[int, int] | None:
        """Where the window is now, in screen coordinates, or None."""
        if self._window is None:
            return None
        try:
            point = self._window.pos()
            return (int(point.x()), int(point.y()))
        except Exception:                           # noqa: BLE001
            return None

    def saved_position(self) -> tuple[int, int] | None:
        """The remembered corner, so a caller can show it or assert on it."""
        return read_position()

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
            self._apply_mask()
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
        """Active / focus / quiet. Redraws and re-masks, never resizes.

        THE MASK HAS TO MOVE WITH THE RING. Focus drops the clickable circle
        from 37 px to 27 px; a mask left at active's size would keep a 10 px
        ring of invisible click target around a smaller orb — the user would
        click what looks like the orb and hit nothing.
        """
        self._mode = str(mode or "active").strip().lower() or "active"
        self._apply_mask()
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
        """First show: the user's saved drag if it is still on a screen,
        otherwise bottom-right, clear of the taskbar.

        THE SAVED POSITION IS CHECKED, NOT OBEYED — `_read_position` returns
        None for a point on a monitor that has since been unplugged, and this
        falls through to the corner. Restoring a window onto a screen that no
        longer exists is how an orb becomes "missing" while running fine.
        """
        if self._placed or self._window is None:
            return
        try:
            saved = read_position()
            if saved is not None:
                self._window.move(*saved)
                self._placed = True
                return
            area = _screen_area()
            if area is None:
                return
            x, y = corner_anchor(area, OVERLAY_PX)
            self._window.move(x, y)
            self._placed = True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: could not choose a corner — "
                  f"{type(e).__name__}: {e}")

    def _apply_mask(self) -> None:
        """Hand the clickable circle to the window manager. Never fatal.

        A window with no mask is the old behaviour — clicks in the corners are
        swallowed — which is bad but visible. A window that is not there is
        worse, so a failure is recorded in `mask_applied` and the orb stays.
        """
        if self._window is None:
            return
        try:
            self._window.setMask(overlay_mask(self._mode))
            self._mask_applied = True
        except Exception as e:                      # noqa: BLE001
            self._mask_applied = False
            print(f"[JARVIS] Orb overlay: no click mask — clicks in the "
                  f"transparent corners will be swallowed ({type(e).__name__}: {e})")

    def drag_to(self, x: int, y: int, moved: bool = True) -> bool:
        """Move the window and remember it, if this was a real drag.

        `moved=False` is a press-and-release on the same pixel: that is the
        click that opens the command bar, not a drag. Treating a zero-length
        drag as a move would swallow the click, and the orb would stop opening
        anything at all. Returns whether the position was saved.
        """
        if not moved or self._window is None:
            return False
        try:
            self._window.move(int(x), int(y))
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: could not move — "
                  f"{type(e).__name__}: {e}")
            return False
        return save_position(int(x), int(y))

    def begin_drag(self, x: int, y: int,
                   gx: int | None = None, gy: int | None = None) -> None:
        """Record where a press started, so the release can measure the move.

        `gx`/`gy` are the SCREEN coordinates of the press. Without them the
        release can still tell a drag from a click, but the orb cannot follow
        the pointer — which is the difference between a movable orb and an orb
        that jumps when the mouse is released.
        """
        self._press_at = (int(x), int(y))
        self._drag_from = None
        if gx is None or gy is None:
            return
        origin = self.position
        if origin is not None:
            self._drag_from = (int(gx), int(gy), origin[0], origin[1])

    def drag_move(self, gx: int, gy: int) -> bool:
        """Follow the pointer, expressed as a DELTA from where the press started.

        A delta rather than "centre the window on the cursor": the user grabbed
        the orb somewhere, and moving it under their finger on the first pixel
        of a drag is the paper-cut that makes a drag feel broken.

        No position is written here — `end_drag` does that once, on release. A
        file write per mouse-move event is 60 writes a second of the same two
        integers.
        """
        if self._drag_from is None or self._window is None:
            return False
        x0, y0, wx, wy = self._drag_from
        try:
            self._window.move(wx + int(gx) - x0, wy + int(gy) - y0)
            return True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: drag move refused — "
                  f"{type(e).__name__}: {e}")
            return False

    def end_drag(self, x: int, y: int, threshold: int | None = None) -> bool:
        """On release: a real move is remembered, a click is passed to `_on_click`.

        Returns whether the release was treated as a drag. `threshold` is small
        on purpose — 4 px absorbs a shaky hand without turning a deliberate
        nudge into a click.
        """
        start, self._press_at = self._press_at, None
        if start is None:
            return False
        limit = DRAG_THRESHOLD if threshold is None else int(threshold)
        dx, dy = int(x) - start[0], int(y) - start[1]
        if max(abs(dx), abs(dy)) < limit:
            return False
        here = self.position
        if here is not None:
            # BOARD 4: "menempel ke tepi". The snap runs on RELEASE, not during
            # the drag: snapping while the pointer moves makes the orb jump out
            # from under the hand, which reads as a stuck window.
            area = _screen_area()
            if area is not None:
                here = snap_to_edge(area, here[0], here[1], OVERLAY_PX)
                try:
                    self._window.move(*here)
                except Exception as e:              # noqa: BLE001
                    print(f"[JARVIS] Orb overlay: could not settle on an edge — "
                          f"{type(e).__name__}: {e}")
            save_position(*here)
        # TRUE EVEN IF THE POSITION COULD NOT BE READ. "Was this a drag" decides
        # whether the release also counts as a click, and that answer must not
        # depend on whether the window manager let us query the window.
        return True

    def handle_click(self, x: int, y: int, button: str = "left") -> bool:
        """Route one click. True if it landed on the ring and was handled.

        Board 4 gives the two buttons two jobs — left opens the tray panel,
        right opens the quick menu — so the button is part of the question. It
        is a STRING rather than a Qt enum so this rule stays testable without a
        display; the canvas translates.

        A right click with no handler returns False and does NOT fall through to
        the left one: the same press opening the panel on a machine with no menu
        is worse than the press doing nothing.
        """
        if not inside_hit_region(x, y, self._mode):
            return False
        cb = self._on_menu if str(button).lower() == "right" else self._on_click
        if cb is None:
            return False
        try:
            cb()
            return True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Orb overlay: {button} click handler failed — "
                  f"{type(e).__name__}: {e}")
            return False

    def menu_point(self) -> tuple[int, int]:
        """Where a quick menu should open: the window's top-left, in screen
        coordinates. The caller positions its own menu; this is the one place
        that knows it should be next to the orb rather than at the cursor."""
        return self.position or (0, 0)
