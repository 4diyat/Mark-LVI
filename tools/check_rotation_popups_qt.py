"""Test synthetic popup and confirmation input in an isolated rotated proxy.

No workspace, camera, network, model, commands, or real user data is involved.
"""
import faulthandler
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPointF, QTimer, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QGraphicsScene, QGraphicsView, QMenu, QMessageBox,  # noqa: E402
                             QPushButton, QToolButton, QVBoxLayout, QWidget)


def main():
    faulthandler.dump_traceback_later(30, exit=True)
    app = QApplication([])
    scene = QGraphicsScene(0, 0, 900, 700)
    view = QGraphicsView(scene)
    view.setSceneRect(scene.sceneRect())
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(920, 720)
    root = QWidget()
    root.resize(340, 220)
    layout = QVBoxLayout(root)
    menu = QMenu(root)
    action = menu.addAction('Synthetic menu action')
    chosen = []
    action.triggered.connect(lambda: chosen.append(True))
    menu_button = QToolButton()
    menu_button.setText('Open synthetic menu')
    menu_button.setMenu(menu)
    menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    confirm_button = QPushButton('Synthetic confirmation')
    answers = []
    def ask():
        answers.append(QMessageBox.question(root, 'Synthetic', 'Allow synthetic action?',
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                            QMessageBox.StandardButton.No))
    confirm_button.clicked.connect(ask)
    layout.addWidget(menu_button)
    layout.addWidget(confirm_button)
    proxy = scene.addWidget(root)
    proxy.setPos(260, 200)
    proxy.setTransformOriginPoint(proxy.boundingRect().center())
    view.show()
    QTest.qWait(100)
    outcomes = []

    def click_root(widget):
        point = widget.mapTo(root, widget.rect().center())
        pos = view.mapFromScene(proxy.mapToScene(QPointF(point)))
        assert view.viewport().rect().contains(pos)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        app.processEvents()

    def click_popup(widget, point):
        # Qt may host a popup as a child proxy or as its own top-level window.
        # Route the click through the graphics viewport only in the former case.
        popup_proxy = widget.graphicsProxyWidget()
        if popup_proxy is not None:
            pos = view.mapFromScene(popup_proxy.mapToScene(QPointF(point)))
            if not view.viewport().rect().contains(pos):
                outcomes.append('outside')
                widget.close()
                return
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
            outcomes.append('proxy')
        else:
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point)
            outcomes.append('top-level')

    def choose_menu():
        if not menu.isVisible():
            outcomes.append('menu-not-visible')
            menu.close()
            return
        click_popup(menu, menu.actionGeometry(action).center())

    def reject_dialog():
        dialogs = [w for w in app.allWidgets() if isinstance(w, QMessageBox) and w.isVisible()]
        if len(dialogs) != 1:
            outcomes.append('dialog-not-visible')
            return
        box = dialogs[0]
        button = box.button(QMessageBox.StandardButton.No)
        if button is None:
            outcomes.append('no-button-missing')
            box.reject()
            return
        # The confirmation's buttons are real Qt controls; map to the popup's
        # coordinates before dispatching to either its proxy or top-level.
        click_popup(box, button.mapTo(box, button.rect().center()))

    for angle in (0, 31):
        proxy.setRotation(angle)
        app.processEvents()
        print(f'popup proof angle {angle}: menu', flush=True)
        before = len(chosen)
        QTimer.singleShot(100, choose_menu)
        click_root(menu_button)
        QTest.qWait(250)  # InstantPopup may open after the click returns.
        assert len(chosen) == before + 1, outcomes
        print(f'popup proof angle {angle}: reject', flush=True)
        QTimer.singleShot(100, reject_dialog)
        click_root(confirm_button)
        QTest.qWait(250)
        assert answers and answers[-1] == QMessageBox.StandardButton.No, (answers, outcomes)
    assert all(item in ('proxy', 'top-level') for item in outcomes), outcomes
    assert len(outcomes) == 4
    print(f'Popup and rejection proof passed; popup routes: {outcomes}', flush=True)
    view.close()
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
