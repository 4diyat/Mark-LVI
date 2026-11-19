"""Isolated proof: transformed *real* widgets receive mapped input.

This is not connected to the workspace or gesture controller. Native-backed
widgets, popups, dialogs, window lifecycle and OS/device behavior need separate
investigation before this approach can be considered for production.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QGraphicsScene, QGraphicsView,  # noqa: E402
                             QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)


def main():
    app = QApplication([])
    scene = QGraphicsScene(0, 0, 900, 700)
    view = QGraphicsView(scene)
    view.setSceneRect(scene.sceneRect())
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(920, 720)
    root = QWidget()
    root.resize(380, 300)
    layout = QVBoxLayout(root)
    edit = QLineEdit()
    check = QCheckBox('synthetic check')
    button = QPushButton('synthetic action')
    text = QPlainTextEdit()
    text.setPlainText('\n'.join(f'row {n}' for n in range(80)))
    for widget in (edit, check, button, text):
        layout.addWidget(widget)
    calls = []
    button.clicked.connect(lambda: calls.append('clicked'))
    proxy = scene.addWidget(root)
    proxy.setTransformOriginPoint(proxy.boundingRect().center())
    proxy.setPos(260, 180)
    view.show()
    QTest.qWait(100)

    def click(widget, point=None):
        local = point if point is not None else widget.rect().center()
        parent_point = widget.mapTo(root, local)
        scene_point = proxy.mapToScene(QPointF(parent_point))
        target = view.mapFromScene(scene_point)
        assert view.viewport().rect().contains(target)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
        app.processEvents()

    for angle in (0, 37, -90):
        proxy.setRotation(angle)
        app.processEvents()
        # Round trip explicitly checks inverse mapping, not a static snapshot.
        point = QPointF(41, 72)
        mapped = proxy.mapFromScene(proxy.mapToScene(point))
        assert abs(mapped.x() - point.x()) < .001 and abs(mapped.y() - point.y()) < .001
        click(edit)
        assert edit.hasFocus()
        QTest.keyClick(view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(view.viewport(), f'angle{angle}')
        assert edit.text() == f'angle{angle}'
        before = check.isChecked()
        click(check, QPoint(8, check.rect().center().y()))
        assert check.isChecked() != before
        count = len(calls)
        click(button)
        assert len(calls) == count + 1
        click(text)
        QTest.keyClick(view.viewport(), Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
        assert text.verticalScrollBar().value() == text.verticalScrollBar().maximum()
        QTest.keyClick(view.viewport(), Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
        assert text.verticalScrollBar().value() == 0
    view.close()
    print('Rotated widget proof passed (ordinary Qt widgets, offscreen only).')


if __name__ == '__main__':
    main()
