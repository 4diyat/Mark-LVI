"""Desktop history and memory use real stores with guarded operations."""
import os
import subprocess
import sys

import pytest


def test_desktop_history_memory_navigation_and_guards(tmp_path):
    code = r'''
import os, sys, threading, time
from pathlib import Path
try:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n, undo, audit_log
from memory import memory_manager as memory
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
i18n.set_locale('en')
audit_log.reset_shared(); undo.clear()
memory.MEMORY_PATH = Path(os.environ['JARVIS_STATE_DIR']) / 'memory.json'
memory.update_memory({'notes': {'name': '<b>Ada</b>'}, 'preferences': {'tea': 'green tea'}})
audit_log.shared().record('safe_test', 'safe', 'unverified', '<sample>')
calls = []
undo.push_undo('old operation', lambda: 'old reversed')
undo.push_undo('latest operation', lambda: calls.append(threading.get_ident()) or 'attempted')
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
home = shell._main_surface
home.field.setText('unsent draft')
home.nav_buttons['history'].click(); app.processEvents()
desktop = shell._desktop_workspace; history = desktop.history; mem = desktop.memory
assert desktop.current_page() == 'history' and desktop.window.isVisible() and not home.window.isVisible()
def wait(page):
    end = time.monotonic() + 4
    while (getattr(page, 'loading', False) or getattr(page, 'busy', False) or
           getattr(page, '_loading', False) or getattr(page, '_busy', False)) and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not (getattr(page, 'loading', False) or getattr(page, 'busy', False) or
                getattr(page, '_loading', False) or getattr(page, '_busy', False))
wait(history)
assert [r[1] for r in history.undo_rows] == ['latest operation', 'old operation']
assert len(history.row_widgets) == 2 and history.row_widgets[0][1].isEnabled()
assert not history.row_widgets[1][1].isEnabled()
assert history.audit_rows[-1]['outcome'] == 'unverified'
history.search.setText('old'); app.processEvents()
assert len(history.row_widgets) == 1 and not history.row_widgets[0][1].isEnabled()
history.search.clear(); app.processEvents()
# Newer action invalidates the displayed identity: no wrong reversal.
undo.push_undo('arrived later', lambda: calls.append('wrong'))
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
history.row_widgets[0][1].click(); wait(history)
assert not calls and 'changed' in history.status.text().lower()
assert history.undo_rows[0][1] == 'arrived later'
# Change while modal is open prevents clearing the wrong snapshot.
def change_then_yes():
    undo.push_undo('changed during dialog', lambda: '')
    QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value)
QTimer.singleShot(0, change_then_yes)
history.confirm_clear(); wait(history)
assert undo.history()[0] == 'changed during dialog'
assert 'changed' in history.status.text().lower()
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.No.value))
history.confirm_clear(); assert len(undo.history()) == 4
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
history.confirm_clear(); wait(history)
assert undo.history() == [] and not history.clear_button.isEnabled()
# Undo executes on a worker, never blocks Qt, and reports only the actual result.
started, release = threading.Event(), threading.Event()
def reversible():
    started.set(); release.wait(2); calls.append(threading.get_ident()); return 'reversal attempted'
undo.push_undo('worker test', reversible)
history.refresh(); wait(history)
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.No.value))
history.row_widgets[0][1].click(); assert not started.is_set() and undo.history() == ['worker test']
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
history.row_widgets[0][1].click()
assert started.wait(1) and history.busy
fired = []
QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents()
assert fired and not history.clear_button.isEnabled()
release.set(); wait(history)
assert len(calls) == 1 and calls[0] != shell._ui_thread_id
assert 'attempted' in history.status.text().lower() and not undo.history()
# Corrupt audit is reported unavailable, not an empty audit.
audit_path = Path(os.environ['JARVIS_STATE_DIR']) / 'audit.jsonl'
audit_path.write_text('{broken\n', encoding='utf8')
history.refresh(); wait(history)
assert history.audit_rows is None and history.undo_rows == []
assert audit_path.read_text() == '{broken\n'
# Memory is the same store and the same reusable desktop window.
def answer_both(first, second):
    def answer_first():
        QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(second.value))
        QApplication.activeModalWidget().done(first.value)
    QTimer.singleShot(0, answer_first)
desktop.buttons['memory'].click(); wait(mem)
assert desktop.current_page() == 'memory' and len(mem.memory_cards) == 2
card = next(c for c in mem.memory_cards if c.row['key'] == 'name')
assert card.value.text() == '<b>Ada</b>' and card.value.textFormat() == Qt.TextFormat.PlainText
card.expand.click(); assert card.details.isVisible()
row = card.row
memory.update_memory({'notes': {'name': 'updated'}})
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes)
mem.confirm_forget(row); wait(mem)
assert 'changed' in mem.status.text().lower()
assert memory.load_memory(strict=True)['notes']['name']['value'] == 'updated'
mem.refresh(); wait(mem)
card = next(c for c in mem.memory_cards if c.row['key'] == 'name')
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.No.value))
mem.confirm_forget(card.row); assert memory.load_memory(strict=True)['notes']['name']['value'] == 'updated'
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
mem.confirm_forget(card.row); assert memory.load_memory(strict=True)['notes']['name']['value'] == 'updated'
answer_both(QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes)
mem.confirm_forget(card.row); wait(mem)
assert 'name' not in memory.load_memory(strict=True)['notes']
assert not mem.clear_button.isEnabled()
desktop.return_home(); app.processEvents()
assert home.field.text() == 'unsent draft' and home.window.isVisible()
home.nav_buttons['memory'].click(); wait(mem)
assert shell._desktop_workspace is desktop and desktop.current_page() == 'memory'
desktop.close(); home.close(); undo.clear()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
