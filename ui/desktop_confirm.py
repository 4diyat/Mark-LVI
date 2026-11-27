"""Two explicit, default-cancel decisions for sensitive desktop actions."""

# Same dark surfaces and blue accents as the workspace. This deliberately keeps
# QMessageBox's accessible native roles and keyboard behaviour; appearance must
# not turn Return, Escape or a window close into unintended approval.
DIALOG_STYLE = '''
QMessageBox { background: #101c2a; color: #edf5ff; }
QMessageBox QLabel { color: #cbd9e8; font-size: 14px; }
QMessageBox QLabel#qt_msgbox_label { color: #edf5ff; font-size: 18px; font-weight: 700; }
QMessageBox QLabel#qt_msgbox_informativelabel { min-width: 340px; }
QMessageBox QPushButton { min-width: 112px; min-height: 38px; padding: 3px 14px;
    color: #d9e9fa; background: #182b3d; border: 1px solid #466d8d; border-radius: 8px; }
QMessageBox QPushButton:hover { background: #22415e; border-color: #78bfff; }
QMessageBox QPushButton:focus { border: 2px solid #8bcbff; }
QMessageBox QPushButton#confirmProceed { background: #3b222a; border: 1px solid #bd6674; color:#ffe7e9; }
QMessageBox QPushButton#confirmProceed:hover { background: #5b303b; }
'''


def style_dialog(dialog):
    dialog.setStyleSheet(DIALOG_STYLE)


def _ask_once(parent, title, text, accept, cancel):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    dialog = QMessageBox(parent)
    style_dialog(dialog)
    from PyQt6.QtCore import QSize
    from ui.hud_icons import icon
    dialog.setIconPixmap(icon('shield', '#64baff', 44).pixmap(QSize(44, 44)))
    dialog.setMinimumWidth(480)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setWindowTitle(title)
    dialog.setText(title)
    dialog.setInformativeText(text)
    dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    dialog.button(QMessageBox.StandardButton.Yes).setText(accept)
    dialog.button(QMessageBox.StandardButton.Yes).setObjectName('confirmProceed')
    # Style directly so the workspace's inherited QMessageBox rule cannot
    # override the destructive-action treatment.
    dialog.button(QMessageBox.StandardButton.Yes).setStyleSheet(
        'QPushButton { background:#3b222a; border:1px solid #bd6674; color:#ffe7e9; } '
        'QPushButton:hover { background:#5b303b; } '
        'QPushButton:focus { border:2px solid #ffb3bd; }')
    dialog.button(QMessageBox.StandardButton.No).setText(cancel)
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    return dialog.exec() == QMessageBox.StandardButton.Yes


def confirm_twice(parent, title, text, final_title, final_text, accept, cancel):
    """Closing or cancelling either dialog must never run the operation."""
    return (_ask_once(parent, title, text, accept, cancel)
            and _ask_once(parent, final_title, final_text, accept, cancel))
