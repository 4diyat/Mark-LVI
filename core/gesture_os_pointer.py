"""Sending the decided intent to the operating system, and nothing else.

WHY THIS IS SEPARATE FROM `core/gesture_os.py`
    The decision can be tested anywhere; the sending can only be tested where
    there is a desktop. Keeping them apart means the rules have tests that run
    on every CI runner, and this file has almost nothing in it that could be
    wrong — it names three pyautogui calls and fails loudly if a fourth appears.

WHY PYAUTOGUI IS INJECTED
    `core/hand_gesture.py` already does `import pyautogui` inside the worker
    thread so that importing the module costs nothing on a machine without it.
    The same applies here, and there is a second reason: a test can pass a fake
    and assert exactly which calls were made, which is the only way to check
    "never typed a key" from a machine that has no keyboard to type on.

WHAT THE DEPENDENCY IS ALLOWED TO BE
    Three calls: `moveTo`, `mouseDown`, `mouseUp`. Plus `scroll` clamped to an
    integer. If a future change adds `press`, `keyDown`, `write` or `hotkey`
    here, that is rule 1 being broken in the one place where breaking it is
    invisible — so a test walks this file's AST for exactly those names.
"""
from __future__ import annotations

from core import gesture_os, logbook

# The only pyautogui attributes this module may ever touch. Anything else is a
# capability that was added without the conversation that rule 1 requires.
_ALLOWED_CALLS = frozenset({"moveTo", "mouseDown", "mouseUp", "scroll"})


class OsPointer:
    """One `HandPointer`'s intents, delivered to the desktop.

    `mouse` is whatever object offers those four calls; the real one is
    pyautogui, and a test passes a recorder.
    """

    def __init__(self, mouse=None):
        self._mouse = mouse
        self._errors = 0

    # ── the dependency, loaded once and only when needed ──────────────────

    def _driver(self):
        if self._mouse is not None:
            return self._mouse
        try:
            import pyautogui
        except ImportError as e:
            raise RuntimeError(
                "pyautogui is not installed, so hand gestures cannot reach the "
                "desktop") from e
        self._mouse = pyautogui
        return self._mouse

    # ── the one entry point ───────────────────────────────────────────────

    def apply(self, intent: gesture_os.Intent, screen: tuple[int, int] | None = None):
        """Perform `intent` — or nothing, when it says nothing.

        Returns True when the desktop was touched. Never raises: a gesture
        pipeline that throws during a frame takes the camera thread with it,
        and the user's only symptom would be that hand control stopped.
        """
        if intent.is_empty:
            return False
        try:
            mouse = self._driver()
            if intent.action == gesture_os.POINTER:
                width, height = screen or self._size(mouse)
                x, y = gesture_os.coordinate(intent.x, intent.y, width, height)
                mouse.moveTo(x, y)
                return True
            if intent.action == gesture_os.CLICK:
                if intent.press:
                    mouse.mouseDown()
                elif intent.release:
                    mouse.mouseUp()
                return True
            if intent.action == gesture_os.SCROLL:
                mouse.scroll(int(intent.amount))
                return True
        except Exception as e:                    # noqa: BLE001 — see docstring
            self._errors += 1
            # Logged once per failure but never re-raised: the caller is a
            # camera loop, and the user needs the loop to keep running so the
            # gesture that releases a stuck button still arrives.
            logbook.get(__name__).warning("could not deliver %s: %s",
                                          intent.action, e)
        return False

    @staticmethod
    def _size(mouse) -> tuple[int, int]:
        try:
            return mouse.size()
        except Exception as e:                    # noqa: BLE001
            logbook.get(__name__).debug("no screen size from the driver: %s", e)
            return (1920, 1080)

    @property
    def errors(self) -> int:
        return self._errors


def release(mouse=None) -> bool:
    """Let go of the button, unconditionally.

    The escape hatch used when tracking stops, the mode is switched off, the
    window closes, or the frame loop dies: it must not depend on a hand being
    visible, on a decision being correct, or on the state machine agreeing.
    """
    try:
        (mouse or _real()).mouseUp()
        return True
    except Exception as e:                        # noqa: BLE001
        logbook.get(__name__).warning("could not release the mouse button: %s", e)
        return False


def _real():
    import pyautogui
    return pyautogui


__all__ = ["OsPointer", "release"]
