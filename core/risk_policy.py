"""core/risk_policy.py — how much of the machine an action is allowed to touch.

WHY A SECOND GATE, WHEN `core/confirm.py` ALREADY EXISTS
    `confirm.py` answers one question: "is this irreversible?". It is a good
    answer and it is not enough. Every action that is not irreversible falls
    through it, so "move 14 files", "run this script" and "read the clipboard"
    were indistinguishable from "open Spotify". The undo stack in `core/undo.py`
    records whatever an action decides to register, which means an action that
    forgets to push a closure becomes silently irreversible — the bad outcome
    arrives with no warning at all.

    This module answers the other question: WHERE on the damage scale the
    action sits, BEFORE it runs. Three levels, one per the product principle:

        safe    read-only, or a change the user can see and redo. runs now.
        medium  changes state, and the action has registered an undo. runs
                now, but the user is told, and `core/undo` can reverse it.
        risky   cannot be undone, or touches something the user cannot see
                (their money, another person, the machine's power state).
                needs a human confirmation from the trusted UI.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
    It does not run anything, log anything secret, or talk to the model. It maps
    a tool name to a level and returns a decision; the caller executes, records
    and (for risky) asks `core.confirm`.

WHY UNKNOWN TOOLS ARE `risky` AND NOT `safe`
    A registry defaults to what is cheap to write, and the cheapest default is
    "allow". An action added by a plugin, a renamed tool, a typo in the registry
    key — all of them would run unconfirmed. Defaulting to the strict end means
    a forgotten entry is noisy and safe, which is the failure mode to choose.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

SAFE, MEDIUM, RISKY = "safe", "medium", "risky"
LEVELS = (SAFE, MEDIUM, RISKY)
_RANK = {level: rank for rank, level in enumerate(LEVELS)}


@dataclass(frozen=True)
class Decision:
    """What the caller should do about one action, and why."""

    action: str
    level: str
    reason: str
    needs_undo: bool = False      # medium: only valid if an undo was registered
    needs_confirm: bool = False   # risky: a human must say yes

    @property
    def allowed(self) -> bool:
        """Whether the action may run without a human in the loop."""
        return not self.needs_confirm


# The registry. Grouped by WHY the level is what it is, because a level with no
# stated reason is how a classification rots: the next person copies the
# neighbouring line instead of thinking about it.
#
# Read-only or trivially reversible. Nothing here leaves the machine in a state
# the user cannot get out of.
_SAFE = frozenset({
    "web_search", "weather_report", "screen_processor", "system_monitor",
    "browser_read", "file_read", "code_syntax", "code_checks", "clipboard_read",
    "window_list", "memory_read", "history_read", "plugin_list",
})

# Changes state, and the change is one the user can walk back — provided the
# action registered an undo. `clipboard_write` is here rather than safe because
# it destroys whatever the user had copied.
_MEDIUM = frozenset({
    "open_app", "desktop", "window_layout", "clipboard_write", "file_move",
    "file_create", "file_write", "code_edit", "dev_agent", "reminder",
    "memory_write", "editor_assist", "video_player", "browser_control",
})

# Irreversible, or visible to somebody other than the user: money, other
# people, the machine's own power state, or deleting something wholesale.
_RISKY = frozenset({
    "send_message", "mt5_trade", "shutdown", "restart", "computer_settings",
    "code_run", "file_delete", "game_updater", "shell", "installer",
    "credential_write", "privacy_erase",
})

_REGISTRY: dict[str, str] = {}
for _level, _names in ((SAFE, _SAFE), (MEDIUM, _MEDIUM), (RISKY, _RISKY)):
    for _name in _names:
        _REGISTRY[_name] = _level

# Runtime additions. A plugin or a phase may register a level for its own tools;
# an explicit entry always beats the default, and can only be READ here.
_extra: dict[str, str] = {}
_lock = threading.Lock()

# Why a given level was chosen, for the audit log. Kept separate from the
# frozensets so the sentence can be written once per level rather than once per
# tool.
_REASON = {
    SAFE: "read-only or trivially reversible",
    MEDIUM: "changes state, reversible with an undo",
    RISKY: "irreversible or visible to somebody other than the user",
}


def register(name: str, level: str) -> bool:
    """Declare the level of a tool that is not in the built-in registry.

    Returns False for an unknown level rather than guessing. Called from plugin
    and phase setup, not from the request path — which is why the lock is cheap.
    """
    level = str(level or "").strip().lower()
    # A blank name is not a registration: it would sit in `_extra` under "" and
    # never match a real tool, while making `registered()` look populated.
    if level not in LEVELS or not str(name or "").strip():
        return False
    with _lock:
        _extra[str(name).strip()] = level
    return True


def level_of(action: str) -> str:
    """The level for `action`, or `risky` when nobody has said what it is."""
    name = str(action or "").strip()
    with _lock:
        level = _extra.get(name)
    if level is not None:
        return level
    return _REGISTRY.get(name, RISKY)


def decide(action: str, undo_registered: bool = False) -> Decision:
    """Classify one action and say what the caller must do about it.

    `undo_registered` is the caller's answer to "did this action push a closure
    onto `core.undo`?". A medium action WITHOUT one is escalated to risky: the
    middle level exists to promise the user a way back, and a promise nobody
    implemented is worse than asking them first.
    """
    name = str(action or "").strip()
    level = level_of(name)
    reason = _REASON[level]

    if level == MEDIUM and not undo_registered:
        return Decision(name, RISKY,
                        "medium action with no undo registered — treated as risky",
                        needs_undo=True, needs_confirm=True)
    if level == RISKY:
        return Decision(name, RISKY, reason, needs_confirm=True)
    if level == MEDIUM:
        return Decision(name, MEDIUM, reason, needs_undo=True)
    return Decision(name, SAFE, reason)


def is_at_least(level: str, threshold: str) -> bool:
    """Whether `level` is at or above `threshold`. Ordering lives in one place."""
    try:
        return _RANK[str(level).lower()] >= _RANK[str(threshold).lower()]
    except KeyError:
        # An unrecognised level on either side is not evidence of safety.
        return True


def registered() -> dict[str, str]:
    """Snapshot of everything known, for the audit log and the UI's risk table."""
    with _lock:
        merged = dict(_REGISTRY)
        merged.update(_extra)
    return merged


def unregistered(actions: Iterable[str]) -> list[str]:
    """Actions that would fall through to `risky`, so a phase can declare them.

    Exists because "unknown means risky" is safe but silent: without this the
    user meets a confirmation dialog for a harmless tool and blames the gate.
    """
    with _lock:
        known = set(_REGISTRY) | set(_extra)
    return sorted({str(a) for a in actions if str(a) not in known})
