"""Validation and cancellation for assistant requests to a specific SSH session."""
import re

from core.browser_read import BrowserReadRequest
from core.ssh_session import validate_command

MAX_SHARED_OUTPUT = 8000


def validate(parameters):
    if not isinstance(parameters, dict):
        raise ValueError('Expected an SSH assistance request.')
    action = parameters.get('action')
    if action not in ('inspect', 'execute'):
        raise ValueError('Unsupported SSH assistance action.')
    target = parameters.get('target', '')
    if not isinstance(target, str) or not re.fullmatch(r'doc-[1-9][0-9]{0,8}', target):
        raise ValueError('Use the exact SSH document ID from workspace_control list.')
    token = parameters.get('session', '')
    command = parameters.get('command', '')
    if action == 'execute':
        if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('Inspect the selected SSH session first.')
        command = validate_command(command)
    else:
        token, command = '', ''
    return {'action': action, 'target': target, 'session': token, 'command': command}


class SSHAssistRequest(BrowserReadRequest):
    def __init__(self, parameters):
        super().__init__()
        self.command = validate(parameters)

    def start_if_active(self, start):
        """Atomically hand off an approved command against worker timeout."""
        with self._lock:
            if self._cancelled or self._done.is_set():
                return False
            try:
                start()
                self._result = {'ok': True, 'message': 'Command started after local approval; completion is not yet confirmed.'}
            except Exception:
                self._result = {'ok': False, 'message': 'Could not start the approved command.'}
            self._done.set()
            return self._result['ok']

    def wait(self, timeout):
        result = super().wait(timeout)
        if result.get('message') == 'Browser read timed out and was cancelled.':
            return {'ok': False, 'message': 'SSH assistance timed out and was cancelled.'}
        return result
