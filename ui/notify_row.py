"""The notifications row in the CONTROLS drawer.

WHY THIS IS A MODULE AND NOT TWO METHODS ON `MainWindow`
    `ui/window.py` has a ceiling (`tests/test_ui_split.py`) because it was
    7,504 lines once and the split exists to stop that happening again. Adding
    this row there took it to 4,271 of 4,250. The rule is extract, never raise —
    so the button, its two states and its click handler live here, next to
    `ui/wake_sleep.py`, which was split off for the same reason.

WHAT LIVES WHERE
    This file owns only the APPEARANCE and the toggle. The decision about when
    a notification is allowed to fire is `core/notify.py`; the decision about
    which mode asks for one is `ui/lifecycle.py`. Keeping the three apart is
    what makes each of them testable on its own.

WHY IT USES THE SAME TWO STYLES AS THE PUSH-TO-TALK ROW
    A drawer where "on" looks different depending on which row you are reading
    makes the user learn the interface twice. The colours are read from
    `ui.theme.C` at call time, not captured, so an accent change applies here
    too.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core.i18n import label as _t
from memory.config_manager import (get_desktop_notifications,
                                   save_desktop_notifications)


def build_notifications_button(layout, row_factory, on_toggled=None) -> QPushButton:
    """Add the NOTIFICATIONS row to `layout` and return the button.

    `row_factory(button)` is the drawer's own `_row` helper — passed in rather
    than imported, because it carries the layout and the font/padding the whole
    drawer uses, and duplicating it here would let the two drift.

    `on_toggled(enabled)` is called after a successful save, for the caller that
    wants to log it.
    """
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, on_toggled))
    paint(button)
    return button


def paint(button: QPushButton) -> None:
    """Repaint from the saved setting. Called on build, on toggle, on i18n."""
    from ui.theme import C

    on = get_desktop_notifications()
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#001a08' if on else 'transparent'};
            color: {C.GREEN if on else C.TEXT_DIM};
            border: 1px solid {C.GREEN_D if on else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if on else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    button.setText(_t("ui.notify.on" if on else "ui.notify.off"))
    button.setToolTip(_t("ui.notify.hint"))


def toggle(button: QPushButton, on_toggled=None) -> bool:
    """Flip the setting, repaint, and report. Returns the new value."""
    want = not get_desktop_notifications()
    save_desktop_notifications(want)
    paint(button)
    if on_toggled is not None:
        on_toggled(want)
    return want
