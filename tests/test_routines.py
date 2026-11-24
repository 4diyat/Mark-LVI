"""The routine policy, store and scheduler — tested without Qt or a session.

Three layers, each pinned to its own contract:

  * `core/routines.py` is PURE: parsing a phrase, validating a schedule, and
    deciding "is this due now?" against an injectable clock. No I/O, so these
    run in a millisecond and cover the edge cases a real clock hides.
  * `memory/routine_store.py` is the only writer of `memory/routines.json`:
    add / remove / toggle / mark-fired, all round-tripped through disk.
  * `core/routine_scheduler.py` owns the THREAD, but `tick_once()` runs one
    poll synchronously so a test can pin the clock and assert exactly which
    routines fire — and that a due routine is not fired twice.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from core.routines import (Schedule, Routine, humanize_when, is_due,
                           next_fire, parse_schedule, parse_schedule_or_raise,
                           validate_schedule)
from memory.routine_store import RoutineStore
from core.routine_scheduler import RoutineScheduler


# ── pure policy ─────────────────────────────────────────────────────────────

def test_parse_every_day_phrase():
    sched = parse_schedule("setiap hari jam 07")
    assert sched.time == "07:00"
    assert sched.days == ()                       # every day
    assert validate_schedule(sched) is None


def test_parse_day_name_phrase():
    sched = parse_schedule("setiap Senin jam 19:30")
    assert sched.time == "19:30"
    assert sched.days == (0,)                     # Monday


def test_parse_multiple_days():
    sched = parse_schedule("setiap Senin, Rabu 08:00")
    assert sched.time == "08:00"
    assert sched.days == (0, 2)


def test_parse_bare_day_and_time():
    sched = parse_schedule("Senin 19:30")
    assert sched.time == "19:30"
    assert sched.days == (0,)


def test_parse_rejects_bad_time_shape():
    # No recognisable time: the Schedule is left with an empty time, and
    # validate_schedule refuses it rather than the parser guessing.
    sched = parse_schedule("setiap hari")
    assert sched.time == ""
    assert validate_schedule(sched) is not None


def test_validate_rejects_out_of_range_hour():
    sched = Schedule(time="25:00")
    reason = validate_schedule(sched)
    assert reason and "HH:MM" in reason


def test_validate_rejects_bad_day():
    sched = Schedule(time="07:00", days=(7,))
    reason = validate_schedule(sched)
    assert reason and "0..6" in reason


def test_parse_schedule_or_raise_raises_on_bad():
    with pytest.raises(ValueError):
        parse_schedule_or_raise("nonsense")


def test_next_fire_is_after_now():
    now = _dt.datetime(2026, 11, 24, 8, 0)          # Tuesday 08:00
    sched = Schedule(time="07:00", days=(0,))        # Mondays only
    nxt = next_fire(sched, now)
    assert nxt.weekday() == 0                        # next Monday
    assert nxt > now


def test_is_due_true_at_or_after_time_on_allowed_day():
    now = _dt.datetime(2026, 11, 24, 7, 30)          # Tuesday
    sched = Schedule(time="07:00", days=())          # every day
    assert is_due(sched, now, last_fired="") is True


def test_is_due_false_before_time():
    now = _dt.datetime(2026, 11, 24, 6, 59)
    sched = Schedule(time="07:00", days=())
    assert is_due(sched, now, last_fired="") is False


def test_is_due_false_on_disallowed_day():
    now = _dt.datetime(2026, 11, 24, 8, 0)           # Tuesday
    sched = Schedule(time="07:00", days=(0,))        # Mondays
    assert is_due(sched, now, last_fired="") is False


def test_is_due_false_when_already_fired_today():
    now = _dt.datetime(2026, 11, 24, 8, 0)
    sched = Schedule(time="07:00", days=())
    assert is_due(sched, now, last_fired="2026-11-24") is False


def test_humanize_when_reads_back():
    assert humanize_when(Schedule(time="07:00", days=())) == "setiap hari 07:00"
    assert humanize_when(Schedule(time="19:30", days=(0,))) == "setiap senin 19:30"


# ── store ────────────────────────────────────────────────────────────────────

def _routine(rid="r1", time="07:00", payload="bacakan ringkasan"):
    return Routine(id=rid, name="Ringkasan",
                   schedule=Schedule(time=time, days=()),
                   payload=payload, enabled=True)


def test_store_roundtrips_a_routine(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine())
    loaded = store.all()
    assert len(loaded) == 1
    assert loaded[0].name == "Ringkasan"
    assert loaded[0].schedule.time == "07:00"
    assert loaded[0].payload == "bacakan ringkasan"


def test_store_refuses_duplicate_id(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine(rid="r1"))
    again = store.add(_routine(rid="r1", payload="berbeda"))
    assert len(store.all()) == 1
    # The existing one is returned unchanged, not overwritten.
    assert store.all()[0].payload == "bacakan ringkasan"
    assert again.id == "r1"


def test_store_remove_and_toggle(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine())
    assert store.remove("r1") is True
    assert store.remove("r1") is False
    store.add(_routine())
    toggled = store.set_enabled("r1", False)
    assert toggled is not None and toggled.enabled is False
    assert store.get("r1").enabled is False


def test_store_mark_fired_persists(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine())
    store.mark_fired("r1", "2026-11-24")
    assert store.get("r1").last_fired == "2026-11-24"


def test_store_corrupt_file_reads_empty(tmp_path):
    path = tmp_path / "routines.json"
    path.write_text("{ not json", encoding="utf-8")
    store = RoutineStore(path)
    assert store.all() == []                       # no crash, no raise


def test_store_missing_file_is_empty(tmp_path):
    store = RoutineStore(tmp_path / "absent.json")
    assert store.all() == []


# ── scheduler ───────────────────────────────────────────────────────────────

def test_scheduler_fires_only_due_routines(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine(rid="morning", time="07:00"))
    store.add(_routine(rid="evening", time="19:00"))

    fired: list[str] = []
    # Clock is 08:00 on 2026-11-24: morning is due, evening is not.
    clock = lambda: _dt.datetime(2026, 11, 24, 8, 0)
    sched = RoutineScheduler(store, lambda r: fired.append(r.id),
                             clock=clock)
    result = sched.tick_once()

    assert [r.id for r in result] == ["morning"]
    assert fired == ["morning"]


def test_scheduler_does_not_fire_twice_on_second_tick(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine(rid="morning", time="07:00"))
    fired: list[str] = []
    sched = RoutineScheduler(
        store, lambda r: fired.append(r.id),
        clock=lambda: _dt.datetime(2026, 11, 24, 8, 0))
    sched.tick_once()
    sched.tick_once()                              # same "now", same day
    assert fired == ["morning"]                    # stamped, not re-fired


def test_scheduler_skips_disabled(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine(rid="off", time="07:00"))
    store.set_enabled("off", False)
    fired: list[str] = []
    sched = RoutineScheduler(
        store, lambda r: fired.append(r.id),
        clock=lambda: _dt.datetime(2026, 11, 24, 8, 0))
    sched.tick_once()
    assert fired == []


def test_scheduler_on_fire_error_does_not_stop_others(tmp_path):
    store = RoutineStore(tmp_path / "routines.json")
    store.add(_routine(rid="bad", time="07:00"))
    store.add(_routine(rid="good", time="07:00"))
    fired: list[str] = []

    def on_fire(r):
        if r.id == "bad":
            raise RuntimeError("boom")
        fired.append(r.id)

    sched = RoutineScheduler(
        store, on_fire, clock=lambda: _dt.datetime(2026, 11, 24, 8, 0))
    result = sched.tick_once()
    # Both were due; the bad one raised but the good one still fired.
    assert [r.id for r in result] == ["bad", "good"]
    assert fired == ["good"]
