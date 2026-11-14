"""Coordinate the assistant's local camera consumers within this process."""
import threading

_lock = threading.Lock()


def acquire():
    return _lock.acquire(blocking=False)


def release():
    _lock.release()
