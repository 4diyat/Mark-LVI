"""Aktif / Fokus / Senyap — and the rule that a held suggestion is never lost.

The panel promises "3 tertahan · akan muncul setelahnya". That sentence is the
contract these tests hold the module to.
"""
from __future__ import annotations

import pytest

from core import presence_mode
from core.presence_mode import ACTIVE, FOCUS, MODES, QUIET


@pytest.fixture(autouse=True)
def fresh():
    presence_mode.reset()
    presence_mode.bind(None, None)
    yield
    presence_mode.reset()
    presence_mode.bind(None, None)


def test_the_default_mode_is_active():
    assert presence_mode.current() == ACTIVE


def test_an_unknown_mode_is_refused():
    assert presence_mode.set_mode("invisible") is False
    assert presence_mode.current() == ACTIVE


def test_focus_holds_rather_than_drops():
    presence_mode.set_mode(FOCUS)
    assert presence_mode.offer("Anggaran lewat plafon") == "hold"
    assert presence_mode.held_count() == 1


def test_quiet_drops_because_the_user_asked_for_silence():
    presence_mode.set_mode(QUIET)
    assert presence_mode.offer("anything") == "drop"
    assert presence_mode.held_count() == 0


def test_active_shows_immediately():
    assert presence_mode.offer("anything") == "show"


def test_held_items_come_back_in_the_order_they_arrived():
    presence_mode.set_mode(FOCUS)
    presence_mode.offer("first")
    presence_mode.offer("second")
    presence_mode.set_mode(ACTIVE)
    assert presence_mode.take_held() == ["first", "second"]


def test_leaving_focus_requires_a_drain_not_a_loss():
    """Switching mode must not silently delete what was held."""
    presence_mode.set_mode(FOCUS)
    presence_mode.offer("kept")
    presence_mode.set_mode(ACTIVE)
    assert presence_mode.held_count() == 1
    assert presence_mode.take_held() == ["kept"]


def test_take_held_empties_the_queue():
    presence_mode.set_mode(FOCUS)
    presence_mode.offer("a")
    presence_mode.take_held()
    assert presence_mode.held_count() == 0


def test_quiet_refuses_banners_but_still_answers():
    presence_mode.set_mode(QUIET)
    assert presence_mode.allows_banner() is False
    assert presence_mode.should_hold() is False


def test_focus_is_not_quiet():
    presence_mode.set_mode(FOCUS)
    assert presence_mode.allows_banner() is True
    assert presence_mode.should_hold() is True


def test_the_mode_is_read_from_the_bound_store_when_present():
    presence_mode.bind(read=lambda: "focus", write=None)
    assert presence_mode.current() == FOCUS


def test_a_bad_stored_value_does_not_blank_the_mode():
    presence_mode.bind(read=lambda: "sideways", write=None)
    assert presence_mode.current() == ACTIVE


def test_a_reader_that_raises_is_survivable():
    def boom():
        raise RuntimeError("config unreadable")

    presence_mode.bind(read=boom, write=None)
    assert presence_mode.current() == ACTIVE


def test_the_mode_is_written_when_a_writer_is_bound():
    seen = []
    presence_mode.bind(read=None, write=seen.append)
    assert presence_mode.set_mode(FOCUS) is True
    assert seen == [FOCUS]


def test_a_writer_that_raises_does_not_change_the_answer():
    def boom(_mode):
        raise OSError("read-only config")

    presence_mode.bind(read=None, write=boom)
    assert presence_mode.set_mode(QUIET) is True
    assert presence_mode.current() == QUIET


@pytest.mark.parametrize("mode", MODES)
def test_every_declared_mode_can_be_set(mode):
    assert presence_mode.set_mode(mode) is True
    assert presence_mode.current() == mode
