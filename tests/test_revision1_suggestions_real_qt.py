"""Suggestions only fill the field; choosing one is not an execution approval."""
import os
import subprocess
import sys

import pytest


def test_suggestion_selection_does_not_send(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.command_bar import CommandBar
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
sent = []
bar = CommandBar(on_submit=lambda text: sent.append(text), asynchronous=True)
assert bar.open()
menu = bar._suggestions.menu()
menu.popup(bar._suggestions.mapToGlobal(bar._suggestions.rect().bottomLeft()))
app.processEvents(); QTest.qWait(50)
assert menu.isVisible()
menu.setActiveAction(menu.actions()[0])
QTest.keyClick(menu, Qt.Key.Key_Return)
app.processEvents(); QTest.qWait(50)
assert bar._field.text() == 'Show system status'
assert not sent and not bar.sending
bar.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
