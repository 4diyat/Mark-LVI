"""Qt exercise of the voice tracking controls with synthetic hand samples."""
import os
import subprocess
import sys

import pytest


def test_voice_tracking_controls_use_camera_worker_and_stop_on_close(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
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
    stopped = False
    def start(self): self.status = 'active'; return True
    def stop(self): self.status = 'off'; self.stopped = True
    def sample(self): return ((.5, .5, False, False),)
    def landmarks(self): return tuple((.2 + (i % 5) * .13, .1 + (i // 5) * .18) for i in range(21))
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell) and voice_wiring.start_voice_overlay(shell)
feed = shell._hand_feed; feed._controller = Controller()
overlay = shell._voice_overlay
assert not feed._started and not overlay.active
shell.set_state('LISTENING'); shell._main_surface.voice_mode_button.click(); app.processEvents()
assert overlay.active and not feed._started
start, pause = overlay._gesture_buttons
assert start.isVisible() and not pause.isEnabled()
QTest.mouseClick(start, Qt.MouseButton.LeftButton); QTest.qWait(110); app.processEvents()
assert feed._started and pause.isEnabled() and overlay._has_hand
assert len(overlay._gesture_points) == 21 and overlay._gesture_message == 'TANGAN TERDETEKSI'
feed._timer.stop()
with_points = overlay._window.grab().copy(40, 485, 250, 140).toImage()
points = overlay._gesture_points; overlay._gesture_points = (); overlay._refresh(); app.processEvents()
without_points = overlay._window.grab().copy(40, 485, 250, 140).toImage()
assert with_points != without_points
feed._timer.start(); overlay._gesture_points = points
QTest.mouseClick(pause, Qt.MouseButton.LeftButton); app.processEvents()
assert overlay.gestures_paused and not overlay._gesture_points
assert 'KAMERA AKTIF' in overlay._gesture_message
QTest.mouseClick(pause, Qt.MouseButton.LeftButton); QTest.qWait(100); app.processEvents()
assert not overlay.gestures_paused and len(overlay._gesture_points) == 21
# Qt modal dialogs freeze OS gesture input, even without a core confirmation.
modal = QMessageBox(overlay._window); modal.setText('test'); modal.setModal(True); modal.show(); app.processEvents()
assert hand_feed.gesture_context(shell).modal_open
modal.hide(); overlay._window.activateWindow(); app.processEvents(); QTest.qWait(30)
QTest.keyClick(overlay._window, Qt.Key.Key_Escape); app.processEvents()
assert not overlay.active and not feed._started and feed._controller.stopped
voice_wiring.stop_voice_overlay(shell); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=25)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
