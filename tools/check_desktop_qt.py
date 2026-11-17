"""Run a real, offscreen Qt desktop smoke test (not the suite's Qt stubs).

Run with QT_QPA_PLATFORM=offscreen and the normal application dependencies.
No camera, microphone, network, credentials or user config is required.
"""
import os
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QTimer, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox, QFileDialog, QMessageBox, QPushButton, QScrollArea, QSizeGrip, QSlider, QWidget  # noqa: E402

import memory.config_manager as config  # noqa: E402
from core.i18n import label as translate  # noqa: E402
from ui.window import JarvisUI, MainWindow  # noqa: E402
from ui.desktop_workspace import show_document  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        config.CONFIG_DIR = Path(tmp)
        config.CONFIG_FILE = Path(tmp) / "api_keys.json"
        MainWindow._check_config = lambda self: True
        app = QApplication([])
        window = MainWindow("")
        window.resize(1366, 768)
        window.show()
        window.move(0, 0)
        QTest.qWait(300)
        app.processEvents()
        mdi = window._desktop_mdi
        dock = mdi._dock
        from ui.theme import C
        assert C.DESKTOP_PANEL in window._workspace_file_browser.styleSheet()
        assert 'QMenu::item:selected' in window._workspace_file_browser.styleSheet()
        assert dock.parentWidget() is mdi.viewport()
        assert 500 <= dock.width() <= mdi.viewport().width()
        assert all(button.isVisible() for button, _ in window._workspace_dock)
        # Activation is discoverable in Apps -> Controls and needs no external
        # server, installation directory, or camera in this smoke test.
        controls = next(action for action, key in window._workspace_dock_actions if key == "workspace.navigation")
        controls.trigger()
        navigation = window._desktop_windows["navigation"]
        app.processEvents()
        assert navigation.isVisible()
        hand_button = next(button for button in window._left_panel.findChildren(QPushButton)
                           if button.text() == translate("gesture.enable"))
        assert hand_button.isVisible()
        assert hand_button.mapTo(navigation, QPoint(0, 0)).y() + hand_button.height() <= navigation.height()
        assert config.set_config_values(camera_index=3)
        starts = []
        original_start = window._hand_controller.start
        window._hand_controller.start = lambda index: starts.append(index)
        try:
            hand_button.click()
            assert starts == [3]
        finally:
            window._hand_controller.start = original_start
            navigation.hide()
        assert window.hud.hud_style == "orb"
        assert window._drop_zone.isHidden()
        QTest.mouseClick(window._attachment_toggle, Qt.MouseButton.LeftButton)
        assert not window._drop_zone.isHidden()
        QTest.mouseClick(window._attachment_toggle, Qt.MouseButton.LeftButton)
        assert window._drop_zone.isHidden()
        files = window._desktop_windows["files"]
        title = files._workspace_title
        old_position = files.pos()
        QTest.mousePress(title, Qt.MouseButton.LeftButton, pos=QPoint(160, 15))
        QTest.mouseMove(title, QPoint(200, 35), 20)
        QTest.mouseRelease(title, Qt.MouseButton.LeftButton, pos=QPoint(200, 35))
        assert files.pos() != old_position
        grip = files.findChild(QSizeGrip)
        old_size = files.size()
        QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        QTest.mouseMove(grip, QPoint(35, 25), 20)
        QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=QPoint(35, 25))
        assert files.size().width() > old_size.width()
        close = next(button for button in files._workspace_title.findChildren(QPushButton)
                     if button.toolTip() == translate("workspace.close"))
        QTest.mouseClick(close, Qt.MouseButton.LeftButton)
        assert files.isHidden()
        next(button for button, key in window._workspace_dock if key == "workspace.files").click()
        assert not files.isHidden()
        assistant = window._desktop_windows["assistant"]
        assistant._workspace_title.toggle_maximize()
        assert assistant.isMaximized()
        assistant._workspace_title.toggle_maximize()
        assert not assistant.isMaximized()
        assert window._right_panel.parentWidget() is window._assistant_panel

        # Exercise the same worker -> Qt signal -> result path used by plugins.
        bridge = JarvisUI.__new__(JarvisUI)
        bridge._win = window
        assert not bridge.control_workspace({"action": "list"})["ok"]  # no waiting on Qt thread

        def command(payload):
            result = []
            worker = threading.Thread(target=lambda: result.append(bridge.control_workspace(payload)))
            worker.start()
            for _ in range(100):
                if not worker.is_alive():
                    break
                QTest.qWait(20)
            worker.join(timeout=1)
            assert result, "workspace request did not complete"
            return result[0]

        listing = command({"action": "list"})
        assert listing["ok"] and any(item["id"] == "files" for item in listing["windows"])
        assert command({"action": "navigate", "text": tmp})["ok"]
        assert Path(window._workspace_file_browser.path.text()) == Path(tmp).resolve()
        assert command({"action": "search", "text": "report"})["ok"]
        assert window._workspace_file_browser.search.text() == "report"
        assert command({"action": "move_left", "target": "files"})["ok"]
        assert files.x() == 0
        doc = QWidget()
        doc.setWindowTitle("Example")
        sub = show_document(window, doc, "code_editor")
        listing = command({"action": "list"})
        assert any(item["id"] == "doc-1" and item["kind"] == "code_editor" and item["active"] for item in listing["windows"])
        assert not command({"action": "close", "target": "active"})["ok"]
        assert not command({"action": "close", "target": "doc-1"})["ok"]
        assert not sub.isHidden()
        assert command({"action": "minimize", "target": "doc-1"})["ok"]
        assert sub.isMinimized()
        assert command({"action": "restore", "target": "doc-1"})["ok"]
        assert not sub.isMinimized()
        window.get_plugins = lambda: []
        assert not command({"action": "open", "target": "code_editor"})["ok"]
        window.get_plugins = lambda: [{"name": "code_editor", "valid": True, "enabled": True}]
        opened = command({"action": "open", "target": "code_editor"})
        assert opened["ok"] and "doc-2" in opened["message"]
        assert window._workspace_documents["doc-2"][0] == "code_editor"
        assert not command({"action": "close", "target": "doc-2"})["ok"]
        window._workspace_documents["doc-2"][1].close()  # user-initiated close
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        assert "doc-2" not in window._workspace_documents
        # Shared window chrome must never bypass a document's close veto.
        class VetoDocument(QWidget):
            allow = False
            def closeEvent(self, event):
                event.accept() if self.allow else event.ignore()
        veto = VetoDocument()
        veto_sub = show_document(window, veto, "code_editor")
        assert not veto_sub.close() and veto.isVisible()
        veto.allow = True
        assert veto_sub.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        assert "doc-3" not in window._workspace_documents
        assert not command({"action": "focus", "target": "doc-2"})["ok"]
        assert command({"action": "close", "target": "files"})["ok"]
        assert files.isHidden()
        assert command({"action": "open", "target": "files"})["ok"]
        assert not files.isHidden()

        # Feed synthetic tracked hands on the Qt thread: no OS pointer is used.
        window._hand_timer.stop()
        window.activateWindow()
        app.processEvents()
        assert window.isActiveWindow()
        gestures = window._workspace_gestures
        mdi.setActiveSubWindow(files)
        files.raise_()
        app.processEvents()
        viewport = mdi.viewport()
        def sample(point):
            return (point.x() / (viewport.width() - 1), point.y() / (viewport.height() - 1), True)
        def begin(samples):
            gestures.update(samples)
            gestures.pending = (gestures.pending[0], gestures.pending[1] - 1)
            gestures.update(samples)
        anchor = files._workspace_title.mapTo(viewport, QPoint(160, 15))
        before = files.pos()
        begin((sample(anchor),))
        assert gestures.mode == "move"
        gestures.update((sample(anchor + QPoint(35, 20)),))
        assert files.pos() != before
        gestures.update(())  # loss of tracking releases the target
        assert gestures.mode is None
        center = files.mapTo(viewport, QPoint(files.width() // 2, 100))
        left, right = center - QPoint(80, 0), center + QPoint(80, 0)
        before_size = files.size()
        begin((sample(left), sample(right)))
        assert gestures.mode == "resize"
        gestures.update((sample(left - QPoint(40, 0)), sample(right + QPoint(40, 0))))
        assert files.width() > before_size.width()
        gestures.update(())
        mdi.setActiveSubWindow(sub)
        sub.raise_()
        app.processEvents()
        native_title = sub._workspace_title.mapTo(viewport, QPoint(160, 15))
        native_before = sub.pos()
        begin((sample(native_title),))
        assert gestures.mode == "move"
        gestures.update((sample(native_title + QPoint(25, 20)),))
        assert sub.pos() != native_before
        window._hand_closing_confirm = True
        gestures.update((sample(left), sample(right)))
        assert gestures.mode is None
        window._hand_closing_confirm = False
        window._hand_timer.start()

        assert command({"action": "open", "target": "handboard"})["ok"]
        assert window._hand_controller.thread is None  # opening must not start a camera
        assert command({"action": "board_add", "title": "Plan", "text": "First task"})["ok"]
        board = window._hand_board
        QTest.qWait(50)
        cards = command({"action": "board_list"})["items"]
        assert len(cards) == 1 and cards[0]["text"] == "First task"

        # A confirmed pinch release clicks an internal Qt control; tracking
        # loss and safety confirmation must never generate that click.
        window._hand_timer.stop()
        board_sub = window._desktop_windows["handboard"]
        mdi.setActiveSubWindow(board_sub)
        board_sub.raise_()
        app.processEvents()
        test_button = QPushButton(board)
        test_button.setGeometry(10, 70, 100, 30)
        test_button.show()
        test_button.raise_()
        calls = []
        test_button.clicked.connect(lambda: calls.append(True))
        point = test_button.mapTo(viewport, QPoint(40, 15))
        begin((sample(point),))
        assert gestures.mode == "click"
        gestures.update(())  # tracking loss cancels, not a click
        assert not calls
        begin((sample(point),))
        gestures.update(((sample(point)[0], sample(point)[1], False),))
        assert calls == [True]
        begin((sample(point),))
        window._hand_closing_confirm = True
        gestures.update(((sample(point)[0], sample(point)[1], False),))
        window._hand_closing_confirm = False
        assert calls == [True]
        # A central-widget overlay above the workspace blocks underlying input.
        overlay = QWidget(window.centralWidget())
        overlay_pos = viewport.mapTo(window.centralWidget(), point - QPoint(20, 15))
        overlay.setGeometry(overlay_pos.x(), overlay_pos.y(), 50, 35)
        overlay.show()
        overlay.raise_()
        app.processEvents()
        gestures.update((sample(point),))
        assert gestures.pending is None and gestures.mode is None
        gestures.update(((sample(point)[0], sample(point)[1], False),))
        assert calls == [True]
        overlay_button = QPushButton(overlay)
        overlay_button.setGeometry(0, 0, 50, 35)
        overlay_button.show()
        overlay_clicks = []
        overlay_button.clicked.connect(lambda: overlay_clicks.append(True))
        old_overlay = getattr(window, "_plugin_settings_overlay", None)
        window._plugin_settings_overlay = overlay
        app.processEvents()
        begin((sample(point),))
        assert gestures.mode == "click"
        gestures.update(((sample(point)[0], sample(point)[1], False),))
        assert overlay_clicks == [True] and calls == [True]
        window._plugin_settings_overlay = old_overlay
        overlay.hide()
        test_button.hide()
        slider = QSlider(Qt.Orientation.Horizontal, board)
        slider.setGeometry(10, 70, 180, 30)
        slider.setRange(0, 100)
        slider.setValue(25)
        slider.show()
        slider.raise_()
        app.processEvents()
        slider_point = slider.mapTo(viewport, QPoint(40, 15))
        begin((sample(slider_point),))
        assert gestures.mode == "slider"
        gestures.update((sample(slider_point + QPoint(60, 0)),))
        assert slider.value() > 25
        gestures.update(())
        slider.hide()
        combo = QComboBox(board)
        combo.addItems(["First", "Disabled", "Third"])
        combo.model().item(1).setEnabled(False)
        combo.setGeometry(10, 70, 160, 30)
        combo.show()
        combo.raise_()
        app.processEvents()
        combo.showPopup()
        QTest.qWait(20)
        view = combo.view()
        combo_popup = QApplication.activePopupWidget()
        assert combo_popup is view.window()
        def combo_point(row):
            local = view.visualRect(combo.model().index(row, 0)).center()
            return viewport.mapFromGlobal(view.viewport().mapToGlobal(local))
        disabled = combo_point(1)
        gestures.update((sample(disabled),))
        assert gestures.popup_pending is None
        enabled = combo_point(2)
        gestures.update((sample(enabled),))
        assert gestures.popup_pending is not None
        gestures.popup_pending = (gestures.popup_pending[0], gestures.popup_pending[1] - 1)
        gestures.update(((sample(enabled)[0], sample(enabled)[1], False),))
        assert combo.currentIndex() == 2 and not combo_popup.isVisible()
        window.activateWindow()
        app.processEvents()
        activated = []
        combo.activated.connect(activated.append)
        def choose_combo():
            assert QApplication.activePopupWidget() is combo_popup
            pos = combo_point(0)
            gestures.update((sample(pos),))
            assert gestures.popup_pending
            gestures.popup_pending = (gestures.popup_pending[0], gestures.popup_pending[1] - 1)
            gestures.update(((sample(pos)[0], sample(pos)[1], False),))
        combo_anchor = combo.mapTo(viewport, QPoint(30, 15))
        begin((sample(combo_anchor),))
        assert gestures.mode == "click"
        QTimer.singleShot(50, choose_combo)
        QTimer.singleShot(500, combo.hidePopup)
        gestures.update(((sample(combo_anchor)[0], sample(combo_anchor)[1], False),))
        QTest.qWait(100)
        assert combo.currentIndex() == 0 and activated == [0]
        combo.hide()
        window.activateWindow()
        app.processEvents()
        scroll_area = QScrollArea(board)
        scroll_area.setGeometry(10, 130, 140, 100)
        scroll_content = QWidget()
        scroll_content.resize(120, 600)
        scroll_area.setWidget(scroll_content)
        scroll_area.show()
        scroll_area.raise_()
        app.processEvents()
        scroll_point = scroll_area.viewport().mapTo(viewport, QPoint(40, 40))
        one = sample(scroll_point)
        two = sample(scroll_point + QPoint(0, 35))
        gestures.update(((one[0], one[1], False, True),))
        gestures.update(((two[0], two[1], False, True),))
        assert scroll_area.verticalScrollBar().value() > 0
        gestures.update(())
        scroll_area.hide()

        # Dock menus can be chosen with gestures without touching OS windows.
        dock_button = next(button for button, key in window._workspace_dock if key == "workspace.apps")
        menu = dock_button.menu()
        menu.popup(viewport.mapToGlobal(QPoint(100, 100)))
        QTest.qWait(30)
        action = menu.actions()[0]
        triggered = []
        action.triggered.connect(lambda: triggered.append(True))
        menu_point = viewport.mapFromGlobal(menu.mapToGlobal(menu.actionGeometry(action).center()))
        gestures.update((sample(menu_point),))
        assert gestures.popup_pending
        gestures.popup_pending = (gestures.popup_pending[0], gestures.popup_pending[1] - 1)
        gestures.update(((sample(menu_point)[0], sample(menu_point)[1], False),))
        assert triggered == [True] and not menu.isVisible()
        window.activateWindow()
        board_sub.raise_()
        app.processEvents()
        # The dock can scroll at small/offscreen resolutions. Put Apps in its
        # visible viewport before exercising the same click a user can make.
        dock.ensureWidgetVisible(dock_button)
        app.processEvents()
        # Exercise the actual dock-button press -> popup -> gesture selection.
        actual = []
        action.triggered.connect(lambda: actual.append(True))
        def choose_popup():
            assert QApplication.activePopupWidget() is menu
            pos = viewport.mapFromGlobal(menu.mapToGlobal(menu.actionGeometry(action).center()))
            gestures.update((sample(pos),))
            gestures.popup_pending = (gestures.popup_pending[0], gestures.popup_pending[1] - 1)
            gestures.update(((sample(pos)[0], sample(pos)[1], False),))
        dock_pos = dock_button.mapTo(viewport, dock_button.rect().center())
        begin((sample(dock_pos),))
        assert gestures.mode == "click"
        assert gestures.target is dock_button, (f"Unexpected dock hit: {gestures.target!r}; "
                                                f"dock={dock.geometry()!r}, button={dock_button.geometry()!r}, "
                                                f"point={dock_pos!r}")
        QTimer.singleShot(50, choose_popup)
        QTimer.singleShot(500, menu.close)  # avoid hanging if popup selection regresses
        gestures.update(((sample(dock_pos)[0], sample(dock_pos)[1], False),))
        QTest.qWait(100)
        assert actual == [True]
        window.activateWindow()
        board_sub.raise_()
        app.processEvents()

        card = board._items[0]
        def card_point(x, y):
            return board.view.viewport().mapTo(viewport, board.view.mapFromScene(QPointF(x, y)))
        anchor = card_point(120, 110)
        original_pos = card.pos()
        begin((sample(anchor),))
        assert gestures.mode == "card_move"
        gestures.update((sample(anchor + QPoint(40, 20)),))
        assert card.pos() != original_pos
        gestures.update(())
        center = board.view.viewport().mapTo(viewport, board.view.mapFromScene(card.mapToScene(card.rect().center())))
        l, r = center - QPoint(60, 0), center + QPoint(60, 0)
        begin((sample(l), sample(r)))
        assert gestures.mode == "card_transform"
        gestures.update((sample(l - QPoint(30, 20)), sample(r + QPoint(30, 20))))
        assert card.scale() > 1 and abs(card.rotation()) > 1
        gestures.update(())
        card.setScale(1)
        card.setRotation(0)
        card.setPos(30, 30)
        window._hand_timer.start()

        start = board.view.mapFromScene(QPointF(100, 90))
        end = board.view.mapFromScene(QPointF(200, 140))
        QTest.mousePress(board.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(board.view.viewport(), end, 30)
        QTest.mouseRelease(board.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        moved = command({"action": "board_list"})["items"][0]
        assert moved["x"] > cards[0]["x"]
        image_path = str(Path(tmp) / "test.png")
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(QColor("blue"))
        assert image.save(image_path)
        original_dialog = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = lambda *args: (image_path, "")
        try:
            board._new_image()
        finally:
            QFileDialog.getOpenFileName = original_dialog
        assert command({"action": "board_list"})["items"][-1]["kind"] == "image"
        board.scene.clearSelection()
        board._items[-1].setSelected(True)
        original_question = QMessageBox.question
        stops = []
        original_stop = window._hand_controller.stop
        window._hand_controller.stop = lambda: stops.append(True)
        try:
            QMessageBox.question = lambda *args: QMessageBox.StandardButton.No
            board._remove_selected()
            assert len(board._items) == 2 and stops
            QMessageBox.question = lambda *args: QMessageBox.StandardButton.Yes
            board._remove_selected()
            assert len(board._items) == 1
            stops.clear()
            assert command({"action": "close", "target": "handboard"})["ok"]
            assert not stops and window._desktop_windows["handboard"].isHidden()
        finally:
            QMessageBox.question = original_question
            window._hand_controller.stop = original_stop
        assert command({"action": "open", "target": "handboard"})["ok"]
        assert len(command({"action": "board_list"})["items"]) == 1
        # OBJ is read only from a physical file selection, then rendered locally.
        obj_path = Path(tmp) / "tetra.obj"
        obj_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 2 4\n", encoding="utf-8")
        QFileDialog.getOpenFileName = lambda *args: (str(obj_path), "")
        try:
            board._new_model()
        finally:
            QFileDialog.getOpenFileName = original_dialog
        assert command({"action": "board_list"})["items"][-1]["kind"] == "model"
        model_card = board._items[-1]
        window._hand_timer.stop()
        mdi.setActiveSubWindow(board_sub)
        board_sub.raise_()
        window.activateWindow()
        app.processEvents()
        center = board.view.viewport().mapTo(viewport, board.view.mapFromScene(model_card.mapToScene(model_card.rect().center())))
        l, r = center - QPoint(35, 0), center + QPoint(35, 0)
        before_yaw, before_pitch = model_card.model_view.yaw, model_card.model_view.pitch
        begin((sample(l), sample(r)))
        assert gestures.mode == "card_transform"
        gestures.update((sample(l + QPoint(25, 15)), sample(r + QPoint(25, 15))))
        assert model_card.model_view.yaw != before_yaw and model_card.model_view.pitch != before_pitch
        assert not window.grab().isNull()  # exercises the QPainter wireframe path
        gestures.update(())
        assert not board._explode.isEnabled()  # a connected mesh has no separable parts
        from core.obj_wireframe import parse_obj
        parts = parse_obj(b'v -2 0 0\nv -1 0 0\nv -1 1 0\nv 1 0 0\nv 2 0 0\nv 1 1 0\nf 1 2 3\nf 4 5 6\n')
        assert board.add_model("two parts", parts)
        board.scene.clearSelection()
        separated = board._items[-1]
        separated.setSelected(True)
        app.processEvents()
        assert board._explode.isEnabled() and separated.model_view.parts == 2
        slider = board._explode
        start = slider.mapTo(viewport, QPoint(slider.width() // 4, slider.height() // 2))
        begin((sample(start),))
        assert gestures.mode == "slider"
        gestures.update((sample(start + QPoint(60, 0)),))
        assert separated.model_view.explode > 0
        assert command({"action": "board_list"})["items"][-1]["explode"] > 0
        gestures.update(())
        slider.setValue(0)
        assert separated.model_view.explode == 0
        window._hand_timer.start()
        print("Real Qt desktop, workspace and native hand board passed.")


if __name__ == "__main__":
    main()
