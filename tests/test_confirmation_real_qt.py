"""Real Qt confirmation lifecycle: worker dispatch, tokens, safety and expiry."""
import os
import subprocess
import sys

import pytest


def test_confirmation_worker_delivery_stale_cancel_and_expiry(tmp_path):
    code = r'''
import sys, threading, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from core import confirm, action_gate, i18n
from ui.shell import AmbientShell
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
i18n.set_locale('en')
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
confirm.bind(shell.show_confirm, shell.hide_confirm, shell.write_log)
ran = []
def wait(predicate):
    end = time.monotonic() + 3
    while not predicate() and time.monotonic() < end:
        app.processEvents(); QTest.qWait(10)
    assert predicate()
def request():
    return action_gate.check('send_message', lambda: ran.append(threading.get_ident()) or 'test completed',
                             {'recipient': 'Ada', 'message': 'safe test'})
t = threading.Thread(target=request); t.start(); t.join()
wait(lambda: shell._confirm_banner is not None and shell._confirm_banner.isVisible())
banner = shell._confirm_banner
assert 'Ada' in banner._detail_label.text() and 'safe test' in banner._detail_label.text()
assert ran == [] and banner._cancel_button.hasFocus()
# Enter with cancel focused is a refusal, not approval.
QTest.keyClick(banner._cancel_button, Qt.Key.Key_Return)
app.processEvents(); assert not ran and not banner.isVisible()
# A request already cancelled before its queued show never appears.
t = threading.Thread(target=request); t.start(); t.join()
token = confirm._pending.token
confirm.resolve(token, False); app.processEvents()
assert not banner.isVisible() and shell._confirm_token == ''
# New request cannot be hidden by a queued hide for the old token.
t = threading.Thread(target=request); t.start(); t.join()
wait(lambda: banner.isVisible())
current = shell._confirm_token
threading.Thread(target=lambda: shell.hide_confirm(token)).start()
QTest.qWait(30); app.processEvents()
assert banner.isVisible() and shell._confirm_token == current
# Only explicit human click runs it, and it runs off the Qt thread.
QTest.mouseClick(banner._confirm_button, Qt.MouseButton.LeftButton)
wait(lambda: bool(ran)); assert ran == [ran[0]] and ran[0] != shell._ui_thread_id
assert not banner.isVisible()
# Focus is reset to cancel even after an earlier approval.
t = threading.Thread(target=request); t.start(); t.join()
wait(lambda: banner.isVisible())
wait(lambda: banner.focusWidget() is banner._cancel_button)
confirm._pending.at -= confirm.TIMEOUT_SECONDS + 1
wait(lambda: not banner.isVisible())
assert len(ran) == 1 and not confirm.pending_title()
confirm.bind(None, None)
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
