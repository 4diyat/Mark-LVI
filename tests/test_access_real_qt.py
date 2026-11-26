"""Accessibility controls are labeled, honest and operable in real Qt."""
import os
import subprocess
import sys

import pytest


def test_contrast_and_unavailable_controls():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
from ui import pages_actions
app = QApplication([])
panel = TrayPanel({})
shell = type('Shell', (), {'_panel': panel})()
pages_actions._say = lambda *_: None
panel._actions['language'] = lambda code: pages_actions.language_set(shell, code)
panel._actions['contrast_set'] = lambda level: panel.set_high_contrast(level == 'high')
assert panel.open() and panel.set_page('access')
app.processEvents()
assert panel._labels['title'].isVisible()
standard = panel._buttons['ac_contrast:standard']
high = panel._buttons['ac_contrast:high']
assert standard.text() == 'Standard' and standard.isChecked()
assert high.text() == 'High' and not high.isChecked()
QTest.mouseClick(high, Qt.MouseButton.LeftButton)
assert panel.high_contrast and high.isChecked() and not standard.isChecked()
QTest.mouseClick(standard, Qt.MouseButton.LeftButton)
assert not panel.high_contrast and standard.isChecked() and not high.isChecked()
assert not panel._buttons['ac_scale'].isEnabled()
assert not panel._buttons['ac_motion'].isEnabled()
for i in range(3):
    assert not panel._buttons[f'ac_gest_edit:{i}'].isEnabled()
    assert panel._labels[f'ac_gest_act:{i}'].text() == 'Not available'
assert 'not available' in panel._labels['ac_size_note'].text().lower()
assert 'not available' in panel._labels['ac_motion_note'].text().lower()
QTest.mouseClick(panel._buttons['ac_lang:id'], Qt.MouseButton.LeftButton)
assert panel._labels['title'].text() == 'Aksesibilitas'
assert panel._buttons['ac_lang:id'].isChecked()
assert panel._buttons['ac_contrast:standard'].text() == 'Standar'
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
