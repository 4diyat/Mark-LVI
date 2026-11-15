"""Multitasking desktop shell. Existing panels remain owned by MainWindow.

Only local widgets are constructed here; plugin approval and the assistant's
thread-safe dispatch are still owned by the existing application.
"""
from pathlib import Path

from PyQt6.QtCore import QDir, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QFileSystemModel, QHBoxLayout, QLabel, QLineEdit, QMdiArea,
                             QMdiSubWindow, QPushButton, QScrollArea, QTreeView, QVBoxLayout, QWidget)

from core.i18n import label as _t
from ui.theme import C


class PersistentWindow(QMdiSubWindow):
    """Closing a core panel hides it; its dock button can restore it."""
    def closeEvent(self, event):
        self.hide()
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
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        up = QPushButton(_t("workspace.up"))
        up.clicked.connect(self._up)
        header.addWidget(up)
        self.path = QLineEdit(str(Path.home()))
        self.path.returnPressed.connect(lambda: self.navigate(self.path.text()))
        header.addWidget(self.path, 1)
        layout.addLayout(header)
        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(str(Path.home()))
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setSortingEnabled(True)
        self.view.doubleClicked.connect(self._open)
        layout.addWidget(self.view)
        self.status = QLabel(_t("workspace.files_hint"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.navigate(str(Path.home()))

    def navigate(self, path):
        target = Path(path).expanduser()
        if not target.is_dir():
            self.status.setText(_t("workspace.bad_folder"))
            return
        path = str(target.resolve())
        self.view.setRootIndex(self.model.setRootPath(path))
        self.path.setText(path)
        self.status.setText(_t("workspace.files_hint"))

    def _up(self):
        self.navigate(str(Path(self.path.text()).parent))

    def _open(self, index):
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.navigate(path)
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.status.setText(_t("workspace.open_failed"))


def build(window):
    shell = QWidget()
    shell.setObjectName("WorkspaceShell")
    shell.setStyleSheet(f"""
        QWidget#WorkspaceShell {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 #06142c, stop:0.55 #073847, stop:1 #071127); }}
        QMdiArea {{ background: transparent; border: none; }}
        QMdiSubWindow {{ background: {C.PANEL}; border: 1px solid {C.BORDER_B}; }}
        QPushButton#DockButton {{ color: {C.WHITE}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 8px; padding: 7px 10px; }}
        QPushButton#DockButton:hover {{ border-color: {C.PRI}; }}
    """)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(8, 6, 8, 8)
    layout.setSpacing(6)
    mdi = QMdiArea()
    mdi.setViewMode(QMdiArea.ViewMode.SubWindowView)
    mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    mdi.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    layout.addWidget(mdi, 1)
    window._desktop_mdi = mdi
    window._desktop_windows = {}

    def add(name, widget, title):
        sub = PersistentWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(_t(title))
        mdi.addSubWindow(sub)
        window._desktop_windows[name] = sub
        return sub

    add("chat", window._right_panel, "workspace.chat").show()
    add("assistant", window._assistant_panel, "workspace.assistant").show()
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
    row = QHBoxLayout(dock)
    row.setContentsMargins(4, 0, 4, 0)
    row.addStretch(1)
    buttons = (("workspace.chat", lambda: focus("chat")),
               ("workspace.assistant", lambda: focus("assistant")),
               ("workspace.video", lambda: focus("video")),
               ("workspace.camera", lambda: focus("camera")),
               ("workspace.files", lambda: focus("files")),
               ("workspace.code", lambda: creative("editor")),
               ("workspace.image", image_editor),
               ("workspace.ai_image", lambda: creative("canvas")),
               ("workspace.trading", trading),
               ("workspace.order", order),
               ("workspace.navigation", lambda: focus("navigation")),
               ("desktop.plugins", window._open_plugin_manager),
               ("desktop.settings", lambda: window._drawer_btn.click()))
    window._workspace_dock = []
    for key, action in buttons:
        button = QPushButton(_t(key))
        button.setObjectName("DockButton")
        button.clicked.connect(lambda checked=False, fn=action: fn())
        row.addWidget(button)
        window._workspace_dock.append((button, key))
    row.addStretch(1)
    dock_scroll = QScrollArea()
    dock_scroll.setWidgetResizable(True)
    dock_scroll.setWidget(dock)
    dock_scroll.setFixedHeight(58)
    dock_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    dock_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    dock_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    layout.addWidget(dock_scroll)

    def position_initial():
        width = max(mdi.viewport().width(), 800)
        height = max(mdi.viewport().height(), 500)
        chat, assistant, nav = (window._desktop_windows[k] for k in ("chat", "assistant", "navigation"))
        chat.setGeometry(18, 18, max(340, int(width * .47)), max(340, height - 38))
        assistant.setGeometry(max(370, int(width * .50)), 18,
                              max(300, int(width * .47) - 18), max(340, height - 38))
        nav.resize(240, max(350, min(height - 40, 700)))
        chat.show()
        assistant.show()
        nav.hide()
    QTimer.singleShot(0, position_initial)
    return shell


def retranslate(window):
    for button, key in getattr(window, "_workspace_dock", ()):
        button.setText(_t(key))
    for name, key in (("chat", "workspace.chat"), ("assistant", "workspace.assistant"),
                      ("navigation", "workspace.navigation"), ("files", "workspace.files"),
                      ("video", "workspace.video"), ("camera", "workspace.camera")):
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


def show_document(window, document):
    """Host a non-modal workspace in MDI, keeping its own closeEvent/consent.

    Order approval is deliberately not embedded here: its application-modal
    confirmation and explicit LIVE acknowledgement remain separate.
    """
    document.setWindowFlags(Qt.WindowType.Widget)
    sub = QMdiSubWindow()
    sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    sub.setWindowTitle(document.windowTitle())
    sub.setWidget(document)
    window._desktop_mdi.addSubWindow(sub)
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
