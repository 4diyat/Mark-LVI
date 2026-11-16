"""Opt-in two-hand tracking, restricted to internal JARVIS window geometry."""
import math
import time

from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtWidgets import QAbstractButton, QAbstractScrollArea, QApplication, QComboBox, QLabel, QMdiSubWindow, QPushButton, QSlider

from core.i18n import label as _t
from core.workspace_gesture import WorkspaceHandController
from ui.desktop_workspace import WindowTitleBar


class WorkspaceGestures:
    """Manipulate only widgets in the workspace; no global mouse/key injection."""
    def __init__(self, window):
        self.window = window
        self.mode = self.target = self.origin = self.pending = None
        self.scroll_origin = None
        self.popup_pending = None
        self.popup_owner = None
        self.cursors = []
        for _ in range(2):
            cursor = QLabel(window.centralWidget())
            cursor.setFixedSize(20, 20)
            cursor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            cursor.setStyleSheet("background: rgba(50, 200, 255, 80); border: 2px solid #86eaff; border-radius: 10px;")
            cursor.hide()
            self.cursors.append(cursor)

    def reset(self):
        self.mode = self.target = self.origin = self.pending = None
        self.scroll_origin = None
        self.popup_pending = None
        self.popup_owner = None

    def show_cursors(self, samples):
        viewport = self.window._desktop_mdi.viewport()
        for i, cursor in enumerate(self.cursors):
            if i >= len(samples):
                cursor.hide()
                continue
            x, y = samples[i][:2]
            point = QPoint(int(x * max(0, viewport.width() - 1)),
                           int(y * max(0, viewport.height() - 1)))
            point = viewport.mapTo(self.window.centralWidget(), point)
            cursor.move(point.x() - 10, point.y() - 10)
            cursor.show()
            cursor.raise_()

    def _allowed_overlays(self):
        # Only known configuration panels; confirmation banners and unknown
        # overlays never inherit gesture access automatically.
        names = ('_customize_overlay', '_plugin_manager_overlay', '_plugin_settings_overlay',
                 '_audio_overlay', '_providers_overlay')
        return [getattr(self.window, name, None) for name in names]

    def _is_allowed_widget(self, widget):
        if widget is None:
            return False
        viewport = self.window._desktop_mdi.viewport()
        if widget is viewport or viewport.isAncestorOf(widget):
            return True
        for overlay in self._allowed_overlays():
            if overlay is not None and overlay.isVisible() and (widget is overlay or overlay.isAncestorOf(widget)):
                return True
        return False

    def _hit(self, point):
        """Reject points obscured by an unapproved app-owned overlay."""
        viewport = self.window._desktop_mdi.viewport()
        top = self.window.childAt(viewport.mapTo(self.window, point))
        return top if self._is_allowed_widget(top) else None

    def _card_at(self, point):
        from ui.hand_board import Card
        board = getattr(self.window, '_hand_board', None)
        if board is None or not board.isVisible():
            return None
        viewport = self.window._desktop_mdi.viewport()
        view = board.view
        hit = self._hit(point)
        if hit is not view.viewport() and not view.viewport().isAncestorOf(hit):
            return None
        local = view.viewport().mapFrom(viewport, point)
        if not view.viewport().rect().contains(local):
            return None
        scene_point = view.mapToScene(local)
        item = view.scene().itemAt(scene_point, view.transform())
        while item is not None and not isinstance(item, Card):
            item = item.parentItem()
        return (board, item, scene_point) if item in board._items else None

    def _click(self, point):
        """Click the widget under a confirmed release, never a system window."""
        from PyQt6.QtCore import QCoreApplication, QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent
        viewport = self.window._desktop_mdi.viewport()
        widget = self._hit(point)
        if widget is not self.target or not widget.isEnabled():
            return
        global_pos = viewport.mapToGlobal(point)
        local = widget.mapFromGlobal(global_pos)
        # Send directly to this child widget; the system pointer is never moved.
        for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                              (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            try:
                event = QMouseEvent(kind, QPointF(local), QPointF(global_pos),
                                    Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
                QCoreApplication.sendEvent(widget, event)
            except RuntimeError:  # widget was deleted by its press handler
                break

    def _scroll(self, point):
        from PyQt6.QtCore import QCoreApplication, QPointF
        from PyQt6.QtGui import QWheelEvent
        viewport = self.window._desktop_mdi.viewport()
        if self.scroll_origin is None:
            self.scroll_origin = point
            return
        delta = point.y() - self.scroll_origin.y()
        if abs(delta) < 25:
            return
        widget = self._hit(point)
        current = widget
        while current is not None and current is not viewport:
            if isinstance(current, QAbstractScrollArea):
                widget = current.viewport()
                break
            current = current.parentWidget()
        if widget is not None:
            local = widget.mapFromGlobal(viewport.mapToGlobal(point))
            event = QWheelEvent(QPointF(local), QPointF(viewport.mapToGlobal(point)), QPoint(),
                                QPoint(0, 120 if delta < 0 else -120), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QCoreApplication.sendEvent(widget, event)
        self.scroll_origin = point

    def _dock_popup(self, popup, samples):
        """Allow only our dock menus, and only inside the application bounds."""
        viewport = self.window._desktop_mdi.viewport()
        if not any(button.menu() is popup for button, _ in self.window._workspace_dock):
            self.reset()
            self.show_cursors(())
            return
        self.mode = self.target = self.origin = self.pending = None
        self.show_cursors(samples)
        if len(samples) != 1:
            self.popup_pending = None
            return
        sample = samples[0]
        point = QPoint(int(sample[0] * max(0, viewport.width() - 1)),
                       int(sample[1] * max(0, viewport.height() - 1)))
        local = popup.mapFromGlobal(viewport.mapToGlobal(point))
        action = popup.actionAt(local) if popup.rect().contains(local) else None
        if sample[2]:
            if action is None or not action.isEnabled():
                self.popup_pending = None
            elif not self.popup_pending or self.popup_pending[0] is not action:
                self.popup_pending = (action, time.monotonic())
        else:
            pending = self.popup_pending
            self.popup_pending = None
            if pending and action is pending[0] and time.monotonic() - pending[1] >= .35:
                popup.close()
                action.trigger()

    def _combo_popup(self, popup, samples):
        """Select enabled rows only in a combo owned by an allowed app widget."""
        viewport = self.window._desktop_mdi.viewport()
        owner = next((combo for combo in self.window.findChildren(QComboBox)
                      if self._is_allowed_widget(combo) and combo.isVisible()
                      and combo.isEnabled() and combo.view().window() is popup), None)
        if owner is None:
            return False
        self.mode = self.target = self.origin = self.pending = None
        self.show_cursors(samples)
        if len(samples) != 1:
            self.popup_pending = None
            return True
        sample = samples[0]
        p = QPoint(int(sample[0] * max(0, viewport.width() - 1)),
                   int(sample[1] * max(0, viewport.height() - 1)))
        view = owner.view()
        local = view.viewport().mapFromGlobal(viewport.mapToGlobal(p))
        index = view.indexAt(local) if view.viewport().rect().contains(local) else None
        enabled = index is not None and index.isValid() and bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        if sample[2]:
            if not enabled:
                self.popup_pending = None
            elif not self.popup_pending or self.popup_pending[0] != index:
                self.popup_pending = (index, time.monotonic())
        else:
            pending = self.popup_pending
            self.popup_pending = None
            if enabled and pending and pending[0] == index and time.monotonic() - pending[1] >= .35:
                row = index.row()
                owner.hidePopup()
                owner.setCurrentIndex(row)
                owner.activated.emit(row)
                owner.textActivated.emit(owner.itemText(row))
        return True

    def update(self, samples):
        window = self.window
        mdi = window._desktop_mdi
        viewport = mdi.viewport()
        banner = getattr(window, '_confirm_overlay', None)
        popup = QApplication.activePopupWidget()
        if (QApplication.activeModalWidget() is not None
                or getattr(window, '_hand_closing_confirm', False)
                or (banner is not None and banner.isVisible())):
            self.reset()
            self.show_cursors(())
            return
        if popup is not None:
            if popup is not self.popup_owner:
                self.popup_pending = None
                self.popup_owner = popup
            if not self._combo_popup(popup, samples):
                self._dock_popup(popup, samples)
            return
        if not window.isActiveWindow():
            self.reset()
            self.show_cursors(())
            return
        self.popup_pending = None
        self.popup_owner = None
        self.show_cursors(samples)
        coords_all = [QPoint(int(s[0] * max(0, viewport.width() - 1)),
                             int(s[1] * max(0, viewport.height() - 1))) for s in samples]
        hands = sorted((s for s in samples if s[2]), key=lambda s: s[0])
        if not hands:
            # A visible, open hand is an intentional release. Tracking loss,
            # a second hand, focus loss and modal dialogs always cancel clicks.
            if self.mode == 'click' and len(samples) == 1 and len(coords_all) == 1:
                p = coords_all[0]
                if (p - self.origin[0]).manhattanLength() <= 25:
                    self._click(p)
            if len(samples) == 1 and len(samples[0]) > 3 and samples[0][3]:
                self.mode = self.target = self.origin = self.pending = None
                self._scroll(coords_all[0])
            else:
                self.reset()
            return
        self.scroll_origin = None
        if len(hands) > 2:
            self.reset()
            return
        coords = [QPoint(int(s[0] * max(0, viewport.width() - 1)),
                         int(s[1] * max(0, viewport.height() - 1))) for s in hands]
        count = len(coords)
        if any(self._hit(p) is None for p in coords):
            self.reset()
            return
        if self.mode is None or (self.mode in ('move', 'click', 'card_move', 'slider')) != (count == 1):
            self.mode = self.target = self.origin = None
            if not self.pending or self.pending[0] != count:
                self.pending = (count, time.monotonic())
                return
            if time.monotonic() - self.pending[1] < .35:
                return
            p = coords[0] if count == 1 else (coords[0] + coords[1]) / 2
            card = self._card_at(p)
            if card is not None:
                board, item, scene_point = card
                self.pending = None
                self.target = (board, item)
                self.mode = 'card_move' if count == 1 else 'card_transform'
                if count == 1:
                    self.origin = (scene_point, item.pos())
                else:
                    view = item.model_view
                    self.origin = (coords, item.scale(), item.rotation(),
                                   (view.yaw, view.pitch) if view is not None else None)
                board.scene.clearSelection()
                item.setSelected(True)
                return
            widget = self._hit(p)
            hit = widget
            title = None
            while widget is not None and widget is not viewport:
                if isinstance(widget, WindowTitleBar):
                    title = widget
                if isinstance(widget, QMdiSubWindow):
                    break
                widget = widget.parentWidget()
            if count == 1:
                is_title = title is not None
                if isinstance(widget, QMdiSubWindow) and not is_title:
                    content = widget.widget()
                    local = widget.mapFrom(viewport, p)
                    is_title = content is not None and 0 <= local.y() < content.y()
                if is_title and not isinstance(hit, QAbstractButton) and isinstance(widget, QMdiSubWindow) and not widget.isMaximized():
                    self.target, self.mode = widget, 'move'
                    self.origin = (coords, widget.geometry())
                    mdi.setActiveSubWindow(widget)
                elif isinstance(hit, QSlider) and hit.isEnabled():
                    self.target, self.mode = hit, 'slider'
                    self.origin = (p, hit.value())
                elif hit is not None and hit is not viewport:
                    self.target, self.mode = hit, 'click'
                    self.origin = (p,)
                else:
                    self.reset()
                    return
            elif isinstance(widget, QMdiSubWindow) and not widget.isMaximized():
                self.target, self.mode = widget, 'resize'
                self.origin = (coords, widget.geometry())
                mdi.setActiveSubWindow(widget)
            else:
                self.reset()
                return
            self.pending = None
            return
        if self.mode == 'click':
            return
        if self.mode == 'slider':
            try:
                slider = self.target
                start, value = self.origin
                horizontal = slider.orientation() == Qt.Orientation.Horizontal
                distance = coords[0].x() - start.x() if horizontal else start.y() - coords[0].y()
                if slider.invertedAppearance():
                    distance = -distance
                span = max(1, slider.width() if horizontal else slider.height())
                slider.setValue(value + round(distance * (slider.maximum() - slider.minimum()) / span))
            except RuntimeError:
                self.reset()
            return
        if self.mode.startswith('card_'):
            board, item = self.target
            if item not in board._items or not board.isVisible():
                self.reset()
                return
            if self.mode == 'card_move':
                local = board.view.viewport().mapFrom(viewport, coords[0])
                item.setPos(self.origin[1] + board.view.mapToScene(local) - self.origin[0])
            else:
                initial, scale, angle, view_angles = self.origin
                old = math.hypot(initial[1].x() - initial[0].x(), initial[1].y() - initial[0].y())
                new = math.hypot(coords[1].x() - coords[0].x(), coords[1].y() - coords[0].y())
                if old >= 40:
                    initial_angle = math.atan2(initial[1].y() - initial[0].y(), initial[1].x() - initial[0].x())
                    new_angle = math.atan2(coords[1].y() - coords[0].y(), coords[1].x() - coords[0].x())
                    item.setScale(max(.35, min(2.5, scale * new / old)))
                    item.setRotation(angle + math.degrees(new_angle - initial_angle))
                    if view_angles is not None:
                        initial_center = (initial[0] + initial[1]) / 2
                        current_center = (coords[0] + coords[1]) / 2
                        delta = current_center - initial_center
                        item.model_view.set_view(view_angles[0] + delta.x() * .4,
                                                 view_angles[1] + delta.y() * .4)
            return
        try:
            available = self.target and self.target.isVisible() and not self.target.isMaximized()
        except RuntimeError:
            available = False
        if not available:
            self.reset()
            return
        initial, geom = self.origin
        if self.mode == 'move':
            delta = coords[0] - initial[0]
            x = max(0, min(viewport.width() - 40, geom.x() + delta.x()))
            y = max(0, min(viewport.height() - 33, geom.y() + delta.y()))
            self.target.move(x, y)
        else:
            old = math.hypot(initial[1].x() - initial[0].x(), initial[1].y() - initial[0].y())
            new = math.hypot(coords[1].x() - coords[0].x(), coords[1].y() - coords[0].y())
            if old < 40:
                return
            scale = max(.5, min(2., new / old))
            width = max(self.target.minimumWidth(), min(viewport.width() - geom.x(), round(geom.width() * scale)))
            height = max(self.target.minimumHeight(), min(viewport.height() - geom.y(), round(geom.height() * scale)))
            self.target.resize(width, height)


def setup(window):
    from memory.config_manager import load_api_keys
    controller = WorkspaceHandController()
    gestures = WorkspaceGestures(window)
    window._hand_controller = controller
    window._hand_closing_confirm = False
    window._hand_menu = None
    button = QPushButton(_t('gesture.enable'))
    button.setToolTip(_t('gesture.workspace_help'))
    status = QLabel(_t('gesture.off'))
    status.setWordWrap(True)
    window._left_panel.layout().addWidget(status)
    window._left_panel.layout().addWidget(button)

    def refresh():
        key = {'off': 'gesture.off', 'starting': 'gesture.starting', 'active': 'gesture.workspace_active',
               'camera_busy': 'gesture.busy', 'error': 'gesture.error', 'windows_only': 'gesture.windows_only'}.get(controller.status, 'gesture.off')
        running = bool(controller.thread and controller.thread.is_alive() and not controller._stop.is_set())
        if controller.thread and controller.thread.is_alive() and controller._stop.is_set() and controller.status != 'error':
            key = 'gesture.stopping'
        message = _t(key)
        if controller.status == 'error' and controller.error:
            message += ' ' + controller.error
        status.setText(message)
        button.setText(_t('gesture.disable' if running else 'gesture.enable'))
        button.setEnabled(not (controller.thread and controller.thread.is_alive() and controller._stop.is_set()))
        gestures.update(controller.sample() if running else ())

    def toggle():
        if controller.thread and controller.thread.is_alive():
            controller.stop()
            gestures.reset()
        elif not getattr(window, '_hand_closing_confirm', False):
            banner = getattr(window, '_confirm_overlay', None)
            if banner is not None and banner.isVisible():
                status.setText(_t('gesture.confirm_busy'))
                return
            try:
                index = int(load_api_keys().get('camera_index', 0))
            except (ValueError, TypeError):
                index = 0
            controller.start(index)
        refresh()

    window._hand_toggle = toggle
    window._hand_status = status
    window._workspace_gestures = gestures
    button.clicked.connect(toggle)
    timer = QTimer(window)
    timer.timeout.connect(refresh)
    timer.start(40)
    window._hand_timer = timer
    window._hand_refresh = refresh
    QApplication.instance().aboutToQuit.connect(controller.stop)
