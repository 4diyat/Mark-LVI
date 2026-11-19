"""Capture a synthetic offscreen desktop in CI for visual inspection."""
import base64
import os
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import memory.config_manager as config  # noqa: E402
from ui.window import MainWindow  # noqa: E402
from ui.desktop_workspace import open_initial_editor  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['HOME'] = tmp
        config.CONFIG_DIR = Path(tmp)
        config.CONFIG_FILE = Path(tmp) / 'api_keys.json'
        MainWindow._check_config = lambda self: True
        app = QApplication([])
        window = MainWindow('')
        window.resize(1366, 768)
        window.get_plugins = lambda: [{'name': 'code_editor', 'valid': True, 'enabled': True}]
        window.show()
        QTest.qWait(300)
        open_initial_editor(window)
        QTest.qWait(300)
        app.processEvents()
        image = window.grab().scaledToWidth(960, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'JPG', 40):
            raise RuntimeError('Cannot save screenshot')
        encoded = base64.b64encode(bytes(data)).decode('ascii')
        size = 12000
        parts = [encoded[i:i + size] for i in range(0, len(encoded), size)]
        if len(parts) > 9:
            raise RuntimeError(f'Screenshot too large: {len(parts)} chunks')
        for i, part in enumerate(parts):
            print(f'::notice title=Desktop capture {i + 1} of {len(parts)}::{part}', flush=True)
        window._hand_timer.stop()


if __name__ == '__main__':
    main()
