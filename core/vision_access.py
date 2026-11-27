"""Process-local switches for the built-in vision capture functions only.

Not an operating-system permission or a sandbox; other camera and screenshot
features, plugins, external programs and captures already running are outside
this control. Defaults reset on application restart.
"""
import threading

_lock = threading.RLock()
_allowed = {'screen': True, 'camera': True}


def is_allowed(kind):
    with _lock:
        return _allowed[kind]


def set_allowed(kind, value):
    with _lock:
        if kind not in _allowed:
            raise ValueError('unknown vision capture kind')
        _allowed[kind] = bool(value)


def require(kind):
    if not is_allowed(kind):
        raise PermissionError(f'{kind.capitalize()} vision capture is disabled in this session.')


def reset():
    with _lock:
        _allowed.update(screen=True, camera=True)
