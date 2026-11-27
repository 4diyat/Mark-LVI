"""Security desktop uses actual policy and audit, not invented permissions."""
import os
import subprocess
import sys

import pytest


def test_security_page_permissions_filter_and_explicit_export(tmp_path):
    code = r'''
import json, os, sys, time, threading
from pathlib import Path
try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QBoxLayout
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n, audit_log, risk_policy
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
i18n.set_locale('en'); audit_log.reset_shared()
for i in range(55):
    assert audit_log.shared().record('sample_' + str(i), 'safe', 'unverified' if i % 2 else 'done', '<test>')
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
home = shell._main_surface; home.workspace_button.click()
d = shell._desktop_workspace; d.buttons['security'].click(); sec = d.security
def wait():
    end = time.monotonic() + 4
    while (sec.loading or sec.exporting) and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not sec.loading and not sec.exporting
wait()
assert d.current_page() == 'security' and d.buttons['security'].isChecked()
counts = risk_policy.registered()
for level, label in sec.risk_counts.items():
    assert int(label.text()) == sum(value == level for value in counts.values())
assert len(sec.records) == 50 and len(sec.audit_cards) == 50
app.processEvents(); QTest.qWait(20)
assert sec.records_area.height() <= 370 and sec.records_area.verticalScrollBar().maximum() > 0
assert sec.export_button.isVisible()
assert 'not an OS permission' in sec.mic_status.text()
assert '<test>' in sec.audit_cards[0].findChildren(type(sec.mic_status))[-1].text()
assert sec.audit_cards[0].findChildren(type(sec.mic_status))[-1].textFormat() == Qt.TextFormat.PlainText
sec.filter.setCurrentIndex(sec.filter.findData('unverified'))
assert len(sec.audit_cards) == 25
assert sec.export_button.isEnabled()
# Explicit cancellation makes no file; export reads all, not only the filter.
def answer_both(first, second):
    def answer_first():
        QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(second.value))
        QApplication.activeModalWidget().done(first.value)
    QTimer.singleShot(0, answer_first)
out = Path(os.environ['JARVIS_STATE_DIR']) / 'export.json'
QFileDialog.getSaveFileName = lambda *args: (str(out), 'JSON')
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.No.value))
sec.choose_export(); assert not out.exists()
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
sec.choose_export(); assert not out.exists()
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes)
sec.choose_export(); wait()
assert len(json.loads(out.read_text())) == 55 and '55 records' in sec.export_status.text()
out.write_text('keep', encoding='utf8')
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes)
sec.choose_export(); wait()
assert out.read_text() == 'keep' and 'not overwritten' in sec.export_status.text()
# A concurrent refresh queues a second read; Qt remains responsive while storage blocks.
log = audit_log.shared(); original = log.entries
started, release = threading.Event(), threading.Event()
reads = []
def slow_entries(*args, **kwargs):
    reads.append(threading.get_ident())
    if len(reads) == 1:
        started.set(); release.wait(3)
    return original(*args, **kwargs)
log.entries = slow_entries
sec.refresh(); assert started.wait(1)
sec.refresh(); assert sec.reload_requested
fired = []; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents()
assert fired and not sec.export_button.isEnabled()
release.set(); wait()
assert len(reads) == 2 and all(worker != shell._ui_thread_id for worker in reads)
log.entries = original
# Export re-reads strictly: corruption after display cannot create a false empty file.
Path(os.environ['JARVIS_STATE_DIR'], 'audit.jsonl').write_text('{bad\n', encoding='utf8')
corrupt_out = Path(os.environ['JARVIS_STATE_DIR']) / 'corrupt-export.json'
sec.export_to(str(corrupt_out)); wait()
assert not corrupt_out.exists() and 'failed' in sec.export_status.text().lower()
# A corrupted audit must be unavailable, not falsely empty/exported.
sec.refresh(); wait()
assert sec.records is None and not sec.export_button.isEnabled() and 'could not be read' in sec.audit_status.text()
assert Path(os.environ['JARVIS_STATE_DIR'], 'audit.jsonl').read_text() == '{bad\n'
# Compact layout uses stacked panels instead of clipping controls.
d.window.resize(900, 600); app.processEvents(); QTest.qWait(100)
assert sec.columns.direction() == QBoxLayout.Direction.TopToBottom
assert sec.width() <= d.stack.width()
d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
