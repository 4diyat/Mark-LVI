"""Interactive code editor and AI image canvas, owned by the Qt thread."""
from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
                             QVBoxLayout, QWidget)

from core.i18n import label as _t
from plugins import _creative
from ui.theme import C


class CreativeWorkspace(QDialog):
    _run_done = pyqtSignal(object, str)
    _image_done = pyqtSignal(object, str)

    def __init__(self, parent, request):
        super().__init__(parent)
        self.setWindowTitle(_t("creative.title"))
        self.resize(850, 680)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(f"QDialog, QWidget {{ background: #001018; color: {C.TEXT}; }} "
                           f"QPushButton, QLineEdit, QPlainTextEdit {{ background: #001c25; "
                           f"color: {C.TEXT}; border: 1px solid {C.BORDER}; padding: 5px; }}")
        self._host = parent
        self._path = None
        self._image = None
        self._run_done.connect(self._on_run_done)
        self._image_done.connect(self._on_image_done)
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)
        self._build_editor()
        self._build_canvas()
        self._tabs.setTabEnabled(0, self._allowed("code_editor"))
        self._tabs.setTabEnabled(1, self._allowed("image_canvas"))
        if request.get("tab") == "canvas":
            self._tabs.setCurrentIndex(1)
            self._prompt.setPlainText(str(request.get("prompt") or "")[:5000])
        else:
            code = str(request.get("code") or "")[:100000]
            self._code.setPlainText(code)
            self._code.document().setModified(bool(code))

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

    def _button(self, label, slot, row):
        btn = QPushButton(_t(label))
        btn.clicked.connect(slot)
        row.addWidget(btn)
        return btn

    def _build_editor(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self._file_label = QLabel(_t("creative.unsaved"))
        layout.addWidget(self._file_label)
        self._code = QPlainTextEdit()
        self._code.setFont(QFont("Courier New", 10))
        self._code.setPlaceholderText(_t("creative.code_placeholder"))
        layout.addWidget(self._code, 1)
        row = QHBoxLayout()
        self._button("creative.open", self._open_file, row)
        self._button("creative.save", self._save_file, row)
        self._button("creative.save_as", self._save_as, row)
        self._run_btn = self._button("creative.run", self._run_file, row)
        layout.addLayout(row)
        layout.addWidget(QLabel(_t("creative.output")))
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(160)
        layout.addWidget(self._output)
        self._tabs.addTab(page, _t("creative.editor"))

    def _build_canvas(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(_t("creative.prompt")))
        self._prompt = QPlainTextEdit()
        self._prompt.setMaximumHeight(100)
        self._prompt.setPlaceholderText(_t("creative.prompt_placeholder"))
        layout.addWidget(self._prompt)
        row = QHBoxLayout()
        self._generate_btn = self._button("creative.generate", self._generate, row)
        self._save_image_btn = self._button("creative.save_image", self._save_image, row)
        self._save_image_btn.setEnabled(False)
        layout.addLayout(row)
        self._image_label = QLabel(_t("creative.image_empty"))
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(250, 200)
        layout.addWidget(self._image_label, 1)
        self._image_status = QLabel(_t("creative.image_notice"))
        self._image_status.setWordWrap(True)
        layout.addWidget(self._image_status)
        self._tabs.addTab(page, _t("creative.canvas"))

    def _may_discard(self):
        if not self._code.document().isModified():
            return True
        answer = QMessageBox.question(self, _t("creative.unsaved"), _t("creative.discard"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _open_file(self):
        if not self._require("code_editor"):
            return False
        if not self._may_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, _t("creative.open"), "",
                                              "Code (*.py *.js *.mjs *.cjs *.txt);;All files (*)")
        if not path:
            return
        try:
            text = _creative.read_code(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self._output.setPlainText(str(exc))
            return
        self._path = path
        self._code.setPlainText(text)
        self._code.document().setModified(False)
        self._file_label.setText(path)

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
        try:
            _creative.write_code(path, self._code.toPlainText())
        except (OSError, ValueError, UnicodeError) as exc:
            self._output.setPlainText(str(exc))
            return False
        self._path = path
        self._file_label.setText(path)
        self._code.document().setModified(False)
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

    def _generate(self):
        if not self._require("image_canvas"):
            return False
        prompt = self._prompt.toPlainText().strip()
        if not prompt or len(prompt) > 5000:
            self._image_status.setText(_t("creative.prompt_invalid"))
            return
        self._generate_btn.setEnabled(False)
        self._image_status.setText(_t("creative.generating"))

        def worker():
            try:
                from memory.config_manager import get_gemini_key
                data, _mime = _creative.generate_image(prompt, get_gemini_key() or "")
                error = ""
            except Exception as exc:
                data, error = None, str(exc)
            try:
                self._image_done.emit(data, error)
            except RuntimeError:
                pass
        threading.Thread(target=worker, daemon=True, name="creative-image").start()

    def _on_image_done(self, data, error):
        self._generate_btn.setEnabled(True)
        if error:
            self._image_status.setText(_t("creative.image_error", error=error[:500]))
            return
        image = QPixmap()
        if not image.loadFromData(data):
            self._image_status.setText(_t("creative.invalid_image"))
            return
        self._image = image
        self._save_image_btn.setEnabled(True)
        self._image_status.setText(_t("creative.image_ready"))
        self._redraw_image()

    def _redraw_image(self):
        if self._image is not None:
            self._image_label.setPixmap(self._image.scaled(
                self._image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_image_label"):
            self._redraw_image()

    def _save_image(self):
        if not self._require("image_canvas"):
            return False
        if self._image is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, _t("creative.save_image"), "image.png",
                                              "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        if not self._image.save(path):
            self._image_status.setText(_t("creative.image_save_error"))
        else:
            self._image_status.setText(_t("creative.image_saved", path=path))

    def closeEvent(self, event):
        if self._may_discard():
            event.accept()
        else:
            event.ignore()


def open_workspace(window, request):
    """Called only on the main thread by MainWindow's existing code-job signal."""
    name = "image_canvas" if request.get("tab") == "canvas" else "code_editor"
    try:
        allowed = any(row.get("name") == name and row.get("valid") and row.get("enabled")
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
    dialog.show()
    dialog.raise_()
