"""One real Qt session crosses surfaces without invented sends or lost chat."""
import os
import subprocess
import sys

import pytest


def test_shared_session_navigation_delivery_and_confirmation(tmp_path):
    code = r'''
import os, sys, threading, time
from concurrent.futures import Future
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from core import i18n, confirm, action_gate, audit_log
from memory import config_manager
config_manager.CONFIG_DIR = Path(os.environ['JARVIS_STATE_DIR'])
config_manager.CONFIG_FILE = config_manager.CONFIG_DIR / 'config-test.json'
config_manager._LAST_GOOD = {}
i18n.set_locale('en'); audit_log.reset_shared()
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui import tray_panel_wiring, ambient_shell
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
def wait(predicate):
    end = time.monotonic() + 4
    while not predicate() and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert predicate()
# A hidden startup receives a voice exchange before either window exists.
shell._show_exchange('You: simulated spoken question')
shell._show_exchange('JARVIS: simulated reply')
assert open_main(shell); home = shell._main_surface
assert home.messages == [('user', 'simulated spoken question'), ('assistant', 'simulated reply')]
# A pending send cannot add a chat message or be submitted twice.
future = Future(); shell.on_text_command = lambda text: future
home.field.setText('home message'); assert home.submit(); assert not home.submit()
assert home.field.text() == 'home message' and len(home.messages) == 2
future.set_result(None); wait(lambda: not home.sending)
assert home.messages[-1] == ('user', 'home message') and not home.field.text()
# A panel created later inherits the same bounded in-memory session once.
assert tray_panel_wiring.open_panel(shell); panel = shell._panel
assert panel._messages == home.messages
panel.close(); assert tray_panel_wiring.open_panel(shell); assert panel._messages == home.messages
# A tray send updates both surfaces only after the Future succeeds.
future = Future(); shell.on_text_command = lambda text: future
panel._field.setText('tray message'); assert panel.submit_command()
assert ('user', 'tray message') not in home.messages
future.set_result(None); wait(lambda: not panel._command_sending)
assert panel._messages == home.messages and home.messages[-1] == ('user', 'tray message')
# A command bar failure keeps its draft out of both conversations.
assert ambient_shell.open_command_bar(shell); bar = shell._command_bar
future = Future(); shell.on_text_command = lambda text: future
bar._field.setText('uncertain message'); assert bar.submit()
future.set_exception(RuntimeError('test connection lost')); wait(lambda: not bar.sending)
assert bar._field.text() == 'uncertain message' and panel._messages == home.messages
assert ('user', 'uncertain message') not in home.messages
bar.close(); panel.close()
# A draft survives desktop navigation, and synthetic audit stays separate.
home.field.setText('draft across navigation'); home.workspace_button.click()
d = shell._desktop_workspace; d.buttons['history'].click(); h = d.history
wait(lambda: not h.loading and not h.busy)
assert all(row.get('tool') != 'home message' for row in (h.audit_rows or []))
d.buttons['settings'].click(); s = d.settings; s.appearance_button.click()
wait(lambda: not s.appearance.busy); s.appearance.buttons['light'].click()
wait(lambda: not s.appearance.busy); assert panel.theme == 'light'
d.return_home(); assert home.field.text() == 'draft across navigation'
# Gate remains in force across navigation and defaults to cancellation.
confirm.bind(shell.show_confirm, shell.hide_confirm, shell.write_log); ran = []
t = threading.Thread(target=lambda: action_gate.check('send_message', lambda: ran.append(True),
                              {'recipient': 'test only', 'message': 'no external action'}))
t.start(); t.join(); wait(lambda: shell._confirm_banner is not None and shell._confirm_banner.isVisible())
banner = shell._confirm_banner
assert 'test only' in banner._detail_label.text() and not ran
QTest.keyClick(banner._cancel_button, Qt.Key.Key_Return); app.processEvents()
assert not ran and not banner.isVisible()
confirm.bind(None, None); d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
