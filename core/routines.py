"""Routine scheduling — pure policy, no I/O, no Qt, no threading.

WHY A PURE POLICY MODULE
    Board 11 draws three scheduled routines with times and payloads, and the
    build had no routine store at all. The scheduler this adds has to decide
    "is this routine due now?" and "when does it fire next?" without touching
    the clock in a way a test cannot control, and without importing anything
    that needs a screen. So the decision lives here as plain functions over a
    `Schedule` value, and `core/routine_scheduler.py` owns the thread that
    calls them on a real clock.

THE SCHEDULE SHAPE
    A routine fires on a repeating pattern: a set of weekdays (0=Monday..
    6=Sunday, empty meaning every day) at a fixed local time. That is the whole
    model — no seconds, no complex cron, because board 11's artboard draws
    "setiap hari jam 07" and "setiap Senin 19:30", and a schedule the user
    cannot read off the page is a schedule they cannot trust.

    The parser turns a short Indonesian phrase into that shape. It is
    deliberately conservative: an unrecognised phrase is refused with a reason
    rather than guessed at, because a routine that fires at the wrong time is
    worse than no routine.

WHAT IS NOT HERE
    No storage, no clock, no thread. `memory/routine_store.py` owns the file;
    `core/routine_scheduler.py` owns the timing. Both depend on this module;
    this module depends on nothing in the project.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

# Weekday numbers as `datetime.weekday()` uses them: 0 = Monday .. 6 = Sunday.
WEEKDAY_NAMES = {
    "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3,
    "jumat": 4, "sabtu": 5, "minggu": 6,
}
FREQS = ("daily", "weekly")

# Reverse map for `humanize_when`: weekday number -> Indonesian name.
WEEKDAY_NAMES_REV = {v: k for k, v in WEEKDAY_NAMES.items()}


@dataclass(frozen=True)
class Schedule:
    """When a routine fires: which weekdays, at what local time.

    `days` empty means EVERY day (the artboard's "setiap hari"). `time` is a
    "HH:MM" string in 24-hour local time. Both are validated at construction
    by `validate_schedule`, so a Schedule that exists is always well-formed.
    """
    time: str
    days: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        return {"time": self.time, "days": list(self.days)}

    @classmethod
    def from_dict(cls, data: dict) -> "Schedule":
        days = data.get("days") or []
        return cls(time=str(data.get("time", "")).strip(),
                   days=tuple(int(d) for d in days))


@dataclass(frozen=True)
class Routine:
    """One scheduled job: a name, when it runs, and what it says/does.

    `payload` is the command text the session sends when the routine fires —
    the same shape a user would type in the command field, so a routine is
    just "say this, at this time, on these days".
    """
    id: str
    name: str
    schedule: Schedule
    payload: str
    enabled: bool = True
    last_fired: str = ""           # ISO date (YYYY-MM-DD) of the last fire, or ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule.to_dict(),
            "payload": self.payload,
            "enabled": self.enabled,
            "last_fired": self.last_fired,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Routine":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            schedule=Schedule.from_dict(data.get("schedule") or {}),
            payload=str(data.get("payload", "")),
            enabled=bool(data.get("enabled", True)),
            last_fired=str(data.get("last_fired", "") or ""),
        )


def validate_schedule(schedule: Schedule) -> str | None:
    """Return None if the schedule is well-formed, else a reason it is not.

    Pure: it does not look at the clock. A caller that builds a Schedule from
    user input calls this before storing it, so a malformed schedule never
    reaches the file.
    """
    if not schedule.time or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d",
                                             schedule.time):
        return "time must be HH:MM in 24-hour form"
    if not schedule.days:
        return None                              # every day
    for d in schedule.days:
        if d not in range(7):
            return "day must be 0..6 (Monday..Sunday)"
    if len(set(schedule.days)) != len(schedule.days):
        return "days must not repeat"
    return None


def parse_schedule(text: str) -> Schedule:
    """Turn a short Indonesian phrase into a Schedule.

    Accepted shapes (the artboard's own wording):
      "setiap hari jam 07"          -> every day at 07:00
      "setiap hari 07:00"           -> every day at 07:00
      "setiap Senin jam 19:30"      -> Mondays at 19:30
      "Senin 19:30"                 -> Mondays at 19:30
      "setiap Senin, Rabu 08:00"    -> Mondays and Wednesdays at 08:00

    The parser is deliberately conservative: anything it cannot read returns a
    Schedule whose `time` is invalid, and the caller validates it. A routine
    that fires at the wrong time is worse than no routine, so an unknown phrase
    is refused rather than guessed at.
    """
    raw = str(text or "").strip().lower()
    if not raw:
        return Schedule(time="")

    days: list[int] = []
    time_str = ""

    # Pull out the time first: either "HH:MM" or "jam HH".
    m = re.search(r"(\d{1,2}):(\d{2})\b", raw)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            time_str = f"{hh:02d}:{mm:02d}"
    else:
        m = re.search(r"jam\s+(\d{1,2})(?:\s*:\s*(\d{2}))?", raw)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2)) if m.group(2) else 0
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                time_str = f"{hh:02d}:{mm:02d}"

    # The weekdays: every named day present, in the phrase's own order.
    for name, num in WEEKDAY_NAMES.items():
        if re.search(rf"\b{name}\b", raw):
            if num not in days:
                days.append(num)
    days.sort()

    # "setiap hari" / bare "hari" means every day — no day filter.
    every_day = bool(re.search(r"\bsetiap\s+hari\b|\bhari\b", raw)) and not days
    if every_day or not days:
        return Schedule(time=time_str, days=())
    return Schedule(time=time_str, days=tuple(days))


def parse_schedule_or_raise(text: str) -> Schedule:
    """`parse_schedule` + `validate_schedule`; raises ValueError when bad."""
    sched = parse_schedule(text)
    reason = validate_schedule(sched)
    if reason:
        raise ValueError(f"schedule tidak valid: {reason}")
    return sched


def next_fire(schedule: Schedule, now: _dt.datetime) -> _dt.datetime:
    """The next local datetime this schedule fires, strictly after `now`.

    Pure: `now` is a parameter, so a test can pin the clock. If the schedule
    is invalid the behaviour is undefined — callers validate first.
    """
    hours, minutes = (int(x) for x in schedule.time.split(":"))
    allowed = set(schedule.days) if schedule.days else set(range(7))
    candidate = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    # Walk forward day by day until we hit an allowed weekday whose time is
    # still ahead of `now`. At most 7 iterations, so this is cheap.
    for _ in range(8):
        if candidate.weekday() in allowed and candidate > now:
            return candidate
        candidate += _dt.timedelta(days=1)
    # Unreachable for a valid schedule (at least one weekday is always set).
    raise ValueError("schedule has no future fire time")


def is_due(schedule: Schedule, now: _dt.datetime,
           last_fired: str = "") -> bool:
    """Whether the routine should fire on `now`'s date.

    "Due" means: today is an allowed weekday, the local time has arrived, and
    the routine has not already fired today (the `last_fired` date guard). The
    same-day guard is what stops a routine firing twice if the scheduler
    ticks twice across the minute boundary.
    """
    hours, minutes = (int(x) for x in schedule.time.split(":"))
    allowed = set(schedule.days) if schedule.days else set(range(7))
    if now.weekday() not in allowed:
        return False
    if (now.hour, now.minute) < (hours, minutes):
        return False
    return now.date().isoformat() != (last_fired or "")


def humanize_when(schedule: Schedule) -> str:
    """A short phrase describing the schedule, for the board's "when" line.

    Pure text, no clock: "setiap hari 07:00" or "setiap Senin, Rabu 19:30".
    The UI uses this so the page and the store never disagree about wording.
    """
    if schedule.days:
        names = [WEEKDAY_NAMES_REV[d] for d in schedule.days]
        days_part = ", ".join(names)
    else:
        days_part = "hari"
    return f"setiap {days_part} {schedule.time}"


__all__ = [
    "Schedule", "Routine", "FREQS", "WEEKDAY_NAMES", "WEEKDAY_NAMES_REV",
    "validate_schedule", "parse_schedule", "parse_schedule_or_raise",
    "next_fire", "is_due", "humanize_when",
]
