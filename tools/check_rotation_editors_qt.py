"""Exercise real JARVIS editors in an isolated, rotated Qt graphics proxy.

This does not embed workspace windows, simulate camera input, or test WebEngine.
It must never run user code or open user files.
"""
import faulthandler
import os
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QMessageBox  # noqa: E402

from ui.creative import CreativeWorkspace  # noqa: E402
from ui.image_editor import ImageEditor  # noqa: E402


def main():
    faulthandler.dump_traceback_later(30, exit=True)
    print('rotation-editor: starting', flush=True)
    app = QApplication([])
    scene = QGraphicsScene(0, 0, 1400, 1000)
    view = QGraphicsView(scene)
    view.setSceneRect(scene.sceneRect())
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(1420, 1020)
    view.show()

    def embed(document, angle):
        document.setWindowFlags(Qt.WindowType.Widget)
        document.resize(700, 500)
        proxy = scene.addWidget(document)
        assert proxy is not None
        proxy.setPos(350, 250)
        proxy.setTransformOriginPoint(proxy.boundingRect().center())
        proxy.setRotation(angle)
        QTest.qWait(100)
        app.processEvents()
        return proxy

    def mapped(proxy, root, widget, point=None):
        local = point if point is not None else widget.rect().center()
        target = view.mapFromScene(proxy.mapToScene(QPointF(widget.mapTo(root, local))))
        assert view.viewport().rect().contains(target)
        return target

    def click(proxy, root, widget, point=None):
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=mapped(proxy, root, widget, point))
        app.processEvents()

    print('rotation-editor: create code editor', flush=True)
    editor = CreativeWorkspace(None, {'code': 'original draft'})
    editor._host = SimpleNamespace(get_plugins=lambda: [
        {'name': 'code_editor', 'valid': True, 'enabled': True}])
    proxy = embed(editor, 25)
    print('rotation-editor: type first draft', flush=True)
    click(proxy, editor, editor._code.viewport())
    assert editor._code.hasFocus()
    QTest.keyClick(view.viewport(), Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(view.viewport(), ' changed')
    assert editor._code.toPlainText() == 'original draft changed'
    first = editor._code
    print('rotation-editor: new tab', flush=True)
    click(proxy, editor, editor._new_tab_button)
    assert editor._file_tabs.count() == 2 and editor._code is not first
    click(proxy, editor, editor._code.viewport())
    QTest.keyClicks(view.viewport(), 'second draft')
    assert editor._code.toPlainText() == 'second draft'
    # Exercise the real close guard; mock only the answer so no file is lost.
    print('rotation-editor: close guard', flush=True)
    old_question = QMessageBox.question
    questions = []
    try:
        def deny(*args):
            questions.append(args)
            return QMessageBox.StandardButton.No
        QMessageBox.question = staticmethod(deny)
        editor._close_file_tab(0)
    finally:
        QMessageBox.question = old_question
    assert questions and editor._file_tabs.count() == 2 and first.toPlainText() == 'original draft changed'
    for code in tuple(editor._paths):
        code.document().setModified(False)
    print('rotation-editor: close editor', flush=True)
    assert editor.close()
    app.processEvents()

    print('rotation-editor: create image editor', flush=True)
    photo = ImageEditor(None, {})
    proxy = embed(photo, -20)
    picture = QImage(100, 60, QImage.Format.Format_ARGB32)
    picture.fill(Qt.GlobalColor.red)
    photo._image = picture
    photo._render()
    app.processEvents()
    print('rotation-editor: select', flush=True)
    click(proxy, photo, photo._image_tools['image_editor.select'])
    QTest.qWait(30)
    rect = photo._preview._image_rect()
    start = QPoint(round(rect.left() + rect.width() * .25), round(rect.top() + rect.height() * .25))
    end = QPoint(round(rect.left() + rect.width() * .75), round(rect.top() + rect.height() * .75))
    target_start = mapped(proxy, photo, photo._preview, start)
    target_end = mapped(proxy, photo, photo._preview, end)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=target_start)
    QTest.mouseMove(view.viewport(), target_end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=target_end)
    assert photo._preview.selection is not None and not photo._dirty
    assert 49 <= photo._preview.selection[2] <= 52 and 29 <= photo._preview.selection[3] <= 32
    print('rotation-editor: rotate undo', flush=True)
    click(proxy, photo, photo._image_tools['image_editor.rotate'])
    assert (photo._image.width(), photo._image.height()) == (60, 100) and photo._dirty
    click(proxy, photo, photo._file_tools['image_editor.undo'])
    assert (photo._image.width(), photo._image.height()) == (100, 60)
    photo._dirty = False
    assert photo.close()
    view.close()
    faulthandler.cancel_dump_traceback_later()
    print('Rotated JARVIS editor proof passed; workspace integration remains unimplemented.')


if __name__ == '__main__':
    main()
