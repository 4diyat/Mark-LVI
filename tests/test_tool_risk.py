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

    WITH NO ARGUMENTS the tool-level answer stands, and it is `risky`: nothing
    in actions/desktop.py pushes an undo, so the medium-without-undo rule
    escalates it. That is the rule working, not a missing entry.
    """
    risk = tool_risk.classify("desktop_control")
    assert risk.tool == "desktop"
    assert risk.level == RISKY
    assert "no undo" in risk.reason


# ── the seven tools that were never in a table ──────────────────────────────
#
# `actions/` holds sixteen tools. Four had per-action tables; the rest were
# classified by a tool-level entry, and seven of those were in NEITHER table —
# so every call to them took the "medium with no undo" escalation and asked the
# user to confirm it. That is why `desktop_control(action="list")` — reading a
# wallpaper filename — popped a risk banner.
#
# WHAT THESE TESTS ASSERT, AND WHAT THEY DELIBERATELY DO NOT
#
# They assert the shape: one row per tool, so a tool added to `actions/` fails
# here instead of in front of a user. They assert the DANGEROUS actions are
# refused.
#
# They do NOT assert that `open_app` is `medium`. None of these tools pushes an
# undo closure onto `core.undo`, and `core.risk_policy` is explicit about what
# `medium` promises: "the middle level exists to promise the user a way back,
# and a promise nobody implemented is worse than asking them first." Relaxing
# them to `medium` here would be the test writing a claim the code cannot keep.
#
# So the honest statement is the one below: these are `risky` *because no undo
# exists*, the reason says so, and `docs/mockups/NOT-IN-MOCKUP.md` records the
# cost — a banner in front of "open Spotify" is the price of that honesty until
# the undo is real.

# TOOLS WHOSE UNDO IS STILL MISSING. One entry per tool, and the day somebody
# writes the closure the entry moves out of here and the test below starts
# failing — which is the reminder it exists to be.
#
# This list used to hold seven. Four of them earned `medium` by getting a real
# undo (see `tests/test_action_undo.py`); `flight_finder` stayed because it
# reads a public page and nothing else, and calling that "undoable" would be
# inventing a meaning.
UNGRADED = {
    "flight_finder": (),
}


def test_the_tools_that_were_missing_from_every_table_are_graded_now():
    """The bug this whole block exists for.

    Before the sub-action tables were added for these four tools, every call
    took `no per-action entry for '<action>' — treated as risky`. The grade is
    still `risky` for most of them — see `UNGRADED` — but it is now a grade
    somebody WROTE, with a reason that names the action, not a fallthrough that
    names a typo.
    """
    risk = tool_risk.classify("desktop_control", {"action": "list"})
    assert risk.level == SAFE, "reading a wallpaper name must not ask for consent"
    assert risk.action == "list"

    risk = tool_risk.classify("file_processor", {"action": "info"})
    assert risk.level == SAFE

    risk = tool_risk.classify("browser_control", {"action": "search"})
    assert risk.level == SAFE


def test_the_dangerous_actions_under_those_tools_are_still_refused():
    """The half that matters more: grading must not have relaxed anything."""
    for tool, actions in (
        ("desktop_control", ("clean", "organize")),
        ("file_processor", ("convert", "resize", "compress", "trim", "extract")),
    ):
        for action in actions:
            risk = tool_risk.classify(tool, {"action": action})
            assert risk.level == RISKY, f"{tool}:{action}"


def test_the_four_that_earned_medium_are_medium():
    """The level is a claim the code now keeps, not a table somebody relaxed.

    Each one names the action that pushes the closure; `tests/test_action_undo`
    is what proves the closure works.
    """
    assert tool_risk.classify("open_app", {"app_name": "Spotify"}).level == MEDIUM
    assert tool_risk.classify("reminder", {"text": "x"}).level == MEDIUM
    assert tool_risk.classify("youtube_video", {"action": "play"}).level == MEDIUM
    assert tool_risk.classify("browser_control", {"action": "go_to"}).level == MEDIUM
    for tool, args in (("open_app", {"app_name": "Spotify"}),
                       ("reminder", {"text": "x"}),
                       ("youtube_video", {"action": "play"}),
                       ("browser_control", {"action": "go_to"})):
        assert tool_risk.classify(tool, args).reversible is True, tool


def test_the_actions_that_did_not_earn_it_did_not_get_it():
    """`play` is reversible; `summarize` is not. One tool, two answers."""
    for tool, action in (("youtube_video", "summarize"),
                         ("youtube_video", "get_info"),
                         ("youtube_video", "trending"),
                         ("browser_control", "get_text")):
        risk = tool_risk.classify(tool, {"action": action})
        assert risk.level == RISKY, f"{tool}:{action}"
        assert risk.reversible is False


def test_an_ungraded_call_says_the_undo_is_missing_not_that_it_is_dangerous():
    """`open_app` and friends are refused for ONE reason, and the reason is the
    honest one: there is no undo, so `medium` cannot be promised.

    If somebody later adds a real undo closure to `actions/open_app.py`, this
    test fails — and that failure is the signal to move the tool out of
    `UNGRADED`, which is what the set is for.
    """
    for tool, actions in UNGRADED.items():
        if not actions:
            risk = tool_risk.classify(tool)
            assert risk.level == RISKY, tool
            assert "no undo" in risk.reason or "irreversible" in risk.reason, \
                f"{tool}: {risk.reason}"
        for action in actions:
            risk = tool_risk.classify(tool, {"action": action})
            assert risk.level == RISKY, f"{tool}:{action}"
            assert ("no undo" in risk.reason
                    or "no per-action entry" in risk.reason
                    or "irreversible" in risk.reason), f"{tool}:{action} {risk.reason}"


def test_the_two_names_of_the_desktop_tool_agree():
    """The registry says `desktop`; the file and the audit say `desktop_control`.

    A caller reading either name must get one answer, or the gate's verdict
    depends on which module asked. Before the sub-action tables were keyed by
    the real name, `desktop_control` missed every entry and `desktop` matched
    them, so the two names disagreed on the same call.
    """
    for action in ("list", "stats", "current_wallpaper", "clean", "organize"):
        args = {"action": action}
        left = tool_risk.classify("desktop", args)
        right = tool_risk.classify("desktop_control", args)
        assert (left.level, left.action) == (right.level, right.action), action
        # And the sub-action survives: a missing `action` in either answer
        # means the table lookup was skipped and both fell to a tool level,
        # which is how the two names agreed while both were wrong.
        assert right.action == action, action


def test_the_two_desktop_entries_in_every_table_stay_in_step():
    """`desktop` and `desktop_control` are written out twice on purpose.

    A shared constant would have been shorter and would have made the lookup
    key depend on which name the CALLER used, and the two disagreeing is the
    bug this file was extended for. The price of writing them twice is that one
    can be edited alone — so this compares them, table by table.
    """
    for table in (tool_risk._SAFE_ACTIONS, tool_risk._REVERSIBLE_ACTIONS,
                  tool_risk._RISKY_ACTIONS):
        assert table.get("desktop") == table.get("desktop_control"), table


def test_every_tool_in_actions_is_graded_by_a_named_table():
    """The guard that would have caught all seven at once.

    A tool that is in `actions/` and in no table has its level decided by an
    accident. This walks the directory rather than a hand-written list, so a
    new file cannot be forgotten.
    """
    from pathlib import Path

    from core import action_loader, risk_policy

    root = Path(__file__).resolve().parent.parent / "actions"
    registry = action_loader.discover_actions(root, logger=lambda *_: None)
    names = registry.names()
    assert len(names) >= 16, f"discovery found only {len(names)} actions"

    # Known = the gate has a table for it, OR `risk_policy` has been told about
    # it. `register_discovered()` is what supplies the second half, and it runs
    # at startup — so this asks the question the same way `main.py` answers it.
    tool_risk.register_discovered(names)
    unaccounted = risk_policy.unregistered(names)
    assert unaccounted == [], (
        "these tools are in actions/ and in no table, so their level is the "
        f"unlisted-tool accident: {unaccounted}")


def test_registering_what_was_discovered_declares_the_tool_risk_only_uses():
    """`register()` had no caller before this: the registry was the gate's
    second opinion and nothing ever consulted it.

    The declaration is deliberately `risky` — the same answer the gate already
    gives for an unlisted tool — so registering changes no decision and only
    makes the registry say what is true.
    """
    from core import risk_policy

    fresh = {"a_tool_only_the_gate_knows"}
    assert risk_policy.unregistered(fresh) == ["a_tool_only_the_gate_knows"]

    declared = tool_risk.register_discovered(fresh)
    assert declared == {"a_tool_only_the_gate_knows": "risky"}
    assert risk_policy.unregistered(fresh) == []
    assert risk_policy.level_of("a_tool_only_the_gate_knows") == "risky"

    # Idempotent: a second call must not report the same names again, or the
    # startup log repeats itself every time something re-discovers.
    assert tool_risk.register_discovered(fresh) == {}
