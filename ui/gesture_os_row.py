"""The HAND → OS row in the CONTROLS drawer.

WHY THIS IS NOT PART OF ui/hand_gesture.py
    That file is 566 lines about moving widgets inside this program, and its
    controller is started from the workspace panel, not from a drawer row. This
    row is a different switch with a different consequence: the hand stops
    touching JARVIS and starts touching whatever is on screen. Keeping it
    separate is also what keeps this file small enough to read in one go.

WHAT THE ROW DOES NOT DO
    It does not start the camera. Hand tracking is already started from the
    workspace panel, and a drawer row that silently switched the webcam on
    would be a second, hidden way to turn a camera on. If tracking is off, the
    row says so instead of starting it.

WHY THE LABEL CARRIES THE FOCUS RULE
    The one thing a user will otherwise not understand is why the pointer stops
    when they click back to JARVIS. The tooltip says it in one sentence, and
    the same sentence comes back as a log line when it happens.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core import logbook
from core.i18n import label as _t


def _bridge(window):
    bridge = getattr(window, "_gesture_os", None)
    if bridge is None:
        from ui.gesture_os_bridge import GestureOsBridge
        bridge = GestureOsBridge(window)
        window._gesture_os = bridge
    return bridge


def paint(button: QPushButton, window) -> None:
    """Repaint from the bridge's state. Called on build, on toggle, on i18n."""
    from ui.theme import C

    on = _bridge(window).enabled
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#001a08' if on else 'transparent'};
            color: {C.GREEN if on else C.TEXT_DIM};
            border: 1px solid {C.GREEN_D if on else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if on else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    button.setText(_t("ui.gesture_os.on" if on else "ui.gesture_os.off"))
    button.setToolTip(_t("ui.gesture_os.hint"))


def toggle(button: QPushButton, window) -> bool:
    """Flip OS control, repaint, and report. Returns the value now in force."""
    bridge = _bridge(window)
    want = not bridge.enabled
    bridge.set_enabled(want)
    paint(button, window)
    try:
        window.write_log("SYS: " + _t(
            "ui.gesture_os.on" if want else "ui.gesture_os.off"))
    except Exception as e:           # noqa: BLE001 — a closing window has no log
        logbook.get(__name__).debug("could not write to the activity log: %s", e)
    return bridge.enabled


def build_gesture_os_button(layout, row_factory, window) -> QPushButton:
    """Add the HAND → OS row to `layout` and return the button.

    `row_factory(button)` is the drawer's own `_row` helper, passed in for the
    same reason every other row module passes it: it carries the drawer's font
    and padding, and a second copy here would drift.
    """
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, window))
    paint(button, window)
    return button


__all__ = ["build_gesture_os_button", "paint", "toggle"]
