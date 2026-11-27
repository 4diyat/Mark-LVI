"""Voice mode reuses the real main-window orb and responds to audio samples."""
import os
import subprocess
import sys

import pytest


def test_voice_orb_animation_audio_motion_preference_and_lifecycle(tmp_path):
    code = r'''
import sys, threading
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from ui.shell import AmbientShell
from ui.hud_orb import OrbCore
from ui.main_surface import open_main
from ui.voice_overlay import VoiceOverlay
from ui import voice_wiring
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
overlay = VoiceOverlay(on_close=lambda: voice_wiring._on_close(shell))
assert overlay.start(active=False); shell._voice_overlay = overlay
orb = overlay._voice_orb
assert isinstance(orb, OrbCore) and isinstance(shell._main_surface.orb, OrbCore)
assert not orb.timer.isActive()
shell.set_state('LISTENING'); shell._main_surface.voice_mode_button.click()
app.processEvents(); assert overlay.active and orb.timer.isActive()
# Real rendered pixels change over time, even without an audio sample.
first = orb.grab().toImage(); phase = orb.phase
QTest.qWait(600); app.processEvents()
second = orb.grab().toImage()
assert phase != orb.phase and first != second
# The same worker-to-Qt delivery used by audio in the application.
t = threading.Thread(target=lambda: shell.set_audio_level(.75)); t.start(); t.join()
QTest.qWait(100); app.processEvents()
assert abs(orb.samples[-1] - .75) < .001 and abs(overlay._audio_level - .75) < .001
QTest.qWait(500); app.processEvents()
assert orb.level == 0 and overlay._audio_level == 0
# The main accessibility option also freezes voice mode and clears the meter.
shell._main_surface.reduce_motion.setChecked(True); app.processEvents()
assert not orb.timer.isActive() and orb.reduced_motion and not any(orb.samples)
phase = orb.phase; frozen = orb.grab().toImage()
shell.set_audio_level(.9); QTest.qWait(300); app.processEvents()
assert orb.phase == phase and frozen == orb.grab().toImage()
assert overlay._audio_level == 0 and not any(orb.samples)
shell._main_surface.reduce_motion.setChecked(False); app.processEvents()
assert orb.timer.isActive() and not orb.reduced_motion
overlay.hide(); app.processEvents()
assert not orb.timer.isActive() and overlay._timer is None
assert overlay._audio_level == 0 and not any(orb.samples)
shell.set_audio_level(.8); app.processEvents()
assert not any(orb.samples) and overlay._audio_level == 0
overlay.show(); app.processEvents(); assert orb.timer.isActive()
overlay.stop(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=25)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
