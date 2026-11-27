"""Undo history must match the visible entry, even if the stack changes."""
import os
import subprocess
import sys

import pytest


def test_guarded_undo_uses_entry_identity_not_label():
    from core import undo
    undo.clear()
    calls = []
    try:
        undo.push_undo('same', lambda: calls.append('first'))
        shown = undo.history_with_tokens()[0][0]
        undo.push_undo('same', lambda: calls.append('second'))
        ok, _ = undo.undo_if_current(shown)
        assert not ok and calls == []
        ok, _ = undo.undo_if_current(undo.history_with_tokens()[0][0])
        assert ok and calls == ['second']
        assert undo.history() == ['same']
    finally:
        undo.clear()


def test_history_buttons_match_displayed_entry_and_reject_stale_click():
    code = r'''
import sys, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n, undo
i18n.set_locale('en')
from ui import history_panel
from ui.tray_panel import TrayPanel
app = QApplication([])
undo.clear()
calls = []
undo.push_undo('older', lambda: calls.append('older'))
undo.push_undo('newer', lambda: calls.append('newer'))
panel = TrayPanel({'undo_guarded': undo.undo_if_current})
assert panel.open() and panel.set_page('history')
app.processEvents()
assert panel._labels['history:0'].text() == 'newer'
assert panel._buttons['undo:0'].isVisible()
assert not panel._buttons['undo:1'].isVisible()
# A new entry has arrived without a repaint. The visible button must not undo it.
undo.push_undo('newest', lambda: calls.append('newest'))
QTest.mouseClick(panel._buttons['undo:0'], Qt.MouseButton.LeftButton)
end = time.monotonic() + 3
while getattr(panel, '_history_busy', False) and time.monotonic() < end:
    app.processEvents()
    QTest.qWait(5)
assert not panel._history_busy and calls == []
assert undo.history() == ['newest', 'newer', 'older']
assert panel._labels['history:0'].text() == 'newest'
assert 'changed' in panel._labels['history_status'].text().lower()
assert not panel.notes, panel.notes
undo.clear()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_clear_requires_exact_snapshot():
    from core import undo
    undo.clear()
    try:
        undo.push_undo('first', lambda: '')
        snapshot = tuple(token for token, _ in undo.history_with_tokens())
        undo.push_undo('second', lambda: '')
        assert not undo.clear_if_unchanged(snapshot)
        assert undo.history() == ['second', 'first']
        snapshot = tuple(token for token, _ in undo.history_with_tokens())
        assert undo.clear_if_unchanged(snapshot)
        assert undo.history() == []
    finally:
        undo.clear()


def test_pagination_worker_and_clear_confirmation_on_real_qt():
    code = r'''
import sys, threading, time
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
except ImportError:
    sys.exit(77)
from core import i18n, undo
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
app = QApplication([])
undo.clear()
release, started, calls = threading.Event(), threading.Event(), []
def slow():
    started.set()
    release.wait(3)
    calls.append('reversed')
    return 'completed by callback'
for i in range(6): undo.push_undo(f'item {i}', lambda: None)
undo.push_undo('<b>newest</b>', slow)
panel = TrayPanel({'undo_guarded': undo.undo_if_current,
                   'history_clear_guarded': undo.clear_if_unchanged})
assert panel.open() and panel.set_page('history')
app.processEvents()
assert panel._labels['history:0'].text() == '<b>newest</b>'
assert panel._labels['history:0'].textFormat() == Qt.TextFormat.PlainText
QTest.mouseClick(panel._buttons['history_next'], Qt.MouseButton.LeftButton)
assert panel._labels['history:0'].text() == 'item 2'
assert panel._labels['history_page'].text() == 'Page 2 / 2 · 7 undo entries'
assert not panel._buttons['undo:0'].isVisible()
QTest.mouseClick(panel._buttons['history_prev'], Qt.MouseButton.LeftButton)
QTest.mouseClick(panel._buttons['undo:0'], Qt.MouseButton.LeftButton)
assert started.wait(1) and panel._history_busy
assert not panel._buttons['clear'].isEnabled()
ticks = []
QTimer.singleShot(0, lambda: ticks.append('tick'))
app.processEvents()
assert ticks == ['tick'] and not calls
release.set()
end = time.monotonic() + 3
while panel._history_busy and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert not panel._history_busy and calls == ['reversed']
assert 'Undo attempted' in panel._labels['history_status'].text()
assert undo.history()[0] == 'item 5'
# A stack change while the confirmation dialog is open must not be cleared.
def confirm(*args):
    undo.push_undo('arrived later', lambda: '')
    return QMessageBox.StandardButton.Yes
QMessageBox.question = confirm
QTest.mouseClick(panel._buttons['clear'], Qt.MouseButton.LeftButton)
assert undo.history()[0] == 'arrived later'
assert 'changed' in panel._labels['history_status'].text().lower()
QMessageBox.question = lambda *args: QMessageBox.StandardButton.No
QTest.mouseClick(panel._buttons['clear'], Qt.MouseButton.LeftButton)
assert undo.history()[0] == 'arrived later'
QMessageBox.question = lambda *args: QMessageBox.StandardButton.Yes
QTest.mouseClick(panel._buttons['clear'], Qt.MouseButton.LeftButton)
assert undo.history() == []
assert panel._labels['history:0'].text() == 'No actions to undo'
assert not panel._labels['history_dot:0'].isVisible()
assert not panel._buttons['clear'].isEnabled()
assert not panel.notes, panel.notes
undo.clear()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_history_failure_is_not_shown_as_an_empty_stack():
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from core import i18n, undo
i18n.set_locale('en')
from ui.tray_panel import TrayPanel
app = QApplication([])
undo.clear()
def unavailable(): raise OSError('unreadable')
undo.history_with_tokens = unavailable
panel = TrayPanel({'undo_guarded': undo.undo_if_current,
                   'history_clear_guarded': undo.clear_if_unchanged})
assert panel.open() and panel.set_page('history')
app.processEvents()
assert panel._labels['history_count'].text() == 'Undo history unavailable'
assert panel._labels['history:0'].text() == 'Undo history unavailable'
assert not panel._buttons['undo:0'].isVisible()
assert not panel._buttons['clear'].isEnabled()
assert not panel.notes, panel.notes
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
