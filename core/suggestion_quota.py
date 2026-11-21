"""core/suggestion_quota.py — the daily brake on proactive suggestions.

WHY THIS IS NOT JUST A COOLDOWN
    `core/notify.py` already refuses to fire twice within 45 seconds, and that
    solved a different problem: a status cycle that announced every transition.
    It does not stop the slow version of the same failure. Three suggestions in
    an afternoon are three interruptions, each individually reasonable, and
    together they are the reason people switch the feature off in week two and
    never switch it back on.

    So the limit is per DAY and counted, not timed: a budget the user can see
    ("2 dari 3 terpakai" in the tray panel) rather than an invisible rule that
    silently swallows the fourth suggestion.

WHAT COUNTS AS A NEW DAY
    Local midnight, not a rolling 24 hours. "Tiga saran per hari" is what the
    user was promised, and a rolling window would let four land inside one
    afternoon while still claiming to respect a daily cap. The date is stored
    with the count, so a clock change or a restart cannot reset the budget by
    accident — only the date changing does.

WHAT IS PERSISTED, AND WHY SO LITTLE
    `{"date": "2026-11-19", "used": 2}`. Nothing about what was suggested. The
    quota is a counter, not a log; keeping the text would create a second,
    unmanaged record of what the assistant noticed about the user, which is
    exactly what `core/memory` is for and what the privacy page promises.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
import threading

DEFAULT_LIMIT = 3

# Where the counter lives. Kept next to the config rather than inside
# `api_keys.json`: that file is user-editable by hand and a corrupted quota
# should not be able to look like a corrupted key file.
def default_path() -> "os.PathLike[str] | str":
    base = os.environ.get("JARVIS_STATE_DIR")
    if base:
        return os.path.join(base, "suggestions.json")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "config", "suggestions.json")


def _today() -> str:
    return _dt.date.today().isoformat()


class SuggestionQuota:
    """A counted, per-day budget. All methods are safe to call from any thread."""

    def __init__(self, limit: int = DEFAULT_LIMIT, path=None) -> None:
        self._limit = max(0, int(limit))
        self._path = path if path is not None else default_path()
        self._lock = threading.Lock()
        self._date, self._used = self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> tuple[str, int]:
        """(date, used) from disk, or a fresh day if anything is wrong.

        Every failure here is a fresh day rather than an error: a quota file
        that cannot be read must not stop the assistant from working, and the
        worst case of resetting is one extra suggestion — far cheaper than a
        crash on startup.
        """
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            date = str(data.get("date") or "")
            used = int(data.get("used") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            return _today(), 0
        if date != _today():
            return _today(), 0
        return date, max(0, used)

    def _save(self) -> None:
        """Write atomically; failure is logged and otherwise ignored.

        A suggestion counter is not worth an exception on the request path. The
        write goes to a temp file in the same directory and is renamed, so a
        crash mid-write cannot leave a half-file that reads as `used: 0` — which
        would hand out a free reset every time the machine died.
        """
        directory = os.path.dirname(os.path.abspath(self._path)) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".suggestions.", suffix=".tmp", dir=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"date": self._date, "used": self._used}, fh)
            os.replace(tmp, self._path)
        except OSError as e:
            print(f"[Quota] could not save the suggestion counter: {e}")

    # ── the budget ───────────────────────────────────────────────────────────

    def _roll(self) -> None:
        """Start a new day if the date changed. Caller holds the lock."""
        today = _today()
        if today != self._date:
            self._date, self._used = today, 0

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self._limit - self._used)

    def allows(self) -> bool:
        """Whether one more suggestion fits in today's budget. Does NOT spend it."""
        return self.remaining > 0

    def take(self) -> bool:
        """Spend one suggestion. True if it fit, False if the budget is gone.

        Spending and checking are one call on purpose: `allows()` followed later
        by a separate increment is a check-then-act race between two scheduler
        threads, and the failure mode is four suggestions in a day that promised
        three.
        """
        with self._lock:
            self._roll()
            if self._used >= self._limit:
                return False
            self._used += 1
            self._save()
            return True

    def refund(self) -> None:
        """Give one back. For a suggestion that was built but never shown.

        The panel's own action ("Lihat yang tertahan") does not consume budget,
        and neither does a suggestion the user cancelled before it appeared.
        """
        with self._lock:
            self._roll()
            if self._used > 0:
                self._used -= 1
                self._save()

    def reset(self) -> None:
        """Clear today's count. Called from the privacy page's erase action."""
        with self._lock:
            self._date, self._used = _today(), 0
            self._save()


# One process-wide counter, because two schedulers sharing a budget must share
# the object. Tests construct their own SuggestionQuota with a temp path.
_shared: SuggestionQuota | None = None
_shared_lock = threading.Lock()


def shared(limit: int = DEFAULT_LIMIT) -> SuggestionQuota:
    """The counter main.py and the scheduler use. Created on first call."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = SuggestionQuota(limit)
        return _shared


def reset_shared() -> None:
    """Forget the process-wide counter. Used by tests and by privacy-erase."""
    global _shared
    with _shared_lock:
        _shared = None
