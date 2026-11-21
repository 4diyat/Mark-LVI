"""The three-level policy, and the one default that must never soften.

The level a tool gets decides whether the user is asked before their files move
or their money leaves. These tests pin the classification, the escalation that
protects the middle level, and the ordering helper the UI reads.
"""
from __future__ import annotations

import pytest

from core import risk_policy
from core.risk_policy import Decision, MEDIUM, RISKY, SAFE


def test_a_read_only_tool_runs_without_asking():
    decision = risk_policy.decide("web_search")
    assert decision.level == SAFE
    assert decision.allowed is True
    assert decision.needs_confirm is False


def test_an_irreversible_tool_must_be_confirmed():
    decision = risk_policy.decide("send_message")
    assert decision.level == RISKY
    assert decision.allowed is False
    assert decision.needs_confirm is True


def test_a_medium_action_with_an_undo_stays_medium():
    decision = risk_policy.decide("file_move", undo_registered=True)
    assert decision.level == MEDIUM
    assert decision.allowed is True
    assert decision.needs_undo is True


def test_a_medium_action_without_an_undo_is_escalated_not_allowed():
    """The middle level PROMISES a way back. Breaking that promise silently is
    worse than asking, so the missing undo raises the level."""
    decision = risk_policy.decide("file_move", undo_registered=False)
    assert decision.level == RISKY
    assert decision.allowed is False
    assert "no undo" in decision.reason
    assert decision.needs_confirm is True


def test_an_unknown_tool_defaults_to_risky_not_safe():
    """A plugin or a typo must not slip through the unconfirmed path."""
    decision = risk_policy.decide("some_tool_from_the_future")
    assert decision.level == RISKY
    assert decision.needs_confirm is True


def test_an_empty_name_is_not_safe_either():
    assert risk_policy.decide("").level == RISKY
    assert risk_policy.level_of(None) == RISKY


def test_a_declared_level_beats_the_built_in_one():
    assert risk_policy.register("web_search", "risky") is True
    try:
        assert risk_policy.level_of("web_search") == RISKY
        assert risk_policy.decide("web_search").needs_confirm is True
    finally:
        risk_policy._extra.pop("web_search", None)


def test_a_declaration_with_an_unknown_level_is_refused():
    assert risk_policy.register("web_search", "harmless") is False
    assert risk_policy.register("", "safe") is False
    assert risk_policy.level_of("web_search") == SAFE


def test_the_ordering_helper_treats_unknown_input_as_the_strict_end():
    assert risk_policy.is_at_least(RISKY, MEDIUM) is True
    assert risk_policy.is_at_least(SAFE, MEDIUM) is False
    assert risk_policy.is_at_least("nonsense", MEDIUM) is True
    assert risk_policy.is_at_least(MEDIUM, "nonsense") is True


def test_unregistered_names_the_actions_that_would_fall_through():
    unknown = risk_policy.unregistered(["web_search", "made_up_tool"])
    assert unknown == ["made_up_tool"]


def test_the_snapshot_includes_runtime_declarations():
    risk_policy.register("tool_registry_probe", "safe")
    try:
        assert risk_policy.registered()["tool_registry_probe"] == SAFE
    finally:
        risk_policy._extra.pop("tool_registry_probe", None)


@pytest.mark.parametrize("level", [SAFE, MEDIUM, RISKY])
def test_every_level_has_a_reason(level):
    """A level with no stated reason is how a classification rots."""
    assert risk_policy._REASON[level]


def test_no_tool_is_declared_at_two_levels():
    names = [*risk_policy._SAFE, *risk_policy._MEDIUM, *risk_policy._RISKY]
    assert len(names) == len(set(names))


def test_a_decision_is_immutable():
    decision: Decision = risk_policy.decide("web_search")
    with pytest.raises(Exception):
        decision.level = RISKY  # type: ignore[misc]
