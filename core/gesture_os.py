"""Bare-hand gestures that reach the operating system — and the leash on them.

WHY THIS IS A SEPARATE POLICY FROM `core/workspace_gesture.py`
    That module says so itself: "Local camera tracking for the JARVIS
    workspace; never generates OS input." Every one of its five gestures moves
    a widget inside this program, on purpose. Reaching the OS is a different
    act with a different failure mode: a mis-read hand in the workspace drops a
    card somewhere wrong, and a mis-read hand on the OS clicks somebody's
    payment form.

    So the workspace gestures are not widened. They keep working exactly as
    they do, and this module decides whether a gesture may ALSO be sent to the
    operating system — with its own rules, its own allowlist, and its own
    reasons to stop.

THE FOUR RULES

    1. THREE ACTIONS, AND NOTHING ELSE.
       `pointer`, `click`, `scroll`. There is no gesture that types a key, runs
       a shortcut, closes a window or launches a program, and there will not be
       one: a hand pose recognised by a webcam at 30 fps is not a delivery
       mechanism for `Ctrl+W`. `gesture_actions.py` already holds an allowlist
       of desktop shortcuts; none of it is reachable from here.

    2. JARVIS'S OWN SURFACES ARE NEVER HAND-OPERATED.
       The moment this window takes focus, OS control stops. That is not a
       convenience, it is the promise the README already makes — "konfirmasi
       sensitif memerlukan input fisik". If a confirmation banner is up, an OS
       click must not be able to press it, so the pointer is frozen while it is
       visible, and unfrozen when it is not.

    3. A HELD MOUSE BUTTON IS NEVER LEFT BEHIND.
       Losing the hand mid-pinch must release the button on that same frame.
       A stuck mouse button turns the whole desktop into a drag-selection, and
       the user cannot fix it by waving.

    4. GHOST SAMPLES ARE DROPPED, NOT FOLLOWED.
       When a hand appears at a position the previous frame does not account
       for, it is a mis-detection (a face, a sleeve, a second person) and the
       sample is discarded. A pointer that teleports across the screen lands on
       whatever was there.

WHAT THIS MODULE DOES NOT DO
    It does not open the camera, read a frame, or move anything. It is handed
    one sample at a time and answers "move, click, release, scroll, or do
    nothing" — which is the part that can be tested on a machine with no
    webcam, no Windows and no display.
"""
from __future__ import annotations

from dataclasses import dataclass

# The only three things a gesture may do to the operating system.
POINTER = "pointer"
CLICK = "click"
SCROLL = "scroll"
ALLOWED = (POINTER, CLICK, SCROLL)

# A pinch must be held this long before it counts as a click — the same 350 ms
# `core/hand_gesture.py` uses, because a hand and a mouse should not disagree
# about what "I have pressed it" feels like.
PINCH_HOLD_SECONDS = 0.35

# How far the hand may jump between frames before the sample is treated as a
# mis-detection rather than a movement. Measured in normalised screen units.
MAX_JUMP = 0.35

# Scroll is rate-limited: a held two-finger pose is a stream of frames, and one
# scroll event per frame is unusable.
SCROLL_INTERVAL_SECONDS = 0.06
SCROLL_STEP = 3


@dataclass(frozen=True)
class Sample:
    """One frame's worth of tracking, as `core.workspace_gesture` already
    produces it: normalised pointer, plus the three poses."""

    x: float
    y: float
    pinch: bool = False
    scroll: bool = False
    claw: bool = False


@dataclass(frozen=True)
class Context:
    """Everything outside the hand that decides whether it may act.

    `own_window_focused` is true when the JARVIS window is the active window;
    `confirmation_open` when one of its confirmation surfaces is on screen;
    `modal_open` when a dialog of ours is. Any of them freezing the pointer is
    rule 2, and all three are passed in rather than detected here so that the
    decision stays a pure function.
    """

    os_mode: bool = False
    own_window_focused: bool = False
    confirmation_open: bool = False
    modal_open: bool = False
    now: float = 0.0

    @property
    def frozen(self) -> bool:
        return (self.own_window_focused or self.confirmation_open
                or self.modal_open)


@dataclass(frozen=True)
class Intent:
    """What to do with this frame. Never more than one thing."""

    action: str = ""                 # POINTER / CLICK / SCROLL / ""
    x: float = 0.0                   # normalised, for POINTER
    y: float = 0.0
    press: bool = False              # for CLICK: True = button down
    release: bool = False            # for CLICK: True = button up
    amount: int = 0                  # for SCROLL
    reason: str = ""                 # why nothing happened, when nothing did

    @property
    def is_empty(self) -> bool:
        return not self.action


class HandPointer:
    """The state machine between a stream of samples and the operating system.

    One instance per tracking session. `step()` is the only entry point: it
    takes one sample, the context, and returns one `Intent`.
    """

    def __init__(self) -> None:
        self._pinch_since: float | None = None
        self._down = False
        self._last_point: tuple[float, float] | None = None
        self._last_scroll = 0.0
        self._dropped = 0

    # ── state the UI may want to show ─────────────────────────────────────

    @property
    def holding_button(self) -> bool:
        """True while the OS mouse button is being held by a gesture.

        Exposed because the interface must be able to show it: a held button is
        the one state a user cannot diagnose by waving harder.
        """
        return self._down

    @property
    def dropped_samples(self) -> int:
        return self._dropped

    def reset(self) -> None:
        """Forget everything. Returns nothing — the caller must release the
        button itself if `holding_button` was true; `release_now()` does both.
        """
        self._pinch_since = None
        self._down = False
        self._last_point = None
        self._last_scroll = 0.0

    def release_now(self) -> Intent:
        """The intent that lets go of the button, whatever the hand is doing.

        Called when tracking stops, when the window takes focus, when the mode
        is switched off, and when the program exits. Rule 3: a held button is
        never left behind.
        """
        was_down = self._down
        self.reset()
        if was_down:
            return Intent(action=CLICK, release=True)
        return Intent(reason="nothing was held")

    # ── the decision ──────────────────────────────────────────────────────

    def step(self, sample: Sample | None, ctx: Context) -> Intent:
        if not ctx.os_mode:
            return self._stop("OS control is off", ctx)

        if ctx.frozen:
            # Rule 2. The wording differs because the user's next move differs:
            # a confirmation needs a physical press, own focus means the
            # workspace gestures are already handling it.
            if ctx.confirmation_open:
                return self._stop(
                    "a confirmation is on screen; press it with the mouse or "
                    "keyboard", ctx)
            return self._stop("this window has focus; workspace gestures apply", ctx)

        if sample is None:
            return self._stop("the hand was lost", ctx)

        # ── rule 4: is this a real movement or a mis-detection? ───────────
        jump = 0.0
        if self._last_point is not None:
            jump = max(abs(sample.x - self._last_point[0]),
                       abs(sample.y - self._last_point[1]))
        self._last_point = (sample.x, sample.y)
        if jump > MAX_JUMP:
            self._dropped += 1
            # The button is NOT released here on purpose: a hand that jumps is
            # still a hand, and letting go mid-drag because one frame was bad
            # would drop whatever the user was carrying. The sample is simply
            # not acted on.
            return Intent(reason="that frame moved too far to be the hand")

        # ── scroll, first: it is the pose that owns the vertical axis ─────
        if sample.scroll and not sample.pinch:
            self._pinch_since = None
            if ctx.now - self._last_scroll >= SCROLL_INTERVAL_SECONDS:
                self._last_scroll = ctx.now
                return Intent(action=SCROLL, amount=SCROLL_STEP)
            return Intent(reason="scrolling, waiting for the next step")

        # ── click: a pinch held long enough to be deliberate ──────────────
        if sample.pinch:
            if self._pinch_since is None:
                self._pinch_since = ctx.now
                return Intent(reason="pinch started; hold it to click")
            if not self._down and ctx.now - self._pinch_since >= PINCH_HOLD_SECONDS:
                self._down = True
                return Intent(action=CLICK, press=True)
            if self._down:
                return Intent(reason="holding the button")
            return Intent(reason="pinch not held long enough")

        # Pinch released: let go if we were holding, and move on.
        if self._down:
            self._down = False
            self._pinch_since = None
            return Intent(action=CLICK, release=True)
        self._pinch_since = None

        return Intent(action=POINTER, x=sample.x, y=sample.y)

    def _stop(self, reason: str, ctx: Context) -> Intent:
        """Do nothing — and let go of anything being held, whatever stopped it."""
        if self._down:
            self._down = False
            self._pinch_since = None
            return Intent(action=CLICK, release=True)
        self._pinch_since = None
        del ctx
        return Intent(reason=reason)


def describe(intent: Intent) -> str:
    """One line for the activity log. Never called for an empty intent."""
    if intent.action == POINTER:
        return f"pointer to {intent.x:.0%}, {intent.y:.0%}"
    if intent.action == CLICK:
        return "button down" if intent.press else "button up"
    if intent.action == SCROLL:
        return f"scroll {intent.amount}"
    return intent.reason or "nothing"


def coordinate(x: float, y: float, width: int, height: int,
               margin: float = 0.06) -> tuple[int, int]:
    """Normalised hand position to screen pixels, with a border the hand cannot
    reach into.

    The margin is not cosmetic: hand tracking is least accurate at the edges of
    the camera frame, and the corners of a screen hold the things that must not
    be clicked by accident — window close buttons, scrollbars, the Start menu.
    """
    m = max(0.0, min(margin, 0.4))
    fx = min(1.0, max(0.0, float(x)))
    fy = min(1.0, max(0.0, float(y)))
    usable_x = max(1, int(width * (1 - 2 * m)))
    usable_y = max(1, int(height * (1 - 2 * m)))
    px = int(width * m) + int(fx * usable_x)
    py = int(height * m) + int(fy * usable_y)
    return (max(0, min(px, max(0, width - 2))), max(0, min(py, max(0, height - 2))))


__all__ = ["ALLOWED", "CLICK", "Context", "HandPointer", "Intent", "MAX_JUMP",
           "PINCH_HOLD_SECONDS", "POINTER", "SCROLL", "Sample", "coordinate",
           "describe"]
