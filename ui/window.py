from __future__ import annotations

import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

# Qt's video backend prints the ffmpeg stream banner — codec, bitrate, the
# whole signed googlevideo URL — to the console for every stream it opens. That
# is two screenfuls per video, it looks like an error to anyone reading the log,
# and it puts a URL carrying the viewer's IP address into a terminal people
# paste into bug reports. Silenced here, before Qt initialises its logging.
# An explicit setting from the user is left alone.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

# Only what this file uses. The list used to carry QEasingCurve, QMimeData,
# QObject, QParallelAnimationGroup, QPropertyAnimation, QRect, QSize,
# QFontDatabase, QLinearGradient and QPainterPath, none of which appear
# anywhere below — the leftovers of replaced animation code. They cost nothing
# at runtime (PyQt6 loads them for the classes that ARE used) and they cost a
# reader: an import that suggests a feature that is not there.
from PyQt6.QtCore import (
    QPointF, QPoint, QRectF, QSizeF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QCursor, QDragEnterEvent, QDropEvent, QFont,
    QKeySequence, QPainter, QPen, QPixmap, QShortcut,
)
# Video playback for the HUD. Part of PyQt6, so it costs no new dependency —
# but the multimedia plugins are a separate piece of the Qt install and can be
# absent on a stripped-down system, so a failure here disables one feature
# rather than stopping JARVIS from starting.
try:
    from PyQt6.QtMultimedia import QAudioDevice, QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
    HAVE_VIDEO = True
except Exception as _e:            # noqa: BLE001 - reported, never fatal
    QAudioDevice = QAudioOutput = QMediaPlayer = QGraphicsVideoItem = None
    HAVE_VIDEO = False
    print(f"[Video] playback unavailable ({_e}) — the HUD will not show video.")

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMainWindow, QPushButton, QSizePolicy, QSplitter,
    QGraphicsScene, QGraphicsView,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)
try:
    from core.avatar import HoloAvatar
except Exception:      # pragma: no cover — HUD must never die over cosmetics
    HoloAvatar = None

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

def _read_full_config() -> dict:
    """The whole config dict, through `memory/config_manager`. {} on any error.

    WHY NOT `API_FILE.read_text()`
        That is what this did, and it is how the window ended up with a second
        opinion about a file that `memory/config_manager.py` owns: no
        last-good-copy when the JSON is half-written, no shared cache, and a
        read that bypasses anything the manager does later. The manager already
        promises never to raise and to return {} when there is nothing stored,
        which is exactly this function's contract.
    """
    try:
        from memory.config_manager import load_api_keys
        return load_api_keys() or {}
    except Exception:
        return {}

# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
APP_VERSION  = "MARK LVI"
APP_PROTOCOL = APP_VERSION.split()[-1]

_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 170

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# ── the colours and the samplers live in ui/ ────────────────────────────────
#
#     `ui/theme.py` owns the palette (and is the only module that may assign to
#     `C`); `ui/metrics.py` owns the sampler thread. Both are re-exported by the
#     package, and imported here because this file reads them on nearly every
#     line. The long comment that used to sit here — about why the split was
#     worth doing — is in `ui/__init__.py`, where a reader of the package starts.
from ui.desktop_layout import set_assistant_tool
from ui.theme import (          # noqa: F401 — re-exported through the package
    C,
    DEFAULT_UI_COLOR,
    _HUE_LINKED,
    _PALETTE_DEFAULTS,
    apply_ui_accent,
    current_palette,
    qcol,
    retheme_all_widgets,
)
from ui.metrics import (        # noqa: F401 — same object as ui/metrics._metrics
    _SysMetrics,
    _metrics,
    _nvml_gpu_windows,
)
# The three panels that float over the HUD and exist only to set something.
# They moved to their own module because they were the translation work's
# blocking point (a panel that must re-render by hand cannot find its own
# labels) and because this file was at its size ceiling with the language row
# still unwritten. Re-exported through the package, so `ui.CustomizeOverlay`
# and every plugin that names it keep working.
from ui.audio import AudioMixin
from ui.video_fallback import VideoFallbackMixin
from ui.audio_devices import (      # noqa: F401 — re-exported through the package
    AudioDeviceOverlay,
)
from ui.hud_canvas import HudCanvas   # noqa: F401 — re-exported
from ui.icons import build_jarvis_icon
from ui.hud_panels import (        # noqa: F401 — re-exported through the package
    ClipboardPanel,
    MemoryOverlay,
)
from ui.confirm_banner import (   # noqa: F401 — re-exported through the package
    ConfirmBanner,
    _HudOverlay,
)
from ui.remote_keys import (        # noqa: F401 — re-exported through the package
    RemoteKeyOverlay,
)
from ui.providers_overlay import (  # noqa: F401 — re-exported through the package
    ProvidersOverlay,
    _ScrollSafeCombo,
)
from ui.overlays import (      # noqa: F401 — re-exported through the package
    CustomizeOverlay,
    HueWheel,
    PluginManagerOverlay,
    PluginSettingsOverlay,
)
# The words the window shows. Imported by NAME rather than as `i18n.label(...)`
# so every translated string here can be found with one grep, and so the test
# that checks the call sites is checking the function that actually runs.
#
# `_t` and not `label` because this file already uses `label` as a loop
# variable in three places (the OS buttons, the model dropdown, the quick-action
# row). Renaming the import instead of those three is not laziness: a name that
# shadows a translation helper at runtime is a bug waiting for the next edit,
# and `from core.i18n import label as _t` makes the collision impossible.
from core import playback as _pb
from core.display_name import assistant_display as _assistant_display
from core.i18n import active_locale as i18n_active, label as _t, set_locale



class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

# Re-exported here for existing UI and plugin imports.
from ui.chat_log import LogWidget

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
    "folder":  ("📁", "#ffcc00"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    if path.is_dir():
        return "folder"
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

# Folders nobody means when they say "this project": dependencies, build output,
# version control. The same list dev_agent skips, so the count on the card is
# the count of files the coding model will actually look at.
_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env",
              "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build",
              ".idea", ".vscode", ".next", "target", ".jarvis_backup"}

def _count_files(folder: Path, cap: int = 5000) -> int:
    """Files in a project folder, stopping at `cap` — a whole drive dropped by
    mistake must not freeze the window while it is counted."""
    import os
    n = 0
    for _root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        n += len(files)
        if n >= cap:
            return cap
    return n

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"

class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._folder_files = 0
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file() or Path(path).is_dir():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        # Qt has no single dialog that picks "a file or a folder", so the click
        # asks which — a folder is what the coding model works on.
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {C.DARK}; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER_B}; font-family: 'Courier New'; }}"
            f"QMenu::item {{ padding: 6px 18px; }}"
            f"QMenu::item:selected {{ background: {C.PRI_GHO}; }}")
        pick_file = menu.addAction("📄  Choose a file…")
        pick_dir = menu.addAction("📁  Choose a folder…  (for coding)")
        chosen = menu.exec(QCursor.pos())
        if chosen is pick_dir:
            path = QFileDialog.getExistingDirectory(
                self, _t("dialog.pick_project", name=_assistant_display()),
                str(Path.home()))
            if path:
                self._set_file(path)
            return
        if chosen is not pick_file:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, _t("dialog.pick_file", name=_assistant_display()),
            str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._folder_files = _count_files(Path(path)) if Path(path).is_dir() else 0
        self._canvas.update()
        self.file_selected.emit(path)

class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop a file or folder  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Project folders")

    def _paint_drag_over(self, p, W, H):
        cy = H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        try:
            size_str = _fmt_size(path.stat().st_size)
        except OSError:                       # moved or deleted since loading
            size_str = "gone"
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"
        if cat == "folder":
            n = self._z._folder_files
            ext_str, size_str = "FOLDER", f"{n}{'+' if n >= 5000 else ''} files"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)

class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel(_t("ui.visual_input"))
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont("Courier New", 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s

class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl(_t("setup.heading"), 13, True))
        layout.addWidget(_lbl(_t("setup.intro"), 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl(_t("setup.api_key"), 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText(_t("ui.placeholder.key"))
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl(_t("setup.os"), 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, os_name in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(os_name)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton(_t("init.button"))
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)









class MainWindow(VideoFallbackMixin, AudioMixin, QMainWindow):
    _log_sig        = pyqtSignal(str)
    _speech_caption_sig = pyqtSignal(object)
    _phone_connected_sig = pyqtSignal()
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _codejob_sig    = pyqtSignal(object)     # dev_agent job state — live coding panel
    _plugins_ready_sig = pyqtSignal()  # registry can be supplied from a worker thread
    _ssh_assist_sig = pyqtSignal(object)
    _editor_assist_sig = pyqtSignal(object)
    _workspace_command_sig = pyqtSignal(object)  # worker request, completed on Qt thread
    _visual_content_sig = pyqtSignal(object)
    _narrative_content_sig = pyqtSignal(object)
    _browser_read_sig = pyqtSignal(object)
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _video_open_sig  = pyqtSignal(str, str, bool, str, object, object)  # video, title, muted, audio, fallbacks, on_exhausted
    _wake_btns_sig   = pyqtSignal()          # wake state resolved off-thread
    _ptt_shortcut_sig = pyqtSignal(bool)
    _video_close_sig = pyqtSignal()
    _video_mute_sig  = pyqtSignal(bool)
    # Audio playback — a file, a stream URL, or YouTube audio. Separate from the
    # video surface on purpose: sound is played where the assistant speaks from
    # (the `output` device the user chose), not where a video would be drawn, so
    # the two cannot fight over the same device.
    _audio_open_sig  = pyqtSignal(str, str, float, bool, object, object)   # source, title, volume, loop, fallbacks, on_exhausted
    _audio_stop_sig  = pyqtSignal()
    _audio_pause_sig = pyqtSignal(bool)
    _audio_vol_sig   = pyqtSignal(float)
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _hand_menu_sig  = pyqtSignal(object)     # menu target captured on gesture thread
    _confirm_sig    = pyqtSignal(str, str, str)  # request ID, title, detail
    _confirm_hide_sig = pyqtSignal(str)        # request ID
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _quiz_sig       = pyqtSignal(str, object, object)  # (topic, questions, grader)
    _quiz_hide_sig  = pyqtSignal()
    _review_sig     = pyqtSignal(str, str, object, object)  # document review payload

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path
        self._ui_thread_id = threading.get_ident()

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "JARVIS").strip()
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        # The locale is settled before the first label is read, so the very
        # first paint is already in the user's language. 'auto' means ask the
        # OS; a failure to read the setting falls back to the same thing rather
        # than to English, because the OS knows more about the user than we do.
        try:
            from memory.config_manager import get_ui_language
            _pref = get_ui_language()
            set_locale(_pref if _pref != "auto" else None)
        except Exception as e:   # noqa: BLE001 — reported, never fatal
            print(f"⚠ i18n: could not read the language setting ({e})")
            set_locale(None)
        self.setWindowTitle(f"{_display} — {APP_VERSION}")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop JARVIS mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by JarvisLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by JarvisLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by JarvisLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.on_push_to_talk   = None   # callable: (enable: bool) -> str scope
        self.ptt_hold          = None   # callable: (held: bool) -> None — windowed chord
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None

        central = QWidget()
        central.setObjectName("DesktopRoot")
        central.setStyleSheet(f"QWidget#DesktopRoot {{ background: {C.BG}; }}")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()
        self._quiz_panel = self._build_quiz_panel()

        # Live camera container is hosted separately by the desktop workspace.
        _cam_cont = QWidget()
        self._camera_cont = _cam_cont
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel(_t("ui.camera.heading"))
        _cam_title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton(_t("ui.close_x"))
        _cam_x.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # ── Video surface ────────────────────────────────────────────────
        # The video widget is hosted separately by the desktop workspace, so
        # starting or stopping video does not interrupt the camera/HUD stack.
        self._video_split = False        # is the sound a separate stream?
        self._video_auto_muted = False   # did JARVIS close the mic, or the user?
        # A plain flag rather than reading the widget. video_is_playing() is
        # called from plugin threads, and reading a widget's state from one is
        # not something to rely on; an attribute is.
        self._video_on = False
        # Set when the picture reached its end, and when the separate soundtrack
        # failed on its own. Both are read by the mute button and by the status
        # handler; neither is inferable from the player after the fact.
        self._video_ended = False
        self._video_sound_failed = False
        self._init_video_fallback()
        self._video_cont = QWidget()
        self._video_cont.setStyleSheet(f"background: {C.BG};")
        _vid_v = QVBoxLayout(self._video_cont)
        _vid_v.setContentsMargins(8, 6, 8, 8)
        _vid_v.setSpacing(4)

        _vid_hdr = QHBoxLayout()
        self._video_title = QLabel(_t("ui.video.heading"))
        self._video_title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._video_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _vid_hdr.addWidget(self._video_title)
        _vid_hdr.addStretch()

        def _vid_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_DIM}; background: transparent;
                    border: none; padding: 2px 6px;
                }}
                QPushButton:hover {{ color: {C.PRI}; }}
            """)
            return b

        # Muted is the default and the button says so, because a soundtrack
        # talking over JARVIS is the one way this feature could make the
        # assistant worse rather than better.
        self._video_mute_btn = _vid_btn(_t("ui.video.sound_off"))
        self._video_mute_btn.clicked.connect(self._toggle_video_mute)
        _vid_hdr.addWidget(self._video_mute_btn)

        _vid_x = _vid_btn(_t("ui.close_x"))
        _vid_x.clicked.connect(self.stop_video)
        _vid_hdr.addWidget(_vid_x)
        _vid_v.addLayout(_vid_hdr)
        # The audio bar is built by ui/audio.py — see that module for why.
        self._build_audio_bar(_vid_btn)

        if HAVE_VIDEO:
            # A GRAPHICS ITEM, NOT A QVideoWidget.
            #
            # QVideoWidget gets a native window of its own, and a native window
            # is painted by the compositor above every ordinary widget that
            # shares the screen with it — so the settings drawer opened
            # *underneath* the video and raise_() could not help, because the
            # two are not in the same painting order at all. A video item drawn
            # into a QGraphicsView goes through Qt's own painter like any other
            # widget, and anything laid over it stays over it.
            self._video_scene = QGraphicsScene(self)
            self._video_item = QGraphicsVideoItem()
            self._video_scene.addItem(self._video_item)
            self._video_widget = QGraphicsView(self._video_scene)
            self._video_widget.setStyleSheet("background: #000; border: none;")
            self._video_widget.setFrameShape(QGraphicsView.Shape.NoFrame)
            self._video_widget.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            _vid_v.addWidget(self._video_widget, stretch=1)

            self._video_audio = QAudioOutput()
            self._video_audio.setMuted(True)
            self._video_player = QMediaPlayer()
            self._video_player.setVideoOutput(self._video_item)
            # Keep the picture filling the view as the window is resized.
            self._video_item.nativeSizeChanged.connect(self._fit_video)
            self._video_player.setAudioOutput(self._video_audio)
            self._video_player.errorOccurred.connect(self._on_video_error)
            # NOTHING USED TO LISTEN FOR THIS. When a video reached its end the
            # HUD stayed on the last frame, `video_is_playing()` kept answering
            # yes, the resync timer kept running — and if the sound had been on,
            # the microphone JARVIS closed for it stayed closed. JARVIS was deaf
            # for the rest of the session, with no video on screen and nothing
            # anywhere saying why.
            self._video_player.mediaStatusChanged.connect(self._on_video_status)

            # A SECOND player, for sound that arrives separately.
            #
            # YouTube no longer serves a single stream carrying both picture and
            # sound — not for new uploads and not for old ones; checked against
            # three videos including the oldest on the site, and every one of
            # them offered zero combined formats. Picture and sound are two
            # URLs, so they are two players, started together and nudged back
            # into line by the timer below.
            #
            # A local file or a direct video URL still uses the first player
            # alone: one stream, one player, nothing to synchronise.
            self._video_sound = QMediaPlayer()
            self._video_sound_out = QAudioOutput()
            self._video_sound_out.setMuted(True)
            self._video_sound.setAudioOutput(self._video_sound_out)
            # The soundtrack is the stream that CAN fail on its own — it is a
            # second URL, resolved separately, and YouTube rotates its
            # signatures. Without this connection a failure here produced a
            # silent video whose bar still said SOUND ON, which is
            # indistinguishable from a video that simply has no audio.
            self._video_sound.errorOccurred.connect(self._on_video_sound_error)

            self._video_sync = QTimer(self)
            self._video_sync.setInterval(1000)
            self._video_sync.timeout.connect(self._sync_video_sound)

            # Audio playback. Its own player and its own output on purpose: a
            # song must not be able to take the video surface, and the two
            # outputs are different devices.
            self._audio_player = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._audio_player.setAudioOutput(self._audio_out)
            self._audio_player.errorOccurred.connect(self._on_audio_error)
            self._audio_player.mediaStatusChanged.connect(self._on_audio_status)
            self._apply_audio_device()
        else:
            self._video_scene = None
            self._video_item = None
            self._video_widget = None
            self._video_player = None
            self._video_audio = None
            self._video_sound = None
            self._video_sound_out = None
            self._video_sync = None
            self._audio_player = None
            self._audio_out = None
            _miss = QLabel(_t("ui.video.unavailable"))
            _miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _miss.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            _vid_v.addWidget(_miss, stretch=1)

        if HAVE_VIDEO:
            from ui.video_controls import install as install_video_controls
            install_video_controls(self, _vid_v)

        # Keep the HUD stack for existing assistant panel logic. Camera and video
        # each have their own desktop surface.
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)

        # The audio strip is a SECTION OF THE SPLITTER, and it is here because
        # the previous home was not a home at all.
        #
        # It used to be put in a wrapper widget that was never added to any
        # layout — and worse, the HUD stack was added to that wrapper and then
        # added to the splitter, which MOVES a widget rather than copying it, so
        # the wrapper was left holding only the audio bar while nothing
        # displayed it. "Play some music" answered "playing", the log agreed,
        # and no bar appeared anywhere. No test could see it: this file was
        # never imported by one, and the player itself worked perfectly.
        #
        # Not inside the content panel either: that panel is hidden by default
        # and a widget cannot be visible inside a hidden parent, and its close
        # button would then hide the song with it. A splitter section owns its
        # own visibility, hides itself when nothing plays, and gives back the
        # height it took.
        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._content_panel)
        self._center_split.addWidget(self._quiz_panel)
        # Last, so the song is the bottom strip and never pushes the HUD up.
        self._center_split.addWidget(self._audio_cont)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setStretchFactor(1, 1)
        self._center_split.setCollapsible(0, False)
        # Conversation is the primary surface; the avatar and real tool/media
        # workspace remain together in the assistant column.
        self._right_panel = self._build_right_panel()
        from ui.desktop_layout import build_assistant_panel
        self._assistant_panel = build_assistant_panel(self)
        from ui.desktop_workspace import build as build_desktop_workspace
        body.addWidget(build_desktop_workspace(self), stretch=1)

        root.addLayout(body, stretch=1)
        # Keyboard shortcuts remain available; the workspace itself has no
        # large footer bar, leaving the dock at the bottom like the mockup.
        self._desktop_footer = self._build_footer()
        self._desktop_footer.hide()
        root.addWidget(self._desktop_footer)

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._ctrl_drawer = self._build_controls_drawer()
        self._warm_wake_state()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._speech_caption_sig.connect(self._speech_caption.handle)
        self._phone_connected_sig.connect(self.notify_phone_connected)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._codejob_sig.connect(self._show_code_job)
        from ui.desktop_workspace import open_initial_editor
        self._plugins_ready_sig.connect(lambda: open_initial_editor(self))
        self._workspace_command_sig.connect(self._execute_workspace_command)
        self._visual_content_sig.connect(self._open_visual_content)
        self._narrative_content_sig.connect(self._open_narrative_content)
        self._editor_assist_sig.connect(self._execute_editor_assist)
        self._ssh_assist_sig.connect(self._execute_ssh_assist)
        self._browser_read_sig.connect(self._execute_browser_read)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._wake_btns_sig.connect(self._refresh_wake_btns)
        self._ptt_shortcut_sig.connect(self._apply_ptt_shortcut)
        self._video_open_sig.connect(self._on_video_open)
        self._video_close_sig.connect(self._on_video_close)
        self._video_mute_sig.connect(self._on_video_mute)
        self._audio_open_sig.connect(self._on_audio_open)
        self._audio_stop_sig.connect(self._on_audio_stop)
        self._audio_pause_sig.connect(self._on_audio_pause)
        self._audio_vol_sig.connect(self._on_audio_volume)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._quiz_sig.connect(self._show_quiz)
        self._quiz_hide_sig.connect(self._hide_quiz)
        self._review_sig.connect(self._show_review)
        self._cam_stop = threading.Event()
        self._cam_start_lock = threading.Lock()
        self._cam_thread = None
        self._camera_active = False
        from ui.hand_gesture import setup as setup_hand_gesture
        setup_hand_gesture(self)

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._setup_saved = False   # set by _on_setup_done; read by _on_setup_closed
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        # ── the shortcut that brings the interface back ──────────────────────
        # Window-scoped, so it needs the window focused — which is fine for the
        # mode it exists to serve: getting OUT of a window you already have
        # focus in. Getting back IN, with no window to focus, cannot be done
        # from a Qt shortcut at all and is the tray's job (see ui/tray.py).
        #
        # Ctrl+Shift+J rather than Ctrl+J, which is the browser's downloads
        # panel and a common editor binding; the extra modifier is what makes it
        # safe to install without asking.
        sc_hide = QShortcut(QKeySequence("Ctrl+Shift+J"), self)
        sc_hide.activated.connect(self._put_interface_away)

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    def _execute_ssh_assist(self, request):
        from ui.ssh_assist import execute
        execute(self, request)

    def _execute_editor_assist(self, request):
        from ui.editor_assist import execute
        execute(self, request)

    def _execute_browser_read(self, request):
        from ui.browser_read import execute
        execute(self, request)

    def _open_narrative_content(self, request):
        from ui.visual_bridge import open_content
        open_content(self, 'narrative', request)

    def _open_visual_content(self, request):
        from ui.visual_bridge import open_content
        open_content(self, 'chart', request)

    def _execute_workspace_command(self, request):
        """Run on the Qt thread and always return an explicit outcome."""
        if not request.claim():
            return
        try:
            from ui.workspace_commands import execute
            request.finish(execute(self, request.command))
        except Exception as exc:
            request.finish({"ok": False, "message": f"Workspace command failed: {exc}"})

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    def closeEvent(self, event):
        from ui.desktop_workspace import confirm_shutdown

        # CLOSING THE WINDOW IN AMBIENT MODE MEANS "PUT IT AWAY".
        #
        # With a tray icon there is still a way back, so a close that ended the
        # whole session would be a surprise: the user dismissed a window and
        # lost the assistant. Hide instead, and let the tray's Quit item be the
        # thing that ends the program. Without a tray there is no way back, so
        # the old behaviour stands.
        host = getattr(self, "_shell", None)
        if host is not None and getattr(host, "tray_available", False):
            if not confirm_shutdown(self):
                event.ignore()
                return
            self.stop_camera_stream()
            self._on_video_close()
            event.ignore()
            host.dismiss()
            return

        if not confirm_shutdown(self):
            event.ignore()
            return
        self.stop_camera_stream()
        self._on_video_close()
        super().closeEvent(event)

    # --- Live camera stream in its desktop panel ----------------------------
    def _on_cam_stream(self, start: bool) -> None:
        from ui.desktop_workspace import hide_camera, show_camera
        # A queued "started" signal can arrive after the user requested stop.
        if start and self._cam_stop.is_set():
            return
        self._camera_active = bool(start)
        if start:
            show_camera(self)
        else:
            hide_camera(self)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        with self._cam_start_lock:
            if self._cam_thread is not None and self._cam_thread.is_alive():
                return
            self._cam_stop.clear()
            self._cam_thread = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
            self._cam_thread.start()

    def _cam_loop(self) -> None:
        from core import camera_lease
        if not camera_lease.acquire():
            self._log_sig.emit("ERR: Camera is busy; stop the other camera feature first.")
            self._cam_stream_sig.emit(False)
            return
        cap = None
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                cfg = _read_full_config()
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self._log_sig.emit("ERR: Could not open the camera.")
                return
            # Do not claim the feed is running until the device opened, and
            # honour a stop requested while initialization was in progress.
            for _ in range(5):
                if self._cam_stop.is_set():
                    return
                cap.read()
            if self._cam_stop.is_set():
                return
            self._cam_stream_sig.emit(True)
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            try:
                if cap is not None:
                    cap.release()
            finally:
                camera_lease.release()
                self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # --- Video in its independent desktop window -----------------------------
    #
    # Everything below runs on the Qt thread. Plugins and the assistant reach it
    # through the signals above, the same way every other panel is driven, so a
    # background thread never touches a widget.

    def _fit_video(self, *_a) -> None:
        """Size the picture to the panel, keeping its shape."""
        if not (self._video_item and self._video_widget):
            return
        try:
            native = self._video_item.nativeSize()
            if native.isEmpty():
                return
            view = self._video_widget.viewport().size()
            scale = min(view.width() / native.width(),
                        view.height() / native.height())
            w, h = native.width() * scale, native.height() * scale
            self._video_item.setSize(QSizeF(w, h))
            self._video_scene.setSceneRect(0, 0, w, h)
            self._video_widget.centerOn(self._video_item)
        except Exception:
            pass


    def _set_video_muted(self, muted: bool) -> None:
        """Silence whichever output is carrying the sound for this video."""
        muted = bool(muted)
        if self._video_audio:
            # When the sound is a separate stream this player has none, but
            # muting it too costs nothing and keeps the two paths identical.
            self._video_audio.setMuted(muted)
        if self._video_sound_out:
            self._video_sound_out.setMuted(muted)
        self._sync_video_mute_btn()
        self._sync_mic_for_video()


    def _sync_mic_for_video(self) -> None:
        """Close the microphone while the video is making sound.

        JARVIS subtracts its OWN output from the microphone — that is what
        core/echo.py does — but a video plays through a different output
        entirely, so the guard has never heard of it and the assistant answers
        the film. There is no arrangement in which an open microphone and a
        loudspeaker in the same room do not do that.

        So the microphone closes for exactly as long as the sound is on, and
        opens again by itself the moment it goes off or the video is closed.
        Only if JARVIS closed it: a microphone the user muted themselves stays
        muted, and pressing the mute key during a video hands the decision back
        to them for good.
        """
        out = self._video_sound_out if self._video_split else self._video_audio
        try:
            muted = bool(out.isMuted()) if out else True
        except Exception:
            muted = True
        plan = _pb.mic_plan(video_on=bool(self._video_on), sound_muted=muted,
                            already_auto_muted=bool(self._video_auto_muted),
                            user_muted=bool(self._muted))
        if plan["close"]:
            self._video_auto_muted = True
            self._set_muted(True, _t("ui.video.mic_held"))
        elif plan["reopen"]:
            self._video_auto_muted = False
            self._set_muted(False, _t("ui.video.mic_back"))

    def _sync_video_mute_btn(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        muted = bool(out and out.isMuted())
        if muted:
            self._video_mute_btn.setText(_t("ui.video.sound_off"))
        else:
            # A bar that says SOUND ON over silence is worse than no bar: it
            # tells the user the opposite of the truth about their own machine.
            self._video_mute_btn.setText(_t("ui.video.sound_on"))

    def _toggle_video_mute(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        if out:
            self._set_video_muted(not out.isMuted())

    def write_log(self, text: str) -> None:
        """Thread-safe: append a line to the live log panel.

        Owned by MainWindow because it holds `_log_sig` (wired to `_log.append_log`
        at startup) and the `_log` widget. `JarvisUI.write_log` delegates to this
        via `self._win._log_sig.emit`; MainWindow methods call it directly.
        """
        self._log_sig.emit(text)


    # ── what a finished video does ─────────────────────────────────────────
    #
    # The rules live in core/playback (Qt-free, so they are tested); this is
    # only the translation of Qt's enums into them, in one place, because that
    # translation is exactly where this feature kept going wrong.
    def _status_word(self, status) -> str:
        try:
            S = QMediaPlayer.MediaStatus
            if status in (S.EndOfMedia,):
                return "ended"
            if status in (S.InvalidMedia,):
                return "invalid"
            if status in (S.NoMedia,):
                return "no_media"
            if status in (S.BufferingMedia, S.StalledMedia):
                return "buffering"
            if status in (S.LoadingMedia,):
                return "loading"
            return "playing"
        except Exception:
            return "playing"



    def _report_video_failure(self, player, detail: str = "",
                              sound_only: bool = False) -> None:
        try:
            detail = detail or player.errorString()
        except Exception:
            detail = detail or ""
        key = "ui.video.audio_failed" if sound_only else "ui.video.failed"
        self.write_log(_t(key, detail=detail) if detail else _t(key, detail="?"))
        if sound_only:
            # Keep the picture playing; just stop pretending there is sound.
            self._video_split = False
            if self._video_sound:
                try:
                    self._video_sound.stop()
                except Exception:
                    pass
            self._set_video_muted(True)

    def _video_muted_state(self) -> bool:
        out = self._video_sound_out if self._video_split else self._video_audio
        try:
            return bool(out.isMuted()) if out else True
        except Exception:
            return True

    def _release_video_mic(self) -> None:
        """Give the microphone back if JARVIS is the one who closed it."""
        if self._video_auto_muted:
            self._video_auto_muted = False
            self._set_muted(False, _t("ui.video.mic_back"))

    def stop_video(self) -> None:
        self._video_close_sig.emit()

    def video_is_playing(self) -> bool:
        return bool(self._video_on)

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "J.A.R.V.I.S AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "J.A.R.V.I.S AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "jarvis.ico"
        if not ico_path.exists():
            build_jarvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "J.A.R.V.I.S.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "J.A.R.V.I.S.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "JARVIS"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>JARVIS</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.jarvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>J.A.R.V.I.S</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "J.A.R.V.I.S.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=J.A.R.V.I.S\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _put_interface_away(self):
        """Ctrl+Shift+J — hand the screen back, if there is a tray to hold it.

        With no tray this does nothing rather than hiding the only surface the
        user has. `JarvisUI.dismiss` enforces that; this is the keystroke.
        """
        host = getattr(self, "_shell", None)
        if host is not None:
            host.dismiss()

    def _toggle_fullscreen(self):
        # F11 WHILE THE WINDOW IS HIDDEN IS NOT A FULL-SCREEN REQUEST.
        #
        # In ambient mode the window exists but is deliberately not on screen.
        # `showFullScreen()` on a hidden window would put a full-screen interface
        # in front of the desktop the user is working on — from a keystroke that
        # belongs to whatever they were actually doing. Refuse instead: the way
        # back to the interface is the tray, or the summon shortcut, both of
        # which are deliberate.
        if not self.isVisible():
            return
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()
        if hasattr(self, '_ctrl_drawer') and self._ctrl_drawer.isVisible():
            self._position_ctrl_drawer()
        self._fit_video()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(_t("ui.uptime", clock=f"{h:02d}:{m:02d}"))
        except Exception:
            self._uptime_lbl.setText(_t("ui.uptime_idle"))

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(_t("ui.proc", count=proc_count))
        except Exception:
            self._proc_lbl.setText(_t("ui.proc_idle"))


    def _build_header(self) -> QWidget:
        from ui.desktop_layout import build_menu_bar
        return build_menu_bar(self)

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        from ui.desktop_layout import build_navigation
        return build_navigation(self, MetricBar, _LEFT_W)

    def _build_right_panel(self) -> QWidget:
        from ui.desktop_layout import build_conversation
        return build_conversation(self, LogWidget, FileDropZone)

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: #00091a; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """

        self._BTN_PRI, self._BTN_DIM = _BTN_STYLE_PRI, _BTN_STYLE_DIM
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.DARK};
                border: 1px solid {C.BORDER_B};
                border-top: none;
                border-radius: 0 0 6px 6px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel(_t("ui.setup.panel"))
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton(_t("ui.remote_control"))
        remote_btn.setFixedHeight(30)
        remote_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        sc_btn = QPushButton(_t("ui.desktop_shortcut"))
        sc_btn.setFixedHeight(26)
        sc_btn.setFont(QFont("Courier New", 7))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton(_t("ui.autostart.off"))
        self._autostart_btn.setFixedHeight(26)
        self._autostart_btn.setFont(QFont("Courier New", 7))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        cust_btn = QPushButton(_t("setup.customise"))
        cust_btn.setFixedHeight(26)
        cust_btn.setFont(QFont("Courier New", 7))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE_DIM)
        cust_btn.clicked.connect(self._open_customize)
        lay.addWidget(cust_btn)

        audio_btn = QPushButton(_t("ui.audio.heading"))
        audio_btn.setFixedHeight(26)
        audio_btn.setFont(QFont("Courier New", 7))
        audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_btn.setStyleSheet(_BTN_STYLE_DIM)
        audio_btn.clicked.connect(self._open_audio_devices)
        lay.addWidget(audio_btn)

        mem_btn = QPushButton(_t("ui.memory.button"))
        mem_btn.setFixedHeight(26)
        mem_btn.setFont(QFont("Courier New", 7))
        mem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mem_btn.setStyleSheet(_BTN_STYLE_DIM)
        mem_btn.clicked.connect(self._open_memory_panel)
        lay.addWidget(mem_btn)

        plugin_btn = QPushButton(_t("ui.plugins.button"))
        plugin_btn.setFixedHeight(26)
        plugin_btn.setFont(QFont("Courier New", 7))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        settings_btn = QPushButton(_t("plugins.heading"))
        settings_btn.setFixedHeight(26)
        settings_btn.setFont(QFont("Courier New", 7))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(_BTN_STYLE_DIM)
        settings_btn.clicked.connect(self._open_plugin_settings)
        lay.addWidget(settings_btn)

        # The button is built here with the rest of the drawer; the panel behind
        # it — and the whole providers package — is imported on the click. The
        # drawer used to stutter for a measured 2.104 seconds because a state
        # check imported openwakeword while it was being built, and adding a
        # second thing that does that would undo the fix rather than repeat it.
        prov_btn = QPushButton(_t("ui.engine.button"))
        prov_btn.setFixedHeight(26)
        prov_btn.setFont(QFont("Courier New", 7))
        prov_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prov_btn.setStyleSheet(_BTN_STYLE_DIM)
        prov_btn.clicked.connect(self._open_providers)
        lay.addWidget(prov_btn)

        w.adjustSize()
        return w

    def _build_controls_drawer(self) -> QWidget:
        """The switches that get flicked every day, in their own panel."""
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(self._quick_drawer.styleSheet())
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)

        hdr = QLabel(_t("ui.controls"))
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)

        def _row(button, style=None, height=26):
            button.setFixedHeight(height)
            button.setFont(QFont("Courier New", 7))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if style:
                button.setStyleSheet(style)
            lay.addWidget(button)
            return button

        fs_btn = _row(QPushButton(_t("ui.fullscreen")), self._BTN_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)

        self._brief_btn = _row(QPushButton())
        self._brief_btn.clicked.connect(self._toggle_brief)

        self._wake_btn = _row(QPushButton())
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        self._wake_sleep_btn = _row(QPushButton())
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        # Neutral until the real state lands from the background warm-up.
        self._wake_btn.setText(_t("ui.wake_word"))
        self._wake_btn.setStyleSheet(self._BTN_DIM)
        self._wake_sleep_btn.hide()

        from ui.wake_sleep import build_wake_sleep_row
        lay.addLayout(build_wake_sleep_row(lambda m: (getattr(self, "on_wake_sleep_timeout", None) or (lambda _: None))(float(m))))

        self._ptt_btn = _row(QPushButton())
        self._ptt_btn.clicked.connect(self._toggle_ptt)
        self._refresh_talk_btns()

        self._hud_btn = _row(QPushButton())
        self._hud_btn.clicked.connect(self._toggle_hud_style)
        self._refresh_hud_btn()

        # Interface mode. Next to the HUD style button because it answers the
        # same kind of question — "how much of my screen does this thing take up"
        # — and belongs in the same drawer the user opens to change that.
        self._iface_btn = _row(QPushButton())
        self._iface_btn.clicked.connect(self._toggle_interface_mode)
        self._refresh_iface_btn()

        w.adjustSize()
        return w

    def _warm_wake_state(self) -> None:
        """Work out the wake-word state off the UI thread, once.

        It used to be resolved when the drawer opened, and that made opening the
        drawer take two seconds the first time — measured at 2.10s, all of it
        `import openwakeword` dragging in onnxruntime behind it. The button
        count had nothing to do with it; the Qt thread was simply waiting on an
        import. Afterwards the same check costs about a millisecond, so it only
        ever needed to happen somewhere other than in front of the user.
        """
        def work():
            try:
                self._wake_state()
            except Exception:
                pass
            self._wake_btns_sig.emit()
        threading.Thread(target=work, daemon=True, name="wake-state-warm").start()

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._close_controls()
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _toggle_controls(self, checked: bool):
        if checked:
            self._close_setup()
            self._refresh_wake_btns()   # cheap now: the state was warmed at boot
            self._position_ctrl_drawer()
            self._ctrl_drawer.show()
            self._ctrl_drawer.raise_()
        else:
            self._ctrl_drawer.hide()

    def _close_setup(self):
        if hasattr(self, "_quick_drawer"):
            self._quick_drawer.hide()
        if hasattr(self, "_drawer_btn"):
            self._drawer_btn.setChecked(False)

    def _close_controls(self):
        if hasattr(self, "_ctrl_drawer"):
            self._ctrl_drawer.hide()
        if hasattr(self, "_ctrl_btn"):
            self._ctrl_btn.setChecked(False)

    def _place_drawer(self, drawer, left: int):
        _W = 220
        drawer.setFixedWidth(_W)
        drawer.adjustSize()
        left = max(0, min(left, self.centralWidget().width() - _W))
        top = self._desktop_menu_bar.height()
        drawer.setGeometry(left, top, _W, drawer.sizeHint().height())

    def _position_quick_drawer(self):
        if hasattr(self, "_quick_drawer"):
            left = 12
            try:
                left = self._drawer_btn.mapTo(self.centralWidget(), QPoint(0, 0)).x() - 8
            except Exception:
                pass
            self._place_drawer(self._quick_drawer, left)

    def _position_ctrl_drawer(self):
        # Under its own header button rather than under the other one's.
        if hasattr(self, "_ctrl_drawer"):
            left = 12
            try:
                left = max(12, self._ctrl_btn.mapTo(self.centralWidget(),
                                                    QPoint(0, 0)).x() - 8)
            except Exception:
                pass
            self._place_drawer(self._ctrl_drawer, left)

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText(_t("ui.placeholder.command"))
        self._input.setFont(QFont("Arial", 11))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; color: {C.DESKTOP_TEXT};
                border: 1px solid transparent; border-radius: 6px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton(">")
        self._send_btn = send
        send.setToolTip(_t("desktop.send"))
        send.setAccessibleName(_t("desktop.send"))
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet("""
            QPushButton {
                background: #287fce; color: #ffffff;
                border: 1px solid #4b9fff; border-radius: 15px;
            }
            QPushButton:hover { background: #3599eb; }
            QPushButton:focus { border: 2px solid #ffffff; }
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel(_t("ui.briefing"))
        self._content_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont("Courier New", 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton(_t("ui.dismiss_x"))
        dismiss.setFont(QFont("Courier New", 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(lambda: set_assistant_tool(self, w, False))
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont("Courier New", 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        # The panel opens below the head, so the head looks down at it. It is a
        # tiny thing that answers "did that land?" before you read a word.
        self.hud.glance(0.0, -0.85, hold=1.3)
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        set_assistant_tool(self, self._content_panel, True)
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    # ── the coding agent, live ───────────────────────────────────────────────
    # The panel under the head shows a folder job while it runs: what was asked,
    # the plan, every file with its state, and the steps as they happen. Drawn
    # from a snapshot the job publishes on every step, so this slot never reads
    # anything a worker thread is still changing.
    _JOB_STATES = {
        "waiting": ("TEXT_DIM", "○"), "writing": ("PRI", "✎"),
        "done": ("GREEN", "✓"), "fixing": ("ACC2", "↻"),
        "skipped": ("TEXT_DIM", "–"), "failed": ("RED", "✕"),
        "broken": ("RED", "!"),
    }
    _JOB_PHASES = ("reading", "planning", "writing", "checking")
    def _show_code_job(self, job: dict):
        """Slot — Qt main thread. Draws the coding agent's progress."""
        import time as _time
        if not job:
            return
        if job.get("kind") in ("creative_workspace", "trading_terminal", "mt5_trade", "image_editor", "workspace_browser", "ssh_manager"):
            from ui.workspace_router import open_workspace
            open_workspace(self, job); return
        e = self._esc
        col = lambda name: getattr(C, name, C.TEXT)
        status = job.get("status", "")
        finished = job.get("finished")
        took = (finished or _time.time()) - job.get("started", _time.time())
        # Phase strip: where in the job it is, readable at a glance.
        strip = []
        phases = list(job.get("phases") or self._JOB_PHASES)
        here = phases.index(status) if status in phases else (
            len(phases) if finished else -1)
        for i, ph in enumerate(phases):
            c = C.GREEN if i < here else (C.PRI if i == here else C.TEXT_DIM)
            mark = "●" if i <= here else "○"
            strip.append(f'<span style="color:{c};">{mark} {ph.upper()}</span>')
        if finished:
            fin = C.GREEN if status == "done" else (C.RED if status == "failed" else C.ACC2)
            strip.append(f'<span style="color:{fin};"><b>● {e(status.upper())}</b></span>')

        parts = [f'<div style="color:{C.TEXT}; font-family:Courier New;">',
                 f'<div style="color:{C.TEXT_DIM};">{"  ".join(strip)}'
                 f'&nbsp;&nbsp;·&nbsp;&nbsp;{took:.0f}s</div>',
                 f'<div style="margin-top:6px;"><span style="color:{C.TEXT_DIM};">'
                 f'REQUEST&nbsp;</span>{e(job.get("request", ""))}</div>']
        if job.get("summary"):
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin:8px 0;">{e(job["summary"])}</div>')
        files = job.get("files") or {}
        if files:
            parts.append(f'<div style="color:{C.TEXT_DIM}; margin-top:4px;">FILES</div>')
            for path, f in files.items():
                cname, mark = self._JOB_STATES.get(f.get("state", ""), ("TEXT_DIM", "·"))
                verb = "new " if f.get("action") == "create" else ""
                parts.append(
                    f'<div><span style="color:{col(cname)};">{mark}</span>&nbsp;'
                    f'<span style="color:{C.WHITE};">{e(path)}</span>&nbsp;'
                    f'<span style="color:{C.TEXT_DIM};">{verb}{e(f.get("what", ""))[:110]}'
                    f'</span></div>')
        # Newest first, so the latest step sits under the plan and the whole
        # state of the job is visible without scrolling in a 220-pixel panel.
        steps = job.get("steps") or []
        if steps:
            parts.append(f'<div style="color:{C.TEXT_DIM}; margin-top:8px;">'
                         f'STEPS — newest first</div>')
            for t, msg in reversed(steps[-14:]):
                parts.append(f'<div><span style="color:{C.TEXT_DIM};">{float(t):6.1f}s'
                             f'</span>&nbsp;{e(msg)}</div>')
        parts.append("</div>")

        title = f"CODE AGENT — {job.get('folder', '')} · {job.get('model', '')}"
        first = self._content_title_lbl.text() != title.upper()[:48]
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        bar = self._content_display.verticalScrollBar()
        keep = 0 if first else bar.value()
        self._content_display.setHtml("".join(parts))
        # setHtml jumps to the top; put the reader back where they were.
        bar.setValue(keep)
        if not self._content_panel.isVisible():
            self.hud.glance(0.0, -0.85, hold=1.3)
            set_assistant_tool(self, self._content_panel, True)
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 260, 120), 260])

    # ── document review ──────────────────────────────────────────────────────
    # Rendered as rich text into the content panel that already exists, rather
    # than into a panel of its own. A review is read, not clicked, so QTextEdit
    # gives scrolling, selection and copy for nothing, and the HUD gains no
    # widget it has to lay out. Severity decides colour and order here because
    # that is presentation; the plugin supplies no styling and knows no palette,
    # which is also what lets a re-theme repaint a review correctly.

    # Severity is marked by a symbol and a colour, not by a word. The findings
    # themselves are in the user's language, and "[SERIOUS]" sitting inside a
    # Turkish sentence is the kind of seam this project tries not to have —
    # while translating the tag would mean a table per language, which is worse.
    # A shape carries it in every language, and shape plus colour still reads
    # for someone who cannot separate red from amber. What the marks mean
    # arrives the way everything else does: JARVIS says it out loud.
    _REVIEW_MARKS = {"serious": ("RED", "▲"), "caution": ("ACC2", "●"), "note": ("PRI_DIM", "·")}

    @staticmethod
    def _esc(s) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))

    def _show_review(self, title: str, summary: str, findings, unclear):
        """Slot — Qt main thread. Lays a document review into the content panel."""
        e = self._esc
        parts = [f'<div style="color:{C.TEXT}; font-family:Courier New;">']

        if summary:
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin-bottom:10px;">{e(summary)}</div>')

        for f in (findings or []):
            key, mark = self._REVIEW_MARKS.get(f.get("severity"), ("PRI_DIM", "·"))
            colour = getattr(C, key)
            parts.append('<div style="margin-bottom:11px;">')
            parts.append(
                f'<span style="color:{colour}; font-weight:bold;">{mark}</span> '
                f'<span style="color:{C.WHITE}; font-weight:bold;">'
                f'{e(f.get("heading"))}</span>')
            if f.get("detail"):
                parts.append(f'<div style="margin-left:12px;">{e(f["detail"])}</div>')
            if f.get("quote"):
                # The document's own wording, visually separated from the
                # explanation so the two are never mistaken for each other.
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_DIM};'
                    f' border-left:1px solid {C.BORDER}; padding-left:7px;">'
                    f'&ldquo;{e(f["quote"])}&rdquo;</div>')
            if f.get("suggestion"):
                parts.append(
                    f'<div style="margin-left:12px; color:{C.PRI};">'
                    f'&rarr; {e(f["suggestion"])}</div>')
            parts.append('</div>')

        if unclear:
            parts.append(
                f'<div style="margin-top:6px; border-top:1px solid {C.BORDER};'
                f' padding-top:7px; color:{C.TEXT_MED};">'
                'The document does not settle:</div>')
            for u in unclear:
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_MED};">'
                    f'&middot; {e(u)}</div>')
        parts.append('</div>')

        import time as _time
        self.hud.glance(0.0, -0.85, hold=1.3)
        # Left as written, not upper-cased. The other content-panel titles are
        # the app's own English labels, but this one is the document's name in
        # the user's language, and str.upper() applies English casing rules to
        # it: Turkish "Sözleşmesi" comes back "SÖZLEŞMESI", having lost the
        # dotted capital İ. Python has no locale-aware upper to reach for, and
        # imposing one language's rules on all of them is the bug, not the fix.
        self._content_title_lbl.setText((title or "Document")[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setHtml("".join(parts))
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        first_show = not self._content_panel.isVisible()
        set_assistant_tool(self, self._content_panel, True)
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 260, 120), 260, 0])

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message JARVIS reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _quiz_btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFont(QFont("Courier New", 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(24)
        edge = C.BORDER_B if primary else C.BORDER
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {col};
                border: 1px solid {edge}; border-radius: 2px;
                padding: 3px 9px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """)
        return b

    def _build_quiz_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("QuizPanel")
        w.setStyleSheet(f"""
            QWidget#QuizPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._quiz_title_lbl = QLabel(_t("ui.quiz.heading"))
        self._quiz_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._quiz_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._quiz_title_lbl)
        hdr.addStretch()

        self._quiz_count_lbl = QLabel("")
        self._quiz_count_lbl.setFont(QFont("Courier New", 7))
        self._quiz_count_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._quiz_count_lbl)

        quit_btn = QPushButton(_t("ui.dismiss_x"))
        quit_btn.setFont(QFont("Courier New", 7))
        quit_btn.setFixedHeight(18)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        quit_btn.clicked.connect(self._hide_quiz)
        hdr.addWidget(quit_btn)
        lay.addLayout(hdr)

        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(rule)

        self._quiz_q_lbl = QLabel("")
        self._quiz_q_lbl.setWordWrap(True)
        self._quiz_q_lbl.setFont(QFont("Courier New", 9))
        self._quiz_q_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(self._quiz_q_lbl)

        self._quiz_answers = QWidget()
        self._quiz_answers.setStyleSheet("background: transparent;")
        self._quiz_answers_lay = QVBoxLayout(self._quiz_answers)
        self._quiz_answers_lay.setContentsMargins(0, 2, 0, 0)
        self._quiz_answers_lay.setSpacing(4)
        lay.addWidget(self._quiz_answers)

        self._quiz_note_lbl = QLabel("")
        self._quiz_note_lbl.setWordWrap(True)
        self._quiz_note_lbl.setFont(QFont("Courier New", 8))
        self._quiz_note_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._quiz_note_lbl.hide()
        lay.addWidget(self._quiz_note_lbl)

        foot = QHBoxLayout()
        foot.addStretch()
        self._quiz_next_btn = self._quiz_btn("NEXT  →", primary=True)
        self._quiz_next_btn.setFixedWidth(110)
        self._quiz_next_btn.clicked.connect(self._quiz_next)
        self._quiz_next_btn.hide()
        foot.addWidget(self._quiz_next_btn)
        lay.addLayout(foot)

        self._quiz = None
        return w

    def _show_quiz(self, topic: str, questions, grader=None):
        """Slot — Qt main thread. Puts a fresh quiz on the board."""
        if not questions:
            return
        self._quiz = {
            "topic": topic or "",
            "questions": list(questions),
            "grader": grader,
            "i": 0,
            "results": [],
            "answered": False,
        }
        self._quiz_title_lbl.setText((topic or "quiz").upper()[:48])
        self.hud.glance(0.0, -0.85, hold=1.3)
        first_show = not self._quiz_panel.isVisible()
        set_assistant_tool(self, self._quiz_panel, True)
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 250, 120), 0, 250])
        self._quiz_render()

    def _hide_quiz(self):
        self._quiz = None
        set_assistant_tool(self, self._quiz_panel, False)

    def _quiz_clear_answers(self):
        while self._quiz_answers_lay.count():
            item = self._quiz_answers_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _quiz_render(self):
        q = self._quiz["questions"][self._quiz["i"]]
        n, total = self._quiz["i"] + 1, len(self._quiz["questions"])
        self._quiz_count_lbl.setText(f"{n} / {total}")
        self._quiz_q_lbl.setText(q.get("question", ""))
        self._quiz_note_lbl.hide()
        self._quiz_next_btn.hide()
        self._quiz["answered"] = False
        self._quiz_clear_answers()

        opts = q.get("options") or []
        if opts:
            for text in opts:
                b = self._quiz_btn("   " + text)
                b.clicked.connect(lambda _=False, t=text: self._quiz_submit(t))
                self._quiz_answers_lay.addWidget(b)
        else:
            row = QWidget(); row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
            field = QLineEdit()
            field.setFont(QFont("Courier New", 9))
            field.setPlaceholderText(_t("ui.placeholder.answer"))
            field.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL2}; color: {C.WHITE};
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 4px 7px;
                }}
                QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
            """)
            send = self._quiz_btn("ANSWER", primary=True)
            send.setFixedWidth(90)
            field.returnPressed.connect(lambda: self._quiz_submit(field.text()))
            send.clicked.connect(lambda: self._quiz_submit(field.text()))
            h.addWidget(field, stretch=1)
            h.addWidget(send)
            self._quiz_answers_lay.addWidget(row)
            field.setFocus()

    def _quiz_submit(self, given: str):
        if self._quiz is None or self._quiz["answered"]:
            return
        self._quiz["answered"] = True
        q = self._quiz["questions"][self._quiz["i"]]
        grader = self._quiz.get("grader")
        verdict = None
        if callable(grader):
            try:
                verdict = grader(q, given)
            except Exception:
                verdict = None
        self._quiz["results"].append({
            "question": q.get("question", ""),
            "type": q.get("type", ""),
            "given": str(given or "").strip(),
            "answer": q.get("answer", ""),
            "correct": verdict,
        })

        for i in range(self._quiz_answers_lay.count()):
            wdg = self._quiz_answers_lay.itemAt(i).widget()
            if wdg is not None:
                wdg.setEnabled(False)

        if verdict is True:
            mark, colour = "✓  correct", C.GREEN
        elif verdict is False:
            mark, colour = "✕  " + str(q.get("answer", "")), C.RED
        else:
            # Open answers and near-miss gap-fills are JARVIS's to judge. Saying
            # so is honest; marking it wrong here would be a guess.
            mark, colour = "…  noted — I'll go over this one with you", C.ACC2
        note = q.get("note") or ""
        self._quiz_note_lbl.setText(mark + (("\n" + note) if note else ""))
        self._quiz_note_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self._quiz_note_lbl.show()

        last = self._quiz["i"] >= len(self._quiz["questions"]) - 1
        self._quiz_next_btn.setText(_t("ui.quiz.finish") if last
                                    else _t("ui.quiz.next"))
        self._quiz_next_btn.show()
        self._quiz_next_btn.setFocus()

    def _quiz_next(self):
        if self._quiz is None:
            return
        if self._quiz["i"] >= len(self._quiz["questions"]) - 1:
            self._quiz_finish()
        else:
            self._quiz["i"] += 1
            self._quiz_render()

    def _quiz_finish(self):
        if self._quiz is None:
            return
        topic = self._quiz["topic"]
        results = self._quiz["results"]
        right = sum(1 for r in results if r["correct"] is True)
        unsure = sum(1 for r in results if r["correct"] is None)
        total = len(results)
        set_assistant_tool(self, self._quiz_panel, False)
        self._quiz = None

        self._log.append_log(f"QUIZ: {topic or 'quiz'} — {right}/{total} correct")

        # Hand it back to JARVIS as a message, not as a tool return: the tool
        # call ended minutes ago. This is the same channel a dropped file uses.
        lines = [f"[QUIZ_DONE] topic={topic or 'general'} | "
                 f"auto-marked {right}/{total} correct"
                 + (f", {unsure} still need your marking" if unsure else "")]
        for i, r in enumerate(results, 1):
            state = ("correct" if r["correct"] is True
                     else "wrong" if r["correct"] is False else "NEEDS MARKING")
            lines.append(
                f"{i}. [{r['type']}] {r['question']} | they answered: "
                f"{r['given'] or '(blank)'} | expected: {r['answer']} | {state}")
        lines.append(
            "Mark every question flagged NEEDS MARKING yourself — accept an answer "
            "that means the same thing. Then tell them how they did in their own "
            "language: the score, what they got wrong and why, in a couple of "
            "sentences. Offer another round only if it fits. "
            "Remember something only if it would still matter next week — that they "
            "are working through a subject, or keep missing the same thing. A score "
            "from one session is not worth a memory, and a memory per quiz would "
            "bury the things that are.")
        msg = "\n".join(lines)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("By FatihMakes", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        if cat == "folder":
            n = self._drop_zone._folder_files
            self._file_hint.setText(
                f"{icon}  {p.name}  ·  {n} files  ·  "
                + _t("ui.files_hint", name=self._assistant_name))
            self._log.append_log(f"FOLDER: {p.name} ({n} files) loaded")
            if self.on_text_command:
                msg = (
                    f"[FOLDER_UPLOADED] path={path} | name={p.name} | files={n} | "
                    f"Briefly tell the user the project folder '{p.name}' is loaded "
                    f"and that you can improve, fix or extend it with the coding "
                    f"model — ask what they want changed. When they say, call "
                    f"dev_agent with mode='improve' and their request as the "
                    f"description."
                )
                threading.Thread(target=self.on_text_command, args=(msg,),
                                 daemon=True).start()
            return
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  "
                                 + _t("ui.file_hint", name=self._assistant_name))
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        berr   = result[4] if len(result) >= 5 else ""
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw, bind_error=berr,
                               assistant_name=self._assistant_name)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "JARVIS_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.jarvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "JARVIS_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "JARVIS_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.jarvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "jarvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText(_t("ui.autostart.on"))
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText(_t("ui.autostart.off"))
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before JarvisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"] and not st["enabled"]:
            self._wake_btn.setText(_t("ui.wake_word.download"))
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText(_t("ui.wake_word.on"))
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText(_t("ui.sleep_now") if st["awake"]
                                         else _t("ui.wake_now"))
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText(_t("ui.wake_word.off"))
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _refresh_talk_btns(self):
        """Repaint the push-to-talk row from the saved setting."""
        if not hasattr(self, "_ptt_btn"):
            return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""

        ptt = get_push_to_talk_enabled()
        self._ptt_btn.setText(f"🎚  PUSH-TO-TALK: {chord_label()}" if ptt
                              else "🎚  PUSH-TO-TALK: OFF")
        self._ptt_btn.setStyleSheet(_on if ptt else _off)
        self._ptt_btn.setToolTip(
            "Microphone stays closed until you hold the key — nothing is sent "
            "while you are not holding it." if ptt
            else "Hold a key to talk instead of streaming the mic continuously.")


    def _refresh_hud_btn(self):
        from memory.config_manager import get_hud_style
        current = get_hud_style()
        # Neither state is "off", so both read as active — this is a choice
        # between two things, not a switch with a disabled side.
        style = f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}"""
        self._hud_btn.setText(_t("ui.hud." + current))
        self._hud_btn.setStyleSheet(style)
        self._hud_btn.setToolTip(_t("ui.hud.cycle_hint"))

    def _refresh_iface_btn(self):
        """Paint the interface-mode button from what is actually stored.

        Read from the config rather than from `JarvisUI`, so a mode that failed
        to take effect cannot be reported as if it had: the button shows the
        saved value, and the failure is a log line.

        In ambient mode this button is not reachable at all — there is no window
        to show it in. That is not a gap: the mode is changed from the HUD, and
        the tray's "Show" item is the way back to it.
        """
        from memory.config_manager import get_ui_mode
        current = get_ui_mode()
        self._iface_btn.setText(_t("ui.iface." + current))
        # The same palette names as `_refresh_hud_btn` — the adjacent button in
        # the same drawer — so the two cannot look like they came from different
        # screens. (An earlier draft invented C.ACCENT and C.TEXT; neither is a
        # name in ui/theme.py, and the window stub said so immediately.)
        self._iface_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}""")
        self._iface_btn.setToolTip(_t("ui.iface.hint"))

    def _toggle_interface_mode(self):
        """Cycle the three interface modes; believe only what actually took.

        hud -> ambient -> bubble -> hud. The same order as the HUD style button
        next to it, which also cycles rather than presenting a list — one button
        that shows where you are is cheaper to read than a menu, and the label
        always says which mode you are in.
        """
        from memory.config_manager import get_ui_mode
        order = ("hud", "ambient", "bubble")
        want = order[(order.index(get_ui_mode()) + 1) % len(order)]
        ok = False
        host = getattr(self, "_shell", None)
        if host is not None:
            try:
                ok = bool(host.set_interface_mode(want))
            except Exception as e:                  # noqa: BLE001
                self._log.append_log(f"ERR: Interface mode failed — {e}")
                ok = False
        if not ok:
            # Said plainly instead of flipping the label and pretending. The
            # commonest cause is a desktop with no notification area, and the
            # user can do nothing about that — so they are told why the button
            # will keep going back to what it was.
            self._log.append_log(f"ERR: {_t('ui.iface.unavailable')}")
        self._refresh_iface_btn()

    def _toggle_hud_style(self):
        """Swap the centrepiece. Both objects stay in memory, so the change is
        instant and switching back costs nothing."""
        from memory.config_manager import get_hud_style, save_hud_style
        styles = ("orb", "face", "core")
        want = styles[(styles.index(get_hud_style()) + 1) % len(styles)]
        save_hud_style(want)
        try:
            self.hud.hud_style = want
            self.hud.update()
            self._desktop_mdi.position_emblem()
        except Exception:
            pass
        self._refresh_hud_btn()
        self._log.append_log("SYS: " + _t("ui.hud." + want))

    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Push-to-talk failed — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                pass

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"] and not st["enabled"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText(_t("ui.wake_word.downloading"))
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through JarvisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText(_t("ui.brief.on"))
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText(_t("ui.brief.off"))
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "JARVIS") or "JARVIS",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = "", language: str = ""):
        """Update all name/theme/language-dependent UI elements and persist.

        The language is applied BEFORE the log lines below are written, so the
        confirmation the user reads is in the language they just chose — a
        "saved" message in the old language is the one moment they cannot tell
        whether the switch worked.
        """
        self._assistant_name = name.strip() or "JARVIS"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION}")
        self._title_lbl.setText(display)
        if display in ("JARVIS", "J.A.R.V.I.S"):
            self._sub_lbl.setText(_t("app.tagline"))
        else:
            self._sub_lbl.setText(_t("app.title"))
        self._log._ai_name_lc = self._assistant_name.lower()
        self._assistant_heading.setText(self._assistant_name)
        self._assistant_mark.setAccessibleName(self._assistant_name)
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        if language:
            # Persist first, then apply: if the write fails the window stays in
            # the language its config file still says, instead of forgetting the
            # choice at the next start.
            from memory.config_manager import get_ui_language, save_ui_language
            if language != get_ui_language():
                save_ui_language(language)
            set_locale(language if language != "auto" else None)
            self._retranslate_window()

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            # Through config_manager, not by writing api_keys.json here. This
            # block used to be a second writer into the same file, which is
            # exactly the race config_manager exists to remove: the Qt thread
            # rewriting the whole document while the session thread saved a
            # voice, and whichever finished second won.
            from memory.config_manager import set_config_values
            fields = {"assistant_name": self._assistant_name,
                      "user_name": user_name.strip()}
            if ui_color:
                fields["ui_color"] = ui_color.strip().lower()
            set_config_values(**fields)
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _retranslate_window(self) -> None:
        """Re-render every label the window owns, after a language change.

        Deliberately NOT a rebuild. Rebuilding the HUD would drop the
        conversation, the drop zone's file, the session and the widget handles
        that background threads write into (the uptime label, the log); a
        language switch is not worth losing any of those. So the labels whose
        handles this class keeps are re-read, and the constant ones are set from
        the same keys the constructor used.

        Called on the Qt thread (it is a slot on the saved signal), never from a
        worker: every call below touches a widget.
        """
        self._title_lbl.setText(self._assistant_name.upper())
        if self._assistant_name.upper() in ("JARVIS", "J.A.R.V.I.S"):
            self._sub_lbl.setText(_t("app.tagline"))
        else:
            self._sub_lbl.setText(_t("app.title"))
        self._input.setPlaceholderText(_t("ui.placeholder.command"))
        from ui.desktop_layout import retranslate
        from ui.desktop_workspace import retranslate as retranslate_workspace
        retranslate(self)
        retranslate_workspace(self)
        self._uptime_lbl.setText(_t("ui.uptime_idle"))
        self._proc_lbl.setText(_t("ui.proc_idle"))
        # Buttons whose text depends on state are read from the state they are
        # ALREADY in — repainting a switch must not flip it. These are the same
        # functions the settings handlers use, so there is one rule for what a
        # button says, not a second copy that can drift.
        self._style_mute_btn()
        self._sync_video_mute_btn()
        self._refresh_iface_btn()
        self._refresh_wake_btns()
        self._refresh_talk_btns()
        for name, key in (("_drawer_btn", "ui.settings_button"),
                          ("_ctrl_btn", "ui.controls_button"),
                          ("_file_hint", None)):
            btn = getattr(self, name, None)
            if btn is not None and key:
                btn.setToolTip(_t(key))
        if not self._file_hint.text().strip():
            self._file_hint.setText(_t("ui.drop.empty"))
        self._log.append_log(f"SYS: Interface language — {i18n_active().upper()}")

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Engine & providers ───────────────────────────────────────────────────

    def _open_providers(self):
        """Open the engine panel. Everything it needs is imported on this call.

        A failure here must not take the drawer with it — the folder can be
        deleted, which is the point of it being a folder, and the honest answer
        to that is a line in the log rather than a traceback.
        """
        try:
            ov = ProvidersOverlay(parent=self.centralWidget())
        except ImportError:
            self._log.append_log(
                "SYS: The providers folder is not installed — "
                "the assistant runs on Gemini Live.")
            return
        except Exception as e:
            self._log.append_log(f"SYS: Provider settings unavailable: {e}")
            return
        ov.changed.connect(self._on_providers_applied)
        self._centre_overlay(ov)
        self._providers_overlay = ov        # keep a reference so it isn't GC'd

    def _on_providers_applied(self):
        """Rebuild the session so the new engine takes over.

        Reuses the audio-device callback rather than adding a second one: both
        mean 'the conversation has to be rebuilt', main.py already keeps the
        transcript across such a rebuild through session resumption, and one
        path that is known to work is better than two that look alike."""
        self._log.append_log("SYS: Engine settings saved — reconnecting.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, token: str, title: str, detail: str):
        from core.confirm import is_pending
        if not is_pending(token):
            return  # a queued banner for an expired or replaced request
        if hasattr(self, "_hand_controller"):
            self._hand_controller.stop()
        if getattr(self, "_hand_menu", None) is not None:
            self._hand_menu.close()
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(lambda accepted: self._on_confirm_answered(token, accepted))
        self._centre_overlay(ov)
        self._confirm_overlay = ov
        self._confirm_token = token

    def _hide_confirm_banner(self, token=None):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None and (token is None or token == getattr(self, "_confirm_token", None)):
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None
            self._confirm_token = None

    def _on_confirm_answered(self, token: str, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner(token)
        try:
            from core.confirm import resolve
            resolve(token, bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.setFixedWidth(max(1, min(PluginManagerOverlay._OW, cw.width() - 16)))
        ov.on_changed = getattr(self, "on_plugins_changed", None)
        height = max(1, min(600, cw.height() - 16, 120 + 35 * len(plugins)))
        ov.setGeometry(
            max(0, (cw.width() - ov.width()) // 2),
            max(0, (cw.height() - height) // 2),
            ov.width(), height,
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        # The panel's empty state offers a way out, and this is where the way
        # out leads: the manager, which lists every plugin including the ones
        # that declare no form. Wired as a callback so the panel never learns
        # what a manager is.
        ov.on_open_manager = self._open_plugin_manager
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        # A deliberate press settles the question: whatever the video did, or is
        # about to do, the user has now said what they want.
        self._video_auto_muted = False
        self._set_muted(not self._muted)

    def _set_muted(self, muted: bool, note: str = ""):
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.hud.muted = muted
        self._style_mute_btn()
        if muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted." + (f" {note}" if note else ""))
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active." + (f" {note}" if note else ""))

    def _style_mute_btn(self):
        if getattr(self, "_deaf", False):
            self._mute_btn.setText(_t("ui.mic.absent"))
            self._mute_btn.setEnabled(False)
        elif self._muted:
            self._mute_btn.setText(_t("ui.mic.muted"))
            self._mute_btn.setEnabled(True)
        elif self.hud.state == "INITIALISING":
            self._mute_btn.setText(_t("ui.mic.initialising"))
            self._mute_btn.setEnabled(True)
        else:
            self._mute_btn.setText(_t("ui.mic.active"))
            self._mute_btn.setEnabled(True)
        border = C.MUTED_C if self._muted else C.DESKTOP_BORDER
        self._mute_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT};
                           border: 1px solid {border}; border-radius: 6px; }}
            QPushButton:hover {{ background: {C.DESKTOP_SIDEBAR}; }}
            QPushButton:disabled {{ color: {C.DESKTOP_MUTED}; }}
        """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        if hasattr(self, "_desktop_state"):
            from ui.desktop_layout import update_state
            update_state(self, state)
        stage = getattr(self.hud, "_desktop_stage", None)
        if stage is not None:
            stage.update()
        # The microphone button is the only control on this window that claims
        # something about the hardware, so it has to admit when there is none.
        # `NO MIC` comes from main.py when the stream could not be opened; the
        # button then says so and is disabled, instead of offering to unmute a
        # device that does not exist.
        self._deaf = (state == "NO MIC")
        try:
            self._style_mute_btn()
        except AttributeError:
            # _apply_state runs during construction, before the button exists.
            pass

    def _check_config(self) -> bool:
        try:
            from memory.config_manager import get_gemini_key, load_api_keys
            return bool(get_gemini_key()) and bool(load_api_keys().get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        """Show the setup screen — at launch, and again when a key is rejected.

        THE SECOND TIME IS WHY THIS IS WRITTEN THE WAY IT IS
            Both callers used to be the same five lines, and the branch that
            matters is the second one: when the session loop decides the API
            key is invalid it emits _reconfig_sig and then waits, in a
            `while not self._win._ready` loop, for this screen to bring it back.
            That only works if the overlay it creates is the one whose `done`
            is connected to _on_setup_done. It was not — the overlay was built,
            shown, and thrown away — so the key could be retyped, saved and
            accepted and the session loop still sat there forever, asleep.
            Unlike the launch case, a dismissal here MUST also settle `_ready`:
            otherwise closing the box leaves the app in the same permanent wait.

            Verified change: `_overlay` is now assigned, `done` is connected on
            both paths, and a close that is not a save sets `_ready` too — see
            _on_setup_closed.
        """
        cw = self.centralWidget()
        # Never leak the previous one: a second _show_setup while a box is open
        # would otherwise leave a live overlay with nowhere to report back to.
        old = getattr(self, "_overlay", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        ov = SetupOverlay(cw)
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        # The "not a save" path: Qt sends destroyed on close() and hide(); the
        # setup box has no cancel button, so anything other than a save is the
        # user closing it to get their window back.
        ov.destroyed.connect(self._on_setup_closed)
        ov.show()
        ov.raise_()
        self._overlay = ov

    def _on_setup_closed(self, *_):
        """The box went away without a key. Let the session loop try again."""
        if getattr(self, "_setup_saved", False):
            return                      # _on_setup_done already settled it
        self._overlay = None
        if not self._ready:
            self._ready = True          # unblocks main.py's wait loop
        self._log.append_log(
            "SYS: Setup closed without an API key — retrying the connection.")

    def _on_setup_done(self, key: str, os_name: str):
        """Save from the setup screen. MERGES into the config; never replaces.

        This used to write {"gemini_api_key", "os_system"} with write_text(),
        which is correct on a first run and destructive on every other: the
        same screen appears when a key is rejected, and saving from it deleted
        the assistant's name, its voice, the device choices and every plugin
        credential — OAuth tokens included. It now goes through the one config
        writer, which holds a lock and swaps the file in atomically.
        """
        self._setup_saved = True
        try:
            from memory.config_manager import save_setup
            if not save_setup(key, os_name):
                raise OSError("Could not write configuration")
        except Exception as e:
            self._setup_saved = False
            self._log.append_log(f"ERR: Could not save setup: {e}")
            return
        self._ready = True
        ov, self._overlay = getattr(self, "_overlay", None), None
        if ov is not None:
            ov.hide()
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "JARVIS") or "JARVIS"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")
        self._setup_saved = False


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


def _auto_ui_scale() -> float:
    """A scale for the interface from the primary screen's usable height.

    Every size in this file — 7 and 8 point text, fixed button heights, panel
    widths — was laid out on a 1080-pixel-tall screen. Windows only enlarges it
    when the user has raised display scaling, so on a 1440p monitor left at 100%
    the whole HUD came out at three-quarters size and the settings text was hard
    to read. Measured against 900 logical pixels rather than 1080 because the
    designed sizes were on the small side even there — reported as "generally
    small" on a 1440p screen already at 125%.

    Windows only, through calls that are not DPI-virtualised — so nothing about
    the process's DPI awareness is touched before Qt sets it. Elsewhere the
    system's own scaling is trusted and this returns 1."""
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        try:
            physical_h = gdi32.GetDeviceCaps(hdc, 117)      # DESKTOPVERTRES
        finally:
            user32.ReleaseDC(0, hdc)
        percent = ctypes.windll.shcore.GetScaleFactorForDevice(0) or 100
        logical_h = physical_h * 100.0 / percent
    except Exception:
        return 1.0
    return max(1.0, min(2.0, round(logical_h / 900.0 * 20) / 20))


def _apply_ui_scale() -> None:
    """Set Qt's global scale factor. Must run before QApplication exists."""
    if QApplication.instance() is not None or os.environ.get("QT_SCALE_FACTOR"):
        return              # too late, or the user set it themselves
    try:
        from memory.config_manager import get_ui_scale
        scale = get_ui_scale() or _auto_ui_scale()
    except Exception:
        scale = _auto_ui_scale()
    if abs(scale - 1.0) > 0.01:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"


class JarvisUI:
    """The whole interface, and whether any of it is on screen.

    AMBIENT MODE, AND WHY THE WINDOW IS STILL BUILT IN IT
        `ui_mode` in the config decides what happens at launch. "hud" is what
        this app has always done: build the window and fill the screen with it.
        "ambient" builds the same window and does NOT show it — JARVIS lives in
        the notification area and answers by voice until it is summoned.

        The window is still constructed rather than deferred. Everything the
        rest of the program talks to lives on it (`write_log`, `set_state`,
        `show_confirm`, the plugin registry, the camera stream target), and
        `main.py` starts using those before anyone could plausibly summon the
        interface. Building it and keeping it hidden keeps every one of those
        30 attributes working, in both modes, with no branch at any call site.
        It costs the memory of a window that is not drawn; it saves rewriting
        the seam between the session loop and the interface.
    """

    def __init__(self, face_path: str, size=None):
        _apply_ui_scale()
        if QApplication.instance() is None:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        self._tray = None
        self._bubble = None
        self._face_path = face_path
        self._ambient = False
        # The window's closeEvent has to be able to tell "put it away" from
        # "quit", and only this object knows whether a tray exists. It reaches
        # back through this one attribute rather than being handed a callback
        # per concern.
        self._win._shell = self
        # Launch, summon and dismiss live in ui/lifecycle.py: 200 lines of them
        # pushed this file past the ceiling that exists to stop it growing again,
        # and the ceiling was not raised for new code. The methods below are
        # thin delegations so every existing caller is unaffected.
        from ui import lifecycle
        self._lifecycle = lifecycle
        lifecycle.start_interface(self)

    # ── the interface's own lifecycle ────────────────────────────────────────
    # Convenience pass-throughs. `lifecycle` takes the shell explicitly; these
    # keep `shell.summon()` working for main.py, plugins and the tray.

    @property
    def ambient(self) -> bool:
        """True when there is no window and the tray is the only surface."""
        return self._ambient

    @property
    def tray_available(self) -> bool:
        """Whether a notification-area icon is standing by.

        Read by `MainWindow.closeEvent`: with one, closing means hide; without
        one, closing means quit, because there would be no way back.
        """
        tray = getattr(self, "_tray", None)
        return tray is not None and tray.available

    def _start_tray(self) -> bool:
        return self._lifecycle.start_tray(self)

    def _face_path_or_default(self) -> str:
        """The face image the bubble should draw, as the window was given it."""
        return getattr(self, "_face_path", None) or "face.png"

    def summon(self) -> None:
        self._lifecycle.summon(self)

    def dismiss(self) -> None:
        self._lifecycle.dismiss(self)

    def toggle_interface(self) -> None:
        self._lifecycle.toggle_interface(self)

    def set_interface_mode(self, mode: str) -> bool:
        return self._lifecycle.set_interface_mode(self, mode)

    def request_wake(self) -> None:
        self._lifecycle.request_wake(self)

    def request_sleep(self) -> None:
        self._lifecycle.request_sleep(self)

    def summon_settings(self) -> None:
        self._lifecycle.summon_settings(self)

    def quit(self) -> None:
        self._lifecycle.quit_app(self)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, token: str, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(token, title, detail)

    def hide_confirm(self, token: str) -> None:
        """Thread-safe: take down only the matching gate."""
        self._win._confirm_hide_sig.emit(token)

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb
        if cb is not None:
            self._win._plugins_ready_sig.emit()

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def on_wake_sleep_timeout(self):
        return getattr(self._win, "on_wake_sleep_timeout", None)
    @on_wake_sleep_timeout.setter
    def on_wake_sleep_timeout(self, cb):
        self._win.on_wake_sleep_timeout = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass
        bubble = getattr(self, "_bubble", None)
        if bubble is not None:
            bubble.set_audio_level(level)

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Ask the avatar to look somewhere for a moment (see HoloAvatar.glance)."""
        try:
            if self._avatar is not None:
                self._avatar.glance(dx, dy, hold)
        except Exception:
            pass

    @property
    def ptt_hold(self):
        return self._win.ptt_hold

    @ptt_hold.setter
    def ptt_hold(self, cb):
        self._win.ptt_hold = cb

    @property
    def on_push_to_talk(self):
        return self._win.on_push_to_talk

    @on_push_to_talk.setter
    def on_push_to_talk(self, cb):
        self._win.on_push_to_talk = cb

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe: post a schedule of (level, openness, width) mouth frames
        for JARVIS's own speech. `at` is the wall-clock time the batch begins to
        sound, not the time of the call. See HudCanvas.push_visemes()."""
        try:
            self._win.hud.push_visemes(frames, hop, at)
        except Exception:
            pass
        # Without this the floating face mouths nothing while the assistant
        # talks — it would sit there breathing, which looks broken rather than
        # muted.
        bubble = getattr(self, "_bubble", None)
        if bubble is not None:
            bubble.push_visemes(frames, hop, at)

    def notify_phone_connected(self) -> None:
        self._win._phone_connected_sig.emit()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)
        # THE TOOLTIP IS THE ONLY STATUS READOUT IN AMBIENT MODE.
        #
        # With no window, "is it listening?" has exactly one answer the user can
        # see without summoning the interface. Cheap: one string assignment and
        # one setToolTip per transition, and `set_state` is called on state
        # changes, not per frame.
        # `getattr` rather than `self._tray`: this facade is built piecemeal in
        # tests and by plugins, and a status update must never be the thing that
        # raises because an attribute was not there. The tray is an extra
        # surface, not a precondition.
        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.set_state(state)
        # The bubble is a SECOND place the state is visible, and it is the only
        # one on screen in bubble mode — a face that keeps breathing while the
        # assistant is asleep would be a lie told in the most visible place.
        bubble = getattr(self, "_bubble", None)
        if bubble is not None:
            bubble.set_state(state)

    def speech_caption(self, event):
        self._win._speech_caption_sig.emit(event)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_code_job(self, job: dict) -> None:
        """Thread-safe: draw the coding agent's live progress in the panel."""
        self._win._codejob_sig.emit(dict(job))

    def show_narrative_content(self, payload: dict) -> dict:
        from ui.visual_bridge import request
        return request(self._win, 'narrative', payload)

    def show_visual_content(self, payload: dict) -> dict:
        from ui.visual_bridge import request
        return request(self._win, 'chart', payload)

    def control_workspace(self, command: dict) -> dict:
        """Worker-only request to the desktop; timeout cancels unstarted work."""
        from core.workspace_control import WorkspaceRequest, validate
        if threading.get_ident() == self._win._ui_thread_id:
            return {"ok": False, "message": "Workspace control must run on a worker thread."}
        try:
            request = WorkspaceRequest(validate(command))
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        self._win._workspace_command_sig.emit(request)
        return request.wait(3.0)

    def assist_ssh(self, command: dict) -> dict:
        """Worker-only request; Qt performs session checks and local approval."""
        from core.ssh_assist import SSHAssistRequest
        if threading.get_ident() == self._win._ui_thread_id:
            return {"ok": False, "message": "SSH assistance must run on a worker thread."}
        try:
            request = SSHAssistRequest(command)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}
        self._win._ssh_assist_sig.emit(request)
        return request.wait(60.0)

    def assist_editor(self, command: dict) -> dict:
        """Worker-only, locally approved access to an exact editor document."""
        from core.editor_assist import EditorRequest
        if threading.get_ident() == self._win._ui_thread_id:
            return {"ok": False, "message": "Editor assistance must run on a worker thread."}
        try:
            request = EditorRequest(command)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}
        self._win._editor_assist_sig.emit(request)
        return request.wait(60.0)

    def read_browser(self, scope="any") -> dict:
        """Request a locally approved read of the active browser, from a worker."""
        from core.browser_read import BrowserReadRequest
        if threading.get_ident() == self._win._ui_thread_id:
            return {"ok": False, "message": "Browser read must run on a worker thread."}
        try:
            request = BrowserReadRequest(scope)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        self._win._browser_read_sig.emit(request)
        return request.wait(60.0)

    def show_quiz(self, topic: str, questions, grade=None) -> None:
        """Thread-safe: put an interactive quiz on the board.

        `grade(question, given)` decides each answer — the plugin supplies it so
        the marking rules live with the questions rather than being duplicated
        here. Returning None from it means "JARVIS should judge this one", which
        is how open answers and near-miss gap-fills are handled.

        Returns immediately: the user answers at their own pace and the finished
        result is delivered back through on_text_command.
        """
        self._win._quiz_sig.emit(str(topic or ""), list(questions or []), grade)

    def hide_quiz(self) -> None:
        """Thread-safe: clear any quiz currently on the board."""
        self._win._quiz_hide_sig.emit()

    def show_review(self, title: str, summary: str, findings, unclear=None) -> None:
        """Thread-safe: lay a document review into the panel below the HUD.

        `findings` is a list of {heading, detail, severity, quote, suggestion};
        severity is one of 'serious' / 'caution' / 'note' and decides colour and
        order here, so the caller supplies no styling of its own.
        """
        self._win._review_sig.emit(str(title or ""), str(summary or ""),
                                   list(findings or []), list(unclear or []))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def show_video(self, source: str, title: str = "", muted: bool = True,
                   audio_source: str = "", fallbacks=None,
                   on_exhausted=None, audio_fallbacks=None) -> None:
        """Thread-safe: play a video where the avatar normally is.

        `source` is a local path or a direct media URL. `audio_source` is for
        the case where the sound arrives as its own stream — YouTube serves no
        combined format any more — and when it is given the two are played
        together and kept in step.

        Muted by default, and that is a decision rather than a default: a
        soundtrack talking over JARVIS is the one way this could make the
        assistant worse. The user turns sound on from the header button or by
        asking, and closes it the same two ways.
        """
        payload = ({"video": list(fallbacks or []),
                    "audio": list(audio_fallbacks)}
                   if audio_fallbacks else list(fallbacks or []))
        self._win._video_open_sig.emit(str(source or ""), str(title or ""),
                                       bool(muted), str(audio_source or ""),
                                       payload, on_exhausted)

    def stop_video(self) -> None:
        """Thread-safe: close the video and give the HUD back to the avatar."""
        self._win._video_close_sig.emit()

    def set_video_muted(self, muted: bool) -> None:
        """Thread-safe: silence or unsilence whatever is playing."""
        self._win._video_mute_sig.emit(bool(muted))

    def video_is_playing(self) -> bool:
        return bool(self._win.video_is_playing())

    # ── audio ──────────────────────────────────────────────────────────────
    # Same rule as everything else here: a plugin thread never touches a widget,
    # it emits and returns. The window's slots run on the Qt thread.

    def play_audio(self, source: str, title: str = "", volume: float = 0.7,
                   loop: bool = False, fallbacks=None,
                   on_exhausted=None) -> None:
        """Thread-safe: play audio — a file, a stream URL, or YouTube audio.

        Sound goes to the output device chosen in AUDIO DEVICES, not to the
        system default, so a song comes out of the speaker the user picked.
        """
        self._win._audio_open_sig.emit(str(source or ""), str(title or ""),
                                       float(volume), bool(loop),
                                       list(fallbacks or []), on_exhausted)

    def stop_audio(self) -> None:
        """Thread-safe: stop the audio and hide its bar."""
        self._win._audio_stop_sig.emit()

    def pause_audio(self, paused: bool = True) -> None:
        """Thread-safe: pause or resume."""
        self._win._audio_pause_sig.emit(bool(paused))

    def set_audio_volume(self, volume: float) -> None:
        """Thread-safe: 0.0 .. 1.0."""
        self._win._audio_vol_sig.emit(float(volume))

    def audio_is_playing(self) -> bool:
        return bool(self._win.audio_is_playing())

    def start_camera_stream(self) -> None:
        """Thread-safe: start the live camera feed in its desktop panel."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")


# ── WHAT THE PACKAGE RE-EXPORTS — AT THE BOTTOM, ON PURPOSE ─────────────────
#
#     `ui/__init__.py` does `from ui.window import *`, and a module without
#     `__all__` exports only the names that do not start with an underscore.
#
#     The list is built from `dir()`, so it can only be complete once every
#     class in this file exists. Written at the top it exported the imports and
#     the first two classes and no widgets at all: `ui.ProvidersOverlay` stopped
#     existing while `ui.MainWindow` still worked — a split that breaks half its
#     callers and leaves the other half green.
#
#     The underscored names are the ones other code reaches for BY NAME
#     (`ui._ScrollSafeCombo` in the provider self-test, `ui._metrics` in this
#     file, `ui._OS` in main.py). A star-import never carries those, so they are
#     listed. Add one when you write `ui._something` somewhere else.
__all__ = [n for n in dir() if not n.startswith("_")]
__all__ += [
    "_OS",
    "_RootShim",
    "_ScrollSafeCombo",
    "_SysMetrics",
    "_WIN_HIDE",
    "_metrics",
    "_nvml_gpu_windows",
    "_auto_ui_scale",
]
