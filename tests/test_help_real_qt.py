"""Writing-help page must never imply unimplemented capabilities are active."""
import os
import subprocess
import sys

import pytest


def test_help_surface_is_honest_and_links_to_real_voice_tools():
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
from ui.tray_panel import TrayPanel
app = QApplication([])
panel = TrayPanel({})
assert panel.open() and panel.set_page('help')
app.processEvents()
assert panel._labels['title'].isVisible()
assert 'not available' in panel._labels['hp_read'].text().lower()
assert not panel._buttons['hp_read'].isEnabled()
assert 'not available' in panel._labels['hp_preview'].text().lower()
assert not panel._buttons['hp_form_apply'].isEnabled()
assert all(not panel._inputs[f'hp_form_input:{i}'].isEnabled() for i in range(3))
QTest.mouseClick(panel._buttons['hp_dictate_tools'], Qt.MouseButton.LeftButton)
assert panel.page == 'tools'
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_help_action_refuses_direct_calls_without_touching_browser(monkeypatch):
    from ui import pages_actions
    calls = []
    monkeypatch.setattr('actions.browser_form.fill_form_to_page',
                        lambda *args: calls.append(args) or [])
    monkeypatch.setattr(pages_actions, '_say', lambda *_: None)
    edit = type('Edit', (), {'text': lambda self: 'https://example.com'})()
    panel = type('Panel', (), {'_inputs': {'hp_form_url': edit}, 'refresh': lambda self: None})()
    shell = type('Shell', (), {'_panel': panel})()
    assert not pages_actions.form_fill_apply(shell)
    assert not calls


def test_legacy_adapter_does_not_write_to_an_unchecked_page(monkeypatch):
    from actions import browser_control
    from actions.browser_form import fill_form_to_page
    calls = []
    monkeypatch.setattr(browser_control._registry, 'has', lambda *a: True)
    monkeypatch.setattr(browser_control._registry, 'get', lambda *a: calls.append('get'))
    result = fill_form_to_page('https://example.com', {'#field0': 'Alice'})
    assert not calls
    assert len(result) == 1 and not result[0].ok
