"""Run a real, offscreen Qt desktop smoke test (not the suite's Qt stubs).

Run with QT_QPA_PLATFORM=offscreen and the normal application dependencies.
No camera, microphone, network, credentials or user config is required.
"""
import os
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton, QSizeGrip, QWidget  # noqa: E402

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
        QTest.qWait(300)
        app.processEvents()
        mdi = window._desktop_mdi
        dock = mdi._dock
        assert dock.parentWidget() is mdi.viewport()
        assert dock.width() >= 850
        assert all(button.isVisible() for button, _ in window._workspace_dock)
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
        assert not command({"action": "focus", "target": "doc-2"})["ok"]
        assert command({"action": "close", "target": "files"})["ok"]
        assert files.isHidden()
        assert command({"action": "open", "target": "files"})["ok"]
        assert not files.isHidden()
        assert command({"action": "open", "target": "handboard"})["ok"]
        assert window._hand_controller.thread is None  # opening must not start a camera
        assert command({"action": "board_add", "title": "Plan", "text": "First task"})["ok"]
        board = window._hand_board
        QTest.qWait(50)
        cards = command({"action": "board_list"})["items"]
        assert len(cards) == 1 and cards[0]["text"] == "First task"
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
            board._owned_control = True
            stops.clear()
            assert command({"action": "close", "target": "handboard"})["ok"]
            assert stops and window._desktop_windows["handboard"].isHidden()
        finally:
            QMessageBox.question = original_question
            window._hand_controller.stop = original_stop
        assert command({"action": "open", "target": "handboard"})["ok"]
        assert len(command({"action": "board_list"})["items"]) == 1
        print("Real Qt desktop, workspace and native hand board passed.")


if __name__ == "__main__":
    main()
