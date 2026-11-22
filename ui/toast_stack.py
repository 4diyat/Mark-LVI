"""The transparent window that stacks board 2's toast cards.

WHY THIS EXISTS AT ALL, AND WHAT IT REPLACES
    `ui/toast_queue.py` has kept the toast arithmetic since before there was a
    card to draw: how many, in what order, which one the cap replaced. Nothing
    in the build ever rendered it. The only thing a user saw when something
    finished was `core/notify.py`'s native OS notification — a different widget
    on a different surface, which cannot show the sentence board 2 puts under
    the stack or the "2 dari 3 terpakai" the panel promises.

    So this window is the missing half: it polls the queue on one timer, draws
    each card through `ui/toast_card.paint_card`, and routes a click to the card
    under it.

THE THREE PROMISES, AND WHERE EACH ONE LIVES
    "Hilang otomatis 8 detik"   — `Toast.ttl`, swept by `tick()` on one timer.
    "tidak pernah meminta fokus" — `WindowDoesNotAcceptFocus` plus
                                   `WA_ShowWithoutActivating`. Both, because the
                                   flag stops the window manager and the
                                   attribute stops Qt asking on show.
    "maksimal 3 saran per hari"  — not this module's rule; the budget is
                                   `core/suggestion_quota`. This window only
                                   shows the count when asked.

WHY IT IS SHOWN AND HIDDEN RATHER THAN KEPT ALIVE
    An always-on transparent 340x324 window on top of everything is a window the
    compositor has to blend every frame even when it is empty. It is hidden the
    moment the last card expires, and shown again by the next push.

WHAT IT DOES NOT DO
    It never asks for focus, never blocks, and never raises from a paint or a
    click. A toast is decoration on top of an action that already succeeded; a
    failed repaint costs a frame and nothing else.
"""
from __future__ import annotations

from typing import Callable

from ui import toast_card
from ui.toast_queue import DEFAULT_TTL, ToastQueue

# Where the window's flags are named, and pinned by a test — the same reason
# `ui/orb_overlay._FLAGS` exists: a missing name is a TypeError on the user's
# desktop and nowhere else.
_FLAGS = ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint",
          "WindowDoesNotAcceptFocus")

# The corner gap, from `n02()`: the stack's last card ends ~24 px above the
# taskbar, the same margin the orb uses.
MARGIN = 24

# 12 fps, like the orb: the stack only changes when a card arrives or expires,
# and the sweep is a list comprehension. A 60 fps timer would be 60 wake-ups a
# second to draw the same four rounded rectangles.
FRAME_MS = 83


def WindowSize() -> object:                     # noqa: N802 — reads like a type
    """The window's size, as a rect-shaped object.

    A function rather than a constant because `toast_card.window_size()` is the
    one place the arithmetic lives, and a second copy here is the copy that
    drifts.
    """
    w, h = toast_card.window_size()
    return _Size(w, h)


class _Size:
    """Minimal rect: what `corner_anchor` asks for, and nothing else."""

    def __init__(self, width: int, height: int):
        self._w, self._h = int(width), int(height)

    def width(self):
        return self._w

    def height(self):
        return self._h

    def x(self):
        return 0

    def y(self):
        return 0


def stack_anchor(area, width: int, height: int,
                 margin: int = MARGIN) -> tuple[int, int]:
    """Bottom-right of `area`, clear of the taskbar — the orb's own rule.

    Delegates to `ui.orb_place.corner_anchor` rather than re-deriving it: two
    surfaces anchored by two copies of the same arithmetic is how one of them
    ends up on the taskbar.
    """
    from ui.orb_place import corner_anchor

    return corner_anchor(area, width, margin)


def window_flags(Qt) -> int:
    """Frameless, off the taskbar, on top, and NEVER focused."""
    flags = Qt.WindowType
    out = 0
    for name in _FLAGS:
        out |= getattr(flags, name)
    return out


def _screen_area():
    from ui.orb_place import screen_area

    return screen_area()


# What `hits()` reports for a point that is on a card. Three answers, because
# the three need different reactions — the same argument `presence_mode` makes
# for its own "show / hold / drop".
CARD_BODY = -1        # dismiss the card
NO_BUTTON = -2        # inside the button row, on no button: do nothing


def hits(x: float, y: float, toasts) -> tuple[int, int] | None:
    """(card index, button index or -1) for a window coordinate, or None.

    THE SAME ARITHMETIC `paint_card` DRAWS WITH, deliberately: a hit test that
    re-derives the button widths is a second copy of `12 + len * 6.4`, and the
    copy drifts until a click lands one button to the left.

    Cards are laid out from the BOTTOM up? No — board 2 stacks them downward
    from the top of the window, so the first card is at y=0 and each next one
    starts at `offset + height + GAP`.

    Resolved against the CURRENT stack every call, so a click after a dismissal
    hits the card that moved up rather than the one that left.
    """
    for index, offset in enumerate(toast_card.stack_offsets(toasts)):
        toast = toasts[index]
        if not (offset <= y < offset + toast.height):
            continue
        if not (0 <= x < toast_card.CARD_W):
            return None
        # inside the card but right of the text column counts as the body —
        # clicking anywhere on a card dismisses it, which is what the artboard's
        # cards imply and what every desktop toast does
        # THE BUTTON ROW IS ITS OWN BAND. A click inside it that misses every
        # button lands in the 10 px gap between them, and treating that as "the
        # card's body" would DISMISS the card — a click that misses a button by
        # two pixels would throw away the action the user was reaching for. So
        # the row reports `NO_BUTTON` and `click()` does nothing with it.
        top = offset + toast_card.BUTTON_DY
        if toast.actions and top <= y < top + toast_card.BUTTON_H:
            ax = toast_card.PAD
            for button, label in enumerate(toast.actions):
                width = toast_card.button_width(label)
                if ax <= x < ax + width:
                    return (index, button)
                ax += width + toast_card.BUTTON_GAP
            return (index, NO_BUTTON)
        return (index, CARD_BODY)
    return None


class ToastStack:
    """The window. One timer, one canvas, no focus.

    `on_action(label, toast)` is called when a card's button is clicked.
    `on_empty` is called when the last card goes, so a caller can tell the
    difference between "hidden" and "never shown".
    """

    def __init__(self, on_action: Callable | None = None,
                 on_empty: Callable[[], None] | None = None,
                 ttl: float = DEFAULT_TTL) -> None:
        self._on_action = on_action
        self._on_empty = on_empty
        self._queue = ToastQueue(ttl=ttl)
        self._window = None
        self._canvas = None
        self._timer = None
        self._placed = False
        self._error = ""

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def error(self) -> str:
        return self._error

    @property
    def queue(self) -> ToastQueue:
        return self._queue

    @property
    def visible(self) -> bool:
        if self._window is None:
            return False
        try:
            return bool(self._window.isVisible())
        except Exception:                           # noqa: BLE001
            return False

    def overflow_text(self) -> str:
        return self._queue.overflow_label()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Build and place the window, hidden. Never raises."""
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QWidget

            window = QWidget()
            window.setWindowFlags(window_flags(Qt))
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # THE SECOND HALF OF "never asks for focus". The flag is the window
            # manager's instruction; this is Qt's, and a window with only one of
            # them still activates on the first show.
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setFixedSize(*toast_card.window_size())

            canvas = _build_canvas(window, self)
            canvas.setGeometry(0, 0, *toast_card.window_size())

            self._window, self._canvas = window, canvas
            self._place()
            self._start_timer()
            return True
        except Exception as e:                      # noqa: BLE001
            self._window = None
            self._canvas = None
            self._error = f"{type(e).__name__}: {e}"
            return False

    def stop(self) -> None:
        self._stop_timer()
        window, self._window = self._window, None
        self._canvas = None
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: could not remove the window — "
                  f"{type(e).__name__}: {e}")

    def _place(self) -> None:
        if self._placed or self._window is None:
            return
        try:
            area = _screen_area()
            if area is None:
                return
            size = toast_card.window_size()
            x, y = stack_anchor(area, size[0], size[1])
            self._window.move(x, y)
            self._placed = True
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: could not choose a corner — "
                  f"{type(e).__name__}: {e}")

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        try:
            from PyQt6.QtCore import QTimer

            timer = QTimer()
            timer.setInterval(FRAME_MS)
            timer.timeout.connect(self.tick)
            timer.start()
            self._timer = timer
        except Exception as e:                      # noqa: BLE001
            # A stack with no timer never expires anything; it is still better
            # than no stack, so this is a warning and not a failure.
            print(f"[JARVIS] Toast stack: no expiry timer — "
                  f"{type(e).__name__}: {e}")

    def _stop_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: timer would not stop — "
                  f"{type(e).__name__}: {e}")

    # ── pushing and sweeping ─────────────────────────────────────────────────

    def push(self, text: str, kind: str = "info", body: str = "",
             actions=(), ttl: float | None = None) -> None:
        """Add a card and show the window. A refused toast shows nothing."""
        toast = self._queue.push(text, kind=kind, body=body, actions=actions)
        if toast is None:
            return
        if ttl is not None:
            toast.ttl = max(0.0, float(ttl))
        self._show()
        self._repaint()

    def tick(self) -> None:
        """Sweep expired cards, then hide if the stack is empty.

        Called by the timer. Public because a test has no timer: calling the
        sweep directly is the same code path the timer runs.
        """
        before = len(self._queue)
        alive = self._queue.current()               # expires in place
        if alive and len(alive) != before:
            self._repaint()
        if not alive and self.visible:
            self._hide()
            if self._on_empty is not None:
                try:
                    self._on_empty()
                except Exception as e:              # noqa: BLE001
                    print(f"[JARVIS] Toast stack: on_empty failed — "
                          f"{type(e).__name__}: {e}")

    def clear(self) -> None:
        """Drop every card and hide. For a mode change or a privacy erase."""
        self._queue.clear()
        self._hide()

    # ── clicks ───────────────────────────────────────────────────────────────

    def click(self, x: int, y: int) -> bool:
        """Route one click in window coordinates. True if the stack used it.

        A button runs `on_action` and LEAVES THE CARD: the button is the more
        specific target, and dismissing on the same click takes the card away
        before the action runs. Anywhere else on the card dismisses it.
        """
        toasts = self._queue.current()
        hit = hits(x, y, toasts)
        if hit is None:
            return False
        index, button = hit
        toast = toasts[index]
        if button == NO_BUTTON:
            # Consumed — the press was ours — but nothing happens. Falling
            # through to the dismissal is how a near miss becomes a lost card.
            return True
        if button >= 0:
            label = toast.actions[button]
            cb = self._on_action
            if cb is not None:
                try:
                    cb(label, toast)
                except Exception as e:              # noqa: BLE001
                    print(f"[JARVIS] Toast stack: action failed — "
                          f"{type(e).__name__}: {e}")
            return True
        self._queue.dismiss(toast)
        self._repaint()
        return True

    # ── visibility ───────────────────────────────────────────────────────────

    def _show(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.show()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: could not show — "
                  f"{type(e).__name__}: {e}")

    def _hide(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.hide()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: could not hide — "
                  f"{type(e).__name__}: {e}")

    def _repaint(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.update()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Toast stack: repaint dropped — "
                  f"{type(e).__name__}: {e}")


def _painter_for(widget, event=None):
    """A QPainter on `widget`, or the one handed in as `event.painter`.

    Same seam as `ui.orb_canvas`: the suite's QPainter stub is a no-op, so a
    test that wants to see what was drawn has to be able to hand one in.
    """
    supplied = getattr(event, "painter", None) if event is not None else None
    if supplied is not None:
        return supplied
    from PyQt6.QtGui import QPainter

    return QPainter(widget)


def paint_stack(painter, owner) -> None:
    """Draw every live card, top to bottom, then the overflow label.

    THE OVERFLOW LINE IS UNDER THE STACK, right-aligned to the card's edge —
    `toast_queue()` in build.py puts it at `(x + w, y + off - 2)` with
    `anchor="end"`.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont

    toasts = owner.queue.current()
    offsets = toast_card.stack_offsets(toasts)
    for toast, offset in zip(toasts, offsets):
        toast_card.paint_card(painter, 0, offset, toast)

    label = owner.overflow_text()
    if not label:
        return
    bottom = offsets[-1] + toasts[-1].height + toast_card.GAP
    font = QFont()
    font.setPixelSize(10)
    painter.setFont(font)
    painter.setPen(QColor(toast_card.MUTED))
    painter.drawText(
        QRectF(0, bottom, toast_card.CARD_W, 16),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        label)


def _build_canvas(parent, owner: "ToastStack"):
    """Build the widget that paints the stack.

    A class inside a function for the reason `ui/orb_canvas` documents: a
    `QWidget` subclass needs Qt at class-creation time, and this module is
    imported on machines with no display.
    """
    from PyQt6.QtWidgets import QWidget

    class _ToastCanvas(QWidget):
        def paintEvent(self, event=None):           # noqa: N802 — Qt's name
            try:
                painter = _painter_for(self, event)
                try:
                    paint_stack(painter, owner)
                finally:
                    painter.end()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Toast stack: could not paint — "
                      f"{type(e).__name__}: {e}")

        def mousePressEvent(self, event):           # noqa: N802 — Qt's name
            """A press routes straight to `click`: a toast has no drag, and
            waiting for the release would let a card expire between the two."""
            try:
                pos = event.position()
                if owner.click(int(pos.x()), int(pos.y())):
                    event.accept()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Toast stack: press not handled — "
                      f"{type(e).__name__}: {e}")

    return _ToastCanvas(parent)


__all__ = ["MARGIN", "ToastStack", "hits", "stack_anchor", "window_flags"]
