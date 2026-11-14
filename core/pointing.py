"""Short-lived, local gesture pointer coordinates, normalized to the primary screen."""
import threading
import time

_lock = threading.Lock()
_point = None


def update(point):
    global _point
    with _lock:
        _point = (point, time.monotonic()) if point is not None else None


def recent(max_age=1.5):
    with _lock:
        item = _point
    if item is None or time.monotonic() - item[1] > max_age:
        return None
    return item[0]
