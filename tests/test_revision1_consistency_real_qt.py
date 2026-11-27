"""Real Qt checks for consistent confirmation and security presentation."""
import os
import subprocess
import sys

import pytest


def test_dialogs_remain_default_cancel_and_security_list_is_usable(tmp_path):
    code = r'''
import sys, time
try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox, QBoxLayout
except ImportError:
    sys.exit(77)
from core import audit_log, i18n
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui.desktop_confirm import confirm_twice
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
i18n.set_locale('id'); audit_log.reset_shared()
for i in range(8):
    audit_log.shared().record('uji ' + str(i), 'safe', 'done', 'Contoh data')
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); shell._main_surface.workspace_button.click()
workspace = shell._desktop_workspace
workspace.window.resize(1500, 1050); workspace.navigate('security')
end = time.monotonic() + 4
while workspace.security.loading and time.monotonic() < end:
    app.processEvents(); QTest.qWait(10)
app.processEvents()
security = workspace.security
assert not security.loading and len(security.audit_cards) == 8
assert 300 <= security.records_area.height() <= 370
assert security.records_area.verticalScrollBar().maximum() > 0
seen = []
def check_dialog():
    dialog = QApplication.activeModalWidget()
    assert dialog.text() == 'Konfirmasi terakhir'
    assert dialog.informativeText() == 'Rincian <contoh>'
    assert dialog.textFormat() == Qt.TextFormat.PlainText
    assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.No
    assert 'background:#3b222a' in dialog.button(QMessageBox.StandardButton.Yes).styleSheet()
    seen.append(True)
    QTest.keyClick(dialog.defaultButton(), Qt.Key.Key_Return)
def first():
    dialog = QApplication.activeModalWidget()
    assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.No
    QTimer.singleShot(0, check_dialog)
    dialog.done(QMessageBox.StandardButton.Yes.value)
QTimer.singleShot(0, first)
assert not confirm_twice(workspace.window, 'Pertama', 'Rincian', 'Konfirmasi terakhir',
                         'Rincian <contoh>', 'Lupakan', 'Batal')
assert seen == [True]
# Escape also cancels the first step; the second must never open.
def escape():
    dialog = QApplication.activeModalWidget()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
QTimer.singleShot(0, escape)
assert not confirm_twice(workspace.window, 'Pertama', 'Rincian', 'Terakhir',
                         'Rincian', 'Lupakan', 'Batal')
workspace.window.resize(900, 600); app.processEvents(); QTest.qWait(50)
assert security.columns.direction() == QBoxLayout.Direction.TopToBottom
assert security.width() <= workspace.stack.width()
workspace.close(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
