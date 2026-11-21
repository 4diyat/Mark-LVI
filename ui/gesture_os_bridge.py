"""The one place the hand-tracking loop is allowed to reach the desktop.

WHY A BRIDGE AND NOT A FEW LINES IN THE TRACKING LOOP
    `ui/hand_gesture.py` owns the workspace gestures and is 566 lines about
    manipulating widgets inside this program. Adding "and also drive the OS"
    there would put a rule with a safety argument next to a rule about dragging
    a card, and the safety argument would be the one that got lost.

    So the loop asks this object one question per frame, and this object is the
    only thing in the program that holds a `HandPointer` and an `OsPointer`
    together. Everything it decides is decided by `core/gesture_os.py`, which
    has no Qt in it and is tested without a display.

THE FREEZE, WHICH IS THE POINT
    Rule 2 says this program's own surfaces are never hand-operated. This
    object reads that from the window every frame rather than remembering it:
    focus can change between two frames, and a cached flag would be one frame
    of a gesture clicking the confirmation banner.

    Two things can make the pointer frozen, and both are checked here:
      * the JARVIS window is the active window (workspace gestures apply);
      * a confirmation banner or a modal dialog of ours is visible.
    A third — the mode being off — is the `Context.os_mode` flag.

WHAT IT NEVER DOES
    It never opens the camera. The camera belongs to `WorkspaceHandController`,
    which already leases it; this object is fed samples from there.
"""
from __future__ import annotations

from core import gesture_os, logbook


class GestureOsBridge:
    """Turn tracked hand samples into OS input, for one window."""

    def __init__(self, window):
        self._window = window
        self._pointer = gesture_os.HandPointer()
        self._out = None                 # built lazily: pyautogui is 200ms
        self._enabled = False
        self._last_reason = ""

    # ── state ─────────────────────────────────────────────────────────────

    @property
    def holding_button(self) -> bool:
        return self._pointer.holding_button

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> bool:
        """Switch OS control on or off. Turning it off lets go of the button."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self.release()
        return self._enabled

    # ── the frame ─────────────────────────────────────────────────────────

    def feed(self, samples, now: float) -> bool:
        """One frame of tracking. Returns True when the desktop was touched.

        `samples` is what `WorkspaceHandController.sample()` already returns:
        tuples of (x, y, pinch, scroll) per hand, plus a fifth `claw` field the
        workspace uses. Two hands are ignored here on purpose — resize and
        rotate are workspace gestures, and an OS gesture that needs both hands
        is one the camera cannot tell apart from somebody gesturing while
        talking.
        """
        sample = None
        if samples and len(samples) == 1:
            raw = samples[0]
            try:
                sample = gesture_os.Sample(
                    x=float(raw[0]), y=float(raw[1]),
                    pinch=bool(raw[2]), scroll=bool(raw[3]) if len(raw) > 3 else False)
            except (TypeError, ValueError, IndexError):
                sample = None

        ctx = gesture_os.Context(
            os_mode=self._enabled,
            own_window_focused=self._own_focus(),
            confirmation_open=self._confirmation_open(),
            modal_open=self._modal_open(),
            now=now,
        )
        intent = self._pointer.step(sample, ctx)
        if intent.is_empty:
            # Remembered, not logged per frame: "the hand was lost" at 30 fps
            # is 30 lines a second of a sentence the user already knows.
            self._last_reason = intent.reason
            return False
        if self._out is None:
            from core import gesture_os_pointer
            self._out = gesture_os_pointer.OsPointer()
        return bool(self._out.apply(intent))

    def release(self) -> None:
        """Let go. Called on stop, on mode off, and on close."""
        from core import gesture_os_pointer
        if self._pointer.holding_button:
            self._pointer.release_now()
            gesture_os_pointer.release()
        else:
            self._pointer.reset()

    # ── what the window says ──────────────────────────────────────────────

    def _own_focus(self) -> bool:
        try:
            return bool(self._window.isActiveWindow())
        except Exception as e:              # noqa: BLE001 — a closing window
            logbook.get(__name__).debug("could not read focus: %s", e)
            return True                      # assume ours: the safe way is off

    def _confirmation_open(self) -> bool:
        banner = getattr(self._window, "_confirm_overlay", None)
        try:
            return bool(banner is not None and banner.isVisible())
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not read the banner: %s", e)
            return True

    def _modal_open(self) -> bool:
        try:
            from PyQt6.QtWidgets import QApplication
            return QApplication.activeModalWidget() is not None
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not read the modal state: %s", e)
            return True

    @property
    def last_reason(self) -> str:
        """Why the last frame did nothing — for the status line."""
        return self._last_reason


__all__ = ["GestureOsBridge"]
