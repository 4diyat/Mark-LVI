"""The level of one CALL: three tools that are not one level each.

WHY THIS FILE IS THE ONE THAT MATTERS FOR SAFETY
    `computer_settings` is one tool with ~50 actions under it. Classifying it by
    name would either make `volume_up` require a confirmation or let `shutdown`
    through without one, and the registry this replaces had exactly that shape
    of mistake in it already: `shutdown` was a name in a set while the tool the
    model actually calls is `computer_settings(action="shutdown")`.

    Every case below is a pair — same tool, different arguments, different
    answer — because a table that only ever sees one of them cannot be wrong.
"""
from __future__ import annotations

from core import tool_risk
from core.risk_policy import MEDIUM, RISKY, SAFE


def test_shutdown_is_risky_even_though_the_tool_is_called_computer_settings():
    """The name `shutdown` is in risk_policy, and it is NOT the tool name the
    model calls. Without the sub-action table this call would be classified by
    `computer_settings` and land somewhere arbitrary."""
    risk = tool_risk.classify("computer_settings", {"action": "shutdown"})
    assert risk.level == RISKY
    assert risk.action == "shutdown"


def test_volume_up_is_medium_and_its_undo_is_real():
    risk = tool_risk.classify("computer_settings", {"action": "volume_up"})
    assert risk.level == MEDIUM
    assert risk.reversible is True


def test_wifi_is_risky_because_it_cuts_the_assistant_off():
    risk = tool_risk.classify("computer_settings", {"action": "toggle_wifi"})
    assert risk.level == RISKY
    assert "outside" in risk.reason


def test_a_screenshot_is_safe():
    assert tool_risk.classify("computer_settings",
                             {"action": "screenshot"}).level == SAFE


def test_reading_a_file_is_safe_and_deleting_one_is_not_the_same_level():
    assert tool_risk.classify("file_controller", {"action": "read"}).level == SAFE
    delete = tool_risk.classify("file_controller", {"action": "delete"})
    assert delete.level == MEDIUM
    assert delete.reversible is True


def test_running_code_is_risky():
    assert tool_risk.classify("code_helper", {"action": "run"}).level == RISKY


def test_an_unlisted_sub_action_inherits_the_parent_and_says_so():
    """A new action added to computer_settings without a table entry must not
    silently become safe — it takes the parent's level, and the reason says the
    entry is missing so the next person can add it."""
    risk = tool_risk.classify("computer_settings", {"action": "teleport"})
    assert risk.level == RISKY
    assert "no per-action entry" in risk.reason


def test_an_action_name_is_case_and_space_insensitive():
    """The model writes prose into these fields."""
    assert tool_risk.classify("computer_settings",
                              {"action": "  SHUTDOWN "}).level == RISKY


def test_a_missing_action_argument_uses_the_tool_level():
    assert tool_risk.classify("computer_settings", {}).level == RISKY
    assert tool_risk.classify("web_search", None).level == SAFE


def test_a_tool_main_py_dispatches_directly_is_known():
    """These never reach the action registry, so without this table they would
    fall through to risky — and `recall_memory` would ask for confirmation to
    read a memory file."""
    assert tool_risk.classify("recall_memory").level == SAFE
    assert tool_risk.classify("recall_history").level == SAFE
    assert tool_risk.classify("undo").level == MEDIUM


def test_undo_does_not_promise_a_reversible_undo():
    """`undo` reverses something already done; it does not register its own."""
    assert tool_risk.classify("undo").reversible is False


def test_an_unknown_tool_is_risky():
    assert tool_risk.classify("some_future_tool").level == RISKY
    assert tool_risk.classify("").level == RISKY


def test_the_desktop_name_matches_the_registry():
    """`desktop` is what the model calls; `desktop_control` is the file name.

    The level is `risky` on purpose: `risk_policy` calls `desktop` medium and
    nothing in actions/desktop.py pushes an undo, so the medium-without-undo
    rule escalates it. That escalation is the rule working, not a missing entry.
    """
    risk = tool_risk.classify("desktop_control")
    assert risk.tool == "desktop"
    assert risk.level == RISKY
    assert "no undo" in risk.reason


def test_the_audit_name_includes_the_action_only_when_there_is_one():
    assert tool_risk.classify("computer_settings",
                              {"action": "mute"}).audit_name == "computer_settings:mute"
    assert tool_risk.classify("web_search").audit_name == "web_search"


def test_every_risky_sub_action_is_also_named_in_the_reversibility_tables_once():
    """A sub-action must not be both reversible and forbidden-looking without
    the stricter answer winning — if one ever is, the tables disagree."""
    for tool, risky in tool_risk._RISKY_ACTIONS.items():
        safe = tool_risk._SAFE_ACTIONS.get(tool, frozenset())
        assert not (risky & safe), f"{tool} lists an action as both risky and safe"
    for tool, risky in tool_risk._RISKY_ACTIONS.items():
        for action in risky:
            assert tool_risk.classify(tool, {"action": action}).level == RISKY


def test_every_safe_sub_action_really_is_safe():
    for tool, actions in tool_risk._SAFE_ACTIONS.items():
        for action in actions:
            assert tool_risk.classify(tool, {"action": action}).level == SAFE


def test_every_reversible_sub_action_is_medium_or_stricter():
    """Reversible does not mean harmless. An entry listed in both tables takes
    the risky answer, and that is the only allowed exception."""
    for tool, actions in tool_risk._REVERSIBLE_ACTIONS.items():
        risky = tool_risk._RISKY_ACTIONS.get(tool, frozenset())
        for action in actions:
            level = tool_risk.classify(tool, {"action": action}).level
            if action in risky:
                assert level == RISKY, f"{tool}:{action} is risky but read as {level}"
            else:
                assert level == MEDIUM, (
                    f"{tool}:{action} claims a real undo but does not classify as medium")


def test_reversible_and_risky_can_both_be_true_and_risky_wins():
    """`organize_desktop` pushes an undo AND moves every file on the desktop.
    Reversibility and alarm are different axes; the stricter one decides."""
    risk = tool_risk.classify("file_controller", {"action": "organize_desktop"})
    assert risk.level == RISKY
    assert risk.reversible is False


def test_is_reversible_answers_for_the_call_not_the_tool():
    assert tool_risk.is_reversible("file_controller", {"action": "move"}) is True
    assert tool_risk.is_reversible("file_controller", {"action": "find"}) is False


def test_classify_never_raises_on_garbage():
    for args in (None, {}, {"action": None}, {"action": 42}, {"action": ["x"]}):
        assert tool_risk.classify("computer_settings", args).level in (
            SAFE, MEDIUM, RISKY)
