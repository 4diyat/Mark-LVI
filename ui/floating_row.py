"""The FLOATING WIDGETS row in the CONTROLS drawer.

WHY A ROW
    A capability nobody can reach is the same as no capability. `ui/window.py`
    is at its ceiling, so this follows `ui/wake_sleep.py` and `ui/notify_row.py`:
    the row lives in its own file and the window imports one function.

WHAT IT DOES NOT DO
    It does not decide whether floating is possible. That is
    `core/floating.py`, and the answer differs per widget and per desktop — a
    Wayland session will float but cannot promise always-on-top, and the row
    says so instead of pretending. It also refuses to float the widgets that
    are anchored or modal, and the refusal is a sentence, not a greyed button
    with no explanation.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core.i18n import label as _t


def paint(button: QPushButton, panel) -> None:
    """Repaint from what is floating right now. Called on build and on toggle."""
    from ui.theme import C

    count = len(panel.state.names())
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#001a20' if count else 'transparent'};
            color: {C.PRI if count else C.TEXT_DIM};
            border: 1px solid {C.PRI if count else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if count else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    button.setText(_t("ui.floating.on" if count else "ui.floating.off").replace(
        "{n}", str(count)))
    button.setToolTip(_t("ui.floating.hint"))


def toggle(button: QPushButton, panel, names=("speech_caption",)) -> int:
    """Float or dock the widgets named. Returns how many are floating after."""
    widgets = {"speech_caption": getattr(panel._window, "_speech_caption", None)}
    for name in names:
        widget = widgets.get(name)
        if widget is None:
            continue
        panel.toggle(name, widget)
    paint(button, panel)
    return len(panel.state.names())


def build_floating_button(layout, row_factory, window) -> QPushButton:
    """Add the FLOATING WIDGETS row to `layout` and return the button.

    `row_factory(button)` is the drawer's own `_row` helper, passed in for the
    same reason every other row module passes it: it carries the drawer's font
    and padding, and a second copy here would drift.

    The panel is created here and kept on the window, because `ui/window.py` is
    at its line ceiling and `self._floating = FloatingPanel(self)` is one line
    the file does not have. Reused if it already exists, so opening the drawer
    twice does not forget which widgets are floating.
    """
    from ui.floating_panel import FloatingPanel

    panel = getattr(window, "_floating", None) or FloatingPanel(window)
    window._floating = panel
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, panel))
    paint(button, panel)
    return button


__all__ = ["build_floating_button", "paint", "toggle"]
