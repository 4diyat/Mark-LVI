"""Board 5.9's keyboard navigation policy: tab order and focus moves.

These test the pure policy in `core.keyboard_nav` with no Qt. The point is
predictability: Tab and Shift+Tab move through enabled widgets in a fixed,
declared order, disabled widgets are never tab stops, and the sequence
wraps at the ends.
"""
from __future__ import annotations

from core.keyboard_nav import (Focusable, focusable_ids, next_focus,
                               previous_focus, tab_order)


def _panel():
    return [
        Focusable(id="search", kind="field", order=0),
        Focusable(id="toggle", kind="toggle", order=1),
        Focusable(id="run", kind="button", order=2),
        Focusable(id="disabled-btn", kind="button", order=3, enabled=False),
        Focusable(id="link", kind="link", order=4),
    ]


# ── tab_order ─────────────────────────────────────────────────────────────

def test_disabled_widgets_are_not_in_the_order():
    order = tab_order(_panel())
    ids = [w.id for w in order]
    assert "disabled-btn" not in ids
    assert ids == ["search", "toggle", "run", "link"]


def test_the_order_follows_declared_position():
    order = tab_order([
        Focusable(id="z", kind="button", order=5),
        Focusable(id="a", kind="button", order=1),
    ])
    assert [w.id for w in order] == ["a", "z"]


def test_kind_breaks_ties_within_a_position():
    order = tab_order([
        Focusable(id="btn", kind="button", order=0),
        Focusable(id="field", kind="field", order=0),
        Focusable(id="toggle", kind="toggle", order=0),
    ])
    # Within one position: field, toggle, button — matching the visual flow.
    assert [w.id for w in order] == ["field", "toggle", "btn"]


def test_non_focusable_items_are_ignored():
    order = tab_order([Focusable(id="a", order=0), "not-a-widget", 42, None])
    assert [w.id for w in order] == ["a"]


def test_an_empty_panel_has_no_order():
    assert tab_order([]) == []


# ── next_focus ────────────────────────────────────────────────────────────

def test_tab_moves_to_the_next_enabled_widget():
    assert next_focus(_panel(), "search") == "toggle"


def test_tab_skips_disabled_widgets():
    assert next_focus(_panel(), "run") == "link"


def test_tab_wraps_to_the_first_from_the_last():
    assert next_focus(_panel(), "link") == "search"


def test_tab_from_a_widget_not_in_the_order_goes_to_the_first():
    assert next_focus(_panel(), "ghost") == "search"


def test_tab_with_no_focusable_returns_none():
    assert next_focus([], "search") is None


def test_tab_with_only_disabled_widgets_returns_none():
    widgets = [Focusable(id="x", enabled=False)]
    assert next_focus(widgets, "x") is None


# ── previous_focus ────────────────────────────────────────────────────────

def test_shift_tab_moves_to_the_previous_widget():
    assert previous_focus(_panel(), "toggle") == "search"


def test_shift_tab_wraps_to_the_last_from_the_first():
    assert previous_focus(_panel(), "search") == "link"


def test_shift_tab_from_a_widget_not_in_the_order_goes_to_the_last():
    assert previous_focus(_panel(), "ghost") == "link"


def test_shift_tab_with_no_focusable_returns_none():
    assert previous_focus([], "search") is None


# ── focusable_ids ─────────────────────────────────────────────────────────

def test_focusable_ids_matches_the_order():
    assert focusable_ids(_panel()) == ["search", "toggle", "run", "link"]
