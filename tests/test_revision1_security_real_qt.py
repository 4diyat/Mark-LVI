"""Risk switches on the real desktop page control the actual action gate."""
import os
import subprocess
import sys

import pytest


def test_risk_permission_switch_controls_gate(tmp_path):
    code = r'''
import sys, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import action_gate, tool_permissions
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
tool_permissions.reset()
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); shell._main_surface.workspace_button.click()
page = shell._desktop_workspace.security
shell._desktop_workspace.navigate('security'); app.processEvents()
check = page.permission_checks['medium']; assert check.isChecked()
check.setChecked(False); app.processEvents()
ran = []
verdict = action_gate.check('file_controller', lambda: ran.append(1), {'action': 'delete'})
assert not verdict.ran and 'disabled' in verdict.message and not ran
check.setChecked(True); assert tool_permissions.is_allowed('medium')
shell._desktop_workspace.close(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
