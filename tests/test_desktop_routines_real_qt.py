"""Desktop routines operate on the real isolated store, with guarded writes."""
import os
import subprocess
import sys

import pytest


def test_routines_page_create_delete_toggle_and_failure(tmp_path):
    code = r'''
import os, sys, time, threading
from dataclasses import replace
from pathlib import Path
try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
from core.routines import Routine, Schedule
from memory import routine_store
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
i18n.set_locale('en')
store = routine_store.RoutineStore(Path(os.environ['JARVIS_STATE_DIR']) / 'isolated.json')
routine_store.default_store = lambda: store
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); home = shell._main_surface
home.workspace_button.click(); d = shell._desktop_workspace; d.buttons['routines'].click(); page = d.routines
def wait():
    end = time.monotonic() + 4
    while (page.loading or page.busy) and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not page.loading and not page.busy
wait()
assert d.current_page() == 'routines' and page.rows == []
assert page.create_button.isEnabled() and 'No routines' in page.status.text()
page.time_field.setText('24:00'); page.command_field.setText('First command')
page.confirm_create(); assert not store.all() and page.command_field.text() == 'First command'
page.time_field.setText('07:30')
def answer(button):
    def on_dialog():
        modal = QApplication.activeModalWidget()
        assert modal.defaultButton() == modal.button(QMessageBox.StandardButton.No)
        assert '07:30' in modal.text() and 'First command' in modal.text()
        modal.done(button.value)
    QTimer.singleShot(0, on_dialog)
answer(QMessageBox.StandardButton.No); page.confirm_create()
assert not store.all() and page.command_field.text() == 'First command'
answer(QMessageBox.StandardButton.Yes); page.confirm_create(); wait()
assert len(store.all()) == 1 and store.all()[0].payload == 'First command'
assert store.all()[0].enabled and store.all()[0].schedule == Schedule('07:30')
assert not page.command_field.text() and 'saved' in page.operation_status.text()
# A routine changed after the card was drawn must not be paused/deleted.
row = store.all()[0]; store.update(replace(row, payload='Changed command'))
page.cards[0].toggle.click(); wait()
assert store.get(row.id).enabled and 'changed' in page.operation_status.text()
assert page.cards[0].routine.payload == 'Changed command'
page.cards[0].toggle.click(); wait(); assert not store.get(row.id).enabled
# Enabling requires confirmation and accurately describes immediate delivery.
def check_enable():
    modal = QApplication.activeModalWidget()
    assert modal.defaultButton() == modal.button(QMessageBox.StandardButton.No)
    assert 'immediately' in modal.text() and 'Changed command' in modal.text()
    modal.done(QMessageBox.StandardButton.No.value)
QTimer.singleShot(0, check_enable); page.cards[0].toggle.click(); assert not store.get(row.id).enabled
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
page.cards[0].toggle.click(); wait(); assert store.get(row.id).enabled
# Change during confirmation: neither an unintended deletion nor a false success.
def change_during_dialog():
    item = store.get(row.id); store.update(replace(item, payload='Newer command'))
    QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value)
QTimer.singleShot(0, change_during_dialog); page.cards[0].delete.click(); wait()
assert store.get(row.id).payload == 'Newer command' and 'changed' in page.operation_status.text()
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.No.value))
page.cards[0].delete.click(); assert store.get(row.id) is not None
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
page.cards[0].delete.click(); wait(); assert store.get(row.id) is None
# Paging reaches all saved routines.
for i in range(6):
    store.add(Routine(str(i), 'Routine '+str(i), Schedule('08:00'), 'command', True))
page.refresh(); wait(); assert len(page.cards) == 4 and page.next.isEnabled()
page.next.click(); assert len(page.cards) == 2 and page.cards[0].routine.id == '4'
page.prev.click(); assert page.cards[0].routine.id == '0'
# Worker reads do not block Qt and a second refresh is not lost.
original = store.all; started = threading.Event(); release = threading.Event(); reads = []
def slow():
    reads.append(threading.get_ident())
    if len(reads) == 1: started.set(); release.wait(3)
    return original()
store.all = slow
page.refresh(); assert started.wait(1); page.refresh(); assert page.reload_requested
fired=[]; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents(); assert fired
release.set(); wait(); assert len(reads) == 2 and all(x != shell._ui_thread_id for x in reads)
store.all = original
# Failed writes keep the draft; do not claim success.
original_write = store._write
def fail_write(_rows): raise OSError('disk unavailable')
store._write = fail_write
page.time_field.setText('09:10'); page.command_field.setText('Keep this draft')
QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(QMessageBox.StandardButton.Yes.value))
page.confirm_create(); wait()
assert page.command_field.text() == 'Keep this draft' and page.time_field.text() == '09:10'
assert 'Could not save' in page.operation_status.text() and len(store.all()) == 6
store._write = original_write
# Unreadable storage is never mistaken for empty or overwritten.
store.path.write_text('{bad', encoding='utf8'); page.refresh(); wait()
assert page.rows is None and not page.create_button.isEnabled() and 'could not be read' in page.status.text()
assert store.path.read_text() == '{bad'
d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_routine_schedule_localized_for_indonesian_and_english():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n
from core.routines import Schedule
from ui.desktop_routines import schedule_text
app = QApplication([])
i18n.set_locale('id')
assert schedule_text(Schedule('07:00')) == 'Setiap hari · 07:00 (waktu lokal)'
assert schedule_text(Schedule('09:00', (0, 2))) == 'Sen, Rab · 09:00 (waktu lokal)'
i18n.set_locale('en')
assert schedule_text(Schedule('07:00')) == 'Every day · 07:00 (local time)'
assert schedule_text(Schedule('09:00', (0, 2))) == 'Mon, Wed · 09:00 (local time)'
assert schedule_text(Schedule('25:00')) == 'Invalid schedule'
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
