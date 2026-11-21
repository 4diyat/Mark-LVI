"""The DASHBOARD row in the CONTROLS drawer, and the key that leaves it.

WHY THE ROW AND THE KEY LIVE TOGETHER
    They are the same intent expressed twice, and the two ways of getting a
    layer wrong are "no way in" and "no way out". Keeping them in one small file
    means a change to one is visible next to the other; the previous shape of
    this project has a button in `ui/window.py` and its Escape handler three
    hundred lines away, which is how a full-screen mode once became a trap.

WHY THIS FILE IS NOT IN `ui/window.py`
    That file is at its ceiling (`tests/test_ui_split.py`) and this is not a
    window concern: the drawer row is built here and the window imports one
    function, the same pattern as `ui/wake_sleep.py` and `ui/floating_row.py`.

WHAT IT DOES NOT DECIDE
    Which widgets may appear, what a tile is worth, and the sentence for each
    way of leaving — all of that is `core/dashboard.py`. This file paints a
    button and routes a keystroke.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core import dashboard as _dash
from core.i18n import label as _t


def paint(button: QPushButton, layer) -> None:
    """Repaint from whether the board is open right now."""
    from ui.theme import C

    is_open = bool(getattr(layer, "open", False))
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#001a20' if is_open else 'transparent'};
            color: {C.PRI if is_open else C.TEXT_DIM};
            border: 1px solid {C.PRI if is_open else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if is_open else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    count = len(_dash.catalogue())
    key = "ui.dashboard.off" if is_open else "ui.dashboard.on"
    button.setText(_t(key).replace("{n}", str(count)))
    # The tooltip names the exit, because a full-screen surface the user does
    # not know how to leave is the failure mode this whole feature is written
    # against.
    button.setToolTip(_t("ui.dashboard.hint"))


def toggle(window, button=None) -> None:
    """Enter or leave the board, and repaint the row either way."""
    from ui import dashboard_layer

    layer = dashboard_layer.attach(window)
    layer.toggle()
    if button is not None:
        paint(button, layer)


def escape(window) -> bool:
    """Esc was pressed. Returns whether it was consumed.

    CONSUMED ONLY WHEN THE BOARD WAS OPEN. An Escape that is swallowed in a
    normal window is an Escape the user presses again, harder, to close the
    drawer — so this answers a question rather than eating the key.
    """
    layer = getattr(window, "_dashboard_layer", None)
    if layer is None or not getattr(layer, "open", False):
        return False
    return layer.hide("escape")


def build(window, layout, row_factory) -> QPushButton:
    """Build the row and return the button the window keeps for repainting."""
    button = row_factory(QPushButton())

    def _clicked():
        toggle(window, button)

    button.clicked.connect(_clicked)
    from ui import dashboard_layer
    layer = dashboard_layer.attach(window)
    paint(button, layer)
    return button


__all__ = ["build", "escape", "paint", "toggle"]
