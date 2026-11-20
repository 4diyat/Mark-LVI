"""Capture browser chrome offscreen with no site, credentials or network."""
import base64
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QBuffer, QByteArray, QCoreApplication, QIODevice, Qt  # noqa: E402
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from ui.workspace_browser import BrowserWindow  # noqa: E402


def main():
    app = QApplication([sys.argv[0]])
    class Host:
        def get_plugins(self):
            return [{'name': 'workspace_browser', 'valid': True, 'enabled': True}]
    window = BrowserWindow(Host())
    window.resize(1000, 650)
    window.add_tab()
    # Input only, deliberately never navigate or read a vault.
    window.tabs.currentWidget().address.setText('https://example.test/')
    window.show()
    QTest.qWait(500)
    app.processEvents()
    image = window.grab().scaledToWidth(820, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'JPG', 30):
        raise RuntimeError('Cannot save browser capture')
    encoded = base64.b64encode(bytes(data)).decode('ascii')
    parts = [encoded[i:i + 3900] for i in range(0, len(encoded), 3900)]
    if len(parts) > 9:
        raise RuntimeError(f'Browser capture too large: {len(parts)} chunks')
    for i, part in enumerate(parts):
        print(f'::notice title=Browser capture {i + 1} of {len(parts)}::{part}', flush=True)
    window.close()
    app.processEvents()


if __name__ == '__main__':
    main()
