"""Live command bar and tray share honest asynchronous delivery semantics."""
import os
import subprocess
import sys

import pytest


def test_ambient_surfaces_preserve_drafts_and_wait_for_send(tmp_path):
    code = r'''
import sys, time, threading
from concurrent.futures import Future
from pathlib import Path
try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n, audit_log
i18n.set_locale('en'); audit_log.reset_shared()
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui import ambient_shell, tray_panel_wiring
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); home = shell._main_surface
assert ambient_shell.open_command_bar(shell)
bar = shell._command_bar
assert bar._asynchronous
def spin(predicate):
    end = time.monotonic() + 4
    while not predicate() and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert predicate()
spin(lambda: not bar._audit_running)
# No session: no false success, no lost draft.
bar._field.setText('keep me'); shell.on_text_command = lambda text: False
assert bar.submit(); spin(lambda: not bar.sending)
assert bar._field.text() == 'keep me' and 'Not sent' in bar.hint
bar.close(); assert ambient_shell.open_command_bar(shell); assert bar._field.text() == 'keep me'
assert not tray_panel_wiring.prefill(shell, 'overwrite') and bar._field.text() == 'keep me'
# A pending future does not block the UI or permit duplicate sends.
future = Future(); calls = []
def deliver(text):
    calls.append((text, threading.get_ident())); return future
shell.on_text_command = deliver
assert bar.submit(); spin(lambda: len(calls) == 1)
assert not bar.submit() and not bar._field.isEnabled()
fired = []; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents(); assert fired
future.set_result(None); spin(lambda: not bar.sending)
assert not bar._field.text() and bar.history[0] == 'keep me'
assert 'outcome is not yet known' in bar.hint and calls[0][1] != shell._ui_thread_id
# Failure after submission is uncertain, not a confirmed non-send.
future = Future(); shell.on_text_command = lambda text: future
bar._field.setText('uncertain'); assert bar.submit()
future.set_exception(RuntimeError('connection lost')); spin(lambda: not bar.sending)
assert bar._field.text() == 'uncertain' and 'uncertain' in bar.hint and 'do not retry' in bar.hint.lower()
bar._field.setText('x' * 2001); assert not bar.submit() and len(bar._field.text()) == 2001
# Strict corrupt audit is unavailable, not an empty log.
Path(sys.argv[1], 'audit.jsonl').write_text('{bad\n', encoding='utf8')
bar.close(); assert ambient_shell.open_command_bar(shell)
spin(lambda: not bar._audit_running)
assert bar._audit_state == 'error' and not bar.rows
# Tray uses the same real callback and only records after completion.
assert tray_panel_wiring.open_panel(shell); panel = shell._panel
future = Future(); shell.on_text_command = lambda text: future
panel._field.setText('tray test'); assert panel.submit_command()
assert not panel.submit_command() and panel._field.text() == 'tray test'
future.set_result(None); spin(lambda: not panel._command_sending)
assert ('user', 'tray test') in panel._messages and not panel._field.text()
assert 'outcome unknown' in panel._labels['command_status'].text()
shell.on_text_command = lambda text: False
panel._field.setText('retain'); assert panel.submit_command(); spin(lambda: not panel._command_sending)
assert panel._field.text() == 'retain' and 'Not sent' in panel._labels['command_status'].text()
assert ('user','retain') not in panel._messages
panel.close(); bar.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_voice_pause_has_a_focused_window_fallback(tmp_path):
    code = r'''
import sys
from types import SimpleNamespace
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from ui.voice_overlay import VoiceOverlay
from ui import voice_wiring
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
overlay = VoiceOverlay(); assert overlay.start(active=False)
shell = SimpleNamespace(_voice_overlay=overlay)
voice_wiring._install_pause_fallback(shell)
overlay.show(); overlay._window.activateWindow(); overlay._window.setFocus()
QTest.qWait(100)
QTest.keyClick(overlay._window, Qt.Key.Key_G,
               Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
QTest.qWait(100)
assert overlay.gestures_paused
voice_wiring.stop_pause_hotkey(shell); overlay.stop()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_platform_shortcuts_have_codes_and_do_not_collide():
    from core.hotkey import DEFAULT_CHORD, _MAC_KEYCODE, _QT_NAME, _VK, _X11_KEYSYM
    from ui.ambient_shell import BAR_CHORD
    from ui.lifecycle import SUMMON_CHORD
    from ui.voice_wiring import PAUSE_CHORD
    chords = (DEFAULT_CHORD, BAR_CHORD, SUMMON_CHORD, PAUSE_CHORD)
    assert len(set(chords)) == len(chords)
    for table in (_MAC_KEYCODE, _QT_NAME, _VK, _X11_KEYSYM):
        assert all(key in table for chord in chords for key in chord)
