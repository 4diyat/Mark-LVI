"""Run a real, offscreen Qt desktop smoke test (not the suite's Qt stubs).

Run with QT_QPA_PLATFORM=offscreen and the normal application dependencies.
No camera, microphone, network, credentials or user config is required.
"""
import os
import tempfile
import threading
import time
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QFileInfo, QPoint, QTimer, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QScrollArea, QSizeGrip, QSlider, QWidget  # noqa: E402

import memory.config_manager as config  # noqa: E402
from core.i18n import label as translate  # noqa: E402
from ui.window import JarvisUI, LogWidget, MainWindow  # noqa: E402
from ui.desktop_workspace import show_document  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        config.CONFIG_DIR = Path(tmp)
        config.CONFIG_FILE = Path(tmp) / "api_keys.json"
        MainWindow._check_config = lambda self: True
        app = QApplication([])
        chat = LogWidget()
        chat.resize(400, 220)
        chat.show()
        app.processEvents()
        chat._tag, chat._text, chat._pos = 'you', '<', 0
        chat._step()
        assert chat.toPlainText() == '<'
        assert chat.textCursor().blockFormat().alignment() == Qt.AlignmentFlag.AlignRight
        before = chat.textCursor().blockFormat().leftMargin()
        chat.selectAll()
        chat.resize(600, 220)
        app.processEvents()
        assert chat.toPlainText() == '<' and chat.textCursor().selectedText() == '<'
        assert chat.document().firstBlock().blockFormat().leftMargin() > before
        chat.close()
        # Real Qt navigation: back/forward, branch history, and a directory
        # removed after it was visited must not move the current location.
        from ui.desktop_workspace import FileBrowser
        browser = FileBrowser()
        assert browser.view.isColumnHidden(2)
        assert browser.view.header().visualIndex(3) < browser.view.header().visualIndex(1)
        assert browser.status.isHidden()
        assert not browser.navigate(str(Path(tmp) / 'missing'))
        assert not browser.status.isHidden()
        first, second, third = (Path(tmp) / name for name in ('first', 'second', 'third'))
        for folder in (first, second, third):
            folder.mkdir()
        assert not browser._icon_provider.icon(QFileInfo(str(first))).isNull()
        assert browser.navigate(str(tmp))
        # QFileSystemModel fills icons on its worker; wait for that real model,
        # not just the icon provider, while keeping the test bounded.
        for _ in range(30):
            if not browser.model.fileIcon(browser.model.index(str(first))).isNull():
                break
            QTest.qWait(100)
        else:
            raise AssertionError("folder icon was not populated by the filesystem model")
        assert browser.navigate(str(first)) and browser.status.isHidden()
        assert browser.navigate(str(second))
        assert browser.folder_title.text() == 'second' and browser.path.isHidden()
        browser._edit_path()
        assert not browser.path.isHidden() and browser.folder_title.isHidden()
        browser.path.setText(str(first))
        browser._accept_path()
        assert browser.path.isHidden() and browser.folder_title.text() == 'first'
        assert browser.navigate(str(second))
        browser._history_step(-1)
        assert Path(browser.path.text()) == first.resolve() and browser.forward.isEnabled()
        browser._history_step(1)
        assert Path(browser.path.text()) == second.resolve()
        browser._history_step(-1)
        assert browser.navigate(str(third)) and not browser.forward.isEnabled()
        third.rmdir()
        browser._history_step(-1)
        assert Path(browser.path.text()) == first.resolve()
        browser._history_step(1)
        assert Path(browser.path.text()) == first.resolve() and browser.forward.isEnabled()
        browser.close()
        window = MainWindow("")
        window.resize(1366, 768)
        window.show()
        window.move(0, 0)
        # Live language changes must not discard code/image editor state.
        from core.i18n import active_locale, set_locale
        from ui.creative import CreativeWorkspace
        from ui.image_editor import ImageEditor
        previous_locale = active_locale()
        window.get_plugins = lambda: [
            {"name": name, "valid": True, "enabled": True}
            for name in ("code_editor", "image_editor")]
        set_locale("en")
        creative = CreativeWorkspace(window, {"code": "print('unsaved')"})
        image = ImageEditor(window, {})
        # Real Qt checks for the editor gutter and syntax layout, not Qt stubs.
        assert creative._output.isHidden() and creative._output_heading.isHidden()
        assert creative._file_label.isHidden()
        assert creative._file_tabs.cornerWidget(Qt.Corner.TopRightCorner) is creative._new_tab_button
        before = creative._file_tabs.count()
        creative._new_tab_button.click()
        assert creative._file_tabs.count() == before + 1
        creative._close_file_tab(creative._file_tabs.currentIndex())
        assert creative._file_tabs.count() == before and creative._code.toPlainText() == "print('unsaved')"
        creative._output.setPlainText('Run output')
        assert not creative._output.isHidden() and not creative._output_heading.isHidden()
        assert creative._code.line_number_width() > 0
        creative._code.highlighter.set_language('python')
        creative._code.highlighter.rehighlight()
        assert creative._code.document().firstBlock().layout().formats()
        set_locale("id")
        creative.retranslate()
        image.retranslate()
        assert creative._code.toPlainText() == "print('unsaved')"
        assert creative._code.document().isModified()
        first_file = creative._code
        second_file = creative._add_code_tab('second file', dirty=True)
        assert creative._file_tabs.count() == 2 and creative._code is second_file
        creative._file_tabs.setCurrentIndex(0)
        assert creative._code is first_file and creative._code.toPlainText() == "print('unsaved')"
        second_file.document().setModified(False)
        creative._close_file_tab(1)
        assert creative._file_tabs.count() == 1
        assert image.windowTitle() == translate("image_editor.title")
        set_locale(previous_locale)
        # Don't close the unsaved editor via a confirmation dialog in smoke CI.
        creative._code.document().setModified(False)
        creative.close()
        image.close()
        QTest.qWait(300)
        app.processEvents()
        mdi = window._desktop_mdi
        dock = mdi._dock
        # Verify actual Qt geometry, not just the pure geometry calculation.
        from ui.desktop_workspace import initial_window_geometry
        expected_files, expected_assistant = initial_window_geometry(mdi.viewport().width(), mdi.viewport().height())
        for name, expected in (("files", expected_files), ("assistant", expected_assistant)):
            geometry = window._desktop_windows[name].geometry()
            actual = (geometry.x(), geometry.y(), geometry.width(), geometry.height())
            assert actual == expected, f"{name} actual={actual}, expected={expected}"
        from ui.theme import C
        assert C.DESKTOP_PANEL in window._workspace_file_browser.styleSheet()
        assert 'QMenu::item:selected' in window._workspace_file_browser.styleSheet()
        assert window._workspace_file_browser.view.header().sectionSize(0) >= 110
        assert dock.parentWidget() is mdi.viewport()
        assert 500 <= dock.width() <= mdi.viewport().width()
        assert all(button.isVisible() for button, _ in window._workspace_dock)
        for button, key in window._workspace_dock:
            assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
            assert button.accessibleName() == button.toolTip() == translate(key)
            assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus
        from ui.desktop_workspace import retranslate as retranslate_workspace
        set_locale("id")
        retranslate_workspace(window)
        assert all(button.accessibleName() == button.toolTip() == translate(key)
                   for button, key in window._workspace_dock)
        set_locale(previous_locale)
        retranslate_workspace(window)
        # The mockup's menu labels are functional controls, not decorative text.
        assert len(window._desktop_menus) == 5
        edit_button, edit_menu = window._desktop_menus['desktop.menu_edit']
        window.activateWindow()
        window._input.setText('edit menu test')
        window._input.setFocus()
        app.processEvents()
        assert QApplication.focusWidget() is window._input
        edit_debug = []
        def choose_select_all():
            edit_debug.append((repr(QApplication.focusWidget()), repr(window._desktop_focus_tracker.target),
                               edit_menu.actions()[-1].isEnabled(), QApplication.activePopupWidget() is edit_menu))
            edit_menu.actions()[-1].trigger()
            edit_menu.close()
        QTimer.singleShot(50, choose_select_all)
        QTimer.singleShot(500, edit_menu.close)
        QTest.mouseClick(edit_button, Qt.MouseButton.LeftButton)
        QTest.qWait(100)  # InstantPopup can return before its queued menu action.
        assert window._input.selectedText() == 'edit menu test', (edit_debug, repr(window._input))
        window._input.clear()
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
        assert window.hud.hud_style == "face"
        assert window.hud._avatar is not None
        assert mdi._avatar_stage.isVisible() and not mdi._emblem.isVisible()
        face_geometry = mdi._avatar_stage.geometry()
        files_geometry = window._desktop_windows["files"].geometry()
        assistant_geometry = window._desktop_windows["assistant"].geometry()
        assert files_geometry.right() < face_geometry.left()
        assert face_geometry.right() < assistant_geometry.left()
        assert face_geometry.bottom() < dock.geometry().top()
        assert window._hud_cam_stack.isHidden() and window._center_split.isHidden()
        assert window._suggestions_card.isVisible()
        assert all(button.isVisible() for button, _ in window._suggestion_buttons)
        window._show_content('Test', 'Auxiliary result')
        app.processEvents()
        assert window._center_split.isVisible() and window._content_panel.isVisible()
        window._content_panel.hide()
        from ui.desktop_layout import refresh_assistant_tools
        refresh_assistant_tools(window)
        assert window._center_split.isHidden()
        window._show_audio_bar()
        app.processEvents()
        assert window._center_split.isVisible() and window._audio_cont.isVisible()
        window._audio_cont.hide()
        refresh_assistant_tools(window)
        assert window._center_split.isHidden()
        assert not window.grab().isNull()  # paints the actual animated face
        window.hud.hud_style = "orb"
        mdi.position_emblem()
        assert not mdi._avatar_stage.isVisible() and mdi._emblem.isVisible()
        assert not window._hud_cam_stack.isHidden() and not window._center_split.isHidden()
        window.hud.hud_style = "face"
        mdi.position_emblem()
        assert window._hud_cam_stack.isHidden() and window._center_split.isHidden()
        files_for_clap = window._desktop_windows["files"]
        assistant_for_clap = window._desktop_windows["assistant"]
        mdi.minimize_for_clap()
        assert files_for_clap.isMinimized() and assistant_for_clap.isMinimized()
        restore_action = next(action for action, key in window._workspace_dock_actions
                              if key == "workspace.restore_clap")
        restore_action.trigger()
        assert not files_for_clap.isMinimized() and not assistant_for_clap.isMinimized()
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
            gestures.pending = (gestures.pending[0], gestures.pending[1] - 1, *gestures.pending[2:])
            gestures.update(samples)
        # Claw manipulation is limited to the active multi-part model canvas.
        model_sub = window._open_model_viewer()
        model_sub.showNormal()
        mdi.setActiveSubWindow(model_sub)
        app.processEvents()
        viewer = window._model_viewer
        viewer.explode_slider.setEnabled(True)
        claw_point = viewer.canvas.mapTo(viewport, viewer.canvas.rect().center())
        claw = lambda p: (p.x() / (viewport.width() - 1), p.y() / (viewport.height() - 1),
                          False, False, True)
        gestures.update((claw(claw_point),))
        assert gestures.claw_pending is not None
        gestures.claw_pending = (gestures.claw_pending[0] - 1, gestures.claw_pending[1])
        gestures.update((claw(claw_point),))
        assert gestures.mode == 'claw'
        gestures.update((claw(claw_point - QPoint(0, 30)),))
        assert viewer.explode_slider.value() > 0
        gestures.update(())
        assert gestures.mode is None
        model_sub.hide()
        mdi.setActiveSubWindow(files)
        files.raise_()
        app.processEvents()
        # A dwell must restart when the pointer changes target or moves too far.
        original_hit = gestures._hit
        first, second = QPushButton(window), QPushButton(window)
        gestures._hit = lambda point: first if point.x() < 150 else second
        gestures.reset()
        gestures.update((sample(QPoint(100, 100)),))
        gestures.pending = (gestures.pending[0], gestures.pending[1] - 1, *gestures.pending[2:])
        gestures.update((sample(QPoint(160, 100)),))
        assert gestures.mode is None and gestures.pending[2][0] is second
        gestures.pending = (gestures.pending[0], gestures.pending[1] - 1, *gestures.pending[2:])
        gestures.update((sample(QPoint(190, 100)),))
        assert gestures.mode is None  # same widget, but exceeded the dwell radius
        gestures.reset()
        # A closed hand plus another visible open hand must not arm a click.
        open_hand = (0.3, 0.3, False, False)
        gestures.update((sample(QPoint(100, 100)), open_hand))
        assert gestures.mode is None and gestures.pending is None
        gestures.reset()
        gestures._hit = original_hit
        first.deleteLater()
        second.deleteLater()
        anchor = files._workspace_title.mapTo(viewport, QPoint(160, 15))
        before = files.pos()
        begin((sample(anchor),))
        assert gestures.mode == "move"
        gestures.update((sample(anchor + QPoint(35, 20)),))
        assert files.pos() != before
        gestures.update(())  # loss of tracking releases the target
        assert gestures.mode is None
        # A deliberate, recent fast title drag throws only the active window.
        anchor = files._workspace_title.mapTo(viewport, QPoint(160, 15))
        begin((sample(anchor),))
        before_flick = files.pos()
        now = time.monotonic()
        gestures.flick.points = [(now - .1, 100, 100), (now, 200, 100)]
        gestures.update(((anchor.x() / (viewport.width() - 1),
                          anchor.y() / (viewport.height() - 1), False, False),))
        assert files.x() > before_flick.x()
        center = files.mapTo(viewport, QPoint(files.width() // 2, 100))
        left, right = center - QPoint(80, 0), center + QPoint(80, 0)
        before_size = files.size()
        begin((sample(left), sample(right)))
        assert gestures.mode == "resize"
        before_position = files.pos()
        gestures.update((sample(left + QPoint(20, 10)), sample(right + QPoint(20, 10))))
        assert files.pos() != before_position  # two pinches translate the same JARVIS window
        assert files.size() == before_size
        gestures.update((sample(left - QPoint(40, 0)), sample(right + QPoint(40, 0))))
        assert files.width() > before_size.width()
        # Real Qt visual feedback driven by synthetic controller data, not a camera.
        controller = window._hand_controller
        original_sample = controller.sample
        controller.thread = SimpleNamespace(is_alive=lambda: True)
        controller._stop.clear()
        controller.status = 'active'
        controller.sample = lambda: (sample(left - QPoint(40, 0)), sample(right + QPoint(40, 0)))
        window._hand_refresh()
        assert window._hand_visual_panel.isVisible()
        assert gestures.link.isVisible()
        assert window._hand_visual_mode.text() == translate('gesture.mode_transform')
        window._hand_closing_confirm = True
        window._hand_refresh()
        assert not window._hand_visual_panel.isVisible() and not gestures.link.isVisible()
        window._hand_closing_confirm = False
        controller.sample = lambda: ()
        window._hand_refresh()
        assert window._hand_visual_panel.isVisible()
        QTest.mouseClick(window._hand_visual_stop, Qt.MouseButton.LeftButton)
        assert controller._stop.is_set() and not window._hand_visual_panel.isVisible()
        controller.sample = original_sample
        controller.thread = None
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

        assert command({"action": "open", "target": "model_viewer"})["ok"]
        assert window._hand_controller.thread is None  # opening must not start a camera
        model = window._model_viewer
        obj_path = Path(tmp) / "parts.obj"
        obj_path.write_text("v -2 0 0\nv -1 0 0\nv -1 1 0\nv 1 0 0\nv 2 0 0\nv 1 1 0\nf 1 2 3\nf 4 5 6\n", encoding="utf-8")
        assert model.load_file(str(obj_path)) and model.canvas.parts == 2
        assert model.explode_slider.isEnabled()
        model.explode_slider.setValue(60)
        assert model.canvas.explode == .6
        assert not model.load_file(str(Path(tmp) / "missing.obj"))
        assert model.canvas.parts == 2  # failed load leaves the existing model intact
        assert not window.grab().isNull()

        # A confirmed pinch release clicks an internal Qt control; tracking
        # loss and safety confirmation must never generate that click.
        window._hand_timer.stop()
        board_sub = files
        board = files.widget()
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
        mdi.setActiveSubWindow(board_sub)
        board_sub.raise_()
        mdi.position_dock()
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
        mdi.setActiveSubWindow(board_sub)
        board_sub.raise_()
        app.processEvents()

        # Plugin discovery can finish on a worker; its signal must create only
        # one real editor on the Qt thread, below the initial Files geometry.
        from ui.desktop_workspace import open_initial_editor
        window.get_plugins = lambda: [{"name": "code_editor", "valid": True, "enabled": True}]
        # Close test documents first, without affecting the original smoke tests.
        for kind, existing in tuple(window._workspace_documents.values()):
            if kind == "code_editor":
                existing.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        open_initial_editor(window)
        editors = [sub for kind, sub in window._workspace_documents.values() if kind == "code_editor"]
        assert len(editors) == 1
        editor_sub = editors[0]
        initial_files, _ = initial_window_geometry(mdi.viewport().width(), mdi.viewport().height())
        assert editor_sub.x() == initial_files[0]
        assert editor_sub.y() == initial_files[1] + initial_files[3] + 18
        assert editor_sub.width() == initial_files[2]
        assert editor_sub.y() + editor_sub.height() <= mdi.viewport().height() - 90
        editor_sub._document._code.setPlainText("unsaved")
        editor_sub._document._code.document().setModified(True)
        open_initial_editor(window)
        assert editor_sub._document._code.toPlainText() == "unsaved"
        editor_sub._document._code.document().setModified(False)
        editor_sub.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        open_initial_editor(window)
        assert not any(kind == "code_editor" for kind, _ in window._workspace_documents.values())

        window._hand_timer.start()
        print("Real Qt desktop, workspace and local OBJ viewer passed.")


if __name__ == "__main__":
    main()
