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
        # Fictional contents make the listing and chat inspectable without
        # uploading any user documents, history, or credentials in CI.
        home = Path(tmp)
        for name in ('Projects', 'Documents', 'Downloads', 'Desktop'):
            (home / name).mkdir()
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
        # Example code is synthetic, unsaved, and never executed.
        from ui.creative import CreativeWorkspace
        editor = next((sub.widget() for sub in window._desktop_mdi.subWindowList()
                       if isinstance(sub.widget(), CreativeWorkspace)), None)
        if editor is not None:
            editor._code.setPlainText("def analyze_system(data):\n    return {'status': 'ready'}\n")
            editor._code.highlighter.set_language('python')
        for text in ('You: Summarize my latest project.',
                     'JARVIS: This preview uses fictional data for visual testing.'):
            window._log._enqueue(text)
            for _ in range(len(text) + 1):
                window._log._step()
            # _step queues _next via the event loop; advance it now rather than
            # spinning until that queued callback is allowed to run.
            window._log._next()
        QTest.qWait(300)
        app.processEvents()
        image = window.grab().scaledToWidth(820, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'JPG', 30):
            raise RuntimeError('Cannot save screenshot')
        encoded = base64.b64encode(bytes(data)).decode('ascii')
        size = 3900
        parts = [encoded[i:i + size] for i in range(0, len(encoded), size)]
        if len(parts) > 9:
            raise RuntimeError(f'Screenshot too large: {len(parts)} chunks')
        for i, part in enumerate(parts):
            print(f'::notice title=Desktop capture {i + 1} of {len(parts)}::{part}', flush=True)
        window._hand_timer.stop()


if __name__ == '__main__':
    main()
