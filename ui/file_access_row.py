"""The FULL FILE ACCESS row in the CONTROLS drawer.

WHY THIS IS A MODULE AND NOT TWO METHODS ON `MainWindow`
    `ui/window.py` has a ceiling (`tests/test_ui_split.py`) and the rule is
    extract, never raise. This follows `ui/notify_row.py` and
    `ui/wake_sleep.py`, which were split off for the same reason.

WHAT THIS FILE IS ALLOWED TO DECIDE
    Only the interaction: which folders the user picked, and whether the
    permission they are looking at was actually written. Every rule about what
    may then be touched lives in `core/file_access.py`, and nothing here can
    soften one — the policy is asked after the fact, never constructed with
    extra roots.

WHY THE PICKER IS A PARAMETER
    A folder picker cannot be clicked from a test, and a `QFileDialog` import
    at module scope would make this file untestable without a display. The
    default is resolved when the button is pressed, so a machine with no
    display can still import the module and drive the handler with a fake
    picker that returns a list of paths.

WHY IT ASKS FOR THE PATH AGAIN AFTER SAVING
    A save and a read are two different claims, and only the second one is
    what the file controller will see. Reporting the saved values would let a
    settings screen say "granted" while the boundary stayed shut.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core import file_access
from core.i18n import label as _t


def _pick_folders(parent=None) -> list[str]:
    """Ask the user for folders. Real Qt dialog, imported at click time."""
    from PyQt6.QtWidgets import QFileDialog

    chosen = QFileDialog.getExistingDirectory(
        parent, _t("ui.file_access.pick"))
    return [chosen] if chosen else []


def grant(button, picker=None, on_toggled=None, home=None) -> bool:
    """Pick folders, save them, repaint. Returns whether access is now on."""
    pick = picker or _pick_folders
    folders = list(pick() or ())
    if not folders:
        return file_access.load(home=home).enabled

    on = file_access.save(folders)
    # The policy as it will be read by the controller, not as we hoped it was
    # written. `save` returning True still has to survive a round trip.
    on = file_access.load(home=home).enabled if on else False
    paint(button, home=home)
    if on_toggled is not None:
        on_toggled(on)
    return on


def revoke(button, on_toggled=None, home=None) -> bool:
    """Turn it off and drop the granted folders. Returns False (off)."""
    file_access.disable()
    paint(button, home=home)
    if on_toggled is not None:
        on_toggled(False)
    return False


def toggle(button, picker=None, on_toggled=None, home=None) -> bool:
    """One button, two directions: on asks WHERE, off asks nothing."""
    policy = file_access.load(home=home)
    if policy.enabled:
        return revoke(button, on_toggled=on_toggled, home=home)
    return grant(button, picker=picker, on_toggled=on_toggled, home=home)


def paint(button: QPushButton, home=None) -> None:
    """Repaint from the policy in force. Called on build, on toggle, on i18n."""
    from ui.theme import C

    policy = file_access.load(home=home)
    on = policy.enabled
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#200000' if on else 'transparent'};
            color: {C.RED if on else C.TEXT_DIM};
            border: 1px solid {C.RED if on else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if on else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    if not on:
        button.setText(_t("ui.file_access.off"))
    else:
        count = len(policy.effective_roots())
        button.setText(_t("ui.file_access.on").format(n=count))
    button.setToolTip(_t("ui.file_access.hint"))


def build_file_access_button(layout, row_factory, on_toggled=None) -> QPushButton:
    """Add the FULL FILE ACCESS row to `layout` and return the button.

    `row_factory(button)` is the drawer's own `_row` helper, passed in for the
    same reason `ui/notify_row.py` passes it: it carries the drawer's font and
    padding, and a second copy here would drift.
    """
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, on_toggled=on_toggled))
    paint(button)
    return button
