"""Settings scope, real home motion and truthful plugin registry states."""
import os
import subprocess
import sys

import pytest


def test_settings_scope_registry_and_tray_delegation(tmp_path):
    code = r'''
import threading, time, sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt, QTimer
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui import tray_panel_wiring
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell); home = shell._main_surface
home.workspace_button.click(); d = shell._desktop_workspace; d.buttons['settings'].click()
p = d.settings
assert d.current_page() == 'settings' and p.locale.text().endswith('en')
assert p.motion.isEnabled() and p.motion.isChecked() == home.reduce_motion.isChecked()
p.motion.setChecked(True); assert home.reduce_motion.isChecked() and home.orb.reduced_motion
home.reduce_motion.setChecked(False); p.refresh_access(); assert not p.motion.isChecked()
# The only write controls go through existing tray surfaces, including failure reporting.
tray_panel_wiring.open_panel = lambda shell: False
p.open_tray('access'); assert 'Could not open' in p.access_status.text()
opened = []
shell._panel = type('Panel', (), {'set_page': lambda self, page: opened.append(page) or True})()
tray_panel_wiring.open_panel = lambda shell: True
p.open_tray('access'); assert opened == ['access'] and 'opened' in p.access_status.text()
# No provider is not the same as an empty registry.
p.plugins_button.click()
def wait():
    end = time.monotonic() + 4
    while p.loading and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not p.loading
wait()
assert p.records is None and 'could not be read' in p.plugin_status.text()
rows = [
 {'name':'valid', 'valid':True, 'enabled':False, 'permissions':['network'], 'description':'<sample>'},
 {'name':'duplicate', 'valid':True, 'enabled':True, 'permissions':[]},
 {'name':'duplicate', 'valid':True, 'enabled':True, 'permissions':[]},
 {'name':'bad', 'valid':False, 'enabled':False, 'permissions':[], 'error':'invalid plugin'},
 {'name':'fifth', 'valid':True, 'enabled':True, 'permissions':[]},
]
started, release = threading.Event(), threading.Event(); calls = []
def provider():
    calls.append(threading.get_ident())
    if len(calls) == 1: started.set(); release.wait(3)
    return rows
shell.get_plugins = provider
p.refresh_plugins(); assert started.wait(1)
p.refresh_plugins(); assert p.reload_requested
fired = []; QTimer.singleShot(0, lambda: fired.append(True)); app.processEvents(); assert fired
release.set(); wait(); assert len(calls) == 2 and all(x != shell._ui_thread_id for x in calls)
assert len(p.cards) == 4 and p.next.isEnabled()
labels = p.cards[0].findChildren(type(p.locale))
assert any(x.text() == '<sample>' and x.textFormat() == Qt.TextFormat.PlainText for x in labels)
assert any('Disabled in configuration' in x.text() and 'network' in x.text() for x in labels)
assert any('Cannot be managed' in x.text() for x in p.cards[1].findChildren(type(p.locale)))
p.next.click(); assert len(p.cards) == 1 and p.prev.isEnabled()
p.open_tray('plugins'); assert opened == ['access', 'plugins']
# Helpfully refuses to imply pairing, OS permission, or connected devices.
p.gesture_button.click(); assert p.tabs.currentIndex() == 2
d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_tray_settings_entry_points(tmp_path):
    code = r'''
import os, sys
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt
except ImportError:
    sys.exit(77)
from core import i18n
from memory import config_manager
i18n.set_locale('en')
config_manager.CONFIG_DIR = Path(os.environ['JARVIS_STATE_DIR'])
config_manager.CONFIG_FILE = config_manager.CONFIG_DIR / 'config-test.json'
config_manager._LAST_GOOD = {}
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
shell.get_plugins = lambda: []
assert open_main(shell); home = shell._main_surface; home.workspace_button.click()
d = shell._desktop_workspace; d.buttons['settings'].click(); p = d.settings
p.open_tray('access'); app.processEvents()
assert shell._panel.page == 'access' and shell._panel._visible()
QTest.mouseClick(shell._panel._buttons['ac_lang:id'], Qt.MouseButton.LeftButton)
assert i18n.active_locale() == 'id'
p.refresh_access(); assert p.locale.text().endswith('id')
p.open_tray('plugins'); app.processEvents(); assert shell._panel.page == 'plugins'
assert not config_manager.CONFIG_FILE.exists()
shell._panel.close(); d.close(); home.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
