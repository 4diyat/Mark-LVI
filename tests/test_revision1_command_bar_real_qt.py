"""Real Qt checks for audit outcomes, accessible labels and the command bar."""
import os
import subprocess
import sys

import pytest


def test_command_bar_outcomes_are_accessible_and_empty_is_honest(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import audit_log, i18n
from ui.command_bar import CommandBar
from ui.command_paint import default_rows
from ui.hud_icons import icon
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
from ui.qt_thread import init_dispatcher
init_dispatcher()
i18n.set_locale('id')
audit_log.reset_shared()
audit = audit_log.shared()
assert default_rows(strict=True) == []
for tool, result in [('uji-gagal', 'failed'), ('uji-belum', 'unverified'), ('uji-selesai', 'done')]:
    audit.record(tool, 'safe', result, 'Contoh ' + 'panjang ' * 100)
rows = default_rows(strict=True)
assert [r.level for r in rows] == ['done', 'unverified', 'failed']
assert [r.state for r in rows] == ['Tercatat selesai', 'Belum terverifikasi', 'Gagal']
for name in ('hexagon', 'sparkles', 'shield-check', 'triangle-alert', 'file-text'):
    assert not icon(name).isNull(), name
bar = CommandBar(asynchronous=True)
assert bar.open(), bar.error
import time
end = time.monotonic() + 5
while bar._audit_running and time.monotonic() < end:
    app.processEvents(); QTest.qWait(10)
assert not bar._audit_running
app.processEvents()
labels = bar._window._audit_accessible_labels
assert len(labels) == 3 and all(label.isVisible() for label in labels)
assert [label.accessibleName().split(': ')[1].split('.')[0] for label in labels] == [r.state for r in rows]
assert all(label.toolTip() == label.accessibleName() for label in labels)
assert all('panjang ' * 20 in label.toolTip() for label in labels)
labels[0].setFocus(); app.processEvents()
assert labels[0].hasFocus()
QTest.keyClick(labels[0], Qt.Key.Key_Escape); app.processEvents()
assert not bar.is_open
bar.open(); bar.set_rows([]); app.processEvents()
assert all(not label.isVisible() for label in labels)
bar.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
