"""Explicit, session-only desktop gesture opt-in with a real Qt dialog."""
import os
import subprocess
import sys

import pytest


def test_desktop_gestures_confirm_cancel_pause_and_shortcut_failure(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox
except ImportError:
    sys.exit(77)
from core import i18n
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui import voice_wiring, hand_feed
app = QApplication([]); app.setQuitOnLastWindowClosed(False); i18n.set_locale('id')
voice_wiring.start_pause_hotkey = lambda shell: 'window'
voice_wiring.gesture_bridge_enabled = lambda: False
hand_feed.gesture_bridge_enabled = lambda: False
class Controller:
    status = 'off'
    def start(self): self.status = 'active'; return True
    def stop(self): self.status = 'off'
    def sample(self): return ((.5, .5, False, False),)
    def landmarks(self): return ((.5, .5),) * 21
class Bridge:
    enabled = False
    def __init__(self): self.samples = []
    def enable(self): self.enabled = True; return True
    def disable(self): self.enabled = False
    def pump(self, sample, ctx): self.samples.append((sample, ctx))
class Hotkey:
    scope = 'global'
    def stop(self): pass
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell) and voice_wiring.start_voice_overlay(shell)
feed = shell._hand_feed; feed._controller = Controller(); feed._bridge = Bridge()
shell._pause_hotkey = Hotkey()
overlay = shell._voice_overlay
shell.set_state('LISTENING'); shell._main_surface.voice_mode_button.click(); app.processEvents()
QTest.mouseClick(overlay._gesture_buttons[0], Qt.MouseButton.LeftButton); QTest.qWait(100)
assert feed._started and not feed.bridge.enabled
assert overlay._desktop_button.isEnabled()
# Rejecting does not arm, close, or call the pointer bridge.
def reject():
    dialog = QApplication.activeModalWidget()
    assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.No
    QTest.keyClick(dialog.defaultButton(), Qt.Key.Key_Return)
QTimer.singleShot(0, reject)
QTest.mouseClick(overlay._desktop_button, Qt.MouseButton.LeftButton); app.processEvents()
assert overlay.active and not feed.bridge.enabled and not getattr(feed, '_voice_desktop_control', False)
# Confirmation activates session-only control and hides the fullscreen view.
def accept():
    dialog = QApplication.activeModalWidget()
    assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.No
    dialog.done(QMessageBox.StandardButton.Yes.value)
QTimer.singleShot(0, accept)
QTest.mouseClick(overlay._desktop_button, Qt.MouseButton.LeftButton); app.processEvents()
assert not overlay.active and feed._started and feed.bridge.enabled and feed._voice_desktop_control
assert hand_feed.gesture_context(shell).os_mode
# Global pause uses the same overlay state even while the view is hidden.
assert voice_wiring.toggle_gestures(shell)
feed.poll(); assert feed.bridge.samples[-1][0] is None
assert not voice_wiring.toggle_gestures(shell)
# Reopening voice mode provides a direct stop, without disabling tracking there.
shell._main_surface.voice_mode_button.click(); app.processEvents()
assert overlay.active and 'Matikan' in overlay._desktop_button.text()
QTest.mouseClick(overlay._desktop_button, Qt.MouseButton.LeftButton); app.processEvents()
assert not feed.bridge.enabled and not feed._voice_desktop_control and feed._started
QTimer.singleShot(0, accept)
QTest.mouseClick(overlay._desktop_button, Qt.MouseButton.LeftButton); app.processEvents()
assert feed._voice_desktop_control and feed.bridge.enabled and not overlay.active
# If the global stop shortcut fails, camera and input shut down.
shell._pause_hotkey.scope = 'window'
feed.poll()
assert not feed._started and not feed.bridge.enabled and not feed._voice_desktop_control
assert not hand_feed.gesture_context(shell).os_mode
voice_wiring.stop_voice_overlay(shell); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=25)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
