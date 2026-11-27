"""Local storage for scheduled routines — the only writer of `memory/routines.json`.

WHY THIS IS A SEPARATE STORE, NOT ANOTHER KEY IN `api_keys.json`
    Routines are USER-CREATED DATA, not a setting. `api_keys.json` holds
    switches and credentials; a routines file keeps the routine list readable,
    backable-up and gitignored on its own, and — like the voiceprint — lets a
    structural test assert that exactly one module writes it. A routine the
    user built over a month should not live in the same file as the API key.

THE CONTRACT
    `RoutineStore` is a thin, thread-safe wrapper over one JSON file. It is
    pure I/O plus a lock: it does not decide WHEN a routine fires (that is
    `core/routines.py`) or run it (that is `core/routine_scheduler.py`). Like
    `memory/voiceprint_store.py`, it is the ONLY module that touches the file.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from core.routines import Routine, is_due

# Next to the other local data, gitignored like the voiceprint.
ROUTINES_PATH = Path(__file__).resolve().parent / "routines.json"

# Instances serving the UI and scheduler must share a transaction lock. This
# protects threads in one process, not independent processes or external editors.
_STORE_LOCK = threading.RLock()


class RoutineStoreError(RuntimeError):
    """A store could not be safely read; never overwrite it as if empty."""


def default_store(path: Path | None = None) -> "RoutineStore":
    """A store rooted at the default location, or a caller-supplied one."""
    return RoutineStore(path or ROUTINES_PATH)


class RoutineStore:
    """Thread-safe persistence for scheduled routines.

    One lock, one file, atomic writes. The file holds a JSON object:
    `{"routines": [ {Routine.to_dict()}, ... ]}`. An empty or missing file is
    not an error — it means "no routines yet".
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = _STORE_LOCK

    @property
    def path(self) -> Path:
        return self._path

    # ── read ──────────────────────────────────────────────────────────────

    def _load(self) -> list[Routine]:
        with self._lock:
            try:
                raw = self._path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return []
            except (OSError, UnicodeError) as exc:
                raise RoutineStoreError("Cannot read routine store") from exc
            try:
                data = json.loads(raw)
                rows = data.get("routines") if isinstance(data, dict) else data
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ValueError("invalid routine list")
                result = [Routine.from_dict(r) for r in rows]
                if any(not r.id for r in result) or len({r.id for r in result}) != len(result):
                    raise ValueError("missing or duplicate routine id")
                return result
            except (ValueError, TypeError, AttributeError) as exc:
                raise RoutineStoreError("Invalid routine store") from exc

    def all(self) -> list[Routine]:
        """Every routine, in file order. A snapshot, not a live view."""
        return list(self._load())

    def get(self, routine_id: str) -> Routine | None:
        for r in self._load():
            if r.id == routine_id:
                return r
        return None

    # ── write ─────────────────────────────────────────────────────────────

    def _write(self, routines: list[Routine]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"routines": [r.to_dict() for r in routines]}
            fd, tmp = tempfile.mkstemp(prefix=".routines-", suffix=".tmp",
                                       dir=self._path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(tmp, self._path)
            except BaseException:
                # A failed write must not leave a half-written file behind.
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def add(self, routine: Routine) -> Routine:
        """Insert a routine. Refuses a duplicate id (returns the existing one)."""
        with self._lock:
            routines = self._load()
            for r in routines:
                if r.id == routine.id:
                    return r
            routines.append(routine)
            self._write(routines)
            return routine

    def update(self, routine: Routine) -> Routine:
        """Replace a routine by id. Returns None if the id is unknown."""
        with self._lock:
            routines = self._load()
            for i, r in enumerate(routines):
                if r.id == routine.id:
                    routines[i] = routine
                    self._write(routines)
                    return routine
            return None

    def remove(self, routine_id: str) -> bool:
        """Delete a routine by id. Returns whether one was removed."""
        with self._lock:
            routines = self._load()
            kept = [r for r in routines if r.id != routine_id]
            if len(kept) == len(routines):
                return False
            self._write(kept)
            return True

    def set_enabled(self, routine_id: str, enabled: bool) -> Routine | None:
        """Toggle a routine's enabled flag. Returns the updated routine or None."""
        with self._lock:
            routines = self._load()
            for i, r in enumerate(routines):
                if r.id == routine_id:
                    toggled = Routine(
                        id=r.id, name=r.name, schedule=r.schedule,
                        payload=r.payload, enabled=bool(enabled),
                        last_fired=r.last_fired,
                    )
                    routines[i] = toggled
                    self._write(routines)
                    return toggled
            return None

    @staticmethod
    def _same_displayed(current: Routine, expected: Routine) -> bool:
        # The scheduler may stamp last_fired while the user reads the card.
        # That is not an edit to the command, schedule, or enabled state.
        return (current.id == expected.id and current.name == expected.name and
                current.schedule == expected.schedule and current.payload == expected.payload and
                current.enabled == expected.enabled)

    def remove_if_unchanged(self, expected: Routine) -> bool:
        """Remove only the routine the user reviewed, atomically within this process."""
        with self._lock:
            rows = self._load()
            for index, row in enumerate(rows):
                if row.id == expected.id:
                    if not self._same_displayed(row, expected):
                        return False
                    del rows[index]
                    self._write(rows)
                    return True
            return False

    def set_enabled_if_unchanged(self, expected: Routine, enabled: bool) -> Routine | None:
        """Change only the reviewed routine; preserve a concurrent scheduler stamp."""
        with self._lock:
            rows = self._load()
            for index, row in enumerate(rows):
                if row.id == expected.id:
                    if not self._same_displayed(row, expected):
                        return None
                    updated = Routine(row.id, row.name, row.schedule, row.payload,
                                      bool(enabled), row.last_fired)
                    rows[index] = updated
                    self._write(rows)
                    return updated
            return None

    def mark_fired(self, routine_id: str, when: str) -> Routine | None:
        """Record that a routine fired on `when` (ISO date), so it does not
        re-fire the same day. Returns the updated routine or None."""
        with self._lock:
            routines = self._load()
            for i, r in enumerate(routines):
                if r.id == routine_id:
                    updated = Routine(
                        id=r.id, name=r.name, schedule=r.schedule,
                        payload=r.payload, enabled=r.enabled, last_fired=when,
                    )
                    routines[i] = updated
                    self._write(routines)
                    return updated
            return None


    def claim_due(self, routine_id: str, now) -> Routine | None:
        """Atomically recheck current state and mark one due routine fired."""
        with self._lock:
            routines = self._load()
            for index, routine in enumerate(routines):
                if routine.id != routine_id:
                    continue
                if not routine.enabled or not is_due(routine.schedule, now, routine.last_fired):
                    return None
                routines[index] = Routine(
                    id=routine.id, name=routine.name, schedule=routine.schedule,
                    payload=routine.payload, enabled=routine.enabled,
                    last_fired=now.date().isoformat())
                self._write(routines)
                return routines[index]
            return None


__all__ = ["RoutineStoreError", "RoutineStore", "default_store", "ROUTINES_PATH"]
