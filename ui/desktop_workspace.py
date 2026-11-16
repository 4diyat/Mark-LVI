"""Multitasking desktop shell. Existing panels remain owned by MainWindow.

Only local widgets are constructed here; plugin approval and the assistant's
thread-safe dispatch are still owned by the existing application.
"""
from pathlib import Path

from PyQt6.QtCore import QDir, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (QBrush, QColor, QDesktopServices, QFileSystemModel, QIcon,
                         QLinearGradient, QPainter, QPixmap)
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMdiArea,
                             QMdiSubWindow, QMenu, QPushButton, QScrollArea, QSizeGrip, QStyle, QToolButton,
                             QTreeView, QVBoxLayout, QWidget)

from core.i18n import label as _t
from ui.theme import C


class WallpaperArea(QMdiArea):
    """Scale the original wallpaper to cover the desktop, not the app windows."""
    def __init__(self):
        super().__init__()
        self._wallpaper = QPixmap(str(Path(__file__).resolve().parent.parent / "assets/workspace/aurora.png"))
        self._dock = None

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


class FileBrowser(QWidget):
    """Read-only navigation; opening files delegates to the user's OS."""
    def __init__(self):
        super().__init__()
        self.setObjectName("WorkspaceFiles")
        self.setStyleSheet(f"""
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
            QPushButton:hover {{ background: {C.DESKTOP_DOCK}; }}
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QWidget()
        sidebar.setFixedWidth(145)
        sidebar.setStyleSheet(f"background: {C.DESKTOP_SIDEBAR};")
        favorites = QVBoxLayout(sidebar)
        favorites.setContentsMargins(10, 12, 10, 10)
        favorites.addWidget(QLabel(_t("workspace.favorites")))
        home = Path.home()
        for key, folder in (("workspace.home", home), ("workspace.desktop", home / "Desktop"),
                            ("workspace.documents", home / "Documents"), ("workspace.downloads", home / "Downloads")):
            button = QPushButton(_t(key))
            button.setEnabled(folder.is_dir())
            button.clicked.connect(lambda checked=False, target=folder: self.navigate(str(target)))
            favorites.addWidget(button)
        favorites.addStretch(1)
        root.addWidget(sidebar)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        header = QHBoxLayout()
        up = QPushButton(_t("workspace.up"))
        up.clicked.connect(self._up)
        header.addWidget(up)
        self.path = QLineEdit(str(home))
        self.path.returnPressed.connect(lambda: self.navigate(self.path.text()))
        header.addWidget(self.path, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("workspace.search"))
        self.search.setMaximumWidth(170)
        self.search.textChanged.connect(self._filter)
        header.addWidget(self.search)
        layout.addLayout(header)
        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setNameFilterDisables(False)
        self.model.setRootPath(str(home))
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.doubleClicked.connect(self._open)
        layout.addWidget(self.view, 1)
        self.status = QLabel(_t("workspace.files_hint"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        root.addWidget(content, 1)
        self.navigate(str(home))

    def _filter(self, text):
        # QFileSystemModel applies these patterns to files; directories remain
        # navigable. This never alters or sends a user's files.
        text = text.strip()
        self.model.setNameFilters([f"*{text}*"] if text else [])

    def navigate(self, path):
        target = Path(path).expanduser()
        if not target.is_dir():
            self.status.setText(_t("workspace.bad_folder"))
            return False
        path = str(target.resolve())
        self.view.setRootIndex(self.model.setRootPath(path))
        self.path.setText(path)
        self.status.setText(_t("workspace.files_hint"))
        return True

    def _up(self):
        self.navigate(str(Path(self.path.text()).parent))

    def _open(self, index):
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.navigate(path)
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.status.setText(_t("workspace.open_failed"))


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
    file_x = max(0, int(width * .045))
    file_y = max(0, int(height * .10))
    file_w = max(1, int(width * (.45 if width >= 1100 else .48)))
    file_h = max(1, min(int(height * .66), floor - file_y))
    assistant_w = max(1, min(max(320, int(width * .29)), width))
    assistant_x = min(int(width * .65), width - assistant_w)
    assistant_y = max(0, int(height * .12))
    assistant_h = max(1, min(max(400, int(height * .72)), floor - assistant_y))
    return (file_x, file_y, file_w, file_h), (assistant_x, assistant_y, assistant_w, assistant_h)


def build(window):
    shell = QWidget()
    shell.setObjectName("WorkspaceShell")
    shell.setStyleSheet(f"""
        QWidget#WorkspaceShell {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 #06142c, stop:0.55 #073847, stop:1 #071127); }}
        QMdiArea {{ border: none; }}
        QMdiSubWindow {{ background: {C.DESKTOP_PANEL}; border: 1px solid {C.DESKTOP_BORDER}; }}
        QMdiSubWindow::title {{ background: {C.DESKTOP_SIDEBAR}; color: {C.DESKTOP_TEXT};
                               padding: 5px; }}
        QWidget#DesktopDock {{ background: {C.DESKTOP_DOCK}; border: 1px solid {C.DESKTOP_BORDER};
                               border-radius: 15px; }}
        QToolButton#DockButton {{ color: {C.DESKTOP_TEXT}; background: transparent;
            border: none; border-radius: 8px; padding: 4px; }}
        QToolButton#DockButton:hover {{ background: {C.DESKTOP_SIDEBAR}; }}
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

    def open_handboard():
        if "handboard" not in window._desktop_windows:
            from ui.hand_board import HandBoard
            board = HandBoard(window)
            sub = PersistentWindow()
            sub.setWidget(board)
            sub.setWindowTitle(_t("handboard.title"))
            mdi.addSubWindow(sub)
            sub.resize(900, 600)
            window._hand_board = board
            window._desktop_windows["handboard"] = sub
        sub = window._desktop_windows["handboard"]
        sub.showNormal()
        mdi.setActiveSubWindow(sub)
        sub.raise_()
        mdi.position_dock()
        return sub

    window._open_handboard = open_handboard

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
            if name == "chat":
                window._input.setFocus()

    def creative(tab):
        from ui.creative import open_workspace
        open_workspace(window, {"kind": "creative_workspace", "tab": tab})

    def trading():
        from ui.trading_terminal import open_terminal
        open_terminal(window, {"kind": "trading_terminal"})

    def image_editor():
        from ui.image_editor import open_editor
        open_editor(window, {})

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
        ("workspace.editors", "SP_FileIcon", (("workspace.code", lambda: creative("editor")),
                                                ("workspace.image", image_editor),
                                                ("workspace.ai_image", lambda: creative("canvas")))),
        ("workspace.media", "SP_MediaPlay", (("workspace.video", lambda: focus("video")),
                                                 ("workspace.camera", lambda: focus("camera")))),
        ("workspace.trading", "SP_FileDialogInfoView", (("workspace.trading", trading),
                                                           ("workspace.order", order))),
        ("workspace.apps", "SP_TitleBarMenuButton", (("handboard.title", open_handboard),
                                                         ("workspace.navigation", lambda: focus("navigation")),
                                                         ("desktop.plugins", window._open_plugin_manager))),
        ("desktop.settings", "SP_FileDialogListView", lambda: window._drawer_btn.click()),
    )
    window._workspace_dock = []
    window._workspace_dock_actions = []
    colors = (C.DOCK_BLUE, C.DOCK_TEAL, C.DOCK_GREEN, C.DOCK_PURPLE,
              C.DOCK_ORANGE, C.DOCK_CHARCOAL, C.DOCK_CHARCOAL)
    for (key, icon, action), color in zip(buttons, colors):
        button = QToolButton()
        button.setText(_t(key))
        button.setObjectName("DockButton")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIcon(dock_icon(window.style(), icon, color))
        button.setIconSize(QSize(44, 44))
        button.setMinimumWidth(64)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if isinstance(action, tuple):
            menu = QMenu(button)
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
    for action, key in getattr(window, "_workspace_dock_actions", ()):
        action.setText(_t(key))
    for name, key in (("assistant", "workspace.assistant"),
                      ("navigation", "workspace.navigation"), ("files", "workspace.files"),
                      ("video", "workspace.video"), ("camera", "workspace.camera"), ("handboard", "handboard.title")):
        sub = getattr(window, "_desktop_windows", {}).get(name)
        if sub:
            sub.setWindowTitle(_t(key))


def show_video(window):
    """Bring the actual video surface forward without disturbing the camera."""
    sub = window._desktop_windows["video"]
    sub.showNormal()
    window._desktop_mdi.setActiveSubWindow(sub)
    sub.raise_()


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
    return sub


def show_camera(window):
    """Bring a running camera preview forward without altering other media."""
    sub = window._desktop_windows["camera"]
    sub.showNormal()
    window._desktop_mdi.setActiveSubWindow(sub)
    sub.raise_()


def hide_camera(window):
    window._desktop_windows["camera"].hide()


def confirm_shutdown(window):
    """Ask before losing unsaved editor contents when the main window closes."""
    for attr in ("_creative_dialogs", "_image_editors"):
        for document in tuple(getattr(window, attr, ())):
            try:
                if not document._may_discard():
                    return False
            except RuntimeError:
                # A deleted Qt wrapper is not an unsaved document.
                continue
    return True
