"""Exercise actual Qt rendering and hit testing when Qt can run offscreen."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


def test_permissions_theme_and_switch_on_real_qt():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from ui import tray_panel
from ui.tray_panel_model import Snapshot

app = QApplication([])
states = {
    'screen': {'on': True, 'fixed': True},
    'microphone': {'on': True, 'fixed': True},
    'files': {'on': None, 'fixed': True, 'note': 'unavailable'},
    'apps': {'on': None, 'fixed': True, 'note': 'unavailable'},
}
tray_panel.snapshot = lambda: Snapshot(permissions=states)
calls = []
def permission(key, value):
    calls.append((key, value))
    states[key]['on'] = value
panel = tray_panel.TrayPanel({'permission': permission})
assert panel.open(), panel.error
assert panel.set_page('privacy')
assert panel.set_theme('light')
app.processEvents()
assert panel._labels['p6_status:screen'].text() != 'Available'
assert panel._labels['p6_status:microphone'].text() == 'Unknown'
assert not panel._labels['perm_dot:screen'].isVisible()
assert not panel._buttons['p6:screen'].isEnabled()
assert '#ffffff' in panel._labels['p6_card:screen'].styleSheet().lower()
pixel = panel._window.grab().toImage().pixelColor(30, 110)
assert pixel.red() > 220 and pixel.green() > 220 and pixel.blue() > 220, pixel.name()
assert panel._labels['p6_status:files'].text() == 'Not available'
assert not panel._buttons['p6:files'].isEnabled()
assert not panel._labels['perm_dot:files'].isVisible()
assert not panel.press_permission('files', True)
assert calls == []
assert panel.set_theme('dark')
app.processEvents()
assert '#14181c' in panel._labels['p6_card:screen'].styleSheet().lower()
assert panel.set_page('memory')
assert panel._labels['title'].isVisible() and panel._labels['subtitle'].isVisible()
'''
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run([sys.executable, "-c", code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip("PyQt6 or its system libraries are unavailable")
    assert result.returncode == 0, result.stdout + result.stderr
