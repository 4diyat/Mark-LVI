"""Navigation hit-testing, return path and theme with real Qt."""
import os
import subprocess
import sys

import pytest


def test_more_cards_are_clickable_and_return_to_their_parent():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
app = QApplication([])
panel = TrayPanel({})
assert panel.open() and panel.set_page('more')
app.processEvents()
page = panel._pages['more']
name = panel._labels['more_name:routines']
button = panel._buttons['more:routines']
assert panel._labels['more_sub'].geometry().bottom() < panel._buttons['more:memory'].geometry().top()
assert button.accessibleName() == name.text()
# Test where the name is painted, not just the button's exposed corner.
point = name.geometry().center()
target = page.childAt(point)
assert target is button, (target, button)
QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFrom(page, point))
assert panel.page == 'routines'
QTest.mouseClick(panel._buttons['panel_back'], Qt.MouseButton.LeftButton)
assert panel.page == 'more'
QTest.mouseClick(panel._buttons['panel_back'], Qt.MouseButton.LeftButton)
assert panel.page == 'main'
assert panel.set_page('more') and panel.set_theme('light')
assert '#0b1a24' in panel._labels['more_name:routines'].styleSheet().lower()
assert '#5b7480' in panel._labels['more_board:routines'].styleSheet().lower()
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
