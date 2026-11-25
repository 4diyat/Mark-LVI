"""core/keyboard_nav.py — the pure policy behind keyboard navigation
(board 5.9, the part that was missing).

WHAT THIS DECIDES
    Board 15 offers accessibility controls; one of the roadmap's missing
    pieces is full keyboard navigation — moving focus with Tab / Shift+Tab
    through a panel's controls without a mouse. This module computes the tab
    order of a panel's focusable widgets and decides which widget receives
    focus next or previous, with no Qt and no widget object.

WHY THE DECISION IS PURE
    A tab order is an ordering over a list of widget descriptors, and "the
    widget after this one" is a position in that list. Deciding the order,
    skipping disabled widgets, and wrapping at the ends are arithmetic over
    a list of records. The widget objects live in the UI; this policy works
    on descriptors so a test can drive every move with fixtures.

THE WIDGETS ARE DESCRIPTORS, NOT OBJECTS
    Each focusable widget is described by `{id, kind, enabled}`. `kind`
    orders the tab sequence (a button, a field, a toggle, a link); the policy
    sorts by the panel's declared order first, then by kind, so a control
    that should come first in the flow is reachable first by Tab. A widget
    that is not enabled is skipped — Tab must never land on a control the
    user cannot use.

WHAT THIS DOES NOT DO
    It does not set focus on a real widget. The UI calls `next_focus` /
    `previous_focus` with the panel's live widget list and applies the
    returned id; this module decides WHICH widget, never touches it. That
    split keeps the traversal logic testable and the widget handling in the
    Qt thread where it belongs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# The kinds of focusable control, in the order Tab should reach them within
# the same declared position. A field before a button matches the visual
# flow a keyboard user expects; a link last, because it is the "go" action.
KIND_ORDER = ("field", "toggle", "button", "link")


@dataclass
class Focusable:
    """One widget's place in the tab order.

    `order` is the panel's declared position (its visual order). `kind`
    breaks ties within a position and gives a stable, predictable sequence.
    `enabled` is whether the widget may receive focus — a disabled widget is
    never a tab stop.
    """

    id: str
    kind: str = "button"
    order: int = 0
    enabled: bool = True


def _is_focusable(item) -> bool:
    return isinstance(item, Focusable)


def tab_order(widgets: Iterable) -> list[Focusable]:
    """The widgets that receive focus, in Tab order.

    Disabled widgets are dropped entirely — they are not skipped-and-returned-
    to, they are not in the sequence. A widget that is not a `Focusable` is
    ignored, so a panel can pass a mixed list without the policy crashing on
    something it does not understand. The sort is (declared order, kind
    order, id) so the sequence is deterministic and matches the flow.
    """
    focusable = [w for w in (widgets or ()) if _is_focusable(w) and w.enabled]
    kind_rank = {k: i for i, k in enumerate(KIND_ORDER)}
    focusable.sort(key=lambda w: (w.order, kind_rank.get(w.kind, 99), w.id))
    return focusable


def _index(order: list[Focusable], current_id: str) -> int:
    """The position of `current_id` in the order, or -1 if it is not there.

    A widget that is not in the tab order (disabled, or not focusable) has
    no position; `next_focus` then falls back to the first focusable, which
    is the honest answer for "Tab from a widget that cannot be tabbed to".
    """
    for i, widget in enumerate(order):
        if widget.id == current_id:
            return i
    return -1


def next_focus(widgets: Iterable, current_id: str) -> Optional[str]:
    """The id that receives focus on Tab, or None if there is nowhere to go.

    Tab moves to the next enabled widget in the tab order, wrapping to the
    first when the current widget is the last. From a widget that is not in
    the order (or with no order at all), Tab goes to the first focusable —
    that is "press Tab to start", not "press Tab and nothing happens".
    """
    order = tab_order(widgets)
    if not order:
        return None
    idx = _index(order, current_id)
    if idx < 0:
        return order[0].id
    return order[(idx + 1) % len(order)].id


def previous_focus(widgets: Iterable, current_id: str) -> Optional[str]:
    """The id that receives focus on Shift+Tab, or None if there is nowhere.

    The mirror of `next_focus`: the previous enabled widget, wrapping to the
    last when the current widget is the first.
    """
    order = tab_order(widgets)
    if not order:
        return None
    idx = _index(order, current_id)
    if idx < 0:
        return order[-1].id
    return order[(idx - 1) % len(order)].id


def focusable_ids(widgets: Iterable) -> list[str]:
    """The ids in tab order, for a panel that wants to show the sequence."""
    return [w.id for w in tab_order(widgets)]


__all__ = [
    "KIND_ORDER", "Focusable", "tab_order", "next_focus",
    "previous_focus", "focusable_ids",
]
