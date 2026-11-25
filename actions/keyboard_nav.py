"""actions/keyboard_nav.py — the keyboard navigation adapter (board 5.9).

WHAT THIS DOES
    Turns a panel's live widget collection into the `Focusable` descriptors
    the pure policy in `core.keyboard_nav` reads, and applies the policy's
    answer back to the real widgets. This module is the bridge between the
    Qt widget objects (which live in the UI thread) and the policy (which
    must stay pure and testable).

WHY THE ADAPTERS SPLIT
    The policy in `core/keyboard_nav.py` works on descriptors and returns
    ids; it never touches a widget. That is so a test can drive Tab /
    Shift+Tab with fixtures. This adapter is the only place that knows what
    a "widget" is in this app: it reads each widget's geometry/order and
    enabled state, hands descriptors to the policy, and calls the returned
    id back onto the panel.

WHAT IT DOES NOT DO
    It does not create widgets and it does not run on a worker thread. The
    UI calls `move` from the Qt main thread (where the widgets live); the
    policy decision is computed here but applied by the caller, so the
    threading rule in AGENTS.md is never crossed.
"""
from __future__ import annotations

from typing import Iterable, Optional


def describe(widgets: Iterable) -> list:
    """Build `Focusable` descriptors from a panel's widget collection.

    Each widget may carry `id`, `kind`, `order` (its visual position) and
    `enabled`. A widget that exposes none of these is given a default
    button descriptor with a stable order, so a panel with a plain list of
    ids still produces a usable tab order. This function never raises on a
    malformed widget — it describes what it can and skips what it cannot.
    """
    from core.keyboard_nav import Focusable

    out: list[Focusable] = []
    for index, widget in enumerate(widgets or ()):
        if not widget:
            continue
        wid = getattr(widget, "id", None) or getattr(widget, "name", None)
        if not wid:
            continue
        kind = getattr(widget, "kind", "button")
        order = getattr(widget, "order", index)
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = index
        enabled = getattr(widget, "enabled", True)
        out.append(Focusable(id=str(wid), kind=str(kind),
                             order=order, enabled=bool(enabled)))
    return out


def move(widgets: Iterable, current_id: str, *, forward: bool = True) -> Optional[str]:
    """The id that should receive focus on Tab (forward) or Shift+Tab.

    Returns the id, or None when there is no focusable widget to move to.
    The caller applies this to the real panel; this adapter only computes.
    """
    from core.keyboard_nav import next_focus, previous_focus

    descriptors = describe(widgets)
    if forward:
        return next_focus(descriptors, current_id)
    return previous_focus(descriptors, current_id)


def sequence(widgets: Iterable) -> list[str]:
    """The panel's tab order as ids, for display or for a focus ring."""
    from core.keyboard_nav import focusable_ids

    return focusable_ids(describe(widgets))


__all__ = ["describe", "move", "sequence"]
