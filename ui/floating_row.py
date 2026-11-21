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


def toggle(button: QPushButton, panel) -> int:
    """Float the captions out, or put them back. Returns how many are out.

    ONE widget, named once. The previous version took a tuple of names and
    looked each one up in a dictionary holding a single real widget, which is a
    list pretending to be general and would have floated nothing at all for any
    second name — including the two names it used to advertise.
    """
    widget = getattr(panel._window, "_speech_caption", None)
    if widget is not None:
        panel.toggle("speech_caption", widget)
    else:
        panel.say(_t("ui.floating.no_caption"))
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

    The row must still REPAINT on every rebuild: the drawer throws its buttons
    away each time it opens, so a row that only painted once would come back
    saying OFF while the captions were out on the desktop.
    """
    from ui.floating_panel import FloatingPanel

    panel = getattr(window, "_floating", None) or FloatingPanel(window)
    window._floating = panel
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, panel))
    paint(button, panel)
    # THE ROW'S OWN EXPLANATION, added here rather than in the window: the
    # drawer column is built by `ui/window.py`, which is at its line ceiling,
    # and a capability note belongs next to the button that made the user ask.
    # It also keeps the note and the button from drifting apart.
    from ui.drawer_note import build_capability_note
    window._floating_note = build_capability_note(
        layout, row_factory, "ui.capability.captions")
    return button


def build_gesture_os_button(*args, **kwargs):
    """Re-exported so the drawer needs one import, not two.

    `ui/window.py` is at its line ceiling and every import there costs a line
    it does not have. The row itself still lives in its own module — this is a
    name, not a move.
    """
    from ui.gesture_os_row import build_gesture_os_button as _build
    return _build(*args, **kwargs)


def build_floating_rows(layout, row_factory, window):
    """Add BOTH floating rows, plus their note, and return the first button.

    WHY ONE ENTRY POINT
        `ui/window.py` is at exactly 3,800 lines and has room for one statement
        here, not three. The two rows are also read together by a user — "what
        can leave" and "what has left" — so building them in one place keeps
        them adjacent in the drawer instead of one drifting below unrelated
        settings the next time that file is edited.

    Returns the captions button, which is what the window keeps a reference to.
    The documents button is kept on the window by its own builder.
    """
    from ui.floating_documents_row import build_floating_documents_button

    button = build_floating_button(layout, row_factory, window)
    window._floating_docs_btn = build_floating_documents_button(
        layout, row_factory, window)
    return button


def build_floating_documents_button(*args, **kwargs):
    """Re-exported for the same reason as `build_gesture_os_button` below:
    `ui/window.py` is at its line ceiling and every import there costs a line
    the file does not have. The row lives in `ui/floating_documents_row.py`.
    """
    from ui.floating_documents_row import build_floating_documents_button as _b
    return _b(*args, **kwargs)


__all__ = ["build_floating_button", "build_floating_documents_button",
           "build_floating_rows", "build_gesture_os_button", "paint", "toggle"]
