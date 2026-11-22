"""Board 6 — the voice overlay, with the gesture camera tile inside it.

WHAT THIS IS, AND WHY IT IS NOT THE ORB
    `ui/orb_overlay.py` is the 96 px ring that says "the assistant is here" while
    the user is doing something else. This is the other surface: the moment the
    assistant is actually listening, the whole screen becomes the interface — a
    2 px cyan edge, a camera tile in the corner that shows the hand it is
    reading, the words it just heard, and the answer underneath. The artboard is
    `docs/mockups/build.py: n06()` and every number below is read off it.

    They are two windows because they answer two questions and are on screen at
    different times. Merging them would mean a 96 px window that has to become
    1280 px and take over the desktop — and the orb's own docstring explains why
    its click target must stay small.

WHY THE CAMERA TILE IS DRAWN BY A PAINTER AND NOT BY A WIDGET PER LANDMARK
    The tile is 300×200 and holds a hand skeleton: 21 dots and a palm, redrawn
    while a gesture is happening. Qt can do that with 22 child widgets, and the
    22 children would each have to be positioned, styled, and recreated on every
    mode change. One `paintEvent` draws all of it from a `(x, y, pinch)` tuple,
    which is also the only shape a test can check without a display.

    The hand is drawn from the SAME tuple `core.workspace_gesture.hand_sample`
    publishes, on purpose: if the drawing and the OS pointer disagreed about
    which way is up, the user would see their hand mirrored and the click would
    land somewhere else. `_finger_joints` is the one place that mapping lives.

WHAT THE EDGE GLOW MEANS, AND WHAT IT DOES NOT
    The artboard's footnote is a contract: the glow is there ONLY while the
    overlay is active, so `edge_alpha()` returns 0 when it is hidden — a number
    a test can assert and a screenshot cannot. The glow is cyan, never amber:
    being listened to is the state the user asked for, not a warning.

WHAT IS UNPROVEN HERE, SAID HERE
    * The overlay is frameless and always-on-top, and on Windows a transparent
      frameless window over a maximised app is the classic click-through
      problem. This build does NOT claim click-through: `WA_TransparentForInput`
      is not set, so the overlay takes clicks while it is up, and Esc closes it.
      Whether Windows returns focus to the app underneath afterwards is not
      testable in this sandbox and is stated as unproven in
      `docs/verification.md`, not assumed.
    * The camera is `core.hand_gesture` / `core.workspace_gesture`, which refuse
      to start off Windows (mediapipe is a Windows-only dependency here). On
      this machine the tile shows the idle hand and says "KAMERA NONAKTIF"
      rather than pretending a camera it cannot open.
"""
from __future__ import annotations

from typing import Callable

# The artboard's numbers. The tile and the hand geometry moved to
# `ui/voice_hand` with the 600-line split; the rest stay here because they are
# this file's rules.
from ui.voice_hand import (                     # noqa: E402 — after the docstring
    CAMERA, REFERENCE, Hand, hand_from_sample, hand_point, pose_of, tile_rect,
)

EDGE_PX = 2                 # the cyan border, in artboard pixels
EDGE_OPACITY = 0.45
GLOW_MAX_OPACITY = 0.22     # radial edge gradient, artboard stop at 1.0
GLOW_INNER = 0.68           # the gradient is transparent until 68% of the radius
CAMERA_RADIUS = 12
LABEL_AT = (40, 62)                 # "MENDENGARKAN"
ORB_AT = (640, 300)
ORB_RADIUS = 44
TRANSCRIPT_AT = (640, 394)
ANSWER_AT = (640, 416)
FOOTNOTE_AT = (40, 690)

# Redrawn at 12 fps like the orb: the transcript does not move between tokens
# and the hand does not need 30 fps to look live at this size.
FRAME_MS = 83

# `idle` is not "hidden": hidden is a separate axis, because a hidden overlay
# that thought it was listening would still draw a glow if they were one flag.
STATES = ("idle", "listening", "speaking")


def edge_alpha(active: bool, state: str = "listening") -> float:
    """The edge glow's opacity, 0..`GLOW_MAX_OPACITY`.

    THE FOOTNOTE IS THE SPEC: "Glow tepi hanya saat overlay aktif". So an
    inactive overlay returns 0.0 — not a dimmer glow, none — and a test can hold
    that line while a screenshot cannot. Speaking is slightly brighter than
    listening because the user can then tell, from the edge alone, whether the
    microphone is still the thing being used.
    """
    if not active:
        return 0.0
    if str(state).strip().lower() == "speaking":
        return GLOW_MAX_OPACITY
    if str(state).strip().lower() == "idle":
        return GLOW_MAX_OPACITY * 0.5
    return GLOW_MAX_OPACITY * 0.8


PAUSED_WORD = "GESTUR DIPENGGU"


def status_word(state: str) -> str:
    """The word at the top-left, in the UI's language (Indonesian).

    WHY NOT `core.i18n`
        `i18n` exists for the control panel's labels, and this overlay has three
        words that are part of the artboard itself — the artboard is drawn in
        Indonesian and the footnote says so. One catalogue for the panel and one
        place for the overlay's three words would mean two lookups for one
        screen; keeping them here means `n06()` can be read against this file
        line by line, which is the property the design cut was for.
    """
    return {"listening": "MENDENGARKAN",
            "speaking": "BERBICARA",
            "idle": "SIAGA"}.get(str(state).strip().lower(), "SIAGA")


def footnote() -> str:
    """The artboard's footnote, verbatim. It is the overlay's key help."""
    return ("Glow tepi hanya saat overlay aktif · Esc keluar · "
            "Ctrl+Alt+G menjeda gestur")


def camera_label(available: bool) -> str:
    """What the tile says above the hand.

    "KAMERA" while a camera is feeding it, "KAMERA NONAKTIF" when there is not.
    A tile that looked identical in both cases would be a picture of a feature
    rather than an indicator of one, and on a Linux box — where mediapipe is not
    installed — the second is the truth.
    """
    return "KAMERA" if available else "KAMERA NONAKTIF"


def lines_for(text: str, limit: int) -> list[str]:
    """Split a transcript into at most `limit` lines, wrapping on words.

    WHY IT WRAPS HERE AND NOT IN THE PAINTER
        The painter has a font and a width; this has neither, and the test can
        check this one. A transcript that ran off the edge of the screen was the
        most obvious failure mode of the first sketch, and it is arithmetic.
    """
    words = str(text or "").split()
    if not words:
        return []
    per_line = max(1, int(limit))
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= per_line or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class VoiceOverlay:
    """The window, and everything that can be decided without one.

    The split is the same one `OrbOverlay` makes, for the same reason: Qt is
    imported inside `start()`, so this module is importable on a machine with no
    display and every rule below is testable there.

    `on_close` is called when the user presses Esc. It is a callback rather than
    an internal `hide()` because closing the overlay is what tells the
    assistant to stop listening, and that is a decision the owner of this
    object makes — not a widget.
    """

    def __init__(self, on_close: Callable[[], None] | None = None,
                 state: str = "idle"):
        self._on_close = on_close
        self._state = state if state in STATES else "idle"
        self._active = False
        self._window = None
        self._canvas = None
        self._timer = None
        self._error = ""
        self._hand = Hand()
        self._transcript = ""
        self._answer = ""
        self._camera_available = False
        self._gestures_paused = False

    # ── what is true ─────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def error(self) -> str:
        return self._error

    @property
    def state(self) -> str:
        return self._state

    @property
    def active(self) -> bool:
        return self._active

    @property
    def hand(self) -> Hand:
        return self._hand

    @property
    def transcript(self) -> str:
        return self._transcript

    @property
    def answer(self) -> str:
        return self._answer

    @property
    def gestures_paused(self) -> bool:
        return self._gestures_paused

    def glow(self) -> float:
        """The number the painter uses for the edge. Public so a test reads the
        same quantity the frame does."""
        return edge_alpha(self._active, self._state)

    # ── state, all cheap and idempotent ──────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Idle / listening / speaking. An unknown word is `idle`, not a crash.

        The audio thread and the model both call this, sometimes out of order;
        a state machine that rejected an unexpected word would raise inside a
        paint callback. Falling back keeps the overlay drawing.
        """
        word = str(state or "").strip().lower()
        self._state = word if word in STATES else "idle"
        self._refresh()

    def set_hand(self, sample) -> None:
        """The newest camera sample, or None. Never blocks, never raises."""
        self._hand = hand_from_sample(sample)
        self._refresh()

    def set_transcript(self, text: str) -> None:
        self._transcript = str(text or "")
        self._refresh()

    def set_answer(self, text: str) -> None:
        self._answer = str(text or "")
        self._refresh()

    def set_camera_available(self, available: bool) -> None:
        self._camera_available = bool(available)
        self._refresh()

    def set_gestures_paused(self, paused: bool) -> None:
        """Ctrl+Alt+G. Pausing gestures does NOT close the overlay: the user is
        still talking to it, and taking the transcript away because they stopped
        waving would be answering a question they did not ask."""
        self._gestures_paused = bool(paused)
        if self._gestures_paused:
            self._hand = Hand()
        self._refresh()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self, active: bool = True) -> bool:
        """Build and show the overlay. Returns `available`; never raises.

        Same contract as the orb: a surface that fails to build must not turn
        the assistant's state update into an exception on the caller's thread.
        """
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QWidget

            window = QWidget()
            window.setWindowFlags(self.window_flags(Qt))
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            window.setWindowTitle(_assistant_name())
            window.setGeometry(0, 0, *REFERENCE)

            canvas = _build_canvas(window, self)
            canvas.setGeometry(0, 0, *REFERENCE)

            self._window, self._canvas = window, canvas
            self._active = bool(active)
            window.show()
            self._start_timer()
            return True
        except Exception as exc:                    # noqa: BLE001
            self._window = None
            self._canvas = None
            self._error = f"{type(exc).__name__}: {exc}"
            return False

    def stop(self) -> None:
        self._stop_timer()
        window, self._window = self._window, None
        self._canvas = None
        self._active = False
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] Voice overlay: could not remove the window — "
                  f"{type(exc).__name__}: {exc}")

    def show(self) -> None:
        self._apply_visibility(True)

    def hide(self) -> None:
        self._apply_visibility(False)

    def toggle(self) -> bool:
        """Ctrl+Space's counterpart for the overlay itself. Returns the state."""
        self._apply_visibility(not self._active)
        return self._active

    def _apply_visibility(self, visible: bool) -> None:
        self._active = bool(visible)
        window = self._window
        if window is None:
            return
        try:
            if visible:
                window.show()
                self._start_timer()
                window.raise_() if hasattr(window, "raise_") else None
            else:
                window.hide()
                self._stop_timer()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] Voice overlay: could not change visibility — "
                  f"{type(exc).__name__}: {exc}")
        self._refresh()

    @staticmethod
    def window_flags(Qt) -> int:
        """Frameless, off the taskbar, always on top — the same trio as the orb.

        `WindowTransparentForInput` is NOT here: the footnote promises Esc
        closes the overlay, and a click-through window cannot receive the key
        that closes it. Windows click-through stays documented as unproven
        rather than attempted — a promise kept beats a promise bold.
        """
        flags = Qt.WindowType
        return (getattr(flags, "FramelessWindowHint")
                | getattr(flags, "Tool")
                | getattr(flags, "WindowStaysOnTopHint"))

    # ── input ────────────────────────────────────────────────────────────────

    def handle_escape(self) -> bool:
        """Esc. Returns True when something was closed.

        Separate from `keyPressEvent` so the rule — Esc on an inactive overlay
        is not ours to consume — is testable without a display.
        """
        if not self._active:
            return False
        self._apply_visibility(False)
        callback = self._on_close
        if callback is not None:
            try:
                callback()
            except Exception as exc:                # noqa: BLE001
                print(f"[JARVIS] Voice overlay: close handler failed — "
                      f"{type(exc).__name__}: {exc}")
        return True

    def handle_toggle_gestures(self) -> bool:
        """Ctrl+Alt+G. Returns the new paused flag.

        The same chord `core.hand_gesture.HandController` polls as its emergency
        stop, so there are two listeners for one key: this one redraws the tile,
        that one stops driving the OS pointer. They cannot disagree, because
        this method is called BY the owner when the controller reports a change
        rather than polling the keyboard a second time.
        """
        self.set_gestures_paused(not self._gestures_paused)
        return self._gestures_paused

    # ── timer ────────────────────────────────────────────────────────────────

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        try:
            from PyQt6.QtCore import QTimer

            timer = QTimer()
            timer.setInterval(FRAME_MS)
            timer.timeout.connect(self._refresh)
            timer.start()
            self._timer = timer
        except Exception as exc:                    # noqa: BLE001
            # A static overlay still works; the timer only moves the hand.
            print(f"[JARVIS] Voice overlay: no animation timer — "
                  f"{type(exc).__name__}: {exc}")

    def _stop_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] Voice overlay: timer would not stop — "
                  f"{type(exc).__name__}: {exc}")

    def _refresh(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        try:
            canvas.update()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] Voice overlay: repaint dropped — "
                  f"{type(exc).__name__}: {exc}")


def _assistant_name() -> str:
    """The name the user gave the assistant, for the window title.

    Reused from `ui/orb_overlay.py` rather than written again: the rule there is
    the same one — a title is a value the user typed, `i18n.label()` has no key
    for it, and a constructor that raised because a config file was unreadable
    would turn a cosmetic surface into a crash. Imported lazily so this module
    keeps importing with no Qt on the machine.
    """
    try:
        from ui.orb_overlay import _assistant_name as name

        return name()
    except Exception:                               # noqa: BLE001
        return "JARVIS"


def _build_canvas(parent, owner: "VoiceOverlay"):
    """The widget that paints the frame.

    Built in a function, never a class at module scope: a `QWidget` subclass
    imports Qt when the class is created, and this module is imported by tests
    with no display.
    """
    from PyQt6.QtWidgets import QWidget

    class _VoiceCanvas(QWidget):
        """Owns no state: asks the overlay what the frame looks like."""

        def paintEvent(self, _event):               # noqa: N802 — Qt's name
            try:
                from PyQt6.QtGui import QPainter

                painter = QPainter(self)
                try:
                    paint_frame(painter, REFERENCE, owner)
                finally:
                    painter.end()
            except Exception as exc:                # noqa: BLE001
                print(f"[JARVIS] Voice overlay: could not paint — "
                      f"{type(exc).__name__}: {exc}")

        def keyPressEvent(self, event):             # noqa: N802 — Qt's name
            try:
                if event.key() == _Qt_Escape():
                    if owner.handle_escape():
                        event.accept()
                        return
            except Exception as exc:                # noqa: BLE001
                print(f"[JARVIS] Voice overlay: key not handled — "
                      f"{type(exc).__name__}: {exc}")
            super().keyPressEvent(event)

    return _VoiceCanvas(parent)


def _Qt_Escape():                                   # noqa: N802 — mirrors Qt's name
    """`Qt.Key.Key_Escape`, or None when Qt is not importable.

    Kept in a function because the canvas is built only when Qt exists; a
    module-level constant would import Qt on every test collection.
    """
    try:
        from PyQt6.QtCore import Qt

        return Qt.Key.Key_Escape
    except Exception:                               # noqa: BLE001
        return None


# ── the frame ───────────────────────────────────────────────────────────────

def paint_frame(painter, size, overlay) -> None:
    """""Draw board 6. The Qt calls live in `ui/voice_paint`; this is the door.

    Re-exported rather than imported at every call site so that a test which
    wants to prove "the canvas really calls a painter" has one name to patch,
    and so that the module split is invisible to `_build_canvas`.
    """
    from ui.voice_paint import paint_frame as _paint

    _paint(painter, size, overlay)


# ── the frame as data ───────────────────────────────────────────────────────

def frame_words(overlay: "VoiceOverlay") -> dict:
    """Everything the frame says, as strings a test can read.

    `paint_frame` needs Qt and a display, so a headless test can only prove it
    did not raise. The TEXT is what the user actually reads, so it lives here
    where it can be asserted, and the painter keeps the geometry.
    """
    return {
        "status": status_word(overlay.state),
        "transcript": lines_for(overlay.transcript, 74)[:3],
        "answer": lines_for(overlay.answer, 96)[:2],
        "camera": camera_label(overlay._camera_available),
        "footnote": footnote(),
        "paused": PAUSED_WORD if overlay.gestures_paused else "",
        "glow": overlay.glow(),
    }


__all__ = [
    "ANSWER_AT", "CAMERA", "EDGE_OPACITY", "EDGE_PX", "FOOTNOTE_AT", "FRAME_MS",
    "GLOW_INNER", "GLOW_MAX_OPACITY", "Hand", "LABEL_AT", "ORB_AT", "ORB_RADIUS",
    "REFERENCE", "STATES", "TRANSCRIPT_AT", "VoiceOverlay", "camera_label",
    "edge_alpha", "footnote", "frame_words", "hand_from_sample", "hand_point",
    "lines_for", "paint_frame", "pose_of", "status_word", "tile_rect",
    "Hand", "CAMERA", "PAUSED_WORD",
]
