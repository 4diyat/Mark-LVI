"""Real Qt preview rendering and privacy lifecycle, with a synthetic JPEG."""
import os
import subprocess
import sys

import pytest


def test_voice_preview_never_survives_hide_or_stop(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
    from PyQt6.QtGui import QImage, QColor
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from types import SimpleNamespace
from core.workspace_gesture import WorkspaceHandController
from ui.hand_feed import poll_hand
from ui.voice_overlay import VoiceOverlay
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
overlay = VoiceOverlay(); assert overlay.start(active=True)
controller = WorkspaceHandController(); controller.status = 'active'
controller.sample = lambda: ()
feed = SimpleNamespace(_controller=controller)
overlay._gesture_feed = feed
shell = SimpleNamespace(_voice_overlay=overlay, _hand_feed=feed)
poll_hand(shell, controller)
assert controller._preview_enabled and overlay._camera_preview_image is None
image = QImage(20, 20, QImage.Format.Format_RGB32); image.fill(QColor('red'))
data = QByteArray(); buf = QBuffer(data); buf.open(QIODevice.OpenModeFlag.WriteOnly)
assert image.save(buf, 'JPG'); buf.close()
controller._publish_preview(bytes(data)); poll_hand(shell, controller)
assert overlay._camera_preview_image is not None
app.processEvents(); shown = overlay._window.grab().toImage()
assert shown.pixelColor(70, 535).red() > 180
# Tracking may continue for desktop control, but preview must be unsubscribed.
overlay.hide(); assert not controller._preview_enabled and not controller.preview()
assert overlay._camera_preview_image is None
controller._publish_preview(bytes(data)); assert not controller.preview()
overlay.show(); poll_hand(shell, controller); assert controller._preview_enabled
controller._publish_preview(bytes(data)); poll_hand(shell, controller)
overlay.stop(); assert not controller._preview_enabled and not controller.preview()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=25)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
