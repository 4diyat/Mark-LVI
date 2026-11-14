"""Qt-thread controls and menus for the experimental desktop hand pointer."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QPushButton

from core.hand_gesture import HandController, normalize_settings
from core.i18n import label as _t


def setup(window):
    from memory.config_manager import load_api_keys

    def capture_and_request():
        # This runs on the camera worker: capture before Qt's popup changes focus.
        from core.gesture_actions import WindowsActions
        target = WindowsActions().capture()
        window._hand_menu_sig.emit(target)

    controller = HandController(on_menu=capture_and_request)
    window._hand_controller = controller
    window._hand_menu = None
    window._hand_closing_confirm = False
    button = QPushButton(_t("gesture.enable"))
    settings_button = QPushButton(_t("gesture.settings"))
    button.setToolTip(_t("gesture.help"))
    settings_button.setToolTip(_t("gesture.settings_hint"))
    status = QLabel(_t("gesture.off"))
    status.setWordWrap(True)
    window._assistant_panel.layout().addWidget(status)
    window._assistant_panel.layout().addWidget(button)
    window._assistant_panel.layout().addWidget(settings_button)

    def toggle():
        if controller.thread and controller.thread.is_alive():
            controller.stop()
            refresh()
            return
        banner = getattr(window, "_confirm_overlay", None)
        if (banner is not None and banner.isVisible()) or window._hand_closing_confirm:
            status.setText(_t("gesture.confirm_busy"))
            return
        config = load_api_keys()
        try:
            index = int(config.get("camera_index", 0))
        except (ValueError, TypeError):
            index = 0
        controller.start(index, config.get("hand_gesture"))
        refresh()

    def refresh():
        key = {"off": "gesture.off", "starting": "gesture.starting", "active": "gesture.active",
               "camera_busy": "gesture.busy", "error": "gesture.error", "windows_only": "gesture.windows_only"}.get(controller.status, "gesture.off")
        if controller.thread and controller.thread.is_alive() and controller._stop.is_set() and controller.status != "error":
            key = "gesture.stopping"
        message = _t(key)
        if controller.status == "error" and controller.error:
            message += " " + controller.error
        if key == "gesture.active" and controller._engine is not None:
            message += "\n" + _t("gesture.pose_" + controller._engine.gesture)
        status.setText(message)
        running = controller.thread and controller.thread.is_alive() and not controller._stop.is_set()
        button.setText(_t("gesture.disable" if running else "gesture.enable"))
        button.setEnabled(not (controller.thread and controller.thread.is_alive() and controller._stop.is_set()))

    def settings_menu():
        from memory.config_manager import set_config_values
        settings = normalize_settings(load_api_keys().get("hand_gesture"))
        menu = QMenu(window)
        actions = {}
        for key, caption, choices in (
            ("pinch_ms", "gesture.setting_pinch", ((350, "gesture.ms_350"), (500, "gesture.ms_500"), (700, "gesture.ms_700"))),
            ("movement_range", "gesture.setting_range", ((0, "gesture.range_full"), (10, "gesture.range_medium"), (20, "gesture.range_small"))),
            ("three_finger", "gesture.setting_three", (("switch", "gesture.action_switch"), ("task_view", "gesture.action_task_view"), ("none", "gesture.action_none"))),
        ):
            sub = menu.addMenu(_t(caption))
            for value, label in choices:
                action = sub.addAction(_t(label))
                action.setCheckable(True)
                action.setChecked(settings[key] == value)
                actions[action] = (key, value)
        chosen = menu.exec(QCursor.pos())
        if chosen in actions:
            key, value = actions[chosen]
            settings[key] = value
            ok = set_config_values(hand_gesture=settings)
            window._log.append_log(_t("gesture.settings_saved" if ok else "gesture.settings_failed"))

    def open_menu(target):
        if controller._stop.is_set() or controller.status != "active" or window._hand_menu is not None:
            return
        menu = QMenu(window)
        window._hand_menu = menu
        choices = {}
        for key in ("switch", "task_view", "desktop", "start", "minimize", "maximize",
                    "volume_up", "volume_down", "volume_mute", "media_play", "close"):
            action = menu.addAction(_t("gesture.action_" + key))
            if key in ("switch", "minimize", "maximize", "close"):
                action.setEnabled(target is not None)
            choices[action] = key
        try:
            selected = menu.exec(QCursor.pos())
        finally:
            window._hand_menu = None
        command = choices.get(selected)
        if command is None or controller._stop.is_set():
            return
        from core.gesture_actions import WindowsActions, close_with_confirmation
        try:
            backend = WindowsActions()
            if command == "close":
                def confirm(close_target):
                    from PyQt6.QtWidgets import QMessageBox
                    window._hand_closing_confirm = True
                    try:
                        dialog = QMessageBox(window)
                        dialog.setWindowTitle(_t("gesture.close_title"))
                        dialog.setTextFormat(Qt.TextFormat.PlainText)
                        dialog.setText(_t("gesture.close_detail").format(title=close_target.title))
                        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                        dialog.setDefaultButton(QMessageBox.StandardButton.No)
                        answer = dialog.exec()
                        banner = getattr(window, "_confirm_overlay", None)
                        return (answer == QMessageBox.StandardButton.Yes and
                                not (banner is not None and banner.isVisible()))
                    finally:
                        window._hand_closing_confirm = False
                result = close_with_confirmation(controller, backend, target, confirm)
                if result == "invalid":
                    window._log.append_log(_t("gesture.action_failed"))
            elif not backend.run(command, target):
                window._log.append_log(_t("gesture.action_failed"))
        except Exception as exc:
            window._log.append_log(_t("gesture.action_error").format(error=str(exc)))

    button.clicked.connect(toggle)
    settings_button.clicked.connect(settings_menu)
    window._hand_menu_sig.connect(open_menu)
    timer = QTimer(window)
    timer.timeout.connect(refresh)
    timer.start(300)
    window._hand_timer = timer
    window._hand_refresh = refresh
    QApplication.instance().aboutToQuit.connect(controller.stop)
