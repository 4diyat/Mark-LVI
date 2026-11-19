"""Interactive, multi-file code editor owned by the Qt thread."""
from __future__ import annotations

import secrets
import threading
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPlainTextEdit, QTabWidget,
                             QToolButton, QVBoxLayout, QWidget)

from core.i18n import label as _t
from plugins import _creative
from ui.theme import C, workspace_stylesheet
from ui.localization import TranslationBindings
from ui.code_editor import CodeEditor
from core.code_syntax import language_for_path


def _tool_icon(kind):
    """Draw small, font-independent editor actions on the Qt thread."""
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(C.DESKTOP_TEXT))
    pen.setWidthF(1.45)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if kind == "open":
        path.moveTo(3, 8)
        path.lineTo(3, 19)
        path.lineTo(20, 19)
        path.lineTo(21, 10)
        path.lineTo(10, 10)
        path.lineTo(8, 7)
        path.lineTo(4, 7)
        path.closeSubpath()
    elif kind in ("save", "save_as"):
        path.addRoundedRect(QRectF(4, 3, 16, 18), 2, 2)
        path.moveTo(8, 3)
        path.lineTo(8, 9)
        path.lineTo(16, 9)
        path.lineTo(16, 3)
        path.moveTo(8, 20)
        path.lineTo(8, 14)
        path.lineTo(16, 14)
        path.lineTo(16, 20)
        if kind == "save_as":
            path.moveTo(16, 17)
            path.lineTo(21, 12)
            path.moveTo(17, 13)
            path.lineTo(21, 12)
            path.lineTo(20, 16)
    elif kind == "run":
        path.moveTo(7, 4)
        path.lineTo(19, 12)
        path.lineTo(7, 20)
        path.closeSubpath()
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class CreativeWorkspace(QDialog):
    _run_done = pyqtSignal(object, str)

    def __init__(self, parent, request):
        super().__init__(parent)
        self._translations = TranslationBindings()
        self._translations.title(self, "creative.title")
        self.resize(850, 680)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(workspace_stylesheet())
        self._host = parent
        self._path = None
        self._paths = {}
        self._run_done.connect(self._on_run_done)
        layout = QVBoxLayout(self)
        self._build_editor(layout)
        code = str(request.get("code") or "")[:100000]
        self._code.setPlainText(code)
        self._code.document().setModified(bool(code))

    def retranslate(self):
        self._translations.refresh()
        for code in self._paths:
            code.setAccessibleName(_t("creative.editor"))
            code.setPlaceholderText(_t("creative.code_placeholder"))
        for button, key in self._editor_tools:
            button.setToolTip(_t(key))
            button.setAccessibleName(_t(key))
        self._refresh_file_tabs()
        self._update_editor_status()

    def _allowed(self, name):
        try:
            return any(row.get("name") == name and row.get("valid") and row.get("enabled")
                       for row in self._host.get_plugins())
        except Exception:
            return False

    def _require(self, name):
        if self._allowed(name):
            return True
        QMessageBox.warning(self, _t("creative.title"), _t("creative.plugin_disabled"))
        return False

    def _build_editor(self, parent_layout):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(5, 5, 5, 5)
        sidebar.setSpacing(4)
        self._editor_tools = []
        for icon, key, callback in (("open", "creative.open", self._open_file),
                                    ("save", "creative.save", self._save_file),
                                    ("save_as", "creative.save_as", self._save_as),
                                    ("run", "creative.run", self._run_file)):
            button = QToolButton()
            button.setIcon(_tool_icon(icon))
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setToolTip(_t(key))
            button.setAccessibleName(_t(key))
            button.setFixedSize(36, 34)
            button.setStyleSheet(f"QToolButton {{ background: transparent; color: {C.DESKTOP_TEXT}; "
                                 "border: 1px solid transparent; border-radius: 6px; padding: 2px; } "
                                 f"QToolButton:hover {{ background: {C.DESKTOP_DOCK}; }} "
                                 "QToolButton:focus { border: 1px solid #4b9fff; }")
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            sidebar.addWidget(button)
            self._editor_tools.append((button, key))
            if key == "creative.run":
                self._run_btn = button
        sidebar.addStretch()
        outer.addLayout(sidebar)
        layout = QVBoxLayout()
        outer.addLayout(layout, 1)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # The tab already labels the current file and exposes its full path in
        # a tooltip; avoid a duplicate path row consuming the code canvas.
        self._file_label = self._translations.text(QLabel(), "creative.unsaved", conditional=True)
        self._file_label.hide()
        self._file_tabs = QTabWidget()
        self._file_tabs.setTabsClosable(True)
        self._file_tabs.setMovable(True)
        self._new_tab_button = QToolButton()
        self._new_tab_button.setText("+")
        self._new_tab_button.setToolTip(_t("editor.new"))
        self._new_tab_button.setAccessibleName(_t("editor.new"))
        self._new_tab_button.clicked.connect(lambda _checked=False: self._new_file())
        self._editor_tools.append((self._new_tab_button, "editor.new"))
        self._file_tabs.setCornerWidget(self._new_tab_button, Qt.Corner.TopRightCorner)
        self._file_tabs.currentChanged.connect(self._select_file_tab)
        self._file_tabs.tabCloseRequested.connect(self._close_file_tab)
        layout.addWidget(self._file_tabs, 1)
        self._editor_status = QLabel()
        self._editor_status.setStyleSheet(f"background: {C.DESKTOP_SIDEBAR}; color: {C.DESKTOP_MUTED}; "
                                          "padding: 4px 8px; border: none;")
        layout.addWidget(self._editor_status)
        self._add_code_tab()
        self._output_heading = self._translations.text(QLabel(), "creative.output")
        layout.addWidget(self._output_heading)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(160)
        layout.addWidget(self._output)
        # Keep the editor readable in the compact desktop layout. The output
        # panel appears as soon as a run or error writes to it.
        self._output_heading.hide()
        self._output.hide()
        self._output.textChanged.connect(self._show_output_when_written)
        parent_layout.addWidget(page)

    def _show_output_when_written(self):
        if self._output.toPlainText():
            self._output_heading.show()
            self._output.show()

    def _add_code_tab(self, text='', path=None, dirty=False):
        code = CodeEditor()
        code._assist_token = secrets.token_hex(16)
        code.setAccessibleName(_t("creative.editor"))
        code.setFont(QFont("Courier New", 10))
        code._update_gutter_width()
        code.setPlaceholderText(_t("creative.code_placeholder"))
        code.setPlainText(text)
        code.document().setModified(dirty)
        self._paths[code] = path
        code.cursorPositionChanged.connect(lambda: self._update_editor_status() if self._code is code else None)
        code.document().modificationChanged.connect(lambda _changed: self._refresh_file_tabs())
        index = self._file_tabs.addTab(code, '')
        self._file_tabs.setCurrentIndex(index)
        self._select_file_tab(index)
        self._refresh_file_tabs()
        return code

    def _select_file_tab(self, index):
        code = self._file_tabs.widget(index) if index >= 0 else None
        if code not in self._paths:
            return
        self._code = code
        self._path = self._paths[code]
        self._file_label.setText(self._path or _t("creative.unsaved"))
        self._update_editor_status()

    def _refresh_file_tabs(self):
        for index in range(self._file_tabs.count()):
            code = self._file_tabs.widget(index)
            path = self._paths.get(code)
            title = Path(path).name if path else _t("creative.unsaved")
            self._file_tabs.setTabText(index, title + (" •" if code.document().isModified() else ""))
            self._file_tabs.setTabToolTip(index, path or _t("creative.unsaved"))

    def _new_file(self):
        if self._require("code_editor"):
            self._add_code_tab()

    def _confirm_discard(self, code):
        if not code.document().isModified():
            return True
        path = self._paths.get(code)
        name = Path(path).name if path else _t("creative.unsaved")
        answer = QMessageBox.question(self, _t("creative.unsaved"),
                                      _t("editor.discard_file", name=name),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _close_file_tab(self, index):
        code = self._file_tabs.widget(index)
        if code not in self._paths or not self._confirm_discard(code):
            return
        # Add the replacement before removing the final tab so there is always
        # a current editor, including while Qt emits currentChanged.
        if self._file_tabs.count() == 1:
            self._add_code_tab()
        self._file_tabs.removeTab(self._file_tabs.indexOf(code))
        self._paths.pop(code, None)
        code.deleteLater()
        self._select_file_tab(self._file_tabs.currentIndex())

    def _update_editor_status(self):
        language = language_for_path(self._path)
        self._code.highlighter.set_language(language)
        cursor = self._code.textCursor()
        self._editor_status.setText(_t('editor.status', language=language.upper(),
                                       line=cursor.blockNumber() + 1,
                                       column=cursor.positionInBlock() + 1))

    def _may_discard(self):
        # All tabs must be confirmed before the window/application is closed.
        return all(self._confirm_discard(code) for code in tuple(self._paths))

    def _open_file(self):
        if not self._require("code_editor"):
            return False
        path, _ = QFileDialog.getOpenFileName(self, _t("creative.open"), "",
                                              "Code (*.py *.js *.mjs *.cjs *.txt);;All files (*)")
        if not path:
            return
        resolved = str(Path(path).resolve())
        for code, existing in self._paths.items():
            if existing and str(Path(existing).resolve()) == resolved:
                self._file_tabs.setCurrentWidget(code)
                return
        try:
            text = _creative.read_code(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self._output.setPlainText(str(exc))
            return
        if not self._path and not self._code.document().isModified() and not self._code.toPlainText():
            self._path = path
            self._paths[self._code] = path
            self._code._assist_token = secrets.token_hex(16)
            self._code.setPlainText(text)
            self._code.document().setModified(False)
            self._file_label.setText(path)
            self._update_editor_status()
            self._refresh_file_tabs()
        else:
            self._add_code_tab(text, path)

    def _save_as(self):
        if not self._require("code_editor"):
            return False
        path, _ = QFileDialog.getSaveFileName(self, _t("creative.save_as"), self._path or "",
                                              "Python (*.py);;JavaScript (*.js);;Text (*.txt);;All files (*)")
        if not path:
            return False
        return self._write(path)

    def _save_file(self):
        if not self._require("code_editor"):
            return False
        return self._write(self._path) if self._path else self._save_as()

    def _write(self, path):
        resolved = str(Path(path).resolve())
        if any(code is not self._code and existing and str(Path(existing).resolve()) == resolved
               for code, existing in self._paths.items()):
            self._output.setPlainText(_t("editor.already_open"))
            return False
        try:
            _creative.write_code(path, self._code.toPlainText())
        except (OSError, ValueError, UnicodeError) as exc:
            self._output.setPlainText(str(exc))
            return False
        if self._path != path:
            self._code._assist_token = secrets.token_hex(16)
        self._path = path
        self._paths[self._code] = path
        self._file_label.setText(path)
        self._code.document().setModified(False)
        self._refresh_file_tabs()
        self._update_editor_status()
        return True

    def _run_file(self):
        if not self._require("code_editor"):
            return False
        if not self._path or self._code.document().isModified():
            self._output.setPlainText(_t("creative.save_before_run"))
            return
        path = self._path
        answer = QMessageBox.question(self, _t("creative.run"),
                                      _t("creative.run_warning", path=path),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_btn.setEnabled(False)
        self._output.setPlainText(_t("creative.running"))

        def worker():
            try:
                rc, output = _creative.run_code(path)
                summary = _t("creative.timed_out") if rc is None else _t("creative.exit_code", code=rc)
            except Exception as exc:
                summary, output = _t("creative.run_error"), str(exc)
            try:
                self._run_done.emit(summary, output)
            except RuntimeError:
                pass  # dialog closed while the process was running
        threading.Thread(target=worker, daemon=True, name="creative-run").start()

    def _on_run_done(self, summary, output):
        self._run_btn.setEnabled(True)
        self._output.setPlainText(f"{summary}\n{output}")

    def closeEvent(self, event):
        if self._may_discard():
            event.accept()
        else:
            event.ignore()


def open_workspace(window, request):
    """Called only on the main thread by MainWindow's existing code-job signal."""
    if request.get("tab", "editor") != "editor":
        window.write_log(_t("editor.unsupported_workspace"))
        return
    try:
        allowed = any(row.get("name") == "code_editor" and row.get("valid") and row.get("enabled")
                      for row in window.get_plugins())
    except Exception:
        allowed = False
    if not allowed:
        window.write_log(_t("creative.plugin_disabled"))
        return
    dialog = CreativeWorkspace(window, request)
    # Keep every open workspace alive, including one with unsaved work.
    if not hasattr(window, "_creative_dialogs"):
        window._creative_dialogs = set()
    window._creative_dialogs.add(dialog)
    dialog.destroyed.connect(lambda: window._creative_dialogs.discard(dialog))
    from ui.desktop_workspace import show_document
    return show_document(window, dialog, "code_editor")
