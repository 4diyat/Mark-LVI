"""Clipboard page regression with real Qt, using an isolated test clipboard."""
import os
import subprocess
import sys

import pytest


def test_tools_theme_clipboard_states_and_clicks():
    code = r'''
import sys
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui import pages_people, pages_actions, tray_panel

app = QApplication([])
clipboard = {'text': None}
pages_people.clipboard_text = lambda: clipboard['text']
messages = []
pages_actions._say = lambda shell, text: messages.append(text)
writes = []
def write(shell, text, done, fail):
    writes.append(text)
    clipboard['text'] = text
    return True
pages_actions._clipboard_set = write
shell = type('Shell', (), {})()
panel = tray_panel.TrayPanel({'tools_safe': lambda: pages_actions.tools_mark_safe(shell),
                               'tools_clear': lambda: pages_actions.tools_clear(shell)})
shell._panel = panel
assert panel.open(), panel.error
assert panel.set_page('tools')
app.processEvents()
assert panel._labels['title'].isVisible()
assert panel._labels['tl_clip'].text() == 'Clipboard unavailable'
assert not panel._buttons['tl_safe'].isEnabled()
clipboard['text'] = '<b>secret</b> sk-abcdefghijklmnop'
panel.refresh()
assert panel._labels['tl_clip'].textFormat() == Qt.TextFormat.PlainText
assert panel._labels['tl_clip'].text().startswith('<b>secret</b>')
assert panel._buttons['tl_safe'].isEnabled()
QTest.mouseClick(panel._buttons['tl_safe'], Qt.MouseButton.LeftButton)
assert panel._marked_safe
clipboard['text'] = 'changed clipboard'
QTest.mouseClick(panel._buttons['tl_clear'], Qt.MouseButton.LeftButton)
assert not writes and not panel._marked_safe
QTest.mouseClick(panel._buttons['tl_clear'], Qt.MouseButton.LeftButton)
assert writes == ['']
assert panel._labels['tl_clip'].text() == 'No text on clipboard'
assert not panel._buttons['tl_clear'].isEnabled()
assert panel.set_theme('light')
assert '#ffffff' in panel._labels['tl_clip_card'].styleSheet().lower()
assert panel.set_theme('dark')
assert '#14181c' in panel._labels['tl_clip_card'].styleSheet().lower()
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_file_search_keeps_real_qt_event_loop_responsive():
    code = r'''
import sys, threading, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui import pages_people, tray_panel

app = QApplication([])
owner = threading.get_ident()
entered, release = threading.Event(), threading.Event()
real_search = pages_people.find_files
pages_people.clipboard_text = lambda: None
calls = []
def controlled_search(query, *, cancel):
    assert threading.get_ident() != owner
    calls.append(query)
    if query == 'old':
        entered.set()
        assert release.wait(2)
    return real_search(query, cancel=cancel)
pages_people.find_files = controlled_search
with tempfile.TemporaryDirectory() as tmp:
    Path.home = classmethod(lambda cls: Path(tmp))
    docs = Path(tmp) / 'Documents'
    docs.mkdir()
    result = docs / 'new-report.txt'
    result.write_text('test')
    panel = tray_panel.TrayPanel({})
    assert panel.open(), panel.error
    panel.set_page('tools')
    field = panel._fields['tl_find']
    field.setText('old')
    assert panel.run_search('old')
    assert entered.wait(1)
    assert panel._labels['tl_hit:0'].text() == 'Searching…'
    loop = QEventLoop()
    def change():
        assert threading.get_ident() == owner
        field.setText('new')
        assert panel.search_status == 'idle'
        assert panel.run_search('new')
        release.set()
    def check():
        if panel.search_status == 'done':
            loop.quit()
    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(20)
    QTimer.singleShot(20, change)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert calls == ['old', 'new'], calls
    assert panel.search_status == 'done', panel.search_status
    assert panel.hits == (str(result),), panel.hits
    assert panel._labels['tl_hit:0'].text() == str(result)
    assert not panel.notes, panel.notes
    panel.stop()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=10)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
