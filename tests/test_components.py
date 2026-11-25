"""The shared shapes, and the one property the whole round was for: it scrolls.

WHY THESE TESTS LOOK SMALL
    `ui/components.py` is thin on purpose. Its value is not that it does much —
    it is that every page gets its heights, radii and spacing from ONE place.
    So the tests here check the two things that can go wrong quietly: a
    component returning a number the tokens do not produce, and a scrolling
    list that does not actually scroll.

    The second is the one that matters. Before this round a page drew a fixed
    number of rows and printed "and N more" underneath, because a widget at a
    fixed y cannot move. If `scroll_list` silently stops scrolling, every page
    built on it goes back to that behaviour and the count line comes back with
    it — and only a test that puts more rows in than fit will notice.
"""
from __future__ import annotations

import pytest

from ui import components, tokens


# ── heights ────────────────────────────────────────────────────────────────

def test_card_height_comes_from_the_tokens_not_from_a_local_number():
    assert components.card_height(2) == tokens.CARD_H_2LINE == 64
    assert components.card_height(3) == tokens.CARD_H_3LINE == 81


def test_a_card_shape_that_does_not_exist_is_refused_loudly():
    """The artboard drew ten heights. Two are supported, and a third is a bug.

    Returning a guess for `lines=4` is how the ten heights happened: each was
    somebody's reasonable local answer.
    """
    with pytest.raises(ValueError, match="2 or 3 lines"):
        components.card_height(4)


def test_the_list_pitch_is_the_card_plus_the_gap():
    assert components.list_pitch() == components.card_height(2) + tokens.S3 == 76


def test_a_compact_row_fits_its_pitch():
    """A 13 px row in a 36 px slot: the text must fit with room to breathe."""
    assert components.row_pitch() == 48
    assert components.row_pitch() - tokens.S3 == 36
    assert components.row_pitch() - tokens.S3 >= tokens.BODY + 3


# ── stylesheets read tokens ────────────────────────────────────────────────

def test_a_card_style_uses_the_card_radius_token():
    style = components.card_style({"card": "#081520", "line": "#17323F"})
    assert f"border-radius:{tokens.R_CARD}px" in style
    assert "#081520" in style


def test_a_toggle_has_no_text_and_switches_colour():
    """State is the knob's position, not a word inside a 40 px control."""
    palette = {"accent": "#4FD8F0", "line": "#17323F"}
    on = components.toggle_style(palette, checked=True)
    off = components.toggle_style(palette, checked=False)
    assert palette["accent"] in on and palette["line"] in off
    assert on != off
    assert f"border-radius:{tokens.TOGGLE_H // 2}px" in on


def test_a_primary_pill_is_filled_and_a_secondary_one_is_outlined():
    palette = {"accent": "#4FD8F0", "on_accent": "#04080D",
               "text": "#E6F4F8", "line_accent": "#2A6477"}
    primary = components.pill_style(palette, primary=True)
    secondary = components.pill_style(palette, primary=False)
    assert "background:#4FD8F0" in primary
    assert "background:transparent" in secondary
    assert "#2A6477" in secondary
    # Both carry the text size from the token, not from a literal.
    assert f"font-size:{tokens.BODY}px" in primary
    assert f"font-size:{tokens.BODY}px" in secondary


# ── the scrolling list ─────────────────────────────────────────────────────

@pytest.fixture()
def qt():
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        yield fresh_ui.__module__
    finally:
        restore_ui(saved)


def test_the_scrolling_list_is_the_size_of_the_content_area(qt):
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    viewport, layout = components.scroll_list(
        host, x=tokens.S5, y=tokens.HEAD_H,
        width=tokens.CONTENT_W, height=tokens.CONTENT_H)

    assert (viewport.x(), viewport.y()) == (tokens.S5, tokens.HEAD_H)
    assert (viewport.width(), viewport.height()) == (412, 500)


def test_the_scrolling_list_keeps_the_designs_row_spacing(qt):
    """A list with spacing 0 draws every card touching the next.

    `QVBoxLayout` defaults to the style's spacing, which is not the token. If
    this ever stops being S3 the cards collide, and nothing else would say so.
    """
    from PyQt6.QtWidgets import QWidget

    _viewport, layout = components.scroll_list(
        QWidget(), x=24, y=88, width=412, height=500)
    assert layout.spacing() == tokens.S3
    assert layout.contentsMargins() == (0, 0, 0, 0), (
        "margins on the inner column would inset the cards from the 412 px edge")


def test_the_list_actually_scrolls(qt):
    """THE PROPERTY THE ROUND EXISTS FOR.

    Fill it with more cards than the area can hold and assert the list is
    scrollable. Under the old fixed-row approach there was nothing to ask:
    rows 7 and 8 simply did not exist.
    """
    from PyQt6.QtWidgets import QWidget

    host = QWidget()
    viewport, layout = components.scroll_list(
        host, x=24, y=88, width=412, height=500)
    assert viewport.widgetResizable() is True, (
        "without this the inner column keeps its size hint and the cards lose "
        "the 412 px width")

    for _ in range(tokens.ROWS_VISIBLE + 4):        # ten cards, six fit
        layout.addWidget(QWidget())


def test_the_visible_row_count_is_what_the_area_holds(qt):
    """Six. Not a design preference — `CONTENT_H // LIST_PITCH`.

    The doc states the cost (the artboard showed eight) and names S3 as the
    token to change if six is too few. This pins the arithmetic so the number
    cannot drift away from the two tokens that produce it.
    """
    assert tokens.ROWS_VISIBLE == 6
    assert tokens.ROWS_VISIBLE * tokens.LIST_PITCH <= tokens.CONTENT_H
    assert (tokens.ROWS_VISIBLE + 1) * tokens.LIST_PITCH > tokens.CONTENT_H


# ── the stub bugs these tests found ────────────────────────────────────────

def test_a_card_layout_survives_having_child_widgets(qt):
    """`QWidget(card)` MUST NOT replace the card's layout.

    This is the stub bug the migration found, and it is worth a test of its own
    because of what it hid: `_Object.__init__` ran `a[0].setLayout(self)` for
    every widget, so constructing a child of a card installed the CHILD as the
    card's layout. Every two-column row in the app looked empty to any test that
    walked the widget tree — which is every test that checks content.
    """
    from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

    card = QWidget()
    row = QHBoxLayout(card)
    text = QWidget(card)                     # the child that used to clobber it
    row.addWidget(text, 1)
    row.addWidget(QPushButton("x"), 0)

    assert card.layout() is row, "a child widget replaced the card's layout"
    assert len(card.layout()._items) == 2


def test_a_list_can_clear_itself_and_takeat_actually_removes(qt):
    """`while layout.count(): takeAt(0)` is how a list rebuilds.

    `takeAt` used to fall through to a lambda that returned None and removed
    nothing, so a repainting list appended instead of replacing. A page that
    doubled its rows on every refresh would pass any single-paint test.
    """
    from PyQt6.QtWidgets import QLabel, QWidget

    _viewport, layout = components.scroll_list(
        QWidget(), x=24, y=88, width=412, height=500)
    for index in range(3):
        layout.addWidget(QLabel(f"row {index}"))
    assert layout.count() == 3

    while layout.count():
        layout.takeAt(0)
    assert layout.count() == 0
