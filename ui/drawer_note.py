"""A short text row in the CONTROLS drawer, for things that are not buttons.

WHY THIS EXISTS
    The drawer is a column of buttons. Two of its newest rows are not actions
    but CAPABILITIES that a user asked about and found missing: the metrics
    column and the captions cannot leave the window, and the honest answer is a
    sentence explaining why, not a greyed-out button that produces nothing when
    clicked.

    "Cannot" without a reason is the failure mode this project keeps designing
    against — the same reason `core/platform_support.py` refuses to claim a
    Wayland feature it cannot deliver. So the refusal is written here, in the
    same drawer, next to the buttons that do work.

WHAT IT IS NOT
    It is not disabled-looking. A dimmed row that never responds reads as "not
    installed"; this one is deliberately styled as text, because it is text.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from core.i18n import label as _t


def build_capability_note(layout, row_factory, key: str) -> QLabel:
    """Add one explanatory row to `layout` and return the label.

    `row_factory` is the drawer's own `_row` helper, passed in for the same
    reason every other row module passes it: it carries the drawer's font and
    padding, and a second copy here would drift.
    """
    from ui.theme import C

    note = QLabel(_t(key))
    note.setWordWrap(True)
    note.setFont(QFont("Courier New", 6))
    note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                       f" border: none; padding: 0 8px;")
    note.setTextInteractionFlags(_no_selection())
    # `row_factory` is the DRAWER, not a decorator: it adds the widget to its
    # own layout, which is why nothing here calls `layout.addWidget`. Doing
    # both would add the note twice.
    row_factory(note)
    # …and then undo the two things `_row` does that are right for a one-line
    # BUTTON and wrong for a wrapped sentence: a fixed 26px height (which clips
    # the second line) and a pointing-hand cursor (which promises a click that
    # does not exist).
    note.setMaximumHeight(16777215)          # QWIDGETSIZE_MAX: let it grow
    note.setCursor(_arrow())
    return note


def _arrow():
    from PyQt6.QtCore import Qt
    return Qt.CursorShape.ArrowCursor


def _no_selection():
    """Not selectable: this drawer closes on focus loss, and a row that steals
    focus as the mouse passes is a drawer that vanishes mid-sentence."""
    from PyQt6.QtCore import Qt
    return Qt.TextInteractionFlag.NoTextInteraction


def refresh(labels) -> None:
    """Re-read the text of every note. Used by the i18n pass."""
    for label, key in labels:
        label.setText(_t(key))


__all__ = ["build_capability_note", "refresh"]
