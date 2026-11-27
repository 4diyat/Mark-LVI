"""Optional guide and tray-only appearance, exercised through real Qt."""
import os
import subprocess
import sys

import pytest


def test_stage10_guide_theme_and_legacy_mic_are_honest(tmp_path):
    code = r'''
import sys, os, time, threading
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import QTimer
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from memory import config_manager
config_manager.CONFIG_DIR = Path(os.environ['JARVIS_STATE_DIR'])
config_manager.CONFIG_FILE = config_manager.CONFIG_DIR / 'config-test.json'
config_manager._LAST_GOOD = {}
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui import tray_panel_wiring, pages_actions
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); home = shell._main_surface; home.workspace_button.click()
d = shell._desktop_workspace
# Four informational screens. The microphone page cannot claim an OS grant.
d.navigate('welcome'); w = d.welcome
assert 'Welcome' in w.title.text() and not w.back.isEnabled()
w.next.click(); assert 'Microphone' in w.title.text()
assert 'cannot determine or change' in w.intro.text()
assert any('does not turn off' in x.text() for x in w.points)
assert not config_manager.CONFIG_FILE.exists()
w.next.click(); assert 'not microphone permissions' in w.intro.text()
w.next.click(); assert 'not confirmation' in w.intro.text()
w.back.click(); assert w.index == 2
w.next.click(); w.next.click(); assert d.current_page() == 'dashboard'
# Theme changes are scoped, verified, non-blocking, and persisted on the panel.
d.navigate('settings'); s = d.settings; s.appearance_button.click(); p = s.appearance
def wait():
    end = time.monotonic() + 4
    while p.busy and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not p.busy
wait(); assert p.buttons['auto'].isChecked()
assert tray_panel_wiring.open_panel(shell); panel = shell._panel
p.buttons['light'].click(); wait()
assert panel.theme == 'light' and config_manager.get_ui_theme() == 'light'
assert 'Tray theme saved' in p.status.text() and p.buttons['light'].isChecked()
assert '#0a1522' not in panel._window.styleSheet().lower()
assert d.window.styleSheet()  # workspace remains independently styled
# Failure cannot be reported as saved even if the requested value was already stored.
original = config_manager.set_config_values
started, release = threading.Event(), threading.Event()
def fail(**kw):
    started.set(); release.wait(3); return False
config_manager.set_config_values = fail
p.save('light'); assert started.wait(1)
fired = []; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents(); assert fired
release.set(); wait(); assert 'not saved' in p.status.text() and panel.theme == 'light'
# Tray header rolls back optimistic changes when persistence explicitly fails.
assert panel.press_theme() == 'light' and panel.theme == 'light'
config_manager.set_config_values = original
# The old onboarding path no longer writes an unenforced mic-consent flag.
assert panel.set_page('consent'); panel._onboarding = None
assert pages_actions.onboard_next(shell); app.processEvents()
assert panel._onboarding.current == 'mic'
assert not panel._buttons['cn_toggle'].isVisible()
assert 'unknown' in panel._labels['cn_when'].text().lower()
assert pages_actions.onboard_next(shell)
assert panel._onboarding.current == 'presence'
assert 'microphone_consent' not in config_manager.load_api_keys()
panel.close(); d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
