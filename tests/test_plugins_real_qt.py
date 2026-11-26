"""Real Qt checks for plugin and phone status surfaces."""
import os
import subprocess
import sys

import pytest


def test_phone_panel_does_not_invent_paired_device_or_code():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from core.phone_pairing import PairingSession
from ui.tray_panel import TrayPanel
app = QApplication([])
panel = TrayPanel({})
panel._phone_pair = PairingSession()
code = panel._phone_pair.mint_code()
panel._phone_pair.consume_code(code.code, 'A fictitious device')
assert panel.open() and panel.set_page('plugins')
app.processEvents()
assert panel._labels['pl_phone'].text() == 'Phone pairing is not available in this panel.'
assert 'fictitious' not in panel._labels['pl_phone'].text()
assert panel._labels['pl_phone2'].text() == 'Connection status is unavailable here.'
assert panel._labels['pl_code_box'].text() == 'No pairing code is available in this panel.'
for key in ('pl_phone_make', 'pl_phone_pair', 'pl_phone_unpair'):
    assert not panel._buttons[key].isEnabled()
    assert not panel._buttons[key].isVisible()
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_registry_pagination_uses_visible_identity_and_clears_empty_rows():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui import plugin_panel
from ui.tray_panel import TrayPanel
app = QApplication([])
rows = [dict(name=f'plugin_{i}', valid=True, enabled=False, permissions=['files'], error='')
        for i in range(5)]
calls = []
panel = TrayPanel({'plugins_list': lambda: rows, 'plugin_toggle': lambda *args: calls.append(args)})
plugin_panel.confirm_enable = lambda panel, row: True
assert panel.open() and panel.set_page('plugins')
app.processEvents()
assert panel._labels['subtitle'].text() == '0 of 5 plugins on'
assert panel._buttons['pl_toggle:0'].text() == 'OFF'
QTest.mouseClick(panel._buttons['pl_next'], Qt.MouseButton.LeftButton)
assert panel._labels['pl_name:0'].text() == 'plugin_3'
assert not panel._buttons['pl_toggle:2'].isVisible()
rows.reverse()
QTest.mouseClick(panel._buttons['pl_toggle:0'], Qt.MouseButton.LeftButton)
assert calls == [('plugin_3', False, ('files',))]
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_plugin_action_checks_registry_and_permissions_before_saving(monkeypatch):
    from ui import pages_actions, pages_admin
    messages, written, reconnects = [], [], []
    rows = [dict(name='plugin', valid=True, enabled=False, permissions=['files'], error='')]
    shell = type('Shell', (), {'get_plugins': lambda self: rows,
                               'on_plugins_changed': lambda self: reconnects.append(True)})()
    monkeypatch.setattr(pages_actions, '_say', lambda _shell, text: messages.append(text))
    monkeypatch.setattr(pages_admin, 'set_plugin', lambda name, on: written.append((name, on)) or True)
    assert not pages_actions.plugin_toggle(shell, 'plugin', False, ('network',))
    assert not written and not reconnects
    assert pages_actions.plugin_toggle(shell, 'plugin', False, ('files',))
    assert written == [('plugin', True)] and reconnects == [True]
    rows[0]['valid'] = False
    assert not pages_actions.plugin_toggle(shell, 'plugin', False, ('files',))
    assert written == [('plugin', True)] and reconnects == [True]


def test_confirmation_displays_permissions_and_cancel_makes_no_change():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
app = QApplication([])
rows = [dict(name='<plugin>', valid=True, enabled=False, permissions=['network', 'files'], error='')]
calls, shown = [], []
panel = TrayPanel({'plugins_list': lambda: rows, 'plugin_toggle': lambda *args: calls.append(args)})
def reject(dialog):
    shown.append((dialog.text(), dialog.informativeText(), dialog.textFormat()))
    return QMessageBox.StandardButton.No
QMessageBox.exec = reject
assert panel.open() and panel.set_page('plugins')
app.processEvents()
QTest.mouseClick(panel._buttons['pl_toggle:0'], Qt.MouseButton.LeftButton)
assert not calls
assert len(shown) == 1
assert '<plugin>' in shown[0][0] and 'network access' in shown[0][0] and 'read or write files' in shown[0][0]
assert 'not a sandbox' in shown[0][1] and shown[0][2] == Qt.TextFormat.PlainText
assert panel._buttons['pl_toggle:0'].text() == 'OFF'
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_plugin_page_registry_failure_and_invalid_rows_are_not_enabled():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
app = QApplication([])
state = [None]
panel = TrayPanel({'plugins_list': lambda: state[0], 'plugin_toggle': lambda *args: None})
assert panel.open() and panel.set_page('plugins')
app.processEvents()
assert panel._labels['subtitle'].text() == 'Plugin registry unavailable'
assert not panel._buttons['pl_toggle:0'].isVisible()
state[0] = [dict(name='refused', valid=False, enabled=True, permissions=['files'], error='bad hash')]
panel.refresh()
assert panel._labels['subtitle'].text() == '0 of 1 plugins on'
assert not panel._buttons['pl_toggle:0'].isEnabled()
assert panel._buttons['pl_toggle:0'].text() == '—'
assert panel._labels['pl_desc:0'].toolTip() == 'bad hash'
state[0] = []
panel.refresh()
assert not panel._buttons['pl_toggle:0'].isVisible()
assert panel._labels['pl_name:0'].text() == ''
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_plugin_failed_save_and_ambiguous_name_do_not_reconnect(monkeypatch):
    from ui import pages_actions, pages_admin
    rows = [dict(name='plugin', valid=True, enabled=False, permissions=[], error='')]
    reconnects = []
    shell = type('Shell', (), {'get_plugins': lambda self: rows,
                               'on_plugins_changed': lambda self: reconnects.append(True)})()
    monkeypatch.setattr(pages_actions, '_say', lambda *_: None)
    monkeypatch.setattr(pages_admin, 'set_plugin', lambda *_: False)
    assert not pages_actions.plugin_toggle(shell, 'plugin', False, ())
    assert not reconnects
    rows.append(dict(rows[0]))
    assert not pages_actions.plugin_toggle(shell, 'plugin', False, ())
    assert not reconnects


def test_plugin_toggle_changes_real_registry_and_declarations(tmp_path, isolated_config, monkeypatch):
    from core.plugin_loader import discover_plugins
    from tests.test_loaders import _signed
    from ui import pages_actions

    folder = tmp_path / 'plugins'
    _signed(folder, 'reviewed', ['network'])
    registry = discover_plugins(folder, set(), lambda _: None)
    assert registry.list_for_ui()[0]['enabled'] is False
    assert registry.get_tool_declarations() == []
    reconnects = []
    shell = type('Shell', (), {'get_plugins': lambda self: registry.list_for_ui(),
                               'on_plugins_changed': lambda self: reconnects.append(True)})()
    monkeypatch.setattr(pages_actions, '_say', lambda *_: None)
    assert pages_actions.plugin_toggle(shell, 'reviewed', False, ('network',))
    assert registry.list_for_ui()[0]['enabled'] is True
    assert [row['name'] for row in registry.get_tool_declarations()] == ['reviewed']
    assert pages_actions.plugin_toggle(shell, 'reviewed', True, ('network',))
    assert not registry.list_for_ui()[0]['enabled']
    assert registry.get_tool_declarations() == []
    assert len(reconnects) == 2


def test_qt_click_reaches_runtime_registry_and_reconnects():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from memory import config_manager
from core.plugin_loader import discover_plugins
from tests.test_loaders import _signed
from ui import pages_actions, plugin_panel
from ui.tray_panel import TrayPanel
from ui.tray_panel_wiring import actions_for
app = QApplication([])
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    config_manager.CONFIG_DIR = root
    config_manager.CONFIG_FILE = root / 'settings.json'
    config_manager._LAST_GOOD = {}
    _signed(root / 'plugins', 'reviewed', ['network'])
    registry = discover_plugins(root / 'plugins', set(), lambda _: None)
    reconnects, prompts = [], []
    shell = type('Shell', (), {})()
    shell.get_plugins = registry.list_for_ui
    shell.on_plugins_changed = lambda: reconnects.append(True)
    pages_actions._say = lambda *_: None
    plugin_panel.confirm_enable = lambda panel, row: prompts.append(row) or True
    panel = TrayPanel(actions_for(shell)); shell._panel = panel
    assert panel.open() and panel.set_page('plugins')
    app.processEvents()
    QTest.mouseClick(panel._buttons['pl_toggle:0'], Qt.MouseButton.LeftButton)
    assert prompts[0]['permissions'] == ['network']
    assert registry.list_for_ui()[0]['enabled']
    assert panel._buttons['pl_toggle:0'].text() == 'ON'
    assert [r['name'] for r in registry.get_tool_declarations()] == ['reviewed']
    QTest.mouseClick(panel._buttons['pl_toggle:0'], Qt.MouseButton.LeftButton)
    assert not registry.list_for_ui()[0]['enabled']
    assert panel._buttons['pl_toggle:0'].text() == 'OFF'
    assert len(prompts) == 1 and len(reconnects) == 2
    assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
