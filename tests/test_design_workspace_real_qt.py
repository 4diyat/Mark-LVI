"""The desktop design must be reachable and use the real memory store."""
import os
import subprocess
import sys

import pytest


def test_workspace_opens_from_panel_and_reads_real_memory():
    code = r'''
import sys, tempfile
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
from memory import memory_manager
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
from ui.tray_panel_wiring import actions_for
app = QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    memory_manager.MEMORY_PATH = Path(tmp) / 'memory.json'
    memory_manager.update_memory({'preferences': {'tea': 'green tea'}, 'notes': {'name': '<b>Ada</b>'}})
    shell = type('Shell', (), {})()
    shell._app = app
    shell.write_log = lambda *_: None
    panel = TrayPanel(actions_for(shell), app=app); shell._panel = panel
    assert panel.open() and panel.set_page('more')
    QTest.mouseClick(panel._buttons['more_workspace'], Qt.MouseButton.LeftButton)
    app.processEvents()
    desktop = shell._desktop_workspace
    assert desktop.current_page() == "memory"
    workspace = desktop.memory
    import time
    end = time.monotonic() + 3
    while workspace._loading and time.monotonic() < end:
        app.processEvents(); QTest.qWait(5)
    assert not workspace._loading
    assert desktop.window.isVisible()
    assert desktop.window.width() >= 840
    assert workspace.memory_count.text() == '2 memories'
    assert len(workspace.memory_cards) == 2
    card = next(c for c in workspace.memory_cards if c.row['key'] == 'name')
    assert card.value.text() == '<b>Ada</b>'
    assert card.value.textFormat() == Qt.TextFormat.PlainText
    QTest.qWait(30)  # allow the layout to place freshly loaded cards
    QTest.mouseClick(card.expand, Qt.MouseButton.LeftButton)
    assert card.details.isVisible()
    assert 'Not available' in card.details.text()
    assert not panel.notes, panel.notes
    desktop.close(); panel.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_memory_delete_guard_preserves_changed_entry(tmp_path, monkeypatch):
    from memory import memory_manager as memory
    monkeypatch.setattr(memory, 'MEMORY_PATH', tmp_path / 'memory.json')
    memory.update_memory({'notes': {'fact': 'old'}})
    row = memory.all_entries_for_ui(strict=True)[0]
    memory.update_memory({'notes': {'fact': 'new'}})
    assert not memory.forget_if_unchanged(row)
    assert memory.load_memory(strict=True)['notes']['fact']['value'] == 'new'


def test_workspace_read_failure_and_confirmed_delete():
    code = r'''
import sys, tempfile, time
from pathlib import Path
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QTimer
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n
from memory import memory_manager as memory
from ui.design_workspace import DesignWorkspace
app = QApplication([])
i18n.set_locale('en')
with tempfile.TemporaryDirectory() as tmp:
    memory.MEMORY_PATH = Path(tmp) / 'memory.json'
    shell = type('Shell', (), {})()
    workspace = DesignWorkspace(shell)
    def wait():
        end = time.monotonic() + 3
        while (workspace._loading or workspace._busy) and time.monotonic() < end:
            app.processEvents(); QTest.qWait(5)
        assert not workspace._loading and not workspace._busy
    memory.MEMORY_PATH.write_text('{invalid', encoding='utf8')
    workspace.show(); wait()
    assert workspace.memory_count.text() == 'Not available'
    assert workspace.status.text() == 'Memory could not be read.'
    assert memory.MEMORY_PATH.read_text() == '{invalid'
    memory.MEMORY_PATH.unlink()
    memory.update_memory({'notes': {'fact': 'old'}})
    workspace.refresh(); wait()
    row = workspace.memory_cards[0].row
    def answer(button):
        def first():
            if button == QMessageBox.StandardButton.Yes:
                QTimer.singleShot(0, lambda: QApplication.activeModalWidget().done(button.value))
            QApplication.activeModalWidget().done(button.value)
        QTimer.singleShot(0, first)
    answer(QMessageBox.StandardButton.No)
    workspace.confirm_forget(row)
    assert memory.all_entries_for_ui(strict=True)
    memory.update_memory({'notes': {'fact': 'changed'}})
    answer(QMessageBox.StandardButton.Yes)
    workspace.confirm_forget(row); wait()
    assert workspace.status.text() == 'The memory changed or was removed; nothing was deleted.'
    assert memory.all_entries_for_ui(strict=True)[0]['value'] == 'changed'
    workspace.refresh(); wait()
    answer(QMessageBox.StandardButton.Yes)
    workspace.confirm_forget(workspace.memory_cards[0].row); wait()
    assert memory.all_entries_for_ui(strict=True) == []
    assert workspace.status.text() == 'No memories are stored.'
    workspace.window.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_setup_request_from_worker_is_delivered_to_qt_thread():
    code = r'''
import sys, threading, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from ui.shell import AmbientShell
from ui import setup_screen
app = QApplication([])
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
seen = []
setup_screen.build = lambda _shell: seen.append(threading.get_ident())
result = []
t = threading.Thread(target=lambda: result.append(setup_screen.open_setup(shell)))
t.start(); t.join()
end = time.monotonic() + 2
while not seen and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert result == [True]
assert seen == [shell._ui_thread_id]
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
