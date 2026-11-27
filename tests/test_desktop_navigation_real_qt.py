"""Desktop navigation connects real surfaces without inventing future pages."""
import os
import subprocess
import sys

import pytest


def test_desktop_navigation_preserves_home_and_future_pages():
    code = r'''
import sys, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('id')
from ui.shell import AmbientShell
from ui.main_surface import open_main
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
home = shell._main_surface
home.field.setText('Draf yang belum dikirim')
home.workspace_button.click(); app.processEvents()
desktop = shell._desktop_workspace
assert desktop.window.isVisible() and not home.window.isVisible()
assert desktop.current_page() == 'dashboard'
assert set(desktop.buttons) == {'dashboard','chat','modules','history','memory','routines','tools','security','settings'}
assert desktop.buttons['history'].isEnabled() and desktop.buttons['memory'].isEnabled()
assert desktop.buttons['security'].isEnabled()
assert desktop.buttons['routines'].isEnabled()
assert desktop.buttons['tools'].isEnabled()
assert desktop.buttons['settings'].isEnabled()
assert 'tidak diketahui' in desktop.status.text().lower()
shell.get_session_connected = lambda: False
desktop._update_session()
assert 'tidak tersambung' in desktop.status.text().lower()
shell.get_session_connected = lambda: True
desktop._update_session()
assert 'sesi aktif' in desktop.status.text().lower()
shell.get_session_connected = lambda: None
desktop._update_session()
assert 'tidak diketahui' in desktop.status.text().lower()
assert desktop.sampler.timer.isActive()
desktop.buttons['modules'].click(); app.processEvents()
assert desktop.current_page() == 'modules' and desktop.buttons['modules'].isChecked()
assert desktop.modules.objectName() == 'desktopPage'
assert set(desktop.modules.cards) == {'agenda','home','code','markets','search','memory'}
assert 'Tidak tersedia' in desktop.modules.ping_value.text()
desktop.buttons['dashboard'].click(); app.processEvents()
assert desktop.current_page() == 'dashboard'
desktop.buttons['chat'].click(); app.processEvents()
assert home.window.isVisible() and not desktop.window.isVisible()
assert home.field.text() == 'Draf yang belum dikirim'
assert not desktop.sampler.timer.isActive()
home.workspace_button.click(); app.processEvents()
assert shell._desktop_workspace is desktop and desktop.window.isVisible()
desktop.buttons['modules'].click(); desktop.modules.cards['code'].click(); app.processEvents()
assert home.window.isVisible() and home.field.text() == 'Draf yang belum dikirim'
home.workspace_button.click(); app.processEvents()
desktop.window.resize(900, 600); app.processEvents(); QTest.qWait(20)
assert desktop.window.width() >= 900 and desktop.window.height() >= 600
# Native window close returns to the same home; shutdown closes without reopening.
desktop.window.close(); app.processEvents()
assert home.window.isVisible() and not desktop.window.isVisible()
home.workspace_button.click(); app.processEvents()
desktop.close(); app.processEvents()
assert not desktop.window.isVisible() and not home.window.isVisible()
home.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
