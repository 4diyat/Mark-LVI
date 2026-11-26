"""Real Qt desktop tools: explicit clipboard, bounded search, honest help."""
import os
import subprocess
import sys

import pytest


def test_desktop_tools_clipboard_search_help_and_drafts(tmp_path):
    code = r'''
import sys, threading, time
from pathlib import Path
try:
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
from ui import pages_people
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False); i18n.set_locale('en')
clip = {'text': None, 'calls': 0}
def clipboard():
    assert threading.get_ident() != shell._ui_thread_id
    clip['calls'] += 1
    return clip['text']
pages_people.clipboard_text = clipboard
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); home = shell._main_surface
home.workspace_button.click(); desktop = shell._desktop_workspace
desktop.buttons['tools'].click(); page = desktop.tools
assert desktop.current_page() == 'tools' and clip['calls'] == 0
assert page.clip_text.text() == 'Not read.'
def wait_clip():
    end = time.monotonic() + 3
    while page.clip_running and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not page.clip_running
page.read_clipboard(); wait_clip(); assert 'could not' in page.clip_text.text()
clip['text'] = ''; page.read_clipboard(); wait_clip(); assert 'empty' in page.clip_text.text()
clip['text'] = '<b>sk-abcdefghijklmnop</b>'
page.read_clipboard(); wait_clip()
assert page.clip_text.text() == clip['text'] and page.clip_text.textFormat() == Qt.TextFormat.PlainText
assert 'not a security check' in page.clip_kind.text()
# Data is cleared on navigating to help or away; stale read cannot reappear.
started, release = threading.Event(), threading.Event()
def blocked():
    started.set(); release.wait(3); return 'private stale clipboard'
pages_people.clipboard_text = blocked
page.read_clipboard(); assert started.wait(1)
page.help_button.click(); assert page.tabs.currentIndex() == 1 and page.clip_text.text() == 'Not read.'
release.set(); wait_clip(); assert page.clip_text.text() == 'Not read.'
page.tabs.setCurrentIndex(0)
pages_people.clipboard_text = clipboard
# Search on one worker; input changes cancel stale data and queue latest.
started, release = threading.Event(), threading.Event(); calls = []
def search(query, *, cancel):
    calls.append((query, threading.get_ident()))
    if query == 'old': started.set(); release.wait(3)
    if query == 'bad': raise PermissionError('denied')
    return ['/test/' + query + '<result>.txt']
pages_people.find_files = search
page.query.setText('ab'); page.start_search(); assert '3 characters' in page.search_status.text()
page.query.setText('old'); page.start_search(); assert started.wait(1)
fired = []; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents(); assert fired
page.query.setText('new'); page.start_search(); release.set()
def wait_search():
    end = time.monotonic() + 4
    while page.search_view.search_status == 'searching' and time.monotonic() < end:
        app.processEvents(); QTest.qWait(10)
    assert page.search_view.search_status != 'searching'
wait_search()
assert [x[0] for x in calls] == ['old','new'] and all(x[1] != shell._ui_thread_id for x in calls)
assert page.result_labels[0].text() == '/test/new<result>.txt'
assert page.result_labels[0].textFormat() == Qt.TextFormat.PlainText
page.query.setText('bad'); page.start_search(); wait_search()
assert 'failed' in page.search_status.text() and not page.search_view.hits
page.query.setText('new'); page.start_search(); wait_search()
desktop.buttons['memory'].click(); assert not page.search_view.hits
# Helper cards do not enable screen reading or browser form automation.
desktop.buttons['tools'].click(); page.help_button.click()
buttons = page.tabs.widget(1).findChildren(type(page.help_button))
assert len([x for x in buttons if x.text() == 'Unavailable' and not x.isEnabled()]) == 2
page.tabs.setCurrentIndex(0)
# Quick action never overwrites an existing draft or sends a command.
home.field.setText('existing draft'); calls_sent=[]; shell.on_text_command = lambda text: calls_sent.append(text)
from PyQt6.QtWidgets import QPushButton
button = next(x for x in page.findChildren(QPushButton) if x.text() == 'Summarize text')
button.click(); app.processEvents()
assert home.window.isVisible() and home.field.text() == 'existing draft' and not calls_sent
home.field.clear(); home.workspace_button.click(); desktop.buttons['tools'].click()
button.click(); app.processEvents()
assert home.field.text().startswith('Help me summarize') and not calls_sent
desktop.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
