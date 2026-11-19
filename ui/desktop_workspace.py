"""Multitasking desktop shell. Existing panels remain owned by MainWindow.

Only local widgets are constructed here; plugin approval and the assistant's
thread-safe dispatch are still owned by the existing application.
"""
from pathlib import Path

from PyQt6.QtCore import QDir, QFileInfo, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (QBrush, QColor, QDesktopServices, QFileSystemModel, QIcon,
                         QLinearGradient, QPainter, QPixmap)
from PyQt6.QtWidgets import (QFileIconProvider, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMdiArea,
                             QMdiSubWindow, QMenu, QPushButton, QScrollArea, QSizeGrip, QStyle, QToolButton,
                             QTreeView, QVBoxLayout, QWidget)

from core.i18n import label as _t
from ui.theme import C, workspace_stylesheet


class WorkspaceEmblem(QWidget):
    """Decorative JARVIS emblem; never claims a live microphone or AI state."""
    def __init__(self, name, parent):
        super().__init__(parent)
        self.name = name
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAccessibleName(name)

    def paintEvent(self, event):
        from PyQt6.QtGui import QFont, QPen, QRadialGradient
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width() - 20, self.height() - 80, 168)
        if side <= 0:
            return
        x = (self.width() - side) / 2
        y = max(4, (self.height() - side - 65) / 2)
        glow = QRadialGradient(x + side * .44, y + side * .37, side * .75)
        for stop, color in ((0, "#39679c"), (.36, "#102b51"), (.66, "#071729"), (1, "#173f6b")):
            glow.setColorAt(stop, QColor(color))
        painter.setPen(QPen(QColor("#70c8ff"), 2))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QRectF(x, y, side, side))
        painter.setPen(QPen(QColor("#4b95dd"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(x + 7, y + 7, side - 14, side - 14))
        painter.setPen(QColor(C.DESKTOP_TEXT))
        painter.setFont(QFont("Arial", 17, QFont.Weight.Bold))
        painter.drawText(QRectF(0, y + side + 14, self.width(), 32),
                         Qt.AlignmentFlag.AlignCenter, self.name.upper())
        painter.end()


class WorkspaceAvatar(QWidget):
    """A transparent central view of the existing live HUD face animation."""
    def __init__(self, hud, parent):
        super().__init__(parent)
        self.hud = hud
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

    def paintEvent(self, event):
        from PyQt6.QtGui import QFont, QRadialGradient
        from ui.desktop_layout import state_label
        from ui.theme import qcol
        del event
        avatar = self.hud._avatar
        if avatar is None or self.hud.hud_style != 'face':
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        radius = max(1., min(width * .33, (height - 75) / (avatar.SPAN + .2)))
        cx = width / 2
        cy = max(radius + 5, (height - 75 - avatar.SPAN * radius) / 2 + radius)
        aura = QRadialGradient(cx, cy, radius * 1.7)
        aura.setColorAt(0., QColor(36, 112, 176, 75))
        aura.setColorAt(.65, QColor(35, 136, 213, 55))
        aura.setColorAt(1., QColor(11, 26, 42, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(aura))
        painter.drawEllipse(QRectF(cx - radius * 1.7, cy - radius * 1.7, radius * 3.4, radius * 3.4))
        color = qcol(C.MUTED_C if self.hud.muted else C.PRI)
        # A brighter projection improves facial features on the dark desktop;
        # preserve the user's hue and the distinct muted state.
        if not self.hud.muted:
            color = color.lighter(135)
        avatar.paint(painter, cx, cy, radius, color, color, qcol(C.DESKTOP_BAR), wireframe=False)
        bottom = min(height - 58, cy + (avatar.SPAN - 1) * radius + 5)
        painter.setPen(qcol(C.DESKTOP_TEXT))
        painter.setFont(QFont("Arial", 19, QFont.Weight.Bold))
        painter.drawText(QRectF(0, bottom, width, 28), Qt.AlignmentFlag.AlignCenter,
                         (self.hud._assistant_name or 'JARVIS').upper())
        painter.setFont(QFont("Arial", 10, QFont.Weight.Normal))
        painter.setPen(qcol(C.MUTED_C if self.hud.muted else C.PRI))
        painter.drawText(QRectF(0, bottom + 29, width, 24), Qt.AlignmentFlag.AlignCenter,
                         state_label('MUTED' if self.hud.muted else self.hud.state))
        painter.end()


class WallpaperArea(QMdiArea):
    """Scale the original wallpaper to cover the desktop, not the app windows."""
    def __init__(self):
        super().__init__()
        self._wallpaper = QPixmap(str(Path(__file__).resolve().parent.parent / "assets/workspace/jarvis-desktop-wave.png"))
        self._dock = None
        self._emblem = None
        self._avatar_stage = None
        self._host_window = None
        self._clap_windows = []

    def minimize_for_clap(self):
        # Preserve windows already minimized and hidden; restore only this batch.
        for sub in self.subWindowList():
            if sub.isVisible() and not sub.isMinimized():
                self._clap_windows = [(old, maximized) for old, maximized in self._clap_windows
                                      if old is not sub]
                self._clap_windows.append((sub, sub.isMaximized()))
                sub.showMinimized()
        self.position_dock()

    def restore_clap_windows(self):
        windows, self._clap_windows = self._clap_windows, []
        for sub, maximized in windows:
            try:
                # Do not reopen windows the user closed or already restored.
                if sub in self.subWindowList() and sub.isVisible() and sub.isMinimized():
                    sub.showMaximized() if maximized else sub.showNormal()
            except RuntimeError:
                pass
        self.position_dock()

    def position_emblem(self):
        if self._emblem is not None:
            width, height = self.viewport().width(), self.viewport().height()
            wide = width >= 1100 and height >= 400
            stage = self._avatar_stage
            face = bool(stage is not None and stage.hud.hud_style == 'face' and stage.hud._avatar is not None)
            self._emblem.setVisible(wide and not face)
            # The stage fits in the breathing room between the initial Files
            # and Assistant windows and stays clear of the dock on short screens.
            files, assistant = initial_window_geometry(width, height)
            gap_left, gap_right = files[0] + files[2], assistant[0]
            stage_width = max(1, min(320, gap_right - gap_left - 20))
            stage_top = max(0, int(height * .18))
            stage_height = max(1, min(350, height - stage_top - 90))
            geometry = (gap_left + (gap_right - gap_left - stage_width) // 2,
                        stage_top, stage_width, stage_height)
            self._emblem.setGeometry(*geometry)
            if stage is not None:
                stage.setGeometry(*geometry)
                stage.setVisible(wide and face)
            # The live central face replaces the duplicate HUD on wide
            # desktops. Orb/core and compact layouts retain their live HUD.
            if self._host_window is not None:
                from ui.desktop_layout import refresh_assistant_tools
                self._host_window._hud_cam_stack.setVisible(not (wide and face))
                refresh_assistant_tools(self._host_window)

    def position_dock(self):
        if self._dock is not None:
            preferred = self._dock.widget().sizeHint().width() + 16
            width = max(1, min(1020, max(500, preferred), self.viewport().width() - 20))
            self._dock.setGeometry((self.viewport().width() - width) // 2,
                                   max(0, self.viewport().height() - 86), width, 76)
            self._dock.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._wallpaper.isNull():
            image = self._wallpaper.scaled(self.viewport().size(),
                                           Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                           Qt.TransformationMode.SmoothTransformation)
            self.setBackground(QBrush(image))
        self.position_emblem()
        self.position_dock()


class WindowTitleBar(QWidget):
    """Draggable title bar with working close, minimize and maximize controls."""
    def __init__(self, sub):
        super().__init__()
        self._sub = sub
        self._drag_offset = None
        self.setFixedHeight(33)
        self.setObjectName("WorkspaceTitleBar")
        self.setStyleSheet(f"QWidget#WorkspaceTitleBar {{ background: {C.DESKTOP_SIDEBAR}; "
                           f"border-bottom: 1px solid {C.DESKTOP_BORDER}; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(7)
        for color, tip, action in (("#ff6058", "workspace.close", sub.close),
                                   ("#ffbd2e", "workspace.minimize", sub.showMinimized),
                                   ("#28c840", "workspace.maximize", self.toggle_maximize)):
            button = QPushButton()
            button.setFixedSize(12, 12)
            button.setToolTip(_t(tip))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"QPushButton {{ background: {color}; border: none; border-radius: 6px; }}")
            button.clicked.connect(lambda checked=False, fn=action: fn())
            row.addWidget(button)
        row.addStretch(1)
        self.title = QLabel("")
        self.title.setStyleSheet(f"color: {C.DESKTOP_TEXT}; background: transparent; border: none; font-weight: bold;")
        row.addWidget(self.title)
        row.addStretch(1)
        row.addSpacing(50)  # balances the three controls at the opposite edge

    def toggle_maximize(self):
        if self._sub.isMaximized():
            self._sub.showNormal()
        else:
            self._sub.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._sub.pos()
            self._sub.setFocus()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton and not self._sub.isMaximized():
            self._sub.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class PersistentWindow(QMdiSubWindow):
    """Real subwindow with custom chrome; closing hides its live content."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self._workspace_title = None

    def setWidget(self, widget):
        wrapper = QWidget()
        wrapper.setObjectName("WorkspaceWindowBody")
        wrapper.setStyleSheet(f"QWidget#WorkspaceWindowBody {{ background: {C.DESKTOP_PANEL}; }}")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._workspace_title = WindowTitleBar(self)
        layout.addWidget(self._workspace_title)
        layout.addWidget(widget, 1)
        resize_row = QHBoxLayout()
        resize_row.setContentsMargins(0, 0, 0, 0)
        resize_row.addStretch(1)
        grip = QSizeGrip(wrapper)
        grip.setFixedSize(12, 12)
        grip.setToolTip(_t("workspace.resize"))
        resize_row.addWidget(grip)
        layout.addLayout(resize_row)
        super().setWidget(wrapper)

    def setWindowTitle(self, title):
        super().setWindowTitle(title)
        if self._workspace_title is not None:
            self._workspace_title.title.setText(title)

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class DocumentWindow(PersistentWindow):
    """Shared workspace chrome while preserving the document's close veto."""
    def __init__(self, document):
        super().__init__()
        self._document = document

    def closeEvent(self, event):
        if self._document.close():
            # Bypass PersistentWindow's hide-only behaviour for disposable docs.
            QMdiSubWindow.closeEvent(self, event)
        else:
            event.ignore()


class VideoWindow(PersistentWindow):
    """Closing the video window stops playback; hiding must not leave sound playing."""
    def __init__(self, host):
        super().__init__()
        self._host = host

    def closeEvent(self, event):
        self._host._on_video_close()
        event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Wait until the embedded graphics view has received its new geometry.
        QTimer.singleShot(0, self._host._fit_video)


class CameraWindow(PersistentWindow):
    """Closing the camera preview stops capture rather than hiding a live feed."""
    def __init__(self, host):
        super().__init__()
        self._host = host

    def closeEvent(self, event):
        self._host.stop_camera_stream()
        self.hide()
        event.ignore()


class WorkspaceFileIcons(QFileIconProvider):
    """Stable folder glyphs; defer files and symlinks to the operating system."""
    def __init__(self):
        super().__init__()
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#31a2dc"))
        painter.drawRoundedRect(QRectF(2, 6, 14, 9), 2, 2)
        gradient = QLinearGradient(0, 10, 0, 27)
        gradient.setColorAt(0, QColor("#65c6ef"))
        gradient.setColorAt(1, QColor("#198acb"))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(QRectF(2, 10, 28, 17), 3, 3)
        painter.end()
        self._folder = QIcon(pixmap)

    def icon(self, info):
        # Preserve the platform's symlink badge and all file-type associations.
        if isinstance(info, QFileInfo) and info.isDir() and not info.isSymLink():
            return self._folder
        return super().icon(info)


class FileBrowser(QWidget):
    """Read-only navigation; opening files delegates to the user's OS."""
    def __init__(self):
        super().__init__()
        self.setObjectName("WorkspaceFiles")
        self.setStyleSheet(workspace_stylesheet() + f"""
            QWidget#WorkspaceFiles {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; }}
            QLabel {{ color: {C.DESKTOP_MUTED}; }}
            QTreeView {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; border: none;
                         alternate-background-color: {C.DESKTOP_SIDEBAR}; }}
            QTreeView::item:selected {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT}; }}
            QHeaderView::section {{ background: {C.DESKTOP_BAR}; color: {C.DESKTOP_MUTED};
                                    border: none; padding: 6px; }}
            QLineEdit {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT};
                         border: 1px solid {C.DESKTOP_BORDER}; border-radius: 6px; padding: 6px; }}
            QPushButton {{ background: transparent; color: {C.DESKTOP_TEXT}; border: none;
                           text-align: left; padding: 8px; border-radius: 6px; }}
            QPushButton:hover, QPushButton:checked {{ background: {C.DESKTOP_DOCK}; }}
            QPushButton#FileNavigation {{ text-align: center; padding: 0; font-size: 18px; }}
            QPushButton#FileFolderTitle {{ font-weight: bold; color: {C.DESKTOP_TEXT}; padding: 5px; }}
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QWidget()
        sidebar.setFixedWidth(145)
        sidebar.setStyleSheet(f"background: {C.DESKTOP_SIDEBAR};")
        favorites = QVBoxLayout(sidebar)
        favorites.setContentsMargins(10, 12, 10, 10)
        self.favorites_heading = QLabel(_t("workspace.favorites"))
        favorites.addWidget(self.favorites_heading)
        self._favorite_buttons = []
        self._favorite_paths = []
        self._history = []
        self._history_index = -1
        home = Path.home()
        for key, folder, icon in (("workspace.projects", home / "Projects", "SP_DirIcon"),
                                  ("workspace.home", home, "SP_DirHomeIcon"),
                                  ("workspace.desktop", home / "Desktop", "SP_DesktopIcon"),
                                  ("workspace.documents", home / "Documents", "SP_FileIcon"),
                                  ("workspace.downloads", home / "Downloads", "SP_DirIcon")):
            button = QPushButton(_t(key))
            button.setCheckable(True)
            button.setIcon(self.style().standardIcon(getattr(QStyle.StandardPixmap, icon)))
            button.setIconSize(QSize(18, 18))
            button.setEnabled(folder.is_dir())
            button.clicked.connect(lambda checked=False, target=folder: self.navigate(str(target)))
            favorites.addWidget(button)
            self._favorite_buttons.append((button, key))
            self._favorite_paths.append((button, folder))
        favorites.addStretch(1)
        root.addWidget(sidebar)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        header = QHBoxLayout()
        self.back = QPushButton("‹")
        self.forward = QPushButton("›")
        for button in (self.back, self.forward):
            button.setObjectName("FileNavigation")
            button.setFixedSize(26, 30)
        self.back.clicked.connect(lambda: self._history_step(-1))
        self.forward.clicked.connect(lambda: self._history_step(1))
        header.addWidget(self.back)
        header.addWidget(self.forward)
        self.up = QPushButton("↑")
        self.up.setObjectName("FileNavigation")
        self.up.setFixedSize(26, 30)
        self.up.clicked.connect(self._up)
        header.addWidget(self.up)
        self.folder_title = QPushButton()
        self.folder_title.setObjectName("FileFolderTitle")
        self.folder_title.clicked.connect(self._edit_path)
        header.addWidget(self.folder_title, 1)
        self.path = QLineEdit(str(home))
        self.path.returnPressed.connect(self._accept_path)
        header.addWidget(self.path, 1)
        self.path.hide()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("workspace.search"))
        self.search.setMaximumWidth(170)
        self.search.textChanged.connect(self._filter)
        header.addWidget(self.search)
        layout.addLayout(header)
        self.model = QFileSystemModel(self)
        self._icon_provider = WorkspaceFileIcons()
        self.model.setIconProvider(self._icon_provider)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilterDisables(False)
        self.model.setRootPath(str(home))
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setIconSize(QSize(20, 20))
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        # Finder-style table: keep names readable, omit the redundant type
        # column, and put modification time before size. Reserve a usable name
        # column instead of letting long timestamps consume the whole view;
        # metadata columns remain resizable and scroll on narrow windows.
        self.view.setColumnHidden(2, True)
        header_view = self.view.header()
        header_view.moveSection(header_view.visualIndex(3), 1)
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header_view.resizeSection(1, 62)
        header_view.resizeSection(3, 130)
        self.view.doubleClicked.connect(self._open)
        layout.addWidget(self.view, 1)
        self._status_key = "workspace.files_hint"
        self.status = QLabel(_t(self._status_key))
        self.status.setWordWrap(True)
        # Ordinary navigation needs no persistent explanatory banner. Keep the
        # status widget for translated errors, which must remain visible.
        self.status.hide()
        layout.addWidget(self.status)
        root.addWidget(content, 1)
        self.navigate(str(home))
        self.retranslate()

    def _set_status(self, key):
        self._status_key = key
        self.status.setText(_t(key))
        self.status.setVisible(key != "workspace.files_hint")

    def retranslate(self):
        self.favorites_heading.setText(_t("workspace.favorites"))
        for button, key in self._favorite_buttons:
            button.setText(_t(key))
        for button, key in ((self.back, "workspace.back"), (self.forward, "workspace.forward"),
                            (self.up, "workspace.up")):
            button.setToolTip(_t(key))
            button.setAccessibleName(_t(key))
        self.search.setPlaceholderText(_t("workspace.search"))
        self.folder_title.setAccessibleName(_t("workspace.edit_path"))
        self.folder_title.setToolTip(_t("workspace.edit_path"))
        self.path.setAccessibleName(_t("workspace.edit_path"))
        self.status.setText(_t(self._status_key))

    def _filter(self, text):
        # QFileSystemModel applies these patterns to files; directories remain
        # navigable. This never alters or sends a user's files.
        text = text.strip()
        self.model.setNameFilters([f"*{text}*"] if text else [])

    def navigate(self, path, *, _record=True):
        target = Path(path).expanduser()
        if not target.is_dir():
            self._refresh_favorites()
            self._set_status("workspace.bad_folder")
            return False
        path = str(target.resolve())
        if _record and (self._history_index < 0 or self._history[self._history_index] != path):
            del self._history[self._history_index + 1:]
            self._history.append(path)
            self._history = self._history[-100:]
            self._history_index = len(self._history) - 1
        self.view.setRootIndex(self.model.setRootPath(path))
        self.path.setText(path)
        self.folder_title.setText(Path(path).name or Path(path).anchor)
        self._refresh_favorites()
        self._sync_history()
        self._set_status("workspace.files_hint")
        return True

    def _refresh_favorites(self):
        current = self._history[self._history_index] if self._history_index >= 0 else ""
        for button, folder in self._favorite_paths:
            exists = folder.is_dir()
            button.setEnabled(exists)
            button.setChecked(exists and str(folder.resolve()) == current)

    def showEvent(self, event):
        super().showEvent(event)
        # Folders may be created or removed while the Files window is hidden.
        self._refresh_favorites()

    def _edit_path(self):
        self.folder_title.hide()
        self.path.show()
        self.path.setFocus()
        self.path.selectAll()

    def _accept_path(self):
        if self.navigate(self.path.text()):
            self.path.hide()
            self.folder_title.show()

    def _sync_history(self):
        self.back.setEnabled(self._history_index > 0)
        self.forward.setEnabled(self._history_index + 1 < len(self._history))

    def _history_step(self, delta):
        index = self._history_index + delta
        if 0 <= index < len(self._history) and self.navigate(self._history[index], _record=False):
            self._history_index = index
            self._refresh_favorites()
            self._sync_history()

    def _up(self):
        if self._history_index >= 0:
            self.navigate(str(Path(self._history[self._history_index]).parent))

    def _open(self, index):
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.navigate(path)
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._set_status("workspace.open_failed")


def dock_icon(style, icon_name, color):
    """Make a rounded, coloured tile around the platform's real action icon."""
    pixmap = QPixmap(44, 44)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 0, 44)
    gradient.setColorAt(0, QColor(color).lighter(145))
    gradient.setColorAt(1, QColor(color).darker(130))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(QRectF(1, 1, 42, 42), 10, 10)
    icon = style.standardIcon(getattr(QStyle.StandardPixmap, icon_name))
    painter.drawPixmap(8, 8, icon.pixmap(28, 28))
    painter.end()
    return QIcon(pixmap)


def initial_window_geometry(width, height):
    """Keep both initial panels within the desktop above the floating dock."""
    width, height = max(1, width), max(1, height)
    floor = max(1, height - 90)
    # Wide layouts leave a breathing space for the JARVIS emblem between
    # the files on the left and the conversation on the right. Compact layouts
    # use the space for the real tools instead of overlapping the panels.
    wide = width >= 1100
    file_x = max(0, int(width * .02))
    file_y = max(0, int(height * .07))
    file_w = max(1, min(int(width * (.37 if wide else .46)), width - file_x))
    file_h = max(1, min(int(height * (.36 if wide else .48)), floor - file_y))
    assistant_x = max(0, min(int(width * (.63 if wide else .51)), width - 1))
    assistant_y = max(0, int(height * (.10 if wide else .14)))
    assistant_w = max(1, min(int(width * (.35 if wide else .47)), width - assistant_x))
    assistant_h = max(1, min(int(height * (.80 if wide else .66)), floor - assistant_y))
    return (file_x, file_y, file_w, file_h), (assistant_x, assistant_y, assistant_w, assistant_h)


def open_initial_editor(window):
    """Open one blank editor after plugin discovery, only on a roomy desktop.

    Never re-open a closed window on registry refresh, and never bypass plugin
    enablement. This is dispatched on the Qt thread, not the registry worker.
    """
    if getattr(window, "_initial_editor_attempted", False):
        return
    window._initial_editor_attempted = True
    mdi = window._desktop_mdi
    width, height = mdi.viewport().width(), mdi.viewport().height()
    if width < 1100 or height < 650:
        return
    if any(kind == "code_editor" for kind, _ in window._workspace_documents.values()):
        return
    try:
        enabled = any(item.get("name") == "code_editor" and item.get("valid") and item.get("enabled")
                      for item in window.get_plugins())
    except Exception:
        return
    if not enabled:
        return
    from ui.creative import open_workspace
    sub = open_workspace(window, {"kind": "creative_workspace", "tab": "editor"})
    if sub is None:
        return
    files, _ = initial_window_geometry(width, height)
    x, y, w, h = files
    top = y + h + 18
    sub.setGeometry(x, top, w, max(1, height - 90 - top))
    mdi.position_dock()


def build(window):
    shell = QWidget()
    shell.setObjectName("WorkspaceShell")
    shell.setStyleSheet(f"""
        QWidget#WorkspaceShell {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 #0b1725, stop:0.55 #192d43, stop:1 #091522); }}
        QMdiArea {{ border: none; }}
        QMdiSubWindow {{ background: {C.DESKTOP_PANEL}; border: 1px solid {C.DESKTOP_BORDER}; }}
        QMdiSubWindow::title {{ background: {C.DESKTOP_SIDEBAR}; color: {C.DESKTOP_TEXT};
                               padding: 5px; }}
        QWidget#DesktopDock {{ background: rgba(21, 34, 49, 242); border: 1px solid {C.DESKTOP_BORDER};
                               border-radius: 15px; }}
        QToolButton#DockButton {{ color: {C.DESKTOP_TEXT}; background: transparent;
            border: none; border-radius: 8px; padding: 4px; }}
        QToolButton#DockButton:hover {{ background: {C.DESKTOP_SIDEBAR}; }}
        QToolButton#DockButton:focus {{ border: 1px solid #69c8f4; }}
    """)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    mdi = WallpaperArea()
    mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
    mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    layout.addWidget(mdi, 1)
    window._desktop_mdi = mdi
    mdi._host_window = window
    mdi._emblem = WorkspaceEmblem(window._assistant_name, mdi.viewport())
    mdi._avatar_stage = WorkspaceAvatar(window.hud, mdi.viewport())
    window.hud._desktop_stage = mdi._avatar_stage
    mdi.position_emblem()
    mdi._avatar_stage.lower()
    mdi._emblem.lower()
    window._desktop_windows = {}
    window._workspace_documents = {}
    window._workspace_document_counter = 0

    def add(name, widget, title):
        sub = PersistentWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(_t(title))
        mdi.addSubWindow(sub)
        window._desktop_windows[name] = sub
        return sub

    assistant = add("assistant", window._assistant_panel, "workspace.assistant")
    assistant.show()
    # The real conversation now lives alongside the HUD in the assistant panel.
    window._desktop_windows["chat"] = assistant
    window._workspace_file_browser = FileBrowser()
    add("files", window._workspace_file_browser, "workspace.files").show()
    add("navigation", window._left_panel, "workspace.navigation").hide()
    video = VideoWindow(window)
    video.setWidget(window._video_cont)
    video.setWindowTitle(_t("workspace.video"))
    mdi.addSubWindow(video)
    video.resize(720, 480)
    video.hide()
    window._desktop_windows["video"] = video
    camera = CameraWindow(window)
    camera.setWidget(window._camera_cont)
    camera.setWindowTitle(_t("workspace.camera"))
    mdi.addSubWindow(camera)
    camera.resize(600, 430)
    camera.hide()
    window._desktop_windows["camera"] = camera

    def open_model_viewer():
        if "model_viewer" not in window._desktop_windows:
            from ui.model_viewer import ModelViewer
            sub = PersistentWindow()
            window._model_viewer = ModelViewer(window)
            sub.setWidget(window._model_viewer)
            sub.setWindowTitle(_t("model.title"))
            mdi.addSubWindow(sub)
            sub.resize(min(720, max(1, mdi.viewport().width())),
                       min(540, max(1, mdi.viewport().height() - 90)))
            window._desktop_windows["model_viewer"] = sub
        sub = window._desktop_windows["model_viewer"]
        sub.showNormal()
        mdi.setActiveSubWindow(sub)
        sub.raise_()
        mdi.position_dock()
        return sub

    window._open_model_viewer = open_model_viewer

    def focus(name):
        if name == "camera" and not window._camera_active:
            window.write_log(_t("workspace.camera_starting"))
            window.start_camera_stream()
            return
        sub = window._desktop_windows.get(name)
        if sub is None and name == "files":
            sub = add("files", FileBrowser(), "workspace.files")
            sub.resize(720, 450)
        if sub:
            sub.showNormal()
            mdi.setActiveSubWindow(sub)
            sub.raise_()
            mdi.position_dock()
            if name == "chat":
                window._input.setFocus()

    def creative():
        from ui.creative import open_workspace
        open_workspace(window, {"kind": "creative_workspace", "tab": "editor"})

    def trading():
        from ui.trading_terminal import open_terminal
        open_terminal(window, {"kind": "trading_terminal"})

    def image_editor():
        from ui.workspace_router import open_workspace
        open_workspace(window, {"kind": "image_editor"})

    def browser():
        from ui.workspace_router import open_workspace
        open_workspace(window, {"kind": "workspace_browser"})

    def ssh_manager():
        from ui.workspace_router import open_workspace
        open_workspace(window, {"kind": "ssh_manager"})

    def order():
        from ui.mt5_trade import open_trade
        open_trade(window, {"kind": "mt5_trade", "draft": {}})

    dock = QWidget()
    dock.setObjectName("DesktopDock")
    row = QHBoxLayout(dock)
    row.setContentsMargins(4, 0, 4, 0)
    row.addStretch(1)
    # Group related destinations instead of repeating overlapping dock entries.
    buttons = (
        ("workspace.chat", "SP_MessageBoxInformation", lambda: focus("chat")),
        ("workspace.files", "SP_DirIcon", lambda: focus("files")),
        ("browser.title", "SP_ComputerIcon", browser),
        ("workspace.editors", "SP_FileIcon", (("workspace.code", creative),
                                                ("workspace.image", image_editor))),
        ("workspace.media", "SP_MediaPlay", (("workspace.video", lambda: focus("video")),
                                                 ("workspace.camera", lambda: focus("camera")))),
        ("workspace.trading", "SP_FileDialogInfoView", (("workspace.trading", trading),
                                                           ("workspace.order", order))),
        ("workspace.apps", "SP_TitleBarMenuButton", (("workspace.restore_clap", mdi.restore_clap_windows),
                                                         ("model.title", open_model_viewer),
                                                         ("workspace.navigation", lambda: focus("navigation")),
                                                         ("ssh.title", ssh_manager),
                                                         ("desktop.plugins", window._open_plugin_manager))),
        ("desktop.settings", "SP_FileDialogListView", lambda: window._drawer_btn.click()),
    )
    window._workspace_dock = []
    window._workspace_dock_actions = []
    colors = (C.DOCK_BLUE, C.DOCK_TEAL, C.DOCK_BLUE, C.DOCK_GREEN, C.DOCK_PURPLE,
              C.DOCK_ORANGE, C.DOCK_CHARCOAL, C.DOCK_CHARCOAL)
    for (key, icon, action), color in zip(buttons, colors):
        button = QToolButton()
        button.setText(_t(key))
        button.setToolTip(_t(key))
        button.setAccessibleName(_t(key))
        button.setObjectName("DockButton")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setIcon(dock_icon(window.style(), icon, color))
        button.setIconSize(QSize(44, 44))
        button.setMinimumWidth(64)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if isinstance(action, tuple):
            menu = QMenu(button)
            menu.setStyleSheet(workspace_stylesheet())
            for label, callback in action:
                entry = menu.addAction(_t(label))
                entry.triggered.connect(lambda checked=False, fn=callback: fn())
                window._workspace_dock_actions.append((entry, label))
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            button.clicked.connect(lambda checked=False, fn=action: fn())
        row.addWidget(button)
        window._workspace_dock.append((button, key))
    row.addStretch(1)
    dock_scroll = QScrollArea(mdi.viewport())
    dock_scroll.setWidgetResizable(True)
    dock_scroll.setWidget(dock)
    dock_scroll.setFixedHeight(76)
    dock_scroll.setMaximumWidth(1020)
    dock_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    dock_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    dock_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    mdi._dock = dock_scroll
    mdi.subWindowActivated.connect(lambda _sub: mdi.position_dock())
    dock_scroll.show()
    mdi.position_dock()

    def position_initial():
        width = mdi.viewport().width()
        height = mdi.viewport().height()
        files, assistant, nav = (window._desktop_windows[k] for k in ("files", "assistant", "navigation"))
        file_geometry, assistant_geometry = initial_window_geometry(width, height)
        files.setGeometry(*file_geometry)
        assistant.setGeometry(*assistant_geometry)
        nav.resize(240, max(350, min(height - 40, 700)))
        files.show()
        assistant.show()
        nav.hide()
        mdi.position_dock()
    QTimer.singleShot(0, position_initial)
    return shell


def retranslate(window):
    for button, key in getattr(window, "_workspace_dock", ()):
        button.setText(_t(key))
        button.setToolTip(_t(key))
        button.setAccessibleName(_t(key))
    for action, key in getattr(window, "_workspace_dock_actions", ()):
        action.setText(_t(key))
    for name, key in (("assistant", "workspace.assistant"),
                      ("navigation", "workspace.navigation"), ("files", "workspace.files"),
                      ("video", "workspace.video"), ("camera", "workspace.camera"), ("model_viewer", "model.title")):
        sub = getattr(window, "_desktop_windows", {}).get(name)
        if sub:
            sub.setWindowTitle(_t(key))
    window._workspace_file_browser.retranslate()
    model_viewer = getattr(window, "_model_viewer", None)
    if model_viewer:
        model_viewer.retranslate()
    # Repaint active tool windows without rebuilding them or dropping state.
    for kind, sub in tuple(getattr(window, "_workspace_documents", {}).values()):
        try:
            document = sub._document
            if callable(getattr(document, "retranslate", None)):
                document.retranslate()
                sub.setWindowTitle(document.windowTitle())
        except RuntimeError:
            continue  # The Qt wrapper was deleted during shutdown.
    for dialog in tuple(getattr(window, "_order_dialogs", ())):
        try:
            dialog.retranslate()
        except RuntimeError:
            continue


def show_video(window):
    """Bring the actual video surface forward without disturbing the camera."""
    sub = window._desktop_windows["video"]
    sub.showNormal()
    window._desktop_mdi.setActiveSubWindow(sub)
    sub.raise_()
    window._desktop_mdi.position_dock()


def hide_video(window):
    window._desktop_windows["video"].hide()


def show_document(window, document, kind="document"):
    """Host a non-modal workspace in MDI, keeping its own closeEvent/consent.

    Order approval is deliberately not embedded here: its application-modal
    confirmation and explicit LIVE acknowledgement remain separate.
    """
    document.setWindowFlags(Qt.WindowType.Widget)
    sub = DocumentWindow(document)
    sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    sub.setWidget(document)
    sub.setWindowTitle(document.windowTitle())
    window._desktop_mdi.addSubWindow(sub)
    window._workspace_document_counter += 1
    doc_id = f"doc-{window._workspace_document_counter}"
    window._workspace_documents[doc_id] = (kind, sub)
    sub.destroyed.connect(lambda *_args, key=doc_id: window._workspace_documents.pop(key, None))
    sub.resize(document.size())
    sub.show()
    window._desktop_mdi.setActiveSubWindow(sub)
    document.show()
    window._desktop_mdi.position_dock()
    return sub


def show_camera(window):
    """Bring a running camera preview forward without altering other media."""
    sub = window._desktop_windows["camera"]
    sub.showNormal()
    window._desktop_mdi.setActiveSubWindow(sub)
    sub.raise_()
    window._desktop_mdi.position_dock()


def hide_camera(window):
    window._desktop_windows["camera"].hide()


def confirm_shutdown(window):
    """Preflight all unsaved work and SSH sessions before stopping any of them."""
    for attr in ("_creative_dialogs", "_image_editors"):
        for document in tuple(getattr(window, attr, ())):
            try:
                if not document._may_discard():
                    return False
            except RuntimeError:
                # A deleted Qt wrapper is not an unsaved document.
                continue
    sessions = []
    for kind, sub in tuple(getattr(window, "_workspace_documents", {}).values()):
        if kind != "ssh_manager":
            continue
        try:
            manager = sub._document
            panels = manager.shutdown_panels()
            if not manager._confirm_close(panels):
                return False
            sessions.extend(panels)
        except RuntimeError:
            continue  # Already deleted by Qt.
    for panel in sessions:
        try:
            panel.disconnect_session()
        except RuntimeError:
            continue
    return True
