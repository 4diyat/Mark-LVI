"""Exercise the actual security page controls with simulated devices."""
import os
import subprocess
import sys

import pytest


def test_guest_and_vision_controls(tmp_path):
    code = r'''
import sys, time
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QTimer
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import guest_mode, vision_access
from actions import screen_processor
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); shell._main_surface.workspace_button.click()
workspace = shell._desktop_workspace
workspace.navigate('security'); app.processEvents()
page = workspace.security
page.vision_checks['camera'].setChecked(False)
try:
    screen_processor._capture_camera()
except PermissionError: pass
else: raise AssertionError('capture should be blocked')

def answer_no():
    dlg = QApplication.activeModalWidget()
    assert dlg.standardButton(dlg.defaultButton()) == QMessageBox.StandardButton.No
    dlg.done(QMessageBox.StandardButton.No.value)
QTimer.singleShot(0, answer_no); page._enable_guest()
assert not guest_mode.active() and page.guest_button.isEnabled()
def answer_yes():
    QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value)
QTimer.singleShot(0, answer_yes); page._enable_guest()
deadline = time.monotonic() + 3
while (not guest_mode.active() or page.guest_enabling) and time.monotonic() < deadline:
    app.processEvents(); QTest.qWait(10)
assert guest_mode.active() and not page.guest_button.isEnabled()
assert not vision_access.is_allowed('camera')
workspace.close(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
