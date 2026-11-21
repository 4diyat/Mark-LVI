"""Opt-in two-hand tracking, restricted to internal JARVIS window geometry."""
import time

from PyQt6.QtCore import QPoint, QPointF, QTimer, Qt
from PyQt6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QApplication, QComboBox, QHBoxLayout,
                             QLabel, QMdiSubWindow, QPushButton, QSlider, QVBoxLayout, QWidget)

from core.i18n import label as _t
from core.workspace_gesture import ClapTracker, WorkspaceHandController, dwell_matches
from core.workspace_transform import FlickTracker, bounded_flick, transform_window
from ui.desktop_workspace import WindowTitleBar


class GestureLink(QWidget):
    """Non-interactive visual link; never generates input or claims tracking."""
    def __init__(self, viewport):
        super().__init__(viewport)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.points = ()
        self.hide()

    def set_samples(self, samples, enabled):
        self.points = tuple((s[0], s[1]) for s in samples) if enabled and len(samples) == 2 else ()
        self.setVisible(bool(self.points))
        if self.points:
            parent = self.parentWidget()
            self.setGeometry(0, 0, parent.width(), parent.height())
            self.raise_()
            self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QPainter, QPen
        del event
        if len(self.points) != 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor('#65dff5'))
        pen.setWidthF(1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        a, b = self.points
        painter.drawLine(QPointF(a[0] * max(0, self.width() - 1), a[1] * max(0, self.height() - 1)),
                         QPointF(b[0] * max(0, self.width() - 1), b[1] * max(0, self.height() - 1)))
        painter.end()


def build_status_panel(window):
    """Small local camera indicator and physical or gesture-accessible stop."""
    panel = QWidget(window._desktop_mdi.viewport())
    panel.setObjectName('HandStatusPanel')
    panel.setStyleSheet("""
        QWidget#HandStatusPanel { background: #142536; border: 1px solid #3b6176; border-radius: 12px; }
        QLabel { color: #d8edf6; background: transparent; border: none; }
        QPushButton { background: #233b4f; color: #effbff; border: 1px solid #5799ad;
                      border-radius: 7px; padding: 5px 10px; }
        QPushButton:hover, QPushButton:focus { background: #31536a; border-color: #85e6f4; }
    """)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(3)
    heading = QLabel()
    heading.setAccessibleName(_t('gesture.badge_accessible'))
    layout.addWidget(heading)
    row = QHBoxLayout()
    mode = QLabel()
    mode.setWordWrap(True)
    row.addWidget(mode, 1)
    stop = QPushButton()
    stop.setAccessibleName(_t('gesture.visual_stop'))
    row.addWidget(stop)
    layout.addLayout(row)
    panel.hide()
    return panel, heading, mode, stop


class WorkspaceGestures:
    """Manipulate only widgets in the workspace; no global mouse/key injection."""
    def __init__(self, window):
        self.window = window
        self.mode = self.target = self.origin = self.pending = None
        self.scroll_origin = None
        self.popup_pending = None
        self.popup_owner = None
        self.flick = FlickTracker()
        self.clap = ClapTracker()
        self.claw_pending = None
        self.link = GestureLink(window._desktop_mdi.viewport())
        self.cursors = []
        for _ in range(2):
            cursor = QLabel(window.centralWidget())
            cursor.setFixedSize(42, 42)
            cursor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            cursor.setStyleSheet("background: rgba(20, 92, 120, 45); border: 2px solid #86eaff; border-radius: 21px;")
            cursor.hide()
            self.cursors.append(cursor)

    def reset(self):
        self.mode = self.target = self.origin = self.pending = None
        self.scroll_origin = None
        self.popup_pending = None
        self.popup_owner = None
        self.flick.points.clear()
        self.claw_pending = None

    def show_cursors(self, samples):
        viewport = self.window._desktop_mdi.viewport()
        for i, cursor in enumerate(self.cursors):
            if i >= len(samples):
                cursor.hide()
                continue
            x, y = samples[i][:2]
            pinched = bool(samples[i][2])
            cursor.setStyleSheet("background: rgba(20, 150, 180, 95); border: 3px solid #9afaff; border-radius: 21px;"
                                 if pinched else
                                 "background: rgba(20, 92, 120, 45); border: 2px solid #86eaff; border-radius: 21px;")
            point = QPoint(round(x * max(0, viewport.width() - 1)),
                           round(y * max(0, viewport.height() - 1)))
            point = viewport.mapTo(self.window.centralWidget(), point)
            cursor.move(point.x() - 21, point.y() - 21)
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
        point = QPoint(round(sample[0] * max(0, viewport.width() - 1)),
                       round(sample[1] * max(0, viewport.height() - 1)))
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
        p = QPoint(round(sample[0] * max(0, viewport.width() - 1)),
                   round(sample[1] * max(0, viewport.height() - 1)))
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
            self.clap.reset()
            self.show_cursors(())
            return
        if popup is not None:
            self.clap.reset()
            if any(len(s) > 4 and s[4] for s in samples):
                self.reset()
                self.show_cursors(())
                return
            if popup is not self.popup_owner:
                self.popup_pending = None
                self.popup_owner = popup
            if not self._combo_popup(popup, samples):
                self._dock_popup(popup, samples)
            return
        if not window.isActiveWindow():
            self.clap.reset()
            self.reset()
            self.show_cursors(())
            return
        self.popup_pending = None
        self.popup_owner = None
        self.show_cursors(samples)
        # Never trigger while manipulating a target or through an overlay.
        if self.mode is not None or any(self._hit(QPoint(
                round(s[0] * max(0, viewport.width() - 1)),
                round(s[1] * max(0, viewport.height() - 1)))) is None for s in samples):
            self.clap.reset()
        elif self.clap.update(samples, time.monotonic()):
            self.reset()
            mdi.minimize_for_clap()
            return
        coords_all = [QPoint(round(s[0] * max(0, viewport.width() - 1)),
                             round(s[1] * max(0, viewport.height() - 1))) for s in samples]
        claw = len(samples) == 1 and len(samples[0]) > 4 and samples[0][4]
        if claw:
            self.clap.reset()
            viewer = getattr(window, '_model_viewer', None)
            sub = window._desktop_windows.get('model_viewer')
            point = coords_all[0]
            try:
                valid = (viewer is not None and sub is not None and sub.isVisible()
                         and mdi.activeSubWindow() is sub and viewer.explode_slider.isEnabled()
                         and self._hit(point) is viewer.canvas)
            except RuntimeError:
                valid = False
            if not valid:
                self.reset()
                return
            if self.mode == 'claw':
                start_y, start_value = self.origin
                viewer.explode_slider.setValue(start_value + round((start_y - point.y()) * 100 /
                                                                     max(1, viewer.canvas.height())))
            else:
                # A new pose cancels any earlier pinch without generating a click.
                self.mode = self.target = self.origin = self.pending = None
                now = time.monotonic()
                if (self.claw_pending is None or
                        (point - self.claw_pending[1]).manhattanLength() > 25):
                    self.claw_pending = (now, point)
                elif now - self.claw_pending[0] >= .4:
                    self.mode, self.target = 'claw', viewer.canvas
                    self.origin = (point.y(), viewer.explode_slider.value())
                    self.claw_pending = None
            return
        if self.mode == 'claw' or self.claw_pending is not None:
            self.reset()
            return  # release/loss cannot become a click
        hands = sorted((s for s in samples if s[2]), key=lambda s: s[0])
        if not hands:
            # A visible, open hand is an intentional release. Tracking loss,
            # a second hand, focus loss and modal dialogs always cancel clicks.
            if self.mode == 'click' and len(samples) == 1 and len(coords_all) == 1:
                p = coords_all[0]
                if (p - self.origin[0]).manhattanLength() <= 25:
                    self._click(p)
            if self.mode == 'move' and len(samples) == 1:
                try:
                    target = self.target
                    delta = self.flick.displacement(time.monotonic())
                    if (delta and target.isVisible() and not target.isMaximized()
                            and mdi.activeSubWindow() is target):
                        position = bounded_flick((target.x(), target.y()), delta,
                                                 (viewport.width(), viewport.height()))
                        if position is not None:
                            target.move(*position)
                except RuntimeError:
                    pass  # Target was destroyed or detached during the drag.
            if len(samples) == 1 and len(samples[0]) > 3 and samples[0][3]:
                self.mode = self.target = self.origin = self.pending = None
                self._scroll(coords_all[0])
            else:
                self.reset()
            return
        self.scroll_origin = None
        # A second visible but open hand is not a one-hand gesture. Reject it
        # rather than arming an action that could transfer to another hand.
        if len(hands) > 2 or len(hands) != len(samples):
            self.reset()
            return
        coords = [QPoint(round(s[0] * max(0, viewport.width() - 1)),
                         round(s[1] * max(0, viewport.height() - 1))) for s in hands]
        count = len(coords)
        if any(self._hit(p) is None for p in coords):
            self.reset()
            return
        if self.mode is None or (self.mode in ('move', 'click', 'slider')) != (count == 1):
            self.mode = self.target = self.origin = None
            p = coords[0] if count == 1 else (coords[0] + coords[1]) / 2
            hit = self._hit(p)
            # The dwell belongs to the original widget, not merely the
            # number of hands. Moving to another target starts a fresh dwell.
            identity = (hit, None)
            positions = tuple((point.x(), point.y()) for point in coords)
            if not dwell_matches(self.pending, count, identity, positions):
                self.pending = (count, time.monotonic(), identity, positions)
                return
            if time.monotonic() - self.pending[1] < .35:
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
                    self.flick.points.clear()
                    self.flick.add((coords[0].x(), coords[0].y()), time.monotonic())
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
        try:
            available = (self.target and self.target.isVisible() and not self.target.isMaximized()
                         and mdi.activeSubWindow() is self.target)
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
            self.flick.add((coords[0].x(), coords[0].y()), time.monotonic())
        else:
            geometry = transform_window(
                [(p.x(), p.y()) for p in initial], [(p.x(), p.y()) for p in coords],
                (geom.x(), geom.y(), geom.width(), geom.height()),
                (viewport.width(), viewport.height()),
                (self.target.minimumWidth(), self.target.minimumHeight()))
            if geometry is not None:
                self.target.setGeometry(*geometry)



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
    panel, panel_heading, panel_mode, panel_stop = build_status_panel(window)
    window._hand_visual_panel = panel
    window._hand_visual_heading = panel_heading
    window._hand_visual_mode = panel_mode
    window._hand_visual_stop = panel_stop

    def refresh():
        key = {'off': 'gesture.off', 'starting': 'gesture.starting', 'active': 'gesture.workspace_active',
               'camera_busy': 'gesture.busy', 'error': 'gesture.error', 'windows_only': 'gesture.windows_only'}.get(controller.status, 'gesture.off')
        running = bool(controller.thread and controller.thread.is_alive() and not controller._stop.is_set())
        if controller.thread and controller.thread.is_alive() and controller._stop.is_set() and controller.status != 'error':
            key = 'gesture.stopping'
        message = _t(key)
        if controller.status == 'error' and controller.error:
            message += ' ' + controller.error
        samples = controller.sample() if running else ()
        gestures.update(samples)
        # The SAME samples, one frame later, offered to the desktop. The
        # workspace acts first on purpose: if a gesture is ambiguous, moving a
        # card here is recoverable and clicking something there may not be.
        bridge = getattr(window, '_gesture_os', None)
        if bridge is not None:
            if running:
                bridge.feed(samples, time.monotonic())
            else:
                bridge.release()
        mode_key = {'move': 'gesture.mode_move', 'resize': 'gesture.mode_transform',
                    'click': 'gesture.mode_click', 'slider': 'gesture.mode_slider',
                    'claw': 'gesture.mode_claw'}.get(gestures.mode)
        if running and controller.status == 'active' and mode_key:
            message += ' · ' + _t(mode_key)
        status.setText(message)
        banner = getattr(window, '_confirm_overlay', None)
        unobstructed = (window.isActiveWindow() and QApplication.activeModalWidget() is None
                        and QApplication.activePopupWidget() is None
                        and not getattr(window, '_hand_closing_confirm', False)
                        and not (banner is not None and banner.isVisible()))
        panel_visible = running and controller.status in ('active', 'starting') and unobstructed
        viewport = window._desktop_mdi.viewport()
        panel_width = max(1, min(300, viewport.width() - 20))
        panel.setGeometry(max(0, viewport.width() - panel_width - 10), 10, panel_width, 80)
        panel_heading.setText(_t('gesture.visual_active' if controller.status == 'active' else 'gesture.visual_starting'))
        panel_mode.setText(_t(mode_key) if controller.status == 'active' and mode_key else
                           _t('gesture.visual_waiting' if controller.status == 'active' else 'gesture.visual_start_wait'))
        panel_stop.setText(_t('gesture.visual_stop'))
        panel_stop.setAccessibleName(_t('gesture.visual_stop'))
        panel.setVisible(panel_visible)
        gestures.link.set_samples(samples, bool(panel_visible and gestures.mode == 'resize'
                                                and len(samples) == 2 and all(s[2] for s in samples)))
        if panel_visible:
            panel.raise_()
        badge = getattr(window, '_hand_badge', None)
        if badge is not None:
            badge.setVisible(running and controller.status in ('active', 'starting'))
            badge.setText(_t('gesture.badge_active' if controller.status == 'active' else 'gesture.badge_starting'))
            badge.setToolTip(message)
            badge.setAccessibleName(_t('gesture.badge_accessible'))
        button.setText(_t('gesture.disable' if running else 'gesture.enable'))
        button.setEnabled(not (controller.thread and controller.thread.is_alive() and controller._stop.is_set()))

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

    def release_os_button():
        """Let go of a button a gesture is holding, if there is one.

        Called wherever tracking can stop — the panel's Stop, the drawer's
        toggle, and the process exiting. A held button left behind turns the
        whole desktop into a drag-selection, and the user cannot fix it by
        waving: the pointer is theirs, the button is this program's.
        """
        bridge = getattr(window, '_gesture_os', None)
        if bridge is not None:
            bridge.release()

    def stop_from_panel():
        # Never toggle: a worker that just exited must not be restarted by Stop.
        controller.stop()
        release_os_button()
        gestures.reset()
        gestures.clap.reset()
        gestures.show_cursors(())
        refresh()

    panel_stop.clicked.connect(stop_from_panel)
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
    QApplication.instance().aboutToQuit.connect(release_os_button)
