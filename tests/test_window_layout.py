"""Board 12's window layout policy: the three-mode arrangement selector.

These test the pure policy in `core.window_layout` with no store and no UI.
The point is honesty about the mode set: an unknown request is refused, a
re-pick changes nothing, and a read that raises or returns garbage falls back
to the artboard's first thumbnail rather than claiming a mode that does not
exist.
"""
from __future__ import annotations

from core.window_layout import (COLUMNS2, COLUMNS3, DEFAULT, FOCUS, MODES,
                                current, is_mode, request, summary)


def test_the_artboard_three_modes_are_the_fixed_set():
    assert MODES == (COLUMNS2, COLUMNS3, FOCUS)
    assert DEFAULT == COLUMNS2


def test_an_unknown_mode_is_refused():
    decision = request(COLUMNS2, "tiled")
    assert decision.allowed is False
    assert decision.desired is COLUMNS2, "a refused request must not change the mode"
    assert decision.changed is False


def test_a_real_mode_change_is_allowed():
    decision = request(COLUMNS2, COLUMNS3)
    assert decision.allowed is True
    assert decision.desired is COLUMNS3
    assert decision.changed is True


def test_re_picking_the_current_mode_changes_nothing():
    decision = request(FOCUS, FOCUS)
    assert decision.allowed is True
    assert decision.changed is False


def test_is_mode_filters_the_set():
    assert is_mode(COLUMNS3) is True
    assert is_mode("tiled") is False
    assert is_mode(None) is False


def test_a_read_that_raises_falls_back_to_the_default():
    def _boom():
        raise RuntimeError("config locked")

    assert current(_boom) is DEFAULT


def test_a_read_returning_an_unknown_value_falls_back():
    assert current(lambda: "tiled") is DEFAULT
    assert current(lambda: COLUMNS3) is COLUMNS3


def test_the_summary_names_the_mode():
    assert "three columns" in summary(COLUMNS3)
    assert "focus" in summary(FOCUS)
    assert "two columns" in summary(COLUMNS2)


def test_the_decision_repr_is_informative():
    decision = request(COLUMNS2, FOCUS)
    text = repr(decision)
    assert "current=columns2" in text and "desired=focus" in text


def test_a_refused_decision_keeps_the_current_mode():
    decision = request(FOCUS, "tiled")
    assert decision.current is FOCUS
    assert decision.desired is FOCUS
    assert decision.allowed is False
