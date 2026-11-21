"""The dashboard layer — widgets lifted OUT of the workspace, all at once.

WHAT THE USER MEANT, AND WHY IT IS NOT WHAT EXISTS
    "Floating widget" already exists in this program: a document can be
    re-parented into a frameless window of its own (`core/floating.py`,
    `ui/floating_documents.py`). That is a WINDOW. The macOS Dashboard is a
    PLACE: one full-screen layer, entered on purpose, that shows the small set
    of things you want to glance at, and left again with everything exactly
    where it was.

    The difference is not cosmetic, and it is where every dashboard feature
    fails:

      * a floating window is always there; a layer is only there while you are
        in it;
      * a floating window can be behind another window; a layer is by
        definition in front of everything this program owns;
      * a floating window persists after a restart because it is a window; a
        layer must never survive one, or the user starts the app inside a mode
        they did not choose.

THE ONE RULE THAT MAKES IT SAFE
    A widget can be in the LAYER or in the WORKSPACE, never both. Both would
    mean two live surfaces for one thing — two caption labels updated by one
    audio loop, two metric readers, two editors over one file. This is the
    one-parent problem from `ui/floating_window.py`, one level up: the refusal
    is named, not worked around.

WHAT IS IN THE CATALOGUE, AND WHY THAT IS A DECISION
    Not "any widget". An entry gets in when somebody has thought about what it
    looks like alone on a full-screen board with no frame around it. A button
    that opens the dashboard and shows an empty board teaches the user the
    feature does not work; the catalogue and a per-widget tile size are the
    difference between a dashboard and a blank screen.

THE ESCAPE HATCH
    A dashboard you cannot leave is a modal trap. Esc, the same chord again,
    and the button all exit — and `exit_reason()` turns each of those into a
    sentence for the log rather than three silent code paths.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── the catalogue ─────────────────────────────────────────────────────────
#
# Each entry says what the thing IS, because that sentence is what decides
# whether it belongs on a dashboard at all: a dashboard shows things you
# GLANCE at, never things you TYPE into.
DASHBOARD_WIDGETS = {
    "speech_caption": "the assistant's own words, as they are spoken — read-only",
    "metrics": "CPU / MEM / NET / GPU / TMP, one column — read-only",
    "camera_preview": "what the camera sees right now — read-only, and already a "
                      "self-timing overlay, so it is shown HERE rather than moved",
}

# Refused, with the reason. The interesting half: every entry is a way the
# layer would have broken something the window depends on.
NOT_ON_DASHBOARD = {
    "conversation": "the primary surface — a dashboard is for glancing, and a "
                    "chat with no input row underneath it is a dead end",
    "input_row": "typing box; its conversation is not on the layer",
    "drawer": "anchored to a button in the window through mapTo(); on a "
              "full-screen layer it has nothing to anchor to",
    "order_dialog": "an application-modal LIVE acknowledgement. A dashboard "
                    "must never be able to display, let alone accept, one",
    "code_editor": "an editor is where you WORK; lifting it onto a glance "
                   "layer puts a keyboard surface over everything and has no "
                   "way back except leaving the layer",
}

# Tile sizes on the board, in the same units as the board's own layout.
# A widget with no size here cannot be placed, and placing everything at one
# size is how a dashboard becomes a grid of clipped text.
TILE_SIZE = {
    "speech_caption": (3, 1),
    "metrics": (2, 2),
    "camera_preview": (2, 2),
}

# How the board arranges its tiles. Columns first, because a dashboard is read
# top-to-bottom in columns, not left-to-right like a paragraph.
BOARD_COLUMNS = 4


@dataclass(frozen=True)
class Entry:
    """One widget's eligibility for the layer, and what it will look like."""

    name: str
    allowed: bool
    reason: str = ""
    columns: int = 1
    rows: int = 1

    def describe(self) -> str:
        if not self.allowed:
            return f"cannot go on the dashboard: {self.reason}"
        return f"dashboard tile {self.columns}×{self.rows}"


def entry(name: str) -> Entry:
    """May `name` be lifted onto the dashboard? A refusal is a sentence."""
    name = (name or "").strip().lower()
    if name in NOT_ON_DASHBOARD:
        return Entry(name, False, NOT_ON_DASHBOARD[name])
    if name not in DASHBOARD_WIDGETS:
        # Unknown names are refused rather than allowed: a plugin asking for a
        # capability nobody reviewed should not get one by default.
        return Entry(name, False,
                     f"'{name}' is not a widget this program shows on a dashboard")
    columns, rows = TILE_SIZE.get(name, (1, 1))
    return Entry(name, True, "", columns, rows)


def catalogue() -> list[str]:
    """Everything that may appear on a layer, in a stable order.

    Sorted, not dict order: the dashboard must look the same on two launches,
    and an accidental reordering of the catalogue above must not move the
    tiles.
    """
    return sorted(DASHBOARD_WIDGETS)


# ── what may be on the layer at once ──────────────────────────────────────

class Layer:
    """Which widgets are lifted, and from where.

    Deliberately NOT a bare set: every lifted widget remembers the slot it
    came from, because putting it back by index is the only way it returns to
    the place the user left it (`ui/floating_window.py` learned this for a
    single window; a layer has the same problem for every tile at once).
    """

    def __init__(self):
        self._slots: dict[str, object] = {}

    def lift(self, name: str, slot=None) -> Entry:
        """Take `name` out of the workspace. Returns what was decided.

        Lifting something already lifted keeps the ORIGINAL slot: a second
        lift is a redraw, not a new home, and overwriting the slot is how a
        widget ends up back in the wrong place.
        """
        decision = entry(name)
        if not decision.allowed:
            return decision
        # Keyed on the name `entry()` decided on, not the one passed in. Storing
        # the raw string meant "  METRICS  " and "metrics" were two different
        # widgets, so the same one could be lifted twice and both copies would
        # be put back in different places.
        if decision.name not in self._slots:
            self._slots[decision.name] = slot
        return decision

    def dock(self, name: str):
        """Put `name` back, returning the slot it came from (or None)."""
        return self._slots.pop((name or "").strip().lower(), None)

    def names(self) -> list[str]:
        return sorted(self._slots)

    def slot_for(self, name: str):
        return self._slots.get((name or "").strip().lower())

    def __contains__(self, name) -> bool:
        return (name or "").strip().lower() in self._slots

    def __len__(self) -> int:
        return len(self._slots)


def plan(names, active: bool = True) -> tuple[list[tuple[str, Entry]], list[Entry]]:
    """Split a requested set into `(shown, refused)`.

    A refusal does not cancel the layer: the user asked for three things and
    two of them are showable, so the layer opens with two and the refusal is
    logged. Refusing the whole request would punish the user for a plugin they
    did not write.
    """
    if not active:
        return [], []
    shown, refused = [], []
    for name in names or ():
        decision = entry(name)
        if decision.allowed:
            shown.append((decision.name, decision))
        else:
            refused.append(decision)
    return shown, refused


# ── leaving ───────────────────────────────────────────────────────────────

# The ways out. A dashboard you cannot leave is a modal trap, so every one of
# these must work, and each becomes a sentence rather than a silent path.
EXITS = {
    "escape": "Esc pressed",
    "toggle": "the dashboard button pressed again",
    "blur": "the window lost focus to another application",
    "shutdown": "the application is closing",
}


def exit_reason(key: str) -> str:
    """The sentence for one way of leaving. Unknown keys get a plain one."""
    return EXITS.get((key or "").strip().lower(),
                     "the dashboard was closed")


def survives_restart() -> bool:
    """Should the layer still be open after a restart?

    Never. A floating WINDOW may persist because it is a window; a LAYER is a
    mode, and starting the app inside a mode the user did not choose this time
    is how a dashboard becomes something to escape from.
    """
    return False


__all__ = ["BOARD_COLUMNS", "DASHBOARD_WIDGETS", "EXITS", "Entry", "Layer",
           "NOT_ON_DASHBOARD", "TILE_SIZE", "catalogue", "entry", "exit_reason",
           "plan", "survives_restart"]
