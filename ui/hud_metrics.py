"""Read the existing system monitor on one worker, never on the Qt thread."""
from __future__ import annotations

import threading

from PyQt6.QtCore import QTimer


class MetricsSampler:
    def __init__(self, owner, deliver):
        self.owner = owner
        self.deliver = deliver
        self.running = False
        self.timer = QTimer()
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.refresh)

    def start(self):
        self.refresh()
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def refresh(self):
        if self.running:
            return
        self.running = True
        def read():
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=0.2)
                ram = psutil.virtual_memory().percent
                cpu = float(cpu) if cpu is not None and 0 <= float(cpu) <= 100 else None
                ram = float(ram) if ram is not None and 0 <= float(ram) <= 100 else None
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] System metrics unavailable: {type(exc).__name__}: {exc}')
                cpu = ram = None
            from ui.qt_thread import run_on_qt_thread
            run_on_qt_thread(self.owner, lambda: self._finish(cpu, ram))
        try:
            threading.Thread(target=read, name='hud-metrics', daemon=True).start()
        except Exception as exc:  # noqa: BLE001
            print(f'[JARVIS] System metrics worker failed: {type(exc).__name__}: {exc}')
            self._finish(None, None)

    def _finish(self, cpu, ram):
        self.running = False
        self.deliver(cpu, ram)
