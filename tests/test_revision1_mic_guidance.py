"""Only explicit backend denial can trigger the microphone guidance."""
import os
import subprocess
import sys

import pytest

from ui.mic_guidance import explicitly_denied


@pytest.mark.parametrize('problem', ['Permission denied', 'OS error: access denied',
                                      'PermissionError: no access', 'device not authorized'])
def test_explicit_denial(problem):
    assert explicitly_denied(problem)


@pytest.mark.parametrize('problem', ['', None, 'No microphone available', 'device busy',
                                      'invalid sample rate'])
def test_unknown_is_not_called_an_os_denial(problem):
    assert not explicitly_denied(problem)


def test_backend_denial_offers_guidance_once_across_retries(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from tests.test_voice_command_regressions import methods
    from ui import mic_guidance
    seen = []
    monkeypatch.setattr(mic_guidance, 'report_denial', lambda ui, problem: seen.append(problem))
    device = SimpleNamespace(resolve=lambda *args: None,
                             open_input_stream=lambda *args, **kwargs: (None, 'Permission denied'))
    states = []
    attempts = []
    async def wait():
        attempts.append(1)
        if len(attempts) == 2: raise asyncio.CancelledError
    obj = SimpleNamespace(ui=SimpleNamespace(set_state=states.append, write_log=lambda _: None),
                          _mic_recovered=False, _deaf=False, _wait_for_microphone=wait,
                          _apply_listening_state=lambda: None)
    ns = methods('_listen_audio', extra={'audio_devices': device, 'get_input_device': lambda: ''})
    async def run():
        with pytest.raises(asyncio.CancelledError):
            await ns['_listen_audio'](obj)
    asyncio.run(run())
    assert states == ['NO MIC'] and seen == ['Permission denied']


def test_guidance_opens_on_real_qt_thread(tmp_path):
    code = r'''
import sys
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)
from ui.shell import AmbientShell
from ui.main_surface import open_main
from ui.mic_guidance import report_denial
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
assert open_main(shell)
assert not report_denial(shell, 'device busy')
assert getattr(shell, '_desktop_workspace', None) is None
assert report_denial(shell, 'Permission denied')
app.processEvents()
workspace = shell._desktop_workspace
assert workspace.current_page() == 'welcome' and workspace.welcome.index == 1
assert 'microphone' in workspace.welcome.title.text().lower() or 'mikrofon' in workspace.welcome.title.text().lower()
workspace.close(); shell._main_surface.close()
'''
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', JARVIS_STATE_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=20)
    if result.returncode == 77:
        pytest.skip('Qt system libraries unavailable')
    assert result.returncode == 0, result.stdout + result.stderr
