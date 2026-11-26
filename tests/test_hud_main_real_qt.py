"""HUD home uses real state, real audio samples, and honest metrics/actions."""
import os
import subprocess
import sys

import pytest


def test_hud_navigation_and_truthful_controls():
    code = r'''
import sys, threading, time
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
hud = shell._main_surface
assert hud.current_page() == 'orb'
assert set(hud.nav_buttons) == {'orb', 'history', 'memory'}
assert hud.nav_buttons['history'].isEnabled() and hud.nav_buttons['memory'].isEnabled()
assert 'Space Grotesk' in hud.window.font().family()
assert hud.orb.isVisible() and hud.empty_panel.isVisible()
assert hud.segment.objectName() == 'segmented'
assert hud.composer.height() >= 72 and hud.send_button.height() >= 56
assert hud.sparkle_button.toolTip() and not hud.sparkle_button.icon().isNull()
assert set(hud.cards) == {'summarize', 'meeting', 'analyze', 'command'}
assert hud.orb.level == 0
assert 'online' not in hud.connection_label.text().lower()
shell.get_session_connected = lambda: False
hud.refresh_mic()
assert 'tidak tersambung' in hud.connection_label.text().lower()
assert not hud.field.isEnabled() and not hud.send_button.isEnabled()
assert all(not card.isEnabled() for card in hud.cards.values())
hud.window.resize(1000, 650); app.processEvents(); QTest.qWait(30)
assert hud.home_scroll.verticalScrollBar().value() == hud.home_scroll.verticalScrollBar().maximum()
calls = []
shell.get_retry_state = lambda: (time.monotonic() + 5, True)
shell.on_retry_connection = lambda: calls.append(True) or True
hud.refresh_mic()
assert hud.retry_button.isEnabled() and 'detik' in hud.countdown_label.text()
hud.retry_button.click()
assert calls == [True]
del shell.get_retry_state, shell.on_retry_connection
shell.get_session_connected = lambda: True
hud.refresh_mic()
assert 'sesi aktif' in hud.connection_label.text().lower() and hud.avatar.connected is True
assert hud.field.isEnabled() and all(card.isEnabled() for card in hud.cards.values())
del shell.get_session_connected
assert not hud.mic_button.isEnabled()
# Real audio goes via the shared Qt dispatcher; no fabricated waveform.
shell.set_state('LISTENING')
shell.on_text_command = lambda text: True
thread = threading.Thread(target=lambda: shell.set_audio_level(0.65))
thread.start(); thread.join()
end = time.monotonic()+2
while hud.orb.level < 0.6 and time.monotonic()<end:
    app.processEvents(); QTest.qWait(5)
assert hud.orb.level >= 0.6 and max(hud.orb.samples) >= 0.6
assert 'mendengarkan' in hud.status_label.text().lower()
assert hud.mic_button.isEnabled()
hud.mic_button.click(); assert shell.muted
assert 'dibisukan' in hud.status_label.text().lower()
hud.mic_button.click(); assert not shell.muted
hud.reduce_motion.setChecked(True)
assert hud.orb.reduced_motion and not hud.orb.timer.isActive()
hud.reduce_motion.setChecked(False)
assert hud.orb.timer.isActive()
hud.field.setText('tetap di sini'); hud.prepare('summarize')
assert hud.field.text() == 'tetap di sini'
hud.window.resize(1000, 650); app.processEvents()
hud.show_system_card(); app.processEvents(); QTest.qWait(30)
assert not hud.system_card.isHidden()
assert hud.system_card.height() >= 170
assert not hud.cards['summarize'].geometry().intersects(hud.chat_stack.geometry())
assert hud.home_scroll.verticalScrollBar().maximum() > 0
assert not hud.system_card.clean.isEnabled()
hud.system_card.later.click(); assert hud.system_card.isHidden()
hud.modules_button.click()
assert hud.current_page() == 'modules'
assert set(hud.modules.cards) == {'agenda','home','code','markets','search','memory'}
assert not hud.modules.cards['home'].isEnabled()
assert hud.modules.cards['memory'].isEnabled()
assert 'Tidak tersedia' in hud.modules.ping_value.text()
hud.window.resize(1000, 650); app.processEvents()
hud.modules.cards['code'].click()
assert hud.current_page() == 'orb' and hud.field.text() == 'tetap di sini'
shell.set_state('NO MIC'); app.processEvents()
assert not hud.mic_button.isEnabled()
hud.add_message('assistant', 'Respons nyata untuk uji rendering')
shell.get_session_connected = lambda: False
shell.get_retry_state = lambda: (time.monotonic() + 5, True)
shell.on_retry_connection = lambda: calls.append(True) or True
hud.refresh_mic(); app.processEvents()
assert hud.retry_inline_panel.isVisible() and hud.retry_inline.isEnabled()
hud.retry_inline.click()
assert len(calls) == 2
assert hud.avatar.connected is False
hud.window.close()
assert not hud.sampler.timer.isActive()
assert open_main(shell) and hud.sampler.timer.isActive()
hud.window.close()
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6 or its system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr


def test_metrics_are_read_off_thread_and_failure_is_not_zero():
    code = r'''
import sys, threading, time
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    import psutil
except ImportError:
    sys.exit(77)
from ui.qt_thread import init_dispatcher
from ui.hud_metrics import MetricsSampler
app = QApplication([]); init_dispatcher()
owner = threading.get_ident(); reads = []; delivered = []
def cpu(interval):
    reads.append((threading.get_ident(), interval))
    raise OSError('not available')
psutil.cpu_percent = cpu
sampler = MetricsSampler(owner, lambda cpu, ram: delivered.append((threading.get_ident(), cpu, ram)))
sampler.refresh()
end = time.monotonic() + 3
while not delivered and time.monotonic() < end:
    app.processEvents(); QTest.qWait(5)
assert reads and reads[0][0] != owner
assert delivered == [(owner, None, None)]
assert not sampler.running
'''
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'offscreen'
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip('PyQt6, psutil or system libraries are unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
