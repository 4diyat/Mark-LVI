"""The routine scheduler — the thread that turns a store into firing jobs.

WHY THIS IS A SEPARATE MODULE FROM `core/routines.py`
    `core/routines.py` decides WHEN a routine fires (pure functions over a
    `Schedule`). This module owns the CLOCK and the THREAD: it polls the store,
    asks the policy whether anything is due, and hands a due routine to a
    callback the session wires in. Keeping the thread here — not in `main.py`
    or in the store — means the timing is testable without a session: a test
    can inject a fake clock and a recording callback and assert the scheduler
    fires exactly the routines that are due, and nothing else.

THE LOOP
    A daemon thread wakes every `tick_seconds`, reads the store once, and for
    each enabled routine checks `is_due(schedule, now, last_fired)`. A due
    routine is passed to `on_fire(routine)` and its `last_fired` is stamped
    with today's date so it does not fire twice across a tick boundary. The
    callback runs on the scheduler's own thread; the session is expected to
    marshal the actual "say this" onto its own loop (the same shape
    `main.py` uses for every other cross-thread callback).

WHAT IT DOES NOT DO
    It does not store anything beyond the store, does not speak, and does not
    own the session. If `on_fire` raises, the error is reported through
    `on_error` (default: printed) and the scheduler keeps ticking — one routine
    that fails must not stop the others or the whole schedule.
"""
from __future__ import annotations

import datetime as _dt
import threading
from typing import Callable

from core.routines import Routine, is_due
from memory.routine_store import RoutineStore

FireCallback = Callable[[Routine], None]
ErrorCallback = Callable[[Routine, BaseException], None]


class RoutineScheduler:
    """Polls a store and fires due routines on a background thread.

    One instance per session. `start()` begins the daemon thread; `stop()`
    asks it to end and joins it. The scheduler is safe to start/stop once;
    restarting after stop is supported (a fresh thread is spawned).
    """

    def __init__(self, store: RoutineStore, on_fire: FireCallback,
                 tick_seconds: float = 30.0,
                 on_error: ErrorCallback | None = None,
                 clock: Callable[[], _dt.datetime] | None = None) -> None:
        self._store = store
        self._on_fire = on_fire
        self._tick = float(tick_seconds)
        self._on_error = on_error
        # `clock` is injectable so a test can pin "now"; production uses the
        # real local clock.
        self._clock = clock or (lambda: _dt.datetime.now())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Begin polling. Idempotent: a second start while running is a no-op."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="routine-scheduler",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the thread to end and wait for it. Safe to call when not running."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def tick_once(self) -> list[Routine]:
        """Run one poll synchronously and return what fired. For tests.

        The production thread calls this each tick; a test calls it directly
        with a pinned clock to assert exactly which routines fire.
        """
        now = self._clock()
        fired: list[Routine] = []
        for routine in self._store.all():
            if not routine.enabled:
                continue
            if not is_due(routine.schedule, now, routine.last_fired):
                continue
            # Stamp BEFORE firing so a re-entrant or slow callback cannot cause
            # a double-fire on the same tick.
            self._store.mark_fired(routine.id, now.date().isoformat())
            fired.append(routine)
            try:
                self._on_fire(routine)
            except BaseException as e:           # noqa: BLE001
                if self._on_error is not None:
                    self._on_error(routine, e)
                else:
                    print(f"[Routines] {routine.name!r} failed: {type(e).__name__}: {e}")
        return fired

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except BaseException as e:            # noqa: BLE001
                # A poll-level failure (e.g. store unreadable) must not kill
                # the thread: report once and keep ticking.
                print(f"[Routines] poll failed: {type(e).__name__}: {e}")
            # wait() returns True immediately if stop is set during the sleep,
            # so stop() is responsive rather than waiting out the full tick.
            self._stop.wait(self._tick)


__all__ = ["RoutineScheduler"]
