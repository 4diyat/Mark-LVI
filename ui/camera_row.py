"""The SECURITY CAMERA row in the CONTROLS drawer.

WHY A ROW AND NOT A CONFIG KEY
    `core/security_camera.py` is off by default and nothing but a person can
    turn it on — no plugin, no tool, no model. A switch that only exists in a
    JSON file is, in practice, a switch nobody knows they have; the same reason
    `ui/notify_row.py` exists for a setting that could equally have lived in the
    config.

WHAT THE ROW DOES NOT DO
    It does not open the camera. Pressing it writes the setting and repaints;
    the first look happens on the next tick of `main.py`'s loop. A button that
    lights the device indicator while the user is still reading the label is a
    button that surprises people.

WHY IT REPAINTS FROM A READ
    Same rule as `ui/file_access_row.py`: the label says what the config says,
    not what the press hoped to write. A write that failed must look like a
    failed write.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core import security_camera
from core.i18n import label as _t


def paint(button: QPushButton) -> None:
    """Repaint from the setting in force. Called on build, on toggle, on i18n."""
    from ui.theme import C

    on = security_camera.enabled()
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#200000' if on else 'transparent'};
            color: {C.RED if on else C.TEXT_DIM};
            border: 1px solid {C.RED if on else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if on else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    button.setText(_t("ui.camera.on" if on else "ui.camera.off"))
    button.setToolTip(_t("ui.camera.hint"))


def toggle(button: QPushButton, on_toggled=None) -> bool:
    """Flip the setting, repaint, and report. Returns the value now in force."""
    want = not security_camera.enabled()
    # No cadence argument: the module's own default applies, because a row
    # with no cadence control must not silently choose the most aggressive one.
    security_camera.save(want)
    paint(button)
    now = security_camera.enabled()
    if on_toggled is not None:
        on_toggled(now)
    return now


def build_camera_button(layout, row_factory, on_toggled=None) -> QPushButton:
    """Add the SECURITY CAMERA row to `layout` and return the button.

    `row_factory(button)` is the drawer's own `_row` helper, passed in for the
    same reason every other row module passes it: it carries the drawer's font
    and padding, and a second copy here would drift.
    """
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, on_toggled))
    paint(button)
    return button
