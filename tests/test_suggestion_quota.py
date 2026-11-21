"""The daily suggestion budget: counted, visible, and reset only by the date.

The failure this guards is quiet: three suggestions a day is a promise, and an
off-by-one or a rolling window turns it into four without anybody noticing.
"""
from __future__ import annotations

import datetime as dt
import json
import threading

import pytest

from core import suggestion_quota
from core.suggestion_quota import SuggestionQuota


@pytest.fixture
def counter(tmp_path):
    return SuggestionQuota(limit=3, path=str(tmp_path / "suggestions.json"))


def test_the_budget_is_spent_one_at_a_time(counter):
    assert counter.allows() is True
    assert counter.take() is True
    assert counter.used == 1
    assert counter.remaining == 2


def test_the_fourth_suggestion_in_a_day_is_refused(counter):
    assert [counter.take() for _ in range(3)] == [True, True, True]
    assert counter.take() is False
    assert counter.remaining == 0
    assert counter.allows() is False


def test_allows_does_not_spend(counter):
    """Checking is not taking; the caller asks before it builds a suggestion."""
    for _ in range(5):
        assert counter.allows() is True
    assert counter.used == 0


def test_a_refund_returns_one(counter):
    counter.take()
    counter.take()
    counter.refund()
    assert counter.used == 1
    assert counter.remaining == 2


def test_a_refund_on_an_empty_counter_does_not_go_negative(counter):
    counter.refund()
    assert counter.used == 0


def test_a_refund_of_the_only_used_slot_actually_returns_it(counter):
    """The boundary the guard exists for: one used, refund to zero.

    A `> 0` written as `> 1` passes the empty-counter test above (both leave it
    at 0) and silently refuses to give back the last suggestion.
    """
    counter.take()
    assert counter.used == 1
    counter.refund()
    assert counter.used == 0
    assert counter.remaining == 3


def test_the_count_survives_a_restart(tmp_path):
    path = str(tmp_path / "suggestions.json")
    first = SuggestionQuota(limit=3, path=path)
    first.take()
    first.take()
    second = SuggestionQuota(limit=3, path=path)
    assert second.used == 2
    assert second.remaining == 1


def test_the_stored_file_holds_nothing_but_a_date_and_a_count(tmp_path):
    """The quota must not become a second, unmanaged record of the user."""
    path = tmp_path / "suggestions.json"
    counter = SuggestionQuota(limit=3, path=str(path))
    counter.take()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"date", "used"}
    assert data["used"] == 1


def test_a_new_day_starts_a_fresh_budget(tmp_path, monkeypatch):
    path = str(tmp_path / "suggestions.json")
    counter = SuggestionQuota(limit=3, path=path)
    for _ in range(3):
        counter.take()
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    monkeypatch.setattr(suggestion_quota, "_today", lambda: tomorrow.isoformat())
    assert counter.allows() is True
    assert counter.used == 0
    assert counter.take() is True


def test_a_corrupt_file_gives_a_fresh_day_rather_than_an_error(tmp_path):
    path = tmp_path / "suggestions.json"
    path.write_text("{not json", encoding="utf-8")
    counter = SuggestionQuota(limit=3, path=str(path))
    assert counter.used == 0
    assert counter.take() is True


def test_a_file_from_another_day_is_ignored_on_load(tmp_path):
    """Not just `used`: the stored DATE must be replaced too, or the first
    `_roll()` after load would compare today against a stale date forever."""
    path = tmp_path / "suggestions.json"
    path.write_text(json.dumps({"date": "2001-01-01", "used": 3}), encoding="utf-8")
    counter = SuggestionQuota(limit=3, path=str(path))
    assert counter.used == 0
    # `_roll()` repairs the date lazily, so checking it through a public
    # property cannot tell a fixed loader from a broken one. Assert the loader
    # directly: it must return today's date, not the stale one on disk.
    path.write_text(json.dumps({"date": "2001-01-01", "used": 3}), encoding="utf-8")
    assert counter._load() == (dt.date.today().isoformat(), 0)


def test_a_negative_or_garbage_count_cannot_grant_extra_budget(tmp_path):
    path = tmp_path / "suggestions.json"
    path.write_text(json.dumps({"date": dt.date.today().isoformat(), "used": -5}),
                    encoding="utf-8")
    counter = SuggestionQuota(limit=3, path=str(path))
    assert counter.used == 0


def test_an_unwritable_directory_does_not_raise(tmp_path):
    """A counter that cannot be saved must not take down the suggestion path."""
    counter = SuggestionQuota(limit=3, path=str(tmp_path / "missing" / "deep" / "s.json"))
    assert counter.take() is True


def test_a_limit_of_zero_allows_nothing(tmp_path):
    """Setting the daily cap to zero must mean zero, not 'unlimited'."""
    counter = SuggestionQuota(limit=0, path=str(tmp_path / "suggestions.json"))
    assert counter.allows() is False
    assert counter.take() is False


def test_reset_clears_today(tmp_path):
    path = str(tmp_path / "suggestions.json")
    counter = SuggestionQuota(limit=3, path=path)
    counter.take()
    counter.reset()
    assert counter.used == 0


def test_take_is_atomic_across_threads(tmp_path):
    """Two schedulers sharing one budget must not both spend the last slot."""
    counter = SuggestionQuota(limit=3, path=str(tmp_path / "suggestions.json"))
    granted = []

    def worker():
        granted.append(counter.take())

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in granted if g) == 3


def test_the_shared_counter_is_one_object():
    suggestion_quota.reset_shared()
    first = suggestion_quota.shared()
    assert suggestion_quota.shared() is first
    suggestion_quota.reset_shared()
    assert suggestion_quota.shared() is not first
