"""The toast queue — the arithmetic behind "3 tertahan · akan muncul setelahnya".

WHY THIS IS NOT PART OF THE WIDGET
    A toast is shown when something happens, and things happen on the scheduler
    thread, on the agent thread, and inside action callbacks. The one place a
    Qt widget cannot be is any of those. So the queue — how many, in what order,
    which ones are held, and what happens when the tenth one arrives — lives
    here, and a widget reads it.

WHY THERE IS A CAPACITY AND NOT JUST A LIMIT
    A daily budget (`core/suggestion_quota`) says how many suggestions the
    assistant may make. It says nothing about how many may be on screen at once:
    five queued suggestions at 90 px each is a wall down the right edge of a
    720 px desktop. The two numbers are different questions and get two answers.

    What happens at the cap is the part that has to be honest. The third toast
    replaces the oldest, and the queue keeps a count of what it dropped — the
    label becomes "2 lagi" rather than silently losing one. A queue that
    discards without saying so is indistinguishable from a queue that lost it.

WHAT IT NEVER DOES
    It never blocks and never raises. It is called from inside the code path
    that is producing the result the user asked for, so a full queue must not
    turn a completed action into a failed one.
"""

from __future__ import annotations

import threading
import time

from dataclasses import dataclass, field

# Three visible at once: 3 × 90 px fits in the 330 px stack drawn on board 2,
# with the taskbar clearance to spare. The fourth replaces the oldest.
VISIBLE_MAX = 3
# A toast is a glance, not a notification centre. After this many seconds it
# leaves on its own even if nothing else arrives.
DEFAULT_TTL = 6.0

KIND_INFO, KIND_WARN, KIND_RISKY = "info", "warn", "risky"
KINDS = (KIND_INFO, KIND_WARN, KIND_RISKY)


@dataclass
class Toast:
    text: str
    kind: str = KIND_INFO
    created: float = field(default_factory=time.monotonic)
    ttl: float = DEFAULT_TTL

    def expired(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return (now - self.created) >= self.ttl


class ToastQueue:
    """A bounded, ordered queue of toasts with an honest dropped count.

    Thread-safe: `push` is called from whatever thread produced the message and
    `drain` from the UI tick. No Qt, no signals — the widget polls.
    """

    def __init__(self, visible_max: int = VISIBLE_MAX, ttl: float = DEFAULT_TTL) -> None:
        self._max = max(1, int(visible_max))
        self._ttl = max(0.0, float(ttl))
        self._items: list[Toast] = []
        self._dropped = 0
        self._lock = threading.Lock()

    # ── writing ──────────────────────────────────────────────────────────────

    def push(self, text: str, kind: str = KIND_INFO) -> Toast | None:
        """Add one toast. Returns it, or None if it was empty.

        An unknown `kind` becomes `info` rather than being refused: the caller
        is usually an action that just succeeded, and a typo in a label must not
        turn a completed action into an error.
        """
        text = str(text or "").strip()
        if not text:
            return None
        if kind not in KINDS:
            kind = KIND_INFO
        toast = Toast(text=text, kind=kind, created=time.monotonic(), ttl=self._ttl)
        with self._lock:
            self._items.append(toast)
            while len(self._items) > self._max:
                self._items.pop(0)
                self._dropped += 1
        return toast

    # ── reading ──────────────────────────────────────────────────────────────

    def current(self) -> list[Toast]:
        """The toasts that should be on screen now, oldest first, expired removed."""
        now = time.monotonic()
        with self._lock:
            self._items = [t for t in self._items if not t.expired(now)]
            return list(self._items)

    def dropped(self) -> int:
        """How many were pushed out by the cap since the last `clear_dropped`."""
        with self._lock:
            return self._dropped

    def overflow_label(self) -> str:
        """The text that accompanies the stack, or "" when nothing was lost.

        Indonesian, because it sits in the Indonesian interface; the number is
        the one the user can act on ("wait, what did I miss?").
        """
        count = self.dropped()
        if count <= 0:
            return ""
        return f"{count} lagi"

    def clear_dropped(self) -> None:
        with self._lock:
            self._dropped = 0

    # ── dismissing ───────────────────────────────────────────────────────────

    def dismiss(self, toast: Toast) -> bool:
        """Remove one toast the user clicked away. False if it was already gone."""
        with self._lock:
            try:
                self._items.remove(toast)
                return True
            except ValueError:
                return False

    def dismiss_top(self) -> Toast | None:
        """Remove and return the oldest. Bound to Esc in the stack."""
        with self._lock:
            if not self._items:
                return None
            return self._items.pop(0)

    def clear(self) -> None:
        """Empty the stack and forget the dropped count. For a mode change."""
        with self._lock:
            self._items.clear()
            self._dropped = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
