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
#
# EIGHT, NOT SIX. `n02()` prints "Hilang otomatis 8 detik" and the brief says
# eight; this constant said 6.0, and no test noticed because the test was
# written from the constant. A toast that leaves while the user is still
# reading the first line did not arrive at all.
DEFAULT_TTL = 8.0

KIND_INFO, KIND_WARN, KIND_RISKY = "info", "warn", "risky"
KINDS = (KIND_INFO, KIND_WARN, KIND_RISKY)

# The accent rule down the card's left edge — `toast(x, y, w, ..., accent=CYAN)`
# in build.py. Risky is amber for the same reason board 14a's confirmation is:
# a dangerous toast and a friendly one must not look alike at a glance.
ACCENTS = {
    KIND_INFO: "#4FD8F0",
    KIND_WARN: "#4FD8F0",
    KIND_RISKY: "#F5A524",
}

# `toast()` in build.py: `h = 96 if actions else 74`. The taller card is the
# one with a button row; the numbers are asserted against that helper in
# `tests/test_toast_board2.py`.
HEIGHT_WITH_ACTIONS = 96
HEIGHT_PLAIN = 74

# Board 2 draws two buttons and the card is 96 px. A third button would either
# overflow the card or shrink every button below a readable width, so it is
# dropped where the toast is built rather than at paint time — a paint-time
# clip is a button that looks clickable and is not.
MAX_ACTIONS = 2


def _clean_actions(actions) -> tuple[str, ...]:
    """Up to `MAX_ACTIONS` non-empty labels, as a tuple.

    Tuples because the widget reads this on the UI thread while the producer may
    still hold a reference: a mutable list is a race with a friendly face. Empty
    labels are dropped because an empty pill reads as a broken button.
    """
    if not actions:
        return ()
    if isinstance(actions, str):
        actions = (actions,)
    out = []
    for action in actions:
        label = str(action or "").strip()
        if label:
            out.append(label)
        if len(out) >= MAX_ACTIONS:
            break
    return tuple(out)


@dataclass
class Toast:
    """One card: what it says, and the shape board 2 draws for it.

    `text` is the title at 13 px; `body` is the 11.5 px line under it. A toast
    with neither is refused by `push`, so `text` is the only required field.
    """

    text: str
    kind: str = KIND_INFO
    body: str = ""
    actions: tuple[str, ...] = ()
    created: float = field(default_factory=time.monotonic)
    ttl: float = DEFAULT_TTL

    def __post_init__(self) -> None:
        self.kind = self.kind if self.kind in KINDS else KIND_INFO
        self.body = str(self.body or "")
        self.actions = _clean_actions(self.actions)

    @property
    def accent(self) -> str:
        """The 3 px rule's colour for this kind."""
        return ACCENTS.get(self.kind, ACCENTS[KIND_INFO])

    @property
    def height(self) -> int:
        """96 px with a button row, 74 without — board 2's own arithmetic."""
        return HEIGHT_WITH_ACTIONS if self.actions else HEIGHT_PLAIN

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

    def push(self, text: str, kind: str = KIND_INFO, body: str = "",
             actions=()) -> Toast | None:
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
        # Built OUTSIDE the lock: `_clean_actions` walks a tuple and allocates,
        # and doing that inside the critical section makes every producer wait
        # on a string operation it does not share.
        toast = Toast(text=text, kind=kind, body=body, actions=actions,
                      created=time.monotonic(), ttl=self._ttl)
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
        # THE ARTBOARD'S PHRASE, verbatim — `toast_queue()` in build.py:
        # `f"+{hidden} lain dalam antrean"`. It used to say "2 lagi", which reads
        # as "two more are coming", and they are not: the cap replaced them.
        return f"+{count} lain dalam antrean"

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
