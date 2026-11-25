"""Board 14's OS-control switch policy: the physical-confirmation gate.

These test the pure policy in `core.os_control` with no store and no UI. The
gate is the whole point: a bare toggle toward enabling must be refused, a
disable must always proceed, and a no-op must change nothing.
"""
from __future__ import annotations

from core.os_control import (OFF, ON, is_enabled, request, summary)


# ── the gate ────────────────────────────────────────────────────────────────

def test_a_bare_enable_without_confirmation_is_refused():
    """The artboard's sentence: enabling needs a physical keystroke."""
    decision = request(OFF, ON, confirmed=False)
    assert decision.allowed is False
    assert decision.desired is OFF, "a refused change must not claim it moved"
    assert decision.changed is False
    assert "konfirmasi fisik" in decision.reason


def test_a_truthy_string_is_not_a_physical_confirmation():
    """`"yes"` is not the boolean True; a bare toggle must not slip through."""
    decision = request(OFF, ON, confirmed="yes")
    assert decision.allowed is False
    assert decision.desired is OFF


def test_only_the_boolean_true_confirms_an_enable():
    decision = request(OFF, ON, confirmed=True)
    assert decision.allowed is True
    assert decision.desired is ON
    assert decision.changed is True


def test_a_disable_never_needs_confirmation():
    decision = request(ON, OFF, confirmed=False)
    assert decision.allowed is True
    assert decision.desired is OFF
    assert decision.changed is True


def test_a_disable_with_confirmation_is_still_allowed():
    decision = request(ON, OFF, confirmed=True)
    assert decision.allowed is True
    assert decision.desired is OFF


# ── the no-op ───────────────────────────────────────────────────────────────

def test_a_no_op_is_allowed_and_changes_nothing():
    decision = request(OFF, OFF, confirmed=False)
    assert decision.allowed is True
    assert decision.changed is False
    assert decision.desired is OFF


def test_a_no_op_on_an_enabled_switch_is_allowed():
    decision = request(ON, ON, confirmed=False)
    assert decision.allowed is True
    assert decision.changed is False


# ── the decision record ────────────────────────────────────────────────────

def test_a_refused_decision_keeps_the_current_state():
    decision = request(ON, ON, confirmed=False)
    assert decision.current is ON
    assert decision.desired is ON
    assert decision.allowed is True


def test_the_changed_property_tracks_a_real_move():
    assert request(OFF, ON, confirmed=True).changed is True
    assert request(OFF, OFF, confirmed=False).changed is False


# ── the safe read ──────────────────────────────────────────────────────────

def test_a_read_that_raises_is_treated_as_off():
    """An unreadable config must not arm a control the user cannot see."""
    def _boom():
        raise RuntimeError("config file locked")

    assert is_enabled(_boom) is OFF


def test_a_read_returns_the_truthy_state():
    assert is_enabled(lambda: True) is ON
    assert is_enabled(lambda: False) is OFF


# ── the summary sentence ────────────────────────────────────────────────────

def test_the_summary_states_the_state_and_the_gate():
    assert "aktif" in summary(ON)
    assert "nonaktif" in summary(OFF)
    assert "konfirmasi fisik" in summary(OFF)


def test_the_decision_repr_is_informative():
    decision = request(OFF, ON, confirmed=False)
    text = repr(decision)
    assert "current=False" in text and "allowed=False" in text
