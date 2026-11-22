"""The bare hand on the desktop: samples in, pointer out, and one kill switch.

WHY THIS EXISTS NOW AND NOT BEFORE
    `core/gesture_os.py` decided what a hand may do to the operating system, and
    `core/gesture_os_pointer.py` knew how to deliver it — and neither had a
    single caller outside its own tests. Every promise they make (`HandPointer`
    releases a held button on any stop, `OsPointer` may only call four
    pyautogui names) was true of code that never ran. The camera tile on board 6
    showed the hand; the hand controlled nothing.

    This module is the missing third piece and nothing more: it takes the
    samples the camera worker already publishes, asks the policy once per frame,
    and hands the answer to the pointer. All the judgement stays where it was.

WHY IT IS A POLL AND NOT A CALLBACK FROM THE CAMERA THREAD
    `WorkspaceHandController` publishes from its own thread. Delivering an
    intent means calling into pyautogui, and pyautogui on Windows drives the
    same input queue the user's own mouse is using — doing that from a camera
    loop while the Qt thread may be tearing the session down is how a stuck
    button happens. The overlay's 12 fps timer calls `pump()`, and that timer
    runs on the Qt thread by construction.

WHY THE CONTEXT IS ASSEMBLED HERE
    `HandPointer.step()` is a pure function of (sample, context), and the
    context holds the three facts it must not guess: whether OS control is on,
    whether this program's own window has focus, and whether a confirmation is
    on screen. Those live in three places (config, Qt, `core.confirm`), so
    somebody has to read them — and it must be in one place, on the same thread
    that reads the samples, or the pointer will act on a stale idea of whether a
    banner is up.

THE ORDER OF THE CHECKS IS THE SAFETY
    1. disabled  → never build a pipeline at all;
    2. frozen    → release the button and stop (`_stop` does the release);
    3. no hand   → same;
    4. otherwise → step, deliver.
    A button held when the user switches the mode off is released by (1), which
    is why `stop()` is called from the setter rather than left to the next
    frame: there may not be a next frame.

WHAT IT CANNOT DO HERE, SAID IN THE MODULE THAT CANNOT DO IT
    pyautogui is not installed on this Linux runner, the camera is Windows-only,
    and there is no `libxkbcommon` for a Qt application. So the delivery path is
    exercised with a recording mouse and the policy with a real `HandPointer`.
    Nothing below claims to have moved a real cursor.
"""
from __future__ import annotations

from core import gesture_os, logbook

LOG = "gesture_bridge"


class GestureBridge:
    """One camera's samples, one policy, one pointer, one switch.

    `mouse` is injected for the tests, exactly as `OsPointer` takes it: the real
    one is pyautogui and this module never names a fourth method.
    """

    def __init__(self, mouse=None, screen=None):
        self._mouse = mouse
        self._screen = screen
        self._pointer = None
        self._hand = None
        self._os_pointer = None
        self._enabled = False
        self._last_reason = ""
        self._delivered = 0

    # ── what is true ─────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def holding_button(self) -> bool:
        """A held button is the one state a user cannot diagnose by waving."""
        return bool(self._hand is not None and self._hand.holding_button)

    @property
    def last_reason(self) -> str:
        """Why the last frame did nothing. Empty when it did something."""
        return self._last_reason

    @property
    def delivered(self) -> int:
        """How many frames reached the desktop. Zero is the honest answer on a
        machine where nothing could be delivered."""
        return self._delivered

    @property
    def dropped(self) -> int:
        return int(getattr(self._hand, "dropped_samples", 0) or 0)

    # ── the switch ───────────────────────────────────────────────────────────

    def enable(self, mouse=None) -> bool:
        """Turn OS control on. Returns whether the pipeline exists.

        A pipeline is built HERE and not in `__init__` because the disabled path
        must not import pyautogui, open a device, or hold a reference to
        anything that could click. Off means off.

        The driver is resolved now rather than on the first frame so that a
        machine without pyautogui fails at the moment the user asks for the
        feature — where the answer can be shown — instead of mid-gesture.
        """
        if mouse is not None:
            self._mouse = mouse
        if self._hand is not None:
            self._enabled = True
            return True
        try:
            from core.gesture_os_pointer import OsPointer

            pointer = OsPointer(self._mouse)
            pointer._driver()                    # fail here, not mid-gesture
        except Exception as exc:                 # noqa: BLE001
            logbook.get(LOG).warning("gesture OS control refused: %s", exc)
            self._last_reason = str(exc)
            self._enabled = False
            return False
        self._hand = gesture_os.HandPointer()
        self._os_pointer = pointer
        self._enabled = True
        self._last_reason = ""
        return True

    def disable(self) -> None:
        """Turn it off and let go of anything being held.

        THE RELEASE IS NOT LEFT TO THE NEXT FRAME. When the user switches this
        off there may not be one — the session can end on the same click, and a
        button left down turns the whole desktop into a drag-selection that
        waving cannot fix. `release_now()` is asked for the intent; the pointer
        delivers it here.
        """
        if self._hand is not None:
            intent = self._hand.release_now()
            if not intent.is_empty and self._os_pointer is not None:
                self._os_pointer.apply(intent, self._screen)
        self._enabled = False
        self._hand = None
        self._os_pointer = None
        self._last_reason = ""
        self._delivered = 0

    # ── the frame ────────────────────────────────────────────────────────────

    def pump(self, sample, ctx=None) -> gesture_os.Intent:
        """One frame: policy in, desktop out. Never raises.

        `sample` is `WorkspaceHandController.sample()`'s first hand —
        `(x, y, pinch, scroll, ratio, claw)` — or `None`/`()` for "no hand".
        The two extra fields are kept because `core.gesture_os.Sample` has a
        `claw` and dropping it here would make the policy's own vocabulary
        narrower than the camera's.

        A failure to deliver is counted by `OsPointer` and does not stop the
        loop: the gesture that RELEASES a stuck button has to arrive even if the
        one before it failed.
        """
        if not self._enabled or self._hand is None or self._os_pointer is None:
            self._last_reason = "OS control is off"
            return gesture_os.Intent()
        try:
            intent = self._hand.step(_to_sample(sample), ctx or gesture_os.Context())
        except Exception as exc:                 # noqa: BLE001
            logbook.get(LOG).warning("gesture policy failed: %s", exc)
            self._last_reason = f"the policy failed — {exc}"
            return gesture_os.Intent()
        self._last_reason = intent.reason
        if intent.is_empty:
            return intent
        if self._os_pointer.apply(intent, self._screen):
            self._delivered += 1
        return intent


def _to_sample(sample):
    """One camera sample → `gesture_os.Sample`, or None for "no hand".

    `hand_sample()` returns four fields, the raw worker returns six, and both
    mean the same thing to the policy. Absorbing the shapes here keeps
    `gesture_os.Sample` — which is what the tests pin — unchanged.
    """
    if sample is None:
        return None
    if isinstance(sample, gesture_os.Sample):
        return sample
    try:
        values = tuple(sample)
    except TypeError:
        return None
    if len(values) < 2:
        return None
    try:
        return gesture_os.Sample(
            x=float(values[0]),
            y=float(values[1]),
            pinch=bool(values[2]) if len(values) > 2 else False,
            scroll=bool(values[3]) if len(values) > 3 else False,
            claw=bool(values[5]) if len(values) > 5 else False,
        )
    except (TypeError, ValueError):
        return None


__all__ = ["GestureBridge"]
