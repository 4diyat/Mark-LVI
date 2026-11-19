"""Capture a synthetic offscreen desktop in CI for visual inspection."""
import base64
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import memory.config_manager as config  # noqa: E402
from ui.window import MainWindow  # noqa: E402
from ui.desktop_workspace import open_initial_editor, show_document
from ui.image_editor import ImageEditor
from core.image_layers import make_text_layer  # noqa: E402


def emit_capture(widget, title):
    image = widget.grab().scaledToWidth(820, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'JPG', 30):
        raise RuntimeError('Cannot save screenshot')
    encoded = base64.b64encode(bytes(data)).decode('ascii')
    parts = [encoded[i:i + 3900] for i in range(0, len(encoded), 3900)]
    if len(parts) > 9:
        raise RuntimeError(f'Screenshot too large: {len(parts)} chunks')
    for i, part in enumerate(parts):
        print(f'::notice title={title} {i + 1} of {len(parts)}::{part}', flush=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['HOME'] = tmp
        # Fictional contents make the listing and chat inspectable without
        # uploading any user documents, history, or credentials in CI.
        home = Path(tmp)
        for name in ('Projects', 'Documents', 'Downloads', 'Desktop'):
            (home / name).mkdir()
        # A local-only project tree for the screenshot, never user files.
        (home / 'Projects' / 'main.py').touch()
        (home / 'Projects' / 'utils.py').touch()
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
        editor = next(sub._document for kind, sub in window._workspace_documents.values()
                      if kind == 'code_editor')
        if not editor._set_project_root(str(home / 'Projects')):
            raise RuntimeError('Synthetic project could not be opened')
        editor._project_panel.show()
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
        emit_capture(window, 'Desktop capture')
        # A generated in-memory image and fictional text layer reveal the image
        # editor layout without reading or uploading user documents.
        picture = QImage(640, 360, QImage.Format.Format_ARGB32)
        gradient = QLinearGradient(0, 0, 0, 360)
        gradient.setColorAt(0, QColor('#78aaca'))
        gradient.setColorAt(1, QColor('#243e58'))
        painter = QPainter(picture)
        painter.fillRect(picture.rect(), gradient)
        painter.setBrush(QColor('#e7c78b'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(430, 50, 80, 80)
        painter.end()
        photo = ImageEditor(window, {})
        photo._image = picture
        photo._layers = [make_text_layer('Synthetic landscape', 20, 320, 24, 640, 360)]
        photo._update_layers()
        sub = show_document(window, photo, 'image_editor')
        sub.setGeometry(180, 70, 900, 590)
        photo._render()
        QTest.qWait(300)
        app.processEvents()
        emit_capture(sub, 'Image editor capture')
        # Report actual software-render cost; a visual improvement must not
        # silently consume an entire frame budget on the CI runner.
        avatar = window.hud._avatar
        canvas = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
        bg, primary = QColor('#0b1725'), QColor('#8fd3ff')
        elapsed = []
        for _ in range(8):
            canvas.fill(bg)
            painter = QPainter(canvas)
            start = time.perf_counter()
            avatar.paint(painter, 150, 120, 90, primary, primary, bg, wireframe=False)
            painter.end()
            elapsed.append((time.perf_counter() - start) * 1000)
        print(f'::notice title=Desktop face render::Mean {sum(elapsed[1:]) / 7:.1f} ms '
              f'(7 warm frames, offscreen synthetic test)', flush=True)
        window._hand_timer.stop()


if __name__ == '__main__':
    main()
