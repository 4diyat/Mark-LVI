"""The voice view requires explicit activation, never starts for background state."""
import os
import subprocess
import sys

import pytest


def test_voice_mode_only_opens_on_user_request(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui.voice_overlay import VoiceOverlay
from ui import voice_wiring
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
overlay = VoiceOverlay(on_close=lambda: voice_wiring._on_close(shell))
assert overlay.start(active=False); shell._voice_overlay = overlay
shell.set_state('LISTENING'); app.processEvents()
assert not overlay.active and not shell._voice_mode_active
shell._main_surface.voice_mode_button.click(); app.processEvents()
assert overlay.active and shell._voice_mode_active
shell.set_state('IDLE'); app.processEvents()
assert overlay.active and overlay.state == 'voice_idle'
QTest.keyClick(overlay._window, Qt.Key.Key_Escape); app.processEvents()
assert not overlay.active and not shell._voice_mode_active and not shell.muted
shell.set_state('LISTENING'); app.processEvents()
assert not overlay.active
shell.muted = True
shell._main_surface.voice_mode_button.click(); app.processEvents()
assert not overlay.active and not shell._voice_mode_active
overlay.stop(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
