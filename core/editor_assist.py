"""Validated, cancellable editor-assistance requests across the Qt boundary."""
import hashlib
import re

from core.browser_read import BrowserReadRequest

MAX_CODE_BYTES = 100_000


def revision(text, tab_token=''):
    """Bind a read revision to its tab as well as the exact text."""
    return hashlib.sha256((tab_token + '\0' + text).encode('utf-8')).hexdigest()


def validate(action, target, code='', base_revision=''):
    if action not in ('read', 'replace'):
        raise ValueError('Unsupported editor assistance action.')
    if not isinstance(target, str) or not re.fullmatch(r'doc-[1-9][0-9]{0,9}', target):
        raise ValueError('Specify an exact editor document ID from workspace_control list.')
    if action == 'replace':
        if not isinstance(code, str) or len(code.encode('utf-8')) > MAX_CODE_BYTES:
            raise ValueError('Replacement code exceeds the size limit.')
        if not isinstance(base_revision, str) or not re.fullmatch(r'[0-9a-f]{64}', base_revision):
            raise ValueError('Replacement requires the revision from an approved read.')
    return {'action': action, 'target': target, 'code': code if action == 'replace' else '',
            'base_revision': base_revision if action == 'replace' else ''}


class EditorRequest(BrowserReadRequest):
    def __init__(self, command):
        super().__init__()
        self.command = validate(**command)

    def wait(self, timeout):
        result = super().wait(timeout)
        if result.get('message') == 'Browser read timed out and was cancelled.':
            return {'ok': False, 'message': 'Editor assistance timed out and was cancelled.'}
        return result
