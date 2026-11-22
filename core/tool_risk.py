"""core/tool_risk.py — the level of one CALL, not just one tool.

WHY `core/risk_policy` WAS NOT ENOUGH
    `risk_policy` maps a TOOL to a level, and that shape does not survive
    contact with the tools this repo actually has:

        computer_settings   one tool, ~50 actions. `volume_up` is trivially
                            reversible; `shutdown` is not; `toggle_wifi` cuts
                            the connection the assistant is talking over.
        file_controller     one tool, `delete` and `read` under the same name.
        code_helper         one tool that runs a file when asked to.

    Classifying those three by tool name would either make reading a file
    require a confirmation or make deleting one skip it, and both are wrong.
    So the unit here is (tool, arguments): a tool may declare the name of its
    own sub-action and this module maps that instead.

WHY A REVERSIBILITY TABLE AT ALL
    `risk_policy` refuses to let a `medium` action run without a registered
    undo, which is the right rule and would refuse almost everything if the
    registry stayed tool-level: `file_controller` pushes an undo only for the
    actions that can be undone. The table below is the missing half — the
    actions whose undo is real, named explicitly, so `medium` means something
    specific rather than "trust me".

WHAT THIS MODULE IS NOT
    It does not run anything, and it is not the last word on dangerousness: a
    tool that already gates itself through `core.confirm` (four actions do) is
    left alone by the caller, because a second confirmation for the same
    shutdown is how a user learns to dismiss them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from core import risk_policy
from core.risk_policy import MEDIUM, RISKY, SAFE

# Tools whose arguments name the real operation.
_SUB_ACTION_KEY = {
    "computer_settings": "action",
    "file_controller": "action",
    "code_helper": "action",
}

# (tool, sub-action) pairs that push a real undo closure onto core.undo, so a
# medium classification is a promise the code keeps. Read from the actions
# themselves — `file_controller.delete_file` pushes `_restore_from_trash`,
# `computer_settings.volume_*` pushes the previous level, and so on.
_REVERSIBLE_ACTIONS = {
    "computer_settings": frozenset({
        "volume_up", "volume_down", "volume_set", "mute", "unmute",
        "toggle_mute", "brightness_up", "brightness_down", "dark_mode",
    }),
    "file_controller": frozenset({
        "create_file", "create_folder", "move", "copy", "rename", "write",
        "organize_desktop", "delete",
    }),
    "code_helper": frozenset({"edit", "optimize"}),
    # `organize_desktop` is listed in `_RISKY_ACTIONS` as well; the risky check
    # runs first there, so the stricter answer wins. Keeping it in both tables
    # is what makes the disagreement visible instead of implicit.
}

# Sub-actions that are read-only, so they never need to be asked about even
# though their parent tool is not obviously harmless.
_SAFE_ACTIONS = {
    "computer_settings": frozenset({"screenshot", "open_settings", "file_explorer"}),
    "file_controller": frozenset({"list", "read", "find", "info", "largest",
                                  "disk_usage"}),
    "code_helper": frozenset({"syntax", "check", "review"}),
}

# Sub-actions that are irreversible or reach outside the machine. Kept short and
# explicit: this list is the one a reviewer reads.
_RISKY_ACTIONS = {
    "computer_settings": frozenset({"shutdown", "restart", "toggle_wifi",
                                    "open_run", "task_manager"}),
    "file_controller": frozenset({"organize_desktop"}),
    "code_helper": frozenset({"run"}),
}
# `organize_desktop` is in both tables on purpose: it pushes an undo (hence
# reversible) but moves every file on the desktop at once. Reversible and
# frightening are different axes, and the stricter answer wins below.

# Tools `main.py` dispatches directly, which therefore never reach the action
# registry and would otherwise fall through to `risky`.
#
# `writes` says whether the tool can leave a change behind. It is NOT the same
# as reversible: `undo` changes state and cannot be undone, so it is `medium`
# and not reversible. Collapsing the two is how a table stops being readable.
_STATELESS = {
    "recall_memory":  (SAFE,   False),
    "recall_history": (SAFE,   False),
    "system_status":  (SAFE,   False),
    "screen_process": (SAFE,   False),   # reads the screen; nothing is changed
    "undo":           (MEDIUM, False),   # reverses something; cannot reverse itself
    "manage_monitor": (MEDIUM, False),   # changes a display setting
    "save_memory":    (MEDIUM, False),   # overwrites a stored value
}

# Name changes that would otherwise be silent mismatches. `risk_policy` has
# known these tools by other names since before the registry existed, and a
# rename is exactly the kind of thing that turns a `safe` into an accidental
# `risky` without anybody noticing.
_ALIASES = {
    "desktop_control": "desktop",
}


@dataclass(frozen=True)
class CallRisk:
    """The level of one specific call, and what it was derived from."""

    tool: str
    action: str
    level: str
    reason: str
    reversible: bool

    @property
    def audit_name(self) -> str:
        """What to write in the audit log: `tool` or `tool:action`."""
        return f"{self.tool}:{self.action}" if self.action else self.tool


def sub_action(tool: str, args: Mapping | None) -> str:
    """The name of the sub-action this call is for, or '' if the tool has none."""
    key = _SUB_ACTION_KEY.get(tool)
    if not key or not isinstance(args, Mapping):
        return ""
    value = args.get(key)
    return str(value or "").strip().lower()


def classify_plugin(tool: str, declared: str) -> CallRisk:
    """The level of a PLUGIN call, from the level its manifest claims.

    WHY A PLUGIN IS NOT CLASSIFIED LIKE AN ACTION
        An action lives in this repository and `classify` knows its name. A
        plugin may come from anywhere, and `classify` has never heard of it —
        so it would answer `risky` for every plugin, forever, and the honest
        ones (`currency_rates`, `market_price`, the notes readers) would ask
        the user for permission to read a public exchange rate. That is the
        erosion path: a banner nobody needs is a banner nobody reads.

    WHY AN UNSTATED LEVEL IS STILL `risky`
        A plugin that does not say what it does is exactly the case the gate
        exists for. Omission must not be an escape, so `declared` empty falls
        through to `risky` with a reason that names the omission — the user can
        then fix the plugin by adding one line to its manifest.

    A plugin CANNOT claim better than `safe`, and `safe` is not taken on trust:
    `core.plugin_manifest.verify` refuses a manifest whose declared permissions
    disagree with what the source actually imports, so a plugin that claims
    `safe` while importing `subprocess` never reaches this function.
    """
    name = str(tool or "").strip()
    level = str(declared or "").strip().lower()
    if level in (SAFE, MEDIUM):
        return CallRisk(name, "", level,
                        "the plugin's manifest declares it", reversible=False)
    if level == RISKY:
        return CallRisk(name, "", RISKY,
                        "the plugin's manifest declares it risky", reversible=False)
    return CallRisk(name, "", RISKY,
                    "the plugin's manifest does not state a level", reversible=False)


def classify(tool: str, args: Mapping | None = None) -> CallRisk:
    """The level of one call. Never raises; unknown input is `risky`.

    Order of resolution, and why in this order:

      1. the sub-action's explicit table, because it is the most specific thing
         anybody has said;
      2. a tool-level entry in `risk_policy`, which is the registry that phases
         and plugins extend;
      3. `risky`, because a forgotten name must be noisy and safe rather than
         quiet and wrong.
    """
    name = str(tool or "").strip()
    mapped = _ALIASES.get(name, name)   # the registry knows some tools by file name
    action = sub_action(mapped, args)

    if action:
        if action in _RISKY_ACTIONS.get(mapped, ()):
            return CallRisk(mapped, action, RISKY,
                            "that action is irreversible or reaches outside the machine",
                            reversible=False)
        if action in _SAFE_ACTIONS.get(mapped, ()):
            return CallRisk(mapped, action, SAFE, "read-only", reversible=False)
        if action in _REVERSIBLE_ACTIONS.get(mapped, ()):
            return CallRisk(mapped, action, MEDIUM,
                            "changes state, and the action registers an undo",
                            reversible=True)
        # An action nobody listed is `risky`, whatever its parent tool is.
        #
        # Taking the parent's level here looked tidier and was a hole: every
        # parent in `_SUB_ACTION_KEY` is `risky` today, so the branch was
        # unreachable and a mutation that removed the escalation changed
        # nothing. Worse, the day one of those tools is relaxed to `medium`,
        # every unlisted action under it would inherit that and run silently.
        # "Not listed" is exactly the forgotten-entry case, so it gets the
        # strict answer and says why.
        return CallRisk(mapped, action, RISKY,
                        f"no per-action entry for '{action}' — treated as risky",
                        reversible=False)

    if mapped in _STATELESS:
        level, reversible = _STATELESS[mapped]
        return CallRisk(mapped, "", level,
                        "dispatched by main.py, classified here", reversible)

    decision = risk_policy.decide(mapped, undo_registered=False)
    # A tool-level `medium` in `risk_policy` without one of the two tables above
    # has no demonstrated undo, so `decide` already escalated it to risky.
    return CallRisk(mapped, "", decision.level, decision.reason, reversible=False)


def is_reversible(tool: str, args: Mapping | None = None) -> bool:
    """Whether the undo stack can walk this specific call back."""
    return classify(tool, args).reversible
