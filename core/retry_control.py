"""Thread-safe, user-requestable retry for network backoff only."""
from __future__ import annotations

import asyncio
import threading
import time


class RetryControl:
    def __init__(self):
        self._lock = threading.Lock()
        self._deadline = None
        self._manual = False
        self._loop = None
        self._event = None

    def snapshot(self):
        """Return monotonic deadline and whether retry is currently allowed."""
        with self._lock:
            return self._deadline, self._manual

    def request(self):
        with self._lock:
            if not self._manual or self._loop is None or self._event is None:
                return False
            self._manual = False  # One request per backoff window.
            try:
                self._loop.call_soon_threadsafe(self._event.set)
            except RuntimeError:
                return False
            return True

    async def wait(self, delay, allow_manual=False):
        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        with self._lock:
            self._deadline = time.monotonic() + max(0.0, delay)
            self._manual = bool(allow_manual and delay > 0)
            self._loop = loop
            self._event = event
        try:
            try:
                await asyncio.wait_for(event.wait(), timeout=max(0.0, delay))
                return True
            except TimeoutError:
                return False
        finally:
            with self._lock:
                self._deadline = self._loop = self._event = None
                self._manual = False
