"""The redesigned command panel scales controls and painter together."""
import os
import subprocess
import sys

import pytest


def test_command_layout_scales_and_keeps_input_rows_and_retry_usable(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from ui.command_bar import CommandBar
from ui.command_layout import apply, scale_for
from ui.command_paint import BAR_HEIGHT, BAR_WIDTH, Row
from ui.qt_thread import init_dispatcher
app = QApplication([]); app.setQuitOnLastWindowClosed(False); init_dispatcher()
sent = []
bar = CommandBar(on_submit=lambda text: sent.append(text), asynchronous=True)
assert bar.open(), bar.error
screen = bar._window.screen().availableGeometry()
assert bar._window.width() <= screen.width() and bar._window.height() <= screen.height()
assert scale_for(1920, 1080) == 1
small = scale_for(640, 480)
assert 0 < small < 1 and BAR_WIDTH * small <= 616 and BAR_HEIGHT * small <= 456
for scale in (1.0, small):
    apply(bar, scale)
    bar.set_rows([Row('Contoh audit', 'Tercatat selesai', 'done', '#1fe393', 'Hasil contoh')])
    app.processEvents()
    assert abs(bar._window.width() - round(BAR_WIDTH * scale)) <= 1
    field, suggestions = bar._field.geometry(), bar._suggestions.geometry()
    row = bar._window._audit_accessible_labels[0].geometry()
    assert field.right() < suggestions.left() and field.bottom() < row.top()
    assert row.right() < bar._window.width() and row.bottom() < bar._window.height()
    assert bar._field.font().pointSizeF() > 8
    assert not bar._window.grab().isNull()
    bar._suggestions.menu().actions()[0].trigger(); app.processEvents()
    assert bar._field.text() and not sent and not bar.sending
bar.set_retry('coba')
assert bar._retry_button.isVisible()
assert bar._retry_button.geometry().bottom() < bar._window._audit_accessible_labels[0].geometry().top()
bar.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=25)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
