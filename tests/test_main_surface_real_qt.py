"""Main surface: real Qt, real shell wiring, and no mockup sample data."""
import os
import subprocess
import sys

import pytest


def test_main_surface_workflow():
    code = r'''
import sys, threading, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
surface = shell._main_surface
assert surface.window.isVisible() and surface.window.width() >= 1000
assert surface.messages == []
assert 'online' not in surface.status_label.text().lower()
assert surface.modules.cards['memory'].isEnabled()
surface.navigate('orb')
surface.field.setText('unfinished')
surface.prepare('summarize')
assert surface.field.text() == 'unfinished'
surface.field.clear(); surface.prepare('summarize')
assert surface.field.text()
# No session: never drop an unsent draft or pretend a user turn was sent.
surface.field.setText('keep this')
assert not surface.submit()
assert surface.field.text() == 'keep this' and not surface.messages
calls = []
def send(text):
    calls.append((text, threading.get_ident()))
    return False
shell.on_text_command = send
assert surface.submit()
end = time.monotonic() + 3
while surface.sending and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert surface.field.text() == 'keep this' and not surface.messages
assert calls[0][1] != shell._ui_thread_id
shell.on_text_command = lambda text: True
surface.send_button.click()
assert surface.sending
end = time.monotonic() + 3
while surface.sending and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert surface.field.text() == '' and surface.messages == [('user', 'keep this')]
t = threading.Thread(target=lambda: shell.write_log('JARVIS: <b>real answer</b>'))
t.start(); t.join()
end = time.monotonic() + 3
while len(surface.messages) < 2 and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert surface.messages[-1] == ('assistant', '<b>real answer</b>')
assert '<b>real answer</b>' in surface.chat.toPlainText()
shell.set_state('NO MIC'); app.processEvents()
assert 'microphone' in surface.status_label.text().lower()
surface.window.close(); assert not surface.window.isVisible()
assert open_main(shell) and shell._main_surface is surface and surface.window.isVisible()
surface.window.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_startup_respects_hidden_flag():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from types import SimpleNamespace
from ui.shell import AmbientShell
from ui.main_surface import start_main
app = QApplication([])
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
shell._launch = SimpleNamespace(hidden=True)
assert not start_main(shell)
assert getattr(shell, '_main_surface', None) is None
shell._launch.hidden = False
assert start_main(shell)
assert shell._main_surface.window.isVisible()
shell._main_surface.window.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_voice_waveform_paints_with_real_qt():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QPainter
except ImportError:
    sys.exit(77)
from ui.voice_paint import _paint_waveform
app = QApplication([])
image = QImage(1280, 720, QImage.Format.Format_ARGB32)
image.fill(0)
painter = QPainter(image)
_paint_waveform(painter, None)
painter.end()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_pending_send_tracks_future_and_keeps_unverified_draft():
    code = r'''
import sys, time
from concurrent.futures import Future
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
s = shell._main_surface
pending = Future(); shell.on_text_command = lambda text: pending
s.field.setText('keep until known'); assert s.submit()
for _ in range(20): app.processEvents(); QTest.qWait(5)
assert s.sending and s.field.text() == 'keep until known' and not s.messages
assert not s.send_button.isEnabled() and not s.submit()
pending.set_exception(ConnectionError('dropped'))
end = time.monotonic() + 2
while s.sending and time.monotonic() < end: app.processEvents(); QTest.qWait(5)
assert not s.sending and s.field.text() == 'keep until known' and not s.messages
assert 'uncertain' in s.feedback.text().lower()
s.show_feedback('NET: reconnecting')
assert 'uncertain' in s.feedback.text().lower()
pending = Future(); shell.on_text_command = lambda text: pending
assert s.submit()
for _ in range(20): app.processEvents(); QTest.qWait(5)
s.field.setText('another draft')
pending.set_result(None)
end = time.monotonic() + 2
while s.sending and time.monotonic() < end: app.processEvents(); QTest.qWait(5)
assert not s.sending and s.field.text() == 'another draft'
assert s.messages == [('user', 'keep until known')]
assert 'not necessarily complete' in s.feedback.text()
s.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
