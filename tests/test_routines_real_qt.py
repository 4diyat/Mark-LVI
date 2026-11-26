"""Routine empty state and unavailable builder in real Qt."""
import os
import subprocess
import sys

import pytest


def test_routines_show_real_count_and_reject_empty_builder():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui import pages_people
from ui.tray_panel import TrayPanel
app = QApplication([])
pages_people.routines = lambda: []
panel = TrayPanel({})
assert panel.open() and panel.set_page('routines')
app.processEvents()
assert panel._labels['title'].isVisible()
assert panel._labels['subtitle'].text() == '0 enabled routines'
assert panel._labels['rt_card:0'].isVisible()
assert not panel._labels['rt_card:1'].isVisible()
assert not panel._labels['rt_card:2'].isVisible()
assert panel._buttons['rt_builder_create'].isEnabled()
assert panel._inputs['rt_builder_edit'].isEnabled()
assert panel._buttons['rt_builder_create'].isVisible()
pages_people.routines = lambda: [
    {'name': 'one', 'when': '07:00', 'what': 'work', 'on': True},
    {'name': 'two', 'when': '08:00', 'what': 'work', 'on': False},
    {'name': 'three', 'when': '09:00', 'what': 'work', 'on': True},
    {'name': 'four', 'when': '10:00', 'what': 'work', 'on': False},
]
panel.refresh()
assert panel._labels['subtitle'].text() == '2 enabled routines'
assert panel._labels['rt_more'].text() == 'Page 1 / 2 · 4 routines'
assert panel._labels['rt_card:1'].isVisible()
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_routine_buttons_act_on_the_displayed_id_after_store_reorders():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core.routines import Routine, Schedule
from memory import routine_store
from ui import pages_actions
from ui.tray_panel import TrayPanel
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    store = routine_store.RoutineStore(Path(tmp) / 'routines.json')
    routine_store.default_store = lambda: store
    one = Routine('one', 'First', Schedule('07:00'), 'First job', True)
    two = Routine('two', 'Second', Schedule('08:00'), 'Second job', True)
    store.add(one); store.add(two)
    shell = type('Shell', (), {})()
    pages_actions._say = lambda *_: None
    panel = TrayPanel({'routine_toggle': lambda rid, on: pages_actions.routine_toggle(shell, rid, on),
                       'routine_delete': lambda rid: pages_actions.routine_delete(shell, rid)})
    shell._panel = panel
    assert panel.open() and panel.set_page('routines')
    app.processEvents()
    assert panel._labels['rt_name:0'].text() == 'First'
    # The row still displays First after the underlying file changes order.
    assert store.remove('one')
    store.add(one)
    QTest.mouseClick(panel._buttons['rt_toggle:0'], Qt.MouseButton.LeftButton)
    assert not store.get('one').enabled
    assert store.get('two').enabled
    assert panel._labels['rt_name:0'].text() == 'Second'
    # Move Second behind First without repainting and delete the visible row.
    assert store.remove('two')
    store.add(two)
    QTest.mouseClick(panel._buttons['rt_delete:0'], Qt.MouseButton.LeftButton)
    assert store.get('two') is None
    assert store.get('one') is not None
    assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_stored_routines_can_be_reached_without_changing_their_order():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core.routines import Routine, Schedule
from memory import routine_store
from ui import pages_actions
from ui.tray_panel import TrayPanel
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    store = routine_store.RoutineStore(Path(tmp) / 'routines.json')
    routine_store.default_store = lambda: store
    for i in range(5):
        store.add(Routine(str(i), 'Routine '+str(i), Schedule('07:00'), 'command', True))
    shell = type('Shell', (), {})()
    pages_actions._say = lambda *_: None
    panel = TrayPanel({'routine_delete': lambda rid: pages_actions.routine_delete(shell, rid)})
    shell._panel = panel
    assert panel.open() and panel.set_page('routines')
    app.processEvents()
    assert panel._labels['rt_name:0'].text() == 'Routine 0'
    assert not panel._buttons['rt_prev'].isEnabled()
    assert panel._buttons['rt_next'].isEnabled()
    QTest.mouseClick(panel._buttons['rt_next'], Qt.MouseButton.LeftButton)
    assert panel._labels['rt_name:0'].text() == 'Routine 3'
    assert panel._labels['rt_name:1'].text() == 'Routine 4'
    assert not panel._buttons['rt_next'].isEnabled()
    QTest.mouseClick(panel._buttons['rt_delete:1'], Qt.MouseButton.LeftButton)
    QTest.mouseClick(panel._buttons['rt_delete:0'], Qt.MouseButton.LeftButton)
    assert panel._labels['rt_name:0'].text() == 'Routine 0'
    assert not panel._buttons['rt_prev'].isEnabled()
    assert [r.id for r in store.all()] == ['0', '1', '2']
    assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_create_daily_routine_requires_time_and_command_and_saves_both():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from memory import routine_store
from ui import pages_actions
from ui.tray_panel import TrayPanel
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    store = routine_store.RoutineStore(Path(tmp) / 'routines.json')
    routine_store.default_store = lambda: store
    notes = []
    pages_actions._say = lambda _shell, text: notes.append(text)
    shell = type('Shell', (), {})()
    panel = TrayPanel({'routine_create': lambda: pages_actions.routine_create(shell)})
    shell._panel = panel
    assert panel.open() and panel.set_page('routines')
    app.processEvents()
    time = panel._inputs['rt_builder_edit']
    command = panel._inputs['rt_builder_command']
    create = panel._buttons['rt_builder_create']
    assert time.isVisible() and command.isVisible() and create.isEnabled()
    time.setText('07:00')
    QTest.mouseClick(create, Qt.MouseButton.LeftButton)
    assert store.all() == [] and time.text() == '07:00'
    assert panel._labels['rt_builder_status'].text()
    command.setText('Summarize my notes')
    for bad in ('25:00', '07', 'Monday 07:00'):
        time.setText(bad)
        QTest.mouseClick(create, Qt.MouseButton.LeftButton)
        assert store.all() == [] and command.text() == 'Summarize my notes'
    time.setText('07:00')
    QTest.mouseClick(create, Qt.MouseButton.LeftButton)
    entries = store.all()
    assert len(entries) == 1
    assert entries[0].schedule.time == '07:00' and entries[0].schedule.days == ()
    assert entries[0].payload == 'Summarize my notes' and entries[0].enabled
    assert not time.text() and not command.text()
    assert panel._labels['rt_builder_status'].text() == 'Routine created.'
    assert 'Summarize my notes' in panel._labels['rt_name:0'].text()
    assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_unreadable_store_is_not_empty_and_cannot_be_overwritten():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from memory import routine_store
from ui import pages_actions
from ui.tray_panel import TrayPanel
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'routines.json'
    path.write_text('{broken json')
    routine_store.default_store = lambda: routine_store.RoutineStore(path)
    messages = []
    pages_actions._say = lambda _s, msg: messages.append(msg)
    shell = type('Shell', (), {})()
    panel = TrayPanel({})
    shell._panel = panel
    assert panel.open() and panel.set_page('routines')
    assert panel._labels['rt_name:0'].text() == 'Routines unavailable'
    assert 'Unknown' in panel._labels['subtitle'].text()
    assert not panel._buttons['rt_builder_create'].isEnabled()
    panel._inputs['rt_builder_edit'].setText('09:00')
    panel._inputs['rt_builder_command'].setText('do something')
    assert not pages_actions.routine_create(shell)
    assert panel._labels['rt_builder_status'].text() == 'Routine could not be created.'
    assert panel._inputs['rt_builder_command'].text() == 'do something'
    assert path.read_text() == '{broken json'
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
